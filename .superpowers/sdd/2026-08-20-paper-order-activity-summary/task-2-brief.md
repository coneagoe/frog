### Task 2: Calculate Order Activity Averages

**Files:**
- Modify: `paper_trading/services/analytics_service.py:1-48,102-146`
- Modify: `test/paper_trading/services/test_analytics_service.py`
- Modify: `test/paper_trading/api/test_analytics_api.py`

**Interfaces:**
- Consumes `PaperTradingRepository.list_orders(account_id) -> list[PaperOrder]`.
- Changes constructor to `AnalyticsService(repo: PaperTradingRepository, today_provider: Callable[[], date] | None = None)`.
- Produces `AnalyticsResponse.activity: ActivityAnalytics | None` through `_activity(orders: list[PaperOrder]) -> ActivityAnalytics | None`.
- The summary helper has the fixed signature `_activity_summary(orders: list[PaperOrder], coverage_start: date, coverage_end: date, granularity: Literal["daily", "weekly", "monthly"]) -> ActivitySummary`.

- [ ] **Step 1: Write failing status and empty-account service tests**

Add tests that create `filled`, `rejected`, `accepted`, `cancelled`, and `new` orders on `2026-08-01`, then inject `today_provider=lambda: date(2026, 8, 1)`:

```python
assert analytics.activity is not None
assert analytics.activity.daily.total_orders == Decimal("5.000000")
assert analytics.activity.daily.successful_orders == Decimal("1.000000")
assert analytics.activity.daily.failed_orders == Decimal("1.000000")
```

Add an account with no orders and assert `AnalyticsService(repo, today_provider=lambda: date(2026, 8, 20)).get_account_analytics(account.id).activity is None`.

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `uv run pytest test/paper_trading/services/test_analytics_service.py -k activity -v`

Expected: FAIL because the constructor has no injectable provider and the result has no `activity` property.

- [ ] **Step 3: Write failing denominator and boundary tests**

Seed orders on `2026-08-28`, `2026-08-31`, `2026-09-01`, and `2026-09-10`; inject `coverage_end = 2026-09-10`. Arrange two `filled`, one `rejected`, and one `accepted` order. Assert the full range, a weekend-inclusive 14-day denominator, three ISO-week denominator, and two calendar-month denominator:

```python
assert activity.coverage_start == date(2026, 8, 28)
assert activity.coverage_end == date(2026, 9, 10)
assert activity.daily.total_orders == Decimal("0.285714")
assert activity.weekly.total_orders == Decimal("1.333333")
assert activity.monthly.total_orders == Decimal("2.000000")
assert activity.daily.successful_orders == Decimal("0.142857")
assert activity.weekly.failed_orders == Decimal("0.333333")
assert activity.monthly.failed_orders == Decimal("0.500000")
```

- [ ] **Step 4: Run tests to verify denominator failure**

Run: `uv run pytest test/paper_trading/services/test_analytics_service.py -k activity -v`

Expected: FAIL until inclusive date-period denominators are implemented.

- [ ] **Step 5: Implement the minimal service logic**

1. Import `datetime`, `timedelta`, `ZoneInfo`, `Callable`, `Literal`, `ActivityAnalytics`, and `ActivitySummary`.
2. Default `today_provider` to `lambda: datetime.now(ZoneInfo("Asia/Shanghai")).date()`.
3. In `get_account_analytics`, set `activity=self._activity(orders)`; remove `trades` from the Activity call but preserve `trades` loading only if another current calculation requires it.
4. `_activity` sets `coverage_end` to `self.today_provider()`, excludes orders after that date, returns `None` if no orders remain, and otherwise sets `coverage_start` to the minimum remaining order `trade_date`.
5. Count all orders, only `status == "filled"`, and only `status == "rejected"`; do not inspect trades.
6. For daily, count `(coverage_end - coverage_start).days + 1`. For weekly, iterate inclusive dates and count distinct `(iso_year, iso_week)` keys. For monthly, increment `(year, month)` from start through end and count each key once.
7. Quantize each `Decimal(count) / Decimal(denominator)` using existing `_QUANTIZE`, then return daily, weekly, and monthly `ActivitySummary` objects.

- [ ] **Step 6: Verify service and API behavior**

Run: `uv run pytest test/paper_trading/services/test_analytics_service.py test/paper_trading/api/test_analytics_api.py -v`

Expected: PASS, including all existing Overview, Execution, Trade Quality, and Risk tests.

- [ ] **Step 7: Commit**

```bash
git add paper_trading/services/analytics_service.py test/paper_trading/services/test_analytics_service.py test/paper_trading/api/test_analytics_api.py
git commit -m "feat: calculate paper order activity averages"
```
