from common.const import COL_CLOSE, COL_DATE, COL_ETF_ID
from storage.model import ETFShareSize, tb_name_etf_share_size


def test_etf_share_size_table_name_and_primary_keys():
    table = ETFShareSize.__table__

    assert tb_name_etf_share_size == "etf_share_size"
    assert table.name == "etf_share_size"
    assert list(table.primary_key.columns.keys()) == [COL_ETF_ID, COL_DATE]


def test_etf_share_size_documents_raw_provider_units():
    table = ETFShareSize.__table__

    assert table.c[COL_CLOSE].comment == "Tushare etf_share_size close，原始单位"
    assert "Tushare etf_share_size total_share" in table.c["总份额"].comment
    assert "原始单位" in table.c["总份额"].comment
    assert "Tushare etf_share_size total_size" in table.c["总规模"].comment
    assert "原始单位" in table.c["总规模"].comment
