import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PARTITION_DAG_SPECS = [
    (
        ROOT / "dags/download_stock_history_daily.py",
        r"for\s+_pid\s+in\s+get_partition_ids\s*\(\s*\)\s*:",
        1,
    ),
    (
        ROOT / "dags/download_stock_history_qfq_weekend.py",
        r"for\s+_pid\s+in\s+get_partition_ids\s*\(\s*\)\s*:",
        1,
    ),
    (
        ROOT / "dags/download_stk_holdernumber_weekly.py",
        r"for\s+_pid\s+in\s+get_partition_ids\s*\(\s*\)\s*:",
        1,
    ),
    (
        ROOT / "dags/download_etf_daily.py",
        r"for\s+_pid\s+in\s+get_partition_ids\s*\(\s*\)\s*:",
        1,
    ),
    (
        ROOT / "dags/download_hk_ggt_history_daily.py",
        r"partition_tasks\s*=\s*\[\s*PythonOperator[\s\S]*?for\s+pid\s+in\s+get_partition_ids\s*\(\s*\)\s*\]",
        2,
    ),
]


def read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("path", "task_pattern", "expected_get_partition_count_calls"),
    PARTITION_DAG_SPECS,
)
def test_partition_dag_sources_follow_shared_partition_contract(
    path: Path, task_pattern: str, expected_get_partition_count_calls: int
):
    source = read_source(path)

    assert not re.search(r"\bMAX_PARTITIONS\b", source)
    assert len(re.findall(r"\bget_partition_count\s*\(\s*\)", source)) == (
        expected_get_partition_count_calls
    )
    assert re.search(task_pattern, source)


def test_hk_partition_dag_uses_shared_partition_count_everywhere():
    source = read_source(ROOT / "dags/download_hk_ggt_history_daily.py")

    assert re.search(
        (
            r"def\s+download_hk_ggt_history_hfq_partition_task\b[\s\S]*?"
            r"partition_count\s*=\s*get_partition_count\s*\(\s*\)"
        ),
        source,
    )
    assert re.search(
        r"def\s+aggregate_and_save_result\b[\s\S]*?partition_count\s*=\s*get_partition_count\s*\(\s*\)",
        source,
    )


def test_etf_and_hk_docstrings_use_neutral_partition_language():
    for path in [
        ROOT / "dags/download_etf_daily.py",
        ROOT / "dags/download_hk_ggt_history_daily.py",
    ]:
        source = read_source(path)
        assert "partition identifier (0-" not in source
        assert re.search(r"partition identifier", source)
