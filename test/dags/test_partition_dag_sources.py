import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / "dags/download_stock_history_daily.py",
    ROOT / "dags/download_stock_history_qfq_weekend.py",
    ROOT / "dags/download_stk_holdernumber_weekly.py",
    ROOT / "dags/download_etf_daily.py",
    ROOT / "dags/download_hk_ggt_history_daily.py",
]


def test_etf_partition_tasks_are_driven_by_shared_partition_ids():
    source = (ROOT / "dags/download_etf_daily.py").read_text(encoding="utf-8")

    assert "MAX_PARTITIONS" not in source
    assert "min(get_partition_count(), MAX_PARTITIONS)" not in source
    assert re.search(
        r"for\s+_pid\s+in\s+get_partition_ids\s*\(\s*\)\s*:",
        source,
    )


def test_hk_partition_dag_uses_shared_partition_count_everywhere():
    source = (ROOT / "dags/download_hk_ggt_history_daily.py").read_text(encoding="utf-8")

    assert "MAX_PARTITIONS" not in source
    assert "min(get_partition_count(), MAX_PARTITIONS)" not in source
    assert len(re.findall(r"\bget_partition_count\s*\(\s*\)", source)) == 2
    assert re.search(
        r"def\s+download_hk_ggt_history_hfq_partition_task\b[\s\S]*?partition_count\s*=\s*get_partition_count\s*\(\s*\)",
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
        source = path.read_text(encoding="utf-8")
        assert "partition identifier (0-" not in source
        assert re.search(r"partition identifier", source)
