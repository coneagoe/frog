import os
import sys
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import tools.stock_return_report as stock_return_report  # noqa: E402
from common.const import COL_CLOSE, COL_DATE, COL_STOCK_ID, COL_STOCK_NAME  # noqa: E402


def install_storage_stub(
    monkeypatch,
    history_by_stock_id: dict[str, pd.DataFrame],
    stock_info: pd.DataFrame | None = None,
):
    storage = SimpleNamespace()
    history_calls: list[str] = []

    def load_general_info_stock() -> pd.DataFrame:
        if stock_info is None:
            return pd.DataFrame()
        return stock_info

    def load_history_data_stock(
        stock_id, period, adjust, start_date=None, end_date=None
    ) -> pd.DataFrame:
        history_calls.append(stock_id)
        return history_by_stock_id.get(stock_id, pd.DataFrame())

    monkeypatch.setattr(
        storage, "load_general_info_stock", load_general_info_stock, raising=False
    )
    monkeypatch.setattr(
        storage, "load_history_data_stock", load_history_data_stock, raising=False
    )
    monkeypatch.setattr(stock_return_report, "get_storage", lambda: storage)
    return history_calls


def make_history_df(closes: list[float]) -> pd.DataFrame:
    base_date = pd.Timestamp("2026-03-01")
    return pd.DataFrame(
        {
            COL_DATE: [
                (base_date + pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
                for offset in range(len(closes))
            ],
            COL_CLOSE: closes,
        }
    )


def test_main_reads_stock_id_from_csv_and_prints_returns(tmp_path, capsys, monkeypatch):
    csv_path = tmp_path / "stocks.csv"
    pd.DataFrame({"stock_id": ["600547"]}).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )
    install_storage_stub(monkeypatch, {"600547": make_history_df(list(range(1, 26)))})

    exit_code = stock_return_report.main(["--input-csv", str(csv_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "600547" in output
    assert "25.00" in output
    assert "400.00" in output


def test_main_resolves_name_column_via_general_info_stock(tmp_path, monkeypatch):
    csv_path = tmp_path / "stocks.csv"
    pd.DataFrame({"name": ["山东黄金"]}).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )
    stock_info = pd.DataFrame(
        {
            COL_STOCK_ID: ["600547"],
            COL_STOCK_NAME: ["山东黄金"],
        }
    )
    history_calls = install_storage_stub(
        monkeypatch,
        {"600547": make_history_df(list(range(1, 26)))},
        stock_info=stock_info,
    )

    exit_code = stock_return_report.main(["--input-csv", str(csv_path)])

    assert exit_code == 0
    assert history_calls == ["600547"]


def test_main_exports_csv_when_output_path_given(tmp_path, monkeypatch):
    csv_path = tmp_path / "stocks.csv"
    output_path = tmp_path / "result.csv"
    pd.DataFrame({"stock_id": ["600547"]}).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )
    install_storage_stub(monkeypatch, {"600547": make_history_df(list(range(1, 26)))})

    exit_code = stock_return_report.main(
        ["--input-csv", str(csv_path), "--output-csv", str(output_path)],
    )

    assert exit_code == 0
    assert output_path.exists()
    exported = pd.read_csv(output_path, dtype={"stock_id": str})
    assert exported.loc[0, "stock_id"] == "600547"
    assert exported.loc[0, "weekly_return_pct"] == 25.0
    assert exported.loc[0, "monthly_return_pct"] == 400.0


def test_main_marks_missing_returns_when_history_is_insufficient(
    tmp_path, capsys, monkeypatch
):
    csv_path = tmp_path / "stocks.csv"
    pd.DataFrame({"stock_id": ["600547"]}).to_csv(
        csv_path, index=False, encoding="utf-8-sig"
    )
    install_storage_stub(monkeypatch, {"600547": make_history_df([10, 11, 12, 13, 14])})

    exit_code = stock_return_report.main(["--input-csv", str(csv_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "600547" in output
    assert "历史数据不足" in output
