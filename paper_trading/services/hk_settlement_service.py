from datetime import date

from paper_trading.storage.repository import PaperTradingRepository


class HkSettlementService:
    """Processes HK Connect T+2 settlements that have matured."""

    def __init__(self, repo: PaperTradingRepository):
        self.repo = repo

    def process_settlements(self, as_of_date: date) -> int:
        """Settle all pending HK sell proceeds whose expected date <= as_of_date.

        Returns the count of settlements processed.
        """
        accounts = self.repo.list_accounts()
        count = 0
        for account in accounts:
            pending_list = self.repo.list_pending_settlements(account.id)
            for pending in pending_list:
                if pending.expected_settle_date <= as_of_date:
                    self.repo.settle_pending(pending.id)
                    count += 1
        return count
