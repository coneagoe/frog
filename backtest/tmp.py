import os
import sys
import plotly.graph_objects as go
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conf     # noqa: E402
from stock import (
    COL_OPEN,
    COL_CLOSE,
    COL_HIGH,
    COL_LOW,
)
from common import (
    load_test_data,
)

conf.parse_config()


stock = "159985"   # 豆粕ETF

data = load_test_data(security_id=stock, period="daily", 
                      start_date="2023-10-01", end_date="2024-06-08")

fig = go.Figure(data=[go.Candlestick(x=data.index,
                                     open=data[COL_OPEN],
                                     high=data[COL_HIGH],
                                     low=data[COL_LOW],
                                     close=data[COL_CLOSE])])

fig.update_layout(title='Daily Candlestick Chart of 159985',
                  xaxis_title='Date',
                  yaxis_title='Price',
                  xaxis_rangeslider_visible=False)

fig.show()
