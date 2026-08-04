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