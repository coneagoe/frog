"""
风险平价策略 (Risk Parity Strategy)

交易标的：多资产类别ETF（股票、债券、黄金、商品）

策略逻辑：
    1. 选取7只ETF标的，覆盖多资产类别：
       - 股票：510300(沪深300)、512500(中证500)、159915(创业板)、510050(上证50)
       - 债券：511010(国债ETF)
       - 黄金：518880(黄金ETF)
       - 商品：159980(有色ETF)
    2. 每隔rebalance_freq个交易日进行再平衡
    3. 计算过去lookback_days天的年化波动率
    4. 使用波动率倒数作为权重（波动率越低，权重越高）
    5. 应用权重限制：单只ETF权重不超过max_position_weight，不低于min_position_weight

参数：
    lookback_days: 回看窗口天数，默认60天
    rebalance_freq: 再平衡频率，默认20个交易日
    min_position_weight: 最小仓位权重，默认5%
    max_position_weight: 最大仓位权重，默认50%
"""

import argparse
import os
import sys

import backtrader as bt
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import conf  # noqa: E402
from backtest.bt_common import run  # noqa: E402
from backtest.my_strategy import MyStrategy  # noqa: E402
from common.const import SecurityType  # noqa: E402

conf.parse_config()


# 定义ETF标的（多资产类别）
ETF_CODES = [
    "510300",  # 沪深300ETF - 股票大盘
    "512500",  # 中证500ETF - 股票中小盘
    "159915",  # 创业板ETF - 股票成长
    "510050",  # 上证50ETF - 股票蓝筹
    "511010",  # 国债ETF - 债券
    "518880",  # 黄金ETF - 黄金
    "159980",  # 有色ETF - 商品
]

stocks = ETF_CODES


class RiskParityStrategy(MyStrategy):
    """风险平价策略 - 使用波动率倒数加权"""

    stocks: list[str] = []
    params = (
        ("lookback_days", 60),  # 回看窗口天数
        ("rebalance_freq", 20),  # 再平衡频率（交易日）
        ("min_position_weight", 0.05),  # 最小仓位权重
        ("max_position_weight", 0.5),  # 最大仓位权重
    )

    def __init__(self):
        self.stocks = [d._name for d in self.datas]
        super().__init__()
        self.last_rebalance_idx = None
        self.weights = {data._name: 1.0 / len(self.datas) for data in self.datas}

    def next(self):
        super().next()

        current_idx = len(self)

        # 首次运行，等待足够的历史数据
        if current_idx < self.p.lookback_days:
            return

        # 再平衡检查
        if (
            self.last_rebalance_idx is None
            or (current_idx - self.last_rebalance_idx) >= self.p.rebalance_freq
        ):
            self._rebalance()
            self.last_rebalance_idx = current_idx

    def _rebalance(self):
        """执行再平衡，计算风险平价权重"""
        current_date = self.datas[0].datetime.date(0)

        # 计算各ETF的波动率
        volatilities = self._calculate_volatilities()
        if not volatilities:
            return

        # 计算风险平价权重（波动率倒数加权）
        self.weights = self._calculate_rp_weights(volatilities)

        # 执行调仓
        self._execute_rebalance(current_date)

    def _calculate_volatilities(self) -> dict:
        """计算各ETF的年化波动率"""
        volatilities = {}
        lookback = self.p.lookback_days

        for data in self.datas:
            if len(data) < lookback:
                continue

            prices = np.array([float(data.close[-i]) for i in range(lookback + 1)])
            returns = (prices[:-1] / prices[1:]) - 1

            if len(returns) >= 2:
                # 年化波动率
                vol = np.std(returns, ddof=1) * np.sqrt(252)
                # 确保波动率非零
                vol = max(vol, 0.01)
                volatilities[data._name] = vol

        return volatilities

    def _calculate_rp_weights(self, volatilities: dict) -> dict[str, float]:
        """计算风险平价权重（波动率倒数加权）"""
        if not volatilities:
            return {}

        # 波动率倒数
        inv_vols = {code: 1.0 / vol for code, vol in volatilities.items()}

        # 归一化
        total_inv_vol = sum(inv_vols.values())
        if total_inv_vol <= 0:
            equal_weight = 1.0 / len(volatilities)
            return {code: equal_weight for code in volatilities}

        weights = {code: v / total_inv_vol for code, v in inv_vols.items()}

        # 应用权重限制
        for code in weights:
            weights[code] = min(weights[code], self.p.max_position_weight)
            weights[code] = max(weights[code], self.p.min_position_weight)

        # 再次归一化
        total_weight = sum(weights.values())
        if total_weight > 0:
            weights = {code: w / total_weight for code, w in weights.items()}

        # 对于未选中的ETF，权重设为0
        for data in self.datas:
            if data._name not in weights:
                weights[data._name] = 0.0

        return weights

    def _execute_rebalance(self, current_date):
        """执行调仓操作"""
        # 打印权重
        non_zero_weights = {k: v for k, v in self.weights.items() if v > 0.001}
        print(f"{current_date.isoformat()}: rebalance, weights: {non_zero_weights}")

        # 平仓不在目标组合中的ETF
        selected_codes = set(self.weights.keys())
        for data in self.datas:
            if data._name not in selected_codes:
                if self.getposition(data).size != 0:
                    self.order_target_percent(data, target=0.0)
                    print(f"  close {data._name}")

        # 买入目标ETF
        for data in self.datas:
            target = self.weights.get(data._name, 0.0)
            if target > 0.001:  # 忽略太小的权重
                current_pos = self.getposition(data)
                if current_pos.size == 0:
                    self.order_target_percent(data, target=target)
                    print(f"  buy {data._name}: target={target:.1%}")

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
    cerebro.addstrategy(RiskParityStrategy)

    run(
        strategy_name="risk_parity",
        cerebro=cerebro,
        stocks=stocks,
        start_date=args.start,
        end_date=args.end,
        security_type=SecurityType.AUTO,
    )
