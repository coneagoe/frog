from datetime import date
from unittest.mock import MagicMock, call, patch

from shareholder_monitor.runner import run_ssf_change_alert


def make_history_df():
    import pandas as pd

    return pd.DataFrame(
        {
            "股票代码": ["000001"] * 3,
            "公告日期": pd.to_datetime(["2024-03-31", "2023-12-31", "2023-12-31"]),
            "股东名称": [
                "全国社保基金一一八组合",
                "全国社保基金一一八组合",
                "全国社保基金五零三组合",
            ],
            "持有数量（万股）": [1200.0, 1000.0, 500.0],
            "占总流通股本持股比例": [1.5, 1.2, 0.6],
            "持股变动": [200.0, 0.0, 0.0],
        }
    )


def test_run_ssf_change_alert_saves_sends_and_marks():
    mock_storage = MagicMock()
    mock_storage.list_ssf_change_signal_candidates.return_value = [
        ("000001", "2024-03-31")
    ]
    mock_storage.load_top10_floatholders_history.return_value = make_history_df()
    mock_storage.save_ssf_change_signals.return_value = [1]
    mock_storage.list_pending_ssf_change_signals.return_value = [
        MagicMock(
            id=1,
            stock_id="000001",
            ann_date=date(2024, 3, 31),
            score=88.0,
            event_types=["increase"],
            ssf_holder_count_change=1,
            ssf_total_hold_ratio_change=0.8,
            detail_json={"holders": []},
        )
    ]

    with (
        patch("shareholder_monitor.runner.get_storage", return_value=mock_storage),
        patch("shareholder_monitor.runner.send_email") as mock_email,
    ):
        summary = run_ssf_change_alert()

    mock_storage.ensure_ssf_change_signals_table.assert_called_once()
    mock_storage.save_ssf_change_signals.assert_called_once()
    mock_email.assert_called_once()
    mock_storage.mark_ssf_change_signals_alerted.assert_called_once_with([1])
    assert summary.inserted == 1


def test_run_ssf_change_alert_skips_email_when_no_pending():
    mock_storage = MagicMock()
    mock_storage.list_ssf_change_signal_candidates.return_value = []
    mock_storage.save_ssf_change_signals.return_value = []
    mock_storage.list_pending_ssf_change_signals.return_value = []

    with (
        patch("shareholder_monitor.runner.get_storage", return_value=mock_storage),
        patch("shareholder_monitor.runner.send_email") as mock_email,
    ):
        summary = run_ssf_change_alert()

    mock_email.assert_not_called()
    mock_storage.mark_ssf_change_signals_alerted.assert_not_called()
    assert summary.emailed == 0


def test_run_ssf_change_alert_sends_and_marks_pending_by_ann_date():
    mock_storage = MagicMock()
    mock_storage.list_ssf_change_signal_candidates.return_value = []
    mock_storage.save_ssf_change_signals.return_value = []
    mock_storage.list_pending_ssf_change_signals.return_value = [
        MagicMock(
            id=11,
            stock_id="000001",
            ann_date=date(2024, 3, 31),
            score=88.0,
            event_types=["increase"],
            ssf_holder_count_change=1,
            ssf_total_hold_ratio_change=0.8,
            detail_json={"holders": []},
        ),
        MagicMock(
            id=12,
            stock_id="000002",
            ann_date=date(2024, 6, 30),
            score=92.0,
            event_types=["new_entry"],
            ssf_holder_count_change=1,
            ssf_total_hold_ratio_change=1.2,
            detail_json={"holders": []},
        ),
        MagicMock(
            id=13,
            stock_id="000003",
            ann_date=date(2024, 3, 31),
            score=61.0,
            event_types=["decrease"],
            ssf_holder_count_change=-1,
            ssf_total_hold_ratio_change=-0.5,
            detail_json={"holders": []},
        ),
    ]

    with (
        patch("shareholder_monitor.runner.get_storage", return_value=mock_storage),
        patch("shareholder_monitor.runner.send_email") as mock_email,
    ):
        summary = run_ssf_change_alert()

    assert mock_email.call_count == 2
    newer_subject, newer_body = mock_email.call_args_list[0].args
    older_subject, older_body = mock_email.call_args_list[1].args
    assert "2024-06-30" in newer_subject
    assert "000002" in newer_body
    assert "2024-03-31" in older_subject
    assert "000001" in older_body
    assert "000003" in older_body
    assert "2024-06-30" not in older_subject
    mock_storage.mark_ssf_change_signals_alerted.assert_has_calls(
        [call([12]), call([11, 13])]
    )
    assert summary.emailed == 3
