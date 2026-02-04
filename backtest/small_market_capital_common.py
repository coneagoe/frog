import pandas as pd

from common.const import COL_DATE, COL_IPO_DATE, COL_STOCK_ID
from storage import get_storage, tb_name_a_stock_basic, tb_name_daily_basic_a_stock


def load_daily_basic(date: str, stock_ids: list[str]) -> pd.DataFrame:
    """加载指定日期的daily_basic数据（PB, PE, 市值等）

    Args:
        date: 日期，格式YYYY-MM-DD
        stock_ids: 股票代码列表

    Returns:
        pd.DataFrame: 包含PB, PE, 市值等数据的DataFrame
    """
    storage = get_storage()

    sql = f"""
    SELECT * FROM "{tb_name_daily_basic_a_stock}"
    WHERE "{COL_DATE}" = %s
    AND "{COL_STOCK_ID}" = ANY(%s)
    """

    df = pd.read_sql(sql, storage.engine, params=(date, stock_ids))  # type: ignore[arg-type]
    return df


def load_stock_basic(stock_ids: list[str]) -> pd.DataFrame:
    """加载股票基本信息（用于获取上市日期）

    Args:
        stock_ids: 股票代码列表

    Returns:
        pd.DataFrame: 包含上市日期等信息的DataFrame
    """
    storage = get_storage()

    sql = f"""
    SELECT "{COL_STOCK_ID}", "{COL_IPO_DATE}" FROM "{tb_name_a_stock_basic}"
    WHERE "{COL_STOCK_ID}" = ANY(%s)
    """

    df = pd.read_sql(sql, storage.engine, params=(stock_ids,))  # type: ignore[arg-type]
    return df
