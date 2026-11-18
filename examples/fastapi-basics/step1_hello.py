"""1단계 — 첫 서버와 /docs

실행:
    uvicorn step1_hello:app --reload

확인:
    http://localhost:8000         JSON 이 보인다
    http://localhost:8000/docs    자동으로 만들어진 API 문서
"""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    #dict 반환 -> JSON 
    return {"message": "Movie Planner API"}

