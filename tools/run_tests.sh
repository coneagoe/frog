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

find_available_port() {
  local port=5433
  while ((port <= 65535)); do
    if if command -v nc >/dev/null 2>&1; then
      nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    else
      (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
    fi; then
      port=$((port + 1))
    else
      printf '%s\n' "$port"
      return 0
    fi
  done
  printf 'No available loopback port in range 5433-65535\n' >&2
  return 1
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  trap cleanup EXIT
  export FROG_ENV="${FROG_ENV-test}"
  export PAPER_TRADING_JWT_SECRET="${PAPER_TRADING_JWT_SECRET-test-jwt-secret-for-runner-defaults-1234567890}"
  export PAPER_TRADING_COOKIE_SECURE="${PAPER_TRADING_COOKIE_SECURE-false}"
  TEST_DB_HOST_PORT="$(find_available_port)"
  export TEST_DB_HOST_PORT
  compose up -d --wait test_db
  TEST_POSTGRESQL_URL="postgresql://quant:quant@127.0.0.1:${TEST_DB_HOST_PORT}/quant" \
    uv run pytest test "$@"
fi
