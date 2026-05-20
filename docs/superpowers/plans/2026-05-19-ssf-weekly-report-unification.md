# SSF Weekly Report Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the SSF weekly alert so each DAG run sends one unified weekly email ranked across all pending signals instead of sending one email per announcement date.

**Architecture:** Keep signal generation, scoring, persistence, and retry semantics unchanged. Only modify the alert formatting layer and the runner's final delivery step so all pending signals flow through a single ranking pool and a single `send_email()` / `mark_ssf_change_signals_alerted()` call.

**Tech Stack:** Python 3.12, Poetry, pytest, pandas, Airflow-oriented orchestration code, unittest.mock

---

## File map

- `shareholder_monitor/ssf_alert.py` — builds the weekly email subject/body from the pending signal list.
- `shareholder_monitor/runner.py` — loads pending signals and controls one-shot email delivery plus post-send marking.
- `test/shareholder_monitor/test_ssf_alert.py` — locks the new one-email weekly report subject/body and global score ordering.
- `test/shareholder_monitor/test_runner.py` — locks orchestration behavior: single send, one bulk mark, retry semantics unchanged.

### Task 1: Update the alert formatter for one unified weekly report

**Files:**
- Modify: `test/shareholder_monitor/test_ssf_alert.py`
- Modify: `shareholder_monitor/ssf_alert.py`

- [ ] **Step 1: Write the failing formatter tests**

Replace `test/shareholder_monitor/test_ssf_alert.py` with:

```python
from shareholder_monitor.ssf_alert import build_ssf_change_alert_email


def test_build_ssf_change_alert_email_builds_weekly_summary_and_global_ranking():
    subject, body = build_ssf_change_alert_email(
        [
            {
                "stock_id": "000002",
                "ann_date": "2024-03-31",
                "score": 61.0,
                "event_types": ["decrease"],
                "ssf_holder_count_change": -1,
                "ssf_total_hold_ratio_change": -0.5,
                "detail_json": {"holders": []},
            },
            {
                "stock_id": "000001",
                "ann_date": "2024-06-30",
                "score": 88.0,
                "event_types": ["new_entry", "increase"],
                "ssf_holder_count_change": 1,
                "ssf_total_hold_ratio_change": 0.8,
                "detail_json": {"holders": []},
            },
        ]
    )

    assert subject == "[社保持仓周报] 本周新增 2 只，按综合分排序"
    assert "待发送信号数: 2" in body
    assert "公告日期范围: 2024-03-31 ~ 2024-06-30" in body
    assert "排序规则: 按单条信号综合分降序" in body
    assert body.index("000001 | ann_date=2024-06-30 | score=88.0") < body.index(
        "000002 | ann_date=2024-03-31 | score=61.0"
    )


def test_build_ssf_change_alert_email_works_with_object_style_signals():
    class Signal:
        def __init__(self):
            self.stock_id = "000003"
            self.ann_date = "2024-09-30"
            self.score = 92.0
            self.event_types = ["increase"]
            self.ssf_holder_count_change = 2
            self.ssf_total_hold_ratio_change = 1.3

    subject, body = build_ssf_change_alert_email([Signal()])

    assert subject == "[社保持仓周报] 本周新增 1 只，按综合分排序"
    assert "000003 | ann_date=2024-09-30 | score=92.0" in body
```

- [ ] **Step 2: Run the formatter tests to verify they fail**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_alert.py -v
```

Expected: FAIL because `build_ssf_change_alert_email()` still requires `ann_date` as a second argument and still emits the per-announcement-date subject/body format.

- [ ] **Step 3: Implement the minimal formatter change**

Update `shareholder_monitor/ssf_alert.py` to:

```python
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any


def _read_signal_value(signal: Any, key: str) -> Any:
    if isinstance(signal, Mapping):
        return signal[key]
    return getattr(signal, key)


def _format_ann_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def build_ssf_change_alert_email(signals: list[Any]) -> tuple[str, str]:
    ranked = sorted(
        signals,
        key=lambda item: float(_read_signal_value(item, "score")),
        reverse=True,
    )

    ann_dates = sorted(_format_ann_date(_read_signal_value(item, "ann_date")) for item in ranked)
    ann_date_range = f"{ann_dates[0]} ~ {ann_dates[-1]}" if ann_dates else "N/A"

    subject = f"[社保持仓周报] 本周新增 {len(ranked)} 只，按综合分排序"
    lines = [
        f"待发送信号数: {len(ranked)}",
        f"公告日期范围: {ann_date_range}",
        "排序规则: 按单条信号综合分降序",
        "",
    ]

    for idx, item in enumerate(ranked, start=1):
        stock_id = _read_signal_value(item, "stock_id")
        ann_date = _format_ann_date(_read_signal_value(item, "ann_date"))
        event_types = _read_signal_value(item, "event_types")
        score = _read_signal_value(item, "score")
        count_change = _read_signal_value(item, "ssf_holder_count_change")
        ratio_change = _read_signal_value(item, "ssf_total_hold_ratio_change")
        lines.append(
            f"{idx}. {stock_id} | ann_date={ann_date} | score={score} | "
            f"events={','.join(event_types)} | count_change={count_change} | "
            f"ratio_change={ratio_change}"
        )

    return subject, "\n".join(lines)
```

- [ ] **Step 4: Run the formatter tests to verify they pass**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_alert.py -v
```

Expected: PASS with 2 passed.

- [ ] **Step 5: Commit the formatter change**

Run:

```bash
git add test/shareholder_monitor/test_ssf_alert.py shareholder_monitor/ssf_alert.py
git commit -m "feat: unify SSF weekly alert email"
```

### Task 2: Update the runner to send one email and mark all pending IDs at once

**Files:**
- Modify: `test/shareholder_monitor/test_runner.py`
- Modify: `shareholder_monitor/runner.py`

- [ ] **Step 1: Write the failing runner tests**

In `test/shareholder_monitor/test_runner.py`, replace the multi-email test with:

```python
def test_run_ssf_change_alert_sends_one_weekly_report_for_all_pending_signals():
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

    mock_email.assert_called_once()
    subject, body = mock_email.call_args.args
    assert subject == "[社保持仓周报] 本周新增 3 只，按综合分排序"
    assert body.index("000002 | ann_date=2024-06-30 | score=92.0") < body.index(
        "000001 | ann_date=2024-03-31 | score=88.0"
    )
    assert body.index("000001 | ann_date=2024-03-31 | score=88.0") < body.index(
        "000003 | ann_date=2024-03-31 | score=61.0"
    )
    mock_storage.mark_ssf_change_signals_alerted.assert_called_once_with([11, 12, 13])
    assert summary.emailed == 3
```

Keep the existing failure-path tests, but update any setup that assumes `build_ssf_change_alert_email(signals, ann_date)` to the new one-argument signature if needed.

- [ ] **Step 2: Run the runner tests to verify they fail**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_runner.py -v
```

Expected: FAIL because `run_ssf_change_alert()` still groups by `ann_date`, calls `send_email()` more than once for mixed dates, and marks IDs per subgroup.

- [ ] **Step 3: Implement the minimal runner change**

Update the tail of `shareholder_monitor/runner.py` from the `pending = storage.list_pending_ssf_change_signals()` block onward to:

```python
    pending = storage.list_pending_ssf_change_signals()
    if not pending:
        return summary

    subject, body = build_ssf_change_alert_email(pending)
    send_email(subject, body)
    # We only mark rows after send_email succeeds so delivery failures stay pending
    # for retry. The tradeoff is that a later DB failure can cause one resend on retry,
    # which is safer than silently losing the alert summary.
    storage.mark_ssf_change_signals_alerted([item.id for item in pending])

    summary.emailed = len(pending)
    return summary
```

Also remove the now-unused `defaultdict` import at the top of the file.

- [ ] **Step 4: Run the runner tests to verify they pass**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_runner.py -v
```

Expected: PASS with all runner tests green.

- [ ] **Step 5: Commit the runner change**

Run:

```bash
git add test/shareholder_monitor/test_runner.py shareholder_monitor/runner.py
git commit -m "feat: send one SSF weekly report per run"
```

### Task 3: Run focused regression verification

**Files:**
- Modify: `test/shareholder_monitor/test_ssf_alert.py`
- Modify: `test/shareholder_monitor/test_runner.py`
- Modify: `shareholder_monitor/ssf_alert.py`
- Modify: `shareholder_monitor/runner.py`

- [ ] **Step 1: Run the focused regression commands**

Run:

```bash
poetry run pytest test/shareholder_monitor/test_ssf_alert.py test/shareholder_monitor/test_runner.py -v
```

Expected: PASS with all alert and runner tests passing.

- [ ] **Step 2: Run repository checks for the touched files**

Run:

```bash
poetry run pre-commit run --files shareholder_monitor/ssf_alert.py shareholder_monitor/runner.py test/shareholder_monitor/test_ssf_alert.py test/shareholder_monitor/test_runner.py
```

Expected: PASS with no formatter or lint errors on the touched files.

- [ ] **Step 3: Commit the final verified state**

Run:

```bash
git add shareholder_monitor/ssf_alert.py shareholder_monitor/runner.py test/shareholder_monitor/test_ssf_alert.py test/shareholder_monitor/test_runner.py
git commit -m "feat: unify SSF weekly report delivery"
```
