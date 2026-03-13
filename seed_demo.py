"""
Seed de datos demo para la API del panel.

Uso directo:
    python seed_demo.py          # Puebla la DB si esta vacia

Uso programatico (desde api.py):
    from seed_demo import seed_if_empty
    seed_if_empty()              # No-op si ya hay datos

Seguro de ejecutar multiples veces: solo inserta si conversations esta vacia.

Control por entorno:
    SEED_DEMO=true  -> inserta datos demo si la DB esta vacia.
    (sin variable)  -> solo inicializa tablas, nunca inserta demo data.
    Ejecucion directa (python seed_demo.py) siempre inserta (util en desarrollo).
"""

import os

from services.database import init_db, _conn, _now, _USE_PG

_SEED_ENABLED = os.environ.get("SEED_DEMO", "").lower() in ("true", "1", "yes")


def _is_empty() -> bool:
    """True si no hay conversaciones en la DB."""
    with _conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM conversations").fetchone()
        return row["cnt"] == 0


def _insert_returning_id(conn, sql: str, params: tuple) -> int:
    """
    Inserta un registro y devuelve su id.
    En PostgreSQL usa RETURNING id; en SQLite usa lastrowid.
    """
    if _USE_PG:
        conn.execute(sql + " RETURNING id", params)
        return conn.lastrowid
    else:
        conn.execute(sql, params)
        return conn.lastrowid


def _seed() -> None:
    """Inserta datos demo representativos."""
    now = _now()

    with _conn() as conn:
        # --- Conversacion 1: resuelta por bot (wifi question) ---
        conv1 = _insert_returning_id(conn,
            """INSERT INTO conversations
               (client_id, property_id, telegram_chat_id,
                status, owner, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("demo_client", "apt_centro_01", 100001,
             "bot_resolved", "bot", "normal", now, now),
        )

        conn.execute(
            """INSERT INTO interactions
               (conversation_id, user_message, category, reason, action,
                urgent, escalate, reply_text, ack_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv1, "What is the wifi password?",
             "info_request", "Guest asks for wifi credentials",
             "reply_guest", 0, 0,
             "The wifi network is AptCentro-Guest and the password is Welcome2024!",
             None, now),
        )

        conn.execute(
            """INSERT INTO interactions
               (conversation_id, user_message, category, reason, action,
                urgent, escalate, reply_text, ack_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv1, "Thanks! And what time is checkout?",
             "info_request", "Guest asks about checkout time",
             "reply_guest", 0, 0,
             "Checkout is at 11:00 AM. Please leave the keys on the kitchen table.",
             None, now),
        )

        # --- Conversacion 2: escalada al host (maintenance) ---
        conv2 = _insert_returning_id(conn,
            """INSERT INTO conversations
               (client_id, property_id, telegram_chat_id,
                status, owner, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("demo_client", "apt_centro_01", 100002,
             "host_pending", "host", "high", now, now),
        )

        inter2 = _insert_returning_id(conn,
            """INSERT INTO interactions
               (conversation_id, user_message, category, reason, action,
                urgent, escalate, reply_text, ack_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv2,
             "El aire acondicionado no funciona y hace mucho calor",
             "maintenance", "AC not working, guest is uncomfortable",
             "escalate_host", 1, 1, None,
             "Entendido, he avisado a Ana y te responderemos lo antes posible.",
             now),
        )

        # Alerta asociada (pendiente)
        conn.execute(
            """INSERT INTO alerts
               (interaction_id, conversation_id, reason,
                translated_text, draft_text, urgent, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (inter2, conv2,
             "AC not working, guest is uncomfortable",
             "The air conditioning is not working and it is very hot",
             "Hi [guest], I'm sorry about the AC. I've contacted our maintenance team and they will come today between 14-16h. In the meantime, I've asked reception to bring you a portable fan.",
             1, now),
        )

        # --- Conversacion 3: urgente (locked out) ---
        conv3 = _insert_returning_id(conn,
            """INSERT INTO conversations
               (client_id, property_id, telegram_chat_id,
                status, owner, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("demo_client", "apt_playa_02", 100003,
             "urgent", "host", "high", now, now),
        )

        inter3 = _insert_returning_id(conn,
            """INSERT INTO interactions
               (conversation_id, user_message, category, reason, action,
                urgent, escalate, reply_text, ack_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv3,
             "I'm locked out of the apartment! The door code doesn't work!",
             "emergency", "Guest locked out, door code failing",
             "escalate_host", 1, 1, None,
             "I understand the urgency. I've notified the host and someone will contact you immediately.",
             now),
        )

        # Alerta urgente (pendiente)
        conn.execute(
            """INSERT INTO alerts
               (interaction_id, conversation_id, reason,
                translated_text, draft_text, urgent, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (inter3, conv3,
             "Guest locked out, door code failing",
             "I'm locked out of the apartment! The door code doesn't work!",
             "Hi [guest], I'm very sorry about this. The backup code is 4582#. If that doesn't work, our local manager Carlos is on his way (ETA 10 min). His number is +34 600 123 456.",
             1, now),
        )

        # --- Conversacion 4: info normal en espanol ---
        conv4 = _insert_returning_id(conn,
            """INSERT INTO conversations
               (client_id, property_id, telegram_chat_id,
                status, owner, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("demo_client", "apt_playa_02", 100004,
             "bot_resolved", "bot", "normal", now, now),
        )

        conn.execute(
            """INSERT INTO interactions
               (conversation_id, user_message, category, reason, action,
                urgent, escalate, reply_text, ack_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv4,
             "Hay algun restaurante bueno cerca?",
             "recommendation", "Guest asks for restaurant recommendations",
             "reply_guest", 0, 0,
             "Claro! Te recomiendo La Tasca del Puerto (5 min andando), tienen marisco fresco excelente. Tambien Casa Maria para tapas tradicionales.",
             None, now),
        )

        # --- Alerta resuelta (ejemplo historico) ---
        conv5 = _insert_returning_id(conn,
            """INSERT INTO conversations
               (client_id, property_id, telegram_chat_id,
                status, owner, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("demo_client", "apt_centro_01", 100005,
             "bot_resolved", "bot", "normal", now, now),
        )

        inter5 = _insert_returning_id(conn,
            """INSERT INTO interactions
               (conversation_id, user_message, category, reason, action,
                urgent, escalate, reply_text, ack_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (conv5,
             "The hot water is not working in the shower",
             "maintenance", "Hot water issue reported",
             "escalate_host", 0, 1, None,
             "I've let the host know about the hot water issue. They will get back to you shortly.",
             now),
        )

        conn.execute(
            """INSERT INTO alerts
               (interaction_id, conversation_id, reason,
                translated_text, draft_text, urgent, resolved_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (inter5, conv5,
             "Hot water issue reported",
             "The hot water is not working in the shower",
             "Hi [guest], thank you for letting us know. The boiler needs about 20 minutes to heat up after being idle. Could you try again? If it still doesn't work, I'll send maintenance.",
             0, now, now),
        )

    print(f"[SEED] Datos demo insertados: 5 conversaciones, 6 interacciones, 3 alertas.")


def seed_if_empty() -> None:
    """
    Inicializa la DB y opcionalmente inserta datos demo.

    Solo inserta datos demo si:
    - SEED_DEMO=true esta definido, Y
    - la DB esta vacia (0 conversaciones).

    Sin SEED_DEMO, solo crea las tablas.
    """
    init_db()
    if not _SEED_ENABLED:
        print("[SEED] Seeding deshabilitado (SEED_DEMO no definido).")
        return
    if _is_empty():
        _seed()
    else:
        print("[SEED] DB ya contiene datos, saltando seed.")


if __name__ == "__main__":
    # Ejecucion directa siempre inserta (desarrollo local).
    init_db()
    if _is_empty():
        _seed()
    else:
        print("[SEED] DB ya contiene datos, saltando seed.")
