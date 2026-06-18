from pathlib import Path

UNSUPPORTED_AGENT_FIELDS = {"argument-hint", "handoffs", "mode", "hidden"}
AGENT_DIR = Path(".github/agents")


def _load_frontmatter(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    _, frontmatter, _ = content.split("---", 2)
    parsed: dict[str, object] = {}

    for line in frontmatter.splitlines():
        if not line or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        parsed[key.strip()] = value.strip()

    return parsed


def test_custom_agents_use_supported_frontmatter_only():
    agent_files = sorted(AGENT_DIR.glob("*.agent.md"))

    assert agent_files

    offenders = {
        str(path): sorted(UNSUPPORTED_AGENT_FIELDS.intersection(_load_frontmatter(path)))
        for path in agent_files
        if UNSUPPORTED_AGENT_FIELDS.intersection(_load_frontmatter(path))
    }

    assert offenders == {}
