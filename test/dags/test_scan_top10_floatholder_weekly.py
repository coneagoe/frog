from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_scan_top10_floatholder_weekly_dag_has_scan_identity_and_downstream_analysis_task():
    source = (ROOT / "dags/scan_top10_floatholder_weekly.py").read_text(encoding="utf-8")

    assert '"scan_top10_floatholder_weekly"' in source
    assert 'description="Weekly A-share top10 floatholder scan"' in source
    assert "def scan_top10_floatholder_partition_task(" in source
    assert 'task_id=f"scan_top10_floatholder_p{pid:02d}"' in source
    assert "python_callable=scan_top10_floatholder_partition_task" in source
    assert 'task_id="analyze_ssf_change_signals"' in source
    assert "python_callable=run_ssf_change_alert" in source
    assert "do_xcom_push=False" in source
    assert "partition_tasks = [" in source
    assert "for task in partition_tasks:" in source
    assert "task >> analysis_task" in source
