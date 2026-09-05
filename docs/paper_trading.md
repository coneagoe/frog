# Paper Trading Backend

The paper trading backend provides a FastAPI API for simulated trading. It supports multiple paper accounts, A-share, ETF, and Southbound Hong Kong Stock Connect ordinary-stock limit orders, daily matching runs, market-specific fees, position lots, validity checks, pending HK settlement, and account snapshots.

## Docker (Recommended)

The paper trading backend is containerized. Set the paper-trading environment variables in your `.env` file; secrets must never be committed.

| Variable | Purpose | Required / default | Security / format notes |
| --- | --- | --- | --- |
| `FROG_ENV` | Selects runtime mode for auth settings. | Required; accepted values are `local`, `test`, `production`. | Production rejects the built-in JWT secret and requires secure cookies. |
| `AUTH_REGISTRATION_ENABLED` | Enables browser registration. | Required in Compose; registration only works when the value is exactly `true`. | Any other value leaves registration disabled. |
| `AUTH_PUBLIC_BASE_URL` | Public base URL used when generating password-reset and email-verification links. | Required in Compose. | Must be an absolute `https://` URL. |
| `AUTH_OWNER_EMAIL` | Verified user that receives ownership of pre-existing unowned paper accounts. | Required in Compose when such accounts exist. | Create and verify this user before the ownership backfill; it must identify exactly one user. |
| `PAPER_TRADING_JWT_SECRET` | Signs browser session JWTs. | Required in production; otherwise defaults to the local-development secret. | Use a non-default secret in production. |
| `PAPER_TRADING_JWT_TTL_SECONDS` | Browser session token lifetime. | Optional; defaults to `3600`. | Must be a positive integer. |
| `PAPER_TRADING_COOKIE_SECURE` | Marks session and CSRF cookies as secure. | Required in Compose; defaults to `false` outside production. | Production requires `true`. |
| `PAPER_TRADING_SESSION_COOKIE_NAME` | Session cookie name. | Optional; defaults to `paper_trading_session`. | Must be a valid cookie token. |
| `PAPER_TRADING_CSRF_COOKIE_NAME` | CSRF cookie name. | Optional; defaults to `paper_trading_csrf`. | Must be a valid cookie token. |
| `PAPER_TRADING_API_TOKEN` | Bearer token for backend API and CLI access. | Required in Compose. | Treat as a secret. The browser frontend uses session and CSRF cookies instead. |
| `REDIS_URL` | Redis connection used by auth rate limiting. | Optional; defaults to `redis://redis:6379/0`. | If Redis is unavailable, auth operations fail closed. |
| `MAIL_SERVER` | SMTP host for verification and password-reset mail. | Required when auth mail is used. | Set by Compose from `SMTP_HOST`. |
| `MAIL_PORT` | SMTP port for verification and password-reset mail. | Required when auth mail is used. | Set by Compose from `SMTP_PORT`; must be numeric. |
| `MAIL_SENDER` | From address for auth email. | Required when auth mail is used. | Set by Compose from `SMTP_MAIL_FROM`. |
| `MAIL_PASSWORD` | SMTP password for auth email. | Required when auth mail is used. | Set by Compose from `SMTP_PASSWORD`; treat as a secret. |

For manual backend startup, set the database connection fields that the paper-trading API actually reads from `StorageConfig`:

| Variable | Purpose | Required / default | Security / format notes |
| --- | --- | --- | --- |
| `db_host` | PostgreSQL host used by the paper-trading backend. | Required outside Compose. | Use the database host reachable from the API process. |
| `db_port` | PostgreSQL port used by the paper-trading backend. | Required outside Compose. | Must be a valid port number. |
| `db_username` | PostgreSQL username used by the paper-trading backend. | Required outside Compose. | Secret; do not commit it. |
| `db_password` | PostgreSQL password used by the paper-trading backend. | Required outside Compose. | Secret; do not commit it. |

Complete Docker Compose `.env` example:

```bash
echo 'FROG_ENV="local"' >> .env
echo 'AUTH_REGISTRATION_ENABLED="true"' >> .env
echo 'AUTH_PUBLIC_BASE_URL="https://paper-trading.example.com"' >> .env
echo 'AUTH_OWNER_EMAIL="owner@example.com"' >> .env
echo 'PAPER_TRADING_JWT_SECRET="change-me"' >> .env
echo 'PAPER_TRADING_JWT_TTL_SECONDS="3600"' >> .env
echo 'PAPER_TRADING_COOKIE_SECURE="true"' >> .env
echo 'PAPER_TRADING_SESSION_COOKIE_NAME="paper_trading_session"' >> .env
echo 'PAPER_TRADING_CSRF_COOKIE_NAME="paper_trading_csrf"' >> .env
echo 'PAPER_TRADING_API_TOKEN="change-me"' >> .env
echo 'REDIS_URL="redis://redis:6379/0"' >> .env
echo 'SMTP_HOST="smtp.example.com"' >> .env
echo 'SMTP_PORT="465"' >> .env
echo 'SMTP_MAIL_FROM="sender@example.com"' >> .env
echo 'SMTP_PASSWORD="change-me"' >> .env
echo 'SMTP_USER="smtp-user"' >> .env
echo 'ALERT_EMAILS="ops@example.com"' >> .env
```

Before the first deployment that enables browser ownership, register and verify
`AUTH_OWNER_EMAIL`. During the maintenance window, stop API, CLI, Celery, and
Airflow writers; take and verify a database backup; then run the account
ownership backfill with that verified, unique owner. It fails closed if the
email is missing, ambiguous, or unverified, and must be recorded with the
deployment owner and output. Start the API only after the backfill succeeds,
then start the frontend and resume workers and schedules. New browser-created
accounts are owned by the authenticated user; do not use the backfill as a
routine reassignment tool.

Then start the services:

```bash
docker compose up -d paper-trading paper-trading-frontend
```

The API listens on `http://localhost:8000`. Compose wires `SMTP_HOST`, `SMTP_PORT`, `SMTP_MAIL_FROM`, and `SMTP_PASSWORD` into the backend's `MAIL_*` variables; `SMTP_USER` and `ALERT_EMAILS` are stack-level prerequisites for the shared email wiring.

`FROG_ENV` accepts `local`, `test`, or `production`.
`local` and `test` keep the development JWT secret and insecure cookie defaults used by the static Bearer-token tests.
`production` requires `PAPER_TRADING_JWT_SECRET` to be set to a non-default value and `PAPER_TRADING_COOKIE_SECURE=true`.
If Redis or auth mail is unavailable, the auth endpoints fail closed instead of opening registration or email flows.

## Manual Start

If running outside Docker, set environment variables and start the API directly:

```bash
export PAPER_TRADING_API_TOKEN="change-me"
export FROG_ENV=local
export AUTH_REGISTRATION_ENABLED=true
export AUTH_PUBLIC_BASE_URL="https://paper-trading.example.com"
export AUTH_OWNER_EMAIL="owner@example.com"
export PAPER_TRADING_JWT_SECRET="change-me"
export PAPER_TRADING_JWT_TTL_SECONDS=3600
export PAPER_TRADING_COOKIE_SECURE=false
export PAPER_TRADING_SESSION_COOKIE_NAME=paper_trading_session
export PAPER_TRADING_CSRF_COOKIE_NAME=paper_trading_csrf
export REDIS_URL="redis://localhost:6379/0"
export MAIL_SERVER="smtp.example.com"
export MAIL_PORT=465
export MAIL_SENDER="sender@example.com"
export MAIL_PASSWORD="change-me"
export db_host=localhost
export db_port=5432
export db_username=quant
export db_password=quant
uv run uvicorn paper_trading.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Authentication modes

Browser users authenticate through registration, email verification, and login.
Login issues an HttpOnly session cookie plus a readable CSRF cookie. Browser
requests use the same-origin frontend proxy; unsafe methods include the CSRF
value in `X-CSRF-Token`. Do not put `PAPER_TRADING_API_TOKEN` in browser code,
browser environment variables, or frontend requests.

Bearer-token authentication is for trusted automation only: the repo CLI,
operator scripts, and direct backend API calls. Those clients must send:

```bash
Authorization: Bearer change-me
```

Keep that token in a secret store and never paste production values into logs,
examples, browser tests, or email links. Browser sessions and Bearer tokens are
separate credentials; a browser session is not a substitute for automation,
and a Bearer token is not a browser login mechanism.

When `FROG_ENV=production`, the API refuses to start unless `PAPER_TRADING_JWT_SECRET` is set to a non-default value and `PAPER_TRADING_COOKIE_SECURE=true`.
`AUTH_PUBLIC_BASE_URL` must be an absolute HTTPS URL because it is embedded in password-reset and email-verification links.
`AUTH_REGISTRATION_ENABLED` only enables registration when the value is exactly `true`.

## Start The Frontend

The Docker Compose stack includes the backend and Next.js frontend:

```bash
docker compose up -d paper-trading paper-trading-frontend
```

Open `http://localhost:3000/accounts`. The frontend container talks to the backend container at `http://paper-trading:8000`.

## Manual Frontend Start

The paper trading frontend lives in `frontend/paper-trading` and proxies browser requests to the FastAPI backend.

| Variable | Purpose | Required / default | Security / format notes |
| --- | --- | --- | --- |
| `PAPER_TRADING_API_BASE_URL` | Base URL used by the Next.js server-side routes to reach the paper-trading backend. | Required for local frontend startup; Compose sets it to the backend service URL. | Must point to the backend the server can reach. |

```bash
cd frontend/paper-trading
npm install
export PAPER_TRADING_API_BASE_URL="http://localhost:8000"
npm run dev
```

Open `http://localhost:3000/accounts`. The frontend has separate workspaces for accounts, order entry, historical orders, historical trades, and analytics:

- `Accounts`: create/delete accounts, select an account, and review its positions and cash ledger.
- `Trade`: submit paper limit orders.
- `Orders`: review historical orders in pages of 25, filter by Asia/Shanghai trade date (today, trailing 7 or 30 days, or a custom inclusive range), cancel cancellable orders, and delete orders. The URL preserves the account, dates, and page; a cancel or delete that empties the current page returns the view to the last valid page.
- `Trades`: review historical executions in pages of 25, filter by Asia/Shanghai trade date (today, trailing 7 or 30 days, or a custom inclusive range), preserve the account, date range, and page in the URL, and keep the execution history read-only.
- `Analytics`: review snapshots, total assets, trades, and cash movements. Repair-marked legacy accounts keep the stored snapshot chart but show a repair-required state instead of performance panels.

Browser code calls local `/api/paper/*` endpoints with its session cookie. The
frontend adds the readable CSRF cookie as `X-CSRF-Token` on POST, PATCH, and
DELETE requests; the proxy forwards the browser's cookies, content type, and
CSRF header to the backend. The frontend does not require
`PAPER_TRADING_API_TOKEN`.

Cookie-authenticated requests are limited to the logged-in user's paper
accounts across account details, orders, trades, analytics, snapshots, and
corporate actions. Missing or another user's account is returned as the same
not-found response. The system Bearer token remains the unrestricted interface
for trusted automation, including matching, repairs, snapshot recalculation,
and global ETF eligibility operations. Login attempts are rate-limited by
client IP and normalized email; Redis failures fail closed.

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
uv run tools/paper_trading_cli.py order create --account-id 1 --symbol 510300 --market etf --side buy --quantity 100 --limit-price 4.001 --trade-date 2026-07-18
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment "回踩确认后买入"
uv run tools/paper_trading_cli.py order update-comment --order-id 123 --comment ""
uv run tools/paper_trading_cli.py order delete --order-id 123
uv run tools/paper_trading_cli.py matching run --trade-date 2026-06-16 --account-id 1
uv run tools/paper_trading_cli.py etf_eligibility list --status unknown
uv run tools/paper_trading_cli.py etf_eligibility get --symbol 510300
uv run tools/paper_trading_cli.py etf_eligibility classify --symbol 510300 --status supported --reviewed-by alice
uv run tools/paper_trading_cli.py repair etf-markets
```

The `order update-comment` command with `--comment ""` clears the stored comment to `NULL` on the order and all linked trades.

### ETF Eligibility Review

ETF orders require an eligibility review in the later ETF-support workflow. Use
the CLI to list the refresh-discovered records, inspect one bare six-digit
symbol, and record a reviewer classification. Classification accepts only
`supported` or `money_market`; the API remains the authority for ETF symbol and
provider validation.

```bash
uv run tools/paper_trading_cli.py etf_eligibility list
uv run tools/paper_trading_cli.py etf_eligibility list --status unknown
uv run tools/paper_trading_cli.py etf_eligibility get --symbol 510300
uv run tools/paper_trading_cli.py etf_eligibility classify --symbol 510300 --status supported --reviewed-by alice
```

Order creation queues an accepted order; it does not run matching or create a trade immediately. If an `idempotency_key` is supplied, repeating the same request for the same account returns the original order without reserving cash again. Reusing that key for different order fields is rejected.

Past-date A-share orders are recorded as historical source orders and immediately
rebuild the affected account ledger. The replay processes orders by trade date
and order ID, so historical cash, holdings, T+1 eligibility, and exact-date
market data determine the result. Historical order entry does not reserve the
account's pre-replay current cash or position; replay creates the appropriate
historical reservation. Current-date orders retain their normal immediate
reservation behavior.

After a daily history download, the daily-history DAG automatically calls the
delayed-bar rebuild endpoint. It selects accepted A-share orders with an
unresolved exact-date BFQ diagnostic or ETF orders with an unresolved exact-date
raw diagnostic whose raw `etf_daily` bar is now available, then rebuilds each
affected account from the earliest affected order. The rebuild preserves manual
cash events and cancellations, reapplies normal matching rules, and records
lightweight rebuild audit metadata. The authenticated endpoint is
`POST /paper/matching/runs/rebuilds`.

### Repair Historical ETF Markets

Use the explicit repair operation when historical orders were persisted with
`market="a_share"` even though their bare six-digit symbols are present in the
ETF catalogue. The command defaults to a dry run and reports all candidates
without writes:

```bash
uv run tools/paper_trading_cli.py repair etf-markets
```

After reviewing the result, apply the repair explicitly:

```bash
uv run tools/paper_trading_cli.py repair etf-markets --apply
```

The authenticated API endpoint is `POST /paper/repairs/etf-markets`; its body
defaults to `{"apply": false}`. Applied repairs process one account at a time,
lock the account, change currently qualifying orders to `etf`, and rebuild from
that account's earliest corrected order date. A failed account rolls back while
completed account repairs remain committed. The operation does not remove prior
A-share missing-date diagnostics.

### Repair Trading Snapshot Timestamps

Use this repair when trading snapshots were persisted with a noncanonical
`event_at`. The authenticated API endpoint is `POST
/paper/repairs/trading-snapshot-event-at`; its request body accepts
`account_id`, `start_date`, `end_date`, and `apply`.

Dry runs return the full `matched_count` while capping response details at 100
candidate rows. Applied repairs update only the reviewed noncanonical rows and
report both the full `matched_count` and the `updated_count`. Re-running the
same repair after a successful apply is idempotent: the final dry run should
report `matched_count: 0` and `updated_count: 0`.

```bash
export PAPER_TRADING_API_TOKEN="change-me"
export PAPER_TRADING_API_BASE_URL="http://localhost:8000"

uv run tools/paper_trading_cli.py --json repair snapshot-event-at \
  --account-id 6 --start-date 1970-01-01 --end-date 2026-09-01

uv run tools/paper_trading_cli.py --json repair snapshot-event-at \
  --account-id 6 --start-date 1970-01-01 --end-date 2026-09-01 --apply

uv run tools/paper_trading_cli.py --json repair snapshot-event-at \
  --account-id 6 --start-date 1970-01-01 --end-date 2026-09-01
```

The observed bad processing timestamp is `2026-09-01`, but no narrower
affected business-date span is committed in this repository. Use the complete
historical scope ending at that batch date; the repair itself changes only
noncanonical rows. Retain all three JSON outputs for operator review. Do not
embed a production token or execute these production commands during
implementation tests.

Before executing or accepting the apply, compare its `matched_count` with the
retained dry-run result: the apply `matched_count` must equal the retained
dry-run `matched_count`. If it differs, stop and re-review the scope; do not
treat the apply as approved scope.

Account fee flags are optional. When omitted, account creation uses the built-in `a_share` preset, which matches the previous hardcoded A-share fees: commission rate `0.0003`, minimum commission `5.00`, stamp duty rate `0.0005`, and transfer fee rate `0.00001`. ETF orders use the account's `etf_commission_rate`, defaulting to `0.00006`; ETF fees are commission-only, with no minimum commission, stamp duty, or transfer fee. Explicit fee flags override the preset values for the new account.

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
- Duplicate symbols in the same market create separate lots and aggregate into
  one position per `(market, symbol)`. The same bare symbol may be imported in
  distinct markets as separate positions.
- Import is rejected if the account does not exist (404) or already has positions (422).

### Repair Imported Position Markets

Imports may optionally specify `market` as `a_share` or `hk_connect`. The aggregate
position and each imported lot use the same market-qualified identity. If historical
imported holdings were stored with the wrong market, run the standalone administrative
repair command with an explicit source-market and target-market mapping. Do not use
this command as a general market migration: it never discovers or changes unspecified
account/market/symbol identities, and it never changes trade-sourced lots.

```bash
uv run tools/repair_paper_position_markets.py \
  --mapping ACCOUNT_ID:a_share:00700:hk_connect
```

Replace `ACCOUNT_ID` with the account ID supplied for the deployment; no production
account ID is embedded in this procedure. Repeat `--mapping` for additional explicit
targets. Each mapping names the source and target markets, so the command updates
only the specified source-market position and imported lots. Every requested
source position and target-market collision is checked before any update is
issued. All updates run in one transaction, so a missing source or existing
distinct target-market position leaves all targets unchanged. A successful repeat
must name the position's current market as its source market.
Use `--json` for machine-readable results:

```bash
uv run tools/repair_paper_position_markets.py --json \
  --mapping ACCOUNT_ID:a_share:00700:hk_connect
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

The only built-in preset is `a_share`. Fee values must be non-negative decimals; zero is valid for fee-free test accounts. Account creation requires positive `initial_cash` and writes one `initial` snapshot at NAV `1.000000`. New accounts have no `migration_repair_reason`. Later trading valuations keep one `trading` snapshot per account and `trade_date`; `initial` points keep their existing one-per-account identity.

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

All fee fields are optional in the request body. Supported A-share fields are `commission_rate`, `min_commission`, `stamp_duty_rate`, and `transfer_fee_rate`. The ETF field is `etf_commission_rate`. Supported HK Connect fields are `hk_commission_rate`, `hk_min_commission`, `hk_stamp_duty_rate`, `hk_trading_fee_rate`, `hk_sfc_levy_rate`, `hk_afrc_levy_rate`, and `hk_settlement_fee_rate`. Values must be non-negative decimals. An empty request body (no fee fields) is rejected with a 422 error.

## Hong Kong Stock Connect Support

Set `market` to `hk_connect` when creating Southbound Hong Kong Stock Connect ordinary-stock orders, or `etf` when creating ETF orders. If `market` is omitted, the backend treats the order as `a_share` for backward compatibility.

```bash
curl -X POST http://localhost:8000/paper/accounts/1/orders \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"00700","market":"hk_connect","side":"buy","quantity":100,"limit_price":"400.00","trade_date":"2026-07-18"}'
```

HK Connect support is scoped to ordinary stocks. The backend uses explicit market routing rather than symbol inference: orders, trades, positions, and validity checks persist `market`. State and market-data diagnostics are identified by market and symbol, so records sharing a symbol in different markets remain separate and diagnostics identify the affected market. HK orders use HK GGT daily bars, HK-specific fees, board-lot and tick-size validation, and no A-share limit-up/down validity analysis. HK sell proceeds are not immediately available cash; they remain pending until the T+2 settlement service releases them. Account snapshots include pending settlement in total assets and expose `pending_settlement`.

## ETF Support

For a bare six-digit symbol present in the ETF catalogue, order creation assigns
`market="etf"` whether `market` is omitted, set to `a_share`, or set to `etf`.
Symbols absent from the catalogue retain the requested or default market. The
catalogue determines market identity only: supported ETF orders still require a
currently listed Shanghai or Shenzhen ETF metadata record and an eligibility
classification of `supported`. Money-market, disabled, unreviewed, unknown, and
otherwise ineligible ETFs are rejected before order acceptance.

ETF quantity must be a positive multiple of 100 and the limit price must be a
positive multiple of CNY `0.001`. ETF orders use the account's
`etf_commission_rate` and charge commission only: no minimum commission, stamp
duty, or transfer fee applies. ETF buys reserve the notional amount plus this
commission; ETF sells reserve sellable quantity.

ETF matching and validity checks use ETF daily bars and the daily low/high price
range, without A-share limit-up/down analysis. ETF holdings are T+1: units
bought on a trade date cannot be sold until a later trade date, including during
historical replay. Unlike HK Connect, ETF sell proceeds become available cash
immediately when the sell fills.

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

The matching and snapshot flow treats cash flows as pre-market effective on their `trade_date`. A cash flow changes account scale and share count but does not by itself change unit NAV. API callers may optionally send `occurred_at` as an offset-qualified timestamp such as `2026-07-20T09:30:00+08:00`; a timestamp without a timezone offset is rejected. When it is omitted, the server records the current UTC instant. Ledger history is ordered deterministically by `(occurred_at, ledger_id)`, where `ledger_id` resolves equal timestamps.

Every new account starts with an `initial` snapshot at unit NAV `1.000000`. A deposit or withdrawal uses the latest valid trading NAV at or before its occurrence time; when no such valuation exists, it uses that initial NAV baseline. The persisted effective NAV and share delta make the cash-flow calculation auditable.

## Create Limit Order

```bash
curl -X POST http://localhost:8000/paper/accounts/1/orders \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"000001","side":"buy","quantity":100,"limit_price":"10.00","trade_date":"2026-06-16","comment":"突破买入"}'
```

Buy orders freeze estimated cash. Sell orders freeze sellable position quantity. Invalid lot size, insufficient cash, insufficient position, and A-share T+1 violation (same-day sell) are stored as rejected orders. Past open-date A-share orders are accepted as historical source orders without reserving present-day cash or inventory; replay evaluates them against historical cash, holdings, T+1, and exact-date market data. Current-date orders retain their normal immediate reservation behavior.

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

Deleting an order hard-deletes the order. If the order had already filled, the paper trading backend recalculates the account's trades, cash ledger, positions, position lots, round trips, matching runs, validity checks, and snapshots from the remaining order history. Historical replay uses the same account-level database lock as account-scoped matching, preserves manual cash events, comments, and cancellations, and rolls back the complete rebuild on unexpected errors. A surviving order without an exact-date daily bar remains accepted; its replay matching run records a warning and daily-bar diagnostic rather than treating missing market data as a fatal replay failure.

```bash
uv run tools/paper_trading_cli.py order delete --order-id 123
```

Raw API:

```bash
curl -X DELETE "$PAPER_TRADING_API_BASE_URL/paper/orders/123" \
  -H "Authorization: Bearer $PAPER_TRADING_API_TOKEN"
```

### Rebuild an account ledger from a date

Use an explicit historical ledger rebuild when derived account state needs to be replayed from a known `start_date` without deleting source facts. The rebuild preserves orders, cancellations, deposits, withdrawals, manual cash adjustments, existing validity checks, and historical matching runs, then recreates derived trades, trade cash events, positions, lots, round trips, snapshots, valuation gaps, and new replay matching runs from that date forward. A lightweight audit row records the account, start date, trigger evidence, deleted/regenerated counts, terminal status, and any error detail.

```bash
uv run tools/paper_trading_cli.py account rebuild_ledger --account-id 1 --start-date 2026-07-17 --trigger-evidence "manual repair"
```

Raw API:

```bash
curl -X POST "$PAPER_TRADING_API_BASE_URL/paper/accounts/1/ledger-rebuilds" \
  -H "Authorization: Bearer $PAPER_TRADING_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2026-07-17","trigger_evidence":{"source":"operator","note":"manual repair"}}'
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

Trading snapshots persist a UTC `event_at`, `point_type="trading"`, and a quality status. Every trading snapshot is canonicalized to `23:59:59.999999+00:00` for its `trade_date`; initial snapshots retain their creation timestamp. A valid NAV must be a finite, strictly positive Decimal. Missing, non-finite, zero, or negative NAV is stored as `net_asset_value=None` with `quality_status="invalid"` and one of `missing_share_state`, `missing_nav`, `non_finite_nav`, or `non_positive_nav`. Invalid points keep the other financial fields and do not update account NAV state. NAV is never replaced with `total_assets`. Nullable `valuation_quality` (`current` or `stale_suspended`) and JSON `valuation_details` record later stale-price evidence; both stay `null` on `initial` points and on legacy rows until a later valuation writes them.

Analytics reports valuation gaps separately in date order through `valuation_gaps`. Each entry contains the exact `trade_date`, missing symbols, diagnostic details, and whether the gap has been resolved. A valid snapshot with `valuation_quality="stale_suspended"` remains a NAV input; invalid or unavailable valuation points are excluded from NAV calculations and never fall back to `total_assets`. The bounded snapshot recalculation endpoint may be used to retry one account and trading date after market data is available; it preserves baseline, orders, and ledger data while retaining one trading snapshot for that scope.

### 日期语义

- API/CLI 下单必须显式提供 `trade_date`，不使用默认日期；匹配同样必须显式提供 `trade_date`，并以它进行订单选择、行情柱、成交、结算和快照处理。
- A 股日线历史 DAG 将 Airflow `context['logical_date']` 转换为 `Asia/Shanghai` 后得到业务日期，并将该日期传给 BFQ/HFQ 下载及 EOD 模拟交易匹配；周末及非交易日会跳过。`data_interval_end` 仅表示数据区间右边界，不作为该工作流的交易业务日期。
- 历史订单下单时，如果指定交易日的精确日线数据已存在，会立即从该日期重建整个受影响账户账本；如果数据缺失，则订单保持 `accepted` 并记录诊断，等待后续补数或同日期重试。账本重建按交易日期和订单 ID 重放，以保持历史现金、持仓、T+1 资格及成交结果一致。
- 只有 `OrderService` 的历史重试资格校验会将订单提交日期与 `date.today()` 比较；这只影响订单是否被接受，不会推导订单日期。

日线历史 DAG 对缺失或失败的 BFQ/HFQ 下载记录 provider 结果；汇总警告仍允许模拟交易匹配继续执行，只有致命的汇总失败会阻止匹配。

## Query Account State

```bash
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/positions
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/trades
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/snapshots
curl -H "Authorization: Bearer change-me" http://localhost:8000/paper/accounts/1/cash-ledger
```

Account create, list, get, and patch responses include nullable
`migration_repair_reason`. Normal accounts return `null`. Repair-marked legacy
accounts return `legacy_ordering_uncertain`.

Snapshot list responses keep repository order (`event_at`, then `id`) and include
`point_type` (`initial` or `trading`), timezone-aware `event_at`,
`quality_status` (`valid` or `invalid`), nullable `invalid_reason`, nullable
`valuation_quality` (`current` or `stale_suspended`), and nullable
`valuation_details`. `id` is the stable same-timestamp order key. Invalid points
are returned with their stored financial fields; `total_assets` is never
substituted for NAV. Snapshot listing remains available for repair-marked
accounts and does not invent a baseline point.

Trade responses include the `comment` field:

Position, order, and trade list responses also include the nullable `stock_name`
field. It is a display-only name resolved from the security metadata tables; it
is `null` when metadata is unavailable and is not persisted in paper-trading
records.

Position responses additionally include request-time valuation fields for the
Accounts Positions card:

- `mark_price`: the price used to value the open position, or `null` when no
  usable price is available.
- `price_source`: `real_time` when a valid A-share or HK Connect real-time quote
  is available, or `db_close` when valuation uses the latest stored market
  close. ETF positions use the ETF daily close directly.
- `unrealized_pnl`: `total_quantity * mark_price - cost_amount`, or `null`
  when neither price source is available.

The positions endpoint batches real-time quote retrieval for A-share and HK
Connect positions. A missing or invalid quote falls back per position to the
latest stored BFQ close using its market route. ETF positions bypass the
real-time quote batch and use the latest stored raw `etf_daily` close. This request-time
valuation does not change persisted realized PnL or snapshot/NAV calculations.

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

## Corporate Actions

Corporate actions are account-scoped administrative events. They are submitted
through `POST /paper/accounts/{account_id}/corporate-actions` and listed through
`GET /paper/accounts/{account_id}/corporate-actions`. Both endpoints require the
same bearer token as the other paper-trading endpoints. The create request and
response models are the public names
`CorporateActionCreateRequest`, `CorporateActionCreateResponse`,
`CorporateActionEventResponse`, and `CorporateActionImpactResponse` from
`paper_trading/schemas/corporate_actions.py`. The recalculation member uses
`SnapshotRecalculationResponse`.

Create example:

```bash
curl -X POST http://localhost:8000/paper/accounts/1/corporate-actions \
  -H "Authorization: Bearer change-me" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"000001","market":"a_share","event_type":"dividend","event_at":"2026-07-20T08:00:00+08:00","idempotency_key":"000001-dividend-20260720","parameters":{"per_share_amount":"0.25"}}'
```

The request fields are `symbol`, `market` (default `a_share`), `event_type`,
`event_at`, `idempotency_key`, and `parameters`. `symbol` and
`idempotency_key` are trimmed non-blank strings; their maximum lengths are 20
and 100. `event_at` must contain a timezone offset and is normalized to UTC
before comparison and persistence. The event date is `event_at`'s UTC calendar
date. It is the affected business-date anchor, while `event_at` itself is the
ordering timestamp. The list query supports optional `symbol`, `event_type`,
`start_at`, and `end_at`; timestamp bounds also require timezone offsets.

The response contains `event`, `impact`, and `recalculation`. An event has
`id`, `account_id`, `market`, `symbol`, `event_type`, `event_at`,
`idempotency_key`, `parameters`, `processing_status`, `processed_at`,
`processing_metadata`, `error_details`, the before/after cash, quantity, and
cost fields, `affected_start_date`, `affected_end_date`, and `created_at`.
The impact repeats the cash, quantity, cost, and affected-date fields. The
recalculation response has `account_id`, `updated_dates`,
`unavailable_dates`, `failed_dates`, and `errors`. Event/list money is
represented in serialized/display values at 4 decimal places and quantities at
6 decimal places; this is serialization only and does not reduce internal
precision.

The five supported event types have exact parameter contracts and effects:

- `dividend`: requires positive finite `per_share_amount`. Cash increases by
  `eligible_quantity * per_share_amount`; quantity and cost do not change. If
  the account has shares, the dividend also increases unit NAV by the cash
  delta divided by share count. With no holdings, the impact is zero and no
  dividend cash is created.
- `split`: requires positive finite `ratio`. Quantity becomes
  `before_quantity * ratio`; cost is preserved in aggregate and lot cost is
  repriced to preserve NAV continuity.
- `reverse_split`: requires positive finite `ratio` below 1. Quantity becomes
  `before_quantity * ratio`; the same aggregate-cost and lot repricing rules
  apply. Fractional resulting holdings are rejected because paper holdings are
  integer quantities.
- `bonus_share`: requires positive finite `bonus_ratio`. The quantity delta is
  `before_quantity * bonus_ratio`; no cash is exchanged and aggregate cost is
  unchanged, preserving NAV continuity.
- `rights_issue`: requires positive finite `subscription_ratio` and
  `subscription_price`. New quantity is
  `before_quantity * subscription_ratio`, available cash decreases by the new
  quantity times subscription price, and the subscription cost is added to
  aggregate cost. The account must have enough available cash, and fractional
  resulting holdings are rejected.

Corporate-action cash is an internal `corporate_action` cash-ledger event. It
is not an external deposit or withdrawal and therefore is not treated as an
external TWR cash flow. Deposits and withdrawals change account scale and
share count and are excluded from investment return; corporate-action cash
remains part of the portfolio event and its resulting NAV/account state.
When the eligible quantity is zero, every action has zero quantity/cash impact
except that the event remains auditable; a no-holding event does not invent a
position, alter NAV, or create cash.

Account, cash-ledger, snapshot, and corporate-action amount and quantity fields
use `Numeric(30, 12)` internal/storage precision where specified by the
corporate-action schema. Legacy position, position-lot cost, and price columns
retain their existing precision where applicable. Domain and storage
quantization uses `ROUND_HALF_UP` where the implementation applies that
rounding rule; public Decimal response serialization/display quantization
follows the actual serializer behavior and is not implied to use
`ROUND_HALF_UP`. Cash-flow rounding is auditable through `rounding_residual`,
stored at `Numeric(30, 24)`, with the invariant:

```text
rounding_residual = amount - share_delta * net_asset_value
```

Public Decimal response serialization/display values use the documented
serializer precision of 4 decimal places for money and 6 decimal places for
quantities. Consumers must use stored/internal values for reconciliation, not
the shorter serialized/display values.

Events are listed and audit records are ordered deterministically by
`(event_at, id)`. Newly submitted actions apply to the account's current state;
the implementation does not provide full historical corporate-action event
replay or apply existing actions historically in `(event_at, id)` order. The
account plus `idempotency_key` is unique. Reusing the same key with the same
account, market, symbol, event type, UTC-normalized `event_at`, and canonical
parameters returns the original event/impact/recalculation without applying
the action again. Reusing the key for any different request returns HTTP 409
with `IDEMPOTENCY_KEY_CONFLICT`; validation failures return HTTP 422 and an
unknown account returns HTTP 404.

Creating an event updates the affected account/position state and invokes
bounded snapshot recalculation from the UTC event date through the latest
affected trading snapshot or valuation-gap date. The response identifies
`updated_dates`, `unavailable_dates`, and `failed_dates`. A missing daily price
does not discard the corporate action: the date is recorded as a valuation gap
and can be recalculated later. A stale suspended price may produce a valid
snapshot with `valuation_quality="stale_suspended"` and details; an invalid or
unavailable valuation is not replaced with `total_assets`. The explicit
snapshot recalculation endpoint can retry a bounded date range after market
data is repaired while preserving the initial baseline, source orders, and
cash ledger.

Provider synchronization is out of scope for this API. Corporate-action
creation does not fetch or reconcile provider corporate-action records, and no
provider-sync DAG is added or implied. Existing daily-history provider DAGs
and their matching constraints remain unchanged; they do not submit these
events automatically. Operators or an upstream integration must provide the
validated request explicitly.

### Corporate-Action Migration

The corporate-action table is additive. Migration preserves existing account,
snapshot, order, trade, and cash-ledger data and does not synthesize historical
corporate actions from provider data. Existing snapshot financial fields are
not rewritten to manufacture returns. Chronology that cannot be proven keeps
the account marked `legacy_ordering_uncertain`; such an account retains its
stored snapshot chart but analytics remain unavailable until repaired. The
production PostgreSQL snapshot-series migration inserts at most one valid
initial point at NAV `1.000000` only when positive `initial_cash`, a non-null
`created_at`, no existing initial point, and provable chronology are present.
SQLite startup does not insert that baseline. Migration cannot recover missing
provider events, infer uncertain historical ordering, or repair missing/stale
market prices; those are documented data-quality limitations.

### Analytics

`GET /paper/accounts/{account_id}/analytics` returns account-level analytics for the paper trading dashboard.

The payload is a discriminated union on `available`. A normal account returns
HTTP 200 with `available: true` and the overview, activity, execution, trade
quality, and risk fields below. An account whose `migration_repair_reason` is
set returns HTTP 200 with `available: false`, reason
`legacy_ordering_uncertain`, and any persisted `valuation_gaps`, without metric
computation. A replay-unavailable response likewise retains persisted
`valuation_gaps`; unavailable responses use `valuation_gaps: null` when none
exist. Unknown accounts remain HTTP 404.

The Analytics frontend keeps account selection, loading and error handling, the
Overview container, and the stored snapshot chart. When `available` is false it
replaces the performance summary and the Activity, Execution, Trade Quality, and
Risk panels with: `Historical ordering requires account repair before performance analytics are available.`

The available response includes:

- Activity: nullable paper-order activity summaries. For accounts with orders,
  coverage runs from the earliest order's `trade_date` through the current
  `Asia/Shanghai` date. It reports daily, ISO-weekly, and calendar-month
  averages for total, successful, and failed orders across every period in that
  inclusive range, including zero-order periods, weekends, holidays, and
  partial boundary periods. Orders dated after the current `Asia/Shanghai`
  date are excluded from Activity; if no orders remain after that filter,
  Activity is `null`. Total counts all remaining paper orders; successful
  counts only `filled` orders; failed counts only `rejected` orders. The UI
  presents these summaries rather than period-detail tables; all non-Activity
  panels retain their current behavior.
- Execution: fill rate, rejection rate, and reject reason distribution.
- Trade quality: full-position round-trip win rate, payoff ratio, profit factor, average win/loss, consecutive wins/losses, and holding days.
- Risk: total return, max drawdown, current drawdown, and optional Sharpe, Sortino, and Calmar metrics.

`total_return` is the linked time-weighted return (TWR) from the ordered valid unit-NAV series: each consecutive valid NAV ratio is linked, so deposits and withdrawals change capital scale and shares without appearing as investment gains or losses. The series is valid only when the first persisted snapshot is an `initial` point with finite positive stored NAV, normally the `1.000000` account-creation baseline. Later trading points cannot replace a missing or invalid initial baseline. Invalid, missing, non-finite, or non-positive stored NAV is excluded and is never derived from `total_assets` or `initial_cash`; there is no total-assets-to-NAV fallback. `simple_asset_return` remains a separate scale-sensitive reference from latest total assets versus initial cash and does not feed total return, risk, or chart data. Overview cash and PnL fields still come from the latest persisted snapshot, including when that point's NAV is invalid. Drawdown and risk-adjusted metrics use the same valid NAV series so deposits and withdrawals do not appear as trading gains or losses.

`event_series` is the analytics cash-flow audit trail. It interleaves eligible snapshots and manual `deposit`/`withdrawal` ledger events in occurrence-time order, with a snapshot preceding a cash flow at the same timestamp and the record ID resolving otherwise equal events. Initial funding is excluded because the initial snapshot supplies the baseline. Each cash-flow event includes its ledger ID, `occurred_at`, signed amount, effective NAV, and share delta so consumers can reconcile return calculations with the cash ledger.

Round-trip metrics use full-position cycles. A cycle opens when an account's symbol quantity moves from zero to positive and closes when that symbol returns to zero. Partial exits update the open cycle but do not count as closed round trips.

### Legacy NAV Baseline And Repair State

The canonical repair reason is `legacy_ordering_uncertain`. It is an account-level
warning, not a synthetic snapshot. The closed PostgreSQL enum
`paper_account_migration_repair_reason` has that single label. The column
`paper_accounts.migration_repair_reason` is nullable, has no default, and stays
`NULL` for new accounts and for chronology-safe legacy accounts.

PostgreSQL storage startup serializes the snapshot-series upgrade with the
transaction advisory lock `paper_account_snapshots.nav_series` whenever
`paper_accounts` or `paper_account_snapshots` exists, including when
`paper_orders` is absent. Inside that lock it upgrades repair metadata even
when snapshots and orders are absent. Snapshot DDL, quality backfill,
valuation metadata, chronology classification, and baseline insertion remain
snapshot-gated. After quality backfill, PostgreSQL startup rejects duplicate
`trading` rows for the same account and `trade_date` rather than merging them,
then adds nullable `valuation_quality`/`valuation_details` and the partial unique
index `uq_paper_account_snapshots_account_trading`. The existing
`uq_paper_account_snapshots_account_initial` identity is unchanged.
Missing `paper_orders` does not create orders or snapshots. Concurrent
startups wait on the lock. Reruns are idempotent: they do not overwrite a
stored repair reason, do not rewrite valid snapshot financial fields, and do
not insert a second `initial` point.

Baseline eligibility is proof-based. The migration inserts one `initial`
NAV=`1.000000` point only when `initial_cash` is positive, `created_at` is
present, `migration_repair_reason` is null, and no `initial` point already
exists. Chronology is proven only from persisted timestamps and business
dates, never from IDs or insertion order. The inspected sources are snapshots
(`event_at`, `created_at`, `trade_date`; migration-inserted `initial` points
are excluded), cash ledger (`occurred_at`, `trade_date`), trades
(`trade_time`, `trade_date`), orders (`created_at`, `trade_date`), lots
(`buy_trade_date`), round trips (`open_trade_date`, `close_trade_date`),
matching runs (`trade_date`), and trade-validity checks (`trade_date`).
For snapshots, cash ledger, trades, and orders, an available timestamp at or
after `created_at` is chronology-safe and takes precedence over the paired
date. Date fallback is used only when every applicable timestamp on that row
is null. A timestamp before `created_at` remains uncertain. Date-only tables
and date fallback still require a date strictly after `created_at::date`; a
same-calendar-day or earlier date is unprovable. Null timestamps with no
proving date, missing expected temporal columns on a persisted source row,
and a null account `created_at` mark the account uncertain. Missing
tables are skipped. Matching runs with `account_id IS NULL` apply globally
only when `scope_key = 'all'` if that column exists; older matching-run tables
without `scope_key` still treat a null-account run as global.

When chronology cannot be proven, the migration sets
`migration_repair_reason=legacy_ordering_uncertain`, creates no baseline, and
leaves stored snapshot financial fields unchanged, including invalid NAV
points. Valid history is never rewritten to invent returns.

SQLite startup adds nullable `VARCHAR(40) migration_repair_reason` whenever
`paper_accounts` exists and the column is missing, even when snapshots and
orders are absent. Snapshot series metadata is upgraded only when
`paper_account_snapshots` exists. After series backfill, SQLite rejects
duplicate `trading` rows for the same account and `trade_date` rather than
merging them, then adds nullable `valuation_quality`/`valuation_details` and
the partial unique index `uq_paper_account_snapshots_account_trading`. SQLite
never classifies chronology and never inserts an initial baseline. Baseline
insertion is a PostgreSQL production startup behavior.

## Closed Position Cleanup

Fully sold paper positions are removed from active holdings after their round trip is recorded. Historical position lots, orders, trades, round trips, cash ledger entries, and snapshots remain available. Account-level cumulative realized PnL is preserved for future snapshots.

For databases created before this behavior, run the temporary cleanup during a maintenance window after deploying the account-level schema upgrade. Isolate matching writes and create a verified backup first. Preview all affected accounts and positions without writing:

```bash
uv run tools/cleanup_zero_paper_positions.py --dry-run
```

The command aborts without writes if a zero/negative aggregate position has frozen quantity or an account already has non-zero cumulative realized PnL. If the preview count is expected, run the command without `--dry-run` in the same maintenance window:

```bash
uv run tools/cleanup_zero_paper_positions.py
```

Record the reported account and position counts, confirm the Accounts Positions card no longer lists cleaned symbols, then remove the temporary command from the deployment branch.

## Matching Run Status Bootstrap

The `paper_matching_runs.status` column uses the PostgreSQL enum
`paper_matching_run_status` with these labels, in this order:
`running`, `completed`, `completed_with_warnings`, and `failed`. The bootstrap
command is explicit and must be run as an operator-controlled maintenance
procedure. API, Celery, Airflow, and `StorageDb` startup do not create or alter
the matching-run table or enum.

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
3. Run the bootstrap preflight without changing the database:

    ```bash
    uv run tools/bootstrap_paper_matching_run_status.py --dry-run --json
    ```

    Require exit code zero, `labels` equal to
    `['running', 'completed', 'completed_with_warnings', 'failed']`, and
    `index_verified` equal to `true` for an existing table. For a fresh
    database, preflight reports `table_exists: false` and does not create the
    table or enum. A non-empty unknown-status error must be resolved before the
    actual bootstrap. Do not bypass it by deleting or
    relabeling rows without an approved data decision.
4. Resolve invalid statuses while writes remain isolated. Inspect the affected
   rows, decide the correct lifecycle state from the matching and order audit
   trail, update only approved rows in a transaction, and rerun the dry-run
   until it succeeds. Do not invent a new enum label during this migration.
5. Run the actual bootstrap in the same isolated window:

    ```bash
    uv run tools/bootstrap_paper_matching_run_status.py --json
    ```

    Require exit code zero, `converted` to reflect whether conversion occurred,
    the four expected `labels`, and `index_verified: true`. The migration
    creates or validates the enum, converts the column, and verifies the unique
    active-run partial index on `(trade_date, scope_key)` for `status =
    'running'`. On a fresh database it creates `paper_matching_runs`, the enum,
    and the verified active-run index before matching writers start.
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

### Unified enum governance migration

The unified enum governance migration follows the enum evolution policy in
[`docs/database_design.md`](database_design.md). It is the only supported
production operator interface for the governed Paper Trading, Monitor, Forecast
SSF, and Storage schemas. Keep the maintenance record, verified backup, and
every command's JSON output together.

The governed types are the 18 Paper Trading types:
`paper_account_status`, `paper_fee_preset`, `paper_cash_event_type`,
`paper_order_side`, `paper_order_status`, `paper_trade_validity_status`,
`paper_market`, `paper_position_source`, `paper_round_trip_status`,
`paper_trade_validity_granularity`, `paper_pending_settlement_source`,
`paper_ledger_rebuild_status`, `paper_matching_run_status`,
`paper_etf_eligibility_status`, `paper_snapshot_point_type`,
`paper_snapshot_quality_status`, `paper_snapshot_valuation_quality`, and
`paper_account_migration_repair_reason`; the four
Monitor and Forecast SSF types: `monitor_market`, `monitor_frequency`,
`monitor_reset_mode`, and `forecast_ssf_candidate_state`; and the five Storage
types: `blackroom_market`, `blackroom_source`,
`daily_bar_diagnostic_adjust`, `daily_bar_diagnostic_classification`, and
`ssf_change_signal_status`. `monitor_market` is shared by
`stock_monitor_targets` and `forecast_ssf_candidates`; `monitor_frequency` and
`monitor_reset_mode` belong to `stock_monitor_targets`; and
`forecast_ssf_candidate_state` belongs to `forecast_ssf_candidates`.

Full exports create every managed type before dependent tables. Selected-table
exports create only the required types with duplicate-safe DDL, so a restore
does not replace an existing shared type. `pg_dump` preserves table-owned
defaults, indexes, foreign keys, and JSON checks. A full clean restore drops
dependent tables before the managed types.

Monitor `condition` remains JSON because it carries structured rule
configuration. Application write paths validate the complete conditional-rule
contract, including supported condition-specific direction and field rules.
For direct SQL, PostgreSQL enforces only the minimal stable boundary: the value
must be a JSON object with a supported `type`. Direct SQL does not replace
application validation for conditional rule details.

On a fresh PostgreSQL schema, the migration creates the governed Paper Trading
tables and the dependent operational `paper_account_snapshots` and
`paper_valuation_gaps` tables. A successful non-rollback migration also
restores either missing dependent operational table after converting or
verifying an otherwise complete governed schema. Normal PostgreSQL storage
startup intentionally does not create or convert those governed tables; use the
migration command for that explicit schema change. Startup may create the
snapshot series enum types and the additive
`paper_account_migration_repair_reason` type and add nullable
`paper_accounts.migration_repair_reason` whenever `paper_accounts` exists,
even when snapshots and orders are absent. When `paper_account_snapshots`
exists it also adds snapshot series columns on existing tables, backfills
`event_at`, marks legacy rows as `trading`, derives quality from stored NAV,
drops the old account/date unique constraint or standalone unique index,
classifies unprovable chronology as `legacy_ordering_uncertain`, and inserts
at most one `initial` NAV=1 point for each chronology-safe account whose
legacy `initial_cash` is positive. It does not convert other governed enum
columns, overwrite a stored repair reason, rewrite financial snapshot fields,
or create missing `paper_orders` or `paper_account_snapshots`. On SQLite,
startup adds nullable `VARCHAR(40) migration_repair_reason` whenever
`paper_accounts` exists, even when snapshots and orders are absent. Snapshot
series columns use SQLite-compatible DDL only when `paper_account_snapshots`
exists:
startup then backfills `event_at` from `created_at` and marks legacy rows as
`trading` so ORM listing by `event_at` works. SQLite does not insert an
initial baseline.

Selected-table clean export is unsupported. Selected-table clean import refuses
to run when an unselected table has a foreign key referencing the selected
table. This prevents the restore from silently dropping a constraint that the
selected-table dump cannot recreate. Use a full business-database clean restore
when the required tables are managed together, or use a separately reviewed
recovery procedure.

#### Preconditions

- Record database, schema, deployment revision, maintenance owner, and start
  time.
- Stop API/CLI automation, Airflow scheduling and workers, Celery workers, and
  all other business writers; leave PostgreSQL running.
- Set the source connection values and the immutable backup path in the
  maintenance record, then create the full export:

  ```bash
  export DB_SERVICE=db
  export PROD_DB=quant
  export PROD_SCHEMA=public
  export DB_USER=quant
  export BACKUP_FILE="./backups/${PROD_DB}_pre_enum_$(date +%Y%m%d_%H%M%S).sql.gz"
  bash tools/db_export.sh --service "$DB_SERVICE" --db "$PROD_DB" --user "$DB_USER" \
    --schema "$PROD_SCHEMA" --out "$BACKUP_FILE"
  test -s "$BACKUP_FILE"
  gzip -t "$BACKUP_FILE"
  ```

- Provision an empty, isolated restore database before the maintenance window.
  It must not be the production database and must use the same schema name as
  `PROD_SCHEMA`: the plain SQL dump contains schema-qualified objects and
  `db_import.sh` does not rewrite schemas. Record the target database identity,
  schema, provisioning approval, backup checksum, export timestamp, import exit
  status, and catalog-query transcript. Only the isolated target may use
  `--clean`:

  ```bash
  export ISOLATED_DB=quant_enum_restore_20260809
  export ISOLATED_SCHEMA="$PROD_SCHEMA"
  bash tools/db_import.sh --clean --service "$DB_SERVICE" --db "$ISOLATED_DB" \
    --user "$DB_USER" --schema "$ISOLATED_SCHEMA" --in "$BACKUP_FILE"
  ```

  Record the export command's `Wrote:` path, `test -s` and `gzip -t` exit
  statuses, the import command's `[db_import] Done.` output, and its zero exit
  status as the restore proof. Inspect the isolated target before production DDL;
  do not use these commands to create or drop the target. Its isolated
  provisioning is an operator prerequisite.

#### Preflight and Migration

```bash
uv run tools/migrate_enums.py --dry-run --json
uv run tools/migrate_enums.py --json
```

Run only the dry run first. Retain and review its JSON document; do not run the
live command while any group, column, check, or dependency is non-ready. Resolve
unknown legacy values without coercion or relabeling until an approved data
decision exists. After every item is ready, run the live command and retain its
JSON document.

#### Independent Verification and Smoke

Verify enum labels, column types, defaults, indexes, and JSON checks through
PostgreSQL catalog queries independent of the command output. The following
queries are read-only and use the repository's Docker Compose access pattern.
They target the migrated production database after the live command; set the
same `DB_SERVICE`, `PROD_DB`, `PROD_SCHEMA`, and `DB_USER` values recorded
above. Each query must return **zero rows**. Save its output and exit status in
the maintenance record; any row is a mismatch and blocks restart.

```bash
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$PROD_DB" \
  -v "schema=$PROD_SCHEMA" -P pager=off <<'SQL'
WITH expected(type_name, labels) AS (
  VALUES
    ('paper_account_status', ARRAY['active','disabled']),
    ('paper_fee_preset', ARRAY['a_share']),
    ('paper_cash_event_type', ARRAY['deposit','withdrawal','freeze','release','trade','fee']),
    ('paper_order_side', ARRAY['buy','sell']),
    ('paper_order_status', ARRAY['new','accepted','partially_filled','filled','cancelled','rejected']),
    ('paper_trade_validity_status', ARRAY['valid','suspicious','invalid','unchecked']),
    ('paper_market', ARRAY['a_share','hk_connect','etf']),
    ('paper_position_source', ARRAY['trade','imported']),
    ('paper_round_trip_status', ARRAY['open','closed']),
    ('paper_trade_validity_granularity', ARRAY['daily']),
    ('paper_pending_settlement_source', ARRAY['hk_sell']),
    ('paper_ledger_rebuild_status', ARRAY['completed']),
    ('paper_matching_run_status', ARRAY['running','completed','completed_with_warnings','failed']),
    ('paper_etf_eligibility_status', ARRAY['unknown','supported','money_market','disabled']),
    ('paper_snapshot_point_type', ARRAY['initial','trading']),
    ('paper_snapshot_quality_status', ARRAY['valid','invalid']),
    ('paper_snapshot_valuation_quality', ARRAY['current','stale_suspended']),
    ('paper_account_migration_repair_reason', ARRAY['legacy_ordering_uncertain']),
    ('monitor_market', ARRAY['A','HK','ETF']),
    ('monitor_frequency', ARRAY['daily','intraday']),
    ('monitor_reset_mode', ARRAY['auto','manual']),
    ('forecast_ssf_candidate_state', ARRAY['eligible','ineligible','deferred','paused','blackroom','delisted_or_unlisted']),
    ('blackroom_market', ARRAY['A','HK','ETF']),
    ('blackroom_source', ARRAY['manual','shareholder_selling','shareholder_reduction']),
    ('daily_bar_diagnostic_adjust', ARRAY['bfq','qfq','hfq']),
    ('daily_bar_diagnostic_classification', ARRAY['missing_market_data','missing_exact_date','provider_error','downloaded','resolved']),
    ('ssf_change_signal_status', ARRAY['signal','no_signal'])
), observed AS (
  SELECT t.typname AS type_name, array_agg(e.enumlabel ORDER BY e.enumsortorder) AS labels
  FROM pg_type t
  JOIN pg_namespace n ON n.oid = t.typnamespace
  LEFT JOIN pg_enum e ON e.enumtypid = t.oid
  WHERE n.nspname = :'schema'
  GROUP BY t.typname
)
SELECT e.type_name, e.labels AS expected_labels, o.labels AS observed_labels
FROM expected e LEFT JOIN observed o USING (type_name)
WHERE o.labels IS DISTINCT FROM e.labels
ORDER BY e.type_name;
SQL
```

Expected result: zero rows. This proves every governed type has exactly its
documented labels in documented order; it includes readable export labels such
as `bfq`, `downloaded`, `signal`, and `increase`'s JSON-check boundary.

```bash
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$PROD_DB" \
  -v "schema=$PROD_SCHEMA" -P pager=off <<'SQL'
WITH expected(table_name, column_name, type_name) AS (
  VALUES
    ('paper_accounts','status','paper_account_status'), ('paper_accounts','fee_preset','paper_fee_preset'),
    ('paper_cash_ledger','event_type','paper_cash_event_type'), ('paper_orders','side','paper_order_side'),
    ('paper_trades','side','paper_order_side'), ('paper_trade_validity_checks','side','paper_order_side'),
    ('paper_orders','status','paper_order_status'), ('paper_orders','validity_status','paper_trade_validity_status'),
    ('paper_trade_validity_checks','status','paper_trade_validity_status'), ('paper_orders','market','paper_market'),
    ('paper_positions','market','paper_market'), ('paper_position_lots','market','paper_market'),
    ('paper_trades','market','paper_market'), ('paper_trade_validity_checks','market','paper_market'),
    ('paper_positions','source','paper_position_source'), ('paper_position_lots','source','paper_position_source'),
    ('paper_position_round_trips','status','paper_round_trip_status'),
    ('paper_trade_validity_checks','data_granularity','paper_trade_validity_granularity'),
    ('paper_pending_settlement','source','paper_pending_settlement_source'),
    ('paper_ledger_rebuilds','status','paper_ledger_rebuild_status'), ('paper_matching_runs','status','paper_matching_run_status'),
    ('paper_etf_eligibility','status','paper_etf_eligibility_status'),
    ('paper_account_snapshots','point_type','paper_snapshot_point_type'),
    ('paper_account_snapshots','quality_status','paper_snapshot_quality_status'),
    ('paper_account_snapshots','valuation_quality','paper_snapshot_valuation_quality'),
    ('paper_accounts','migration_repair_reason','paper_account_migration_repair_reason'),
    ('stock_monitor_targets','market','monitor_market'), ('forecast_ssf_candidates','market','monitor_market'),
    ('stock_monitor_targets','frequency','monitor_frequency'), ('stock_monitor_targets','reset_mode','monitor_reset_mode'),
    ('forecast_ssf_candidates','state','forecast_ssf_candidate_state'), ('blackroom_records','market','blackroom_market'),
    ('blackroom_records','source','blackroom_source'), ('daily_bar_diagnostics','adjust','daily_bar_diagnostic_adjust'),
    ('daily_bar_diagnostics','classification','daily_bar_diagnostic_classification'), ('ssf_change_signals','status','ssf_change_signal_status')
), observed AS (
  SELECT c.relname AS table_name, a.attname AS column_name, t.typname AS type_name
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace JOIN pg_type t ON t.oid = a.atttypid
  WHERE n.nspname = :'schema' AND a.attnum > 0 AND NOT a.attisdropped
)
SELECT e.*, o.type_name AS observed_type
FROM expected e LEFT JOIN observed o USING (table_name, column_name)
WHERE o.type_name IS DISTINCT FROM e.type_name
ORDER BY e.table_name, e.column_name;
SQL
```

Expected result: zero rows. This proves all 35 governed columns use their
managed enum types.

```bash
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$PROD_DB" \
  -v "schema=$PROD_SCHEMA" -P pager=off <<'SQL'
WITH expected AS (
  SELECT * FROM (VALUES
    ('paper_accounts','status', '''active''::paper_account_status'),
    ('paper_accounts','fee_preset', '''a_share''::paper_fee_preset'),
    ('paper_orders','market', '''a_share''::paper_market'),
    ('paper_positions','market', '''a_share''::paper_market'),
    ('paper_position_lots','market', '''a_share''::paper_market'),
    ('paper_trades','market', '''a_share''::paper_market'),
    ('paper_trade_validity_checks','market', '''a_share''::paper_market'),
    ('paper_positions','source', '''trade''::paper_position_source'),
    ('paper_position_lots','source', '''trade''::paper_position_source'),
    ('paper_position_round_trips','status', '''open''::paper_round_trip_status'),
    ('paper_trade_validity_checks','data_granularity', '''daily''::paper_trade_validity_granularity'),
    ('stock_monitor_targets','market', '''A''::monitor_market'),
    ('forecast_ssf_candidates','market', '''A''::monitor_market'),
    ('stock_monitor_targets','frequency', '''daily''::monitor_frequency'),
    ('stock_monitor_targets','reset_mode', '''auto''::monitor_reset_mode'),
    ('blackroom_records','market', '''A''::blackroom_market'),
    ('blackroom_records','source', '''manual''::blackroom_source'),
    ('daily_bar_diagnostics','adjust', NULL),
    ('daily_bar_diagnostics','classification', NULL),
    ('ssf_change_signals','status', '''signal''::ssf_change_signal_status'),
    ('paper_cash_ledger','event_type', NULL),
    ('paper_orders','side', NULL), ('paper_trades','side', NULL),
    ('paper_trade_validity_checks','side', NULL), ('paper_orders','status', NULL),
    ('paper_orders','validity_status', NULL), ('paper_trade_validity_checks','status', NULL),
    ('paper_pending_settlement','source', NULL), ('paper_ledger_rebuilds','status', NULL),
    ('paper_matching_runs','status', NULL), ('forecast_ssf_candidates','state', NULL),
    ('paper_accounts','migration_repair_reason', NULL)
  ) AS v(table_name, column_name, default_expression)
), observed AS (
  SELECT c.relname AS table_name, a.attname AS column_name, pg_get_expr(d.adbin, d.adrelid) AS default_expression
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
  WHERE n.nspname = :'schema' AND a.attnum > 0 AND NOT a.attisdropped
)
SELECT e.*, o.default_expression AS observed_default
FROM expected e LEFT JOIN observed o USING (table_name, column_name)
WHERE coalesce(replace(replace(lower(o.default_expression), '(', ''), ')', ''), '')
  IS DISTINCT FROM coalesce(lower(e.default_expression), '')
ORDER BY e.table_name, e.column_name;
SQL
```

Expected result: zero rows. This verifies every governed enum default and that
every other governed enum column has no unexpected default.

```bash
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$PROD_DB" \
  -v "schema=$PROD_SCHEMA" -P pager=off <<'SQL'
WITH expected(name) AS (
  VALUES ('ix_paper_orders_status'), ('ix_paper_orders_validity_status'),
    ('ix_paper_trade_validity_checks_status'), ('ix_paper_orders_market'),
    ('ix_paper_positions_market'), ('ix_paper_position_lots_market'), ('ix_paper_trades_market'),
    ('ix_paper_trade_validity_checks_market'), ('ix_paper_position_round_trips_status'),
    ('ix_paper_ledger_rebuilds_status'), ('uq_matching_active_scope'),
    ('ix_stock_monitor_targets_market'), ('ix_forecast_ssf_candidates_market'),
    ('ix_stock_monitor_targets_frequency'), ('ix_stock_monitor_targets_reset_mode'),
    ('ix_forecast_ssf_candidates_state')
), observed AS (
  SELECT c.relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = :'schema' AND c.relkind = 'i'
)
SELECT e.name AS missing_index FROM expected e LEFT JOIN observed o USING (name) WHERE o.name IS NULL
UNION ALL
SELECT 'uq_matching_active_scope predicate=' || coalesce(pg_get_expr(i.indpred, i.indrelid), '<missing>')
FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :'schema' AND c.relname = 'uq_matching_active_scope'
  AND (NOT i.indisunique OR pg_get_expr(i.indpred, i.indrelid) !~* 'status\s*=\s*''running''\s*::\s*paper_matching_run_status');
SQL
```

Expected result: zero rows. This proves all managed indexes exist and the
active matching-run index remains unique with the enum-typed `running`
predicate.

```bash
docker compose exec -T "$DB_SERVICE" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$PROD_DB" \
  -v "schema=$PROD_SCHEMA" -P pager=off <<'SQL'
WITH expected(table_name, constraint_name, definition) AS (
  VALUES
    ('stock_monitor_targets','ck_stock_monitor_targets_condition_type',
     $condition$CHECK (((jsonb_typeof(condition) = 'object'::text) AND (condition ? 'type'::text) AND ((condition ->> 'type'::text) IS NOT NULL) AND ((condition ->> 'type'::text) = ANY (ARRAY['price_threshold'::text, 'price_cross_ma'::text, 'close_cross_ma'::text, 'ma_cross'::text, 'change_pct'::text, 'rsi'::text]))))$condition$),
    ('daily_bar_diagnostics','ck_daily_bar_diagnostics_provider_outcome_status',
     $provider$CHECK (((jsonb_typeof((provider_outcomes)::jsonb) = 'array'::text) AND (NOT jsonb_path_exists((provider_outcomes)::jsonb, '$[*]?(((@.type() != "object" || !(exists (@."status"))) || @."status".type() != "string") || !((@."status" == "downloaded" || @."status" == "empty") || @."status" == "error"))'::jsonpath))))$provider$),
    ('ssf_change_signals','ck_ssf_change_signals_event_types',
     $ssf$CHECK (((jsonb_typeof((event_types)::jsonb) = 'array'::text) AND (NOT jsonb_path_exists((event_types)::jsonb, '$[*]?(@.type() != "string" || !(((@ == "increase" || @ == "decrease") || @ == "new_entry") || @ == "exit"))'::jsonpath))))$ssf$)
), observed AS (
  SELECT t.relname AS table_name, c.conname AS constraint_name,
    replace(replace(regexp_replace(lower(pg_get_constraintdef(c.oid)), '[[:space:]]+', '', 'g'), '::jsonb', ''), '::text', '') AS normalized_definition
  FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
  WHERE n.nspname = :'schema' AND c.contype = 'c'
), normalized_expected AS (
  SELECT table_name, constraint_name,
    replace(replace(regexp_replace(lower(definition), '[[:space:]]+', '', 'g'), '::jsonb', ''), '::text', '') AS normalized_definition
  FROM expected
)
SELECT e.*, o.normalized_definition AS observed_definition
FROM normalized_expected e LEFT JOIN observed o USING (table_name, constraint_name)
WHERE o.normalized_definition IS DISTINCT FROM e.normalized_definition
ORDER BY e.table_name, e.constraint_name;
SQL
```

Expected result: zero rows. This proves all three managed JSON checks exist and
their full normalized PostgreSQL catalog definitions match the documented
expressions. Normalization removes whitespace and only PostgreSQL's
presentation-only `::jsonb` and `::text` casts; it preserves parentheses,
Boolean grouping, and operators. Do not restart on a conflicting definition.

Run
`uv run pytest test/storage/test_enum_governance_smoke.py -v` with
`TEST_POSTGRESQL_URL` targeting an isolated migrated database. Resume compatible
services only after this gate passes.

The label contract crosses API responses, CLI task output, Airflow task output,
Celery task output, frontend consumers, and database exports. Repository tests
cover the export/import contract; operators must observe canonical readable
labels in the API, CLI, Airflow, Celery, and frontend runtime paths because this
repository does not claim runtime verification for those consumers.

Restart in this order: keep the database running; start the application/API;
start one worker class at a time and observe canonical labels in its output;
confirm canonical labels in API and CLI task output and in an export; then
return Airflow schedules to normal. Do not resume a consumer that cannot read
every label in the migrated database.

#### Schema Rollback

```bash
uv run tools/migrate_enums.py --rollback --json
```

Keep writers stopped. This converts columns back to documented varchar types and
removes managed types and checks after dependency verification. It is schema-only
and non-destructive: it does not restore lost data or replace a verified backup
restore. Never drop governed tables to force rollback and never rely on
application startup to migrate schema. Retain the rollback JSON document and
restart only versions compatible with the independently verified schema.

### Future label compatibility

Enum labels are a compatibility contract across the database, SQLAlchemy
models, API responses, CLI output, Celery tasks, Airflow DAGs, and frontend
consumers. Additive labels require a separately reviewed migration and a
compatibility pass across every consumer. Existing labels must never be
renamed or removed in place; PostgreSQL enum ordering and persisted values are
part of the contract. A service must be able to read all labels present in the
database before that label is introduced in production. Treat unknown labels
as a deployment/schema mismatch, not as a value to coerce silently.

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
