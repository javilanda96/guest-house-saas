"""
CRUD de propiedades y knowledge base.

Extraido de services/database.py (Milestone 2A/2B).
Depende de los helpers internos de services.database para conexion y utilidades.

Responsabilidades:
- Lectura de propiedades y sus knowledge entries.
- Escritura y actualizacion de perfiles de propiedad.
- Actualizacion de contenido de knowledge base.
- Importacion de propiedades desde el sistema de archivos.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.database import _conn, _now, _rows_to_list


# =========================================================
# Constantes de validacion
# =========================================================

VALID_KNOWLEDGE_TOPICS = frozenset([
    "faq", "checkin", "house_rules",
    "emergencies", "host_notes", "local_tips",
])


# =========================================================
# Lectura — Propiedades (Milestone 2A)
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


# =========================================================
# Escritura — Propiedades (Milestone 2B: editor)
# =========================================================

def update_property_profile(
    property_db_id: int,
    *,
    property_name: str,
    contact_name: Optional[str],
    contact_phone: Optional[str],
    default_language: str,
    city: Optional[str],
    country: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Actualiza los campos de perfil de una propiedad existente.
    Devuelve la fila actualizada o None si no existe.
    """
    now = _now()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM properties WHERE id = ?",
            (property_db_id,),
        ).fetchone()
        if existing is None:
            return None

        conn.execute(
            """UPDATE properties
               SET property_name = ?, contact_name = ?, contact_phone = ?,
                   default_language = ?, city = ?, country = ?,
                   updated_at = ?
               WHERE id = ?""",
            (property_name, contact_name, contact_phone,
             default_language, city, country, now, property_db_id),
        )

        updated = conn.execute(
            "SELECT * FROM properties WHERE id = ?",
            (property_db_id,),
        ).fetchone()

    return dict(updated)


def update_knowledge_content(
    property_db_id: int,
    topic: str,
    content: str,
) -> Optional[Dict[str, Any]]:
    """
    Actualiza (o crea) el contenido de un topic en el knowledge base.
    El topic debe estar en VALID_KNOWLEDGE_TOPICS.
    Devuelve la fila de knowledge_entry, o None si la propiedad no existe.
    """
    now = _now()
    with _conn() as conn:
        prop = conn.execute(
            "SELECT id FROM properties WHERE id = ?",
            (property_db_id,),
        ).fetchone()
        if prop is None:
            return None

        existing = conn.execute(
            "SELECT id FROM knowledge_entries WHERE property_db_id = ? AND topic = ?",
            (property_db_id, topic),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE knowledge_entries SET content = ?, updated_at = ? WHERE id = ?",
                (content, now, existing["id"]),
            )
            row = conn.execute(
                "SELECT * FROM knowledge_entries WHERE id = ?",
                (existing["id"],),
            ).fetchone()
        else:
            conn.execute(
                """INSERT INTO knowledge_entries
                   (property_db_id, topic, content, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (property_db_id, topic, content, now),
            )
            row = conn.execute(
                "SELECT * FROM knowledge_entries WHERE property_db_id = ? AND topic = ?",
                (property_db_id, topic),
            ).fetchone()

    return dict(row)
