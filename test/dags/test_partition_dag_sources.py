from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGETS = [
    ROOT / "dags/download_stock_history_daily.py",
    ROOT / "dags/download_stock_history_qfq_weekend.py",
    ROOT / "dags/download_stk_holdernumber_weekly.py",
    ROOT / "dags/download_etf_daily.py",
    ROOT / "dags/download_hk_ggt_history_daily.py",
]


def test_all_partition_dags_use_shared_partition_source():
    for path in TARGETS:
        source = path.read_text(encoding="utf-8")
        assert "MAX_PARTITIONS" not in source
        assert "min(get_partition_count(), MAX_PARTITIONS)" not in source
        assert "get_partition_ids" in source
