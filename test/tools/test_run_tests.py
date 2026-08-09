from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_defines_isolated_test_database():
    compose_file = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "  test_db:\n" in compose_file
    assert "timescale/timescaledb:latest-pg16" in compose_file
    assert 'ports: ["127.0.0.1:5433:5432"]' in compose_file
    assert "- /var/lib/postgresql/data" in compose_file
    assert "./docker/db:/var/lib/postgresql/data" in compose_file
