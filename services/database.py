"""
Capa de persistencia mínima en SQLite.

Responsabilidades:
- Inicializar la base de datos y crear tablas si no existen.
- Escribir cada interacción del bot de forma incremental.

No reemplaza el logging JSONL existente — escribe en paralelo.
Si la escritura a DB falla, el bot sigue funcionando normalmente.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Ruta absoluta basada en la ubicación del proyecto, no en el cwd.
# services/database.py -> parent = services/ -> parent = project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "bot.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Crea las tablas si no existen. Seguro de llamar múltiples veces."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id           TEXT    NOT NULL,
                property_id         TEXT    NOT NULL,
                telegram_chat_id    INTEGER NOT NULL,
                status              TEXT    NOT NULL DEFAULT 'open',
                owner               TEXT    NOT NULL DEFAULT 'bot',
                priority            TEXT    NOT NULL DEFAULT 'normal',
                created_at          TEXT    NOT NULL,
                updated_at          TEXT    NOT NULL,
                UNIQUE(client_id, property_id, telegram_chat_id)
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id     INTEGER NOT NULL REFERENCES conversations(id),
                user_message        TEXT    NOT NULL,
                category            TEXT,
                reason              TEXT,
                action              TEXT,
                urgent              INTEGER NOT NULL DEFAULT 0,
                escalate            INTEGER NOT NULL DEFAULT 0,
                reply_text          TEXT,
                ack_text            TEXT,
                created_at          TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                interaction_id      INTEGER NOT NULL REFERENCES interactions(id),
                conversation_id     INTEGER NOT NULL REFERENCES conversations(id),
                reason              TEXT,
                translated_text     TEXT,
                draft_text          TEXT,
                urgent              INTEGER NOT NULL DEFAULT 0,
                resolved_at         TEXT,
                created_at          TEXT    NOT NULL
            );
        """)


def _log_interaction_db(
    *,
    client_id: str,
    property_id: str,
    telegram_chat_id: int,
    user_message: str,
    category: Optional[str],
    reason: Optional[str],
    action: Optional[str],
    urgent: bool,
    escalate: bool,
    reply_text: Optional[str],
    ack_text: Optional[str],
    translated_text: Optional[str],
    draft_text: Optional[str],
    status: str,
    owner: str,
    priority: str,
) -> None:
    """Escritura interna a DB. No atrapa excepciones — el caller decide."""
    now = _now()
    with _conn() as conn:
        # Upsert conversation: crea si es nueva, actualiza estado si ya existe
        conn.execute(
            """
            INSERT INTO conversations
                (client_id, property_id, telegram_chat_id,
                 status, owner, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_id, property_id, telegram_chat_id) DO UPDATE SET
                status     = excluded.status,
                owner      = excluded.owner,
                priority   = excluded.priority,
                updated_at = excluded.updated_at
            """,
            (client_id, property_id, telegram_chat_id,
             status, owner, priority, now, now),
        )

        row = conn.execute(
            "SELECT id FROM conversations "
            "WHERE client_id=? AND property_id=? AND telegram_chat_id=?",
            (client_id, property_id, telegram_chat_id),
        ).fetchone()
        conv_id: int = row["id"]

        # Insertar interacción
        cursor = conn.execute(
            """
            INSERT INTO interactions
                (conversation_id, user_message, category, reason, action,
                 urgent, escalate, reply_text, ack_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (conv_id, user_message, category, reason, action,
             int(urgent), int(escalate), reply_text, ack_text, now),
        )

        # Insertar alerta solo si hubo escalado
        if escalate:
            conn.execute(
                """
                INSERT INTO alerts
                    (interaction_id, conversation_id, reason,
                     translated_text, draft_text, urgent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cursor.lastrowid, conv_id, reason,
                 translated_text, draft_text, int(urgent), now),
            )


def persist_interaction(
    *,
    client_id: str,
    property_id: str,
    telegram_chat_id: int,
    user_message: str,
    result: Dict[str, Any],
) -> None:
    """
    Función pública para bot.py.

    Encapsula la extracción de campos del dict `result` y la escritura a DB.
    Si falla, emite un warning a stderr y no interrumpe el bot.
    """
    try:
        _log_interaction_db(
            client_id=client_id,
            property_id=property_id,
            telegram_chat_id=telegram_chat_id,
            user_message=user_message,
            category=result.get("category"),
            reason=result.get("reason"),
            action=result.get("action"),
            urgent=bool(result.get("urgent", False)),
            escalate=bool(result.get("escalate", False)),
            reply_text=result.get("reply_text"),
            ack_text=result.get("ack_text"),
            translated_text=result.get("translated_text"),
            draft_text=result.get("draft_text"),
            status=result.get("status", "open"),
            owner=result.get("owner", "bot"),
            priority=result.get("priority", "normal"),
        )
    except Exception as e:
        print(f"⚠️ [DB] Error de persistencia: {e}")


# =========================================================
# Funciones de lectura (usadas por api.py)
# =========================================================

def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Convierte un sqlite3.Row a dict estándar."""
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows: list) -> list:
    """Convierte una lista de sqlite3.Row a lista de dicts."""
    return [dict(r) for r in rows]


def get_conversations(*, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """
    Lista conversaciones con conteo de mensajes y última actividad.
    Ordenadas por última actividad (más recientes primero).
    """
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.*,
                COUNT(i.id) AS message_count,
                MAX(i.created_at) AS last_message_at,
                (SELECT user_message FROM interactions
                 WHERE conversation_id = c.id
                 ORDER BY created_at DESC LIMIT 1) AS last_user_message,
                (SELECT COUNT(*) FROM alerts
                 WHERE conversation_id = c.id
                   AND resolved_at IS NULL) AS pending_alerts
            FROM conversations c
            LEFT JOIN interactions i ON i.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM conversations"
        ).fetchone()["cnt"]

    return {
        "conversations": _rows_to_list(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_conversation_interactions(
    conversation_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Lista interacciones de una conversación.
    Devuelve None si la conversación no existe.
    """
    with _conn() as conn:
        conv = conn.execute(
            "SELECT id, telegram_chat_id FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

        if conv is None:
            return None

        rows = conn.execute(
            """
            SELECT * FROM interactions
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (conversation_id, limit, offset),
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(*) AS cnt FROM interactions WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()["cnt"]

        # Fetch alerts for this conversation, grouped by interaction_id
        alert_rows = conn.execute(
            """
            SELECT * FROM alerts
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        ).fetchall()

    # Build lookup: interaction_id → [alert, ...]
    alerts_by_interaction: Dict[int, list] = {}
    for a in alert_rows:
        ad = dict(a)
        ad["resolved"] = ad["resolved_at"] is not None
        alerts_by_interaction.setdefault(ad["interaction_id"], []).append(ad)

    # Attach alerts to each interaction
    messages = []
    for r in rows:
        m = dict(r)
        m["alerts"] = alerts_by_interaction.get(m["id"], [])
        messages.append(m)

    return {
        "conversation_id": conv["id"],
        "telegram_chat_id": conv["telegram_chat_id"],
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_alerts(
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Lista alertas. Filtra opcionalmente por estado:
    - 'pending': resolved_at IS NULL
    - 'resolved': resolved_at IS NOT NULL
    - None: todas
    """
    where = ""
    params: list = []

    if status == "pending":
        where = "WHERE a.resolved_at IS NULL"
    elif status == "resolved":
        where = "WHERE a.resolved_at IS NOT NULL"

    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
                a.*,
                c.telegram_chat_id
            FROM alerts a
            JOIN conversations c ON c.id = a.conversation_id
            {where}
            ORDER BY a.created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        count_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM alerts a {where}",
            params,
        ).fetchone()
        total = count_row["cnt"]

    # Enriquecer con campo 'resolved' booleano
    alert_list = []
    for r in rows:
        d = dict(r)
        d["resolved"] = d["resolved_at"] is not None
        alert_list.append(d)

    return {
        "alerts": alert_list,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# =========================================================
# Funciones de escritura operativa (usadas por api.py)
# =========================================================

VALID_CONV_STATUSES = {"open", "bot_resolved", "host_pending", "urgent"}
VALID_CONV_OWNERS = {"bot", "host"}


def resolve_alert(alert_id: int) -> Optional[Dict[str, Any]]:
    """
    Marca una alerta como resuelta (resolved_at = ahora).
    Devuelve la alerta actualizada, None si no existe, o lanza ValueError si ya resuelta.
    """
    now = _now()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM alerts WHERE id = ?", (alert_id,)
        ).fetchone()

        if row is None:
            return None

        if row["resolved_at"] is not None:
            raise ValueError("Alert already resolved")

        conn.execute(
            "UPDATE alerts SET resolved_at = ? WHERE id = ?",
            (now, alert_id),
        )

        updated = conn.execute(
            """
            SELECT a.*, c.telegram_chat_id
            FROM alerts a
            JOIN conversations c ON c.id = a.conversation_id
            WHERE a.id = ?
            """,
            (alert_id,),
        ).fetchone()

    d = dict(updated)
    d["resolved"] = d["resolved_at"] is not None
    return d


def update_conversation_status(
    conversation_id: int,
    status: str,
) -> Optional[Dict[str, Any]]:
    """
    Actualiza el status de una conversación.
    Devuelve la conversación actualizada o None si no existe.
    """
    if status not in VALID_CONV_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    now = _now()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

        if row is None:
            return None

        conn.execute(
            "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, conversation_id),
        )

        updated = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

    return dict(updated)


def update_conversation_owner(
    conversation_id: int,
    owner: str,
) -> Optional[Dict[str, Any]]:
    """
    Actualiza el owner de una conversación.
    Devuelve la conversación actualizada o None si no existe.
    """
    if owner not in VALID_CONV_OWNERS:
        raise ValueError(f"Invalid owner: {owner}")

    now = _now()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

        if row is None:
            return None

        conn.execute(
            "UPDATE conversations SET owner = ?, updated_at = ? WHERE id = ?",
            (owner, now, conversation_id),
        )

        updated = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()

    return dict(updated)
