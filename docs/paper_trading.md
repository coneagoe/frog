# Paper Trading Backend

The paper trading backend provides a FastAPI API for A-share simulated trading. The MVP supports multiple paper accounts, limit orders, daily matching runs, basic A-share fees, position lots, and account snapshots.

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
- `Orders`: review historical orders and cancel cancellable orders.
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
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 000001 --side buy --quantity 100 --limit-price 10.00 --trade-date 2026-06-16
uv run tools/paper_trading_cli.py matching run --trade-date 2026-06-16 --account-id 1
```

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

All fee fields are optional in the request body. Supported fields: `commission_rate`, `min_commission`, `stamp_duty_rate`, `transfer_fee_rate`. Values must be non-negative decimals. An empty request body (no fee fields) is rejected with a 422 error.

## Delete Account

Deleting an account permanently removes the paper account and its associated orders, trades, positions, position lots, snapshots, matching runs, and cash ledger entries.

```bash
curl -X DELETE http://localhost:8000/paper/accounts/1 \
  -H "Authorization: Bearer change-me"
```

## Create Limit Order

```bash
curl -X POST http://localhost:8000/paper/accounts/1/orders \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"000001","side":"buy","quantity":100,"limit_price":"10.00","trade_date":"2026-06-16"}'
```

Buy orders freeze estimated cash. Sell orders freeze sellable position quantity. Invalid lot size, insufficient cash, insufficient position, and A-share T+1 violation (same-day sell) are stored as rejected orders.

## Trade Validity Analysis

Paper trading records the original trading intent and analyzes whether the operation was valid for the specified `trade_date`. The order lifecycle status (`accepted`, `rejected`, `filled`, `cancelled`) remains separate from validity status.

Validity statuses:

- `valid`: available data supports the operation.
- `suspicious`: daily data indicates risk or uncertainty, such as a same-day limit touch.
- `invalid`: the operation is not valid for the specified trading day, such as a price outside the daily low/high range.
- `unchecked`: required market data was unavailable, so the original order is preserved without a completed analysis.

The first version uses daily bars for limit-up and limit-down detection. `trade_date` is the operation date, so default analysis and matching are same-day. A-share T+1 remains a sellable-position rule and does not shift matching to the next day.

## Run Matching

```bash
curl -X POST http://localhost:8000/paper/matching/runs \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"trade_date":"2026-06-16","account_id":1}'
```

Matching processes accepted orders for the trade date. Tradable orders fill at limit price, untouched orders remain accepted, and suspended symbols are rejected.

## Query Account State

```bash
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/positions
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/trades
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/snapshots
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/cash-ledger
```

Snapshots are generated after matching and use close prices for valuation.

### Analytics

`GET /paper/accounts/{account_id}/analytics` returns account-level analytics for the paper trading dashboard.

The response includes:

- Activity: daily, weekly, and monthly order/trade frequency.
- Execution: fill rate, rejection rate, and reject reason distribution.
- Trade quality: full-position round-trip win rate, payoff ratio, profit factor, average win/loss, consecutive wins/losses, and holding days.
- Risk: total return, max drawdown, current drawdown, and optional Sharpe, Sortino, and Calmar metrics.

Round-trip metrics use full-position cycles. A cycle opens when an account's symbol quantity moves from zero to positive and closes when that symbol returns to zero. Partial exits update the open cycle but do not count as closed round trips.
