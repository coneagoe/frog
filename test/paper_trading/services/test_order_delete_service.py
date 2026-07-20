from datetime import date
from decimal import Decimal

import pytest

from paper_trading.domain.enums import REPLAY_REJECTION_MARKER, CashEventType, MatchingRunStatus, OrderSide, OrderStatus
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.services.order_service import OrderService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.repository import PaperTradingRepository
from test.paper_trading.fakes import FakeMarketDataProvider


def test_delete_missing_order_returns_false(session):
    repo = PaperTradingRepository(session)
    service = OrderDeleteService(repo, FakeMarketDataProvider())

    assert service.delete_order(999999) is False


def test_delete_filled_order_rebuilds_account_from_remaining_orders(session):
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))
    first = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("1005.0000"),
    )
    second = repo.create_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("2005.0000"),
    )
    snapshot_service = SnapshotService(repo, market_data)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 17), account.id)
    MatchingService(repo, market_data, snapshot_service).run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 2

    deleted = OrderDeleteService(repo, market_data).delete_order(first.id)

    assert deleted is True
    with pytest.raises(KeyError):
        repo.get_order(first.id)
    remaining_orders = repo.list_orders(account.id)
    assert [order.id for order in remaining_orders] == [second.id]
    trades = repo.list_trades(account.id)
    assert len(trades) == 1
    assert trades[0].order_id == second.id
    positions = repo.get_positions(account.id)
    assert [(position.symbol, int(position.total_quantity)) for position in positions] == [("000002", 100)]
    assert all(snapshot.trade_date >= date(2026, 7, 18) for snapshot in repo.list_snapshots(account.id))
    ledger = repo.list_cash_ledger(account.id)
    assert ledger[0].note == "initial_cash"
    assert repo.get_cash_available(account.id) < Decimal("100000")


# ── Bug reproduction: cash freeze / position freeze / validity checks ──────────


def test_delete_surviving_buy_has_correct_cash_available(session):
    """Surviving filled BUY order replayed after sibling-delete must have
    cash_available = initial_cash − actual_cost_of_surviving_order.

    Without the fix the cash FREEZE ledger event is not recreated before
    the replay MatchringService.run, so cash_available stays at initial_cash
    (the freeze is missing and release = frozen_cash − actual_cost = 0).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place two BUY orders via OrderService so real freeze events are created.
    order1 = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order2 = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )

    # Fill both through matching.
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)

    # Confirm both had freeze events before delete.
    ledger_before = repo.list_cash_ledger(account.id)
    freeze_before = [e for e in ledger_before if e.event_type == CashEventType.FREEZE.value]
    assert len(freeze_before) == 2

    # Delete the first order.
    deleted = OrderDeleteService(repo, market_data).delete_order(order1.id)
    assert deleted is True

    # Correct cash = 100000 − frozen_cash(order2) = 100000 − 2005.02
    expected_cash = Decimal("97994.9800")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash_available={expected_cash}, got {actual_cash}"

    # The cash ledger must contain a FREEZE event for the surviving order.
    ledger = repo.list_cash_ledger(account.id)
    freeze_events = [e for e in ledger if e.event_type == CashEventType.FREEZE.value]
    assert len(freeze_events) == 1
    assert freeze_events[0].order_id == order2.id


def test_delete_surviving_sell_replay_not_negative_frozen_quantity(session):
    """Surviving filled SELL order replayed after sibling-delete must not
    produce a negative frozen_quantity on the position.

    The replay resets the SELL order to ACCEPTED with frozen_quantity intact,
    but positions are rebuilt from imported lots with frozen_quantity=0.
    Without the fix _settle_sell computes  0 − frozen_quantity < 0.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    # Seed an imported lot (durable baseline) for the sell symbol.
    repo.upsert_position(
        account.id,
        "000001",
        total_quantity=200,
        frozen_quantity=0,
        cost_amount=Decimal("2000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "000001",
        date(2026, 7, 15),
        200,
        200,
        Decimal("10.00"),
        source="imported",
    )

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place a SELL that will fill and a BUY that will be deleted.
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    buy_order = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )

    # Fill both.
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)

    # Delete the BUY — replay must process the surviving SELL.
    deleted = OrderDeleteService(repo, market_data).delete_order(buy_order.id)
    assert deleted is True

    # The imported-position replay must keep frozen_quantity non-negative.
    position = repo.get_position(account.id, "000001")
    assert position is not None
    assert position.frozen_quantity >= 0, f"Negative frozen_quantity: {position.frozen_quantity}"
    assert int(position.frozen_quantity) == 0, f"Expected frozen_quantity=0 after fill, got {position.frozen_quantity}"
    # 200 imported − 100 sold = 100 remaining
    assert int(position.total_quantity) == 100, f"Expected total_quantity=100, got {position.total_quantity}"


def test_delete_regenerates_validity_checks_for_surviving_orders(session):
    """After order-delete clears all PaperTradeValidityCheck rows and replays,
    surviving orders must have validity checks regenerated.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    order1 = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order2 = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )

    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)

    # Delete the first order — second survives.
    deleted = OrderDeleteService(repo, market_data).delete_order(order1.id)
    assert deleted is True

    # Surviving order must have at least one validity check re-generated.
    checks = repo.list_trade_validity_checks(order2.id)
    assert len(checks) > 0, f"Surviving order should have regenerated validity checks, got {len(checks)}"


def test_delete_surviving_buy_then_sell_same_symbol_preserves_position(session):
    """When a surviving BUY on T1 and surviving SELL on T2 share the same
    symbol, and both are replayed after a sibling-delete, the position must
    have non-negative frozen_quantity and correct total_quantity.

    The previous approach restored *all* reservations upfront, but the SELL
    freeze restore failed because the BUY-derived position did not yet exist
    (it was wiped by clear_account_rebuild_state).  The fix restores
    reservations per trade date, so the BUY replay creates the position
    before the SELL freeze is applied.

    Note: the sell order is placed *after* the buy matching run, because
    OrderService._accept_sell_order requires a non-zero position at the
    time the order is placed (real-world: the position could come from
    a prior day's fill or imported lots).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Order 1: BUY 000001 on 7/17.
    buy = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    # Fill the buy first to create the position, so the sell can be placed.
    matching_service.run(date(2026, 7, 17), account.id)

    # Order 2: SELL 000001 on 7/18 (position now exists, T+1 satisfied because
    # the lot was created on 7/17 < 7/18).
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    # Order 3: unrelated BUY that will be deleted.
    delete_me = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 19),
    )

    # Fill remaining.
    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)

    # Confirm we have 3 trades before delete.
    all_trades = repo.list_trades(account.id)
    assert len(all_trades) == 3

    # Delete the unrelated BUY — must replay the buy + sell for 000001.
    deleted = OrderDeleteService(repo, market_data).delete_order(delete_me.id)
    assert deleted is True

    # Position for the buy/sell symbol must be correct.
    position = repo.get_position(account.id, "000001")
    assert position is not None
    assert int(position.frozen_quantity) == 0, (
        f"Expected frozen_quantity=0 after full cycle, got {position.frozen_quantity}"
    )
    assert int(position.total_quantity) == 0, (
        f"Expected total_quantity=0 after buy 100 / sell 100, got {position.total_quantity}"
    )

    # Trades for the buy+sell must survive.
    trades = repo.list_trades(account.id)
    surviving_symbols = [t.symbol for t in trades]
    assert surviving_symbols == ["000001", "000001"], f"Expected two trades for 000001, got {surviving_symbols}"

    # Cash must reflect buy cost and sell proceeds.
    # initial 100000 − buy_cost(1005.01) + sell_net(1494.23) = 100489.22
    expected_cash = Decimal("100489.2200")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"

    # Both surviving orders must have validity checks regenerated.
    for surviving_order in (buy, sell):
        checks = repo.list_trade_validity_checks(surviving_order.id)
        assert len(checks) > 0, f"Order {surviving_order.id} missing regenerated validity checks"


def test_delete_inventory_buy_rejects_surviving_sell_without_naked_trade(session):
    """When the BUY that provided inventory for a later SELL is deleted, the
    surviving SELL must be rejected during replay and must NOT produce a
    naked trade or cash event (MatchingService._settle_sell creates the cash
    TRADE event before returning early if position is None).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # BUY that creates inventory for the SELL.
    buy = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    matching_service.run(date(2026, 7, 17), account.id)

    # SELL that consumes the BUY inventory.
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    # Unrelated surviving order so the account is non-empty after delete.
    order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 19),
    )

    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)

    assert len(repo.list_trades(account.id)) == 3

    # DELETE THE INVENTORY BUY — the SELL should now be rejected on replay.
    deleted = OrderDeleteService(repo, market_data).delete_order(buy.id)
    assert deleted is True

    # The sell must be rejected, not filled or accepted.
    sell_order = repo.get_order(sell.id)
    assert sell_order.status == OrderStatus.REJECTED.value, f"Expected REJECTED, got {sell_order.status}"

    # No trades for the sell symbol (no naked sell).
    trades = repo.list_trades(account.id)
    sell_trades = [t for t in trades if t.symbol == "000001"]
    assert len(sell_trades) == 0, f"Expected 0 sell trades for 000001, got {len(sell_trades)}"

    # No position for the sold symbol.
    position = repo.get_position(account.id, "000001")
    assert position is None or int(position.total_quantity) == 0

    # Cash must not include sell proceeds.
    # Only the surviving BUY 000002 freeze remains: 100000 − 2005.02 = 97994.98
    expected_cash = Decimal("97994.9800")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"


def test_delete_preserves_validity_checks_for_canceled_order(session):
    """Surviving canceled orders must have validity checks regenerated after
    delete+replay clears all PaperTradeValidityCheck rows.

    OrderService.place_order creates a validity check for accepted orders,
    and cancel_order changes the status to CANCELLED but does not remove
    the check.  After clear+replay the check must be recreated.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place an order and cancel it.
    order = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order_service.cancel_order(order.id)

    # Place an unrelated order that will be deleted.
    other = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )

    # Delete the unrelated order.
    deleted = OrderDeleteService(repo, market_data).delete_order(other.id)
    assert deleted is True

    # Canceled order must have validity checks regenerated.
    checks = repo.list_trade_validity_checks(order.id)
    assert len(checks) > 0, f"Canceled order should have regenerated validity checks, got {len(checks)}"

    # Order remains canceled.
    assert repo.get_order(order.id).status == OrderStatus.CANCELLED.value


def test_delete_over_reserved_same_date_sells_rejects_unsupported(session):
    """When multiple surviving SELL orders share the same trade date and
    symbol, and a deleted order removed part of the backing inventory,
    _restore_date_reservations must check *available* quantity
    (total − already-restored frozen), not total alone — otherwise the
    second SELL over-reserves and matching drives total_quantity negative.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── Baseline: imported lot (60 shares) ────────────────────────────────
    repo.upsert_position(
        account.id,
        "000001",
        total_quantity=60,
        frozen_quantity=0,
        cost_amount=Decimal("600.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "000001",
        date(2026, 7, 14),
        60,
        60,
        Decimal("10.00"),
        source="imported",
    )

    # ── BUY-A (will be deleted): 100 shares @ 10, trade_date=7/15 ────────
    buy_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 15),
    )
    matching_service.run(date(2026, 7, 15), account.id)

    # ── BUY-B (survives): 100 shares @ 10, trade_date=7/16 ───────────────
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)

    # Position: 60 (imported) + 100 (BUY-A) + 100 (BUY-B) = 260
    pos = repo.get_position(account.id, "000001")
    assert pos is not None
    assert int(pos.total_quantity) == 260

    # ── Two SELL orders, same date & symbol (100 each = 200, fits 260) ───
    sell_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    sell_b = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )

    matching_service.run(date(2026, 7, 18), account.id)

    # Both filled: position = 260 − 100 − 100 = 60
    pos = repo.get_position(account.id, "000001")
    assert pos is not None
    assert int(pos.total_quantity) == 60
    assert len(repo.list_trades(account.id)) == 4  # 2 buys + 2 sells

    # ── DELETE BUY-A (removes 100 shares of inventory) ───────────────────
    deleted = OrderDeleteService(repo, market_data).delete_order(buy_a.id)
    assert deleted is True

    # After clear: imported lot (60) survives.  BUY-A and BUY-B lots
    # (source="trade") are deleted.  Position rebuilt: total=60, frozen=0.
    # Orders: BUY-B (ACCEPTED, 100@10), SELL A (100), SELL B (100).
    # Dates: [7/16, 7/18]

    # Verify final position is non-negative and correct.
    position = repo.get_position(account.id, "000001")
    assert position is not None
    assert int(position.frozen_quantity) >= 0, f"Negative frozen_quantity: {position.frozen_quantity}"
    # Position = 60 (imported) + 100 (BUY-B replay) − 100 (one sell) = 60
    expected_qty = 60
    assert int(position.total_quantity) == expected_qty, (
        f"Expected total_quantity={expected_qty}, got {position.total_quantity}"
    )

    # Only one sell should have been filled (insufficient inventory for both).
    sell_a_reloaded = repo.get_order(sell_a.id)
    sell_b_reloaded = repo.get_order(sell_b.id)
    sell_filled_ids = {o.id for o in (sell_a_reloaded, sell_b_reloaded) if o.status == OrderStatus.FILLED.value}
    sell_rejected_ids = {o.id for o in (sell_a_reloaded, sell_b_reloaded) if o.status == OrderStatus.REJECTED.value}
    assert len(sell_filled_ids) == 1, f"Expected exactly 1 sell FILLED, got {len(sell_filled_ids)}"
    assert len(sell_rejected_ids) == 1, f"Expected exactly 1 sell REJECTED, got {len(sell_rejected_ids)}"

    # Trades: only BUY-B fill + the one supported sell = 2 trades.
    trades = repo.list_trades(account.id)
    assert len(trades) == 2, f"Expected 2 trades (BUY-B + 1 sell), got {len(trades)}"

    # Cash must not include the unsupported sell proceeds.
    # initial 100000 − BUY-B frozen(1005.01) + supported sell net(1494.23)
    expected_cash = Decimal("100489.2200")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"


def test_delete_sell_funded_buy_rejects_when_cash_insufficient(session):
    """When a SELL that funded a later BUY is deleted, the BUY must be
    rejected during replay if the remaining cash cannot support its freeze.
    Otherwise the unconditional freeze drives cash_available negative.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Imported lot to back the sell.
    repo.upsert_position(
        account.id,
        "000001",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "000001",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )

    # SELL that fills and creates proceeds (net = 1494.23).
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 17),
    )
    matching_service.run(date(2026, 7, 17), account.id)
    # Cash: 100000 + 1494.23 = 101494.23

    # BUY affordable only with sell proceeds (frozen_cash = 100031.00 > 100000).
    buy = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        1000,
        Decimal("100.00"),
        date(2026, 7, 18),
    )
    matching_service.run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 2

    # Delete the SELL → BUY becomes unsupportable.
    deleted = OrderDeleteService(repo, market_data).delete_order(sell.id)
    assert deleted is True

    # BUY must be rejected, not filled.
    buy_order = repo.get_order(buy.id)
    assert buy_order.status == OrderStatus.REJECTED.value, f"Expected REJECTED, got {buy_order.status}"

    # Cash must not be negative.
    cash = repo.get_cash_available(account.id)
    assert cash >= 0, f"Negative cash: {cash}"
    assert cash == Decimal("100000.0000"), f"Expected cash=100000, got {cash}"

    # No trades at all (sell deleted, buy rejected).
    trades = repo.list_trades(account.id)
    assert len(trades) == 0, f"Expected 0 trades after sell delete+replay, got {len(trades)}"

    # No position for the buy symbol (never created).
    pos = repo.get_position(account.id, "000002")
    assert pos is None


def test_delete_same_date_sell_fills_before_buy_cash_check(session):
    """When a surviving lower-id SELL and higher-id BUY share the same trade
    date, the SELL must be restored/matched *before* the BUY's cash check,
    so the SELL's proceeds make the BUY affordable.

    Per-date reservation restore fails here because it checks cash for ALL
    same-date orders before any matching, so the BUY sees only initial cash
    (without SELL proceeds).  Per-order (trade_date, id) fixes this.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── Two imported lots ────────────────────────────────────────────────
    # 000001 (back the surviving sell)
    repo.upsert_position(
        account.id,
        "000001",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "000001",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )
    # 999999 (back the prior sell that will be deleted)
    repo.upsert_position(
        account.id,
        "999999",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "999999",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )

    # ── Prior SELL (provides cash for BUY, will be deleted) ──────────────
    prior_sell = order_service.place_order(
        account.id,
        "999999",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)
    # Cash: 100000 + 1494.23 = 101494.23

    # ── Surviving same-date orders ───────────────────────────────────────
    # SELL (lower ID): 000001, 100 @ 15, trade_date=7/18
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )
    # BUY (higher ID): 000002, 1000 @ 100, trade_date=7/18
    buy = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        1000,
        Decimal("100.00"),
        date(2026, 7, 18),
    )
    matching_service.run(date(2026, 7, 18), account.id)
    assert len(repo.list_trades(account.id)) == 3  # prior sell + same-date sell + buy

    # ── Delete the prior SELL → cash drops to 100000 ─────────────────────
    deleted = OrderDeleteService(repo, market_data).delete_order(prior_sell.id)
    assert deleted is True

    # Both surviving same-date orders must fill (SELL proceeds fund the BUY).
    sell_order = repo.get_order(sell.id)
    buy_order = repo.get_order(buy.id)
    assert sell_order.status == OrderStatus.FILLED.value, f"Expected SELL FILLED, got {sell_order.status}"
    assert buy_order.status == OrderStatus.FILLED.value, f"Expected BUY FILLED, got {buy_order.status}"

    # Cash = 100000 + 1494.23 - 100031.00 = 1463.23
    expected_cash = Decimal("1463.2300")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"

    # 2 trades (sell + buy), no trades for the deleted symbol.
    trades = repo.list_trades(account.id)
    assert len(trades) == 2, f"Expected 2 trades, got {len(trades)}"
    for t in trades:
        assert t.symbol in ("000001", "000002"), f"Unexpected trade symbol: {t.symbol}"

    # Position 000001 = 0 (sold), 000002 = 1000 (bought).
    pos1 = repo.get_position(account.id, "000001")
    assert pos1 is not None and int(pos1.total_quantity) == 0
    pos2 = repo.get_position(account.id, "000002")
    assert pos2 is not None and int(pos2.total_quantity) == 1000


def test_delete_snapshot_per_date_not_final_state(session):
    """Snapshots after delete+replay must reflect state at each trade date,
    not the final state after all dates have been replayed.

    Without per-date snapshot generation, an earlier-date snapshot would
    include positions/trades created by a later date's replay.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Order A (survives): BUY 000001 on 7/17 → position 000001 created.
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    # Order B (survives): BUY 000002 on 7/18 → position 000002 created.
    order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )
    # Order C (will be deleted): BUY 000003 on 7/19.
    order_c = order_service.place_order(
        account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("30.00"),
        date(2026, 7, 19),
    )

    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)
    assert len(repo.list_trades(account.id)) == 3

    # Delete order C → replay re-processes 7/17 and 7/18.
    deleted = OrderDeleteService(repo, market_data).delete_order(order_c.id)
    assert deleted is True

    snapshots = repo.list_snapshots(account.id)
    # Must have snapshots for both replayed dates.
    assert len(snapshots) == 2, f"Expected 2 snapshots, got {len(snapshots)}"

    snap_17 = next(s for s in snapshots if s.trade_date == date(2026, 7, 17))
    snap_18 = next(s for s in snapshots if s.trade_date == date(2026, 7, 18))

    # 7/17 snapshot: only position 000001 exists (just bought this day).
    assert snap_17.position_count == 1, f"7/17 snapshot should have 1 position, got {snap_17.position_count}"
    # 7/18 snapshot: both positions exist (000001 from 7/17 + 000002 bought this day).
    assert snap_18.position_count == 2, f"7/18 snapshot should have 2 positions, got {snap_18.position_count}"


def test_delete_regenerates_matching_runs(session):
    """After delete+replay, PaperMatchingRun records must be recreated for
    all replayed trade dates with COMPLETED status.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # Two surviving orders on different dates.
    order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )
    order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        100,
        Decimal("20.00"),
        date(2026, 7, 18),
    )
    # One order to delete so replay is triggered.
    order_c = order_service.place_order(
        account.id,
        "000003",
        OrderSide.BUY,
        100,
        Decimal("30.00"),
        date(2026, 7, 19),
    )
    matching_service.run(date(2026, 7, 17), account.id)
    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)
    assert len(repo.list_matching_runs()) == 3

    deleted = OrderDeleteService(repo, market_data).delete_order(order_c.id)
    assert deleted is True

    runs = repo.list_matching_runs()
    # Original runs deleted + 2 new ones (7/17 and 7/18).
    assert len(runs) == 2, f"Expected 2 matching runs, got {len(runs)}"
    for run in runs:
        assert run.status == MatchingRunStatus.COMPLETED.value, f"Expected COMPLETED, got {run.status}"


def test_match_order_unavailable_data_fails_not_rejects(session):
    """When market data is unavailable during replay matching,
    match_order must return 'failed' (not call _reject_order which
    releases reservations and changes status).
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)

    # Place an order via the normal provider.
    order = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 17),
    )

    # Create a provider that raises KeyError.
    class UnavailableMarketData(FakeMarketDataProvider):
        def get_daily_bar(self, symbol, trade_date):
            raise KeyError(f"No data for {symbol}")

    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, UnavailableMarketData(), snapshot_service)

    outcome = matching_service.match_order(order)

    # Must return 'failed' not True/False.
    assert outcome == "failed", f"Expected 'failed', got {outcome!r}"
    # Order stays ACCEPTED, not rejected.
    assert order.status == OrderStatus.ACCEPTED.value, f"Expected ACCEPTED, got {order.status}"


def test_delete_same_date_buy_then_sell_t1_rejects_if_no_matured_lot(session):
    """When a prior-day BUY (matured inventory) is deleted, a surviving
    same-date lower-id BUY and higher-id SELL must not let the SELL consume
    the same-day lot (A-share T+1).  Replay must check matured lots only
    (buy_trade_date < trade_date), not aggregate total_quantity.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── BUY A (will be deleted): creates matured inventory on 7/16 ──────
    buy_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)
    # Position: 100 shares, lot buy_trade_date=7/16 (matured by 7/18)

    # ── Same-date surviving orders on 7/18 ──────────────────────────────
    # BUY B (lower ID, same symbol): creates a lot on 7/18
    buy_b = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 7, 18),
    )
    # SELL (higher ID, same symbol): tries to sell 100 shares
    sell = order_service.place_order(
        account.id,
        "000001",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 18),
    )

    matching_service.run(date(2026, 7, 18), account.id)
    # Both fill: position = 200 (100 from 7/16 + 100 from 7/18) − 100 = 100
    assert len(repo.list_trades(account.id)) == 3

    # ── Delete BUY A (removes the matured lot) ──────────────────────────
    deleted = OrderDeleteService(repo, market_data).delete_order(buy_a.id)
    assert deleted is True

    # After replay:
    # - BUY B fills: creates lot on 7/18, position 000001: total=100
    # - SELL checks matured lots: only lot is buy_trade_date=7/18,
    #   which is NOT < 7/18 → matured=0 → SELL must be REJECTED.

    sell_order = repo.get_order(sell.id)
    assert sell_order.status == OrderStatus.REJECTED.value, f"Expected SELL REJECTED (T+1), got {sell_order.status}"
    assert sell_order.rejection_code == "A_SHARE_T1_VIOLATION", (
        f"Expected A_SHARE_T1_VIOLATION, got {sell_order.rejection_code}"
    )

    buy_b_order = repo.get_order(buy_b.id)
    assert buy_b_order.status == OrderStatus.FILLED.value, f"Expected BUY FILLED, got {buy_b_order.status}"

    # Position: only the 100 from BUY B remain (sell did not go through).
    position = repo.get_position(account.id, "000001")
    assert position is not None
    assert int(position.total_quantity) == 100, f"Expected total_quantity=100, got {position.total_quantity}"
    assert int(position.frozen_quantity) == 0, f"Expected frozen_quantity=0, got {position.frozen_quantity}"

    # Cash = 100000 − BUY B freeze(1005.01) = 98994.99 (no sell proceeds).
    expected_cash = Decimal("98994.9900")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"

    # Only the buy trade survives (no sell trade).
    trades = repo.list_trades(account.id)
    assert len(trades) == 1, f"Expected 1 trade, got {len(trades)}"
    assert trades[0].side == OrderSide.BUY.value


def test_replay_rejected_order_reconsidered_on_later_delete(session):
    """A replay-induced rejection must not be sticky across subsequent deletes.
    If delete #1 rejects a BUY due to removed funding, and delete #2 removes
    a cash-consuming order making the BUY affordable, the BUY should be
    reconsidered and fill.  Original (non-replay) rejections must persist.
    """
    repo = PaperTradingRepository(session)
    market_data = FakeMarketDataProvider()
    account = repo.create_account("demo", Decimal("100000"))

    validity_service = TradeValidityService(repo, market_data)
    order_service = OrderService(repo, market_data, validity_service)
    snapshot_service = SnapshotService(repo, market_data)
    matching_service = MatchingService(repo, market_data, snapshot_service)

    # ── Imported lots for the prior SELL symbol ─────────────────────────
    repo.upsert_position(
        account.id,
        "999999",
        total_quantity=100,
        frozen_quantity=0,
        cost_amount=Decimal("1000.0000"),
        source="imported",
    )
    repo.create_position_lot(
        account.id,
        "999999",
        date(2026, 7, 14),
        100,
        100,
        Decimal("10.00"),
        source="imported",
    )

    # ── Prior SELL (deleted in delete #1): provides cash for BUY B ──────
    prior_sell = order_service.place_order(
        account.id,
        "999999",
        OrderSide.SELL,
        100,
        Decimal("15.00"),
        date(2026, 7, 16),
    )
    matching_service.run(date(2026, 7, 16), account.id)

    # ── BUY A (deleted in delete #2): consumes cash ─────────────────────
    buy_a = order_service.place_order(
        account.id,
        "000001",
        OrderSide.BUY,
        400,
        Decimal("100.00"),
        date(2026, 7, 17),
    )
    matching_service.run(date(2026, 7, 17), account.id)

    # ── BUY B (reconsidered after delete #2): needs SELL cash ───────────
    buy_b = order_service.place_order(
        account.id,
        "000002",
        OrderSide.BUY,
        600,
        Decimal("100.00"),
        date(2026, 7, 18),
    )

    # ── Original rejection (must persist across deletes) ─────────────────
    orig_rejected = order_service.place_order(
        account.id,
        "000003",
        OrderSide.BUY,
        250,
        Decimal("10.00"),
        date(2026, 7, 19),
    )

    matching_service.run(date(2026, 7, 18), account.id)
    matching_service.run(date(2026, 7, 19), account.id)
    assert orig_rejected.status == OrderStatus.REJECTED.value
    assert len(repo.list_trades(account.id)) == 3  # SELL + BUY A + BUY B

    # ── DELETE #1: remove the prior SELL → BUY B becomes unaffordable ───
    delete_svc = OrderDeleteService(repo, market_data)
    deleted1 = delete_svc.delete_order(prior_sell.id)
    assert deleted1 is True

    buy_b_after_d1 = repo.get_order(buy_b.id)
    assert buy_b_after_d1.status == OrderStatus.REJECTED.value, (
        f"After delete #1, BUY B should be REJECTED, got {buy_b_after_d1.status}"
    )
    # Must carry the replay marker.
    assert buy_b_after_d1.rejection_reason is not None
    assert buy_b_after_d1.rejection_reason.startswith(REPLAY_REJECTION_MARKER), (
        f"Expected replay marker, got: {buy_b_after_d1.rejection_reason}"
    )

    # Original rejection persists and is NOT marked.
    orig_after_d1 = repo.get_order(orig_rejected.id)
    assert orig_after_d1.status == OrderStatus.REJECTED.value
    assert orig_after_d1.rejection_reason is None or not orig_after_d1.rejection_reason.startswith(
        REPLAY_REJECTION_MARKER
    ), "Original rejection should not have replay marker"

    # ── DELETE #2: remove BUY A → BUY B should become affordable ────────
    delete_svc2 = OrderDeleteService(repo, market_data)
    deleted2 = delete_svc2.delete_order(buy_a.id)
    assert deleted2 is True

    # BUY B must be reconsidered and fill.
    buy_b_after_d2 = repo.get_order(buy_b.id)
    assert buy_b_after_d2.status == OrderStatus.FILLED.value, (
        f"After delete #2, BUY B should be FILLED, got {buy_b_after_d2.status}"
    )

    # Original rejection still persists.
    orig_after_d2 = repo.get_order(orig_rejected.id)
    assert orig_after_d2.status == OrderStatus.REJECTED.value

    # Cash: 100000 − BUY B frozen(60018.60) = 39981.40
    expected_cash = Decimal("39981.4000")
    actual_cash = repo.get_cash_available(account.id)
    assert actual_cash == expected_cash, f"Expected cash={expected_cash}, got {actual_cash}"
