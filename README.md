# Booking Bot

Asistente de mensajería para huéspedes de alojamientos turísticos. Recibe mensajes por Telegram, los clasifica, genera respuestas contextuales a partir de una base de conocimiento de la propiedad y escala situaciones sensibles al anfitrión. Incluye un panel de administración web para gestionar conversaciones y alertas.

## Requisitos previos

Las siguientes variables de entorno son necesarias:

| Variable | Obligatoria | Descripción |
|---|---|---|
| `OPENAI_API_KEY` | Sí | Clave de API de OpenAI |
| `TELEGRAM_BOT_TOKEN` | Sí | Token del bot de Telegram |
| `TELEGRAM_ALERT_CHAT_IDS` | No | IDs de chat separados por comas para alertas al equipo |
| `CLIENT_ID` | No | Identificador del cliente (por defecto: `cliente_demo`) |
| `PROPERTY_ID` | No | Identificador de la propiedad (por defecto: `emilias_cabin`) |
| `PANEL_PASSWORD` | No | Activa HTTP Basic Auth en el panel de administración |
| `SEED_DEMO` | No | Establecer a `true` para insertar datos demo en el primer arranque |

## Ejecución local

**Bot (polling de Telegram):**
```bash
python bot.py
```

**API + panel de administración:**
```bash
uvicorn api:app --port 8000 --reload
```

## Despliegue

En producción ambos procesos se ejecutan en un único servicio web de Render. Ver [`start.sh`](start.sh) y [`render.yaml`](render.yaml).

## Arquitectura

Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para el diseño del sistema, flujo de arranque, esquema de base de datos y detalles de despliegue.
