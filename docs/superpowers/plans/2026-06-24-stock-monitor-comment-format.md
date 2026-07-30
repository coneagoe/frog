# Stock Monitor Comment Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify stock monitor human-readable titles so alert text and `target list/get` CLI output render `股票代码 股票名称 comment` when `comment` exists, otherwise `股票代码 股票名称 监控条件`.

**Architecture:** Add one shared formatter in the monitor domain that trims `note`, falls back to the existing human-readable condition text, and returns a single title string. Update `tools/stock_monitor_cli.py` human-readable output and `monitor/monitor_runner.py` alert subject rendering to call that formatter, while keeping storage schemas and `--json` output unchanged.

**Tech Stack:** Python 3.11+, pytest, unittest.mock, stock monitor CLI, monitor runner.

## Global Constraints

- Use `uv run` for Python commands in this repo. Do not use bare `python` or `python3` for project tasks.
- Keep JSON output stable: `tools/stock_monitor_cli.py --json` must preserve current structure and field values.
- Do not change database schema, CLI arguments, target persistence payloads, or blackroom output behavior.
- Treat `None`, empty string, and whitespace-only `note` as “comment not specified”.
- Reuse the existing condition text source instead of inventing a new condition wording format.
- Keep changes minimal and focused; do not change DAG/task scheduling or unrelated business logic.

---

## File Structure

- Create `test/monitor/test_monitor_target_label.py`: focused formatter tests for note priority and condition fallback.
- Modify `monitor/monitor_target_service.py`: expose a small shared helper that converts serialized target fields into the human-readable title and, if needed, a condition summary helper used by both CLI and runner.
- Modify `tools/stock_monitor_cli.py`: render `target list/get` human-readable output via the shared helper while leaving `--json` untouched.
- Modify `test/tools/test_stock_monitor_cli.py`: add text-output regression tests for `target list/get` and preserve JSON behavior assertions.
- Modify `monitor/monitor_runner.py`: build alert subjects from the shared helper instead of `target.note or ctype`.
- Modify `test/monitor/test_monitor_runner.py`: add alert subject assertions for note priority and whitespace fallback.
- Modify `docs/stock_monitor.md`: update only the human-readable output convention/example if the implementation changes what the doc promises.

### Task 1: Add Shared Title Formatter With TDD

**Files:**
- Create: `test/monitor/test_monitor_target_label.py`
- Modify: `monitor/monitor_target_service.py`

**Interfaces:**
- Consumes: serialized target-shaped fields `stock_code: str | None`, `condition: dict[str, Any] | None`, `note: str | None`
- Produces: `format_monitor_target_label(stock_code: str | None, stock_name: str | None, condition: dict[str, Any] | None, note: str | None) -> str`

- [ ] **Step 1: Write the failing formatter tests**

Create `test/monitor/test_monitor_target_label.py`:

```python
from monitor.monitor_target_service import format_monitor_target_label


def test_format_monitor_target_label_prefers_note_text():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note="抄底提醒",
    )

    assert label == "600519 贵州茅台 抄底提醒"


def test_format_monitor_target_label_falls_back_to_condition_when_note_missing():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note=None,
    )

    assert label == "600519 贵州茅台 price_threshold below 1500"


def test_format_monitor_target_label_treats_blank_note_as_missing():
    label = format_monitor_target_label(
        stock_code="600519",
        stock_name="贵州茅台",
        condition={"type": "price_threshold", "direction": "below", "value": 1500},
        note="   ",
    )

    assert label == "600519 贵州茅台 price_threshold below 1500"
```

- [ ] **Step 2: Run the formatter tests to verify they fail**

Run:

```bash
uv run pytest test/monitor/test_monitor_target_label.py -q
```

Expected: FAIL because `format_monitor_target_label` does not exist yet.

- [ ] **Step 3: Write the minimal shared formatter**

Edit `monitor/monitor_target_service.py` and add these helpers near the module top, above `MonitorTargetService`:

```python
def _format_condition_summary(condition: dict[str, Any] | None) -> str:
    if not isinstance(condition, dict):
        return "unknown"

    ctype = condition.get("type", "unknown")
    direction = condition.get("direction")

    if ctype == "price_threshold":
        return f"{ctype} {direction} {condition.get('value')}"
    if ctype == "change_pct":
        return f"{ctype} {direction} {condition.get('value')}"
    if ctype == "price_cross_ma":
        return f"{ctype} {direction} {condition.get('period')}"
    if ctype == "ma_cross":
        return f"{ctype} {direction} {condition.get('fast')}/{condition.get('slow')}"
    if ctype == "rsi":
        return f"{ctype} {direction} {condition.get('value')}"
    return str(ctype)


def format_monitor_target_label(
    stock_code: str | None,
    stock_name: str | None,
    condition: dict[str, Any] | None,
    note: str | None,
) -> str:
    code = (stock_code or "").strip()
    name = (stock_name or "").strip()
    normalized_note = note.strip() if isinstance(note, str) else ""
    suffix = normalized_note or _format_condition_summary(condition)

    return " ".join(part for part in [code, name, suffix] if part)
```

Also extend `_serialize_target()` to include `stock_name` if storage already provides it:

```python
"stock_name": getattr(target, "stock_name", None),
```

- [ ] **Step 4: Run the formatter tests to verify they pass**

Run:

```bash
uv run pytest test/monitor/test_monitor_target_label.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add monitor/monitor_target_service.py test/monitor/test_monitor_target_label.py
git commit -m "feat: add stock monitor target label formatter"
```

### Task 2: Switch CLI Text Output To The Shared Formatter

**Files:**
- Modify: `tools/stock_monitor_cli.py`
- Modify: `test/tools/test_stock_monitor_cli.py`

**Interfaces:**
- Consumes: `format_monitor_target_label(...) -> str` from Task 1 and service results shaped like `{"success": bool, "code": str, "message": str, "data": dict | list | None}`
- Produces: `_emit_target_text(result: dict[str, Any], target_command: str | None) -> bool` returning whether custom target text output was emitted

- [ ] **Step 1: Write the failing CLI output tests**

Add these tests to `test/tools/test_stock_monitor_cli.py` near the existing target command tests:

```python
def test_target_list_text_output_uses_note_label(capsys):
    service = MagicMock()
    service.list.return_value = {
        "success": True,
        "code": "OK",
        "message": "targets listed",
        "data": [
            {
                "id": 1,
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "condition": {"type": "price_threshold", "direction": "below", "value": 1500},
                "note": "抄底提醒",
            }
        ],
    }

    exit_code = main(["target", "list"], service=service)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "600519 贵州茅台 抄底提醒" in out


def test_target_get_text_output_falls_back_to_condition_when_note_blank(capsys):
    service = MagicMock()
    service.get.return_value = {
        "success": True,
        "code": "OK",
        "message": "target fetched",
        "data": {
            "id": 1,
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "condition": {"type": "price_threshold", "direction": "below", "value": 1500},
            "note": "   ",
        },
    }

    exit_code = main(["target", "get", "--target-id", "1"], service=service)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "600519 贵州茅台 price_threshold below 1500" in out


def test_target_list_json_output_is_unchanged(capsys):
    service = MagicMock()
    service.list.return_value = {
        "success": True,
        "code": "OK",
        "message": "targets listed",
        "data": [
            {
                "id": 1,
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "condition": {"type": "price_threshold", "direction": "below", "value": 1500},
                "note": "抄底提醒",
            }
        ],
    }

    exit_code = main(["--json", "target", "list"], service=service)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == service.list.return_value
```

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run:

```bash
uv run pytest test/tools/test_stock_monitor_cli.py -q
```

Expected: FAIL because the current CLI prints only `CODE: message` and raw JSON data, not the requested title format.

- [ ] **Step 3: Write the minimal CLI text formatter integration**

Edit `tools/stock_monitor_cli.py`:

1. Import the shared formatter:

```python
from monitor.monitor_target_service import (
    MonitorTargetService,
    TargetNotFoundError,
    TargetValidationError,
    format_monitor_target_label,
)
```

2. Add target-specific text rendering helpers above `_emit`:

```python
def _render_target_line(item: dict[str, Any]) -> str:
    return format_monitor_target_label(
        stock_code=item.get("stock_code"),
        stock_name=item.get("stock_name"),
        condition=item.get("condition"),
        note=item.get("note"),
    )


def _emit_target_text(result: dict[str, Any], target_command: str | None) -> bool:
    if not result.get("success"):
        return False

    data = result.get("data")
    if target_command == "get" and isinstance(data, dict):
        print(_render_target_line(data))
        return True
    if target_command == "list" and isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                print(_render_target_line(item))
        return True
    return False
```

3. Change `_emit` to accept target command context and use custom text output only for non-JSON `target list/get`:

```python
def _emit(result: dict[str, Any], json_output: bool, target_command: str | None = None) -> None:
    if json_output:
        print(json.dumps(result, ensure_ascii=False))
        return

    if target_command in {"list", "get"} and _emit_target_text(result, target_command):
        return

    print(f"{result.get('code', 'UNKNOWN')}: {result.get('message', '')}")
    if result.get("data") is not None:
        print(json.dumps(result["data"], ensure_ascii=False))
```

4. Update the final emit call in `main()`:

```python
target_command = args.target_command if args.command == "target" else None
_emit(result, json_output=args.json_output, target_command=target_command)
```

- [ ] **Step 4: Run the CLI tests to verify they pass**

Run:

```bash
uv run pytest test/tools/test_stock_monitor_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/stock_monitor_cli.py test/tools/test_stock_monitor_cli.py
git commit -m "feat: format stock monitor cli target labels"
```

### Task 3: Switch Alert Subjects And Update Docs

**Files:**
- Modify: `monitor/monitor_runner.py`
- Modify: `test/monitor/test_monitor_runner.py`
- Modify: `docs/stock_monitor.md`

**Interfaces:**
- Consumes: `format_monitor_target_label(...) -> str` from Task 1
- Produces: alert subjects prefixed with `[股票监控告警] ` and followed by the shared label text

- [ ] **Step 1: Write the failing runner tests**

Add these tests to `test/monitor/test_monitor_runner.py`:

```python
def test_run_monitor_alert_subject_prefers_note_text():
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
    assert subject == "[股票监控告警] 600519 贵州茅台 price_threshold below 1500.0"
```

- [ ] **Step 2: Run the runner tests to verify they fail**

Run:

```bash
uv run pytest test/monitor/test_monitor_runner.py -q
```

Expected: FAIL because the current subject uses `target.note or ctype` and does not include stock name or condition fallback text.

- [ ] **Step 3: Write the minimal runner integration and doc update**

Edit `monitor/monitor_runner.py`:

1. Import the formatter:

```python
from monitor.monitor_target_service import format_monitor_target_label
```

2. Replace the subject assignment in `_send_alert()` with:

```python
subject = f"[股票监控告警] {format_monitor_target_label(target.stock_code, getattr(target, 'stock_name', None), target.condition, target.note)}"
```

Leave the email body lines unchanged unless a test proves they must change.

Then update `docs/stock_monitor.md` output convention section with one concrete note such as:

```md
- `target list/get` 默认文本输出使用统一标题：有备注时显示 `股票代码 股票名称 备注`，未指定备注时显示 `股票代码 股票名称 监控条件`。
```

- [ ] **Step 4: Run the runner tests and focused CLI tests to verify they pass**

Run:

```bash
uv run pytest test/monitor/test_monitor_runner.py test/tools/test_stock_monitor_cli.py test/monitor/test_monitor_target_label.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add monitor/monitor_runner.py test/monitor/test_monitor_runner.py docs/stock_monitor.md
git commit -m "feat: unify stock monitor alert titles"
```

### Task 4: Final Verification

**Files:**
- Modify: none expected
- Verify: `monitor/monitor_target_service.py`, `tools/stock_monitor_cli.py`, `monitor/monitor_runner.py`, related tests and docs

**Interfaces:**
- Consumes: all changes from Tasks 1-3
- Produces: verified implementation with focused regression evidence

- [ ] **Step 1: Run focused regression suite**

Run:

```bash
uv run pytest test/monitor/test_monitor_target_label.py test/tools/test_stock_monitor_cli.py test/monitor/test_monitor_runner.py -q
```

Expected: PASS.

- [ ] **Step 2: Run targeted lint on changed files**

Run:

```bash
uv run ruff check monitor/monitor_target_service.py monitor/monitor_runner.py tools/stock_monitor_cli.py test/monitor/test_monitor_target_label.py test/monitor/test_monitor_runner.py test/tools/test_stock_monitor_cli.py docs/stock_monitor.md
```

Expected: PASS.

- [ ] **Step 3: Run targeted format check on changed Python files**

Run:

```bash
uv run ruff format --check monitor/monitor_target_service.py monitor/monitor_runner.py tools/stock_monitor_cli.py test/monitor/test_monitor_target_label.py test/monitor/test_monitor_runner.py test/tools/test_stock_monitor_cli.py
```

Expected: PASS.

- [ ] **Step 4: Commit verification-only follow-up if needed**

```bash
git add monitor/monitor_target_service.py monitor/monitor_runner.py tools/stock_monitor_cli.py test/monitor/test_monitor_target_label.py test/monitor/test_monitor_runner.py test/tools/test_stock_monitor_cli.py docs/stock_monitor.md
git commit -m "test: cover stock monitor comment label formatting"
```

Skip this commit if Tasks 1-3 were squashed locally and there are no new changes.
