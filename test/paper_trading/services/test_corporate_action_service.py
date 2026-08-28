from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest

from paper_trading.domain.enums import CashEventType, CorporateActionType, Market
from paper_trading.domain.errors import InsufficientRightsCashError, InvalidCorporateActionParametersError
from paper_trading.services.corporate_action_service import (
    CorporateActionIdempotencyConflict,
    CorporateActionService,
)
from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationResult
from paper_trading.storage.models import PaperValuationGap
from paper_trading.storage.repository import PaperTradingRepository


class _NoopRecalculation:
    def recalculate(self, account_id, start_date, end_date, session=None):
        return SnapshotRecalculationResult(account_id, [start_date], [], [], [])


class _FailedDatesRecalculation:
    def recalculate(self, account_id, start_date, end_date, session=None):
        return SnapshotRecalculationResult(account_id, [], [], [start_date], [f"{start_date}: unavailable"])


def _service(session):
    return CorporateActionService(PaperTradingRepository(session), recalculation_service=_NoopRecalculation())


def test_dividend_is_audited_and_credits_cash(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-dividend", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 100, 100, Decimal("10"))

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
    expected_cost = (
        Decimal("1040.000000000000") if event_type is CorporateActionType.RIGHTS_ISSUE else Decimal("1000.000000000000")
    )
    assert result.impact.after_cost_amount == expected_cost
    if event_type is CorporateActionType.RIGHTS_ISSUE:
        assert account.net_asset_value == Decimal("1.000000")
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
    account.cumulative_deposit = Decimal("12000.000000")
    account.cumulative_withdrawal = Decimal("2000.000000")
    service = _service(sqlite_session)
    timestamp = datetime(2026, 8, 27, tzinfo=timezone.utc)
    first = service.apply(
        account.id, "000001", CorporateActionType.DIVIDEND, timestamp, "same", {"per_share_amount": Decimal("1")}
    )
    replay = service.apply(
        account.id, "000001", CorporateActionType.DIVIDEND, timestamp, "same", {"per_share_amount": Decimal("1.0")}
    )
    assert replay.event.id == first.event.id
    assert replay.recalculation == first.recalculation
    assert account.cumulative_deposit == Decimal("12000.000000")
    assert account.cumulative_withdrawal == Decimal("2000.000000")
    with pytest.raises(CorporateActionIdempotencyConflict):
        service.apply(
            account.id, "000001", CorporateActionType.DIVIDEND, timestamp, "same", {"per_share_amount": Decimal("2")}
        )


def test_recalculation_failure_rolls_back_all_accounting_writes(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-rollback", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 100, 100, Decimal("10"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 8, 27),
        event_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        point_type="trading",
        quality_status="valid",
        cash_available=Decimal("10000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("1000"),
        total_assets=Decimal("11000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=1,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )
    repo.upsert_valuation_gap(account.id, date(2026, 8, 28), ["000001"], [{"reason": "missing"}])
    initial_position = (100, Decimal("1000"))
    initial_lot = (100, 100, Decimal("10"))
    initial_cash = repo.get_cash_available(account.id)
    initial_snapshot_count = len(repo.list_snapshots(account.id))
    initial_gap_count = sqlite_session.query(PaperValuationGap).filter_by(account_id=account.id).count()
    initial_totals = (
        account.cumulative_deposit,
        account.cumulative_withdrawal,
        account.net_asset_value,
        account.share_count,
    )
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
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None
    assert (position.total_quantity, position.cost_amount) == initial_position
    lot = repo.get_lots(account.id, Market.A_SHARE, "000001")[0]
    assert (lot.original_quantity, lot.remaining_quantity, lot.cost_price) == initial_lot
    assert len(repo.list_snapshots(account.id)) == initial_snapshot_count
    assert sqlite_session.query(PaperValuationGap).filter_by(account_id=account.id).count() == initial_gap_count
    assert (
        account.cumulative_deposit,
        account.cumulative_withdrawal,
        account.net_asset_value,
        account.share_count,
    ) == initial_totals
    assert len(repo.list_cash_ledger(account.id)) == 1


def test_insufficient_rights_cash_rejects_without_any_persisted_change(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-insufficient-cash", Decimal("10"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 100, 100, Decimal("10"))
    sqlite_session.commit()

    with pytest.raises(InsufficientRightsCashError, match="cash"):
        _service(sqlite_session).apply(
            account.id,
            "000001",
            CorporateActionType.RIGHTS_ISSUE,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            "insufficient-cash",
            {"subscription_ratio": Decimal("1"), "subscription_price": Decimal("1")},
        )
    sqlite_session.rollback()
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None and position.total_quantity == 100
    assert repo.get_cash_available(account.id) == Decimal("10.0000")
    assert repo.list_corporate_actions(account.id) == []
    assert len(repo.list_cash_ledger(account.id)) == 1


def test_rights_issue_uses_internal_cash_precision_for_eligibility(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-precise-cash", Decimal("10.00004"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 1, 0, Decimal("1"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 1, 1, Decimal("1"))

    result = _service(sqlite_session).apply(
        account.id,
        "000001",
        CorporateActionType.RIGHTS_ISSUE,
        datetime(2026, 8, 27, tzinfo=timezone.utc),
        "precise-cash",
        {"subscription_ratio": Decimal("1"), "subscription_price": Decimal("10.00004")},
    )

    assert repo.get_cash_available(account.id) == Decimal("0.0000")
    assert repo.get_cash_available_internal(account.id) == Decimal("0.000000000000")
    assert result.impact.before_cash_available == Decimal("10.000040000000")


def test_rights_issue_preserves_large_twelve_decimal_cash_eligibility(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    cash = Decimal("999999999999.125000000000")
    account = repo.create_account("corporate-action-large-cash", cash)
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 1, 0, Decimal("1"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 1, 1, Decimal("1"))

    assert repo.get_cash_available_internal(account.id) == cash
    result = _service(sqlite_session).apply(
        account.id,
        "000001",
        CorporateActionType.RIGHTS_ISSUE,
        datetime(2026, 8, 27, tzinfo=timezone.utc),
        "large-precise-cash",
        {"subscription_ratio": Decimal("1"), "subscription_price": cash},
    )

    assert result.impact.before_cash_available == cash
    assert repo.get_cash_available_internal(account.id) == Decimal("0.000000000000")


def test_service_rejects_extra_parameters_before_idempotency_resolution(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-extra-parameters", Decimal("10000"))
    service = _service(sqlite_session)
    event_at = datetime(2026, 8, 27, tzinfo=timezone.utc)
    service.apply(
        account.id,
        "000001",
        CorporateActionType.DIVIDEND,
        event_at,
        "same",
        {"per_share_amount": Decimal("1")},
    )

    with pytest.raises(InvalidCorporateActionParametersError, match="unexpected"):
        service.apply(
            account.id,
            "000001",
            CorporateActionType.DIVIDEND,
            event_at,
            "same",
            {"per_share_amount": Decimal("1"), "ratio": Decimal("2")},
        )
    assert len(repo.list_corporate_actions(account.id)) == 1


def test_invalid_holding_rejects_before_writes(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-invalid-holding", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 90, 90, Decimal("10"))
    sqlite_session.commit()

    with pytest.raises(ValueError, match="aggregate"):
        _service(sqlite_session).apply(
            account.id,
            "000001",
            CorporateActionType.SPLIT,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            "invalid-holding",
            {"ratio": Decimal("2")},
        )
    sqlite_session.rollback()
    assert repo.list_corporate_actions(account.id) == []
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None and position.total_quantity == 100
    assert repo.get_lots(account.id, Market.A_SHARE, "000001")[0].remaining_quantity == 90


def test_fractional_result_rejects_integer_backed_holding_without_writes(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-fractional", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 101, 0, Decimal("1010"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 101, 101, Decimal("10"))
    sqlite_session.commit()

    with pytest.raises(ValueError, match="fractional quantity"):
        _service(sqlite_session).apply(
            account.id,
            "000001",
            CorporateActionType.SPLIT,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            "fractional-result",
            {"ratio": Decimal("1.5")},
        )
    sqlite_session.rollback()
    assert repo.list_corporate_actions(account.id) == []
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None and position.total_quantity == 101


def test_failed_recalculation_dates_roll_back_event_and_all_accounting_changes(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-failed-date", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 100, 100, Decimal("10"))
    sqlite_session.commit()

    with pytest.raises(RuntimeError, match="2026-08-27"):
        CorporateActionService(repo, recalculation_service=_FailedDatesRecalculation()).apply(
            account.id,
            "000001",
            CorporateActionType.DIVIDEND,
            datetime(2026, 8, 27, tzinfo=timezone.utc),
            "failed-date",
            {"per_share_amount": Decimal("1")},
        )
    sqlite_session.rollback()
    assert repo.list_corporate_actions(account.id) == []
    assert repo.get_cash_available(account.id) == Decimal("10000.0000")
    position = repo.get_position(account.id, Market.A_SHARE, "000001")
    assert position is not None and position.total_quantity == 100


def test_recalculation_covers_event_and_later_snapshot_and_gap_dates(sqlite_session):
    repo = PaperTradingRepository(sqlite_session)
    account = repo.create_account("corporate-action-recalculation-range", Decimal("10000"))
    repo.upsert_position(account.id, Market.A_SHARE, "000001", 100, 0, Decimal("1000"))
    repo.create_position_lot(account.id, Market.A_SHARE, "000001", date(2026, 8, 1), 100, 100, Decimal("10"))
    repo.save_snapshot(
        account_id=account.id,
        trade_date=date(2026, 8, 28),
        event_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        point_type="trading",
        quality_status="valid",
        cash_available=Decimal("10000"),
        cash_frozen=Decimal("0"),
        market_value=Decimal("1000"),
        total_assets=Decimal("11000"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        position_count=1,
        order_count=0,
        trade_count=0,
        net_asset_value=Decimal("1"),
    )
    repo.upsert_valuation_gap(account.id, date(2026, 8, 29), ["000001"], [{"reason": "missing"}])
    sqlite_session.commit()
    recalculation = Mock(
        recalculate=Mock(
            return_value=SnapshotRecalculationResult(
                account.id,
                [date(2026, 8, 27), date(2026, 8, 28)],
                [date(2026, 8, 29)],
                [],
                [],
            )
        )
    )

    result = CorporateActionService(repo, recalculation_service=recalculation).apply(
        account.id,
        "000001",
        CorporateActionType.SPLIT,
        datetime(2026, 8, 27, 15, tzinfo=timezone.utc),
        "bounded-range",
        {"ratio": Decimal("2")},
    )

    recalculation.recalculate.assert_called_once_with(
        account.id,
        date(2026, 8, 27),
        date(2026, 8, 29),
        session=sqlite_session,
    )
    assert result.recalculation.updated_dates == [date(2026, 8, 27), date(2026, 8, 28)]
    assert result.recalculation.unavailable_dates == [date(2026, 8, 29)]
    assert repo.get_valuation_gap(account.id, date(2026, 8, 29)) is not None
