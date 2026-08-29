from typing import Any


class PaperTradingError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class CorporateActionError(PaperTradingError):
    """Base error for invalid corporate-action domain operations."""


class InvalidCorporateActionParametersError(CorporateActionError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("INVALID_CORPORATE_ACTION_PARAMETERS", message, details)


class InvalidCorporateActionInputError(CorporateActionError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__("INVALID_CORPORATE_ACTION_INPUT", message, details)


class UnknownCorporateActionTypeError(CorporateActionError):
    def __init__(self, event_type: Any):
        super().__init__(
            "UNKNOWN_CORPORATE_ACTION_TYPE",
            f"unknown corporate action type: {event_type}",
            {"event_type": str(event_type)},
        )


class InsufficientRightsCashError(CorporateActionError):
    def __init__(self, available: Any, required: Any):
        super().__init__(
            "INSUFFICIENT_RIGHTS_CASH",
            "Insufficient available cash to subscribe to rights issue",
            {"available": str(available), "required": str(required)},
        )
