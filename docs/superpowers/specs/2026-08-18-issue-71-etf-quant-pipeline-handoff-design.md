# Issue 71 ETF Quant Pipeline Handoff Design

## Purpose

Harden the first-stage ETF quant data pipeline for handoff. Future users and agents should understand what the pipeline downloads, which tables it writes, how the derived net-flow metrics are calculated, which unit conversions are risky, what is deliberately out of scope, and which focused commands prove the touched implementation is safe.

## Scope

This issue is documentation and verification hardening for the pipeline implemented by issues #66 through #70. It should not add new provider calls, new business tables, new calculations, DAG schedule changes, dashboard work, holder-disclosure parsing, financing aggregation, or gross申购/赎回 split support.

## Existing Context

- `docs/superpowers/specs/2026-08-17-etf-quant-data-download-design.md` describes the intended first-stage architecture.
- `docs/superpowers/specs/2026-08-18-issue-69-derived-etf-net-flow-design.md` describes the derived net-flow calculation and unit assumptions.
- `docs/todo/wangwang-etf-quant-data.md` contains the broader Wangwang ETF research roadmap and notes later-stage out-of-scope items.
- `download/download_manager.py` exposes `download_etf_quant_data()`, which coordinates raw ETF share/size download, raw core-index turnover download, and derived net-flow rebuild.
- `tools/db_common.sh` already lists business tables used by export, import, and clean scripts; tests should prove the ETF quant tables stay covered.

## Recommended Approach

Add a focused handoff document under `docs/` rather than spreading operational notes across issue specs. Keep the document concise, source-linked to code entry points, and explicit about raw layer boundaries, derived calculation dependencies, unit conversion risks, diagnostics, and verification commands.

Strengthen tests only where they prove issue #71 acceptance criteria: DB script coverage for the three ETF quant tables and focused commands that run cleanly. Avoid changing production pipeline behavior unless tests reveal an existing issue in the handoff surface.

## Documentation Content

The handoff document should cover these sections:

1. Pipeline purpose and entry point.
2. Raw ETF share/size layer: source, manager/downloader/storage path, table, primary key, preserved raw units, and why it remains separate from ETF行情.
3. Raw index turnover layer: source, table, primary key, raw turnover unit, and mapping relationship to ETF groups.
4. Derived ETF net-flow layer: raw inputs, lookback requirement, calculations, idempotent persistence, diagnostics, and no fallback-zero behavior.
5. Unit conversion risks: ETF share-size units, ETF行情 amount/volume units, index turnover units, and same-currency ratio requirement.
6. Out of scope: gross申购/赎回 split, holder disclosure, financing/margin aggregation, dashboards, DAG schedule changes, and live-provider tests.
7. Focused verification commands: ETF net-flow tests, manager orchestration tests, DB script/common tests, and optional PostgreSQL runner guidance.

## Verification Design

The evidence path is documentation review plus focused offline tests:

- DB common tests prove `etf_share_size`, `index_daily_turnover`, and `etf_net_flow` are in `BUSINESS_TABLES`, so export/import/clean scripts include them in all-business workflows.
- DB script tests prove the full export and full clean import command paths include the three ETF quant tables.
- Existing ETF net-flow and manager tests prove the calculations and orchestration still pass after documentation hardening.
- Ruff checks prove touched docs-adjacent tests remain formatted and lint-clean.

## Definition of Done

- Repository documentation describes raw ETF share/size, raw index turnover, and derived ETF net-flow layers.
- Documentation explicitly calls out unit conversion risks and that gross申购/赎回 split is out of scope.
- Focused verification commands are documented in the repository and pass locally.
- Tests prove the three ETF quant business tables participate in export/import/clean coverage.
- No focused tests fail in touched areas.
