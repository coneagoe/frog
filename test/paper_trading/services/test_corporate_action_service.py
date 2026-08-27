from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from paper_trading.domain.enums import CashEventType, CorporateActionType, Market
from paper_trading.services.corporate_action_service import (
    CorporateActionIdempotencyConflict,
    CorporateActionService,
)
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationResult
from paper_trading.storage.repository import PaperTradingRepository
from test.paper_trading.fakes import FakeMarketDataProvider


class _NoopRecalculation:
    def recalculate(self, account_id, start_date, end_date, session=None):
        return SnapshotRecalculationResult(account_id, [start_date], [], [], [])


def _service(session):
    return CorporateActionService(PaperTradingRepository(session), recalculation_service=_NoopRecalculation())


def test_dividend_is_audited_and_credits_cash(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-dividend", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))

    result = _service(sqlite_session).apply(
        account.id,
        "000001",
        CorporateActionType.DIVIDEND,
        datetime(2026, 8, 27, 9, tzinfo=timezone.utc),
        "dividend-1",
        {"per_share_amount": Decimal("0.25")},
    )

    assert result.impact.cash_delta == Decimal("25.000000000000")
    assert repo.get_cash_available(account.id) == Decimal("10025.0000")
    assert any(row.event_type == CashEventType.CORPORATE_ACTION.value for row in repo.list_cash_ledger(account.id))
    assert repo.list_corporate_actions(account.id)[0] is result.event


@pytest.mark.parametrize(
    ("event_type", "parameters", "expected_quantity"),
    [
        (CorporateActionType.SPLIT, {"ratio": Decimal("2")}, 200),
        (CorporateActionType.REVERSE_SPLIT, {"ratio": Decimal("0.5")}, 50),
        (CorporateActionType.BONUS_SHARE, {"bonus_ratio": Decimal("0.1")}, 110),
        (
            CorporateActionType.RIGHTS_ISSUE,
            {"subscription_ratio": Decimal("0.2"), "subscription_price": Decimal("2")},
            120,
        ),
    ],
)
def test_non_dividend_actions_keep_position_and_lot_consistent(
    sqlite_session, event_type, parameters, expected_quantity
):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account(f"corporate-action-{event_type.value}", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 100, 100, Decimal("10"))

    result = _service(sqlite_session).apply(
        account.id, "000001", event_type, datetime(2026, 8, 27, tzinfo=timezone.utc), event_type.value, parameters
    )

    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None
    assert position.total_quantity == expected_quantity
    assert repo.get_lots(account.id, Market.A_SHARE, "000001")[0].remaining_quantity == expected_quantity
    assert result.impact.after_cost_amount == Decimal("1000.000000000000")
    assert [row.event_type for row in repo.list_cash_ledger(account.id)].count(
        CashEventType.CORPORATE_ACTION.value
    ) == (1 if event_type is CorporateActionType.RIGHTS_ISSUE else 0)


def test_no_holding_creates_zero_impact_event(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-empty", Decimal("10000"))

    result = _service(sqlite_session).apply(
        account.id,
        "000001",
        CorporateActionType.DIVIDEND,
        datetime(2026, 8, 27, tzinfo=timezone.utc),
        "empty-1",
        {"per_share_amount": Decimal("1")},
    )

    assert result.impact.cash_delta == 0
    assert result.event.before_quantity == 0


def test_idempotent_replay_returns_original_and_conflict_is_rejected(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-idempotent", Decimal("10000"))
    service = _service(sqlite_session)
    timestamp = datetime(2026, 8, 27, tzinfo=timezone.utc)
    first = service.apply(
        account.id, "000001", CorporateActionType.DIVIDEND, timestamp, "same", {"per_share_amount": Decimal("1")}
    )
    replay = service.apply(
        account.id, "000001", CorporateActionType.DIVIDEND, timestamp, "same", {"per_share_amount": Decimal("1.0")}
    )
    assert replay.event.id == first.event.id
    with pytest.raises(CorporateActionIdempotencyConflict):
        service.apply(
            account.id, "000001", CorporateActionType.DIVIDEND, timestamp, "same", {"per_share_amount": Decimal("2")}
        )


def test_recalculation_failure_rolls_back_all_accounting_writes(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-rollback", Decimal("10000"))
    initial_cash = repo.get_cash_available(account.id)
    sqlite_session.commit()

    class FailingRecalculation:
        def recalculate(self, account_id, start_date, end_date, session=None):
            raise RuntimeError("recalculation failed")

    service = CorporateActionService(repo, recalculation_service=FailingRecalculation())
    with pytest.raises(RuntimeError, match="recalculation failed"):
        service.apply(
            account.id,
            "000001",
            CorporateActionType.DIVIDEND,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            "rollback-1",
            {"per_share_amount": Decimal("1")},
        )
    sqlite_session.rollback()

    assert repo.get_cash_available(account.id) == initial_cash
    assert repo.list_corporate_actions(account.id) == []
    assert repo.list_cash_ledger(account.id)
