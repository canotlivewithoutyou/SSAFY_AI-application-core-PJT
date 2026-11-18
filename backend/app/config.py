"""Environment-driven application settings.

Secrets are only read here and are never included in API responses or logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(_text(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _database_path() -> Path:
    configured = Path(_text("DATABASE_PATH", "backend/data/planner.db"))
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / configured


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_env: str
    api_prefix: str
    database_path: Path
    cors_origins: tuple[str, ...]
    replan_limit: int
    upstream_timeout_seconds: int
    openai_api_key: str
    openai_model: str
    kakao_rest_api_key: str
    nmc_service_key: str

    def integration_status(self) -> dict[str, bool]:
        """Return presence flags only; never return credential values."""

        return {
            "llm": bool(self.openai_api_key and self.openai_model),
            "kakao": bool(self.kakao_rest_api_key),
            "medical_data": bool(self.nmc_service_key),
        }

    def missing_integration_settings(self) -> list[str]:
        missing: list[str] = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.openai_model:
            missing.append("OPENAI_MODEL")
        if not self.kakao_rest_api_key:
            missing.append("KAKAO_REST_API_KEY")
        if not self.nmc_service_key:
            missing.append("NMC_SERVICE_KEY")
        return missing


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    origins = tuple(
        origin.strip()
        for origin in _text(
            "CORS_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500",
        ).split(",")
        if origin.strip()
    )
    return Settings(
        app_name="Night & Holiday Visit Planner",
        app_env=_text("APP_ENV", "local"),
        api_prefix="/api/v1",
        database_path=_database_path(),
        cors_origins=origins,
        replan_limit=_positive_int("REPLAN_LIMIT", 5),
        upstream_timeout_seconds=_positive_int("UPSTREAM_TIMEOUT_SECONDS", 10),
        openai_api_key=_text("OPENAI_API_KEY"),
        openai_model=_text("OPENAI_MODEL"),
        kakao_rest_api_key=_text("KAKAO_REST_API_KEY"),
        nmc_service_key=_text("NMC_SERVICE_KEY"),
    )


async def settings_dependency() -> Settings:
    """FastAPI dependency that avoids an unnecessary worker-thread hop."""

    return get_settings()

