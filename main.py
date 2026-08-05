import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

app = FastAPI()

# CORS 설정 (HTML에서 API 요청 가능하도록 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 배포 후 특정 domain으로 제한 가능
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 환경 변수에서 DB 주소를 불러옵니다 (Render 환경변수에 등록 예정)
DATABASE_URL = os.getenv("DATABASE_URL")


def get_engine():
    db_url = DATABASE_URL.replace("postgres://", "postgresql://")
    return create_engine(db_url)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Server is Running"}


@app.get("/make_db_tbale")
def mktb():
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
        conn.commit()  # 원래 코드엔 commit()이 없어서 테이블 생성이 실제로 반영 안 될 수 있었어요.
    return {"status": "ok"}


@app.post("/save/pjt")
async def save_pjt(request: Request):
    body = await request.json()
    prmpt_txt = body.get("prmpt_txt", "")
    code_ctnt = body.get("code_ctnt", "")

    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                INSERT INTO projects (topic, change_prmpt1, change_log1)
                VALUES (:tpc, :prmpt, :log)
                RETURNING id
            """),
            {"tpc": prmpt_txt, "prmpt": prmpt_txt, "log": code_ctnt}
        )
        new_id = result.fetchone()[0]

        if conn.execute(text("SELECT COUNT(*) FROM projects")).fetchone()[0] > 6:
            conn.execute(text("DELETE FROM projects WHERE id = (SELECT MIN(id) FROM projects)"))

        conn.commit()

    return {"status": "ok", "id": new_id}


@app.post("/save/{pjt_id}/log")
async def save_log(pjt_id: int, request: Request):
    body = await request.json()
    prmpt_txt = body.get("prmpt_txt", "")
    code_ctnt = body.get("code_ctnt", "")

    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT id FROM projects WHERE id = :pjt_id"),
            {"pjt_id": pjt_id}
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="해당 프로젝트를 찾을 수 없습니다.")

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
            {"pjt_id": pjt_id, "prmpt": prmpt_txt, "log": code_ctnt}
        )
        conn.commit()

    return {"status": "ok"}


@app.get("/load/history/list")
def load_his_list():
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, topic FROM projects ORDER BY id DESC")).fetchall()

    project_list = [{"id": row[0], "topic": row[1]} for row in result]
    return {"status": "ok", "projects": project_list}


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

# /load/logs/list 는 말씀대로 뺐어요. (history/list랑 목적이 겹치고, 원래 SQL에 콤마 오타도 있었어요)
