from enum import StrEnum


class MonitorMarket(StrEnum):
    A = "A"
    HK = "HK"
    ETF = "ETF"


class MonitorFrequency(StrEnum):
    DAILY = "daily"
    INTRADAY = "intraday"


class MonitorResetMode(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class ForecastSSFCandidateState(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    DEFERRED = "deferred"
    PAUSED = "paused"
    BLACKROOM = "blackroom"
    DELISTED_OR_UNLISTED = "delisted_or_unlisted"
