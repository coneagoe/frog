# Volatility Factor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 20-day return-volatility factor with full Alphapurify integration and tests, aligned with existing momentum/obos patterns.

**Architecture:** Implement the factor logic in a focused `factor/volatility.py` module, then add a dedicated `factor/alphapurify_volatility.py` script that follows the existing DB-to-panel-to-analyzer flow. Keep behavior and CLI conventions consistent with current factor scripts, and validate through one pure factor test file plus one script-flow test file.

**Tech Stack:** Python 3.11+, pandas, pytest, Poetry, existing storage/factor modules

---

## File map

- Create: `factor/volatility.py`
  - Define `COL_VOLATILITY` and `compute_volatility(prices, n=20)`.
- Create: `factor/alphapurify_volatility.py`
  - Parse CLI args, load DB history, normalize panel, run `FactorAnalyzer`.
- Create: `test/factor/test_volatility.py`
  - Verify volatility formula and window behavior.
- Create: `test/factor/test_alphapurify_volatility.py`
  - Verify end-to-end script wiring via mocked storage/analyzer.
- Modify: `docs/superpowers/specs/2026-05-15-volatility-factor-design.md` (only if implementation constraints force clarification updates).

### Task 1: Lock factor behavior with failing unit tests

**Files:**
- Create: `test/factor/test_volatility.py`
- Test target: `test/factor/test_volatility.py`

- [ ] **Step 1: Write failing tests for volatility definition and defaults**

```python
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from common.const import COL_CLOSE  # noqa: E402
from factor.volatility import COL_VOLATILITY, compute_volatility  # noqa: E402


def test_compute_volatility_uses_return_rolling_std():
    prices = pd.DataFrame({COL_CLOSE: [100.0, 110.0, 121.0, 133.1, 146.41]})

    result = compute_volatility(prices.copy(), n=2)

    expected_ret = prices[COL_CLOSE].pct_change()
    expected = expected_ret.rolling(2).std()
    pd.testing.assert_series_equal(
        result[COL_VOLATILITY].round(10),
        expected.round(10),
        check_names=True,
    )


def test_compute_volatility_default_window_is_20():
    prices = pd.DataFrame({COL_CLOSE: [100.0 + i for i in range(30)]})

    result = compute_volatility(prices.copy())

    assert result[COL_VOLATILITY].iloc[:20].isna().all()
    assert result[COL_VOLATILITY].iloc[21:].notna().any()
```

- [ ] **Step 2: Run the new unit tests and confirm initial failure**

Run: `poetry run pytest test/factor/test_volatility.py -v`

Expected: FAIL because `factor.volatility` does not exist yet.

- [ ] **Step 3: Commit test scaffold after Task 2 passes**

```bash
git add test/factor/test_volatility.py factor/volatility.py
git commit -m "feat: add volatility factor computation"
```

### Task 2: Implement volatility factor module

**Files:**
- Create: `factor/volatility.py`
- Test: `test/factor/test_volatility.py`

- [ ] **Step 1: Add minimal volatility implementation**

```python
import pandas as pd

from common.const import COL_CLOSE

COL_VOLATILITY = "volatility"
VOLATILITY_PARAM_N = 20


def compute_volatility(
    prices: pd.DataFrame, n: int = VOLATILITY_PARAM_N
) -> pd.DataFrame:
    returns = prices[COL_CLOSE].pct_change()
    prices[COL_VOLATILITY] = returns.rolling(n).std()
    return prices
```

- [ ] **Step 2: Run focused factor tests**

Run: `poetry run pytest test/factor/test_volatility.py -v`

Expected: PASS

- [ ] **Step 3: Run existing factor regression to ensure no collateral break**

Run: `poetry run pytest test/factor/test_momentum.py -v`

Expected: PASS

### Task 3: Add Alphapurify volatility script and its tests (TDD)

**Files:**
- Create: `factor/alphapurify_volatility.py`
- Create: `test/factor/test_alphapurify_volatility.py`
- Test targets: `test/factor/test_alphapurify_volatility.py`, `test/factor/test_alphapurify_momentum.py`, `test/factor/test_alphapurify_obos.py`

- [ ] **Step 1: Write failing integration-style test mirroring existing script tests**

```python
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import factor.alphapurify_volatility as alphapurify_volatility  # noqa: E402
from common.const import COL_CLOSE, COL_DATE, COL_STOCK_ID  # noqa: E402


def _make_history_df(rows: int = 60) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    closes = [100 + i * 0.2 for i in range(rows)]
    return pd.DataFrame({COL_DATE: dates, COL_CLOSE: closes})


def test_main_loads_db_data_and_writes_ic_report(tmp_path, monkeypatch):
    stock_info = pd.DataFrame({COL_STOCK_ID: ["000001", "000002"]})
    history_map = {"000001": _make_history_df(), "000002": _make_history_df()}

    storage = SimpleNamespace(
        load_general_info_stock=lambda: stock_info,
        load_history_data_stock=lambda stock_id, period, adjust, start_date=None, end_date=None: history_map[stock_id],
    )
    monkeypatch.setattr(alphapurify_volatility, "get_storage", lambda: storage)

    captured = {}

    class FakeFigure:
        def write_html(self, path):
            Path(path).write_text("ok", encoding="utf-8")

    class FakeFactorAnalyzer:
        def __init__(self, base_df, trade_date_col, symbol_col, price_col, factor_name, research_cfg=None, analysis_cfg=None):
            captured["base_df"] = base_df.copy()
            captured["trade_date_col"] = trade_date_col
            captured["symbol_col"] = symbol_col
            captured["price_col"] = price_col
            captured["factor_name"] = factor_name

        def run(self):
            captured["run_called"] = True

        def create_single_fac_ic_sheet(self):
            captured["ic_sheet_called"] = True
            return FakeFigure()

    monkeypatch.setattr(alphapurify_volatility, "FactorAnalyzer", FakeFactorAnalyzer)

    output_path = tmp_path / "volatility_ic.html"
    code = alphapurify_volatility.main(
        [
            "--start-date", "2024-01-01",
            "--end-date", "2024-12-31",
            "--max-stocks", "2",
            "--report-html", str(output_path),
        ]
    )

    assert code == 0
    assert captured["run_called"] is True
    assert captured["ic_sheet_called"] is True
    assert output_path.exists()
    assert captured["trade_date_col"] == "datetime"
    assert captured["symbol_col"] == "symbol"
    assert captured["price_col"] == "close"
    assert captured["factor_name"] == "volatility"
    assert not captured["base_df"].empty
```

- [ ] **Step 2: Run focused test and confirm failure**

Run: `poetry run pytest test/factor/test_alphapurify_volatility.py -v`

Expected: FAIL because the script is not implemented.

- [ ] **Step 3: Implement `factor/alphapurify_volatility.py` by adapting momentum script structure**

```python
#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.const import (  # noqa: E402
    COL_CLOSE,
    COL_DATE,
    COL_STOCK_ID,
    AdjustType,
    PeriodType,
)
from factor.volatility import COL_VOLATILITY, compute_volatility  # noqa: E402
from storage import get_storage  # noqa: E402

try:
    from alphapurify import FactorAnalyzer
except Exception:
    FactorAnalyzer = None

EXIT_OK = 0
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 DB 读取 A 股日线数据，计算波动率因子并用 Alphapurify 做分析"
    )
    parser.add_argument("--start-date", default="2024-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--max-stocks", type=int, default=100, help="最多读取多少只股票")
    parser.add_argument(
        "--adjust", choices=["qfq", "hfq"], default="qfq", help="读取 DB 时使用的复权类型"
    )
    parser.add_argument("--volatility-n", type=int, default=20, help="波动率窗口天数 N")
    parser.add_argument("--report-html", default=None, help="可选：IC 报告 HTML 输出路径")
    return parser


def _normalize_history_df(
    history_df: pd.DataFrame, stock_id: str, volatility_n: int
) -> pd.DataFrame:
    if history_df.empty:
        return pd.DataFrame()

    required_cols = [COL_DATE, COL_CLOSE]
    if any(col not in history_df.columns for col in required_cols):
        return pd.DataFrame()

    normalized = history_df[required_cols].copy()
    normalized[COL_DATE] = pd.to_datetime(normalized[COL_DATE], errors="coerce")
    normalized = normalized.dropna(subset=[COL_DATE]).sort_values(COL_DATE).reset_index(drop=True)
    if normalized.empty:
        return pd.DataFrame()

    normalized[COL_CLOSE] = pd.to_numeric(normalized[COL_CLOSE], errors="coerce")
    normalized = normalized.dropna(subset=[COL_CLOSE]).copy()
    normalized = compute_volatility(normalized, n=volatility_n)
    normalized = normalized.dropna(subset=[COL_VOLATILITY]).copy()
    if normalized.empty:
        return pd.DataFrame()

    normalized["datetime"] = normalized[COL_DATE]
    normalized["symbol"] = stock_id
    normalized["close"] = normalized[COL_CLOSE]
    return normalized.loc[:, ["datetime", "symbol", "close", COL_VOLATILITY]].copy()


def load_volatility_panel_from_db(
    storage: Any,
    start_date: str | None,
    end_date: str | None,
    max_stocks: int,
    adjust: str,
    volatility_n: int,
) -> pd.DataFrame:
    stock_info = storage.load_general_info_stock()
    if stock_info.empty or COL_STOCK_ID not in stock_info.columns:
        return pd.DataFrame(columns=["datetime", "symbol", "close", COL_VOLATILITY])

    adjust_type = AdjustType.QFQ if adjust == "qfq" else AdjustType.HFQ
    stock_ids = (
        stock_info[COL_STOCK_ID]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .drop_duplicates()
        .head(max_stocks)
        .tolist()
    )

    frames: list[pd.DataFrame] = []
    for stock_id in stock_ids:
        history_df = storage.load_history_data_stock(
            stock_id=stock_id,
            period=PeriodType.DAILY,
            adjust=adjust_type,
            start_date=start_date,
            end_date=end_date,
        )
        panel_piece = _normalize_history_df(
            history_df=history_df, stock_id=stock_id, volatility_n=volatility_n
        )
        if not panel_piece.empty:
            frames.append(panel_piece)

    if not frames:
        return pd.DataFrame(columns=["datetime", "symbol", "close", COL_VOLATILITY])

    return pd.concat(frames, ignore_index=True).sort_values(["datetime", "symbol"]).reset_index(drop=True)


def run_analysis(panel_df: pd.DataFrame, report_html: str | None = None) -> Any:
    if FactorAnalyzer is None:
        raise ImportError("alphapurify 未安装，请先执行: poetry run pip install alphapurify")

    analyzer = FactorAnalyzer(
        base_df=panel_df,
        trade_date_col="datetime",
        symbol_col="symbol",
        price_col="close",
        factor_name=COL_VOLATILITY,
    )
    analyzer.run()

    if report_html:
        fig = analyzer.create_single_fac_ic_sheet()
        output_path = Path(report_html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_path))

    return analyzer


def main(argv: list[str] | None = None, storage: Any | None = None) -> int:
    args = build_parser().parse_args(argv)
    storage = storage or get_storage()
    try:
        panel_df = load_volatility_panel_from_db(
            storage=storage,
            start_date=args.start_date,
            end_date=args.end_date,
            max_stocks=args.max_stocks,
            adjust=args.adjust,
            volatility_n=args.volatility_n,
        )
        if panel_df.empty:
            print("[错误] 未从 DB 构造出有效的波动率因子面板数据")
            return EXIT_ERROR

        analyzer = run_analysis(panel_df=panel_df, report_html=args.report_html)
    except Exception as exc:
        print(f"[错误] {exc}")
        return EXIT_ERROR

    print(
        f"面板数据: rows={len(panel_df)}, symbols={panel_df['symbol'].nunique()}, dates={panel_df['datetime'].nunique()}"
    )
    if getattr(analyzer, "mean_ics_dict", None) is not None:
        print(f"mean_ics_dict={analyzer.mean_ics_dict}")
    if args.report_html:
        print(f"IC 报告已输出: {args.report_html}")
    return EXIT_OK
```

- [ ] **Step 4: Run the new script test**

Run: `poetry run pytest test/factor/test_alphapurify_volatility.py -v`

Expected: PASS

- [ ] **Step 5: Run existing script tests for regression**

Run: `poetry run pytest test/factor/test_alphapurify_momentum.py test/factor/test_alphapurify_obos.py -v`

Expected: PASS

- [ ] **Step 6: Commit script + tests**

```bash
git add factor/alphapurify_volatility.py test/factor/test_alphapurify_volatility.py
git commit -m "feat: add alphapurify volatility factor workflow"
```

### Task 4: Final verification on touched factor scope

**Files:**
- Create/Modify: `factor/volatility.py`
- Create/Modify: `factor/alphapurify_volatility.py`
- Create/Modify: `test/factor/test_volatility.py`
- Create/Modify: `test/factor/test_alphapurify_volatility.py`

- [ ] **Step 1: Run full touched-factor test slice**

Run: `poetry run pytest test/factor/test_volatility.py test/factor/test_alphapurify_volatility.py test/factor/test_momentum.py test/factor/test_alphapurify_momentum.py test/factor/test_alphapurify_obos.py -v`

Expected: PASS

- [ ] **Step 2: Run pre-commit checks on touched files**

Run: `poetry run pre-commit run --files factor/volatility.py factor/alphapurify_volatility.py test/factor/test_volatility.py test/factor/test_alphapurify_volatility.py`

Expected: PASS

- [ ] **Step 3: Final commit**

```bash
git add factor/volatility.py factor/alphapurify_volatility.py test/factor/test_volatility.py test/factor/test_alphapurify_volatility.py
git commit -m "feat: implement volatility factor pipeline"
```
