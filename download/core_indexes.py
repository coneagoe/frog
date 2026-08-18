from enum import StrEnum
from types import MappingProxyType


class CoreIndexGroup(StrEnum):
    CSI_300 = "csi_300"
    SSE_50 = "sse_50"
    SSE_180 = "sse_180"
    CSI_500 = "csi_500"
    CSI_800 = "csi_800"
    CSI_1000 = "csi_1000"
    CHINEXT = "chinext"
    STAR_50 = "star_50"
    SZSE_100 = "szse_100"


CORE_INDEX_TS_CODES = MappingProxyType(
    {
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
)


CORE_INDEX_DISPLAY_NAMES = MappingProxyType(
    {
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
)
