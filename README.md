# Booking Bot

AI-powered guest messaging assistant for vacation rentals. Receives guest messages via Telegram, classifies them, generates contextual replies from a property knowledge base, and escalates sensitive situations to the host. Includes a web admin panel for managing conversations and alerts.

## Prerequisites

The following environment variables are required:

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `TELEGRAM_ALERT_CHAT_IDS` | No | Comma-separated chat IDs for staff alerts |
| `CLIENT_ID` | No | Client identifier (default: `cliente_demo`) |
| `PROPERTY_ID` | No | Property identifier (default: `emilias_cabin`) |
| `PANEL_PASSWORD` | No | Enables HTTP Basic Auth on the admin panel |
| `SEED_DEMO` | No | Set to `true` to seed demo data on first startup |

## Running locally

**Bot (Telegram polling):**
```bash
python bot.py
```

**API + admin panel:**
```bash
uvicorn api:app --port 8000 --reload
```

## Deployment

Production runs both processes via a single Render web service. See [`start.sh`](start.sh) and [`render.yaml`](render.yaml).

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for system design, startup flow, database schema, and deployment details.
