import conf
from stock import load_stock_history_data

conf.config = conf.parse_config()

stock_id = '000001'
start_date = '20230201'
end_date = '20230401'

df = load_stock_history_data(stock_id, start_date, end_date)
print(df)
