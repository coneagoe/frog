# Issue 71 ETF Quant Pipeline Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document and verify the first-stage ETF quant data pipeline handoff surface.

**Architecture:** Add one focused handoff document for the raw ETF share/size layer, raw index turnover layer, and derived ETF net-flow layer. Strengthen existing DB script tests so the three ETF quant business tables are explicitly covered by export/import/clean workflows, without changing production pipeline behavior.

**Tech Stack:** Markdown, Bash DB scripts, pytest, uv, Ruff.

## Global Constraints

- Use `uv run` for Python commands; do not use bare `python` or `python3` for project tasks.
- Do not change DAG schedules, dependencies, retries, task boundaries, or SLA.
- Mock external providers; do not call live Tushare in tests.
- Do not add new provider calls, new tables, new derived metrics, holder parsing, financing aggregation, dashboards, or gross申购/赎回 split support.
- Preserve existing production behavior unless a focused test exposes a real issue in documentation or DB script coverage.
- Do not commit unless explicitly asked by the user.

---

## Verification Plan

The main claim is that issue #71 makes the ETF quant pipeline understandable and safely handoff-ready without changing behavior. Evidence comes from a dedicated Markdown handoff doc, DB common tests proving all ETF quant tables are in `BUSINESS_TABLES`, DB script tests proving full export and clean import include those tables, and existing focused ETF net-flow/manager tests proving the touched areas still pass.

---

## File Structure

- Create `docs/etf_quant_pipeline.md`: handoff documentation for pipeline layers, calculations, unit risks, out-of-scope items, and commands.
- Modify `test/tools/test_db_common.py`: explicit table coverage assertions for the ETF quant table set.
- Modify `test/tools/test_db_scripts.py`: explicit command-path assertions that full export and clean import include all ETF quant tables.

---

### Task 1: Pipeline Handoff Documentation

**Files:**
- Create: `docs/etf_quant_pipeline.md`

**Interfaces:**
- Consumes existing code/docs: `download/download_manager.py`, `download/etf_net_flow.py`, `tools/db_common.sh`, `docs/todo/wangwang-etf-quant-data.md`, and issue #69/#70 specs.
- Produces a user-facing handoff document with focused verification commands.

- [x] **Step 1: Create the handoff doc**

Create `docs/etf_quant_pipeline.md` with these exact sections: `Purpose`, `Run Surface`, `Layer 1: Raw ETF Share/Size`, `Layer 2: Raw Index Turnover`, `Layer 3: Derived ETF Net Flow`, `Unit Conversion Risks`, `Out of Scope`, and `Focused Verification`.

- [x] **Step 2: Include command references**

Document these commands exactly:

```bash
uv run pytest test/download/test_etf_net_flow.py test/download/test_download_manager.py -k 'etf_net_flow or download_etf_quant_data or rebuild_etf_net_flow' -v
uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -k 'etf_quant or business_tables_include_etf_quant_pipeline_tables or clean_full_import or clean_full_matching_export' -v
uv run ruff check test/tools/test_db_common.py test/tools/test_db_scripts.py
```

- [x] **Step 3: Self-check the doc**

Verify the doc explicitly mentions `etf_share_size`, `index_daily_turnover`, `etf_net_flow`, unit conversion risks, and gross申购/赎回 split out of scope.

---

### Task 2: DB Script Coverage Tests

**Files:**
- Modify: `test/tools/test_db_common.py`
- Modify: `test/tools/test_db_scripts.py`

**Interfaces:**
- Consumes `tools/db_common.sh` `BUSINESS_TABLES` and the fake Docker command log in `test/tools/test_db_scripts.py`.
- Produces explicit assertions that `etf_share_size`, `index_daily_turnover`, and `etf_net_flow` are covered by DB common and full export/import/clean command paths.

- [x] **Step 1: Strengthen DB common table-set test**

In `test/tools/test_db_common.py`, add a constant:

```python
ETF_QUANT_PIPELINE_TABLES = {"etf_share_size", "index_daily_turnover", "etf_net_flow"}
```

Add this test:

```python
def test_business_tables_include_etf_quant_pipeline_tables():
    assert ETF_QUANT_PIPELINE_TABLES <= _parse_business_tables()
```

- [x] **Step 2: Strengthen DB script command tests**

In `test/tools/test_db_scripts.py`, add the same table-set constant near the existing enum constants. Add assertions to `test_clean_full_matching_export_retains_business_table_selection()` that each ETF quant table appears as `--table=public.<table>`.

Add a focused clean-import test:

```python
def test_clean_full_import_drops_etf_quant_pipeline_tables(tmp_path: Path):
    input_file = tmp_path / "etf-quant.sql"
    input_file.write_text("SELECT 1;\n", encoding="utf-8")

    _run_script("db_import.sh", ["--clean", "--in", str(input_file)], tmp_path)

    drop_sql = (tmp_path / "commands.log").read_text(encoding="utf-8").split(" -c ", 1)[1]
    for table_name in ETF_QUANT_PIPELINE_TABLES:
        assert f'DROP TABLE IF EXISTS "public"."{table_name}"' in drop_sql
```

- [x] **Step 3: Run focused tests**

Run:

```bash
uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -k 'etf_quant or business_tables_include_etf_quant_pipeline_tables or clean_full_import or clean_full_matching_export' -v
```

Expected: PASS.

---

### Task 3: Focused Final Verification

**Files:**
- No new files unless a preceding test exposes a defect.

**Interfaces:**
- Consumes documentation and test edits from Tasks 1-2.
- Produces final verification evidence for issue #71.

- [x] **Step 1: Run ETF pipeline focused tests**

Run:

```bash
uv run pytest test/download/test_etf_net_flow.py test/download/test_download_manager.py -k 'etf_net_flow or download_etf_quant_data or rebuild_etf_net_flow' -v
```

Expected: PASS.

- [x] **Step 2: Run DB coverage focused tests**

Run:

```bash
uv run pytest test/tools/test_db_common.py test/tools/test_db_scripts.py -k 'etf_quant or business_tables_include_etf_quant_pipeline_tables or clean_full_import or clean_full_matching_export' -v
```

Expected: PASS.

- [x] **Step 3: Run lint on touched tests**

Run:

```bash
uv run ruff check test/tools/test_db_common.py test/tools/test_db_scripts.py
```

Expected: PASS.

- [x] **Step 4: Simplify review**

Inspect the touched tests and doc for duplication or ambiguity. Apply only targeted simplifications that preserve the issue scope and verified behavior.
