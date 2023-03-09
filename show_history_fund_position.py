import logging
from os import walk
from os.path import basename
import sys
import plotly.express as px
from plotly.subplots import make_subplots
import conf
from fund import *


# logging.getLogger().setLevel(logging.DEBUG)

conf.config = conf.parse_config()


def get_available_date_range() -> (str, str):
    filenames = next(walk(get_fund_position_path()), (None, None, []))[2]
    if len(filenames) > 0:
        start_date = filenames[0].rstrip('.csv')
        end_date = filenames[-1].rstrip('.csv')
        return start_date, end_date
    else:
        logging.info("No history fund position data")
        exit()


def usage():
    print(f"{basename(__file__)} <start-date> <end-date>")
    print("start-date/end-date: YYYY-MM-DD")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        usage()
        exit()

    start_date, end_date = sys.argv[1], sys.argv[2]

    df_asset, df_profit, df_profit_rate = load_history_position(start_date, end_date)

    fig = px.line(df_profit, title=col_profit)
    #fig = make_subplots(rows=3, cols=1)
    #fig.add_trace(px.line(df_asset))
    #fig.add_trace(px.line(df_profit))
    #fig.add_trace(px.line(df_profit_rate))
    fig.show()