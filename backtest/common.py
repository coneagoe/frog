import os
import sys
import webbrowser
from datetime import datetime

# Directly fix the problematic function in quantstats by monkey
# patching only the specific issue.
# The issue is in quantstats._plotting.core.plot_timeseries
# where it uses .sum(axis=0) on a resampler
import backtrader as bt
import pandas as pd
import pandas_market_calendars as mcal
import plotly.graph_objs as go
import quantstats as qs
from plotly.subplots import make_subplots
from tqdm import tqdm

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.my_analyzer import MyAnalyzer  # noqa: E402
from stock import (  # noqa: E402
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_VOLUME,
    drop_suspended_stocks,
    load_history_data,
)

# Save the original function
original_sum = pd.core.resample.Resampler.sum


# Patch the pandas resampler's sum method to handle the axis parameter correctly
def patched_sum(self, *args, **kwargs):
    # Drop the axis parameter which causes the error
    if "axis" in kwargs:
        del kwargs["axis"]
    return original_sum(self, *args, **kwargs)


# Apply the patch to the resampler's sum method
pd.core.resample.Resampler.sum = patched_sum  # type: ignore

print("Pandas Resampler sum method patched successfully!")

fee_rate = 0.0003


use_plotly = True


df_data = []


g_start_date = "2020-01-01"
g_end_date = "2020-12-31"
g_strategy_name = None

g_filter_st = False


def config(strategy_name: str, start_date: str, end_date: str):
    global g_strategy_name, g_start_date, g_end_date
    g_strategy_name = strategy_name
    g_start_date = start_date
    g_end_date = end_date


def disable_plotly():
    global use_plotly
    use_plotly = False


def enable_optimize():
    os.environ["OPTIMIZER"] = "True"


def load_test_data(
    security_id: str,
    period: str,
    start_date: str,
    end_date: str,
    adjust="qfq",
    security_type="auto",
) -> pd.DataFrame:
    df = load_history_data(
        security_id=security_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
        security_type=security_type,
    )

    df = df[[COL_DATE, COL_OPEN, COL_CLOSE, COL_HIGH, COL_LOW, COL_VOLUME]]
    df.columns = pd.Index(
        [
            "date",
            "open",
            "close",
            "high",
            "low",
            "volume",
        ]
    )

    start_date_dt = pd.to_datetime(start_date)
    if start_date_dt < df.iloc[0]["date"]:
        cal = mcal.get_calendar("XSHG")
        schedule = cal.schedule(start_date=start_date, end_date=df.iloc[0]["date"])
        all_days = schedule.index

        df_tmp = pd.DataFrame(
            columns=["date", "open", "close", "high", "low", "volume"],
            index=range(len(all_days)),
        )

        df_tmp["date"] = all_days
        df_tmp[["open", "close", "high", "low", "volume"]] = 1.0
        df_tmp.set_index("date", inplace=True)
        df.set_index("date", inplace=True)

        df = pd.concat([df_tmp, df], axis=0)
        df.sort_index(inplace=True)

    else:
        df.set_index("date", inplace=True)

    df.index.name = "date"

    # assert not (df['open'] >= 2683.0).any(), (
    #     f"Data error: {security_id} {start_date} {end_date}"
    # )
    # assert not (df['close'] >= 2683.0).any(), (
    #     f"Data error: {security_id} {start_date} {end_date}"
    # )
    # assert not (df['high'] >= 2683.0).any(), (
    #     f"Data error: {security_id} {start_date} {end_date}"
    # )
    # assert not (df['low'] >= 2683.0).any(), (
    #     f"Data error: {security_id} {start_date} {end_date}"
    # )

    return df


def drop_suspended(
    stocks: list, start_date: str, end_date: str, num_points: int
) -> list:
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    delta = (end - start) / (num_points - 1)
    dates = [(start + i * delta).strftime("%Y-%m-%d") for i in range(num_points)]

    for date in dates:
        stocks = drop_suspended_stocks(stocks, date)

    return stocks


def set_stocks(
    cerebro, stocks: list, start_date: str, end_date: str, security_type: str
):
    global df_data

    # if pd.to_datetime(end_date) - pd.to_datetime(start_date) < pd.Timedelta(days=365):
    #     adjust = ""
    # else:
    #     adjust = "qfq"
    adjust = "hfq"

    # 添加数据
    for stock in tqdm(stocks):
        # 获取数据
        df = load_test_data(
            security_id=stock,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            security_type=security_type,
        )

        df_data.append(df)

        # 创建数据源
        data = bt.feeds.PandasData(dataname=df)

        # 添加数据源
        cerebro.adddata(data, name=stock)


def add_analyzer(cerebro):
    if os.getenv("OPTIMIZER"):
        return

    # 设置起始资金
    init_cash = os.getenv("INIT_CASH")
    start_cash = float(init_cash) if init_cash else 1000000.0
    cerebro.broker.setcash(start_cash)

    cerebro.broker.setcommission(commission=fee_rate)  # 设置交易手续费

    # cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trade_analysis")
    # cerebro.addanalyzer(bt.analyzers.Transactions, _name="transactions")
    # cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe_ratio")
    # cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annual_return")
    # cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    # cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    # cerebro.addanalyzer(bt.analyzers.VWR, _name="vwr")
    # cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")
    cerebro.addanalyzer(bt.analyzers.PyFolio, _name="pyfolio")
    cerebro.addanalyzer(MyAnalyzer, _name="my_analyzer")
    # cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    # cerebro.addanalyzer(BacktraderPlottingLive)
    # cerebro.addanalyzer(RecorderAnalyzer)


def generate_report(cerebro, results):
    if os.getenv("OPTIMIZER"):
        return

    strategy = results[0]

    pyfolio = strategy.analyzers.getbyname("pyfolio")
    returns, positions, transactions, gross_lev = pyfolio.get_pf_items()

    qs.extend_pandas()
    metrics = qs.reports.metrics(returns, mode="full", display=False)
    # metrics = qs.reports.metrics(returns, display=False)
    # 打印完整的metrics
    print(metrics.to_string())
    # print(metrics)

    # report_file_name = f'report_{g_strategy_name}_{g_start_date}_{g_end_date}.html'
    # qs.reports.html(returns=returns, positions=positions,
    #                 transactions=transactions, gross_lev=gross_lev,
    #                 output=report_file_name)

    if os.getenv("PLOT_REPORT") == "true":
        # qs.plots.snapshot(returns, show=True)
        report_file_name = f"report_{g_strategy_name}_{g_start_date}_{g_end_date}.html"
        # qs.reports.html(returns=returns, mode='full', output=report_file_name)
        qs.reports.html(returns=returns, output=report_file_name)
        webbrowser.open("file://" + os.path.realpath(report_file_name))
        plot(strategy)


def run(
    strategy_name: str,
    cerebro,
    stocks: list,
    start_date: str,
    end_date: str,
    security_type: str,
):
    config(strategy_name, start_date, end_date)

    set_stocks(cerebro, stocks, start_date, end_date, security_type)

    add_analyzer(cerebro)

    if os.environ.get("OPTIMIZER"):
        results = cerebro.run(maxcpus=1)
    else:
        results = cerebro.run()

    generate_report(cerebro, results)


def show_position(positions):
    for data, position in positions.items():
        if position:
            print(
                f"current position(当前持仓): {data._name}, "
                f'size(数量): {"%.2f" % position.size}'
            )


def plot(strategy: bt.Strategy):
    analyzer = strategy.analyzers.my_analyzer.get_analysis()

    df_cashflow = pd.DataFrame(analyzer.cashflow, columns=["total"])
    df_value = pd.DataFrame(analyzer.values, columns=["value"])

    trades_list = []
    for stock, trades in strategy.trades.items():
        trades_list.extend(trades)

    if len(trades_list) == 0:
        return

    df_trades = pd.DataFrame(trades_list)
    holding_time_counts = df_trades["holding_time"].value_counts().sort_index()

    df_trades["open_time"] = pd.to_datetime(
        df_trades["open_time"]
    )  # ensure open_time is datetime
    monthly_trades = df_trades.groupby(df_trades["open_time"].dt.to_period("M")).size()

    num_subplots = 4

    subplot_titles = ["Value & Cashflow", "", "Holding Time", "Monthly Trades"]

    fig = make_subplots(
        rows=num_subplots,
        cols=1,
        subplot_titles=subplot_titles,
    )

    fig.update_layout(height=500 * num_subplots)

    x_axis = df_data[0].index

    row = 1
    fig.add_trace(
        go.Scatter(x=x_axis, y=df_value["value"], name="Value", yaxis="y1"),
        row=row,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=x_axis, y=df_cashflow["total"], name="Cashflow", yaxis="y2"),
        row=row,
        col=1,
    )

    row += 2
    fig.add_trace(
        go.Bar(
            x=holding_time_counts.index,
            y=holding_time_counts.values,
            name="Holding Time",
            xaxis="x3",
            yaxis="y3",
        ),
        row=row,
        col=1,
    )

    row += 1
    fig.add_trace(
        go.Bar(
            x=monthly_trades.index.astype(str),
            y=monthly_trades.values,
            name="Monthly Trades",
            xaxis="x4",
            yaxis="y4",
        ),
        row=row,
        col=1,
    )

    fig.update_layout(
        yaxis1=dict(title="Value", side="left"),
        yaxis2=dict(title="Cashflow", side="right", overlaying="y1"),
        xaxis3=dict(title="持仓时间"),
        yaxis3=dict(title="交易次数"),
        xaxis4=dict(title="月份"),
        yaxis4=dict(title="交易次数"),
        # yaxis5=dict(title='Average Monthly Profit')
    )

    plot_file_name = f"plot_{g_strategy_name}_{g_start_date}_{g_end_date}.html"
    fig.write_html(plot_file_name)
    webbrowser.open("file://" + os.path.realpath(plot_file_name))
