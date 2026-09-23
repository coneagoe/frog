"""Common utilities for Airflow DAGs."""

import os
import sys
from datetime import datetime, timedelta
from typing import Callable, Final, TypeVar
from zoneinfo import ZoneInfo

# Ensure project root is on sys.path
# Airflow container mounts code at /opt/airflow/frog
project_root = os.environ.get("FROG_PROJECT_ROOT") or "/opt/airflow/frog"
if os.path.isdir(project_root):
    sys.path.insert(0, project_root)
else:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOCAL_TZ: Final = ZoneInfo("Asia/Shanghai")
MAX_PARTITIONS: Final = 16
DEFAULT_PARTITION_COUNT: Final = 4
ItemT = TypeVar("ItemT")
OutcomeT = TypeVar("OutcomeT")


def parse_alert_emails(raw: str) -> list[str]:
    """Parse alert emails from a string, supporting both comma and semicolon separators."""
    return [email.strip() for email in raw.replace(";", ",").split(",") if email.strip()]


def get_alert_emails() -> list[str]:
    """Get alert emails from environment variables."""
    raw = os.environ.get("ALERT_EMAILS") or os.environ.get("MAIL_RECEIVERS") or ""
    return parse_alert_emails(raw)


def get_default_args() -> dict:
    """Get default arguments for DAG configuration."""
    alert_emails = get_alert_emails()
    default_args = {
        "owner": "frog",
        "depends_on_past": False,
        "start_date": datetime(2025, 1, 1, tzinfo=LOCAL_TZ),
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }
    if alert_emails:
        from airflow.providers.smtp.notifications.smtp import SmtpNotifier

        default_args["on_failure_callback"] = [
            SmtpNotifier(
                to=alert_emails,
                subject="Frog Airflow task failed",
                html_content="Task {{ ti.task_id }} failed in DAG {{ ti.dag_id }}.",
            )
        ]
    return default_args


def parse_int(value: str | None) -> int | None:
    """Parse a string to an integer, returning None if parsing fails."""
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def get_partition_count() -> int:
    """Get the partition count for Airflow tasks.

    Priority:
    1. Environment variable DOWNLOAD_PROCESS_COUNT
    2. Default value (4)
    """
    env_value = os.getenv("DOWNLOAD_PROCESS_COUNT")
    parsed = parse_int(env_value)
    if parsed is not None:
        return max(1, parsed)

    return DEFAULT_PARTITION_COUNT


def get_partition_ids(partition_count: int | None = None) -> range:
    """Return the active partition ids derived from the partition count."""
    if partition_count is None:
        partition_count = get_partition_count()
    return range(max(1, partition_count))


def get_partitioned_ids(items: list[ItemT], partition_id: int, partition_count: int) -> list[ItemT]:
    """Get a subset of items for a specific partition.

    Args:
        items: List of all items
        partition_id: The partition identifier (0-based)
        partition_count: Total number of partitions

    Returns:
        List of items assigned to this partition
    """
    return [item for idx, item in enumerate(items) if (idx % partition_count) == partition_id]


def run_partition_items(
    items: list[ItemT],
    partition_index: int,
    partition_count: int,
    action: Callable[[ItemT], OutcomeT],
    is_failure: Callable[[OutcomeT], bool],
    on_progress: Callable[[ItemT, int, int], None] | None = None,
) -> tuple[list[ItemT], list[tuple[ItemT, OutcomeT]]]:
    """Run an action for this partition and return items with failed outcomes.

    Items are selected in their input order using round-robin partitioning, so
    both the selected items and failure results preserve that order. Exceptions
    from ``action``, ``is_failure``, or ``on_progress`` are not caught.

    The optional progress callback is called after each item's action has
    completed and its outcome has been classified. It receives the item, the
    one-based number of completed selected items, and the total number of
    selected items.
    """
    selected = get_partitioned_ids(items, partition_index, partition_count)
    failures: list[tuple[ItemT, OutcomeT]] = []
    total_selected = len(selected)

    for completed, item in enumerate(selected, start=1):
        outcome = action(item)
        if is_failure(outcome):
            failures.append((item, outcome))
        if on_progress is not None:
            on_progress(item, completed, total_selected)

    return selected, failures
