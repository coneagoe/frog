import os
import sys
import conf
from fund import *
import seaborn as sns


df_asset, df_profit, df_profit_rate = (None, None, None)


def usage():
    print(f"{os.path.basename(__file__)} <start_date> <end_date>")
    print("<start_date> <end_date>: yyyy-mm-dd")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        usage()
        exit()

    conf.config = conf.parse_config()

    df_asset, df_profit, df_profit_rate = load_history_position(sys.argv[1], sys.argv[2])
    print(df_asset)
    print(df_profit)
    print(df_profit_rate)
    #sns.set_theme()

    #sns.relplot(data=df_asset, kind="line")
