"""Main orchestrator: load targets → fetch data → evaluate → alert."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from common.const import COL_CLOSE
from monitor.condition import ConditionResult, evaluate_condition
from monitor.price_fetcher import fetch_current_price, fetch_history_df
from storage import get_storage
from utility import send_email

logger = logging.getLogger(__name__)


@dataclass
class MonitorSummary:
    total: int = 0
    triggered: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list = field(default_factory=list)


def _build_history_for_condition(condition: dict, stock_code: str, market: str):
    """Determine min_periods needed for the condition and fetch history."""
    ctype = condition.get("type")
    if ctype == "price_threshold":
        return None  # no history needed
    if ctype == "change_pct":
        return None  # uses change_pct kwarg, not history
    if ctype == "price_cross_ma":
        return fetch_history_df(stock_code, market, min_periods=int(condition["period"]) + 5)
    if ctype == "ma_cross":
        return fetch_history_df(stock_code, market, min_periods=int(condition["slow"]) + 5)
    if ctype == "rsi":
        return fetch_history_df(stock_code, market, min_periods=int(condition.get("period", 14)) + 5)
    return None


def _compute_change_pct(current_price: float, history_df) -> Optional[float]:
    """Compute today's % change from yesterday's close."""
    if history_df is None or len(history_df) < 1:
        return None
    prev_close = float(history_df[COL_CLOSE].iloc[-1])
    if prev_close == 0:
        return None
    return (current_price - prev_close) / prev_close * 100


def run_monitor(frequency: str = "daily") -> MonitorSummary:
    """
    Load all enabled monitoring targets for the given frequency,
    evaluate their conditions, and send email alerts on edge triggers.

    Args:
        frequency: 'daily' or 'intraday'

    Returns:
        MonitorSummary with counts of triggered/skipped/error targets.
    """
    storage = get_storage()
    storage.ensure_monitor_targets_table()
    targets = storage.load_monitor_targets(frequency=frequency)

    summary = MonitorSummary(total=len(targets))

    for target in targets:
        try:
            condition = target.condition
            history_df = _build_history_for_condition(condition, target.stock_code, target.market)
            current_price = fetch_current_price(target.stock_code, target.market)

            change_pct = None
            if condition.get("type") == "change_pct":
                hist_for_pct = fetch_history_df(target.stock_code, target.market, min_periods=2)
                change_pct = _compute_change_pct(current_price, hist_for_pct)

            result = evaluate_condition(
                condition,
                current_price=current_price,
                history_df=history_df,
                change_pct=change_pct,
            )

            if result == ConditionResult.INSUFFICIENT_DATA:
                logger.warning(
                    f"[monitor] {target.stock_code} 数据不足，跳过条件评估. "
                    f"condition={condition}"
                )
                summary.skipped += 1
                continue

            condition_met = result == ConditionResult.TRIGGERED

            # Edge trigger: only alert on False→True transition
            if condition_met and not target.last_state:
                now = datetime.now(timezone.utc)
                _send_alert(target, current_price, change_pct)
                storage.update_monitor_target_state(target.id, True, triggered_at=now)
                summary.triggered += 1
                logger.info(
                    f"[monitor] 告警触发: {target.stock_code} note={target.note!r} "
                    f"price={current_price}"
                )

            elif not condition_met and target.last_state and target.reset_mode == "auto":
                storage.update_monitor_target_state(target.id, False, triggered_at=None)
                logger.info(f"[monitor] 自动重置: {target.stock_code} 条件已恢复正常")

        except Exception as exc:
            logger.error(f"[monitor] 处理 {target.stock_code} 出错: {exc}", exc_info=True)
            summary.errors += 1
            summary.error_details.append(f"{target.stock_code}: {exc}")

    return summary


def _send_alert(target, current_price: Optional[float], change_pct: Optional[float]):
    """Compose and send an email alert for a triggered condition."""
    ctype = target.condition.get("type", "unknown")

    subject = f"[股票监控告警] {target.stock_code} 触发条件: {target.note or ctype}"

    lines = [
        f"股票代码: {target.stock_code}  市场: {target.market}",
        f"备注: {target.note or '无'}",
        f"当前价格: {current_price}",
    ]
    if change_pct is not None:
        lines.append(f"当日涨跌幅: {change_pct:.2f}%")
    lines.append(f"触发条件: {target.condition}")

    send_email(subject, "\n".join(lines))
