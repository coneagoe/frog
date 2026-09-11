from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from monitor.domain_enums import MonitorConditionType, MonitorFrequency, MonitorMarket
from monitor.monitor_health_service import MonitorTargetHealthService
from monitor.monitor_target_service import MonitorTargetService
from paper_trading.api.deps import get_security_name_provider, require_browser_user, require_csrf
from paper_trading.api.monitor_target_storage import ManualMonitorTargetStorage
from paper_trading.schemas.monitor_targets import (
    CreateMonitorTargetRequest,
    MonitorTargetHealthItemResponse,
    MonitorTargetHealthResponse,
    MonitorTargetListResponse,
    MonitorTargetResponse,
    SetMonitorTargetEnabledRequest,
    UnifiedMonitorTargetResponse,
    UnifiedMonitorTargetResponseEnvelope,
    UpdateMonitorTargetRequest,
)
from paper_trading.storage.security_metadata import SecurityNameProvider
from storage import get_storage

router = APIRouter(
    prefix="/paper/monitor-targets",
    tags=["monitor-targets"],
    dependencies=[Depends(require_browser_user)],
)


def get_monitor_target_service() -> MonitorTargetService:
    return MonitorTargetService(storage=ManualMonitorTargetStorage(get_storage()))


def get_monitor_target_health_service() -> MonitorTargetHealthService:
    return MonitorTargetHealthService(storage=get_storage())


ServiceDep = Annotated[MonitorTargetService, Depends(get_monitor_target_service)]
HealthServiceDep = Annotated[MonitorTargetHealthService, Depends(get_monitor_target_health_service)]


def _response(result: dict) -> MonitorTargetResponse:
    _raise_for_result(result)
    response = MonitorTargetResponse.model_validate(cast(dict[str, object], result["data"]))
    if not isinstance(response, MonitorTargetResponse):
        raise TypeError("invalid monitor target response")
    return response


def _raise_for_result(result: dict) -> None:
    if result["success"]:
        return
    status_code = status.HTTP_404_NOT_FOUND if result["code"] == "NOT_FOUND" else status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=status_code, detail=result["message"])


def _enrichment_market(market: MonitorMarket) -> str:
    return {MonitorMarket.A: "a_share", MonitorMarket.HK: "hk_connect", MonitorMarket.ETF: "etf"}[market]


def _enrich_items(items: list[dict[str, object]], response_type: Any, provider: SecurityNameProvider) -> list[Any]:
    responses = [response_type.model_validate(item) for item in items]
    try:
        names = provider.resolve_names(
            {(_enrichment_market(response.market), response.stock_code) for response in responses}
        )
    except Exception:
        names = {}
    return [
        response.model_copy(
            update={
                "stock_name": name
                if isinstance(name := names.get((_enrichment_market(response.market), response.stock_code)), str)
                and name.strip()
                else None
            }
        )
        for response in responses
    ]


@router.get("", response_model=UnifiedMonitorTargetResponseEnvelope)
def list_monitor_targets(
    service: ServiceDep,
    frequency: MonitorFrequency | None = None,
    enabled: bool | None = None,
    market: MonitorMarket | None = None,
    condition_type: MonitorConditionType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort: Literal["default", "stock_code_asc", "stock_code_desc"] = Query(default="default"),
    provider: SecurityNameProvider = Depends(get_security_name_provider),
) -> UnifiedMonitorTargetResponseEnvelope:
    if page_size not in {25, 50, 100}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="page_size must be 25, 50, or 100",
        )
    result = service.list_unified_targets(
        frequency=frequency,
        enabled=enabled,
        market=market,
        condition_type=condition_type,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    _raise_for_result(result)
    data = cast(dict[str, object], result["data"])
    enriched = _enrich_items(cast(list[dict[str, object]], data["items"]), UnifiedMonitorTargetResponse, provider)
    response = UnifiedMonitorTargetResponseEnvelope.model_validate(
        data | {"items": enriched}
    )
    if not isinstance(response, UnifiedMonitorTargetResponseEnvelope):
        raise TypeError("invalid monitor target list response")
    return response


@router.post("", response_model=MonitorTargetResponse)
def create_monitor_target(
    request: CreateMonitorTargetRequest,
    service: ServiceDep,
    _: None = Depends(require_csrf),
) -> MonitorTargetResponse:
    return _response(service.add_target(**request.model_dump()))


@router.get("/health", response_model=MonitorTargetHealthResponse)
def get_monitor_targets_health(
    service: HealthServiceDep,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    provider: SecurityNameProvider = Depends(get_security_name_provider),
) -> MonitorTargetHealthResponse:
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</paper/monitor-targets>; rel="successor-version"'
    result = service.get_health(page=page, page_size=page_size)
    response = MonitorTargetHealthResponse.model_validate(
        {
            **result,
            "items": _enrich_items(
                cast(list[dict[str, object]], result["items"]), MonitorTargetHealthItemResponse, provider
            ),
        }
    )
    if not isinstance(response, MonitorTargetHealthResponse):
        raise TypeError("invalid monitor target health response")
    return response


@router.get("/manual", response_model=MonitorTargetListResponse, deprecated=True)
def list_manual_monitor_targets_compat(
    service: ServiceDep,
    response: Response,
    frequency: MonitorFrequency | None = None,
    enabled: bool | None = None,
    market: MonitorMarket | None = None,
    condition_type: MonitorConditionType | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    provider: SecurityNameProvider = Depends(get_security_name_provider),
) -> MonitorTargetListResponse:
    response.headers["Deprecation"] = "true"
    result = service.list_targets(
        frequency=frequency,
        enabled=enabled,
        market=market,
        condition_type=condition_type,
        page=page,
        page_size=page_size,
    )
    _raise_for_result(result)
    data = cast(dict[str, object], result["data"])
    return MonitorTargetListResponse.model_validate(
        data | {"items": _enrich_items(cast(list[dict[str, object]], data["items"]), MonitorTargetResponse, provider)}
    )


@router.get("/{target_id}", response_model=MonitorTargetResponse)
def get_monitor_target(target_id: int, service: ServiceDep) -> MonitorTargetResponse:
    return _response(service.get_target(target_id))


@router.patch("/{target_id}", response_model=MonitorTargetResponse)
def update_monitor_target(
    target_id: int,
    request: UpdateMonitorTargetRequest,
    service: ServiceDep,
    _: None = Depends(require_csrf),
) -> MonitorTargetResponse:
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="at least one update is required")
    return _response(service.update_target(target_id, **updates))


@router.patch("/{target_id}/enabled", response_model=MonitorTargetResponse)
def set_monitor_target_enabled(
    target_id: int,
    request: SetMonitorTargetEnabledRequest,
    service: ServiceDep,
    _: None = Depends(require_csrf),
) -> MonitorTargetResponse:
    return _response(service.set_target_status(target_id, request.enabled))


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor_target(
    target_id: int,
    service: ServiceDep,
    _: None = Depends(require_csrf),
) -> Response:
    _raise_for_result(service.remove_target(target_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
