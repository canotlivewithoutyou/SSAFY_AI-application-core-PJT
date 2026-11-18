"""6 · 7단계 — 라우터를 붙이고, 화면(index.html)이 부를 수 있게 CORS 를 연다

실행 (1일차 폴더에서, app 폴더 바깥):
    uvicorn app.main:app --reload

화면은 터미널을 하나 더 열어 띄운다:
    python -m http.server 5500      →  http://localhost:5500
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import plans

app = FastAPI(title="Movie Planner")

app.add_middleware(              
    CORSMiddleware,
    allow_origins=["http://localhost:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plans.router)   
