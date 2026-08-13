from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from tools import backfill_forecast as command


def test_resolve_dates_uses_default_start_and_seven_day_lag():
    dates = command.resolve_dates(today=date(2026, 8, 13))

    assert dates[0] == date(2026, 1, 1)
    assert dates[-1] == date(2026, 8, 6)
    assert len(dates) == 218


def test_resolve_dates_includes_explicit_boundaries():
    assert command.resolve_dates(date(2026, 8, 1), date(2026, 8, 3)) == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]


def test_main_reports_complete_summary_and_continues_after_failed_date(monkeypatch, capsys):
    manager = MagicMock()
    manager.download_forecast.side_effect = [
        SimpleNamespace(announcement_date="20260801", source_rows=2, a_share_rows=2, saved=True),
        SimpleNamespace(announcement_date="20260802", source_rows=0, a_share_rows=0, saved=False),
        SimpleNamespace(announcement_date="20260803", source_rows=3, a_share_rows=0, saved=True),
    ]
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "DownloadManager", lambda: manager)

    assert command.main(["--start-date", "2026-08-01", "--end-date", "2026-08-03"]) == 1

    assert manager.download_forecast.call_args_list == [
        call(ann_date="20260801"),
        call(ann_date="20260802"),
        call(ann_date="20260803"),
    ]
    assert capsys.readouterr().out == (
        "requested_dates=3 successful_dates=2 empty_dates=1 failed_dates=1 "
        "source_rows=5 a_share_rows=2\nfailed_announcement_dates=20260802\n"
    )


def test_main_returns_zero_for_successful_empty_results(monkeypatch, capsys):
    manager = MagicMock()
    manager.download_forecast.return_value = SimpleNamespace(
        announcement_date="20260801", source_rows=0, a_share_rows=0, saved=True
    )
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "DownloadManager", lambda: manager)

    assert command.main(["--start-date", "2026-08-01", "--end-date", "2026-08-01"]) == 0
    assert "successful_dates=1 empty_dates=1 failed_dates=0" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--start-date", "2026-08-01"],
        ["--start-date", "2026-08-03", "--end-date", "2026-08-01"],
        ["--start-date", "2026-08-01", "--end-date", "2026-08-32"],
        ["--start-date", "20260801", "--end-date", "2026-08-03"],
        ["--start-date", "2026-W31-6", "--end-date", "2026-08-03"],
    ],
)
def test_main_rejects_invalid_date_range_arguments(argv):
    with pytest.raises(SystemExit) as exc_info:
        command.main(argv)

    assert exc_info.value.code == 2
