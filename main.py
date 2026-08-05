import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

app = FastAPI()

# CORS 설정 (HTML에서 API 요청 가능하도록 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 배포 후 특정 domain으로 제한 가능
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 환경 변수에서 DB 주소를 불러옵니다 (Render 환경변수에 등록 예정)
DATABASE_URL = os.getenv("DATABASE_URL")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "API Server is Running"}

@app.get("/make_db_tbale")
def mktb():
    db_url = DATABASE_URL.replace("postgres://", "postgresql://")
    engine = create_engine(db_url)
    
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

@app.post("/save/pjt")
def save_pjt(prmpt_txt: str, code_ctnt: str):
    db_url = DATABASE_URL.replace("postgres://", "postgresql://")
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        conn.execute(text("""insert into projects (topic,change_prmpt1,change_log1) values (:tpc,:prmpt,:log)"""),{"tpc":prmpt_txt,"prmpt":prmpt_txt,"log":code_ctnt})
        if conn.execute(text("SELECT COUNT(*) FROM projects")).fetchone()[0]>=6:
            conn.execute(text("delete from projects where id = (select min(id) from projects)"))
                
        conn.commit()

@app.post("/save/{pjt_id}/log")
def save_log(pjt_id:int, prmpt_txt: str, code_ctnt: str):
    db_url = DATABASE_URL.replace("postgres://", "postgresql://")
    engine = create_engine(db_url)

    with engine.connect() as conn:
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

# Neon DB 테스트용 API
@app.get("/db-test")
def test_db():
    if not DATABASE_URL:
        return {"error": "DATABASE_URL이 설정되지 않았습니다."}
    
    # postgres:// 를 postgresql:// 로 변경 (SQLAlchemy 호환)
    db_url = DATABASE_URL.replace("postgres://", "postgresql://")
    engine = create_engine(db_url)
    
    with engine.connect() as connection:
        result = connection.execute(text("SELECT NOW();"))
        row = result.fetchone()
        return {"db_time": str(row[0])}
