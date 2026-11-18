"""Service health and non-secret setup visibility."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, settings_dependency
from ..database import is_database_ready
from ..tools import catalog


router = APIRouter(tags=["system"])


@router.get("/health")
async def health(settings: Settings = Depends(settings_dependency)) -> dict:
    database_ready = is_database_ready(settings.database_path)
    return {
        "status": "ok" if database_ready else "degraded",
        "environment": settings.app_env,
        "database": "ready" if database_ready else "unavailable",
        "integrations": settings.integration_status(),
    }


@router.get("/meta/tools")
async def tool_catalog() -> dict:
    return {"tools": catalog()}

