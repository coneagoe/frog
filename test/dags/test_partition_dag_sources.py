import json
import re
from datetime import date
from pathlib import Path
from typing import TypedDict
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


class DownloadOutcome(TypedDict):
    stock_id: str
    business_date: str
    adjust: str
    classification: str
    provider_outcomes: list[dict[str, object]]
    resolved: bool


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


def test_business_date_uses_data_interval_end_in_local_timezone():
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    context = {
        "data_interval_end": pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
        "logical_date": pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
    }
    assert dag_module.get_business_date(context) == date(2026, 7, 28)


def test_partition_uses_business_date_not_wall_clock():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert "end_date=business_date.isoformat()" in source
    assert "datetime.now" not in source


def test_closed_business_date_is_skipped(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setattr(dag_module, "is_a_share_trade_date", lambda business_date: False)
    context = {"data_interval_end": pendulum.datetime(2026, 7, 28, 8, tz="UTC")}
    with pytest.raises(dag_module.AirflowSkipException):
        dag_module.ensure_a_share_trade_date(context)


def test_warning_aggregate_writes_structured_bounded_payload(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    business_date = date(2026, 7, 28)
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: business_date)
    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    outcomes: list[DownloadOutcome] = [
        {
            "stock_id": f"300{i:03d}",
            "business_date": business_date.isoformat(),
            "adjust": "bfq",
            "classification": "missing_market_data",
            "provider_outcomes": [{"provider": "tushare", "status": "empty", "detail": None}],
            "resolved": False,
        }
        for i in range(21)
    ]
    ti = MagicMock()
    ti.xcom_pull.side_effect = [
        {"adjust": "hfq", "outcomes": []},
        {"adjust": "bfq", "outcomes": list(reversed(outcomes))},
    ]

    dag_module.save_download_result_to_redis(
        partition_count=1,
        ti=ti,
        data_interval_end=pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
    )

    payload = json.loads(redis_client.set.call_args.args[1])
    assert payload["date"] == "2026-07-28"
    assert payload["result"] == "success"
    assert payload["status"] == "warning"
    assert payload["missing_symbols"] == sorted(item["stock_id"] for item in outcomes)
    assert len(payload["provider_evidence"]) == 20
    assert [item["stock_id"] for item in payload["provider_evidence"]] == [f"300{i:03d}" for i in range(20)]


def test_complete_aggregate_writes_success_payload(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    business_date = date(2026, 7, 28)
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: business_date)
    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    ti = MagicMock()
    ti.xcom_pull.side_effect = [
        {"adjust": "hfq", "outcomes": []},
        {"adjust": "bfq", "outcomes": []},
    ]

    dag_module.save_download_result_to_redis(partition_count=1, ti=ti)

    payload = json.loads(redis_client.set.call_args.args[1])
    assert payload == {
        "date": "2026-07-28",
        "result": "success",
        "status": "success",
        "missing_symbols": [],
        "provider_evidence": [],
    }


def test_warning_summary_runs_matching_with_same_business_date(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setattr(dag_module, "get_business_date", lambda context: date(2026, 7, 28))
    monkeypatch.setattr(dag_module, "is_a_share_trade_date", lambda business_date: True)
    run_matching = Mock(return_value={"id": 7, "warning_count": 1})
    run_rebuild = Mock(return_value={"rebuilt_account_ids": [1]})
    monkeypatch.setattr(dag_module, "run_paper_trading_matching", run_matching)
    monkeypatch.setattr(dag_module, "run_paper_trading_ledger_rebuild", run_rebuild)
    result = dag_module.run_paper_trading_matching_for_active_accounts(
        data_interval_end=pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"})),
    )
    assert run_matching.call_args.kwargs["trade_date"] == "2026-07-28"
    assert "run_id=7" in result
    assert "warning_count=1" in result
    assert "rebuilt_accounts=1" in result
    run_rebuild.assert_called_once()


def test_closed_date_does_not_run_matching(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setattr(dag_module, "is_a_share_trade_date", lambda business_date: False)
    run_matching = Mock()
    monkeypatch.setattr(dag_module, "run_paper_trading_matching", run_matching)
    with pytest.raises(dag_module.AirflowSkipException):
        dag_module.run_paper_trading_matching_for_active_accounts(
            data_interval_end=pendulum.datetime(2026, 7, 28, 8, tz="UTC")
        )
    run_matching.assert_not_called()


def test_fatal_aggregate_does_not_run_matching(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: date(2026, 7, 28))
    run_matching = Mock()
    monkeypatch.setattr(dag_module, "run_paper_trading_matching", run_matching)
    context = {
        "data_interval_end": pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
        "ti": MagicMock(xcom_pull=Mock(return_value={"result": "fail", "status": "fatal"})),
    }
    with pytest.raises(dag_module.AirflowSkipException):
        dag_module.run_paper_trading_matching_for_active_accounts(**context)
    run_matching.assert_not_called()


def test_partition_diagnostic_failure_rolls_back_and_fails(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module
    from paper_trading.domain.market_data_diagnostics import StockHistoryOutcome

    session = MagicMock()
    storage = MagicMock(Session=MagicMock(return_value=session))
    storage.load_general_info_stock.return_value = pd.DataFrame({"股票代码": ["300996"]})
    manager = MagicMock()
    manager.download_stock_history_outcome.return_value = StockHistoryOutcome(
        "300996", "2026-07-28", "bfq", "missing_market_data", (), False
    )
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: date(2026, 7, 28))
    monkeypatch.setattr(dag_module, "get_partitioned_ids", lambda ids, partition_id, partition_count: ids)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DownloadManager", lambda: manager)
    monkeypatch.setattr(dag_module, "_persist_diagnostic", MagicMock(side_effect=RuntimeError("db down")))

    with pytest.raises(RuntimeError, match="db down"):
        dag_module.download_stock_history_bfq_partition_task(
            partition_id=0,
            partition_count=1,
            data_interval_end=pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
        )

    storage.Session.assert_not_called()


def test_persist_diagnostic_commits_and_closes_its_session(monkeypatch):
    pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module
    from paper_trading.domain.enums import Market
    from paper_trading.domain.market_data_diagnostics import StockHistoryOutcome

    events = []
    received_args = []
    session = MagicMock()
    session.commit.side_effect = lambda: events.append("commit")
    session.close.side_effect = lambda: events.append("close")
    storage = MagicMock(Session=MagicMock(return_value=session))

    class Repository:
        def __init__(self, received_session):
            assert received_session is session

        def upsert_daily_bar_diagnostic(self, *args):
            events.append("upsert")
            received_args.extend(args)

    monkeypatch.setattr(dag_module, "PaperTradingRepository", Repository)
    outcome = StockHistoryOutcome("300996", "2026-07-28", "bfq", "missing_market_data", (), False)

    dag_module._persist_diagnostic(
        storage,
        date(2026, 7, 28),
        "300996",
        "bfq",
        outcome,
    )

    assert events == ["upsert", "commit", "close"]
    assert received_args[1] == Market.A_SHARE


def test_daily_dag_closes_diagnostic_session_with_each_write():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")
    diagnostic_source = source[source.index("def _persist_diagnostic") : source.index("def get_redis_client")]

    assert "def _persist_diagnostic(storage," in diagnostic_source
    assert "session = storage.Session()" in diagnostic_source
    assert "session.commit()" in diagnostic_source
    assert "session.close()" in diagnostic_source


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
    matching_source = source[source.index("def run_paper_trading_matching_for_active_accounts") :]
    assert "from paper_trading" not in matching_source
    assert "import paper_trading" not in matching_source
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

    assert "trade_date = ensure_a_share_trade_date(context)" in source
    assert "trade_date=trade_date.isoformat()" in source
    matching_source = source[source.index("def run_paper_trading_matching_for_active_accounts") :]
    assert "session.commit()" not in matching_source
    assert "session.close()" not in matching_source


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
