from enum import StrEnum


class AccountStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class MigrationRepairReason(StrEnum):
    LEGACY_ORDERING_UNCERTAIN = "legacy_ordering_uncertain"


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


class Market(StrEnum):
    A_SHARE = "a_share"
    HK_CONNECT = "hk_connect"
    ETF = "etf"


class CashEventType(StrEnum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FREEZE = "freeze"
    RELEASE = "release"
    TRADE = "trade"
    FEE = "fee"
    CORPORATE_ACTION = "corporate_action"


class CorporateActionType(StrEnum):
    DIVIDEND = "dividend"
    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    BONUS_SHARE = "bonus_share"
    RIGHTS_ISSUE = "rights_issue"


class CorporateActionProcessingStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class MatchingRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class TradeValidityStatus(StrEnum):
    VALID = "valid"
    SUSPICIOUS = "suspicious"
    INVALID = "invalid"
    UNCHECKED = "unchecked"


class FeePreset(StrEnum):
    A_SHARE = "a_share"


class PositionSource(StrEnum):
    TRADE = "trade"
    IMPORTED = "imported"


class PendingSettlementSource(StrEnum):
    HK_SELL = "hk_sell"


class RoundTripStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class TradeValidityGranularity(StrEnum):
    DAILY = "daily"


class LedgerRebuildStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ETFEligibilityStatus(StrEnum):
    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    MONEY_MARKET = "money_market"
    DISABLED = "disabled"


class SnapshotPointType(StrEnum):
    INITIAL = "initial"
    TRADING = "trading"


class SnapshotQualityStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class SnapshotValuationQuality(StrEnum):
    CURRENT = "current"
    STALE_SUSPENDED = "stale_suspended"


class ReplayTimeProvenance(StrEnum):
    CANONICAL_UTC = "canonical_utc"


class NavReplayEventType(StrEnum):
    INITIAL = "initial"
    CASH_FLOW = "cash_flow"
    TRADE_SETTLEMENT = "trade_settlement"
    CORPORATE_ACTION = "corporate_action"
    MARKET_VALUATION = "market_valuation"


class NavBaselineEligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


# Marker prefix for rejection reasons set by OrderDeleteService replay.
# reset_orders_for_replay uses this to distinguish replay-induced rejections
# (which may become resolvable after a later delete) from original/business
# rejections (which should persist).
REPLAY_REJECTION_MARKER = "[replay]"
