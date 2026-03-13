"""
API para el chatbot de huéspedes.

Servidor FastAPI mínimo que expone los datos de bot.db
para consumo desde un panel de administración.

- Lectura: conversaciones, interacciones, alertas.
- Escritura operativa: resolver alertas, cambiar estado/owner de conversaciones.
- Proceso independiente: no interfiere con bot.py.

Seguridad:
- Si PANEL_PASSWORD esta definida -> HTTP Basic Auth en todo excepto /api/health.
- Si no esta definida (local dev) -> sin autenticacion.
- Si PANEL_PASSWORD esta definida -> /docs deshabilitado.

Arrancar local:
    .venv/Scripts/uvicorn api:app --port 8000 --reload
"""

import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from services.database import (
    DB_PATH,
    _USE_PG,
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

# =========================================================
# Auth configuration
# =========================================================

_PANEL_PASSWORD = os.environ.get("PANEL_PASSWORD")
_AUTH_ENABLED = _PANEL_PASSWORD is not None and len(_PANEL_PASSWORD) > 0

security = HTTPBasic()


def _verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Verifica HTTP Basic Auth.
    Username: 'admin' (fijo).
    Password: valor de PANEL_PASSWORD.
    Usa secrets.compare_digest para evitar timing attacks.
    """
    correct_user = secrets.compare_digest(credentials.username, "admin")
    correct_pass = secrets.compare_digest(credentials.password, _PANEL_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )


# Solo aplicar auth si PANEL_PASSWORD esta definida.
# En desarrollo local (sin PANEL_PASSWORD) no hay autenticacion.
_auth_deps = [Depends(_verify_auth)] if _AUTH_ENABLED else []


# =========================================================
# App configuration
# =========================================================

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Deshabilitar /docs en produccion (cuando auth esta activo).
# Los desarrolladores pueden acceder a /docs localmente sin password.
app = FastAPI(
    title="Booking Bot API",
    description="API operativa sobre las conversaciones y alertas del bot.",
    version="0.3.0",
    docs_url=None if _AUTH_ENABLED else "/docs",
    redoc_url=None,
    openapi_url=None if _AUTH_ENABLED else "/openapi.json",
)

# Servir archivos estaticos del panel
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    """Asegura que la DB y las tablas existen al arrancar la API.
    Si la DB esta vacia y SEED_DEMO=true, inserta datos demo."""
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


@app.get("/", include_in_schema=False, dependencies=_auth_deps)
def panel_root():
    """Sirve el panel principal."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


# =========================================================
# Endpoints — Lectura
# =========================================================


@app.get("/api/health")
def health():
    """Verifica que la API arranca y la DB existe. Sin autenticacion (health check de Render)."""
    if _USE_PG:
        return {
            "status": "ok",
            "backend": "postgresql",
        }
    return {
        "status": "ok",
        "backend": "sqlite",
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
    }


@app.get("/api/conversations", dependencies=_auth_deps)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lista conversaciones con conteo de mensajes y última actividad."""
    return get_conversations(limit=limit, offset=offset)


@app.get("/api/conversations/{conversation_id}/interactions", dependencies=_auth_deps)
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


@app.get("/api/alerts", dependencies=_auth_deps)
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


@app.patch("/api/alerts/{alert_id}/resolve", dependencies=_auth_deps)
def patch_resolve_alert(alert_id: int):
    """Marca una alerta como resuelta (resolved_at = ahora UTC)."""
    try:
        result = resolve_alert(alert_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


@app.patch("/api/conversations/{conversation_id}/status", dependencies=_auth_deps)
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


@app.patch("/api/conversations/{conversation_id}/owner", dependencies=_auth_deps)
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
