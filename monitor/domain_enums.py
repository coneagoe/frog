from enum import StrEnum


class MonitorMarket(StrEnum):
    A = "A"
    HK = "HK"
    ETF = "ETF"


class MonitorFrequency(StrEnum):
    DAILY = "daily"
    INTRADAY = "intraday"


class MonitorConditionType(StrEnum):
    PRICE_THRESHOLD = "price_threshold"
    MA_CROSS = "ma_cross"
    CHANGE_PCT = "change_pct"
    PRICE_CROSS_MA = "price_cross_ma"
    CLOSE_CROSS_MA = "close_cross_ma"
    RSI = "rsi"


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
