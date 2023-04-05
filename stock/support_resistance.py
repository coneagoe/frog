import numpy as np
from scipy.signal import argrelextrema
import pandas as pd
from stock.common import *
from stock.data import load_history_data


percent = 0.05


def get_support_resistance(df: pd.DataFrame):
    turning_points = get_turning_points(df)

    current_price = df[col_close].iloc[-1]
    support_point = None
    resistance_point = None
    for i in range(len(turning_points)-1, -1, -1):
        tp = df[col_close].iloc[turning_points[i]]
        if tp < current_price:
            if support_point is None:
                support_point = turning_points[i]

        if tp > current_price:
            if resistance_point is None:
                resistance_point = turning_points[i]

        if support_point and resistance_point:
            break

    return turning_points, support_point, resistance_point


def get_turning_points(df: pd.DataFrame):
    turning_points = argrelextrema(df[col_close].values, np.greater)[0]
    turning_points = np.append(turning_points, argrelextrema(df[col_close].values, np.less)[0])

    # drop points if the interval is less than percent
    i = 1
    while i < len(turning_points):
        tp0 = df[col_close].iloc[turning_points[i]]
        tp1 = df[col_close].iloc[turning_points[i - 1]]
        if abs(tp0 - tp1) < tp1 * percent:
            turning_points = np.delete(turning_points, i)
            continue
        i += 1
    turning_points = np.sort(turning_points)

    return turning_points


def calculate_support_resistance(df: pd.DataFrame, start_date_ts: str, end_date_ts: str):
    df_history_data = load_history_data(df[col_stock_id], start_date_ts, end_date_ts)
    if df_history_data is not None:
        turning_points, support_point, resistance_point = get_support_resistance(df_history_data)
        if support_point:
            support_point = df_history_data[col_close][support_point]

        if resistance_point:
            resistance_point = df_history_data[col_close][resistance_point]
    else:
        support_point = np.nan
        resistance_point = np.nan

    return support_point, resistance_point
