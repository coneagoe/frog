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
| `QG_PROXY_KEY` / `QG_PROXY_PWD` | (empty) | Qingguo proxy credentials for HTTP proxy rotation |
| `DOWNLOAD_PROCESS_COUNT` | `4` | DAG partition fan-out count |

See `config.ini` for additional download provider ordering and backtest settings.

## Factor Research

Local factor-analysis workflows use the research dependency group:

- `uv sync --group research`

If you also need the normal dev tools in the same environment, use:

- `uv sync --group dev --group research`

Business runtime images do not include the research group.
