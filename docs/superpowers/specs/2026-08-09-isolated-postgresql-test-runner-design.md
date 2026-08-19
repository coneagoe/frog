# Isolated PostgreSQL Test Runner Design

## Goal

Provide a repository-owned test command that runs the full pytest suite against
an isolated PostgreSQL service. The command must configure the test database
URL itself, must not depend on `.env`, and must remove the test database when
the test process exits.

## Architecture

Add a `test_db` service to `docker-compose.yml`. It uses the existing
TimescaleDB image and the same non-secret test credentials as the local
development database, but has a separate host port and an anonymous data
volume. It has the same readiness health check as `db` and no dependency on
application services or `.env` values.

Add `tools/run_tests.sh` as the canonical full-suite entry point. It will:

1. Start `test_db` with Docker Compose and wait for its health check.
2. Export a fixed `TEST_POSTGRESQL_URL` that targets `test_db` through its
   dedicated host port.
3. Run `uv run pytest test`, forwarding any command-line arguments.
4. Register a shell trap before starting the service that removes `test_db`
   and its anonymous volume on success, test failure, interruption, or shell
   error.

The script owns only `test_db`; it never starts, stops, or removes the
development `db` service. `docker compose rm -sfv test_db` is used for cleanup
so the container and test data are discarded without changing unrelated
services or volumes.

## Error Handling

Docker Compose start or health-check failures end the command with a non-zero
status. The cleanup trap still runs when a container was created. Pytest's exit
status is preserved after cleanup, so test failures remain visible to CI and
callers.

The test URL is exported only by the runner process. Production and developer
environment files remain free of test database configuration.

## Verification

Automated coverage will verify that the runner exports the expected URL,
forwards pytest arguments, waits for the service, and schedules cleanup for all
exit paths by mocking Docker Compose and pytest commands. A manual run of
`tools/run_tests.sh` will verify PostgreSQL integration tests execute rather
than skip, and `docker compose ps test_db` will show no retained test service
after the command exits.
