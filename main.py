import os
import re
import asyncio

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

import discord
from discord.ext import commands
from google import genai
from google.genai import types

app = FastAPI()

# CORS 설정 (HTML에서 API 요청 가능하도록 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 전부 환경변수에서 읽어옴 (Render > 서비스 > Environment 에 등록) ----
DATABASE_URL = os.getenv("DATABASE_URL")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
WEB_EV_URL = os.getenv("WEB_EV_URL", "").rstrip("/")  # 예: https://ev-frontend.onrender.com

SYSTEM_INSTRUCTION = (
    "너는 EV AI야. 사용자가 프로그램/앱/게임을 만들거나 수정해달라고 하면, "
    "완전하고 실행 가능한 단일 HTML 파일 전체를 하나의 ```html 코드 블록으로만 답해. "
    "코드 블록 앞뒤에 다른 설명은 쓰지 마."
)


def get_engine():
    db_url = DATABASE_URL.replace("postgres://", "postgresql://")
    return create_engine(db_url)


def ensure_table():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            topic TEXT NOT NULL,
            change_prmpt1 TEXT,
            change_log1 TEXT,
            change_prmpt2 TEXT,
            change_log2 TEXT,
            change_prmpt3 TEXT,
            change_log3 TEXT,
            change_prmpt4 TEXT,
            change_log4 TEXT
        );
        """))
        conn.commit()


@app.on_event("startup")
def on_startup_db():
    ensure_table()


# ---------------------------------------------------------------
# 저장/조회 로직을 함수로 분리 — HTTP 엔드포인트와 디스코드 봇이 같이 씀
# ---------------------------------------------------------------

def create_project(topic: str, code: str) -> int:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO projects (topic, change_prmpt1, change_log1)
                VALUES (:tpc, :prmpt, :log)
                RETURNING id
            """),
            {"tpc": topic, "prmpt": topic, "log": code}
        )
        new_id = result.fetchone()[0]

        if conn.execute(text("SELECT COUNT(*) FROM projects")).fetchone()[0] > 6:
            conn.execute(text("DELETE FROM projects WHERE id = (SELECT MIN(id) FROM projects)"))

        conn.commit()
    return new_id


def add_log(pjt_id: int, prompt_txt: str, code: str) -> bool:
    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT id FROM projects WHERE id = :pjt_id"),
            {"pjt_id": pjt_id}
        ).fetchone()
        if not exists:
            return False

        conn.execute(
            text("""
                UPDATE projects
                SET
                    change_prmpt4 = change_prmpt3,
                    change_log4   = change_log3,
                    change_prmpt3 = change_prmpt2,
                    change_log3   = change_log2,
                    change_prmpt2 = change_prmpt1,
                    change_log2   = change_log1,
                    change_prmpt1 = :prmpt,
                    change_log1   = :log
                WHERE id = :pjt_id
            """),
            {"pjt_id": pjt_id, "prmpt": prompt_txt, "log": code}
        )
        conn.commit()
    return True


def get_latest_code(pjt_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT change_log1 FROM projects WHERE id = :pjt_id"),
            {"pjt_id": pjt_id}
        ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------
# 기존 HTTP 엔드포인트 (동작은 그대로, 내부만 위 함수로 재사용)
# ---------------------------------------------------------------

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Server is Running"}


@app.get("/make_db_tbale")
def mktb():
    ensure_table()
    return {"status": "ok"}


@app.post("/save/pjt")
async def save_pjt(request: Request):
    body = await request.json()
    new_id = create_project(body.get("prmpt_txt", ""), body.get("code_ctnt", ""))
    return {"status": "ok", "id": new_id}


@app.post("/save/{pjt_id}/log")
async def save_log(pjt_id: int, request: Request):
    body = await request.json()
    ok = add_log(pjt_id, body.get("prmpt_txt", ""), body.get("code_ctnt", ""))
    if not ok:
        raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")
    return {"status": "ok"}


@app.get("/load/history/list")
def load_his_list():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, topic FROM projects ORDER BY id DESC")).fetchall()
    return {"status": "ok", "projects": [{"id": r[0], "topic": r[1]} for r in result]}


@app.get("/load/history/{pjt_id}")
def load_his_val(pjt_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT change_prmpt1, change_log1 FROM projects WHERE id = :pjt_id"),
            {"pjt_id": pjt_id}
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")
    return {"status": "ok", "data": {"change_prmpt1": row[0], "change_log1": row[1]}}


@app.get("/load/logs/{pjt_id}")
def load_log_val(pjt_id: int):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT change_prmpt1, change_log1,
                       change_prmpt2, change_log2,
                       change_prmpt3, change_log3,
                       change_prmpt4, change_log4
                FROM projects WHERE id = :pjt_id
            """),
            {"pjt_id": pjt_id}
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")
    return {
        "status": "ok",
        "data": {
            "change_prmpt1": row[0], "change_log1": row[1],
            "change_prmpt2": row[2], "change_log2": row[3],
            "change_prmpt3": row[4], "change_log3": row[5],
            "change_prmpt4": row[6], "change_log4": row[7],
        }
    }

# /load/logs/list 는 여전히 제거된 상태예요.


# ---------------------------------------------------------------
# 디스코드 봇 — 같은 프로세스에서 asyncio 백그라운드 태스크로 실행
# ---------------------------------------------------------------

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

intents = discord.Intents.default()
intents.message_content = True  # Developer Portal에서 Message Content Intent 켜져 있어야 함
bot = commands.Bot(command_prefix="!", intents=intents)


def extract_html(text_out: str):
    m = re.search(r"```(?:html)?\s*([\s\S]*?)```", text_out, re.IGNORECASE)
    return m.group(1).strip() if m else None


def ask_gemini(prompt: str) -> str:
    config = types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)
    response = ai_client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=config
    )
    return response.text


def preview_link(pjt_id: int) -> str:
    if not WEB_EV_URL:
        return "(WEB_EV_URL 환경변수가 아직 없어서 링크를 못 만들었어요)"
    return f"{WEB_EV_URL}/?id={pjt_id}"


@bot.event
async def on_ready():
    print(f'🤖 EV AI 파이썬 봇 준비 완료: {bot.user.name}')


@bot.command(name="ev")
async def handle_ev_ai(ctx, *, prompt: str):
    """사용법: !ev [만들고 싶은 것 설명] → 새 히스토리로 저장 + 미리보기 링크"""
    async with ctx.typing():
        try:
            result_text = ask_gemini(prompt)
            code = extract_html(result_text)
            if code:
                new_id = create_project(prompt, code)
                await ctx.send(f"✅ 완성했어요! (히스토리 #{new_id})\n미리보기: {preview_link(new_id)}")
            else:
                for i in range(0, len(result_text), 1900):
                    await ctx.send(result_text[i:i + 1900])
        except Exception as e:
            await ctx.send(f"⚠️ EV AI 처리 중 오류가 발생했습니다: {str(e)}")


@bot.command(name="ev-edit")
async def handle_ev_edit(ctx, pjt_id: int, *, prompt: str):
    """사용법: !ev-edit [히스토리 번호] [수정 요청] → 기존 히스토리에 로그로 이어붙임"""
    async with ctx.typing():
        try:
            prev_code = get_latest_code(pjt_id)
            if prev_code is None:
                await ctx.send(f"⚠️ #{pjt_id} 히스토리를 찾을 수 없어요.")
                return
            full_prompt = f"기존 코드:\n```html\n{prev_code}\n```\n\n위 코드에 대한 수정 요청: {prompt}"
            result_text = ask_gemini(full_prompt)
            code = extract_html(result_text)
            if code:
                add_log(pjt_id, prompt, code)
                await ctx.send(f"✅ 수정했어요! (히스토리 #{pjt_id})\n미리보기: {preview_link(pjt_id)}")
            else:
                for i in range(0, len(result_text), 1900):
                    await ctx.send(result_text[i:i + 1900])
        except Exception as e:
            await ctx.send(f"⚠️ EV AI 처리 중 오류가 발생했습니다: {str(e)}")


_bot_task = None  # 가비지 컬렉션 방지용 참조 보관


@app.on_event("startup")
async def start_discord_bot():
    global _bot_task
    if DISCORD_TOKEN and ai_client:
        _bot_task = asyncio.create_task(bot.start(DISCORD_TOKEN))
    else:
        print("⚠️ DISCORD_TOKEN 또는 GEMINI_API_KEY가 없어서 디스코드 봇은 시작하지 않았어요.")
