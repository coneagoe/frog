from inspect import signature
from datetime import date, datetime

from shareholder_monitor.ssf_alert import build_ssf_change_alert_email


class SignalObject:
    def __init__(
        self,
        stock_id,
        score,
        event_types,
        ssf_holder_count_change,
        ssf_total_hold_ratio_change,
        ann_date,
    ):
        self.stock_id = stock_id
        self.score = score
        self.event_types = event_types
        self.ssf_holder_count_change = ssf_holder_count_change
        self.ssf_total_hold_ratio_change = ssf_total_hold_ratio_change
        self.ann_date = ann_date


def test_build_ssf_change_alert_email_formats_unified_weekly_report():
    assert len(signature(build_ssf_change_alert_email).parameters) == 1

    subject, body = build_ssf_change_alert_email(
        [
            {
                "stock_id": "000002",
                "score": 61.0,
                "event_types": ["decrease"],
                "ssf_holder_count_change": -1,
                "ssf_total_hold_ratio_change": -0.5,
                "ann_date": datetime(2024, 4, 3, 9, 30),
            },
            SignalObject(
                stock_id="000003",
                score=95.0,
                event_types=["new_entry"],
                ssf_holder_count_change=2,
                ssf_total_hold_ratio_change=1.2,
                ann_date="2024-04-01",
            ),
            {
                "stock_id": "000001",
                "score": 88.0,
                "event_types": ["increase"],
                "ssf_holder_count_change": 1,
                "ssf_total_hold_ratio_change": 0.8,
                "ann_date": "2024-03-31",
            },
        ]
    )

    assert subject == "[社保持仓周报] 本周新增 3 只，按综合分排序"
    assert "待发送信号数: 3" in body
    assert "公告日期范围: 2024-03-31 ~ 2024-04-03" in body
    assert "排序规则: 按单条信号综合分降序" in body
    assert body.index("1. 000003 | ann_date=2024-04-01 | score=95.0 | events=new_entry | count_change=2 | ratio_change=1.2") < body.index(
        "2. 000001 | ann_date=2024-03-31 | score=88.0 | events=increase | count_change=1 | ratio_change=0.8"
    )
    assert body.index("2. 000001 | ann_date=2024-03-31 | score=88.0 | events=increase | count_change=1 | ratio_change=0.8") < body.index(
        "3. 000002 | ann_date=2024-04-03 | score=61.0 | events=decrease | count_change=-1 | ratio_change=-0.5"
    )
