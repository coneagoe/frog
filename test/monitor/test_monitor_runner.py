from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from common.const import COL_CLOSE
from monitor.monitor_runner import run_monitor


def _make_target(
    id=1,
    stock_code="600519",
    market="A",
    condition=None,
    note="茅台跌破1500",
    frequency="daily",
    reset_mode="auto",
    last_state=False,
    stock_name=None,
):
    t = MagicMock()
    t.id = id
    t.stock_code = stock_code
    t.market = market
    t.condition = condition or {
        "type": "price_threshold",
        "direction": "below",
        "value": 1500.0,
    }
    t.note = note
    t.frequency = frequency
    t.reset_mode = reset_mode
    t.last_state = last_state
    t.stock_name = stock_name
    return t


def test_run_monitor_triggers_alert_and_updates_state():
    """When condition triggers (last_state was False), sends email and updates state."""
    target = _make_target(last_state=False)

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        summary = run_monitor(frequency="daily")

    mock_email.assert_called_once()
    subject, body = mock_email.call_args[0][:2]
    assert "600519" in subject or "600519" in body
    call_args = mock_storage.update_monitor_target_state.call_args
    assert call_args is not None
    assert call_args[0] == (1, True)
    triggered_at = call_args[1]["triggered_at"]
    assert isinstance(triggered_at, datetime)
    assert abs((triggered_at - datetime.now(timezone.utc)).total_seconds()) < 5
    assert summary.triggered == 1


def test_run_monitor_no_repeat_alert_when_already_triggered():
    """When condition is True but last_state was already True, no email sent (auto reset)."""
    target = _make_target(last_state=True, reset_mode="auto")

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        summary = run_monitor(frequency="daily")

    mock_email.assert_not_called()
    assert summary.triggered == 0


def test_run_monitor_auto_resets_state_when_condition_clears():
    """In auto mode, when condition is no longer true, last_state resets to False."""
    target = _make_target(last_state=True, reset_mode="auto")

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1600.0),  # above threshold
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        run_monitor(frequency="daily")

    mock_storage.update_monitor_target_state.assert_called_with(1, False, triggered_at=None)


def test_run_daily_monitor_uses_latest_history_close_for_ma_condition_when_realtime_price_missing():
    target = _make_target(
        stock_code="002558",
        condition={"type": "price_cross_ma", "direction": "above", "period": 20},
        note="巨人网络 超过 MA20",
        last_state=False,
    )
    history_df = pd.DataFrame({COL_CLOSE: [25.0] * 19 + [28.0]})

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=np.nan),
        patch("monitor.monitor_runner.fetch_history_df", return_value=history_df),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        summary = run_monitor(frequency="daily")

    mock_email.assert_called_once()
    mock_storage.update_monitor_target_state.assert_called_once()
    assert summary.triggered == 1


def test_run_monitor_manual_mode_does_not_auto_reset():
    """In manual mode, last_state stays True even when condition clears."""
    target = _make_target(last_state=True, reset_mode="manual")

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1600.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        run_monitor(frequency="daily")

    # Should NOT reset state in manual mode
    mock_storage.update_monitor_target_state.assert_not_called()


def test_run_monitor_alert_subject_prefers_note_text():
    """Alert subject includes note text when note is provided."""
    target = _make_target(note="抄底提醒")
    target.stock_name = "贵州茅台"

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        run_monitor(frequency="daily")

    subject, _body = mock_email.call_args[0][:2]
    assert subject == "[股票监控告警] 600519 贵州茅台 抄底提醒"


def test_run_monitor_alert_subject_falls_back_when_note_blank():
    """Alert subject falls back to condition summary when note is blank."""
    target = _make_target(note="   ")
    target.stock_name = "贵州茅台"

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        run_monitor(frequency="daily")

    subject, _body = mock_email.call_args[0][:2]
    assert subject == "[股票监控告警] 600519 贵州茅台 价格低于1500.0"


def test_run_monitor_alert_subject_resolves_missing_stock_name():
    """When target has no stock_name, resolve from stock_code via shared helper."""
    target = _make_target(note=None, stock_name=None)
    # stock_name is None by default; condition will be used as suffix

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
        patch("monitor.monitor_runner.resolve_stock_name", return_value="贵州茅台") as mock_resolve,
    ):
        run_monitor(frequency="daily")

    mock_resolve.assert_called_once_with("600519", None)
    subject, _body = mock_email.call_args[0][:2]
    assert subject == "[股票监控告警] 600519 贵州茅台 价格低于1500.0"


def test_run_monitor_alert_subject_graceful_fallback_on_resolver_failure():
    """When resolve_stock_name fails/returns None, subject still shows code + condition."""
    target = _make_target(note=None, stock_name=None)

    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as mock_email,
        patch("monitor.monitor_runner.resolve_stock_name", return_value=None),
    ):
        run_monitor(frequency="daily")

    subject, _body = mock_email.call_args[0][:2]
    # No stock name, condition fallback
    assert subject == "[股票监控告警] 600519 价格低于1500.0"
