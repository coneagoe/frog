# Dynamic Test Database Port Design

## Goal

Allow `tools/run_tests.sh` to start the isolated Docker PostgreSQL test database when the default host port is already in use.

## Design

The `test_db` container continues to listen on PostgreSQL's internal port `5432`. Before invoking Docker Compose, `tools/run_tests.sh` selects an available loopback host port, beginning at `5433`. It passes that value as `TEST_DB_HOST_PORT` to Compose, which maps `127.0.0.1:${TEST_DB_HOST_PORT}:5432`, and uses the identical port in `TEST_POSTGRESQL_URL` for pytest.

The compose file supplies a default `TEST_DB_HOST_PORT` of `5433` so direct Compose usage remains compatible. The runner owns dynamic selection and cleanup continues to remove only `test_db`.

## Verification

`test/tools/test_run_tests.py` will simulate port probing, assert that Compose receives the chosen override, and assert pytest receives the corresponding connection URL. The runner test and a real PostgreSQL-backed test invocation establish both the shell contract and Docker boundary.
