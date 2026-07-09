"""Shared contracts used by every Agent-callable Tool.

Tool handlers never leak an upstream exception to the graph. They always return
the same ``ok/data`` or ``ok/error`` envelope so the Agent can decide whether to
ask the user, skip a candidate, or stop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal


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

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ToolResult":
        raw_error = value.get("error")
        error = ToolError(**raw_error) if raw_error else None
        return cls(ok=bool(value.get("ok")), data=value.get("data"), error=error)


def success(data: dict[str, Any]) -> ToolResult:
    return ToolResult(ok=True, data=data)


def failure(code: str, message: str) -> ToolResult:
    return ToolResult(ok=False, error=ToolError(code=code, message=message))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    use_when: str
    parameters: dict[str, Any]
    output_schema: dict[str, Any]
    failure_codes: tuple[str, ...]
    kind: Literal["external_api", "local_api"] = "external_api"
    handler: Callable[..., ToolResult] | None = None

    @property
    def implemented(self) -> bool:
        return self.handler is not None

    def public_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "use_when": self.use_when,
            "kind": self.kind,
            "parameters": self.parameters,
            "output_schema": self.output_schema,
            "failure_codes": list(self.failure_codes),
            "response_envelope": {
                "success": {"ok": True, "data": "object", "error": None},
                "failure": {
                    "ok": False,
                    "data": None,
                    "error": {"code": "string", "message": "string"},
                },
            },
            "implemented": self.implemented,
        }

    def llm_definition(self) -> dict[str, Any]:
        """Return the OpenAI/LangChain function schema for this Tool."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"{self.use_when} {self.description}",
                "parameters": self.parameters,
            },
        }

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        if self.handler is None:
            return failure("NOT_IMPLEMENTED", f"{self.name} Tool이 등록되지 않았습니다.")
        try:
            result = self.handler(**arguments)
        except TypeError:
            return failure("INVALID_INPUT", "Tool 입력 형식이 명세와 일치하지 않습니다.")
        except Exception:
            return failure("INTERNAL_ERROR", "Tool 처리 중 예기치 못한 오류가 발생했습니다.")
        if not isinstance(result, ToolResult):
            return failure("INVALID_HANDLER_RESULT", "Tool 응답 형식이 올바르지 않습니다.")
        return result

