from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    NEW = "new"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class CashEventType(StrEnum):
    DEPOSIT = "deposit"
    FREEZE = "freeze"
    RELEASE = "release"
    TRADE = "trade"
    FEE = "fee"


class MatchingRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TradeValidityStatus(StrEnum):
    VALID = "valid"
    SUSPICIOUS = "suspicious"
    INVALID = "invalid"
    UNCHECKED = "unchecked"


# Marker prefix for rejection reasons set by OrderDeleteService replay.
# reset_orders_for_replay uses this to distinguish replay-induced rejections
# (which may become resolvable after a later delete) from original/business
# rejections (which should persist).
REPLAY_REJECTION_MARKER = "[replay]"
