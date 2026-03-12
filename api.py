"""
API para el chatbot de huéspedes.

Servidor FastAPI mínimo que expone los datos de bot.db
para consumo desde un panel de administración.

- Lectura: conversaciones, interacciones, alertas.
- Escritura operativa: resolver alertas, cambiar estado/owner de conversaciones.
- Proceso independiente: no interfiere con bot.py.
- Comparte data/bot.db con el bot via SQLite.

Arrancar:
    .venv/Scripts/uvicorn api:app --port 8000 --reload
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from services.database import (
    DB_PATH,
    init_db,
    get_conversations,
    get_conversation_interactions,
    get_alerts,
    resolve_alert,
    update_conversation_status,
    update_conversation_owner,
    VALID_CONV_STATUSES,
    VALID_CONV_OWNERS,
)
from seed_demo import seed_if_empty

_STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Booking Bot API",
    description="API operativa sobre las conversaciones y alertas del bot.",
    version="0.2.0",
)

# Servir archivos estaticos del panel
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    """Asegura que la DB y las tablas existen al arrancar la API.
    Si la DB esta vacia, inserta datos demo para que el panel no aparezca vacio."""
    seed_if_empty()  # Llama init_db() internamente


# =========================================================
# Request models
# =========================================================

class UpdateStatusRequest(BaseModel):
    status: str

class UpdateOwnerRequest(BaseModel):
    owner: str


# =========================================================
# Panel (redirige / a index.html)
# =========================================================


@app.get("/", include_in_schema=False)
def panel_root():
    """Sirve el panel principal."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


# =========================================================
# Endpoints — Lectura
# =========================================================


@app.get("/api/health")
def health():
    """Verifica que la API arranca y la DB existe."""
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
    }


@app.get("/api/conversations")
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lista conversaciones con conteo de mensajes y última actividad."""
    return get_conversations(limit=limit, offset=offset)


@app.get("/api/conversations/{conversation_id}/interactions")
def list_interactions(
    conversation_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lista interacciones (mensajes) de una conversación."""
    result = get_conversation_interactions(
        conversation_id,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@app.get("/api/alerts")
def list_alerts(
    status: Optional[str] = Query(
        default=None,
        description="Filtrar por estado: 'pending' o 'resolved'. Sin valor = todas.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lista alertas, opcionalmente filtradas por estado."""
    if status is not None and status not in ("pending", "resolved"):
        raise HTTPException(
            status_code=400,
            detail="status must be 'pending', 'resolved', or omitted",
        )
    return get_alerts(status=status, limit=limit, offset=offset)


# =========================================================
# Endpoints — Escritura operativa
# =========================================================


@app.patch("/api/alerts/{alert_id}/resolve")
def patch_resolve_alert(alert_id: int):
    """Marca una alerta como resuelta (resolved_at = ahora UTC)."""
    try:
        result = resolve_alert(alert_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


@app.patch("/api/conversations/{conversation_id}/status")
def patch_conversation_status(
    conversation_id: int,
    body: UpdateStatusRequest,
):
    """
    Actualiza el estado de una conversación.

    Valores válidos: open, bot_resolved, host_pending, urgent.
    """
    try:
        result = update_conversation_status(conversation_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@app.patch("/api/conversations/{conversation_id}/owner")
def patch_conversation_owner(
    conversation_id: int,
    body: UpdateOwnerRequest,
):
    """
    Actualiza el owner de una conversación.

    Valores válidos: bot, host.
    """
    try:
        result = update_conversation_owner(conversation_id, body.owner)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result
