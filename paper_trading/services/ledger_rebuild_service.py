from collections import defaultdict
from datetime import date, timedelta, timezone

from paper_trading.domain.enums import MatchingRunStatus, OrderStatus, PaperOrderEventType
from paper_trading.services.matching_service import MatchingService
from paper_trading.services.order_delete_service import OrderDeleteService
from paper_trading.services.round_trip_service import RoundTripService
from paper_trading.services.snapshot_service import SnapshotService
from paper_trading.services.trade_validity_service import TradeValidityService
from paper_trading.storage.hk_metadata import HkConnectMetadataProvider
from paper_trading.storage.market_data import MarketDataProvider
from paper_trading.storage.models import PaperLedgerRebuild, PaperOrder, PaperTradeValidityCheck
from paper_trading.storage.repository import PaperTradingRepository


class LedgerRebuildService:
    def __init__(
        self,
        repo: PaperTradingRepository,
        market_data: MarketDataProvider,
        hk_metadata: HkConnectMetadataProvider | None = None,
    ):
        self.repo = repo
        self.market_data = market_data
        self.hk_metadata = hk_metadata

    def rebuild_account_from(
        self,
        account_id: int,
        start_date: date,
        trigger_evidence: dict | None = None,
        triggering_order_ids: list[int] | None = None,
    ) -> PaperLedgerRebuild:
        deleted_counts: dict[str, int] = {}
        regenerated_counts: dict[str, int] = {"trades": 0, "snapshots": 0, "matching_runs": 0}
        self.repo.lock_account(account_id)
        rebuild = self.repo.create_ledger_rebuild_started(
            account_id,
            start_date,
            trigger_evidence=trigger_evidence,
            triggering_order_ids=triggering_order_ids,
        )
        try:
            with self.repo.session.begin_nested():
                rebuild_id = rebuild.id
                deleted_counts = self.repo.clear_account_rebuild_state_from(account_id, start_date)
                self.repo.reset_orders_for_replay_from(account_id, start_date)
                self.repo.session.expunge_all()
                self._replay_orders(account_id, start_date, regenerated_counts)
                self._regenerate_validity_checks(account_id, start_date)
                RoundTripService(self.repo).rebuild_account(account_id)
                persisted = self.repo.session.get(PaperLedgerRebuild, rebuild_id)
                if persisted is None:
                    raise RuntimeError(f"ledger rebuild audit disappeared: {rebuild_id}")
                return self.repo.complete_ledger_rebuild(persisted, deleted_counts, regenerated_counts)
        except Exception as exc:
            failed = self.repo.fail_ledger_rebuild(
                rebuild,
                error_details=str(exc),
                deleted_counts=deleted_counts,
                regenerated_counts=regenerated_counts,
            )
            self.repo.session.flush()
            if failed.id is None:
                raise RuntimeError("failed ledger rebuild audit was not persisted") from exc
            raise

    def _replay_orders(self, account_id: int, start_date: date, regenerated_counts: dict[str, int]) -> None:
        matching_service = MatchingService(self.repo, self.market_data, SnapshotService(self.repo, self.market_data))
        by_date: dict[date, list[PaperOrder]] = defaultdict(list)
        for order in self.repo.list_orders(account_id):
            if order.trade_date >= start_date and order.status == OrderStatus.ACCEPTED.value:
                self.repo.start_order_replay_lifecycle(order)
                by_date[order.trade_date].append(order)

        for trade_date in sorted(by_date):
            run, owner = self.repo.acquire_matching_run(trade_date, account_id)
            if owner:
                regenerated_counts["matching_runs"] += 1
            processed = filled = skipped = rejected = failed = warning_count = 0
            for order in sorted(by_date[trade_date], key=lambda current_order: current_order.id):
                processed += 1
                lifecycle_events = self.repo.list_effective_order_events(account_id, order.id)
                reservation_event = next(
                    (event for event in lifecycle_events if event.event_type == PaperOrderEventType.RESERVED.value),
                    None,
                )
                if reservation_event is None:
                    accepted_event = next(
                        (event for event in lifecycle_events if event.event_type == PaperOrderEventType.ACCEPTED.value),
                        None,
                    )
                    if accepted_event is None:
                        raise RuntimeError(f"order {order.id} has no accepted event for replay reservation")
                    # Legacy lifecycles may retain accepted/fill/release only;
                    # use their persisted accepted time, never wall-clock time.
                    reservation_at = accepted_event.event_at
                else:
                    reservation_at = reservation_event.event_at
                reservation_at = reservation_at.replace(tzinfo=timezone.utc)
                OrderDeleteService(self.repo, self.market_data, self.hk_metadata)._restore_single_reservation(
                    account_id, order, occurred_at=reservation_at
                )
                if order.status != OrderStatus.ACCEPTED.value:
                    rejected += 1
                    continue
                outcome = matching_service.match_order(order, trade_time=reservation_at + timedelta(microseconds=1))
                if outcome == "filled":
                    filled += 1
                    regenerated_counts["trades"] += 1
                elif outcome == "rejected":
                    rejected += 1
                elif outcome == "skipped":
                    skipped += 1
                elif outcome == "failed":
                    failed += 1
                    raise RuntimeError(f"ledger rebuild replay failed for order {order.id}")
                else:
                    warning_count += 1
            snapshot_outcome = matching_service.snapshot_service.generate_snapshot_or_gap(account_id, trade_date)
            if snapshot_outcome.snapshot is not None:
                regenerated_counts["snapshots"] += 1
            if snapshot_outcome.status == "valuation_gap":
                warning_count += 1
            run_status = (
                MatchingRunStatus.FAILED.value
                if failed
                else MatchingRunStatus.COMPLETED_WITH_WARNINGS.value
                if warning_count
                else MatchingRunStatus.COMPLETED.value
            )
            self.repo.update_matching_run_counts(
                run,
                processed,
                filled,
                skipped,
                rejected,
                failed,
                run_status,
                warning_count=warning_count,
            )

    def _regenerate_validity_checks(self, account_id: int, start_date: date) -> None:
        self.repo.session.query(PaperTradeValidityCheck).filter(
            PaperTradeValidityCheck.account_id == account_id,
            PaperTradeValidityCheck.trade_date >= start_date,
        ).delete(synchronize_session=False)

        validity_service = TradeValidityService(self.repo, self.market_data, hk_metadata=self.hk_metadata)
        for order in self.repo.list_orders(account_id):
            if order.trade_date >= start_date and order.status in (
                OrderStatus.ACCEPTED.value,
                OrderStatus.FILLED.value,
                OrderStatus.PARTIALLY_FILLED.value,
                OrderStatus.REJECTED.value,
                OrderStatus.CANCELLED.value,
            ):
                validity_service.analyze_order(order)
