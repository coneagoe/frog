# frog

## Pre-commit

Install the git hook once:

- uv:
	- `uv sync --group dev`
	- `uv run pre-commit install`

- Or plain pip:
	- `python -m pip install pre-commit`
	- `pre-commit install`

Notes:

- On `git commit`, pre-commit runs only on staged files (the git index).
- `uv run pre-commit run --all-files` runs only on git-tracked files.
- The trailing whitespace fixer excludes `*.csv` by default to avoid accidental data changes.

## Line endings (LF)

This repo enforces LF via `.gitattributes`. If you need a one-time normalization (e.g. after changing `.gitattributes` or after checkout on Windows), run:

- `git add --renormalize .`

## Testing

Run the full test suite with:

```bash
tools/run_tests.sh
```

The runner starts the isolated `test_db` service, supplies `TEST_POSTGRESQL_URL`
only to the test process, and removes the service and its data after pytest exits.

## Configuration

Create a `.env` file in the project root with the following required variables:

| Variable | Description |
|---|---|
| `TUSHARE_TOKEN` | TuShare API token |
| `PAPER_TRADING_API_TOKEN` | Paper trading API auth token |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_MAIL_FROM` | Email alerts SMTP config |
| `ALERT_EMAILS` | Comma-separated alert recipients |

Optional variables:

| Variable | Default | Description |
|---|---|---|
| `PROXY_PROVIDER` | `auto` | `auto` tries local ProxyPool then Qingguo; `proxy_pool` disables fallback; `qingguo` bypasses the local pool. |
| `PROXY_POOL_URL` | `http://proxy_pool:5010` | Internal ProxyPool API address; do not expose it publicly. |
| `QG_PROXY_KEY` / `QG_PROXY_PWD` | (empty) | Qingguo fallback credentials required for `auto` fallback and `qingguo` mode. |
| `DOWNLOAD_PROCESS_COUNT` | `4` | DAG partition fan-out count |

See `config.ini` for additional download provider ordering and backtest settings.

ProxyPool is optional. Start it and verify its availability with:

```bash
docker compose up -d proxy_redis proxy_pool
docker compose ps proxy_redis proxy_pool
docker compose exec proxy_pool sh -c 'wget -qO- http://127.0.0.1:5010/count/'
uv run tools/test_proxy.py
```

Neither ProxyPool port is host-published; keep `proxy_pool` and `proxy_redis` on
the private Compose network. Public proxies are untrusted and are used only for
AkShare retry recovery. To roll back to Qingguo, set `PROXY_PROVIDER=qingguo` and
restart the downloading worker/scheduler.

## Factor Research

Local factor-analysis workflows use the research dependency group:

- `uv sync --group research`

If you also need the normal dev tools in the same environment, use:

- `uv sync --group dev --group research`

Business runtime images do not include the research group.
