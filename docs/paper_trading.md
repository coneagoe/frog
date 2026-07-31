# Paper Trading Backend

The paper trading backend provides a FastAPI API for simulated trading. It supports multiple paper accounts, A-share and Southbound Hong Kong Stock Connect ordinary-stock limit orders, daily matching runs, market-specific fees, position lots, validity checks, pending HK settlement, and account snapshots.

## Docker (Recommended)

The paper trading backend is containerized. Add `PAPER_TRADING_API_TOKEN` to your `.env` file:

```bash
echo 'PAPER_TRADING_API_TOKEN="change-me"' >> .env
```

Then start the service:

```bash
docker compose up -d paper-trading
```

The API listens on `http://localhost:8000`. All other environment variables (DB connection, etc.) are wired via the common Docker Compose config.

## Manual Start

If running outside Docker, set environment variables and start the API directly:

```bash
export PAPER_TRADING_API_TOKEN="change-me"
export db_host=localhost
export db_port=5432
export db_username=quant
export db_password=quant
uv run uvicorn paper_trading.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

All endpoints require a bearer token:

```bash
Authorization: Bearer change-me
```

## Start The Frontend

The Docker Compose stack includes the backend and Next.js frontend:

```bash
docker compose up -d paper-trading paper-trading-frontend
```

Open `http://localhost:3000/accounts`. The frontend container talks to the backend container at `http://paper-trading:8000`.

## Manual Frontend Start

The paper trading frontend lives in `frontend/paper-trading` and proxies browser requests to the FastAPI backend.

```bash
cd frontend/paper-trading
npm install
export PAPER_TRADING_API_BASE_URL="http://localhost:8000"
export PAPER_TRADING_API_TOKEN="change-me"
npm run dev
```

Open `http://localhost:3000/accounts`. The frontend has separate workspaces for accounts, order entry, historical orders, historical trades, and analytics:

- `Accounts`: create/delete accounts, select an account, and review its positions and cash ledger.
- `Trade`: submit paper limit orders.
- `Orders`: review historical orders, cancel cancellable orders, and delete orders.
- `Trades`: review historical executions.
- `Analytics`: review snapshots, total assets, trades, and cash movements.

The bearer token is read only by Next.js route handlers. Browser code calls local `/api/paper/*` endpoints and does not receive `PAPER_TRADING_API_TOKEN`.

## CLI Wrapper

For day-to-day account, order, trade, matching, snapshot, and import management, prefer the repo-local CLI wrapper instead of hand-written `curl`:

```bash
export PAPER_TRADING_API_TOKEN="change-me"
export PAPER_TRADING_API_BASE_URL="http://localhost:8000"

uv run tools/paper_trading_cli.py account list
uv run tools/paper_trading_cli.py account create --name demo --initial-cash 100000
uv run tools/paper_trading_cli.py account create --name custom-fee --initial-cash 100000 --fee-preset a_share --commission-rate 0.00025 --min-commission 5.00 --stamp-duty-rate 0.0005 --transfer-fee-rate 0.00001
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-18 --comment "突破买入"
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 00700 --market hk_connect --side buy --quantity 100 --limit-price 400.00 --trade-date 2026-07-18
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment "回踩确认后买入"
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment ""
uv run tools/paper_trading_cli.py order delete --order-id 123
uv run tools/paper_trading_cli.py matching run --trade-date 2026-06-16 --account-id 1
```

The `order update-comment` command with `--comment ""` clears the stored comment to `NULL` on the order and all linked trades.

Order creation queues an accepted order; it does not run matching or create a trade immediately. If an `idempotency_key` is supplied, repeating the same request for the same account returns the original order without reserving cash again. Reusing that key for different order fields is rejected.

Account fee flags are optional. When omitted, account creation uses the built-in `a_share` preset, which matches the previous hardcoded A-share fees: commission rate `0.0003`, minimum commission `5.00`, stamp duty rate `0.0005`, and transfer fee rate `0.00001`. Explicit fee flags override the preset values for the new account.

Use `--json` when machine-readable output is needed:

```bash
uv run tools/paper_trading_cli.py --json order list --account-id 1
```

### Import Existing Holdings

New paper trading accounts can import pre-existing stock holdings. The import seeds positions and lots without creating trades, orders, or cash ledger entries. Imported lots carry a real `buy_trade_date` so later sells satisfy existing T+1 validation.

Import is only allowed for accounts with no existing positions or lots.

CSV format (columns: `symbol`, `quantity`, `cost_price`, `buy_trade_date`):

```csv
symbol,quantity,cost_price,buy_trade_date
000001,100,10.50,2026-01-15
000002,200,20.00,2026-02-01
```

```bash
uv run tools/paper_trading_cli.py account import-positions --account-id 1 --file holdings.csv
```

```bash
curl -X POST http://localhost:8000/paper/accounts/1/positions/import \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"positions":[{"symbol":"000001","quantity":100,"cost_price":"10.50","buy_trade_date":"2026-01-15"}]}'
```

Validation rules:
- `symbol` is required and whitespace-trimmed.
- `quantity` must be a positive integer.
- `cost_price` must be a non-negative decimal.
- `buy_trade_date` must be a valid calendar date in `YYYY-MM-DD` format.
- Duplicate symbols create separate lots and aggregate into one position per symbol.
- Import is rejected if the account does not exist (404) or already has positions (422).

### Repair Imported Position Markets

Imports may optionally specify `market` as `a_share` or `hk_connect`. The aggregate
position and each imported lot for the same account and symbol must use the same
market value. If historical imported holdings were stored with the wrong market,
run the standalone administrative repair command with an explicit mapping for every
target. Do not use this command as a general market migration: it never discovers or
changes unspecified account/symbol pairs, and it never changes trade-sourced lots.

```bash
uv run tools/repair_paper_position_markets.py \
  --mapping ACCOUNT_ID:00700:hk_connect
```

Replace `ACCOUNT_ID` with the account ID supplied for the deployment; no production
account ID is embedded in this procedure. Repeat `--mapping` for additional explicit
targets. Every requested aggregate position is checked before any update is issued,
and all updates run in one transaction, so a missing target leaves all targets
unchanged. A successful repeat is safe and reports zero changed rows (idempotent).
Use `--json` for machine-readable results:

```bash
uv run tools/repair_paper_position_markets.py --json \
  --mapping ACCOUNT_ID:00700:hk_connect
```

## OpenClaw Conversation Order Entry

OpenClaw can be used for conversation-based paper trading order entry. Conversation channels are outside this repository; this repository does not provide channel-specific webhook services or interactive card payloads.

For natural-language order instructions, OpenClaw should parse the message, ask for missing fields, and send a structured confirmation before submitting the order.

Example conversation:

```text
用户：账户1买入平安银行100股，10元以内

OpenClaw：请确认录入以下模拟交易订单：

账户：1
方向：买入
代码：000001
数量：100
限价：10.00
交易日：2026-07-06

回复“确认”提交订单，回复“取消”放弃。

用户：确认
```

After confirmation, OpenClaw submits the order with the existing CLI:

```bash
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-07-06
```

Order entry does not automatically run matching. Run matching only after a separate user instruction:

```bash
uv run tools/paper_trading_cli.py matching run --trade-date 2026-07-06 --account-id 1
```

Use the raw API examples below when debugging auth, routing, or response-shape issues.

## Create Account

```bash
curl -X POST http://localhost:8000/paper/accounts \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","initial_cash":"100000.00"}'
```

To configure account fees at creation time, pass `fee_preset` and any fee overrides:

```bash
curl -X POST http://localhost:8000/paper/accounts \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"name":"custom-fee","initial_cash":"100000.00","fee_preset":"a_share","commission_rate":"0.00025","min_commission":"5.00","stamp_duty_rate":"0.0005","transfer_fee_rate":"0.00001"}'
```

The only built-in preset is `a_share`. Fee values must be non-negative decimals; zero is valid for fee-free test accounts.

## Update Account Fees

Update fee fields on an existing account. Fee changes apply only to future orders and trades; historical trades and cash ledger entries are not recalculated. The `fee_preset` field is not changed by the update command — only the explicitly provided fee values are modified.

Only the fields you provide are updated; all omitted fields keep their current values. At least one fee field is required.

```bash
uv run tools/paper_trading_cli.py account update-fee --account-id 1 --commission-rate 0.0002 --min-commission 3
```

```bash
curl -X PATCH http://localhost:8000/paper/accounts/1 \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"commission_rate":"0.0002","min_commission":"3.00"}'
```

All fee fields are optional in the request body. Supported A-share fields are `commission_rate`, `min_commission`, `stamp_duty_rate`, and `transfer_fee_rate`. Supported HK Connect fields are `hk_commission_rate`, `hk_min_commission`, `hk_stamp_duty_rate`, `hk_trading_fee_rate`, `hk_sfc_levy_rate`, `hk_afrc_levy_rate`, and `hk_settlement_fee_rate`. Values must be non-negative decimals. An empty request body (no fee fields) is rejected with a 422 error.

## Hong Kong Stock Connect Support

Set `market` to `hk_connect` when creating Southbound Hong Kong Stock Connect ordinary-stock orders. If `market` is omitted, the backend treats the order as `a_share` for backward compatibility.

```bash
curl -X POST http://localhost:8000/paper/accounts/1/orders \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"00700","market":"hk_connect","side":"buy","quantity":100,"limit_price":"400.00","trade_date":"2026-07-18"}'
```

HK Connect support is scoped to ordinary stocks. The backend uses explicit market routing rather than symbol inference: orders, trades, positions, and validity checks persist `market`. HK orders use HK GGT daily bars, HK-specific fees, board-lot and tick-size validation, and no A-share limit-up/down validity analysis. HK sell proceeds are not immediately available cash; they remain pending until the T+2 settlement service releases them. Account snapshots include pending settlement in total assets and expose `pending_settlement`.

## Delete Account

Deleting an account permanently removes the paper account and its associated orders, trades, positions, position lots, snapshots, matching runs, and cash ledger entries.

```bash
curl -X DELETE http://localhost:8000/paper/accounts/1 \
  -H "Authorization: Bearer change-me"
```

## Deposits and Withdrawals

Paper trading accounts support external cash flows through account-scoped deposit and withdrawal operations. Deposits add available cash and mint account shares at the current unit NAV. Withdrawals reduce available cash and redeem account shares at the current unit NAV. Withdrawals cannot exceed available cash and do not automatically sell positions or use frozen cash.

Use these CLI commands:

```bash
uv run tools/paper_trading_cli.py account deposit --account-id 1 --amount 10000 --trade-date 2026-07-20 --note "add cash"
uv run tools/paper_trading_cli.py account withdraw --account-id 1 --amount 5000 --trade-date 2026-07-20 --note "withdraw cash"
```

The matching and snapshot flow treats cash flows as pre-market effective on their `trade_date`. A cash flow changes account scale and share count but does not by itself change unit NAV.

## Create Limit Order

```bash
curl -X POST http://localhost:8000/paper/accounts/1/orders \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"000001","side":"buy","quantity":100,"limit_price":"10.00","trade_date":"2026-06-16","comment":"突破买入"}'
```

Buy orders freeze estimated cash. Sell orders freeze sellable position quantity. Invalid lot size, insufficient cash, insufficient position, and A-share T+1 violation (same-day sell) are stored as rejected orders. A past A-share trade date can be used for a retry only when an unresolved BFQ daily-bar diagnostic exists for the symbol; otherwise the order is rejected as ineligible for a historical retry.

## Update Order Comment

Update the comment on an existing order. The new value is synced to all trades linked to that order.

```bash
curl -X PATCH http://localhost:8000/paper/orders/1/comment \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"comment":"回踩确认后买入"}'
```

Setting `"comment": ""` clears the stored value to `NULL` on the order and all linked trades:

```bash
curl -X PATCH http://localhost:8000/paper/orders/1/comment \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"comment":""}'
```

The order and its linked trades return `"comment": null` in API responses after clearing.

### Delete an order

Deleting an order hard-deletes the order. If the order had already filled, the paper trading backend recalculates the account's trades, cash ledger, positions, position lots, round trips, matching runs, validity checks, and snapshots from the remaining order history. A surviving order without an exact-date daily bar remains accepted; its replay matching run records a warning and daily-bar diagnostic rather than treating missing market data as a fatal replay failure.

```bash
uv run tools/paper_trading_cli.py order delete --order-id 123
```

Raw API:

```bash
curl -X DELETE "$PAPER_TRADING_API_BASE_URL/paper/orders/123" \
  -H "Authorization: Bearer $PAPER_TRADING_API_TOKEN"
```

## Trade Validity Analysis

Paper trading records the original trading intent and analyzes whether the operation was valid for the specified `trade_date`. The order lifecycle status (`accepted`, `rejected`, `filled`, `cancelled`) remains separate from validity status.

Validity statuses:

- `valid`: available data supports the operation.
- `suspicious`: daily data indicates risk or uncertainty, such as a same-day limit touch.
- `invalid`: the operation is not valid for the specified trading day, such as a price outside the daily low/high range.
- `unchecked`: required market data was unavailable, so the original order is preserved without a completed analysis.

The first version uses daily bars for limit-up and limit-down detection. `trade_date` is the operation date, so default analysis and matching are same-day. A-share T+1 remains a sellable-position rule and does not shift matching to the next day. HK Connect validity uses HK metadata, daily low/high, and tick-size alignment only; it does not apply A-share limit-up/down checks.

## Run Matching

```bash
curl -X POST http://localhost:8000/paper/matching/runs \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"trade_date":"2026-06-16","account_id":1}'
```

Matching processes accepted orders for the trade date. Tradable orders fill at limit price, untouched orders remain accepted, and suspended symbols are rejected. A missing exact-date A-share bar leaves the order accepted, records a daily-bar diagnostic, and allows a later same-date matching retry without duplicating an existing fill. Such missing-bar results complete with `status="completed_with_warnings"`; unexpected market-data, fill, settlement, trade, cash, position, or persistence errors mark the matching run as failed with contextual `error_details`.

Snapshots require a daily bar for every held position. When one is unavailable, matching preserves fills, records a valuation gap, and completes with `status="completed_with_warnings"` and a non-zero `warning_count` instead of discarding the run. The account snapshot is created on a later retry once the missing data is available, and the valuation gap is marked resolved. Other matching or persistence errors remain failures and are reported in `error_details`.

### 日期语义

- API/CLI 下单必须显式提供 `trade_date`，不使用默认日期；匹配同样必须显式提供 `trade_date`，并以它进行订单选择、行情柱、成交、结算和快照处理。
- A 股日线历史 DAG 将 Airflow `context['data_interval_end']` 转换为 `Asia/Shanghai` 后得到业务日期，并将该日期传给 BFQ/HFQ 下载及 EOD 模拟交易匹配；周末及非交易日会跳过。订单先入队，匹配单独执行。
- 只有 `OrderService` 的历史重试资格校验会将订单提交日期与 `date.today()` 比较；这只影响订单是否被接受，不会推导订单日期。

日线历史 DAG 对缺失或失败的 BFQ/HFQ 下载记录 provider 结果；汇总警告仍允许模拟交易匹配继续执行，只有致命的汇总失败会阻止匹配。

## Query Account State

```bash
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/positions
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/trades
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/snapshots
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/cash-ledger
```

Trade responses include the `comment` field:

Position, order, and trade list responses also include the nullable `stock_name`
field. It is a display-only name resolved from the security metadata tables; it
is `null` when metadata is unavailable and is not persisted in paper-trading
records.

Position responses additionally include request-time valuation fields for the
Accounts Positions card:

- `mark_price`: the price used to value the open position, or `null` when no
  usable price is available.
- `price_source`: `real_time` when a valid real-time quote is available, or
  `db_close` when valuation falls back to the latest stored BFQ daily close.
- `unrealized_pnl`: `total_quantity * mark_price - cost_amount`, or `null`
  when neither price source is available.

The positions endpoint batches real-time quote retrieval for the account. A
missing or invalid quote falls back per position to the latest stored BFQ close
using its A-share or HK Connect market route. This request-time valuation does
not change persisted realized PnL or snapshot/NAV calculations.

```json
[
  {
    "id": 1,
    "order_id": 1,
    "account_id": 1,
    "symbol": "000001",
    "side": "buy",
    "quantity": 100,
    "price": "10.00",
    "amount": "1000.00",
    "fees": "5.00",
    "trade_date": "2026-07-18",
    "comment": "突破买入"
  }
]
```

Snapshots are generated after matching and use close prices for valuation.

### Analytics

`GET /paper/accounts/{account_id}/analytics` returns account-level analytics for the paper trading dashboard.

The response includes:

- Activity: daily, weekly, and monthly order/trade frequency.
- Execution: fill rate, rejection rate, and reject reason distribution.
- Trade quality: full-position round-trip win rate, payoff ratio, profit factor, average win/loss, consecutive wins/losses, and holding days.
- Risk: total return, max drawdown, current drawdown, and optional Sharpe, Sortino, and Calmar metrics.

`total_return` now represents NAV return: latest unit NAV versus the first valid unit NAV. `simple_asset_return` is the old scale-sensitive reference metric based on total assets versus initial cash. Drawdown and risk-adjusted metrics use the NAV series so deposits and withdrawals do not appear as trading gains or losses.

Round-trip metrics use full-position cycles. A cycle opens when an account's symbol quantity moves from zero to positive and closes when that symbol returns to zero. Partial exits update the open cycle but do not count as closed round trips.

## Matching Run Status Enum Migration

The `paper_matching_runs.status` column uses the PostgreSQL enum
`paper_matching_run_status` with these labels, in this order:
`running`, `completed`, `completed_with_warnings`, and `failed`. The migration
command is explicit and must be run as an operator-controlled maintenance
procedure. It does not run automatically at API startup.

### Rollout sequence

Use one maintenance window and record the database name, schema, backup path,
and migration output. Run commands from the repository root.

1. Isolate all matching writes. Stop or drain the paper-trading API instances
   that accept order/matching writes, stop the Celery workers that execute
   matching tasks, and pause the Airflow DAGs or schedules that can submit
   matching work. Keep read-only consumers available only if they tolerate a
   maintenance window. Confirm there are no in-flight matching transactions
   before continuing.
2. Create and verify a database backup before changing the schema. The normal
   business-table backup is:

   ```bash
   bash tools/db_export.sh --schema public --out ./backups/paper_matching_pre_enum.sql.gz
   ```

   Verify that the file exists and is readable, and retain the exact command
   output with the maintenance record. For a non-Docker database, use the
   equivalent `pg_dump --format=plain --no-owner --no-privileges` command.
3. Run the migration preflight without changing the database:

   ```bash
   uv run tools/migrate_paper_matching_run_status_enum.py --dry-run --json
   ```

   Require exit code zero, `labels` equal to
   `['running', 'completed', 'completed_with_warnings', 'failed']`, and
   `index_verified` equal to `true`. A non-empty unknown-status error must be
   resolved before the actual migration. Do not bypass it by deleting or
   relabeling rows without an approved data decision.
4. Resolve invalid statuses while writes remain isolated. Inspect the affected
   rows, decide the correct lifecycle state from the matching and order audit
   trail, update only approved rows in a transaction, and rerun the dry-run
   until it succeeds. Do not invent a new enum label during this migration.
5. Run the actual migration in the same isolated window:

   ```bash
   uv run tools/migrate_paper_matching_run_status_enum.py --json
   ```

   Require exit code zero, `converted` to reflect whether conversion occurred,
   the four expected `labels`, and `index_verified: true`. The migration
   creates or validates the enum, converts the column, and verifies the unique
   active-run partial index on `(trade_date, scope_key)` for `status =
   'running'`.
6. Before deployment, independently verify the type labels and index in the
   target schema:

   ```sql
   SELECT e.enumlabel
   FROM pg_enum AS e
   JOIN pg_type AS t ON t.oid = e.enumtypid
   JOIN pg_namespace AS n ON n.oid = t.typnamespace
   WHERE n.nspname = 'public' AND t.typname = 'paper_matching_run_status'
   ORDER BY e.enumsortorder;

   SELECT indexname, indexdef
   FROM pg_indexes
   WHERE schemaname = 'public'
     AND indexname = 'uq_matching_active_scope';
   ```

   The first query must return the four labels in the documented order. The
   second must show a unique index over `(trade_date, scope_key)` with the
   `status = 'running'` predicate.
7. Deploy the enum-aware API, Celery worker, and Airflow code together. Start
   the API and workers only after the verification queries pass, then confirm
   health checks and a read-only matching-run listing.
8. Resume or retry the paused Airflow matching tasks using the normal Airflow
   operator procedure. Retry only the affected date/account partitions after
   confirming that no successful fill will be replayed as a duplicate. A
   missing exact-date bar is an expected warning path: verify the resulting
   run has `status="completed_with_warnings"` and a non-zero `warning_count`,
   and verify the corresponding daily-bar diagnostic or valuation gap. An
   unexpected error remains `failed` and must be investigated rather than
   retried blindly.

### Future label compatibility

Enum labels are a compatibility contract across the database, SQLAlchemy
models, API responses, CLI output, Celery tasks, Airflow DAGs, and frontend
consumers. Additive labels require a separately reviewed migration and a
compatibility pass across every consumer. Existing labels must never be
renamed or removed in place; PostgreSQL enum ordering and persisted values are
part of the contract. A service must be able to read all labels present in the
database before that label is introduced in production. Treat unknown labels
as a deployment/schema mismatch, not as a value to coerce silently.

### Backup restore ordering

The table dump scripts are enum-aware for `paper_matching_runs`. An export that
includes that table queries the live `paper_matching_run_status` labels and
writes `CREATE TYPE` before the table dump, preserving their PostgreSQL sort
order. `db_import.sh` therefore loads the type before the table definition and
rows; dependent indexes and constraints are recreated by the dump afterward.
For `--clean`, the importer drops `paper_matching_runs` first and then drops
`paper_matching_run_status` before loading the dump. Unrelated table exports and
imports retain their existing behavior.

The scripts are not a point-in-time rollback mechanism. A clean import commits
its drop phase before loading the dump, so an import failure can leave a
partially restored database; test recovery in an isolated database and retain
the original backup. A pre-enum text dump does not supply the enum definition;
restore the type and convert only validated labels before loading such a dump.

Enum labels are a forward-compatibility boundary: exports preserve any labels
present in the source database, but older application code may reject a dump
containing a newer label. Additive labels require a separately reviewed schema
and consumer migration; existing labels must not be renamed or removed in
place. Test the restore with the target application version before production
recovery.
