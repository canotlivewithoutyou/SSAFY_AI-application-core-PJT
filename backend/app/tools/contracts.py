"""Shared success/failure envelope for all external tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ToolError:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def success(data: dict[str, Any]) -> ToolResult:
    return ToolResult(ok=True, data=data)


def failure(code: str, message: str) -> ToolResult:
    return ToolResult(ok=False, error=ToolError(code=code, message=message))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., ToolResult] | None = None

    @property
    def implemented(self) -> bool:
        return self.handler is not None

    def public_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "implemented": self.implemented,
        }

