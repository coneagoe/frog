import importlib
import sys

MODULES_TO_RESET = [
    "monitor.price_fetcher",
    "tushare",
]


def test_price_fetcher_import_stays_lazy_without_tushare(monkeypatch):
    cached_modules = {}
    for module_name in MODULES_TO_RESET:
        module = sys.modules.pop(module_name, None)
        if module is not None:
            cached_modules[module_name] = module

    monkeypatch.setitem(sys.modules, "tushare", None)

    try:
        module = importlib.import_module("monitor.price_fetcher")
        assert callable(module.fetch_price)
        assert callable(module.fetch_current_price)
    finally:
        for module_name in MODULES_TO_RESET:
            sys.modules.pop(module_name, None)
        sys.modules.update(cached_modules)
