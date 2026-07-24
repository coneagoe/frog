from pathlib import Path


def test_dockerfile_excludes_research_directories_from_runtime_image():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY factor ./factor" not in content
    assert "COPY backtest ./backtest" not in content
    assert "COPY test ./test" not in content
    assert "uv sync --frozen --no-dev" in content


def test_business_runtime_services_do_not_bind_mount_repo_root():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'volumes: [".:/app"]' not in content


def test_airflow_runtime_image_installs_pinned_yfinance():
    content = Path("airflow.Dockerfile").read_text(encoding="utf-8")

    assert "yfinance==0.2.55" in content
