from datetime import date
from unittest.mock import MagicMock

import pytest

from forecast_snapshot import ForecastSnapshotSummary
from tools import create_forecast_snapshot as command


def test_main_prints_completed_snapshot_summary(monkeypatch, capsys):
    summary = ForecastSnapshotSummary(7, 1, "completed", 2, 2, 3, 3, 0, 0, None)
    service = MagicMock()
    service.create_snapshot.return_value = summary
    monkeypatch.setattr(command, "parse_config", lambda: None)
    monkeypatch.setattr(command, "ForecastSnapshotService", lambda: service)

    assert (
        command.main(
            [
                "--report-end-date",
                "2026-06-30",
                "--announcement-start-date",
                "2026-07-01",
                "--announcement-end-date",
                "2026-07-02",
            ]
        )
        == 0
    )
    assert service.create_snapshot.call_args.args[0].report_end_date == date(2026, 6, 30)
    assert "run_id=7 attempt=1 status=completed requested_date_count=2" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--announcement-start-date", "2026-07-01", "--announcement-end-date", "2026-07-02"],
        ["--report-end-date", "2026-06-30", "--announcement-end-date", "2026-07-02"],
        ["--report-end-date", "2026-06-30", "--announcement-start-date", "2026-07-01"],
        [
            "--report-end-date",
            "20260630",
            "--announcement-start-date",
            "2026-07-01",
            "--announcement-end-date",
            "2026-07-02",
        ],
        [
            "--report-end-date",
            "2026-06-30",
            "--announcement-start-date",
            "2026-07-01",
            "--announcement-end-date",
            "2026-07-32",
        ],
        [
            "--report-end-date",
            "2026-06-30",
            "--announcement-start-date",
            "2026-07-02",
            "--announcement-end-date",
            "2026-07-01",
        ],
    ],
)
def test_main_rejects_invalid_arguments_before_loading_configuration(monkeypatch, argv):
    parse_config = MagicMock()
    monkeypatch.setattr(command, "parse_config", parse_config)

    with pytest.raises(SystemExit) as exc_info:
        command.main(argv)

    assert exc_info.value.code == 2
    parse_config.assert_not_called()


def test_main_prints_failed_snapshot_diagnostic_and_returns_one(monkeypatch, capsys):
    summary = ForecastSnapshotSummary(8, 2, "failed", 2, 1, 3, 3, 0, 0, "2026-07-02: RuntimeError: unavailable")
    service = MagicMock()
    service.create_snapshot.return_value = summary
    parse_config = MagicMock()
    monkeypatch.setattr(command, "parse_config", parse_config)
    monkeypatch.setattr(command, "ForecastSnapshotService", lambda: service)

    assert (
        command.main(
            [
                "--report-end-date",
                "2026-06-30",
                "--announcement-start-date",
                "2026-07-01",
                "--announcement-end-date",
                "2026-07-02",
            ]
        )
        == 1
    )

    output = capsys.readouterr().out
    assert "status=failed" in output
    assert "failure_detail=2026-07-02: RuntimeError: unavailable" in output
    parse_config.assert_called_once_with()
