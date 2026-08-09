#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  docker compose rm -sfv test_db >/dev/null 2>&1 || true
}

trap cleanup EXIT

export TEST_POSTGRESQL_URL="postgresql://quant:quant@localhost:5433/quant"
docker compose up -d --wait test_db
uv run pytest test "$@"
