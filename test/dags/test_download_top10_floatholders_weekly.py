from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_top10_floatholders_weekly_dag_has_downstream_analysis_task():
    source = (ROOT / "dags/download_top10_floatholders_weekly.py").read_text(
        encoding="utf-8"
    )

    assert 'task_id="analyze_ssf_change_signals"' in source
    assert "python_callable=run_ssf_change_alert" in source
    assert "do_xcom_push=False" in source
    assert "partition_tasks = [" in source
    assert "for task in partition_tasks:" in source
    assert "task >> analysis_task" in source
