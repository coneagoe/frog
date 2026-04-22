# mypy: disable-error-code="attr-defined,arg-type"

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

ROOT = Path(__file__).resolve().parents[2]
DAG_PATH = ROOT / "dags/download_hk_ggt_history_daily.py"


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
            self.task_dict = {}

        def add_task(self, task):
            self.task_dict[task.task_id] = task

    class FakePythonOperator:
        def __init__(
            self, *, task_id, python_callable, op_kwargs=None, dag=None, **kwargs
        ):
            self.task_id = task_id
            self.python_callable = python_callable
            self.op_kwargs = op_kwargs or {}
            self.dag = dag
            self.kwargs = kwargs
            self.upstream_tasks = []
            self.downstream_tasks = []
            if dag is not None:
                dag.add_task(self)

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
    common_dags_module.get_partitioned_ids = (
        lambda ids, partition_id, partition_count: ids
    )

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
    monkeypatch.setitem(
        sys.modules, "airflow.operators.python", airflow_operators_python_module
    )
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
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, AirflowSkipException, ObosHkSkip


def test_loaded_dag_wires_run_obos_hk_after_aggregate_task(monkeypatch):
    module, _, _ = load_dag_module_with_stubs(monkeypatch)

    assert module.aggregate_task.task_id == "aggregate_results"
    assert module.aggregate_task.python_callable is module.aggregate_and_save_result
    assert module.aggregate_task.op_kwargs == {
        "partition_count": module.PARTITION_COUNT
    }
    assert module.aggregate_task.dag is module.dag
    assert module.partition_tasks
    assert all(
        module.aggregate_task in task.downstream_tasks
        for task in module.partition_tasks
    )

    run_obos_hk_operator = module.dag.task_dict.get("run_obos_hk")
    assert run_obos_hk_operator is not None
    assert run_obos_hk_operator.python_callable is module.run_obos_hk_task
    assert module.aggregate_task.downstream_tasks == [run_obos_hk_operator]


@pytest.mark.parametrize(
    "runner_skip_reason",
    [
        "download result is fail",
        "download result missing",
        "Market is closed today.",
    ],
)
def test_run_obos_hk_task_maps_runner_skip_reasons_to_airflow_skip(
    monkeypatch, runner_skip_reason
):
    module, airflow_skip_exception, obos_hk_skip = load_dag_module_with_stubs(
        monkeypatch
    )

    assert hasattr(module, "run_obos_hk_task")

    run_kwargs = []

    def fake_run_obos_hk_backtest(**kwargs):
        run_kwargs.append(kwargs)
        raise obos_hk_skip(runner_skip_reason)

    monkeypatch.setattr(
        module,
        "run_obos_hk_backtest",
        fake_run_obos_hk_backtest,
        raising=False,
    )

    with pytest.raises(airflow_skip_exception, match=runner_skip_reason) as exc_info:
        module.run_obos_hk_task()

    assert run_kwargs == [
        {
            "python_executable": module.sys.executable,
            "require_download_result": True,
        }
    ]
    assert runner_skip_reason in str(exc_info.value)


def test_run_obos_hk_task_propagates_runtime_errors(monkeypatch):
    module, _, _ = load_dag_module_with_stubs(monkeypatch)

    assert hasattr(module, "run_obos_hk_task")

    run_kwargs = []

    def fake_run_obos_hk_backtest(**kwargs):
        run_kwargs.append(kwargs)
        raise RuntimeError("boom")

    monkeypatch.setattr(
        module,
        "run_obos_hk_backtest",
        fake_run_obos_hk_backtest,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        module.run_obos_hk_task()

    assert run_kwargs == [
        {
            "python_executable": module.sys.executable,
            "require_download_result": True,
        }
    ]


def test_dag_runner_wrapper_uses_project_root_and_restores_cwd(monkeypatch):
    module, _, _ = load_dag_module_with_stubs(monkeypatch)

    original_cwd = ROOT / "test"
    monkeypatch.chdir(original_cwd)
    runner_calls: dict[str, object] = {}

    def fake_shared_runner(**kwargs):
        runner_calls["cwd"] = os.getcwd()
        runner_calls["kwargs"] = kwargs
        return types.SimpleNamespace(status="success")

    monkeypatch.setattr(
        module,
        "_shared_run_obos_hk_backtest",
        fake_shared_runner,
        raising=False,
    )
    monkeypatch.setattr(module, "project_root", str(ROOT))

    result = module.run_obos_hk_backtest(
        python_executable=module.sys.executable,
        require_download_result=True,
    )

    assert result.status == "success"
    assert runner_calls == {
        "cwd": str(ROOT),
        "kwargs": {
            "executable": module.sys.executable,
            "require_download_result": True,
        },
    }
    assert os.getcwd() == str(original_cwd)
