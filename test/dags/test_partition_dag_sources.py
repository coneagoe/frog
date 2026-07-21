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
        ROOT / "dags/scan_top10_floatholder_weekly.py",
        "scan_top10_floatholder_partition_task",
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
    partition_var = "_pid" if "for _pid in get_partition_ids(PARTITION_COUNT):" in source else "pid"
    return (
        rf'op_kwargs\s*=\s*\{{\s*"partition_id"\s*:\s*{partition_var}\s*,\s*"partition_count"\s*:\s*'
        rf"PARTITION_COUNT\s*\}}"
    )


@pytest.mark.parametrize(("path", "task_name", "ids_name"), PARTITION_DAG_SPECS)
def test_partition_dag_sources_freeze_shared_partition_count_once(path: Path, task_name: str, ids_name: str):
    source = read_source(path)

    assert not re.search(r"\bMAX_PARTITIONS\b", source)
    assert len(re.findall(r"\bget_partition_count\s*\(\s*\)", source)) == 1
    assert re.search(r"^PARTITION_COUNT\s*=\s*get_partition_count\s*\(\s*\)", source, re.MULTILINE)
    assert re.search(r"for\s+_?pid\s+in\s+get_partition_ids\s*\(\s*PARTITION_COUNT\s*\)", source)
    assert re.search(build_task_signature_pattern(task_name), source)
    assert re.search(build_partition_kwargs_pattern(source), source)
    assert f"get_partitioned_ids({ids_name}, partition_id, partition_count)" in source


def test_partition_dag_runtime_logic_uses_explicit_partition_count_argument():
    for path, _, _ in PARTITION_DAG_SPECS[:-1]:
        source = read_source(path)
        assert "partition_count = PARTITION_COUNT" not in source


def test_hk_partition_dag_uses_frozen_partition_count_everywhere():
    source = read_source(ROOT / "dags/download_hk_ggt_history_daily.py")

    # PARTITION_COUNT is hardcoded to 1; get_partition_count() must NOT be called
    assert not re.search(r"\bget_partition_count\s*\(\s*\)", source)
    assert re.search(r"^PARTITION_COUNT\s*=\s*1\b", source, re.MULTILINE)
    assert 'DEFAULT_START_DATE: Final = "2026-01-01"' in source
    assert "AdjustType.BFQ" in source
    assert "download_hk_ggt_history_none_p" in source
    assert "download_hk_ggt_history_hfq_p" not in source
    assert re.search(
        build_task_signature_pattern("download_hk_ggt_history_none_partition_task"),
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

    # DAG invariants called out by the task brief
    assert re.search(r'schedule\s*=\s*"30\s+16\s+\*\s+\*\s+1-5"', source)
    assert "catchup=False" in source
    assert "max_active_runs=1" in source
    assert "REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY" in source
    assert re.search(r"for task in partition_tasks:\s+task >> aggregate_task", source)


def test_etf_partition_dag_uses_frozen_partition_count_everywhere():
    source = read_source(ROOT / "dags/download_etf_daily.py")

    assert not re.search(r"\bget_partition_count\s*\(\s*\)", source)
    assert re.search(r"^PARTITION_COUNT\s*=\s*1\b", source, re.MULTILINE)
    assert re.search(
        build_task_signature_pattern("download_etf_daily_partition_task"),
        source,
    )
    assert re.search(r"for\s+_?pid\s+in\s+get_partition_ids\s*\(\s*PARTITION_COUNT\s*\)", source)
    assert re.search(build_partition_kwargs_pattern(source), source)
    assert "get_partitioned_ids(etf_ids, partition_id, partition_count)" in source
    assert "partition_count = PARTITION_COUNT" not in source


def test_daily_dag_has_both_hfq_and_bfq_partition_tasks():
    """The daily stock history DAG must contain both HFQ and BFQ partition tasks."""
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    # HFQ partition task must be defined
    assert re.search(r"def download_stock_history_hfq_partition_task\s*\(", source)
    # BFQ partition task must be defined
    assert re.search(r"def download_stock_history_bfq_partition_task\s*\(", source)
    # BFQ task must use AdjustType.BFQ
    assert "AdjustType.BFQ" in source
    # HFQ task must still use AdjustType.HFQ
    assert "AdjustType.HFQ" in source
    # Both task lists must be wired to the aggregate
    assert "hfq_partition_tasks + bfq_partition_tasks" in source
    # Redis key must remain unchanged
    assert "REDIS_KEY_DOWNLOAD_STOCK_HISTORY_DAILY" in source


def test_daily_dag_uses_weekdays_dag_id_without_hfq_suffix():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert '"download_stock_history_weekdays"' in source
    assert '"download_stock_history_hfq_weekdays"' not in source


def test_daily_dag_runs_paper_trading_matching_after_successful_aggregate():
    """The daily stock history DAG should trigger paper-trading matching via the CLI helper."""
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert re.search(r"def run_paper_trading_matching_for_active_accounts\s*\(", source)
    assert "from paper_trading" not in source
    assert "import paper_trading" not in source
    assert "from tools.paper_trading_cli import run_paper_trading_matching" in source
    assert "requests.post" not in source
    assert '"/paper/matching/runs"' not in source
    assert "PAPER_TRADING_API_BASE_URL" in source
    assert "PAPER_TRADING_API_TOKEN" in source
    assert "run_paper_trading_matching(" in source
    assert re.search(
        r"paper_trading_matching_task\s*=\s*PythonOperator\([\s\S]*?"
        r'task_id\s*=\s*"run_paper_trading_matching"',
        source,
    )
    assert "aggregate_task >> paper_trading_matching_task" in source


def test_daily_dag_paper_trading_matching_uses_local_trade_date_and_commits_once():
    """Paper-trading matching should use the DAG local date for matching."""
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert "trade_date = datetime.now(tz=LOCAL_TZ).date()" in source
    assert "trade_date=trade_date.isoformat()" in source
    assert "session.commit()" not in source
    assert "session.close()" not in source


def test_compose_passes_paper_trading_api_config_to_airflow():
    """Airflow workers should be able to call the paper-trading backend over Docker DNS."""
    source = read_source(ROOT / "docker-compose.yml")

    assert "PAPER_TRADING_API_BASE_URL: http://paper-trading:8000" in source
    assert "PAPER_TRADING_API_TOKEN" in source


def test_etf_and_hk_docstrings_use_neutral_partition_language():
    for path in [
        ROOT / "dags/download_etf_daily.py",
        ROOT / "dags/download_hk_ggt_history_daily.py",
    ]:
        source = read_source(path)
        assert "partition identifier (0-" not in source
        assert re.search(r"partition identifier", source)
