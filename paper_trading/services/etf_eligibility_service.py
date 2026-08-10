from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from paper_trading.domain.enums import ETFEligibilityStatus
from paper_trading.storage.models import ETFEligibility
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.etf_basic import ETFBasic

_VALID_EXCHANGES = {"SH", "SZ"}
_LISTED_STATUS = "L"


@dataclass(frozen=True)
class ETFEligibilityValidation:
    eligible: bool
    code: str
    message: str


class ETFEligibilityService:
    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def reconcile(self, snapshot: Collection[ETFBasic], refreshed_at: datetime) -> list[ETFEligibility]:
        current_symbols: set[str] = set()
        with self.repo.session.begin_nested():
            for etf in snapshot:
                symbol = str(etf.基金代码)
                current_symbols.add(symbol)
                name = cast(str, etf.中文简称)
                exchange = cast(str | None, etf.交易所) or ""
                list_status = cast(str | None, etf.存续状态) or ""
                current = exchange in _VALID_EXCHANGES and list_status == _LISTED_STATUS
                existing = self.repo.get_etf_eligibility(symbol)
                if existing is None and not current:
                    continue
                status = ETFEligibilityStatus.UNKNOWN if existing is None and current else None
                if existing is not None and not current:
                    status = ETFEligibilityStatus.DISABLED
                elif existing is not None and current and existing.status == ETFEligibilityStatus.DISABLED.value:
                    status = ETFEligibilityStatus.UNKNOWN
                self.repo.upsert_etf_eligibility(
                    symbol=symbol,
                    name=name,
                    exchange=exchange,
                    list_status=list_status,
                    refreshed_at=refreshed_at,
                    status=status,
                )
            for eligibility in self.repo.list_etf_eligibility():
                if eligibility.symbol not in current_symbols:
                    eligibility.status = ETFEligibilityStatus.DISABLED.value
                    eligibility.reviewed_at = None
                    eligibility.reviewed_by = None
                    eligibility.last_refresh_at = refreshed_at
            self.repo.session.flush()
        return self.repo.list_etf_eligibility()

    def classify(self, symbol: str, status: ETFEligibilityStatus, reviewed_by: str) -> ETFEligibility:
        eligibility = self.repo.get_etf_eligibility(symbol)
        provider = self.repo.session.get(ETFBasic, symbol)
        if provider is None:
            raise KeyError(f"ETF not found: {symbol}")
        if provider.交易所 not in _VALID_EXCHANGES:
            raise ValueError("ETF exchange must be SH or SZ")
        if provider.存续状态 != _LISTED_STATUS:
            raise ValueError("ETF listing status must be L")
        if eligibility is None:
            raise KeyError(f"ETF eligibility not found: {symbol}")
        return self.repo.classify_etf_eligibility(symbol, status, reviewed_by)

    def validate_etf_eligibility(self, symbol: str) -> ETFEligibilityValidation:
        try:
            eligibility = self.repo.get_etf_eligibility(symbol)
        except ValueError:
            return ETFEligibilityValidation(False, "INVALID_ETF_SYMBOL", "ETF symbol must be a bare six-digit value")
        provider = self.repo.session.get(ETFBasic, symbol)
        if provider is None:
            return ETFEligibilityValidation(False, "ETF_NOT_FOUND", "ETF was not found")
        if provider.交易所 not in _VALID_EXCHANGES:
            return ETFEligibilityValidation(False, "INVALID_ETF_EXCHANGE", "ETF exchange must be SH or SZ")
        if provider.存续状态 != _LISTED_STATUS:
            return ETFEligibilityValidation(False, "INVALID_ETF_LISTING_STATUS", "ETF listing status must be L")
        if eligibility is None:
            return ETFEligibilityValidation(
                False, "ETF_ELIGIBILITY_UNREVIEWED", "ETF eligibility has not been reviewed"
            )
        if eligibility.status == ETFEligibilityStatus.UNKNOWN.value:
            return ETFEligibilityValidation(
                False, "ETF_ELIGIBILITY_UNREVIEWED", "ETF eligibility has not been reviewed"
            )
        if eligibility.status in {ETFEligibilityStatus.MONEY_MARKET.value, ETFEligibilityStatus.DISABLED.value}:
            return ETFEligibilityValidation(False, "UNSUPPORTED_ETF_TYPE", "ETF type is not supported")
        return ETFEligibilityValidation(True, "ELIGIBLE", "ETF is eligible")
