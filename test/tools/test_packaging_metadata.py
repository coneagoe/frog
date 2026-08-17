import tomllib
from pathlib import Path


def test_pyproject_uses_uv_and_ruff_instead_of_poetry_lint_stack():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    build_system = data.get("build-system")
    if build_system is not None:
        assert "poetry-core" not in build_system["requires"]

    dependency_groups = data.get("dependency-groups", {})
    assert "dev" in dependency_groups

    dev_group = dependency_groups["dev"]
    assert any(str(item).startswith("ruff") for item in dev_group)
    assert not any(str(item).startswith("flake8") for item in dev_group)

    assert "tool" in data
    assert "ruff" in data["tool"]
    assert "poetry" not in data["tool"]
    assert "isort" not in data["tool"]
    assert data["tool"]["uv"]["package"] is False


def test_mypy_config_has_explicit_active_source_targets():
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert config["tool"]["mypy"]["files"] == [
        "celery_app.py",
        "common",
        "conf",
        "dags",
        "download",
        "factor",
        "forecast_snapshot",
        "fund",
        "monitor",
        "ocr",
        "paper_trading",
        "storage",
        "task",
        "tools",
        "trigger",
        "top10_floatholder",
        "utility",
    ]
