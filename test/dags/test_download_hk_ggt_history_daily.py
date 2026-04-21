import importlib.util
import os
import re
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = ROOT / "dags/download_hk_ggt_history_daily.py"


def read_source() -> str:
    return DAG_PATH.read_text(encoding="utf-8")


def test_source_wires_run_obos_hk_after_aggregate_task():
    source = read_source()

    assert re.search(
        r'run_obos_hk_operator\s*=\s*PythonOperator\([\s\S]*?task_id\s*=\s*["\']run_obos_hk["\']',
        source,
    )
    assert re.search(
        r"run_obos_hk_operator\s*=\s*PythonOperator\([\s\S]*?python_callable\s*=\s*run_obos_hk_task",
        source,
    )
    assert re.search(r"aggregate_task\s*>>\s*run_obos_hk_operator", source)


def load_dag_module_with_stubs(monkeypatch):
    airflow_module = types.ModuleType("airflow")
    airflow_module.__path__ = []
    airflow_exceptions_module = types.ModuleType("airflow.exceptions")
    airflow_operators_module = types.ModuleType("airflow.operators")
    airflow_operators_module.__path__ = []
    airflow_operators_python_module = types.ModuleType("airflow.operators.python")

    class AirflowSkipException(Exception):
        pass

    class FakeDAG:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class FakePythonOperator:
        def __init__(self, *, task_id, python_callable, op_kwargs=None, dag=None, **kwargs):
            self.task_id = task_id
            self.python_callable = python_callable
            self.op_kwargs = op_kwargs or {}
            self.dag = dag
            self.kwargs = kwargs
            self.upstream_tasks = []
            self.downstream_tasks = []

        def __rshift__(self, other):
            self.downstream_tasks.append(other)
            other.upstream_tasks.append(self)
            return other

    airflow_module.DAG = FakeDAG
    airflow_exceptions_module.AirflowSkipException = AirflowSkipException
    airflow_operators_python_module.PythonOperator = FakePythonOperator

    common_dags_module = types.ModuleType("common_dags")
    common_dags_module.LOCAL_TZ = None
    common_dags_module.get_default_args = lambda: {}
    common_dags_module.get_partition_count = lambda: 1
    common_dags_module.get_partition_ids = lambda count=1: range(count)
    common_dags_module.get_partitioned_ids = lambda ids, partition_id, partition_count: ids

    common_module = types.ModuleType("common")
    common_module.__path__ = []
    common_module.is_a_market_open_today = lambda: True

    common_const_module = types.ModuleType("common.const")
    common_const_module.COL_STOCK_ID = "stock_id"
    common_const_module.DEFAULT_REDIS_URL = "redis://example"
    common_const_module.REDIS_KEY_DOWNLOAD_HK_GGT_HISTORY = "download_hk_ggt_history"
    common_const_module.AdjustType = types.SimpleNamespace(HFQ="hfq")
    common_const_module.PeriodType = types.SimpleNamespace(DAILY="daily")

    common_obos_runner_module = types.ModuleType("common.obos_hk_runner")

    class ObosHkSkip(Exception):
        pass

    common_obos_runner_module.ObosHkSkip = ObosHkSkip
    common_obos_runner_module.run_obos_hk_backtest = lambda **kwargs: None

    download_module = types.ModuleType("download")
    download_module.DownloadManager = type("DownloadManager", (), {})

    storage_module = types.ModuleType("storage")
    storage_module.get_storage = lambda: types.SimpleNamespace()

    redis_module = types.ModuleType("redis")
    redis_module.Redis = type(
        "Redis",
        (),
        {"from_url": staticmethod(lambda *args, **kwargs: object())},
    )

    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.exceptions", airflow_exceptions_module)
    monkeypatch.setitem(sys.modules, "airflow.operators", airflow_operators_module)
    monkeypatch.setitem(sys.modules, "airflow.operators.python", airflow_operators_python_module)
    monkeypatch.setitem(sys.modules, "common_dags", common_dags_module)
    monkeypatch.setitem(sys.modules, "common", common_module)
    monkeypatch.setitem(sys.modules, "common.const", common_const_module)
    monkeypatch.setitem(sys.modules, "common.obos_hk_runner", common_obos_runner_module)
    monkeypatch.setitem(sys.modules, "download", download_module)
    monkeypatch.setitem(sys.modules, "storage", storage_module)
    monkeypatch.setitem(sys.modules, "redis", redis_module)

    spec = importlib.util.spec_from_file_location(
        "testable_download_hk_ggt_history_daily",
        DAG_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, AirflowSkipException, ObosHkSkip


def test_run_obos_hk_task_maps_obos_skip_to_airflow_skip(monkeypatch):
    module, airflow_skip_exception, obos_hk_skip = load_dag_module_with_stubs(monkeypatch)

    assert hasattr(module, "run_obos_hk_task")

    monkeypatch.setattr(
        module,
        "run_obos_hk_backtest",
        lambda **kwargs: (_ for _ in ()).throw(obos_hk_skip("download result is fail")),
        raising=False,
    )

    with pytest.raises(airflow_skip_exception, match="download result is fail"):
        module.run_obos_hk_task()
