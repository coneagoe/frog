import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

PARTITION_DAG_SPECS = [
    (
        ROOT / "dags/download_stock_history_daily.py",
        "download_stock_history_hfq_partition_task",
        "stock_ids",
    ),
    (
        ROOT / "dags/download_stock_history_qfq_weekend.py",
        "download_stock_history_qfq_partition_task",
        "stock_ids",
    ),
    (
        ROOT / "dags/download_stk_holdernumber_weekly.py",
        "download_stk_holdernumber_partition_task",
        "stock_ids",
    ),
    (
        ROOT / "dags/download_etf_daily.py",
        "download_etf_daily_partition_task",
        "etf_ids",
    ),
    (
        ROOT / "dags/download_hk_ggt_history_daily.py",
        "download_hk_ggt_history_hfq_partition_task",
        "stock_ids",
    ),
]


def read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_task_signature_pattern(task_name: str) -> str:
    return (
        rf"def\s+{task_name}\s*"
        rf"\(\s*\*,\s*partition_id:\s*int\s*,\s*partition_count:\s*int\s*,\s*\*\*context\s*\)"
    )


def build_partition_kwargs_pattern(source: str) -> str:
    partition_var = (
        "_pid" if "for _pid in get_partition_ids(PARTITION_COUNT):" in source else "pid"
    )
    return (
        rf'op_kwargs\s*=\s*\{{\s*"partition_id"\s*:\s*{partition_var}\s*,\s*"partition_count"\s*:\s*'
        rf"PARTITION_COUNT\s*\}}"
    )


@pytest.mark.parametrize(("path", "task_name", "ids_name"), PARTITION_DAG_SPECS)
def test_partition_dag_sources_freeze_shared_partition_count_once(
    path: Path, task_name: str, ids_name: str
):
    source = read_source(path)

    assert not re.search(r"\bMAX_PARTITIONS\b", source)
    assert len(re.findall(r"\bget_partition_count\s*\(\s*\)", source)) == 1
    assert re.search(
        r"^PARTITION_COUNT\s*=\s*get_partition_count\s*\(\s*\)", source, re.MULTILINE
    )
    assert re.search(
        r"for\s+_?pid\s+in\s+get_partition_ids\s*\(\s*PARTITION_COUNT\s*\)", source
    )
    assert re.search(build_task_signature_pattern(task_name), source)
    assert re.search(build_partition_kwargs_pattern(source), source)
    assert f"get_partitioned_ids({ids_name}, partition_id, partition_count)" in source


def test_partition_dag_runtime_logic_uses_explicit_partition_count_argument():
    for path, _, _ in PARTITION_DAG_SPECS[:-1]:
        source = read_source(path)
        assert "partition_count = PARTITION_COUNT" not in source


def test_hk_partition_dag_uses_frozen_partition_count_everywhere():
    source = read_source(ROOT / "dags/download_hk_ggt_history_daily.py")

    assert re.search(
        build_task_signature_pattern("download_hk_ggt_history_hfq_partition_task"),
        source,
    )
    assert re.search(
        (
            r"def\s+aggregate_and_save_result\s*\("
            r"\s*\*,\s*partition_count:\s*int\s*,\s*\*\*context\s*\)"
        ),
        source,
    )
    assert re.search(
        (
            r"aggregate_task\s*=\s*PythonOperator\([\s\S]*?op_kwargs\s*=\s*\{"
            r'\s*"partition_count"\s*:\s*PARTITION_COUNT\s*\}'
        ),
        source,
    )
    assert "partition_count = PARTITION_COUNT" not in source


def test_etf_and_hk_docstrings_use_neutral_partition_language():
    for path in [
        ROOT / "dags/download_etf_daily.py",
        ROOT / "dags/download_hk_ggt_history_daily.py",
    ]:
        source = read_source(path)
        assert "partition identifier (0-" not in source
        assert re.search(r"partition identifier", source)
