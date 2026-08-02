from pathlib import Path


def test_dockerfile_excludes_research_directories_from_runtime_image():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "COPY factor ./factor" not in content
    assert "COPY backtest ./backtest" not in content
    assert "COPY test ./test" not in content
    assert "uv sync --frozen --no-dev" in content


def test_dockerfile_copies_only_existing_runtime_directories():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    copied_directories = [
        line.split()[1]
        for line in content.splitlines()
        if line.startswith("COPY ")
        and len(line.split()) == 3
        and line.split()[2].startswith("./")
        and line.split()[1] != "*.csv"
    ]

    assert all(Path(directory).is_dir() for directory in copied_directories)


def test_business_runtime_services_do_not_bind_mount_repo_root():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'volumes: [".:/app"]' not in content


def test_airflow_runtime_image_installs_pinned_yfinance():
    content = Path("airflow.Dockerfile").read_text(encoding="utf-8")

    assert "yfinance==0.2.55" in content
