from __future__ import annotations

from typing import Any

from storage import get_storage


class BlackroomCountdownService:
    def __init__(self, storage: Any = None) -> None:
        self.storage = get_storage() if storage is None else storage

    def run(self) -> dict[str, Any]:
        try:
            data = self.storage.countdown_blackroom_records()
            return self._result(True, "OK", "countdown completed", data)
        except Exception as exc:  # noqa: BLE001
            return self._result(False, "STORAGE_ERROR", str(exc), None)

    @staticmethod
    def _result(success: bool, code: str, message: str, data: Any) -> dict[str, Any]:
        return {"success": success, "code": code, "message": message, "data": data}
