from enum import Enum

COL_STOCK_ID = "股票代码"
COL_STOCK_NAME = "股票名称"
COL_ETF_ID = "基金代码"
COL_ETF_NAME = "基金简称"
COL_POSITION = "持仓"
COL_POSITION_AVAILABLE = "可用"
COL_MARKET_VALUE = "市值"
COL_CURRENT_PRICE = "现价"
COL_COST = "成本"
COL_PROFIT = "浮动盈亏"
COL_PROFIT_RATE = "盈亏(%)"
COL_DATE = "日期"
COL_OPEN = "开盘"
COL_CLOSE = "收盘"
COL_PRE_CLOSE = "昨日收盘价"
COL_HIGH = "最高"
COL_LOW = "最低"
COL_UP_LIMIT = "涨停价"
COL_DOWN_LIMIT = "跌停价"
COL_VOLUME = "成交量"
COL_AMOUNT = "成交额"
COL_TURNOVER_RATE = "换手率(%)"
COL_TURNOVER_RATE_F = "自由流通换手率(%)"
COL_VOLUME_RATIO = "量比"
COL_CHANGE_RATE = "涨跌幅(%)"
COL_PE = "市盈率"
COL_PE_TTM = "市盈率(TTM)"
COL_PB = "市净率"
COL_PB_MRQ = "市净率(MRQ)"
COL_PS = "市销率"
COL_PS_TTM = "市销率(TTM)"
COL_DV_RATIO = "股息率(%)"
COL_DV_TTM = "股息率(TTM)"
COL_TOTAL_SHARE = "总股本"
COL_FLOAT_SHARE = "流通股本"
COL_FREE_SHARE = "自由流通股本"
COL_TOTAL_MV = "总市值"
COL_CIRC_MV = "流通市值"
COL_PCF_NCF_TTM = "市现率(TTM)"
COL_IS_ST = "是否ST"
COL_BUY_COUNT = "买入数量"
COL_BUYING_PRICE = "买入价格"
COL_SUPPORT = "支撑"
COL_RESISTANCE = "阻力"
COL_ADJUSTED_STOPLOSS = "调整后/移动止损价格"
COL_ADJUSTED_TAKE_PROFIT = "调整后止盈价格"
COL_STOPLOSS_PERCENT = "止损(%)"
COL_TAKE_PROFIT_PERCENT = "止盈(%)"
COL_PROFIT_STOPLOSS_RATE = "盈亏比"
COL_TIME = "时间"
COL_BUY_AMOUNT = "买入金额"
COL_IPO_DATE = "上市日期"
COL_DELISTING_DATE = "退市日期"
COL_LIMIT_STATUS = "涨跌停状态"

# TuShare suspend_d
COL_SUSPEND_TIMING = "停牌时间段"
COL_SUSPEND_TYPE = "停复牌类型"

# TuShare stock_basic
COL_TS_CODE = "TS代码"
COL_AREA = "地域"
COL_INDUSTRY = "所属行业"
COL_FULLNAME = "股票全称"
COL_ENNAME = "英文全称"
COL_CN_SPELL = "拼音缩写"
COL_MARKET = "市场类型"
COL_EXCHANGE = "交易所"
COL_CURR_TYPE = "交易货币"
COL_LIST_STATUS = "上市状态"
COL_IS_HS = "是否沪深港通"
COL_ACT_NAME = "实控人姓名"
COL_ACT_ENT_TYPE = "实控人企业性质"

COL_MONITOR_PRICE = "监控价格"
COL_COMMENT = "comment"
# platforms to be notified
COL_EMAIL = "email"
COL_MOBILE = "mobile"
COL_PC = "pc"


# database
DATABASE_NAME = "frog.db"


class AdjustType(Enum):
    BFQ = ""  # 不复权
    QFQ = "qfq"  # 前复权
    HFQ = "hfq"  # 后复权


class PeriodType(Enum):
    DAILY = "daily"
    WEEKLY = "week"
    MONTHLY = "month"


class SecurityType(Enum):
    STOCK = "stock"
    ETF = "etf"
    A_INDEX = "a_index"
    US_INDEX = "us_index"
    HK_GGT_STOCK = "hk_ggt_stock"
    AUTO = "auto"
