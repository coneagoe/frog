from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from paper_trading.domain.enums import Market, OrderSide, OrderStatus
from paper_trading.services.historical_etf_market_repair_service import (
    HistoricalEtfMarketRepairService,
    RepairCandidate,
    RepairedAccount,
)
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.storage.market_data import DailyBar
from paper_trading.storage.models import PaperOrder
from paper_trading.storage.repository import PaperTradingRepository
from storage.model.base import Base
from storage.model.etf_basic import ETFBasic
from test.paper_trading.fakes import FakeMarketDataProvider


class EtfMarketDataProvider(FakeMarketDataProvider):
    def get_daily_bar(self, symbol: str, trade_date: date, market: str | None = None) -> DailyBar:
        if symbol == "518880":
            assert market == Market.ETF.value
        return super().get_daily_bar(symbol, trade_date, market)


def _session_factory(tmp_path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'repair.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_candidates(tmp_path):
    session_factory = _session_factory(tmp_path)
    seed_session = session_factory()
    repo = PaperTradingRepository(seed_session)
    account = repo.create_account("repair", Decimal("100000"))
    seed_session.add(ETFBasic(基金代码="518880", 中文简称="Gold ETF", 交易所="SH", 存续状态="L"))
    candidate = repo.create_order(
        account.id,
        "518880",
        OrderSide.BUY,
        100,
        Decimal("8.80"),
        date(2026, 8, 7),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("885.00"),
    )
    untouched = repo.create_order(
        account.id,
        "000001",
        OrderSide.BUY,
        100,
        Decimal("10.00"),
        date(2026, 8, 7),
        OrderStatus.CANCELLED,
    )
    seed_session.commit()
    return session_factory, seed_session, account, candidate, untouched


def test_dry_run_reports_catalogue_backed_a_share_orders_without_writes(tmp_path):
    session_factory, seed_session, account, candidate, untouched = _seed_candidates(tmp_path)

    result = HistoricalEtfMarketRepairService(session_factory, FakeMarketDataProvider()).run()

    assert result.dry_run is True
    assert result.candidates == [RepairCandidate(account.id, candidate.id, "518880", date(2026, 8, 7))]
    assert result.corrected_orders == []
    assert result.repaired_accounts == []
    assert result.skipped_accounts == []
    assert result.failed_accounts == []
    seed_session.expire_all()
    assert seed_session.get(PaperOrder, candidate.id).market == Market.A_SHARE.value
    assert seed_session.get(PaperOrder, untouched.id).market == Market.A_SHARE.value


def test_apply_applies_catalogue_etf_order_and_rebuilds_derived_state(tmp_path):
    session_factory, seed_session, account, order, _ = _seed_candidates(tmp_path)
    trade_date = date(2026, 8, 7)
    repo = PaperTradingRepository(seed_session)
    repo.upsert_daily_bar_diagnostic(
        trade_date, Market.A_SHARE, "518880", "bfq", "missing_exact_date", [], resolved=False
    )
    seed_session.commit()
    market_data = EtfMarketDataProvider(
        {
            ("518880", trade_date): DailyBar(
                "518880", trade_date, Decimal("8.80"), Decimal("8.892"), Decimal("8.774"), Decimal("8.892")
            )
        }
    )

    result = HistoricalEtfMarketRepairService(session_factory, market_data).run(apply=True)

    assert result.corrected_orders == [RepairCandidate(account.id, order.id, "518880", trade_date)]
    assert result.repaired_accounts == [RepairedAccount(account.id, [order.id], trade_date)]
    assert result.failed_accounts == []
    seed_session.expire_all()
    persisted_order = seed_session.get(PaperOrder, order.id)
    assert persisted_order.market == Market.ETF.value
    assert persisted_order.status == OrderStatus.FILLED.value
    assert all(item.market == Market.ETF.value for item in repo.list_trades(account.id))
    assert repo.get_position(account.id, Market.ETF, "518880").total_quantity == 100
    assert all(item.market == Market.ETF.value for item in repo.get_lots(account.id, Market.ETF, "518880"))
    assert repo.list_cash_ledger(account.id)
    assert repo.list_round_trips(account.id)
    assert repo.list_snapshots(account.id)
    assert repo.list_matching_runs()
    assert repo.get_valuation_gap(account.id, trade_date) is None
    diagnostics = repo.list_daily_bar_diagnostics()
    assert any(item.market == Market.A_SHARE.value and item.stock_id == "518880" for item in diagnostics)
    assert not any(item.market == Market.ETF.value and item.stock_id == "518880" for item in diagnostics)
    assert all(item.market == Market.ETF.value for item in repo.list_trade_validity_checks(order.id))


def test_apply_locks_account_before_market_update(tmp_path, monkeypatch):
    session_factory, _, _, _, _ = _seed_candidates(tmp_path)
    calls: list[str] = []
    original_lock = PaperTradingRepository.lock_account
    original_update = PaperTradingRepository.update_orders_market

    def record_lock(repo, account_id):
        calls.append("lock")
        return original_lock(repo, account_id)

    def record_update(repo, order_ids, market):
        calls.append("update")
        return original_update(repo, order_ids, market)

    monkeypatch.setattr(PaperTradingRepository, "lock_account", record_lock)
    monkeypatch.setattr(PaperTradingRepository, "update_orders_market", record_update)

    HistoricalEtfMarketRepairService(session_factory, FakeMarketDataProvider()).run(apply=True)

    assert calls[:2] == ["lock", "update"]


def test_apply_rebuilds_each_account_once_from_earliest_corrected_date(tmp_path, monkeypatch):
    session_factory, seed_session, account, earlier, _ = _seed_candidates(tmp_path)
    repo = PaperTradingRepository(seed_session)
    later = repo.create_order(
        account.id,
        "518880",
        OrderSide.BUY,
        100,
        Decimal("8.80"),
        date(2026, 8, 8),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("885.00"),
    )
    seed_session.commit()
    calls: list[tuple[int, date, list[int]]] = []
    original_rebuild = OrderDeleteService.rebuild_account_from

    def record_rebuild(service, account_id, start_date, order_ids):
        calls.append((account_id, start_date, order_ids))
        return original_rebuild(service, account_id, start_date, order_ids)

    monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", record_rebuild)

    result = HistoricalEtfMarketRepairService(session_factory, FakeMarketDataProvider()).run(apply=True)

    assert calls == [(account.id, date(2026, 8, 7), [earlier.id, later.id])]
    assert result.repaired_accounts == [RepairedAccount(account.id, [earlier.id, later.id], date(2026, 8, 7))]


def test_apply_sanitizes_failure_error_and_keeps_prior_account(tmp_path, monkeypatch):
    session_factory, seed_session, first, first_order, _ = _seed_candidates(tmp_path)
    repo = PaperTradingRepository(seed_session)
    second = repo.create_account("second", Decimal("100000"))
    second_order = repo.create_order(
        second.id,
        "518880",
        OrderSide.BUY,
        100,
        Decimal("8.80"),
        date(2026, 8, 7),
        OrderStatus.ACCEPTED,
        frozen_cash=Decimal("885.00"),
    )
    seed_session.commit()
    original_rebuild = OrderDeleteService.rebuild_account_from

    def fail_second_account(service, account_id, start_date, order_ids):
        if account_id == second.id:
            raise RuntimeError("postgresql://repair_user:secret-token@db.example.test:5432/paper")
        return original_rebuild(service, account_id, start_date, order_ids)

    monkeypatch.setattr(OrderDeleteService, "rebuild_account_from", fail_second_account)

    result = HistoricalEtfMarketRepairService(session_factory, FakeMarketDataProvider()).run(apply=True)

    assert [item.account_id for item in result.repaired_accounts] == [first.id]
    assert [(item.account_id, item.error) for item in result.failed_accounts] == [(second.id, "repair failed")]
    response_data = str(result)
    assert "postgresql://" not in response_data
    assert "secret-token" not in response_data
    verification_session = session_factory()
    try:
        assert verification_session.get(PaperOrder, first_order.id).market == Market.ETF.value
        assert verification_session.get(PaperOrder, second_order.id).market == Market.A_SHARE.value
    finally:
        verification_session.close()


def test_second_apply_is_no_op_after_successful_repair(tmp_path):
    session_factory, _, _, _, _ = _seed_candidates(tmp_path)
    service = HistoricalEtfMarketRepairService(session_factory, FakeMarketDataProvider())

    service.run(apply=True)
    second = service.run(apply=True)

    assert second.candidates == []
    assert second.corrected_orders == []
    assert second.repaired_accounts == []
    assert second.skipped_accounts == []
    assert second.failed_accounts == []
