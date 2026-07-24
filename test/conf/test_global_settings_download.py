import os
import sys
from configparser import ConfigParser

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from conf.global_settings import parse_download_config  # noqa: E402


def test_parse_download_config_sets_stock_history_provider_order(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", raising=False)
    config = ConfigParser()
    config.read_dict({"download": {"process_count": "2", "stock_history_provider_order": "tushare,akshare"}})

    parse_download_config(config)

    assert os.environ["DOWNLOAD_PROCESS_COUNT"] == "2"
    assert os.environ["DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"] == "tushare,akshare"


def test_parse_download_config_uses_default_stock_history_provider_order(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", raising=False)
    config = ConfigParser()
    config.read_dict({"download": {"process_count": "4"}})

    parse_download_config(config)

    assert os.environ["DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"] == "baostock,tushare,akshare"


def test_parse_download_config_preserves_existing_env_var(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER", "tushare,akshare")
    config = ConfigParser()
    config.read_dict({"download": {"stock_history_provider_order": "baostock,tushare"}})

    parse_download_config(config)

    assert os.environ["DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"] == "tushare,akshare"


def test_parse_download_config_sets_default_hk_stock_history_provider_order(monkeypatch):
    config = ConfigParser()
    config["download"] = {}
    monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    parse_download_config(config)

    assert os.environ["DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"] == "yfinance,tushare,akshare"


def test_parse_download_config_sets_configured_hk_stock_history_provider_order(monkeypatch):
    config = ConfigParser()
    config["download"] = {"hk_stock_history_provider_order": "akshare,tushare"}
    monkeypatch.delenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", raising=False)

    parse_download_config(config)

    assert os.environ["DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"] == "akshare,tushare"


def test_parse_download_config_preserves_existing_hk_stock_history_provider_order(monkeypatch):
    config = ConfigParser()
    config["download"] = {"hk_stock_history_provider_order": "akshare,tushare"}
    monkeypatch.setenv("DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER", "tushare")

    parse_download_config(config)

    assert os.environ["DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"] == "tushare"
