from pathlib import Path


def test_pre_commit_uses_ruff_hooks():
    content = Path(".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "astral-sh/ruff-pre-commit" in content
    assert "id: ruff-format" in content
    assert "id: ruff" in content
    assert "github.com/psf/black" not in content
    assert "github.com/pycqa/isort" not in content
    assert "github.com/pycqa/flake8" not in content


def test_ci_uses_uv_instead_of_poetry():
    content = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "astral-sh/setup-uv" in content
    assert "uv sync --group dev" in content
    assert "uv run pre-commit run --all-files" in content
    assert "uv run pytest test" in content
    assert "install-poetry" not in content
    assert "poetry install" not in content
