import os

STOCK_HISTORY_PROVIDER_ENV = "DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"
DEFAULT_STOCK_HISTORY_PROVIDER_ORDER = ("baostock", "tushare", "akshare")
VALID_STOCK_HISTORY_PROVIDERS = frozenset(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)


def parse_stock_history_provider_order(value: str | None = None) -> list[str]:
    raw_value = value if value is not None else os.getenv(STOCK_HISTORY_PROVIDER_ENV)
    if raw_value is None:
        raw_value = ",".join(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)

    providers: list[str] = []
    seen: set[str] = set()
    for raw_provider in raw_value.split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        if provider not in VALID_STOCK_HISTORY_PROVIDERS:
            raise ValueError(f"Unsupported stock history provider: {provider}")
        if provider in seen:
            continue
        seen.add(provider)
        providers.append(provider)

    if not providers:
        raise ValueError("stock history provider order is empty")
    return providers
