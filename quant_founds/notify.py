"""Notifications (blueprint 10/17): pluggable alert delivery.

Credentials come only from environment variables - never from config files
or code. Without env vars everything degrades to console-only.
"""
from __future__ import annotations

import json
import os
import urllib.request


def _post_json(url: str, payload: dict, timeout: float = 10.0,
               transport=None) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    opener = transport or urllib.request.urlopen
    with opener(req, timeout=timeout) as resp:
        resp.read()


class ConsoleNotifier:
    name = "console"

    def send(self, title: str, message: str) -> None:
        print(f"[alert] {title}: {message}")


class WebhookNotifier:
    """Generic JSON webhook (Discord/Slack-compatible relays etc.)."""
    name = "webhook"

    def __init__(self, url: str, transport=None):
        self.url = url
        self._transport = transport or _post_json

    def send(self, title: str, message: str) -> None:
        try:
            self._transport(self.url, {"content": f"{title}\n{message}"})
        except Exception as exc:
            print(f"[alert] webhook delivery failed: {exc}")


class TelegramNotifier:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, transport=None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._transport = transport or _post_json

    def send(self, title: str, message: str) -> None:
        url = (f"https://api.telegram.org/bot{self.bot_token}/sendMessage")
        try:
            self._transport(url, {"chat_id": self.chat_id,
                                  "text": f"{title}\n{message}"})
        except Exception as exc:
            print(f"[alert] telegram delivery failed: {exc}")


class NotifierChain:
    """Console always + whatever env-configured channels exist."""

    def __init__(self, notifiers: list | None = None):
        self.notifiers = notifiers if notifiers is not None else build_from_env()

    def send(self, title: str, message: str) -> None:
        for n in self.notifiers:
            n.send(title, message)


def build_from_env() -> list:
    chain = [ConsoleNotifier()]
    webhook = os.environ.get("QF_WEBHOOK_URL", "")
    if webhook:
        chain.append(WebhookNotifier(webhook))
    tg_token = os.environ.get("QF_TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("QF_TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        chain.append(TelegramNotifier(tg_token, tg_chat))
    return chain
