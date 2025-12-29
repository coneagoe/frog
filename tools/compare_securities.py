import argparse
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objs as go

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import conf  # noqa: E402
from common import get_last_trading_day  # noqa: E402
from common.const import COL_CLOSE, COL_DATE, PeriodType  # noqa: E402
from stock import get_security_name, load_history_data  # noqa: E402

conf.parse_config()


def show_multiple_securities(security_ids, df_list):
    for i in range(len(df_list)):
        df_list[i]["norm_close"] = (
            df_list[i][COL_CLOSE] - min(df_list[i][COL_CLOSE])
        ) / (max(df_list[i][COL_CLOSE]) - min(df_list[i][COL_CLOSE]))

    merged_df = df_list[0]
    for i in range(1, len(df_list)):
        merged_df = pd.merge(merged_df, df_list[i], on=COL_DATE, suffixes=("", f"_{i}"))

    # Use the merged DataFrame to get norm_close columns for better alignment
    norm_cols = []
    for i in range(len(security_ids)):
        # Get norm_close from the merged DataFrame to ensure date alignment
        norm_col = "norm_close" if i == 0 else f"norm_close_{i}"
        norm_cols.append(merged_df[norm_col])

    # Calculate average of normalized values across all securities
    avg_close = sum(norm_cols) / len(norm_cols)
    fig = go.Figure()

    # Add a trace for each security
    for i, sec_id in enumerate(security_ids):
        # First DataFrame has no suffix, others have index as suffix
        norm_close_col = "norm_close" if i == 0 else f"norm_close_{i}"
        fig.add_trace(
            go.Scatter(
                x=merged_df[COL_DATE],
                y=merged_df[norm_close_col],
                mode="lines",
                name=get_security_name(sec_id),
            )
        )

    # Add average trace
    fig.add_trace(
        go.Scatter(x=merged_df[COL_DATE], y=avg_close, mode="lines", name="Average")
    )

    fig.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-n",
        default=360,
        type=int,
        help="since how many days ago to compare, cannot be used together with -s and -e",  # noqa: E501
    )
    parser.add_argument("-s", "--start", type=str, help="start date, YYYYMMDD")
    parser.add_argument("-e", "--end", type=str, help="end date, YYYYMMDD")
    parser.add_argument(
        "-t", "--template", help="The template file to read securities from."
    )
    parser.add_argument("securities", nargs="*", help="list of security ids to compare")
    args = parser.parse_args()

    if args.template:
        if not os.path.exists(args.template):
            print(f"The template file {args.template} does not exist.")
            exit()

        with open(args.template, "r") as f:
            # read all security IDs from one line
            security_ids = f.readline().split()
    elif not args.securities:
        parser.error(
            "You must specify at least two security IDs, or use the -t option."
        )
        exit()
    else:
        security_ids = args.securities

    start_date = args.start
    end_date = args.end

    if end_date is None:
        end_date = get_last_trading_day()

    if start_date is None:
        end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_date = (end_date_dt - timedelta(days=args.n)).strftime("%Y-%m-%d")

    df_list = []
    for sec_id in security_ids:
        df_list.append(
            load_history_data(
                security_id=sec_id,
                period=PeriodType.DAILY,
                start_date=start_date,
                end_date=end_date,
            )
        )

    show_multiple_securities(security_ids, df_list)
