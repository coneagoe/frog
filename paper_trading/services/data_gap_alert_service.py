from __future__ import annotations

import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any, Callable, cast

from paper_trading.domain.enums import DataGapRecoveryAlertDeliveryState

_SENSITIVE_ERROR = re.compile(r"(?i)(password|passwd|secret|token|api[_ -]?key)\s*[=:]\s*[^\s,;]+")
_SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,47}$")
_SAFE_STOCK = re.compile(r"^[0-9]{6}$")


class DataGapAlertService:
    """Deliver durable data-gap alerts without changing recovery state."""

    def __init__(self, *, repository: Any, sender: Callable[[str, str], None] | None = None):
        self.repository = repository
        self.sender = sender or self._send_smtp

    def send_escalation(self, gap: Any, *, failure_class: str = "escalation") -> Any:
        return self._deliver(gap, f"escalation:{failure_class}", "Data gap escalation", failure_class)

    def send_recovery_system_failure(self, gap: Any, *, failure_class: str) -> Any:
        return self._deliver(gap, f"recovery_system:{failure_class}", "Data gap recovery system failure", failure_class)

    def send_account_recovery_failure(self, gap: Any, *, account_id: int, failure_class: str) -> Any:
        return self._deliver(
            gap,
            f"account:{account_id}:{failure_class}",
            "Data gap account recovery failure",
            failure_class,
            account_id=account_id,
        )

    def _deliver(
        self,
        gap: Any,
        cycle_key: str,
        subject: str,
        failure_class: str,
        *,
        account_id: int | None = None,
    ) -> Any:
        failure_class = self._safe_token(failure_class, "failure_class")
        if not isinstance(gap.id, int) or gap.id <= 0 or not _SAFE_STOCK.fullmatch(str(gap.stock_id)):
            raise ValueError("invalid gap identifier")
        if account_id is not None and (not isinstance(account_id, int) or account_id <= 0):
            raise ValueError("invalid account identifier")
        evidence: dict[str, Any] = {
            "event": subject.lower().replace(" ", "_"),
            "failure_class": failure_class,
            "business_date": gap.business_date.isoformat(),
            "stock_id": gap.stock_id,
        }
        if account_id is not None:
            evidence["account_id"] = account_id
        alert, claimed = self.repository.claim_alert(gap.id, cycle_key, evidence)
        if not claimed:
            return alert
        try:
            self.sender(subject, self._body(gap, failure_class, account_id))
        except Exception as exc:  # noqa: BLE001
            return self.repository.update_alert_delivery(
                alert.id,
                DataGapRecoveryAlertDeliveryState.FAILED,
                {"state": "failed", "error": self._safe_error(exc)},
            )
        return self.repository.update_alert_delivery(
            alert.id, DataGapRecoveryAlertDeliveryState.DELIVERED, {"state": "delivered"}
        )

    @staticmethod
    def _body(gap: Any, failure_class: str, account_id: int | None) -> str:
        account = f" account_id={account_id}" if account_id is not None else ""
        return (
            "Data gap recovery alert\n"
            f"gap_id={gap.id} business_date={gap.business_date.isoformat()} stock_id={gap.stock_id}"
            f"{account} failure_class={failure_class}"
        )

    @staticmethod
    def _safe_error(error: Exception) -> str:
        safe = _SENSITIVE_ERROR.sub(r"\1=[redacted]", str(error))
        return "".join(char if char.isprintable() else " " for char in safe)[:500]

    @staticmethod
    def _safe_token(value: str, name: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        value = value.strip().lower()
        if not _SAFE_TOKEN.fullmatch(value):
            raise ValueError(f"invalid {name}")
        return value

    @staticmethod
    def _send_smtp(subject: str, body: str) -> None:
        host = os.getenv("MAIL_SERVER") or os.getenv("SMTP_HOST")
        port = os.getenv("MAIL_PORT") or os.getenv("SMTP_PORT")
        sender = os.getenv("MAIL_SENDER") or os.getenv("SMTP_MAIL_FROM")
        password = os.getenv("MAIL_PASSWORD") or os.getenv("SMTP_PASSWORD")
        receivers = os.getenv("MAIL_RECEIVERS") or os.getenv("ALERT_EMAILS")
        if not all((host, port, sender, password, receivers)):
            raise RuntimeError("SMTP alert configuration is incomplete")
        host = cast(str, host)
        port = cast(str, port)
        sender = cast(str, sender)
        password = cast(str, password)
        receivers = cast(str, receivers)
        message = EmailMessage()
        message["From"] = sender
        message["To"] = receivers
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP_SSL(host, int(port)) as smtp:
            smtp.login(sender, password)
            smtp.send_message(message)
