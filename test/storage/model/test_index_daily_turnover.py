from common.const import COL_AMOUNT, COL_CLOSE, COL_DATE, COL_INDEX_CODE
from storage.model import IndexDailyTurnover, tb_name_index_daily_turnover


def test_index_daily_turnover_table_name_primary_keys_and_comments():
    table = IndexDailyTurnover.__table__

    assert tb_name_index_daily_turnover == "index_daily_turnover"
    assert table.name == "index_daily_turnover"
    assert [column.name for column in table.primary_key.columns] == [COL_INDEX_CODE, COL_DATE]
    assert table.c[COL_CLOSE].comment == "Tushare index_daily close，收盘点位"
    assert table.c[COL_AMOUNT].comment == "Tushare index_daily amount，成交额（千元）"
