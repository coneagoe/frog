#!/usr/bin/env bash
set -euo pipefail

# Create a dedicated database for Airflow metadata/results.
# NOTE: scripts in /docker-entrypoint-initdb.d run ONLY when the data dir is empty
# (i.e., first initialization of the volume).

DB_NAME="${AIRFLOW_DB_NAME:-airflow}"

if [[ ! "${DB_NAME}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || [[ ${#DB_NAME} -gt 63 ]]; then
  echo "Invalid database name in AIRFLOW_DB_NAME: '${DB_NAME}'. It must start with a letter or underscore, contain only letters, digits, and underscores, and be at most 63 characters long." >&2
  exit 1
fi

if ! psql_output=$(psql \
    -v dbname="${DB_NAME}" \
    -tAc "SELECT 1 FROM pg_database WHERE datname = :'dbname'" \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" 2>&1); then
  echo "${psql_output}" >&2
  exit 1
fi

exists="${psql_output}"
if [[ "${exists}" != "1" ]]; then
  createdb --username "${POSTGRES_USER}" --owner "${POSTGRES_USER}" -- "${DB_NAME}"
fi
