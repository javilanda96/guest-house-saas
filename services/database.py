"""
Capa de persistencia dual SQLite / PostgreSQL.

Soporte dual-backend:
  Existe para evitar la friccion de instalar PostgreSQL localmente
  durante el desarrollo de un MVP por un solo desarrollador.
  Cuando el esquema supere ~5 tablas o el equipo crezca, migrar
  a PostgreSQL-only eliminando _adapt_sql, _ConnWrapper y _TABLES.
  Ver docs/ROADMAP.md, Milestone 3.

Comportamiento:
- Si DATABASE_URL esta definida -> conecta a PostgreSQL.
- Si no -> usa SQLite local en data/bot.db.

Responsabilidades:
- Inicializar la base de datos y crear tablas si no existen.
- Escribir cada interaccion del bot de forma incremental.
- Exponer funciones de lectura/escritura para api.py.

No reemplaza el logging JSONL existente — escribe en paralelo.
Si la escritura a DB falla, el bot sigue funcionando normalmente.
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# =========================================================
# Backend detection
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

# Render usa "postgres://" pero psycopg2 necesita "postgresql://"
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_USE_PG = DATABASE_URL is not None

if _USE_PG:
    import psycopg2
    import psycopg2.extras

# Ruta absoluta para SQLite (solo usada si _USE_PG es False)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "bot.db"


# =========================================================
# Connection helpers
# =========================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raw_conn():
    """Devuelve una conexion cruda (sqlite3 o psycopg2)."""
    if _USE_PG:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


# Regex para traduccion de placeholders.
# Detecta strings entre comillas simples ('...') o el caracter ?.
# Si el match es un string entrecomillado, se deja intacto.
# Si es ?, se reemplaza por %s.
#
# Limitacion conocida: no maneja comillas escapadas dentro de strings
# (ej: 'it''s'). Esto es aceptable porque ninguna query actual o
# previsible en este proyecto usa comillas escapadas en literales SQL.
_PH_RE = re.compile(r"'[^']*'|\?")


def _adapt_sql(sql: str, param_count: int = 0) -> str:
    """
    Traduce placeholders ? -> %s para PostgreSQL, protegiendo strings literales.

    Este es un safeguard pragmatico, NO un parser SQL completo.
    Solo es necesario mientras se mantenga soporte dual SQLite/PostgreSQL.
    """
    if not _USE_PG:
        return sql
    result = _PH_RE.sub(
        lambda m: '%s' if m.group(0) == '?' else m.group(0),
        sql,
    )
    if param_count > 0:
        actual = result.count('%s')
        assert actual == param_count, (
            f"Placeholder mismatch: {actual} placeholders in SQL, "
            f"{param_count} params provided"
        )
    return result


@contextmanager
def _conn():
    """
    Context manager que devuelve una conexion con auto-commit al salir.
    Compatible con ambos backends.
    """
    raw = _raw_conn()
    try:
        if _USE_PG:
            cur = raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = raw.cursor()
        yield _ConnWrapper(raw, cur)
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


class _ConnWrapper:
    """
    Wrapper minimo que normaliza la interfaz entre SQLite y PostgreSQL.
    Traduce ? -> %s y ofrece execute/fetchone/fetchall uniformes.
    """

    def __init__(self, raw_conn, cursor):
        self._conn = raw_conn
        self._cursor = cursor

    def execute(self, sql: str, params=None):
        """Ejecuta SQL adaptando placeholders. Devuelve self para encadenamiento."""
        pc = len(params) if params else 0
        adapted = _adapt_sql(sql, param_count=pc)
        if params:
            self._cursor.execute(adapted, params)
        else:
            self._cursor.execute(adapted)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        if _USE_PG:
            return dict(row)
        return row

    def fetchall(self):
        rows = self._cursor.fetchall()
        if _USE_PG:
            return [dict(r) for r in rows]
        return rows

    @property
    def lastrowid(self):
        if _USE_PG:
            return self._cursor.fetchone()["id"]
        return self._cursor.lastrowid

    @property
    def raw(self):
        return self._conn


# =========================================================
# Schema definition (single source of truth)
# =========================================================
#
# Las tablas se definen UNA SOLA VEZ en _TABLES.
# _render_schema() genera el DDL correcto para cada backend.
#
# Tokens especiales en las columnas:
#   "PK"            -> INTEGER PRIMARY KEY AUTOINCREMENT (SQLite)
#                      SERIAL PRIMARY KEY (PostgreSQL)
#   "BIGINT_OR_INT" -> INTEGER (SQLite), BIGINT (PostgreSQL)
#   cualquier otro  -> se usa tal cual en ambos backends
#
# Para anadir una columna: agregar una tupla a la lista "columns".
# Para anadir una tabla: agregar un dict a _TABLES.

_TABLES: List[Dict[str, Any]] = [
    {
        "name": "conversations",
        "columns": [
            ("id",                 "PK"),
            ("client_id",          "TEXT NOT NULL"),
            ("property_id",        "TEXT NOT NULL"),
            ("telegram_chat_id",   "BIGINT_OR_INT NOT NULL"),
            ("status",             "TEXT NOT NULL DEFAULT 'open'"),
            ("owner",              "TEXT NOT NULL DEFAULT 'bot'"),
            ("priority",           "TEXT NOT NULL DEFAULT 'normal'"),
            ("created_at",         "TEXT NOT NULL"),
            ("updated_at",         "TEXT NOT NULL"),
        ],
        "constraints": [
            "UNIQUE(client_id, property_id, telegram_chat_id)",
        ],
    },
    {
        "name": "interactions",
        "columns": [
            ("id",                 "PK"),
            ("conversation_id",    "INTEGER NOT NULL REFERENCES conversations(id)"),
            ("user_message",       "TEXT NOT NULL"),
            ("category",           "TEXT"),
            ("reason",             "TEXT"),
            ("action",             "TEXT"),
            ("urgent",             "INTEGER NOT NULL DEFAULT 0"),
            ("escalate",           "INTEGER NOT NULL DEFAULT 0"),
            ("reply_text",         "TEXT"),
            ("ack_text",           "TEXT"),
            ("created_at",         "TEXT NOT NULL"),
        ],
        "constraints": [],
    },
    {
        "name": "alerts",
        "columns": [
            ("id",                 "PK"),
            ("interaction_id",     "INTEGER NOT NULL REFERENCES interactions(id)"),
            ("conversation_id",    "INTEGER NOT NULL REFERENCES conversations(id)"),
            ("reason",             "TEXT"),
            ("translated_text",    "TEXT"),
            ("draft_text",         "TEXT"),
            ("urgent",             "INTEGER NOT NULL DEFAULT 0"),
            ("resolved_at",        "TEXT"),
            ("created_at",         "TEXT NOT NULL"),
        ],
        "constraints": [],
    },
    # ---------------------------------------------------
    # Milestone 2A: Property configuration in database.
    # Stores property profile + knowledge base topics.
    # Filesystem loading remains as fallback for bot.py.
    # ---------------------------------------------------
    {
        "name": "properties",
        "columns": [
            ("id",                 "PK"),
            ("client_id",          "TEXT NOT NULL"),
            ("property_id",        "TEXT NOT NULL"),
            ("property_name",      "TEXT NOT NULL"),
            ("contact_name",       "TEXT"),
            ("contact_phone",      "TEXT"),
            ("default_language",   "TEXT NOT NULL DEFAULT 'en'"),
            ("city",               "TEXT"),
            ("country",            "TEXT"),
            ("created_at",         "TEXT NOT NULL"),
            ("updated_at",         "TEXT NOT NULL"),
        ],
        "constraints": [
            "UNIQUE(client_id, property_id)",
        ],
    },
    {
        "name": "knowledge_entries",
        "columns": [
            ("id",                 "PK"),
            ("property_db_id",     "INTEGER NOT NULL REFERENCES properties(id)"),
            ("topic",              "TEXT NOT NULL"),
            ("content",            "TEXT NOT NULL DEFAULT ''"),
            ("updated_at",         "TEXT NOT NULL"),
        ],
        "constraints": [
            "UNIQUE(property_db_id, topic)",
        ],
    },
]


def _render_schema(dialect: str) -> str:
    """
    Genera DDL CREATE TABLE a partir de _TABLES.
    dialect: "sqlite" o "pg"
    """
    stmts = []
    for table in _TABLES:
        col_defs = []
        for col_name, col_spec in table["columns"]:
            if col_spec == "PK":
                if dialect == "sqlite":
                    col_defs.append(f"    {col_name:<24}INTEGER PRIMARY KEY AUTOINCREMENT")
                else:
                    col_defs.append(f"    {col_name:<24}SERIAL PRIMARY KEY")
            elif col_spec.startswith("BIGINT_OR_INT"):
                suffix = col_spec.replace("BIGINT_OR_INT", "").strip()
                if dialect == "sqlite":
                    col_defs.append(f"    {col_name:<24}INTEGER {suffix}".rstrip())
                else:
                    col_defs.append(f"    {col_name:<24}BIGINT {suffix}".rstrip())
            else:
                col_defs.append(f"    {col_name:<24}{col_spec}")

        for constraint in table.get("constraints", []):
            col_defs.append(f"    {constraint}")

        body = ",\n".join(col_defs)
        stmts.append(f"CREATE TABLE IF NOT EXISTS {table['name']} (\n{body}\n);")

    return "\n\n".join(stmts)


_SCHEMA_SQLITE = _render_schema("sqlite")
_SCHEMA_PG = _render_schema("pg")


def init_db() -> None:
    """Crea las tablas si no existen. Seguro de llamar multiples veces."""
    if _USE_PG:
        with _conn() as conn:
            conn.execute(_SCHEMA_PG)
        print("[DB] Inicializado: PostgreSQL")
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # executescript requiere gestion propia de transacciones,
        # por lo que usamos la conexion cruda directamente.
        raw = sqlite3.connect(str(DB_PATH))
        try:
            raw.executescript(_SCHEMA_SQLITE)
        finally:
            raw.close()
        print(f"[DB] Inicializado: SQLite ({DB_PATH})")


# =========================================================
# Escritura (usada por bot.py via persist_interaction)
# =========================================================

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

        # Insertar interaccion
        if _USE_PG:
            conn.execute(
                """
                INSERT INTO interactions
                    (conversation_id, user_message, category, reason, action,
                     urgent, escalate, reply_text, ack_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (conv_id, user_message, category, reason, action,
                 int(urgent), int(escalate), reply_text, ack_text, now),
            )
            interaction_id = conn.lastrowid
        else:
            conn.execute(
                """
                INSERT INTO interactions
                    (conversation_id, user_message, category, reason, action,
                     urgent, escalate, reply_text, ack_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (conv_id, user_message, category, reason, action,
                 int(urgent), int(escalate), reply_text, ack_text, now),
            )
            interaction_id = conn.lastrowid

        # Insertar alerta solo si hubo escalado
        if escalate:
            conn.execute(
                """
                INSERT INTO alerts
                    (interaction_id, conversation_id, reason,
                     translated_text, draft_text, urgent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (interaction_id, conv_id, reason,
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
    Funcion publica para bot.py.

    Encapsula la extraccion de campos del dict `result` y la escritura a DB.
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

def _row_to_dict(row) -> Optional[Dict[str, Any]]:
    """Convierte un Row a dict estandar."""
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows: list) -> list:
    """Convierte una lista de Rows a lista de dicts."""
    return [dict(r) for r in rows]


def get_conversations(*, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """
    Lista conversaciones con conteo de mensajes y ultima actividad.
    Ordenadas por ultima actividad (mas recientes primero).
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
    Lista interacciones de una conversacion.
    Devuelve None si la conversacion no existe.
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

    # Build lookup: interaction_id -> [alert, ...]
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
                c.telegram_chat_id,
                c.property_id
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
    Actualiza el status de una conversacion.
    Devuelve la conversacion actualizada o None si no existe.
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
    Actualiza el owner de una conversacion.
    Devuelve la conversacion actualizada o None si no existe.
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


# =========================================================
# Funciones de lectura — Propiedades (Milestone 2A)
# =========================================================

def get_properties(*, client_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Lista propiedades. Filtra opcionalmente por client_id.
    """
    where = ""
    params: list = []
    if client_id:
        where = "WHERE client_id = ?"
        params = [client_id]

    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM properties {where} ORDER BY property_name ASC",
            params,
        ).fetchall()

    return {
        "properties": _rows_to_list(rows),
        "total": len(rows),
    }


def get_property_detail(property_db_id: int) -> Optional[Dict[str, Any]]:
    """
    Devuelve perfil de propiedad + todas sus knowledge entries.
    Devuelve None si no existe.
    """
    with _conn() as conn:
        prop = conn.execute(
            "SELECT * FROM properties WHERE id = ?",
            (property_db_id,),
        ).fetchone()

        if prop is None:
            return None

        ke_rows = conn.execute(
            "SELECT * FROM knowledge_entries WHERE property_db_id = ? ORDER BY topic ASC",
            (property_db_id,),
        ).fetchall()

    result = dict(prop)
    result["knowledge"] = _rows_to_list(ke_rows)
    return result


def upsert_property_from_dict(
    *,
    client_id: str,
    property_id: str,
    config: Dict[str, Any],
    knowledge: Dict[str, str],
) -> int:
    """
    Inserta o actualiza una propiedad y sus knowledge entries a partir de dicts.
    Usado por el seed y por la importacion desde filesystem.
    Devuelve el id de la propiedad.
    """
    now = _now()
    with _conn() as conn:
        # Upsert property profile
        conn.execute(
            """
            INSERT INTO properties
                (client_id, property_id, property_name,
                 contact_name, contact_phone, default_language,
                 city, country, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_id, property_id) DO UPDATE SET
                property_name    = excluded.property_name,
                contact_name     = excluded.contact_name,
                contact_phone    = excluded.contact_phone,
                default_language = excluded.default_language,
                city             = excluded.city,
                country          = excluded.country,
                updated_at       = excluded.updated_at
            """,
            (client_id, property_id,
             config.get("property_name", property_id),
             config.get("contact_name"),
             config.get("contact_phone"),
             config.get("default_language", "en"),
             config.get("city"),
             config.get("country"),
             now, now),
        )

        row = conn.execute(
            "SELECT id FROM properties WHERE client_id = ? AND property_id = ?",
            (client_id, property_id),
        ).fetchone()
        prop_db_id: int = row["id"]

        # Upsert knowledge entries
        for topic, content in knowledge.items():
            existing = conn.execute(
                "SELECT id FROM knowledge_entries WHERE property_db_id = ? AND topic = ?",
                (prop_db_id, topic),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE knowledge_entries SET content = ?, updated_at = ? WHERE id = ?",
                    (content, now, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO knowledge_entries
                       (property_db_id, topic, content, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (prop_db_id, topic, content, now),
                )

    return prop_db_id


def import_property_from_filesystem(client_id: str, property_id: str) -> Optional[int]:
    """
    Importa una propiedad desde el filesystem al DB.
    Usa property_manager para cargar los datos, luego los persiste.
    Devuelve el property db id, o None si no hay datos en filesystem.
    """
    from services.property_manager import load_property, load_knowledge_base

    try:
        config = load_property(client_id, property_id)
        knowledge = load_knowledge_base(client_id, property_id)
    except FileNotFoundError:
        return None

    return upsert_property_from_dict(
        client_id=client_id,
        property_id=property_id,
        config=config,
        knowledge=knowledge,
    )
