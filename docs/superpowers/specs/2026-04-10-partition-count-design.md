# Partition Count Design

## Problem

The codebase currently derives partition count from multiple places and still applies a DAG-level `MAX_PARTITIONS` cap. This makes the effective partition count less obvious than the configured `DOWNLOAD_PROCESS_COUNT` value.

## Decision

Use `DOWNLOAD_PROCESS_COUNT` as the single source of truth for partition count.

## Design

### Configuration source

- `DOWNLOAD_PROCESS_COUNT` is the only configuration input for partition count.
- `docker-compose.yml`, `entrypoint-common.sh`, and `conf/global_settings.py` may continue to set or inject `DOWNLOAD_PROCESS_COUNT`.
- Partition-aware runtime code must not introduce a second configuration source.

### Runtime read path

- `dags/common_dags.py:get_partition_count()` remains the shared read path for DAG code.
- The function reads `DOWNLOAD_PROCESS_COUNT`, parses it as an integer, and applies the existing lower bound protection (`max(1, parsed)`).
- Invalid or missing values continue to fall back to the existing default of `4`.

### Partition limit handling

- Remove `MAX_PARTITIONS` as a separate cap.
- DAGs should use the value returned by `get_partition_count()` directly instead of applying `min(..., MAX_PARTITIONS)`.
- As a result, the effective partition count now matches `DOWNLOAD_PROCESS_COUNT` exactly after parsing and lower-bound normalization.

## Error handling

- Non-integer `DOWNLOAD_PROCESS_COUNT` values fall back to the existing default (`4`).
- Values lower than `1` normalize to `1`.

## Testing

- Update tests or add focused coverage for `get_partition_count()` if relevant test coverage already exists nearby.
- Verify affected DAG code no longer applies an extra partition cap beyond `DOWNLOAD_PROCESS_COUNT`.
