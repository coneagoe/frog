import argparse
import math
import os
import sys

import backtrader as bt
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from backtest.bt_common import run  # noqa: E402
from common.const import SecurityType  # noqa: E402

conf.parse_config()


ETF_CATEGORIES_RAW = {
    "宽基": ["510300.XSHG", "510050.XSHG", "510500.XSHG", "159915.XSHE", "588000.XSHG"],
    "科技": ["515000.XSHG", "512480.XSHG", "515050.XSHG", "159995.XSHE", "512760.XSHG"],
    "医药": ["512010.XSHG", "512170.XSHG", "159938.XSHE", "515120.XSHG"],
    "消费": ["159928.XSHE", "515650.XSHG", "159996.XSHE", "515170.XSHG"],
    "金融": ["512800.XSHG", "512000.XSHG", "512200.XSHG", "515290.XSHG"],
    "能源": ["515220.XSHG", "159930.XSHE", "516160.XSHG", "159611.XSHE"],
    "材料": ["512400.XSHG", "159881.XSHE", "516360.XSHG"],
    "工业": ["512670.XSHG", "512710.XSHG", "516970.XSHG"],
    "传媒": ["512980.XSHG", "159869.XSHE", "516010.XSHG"],
    "商品": ["518880.XSHG", "159934.XSHE", "159985.XSHE"],
    "债券": ["511010.XSHG", "511220.XSHG", "511260.XSHG"],
}


def normalize_etf_code(etf_code: str) -> str:
    # bt_common/load_history_data uses plain codes (e.g. 510300), while the original
    # script used JQ-style suffixes (e.g. 510300.XSHG / 159915.XSHE).
    return etf_code.split(".")[0]


ETF_CATEGORIES = {
    normalize_etf_code(code): category
    for category, codes in ETF_CATEGORIES_RAW.items()
    for code in codes
}

stocks = [
    normalize_etf_code(code) for codes in ETF_CATEGORIES_RAW.values() for code in codes
]


def get_etf_category(etf_code: str) -> str:
    return ETF_CATEGORIES.get(etf_code, "其他")


class RotateETF6Strategy(bt.Strategy):
    params = (
        ("top_n", 3),
        ("momentum_bars", (21, 63, 126)),
        ("momentum_weights", (0.5, 0.3, 0.2)),
        ("volatility_lookback", 20),
        ("trend_ma", 60),
        ("trend_threshold", -5.0),
        ("max_position_weight", 0.5),
        ("stop_loss", -0.15),
    )

    def __init__(self):
        self.last_month = None
        self.last_year = None
        self.last_date = None

        self.trend_indicators = {
            data._name: bt.indicators.SimpleMovingAverage(
                data.close, period=self.p.trend_ma
            )
            for data in self.datas
        }

    def next(self):
        current_date = self.datas[0].datetime.date(0)
        self.last_date = current_date

        current_month = current_date.month
        current_year = current_date.year
        if self.last_month == current_month and self.last_year == current_year:
            return

        self.last_month = current_month
        self.last_year = current_year

        self._check_stop_loss(current_date)
        self._rebalance(current_date)

    def _check_stop_loss(self, current_date):
        for data in self.datas:
            pos = self.getposition(data)
            if pos.size == 0 or pos.price <= 0:
                continue

            current_price = float(data.close[0])
            drawdown = current_price / pos.price - 1
            if drawdown <= self.p.stop_loss:
                self.order_target_percent(data, target=0.0)
                print(
                    f"{current_date.strftime('%Y-%m-%d')}: STOP_LOSS {data._name} "
                    f"entry={pos.price:.4f}, current={current_price:.4f}, drawdown={drawdown:.2%}"
                )

    def _rebalance(self, current_date):
        candidates = self._select_candidates()
        if not candidates:
            print(f"{current_date.strftime('%Y-%m-%d')}: no ETF passes filters")
            self._clear_all_positions()
            return

        selected = self._diversified_top_n(candidates)
        target_weights = self._risk_parity_weights(selected)

        selected_codes = {item["code"] for item in selected}
        for data in self.datas:
            if data._name not in selected_codes:
                if self.getposition(data).size != 0:
                    self.order_target_percent(data, target=0.0)

        date_str = current_date.strftime("%Y-%m-%d")
        print(f"{date_str}: rebalance, selected={len(selected)}")

        for item in selected:
            data = item["data"]
            target = target_weights[item["code"]]
            self.order_target_percent(data, target=target)
            print(
                f"  {item['code']:<10} cat={item['category']:<6} weight={target:.1%} "
                f"mom={item['momentum']:+.2%} trend={item['trend']:+.2f} vol={item['volatility']:.2%}"
            )

    def _select_candidates(self) -> list[dict]:
        candidates: list[dict] = []
        max_momentum = max(self.p.momentum_bars)
        required_bars = (
            max(max_momentum, self.p.trend_ma, self.p.volatility_lookback) + 1
        )

        for data in self.datas:
            if len(data) < required_bars:
                continue

            momentum = self._multi_period_momentum(data)
            trend_score = self._trend_score(data)
            if trend_score < self.p.trend_threshold:
                continue

            volatility = self._annualized_volatility(data)
            if math.isnan(volatility) or volatility <= 0:
                continue

            candidates.append(
                {
                    "code": data._name,
                    "data": data,
                    "category": get_etf_category(data._name),
                    "momentum": momentum,
                    "trend": trend_score,
                    "volatility": max(volatility, 0.05),
                }
            )

        candidates.sort(key=lambda x: x["momentum"], reverse=True)
        return candidates

    def _multi_period_momentum(self, data):
        score = 0.0
        current = float(data.close[0])
        if current <= 0:
            return -999.0

        for bars, weight in zip(self.p.momentum_bars, self.p.momentum_weights):
            past = float(data.close[-bars])
            if past <= 0:
                continue
            score += (current / past - 1) * weight

        return score

    def _trend_score(self, data):
        ma = float(self.trend_indicators[data._name][0])
        current = float(data.close[0])
        if ma <= 0:
            return 0.0
        return (current / ma - 1) * 100

    def _annualized_volatility(self, data):
        lookback = self.p.volatility_lookback
        returns = []

        for i in range(lookback):
            prev_price = float(data.close[-i - 1])
            curr_price = float(data.close[-i])
            if prev_price <= 0:
                continue
            returns.append(curr_price / prev_price - 1)

        if len(returns) < 2:
            return 0.0

        return float(np.std(returns, ddof=1) * math.sqrt(252))

    def _diversified_top_n(self, ranked_candidates: list[dict]) -> list[dict]:
        selected: list[dict] = []
        selected_categories: set[str] = set()

        for item in ranked_candidates:
            if len(selected) >= self.p.top_n:
                break
            if (
                item["category"] not in selected_categories
                or item["category"] == "其他"
            ):
                selected.append(item)
                selected_categories.add(item["category"])

        if len(selected) < self.p.top_n:
            for item in ranked_candidates:
                if len(selected) >= self.p.top_n:
                    break
                if item not in selected:
                    selected.append(item)

        return selected[: self.p.top_n]

    def _risk_parity_weights(self, selected: list[dict]) -> dict[str, float]:
        inv_vol: dict[str, float] = {
            item["code"]: 1.0 / item["volatility"] for item in selected
        }
        total_inv_vol = sum(inv_vol.values())
        if total_inv_vol <= 0:
            equal_weight = 1.0 / len(selected)
            return {item["code"]: equal_weight for item in selected}

        weights = {code: v / total_inv_vol for code, v in inv_vol.items()}
        weights = {
            code: min(w, self.p.max_position_weight) for code, w in weights.items()
        }

        total_weight = sum(weights.values())
        if total_weight <= 0:
            equal_weight = 1.0 / len(selected)
            return {item["code"]: equal_weight for item in selected}

        return {code: w / total_weight for code, w in weights.items()}

    def _clear_all_positions(self):
        for data in self.datas:
            if self.getposition(data).size != 0:
                self.order_target_percent(data, target=0.0)

    def stop(self):
        print(f"Ending Value: {self.broker.getvalue():.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--start", required=True, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "-e", "--end", required=True, help="End date in YYYY-MM-DD format"
    )
    args = parser.parse_args()

    cerebro = bt.Cerebro()
    cerebro.addstrategy(RotateETF6Strategy)

    run(
        strategy_name="rotate_etf_6",
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.AUTO,
    )
