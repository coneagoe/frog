import numpy as np
from scipy.signal import argrelextrema
import pandas as pd
from . const import (
    COL_CLOSE,
    COL_STOCK_ID,
)
from . data import load_history_data


percent = 0.05


def get_support_resistance(df: pd.DataFrame, turning_points: list) -> tuple:
    current_price = df[COL_CLOSE].iloc[-1]
    support_point = None
    resistance_point = None
    for i in range(len(turning_points)-1, -1, -1):
        tp = df[COL_CLOSE].iloc[turning_points[i]]
        if tp < current_price:
            if support_point is None:
                support_point = turning_points[i]

        if tp > current_price:
            if resistance_point is None:
                resistance_point = turning_points[i]

        if support_point and resistance_point:
            break

    return support_point, resistance_point


def get_turning_points(df: pd.DataFrame):
    # Calculate EMA(12)
    ema = df[COL_CLOSE].ewm(span=12, adjust=False).mean().values

    # Calculate turning points based on EMA
    turning_points = argrelextrema(ema, np.greater)[0]
    turning_points = np.append(turning_points, argrelextrema(ema, np.less)[0])

    # drop points if the interval is less than percent
    i = 1
    while i < len(turning_points):
        tp0 = ema[turning_points[i]]
        tp1 = ema[turning_points[i - 1]]
        # if tp0 == np.nan or tp1 == np.nan:
        #     continue

        if abs(tp0 - tp1) < tp1 * percent:
            turning_points = np.delete(turning_points, i)
            continue
        i += 1

    # turning_points = turning_points[~np.isnan(turning_points)]
    turning_points = np.sort(turning_points)

    return turning_points


def calculate_support_resistance(df: pd.DataFrame, start_date_ts: str, end_date_ts: str):
    support_point = np.nan
    resistance_point = np.nan

    df = load_history_data(security_id=df[COL_STOCK_ID], period='daily',
                           start_date=start_date_ts, end_date=end_date_ts, adjust="qfq")
    if df is not None:
        turning_points = get_turning_points(df)
        support_index, resistance_index = get_support_resistance(df, turning_points)
        if support_index is not None:
            support_point = df[COL_CLOSE].iloc[support_index]

        if resistance_index is not None:
            resistance_point = df[COL_CLOSE].iloc[resistance_index]

    # print(f"support_index: {support_index}, resistance_index: {resistance_index}, support_point: {support_point}, resistance_point: {resistance_point}")

    return support_point, resistance_point
