"""Compatibility wrapper for the renamed blackroom business service."""

from __future__ import annotations

from typing import Any

from monitor.blackroom_service import (
    BlackroomNotFoundError,
    BlackroomService,
    BlackroomValidationError,
)
from storage import get_storage

__all__ = [
    "BlackroomManagementService",
    "BlackroomNotFoundError",
    "BlackroomValidationError",
]


class BlackroomManagementService(BlackroomService):
    """Backward-compatible name for BlackroomService."""

    def __init__(self, storage: Any = None) -> None:
        super().__init__(get_storage() if storage is None else storage)
