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

The paper trading frontend lives in `frontend/paper-trading` and proxies browser requests to the FastAPI backend.

```bash
cd frontend/paper-trading
npm install
export PAPER_TRADING_API_BASE_URL="http://localhost:8000"
export PAPER_TRADING_API_TOKEN="change-me"
npm run dev
```

Open `http://localhost:3000/accounts`.

The bearer token is read only by Next.js route handlers. Browser code calls local `/api/paper/*` endpoints and does not receive `PAPER_TRADING_API_TOKEN`.

## Create Account

```bash
curl -X POST http://localhost:8000/paper/accounts \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","initial_cash":"100000.00"}'
```

## Create Limit Order

```bash
curl -X POST http://localhost:8000/paper/accounts/1/orders \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"000001.SZ","side":"buy","quantity":100,"limit_price":"10.00","trade_date":"2026-06-16"}'
```

Buy orders freeze estimated cash. Sell orders freeze sellable position quantity. Invalid lot size, insufficient cash, and insufficient position are stored as rejected orders.

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
