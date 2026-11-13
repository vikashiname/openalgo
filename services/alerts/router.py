"""Turning order events into alerts, and alerts into deliveries.

Both steps are run by ``subscribers/alert_subscriber.py`` on the event bus:

1. ``alert_for`` reads an order event and, if it belongs to an alert group,
   returns the ``AlertRaisedEvent`` to publish.
2. ``receivers`` names the channels that group is routed to, switched on, so
   the alert is published only when somebody wants it and handed only to
   those channels.
"""

from __future__ import annotations

from collections.abc import Iterable

from events.alert_events import AlertRaisedEvent
from events.base import OrderEvent
from services.alerts.categories import CATEGORY_BY_TOPIC
from services.alerts.channels.base import AlertChannel
from services.alerts.settings import settings_for


def alert_for(event: OrderEvent) -> AlertRaisedEvent | None:
    """The alert an order event raises, or None when it raises none."""
    order_data = event.request_data
    if isinstance(order_data, dict):
        strat = str(order_data.get("strategy", "")).strip().upper()
        if (
            order_data.get("disable_telegram")
            or order_data.get("skip_telegram")
            or order_data.get("notify") is False
            or strat in [
                "MACDFNO",
                "EMACROSSOPEN",
                "OIFNO",
                "NIFTY_COVERED_CALL",
                "MACD_FNO_V1",
                "MACD_FNO_V2",
                "EMACROSSOPEN_V1",
                "EMACROSS_FNO_PAPER",
                "OIFNO_V1",
            ]
            or any(strat.startswith(p) for p in ["MACD", "EMA", "OI", "NIFTY_COVERED"])
        ):
            return None

    category = CATEGORY_BY_TOPIC.get(event.topic)
    if category is None:
        return None
    return AlertRaisedEvent(
        mode=event.mode,
        api_type=event.api_type,
        request_data=event.request_data,
        response_data=event.response_data,
        api_key=event.api_key,
        category=category,
        source_topic=event.topic,
    )


def receivers(category: str, channels: Iterable[AlertChannel]) -> list[AlertChannel]:
    """The channels that are on and receive ``category``, in registry order.

    A channel may still decline an alert it is given, by its own rules: a
    stopped Telegram bot, an unpaired WhatsApp device.
    """
    return [channel for channel in channels if settings_for(channel).receives(category)]


def deliver(channel: AlertChannel, alert: AlertRaisedEvent) -> bool:
    """Hand ``alert`` to ``channel`` if the trader routed its group there.

    Returns:
        Whether the channel was given the alert.
    """
    if not receivers(alert.category, (channel,)):
        return False
    channel.deliver(alert)
    return True
