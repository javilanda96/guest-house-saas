"""
Safety tests for the dual SQLite/PostgreSQL persistence layer.

These tests verify:
1. Placeholder translation correctness (including edge cases)
2. Schema synchronization between backends
3. Write/read roundtrip on the active backend

Run with:
    python tests/test_database_compat.py
"""

import re
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.database import (
    _adapt_sql,
    _PH_RE,
    _TABLES,
    _SCHEMA_SQLITE,
    _SCHEMA_PG,
    _USE_PG,
    _render_schema,
    init_db,
    _conn,
    _now,
)

_passed = 0
_failed = 0


def _check(name: str, condition: bool, detail: str = ""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  OK  {name}")
    else:
        _failed += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f" -- {detail}"
        print(msg)


# =========================================================
# 1. Placeholder translation
# =========================================================

def test_placeholder_translation():
    """Verify ? -> %s translation handles edge cases correctly."""
    print("\n--- Placeholder translation ---")

    # Helper: simulate PG path regardless of actual backend
    def translate(sql: str) -> str:
        return _PH_RE.sub(
            lambda m: '%s' if m.group(0) == '?' else m.group(0),
            sql,
        )

    # Basic replacement
    _check(
        "basic single placeholder",
        translate("SELECT * FROM t WHERE id = ?") == "SELECT * FROM t WHERE id = %s",
    )

    _check(
        "multiple placeholders",
        translate("WHERE a=? AND b=?") == "WHERE a=%s AND b=%s",
    )

    _check(
        "insert with 10 placeholders",
        translate("VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)") ==
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    )

    # Quoted strings must be preserved
    _check(
        "? inside single-quoted string preserved",
        translate("WHERE note LIKE 'question?'") == "WHERE note LIKE 'question?'",
    )

    _check(
        "? inside quotes + ? outside translated",
        translate("WHERE a=? AND b LIKE 'test?test' AND c=?") ==
        "WHERE a=%s AND b LIKE 'test?test' AND c=%s",
    )

    _check(
        "multiple quoted strings with ?",
        translate("WHERE a='x?' AND b='y?' AND c=?") ==
        "WHERE a='x?' AND b='y?' AND c=%s",
    )

    _check(
        "default value in DDL preserved",
        translate("status TEXT NOT NULL DEFAULT 'open'") ==
        "status TEXT NOT NULL DEFAULT 'open'",
    )

    # No placeholders
    _check(
        "no placeholders unchanged",
        translate("SELECT COUNT(*) FROM t") == "SELECT COUNT(*) FROM t",
    )

    # Parameter count assertion
    try:
        # Force PG path for assertion test
        original_use_pg = _USE_PG
        import services.database as db_mod
        db_mod._USE_PG = True
        try:
            _adapt_sql("SELECT * FROM t WHERE a=? AND b=?", param_count=2)
            _check("param count match (2=2)", True)
        except AssertionError:
            _check("param count match (2=2)", False, "unexpected assertion")

        try:
            _adapt_sql("SELECT * FROM t WHERE a=?", param_count=3)
            _check("param count mismatch detected (1!=3)", False, "should have asserted")
        except AssertionError:
            _check("param count mismatch detected (1!=3)", True)
        finally:
            db_mod._USE_PG = original_use_pg
    except Exception as e:
        _check("param count assertion", False, str(e))


# =========================================================
# 2. Schema synchronization
# =========================================================

def test_schema_sync():
    """Verify both schemas define identical tables and columns."""
    print("\n--- Schema synchronization ---")

    # Both schemas are generated from the same _TABLES structure,
    # so they must produce matching table/column names.

    def extract_structure(schema: str):
        """Extract {table_name: [col_names]} from DDL string."""
        tables = {}
        for match in re.finditer(
            r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\);',
            schema, re.DOTALL,
        ):
            name = match.group(1)
            body = match.group(2)
            cols = []
            for line in body.strip().split('\n'):
                line = line.strip().rstrip(',')
                if not line:
                    continue
                first_token = line.split()[0]
                # Skip constraints (UNIQUE, FOREIGN, etc.)
                if first_token.upper() in ('UNIQUE', 'FOREIGN', 'PRIMARY', 'CHECK', 'CONSTRAINT'):
                    continue
                cols.append(first_token)
            tables[name] = cols
        return tables

    sqlite_tables = extract_structure(_SCHEMA_SQLITE)
    pg_tables = extract_structure(_SCHEMA_PG)

    _check(
        f"same table count ({len(sqlite_tables)})",
        len(sqlite_tables) == len(pg_tables),
        f"sqlite={len(sqlite_tables)}, pg={len(pg_tables)}",
    )

    _check(
        "same table names",
        set(sqlite_tables.keys()) == set(pg_tables.keys()),
        f"sqlite={sorted(sqlite_tables.keys())}, pg={sorted(pg_tables.keys())}",
    )

    for table_name in sqlite_tables:
        if table_name not in pg_tables:
            continue
        sqlite_cols = sqlite_tables[table_name]
        pg_cols = pg_tables[table_name]
        _check(
            f"{table_name}: same columns ({len(sqlite_cols)})",
            sqlite_cols == pg_cols,
            f"sqlite={sqlite_cols}, pg={pg_cols}",
        )

    # Verify _TABLES is the actual source
    _check(
        "schemas generated from _TABLES",
        _SCHEMA_SQLITE == _render_schema("sqlite") and _SCHEMA_PG == _render_schema("pg"),
    )

    # Verify expected dialect differences exist
    _check(
        "sqlite uses AUTOINCREMENT",
        "AUTOINCREMENT" in _SCHEMA_SQLITE and "AUTOINCREMENT" not in _SCHEMA_PG,
    )
    _check(
        "pg uses SERIAL",
        "SERIAL" in _SCHEMA_PG and "SERIAL" not in _SCHEMA_SQLITE,
    )
    _check(
        "pg uses BIGINT for chat_id",
        "BIGINT" in _SCHEMA_PG,
    )


# =========================================================
# 3. Write/read roundtrip
# =========================================================

def test_roundtrip():
    """Verify write + read works on the active backend."""
    print("\n--- Roundtrip (active backend) ---")

    init_db()
    now = _now()
    backend = "PostgreSQL" if _USE_PG else "SQLite"
    print(f"  Backend: {backend}")

    with _conn() as conn:
        # Insert a test conversation
        conn.execute(
            """INSERT INTO conversations
               (client_id, property_id, telegram_chat_id,
                status, owner, priority, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(client_id, property_id, telegram_chat_id) DO UPDATE SET
                   updated_at = excluded.updated_at""",
            ("_compat_test_", "_compat_test_", 777888, "open", "bot", "normal", now, now),
        )

        # Read it back
        row = conn.execute(
            "SELECT * FROM conversations WHERE telegram_chat_id = ?",
            (777888,),
        ).fetchone()

        _check("insert + select", row is not None)

        if row:
            _check("client_id correct", row["client_id"] == "_compat_test_")
            _check("status correct", row["status"] == "open")
            _check("row is dict-like", isinstance(row["id"], int))

        # Update
        conn.execute(
            "UPDATE conversations SET status = ? WHERE telegram_chat_id = ?",
            ("urgent", 777888),
        )
        updated = conn.execute(
            "SELECT status FROM conversations WHERE telegram_chat_id = ?",
            (777888,),
        ).fetchone()
        _check("update works", updated and updated["status"] == "urgent")

        # Count
        cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM conversations WHERE telegram_chat_id = ?",
            (777888,),
        ).fetchone()
        _check("count works", cnt and cnt["cnt"] == 1)

        # Cleanup
        conn.execute(
            "DELETE FROM conversations WHERE telegram_chat_id = ?",
            (777888,),
        )
        gone = conn.execute(
            "SELECT * FROM conversations WHERE telegram_chat_id = ?",
            (777888,),
        ).fetchone()
        _check("cleanup (delete)", gone is None)


# =========================================================
# Run all tests
# =========================================================

if __name__ == "__main__":
    test_placeholder_translation()
    test_schema_sync()
    test_roundtrip()

    print(f"\n{'='*40}")
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed > 0:
        sys.exit(1)
    else:
        print("All safety tests passed.")
