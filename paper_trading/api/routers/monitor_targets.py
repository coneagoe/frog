from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from monitor.domain_enums import MonitorConditionType, MonitorFrequency, MonitorMarket
from monitor.monitor_health_service import MonitorTargetHealthService
from monitor.monitor_target_service import MonitorTargetService
from paper_trading.api.deps import require_browser_user, require_csrf
from paper_trading.api.monitor_target_storage import ManualMonitorTargetStorage
from paper_trading.schemas.monitor_targets import (
    CreateMonitorTargetRequest,
    MonitorTargetHealthResponse,
    MonitorTargetResponse,
    SetMonitorTargetEnabledRequest,
    UpdateMonitorTargetRequest,
)
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
    return MonitorTargetResponse.model_validate(cast(dict[str, object], result["data"]))


def _raise_for_result(result: dict) -> None:
    if result["success"]:
        return
    status_code = status.HTTP_404_NOT_FOUND if result["code"] == "NOT_FOUND" else status.HTTP_422_UNPROCESSABLE_CONTENT
    raise HTTPException(status_code=status_code, detail=result["message"])


@router.get("", response_model=list[MonitorTargetResponse])
def list_monitor_targets(
    service: ServiceDep,
    frequency: MonitorFrequency | None = None,
    enabled: bool | None = None,
    market: MonitorMarket | None = None,
    condition_type: MonitorConditionType | None = Query(default=None),
) -> list[MonitorTargetResponse]:
    result = service.list_targets(
        frequency=frequency,
        enabled=enabled,
        market=market,
        condition_type=condition_type,
    )
    _raise_for_result(result)
    return [MonitorTargetResponse.model_validate(target) for target in result["data"]]


@router.post("", response_model=MonitorTargetResponse)
def create_monitor_target(
    request: CreateMonitorTargetRequest,
    service: ServiceDep,
    _: None = Depends(require_csrf),
) -> MonitorTargetResponse:
    return _response(service.add_target(**request.model_dump()))


@router.get("/health", response_model=MonitorTargetHealthResponse)
def get_monitor_targets_health(service: HealthServiceDep) -> MonitorTargetHealthResponse:
    return MonitorTargetHealthResponse.model_validate(service.get_health())


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
