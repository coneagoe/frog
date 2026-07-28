from collections.abc import Collection
from typing import TypeVar

from pydantic import BaseModel

from paper_trading.storage.security_metadata import SecurityNameProvider

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


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
