from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest

from common.const import (
    COL_AMOUNT,
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_STOCK_ID,
    COL_VOLUME,
    AdjustType,
    PeriodType,
)
from paper_trading.services.data_gap_recovery_service import DataGapRecoveryService


def _row(stock_id: str, business_date: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            COL_DATE: [business_date],
            COL_STOCK_ID: [stock_id],
            COL_OPEN: [10.0],
            COL_HIGH: [11.0],
            COL_LOW: [9.0],
            COL_CLOSE: [10.5],
            COL_VOLUME: [100.0],
            COL_AMOUNT: [1000.0],
        }
    )


def _service(storage: Mock, downloader: Mock, repository: Mock) -> DataGapRecoveryService:
    return DataGapRecoveryService(storage=storage, downloader=downloader, repository=repository)


def test_existing_exact_row_skips_provider_and_repair():
    storage = Mock()
    storage.load_history_data_stock.return_value = _row("000001", "2026-08-07")
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "skipped"
    downloader.dl_history_data_stock_by_provider.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    repository.resolve_gap.assert_called_once_with(gap.id)


@pytest.mark.parametrize("stored_row", [_row("000002", "2026-08-07"), _row("000001", "2026-08-08")])
def test_non_matching_existing_row_does_not_skip_provider(stored_row):
    storage = Mock()
    storage.load_history_data_stock.return_value = stored_row
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    downloader.dl_history_data_stock_by_provider.assert_called()


@pytest.mark.parametrize(
    ("market", "adjust", "stock_id"),
    [
        ("hk_connect", "bfq", "000001"),
        ("a_share", "qfq", "000001"),
        ("a_share", "bfq", "１２３４５６"),
    ],
)
def test_invalid_gap_identity_fails_before_storage_or_provider_interaction(market, adjust, stock_id):
    storage = Mock()
    downloader = Mock()
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id=stock_id, market=market, adjust=adjust)

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert result.error
    storage.load_history_data_stock.assert_not_called()
    storage.save_history_data_stock.assert_not_called()
    downloader.dl_history_data_stock_by_provider.assert_not_called()


def test_empty_provider_result_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"
    assert downloader.dl_history_data_stock_by_provider.call_count == 2


def test_invalid_provider_result_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [
        pd.DataFrame({"unexpected": [1]}),
        _row("000001", "2026-08-07"),
    ]
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert result.provider == "tushare"


def test_first_valid_exact_provider_short_circuits_later_providers(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    downloader.dl_history_data_stock_by_provider.assert_called_once()


def test_missing_gap_uses_first_valid_exact_provider_row_and_reads_back():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [
        _row("000002", "2026-08-07"),
        _row("000001", "2026-08-07"),
    ]
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    assert downloader.dl_history_data_stock_by_provider.call_count == 2
    assert all(
        call.args[2:4] == ("20260807", "20260807")
        for call in downloader.dl_history_data_stock_by_provider.call_args_list
    )
    assert all(
        call.args[4:] == (PeriodType.DAILY, AdjustType.BFQ)
        for call in downloader.dl_history_data_stock_by_provider.call_args_list
    )
    saved = storage.save_history_data_stock.call_args.args[0]
    assert len(saved) == 1
    assert saved.iloc[0][COL_STOCK_ID] == "000001"


def test_surrounding_provider_dates_are_narrowed_to_target_row():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), _row("000001", "2026-08-07")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = pd.concat(
        [_row("000001", "2026-08-06"), _row("000001", "2026-08-07"), _row("000001", "2026-08-08")],
        ignore_index=True,
    )
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "recovered"
    saved = storage.save_history_data_stock.call_args.args[0]
    assert len(saved) == 1
    assert saved.iloc[0][COL_DATE].date() == date(2026, 8, 7)


def test_readback_failure_is_retryable():
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame()]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "readback" in (result.error or "")


@pytest.mark.parametrize("readback_row", [_row("000002", "2026-08-07"), _row("000001", "2026-08-08")])
def test_non_matching_non_empty_readback_is_failure(readback_row):
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), readback_row]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    assert "readback" in (result.error or "")


def test_one_failed_gap_does_not_block_later_gap(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame(), _row("000002", "2026-08-08")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [RuntimeError("down"), _row("000002", "2026-08-08")]
    repository = Mock()
    gaps = [
        SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq"),
        SimpleNamespace(id=2, business_date=date(2026, 8, 8), stock_id="000002", market="a_share", adjust="bfq"),
    ]

    results = _service(storage, downloader, repository).recover_gaps(gaps)

    assert [item.status for item in results] == ["failed", "recovered"]


def test_repository_recording_failure_does_not_block_later_gap(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order", lambda: ["baostock"]
    )
    storage = Mock()
    storage.load_history_data_stock.side_effect = [pd.DataFrame(), pd.DataFrame(), _row("000002", "2026-08-08")]
    downloader = Mock()
    downloader.dl_history_data_stock_by_provider.side_effect = [RuntimeError("down"), _row("000002", "2026-08-08")]
    repository = Mock()
    repository.record_attempt.side_effect = RuntimeError("repository down")
    gaps = [
        SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq"),
        SimpleNamespace(id=2, business_date=date(2026, 8, 8), stock_id="000002", market="a_share", adjust="bfq"),
    ]

    results = _service(storage, downloader, repository).recover_gaps(gaps)

    assert [item.status for item in results] == ["failed", "recovered"]


def test_write_failure_is_retryable_and_does_not_accept_another_provider(monkeypatch):
    monkeypatch.setattr(
        "paper_trading.services.data_gap_recovery_service.parse_stock_history_provider_order",
        lambda: ["baostock", "tushare"],
    )
    storage = Mock()
    storage.load_history_data_stock.return_value = pd.DataFrame()
    storage.save_history_data_stock.return_value = False
    downloader = Mock(return_value=None)
    downloader.dl_history_data_stock_by_provider.return_value = _row("000001", "2026-08-07")
    repository = Mock()
    gap = SimpleNamespace(id=1, business_date=date(2026, 8, 7), stock_id="000001", market="a_share", adjust="bfq")

    result = _service(storage, downloader, repository).recover_gap(gap)

    assert result.status == "failed"
    downloader.dl_history_data_stock_by_provider.assert_called_once()
