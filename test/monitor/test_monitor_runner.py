from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
        patch(
            "monitor.monitor_runner.fetch_current_price", return_value=1600.0
        ),  # above threshold
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        run_monitor(frequency="daily")

    mock_storage.update_monitor_target_state.assert_called_with(
        1, False, triggered_at=None
    )


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
