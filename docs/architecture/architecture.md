This document is a human-readable overview.
The source of truth for the current system is PROJECT_CONTEXT.json.

# Arquitectura

Última actualización: 2026-03-12

## Visión general del sistema

Booking Bot es un asistente de mensajería para huéspedes de alojamientos turísticos. Recibe mensajes por Telegram, los clasifica mediante OpenAI, genera respuestas contextuales a partir de la base de conocimiento de la propiedad y escala situaciones sensibles al anfitrión.

El sistema se ejecuta como un único servicio web en Render con dos procesos:
- `bot.py` — bucle de polling de Telegram (en segundo plano)
- `uvicorn` sirviendo `api.py` — API FastAPI + panel de administración (en primer plano)

Ambos procesos comparten el mismo archivo de base de datos SQLite (`data/bot.db`).

```
Huésped (Telegram)
    |
    v
bot.py (polling loop)
    |
    ├── clasificar mensaje (OpenAI)
    ├── enrutar al topic de la base de conocimiento
    ├── generar respuesta (OpenAI)
    ├── detectar idioma, traducir si es necesario (lingua)
    ├── enviar respuesta al huésped (Telegram API)
    ├── enviar alerta al equipo si se escala (Telegram API)
    └── persistir en SQLite
            |
            v
        data/bot.db  <──── api.py (FastAPI)
                               |
                               v
                        Panel de administración (HTML/JS)
```

## Arquitectura del bot (bot.py)

### Punto de entrada
`bot.py` tiene una función `main()` llamada desde `if __name__ == "__main__"`. Ejecuta un bucle infinito que hace polling de Telegram para recibir nuevos mensajes.

### Flujo de procesamiento de mensajes
1. `channel.get_updates()` — hace polling de Telegram con timeout de long-polling de 30s
2. Control de idempotencia — el conjunto `processed_keys` de `(chat_id, message_id)` evita el doble procesamiento
3. Rate limiting — timestamps por chat previenen el abuso
4. `process_message()` en `services/processor.py`:
   - `is_urgent(text)` — escaneo de palabras clave para emergencias (incendio, fuga de gas, etc.)
   - `classify_with_ai()` — OpenAI clasifica en: faq, operational, incident, emergency, complaint, ambiguous
   - `determine_action()` — mapea categoría + urgencia a acción: reply_guest, reply_and_alert, alert_staff_urgent, ask_clarification
   - `choose_kb_key()` + `load_relevant_knowledge()` — selecciona y carga el archivo de base de conocimiento relevante
   - Despacho de handlers: `handle_greeting()`, `handle_reply_guest()`, `handle_sensitive_case()`, `handle_clarification()`
   - `ensure_reply_language()` — detección de idioma con umbral de confianza (lingua, threshold 0.65) para responder en el idioma del huésped
5. Salida del enrutamiento:
   - `reply_guest` — enviar respuesta al huésped por Telegram
   - `reply_and_alert` / `alert_staff_urgent` — enviar alerta a los chat IDs del equipo + enviar acuse/respuesta al huésped
6. Persistir en base de datos via `persist_interaction()`
7. Registrar en archivo JSONL via `log_interaction()`

### Estado en memoria
- `chat_histories: Dict[int, List[dict]]` — contexto de conversación por chat_id, se pierde al reiniciar
- `processed_keys: Set[Tuple[int, int]]` — control de idempotencia, limitado a 2000 entradas
- `_rate_timestamps: Dict[int, List[float]]` — rate limiting por chat

### Configuración (config.py)
Toda la configuración se carga en el momento de importar el módulo:
- `OPENAI_API_KEY` — variable de entorno obligatoria
- `TELEGRAM_BOT_TOKEN` — variable de entorno obligatoria
- `CLIENT_ID` — variable de entorno, por defecto "cliente_demo"
- `PROPERTY_ID` — variable de entorno, por defecto "emilias_cabin"
- `TELEGRAM_ALERT_CHAT_IDS` — variable de entorno separada por comas, opcional
- Contexto de propiedad cargado desde el sistema de archivos: `knowledge/clients/{CLIENT_ID}/properties/{PROPERTY_ID}/`
- Prompts del sistema cargados desde `prompts/system_reply.txt` y `prompts/system_classifier.txt`

**Restricción crítica:** config.py carga todo en el momento de la importación. Una instancia del bot sirve a una única propiedad. Esta es la principal limitación arquitectónica para el soporte multi-propiedad.

### Abstracción de canal
`channels/base_channel.py` define:
```python
class BaseChannel:
    def get_updates(self, offset=None): ...
    def send_message(self, chat_id: int, text: str): ...
```
`channels/telegram.py` implementa esto usando llamadas HTTP directas con urllib a la Telegram Bot API (sin dependencia de SDK).

### Base de conocimiento (sistema de archivos)
```
knowledge/clients/{CLIENT_ID}/properties/{PROPERTY_ID}/
    property.json           # nombre, ciudad, país, contact_name, contact_phone, default_language
    knowledge_base/
        faq.txt             # preguntas frecuentes
        checkin.txt         # instrucciones de check-in
        house_rules.txt     # normas de la casa
        emergencies.txt     # procedimientos de emergencia
        host_notes.txt      # notas específicas del anfitrión
        local_tips.txt      # recomendaciones locales
```
Cargado por `services/property_manager.py` al arrancar. Almacenado en memoria por `services/routing.py`.

## Arquitectura de la API (api.py)

Aplicación FastAPI que sirve:
- Archivos estáticos del panel de administración en `/` y `/static/*`
- API REST en `/api/*`
- Documentación autogenerada en `/docs`

### Endpoints

**Lectura:**
- `GET /api/health` — health check, informa sobre la ruta y existencia de la DB
- `GET /api/conversations` — lista conversaciones con conteo de mensajes, vista previa del último mensaje y conteo de alertas pendientes
- `GET /api/conversations/{id}/interactions` — lista mensajes de una conversación, con alertas asociadas a cada interacción
- `GET /api/alerts` — lista alertas, filtrables por estado (pending/resolved)

**Escritura:**
- `PATCH /api/alerts/{id}/resolve` — marca una alerta como resuelta
- `PATCH /api/conversations/{id}/status` — actualiza el estado (open, bot_resolved, host_pending, urgent)
- `PATCH /api/conversations/{id}/owner` — actualiza el owner (bot, host)

### Arranque
Al arrancar, `api.py` llama a `seed_if_empty()` que:
1. Llama a `init_db()` para crear las tablas si no existen
2. Comprueba si la tabla de conversaciones está vacía
3. Si está vacía, inserta 5 conversaciones demo con interacciones y alertas

## Panel de administración

Tres páginas HTML servidas como archivos estáticos, usando JavaScript y CSS vanilla:

### Bandeja de entrada (static/index.html, servida en /)
- Lista de conversaciones en formato tarjeta (no tabla)
- Pestañas de filtro: Requiere atención (por defecto) / Todas / Resueltas
- Ordenadas por urgencia: urgent > host_pending > open > bot_resolved, luego por recencia
- Cada tarjeta muestra: nombre de propiedad, badge de estado, badge de owner, timestamp relativo, vista previa del último mensaje, conteo de mensajes, indicador de alertas pendientes
- Al hacer clic en una tarjeta se abre el detalle de la conversación

### Detalle de conversación (static/conversation.html)
- Timeline cronológico de mensajes
- Cada interacción muestra: mensaje del usuario, respuesta del bot, badges de clasificación (action, category, urgent, escalated)
- Tarjetas de alerta renderizadas inline después de la interacción que las generó
- Las tarjetas de alerta muestran: motivo, texto traducido, borrador del bot, botón de resolver
- Protección XSS via escape basado en `textContent`

### Alertas (static/alerts.html)
- Tabla de todas las alertas entre conversaciones
- Pestañas de filtro: Todas / Pendientes / Resueltas
- Cada fila enlaza a la conversación padre
- Botón de resolver para alertas pendientes
- Wrapper de scroll horizontal para móvil

### Recursos compartidos
- `static/css/style.css` — todos los estilos incluyendo tarjetas de bandeja, tarjetas de mensaje, tarjetas de alerta inline, badges, media queries responsive
- `static/js/api.js` — helpers de fetch compartidos (`API.get()`, `API.patch()`), formateo de fechas (`fmtDate()`, `timeAgo()`), clases CSS de estado (`statusClass()`)

### Responsividad móvil
Las tres páginas incluyen `<meta name="viewport">`. Un bloque `@media (max-width: 600px)` gestiona: padding reducido, flex-wrap en filas de tarjetas, indentación de alerta eliminada, wrapper de scroll en tabla, tamaños de fuente ajustados.

## Esquema de base de datos (SQLite)

Tres tablas en `data/bot.db`:

### conversations
| Columna | Tipo | Notas |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| client_id | TEXT NOT NULL | Identificador de tenant SaaS |
| property_id | TEXT NOT NULL | Propiedad dentro del cliente |
| telegram_chat_id | INTEGER NOT NULL | Chat ID de Telegram del huésped |
| status | TEXT | open, bot_resolved, host_pending, urgent |
| owner | TEXT | bot, host |
| priority | TEXT | normal, high |
| created_at | TEXT | Timestamp UTC ISO |
| updated_at | TEXT | Timestamp UTC ISO |

Restricción UNIQUE en `(client_id, property_id, telegram_chat_id)`.

### interactions
| Columna | Tipo | Notas |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| conversation_id | INTEGER FK | Referencias conversations(id) |
| user_message | TEXT NOT NULL | Mensaje bruto del huésped |
| category | TEXT | faq, operational, incident, emergency, complaint, ambiguous |
| reason | TEXT | Explicación de la clasificación |
| action | TEXT | reply_guest, reply_and_alert, alert_staff_urgent, ask_clarification |
| urgent | INTEGER | 0 o 1 |
| escalate | INTEGER | 0 o 1 |
| reply_text | TEXT | Respuesta directa del bot |
| ack_text | TEXT | Respuesta de acuse (casos sensibles) |
| created_at | TEXT | Timestamp UTC ISO |

### alerts
| Columna | Tipo | Notas |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| interaction_id | INTEGER FK | Referencias interactions(id) |
| conversation_id | INTEGER FK | Referencias conversations(id), desnormalizado |
| reason | TEXT | Motivo de la alerta |
| translated_text | TEXT | Mensaje traducido al español |
| draft_text | TEXT | Respuesta sugerida para el anfitrión |
| urgent | INTEGER | 0 o 1 |
| resolved_at | TEXT | NULL = pendiente, timestamp = resuelta |
| created_at | TEXT | Timestamp UTC ISO |

## Despliegue (Render)

### Configuración del servicio (render.yaml)
- Servicio web único: `booking-bot-api`
- Runtime: Python 3.12
- Comando de build: `pip install -r requirements.txt`
- Comando de inicio: `bash start.sh`

### Script de arranque (start.sh)
```bash
#!/usr/bin/env bash
set -e
python bot.py &
exec uvicorn api:app --host 0.0.0.0 --port $PORT
```
- `bot.py` se ejecuta en segundo plano (polling de Telegram)
- `uvicorn` se ejecuta en primer plano via `exec` (se convierte en PID 1, recibe SIGTERM directamente de Render)
- Ambos comparten el mismo sistema de archivos y `data/bot.db`

### Variables de entorno requeridas en Render
- `OPENAI_API_KEY` — clave de API de OpenAI para clasificación y generación de respuestas
- `TELEGRAM_BOT_TOKEN` — token del bot de Telegram para polling y envío de mensajes
- `PYTHON_VERSION=3.12`
- `CLIENT_ID` (opcional, por defecto "cliente_demo")
- `PROPERTY_ID` (opcional, por defecto "emilias_cabin")
- `TELEGRAM_ALERT_CHAT_IDS` (opcional, chat IDs de Telegram separados por comas para alertas al equipo)

### Dependencias (requirements.txt)
```
openai==2.24.0
lingua-language-detector==2.2.0
httpx==0.28.1
fastapi==0.135.1
uvicorn[standard]==0.41.0
```

### Limitaciones conocidas del despliegue
- **SQLite es efímero en Render.** Cada deploy o reinicio del servicio borra `data/bot.db`. El script de seed repopula los datos demo, pero el historial real de conversaciones se pierde.
- **Sin autenticación.** La URL del panel es pública. Cualquiera con la URL puede ver todos los datos.
- **Bot de proceso único.** Si `bot.py` se cae en segundo plano, la API continúa pero el bot se detiene silenciosamente. No hay reinicio automático ni monitorización del proceso en segundo plano.
- **Historial de chat en memoria.** El contexto de conversación del bot se pierde en cada reinicio.

## Estructura de archivos

```
booking-bot-sandbox/
    api.py                  # Servidor FastAPI
    bot.py                  # Bucle principal del bot de Telegram
    config.py               # Configuración centralizada (cargada en el momento de importación)
    main.py                 # Alias de compatibilidad legacy para bot.py (no usado por start.sh)
    start.sh                # Script de arranque de Render (ejecuta bot.py + uvicorn)
    render.yaml             # Blueprint de Render
    requirements.txt        # Dependencias Python (completas)
    requirements-api.txt    # Dependencias Python (solo API, como referencia)
    channels/
        base_channel.py     # Interfaz de canal
        telegram.py         # Implementación de Telegram
    services/
        database.py         # Capa de persistencia SQLite
        logger.py           # Logging en archivo
        openai_client.py    # Wrapper de OpenAI API + detección de idioma
        processor.py        # Pipeline de clasificación y generación de respuestas
        property_manager.py # Cargador de base de conocimiento desde sistema de archivos
        routing.py          # Enrutamiento de topics de la base de conocimiento + detección de palabras clave
    prompts/
        system_reply.txt    # Prompt del sistema para respuestas al huésped (con plantilla)
        system_classifier.txt # Prompt del sistema para clasificación
    knowledge/
        clients/{CLIENT_ID}/properties/{PROPERTY_ID}/
            property.json
            knowledge_base/*.txt
    static/
        index.html          # Vista de bandeja de entrada (página de inicio)
        conversation.html   # Detalle de conversación + timeline
        alerts.html         # Lista de alertas
        css/style.css       # Todos los estilos
        js/api.js           # Utilidades JS compartidas
    tools/
        seed_demo.py        # Seeder de datos demo (ejecutado por api.py al arrancar)
        build_knowledge_base.py  # Script de soporte: construye la base de conocimiento desde archivos raw
    datasets/               # Datos de entrenamiento ML y scripts de construcción de datasets
    data/
        bot.db              # Base de datos SQLite (creada en runtime, no versionada)
    tests/
        test_classifier.py   # Tests de precisión de clasificación
        classification_dataset.json
    docs/
        ARCHITECTURE.md      # Este archivo
        PRODUCT_VISION.md    # Dirección del producto a largo plazo
        ROADMAP.md           # Roadmap de implementación
```
