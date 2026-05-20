# SSF Top10 Alert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a weekly social-security-fund top10 floatholder change alert that runs after the existing `download_top10_floatholders_weekly` DAG finishes, scores stock-level changes, stores signals idempotently, and sends one ranked summary email when new signals appear.

**Architecture:** Keep the existing `top10_floatholders` download/storage pipeline intact and add a separate `shareholder_monitor` package for holder classification, two-period diffing, scoring, email formatting, and orchestration. Persist stock-level signals in a dedicated table with an `alert_sent_at` marker so reruns do not duplicate emails and email failures can be retried cleanly without touching the legacy price monitor.

**Tech Stack:** Python 3.11+, Poetry, pandas, SQLAlchemy, Airflow DAG source tests, pytest, pre-commit

---

## File map

- `shareholder_monitor/__init__.py` — package export for the new weekly alert runner.
- `shareholder_monitor/ssf_detector.py` — social-security-fund holder name detection rules.
- `shareholder_monitor/ssf_change_analyzer.py` — latest-vs-previous-announcement diff, stock-level aggregation, and composite score calculation.
- `shareholder_monitor/ssf_alert.py` — subject/body formatter for the ranked summary email.
- `shareholder_monitor/runner.py` — orchestration: fetch candidates, analyze, persist signals, send email, mark alerts sent.
- `storage/model/ssf_change_signal.py` — ORM model for persisted stock-level SSF change signals.
- `storage/model/__init__.py` — export the new ORM model and table name.
- `storage/__init__.py` — re-export the new table name alongside existing storage helpers.
- `storage/storage_db.py` — signal-table helpers and top10 history loaders used by the runner.
- `dags/download_top10_floatholders_weekly.py` — append one downstream analysis task after all existing partition download tasks.
- `test/shareholder_monitor/test_ssf_detector.py` — classification rule tests.
- `test/shareholder_monitor/test_ssf_change_analyzer.py` — diff/scoring tests for new entry, increase, decrease, and exit.
- `test/shareholder_monitor/test_ssf_alert.py` — email subject/body formatting tests.
- `test/shareholder_monitor/test_runner.py` — orchestration tests for save/send/mark-sent behavior.
- `test/storage/model/test_ssf_change_signal.py` — schema-level assertions for the new signal table.
- `test/storage/test_storage_db.py` — storage helper tests for candidates, history loading, saving signals, and marking alerts sent.
- `test/dags/test_download_top10_floatholders_weekly.py` — source-based DAG regression test for the appended analysis task and dependencies.

### Task 1: Add persisted SSF change signals and storage helpers

**Files:**
- Create: `storage/model/ssf_change_signal.py`
- Create: `test/storage/model/test_ssf_change_signal.py`
- Modify: `storage/model/__init__.py`
- Modify: `storage/__init__.py`
- Modify: `storage/storage_db.py`
- Modify: `test/storage/test_storage_db.py`

- [ ] **Step 1: Write the failing schema and storage tests**

Add a new schema test file that locks the table name, required columns, and unique key:

```python
from sqlalchemy import inspect

from storage.model.base import Base
from storage.model.ssf_change_signal import SSFChangeSignal, tb_name_ssf_change_signal


def test_ssf_change_signal_table_name():
    assert tb_name_ssf_change_signal == "ssf_change_signals"
    assert SSFChangeSignal.__tablename__ == "ssf_change_signals"


def test_ssf_change_signal_schema(sqlite_engine):
    Base.metadata.create_all(sqlite_engine)
    inspector = inspect(sqlite_engine)
    columns = {col["name"] for col in inspector.get_columns(tb_name_ssf_change_signal)}
    assert {"id", "stock_id", "ann_date", "prev_ann_date", "event_types", "score", "detail_json", "alert_sent_at"} <= columns

    unique_constraints = inspector.get_unique_constraints(tb_name_ssf_change_signal)
    assert any(
        set(constraint["column_names"]) == {"stock_id", "ann_date"}
        for constraint in unique_constraints
    )
```

Extend `test/storage/test_storage_db.py` with storage-level expectations:

```python
def test_list_ssf_change_signal_candidates_excludes_existing_signal(sqlite_storage):
    db = sqlite_storage
    db.ensure_ssf_change_signals_table()
    db.save_top10_floatholders(
        pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "ann_date": ["20240331", "20231231"],
                "end_date": ["20240331", "20231231"],
                "holder_name": ["全国社保基金一一八组合", "全国社保基金一一八组合"],
                "hold_amount": [1000.0, 900.0],
                "hold_ratio": [1.2, 1.0],
                "hold_float_ratio": [1.2, 1.0],
                "hold_change": [100.0, 0.0],
                "holder_type": ["机构", "机构"],
            }
        )
    )
    db.save_ssf_change_signals(
        [
            {
                "stock_id": "000001",
                "ann_date": "2024-03-31",
                "prev_ann_date": "2023-12-31",
                "event_types": ["increase"],
                "score": 78.0,
                "detail_json": {"holders": []},
            }
        ]
    )

    assert db.list_ssf_change_signal_candidates() == []


def test_mark_ssf_change_signals_alerted_sets_timestamp(sqlite_storage):
    db = sqlite_storage
    db.ensure_ssf_change_signals_table()
    ids = db.save_ssf_change_signals(
        [
            {
                "stock_id": "000001",
                "ann_date": "2024-03-31",
                "prev_ann_date": "2023-12-31",
                "event_types": ["increase"],
                "score": 78.0,
                "detail_json": {"holders": []},
            }
        ]
    )

    db.mark_ssf_change_signals_alerted(ids)
    pending = db.list_pending_ssf_change_signals()
    assert pending == []
```

- [ ] **Step 2: Run the storage tests to verify they fail**

Run:

```bash
poetry run pytest test/storage/model/test_ssf_change_signal.py test/storage/test_storage_db.py -k ssf_change_signal -v
```

Expected: FAIL because the ORM model and new `StorageDb` methods do not exist yet.

- [ ] **Step 3: Implement the ORM model, exports, and storage methods**

Create `storage/model/ssf_change_signal.py`:

```python
from sqlalchemy import JSON, Column, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base

tb_name_ssf_change_signal = "ssf_change_signals"


class SSFChangeSignal(Base):
    __tablename__ = tb_name_ssf_change_signal
    __table_args__ = (
        UniqueConstraint("stock_id", "ann_date", name="uq_ssf_change_signal_stock_ann_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(6), nullable=False, comment="股票代码")
    ann_date = Column(Date, nullable=False, comment="最新公告日期")
    prev_ann_date = Column(Date, nullable=False, comment="上期公告日期")
    event_types = Column(JSON, nullable=False, comment="股票级事件类型列表")
    score = Column(Float, nullable=False, comment="综合分")
    ssf_holder_count_now = Column(Integer, nullable=False, default=0, server_default="0")
    ssf_holder_count_prev = Column(Integer, nullable=False, default=0, server_default="0")
    ssf_holder_count_change = Column(Integer, nullable=False, default=0, server_default="0")
    ssf_total_hold_ratio_now = Column(Float, nullable=False, default=0.0, server_default="0")
    ssf_total_hold_ratio_prev = Column(Float, nullable=False, default=0.0, server_default="0")
    ssf_total_hold_ratio_change = Column(Float, nullable=False, default=0.0, server_default="0")
    detail_json = Column(JSON, nullable=False, comment="股东级明细")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    alert_sent_at = Column(DateTime(timezone=True), nullable=True, comment="汇总邮件发送时间")
```

Export it in `storage/model/__init__.py` and `storage/__init__.py`, then add these methods to `storage/storage_db.py`:

```python
def ensure_ssf_change_signals_table(self) -> None:
    from .model.ssf_change_signal import SSFChangeSignal  # noqa: F401

    SSFChangeSignal.__table__.create(self.engine, checkfirst=True)


def list_ssf_change_signal_candidates(self) -> List[tuple[str, str]]:
    sql = textwrap.dedent(
        f"""\
        SELECT DISTINCT t."{COL_STOCK_ID}" AS stock_id, t."{COL_ANN_DATE}" AS ann_date
        FROM {tb_name_top10_floatholders} t
        JOIN (
            SELECT "{COL_STOCK_ID}" AS stock_id, MAX("{COL_ANN_DATE}") AS ann_date
            FROM {tb_name_top10_floatholders}
            GROUP BY "{COL_STOCK_ID}"
        ) latest
          ON t."{COL_STOCK_ID}" = latest.stock_id
         AND t."{COL_ANN_DATE}" = latest.ann_date
        LEFT JOIN {tb_name_ssf_change_signal} s
          ON s.stock_id = latest.stock_id
         AND s.ann_date = latest.ann_date
        WHERE s.id IS NULL
        ORDER BY latest.ann_date DESC, latest.stock_id
        """
    )
    assert self.engine is not None
    df = pd.read_sql(sql, self.engine)
    return [(row["stock_id"], str(row["ann_date"])) for _, row in df.iterrows()]


def save_ssf_change_signals(self, records: List[Dict[str, Any]]) -> List[int]:
    from .model.ssf_change_signal import SSFChangeSignal

    assert self.Session is not None
    session = self.Session()
    try:
        inserted: List[int] = []
        for payload in records:
            existing = session.query(SSFChangeSignal).filter_by(
                stock_id=payload["stock_id"],
                ann_date=pd.to_datetime(payload["ann_date"]).date(),
            ).first()
            if existing is not None:
                continue
            signal = SSFChangeSignal(**payload)
            session.add(signal)
            session.flush()
            inserted.append(signal.id)
        session.commit()
        return inserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_pending_ssf_change_signals(self) -> List[Any]:
    from .model.ssf_change_signal import SSFChangeSignal

    assert self.Session is not None
    session = self.Session()
    try:
        return session.query(SSFChangeSignal).filter(
            SSFChangeSignal.alert_sent_at.is_(None)
        ).order_by(SSFChangeSignal.score.desc(), SSFChangeSignal.stock_id.asc()).all()
    finally:
        session.close()


def mark_ssf_change_signals_alerted(self, ids: List[int]) -> None:
    from .model.ssf_change_signal import SSFChangeSignal

    if not ids:
        return

    assert self.Session is not None
    session = self.Session()
    try:
        session.query(SSFChangeSignal).filter(SSFChangeSignal.id.in_(ids)).update(
            {"alert_sent_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Re-run the storage tests**

Run:

```bash
poetry run pytest test/storage/model/test_ssf_change_signal.py test/storage/test_storage_db.py -k ssf_change_signal -v
```

Expected: PASS for the new schema and storage helper tests.

- [ ] **Step 5: Commit the persistence slice**

Run:

```bash
git add storage/model/ssf_change_signal.py storage/model/__init__.py storage/__init__.py storage/storage_db.py \
  test/storage/model/test_ssf_change_signal.py test/storage/test_storage_db.py
git commit -m "feat: add ssf change signal storage" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 2: Implement holder detection, diffing, and composite scoring

**Files:**
- Create: `shareholder_monitor/__init__.py`
- Create: `shareholder_monitor/ssf_detector.py`
- Create: `shareholder_monitor/ssf_change_analyzer.py`
- Create: `test/shareholder_monitor/test_ssf_detector.py`
- Create: `test/shareholder_monitor/test_ssf_change_analyzer.py`

- [ ] **Step 1: Write the failing detector/analyzer tests**

Create `test/shareholder_monitor/test_ssf_detector.py`:

```python
from shareholder_monitor.ssf_detector import is_social_security_holder


def test_is_social_security_holder_matches_ssf_keywords():
    assert is_social_security_holder("全国社保基金一一八组合") is True
    assert is_social_security_holder("基本养老保险基金八零二组合") is True


def test_is_social_security_holder_rejects_non_ssf_names():
    assert is_social_security_holder("香港中央结算有限公司") is False
    assert is_social_security_holder("招商银行股份有限公司") is False
```

Create `test/shareholder_monitor/test_ssf_change_analyzer.py` with one stock covering all event types:

```python
import pandas as pd

from shareholder_monitor.ssf_change_analyzer import analyze_ssf_change


def test_analyze_ssf_change_builds_rankable_stock_signal():
    history = pd.DataFrame(
        {
            "股票代码": ["000001"] * 5,
            "公告日期": pd.to_datetime(["2024-03-31"] * 3 + ["2023-12-31"] * 2),
            "股东名称": [
                "全国社保基金一一八组合",
                "全国社保基金四零六组合",
                "香港中央结算有限公司",
                "全国社保基金一一八组合",
                "全国社保基金五零三组合",
            ],
            "持有数量（万股）": [1200.0, 600.0, 2000.0, 1000.0, 500.0],
            "占总流通股本持股比例": [1.5, 0.8, 2.0, 1.2, 0.6],
            "持股变动": [200.0, 600.0, 0.0, 0.0, 0.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["stock_id"] == "000001"
    assert signal["event_types"] == ["new_entry", "increase", "exit"]
    assert signal["ssf_holder_count_now"] == 2
    assert signal["ssf_holder_count_prev"] == 2
    assert signal["ssf_total_hold_ratio_change"] > 0
    assert signal["score"] > 0
```

- [ ] **Step 2: Run the detector/analyzer tests to verify they fail**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_detector.py test/shareholder_monitor/test_ssf_change_analyzer.py -v
```

Expected: FAIL because the `shareholder_monitor` package does not exist yet.

- [ ] **Step 3: Implement the detector and analyzer minimally**

Create `shareholder_monitor/ssf_detector.py`:

```python
SSF_HOLDER_KEYWORDS = (
    "全国社保基金",
    "社保基金",
    "基本养老保险基金",
)


def is_social_security_holder(holder_name: str) -> bool:
    if not holder_name:
        return False
    normalized = holder_name.strip()
    return any(keyword in normalized for keyword in SSF_HOLDER_KEYWORDS)
```

Create `shareholder_monitor/ssf_change_analyzer.py`:

```python
from __future__ import annotations

from typing import Any

import pandas as pd

from common.const import (
    COL_ANN_DATE,
    COL_FLOAT_HOLDER_HOLD_AMOUNT,
    COL_FLOAT_HOLDER_HOLD_CHANGE,
    COL_FLOAT_HOLDER_HOLD_RATIO,
    COL_FLOAT_HOLDER_NAME,
)

from .ssf_detector import is_social_security_holder


EVENT_WEIGHTS = {
    "new_entry": 1.0,
    "increase": 0.7,
    "decrease": -0.7,
    "exit": -1.0,
}
EVENT_ORDER = ["new_entry", "increase", "decrease", "exit"]


def analyze_ssf_change(stock_id: str, history_df: pd.DataFrame) -> dict[str, Any] | None:
    ann_dates = sorted(pd.to_datetime(history_df[COL_ANN_DATE]).dt.date.unique(), reverse=True)
    if len(ann_dates) < 2:
        return None

    latest_ann_date, prev_ann_date = ann_dates[:2]
    latest_df = history_df[pd.to_datetime(history_df[COL_ANN_DATE]).dt.date == latest_ann_date]
    prev_df = history_df[pd.to_datetime(history_df[COL_ANN_DATE]).dt.date == prev_ann_date]

    latest_ssf = latest_df[latest_df[COL_FLOAT_HOLDER_NAME].map(is_social_security_holder)]
    prev_ssf = prev_df[prev_df[COL_FLOAT_HOLDER_NAME].map(is_social_security_holder)]
    if latest_ssf.empty and prev_ssf.empty:
        return None

    latest_map = latest_ssf.set_index(COL_FLOAT_HOLDER_NAME)[COL_FLOAT_HOLDER_HOLD_AMOUNT].to_dict()
    prev_map = prev_ssf.set_index(COL_FLOAT_HOLDER_NAME)[COL_FLOAT_HOLDER_HOLD_AMOUNT].to_dict()

    event_types: list[str] = []
    detail_rows: list[dict[str, Any]] = []
    for holder_name in sorted(set(latest_map) | set(prev_map)):
        latest_amount = latest_map.get(holder_name)
        prev_amount = prev_map.get(holder_name)
        if prev_amount is None:
            event_type = "new_entry"
        elif latest_amount is None:
            event_type = "exit"
        elif float(latest_amount) > float(prev_amount):
            event_type = "increase"
        elif float(latest_amount) < float(prev_amount):
            event_type = "decrease"
        else:
            continue
        event_types.append(event_type)
        detail_rows.append({"holder_name": holder_name, "event_type": event_type, "latest_amount": latest_amount, "prev_amount": prev_amount})

    if not event_types:
        return None

    latest_ratio = float(latest_ssf[COL_FLOAT_HOLDER_HOLD_RATIO].fillna(0).sum())
    prev_ratio = float(prev_ssf[COL_FLOAT_HOLDER_HOLD_RATIO].fillna(0).sum())
    count_now = int(len(latest_ssf))
    count_prev = int(len(prev_ssf))

    event_score = sum(EVENT_WEIGHTS[event] for event in event_types) / len(event_types)
    count_score = min(max((count_now - count_prev) + count_now, 0), 5) / 5
    concentration_score = min(max(latest_ratio - prev_ratio + latest_ratio, 0.0), 5.0) / 5.0
    score = round(50 * event_score + 20 * count_score + 30 * concentration_score, 2)

    return {
        "stock_id": stock_id,
        "ann_date": latest_ann_date.isoformat(),
        "prev_ann_date": prev_ann_date.isoformat(),
        "event_types": [event for event in EVENT_ORDER if event in event_types],
        "score": score,
        "ssf_holder_count_now": count_now,
        "ssf_holder_count_prev": count_prev,
        "ssf_holder_count_change": count_now - count_prev,
        "ssf_total_hold_ratio_now": round(latest_ratio, 4),
        "ssf_total_hold_ratio_prev": round(prev_ratio, 4),
        "ssf_total_hold_ratio_change": round(latest_ratio - prev_ratio, 4),
        "detail_json": {"holders": detail_rows},
    }
```

Create `shareholder_monitor/__init__.py`:

```python
from .ssf_change_analyzer import analyze_ssf_change

__all__ = ["analyze_ssf_change"]
```

- [ ] **Step 4: Re-run the detector/analyzer tests**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_detector.py test/shareholder_monitor/test_ssf_change_analyzer.py -v
```

Expected: PASS for holder classification and stock-level diff/scoring behavior.

- [ ] **Step 5: Commit the pure-analysis slice**

Run:

```bash
git add shareholder_monitor/__init__.py shareholder_monitor/ssf_detector.py shareholder_monitor/ssf_change_analyzer.py \
  test/shareholder_monitor/test_ssf_detector.py test/shareholder_monitor/test_ssf_change_analyzer.py
git commit -m "feat: analyze ssf top10 holder changes" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 3: Add summary email formatting and the weekly orchestration runner

**Files:**
- Create: `shareholder_monitor/ssf_alert.py`
- Create: `shareholder_monitor/runner.py`
- Create: `test/shareholder_monitor/test_ssf_alert.py`
- Create: `test/shareholder_monitor/test_runner.py`
- Modify: `shareholder_monitor/__init__.py`
- Modify: `storage/storage_db.py`

- [ ] **Step 1: Write the failing formatter/runner tests**

Create `test/shareholder_monitor/test_ssf_alert.py`:

```python
from shareholder_monitor.ssf_alert import build_ssf_change_alert_email


def test_build_ssf_change_alert_email_orders_by_score_desc():
    subject, body = build_ssf_change_alert_email(
        [
            {"stock_id": "000002", "score": 61.0, "event_types": ["decrease"], "ssf_holder_count_change": -1, "ssf_total_hold_ratio_change": -0.5, "detail_json": {"holders": []}},
            {"stock_id": "000001", "score": 88.0, "event_types": ["new_entry", "increase"], "ssf_holder_count_change": 1, "ssf_total_hold_ratio_change": 0.8, "detail_json": {"holders": []}},
        ],
        "2024-03-31",
    )

    assert "[社保持仓变动提醒]" in subject
    assert body.index("000001") < body.index("000002")
```

Create `test/shareholder_monitor/test_runner.py`:

```python
from unittest.mock import MagicMock, patch

from shareholder_monitor.runner import run_ssf_change_alert


def test_run_ssf_change_alert_saves_sends_and_marks():
    mock_storage = MagicMock()
    mock_storage.list_ssf_change_signal_candidates.return_value = [("000001", "2024-03-31")]
    mock_storage.load_top10_floatholders_history.return_value = make_history_df()
    mock_storage.save_ssf_change_signals.return_value = [1]
    mock_storage.list_pending_ssf_change_signals.return_value = [
        MagicMock(id=1, stock_id="000001", ann_date="2024-03-31", score=88.0, event_types=["increase"], ssf_holder_count_change=1, ssf_total_hold_ratio_change=0.8, detail_json={"holders": []})
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
```

- [ ] **Step 2: Run the formatter/runner tests to verify they fail**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_alert.py test/shareholder_monitor/test_runner.py -v
```

Expected: FAIL because the formatter, runner, and extra storage read helper do not exist yet.

- [ ] **Step 3: Implement the formatter and runner minimally**

Create `shareholder_monitor/ssf_alert.py`:

```python
from __future__ import annotations

from typing import Any


def build_ssf_change_alert_email(signals: list[Any], ann_date: str) -> tuple[str, str]:
    ranked = sorted(signals, key=lambda item: float(getattr(item, "score", item["score"])), reverse=True)
    subject = f"[社保持仓变动提醒] {ann_date} 新增 {len(ranked)} 只，按综合分排序"
    lines = [f"公告日期: {ann_date}", ""]
    for idx, item in enumerate(ranked, start=1):
        stock_id = getattr(item, "stock_id", item["stock_id"])
        event_types = getattr(item, "event_types", item["event_types"])
        score = getattr(item, "score", item["score"])
        count_change = getattr(item, "ssf_holder_count_change", item["ssf_holder_count_change"])
        ratio_change = getattr(item, "ssf_total_hold_ratio_change", item["ssf_total_hold_ratio_change"])
        lines.append(
            f"{idx}. {stock_id} | score={score} | events={','.join(event_types)} | "
            f"count_change={count_change} | ratio_change={ratio_change}"
        )
    return subject, "\n".join(lines)
```

In `storage/storage_db.py`, add the top10 history loader the runner needs:

```python
def load_top10_floatholders_history(self, stock_id: str, limit_ann_dates: int = 2) -> pd.DataFrame:
    sql = textwrap.dedent(
        f"""\
        SELECT *
        FROM {tb_name_top10_floatholders}
        WHERE "{COL_STOCK_ID}" = %(stock_id)s
          AND "{COL_ANN_DATE}" IN (
              SELECT DISTINCT "{COL_ANN_DATE}"
              FROM {tb_name_top10_floatholders}
              WHERE "{COL_STOCK_ID}" = %(stock_id)s
              ORDER BY "{COL_ANN_DATE}" DESC
              LIMIT %(limit_ann_dates)s
          )
        ORDER BY "{COL_ANN_DATE}" DESC, "{COL_FLOAT_HOLDER_NAME}"
        """
    )
    assert self.engine is not None
    return pd.read_sql(sql, self.engine, params={"stock_id": stock_id, "limit_ann_dates": limit_ann_dates})
```

Create `shareholder_monitor/runner.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from storage import get_storage
from utility import send_email

from .ssf_alert import build_ssf_change_alert_email
from .ssf_change_analyzer import analyze_ssf_change


@dataclass
class SSFAlertSummary:
    candidates: int = 0
    inserted: int = 0
    emailed: int = 0


def run_ssf_change_alert() -> SSFAlertSummary:
    storage = get_storage()
    storage.ensure_ssf_change_signals_table()

    summary = SSFAlertSummary()
    candidates = storage.list_ssf_change_signal_candidates()
    summary.candidates = len(candidates)

    signal_payloads = []
    for stock_id, _ in candidates:
        history_df = storage.load_top10_floatholders_history(stock_id)
        signal = analyze_ssf_change(stock_id, history_df)
        if signal is not None:
            signal_payloads.append(signal)

    inserted_ids = storage.save_ssf_change_signals(signal_payloads)
    summary.inserted = len(inserted_ids)
    pending = storage.list_pending_ssf_change_signals()
    if not pending:
        return summary

    ann_date = str(max(getattr(item, "ann_date") for item in pending))
    subject, body = build_ssf_change_alert_email(pending, ann_date)
    send_email(subject, body)
    storage.mark_ssf_change_signals_alerted([item.id for item in pending])
    summary.emailed = len(pending)
    return summary
```

Update `shareholder_monitor/__init__.py`:

```python
from .runner import SSFAlertSummary, run_ssf_change_alert
from .ssf_change_analyzer import analyze_ssf_change

__all__ = ["SSFAlertSummary", "analyze_ssf_change", "run_ssf_change_alert"]
```

- [ ] **Step 4: Re-run the formatter/runner tests**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_alert.py test/shareholder_monitor/test_runner.py -v
```

Expected: PASS for ranked email formatting and end-to-end orchestration.

- [ ] **Step 5: Commit the runner slice**

Run:

```bash
git add shareholder_monitor/__init__.py shareholder_monitor/ssf_alert.py shareholder_monitor/runner.py storage/storage_db.py \
  test/shareholder_monitor/test_ssf_alert.py test/shareholder_monitor/test_runner.py
git commit -m "feat: send ssf change summary email" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 4: Wire the runner into the existing weekly DAG

**Files:**
- Modify: `dags/download_top10_floatholders_weekly.py`
- Create: `test/dags/test_download_top10_floatholders_weekly.py`

- [ ] **Step 1: Write the failing DAG source test**

Create `test/dags/test_download_top10_floatholders_weekly.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_top10_floatholders_weekly_dag_has_downstream_analysis_task():
    source = (ROOT / "dags/download_top10_floatholders_weekly.py").read_text(encoding="utf-8")

    assert 'task_id="analyze_ssf_change_signals"' in source
    assert "python_callable=run_ssf_change_alert" in source
    assert "partition_tasks = [" in source
    assert "for task in partition_tasks:" in source
    assert "task >> analysis_task" in source
```

- [ ] **Step 2: Run the DAG source test to verify it fails**

Run:

```bash
poetry run pytest test/dags/test_download_top10_floatholders_weekly.py -v
```

Expected: FAIL because the DAG does not yet define the downstream analysis task.

- [ ] **Step 3: Append the analysis task without changing the weekly schedule**

Update `dags/download_top10_floatholders_weekly.py` like this:

```python
from shareholder_monitor import run_ssf_change_alert  # noqa: E402

dag = DAG(
    "download_top10_floatholders_weekly",
    default_args=get_default_args(),
    description="Weekly A-share top10_floatholders download",
    schedule="0 21 * * 0",
    catchup=False,
    max_active_runs=1,
)

partition_tasks = [
    PythonOperator(
        task_id=f"download_top10_floatholders_p{pid:02d}",
        python_callable=download_top10_floatholders_partition_task,
        op_kwargs={"partition_id": pid, "partition_count": PARTITION_COUNT},
        dag=dag,
    )
    for pid in get_partition_ids(PARTITION_COUNT)
]

analysis_task = PythonOperator(
    task_id="analyze_ssf_change_signals",
    python_callable=run_ssf_change_alert,
    dag=dag,
)

for task in partition_tasks:
    task >> analysis_task
```

Do not change `schedule`, `catchup`, `max_active_runs`, or the partition task callable signature.

- [ ] **Step 4: Re-run the DAG source test**

Run:

```bash
poetry run pytest test/dags/test_download_top10_floatholders_weekly.py -v
```

Expected: PASS for the new downstream analysis-task assertion.

- [ ] **Step 5: Commit the DAG wiring slice**

Run:

```bash
git add dags/download_top10_floatholders_weekly.py test/dags/test_download_top10_floatholders_weekly.py
git commit -m "feat: run ssf alert analysis after top10 downloads" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

### Task 5: Run the integrated verification sweep

**Files:**
- Modify: `shareholder_monitor/ssf_change_analyzer.py`
- Modify: `shareholder_monitor/runner.py`
- Modify: `storage/storage_db.py`
- Modify: `test/shareholder_monitor/test_ssf_change_analyzer.py`
- Modify: `test/shareholder_monitor/test_runner.py`

- [ ] **Step 1: Add the final regression tests that close the spec gaps**

Extend `test/shareholder_monitor/test_ssf_change_analyzer.py` with an explicit exit-only case:

```python
def test_analyze_ssf_change_returns_exit_signal_when_latest_period_has_no_ssf_holder():
    history = pd.DataFrame(
        {
            "股票代码": ["000001", "000001"],
            "公告日期": pd.to_datetime(["2024-03-31", "2023-12-31"]),
            "股东名称": ["香港中央结算有限公司", "全国社保基金四零六组合"],
            "持有数量（万股）": [2000.0, 900.0],
            "占总流通股本持股比例": [2.0, 1.1],
            "持股变动": [0.0, 0.0],
        }
    )

    signal = analyze_ssf_change("000001", history)

    assert signal is not None
    assert signal["event_types"] == ["exit"]
```

Extend `test/shareholder_monitor/test_runner.py` with the no-new-signal case:

```python
def test_run_ssf_change_alert_skips_email_when_nothing_new():
    mock_storage = MagicMock()
    mock_storage.list_ssf_change_signal_candidates.return_value = []
    mock_storage.list_pending_ssf_change_signals.return_value = []

    with (
        patch("shareholder_monitor.runner.get_storage", return_value=mock_storage),
        patch("shareholder_monitor.runner.send_email") as mock_email,
    ):
        summary = run_ssf_change_alert()

    mock_email.assert_not_called()
    assert summary.inserted == 0
    assert summary.emailed == 0
```

- [ ] **Step 2: Run the focused end-to-end test set**

Run:

```bash
poetry run pytest \
  test/shareholder_monitor/test_ssf_detector.py \
  test/shareholder_monitor/test_ssf_change_analyzer.py \
  test/shareholder_monitor/test_ssf_alert.py \
  test/shareholder_monitor/test_runner.py \
  test/storage/model/test_ssf_change_signal.py \
  test/storage/test_storage_db.py -k "ssf_change_signal or top10_floatholders or ssf_" -v
```

Expected: PASS for the new package, storage helpers, and signal lifecycle.

- [ ] **Step 3: Run the DAG regression plus targeted repository checks**

Run:

```bash
poetry run pytest test/dags/test_download_top10_floatholders_weekly.py test/dags/test_partition_dag_sources.py -v
poetry run pre-commit run --files \
  shareholder_monitor/__init__.py \
  shareholder_monitor/ssf_detector.py \
  shareholder_monitor/ssf_change_analyzer.py \
  shareholder_monitor/ssf_alert.py \
  shareholder_monitor/runner.py \
  storage/model/ssf_change_signal.py \
  storage/model/__init__.py \
  storage/__init__.py \
  storage/storage_db.py \
  dags/download_top10_floatholders_weekly.py \
  test/shareholder_monitor/test_ssf_detector.py \
  test/shareholder_monitor/test_ssf_change_analyzer.py \
  test/shareholder_monitor/test_ssf_alert.py \
  test/shareholder_monitor/test_runner.py \
  test/storage/model/test_ssf_change_signal.py \
  test/storage/test_storage_db.py \
  test/dags/test_download_top10_floatholders_weekly.py
```

Expected: PASS for DAG source wiring and repository format/lint hooks on touched files.

- [ ] **Step 4: Apply only the minimal fixes surfaced by the verification sweep**

If the verification sweep exposes ordering or serialization issues, keep the fixes local. For example, if SQLAlchemy model instances do not serialize cleanly in the formatter, normalize them before formatting:

```python
def _signal_value(signal, field: str):
    return getattr(signal, field, signal[field])
```

If pandas returns `Timestamp` instead of `date`, normalize inside the analyzer/runner boundary:

```python
latest_ann_date = pd.to_datetime(latest_ann_date).date().isoformat()
```

Do not add new features in this step; only close verification failures.

- [ ] **Step 5: Commit the verification fixes**

Run:

```bash
git add shareholder_monitor storage dags test
git commit -m "fix: finalize ssf top10 alert flow" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
