import os
import sys
from configparser import ConfigParser

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from conf.global_settings import parse_common_config  # noqa: E402


def test_parse_common_config_does_not_read_qingguo_proxy_credentials_from_config(monkeypatch):
    monkeypatch.delenv("QG_PROXY_KEY", raising=False)
    monkeypatch.delenv("QG_PROXY_PWD", raising=False)
    config = ConfigParser()
    config["common"] = {"qg_proxy_key": "test-key", "qg_proxy_pwd": "test-pwd"}

    parse_common_config(config)

    assert "QG_PROXY_KEY" not in os.environ
    assert "QG_PROXY_PWD" not in os.environ


def test_parse_common_config_preserves_qingguo_proxy_credentials_env(monkeypatch):
    monkeypatch.setenv("QG_PROXY_KEY", "env-key")
    monkeypatch.setenv("QG_PROXY_PWD", "env-pwd")
    config = ConfigParser()
    config["common"] = {"qg_proxy_key": "config-key", "qg_proxy_pwd": "config-pwd"}

    parse_common_config(config)

    assert os.environ["QG_PROXY_KEY"] == "env-key"
    assert os.environ["QG_PROXY_PWD"] == "env-pwd"
