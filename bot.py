"""
Orquestador principal del chatbot.

Este módulo conecta todos los componentes del sistema y ejecuta el loop
principal del bot de Telegram.

Responsabilidades principales:
- Recibir mensajes desde Telegram.
- Cargar y guardar la memoria de conversación de cada chat.
- Llamar a `process_message()` para procesar cada mensaje del huésped.
- Enviar respuestas automáticas al usuario.
- Enviar alertas al equipo cuando un mensaje es sensible o urgente.

Este archivo actúa como controlador principal del flujo del chatbot.
"""


import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from channels.telegram import TelegramChannel
from config import (
    ALERT_CHAT_IDS,
    HTTP_TIMEOUT_SECONDS,
    MAX_HISTORY_MESSAGES,
    MAX_PROCESSED_KEYS,
    OPENAI_API_KEY,
    POLL_TIMEOUT_SECONDS,
    POST_LOOP_SLEEP,
    SEND_ACK_ON_SENSITIVE,
    SYSTEM_CLASSIFIER,
    SYSTEM_REPLY,
    TELEGRAM_BOT_TOKEN,
    validate_config,
    CLIENT_ID,
    PROPERTY_ID,
)
from services.processor import process_message
from services.logger import log_interaction
from services.database import init_db, persist_interaction


validate_config()
init_db()
client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)
channel = TelegramChannel(
    token=TELEGRAM_BOT_TOKEN,
    http_timeout=HTTP_TIMEOUT_SECONDS,
)
START_MESSAGE = "👋 ¡Hola! Escríbeme tu duda sobre la estancia y te respondo."
RESET_MESSAGE = "✅ Conversación reiniciada."

# =========================
# Memory per chat (in-memory)
# =========================
chat_histories: Dict[int, List[dict]] = {}

def build_initial_history() -> List[dict]:
    return [{"role": "system", "content": SYSTEM_REPLY}]
def get_history(chat_id: int) -> List[dict]:
    if chat_id not in chat_histories:
        chat_histories[chat_id] = build_initial_history()
    return chat_histories[chat_id]


# =========================
# Rate limiting por chat
# =========================
RATE_LIMIT_MAX = 10       # mensajes máximos por ventana
RATE_LIMIT_WINDOW = 60    # segundos
RATE_LIMIT_MSG = "Por favor, espera un momento antes de enviar más mensajes."

_rate_timestamps: Dict[int, List[float]] = defaultdict(list)


def is_rate_limited(chat_id: int) -> bool:
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    timestamps = _rate_timestamps[chat_id]
    _rate_timestamps[chat_id] = [t for t in timestamps if t > cutoff]
    if len(_rate_timestamps[chat_id]) >= RATE_LIMIT_MAX:
        return True
    _rate_timestamps[chat_id].append(now)
    return False


# =========================
# Idempotencia (evita dobles respuestas)
# =========================
processed_keys: List[Tuple[int, int]] = []
processed_set: set[Tuple[int, int]] = set()


def seen_before(chat_id: int, message_id: Optional[int]) -> bool:
    if message_id is None:
        return False

    key = (chat_id, message_id)
    if key in processed_set:
        return True

    processed_set.add(key)
    processed_keys.append(key)

    overflow = len(processed_keys) - MAX_PROCESSED_KEYS
    if overflow > 0:
        for _ in range(overflow):
            old = processed_keys.pop(0)
            processed_set.discard(old)

    return False


def send_bot_message(chat_id: int, text: str) -> None:
    try:
        channel.send_message(chat_id, text)
    except Exception as e:
        log_interaction({"chat_id": chat_id, "error": f"send_message_failed: {e}", "reply_text": text[:200]})


def build_alert_text(
    chat_id: int,
    reason: str,
    original_text: str,
    translated_text: str,
    draft_text: str,
    urgent: bool,
) -> str:
    header = "🚨🚨 ALERTA URGENTE (SENSIBLE) — REVISAR YA" if urgent else "🚨 ALERTA (SENSIBLE) — REVISAR"

    safe_reason = reason or "(sin motivo)"
    safe_original = original_text or "(sin texto)"
    safe_translated = translated_text or "(sin traducción disponible)"
    safe_draft = draft_text or "(sin borrador disponible)"

    return (
        f"{header}\n\n"
        f"Chat ID: {chat_id}\n"
        f"Motivo: {safe_reason}\n\n"
        f"👤 Mensaje original:\n{safe_original}\n\n"
        f"🌍 Traducción al español:\n{safe_translated}\n\n"
        f"🤖 Borrador sugerido:\n{safe_draft}\n"
    )


def handle_command(chat_id: int, cmd: str) -> bool:
    if cmd == "/reset":
        chat_histories[chat_id] = build_initial_history()
        send_bot_message(chat_id, RESET_MESSAGE)
        return True

    if cmd == "/start":
        send_bot_message(chat_id, START_MESSAGE)
        return True

    return False


def main() -> None:
    print("Telegram LIVE bot iniciado.")
    print("SAFE -> responde. SENSITIVE -> alerta + acuse. UNKNOWN -> pide aclaración.")
    print("Ctrl+C para parar.\n")

    last_update_id: Optional[int] = None
    _error_delay = 2

    while True:
        try:
            offset = (last_update_id + 1) if isinstance(last_update_id, int) else None
            updates = channel.get_updates(
                poll_timeout=POLL_TIMEOUT_SECONDS,
                offset=offset,
            )

            for update in updates:
                last_update_id = update.get("update_id", last_update_id)

                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue

                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = (msg.get("text") or "").strip()
                message_id = msg.get("message_id")

                if not chat_id or not text:
                    continue
                if seen_before(chat_id, message_id):
                    continue

                if is_rate_limited(chat_id):
                    send_bot_message(chat_id, RATE_LIMIT_MSG)
                    continue

                cmd = text.lower().strip()
                if handle_command(chat_id, cmd):
                    continue

                result = process_message(
                    client=client,
                    chat_id=chat_id,
                    system_classifier=SYSTEM_CLASSIFIER,
                    history=get_history(chat_id),
                    text=text,
                    max_history_messages=MAX_HISTORY_MESSAGES,
                    send_ack_on_sensitive=SEND_ACK_ON_SENSITIVE,
                )
                log_interaction({
                    "chat_id": chat_id,
                    "client_id": CLIENT_ID,
                    "property_id": PROPERTY_ID,
                    "user_message": text,
                    "category": result["category"],
                    "reason": result["reason"],
                    "action": result["action"],
                    "escalate": result["escalate"],
                    "urgent": result["urgent"],
                    "reply_text": result.get("reply_text"),
                    "ack_text": result.get("ack_text"),
                    "translated_text": result.get("translated_text"),
                    "draft_text": result.get("draft_text"),
                })
                persist_interaction(
                    client_id=CLIENT_ID,
                    property_id=PROPERTY_ID,
                    telegram_chat_id=chat_id,
                    user_message=text,
                    result=result,
                )

                category = result["category"]
                reason = result["reason"]
                urgent = result["urgent"]
                chat_histories[chat_id] = result["history"]

                action = result["action"]

                if action == "reply_guest":
                    send_bot_message(chat_id, result["reply_text"])
                    continue

                if action in {"reply_and_alert", "alert_staff_urgent"}:
                    if ALERT_CHAT_IDS:
                        alert_text = build_alert_text(
                            chat_id=chat_id,
                            reason=reason,
                            original_text=text,
                            translated_text=result["translated_text"],
                            draft_text=result["draft_text"],
                            urgent=urgent,
                        )
                        for cid in ALERT_CHAT_IDS:
                            send_bot_message(cid, alert_text)

                    outgoing_text = result.get("reply_text") or result.get("ack_text")
                    if outgoing_text:
                        send_bot_message(chat_id, outgoing_text)
                    continue

                send_bot_message(chat_id, result["reply_text"])

            time.sleep(POST_LOOP_SLEEP)
            _error_delay = 2  # reset tras iteración exitosa

        except KeyboardInterrupt:
            print("\nBot detenido.")
            break
        except Exception as e:
            print(f"⚠️ Error en loop: {e}")
            time.sleep(_error_delay)
            _error_delay = min(_error_delay * 2, 60)


if __name__ == "__main__":
    main()