from datetime import datetime, timezone

import pytest

from paper_trading.domain.enums import ETFEligibilityStatus
from paper_trading.services.etf_eligibility_service import ETFEligibilityService
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.etf_basic import ETFBasic


def etf(symbol: str, name: str, exchange: str, list_status: str) -> ETFBasic:
    return ETFBasic(基金代码=symbol, 中文简称=name, 交易所=exchange, 存续状态=list_status)


def test_reconcile_creates_unknown_rows_for_current_sh_and_sz_etfs(session):
    service = ETFEligibilityService(PaperTradingRepository(session))
    refreshed_at = datetime(2026, 8, 10, 9, 30, tzinfo=timezone.utc)

    rows = service.reconcile(
        [etf("510300", "CSI 300 ETF", "SH", "L"), etf("159915", "Chinext ETF", "SZ", "L")], refreshed_at
    )

    assert [(row.symbol, row.status, row.name) for row in rows] == [
        ("159915", "unknown", "Chinext ETF"),
        ("510300", "unknown", "CSI 300 ETF"),
    ]
    assert all(row.last_seen_at == refreshed_at.replace(tzinfo=None) for row in rows)


def test_reconcile_refreshes_provider_fields_and_disables_absent_or_delisted_rows(session):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)
    service.reconcile(
        [etf("510300", "Old name", "SH", "L"), etf("159915", "Delisted ETF", "SZ", "L")],
        datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    rows = service.reconcile(
        [etf("510300", "New name", "SZ", "L"), etf("159915", "Delisted ETF", "SZ", "D")],
        datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert [(row.symbol, row.name, row.exchange, row.list_status, row.status) for row in rows] == [
        ("159915", "Delisted ETF", "SZ", "D", "disabled"),
        ("510300", "New name", "SZ", "L", "unknown"),
    ]
    assert repo.get_etf_eligibility("510300").last_refresh_at == datetime(2026, 8, 10)


def test_reconcile_preserves_review_audit_and_is_idempotent_for_current_listing(session):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)
    snapshot = [etf("510300", "CSI 300 ETF", "SH", "L")]
    refreshed_at = datetime(2026, 8, 10, tzinfo=timezone.utc)
    service.reconcile(snapshot, refreshed_at)
    reviewed = repo.classify_etf_eligibility("510300", ETFEligibilityStatus.SUPPORTED, "operator")

    first = service.reconcile(snapshot, refreshed_at)[0]
    second = service.reconcile(snapshot, refreshed_at)[0]

    assert first.status == second.status == "supported"
    assert first.reviewed_by == second.reviewed_by == "operator"
    assert first.reviewed_at == second.reviewed_at == reviewed.reviewed_at


def test_reconcile_reopens_a_system_disabled_current_listing_as_unreviewed(session):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)
    service.reconcile([etf("510300", "CSI 300 ETF", "SH", "L")], datetime(2026, 8, 8, tzinfo=timezone.utc))
    service.reconcile([], datetime(2026, 8, 9, tzinfo=timezone.utc))

    row = service.reconcile([etf("510300", "CSI 300 ETF", "SH", "L")], datetime(2026, 8, 10, tzinfo=timezone.utc))[0]

    assert row.status == "unknown"


def test_reconcile_does_not_create_rows_for_new_invalid_provider_records(session):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)

    rows = service.reconcile(
        [etf("510300", "Foreign ETF", "HK", "L"), etf("159915", "Delisted ETF", "SZ", "D")],
        datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    assert rows == []
    assert repo.get_etf_eligibility("510300") is None
    assert repo.get_etf_eligibility("159915") is None


def test_classify_accepts_only_current_listing_and_operator_statuses(session):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)
    provider = etf("510300", "CSI 300 ETF", "SH", "L")
    session.add(provider)
    service.reconcile([provider], datetime(2026, 8, 10, tzinfo=timezone.utc))

    reviewed = service.classify("510300", ETFEligibilityStatus.MONEY_MARKET, "operator")

    assert reviewed.status == "money_market"
    assert reviewed.reviewed_by == "operator"
    assert reviewed.reviewed_at is not None
    with pytest.raises(ValueError, match="supported or money_market"):
        service.classify("510300", ETFEligibilityStatus.UNKNOWN, "operator")
    with pytest.raises(ValueError, match="bare six-digit"):
        service.classify("510300.SH", ETFEligibilityStatus.SUPPORTED, "operator")


def test_classify_rejects_provider_records_that_are_not_current_domestic_etfs(session):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)
    foreign = etf("510300", "Foreign ETF", "HK", "L")
    delisted = etf("159915", "Delisted ETF", "SZ", "D")
    session.add_all([foreign, delisted])
    service.reconcile([foreign, delisted], datetime(2026, 8, 10, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="SH or SZ"):
        service.classify("510300", ETFEligibilityStatus.SUPPORTED, "operator")
    with pytest.raises(ValueError, match="listing status"):
        service.classify("159915", ETFEligibilityStatus.SUPPORTED, "operator")


@pytest.mark.parametrize(
    ("symbol", "provider", "eligibility_status", "code", "eligible"),
    [
        ("510300", None, None, "ETF_NOT_FOUND", False),
        ("510301", etf("510301", "Unreviewed ETF", "SH", "L"), None, "ETF_ELIGIBILITY_UNREVIEWED", False),
        ("510302", etf("510302", "Money ETF", "SZ", "L"), "money_market", "UNSUPPORTED_ETF_TYPE", False),
        ("510306", etf("510306", "Disabled ETF", "SZ", "L"), "disabled", "UNSUPPORTED_ETF_TYPE", False),
        ("510303", etf("510303", "Foreign ETF", "HK", "L"), "supported", "INVALID_ETF_EXCHANGE", False),
        ("510304", etf("510304", "Delisted ETF", "SH", "D"), "supported", "INVALID_ETF_LISTING_STATUS", False),
        ("510305", etf("510305", "Supported ETF", "SZ", "L"), "supported", "ELIGIBLE", True),
    ],
)
def test_validate_etf_eligibility_returns_stable_provider_and_review_outcomes(
    session, symbol, provider, eligibility_status, code, eligible
):
    repo = PaperTradingRepository(session)
    service = ETFEligibilityService(repo)
    if provider is not None:
        session.add(provider)
        session.flush()
    if eligibility_status is not None:
        repo.upsert_etf_eligibility(
            symbol,
            provider.中文简称,
            provider.交易所,
            provider.存续状态,
            datetime(2026, 8, 10, tzinfo=timezone.utc),
            status=ETFEligibilityStatus(eligibility_status),
        )

    result = service.validate_etf_eligibility(symbol)

    assert result.code == code
    assert result.eligible is eligible


def test_validate_etf_eligibility_rejects_suffixed_symbol_with_stable_outcome(session):
    result = ETFEligibilityService(PaperTradingRepository(session)).validate_etf_eligibility("510300.SH")

    assert result.eligible is False
    assert result.code == "INVALID_ETF_SYMBOL"
