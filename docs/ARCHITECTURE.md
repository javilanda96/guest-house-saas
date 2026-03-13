# Architecture

Last updated: 2026-03-12

## System Overview

Booking Bot is an AI-powered guest messaging assistant for vacation rentals. It receives guest messages via Telegram, classifies them using OpenAI, generates contextual replies using a property-specific knowledge base, and escalates sensitive situations to the host.

The system runs as a single Render web service containing two processes:
- `bot.py` — Telegram polling loop (background)
- `uvicorn` serving `api.py` — FastAPI API + admin panel (foreground)

Both processes share the same SQLite database file (`data/bot.db`).

```
Guest (Telegram)
    |
    v
bot.py (polling loop)
    |
    ├── classify message (OpenAI)
    ├── route to knowledge base topic
    ├── generate reply (OpenAI)
    ├── detect language, translate if needed (lingua)
    ├── send reply to guest (Telegram API)
    ├── send alert to staff if escalated (Telegram API)
    └── persist to SQLite
            |
            v
        data/bot.db  <──── api.py (FastAPI)
                               |
                               v
                        Admin Panel (HTML/JS)
```

## Bot Architecture (bot.py)

### Entry Point
`bot.py` has a `main()` function called from `if __name__ == "__main__"`. It runs an infinite loop polling Telegram for new messages.

### Message Processing Flow
1. `channel.get_updates()` — polls Telegram with 30s long-polling timeout
2. Idempotency check — `processed_keys` set of `(chat_id, message_id)` prevents double-processing
3. Rate limiting — per-chat timestamps prevent abuse
4. `process_message()` in `services/processor.py`:
   - `is_urgent(text)` — keyword scan for emergencies (fire, gas leak, etc.)
   - `classify_with_ai()` — OpenAI classifies into: faq, operational, incident, emergency, complaint, ambiguous
   - `determine_action()` — maps category + urgency to action: reply_guest, reply_and_alert, alert_staff_urgent, ask_clarification
   - `choose_kb_key()` + `load_relevant_knowledge()` — selects and loads the relevant knowledge base file
   - Handler dispatch: `handle_greeting()`, `handle_reply_guest()`, `handle_sensitive_case()`, `handle_clarification()`
   - `ensure_reply_language()` — confidence-gated language detection (lingua, threshold 0.65) to match reply language to guest language
5. Routing output:
   - `reply_guest` — send reply to guest via Telegram
   - `reply_and_alert` / `alert_staff_urgent` — send alert to configured staff chat IDs + send ack/reply to guest
6. Persist to database via `persist_interaction()`
7. Log to JSONL file via `log_interaction()`

### In-Memory State
- `chat_histories: Dict[int, List[dict]]` — conversation context per chat_id, lost on restart
- `processed_keys: Set[Tuple[int, int]]` — idempotency tracking, capped at 2000 entries
- `_rate_timestamps: Dict[int, List[float]]` — per-chat rate limiting

### Configuration (config.py)
All configuration is loaded at module import time:
- `OPENAI_API_KEY` — required env var
- `TELEGRAM_BOT_TOKEN` — required env var
- `CLIENT_ID` — env var, defaults to "cliente_demo"
- `PROPERTY_ID` — env var, defaults to "emilias_cabin"
- `TELEGRAM_ALERT_CHAT_IDS` — comma-separated env var, optional
- Property context loaded from filesystem: `knowledge/clients/{CLIENT_ID}/properties/{PROPERTY_ID}/`
- System prompts loaded from `prompts/system_reply.txt` and `prompts/system_classifier.txt`

**Critical constraint:** config.py loads everything at import time. A single bot instance serves a single property. This is the main architectural limitation for multi-property support.

### Channel Abstraction
`channels/base_channel.py` defines:
```python
class BaseChannel:
    def get_updates(self, offset=None): ...
    def send_message(self, chat_id: int, text: str): ...
```
`channels/telegram.py` implements this using raw urllib HTTP calls to the Telegram Bot API (no SDK dependency).

### Knowledge Base (filesystem)
```
knowledge/clients/{CLIENT_ID}/properties/{PROPERTY_ID}/
    property.json           # name, city, country, contact_name, contact_phone, default_language
    knowledge_base/
        faq.txt             # frequently asked questions
        checkin.txt         # check-in instructions
        house_rules.txt     # house rules
        emergencies.txt     # emergency procedures
        host_notes.txt      # host-specific notes
        local_tips.txt      # local recommendations
```
Loaded by `services/property_manager.py` at startup. Cached in memory by `services/routing.py`.

## API Architecture (api.py)

FastAPI application serving:
- Admin panel static files at `/` and `/static/*`
- REST API at `/api/*`
- Auto-generated docs at `/docs`

### Endpoints

**Read:**
- `GET /api/health` — health check, reports DB path and existence
- `GET /api/conversations` — list conversations with message counts, last message preview, pending alert counts
- `GET /api/conversations/{id}/interactions` — list messages for a conversation, with alerts attached to each interaction
- `GET /api/alerts` — list alerts, filterable by status (pending/resolved)

**Write:**
- `PATCH /api/alerts/{id}/resolve` — mark alert as resolved
- `PATCH /api/conversations/{id}/status` — update status (open, bot_resolved, host_pending, urgent)
- `PATCH /api/conversations/{id}/owner` — update owner (bot, host)

### Startup
On startup, `api.py` calls `seed_if_empty()` which:
1. Calls `init_db()` to create tables if they don't exist
2. Checks if the conversations table is empty
3. If empty, inserts 5 demo conversations with interactions and alerts

## Admin Panel

Three HTML pages served as static files, using vanilla JavaScript and CSS:

### Inbox (static/index.html, served at /)
- Card-based conversation list (not a table)
- Filter tabs: Needs Attention (default) / All / Resolved
- Sorted by urgency: urgent > host_pending > open > bot_resolved, then by recency
- Each card shows: property name, status badge, owner badge, relative timestamp, last message preview, message count, pending alerts indicator
- Clicking a card opens the conversation detail

### Conversation Detail (static/conversation.html)
- Chronological message timeline
- Each interaction shows: user message, bot reply, classification badges (action, category, urgent, escalated)
- Inline alert cards rendered after the interaction that triggered them
- Alert cards show: reason, translated text, bot draft, resolve button
- XSS protection via `textContent`-based escaping

### Alerts (static/alerts.html)
- Table of all alerts across conversations
- Filter tabs: All / Pending / Resolved
- Each row links to the parent conversation
- Resolve button for pending alerts
- Horizontal scroll wrapper for mobile

### Shared Assets
- `static/css/style.css` — all styles including inbox cards, message cards, inline alert cards, badges, responsive media queries
- `static/js/api.js` — shared fetch helpers (`API.get()`, `API.patch()`), date formatting (`fmtDate()`, `timeAgo()`), status CSS classes (`statusClass()`)

### Mobile Responsiveness
All three pages include `<meta name="viewport">`. A `@media (max-width: 600px)` block handles: reduced padding, flex-wrap on card rows, removed alert indent, table scroll wrapper, adjusted font sizes.

## Database Schema (SQLite)

Three tables in `data/bot.db`:

### conversations
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| client_id | TEXT NOT NULL | SaaS tenant identifier |
| property_id | TEXT NOT NULL | Property within client |
| telegram_chat_id | INTEGER NOT NULL | Guest's Telegram chat ID |
| status | TEXT | open, bot_resolved, host_pending, urgent |
| owner | TEXT | bot, host |
| priority | TEXT | normal, high |
| created_at | TEXT | UTC ISO timestamp |
| updated_at | TEXT | UTC ISO timestamp |

UNIQUE constraint on `(client_id, property_id, telegram_chat_id)`.

### interactions
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| conversation_id | INTEGER FK | References conversations(id) |
| user_message | TEXT NOT NULL | Raw guest message |
| category | TEXT | faq, operational, incident, emergency, complaint, ambiguous |
| reason | TEXT | Classification explanation |
| action | TEXT | reply_guest, reply_and_alert, alert_staff_urgent, ask_clarification |
| urgent | INTEGER | 0 or 1 |
| escalate | INTEGER | 0 or 1 |
| reply_text | TEXT | Bot's direct reply |
| ack_text | TEXT | Acknowledgment reply (sensitive cases) |
| created_at | TEXT | UTC ISO timestamp |

### alerts
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | AUTOINCREMENT |
| interaction_id | INTEGER FK | References interactions(id) |
| conversation_id | INTEGER FK | References conversations(id), denormalized |
| reason | TEXT | Alert reason |
| translated_text | TEXT | Message translated to Spanish |
| draft_text | TEXT | Suggested host response |
| urgent | INTEGER | 0 or 1 |
| resolved_at | TEXT | NULL = pending, timestamp = resolved |
| created_at | TEXT | UTC ISO timestamp |

## Deployment (Render)

### Service Configuration (render.yaml)
- Single web service: `booking-bot-api`
- Runtime: Python 3.12
- Build command: `pip install -r requirements.txt`
- Start command: `bash start.sh`

### Startup Script (start.sh)
```bash
#!/usr/bin/env bash
set -e
python bot.py &
exec uvicorn api:app --host 0.0.0.0 --port $PORT
```
- `bot.py` runs in background (Telegram polling)
- `uvicorn` runs in foreground via `exec` (becomes PID 1, receives SIGTERM directly from Render)
- Both share the same filesystem and `data/bot.db`

### Required Environment Variables on Render
- `OPENAI_API_KEY` — OpenAI API key for classification and reply generation
- `TELEGRAM_BOT_TOKEN` — Telegram bot token for message polling and sending
- `PYTHON_VERSION=3.12`
- `CLIENT_ID` (optional, defaults to "cliente_demo")
- `PROPERTY_ID` (optional, defaults to "emilias_cabin")
- `TELEGRAM_ALERT_CHAT_IDS` (optional, comma-separated Telegram chat IDs for staff alerts)

### Dependencies (requirements.txt)
```
openai==2.24.0
lingua-language-detector==2.2.0
httpx==0.28.1
fastapi==0.135.1
uvicorn[standard]==0.41.0
```

### Known Deployment Limitations
- **SQLite is ephemeral on Render.** Every deploy or service restart wipes `data/bot.db`. The seed script repopulates demo data, but real conversation history is lost.
- **No authentication.** The panel URL is public. Anyone with the URL can view all data.
- **Single-process bot.** If `bot.py` crashes in background, the API continues but the bot stops silently. No auto-restart or health monitoring for the background process.
- **In-memory chat history.** Bot conversation context is lost on every restart.

## File Structure

```
booking-bot-sandbox/
    api.py                  # FastAPI server
    bot.py                  # Telegram bot main loop
    config.py               # Centralized configuration (loaded at import time)
    main.py                 # Legacy entry point
    start.sh                # Render startup script
    render.yaml             # Render blueprint
    seed_demo.py            # Demo data seeder
    requirements.txt        # Python dependencies (full)
    requirements-api.txt    # Python dependencies (API-only, for reference)
    channels/
        base_channel.py     # Channel interface
        telegram.py         # Telegram implementation
    services/
        database.py         # SQLite persistence layer
        logger.py           # File-based logging
        openai_client.py    # OpenAI API wrapper + language detection
        processor.py        # Message classification and reply pipeline
        property_manager.py # Filesystem knowledge base loader
        routing.py          # Knowledge base topic routing + keyword detection
    prompts/
        system_reply.txt    # Guest reply system prompt (templated)
        system_classifier.txt # Classification system prompt
    knowledge/
        clients/{CLIENT_ID}/properties/{PROPERTY_ID}/
            property.json
            knowledge_base/*.txt
    static/
        index.html          # Inbox view (landing page)
        conversation.html   # Conversation detail + timeline
        alerts.html         # Alerts list
        css/style.css       # All styles
        js/api.js           # Shared JS utilities
    data/
        bot.db              # SQLite database (created at runtime)
    logs/
        interactions.jsonl   # Interaction log
        classifier.log       # Classification log
        reply.log            # Reply log
        alerts.log           # Alert log
    tests/
        test_classifier.py   # Classification accuracy tests
        classification_dataset.json
    docs/
        ARCHITECTURE.md      # This file
        PRODUCT_VISION.md    # Long-term product direction
        ROADMAP.md           # Implementation roadmap
```
