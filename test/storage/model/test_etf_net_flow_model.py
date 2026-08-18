from common.const import (
    COL_DATE,
    COL_ETF_ESTIMATED_TRADED_PRICE,
    COL_ETF_ID,
    COL_ETF_NET_FLOW_AMOUNT,
    COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    COL_ETF_NET_SHARE_CHANGE,
    COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
    COL_ETF_TOTAL_SHARE,
    COL_INDEX_CODE,
    COL_INDEX_TURNOVER_AMOUNT,
)
from storage.model import ETFNetFlow, tb_name_etf_net_flow


def test_etf_net_flow_table_name_primary_keys_and_columns():
    table = ETFNetFlow.__table__

    assert tb_name_etf_net_flow == "etf_net_flow"
    assert table.name == "etf_net_flow"
    assert list(table.primary_key.columns.keys()) == [COL_ETF_ID, COL_DATE]
    assert set(table.columns.keys()) == {
        COL_ETF_ID,
        COL_DATE,
        COL_ETF_TOTAL_SHARE,
        COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE,
        COL_ETF_NET_SHARE_CHANGE,
        COL_ETF_ESTIMATED_TRADED_PRICE,
        COL_ETF_NET_FLOW_AMOUNT,
        COL_INDEX_CODE,
        COL_INDEX_TURNOVER_AMOUNT,
        COL_ETF_NET_FLOW_TO_INDEX_TURNOVER_RATIO,
    }


def test_etf_net_flow_unit_comments_are_explicit():
    table = ETFNetFlow.__table__

    assert "原始" in table.c[COL_ETF_TOTAL_SHARE].comment
    assert "原始" in table.c[COL_ETF_PREV_EFFECTIVE_TOTAL_SHARE].comment
    assert "元/份" in table.c[COL_ETF_ESTIMATED_TRADED_PRICE].comment
    assert "元" in table.c[COL_ETF_NET_FLOW_AMOUNT].comment
    assert "千元" in table.c[COL_INDEX_TURNOVER_AMOUNT].comment
