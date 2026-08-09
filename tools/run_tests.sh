#!/usr/bin/env bash
set -euo pipefail

compose() {
  env -u TEST_POSTGRESQL_URL \
    SMTP_HOST=placeholder \
    SMTP_PORT=25 \
    SMTP_USER=placeholder \
    SMTP_PASSWORD=placeholder \
    SMTP_MAIL_FROM=placeholder@example.invalid \
    ALERT_EMAILS=placeholder@example.invalid \
    TUSHARE_TOKEN=placeholder \
    PAPER_TRADING_API_TOKEN=placeholder \
    docker compose "$@"
}

cleanup() {
  compose rm -sfv test_db >/dev/null 2>&1 || true
}

trap cleanup EXIT

compose up -d --wait test_db
TEST_POSTGRESQL_URL="postgresql://quant:quant@127.0.0.1:5433/quant" \
  uv run pytest test "$@"
