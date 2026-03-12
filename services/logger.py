"""
Logger del chatbot.

Registra:
- alertas sensibles
- clasificaciones
- respuestas
- interacciones estructuradas

Objetivo:
que el logging nunca rompa el flujo principal del bot.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

LOGS_DIR = Path("logs")
ALERTS_LOG = LOGS_DIR / "alerts.log"
INTERACTIONS_LOG = LOGS_DIR / "interactions.jsonl"
CLASSIFIER_LOG = LOGS_DIR / "classifier.log"
REPLY_LOG = LOGS_DIR / "reply.log"


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _sanitize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _append_line(path: Path, line: str) -> None:
    _ensure_logs_dir()
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def log_alert(chat_id: Any, message: Any) -> None:
    try:
        timestamp = _now_iso()
        clean_message = _sanitize_text(message)
        line = f"{timestamp} | chat_id={chat_id} | ALERT | {clean_message}"
        _append_line(ALERTS_LOG, line)
    except Exception as e:
        print(f"⚠️ Logging error in log_alert: {e}")


def log_interaction(data: Dict[str, Any]) -> None:
    try:
        _ensure_logs_dir()
        payload = dict(data)
        payload["timestamp"] = _now_iso()

        with INTERACTIONS_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ Logging error in log_interaction: {e}")


def log_classification(message: Any, category: Any, action: Any) -> None:
    try:
        timestamp = _now_iso()
        clean_message = _sanitize_text(message)
        line = (
            f"[{timestamp}] [CLASSIFIER] "
            f"message='{clean_message}' | category={category} | action={action}"
        )
        print(line)
        _append_line(CLASSIFIER_LOG, line)
    except Exception as e:
        print(f"⚠️ Logging error in log_classification: {e}")


def log_reply(reply_text: Any) -> None:
    try:
        timestamp = _now_iso()
        clean_reply = _sanitize_text(reply_text)
        line = f"[{timestamp}] [REPLY] {clean_reply}"
        print(line)
        _append_line(REPLY_LOG, line)
    except Exception as e:
        print(f"⚠️ Logging error in log_reply: {e}")