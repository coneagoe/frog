import tomllib
from pathlib import Path


def test_alphapurify_moves_out_of_default_dependencies():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = data["project"]["dependencies"]
    assert not any(str(item).startswith("alphapurify") for item in dependencies)

    dependency_groups = data.get("dependency-groups", {})
    assert "research" in dependency_groups
    assert any(str(item).startswith("alphapurify") for item in dependency_groups["research"])


def test_readme_documents_research_group_install():
    content = Path("README.md").read_text(encoding="utf-8")

    assert "uv sync --group research" in content
