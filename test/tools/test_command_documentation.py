from pathlib import Path

FILES_WITHOUT_POETRY = [
    "Dockerfile",
    "README.md",
    "CLAUDE.md",
    "docs/paper_trading.md",
    "factor/alphapurify_ssf_ratio.py",
    "factor/alphapurify_ssf_ratio_change.py",
    "factor/alphapurify_ssf_count.py",
    "factor/alphapurify_volatility.py",
    "factor/alphapurify_momentum.py",
    "factor/alphapurify_obos.py",
    "docs/superpowers/plans/2026-06-16-paper-trading-backend.md",
    "docs/superpowers/plans/2026-06-16-paper-trading-frontend.md",
]


def test_selected_docs_and_hints_no_longer_reference_poetry():
    for file_name in FILES_WITHOUT_POETRY:
        content = Path(file_name).read_text(encoding="utf-8")
        assert "poetry" not in content.lower(), file_name


def test_dockerfile_installs_with_uv():
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "uv" in content
    assert "poetry" not in content.lower()
    assert "uv.lock" in content
