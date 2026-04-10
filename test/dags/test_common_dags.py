import os
import sys
import types

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dags.common_dags import get_partition_count, get_partition_ids


def test_get_partition_count_uses_download_process_count(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_PROCESS_COUNT", "6")

    assert get_partition_count() == 6
    assert list(get_partition_ids()) == [0, 1, 2, 3, 4, 5]


@pytest.mark.parametrize("download_process_count", ["0", "-1"])
def test_get_partition_count_normalizes_non_positive_values(
    monkeypatch, download_process_count
):
    monkeypatch.setenv("DOWNLOAD_PROCESS_COUNT", download_process_count)

    assert get_partition_count() == 1
    assert list(get_partition_ids()) == [0]


def test_get_partition_count_falls_back_to_default_when_missing(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_PROCESS_COUNT", raising=False)

    airflow_module = types.ModuleType("airflow")
    airflow_models_module = types.ModuleType("airflow.models")

    class Variable:
        @staticmethod
        def get(name, default_var=None):
            return default_var

    airflow_models_module.Variable = Variable
    airflow_module.models = airflow_models_module
    monkeypatch.setitem(sys.modules, "airflow", airflow_module)
    monkeypatch.setitem(sys.modules, "airflow.models", airflow_models_module)

    assert get_partition_count() == 4
    assert list(get_partition_ids()) == [0, 1, 2, 3]
