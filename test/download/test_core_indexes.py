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
