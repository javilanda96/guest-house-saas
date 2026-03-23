"""
API para el chatbot de huéspedes.

Servidor FastAPI mínimo que expone los datos de bot.db
para consumo desde un panel de administración.

- Lectura: conversaciones, interacciones, alertas.
- Escritura operativa: resolver alertas, cambiar estado/owner de conversaciones.
- Proceso independiente: no interfiere con bot.py.

Seguridad:
- Si PANEL_PASSWORD esta definida -> login con cookie de sesion HMAC-firmada.
- SECRET_KEY obligatoria cuando PANEL_PASSWORD esta activa.
- Sin PANEL_PASSWORD (local dev) -> sin autenticacion.
- Si PANEL_PASSWORD esta definida -> /docs deshabilitado.

Arrancar local:
    .venv/Scripts/uvicorn api:app --port 8000 --reload
"""

import hashlib
import hmac
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
from services.db_properties import (
    get_properties,
    get_property_detail,
    update_property_profile,
    update_knowledge_content,
    VALID_KNOWLEDGE_TOPICS,
)
from tools.seed_demo import seed_if_empty

# =========================================================
# Auth configuration
# =========================================================

_PANEL_PASSWORD = os.environ.get("PANEL_PASSWORD")
_AUTH_ENABLED = _PANEL_PASSWORD is not None and len(_PANEL_PASSWORD) > 0
_SECRET_KEY = os.environ.get("SECRET_KEY", "")

_SESSION_COOKIE = "session"
_SESSION_PAYLOAD = "auth"

# Rutas publicas: el middleware las deja pasar sin cookie de sesion.
_PUBLIC_PATHS = frozenset({"/login", "/logout", "/api/health"})
_PUBLIC_PREFIX = "/static/"


def _sign_session() -> str:
    """Genera token de sesion firmado con HMAC-SHA256: 'auth.<hex_digest>'."""
    digest = hmac.new(
        _SECRET_KEY.encode(), _SESSION_PAYLOAD.encode(), hashlib.sha256
    ).hexdigest()
    return f"{_SESSION_PAYLOAD}.{digest}"


def _is_valid_session(token: str) -> bool:
    """Verifica token de sesion. Usa compare_digest para evitar timing attacks."""
    return secrets.compare_digest(token, _sign_session())


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

@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    """
    Protege todas las rutas salvo las publicas.
    - Rutas API sin cookie valida → 401 JSON.
    - Rutas HTML sin cookie valida → redirige a /login.
    - Sin PANEL_PASSWORD (dev local) → sin restricciones.
    """
    if not _AUTH_ENABLED:
        return await call_next(request)
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIX):
        return await call_next(request)
    token = request.cookies.get(_SESSION_COOKIE, "")
    if token and _is_valid_session(token):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "No autenticado"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


# Servir archivos estaticos del panel
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
def on_startup() -> None:
    """Asegura que la DB y las tablas existen al arrancar la API.
    Si la DB esta vacia y SEED_DEMO=true, inserta datos demo."""
    if _AUTH_ENABLED and not _SECRET_KEY:
        raise RuntimeError(
            "[auth] SECRET_KEY no definida. "
            "Es obligatoria cuando PANEL_PASSWORD esta activa."
        )
    seed_if_empty()  # Llama init_db() internamente


# =========================================================
# Request models
# =========================================================

class UpdateStatusRequest(BaseModel):
    status: str

class UpdateOwnerRequest(BaseModel):
    owner: str

class UpdatePropertyRequest(BaseModel):
    property_name: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    default_language: str = "en"
    city: Optional[str] = None
    country: Optional[str] = None

class UpdateKnowledgeRequest(BaseModel):
    content: str


# =========================================================
# Panel (redirige / a index.html)
# =========================================================


@app.get("/", include_in_schema=False)
def panel_root():
    """Sirve el panel principal. Protegido por middleware."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/login", include_in_schema=False)
def get_login():
    """Sirve la pagina de login. Siempre publica."""
    return FileResponse(str(_STATIC_DIR / "login.html"))


@app.post("/login", include_in_schema=False)
async def post_login(password: str = Form(...)):
    """Valida la contrasena y establece cookie de sesion firmada."""
    if _AUTH_ENABLED and secrets.compare_digest(password, _PANEL_PASSWORD):
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(
            key=_SESSION_COOKIE,
            value=_sign_session(),
            httponly=True,
            samesite="strict",
            secure=bool(os.environ.get("RENDER")),
        )
        return resp
    return RedirectResponse(url="/login?error=1", status_code=303)


@app.get("/logout", include_in_schema=False)
def logout():
    """Cierra sesion eliminando la cookie."""
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(key=_SESSION_COOKIE)
    return resp


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


@app.get("/api/properties")
def list_properties(
    client_id: Optional[str] = Query(
        default=None,
        description="Filtrar por client_id. Sin valor = todas.",
    ),
):
    """Lista propiedades registradas, opcionalmente filtradas por cliente."""
    return get_properties(client_id=client_id)


@app.get("/api/properties/{property_db_id}")
def property_detail(property_db_id: int):
    """Detalle de una propiedad con sus entradas de knowledge base."""
    result = get_property_detail(property_db_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@app.put("/api/properties/{property_db_id}")
def put_property(property_db_id: int, body: UpdatePropertyRequest):
    """Actualiza los campos de perfil de una propiedad."""
    result = update_property_profile(
        property_db_id,
        property_name=body.property_name,
        contact_name=body.contact_name,
        contact_phone=body.contact_phone,
        default_language=body.default_language,
        city=body.city,
        country=body.country,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@app.put("/api/properties/{property_db_id}/knowledge/{topic}")
def put_knowledge_topic(property_db_id: int, topic: str, body: UpdateKnowledgeRequest):
    """Actualiza el contenido de un topic en el knowledge base de una propiedad."""
    if topic not in VALID_KNOWLEDGE_TOPICS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid topic '{topic}'. Allowed: {sorted(VALID_KNOWLEDGE_TOPICS)}",
        )
    result = update_knowledge_content(property_db_id, topic, body.content)
    if result is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


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
