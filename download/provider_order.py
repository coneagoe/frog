import os

STOCK_HISTORY_PROVIDER_ENV = "DOWNLOAD_STOCK_HISTORY_PROVIDER_ORDER"
DEFAULT_STOCK_HISTORY_PROVIDER_ORDER = ("baostock", "tushare", "akshare")
VALID_STOCK_HISTORY_PROVIDERS = frozenset(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)

HK_STOCK_HISTORY_PROVIDER_ENV = "DOWNLOAD_HK_STOCK_HISTORY_PROVIDER_ORDER"
DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER = ("akshare", "yfinance", "tushare")
VALID_HK_STOCK_HISTORY_PROVIDERS = frozenset(DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER)


def _parse_provider_order(
    *,
    raw_value: str,
    valid_providers: frozenset[str],
    unsupported_message: str,
    empty_message: str,
) -> list[str]:
    providers: list[str] = []
    seen: set[str] = set()
    for raw_provider in raw_value.split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        if provider not in valid_providers:
            raise ValueError(unsupported_message.format(provider=provider))
        if provider in seen:
            continue
        seen.add(provider)
        providers.append(provider)

    if not providers:
        raise ValueError(empty_message)
    return providers


def parse_stock_history_provider_order(value: str | None = None) -> list[str]:
    raw_value = value if value is not None else os.getenv(STOCK_HISTORY_PROVIDER_ENV)
    if raw_value is None:
        raw_value = ",".join(DEFAULT_STOCK_HISTORY_PROVIDER_ORDER)

    return _parse_provider_order(
        raw_value=raw_value,
        valid_providers=VALID_STOCK_HISTORY_PROVIDERS,
        unsupported_message="Unsupported stock history provider: {provider}",
        empty_message="stock history provider order is empty",
    )


def parse_hk_stock_history_provider_order(value: str | None = None) -> list[str]:
    raw_value = value if value is not None else os.getenv(HK_STOCK_HISTORY_PROVIDER_ENV)
    if raw_value is None:
        raw_value = ",".join(DEFAULT_HK_STOCK_HISTORY_PROVIDER_ORDER)

    return _parse_provider_order(
        raw_value=raw_value,
        valid_providers=VALID_HK_STOCK_HISTORY_PROVIDERS,
        unsupported_message="Unsupported HK stock history provider: {provider}",
        empty_message="HK stock history provider order is empty",
    )
