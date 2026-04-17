import importlib
import sys

MODULES_TO_RESET = [
    "monitor.price_fetcher",
    "stock",
    "stock.data",
    "stock.data.eastmoney",
    "stock.data.eastmoney.fetch_close_price",
]


def test_price_fetcher_import_does_not_require_scipy(monkeypatch):
    cached_modules = {}
    for module_name in MODULES_TO_RESET:
        module = sys.modules.pop(module_name, None)
        if module is not None:
            cached_modules[module_name] = module

    monkeypatch.setitem(sys.modules, "scipy", None)

    try:
        module = importlib.import_module("monitor.price_fetcher")
        assert callable(module.fetch_close_price)
    finally:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)
        sys.modules.update(cached_modules)
