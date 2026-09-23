import builtins
import importlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict
from unittest.mock import MagicMock, Mock, call

import pandas as pd
import pytest

from paper_trading.domain.market_data_diagnostics import ProviderOutcome, StockHistoryOutcome

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

PARTITION_ITEM_DAG_SPECS = [
    (ROOT / "dags/download_stock_history_qfq_weekend.py", "stock_ids"),
    (ROOT / "dags/download_stk_holdernumber_weekly.py", "stock_ids"),
    (ROOT / "dags/scan_top10_floatholder_weekly.py", "stock_ids"),
    (ROOT / "dags/download_etf_daily.py", "etf_ids"),
]


def read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_business_date_uses_logical_date_in_local_timezone():
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    context = {
        "data_interval_end": pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
        "logical_date": pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
    }
    assert dag_module.get_business_date(context) == date(2026, 7, 27)


def test_partition_uses_business_date_not_wall_clock():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert 'context["logical_date"]' in source
    assert 'context["data_interval_end"]' not in source
    assert "end_date=business_date.isoformat()" in source
    assert "datetime.now" not in source


def test_daily_history_dag_does_not_import_browser_api_dependencies():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert "from paper_trading.api.deps import" not in source


def test_daily_history_dag_import_does_not_load_paper_trading_auth(monkeypatch):
    pytest.importorskip("airflow")

    original_modules = sys.modules.copy()
    dags_package = sys.modules.get("dags")
    original_dag_attribute = getattr(dags_package, "download_stock_history_daily", None)
    had_dag_attribute = dags_package is not None and hasattr(dags_package, "download_stock_history_daily")
    paper_trading_package = sys.modules.get("paper_trading")
    original_auth_attribute = getattr(paper_trading_package, "auth", None)
    had_auth_attribute = paper_trading_package is not None and hasattr(paper_trading_package, "auth")

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "argon2" or name.startswith("argon2."):
            raise ModuleNotFoundError("argon2 imports are blocked for this regression test")
        return original_import(name, globals, locals, fromlist, level)

    original_import = builtins.__import__
    try:
        for module_name in (
            "dags.download_stock_history_daily",
            "paper_trading.auth",
            "paper_trading.auth.service",
        ):
            sys.modules.pop(module_name, None)
        if dags_package is not None:
            dags_package.__dict__.pop("download_stock_history_daily", None)
        if paper_trading_package is not None:
            paper_trading_package.__dict__.pop("auth", None)
        monkeypatch.setattr(builtins, "__import__", blocked_import)

        importlib.import_module("dags.download_stock_history_daily")

        assert "paper_trading.auth" not in sys.modules
        assert "paper_trading.auth.service" not in sys.modules
    finally:
        sys.modules.clear()
        sys.modules.update(original_modules)
        if dags_package is not None:
            if had_dag_attribute:
                setattr(dags_package, "download_stock_history_daily", original_dag_attribute)
            else:
                dags_package.__dict__.pop("download_stock_history_daily", None)
        if paper_trading_package is not None:
            if had_auth_attribute:
                setattr(paper_trading_package, "auth", original_auth_attribute)
            else:
                paper_trading_package.__dict__.pop("auth", None)


def test_closed_business_date_is_skipped(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setattr(dag_module, "is_a_share_trade_date", lambda business_date: False)
    context = {
        "data_interval_end": pendulum.datetime(2026, 7, 29, 8, tz="UTC"),
        "logical_date": pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
    }
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


def test_matching_dag_passes_the_configured_bearer_token_to_both_cli_calls(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "dag-token")
    monkeypatch.setenv("PAPER_TRADING_API_BASE_URL", "http://paper-trading:8000")
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: date(2026, 7, 28))
    run_matching = Mock(return_value={"id": 7})
    run_rebuild = Mock(return_value={"rebuilt_account_ids": []})
    monkeypatch.setattr(dag_module, "run_paper_trading_matching", run_matching)
    monkeypatch.setattr(dag_module, "run_paper_trading_ledger_rebuild", run_rebuild)

    dag_module.run_paper_trading_matching_for_active_accounts(
        data_interval_end=pendulum.datetime(2026, 7, 28, 8, tz="UTC")
    )

    assert run_matching.call_args.kwargs == {
        "trade_date": "2026-07-28",
        "base_url": "http://paper-trading:8000",
        "token": "dag-token",
    }
    assert run_rebuild.call_args.kwargs == {"base_url": "http://paper-trading:8000", "token": "dag-token"}


def test_daily_dag_rebuild_failures_are_not_swallowed():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")
    matching_source = source[source.index("def run_paper_trading_matching_for_active_accounts") :]

    assert "run_paper_trading_ledger_rebuild(" in matching_source
    before_rebuild, _, after_rebuild = matching_source.partition("run_paper_trading_ledger_rebuild(")
    surrounding_source = before_rebuild[-160:] + after_rebuild[:220]
    assert "try:" not in surrounding_source
    assert "except" not in surrounding_source


def test_closed_date_does_not_run_matching(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    monkeypatch.setattr(dag_module, "is_a_share_trade_date", lambda business_date: False)
    run_matching = Mock()
    monkeypatch.setattr(dag_module, "run_paper_trading_matching", run_matching)
    with pytest.raises(dag_module.AirflowSkipException):
        dag_module.run_paper_trading_matching_for_active_accounts(
            data_interval_end=pendulum.datetime(2026, 7, 29, 8, tz="UTC"),
            logical_date=pendulum.datetime(2026, 7, 28, 8, tz="UTC"),
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


def test_warning_summary_and_matching_warning_run_unified_recovery(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    service = Mock()
    service.recover_unresolved_ordinary_gaps.return_value = []
    service_factory = Mock(return_value=service)
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = []
    batch = Mock(id=1)
    repository.record_batch.return_value = batch
    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", service_factory)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: date(2026, 7, 28))
    result = dag_module.run_unified_bfq_data_gap_recovery(
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
    )
    assert result["gap_count"] == 0
    service.recover_unresolved_ordinary_gaps.assert_called_once_with([], batch_id=1)
    assert service_factory.call_args.kwargs["hk_recovery_policy"] is not None
    assert service_factory.call_args.kwargs["hk_recovery_policy"].calendar.__class__.__name__ == "HkTradeCalendar"
    session.close.assert_called_once()


def test_hk_diagnostic_selection_requires_authority_but_keeps_a_share(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    business_date = date(2026, 7, 28)
    a_share = SimpleNamespace(market="a_share", stock_id="000001")
    hk = SimpleNamespace(market="hk_connect", stock_id="00700")
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [a_share, hk]
    authority = Mock()
    authority.evaluate.return_value = {
        "target_date_calendar": True,
        "ordinary_eligibility": True,
        "suspension": "active",
        "source": "official",
        "freshness": True,
        "decision": True,
    }

    selected = dag_module.get_unresolved_ordinary_gaps(
        repository=repository, business_date=business_date, hk_recovery_policy=authority
    )

    assert selected == [a_share, hk]
    authority.evaluate.assert_called_once_with("00700", business_date)

    authority.evaluate.return_value = {"decision": None}
    assert dag_module.get_unresolved_ordinary_gaps(
        repository=repository, business_date=business_date, hk_recovery_policy=authority
    ) == [a_share]


def test_unified_recovery_uses_detached_gaps_and_persistence_repository(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    diagnostic = SimpleNamespace(classification="missing_market_data")
    gap = SimpleNamespace(
        id=7,
        business_date=date(2026, 7, 28),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [diagnostic]
    repository.get_or_create_gap_from_diagnostic.return_value = gap
    repository.record_batch.return_value = SimpleNamespace(id=3)
    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    persistence = Mock()
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: gap.business_date)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: persistence)
    service = Mock()
    service.recover_unresolved_ordinary_gaps.return_value = [SimpleNamespace(status="recovered")]
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", lambda **kwargs: service)

    result = dag_module.run_unified_bfq_data_gap_recovery(
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
    )

    recovered_gap = service.recover_unresolved_ordinary_gaps.call_args.args[0][0]
    assert recovered_gap is not gap
    assert recovered_gap.id == gap.id
    service.assert_not_called()
    persistence.finalize_batch.assert_called_once()
    assert result["gap_count"] == 1


def test_unified_recovery_injects_fresh_session_repository_as_evidence_port():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert source.count("evidence=recovery_repository") == 2

    evidence_start = source.index("class _FreshSessionRecoveryRepository")
    evidence_end = source.index("def classify_diagnostic")
    evidence_source = source[evidence_start:evidence_end]
    assert "session = self.storage.Session()" in evidence_source
    assert "session.commit()" in evidence_source
    assert "session.rollback()" in evidence_source
    assert "session.close()" in evidence_source

    account_source = source[
        source.index("def run_paper_trading_account_recovery") : source.index("def _persist_account_steps")
    ]
    assert "session = session_factory()" in account_source
    assert "LedgerRebuildService(" in account_source
    assert "session.commit()" in account_source
    assert "session.rollback()" in account_source
    assert "session.close()" in account_source
    assert "SnapshotRecalculationService(\n                session_factory," in account_source


def test_unified_recovery_callable_does_not_invoke_account_side_effect_apis(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    diagnostic = SimpleNamespace(classification="missing_market_data")
    gap = SimpleNamespace(
        id=7,
        business_date=date(2026, 7, 28),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "no_impact", "routing": "ordinary"},
    )
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [diagnostic]
    repository.get_or_create_gap_from_diagnostic.return_value = gap
    repository.record_batch.return_value = SimpleNamespace(id=3)
    persistence = Mock()
    persistence.list_batch_account_recovery.return_value = []
    persistence.list_retryable_recovery_work.return_value = []
    service = Mock()
    service.recover_unresolved_ordinary_gaps.return_value = []
    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: gap.business_date)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: persistence)
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", lambda **kwargs: service)
    account_recovery = Mock(return_value={})
    monkeypatch.setattr(dag_module, "run_paper_trading_account_recovery", account_recovery)

    dag_module.run_unified_bfq_data_gap_recovery(
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
    )

    for api in (
        "upsert_account_progress",
        "record_approval",
        "record_alert",
        "rebuild_account_ledger",
        "run_paper_trading_ledger_rebuild",
        "save_snapshot",
        "create_initial_snapshot",
        "create_account",
        "repair_account",
        "repair_order",
        "escalate_gap",
        "escalate_account",
    ):
        getattr(repository, api).assert_not_called()
        getattr(persistence, api).assert_not_called()
        getattr(service, api).assert_not_called()
    account_recovery.assert_called_once()
    assert account_recovery.call_args.kwargs["affected_account_ids"] == []
    assert account_recovery.call_args.kwargs["recovery_work"] == []


def test_unified_recovery_sends_only_recovered_and_skipped_work_to_accounts(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    @dataclass
    class RecoveryResult:
        gap_id: int
        status: str

    business_date = date(2026, 7, 28)
    diagnostic = SimpleNamespace(classification="missing_market_data")
    gap = SimpleNamespace(
        id=7,
        business_date=business_date,
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [diagnostic]
    repository.get_or_create_gap_from_diagnostic.return_value = gap
    repository.record_batch.return_value = SimpleNamespace(id=3)
    persistence = Mock()
    persistence.list_batch_account_recovery.return_value = [
        {"gap_id": 7, "account_id": 11, "start_date": business_date, "end_date": business_date},
        {"gap_id": 8, "account_id": 22, "start_date": business_date, "end_date": business_date},
        {"gap_id": 9, "account_id": 33, "start_date": business_date, "end_date": business_date},
    ]
    persistence.list_retryable_recovery_work.return_value = []
    service = Mock()
    service.recover_unresolved_ordinary_gaps.return_value = [
        RecoveryResult(7, "recovered"),
        RecoveryResult(8, "failed"),
        RecoveryResult(9, "skipped"),
    ]
    storage = MagicMock(Session=Mock(return_value=MagicMock()))
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: business_date)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: persistence)
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", lambda **kwargs: service)
    account_recovery = Mock(return_value={})
    monkeypatch.setattr(dag_module, "run_paper_trading_account_recovery", account_recovery)

    dag_module.run_unified_bfq_data_gap_recovery(
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
    )

    assert account_recovery.call_args.kwargs["affected_account_ids"] == [11, 33]
    assert [item["gap_id"] for item in account_recovery.call_args.kwargs["recovery_work"]] == [7, 9]


def test_unexpected_recovery_failure_preserves_processed_batch_counts(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    gap = SimpleNamespace(
        id=7,
        business_date=date(2026, 7, 28),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [
        SimpleNamespace(classification="missing_market_data")
    ]
    repository.get_or_create_gap_from_diagnostic.return_value = gap
    repository.record_batch.return_value = SimpleNamespace(id=3)
    persistence = Mock()
    partial = [SimpleNamespace(status="recovered"), SimpleNamespace(status="failed")]
    error = RuntimeError("unexpected recovery failure")
    error.__dict__["partial_results"] = partial
    service = Mock()
    service.recover_unresolved_ordinary_gaps.side_effect = error
    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: gap.business_date)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: persistence)
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", lambda **kwargs: service)

    with pytest.raises(RuntimeError, match="unexpected recovery failure"):
        dag_module.run_unified_bfq_data_gap_recovery(
            ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
        )

    kwargs = persistence.finalize_batch.call_args.kwargs
    assert kwargs["status"] == "failed"
    assert kwargs["gap_count"] == 2
    assert kwargs["recovered_count"] == 1
    assert kwargs["failed_count"] == 1


def test_real_service_partial_results_drive_dag_finalization(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module
    import paper_trading.services.data_gap_recovery_service as service_module

    first = SimpleNamespace(
        id=7,
        business_date=date(2026, 7, 28),
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    class BrokenGap:
        id = 8
        business_date = date(2026, 7, 28)
        stock_id = "000002"
        market = "a_share"
        adjust = "bfq"

        @property
        def summary(self):
            raise ValueError("diagnostic unavailable")

    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [Mock(), Mock()]
    repository.get_or_create_gap_from_diagnostic.side_effect = [first, BrokenGap()]
    repository.record_batch.return_value = SimpleNamespace(id=3)
    persistence = Mock()
    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    storage.load_history_data_stock.return_value = pd.DataFrame(
        {
            "日期": ["2026-07-28"],
            "股票代码": ["000001"],
            "开盘": [10.0],
            "最高": [11.0],
            "最低": [9.0],
            "收盘": [10.5],
            "成交量": [100.0],
            "成交额": [1000.0],
        }
    )
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: first.business_date)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: persistence)
    monkeypatch.setattr(service_module, "get_storage", lambda: storage)

    with pytest.raises(ValueError, match="diagnostic unavailable"):
        dag_module.run_unified_bfq_data_gap_recovery(
            ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
        )

    kwargs = persistence.finalize_batch.call_args.kwargs
    assert kwargs["gap_count"] == 1
    assert kwargs["recovered_count"] == 1
    assert kwargs["failed_count"] == 0


def test_fresh_recovery_repository_supports_threshold_escalation(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module
    from paper_trading.services.data_gap_recovery_service import DataGapRecoveryService

    gap = SimpleNamespace(id=7, business_date=date(2026, 9, 1), stock_id="000001", status="open")
    repository = Mock()
    repository.gap_evidence.return_value = {
        "attempts": [SimpleNamespace(batch_id=i, outcome="not_found") for i in (1, 2, 3)]
    }
    repository.get_gap.return_value = gap
    repository.escalate_gap.return_value = gap
    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)

    adapter = dag_module._FreshSessionRecoveryRepository(storage)
    alerts = Mock()
    service = DataGapRecoveryService(storage=Mock(), downloader=Mock(), repository=adapter, alert_service=alerts)

    assert service.maybe_escalate_gap(gap, user_id=0, user_snapshot={"actor": "system"}, as_of=date(2026, 9, 2))
    repository.gap_evidence.assert_called_once_with(7, None)
    alerts.send_escalation.assert_called_once_with(gap, failure_class="threshold")


def test_fatal_aggregate_skips_unified_recovery(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    recovery = Mock()
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", lambda **kwargs: recovery)
    with pytest.raises(dag_module.AirflowSkipException):
        dag_module.run_unified_bfq_data_gap_recovery(
            ti=MagicMock(xcom_pull=Mock(return_value={"result": "fail", "status": "fatal"}))
        )
    recovery.assert_not_called()


def test_matching_failure_skips_unified_recovery():
    source = read_source(ROOT / "dags/download_stock_history_daily.py")
    recovery_source = source[source.index("data_gap_recovery_task") :]
    assert "trigger_rule=TriggerRule.ALL_SUCCESS" in recovery_source
    assert "paper_trading_matching_task >> data_gap_recovery_task" in source


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
    received_args: list[object] = []
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


def test_account_recovery_rebuilds_ledger_and_recalculates_snapshots_per_account(monkeypatch):
    """RED: recovery must not use one global rebuild or one shared snapshot range."""
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    rebuild = Mock(side_effect=lambda account_id, start_date: {"account_id": account_id})
    recalculate = Mock(side_effect=lambda account_id, start_date, end_date: {"account_id": account_id})

    result = dag_module.run_paper_trading_account_recovery(
        affected_account_ids=[11, 22],
        start_date=date(2026, 7, 28),
        end_date=date(2026, 7, 28),
        rebuild_account=rebuild,
        recalculate_snapshots=recalculate,
    )

    assert result == {"recovered_account_ids": [11, 22], "failed_account_ids": []}
    assert rebuild.call_args_list == [call(11, date(2026, 7, 28)), call(22, date(2026, 7, 28))]
    assert recalculate.call_args_list == [
        call(11, date(2026, 7, 28), date(2026, 7, 28)),
        call(22, date(2026, 7, 28), date(2026, 7, 28)),
    ]


def test_account_recovery_isolates_one_account_failure_and_continues(monkeypatch):
    """RED: one account's ledger failure must not suppress another account's recovery."""
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    rebuild = Mock(side_effect=[RuntimeError("account 11 is corrupt"), {"account_id": 22}])
    recalculate = Mock()

    result = dag_module.run_paper_trading_account_recovery(
        affected_account_ids=[11, 22],
        start_date=date(2026, 7, 28),
        end_date=date(2026, 7, 28),
        rebuild_account=rebuild,
        recalculate_snapshots=recalculate,
    )

    assert result == {
        "recovered_account_ids": [22],
        "failed_account_ids": [11],
        "errors": {11: "account 11 is corrupt"},
    }
    recalculate.assert_called_once_with(22, date(2026, 7, 28), date(2026, 7, 28))


def test_unified_recovery_wires_default_account_recovery_and_exposes_persisted_state(monkeypatch):
    """The unified task must not silently skip account ledger/snapshot recovery."""
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    business_date = date(2026, 7, 28)
    diagnostic = SimpleNamespace(classification="missing_market_data")
    gap = SimpleNamespace(
        id=7,
        business_date=business_date,
        stock_id="000001",
        market="a_share",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )

    class DatabaseLayer:
        def __init__(self):
            self.persisted: dict[str, list[dict[str, object]]] = {"ledger": [], "snapshots": []}

        def list_unresolved_ordinary_diagnostics(self, **kwargs):
            return [diagnostic]

        def get_or_create_gap_from_diagnostic(self, *args, **kwargs):
            return gap

        def record_batch(self, *args, **kwargs):
            return SimpleNamespace(id=3)

        def finalize_batch(self, *args, **kwargs):
            return {"status": "completed"}

        def rebuild_account(self, account_id, start_date):
            self.persisted["ledger"].append({"account_id": account_id, "status": "completed"})

        def recalculate_snapshots(self, account_id, start_date, end_date):
            self.persisted["snapshots"].append({"account_id": account_id, "status": "completed"})

    database = DatabaseLayer()

    class RecoveryService:
        def __init__(self, **kwargs):
            pass

        def recover_unresolved_ordinary_gaps(self, gaps, *, batch_id):
            @dataclass
            class RecoveryResult:
                gap_id: int
                status: str
                affected_account_ids: list[int]

            return [RecoveryResult(7, "recovered", [11])]

    session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=session))
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: business_date)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: database)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: database)
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", RecoveryService)

    result = dag_module.run_unified_bfq_data_gap_recovery(
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
    )

    assert result["recovered_account_ids"] == [11]
    assert result["failed_account_ids"] == []
    assert database.persisted == {
        "ledger": [{"account_id": 11, "status": "completed"}],
        "snapshots": [{"account_id": 11, "status": "completed"}],
    }


def test_unified_hk_recovery_replays_from_earliest_gap_to_batch_cutoff(monkeypatch):
    """HK replay must cover the complete affected range, not only today's bar."""
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    cutoff = date(2026, 9, 3)
    earliest_gap = date(2026, 9, 1)
    diagnostic = SimpleNamespace(classification="missing_market_data", market="hk_connect")
    gap = SimpleNamespace(
        id=7,
        business_date=earliest_gap,
        stock_id="00700",
        market="hk_connect",
        adjust="bfq",
        summary={"classification": "order_dependent", "routing": "ordinary"},
    )
    repository = Mock()
    repository.list_unresolved_ordinary_diagnostics.return_value = [diagnostic]
    repository.get_or_create_gap_from_diagnostic.return_value = gap
    repository.record_batch.return_value = SimpleNamespace(id=3)
    persistence = Mock()
    persistence.list_batch_account_recovery.return_value = [
        {"gap_id": 7, "account_id": 11, "start_date": earliest_gap, "end_date": cutoff}
    ]
    persistence.list_retryable_recovery_work.return_value = []
    service = Mock()
    service.recover_unresolved_ordinary_gaps.return_value = [SimpleNamespace(gap_id=7, status="recovered")]
    storage = MagicMock(Session=Mock(return_value=MagicMock()))
    account_recovery = Mock(return_value={})
    monkeypatch.setattr(dag_module, "ensure_a_share_trade_date", lambda context: cutoff)
    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: repository)
    monkeypatch.setattr(dag_module, "_FreshSessionRecoveryRepository", lambda storage: persistence)
    monkeypatch.setattr(dag_module, "DataGapRecoveryService", lambda **kwargs: service)
    monkeypatch.setattr(dag_module, "run_paper_trading_account_recovery", account_recovery)

    dag_module.run_unified_bfq_data_gap_recovery(
        ti=MagicMock(xcom_pull=Mock(return_value={"result": "success", "status": "warning"}))
    )

    persistence.list_retryable_recovery_work.assert_called_once_with(
        datetime.combine(cutoff, time.max, tzinfo=timezone.utc)
    )
    assert account_recovery.call_args.kwargs["start_date"] == earliest_gap
    assert account_recovery.call_args.kwargs["end_date"] == cutoff


def test_account_recovery_retry_skips_completed_ledger_and_retries_failed_snapshot(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    progress_repository = Mock()
    progress_repository.get_account_progress.side_effect = [
        SimpleNamespace(summary={"ledger": {"status": "completed"}, "snapshot": {"status": "failed"}}),
        SimpleNamespace(summary={"ledger": {"status": "completed"}, "snapshot": {"status": "failed"}}),
    ]
    progress_session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=progress_session))
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: progress_repository)
    rebuild = Mock()
    recalculate = Mock()
    work = [{"gap_id": 7, "account_id": 11, "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 3)}]

    result = dag_module.run_paper_trading_account_recovery(
        affected_account_ids=[11],
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 3),
        rebuild_account=rebuild,
        recalculate_snapshots=recalculate,
        recovery_work=work,
        storage=storage,
    )

    assert result == {"recovered_account_ids": [11], "failed_account_ids": []}
    rebuild.assert_not_called()
    recalculate.assert_called_once_with(11, date(2026, 9, 1), date(2026, 9, 3))


def test_account_recovery_replay_preserves_hk_t_plus_two_and_cross_market_evidence():
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    rebuild = Mock()
    recalculate = Mock()
    work = [
        {
            "gap_id": 7,
            "account_id": 11,
            "market": "hk_connect",
            "stock_id": "00700",
            "start_date": date(2026, 9, 1),
            "end_date": date(2026, 9, 3),
            "settlement_days": 2,
        },
        {
            "gap_id": 8,
            "account_id": 11,
            "market": "a_share",
            "stock_id": "000001",
            "start_date": date(2026, 9, 2),
            "end_date": date(2026, 9, 2),
        },
    ]

    result = dag_module.run_paper_trading_account_recovery(
        affected_account_ids=[11],
        start_date=date(2026, 9, 2),
        end_date=date(2026, 9, 2),
        rebuild_account=rebuild,
        recalculate_snapshots=recalculate,
        recovery_work=work,
    )

    assert result == {"recovered_account_ids": [11], "failed_account_ids": []}
    rebuild.assert_called_once_with(11, date(2026, 9, 1))
    recalculate.assert_called_once_with(11, date(2026, 9, 1), date(2026, 9, 3))


def test_account_recovery_failure_redacts_sensitive_error_details(monkeypatch):
    pytest.importorskip("airflow")
    import dags.download_stock_history_daily as dag_module

    progress_repository = Mock()
    progress_repository.get_account_progress.return_value = None
    progress_session = MagicMock()
    storage = MagicMock(Session=Mock(return_value=progress_session))
    monkeypatch.setattr(dag_module, "DataGapRecoveryRepository", lambda session: progress_repository)
    alert_service = Mock()
    alert_service.repository.get_gap.return_value = SimpleNamespace(id=7)
    secret = "authorization=super-secret token=not-for-logs"

    result = dag_module.run_paper_trading_account_recovery(
        affected_account_ids=[11],
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 1),
        rebuild_account=Mock(side_effect=RuntimeError(secret)),
        recalculate_snapshots=Mock(),
        recovery_work=[{"gap_id": 7, "account_id": 11, "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 1)}],
        storage=storage,
        alert_service=alert_service,
    )

    assert result["failed_account_ids"] == [11]
    assert secret not in result["errors"][11]
    assert "super-secret" not in str(progress_repository.record_account_recovery_step.call_args)
    assert "not-for-logs" not in str(alert_service.send_account_recovery_failure.call_args)
    assert result["errors"][11] == "[redacted] [redacted]"


def test_daily_dag_exposes_independent_account_recovery_hook():
    """RED: the DAG currently has no account-scoped recovery orchestration hook."""
    source = read_source(ROOT / "dags/download_stock_history_daily.py")

    assert "def run_paper_trading_account_recovery(" in source
    assert "rebuild_account(" in source
    assert "recalculate_snapshots(" in source
    assert "except Exception" in source


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
    expected_selection = f"run_partition_items(\n        {ids_name},"
    assert expected_selection in source


def test_partition_dag_runtime_logic_uses_explicit_partition_count_argument():
    for path, _, _ in PARTITION_DAG_SPECS[:-1]:
        source = read_source(path)
        assert "partition_count = PARTITION_COUNT" not in source


@pytest.mark.parametrize(
    "path",
    [ROOT / "dags/download_stock_history_daily.py", ROOT / "dags/download_hk_ggt_history_daily.py"],
)
def test_structured_partition_dags_keep_classification_in_action_adapter(path: Path):
    source = read_source(path)

    assert "run_partition_items" in source
    assert "on_progress=on_progress" in source
    assert "is_failure=" not in source
    assert "_failures" not in source
    assert "outcomes.append(asdict(outcome))" in source
    assert 'if outcome.classification != "downloaded":' in source


@pytest.mark.parametrize(("path", "items_name"), PARTITION_ITEM_DAG_SPECS)
def test_partition_item_dags_use_common_runner_with_progress_callback(path: Path, items_name: str):
    source = read_source(path)

    assert "run_partition_items" in source
    assert f"run_partition_items(\n        {items_name}," in source
    assert "on_progress=on_progress" in source


def test_qfq_partition_treats_none_as_failure_in_runtime_contract(monkeypatch, capsys):
    pytest.importorskip("airflow")
    import dags.download_stock_history_qfq_weekend as dag_module
    import download
    import storage

    monkeypatch.setattr(
        storage,
        "get_storage",
        lambda: SimpleNamespace(load_general_info_stock=lambda: pd.DataFrame({"股票代码": ["000001"]})),
    )
    manager = Mock()
    manager.download_stock_history.return_value = None
    monkeypatch.setattr(download, "DownloadManager", lambda: manager)

    with pytest.raises(Exception, match=r"QFQ 分片下载失败: partition=0/1, failed=1/1, ids\(sample\)=000001"):
        dag_module.download_stock_history_qfq_partition_task(partition_id=0, partition_count=1)

    assert "failed=1" in capsys.readouterr().out


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


def test_hk_partition_uses_logical_date_and_returns_structured_outcomes(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    monkeypatch.setattr(dag_module, "is_hk_market_open", lambda business_date: business_date == "2026-07-27")
    monkeypatch.setattr(
        dag_module,
        "get_storage",
        lambda: SimpleNamespace(load_general_info_hk_ggt=lambda: pd.DataFrame({"股票代码": ["00700"]})),
    )
    outcome = StockHistoryOutcome(
        stock_id="00700",
        business_date="2026-07-27",
        adjust="bfq",
        classification="missing_exact_date",
        resolved=False,
        provider_outcomes=(ProviderOutcome(provider="tushare", status="empty", detail="no exact date"),),
    )
    manager = Mock()
    manager.download_hk_ggt_history_outcome.return_value = outcome
    monkeypatch.setattr(dag_module, "DownloadManager", lambda: manager)
    monkeypatch.setattr(dag_module, "_persist_diagnostic", Mock())

    result = dag_module.download_hk_ggt_history_none_partition_task(
        partition_id=0,
        partition_count=1,
        logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
    )

    assert result["outcomes"][0]["classification"] == "missing_exact_date"
    assert manager.download_hk_ggt_history_outcome.call_args.kwargs["end_date"] == "2026-07-27"


@pytest.mark.parametrize(
    ("classification", "metadata", "suspension"),
    [
        ("authority_unavailable", RuntimeError("metadata unavailable"), {"state": "active", "fresh": True}),
        ("ineligible", None, {"state": "active", "fresh": True}),
        (
            "suspended",
            SimpleNamespace(eligible=True, effective_date=date(2026, 7, 27), fresh=True, source="hk"),
            {"state": "suspended", "fresh": True, "source": "hk"},
        ),
    ],
)
def test_hk_partition_persists_authority_classifications(monkeypatch, classification, metadata, suspension):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    class FakeSession:
        def close(self):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

    storage = SimpleNamespace(
        Session=FakeSession,
        load_general_info_hk_ggt=lambda: pd.DataFrame({"股票代码": ["00700"]}),
    )
    saved = []

    class FakeRepository:
        def __init__(self, session):
            pass

        def upsert_daily_bar_diagnostic(self, *args):
            saved.append(args)

    class FakeEligibility:
        def get_security(self, symbol, *, as_of):
            if isinstance(metadata, Exception):
                raise metadata
            return metadata

    class FakeSuspension:
        def get_symbol_suspension_evidence(self, symbol, business_date, market):
            return suspension

    monkeypatch.setattr(dag_module, "get_storage", lambda: storage)
    monkeypatch.setattr(dag_module, "PaperTradingRepository", FakeRepository)
    monkeypatch.setattr(dag_module, "HkTradeCalendar", lambda: SimpleNamespace(is_trade_date=lambda value: True))
    monkeypatch.setattr(dag_module, "HkConnectMetadataProvider", lambda session: FakeEligibility())
    monkeypatch.setattr(dag_module, "StorageMarketDataProvider", lambda value, calendar: FakeSuspension())
    manager = Mock()
    monkeypatch.setattr(dag_module, "DownloadManager", lambda: manager)

    result = dag_module.download_hk_ggt_history_none_partition_task(
        partition_id=0,
        partition_count=1,
        logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
    )

    outcome = result["outcomes"][0]
    assert outcome["classification"] == classification
    assert outcome["provider_outcomes"][0]["detail"].startswith(f"{classification}:")
    assert saved[0][1] == dag_module.Market.HK_CONNECT
    assert saved[0][2] == "00700"
    assert saved[0][4] == classification
    assert saved[0][5][0]["provider"] == "hk_authority"
    manager.download_hk_ggt_history_outcome.assert_not_called()


def test_hk_aggregate_marks_fatal_and_bounds_evidence(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    outcomes = [
        {"stock_id": f"{i:05d}", "classification": "provider_error", "provider_outcomes": []} for i in range(25)
    ]
    ti = MagicMock(xcom_pull=Mock(return_value={"outcomes": outcomes}))

    with pytest.raises(RuntimeError, match="fatal"):
        dag_module.aggregate_and_save_result(
            partition_count=1,
            ti=ti,
            logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
        )

    payload = json.loads(redis_client.set.call_args.args[1])
    assert payload["date"] == "2026-07-27"
    assert payload["result"] == "fail"
    assert payload["status"] == "fatal"
    assert len(payload["provider_evidence"]) == 20


def test_hk_aggregate_persists_then_raises_fatal(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    ti = MagicMock(
        xcom_pull=Mock(return_value={"outcomes": [{"stock_id": "00700", "classification": "provider_error"}]})
    )
    with pytest.raises(Exception):
        dag_module.aggregate_and_save_result(
            partition_count=1, ti=ti, logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC")
        )
    assert redis_client.set.called


def test_hk_aggregate_missing_partition_persists_fatal_payload_before_raise(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    monkeypatch.setattr(dag_module, "is_hk_market_open", lambda value: True)
    with pytest.raises(RuntimeError):
        dag_module.aggregate_and_save_result(
            partition_count=1,
            ti=MagicMock(xcom_pull=Mock(return_value=None)),
            logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
        )
    payload = json.loads(redis_client.set.call_args.args[1])
    assert payload["result"] == "fail"
    assert payload["status"] == "fatal"
    assert payload["date"] == "2026-07-27"


def test_hk_closed_aggregate_writes_skipped_payload(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    monkeypatch.setattr(dag_module, "is_hk_market_open", lambda value: False)
    redis_client = MagicMock()
    monkeypatch.setattr(dag_module, "get_redis_client", lambda: redis_client)
    dag_module.aggregate_and_save_result(
        partition_count=1,
        ti=MagicMock(xcom_pull=Mock(return_value=None)),
        logical_date=pendulum.datetime(2026, 7, 26, 8, tz="UTC"),
    )
    payload = json.loads(redis_client.set.call_args.args[1])
    assert payload["status"] == "skipped"


def test_hk_warning_aggregate_runs_matching_and_recovery(monkeypatch):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    matching = Mock(return_value={"id": 1})
    recovery = Mock(return_value={"gap_count": 1})
    monkeypatch.setattr(dag_module, "run_paper_trading_matching_for_active_accounts", matching)
    monkeypatch.setattr(dag_module, "run_unified_bfq_data_gap_recovery", recovery)
    dag_module.run_hk_matching_task(
        aggregate_task_id="aggregate_results",
        logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
        ti=MagicMock(xcom_pull=Mock(return_value={"date": "2026-07-27", "result": "success", "status": "warning"})),
    )
    dag_module.run_hk_recovery_task(
        aggregate_task_id="aggregate_results",
        logical_date=pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
        ti=MagicMock(xcom_pull=Mock(return_value={"date": "2026-07-27", "result": "success", "status": "warning"})),
    )
    matching.assert_called_once()
    recovery.assert_called_once()
    assert matching.call_args.kwargs["_business_date"] == pendulum.date(2026, 7, 27)
    assert matching.call_args.kwargs["_aggregate_task_id"] == "aggregate_results"
    assert recovery.call_args.kwargs["_business_date"] == pendulum.date(2026, 7, 27)
    assert recovery.call_args.kwargs["_aggregate_task_id"] == "aggregate_results"


@pytest.mark.parametrize("result", ["fail", "fatal", "skipped"])
def test_hk_matching_and_recovery_skip_non_success_aggregate(monkeypatch, result):
    pendulum = pytest.importorskip("pendulum")
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    matching = Mock(side_effect=AssertionError("matching should be skipped"))
    recovery = Mock(side_effect=AssertionError("recovery should be skipped"))
    monkeypatch.setattr(dag_module, "run_paper_trading_matching_for_active_accounts", matching)
    monkeypatch.setattr(dag_module, "run_unified_bfq_data_gap_recovery", recovery)
    context = {
        "logical_date": pendulum.datetime(2026, 7, 27, 8, tz="UTC"),
        "ti": MagicMock(xcom_pull=Mock(return_value={"result": result})),
    }
    with pytest.raises(Exception):
        dag_module.run_hk_matching_task(aggregate_task_id="aggregate_results", **context)
    with pytest.raises(Exception):
        dag_module.run_hk_recovery_task(aggregate_task_id="aggregate_results", **context)
    matching.assert_not_called()
    recovery.assert_not_called()


def test_hk_aggregate_operator_runs_after_partition_skip_or_failure():
    pytest.importorskip("airflow")
    import dags.download_hk_ggt_history_daily as dag_module

    assert str(dag_module.aggregate_task.trigger_rule) in {"all_done", "TriggerRule.ALL_DONE"}
    assert dag_module.aggregate_task.task_id == "aggregate_results"


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
    assert "run_partition_items(\n        etf_ids," in source
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

    assert 'schedule="0 18 * * 1-5"' in source
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
    matching_start = source.index("def run_paper_trading_matching_for_active_accounts")
    matching_end = source.index("def run_unified_bfq_data_gap_recovery", matching_start)
    matching_source = source[matching_start:matching_end]
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
