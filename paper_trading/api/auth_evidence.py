"""Small, passive helpers for authentication incident evidence."""

from __future__ import annotations

import json
import uuid
from enum import StrEnum

from starlette.requests import Request


class AuthEvidenceCode(StrEnum):
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTH_INVALID_CREDENTIALS = "AUTH_INVALID_CREDENTIALS"
    AUTH_RATE_LIMITED = "AUTH_RATE_LIMITED"
    AUTH_UNAVAILABLE = "AUTH_UNAVAILABLE"
    SESSION_INVALID = "SESSION_INVALID"


def new_request_id() -> str:
    return str(uuid.uuid4())


def validate_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    return value if parsed.version == 4 and parsed.variant == uuid.RFC_4122 else None


def request_id_from_request(request: Request) -> str:
    return validate_request_id(request.headers.get("X-Request-ID")) or new_request_id()


def allowed_evidence_path(path: str) -> bool:
    return path == "/auth" or path.startswith("/auth/") or path == "/paper" or path.startswith("/paper/")


def render_evidence(code: AuthEvidenceCode, path: str, request_id: str | None = None) -> str:
    if not allowed_evidence_path(path):
        raise ValueError("Evidence path is not allowlisted")
    payload: dict[str, str] = {"code": code.value, "path": path}
    if request_id is not None and validate_request_id(request_id) is not None:
        payload["request_id"] = request_id
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def error_detail(code: AuthEvidenceCode, message: str, request_id: str | None = None) -> dict[str, object]:
    detail: dict[str, object] = {"code": code.value, "message": message, "details": {}}
    if request_id is not None:
        detail["request_id"] = request_id
    return detail
