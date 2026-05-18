from shareholder_monitor.ssf_alert import build_ssf_change_alert_email


def test_build_ssf_change_alert_email_orders_by_score_desc():
    subject, body = build_ssf_change_alert_email(
        [
            {
                "stock_id": "000002",
                "score": 61.0,
                "event_types": ["decrease"],
                "ssf_holder_count_change": -1,
                "ssf_total_hold_ratio_change": -0.5,
                "detail_json": {"holders": []},
            },
            {
                "stock_id": "000001",
                "score": 88.0,
                "event_types": ["new_entry", "increase"],
                "ssf_holder_count_change": 1,
                "ssf_total_hold_ratio_change": 0.8,
                "detail_json": {"holders": []},
            },
        ],
        "2024-03-31",
    )

    assert "[社保持仓变动提醒]" in subject
    assert body.index("000001") < body.index("000002")
