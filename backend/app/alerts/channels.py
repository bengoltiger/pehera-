"""Notification channel adapters (Section 49).

Every channel implements the same interface. The prototype ships simulated
adapters only -- they write a delivery record and nothing leaves the machine.
Each record carries `is_simulated=True` and the UI renders "SIMULATED
DELIVERY" wherever it is shown. No real gateway is configured, and PEHRA never
claims otherwise.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import List

from app.core.config import settings


@dataclass
class DeliveryResult:
    channel: str
    provider: str
    status: str
    recipient_count: int
    is_simulated: bool
    detail: str
    sent_at: dt.datetime
    delivered_at: dt.datetime | None


class NotificationChannel(abc.ABC):
    key: str = "base"
    label: str = "Base"
    is_simulated: bool = True
    provider_name: str = "SimulatedChannel"

    @abc.abstractmethod
    def enabled(self) -> bool: ...

    @abc.abstractmethod
    def send(self, *, alert, recipients: int, message: str) -> DeliveryResult: ...

    def describe(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "enabled": self.enabled(),
            "is_simulated": self.is_simulated,
            "provider": self.provider_name,
            "note": "Simulated delivery — no message leaves this machine."
            if self.is_simulated
            else "Live gateway configured.",
        }


class _SimulatedChannel(NotificationChannel):
    is_simulated = True
    #: fraction of recipients the simulated funnel marks as delivered
    delivery_ratio = 1.0

    def send(self, *, alert, recipients: int, message: str) -> DeliveryResult:
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        delivered = int(recipients * self.delivery_ratio)
        return DeliveryResult(
            channel=self.key,
            provider=self.provider_name,
            status="delivered",
            recipient_count=delivered,
            is_simulated=True,
            detail=(
                f"SIMULATED DELIVERY — {delivered:,} of {recipients:,} notional recipients on the "
                f"{self.label} channel. No {self.label.lower()} was actually transmitted; "
                "no real gateway is configured in this prototype."
            ),
            sent_at=now,
            delivered_at=now,
        )


class PushChannel(_SimulatedChannel):
    key = "push"
    label = "Push"
    provider_name = "SimulatedPushService"
    delivery_ratio = 0.94

    def enabled(self) -> bool:
        return settings.notification_push_enabled


class SmsChannel(_SimulatedChannel):
    key = "sms"
    label = "SMS"
    provider_name = "SimulatedSmsGateway"
    delivery_ratio = 0.88

    def enabled(self) -> bool:
        # A real gateway would require settings.sms_gateway_url. It is not set,
        # so this channel is honest about being simulated.
        return settings.notification_sms_enabled


class EmailChannel(_SimulatedChannel):
    key = "email"
    label = "Email"
    provider_name = "SimulatedSmtpRelay"
    delivery_ratio = 0.97

    def enabled(self) -> bool:
        return settings.notification_email_enabled


class InAppChannel(_SimulatedChannel):
    key = "inapp"
    label = "In-app"
    provider_name = "PehraInAppBus"
    delivery_ratio = 1.0

    def enabled(self) -> bool:
        return settings.notification_inapp_enabled


CHANNELS: List[NotificationChannel] = [InAppChannel(), PushChannel(), SmsChannel(), EmailChannel()]


def get_channels(keys: List[str] | None = None) -> List[NotificationChannel]:
    if not keys:
        return [c for c in CHANNELS if c.enabled()]
    return [c for c in CHANNELS if c.key in keys and c.enabled()]
