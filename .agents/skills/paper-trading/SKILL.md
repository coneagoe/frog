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

For A-share order symbols, use the 6-digit stock code only. Do not add exchange suffixes like `.SH` or `.SZ`.

When the user gives an order instruction, submit the order as requested. Do not treat repeated or identical order instructions as duplicates, and do not replace execution with status checks unless the user explicitly asks to query, verify, or avoid duplicate orders. If the user repeats the same buy/sell instruction, each repetition is a new intended order.

## Quick Start

Load the repo-local `.env` first; it contains `PAPER_TRADING_API_TOKEN`. Set the backend URL explicitly if `.env` does not contain `PAPER_TRADING_API_BASE_URL`, then run commands through `uv run`:

```bash
set -a
source .env
set +a
export PAPER_TRADING_API_BASE_URL="${PAPER_TRADING_API_BASE_URL:-http://localhost:8000}"
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
| Create order | `uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-06-16` |
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
| Missing token errors | Load repo `.env` with `set -a; source .env; set +a`, or pass `--token`. |
| Connection refused | Start `paper-trading` or pass the correct `--base-url`. |
| Browser/frontend token confusion | Browser calls frontend `/api/paper/*`; CLI calls backend `/paper/*` with bearer auth. |
| Expecting matching on order creation | Run `matching run` for the relevant `trade_date` and account, then inspect trades/snapshots. |
| Using suffixed A-share symbols like `601668.SH` or `000001.SZ` | Use suffixless 6-digit codes like `601668` or `000001`. |
| Intercepting repeated order instructions as duplicates | Submit each repeated buy/sell instruction as a new order unless the user explicitly asks for status-only verification or duplicate prevention. |

## OpenClaw Conversation Order Entry

When OpenClaw receives a natural-language paper trading order instruction through any conversation channel, treat the channel as outside this repository. Do not mention, design, or require channel-specific webhook servers, interactive card payloads, or paper trading API extensions in this repository.

For natural-language order instructions, use this confirmation-first flow:

1. Parse the user's message into a draft order.
2. Ask for any missing required field instead of guessing.
3. Send a structured confirmation message in the same conversation.
4. Submit the order only after the user gives explicit positive confirmation.
5. Report the CLI result back to the user.

Required fields before confirmation:

- `account_id`: paper trading account ID. Do not guess it.
- `symbol`: 6-digit A-share code such as `000001`. Do not add `.SH` or `.SZ`.
- `side`: `buy` or `sell`.
- `quantity`: integer quantity accepted by the CLI.
- `limit_price`: explicit limit price. Do not convert vague phrases like `市价`, `差不多`, or `按现在价格` into a price.
- `trade_date`: resolved date shown in the confirmation message. If the user says `今天`, show the actual date before submitting.

Confirmation message format:

```text
请确认录入以下模拟交易订单：

账户：1
方向：买入
代码：000001
数量：100
限价：10.00
交易日：2026-07-06

回复“确认”提交订单，回复“取消”放弃。
```

Only clear positive replies such as `确认`, `提交`, or `是，提交` authorize submission. Ambiguous replies are not confirmation; ask the user to reply with `确认` or `取消`.

If the user changes the draft before confirmation, regenerate the complete confirmation message. If the user cancels, do not run the CLI.

After confirmation, submit with the existing CLI:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-06
```

Do not automatically run matching after order entry. If the user wants matching, ask for or receive a separate matching instruction and use the existing matching command.

## Implementation Pointers

- CLI wrapper: `tools/paper_trading_cli.py`
- Backend docs: `docs/paper_trading.md`
- FastAPI routers: `paper_trading/api/routers/`
- Paper trading tests: `test/paper_trading/`
- CLI tests: `test/tools/test_paper_trading_cli.py`
