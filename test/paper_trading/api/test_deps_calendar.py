from datetime import date

from paper_trading.api.deps import _DataAvailableCalendar


def test_data_available_calendar_uses_exchange_trading_days():
    calendar = _DataAvailableCalendar()

    assert calendar.is_trade_date(date(2026, 6, 16)) is True
    assert calendar.is_trade_date(date(2026, 6, 14)) is False
    assert calendar.next_trade_date(date(2026, 6, 14)) == date(2026, 6, 15)
