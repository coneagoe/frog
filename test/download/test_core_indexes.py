from download.core_indexes import CORE_INDEX_TS_CODES, CoreIndexGroup


def test_core_index_mapping_pins_broad_market_codes():
    assert CORE_INDEX_TS_CODES == {
        CoreIndexGroup.CSI_300: "000300.SH",
        CoreIndexGroup.SSE_50: "000016.SH",
        CoreIndexGroup.SSE_180: "000010.SH",
        CoreIndexGroup.CSI_500: "000905.SH",
        CoreIndexGroup.CSI_800: "000906.SH",
        CoreIndexGroup.CSI_1000: "000852.SH",
        CoreIndexGroup.CHINEXT: "399006.SZ",
        CoreIndexGroup.STAR_50: "000688.SH",
        CoreIndexGroup.SZSE_100: "399330.SZ",
    }


def test_core_index_display_names_cover_pinned_groups():
    from download.core_indexes import CORE_INDEX_DISPLAY_NAMES

    assert CORE_INDEX_DISPLAY_NAMES == {
        CoreIndexGroup.CSI_300: "沪深300",
        CoreIndexGroup.SSE_50: "上证50",
        CoreIndexGroup.SSE_180: "上证180",
        CoreIndexGroup.CSI_500: "中证500",
        CoreIndexGroup.CSI_800: "中证800",
        CoreIndexGroup.CSI_1000: "中证1000",
        CoreIndexGroup.CHINEXT: "创业板指",
        CoreIndexGroup.STAR_50: "科创50",
        CoreIndexGroup.SZSE_100: "深证100",
    }


def test_core_index_display_names_match_turnover_mapping_keys():
    from download.core_indexes import CORE_INDEX_DISPLAY_NAMES

    assert set(CORE_INDEX_DISPLAY_NAMES) == set(CORE_INDEX_TS_CODES)
