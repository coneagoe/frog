"""Compatibility wrapper for the renamed blackroom business service."""

from __future__ import annotations

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

    def __init__(self, storage=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(get_storage() if storage is None else storage)
