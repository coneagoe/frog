---
name: paper-trading
description: Use when managing this repository's self-developed paper trading backend, paper_trading API, paper accounts, simulated orders, matching runs, snapshots, cash ledger, positions, trades, validity checks, the paper_trading_cli.py CLI wrapper, the paper-trading CLI tool, or troubleshooting PAPER_TRADING_API_TOKEN and PAPER_TRADING_API_BASE_URL usage.
triggers:
  - paper trading
  - paper_trading
  - paper_trading_cli
  - paper-trading CLI
  - PAPER_TRADING_API_BASE_URL
  - 模拟交易
  - 纸面交易
  - paper account
  - simulated order
  - matching run
  - validity check
---

# Paper Trading

## Overview

Use the repo-local CLI first for paper trading account and order operations. The CLI wraps the FastAPI backend and avoids hand-written curl unless debugging raw HTTP behavior.

## Quick Start

Set auth and base URL, then run commands through `uv run`:

```bash
export PAPER_TRADING_API_TOKEN="change-me"
export PAPER_TRADING_API_BASE_URL="http://localhost:8000"
uv run tools/paper_trading_cli.py account list
```

If the backend is not running, start it with Docker:

```bash
docker compose up -d paper-trading
```

Manual backend startup is documented in `docs/paper_trading.md`.

## Command Map

| Need | Command |
| --- | --- |
| Create account | `uv run tools/paper_trading_cli.py account create --name demo --initial-cash 100000` |
| List accounts | `uv run tools/paper_trading_cli.py account list` |
| Get account | `uv run tools/paper_trading_cli.py account get --account-id 1` |
| Delete account | `uv run tools/paper_trading_cli.py account delete --account-id 1` |
| List positions | `uv run tools/paper_trading_cli.py account positions --account-id 1` |
| List cash ledger | `uv run tools/paper_trading_cli.py account cash-ledger --account-id 1` |
| Create order | `uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001.SZ --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-06-16` |
| List orders | `uv run tools/paper_trading_cli.py order list --account-id 1` |
| Get order | `uv run tools/paper_trading_cli.py order get --order-id 1` |
| Cancel order | `uv run tools/paper_trading_cli.py order cancel --order-id 1` |
| Order validity checks | `uv run tools/paper_trading_cli.py order validity-checks --account-id 1 --order-id 1` |
| List trades | `uv run tools/paper_trading_cli.py trade list --account-id 1` |
| Run matching | `uv run tools/paper_trading_cli.py matching run --trade-date 2026-06-16 --account-id 1` |
| List matching runs | `uv run tools/paper_trading_cli.py matching list` |
| Get matching run | `uv run tools/paper_trading_cli.py matching get --run-id 1` |
| List snapshots | `uv run tools/paper_trading_cli.py snapshot list --account-id 1` |

Add `--json` before the command group when machine-readable output is needed:

```bash
uv run tools/paper_trading_cli.py --json order list --account-id 1
```

Override config per invocation with `--base-url` and `--token`.

## Use Raw API Only When Needed

Use `docs/paper_trading.md` for curl examples when investigating HTTP auth, backend routing, or response-shape problems. For normal account, order, matching, trade, and snapshot management, use `tools/paper_trading_cli.py`.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| Running bare `python tools/paper_trading_cli.py` | Use `uv run tools/paper_trading_cli.py ...` in this repo. |
| Missing token errors | Set `PAPER_TRADING_API_TOKEN` or pass `--token`. |
| Connection refused | Start `paper-trading` or pass the correct `--base-url`. |
| Browser/frontend token confusion | Browser calls frontend `/api/paper/*`; CLI calls backend `/paper/*` with bearer auth. |
| Expecting matching on order creation | Run `matching run` for the relevant `trade_date` and account, then inspect trades/snapshots. |

## Implementation Pointers

- CLI wrapper: `tools/paper_trading_cli.py`
- Backend docs: `docs/paper_trading.md`
- FastAPI routers: `paper_trading/api/routers/`
- Paper trading tests: `test/paper_trading/`
- CLI tests: `test/tools/test_paper_trading_cli.py`
