"""Notificaciones opcionales por Telegram. Si no hay token configurado, solo loguea."""
from __future__ import annotations

import logging

import requests

from config import settings

log = logging.getLogger(__name__)


def send(msg: str) -> None:
    log.info("NOTIFY: %s", msg)
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": msg},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo enviar Telegram: %s", exc)
