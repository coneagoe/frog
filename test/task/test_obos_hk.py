import importlib

import pytest

import conf
from common.obos_hk_runner import ObosHkSkip


def test_obos_hk_returns_legacy_skip_string(monkeypatch):
    module = importlib.import_module("task.obos_hk")

    monkeypatch.setattr(conf, "parse_config", lambda: None)
    monkeypatch.setattr(module, "run_obos_hk_backtest", lambda **kwargs: (_ for _ in ()).throw(ObosHkSkip("download result is fail")))

    assert module.obos_hk.run() == "Skip: download result is fail"


def test_obos_hk_returns_market_closed_skip_string(monkeypatch):
    module = importlib.import_module("task.obos_hk")

    monkeypatch.setattr(conf, "parse_config", lambda: None)
    monkeypatch.setattr(module, "run_obos_hk_backtest", lambda **kwargs: (_ for _ in ()).throw(ObosHkSkip("Market is closed today.")))

    assert module.obos_hk.run() == "Market is closed today."


def test_obos_hk_propagates_runtime_failures(monkeypatch):
    module = importlib.import_module("task.obos_hk")

    monkeypatch.setattr(conf, "parse_config", lambda: None)
    monkeypatch.setattr(module, "run_obos_hk_backtest", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        module.obos_hk.run()
