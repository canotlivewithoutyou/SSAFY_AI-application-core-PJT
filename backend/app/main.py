"""FastAPI application factory and router wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import chat, health, logs, plans
from .config import get_settings
from .database import initialize_database


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(settings.database_path)
    yield


app = FastAPI(
    title="전국 야간·휴일 병원·약국 방문 플래너",
    description=(
        "출발 시각, 실제 차량 이동시간, 공개 운영시간을 함께 확인하는 방문 플래너 API"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(plans.router, prefix=settings.api_prefix)
app.include_router(logs.router, prefix=settings.api_prefix)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "health": f"{settings.api_prefix}/health",
        "docs": "/docs",
    }

