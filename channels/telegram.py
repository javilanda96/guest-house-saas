"""
Integración con la API de Telegram.

Este módulo contiene las funciones necesarias para comunicarse con
Telegram Bot API.

Responsabilidades:
- Obtener mensajes enviados al bot.
- Enviar respuestas al usuario.
- Enviar notificaciones al equipo cuando ocurre una alerta.

Separar la integración con Telegram en este módulo permite mantener
la lógica del chatbot independiente del canal de comunicación.
"""
import json
import time
import urllib.request
import urllib.parse
from typing import Optional, List
from channels.base_channel import BaseChannel

class TelegramChannel(BaseChannel):

    def __init__(self, token, http_timeout):
        self.token = token
        self.http_timeout = http_timeout

    def get_updates(self, poll_timeout, offset=None):
        return get_updates(
            self.token,
            self.http_timeout,
            poll_timeout,
            offset=offset,
        )

    def send_message(self, chat_id: int, text: str):
        send_message(
            self.token,
            self.http_timeout,
            chat_id,
            text,
        )

def tg_api(bot_token: str, http_timeout_seconds: int, method: str, params: Optional[dict] = None) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
    data = None
    headers = {}

    if params is not None:
        data = urllib.parse.urlencode(params).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=http_timeout_seconds) as resp:
        raw = resp.read().decode("utf-8")

    payload = json.loads(raw)
    if not payload.get("ok", False):
        raise RuntimeError(f"Telegram API error in {method}: {payload}")
    return payload


def send_message(bot_token: str, http_timeout_seconds: int, chat_id: int, text: str, _retries: int = 2):
    last_err = None
    for attempt in range(_retries + 1):
        try:
            tg_api(bot_token, http_timeout_seconds, "sendMessage", {
                "chat_id": str(chat_id),
                "text": text,
                "disable_web_page_preview": True
            })
            return
        except Exception as e:
            last_err = e
            if attempt < _retries:
                time.sleep(1)
    raise last_err


def get_updates(bot_token: str, http_timeout_seconds: int, poll_timeout_seconds: int, offset: Optional[int] = None) -> List[dict]:
    params = {"timeout": str(poll_timeout_seconds)}
    if offset is not None:
        params["offset"] = str(offset)
    res = tg_api(bot_token, http_timeout_seconds, "getUpdates", params)
    return res.get("result", [])