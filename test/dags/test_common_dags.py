import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dags.common_dags import get_partition_count, get_partition_ids


def test_get_partition_count_uses_download_process_count(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_PROCESS_COUNT", "6")

    assert get_partition_count() == 6
    assert list(get_partition_ids()) == [0, 1, 2, 3, 4, 5]


def test_get_partition_count_normalizes_non_positive_values(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_PROCESS_COUNT", "0")

    assert get_partition_count() == 1
    assert list(get_partition_ids()) == [0]


def test_get_partition_count_falls_back_to_default_when_missing(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_PROCESS_COUNT", raising=False)

    assert get_partition_count() == 4
    assert list(get_partition_ids()) == [0, 1, 2, 3]
