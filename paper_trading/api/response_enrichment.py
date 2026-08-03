from collections.abc import Collection, Mapping
from typing import Any, Literal, Protocol, Self, TypeVar

from paper_trading.storage.security_metadata import SecurityNameProvider


class EnrichableResponse(Protocol):
    market: str
    symbol: str

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: Literal["allow", "ignore", "forbid"] | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self: ...

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self: ...


ResponseModel = TypeVar("ResponseModel", bound=EnrichableResponse)


def enrich_security_names(
    rows: Collection[object],
    response_type: type[ResponseModel],
    provider: SecurityNameProvider,
) -> list[ResponseModel]:
    responses = [response_type.model_validate(row) for row in rows]
    securities = {(response.market, response.symbol) for response in responses}
    names = provider.resolve_names(securities)
    return [
        response.model_copy(update={"stock_name": names.get((response.market, response.symbol))})
        for response in responses
    ]
