from pathlib import Path


def test_legacy_app_entrypoints_are_removed():
    assert not Path("frog_server.py").exists()
    assert not Path("tools/frog_cmd.py").exists()
