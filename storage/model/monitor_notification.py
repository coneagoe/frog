from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.sql import func

from monitor.domain_enums import NotificationDeliveryState

from .base import Base
from .orm_compat import Mapped, mapped_column

tb_name_monitor_notification = "monitor_notifications"


def _value_enum(enum_type: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
        native_enum=True,
        validate_strings=True,
        _create_events=False,
    )


class MonitorNotification(Base):
    __tablename__ = tb_name_monitor_notification
    __table_args__ = (Index("ix_monitor_notifications_state_next_attempt_at", "state", "next_attempt_at"),)

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, comment="通知ID")
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="监控目标ID")
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, comment="通知负载"
    )
    state: Mapped[str] = mapped_column(
        _value_enum(NotificationDeliveryState, "monitor_notification_delivery_state"),
        nullable=False,
        default=NotificationDeliveryState.PENDING.value,
        server_default=NotificationDeliveryState.PENDING.value,
        comment="投递状态",
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
