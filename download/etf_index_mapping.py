from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from download.core_indexes import CORE_INDEX_DISPLAY_NAMES, CORE_INDEX_TS_CODES, CoreIndexGroup


class ETFIndexMappingStatus(StrEnum):
    MAPPED = "mapped"
    UNSUPPORTED_ETF = "unsupported_etf"
    MISSING_MAPPING = "missing_mapping"
    INVALID_CODE = "invalid_code"


@dataclass(frozen=True)
class ETFIndexResolution:
    etf_code: str
    normalized_etf_code: str | None
    status: ETFIndexMappingStatus
    core_index_group: CoreIndexGroup | None
    index_ts_code: str | None
    index_display_name: str | None
    diagnostic_reason: str


@dataclass(frozen=True)
class ETFFlowIndexContext:
    etf_code: str
    normalized_etf_code: str | None
    should_calculate: bool
    index_ts_code: str | None
    diagnostic: ETFIndexResolution


ETF_CORE_INDEX_GROUPS = MappingProxyType(
    {
        "510300": CoreIndexGroup.CSI_300,
        "510310": CoreIndexGroup.CSI_300,
        "159919": CoreIndexGroup.CSI_300,
        "510050": CoreIndexGroup.SSE_50,
        "510180": CoreIndexGroup.SSE_180,
        "510500": CoreIndexGroup.CSI_500,
        "515800": CoreIndexGroup.CSI_800,
        "512100": CoreIndexGroup.CSI_1000,
        "159845": CoreIndexGroup.CSI_1000,
        "159915": CoreIndexGroup.CHINEXT,
        "588000": CoreIndexGroup.STAR_50,
        "588080": CoreIndexGroup.STAR_50,
        "159901": CoreIndexGroup.SZSE_100,
    }
)

UNSUPPORTED_ETF_CODES = frozenset({"510880"})


def normalize_etf_code(etf_code: str) -> str | None:
    candidate = str(etf_code).strip()
    if not candidate:
        return None

    parts = candidate.split(".")
    if len(parts) == 1:
        bare_code = parts[0]
    elif len(parts) == 2 and parts[1] in {"SH", "SZ"}:
        bare_code = parts[0]
    else:
        return None

    if len(bare_code) != 6 or not bare_code.isdigit():
        return None
    return bare_code


def resolve_etf_index(etf_code: str) -> ETFIndexResolution:
    normalized_code = normalize_etf_code(etf_code)
    if normalized_code is None:
        return ETFIndexResolution(
            etf_code=etf_code,
            normalized_etf_code=None,
            status=ETFIndexMappingStatus.INVALID_CODE,
            core_index_group=None,
            index_ts_code=None,
            index_display_name=None,
            diagnostic_reason="invalid_etf_code",
        )

    if normalized_code in UNSUPPORTED_ETF_CODES:
        return ETFIndexResolution(
            etf_code=etf_code,
            normalized_etf_code=normalized_code,
            status=ETFIndexMappingStatus.UNSUPPORTED_ETF,
            core_index_group=None,
            index_ts_code=None,
            index_display_name=None,
            diagnostic_reason="unsupported_etf_without_trusted_core_index_mapping",
        )

    group = ETF_CORE_INDEX_GROUPS.get(normalized_code)
    if group is None:
        return ETFIndexResolution(
            etf_code=etf_code,
            normalized_etf_code=normalized_code,
            status=ETFIndexMappingStatus.MISSING_MAPPING,
            core_index_group=None,
            index_ts_code=None,
            index_display_name=None,
            diagnostic_reason="missing_etf_index_mapping",
        )

    return ETFIndexResolution(
        etf_code=etf_code,
        normalized_etf_code=normalized_code,
        status=ETFIndexMappingStatus.MAPPED,
        core_index_group=group,
        index_ts_code=CORE_INDEX_TS_CODES[group],
        index_display_name=CORE_INDEX_DISPLAY_NAMES[group],
        diagnostic_reason="mapped_to_supported_core_index",
    )


def prepare_etf_flow_index_context(etf_code: str) -> ETFFlowIndexContext:
    diagnostic = resolve_etf_index(etf_code)
    return ETFFlowIndexContext(
        etf_code=etf_code,
        normalized_etf_code=diagnostic.normalized_etf_code,
        should_calculate=diagnostic.status == ETFIndexMappingStatus.MAPPED,
        index_ts_code=diagnostic.index_ts_code,
        diagnostic=diagnostic,
    )
