from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from common.const import COL_CLOSE, COL_DATE
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
    t.workflow = None
    return t


def _candidate_evidence() -> SimpleNamespace:
    return SimpleNamespace(
        evidence={
            "forecast": {
                "report_end_date": "2025-12-31",
                "p_change_min": 50.0,
                "ann_date": "2026-01-15",
            },
            "shareholder": {
                "matched_holder": "全国社保基金一一八组合",
                "ann_date": "2026-01-10",
            },
        }
    )


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


def test_unfiltered_run_does_not_create_blackroom_or_load_candidate_evidence():
    target = _make_target(last_state=False)
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService") as blackroom,
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        run_monitor()

    blackroom.assert_not_called()
    storage.get_forecast_ssf_candidate_for_target.assert_not_called()


def test_unfiltered_daily_run_rechecks_workflow_target_blackroom_before_email():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    blackroom = MagicMock(is_banned=lambda *_: {"success": True, "data": {"banned": True}})

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily")

    email.assert_not_called()
    storage.disable_forecast_ssf_target_for_blackroom.assert_called_once_with(target.id, "active_blackroom")
    assert summary.skipped == 1


def test_unfiltered_daily_run_leaves_manual_target_without_blackroom_lookup():
    target = _make_target(last_state=False)
    target.workflow = None
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService") as blackroom,
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        run_monitor(frequency="daily")

    blackroom.assert_not_called()


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


def test_run_daily_monitor_preserves_realtime_price_for_price_cross_ma():
    target = _make_target(
        condition={"type": "price_cross_ma", "direction": "above", "period": 20},
        last_state=False,
    )
    history_df = pd.DataFrame({COL_CLOSE: [25.0] * 20})
    mock_storage = MagicMock()
    mock_storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=mock_storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=26.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=history_df),
        patch("monitor.monitor_runner.send_email") as mock_email,
    ):
        run_monitor(frequency="daily")

    assert "当前价格: 26.0" in mock_email.call_args.args[1]


def test_final_close_runner_uses_hfq_storage_and_never_fetches_realtime_price():
    target = _make_target(condition={"type": "close_cross_ma", "direction": "above", "period": 20})
    history = pd.DataFrame({COL_DATE: pd.date_range(end="2026-06-03", periods=21), COL_CLOSE: [10.0] * 20 + [11.0]})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=history) as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily", as_of_date=date(2026, 6, 3))

    fetch_final.assert_called_once_with("600519", date(2026, 6, 3), min_periods=21)
    realtime.assert_not_called()
    email.assert_called_once()
    assert summary.triggered == 1


def _close_history(end: str, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({COL_DATE: pd.date_range(end=end, periods=len(closes)), COL_CLOSE: closes})


def test_reenabled_workflow_target_above_ma_waits_for_later_close_crossover():
    target = _make_target(
        condition={"type": "close_cross_ma", "direction": "above", "period": 20},
        last_state=True,
        reset_mode="auto",
    )
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    histories = [
        _close_history("2026-06-03", [10.0] * 18 + [11.0, 11.0, 12.0]),
        _close_history("2026-06-04", [10.0] * 19 + [10.0, 9.0]),
        _close_history("2026-06-05", [10.0] * 18 + [10.0, 9.0, 11.0]),
    ]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", side_effect=histories) as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.BlackroomService") as blackroom,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        first = run_monitor(workflow="forecast_ssf_ma20", as_of_date=date(2026, 6, 3))
        target.last_state = False
        second = run_monitor(workflow="forecast_ssf_ma20", as_of_date=date(2026, 6, 4))
        blackroom.return_value.is_banned.return_value = {"success": True, "data": {"banned": False}}
        third = run_monitor(workflow="forecast_ssf_ma20", as_of_date=date(2026, 6, 5))

    assert fetch_final.call_count == 3
    realtime.assert_not_called()
    state_updates = storage.update_monitor_target_state.call_args_list
    assert state_updates[0].args == (1, False)
    assert state_updates[0].kwargs == {"triggered_at": None}
    assert state_updates[1].args == (1, True)
    assert isinstance(state_updates[1].kwargs["triggered_at"], datetime)
    email.assert_called_once()
    blackroom.return_value.is_banned.assert_called_once_with("600519", "A")
    assert (first.triggered, first.skipped, first.errors) == (0, 0, 0)
    assert (second.triggered, second.skipped, second.errors) == (0, 0, 0)
    assert (third.triggered, third.skipped, third.errors) == (1, 0, 0)


def test_final_close_stale_bar_preserves_state_and_sends_no_email():
    target = _make_target(
        last_state=True,
        condition={"type": "close_cross_ma", "direction": "above", "period": 20},
    )
    stale_history = pd.DataFrame({COL_DATE: pd.date_range("2026-05-05", periods=21), COL_CLOSE: [10.0] * 20 + [11.0]})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=stale_history),
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily", as_of_date=date(2026, 6, 3))

    realtime.assert_not_called()
    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.skipped == 1


def test_final_close_non_a_target_skips_without_provider_or_state_update():
    target = _make_target(
        market="HK",
        last_state=True,
        condition={"type": "close_cross_ma", "direction": "above", "period": 20},
    )
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df") as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily", as_of_date=date(2026, 6, 3))

    fetch_final.assert_not_called()
    realtime.assert_not_called()
    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.skipped == 1


def test_final_close_intraday_target_skips_without_provider_or_state_update():
    target = _make_target(
        frequency="intraday",
        last_state=True,
        condition={"type": "close_cross_ma", "direction": "above", "period": 20},
    )
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df") as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="intraday")

    fetch_final.assert_not_called()
    realtime.assert_not_called()
    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.skipped == 1


def test_final_close_without_as_of_date_uses_current_shanghai_date(monkeypatch):
    target = _make_target(condition={"type": "close_cross_ma", "direction": "above", "period": 20})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 4, 0, 30, tzinfo=tz)

    monkeypatch.setattr("monitor.monitor_runner.datetime", FrozenDateTime)
    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=None) as fetch_final,
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily")

    fetch_final.assert_called_once_with("600519", date(2026, 6, 4), min_periods=21)
    realtime.assert_not_called()
    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.skipped == 1


def test_final_close_missing_close_skips_without_email_or_state_update():
    target = _make_target(
        last_state=True,
        condition={"type": "close_cross_ma", "direction": "above", "period": 20},
    )
    history = pd.DataFrame({COL_DATE: pd.date_range(end="2026-06-03", periods=21), COL_CLOSE: [10.0] * 20 + [None]})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=history),
        patch("monitor.monitor_runner.fetch_current_price") as realtime,
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(frequency="daily", as_of_date=date(2026, 6, 3))

    realtime.assert_not_called()
    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.skipped == 1


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


def test_workflow_auto_resets_without_blackroom_recheck_when_condition_clears():
    target = _make_target(last_state=True, reset_mode="auto")
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService") as blackroom,
        patch("monitor.monitor_runner.fetch_current_price", return_value=1600.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    blackroom.return_value.is_banned.assert_not_called()
    storage.update_monitor_target_state.assert_called_once_with(1, False, triggered_at=None)
    assert summary.errors == 0


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


def test_run_monitor_filters_by_workflow():
    owned = _make_target(id=1)
    owned.workflow = "forecast_ssf_ma20"
    manual = _make_target(id=2)
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [owned, manual]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    assert summary.total == 1
    assert storage.load_monitor_targets.call_args.kwargs == {"frequency": "daily", "workflow": "forecast_ssf_ma20"}


def test_banned_workflow_target_is_disabled_without_email():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    events = []
    storage.get_forecast_ssf_candidate_for_target.side_effect = lambda _: events.append("evidence")
    blackroom = MagicMock()

    def is_banned(*_: object) -> dict[str, object]:
        events.append("blackroom")
        return {"success": True, "data": {"banned": True}}

    blackroom.is_banned.side_effect = is_banned

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    email.assert_not_called()
    storage.disable_forecast_ssf_target_for_blackroom.assert_called_once_with(target.id, "active_blackroom")
    storage.update_monitor_target_state.assert_not_called()
    assert events == ["evidence", "blackroom"]
    assert blackroom.is_banned.call_count == 1
    assert summary.skipped == 1


def test_workflow_blackroom_lookup_failure_counts_as_error():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    blackroom = MagicMock()
    blackroom.is_banned.return_value = {"success": False, "message": "blackroom unavailable", "data": None}

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    email.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()
    assert summary.errors == 1
    assert summary.error_details == ["600519: blackroom unavailable"]


def test_workflow_alert_includes_candidate_evidence():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    storage.get_forecast_ssf_candidate_for_target.return_value = _candidate_evidence()
    blackroom = MagicMock()
    blackroom.is_banned.return_value = {"success": True, "data": {"banned": False}}

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as email,
    ):
        run_monitor(workflow="forecast_ssf_ma20")

    body = email.call_args.args[1]
    for value in ("2025-12-31", "50.0", "2026-01-15", "全国社保基金一一八组合", "2026-01-10"):
        assert value in body


def test_workflow_alert_checks_blackroom_after_evidence_before_email():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    events = []

    def get_candidate_evidence(_: object) -> SimpleNamespace:
        events.append("evidence")
        return _candidate_evidence()

    storage.get_forecast_ssf_candidate_for_target.side_effect = get_candidate_evidence
    blackroom = MagicMock()

    def is_banned(*_: object) -> dict[str, object]:
        events.append("blackroom")
        return {"success": True, "data": {"banned": False}}

    blackroom.is_banned.side_effect = is_banned

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email", side_effect=lambda *_: events.append("email")) as email,
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    email.assert_called_once()
    assert blackroom.is_banned.call_count == 1
    assert events == ["evidence", "blackroom", "email"]
    assert summary.triggered == 1


def test_workflow_blackroom_disable_failure_counts_as_error():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    storage.disable_forecast_ssf_target_for_blackroom.return_value = False
    blackroom = MagicMock()
    blackroom.is_banned.return_value = {"success": True, "data": {"banned": True}}

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email") as email,
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    email.assert_not_called()
    assert summary.skipped == 0
    assert summary.errors == 1
    assert "failed to disable forecast SSF target" in summary.error_details[0]


def test_workflow_email_failure_does_not_update_triggered_state():
    target = _make_target(last_state=False)
    target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]
    storage.get_forecast_ssf_candidate_for_target.return_value = _candidate_evidence()
    blackroom = MagicMock()
    blackroom.is_banned.return_value = {"success": True, "data": {"banned": False}}

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.BlackroomService", return_value=blackroom),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email", side_effect=RuntimeError("email unavailable")),
    ):
        summary = run_monitor(workflow="forecast_ssf_ma20")

    storage.update_monitor_target_state.assert_not_called()
    assert summary.errors == 1


@pytest.mark.parametrize(
    ("current_price", "last_state", "reset_mode"),
    [
        (1400.0, False, "auto"),  # triggered
        (1600.0, False, "auto"),  # condition false
        (1400.0, True, "auto"),  # already triggered
        (1600.0, True, "manual"),  # completed manual reset
    ],
)
def test_run_monitor_records_each_completed_evaluation(current_price, last_state, reset_mode):
    target = _make_target(last_state=last_state, reset_mode=reset_mode)
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=current_price),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
        patch("monitor.monitor_runner._utc_now", return_value=datetime(2026, 9, 7, tzinfo=timezone.utc)),
    ):
        summary = run_monitor()

    assert summary.errors == 0
    storage.record_monitor_target_evaluation.assert_called_once_with(
        target.id, datetime(2026, 9, 7, tzinfo=timezone.utc)
    )
    storage.record_monitor_target_evaluation_error.assert_not_called()


@pytest.mark.parametrize(
    "history",
    [
        None,
        pd.DataFrame({COL_DATE: pd.date_range("2026-06-03", periods=21), COL_CLOSE: [10.0] * 21}),
        pd.DataFrame({COL_DATE: pd.date_range("2026-06-02", periods=21), COL_CLOSE: [10.0] * 21}),
        pd.DataFrame({COL_DATE: pd.date_range("2026-06-03", periods=21), COL_CLOSE: [10.0] * 20 + [None]}),
    ],
)
def test_final_close_insufficient_data_does_not_record_health(history):
    target = _make_target(condition={"type": "close_cross_ma", "direction": "above", "period": 20})
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_final_close_history_df", return_value=history),
    ):
        summary = run_monitor(as_of_date=date(2026, 6, 3))

    assert summary.skipped == 1
    storage.record_monitor_target_evaluation.assert_not_called()
    storage.record_monitor_target_evaluation_error.assert_not_called()
    storage.update_monitor_target_state.assert_not_called()


@pytest.mark.parametrize(
    ("stage", "configure"),
    [
        ("market_data", lambda storage: patch("monitor.monitor_runner.fetch_current_price", side_effect=RuntimeError("https://secret.example/a"))),
        ("condition", lambda storage: patch("monitor.monitor_runner.evaluate_condition", side_effect=RuntimeError("condition failed"))),
        ("workflow_guard", lambda storage: patch("monitor.monitor_runner.BlackroomService", side_effect=RuntimeError("guard failed"))),
        ("notification", lambda storage: patch("monitor.monitor_runner.send_email", side_effect=RuntimeError("notification failed"))),
        ("storage", lambda storage: patch.object(storage, "record_monitor_target_evaluation", side_effect=RuntimeError("storage failed"))),
    ],
)
def test_run_monitor_records_sanitized_error_by_stage(stage, configure):
    target = _make_target()
    if stage == "workflow_guard":
        target.workflow = "forecast_ssf_ma20"
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [target]

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_current_price", return_value=1400.0),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
        patch("monitor.monitor_runner.send_email"),
        configure(storage),
    ):
        summary = run_monitor()

    assert summary.errors == 1
    call = storage.record_monitor_target_evaluation_error.call_args
    assert call.args[0:2] == (target.id, stage)
    assert call.args[2] is not None and len(call.args[2]) <= 240
    assert "https://" not in call.args[2]
    storage.record_monitor_target_evaluation.assert_not_called()


def test_error_health_write_failure_does_not_block_later_targets(caplog):
    failed, completed = _make_target(id=1), _make_target(id=2, stock_code="000001")
    storage = MagicMock()
    storage.load_monitor_targets.return_value = [failed, completed]
    storage.record_monitor_target_evaluation_error.side_effect = RuntimeError("secondary failure")

    with (
        patch("monitor.monitor_runner.get_storage", return_value=storage),
        patch("monitor.monitor_runner.fetch_current_price", side_effect=[RuntimeError("unknown failure"), 1600.0]),
        patch("monitor.monitor_runner.fetch_history_df", return_value=None),
    ):
        summary = run_monitor()

    assert summary.errors == 1
    assert summary.error_details == ["600519: unknown failure"]
    storage.record_monitor_target_evaluation_error.assert_called_once()
    storage.record_monitor_target_evaluation.assert_called_once()
    assert storage.record_monitor_target_evaluation.call_args.args[0] == completed.id
    assert "secondary failure" in caplog.text
