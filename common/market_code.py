from typing import Literal

Market = Literal["A", "ETF", "HK"]

_SZ_A_PREFIXES = ("000", "001", "002", "003", "300", "301")
_SZ_ETF_PREFIXES = ("159", "160", "161", "162", "163", "164")


def to_tushare_code(code: str, market: Market) -> str:
    if market not in ("A", "ETF", "HK"):
        raise ValueError(f"Unknown market: {market}")
    if not code or not all("0" <= character <= "9" for character in code):
        raise ValueError(f"Invalid {market} code: {code}")

    if market == "HK":
        if len(code) != 5:
            raise ValueError(f"Invalid HK code: {code}")
        return f"{code}.HK"

    if len(code) != 6:
        raise ValueError(f"Invalid {market} code: {code}")

    if market == "A":
        if code.startswith("6"):
            suffix = ".SH"
        elif code.startswith(("4", "8")):
            suffix = ".BJ"
        elif code.startswith(_SZ_A_PREFIXES):
            suffix = ".SZ"
        else:
            raise ValueError(f"Unsupported A code prefix: {code}")
    elif code.startswith("5"):
        suffix = ".SH"
    elif code.startswith(_SZ_ETF_PREFIXES):
        suffix = ".SZ"
    else:
        raise ValueError(f"Unsupported ETF code prefix: {code}")

    return f"{code}{suffix}"
