"""Main orchestrator: load targets → fetch data → evaluate → alert."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from common.const import COL_CLOSE, COL_DATE
from monitor.blackroom_service import BlackroomService
from monitor.condition import ConditionResult, evaluate_condition, is_missing_number
from monitor.monitor_target_service import format_monitor_target_label, resolve_stock_name
from monitor.price_fetcher import fetch_current_price, fetch_final_close_history_df, fetch_history_df
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


def _resolve_current_price(
    frequency: str, condition: dict, current_price: Optional[float], history_df
) -> Optional[float]:
    ctype = condition.get("type")
    if frequency != "daily" or ctype != "price_cross_ma":
        return current_price
    if not is_missing_number(current_price):
        return current_price
    if history_df is None or len(history_df) == 0:
        return current_price
    latest_close = pd.to_numeric(pd.Series([history_df[COL_CLOSE].iloc[-1]]), errors="coerce").iloc[0]
    if pd.isna(latest_close):
        return current_price
    return float(latest_close)


def run_monitor(
    frequency: str = "daily", workflow: str | None = None, as_of_date: date | None = None
) -> MonitorSummary:
    """
    Load all enabled monitoring targets for the given frequency,
    evaluate their conditions, and send email alerts on edge triggers.

    Args:
        frequency: 'daily' or 'intraday'
        workflow: optional durable workflow owner used to scope targets and
            apply workflow-specific alert guards and evidence enrichment.

    Returns:
        MonitorSummary with counts of triggered/skipped/error targets.
    """
    storage = get_storage()
    storage.ensure_monitor_targets_table()
    targets = storage.load_monitor_targets(frequency=frequency, workflow=workflow)
    if workflow is not None:
        targets = [target for target in targets if getattr(target, "workflow", None) == workflow]
    summary = MonitorSummary(total=len(targets))

    for target in targets:
        try:
            condition = target.condition
            ctype = condition.get("type")
            history_df = None
            current_price: Optional[float] = None
            change_pct = None
            if ctype == "close_cross_ma":
                if frequency != "daily" or target.market != "A":
                    result = ConditionResult.INSUFFICIENT_DATA
                else:
                    evaluation_date = as_of_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
                    period = int(condition["period"])
                    history_df = fetch_final_close_history_df(
                        target.stock_code, evaluation_date, min_periods=period + 1
                    )
                    if history_df is None or COL_DATE not in history_df or COL_CLOSE not in history_df:
                        result = ConditionResult.INSUFFICIENT_DATA
                    else:
                        history_dates = pd.to_datetime(history_df[COL_DATE], errors="coerce")
                        if history_dates.isna().any() or history_dates.iloc[-1].normalize().date() != evaluation_date:
                            result = ConditionResult.INSUFFICIENT_DATA
                        else:
                            latest_close = pd.to_numeric(
                                pd.Series([history_df[COL_CLOSE].iloc[-1]]), errors="coerce"
                            ).iloc[0]
                            if pd.isna(latest_close):
                                result = ConditionResult.INSUFFICIENT_DATA
                            else:
                                current_price = float(latest_close)
                                result = evaluate_condition(
                                    condition,
                                    current_price=None,
                                    history_df=history_df,
                                )
            else:
                history_df = _build_history_for_condition(condition, target.stock_code, target.market)
                current_price = fetch_current_price(target.stock_code, target.market)
                current_price = _resolve_current_price(frequency, condition, current_price, history_df)

                if ctype == "change_pct":
                    hist_for_pct = fetch_history_df(target.stock_code, target.market, min_periods=2)
                    if current_price is not None:
                        change_pct = _compute_change_pct(current_price, hist_for_pct)

                result = evaluate_condition(
                    condition,
                    current_price=current_price,
                    history_df=history_df,
                    change_pct=change_pct,
                )

            if result == ConditionResult.INSUFFICIENT_DATA:
                logger.warning(f"[monitor] {target.stock_code} 数据不足，跳过条件评估. condition={condition}")
                summary.skipped += 1
                continue

            condition_met = result == ConditionResult.TRIGGERED
            is_forecast_ssf_workflow = target.workflow == "forecast_ssf_ma20"

            # Edge trigger: only alert on False→True transition
            if condition_met and not target.last_state:
                now = datetime.now(timezone.utc)
                evidence = None
                if is_forecast_ssf_workflow:
                    candidate = storage.get_forecast_ssf_candidate_for_target(target.id)
                    evidence = getattr(candidate, "evidence", None) if candidate is not None else None
                    blackroom = BlackroomService(storage=storage)
                    ban_result = blackroom.is_banned(target.stock_code, target.market)
                    if not ban_result.get("success"):
                        raise RuntimeError(ban_result.get("message") or "blackroom lookup failed")
                    if ban_result.get("data", {}).get("banned"):
                        disabled = storage.disable_forecast_ssf_target_for_blackroom(target.id, "active_blackroom")
                        if not disabled:
                            raise RuntimeError("failed to disable forecast SSF target for active blackroom")
                        summary.skipped += 1
                        continue
                _send_alert(target, current_price, change_pct, evidence=evidence)
                storage.update_monitor_target_state(target.id, True, triggered_at=now)
                summary.triggered += 1
                logger.info(f"[monitor] 告警触发: {target.stock_code} note={target.note!r} price={current_price}")

            elif not condition_met and target.last_state and target.reset_mode == "auto":
                storage.update_monitor_target_state(target.id, False, triggered_at=None)
                logger.info(f"[monitor] 自动重置: {target.stock_code} 条件已恢复正常")

        except Exception as exc:
            logger.error(f"[monitor] 处理 {target.stock_code} 出错: {exc}", exc_info=True)
            summary.errors += 1
            summary.error_details.append(f"{target.stock_code}: {exc}")

    return summary


def _send_alert(target, current_price: Optional[float], change_pct: Optional[float], evidence=None):
    """Compose and send an email alert for a triggered condition."""
    label = format_monitor_target_label(
        target.stock_code,
        resolve_stock_name(target.stock_code, getattr(target, "stock_name", None)),
        target.condition,
        target.note,
    )
    subject = f"[股票监控告警] {label}"

    lines = [
        f"股票代码: {target.stock_code}  市场: {target.market}",
        f"备注: {target.note or '无'}",
        f"当前价格: {current_price}",
    ]
    if change_pct is not None:
        lines.append(f"当日涨跌幅: {change_pct:.2f}%")
    lines.append(f"触发条件: {target.condition}")
    if evidence:
        for section in ("forecast", "shareholder"):
            for key, value in evidence.get(section, {}).items():
                if value is not None:
                    lines.append(f"{section}.{key}: {value}")

    send_email(subject, "\n".join(lines))
