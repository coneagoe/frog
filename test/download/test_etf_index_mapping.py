import pytest

from download.core_indexes import CORE_INDEX_TS_CODES, CoreIndexGroup
from download.etf_index_mapping import (
    ETF_CORE_INDEX_GROUPS,
    UNSUPPORTED_ETF_CODES,
    ETFIndexMappingStatus,
    normalize_etf_code,
    prepare_etf_flow_index_context,
    resolve_etf_index,
)


def test_normalize_etf_code_accepts_bare_and_suffixed_provider_codes():
    assert normalize_etf_code("510300") == "510300"
    assert normalize_etf_code("510300.SH") == "510300"
    assert normalize_etf_code("159915.SZ") == "159915"
    assert normalize_etf_code(" 588000.SH ") == "588000"


def test_normalize_etf_code_rejects_invalid_values():
    assert normalize_etf_code("") is None
    assert normalize_etf_code("51030") is None
    assert normalize_etf_code("5103000") is None
    assert normalize_etf_code("ABCDEF") is None
    assert normalize_etf_code("510300.HK") is None
    assert normalize_etf_code("510300.SH.EXTRA") is None


def test_resolve_core_etf_examples_to_pinned_indexes():
    cases = {
        "510300.SH": (CoreIndexGroup.CSI_300, "000300.SH", "沪深300"),
        "510310": (CoreIndexGroup.CSI_300, "000300.SH", "沪深300"),
        "159919.SZ": (CoreIndexGroup.CSI_300, "000300.SH", "沪深300"),
        "510050.SH": (CoreIndexGroup.SSE_50, "000016.SH", "上证50"),
        "510180.SH": (CoreIndexGroup.SSE_180, "000010.SH", "上证180"),
        "510500.SH": (CoreIndexGroup.CSI_500, "000905.SH", "中证500"),
        "515800.SH": (CoreIndexGroup.CSI_800, "000906.SH", "中证800"),
        "512100.SH": (CoreIndexGroup.CSI_1000, "000852.SH", "中证1000"),
        "159845.SZ": (CoreIndexGroup.CSI_1000, "000852.SH", "中证1000"),
        "159915.SZ": (CoreIndexGroup.CHINEXT, "399006.SZ", "创业板指"),
        "588000.SH": (CoreIndexGroup.STAR_50, "000688.SH", "科创50"),
        "588080.SH": (CoreIndexGroup.STAR_50, "000688.SH", "科创50"),
        "159901.SZ": (CoreIndexGroup.SZSE_100, "399330.SZ", "深证100"),
    }

    for etf_code, (group, ts_code, display_name) in cases.items():
        result = resolve_etf_index(etf_code)

        assert result.status == ETFIndexMappingStatus.MAPPED
        assert result.normalized_etf_code == etf_code.split(".")[0]
        assert result.core_index_group == group
        assert result.index_ts_code == ts_code
        assert result.index_display_name == display_name
        assert result.diagnostic_reason == "mapped_to_supported_core_index"


def test_resolve_invalid_code_returns_invalid_diagnostic_without_index():
    result = resolve_etf_index("not-an-etf")

    assert result.status == ETFIndexMappingStatus.INVALID_CODE
    assert result.normalized_etf_code is None
    assert result.core_index_group is None
    assert result.index_ts_code is None
    assert result.index_display_name is None
    assert result.diagnostic_reason == "invalid_etf_code"


def test_resolve_known_unsupported_etf_returns_unsupported_diagnostic():
    result = resolve_etf_index("510880.SH")

    assert result.status == ETFIndexMappingStatus.UNSUPPORTED_ETF
    assert result.normalized_etf_code == "510880"
    assert result.core_index_group is None
    assert result.index_ts_code is None
    assert result.index_display_name is None
    assert result.diagnostic_reason == "unsupported_etf_without_trusted_core_index_mapping"


def test_resolve_valid_but_absent_etf_returns_missing_mapping_diagnostic():
    result = resolve_etf_index("560000.SH")

    assert result.status == ETFIndexMappingStatus.MISSING_MAPPING
    assert result.normalized_etf_code == "560000"
    assert result.core_index_group is None
    assert result.index_ts_code is None
    assert result.index_display_name is None
    assert result.diagnostic_reason == "missing_etf_index_mapping"


def test_etf_core_index_groups_are_immutable():
    with pytest.raises(TypeError):
        ETF_CORE_INDEX_GROUPS["560000"] = CoreIndexGroup.CSI_300  # type: ignore[index]


def test_unsupported_etf_codes_do_not_overlap_mapped_codes():
    assert set(UNSUPPORTED_ETF_CODES).isdisjoint(ETF_CORE_INDEX_GROUPS)


def test_all_mapped_etfs_point_to_supported_core_indexes():
    assert set(ETF_CORE_INDEX_GROUPS.values()).issubset(set(CORE_INDEX_TS_CODES))


def test_prepare_etf_flow_index_context_returns_mapped_index_identifier():
    context = prepare_etf_flow_index_context("510300.SH")

    assert context.should_calculate is True
    assert context.etf_code == "510300.SH"
    assert context.normalized_etf_code == "510300"
    assert context.index_ts_code == "000300.SH"
    assert context.diagnostic.status == ETFIndexMappingStatus.MAPPED
    assert context.diagnostic.diagnostic_reason == "mapped_to_supported_core_index"


def test_prepare_etf_flow_index_context_returns_diagnostic_for_missing_mapping():
    context = prepare_etf_flow_index_context("560000.SH")

    assert context.should_calculate is False
    assert context.etf_code == "560000.SH"
    assert context.normalized_etf_code == "560000"
    assert context.index_ts_code is None
    assert context.diagnostic.status == ETFIndexMappingStatus.MISSING_MAPPING
    assert context.diagnostic.diagnostic_reason == "missing_etf_index_mapping"


def test_prepare_etf_flow_index_context_returns_diagnostic_for_unsupported_mapping():
    context = prepare_etf_flow_index_context("510880.SH")

    assert context.should_calculate is False
    assert context.normalized_etf_code == "510880"
    assert context.index_ts_code is None
    assert context.diagnostic.status == ETFIndexMappingStatus.UNSUPPORTED_ETF
    assert context.diagnostic.diagnostic_reason == "unsupported_etf_without_trusted_core_index_mapping"


def test_prepare_etf_flow_index_context_returns_diagnostic_for_invalid_code():
    context = prepare_etf_flow_index_context("bad-code")

    assert context.should_calculate is False
    assert context.normalized_etf_code is None
    assert context.index_ts_code is None
    assert context.diagnostic.status == ETFIndexMappingStatus.INVALID_CODE
    assert context.diagnostic.diagnostic_reason == "invalid_etf_code"
