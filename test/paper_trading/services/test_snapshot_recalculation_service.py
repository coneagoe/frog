from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from paper_trading.services.snapshot_recalculation_service import SnapshotRecalculationService
from paper_trading.services.snapshot_service import SnapshotOutcome


def test_recalculation_resolves_late_bar_without_matching_or_ledger_rebuild():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    session_factory = MagicMock(return_value=session)
    matching_service = MagicMock()
    order_delete_service = MagicMock()
    snapshot_service = MagicMock()
    snapshot_service.generate_snapshot_or_gap.return_value = SnapshotOutcome(status="complete")

    with (
        patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo),
        patch("paper_trading.services.snapshot_recalculation_service.SnapshotService", return_value=snapshot_service),
    ):
        service = SnapshotRecalculationService(session_factory, MagicMock())
        with patch.object(service, "_dates_with_valuation_state", return_value=[date(2026, 8, 25)]):
            result = service.recalculate(1, date(2026, 8, 25), date(2026, 8, 25))

    assert result.updated_dates == [date(2026, 8, 25)]
    assert result.unavailable_dates == []
    assert result.failed_dates == []
    matching_service.run.assert_not_called()
    order_delete_service.rebuild_account_from.assert_not_called()
    session.commit.assert_called_once()


def test_recalculation_classifies_unavailable_and_failed_dates():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = object()
    snapshot_service = MagicMock()
    snapshot_service.generate_snapshot_or_gap.side_effect = [
        SnapshotOutcome(status="valuation_gap"),
        RuntimeError("market data failed"),
    ]
    factory = MagicMock(return_value=session)

    with (
        patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo),
        patch("paper_trading.services.snapshot_recalculation_service.SnapshotService", return_value=snapshot_service),
    ):
        service = SnapshotRecalculationService(factory, MagicMock())
        with patch.object(
            service,
            "_dates_with_valuation_state",
            return_value=[date(2026, 8, 25), date(2026, 8, 26)],
        ):
            result = service.recalculate(1, date(2026, 8, 25), date(2026, 8, 26))

    assert result.unavailable_dates == [date(2026, 8, 25)]
    assert result.failed_dates == [date(2026, 8, 26)]
    assert result.errors == ["2026-08-26: market data failed"]


def test_recalculation_rejects_inverted_range():
    with pytest.raises(ValueError, match="start_date"):
        SnapshotRecalculationService(MagicMock(), MagicMock()).recalculate(
            1, date(2026, 8, 26), date(2026, 8, 25)
        )


def test_recalculation_rejects_unknown_account():
    session = MagicMock()
    repo = MagicMock()
    repo.get_account.return_value = None
    factory = MagicMock(return_value=session)

    with patch("paper_trading.services.snapshot_recalculation_service.PaperTradingRepository", return_value=repo):
        with pytest.raises(KeyError, match="not found"):
            SnapshotRecalculationService(factory, MagicMock()).recalculate(
                1, date(2026, 8, 25), date(2026, 8, 25)
            )
