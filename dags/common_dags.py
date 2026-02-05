"""Common utilities for Airflow DAGs."""

import os
import sys
from datetime import datetime, timedelta
from typing import Final
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


def parse_alert_emails(raw: str) -> list[str]:
    """Parse alert emails from a string, supporting both comma and semicolon separators."""
    return [
        email.strip() for email in raw.replace(";", ",").split(",") if email.strip()
    ]


def get_alert_emails() -> list[str]:
    """Get alert emails from environment variables."""
    raw = os.environ.get("ALERT_EMAILS") or os.environ.get("MAIL_RECEIVERS") or ""
    return parse_alert_emails(raw)


def get_default_args() -> dict:
    """Get default arguments for DAG configuration."""
    alert_emails = get_alert_emails()
    return {
        "owner": "frog",
        "depends_on_past": False,
        "start_date": datetime(2025, 1, 1, tzinfo=LOCAL_TZ),
        "email": alert_emails,
        "email_on_failure": bool(alert_emails),
        "email_on_retry": False,
        "email_on_success": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    }


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
    2. Airflow Variable DOWNLOAD_PROCESS_COUNT (read at runtime)
    3. Default value (4)
    """
    env_value = os.getenv("DOWNLOAD_PROCESS_COUNT")
    parsed = parse_int(env_value)
    if parsed is not None:
        return max(1, parsed)

    try:
        from airflow.models import Variable

        var_value = Variable.get("DOWNLOAD_PROCESS_COUNT", default_var=None)
    except Exception:
        var_value = None

    parsed = parse_int(var_value)
    if parsed is not None:
        return max(1, parsed)

    return DEFAULT_PARTITION_COUNT


def get_partitioned_ids(
    stock_ids: list[str], partition_id: int, partition_count: int
) -> list[str]:
    """Get a subset of stock IDs for a specific partition.

    Args:
        stock_ids: List of all stock IDs
        partition_id: The partition identifier (0-based)
        partition_count: Total number of partitions

    Returns:
        List of stock IDs assigned to this partition
    """
    return [
        sid
        for idx, sid in enumerate(stock_ids)
        if (idx % partition_count) == partition_id
    ]
