# Roadmap

Last updated: 2026-03-12

## Milestone Structure

The roadmap is organized into phases, each containing small implementation blocks. Each block has a clear scope, a demoable outcome, and explicit boundaries on what NOT to build.

Size estimates:
- **Small** = 1-2 files changed, < 1 session of focused work
- **Medium** = 3-5 files changed, 1-2 sessions
- **Large** = 5+ files changed or significant refactoring, 2+ sessions

---

## Phase 0: Cloud Deployment (COMPLETE)

Single-property bot + operational inbox + Render deployment.

What was built:
- Telegram bot with AI classification and reply generation
- SQLite persistence layer (conversations, interactions, alerts)
- FastAPI API with read and write endpoints
- Admin panel: inbox view (card-based), conversation timeline with inline alerts, alerts page
- Mobile responsive CSS
- Single Render service running bot + API together via start.sh
- Demo data seeding for empty databases

---

## Phase 1: Data Foundation

Goal: Make the system reliable enough for a real pilot.

### Milestone 1A: PostgreSQL Migration

**Size:** Medium
**Goal:** Data persists across deploys and restarts.
**Why now:** Every Render deploy wipes the SQLite file. Nothing else matters until data survives.

**Scope:**
- Add `psycopg2-binary` to requirements.txt
- Modify `services/database.py`: detect `DATABASE_URL` env var. If present, use PostgreSQL. If absent, fall back to SQLite (local dev unchanged).
- Adjust SQL syntax: `?` to `%s` for parameters, `AUTOINCREMENT` to `SERIAL`, `datetime('now')` to `NOW()`, `INTEGER` booleans to proper `BOOLEAN` where needed.
- Update `seed_demo.py` to work with both backends.
- Add `DATABASE_URL` to Render env vars (Render provides this when you attach a PostgreSQL instance).
- Test: deploy, send messages, redeploy, verify data survives.

**What NOT to build:** No ORM. No Alembic. No migration framework. 3 tables do not need migration tooling.
**Risk:** SQL dialect differences between SQLite and PostgreSQL. Small but must be tested.
**Demoable outcome:** Redeploy the service. All conversations still in the panel.

### Milestone 1B: Panel Authentication

**Size:** Small
**Goal:** Guest data is not publicly accessible.
**Why now:** The panel URL is public. Anyone can read all conversations. This is a legal and trust problem.

**Scope:**
- Add `PANEL_PASSWORD` and `SECRET_KEY` env vars.
- Create a login page (`static/login.html`): one password input, one button.
- Add FastAPI middleware: check signed HTTP-only cookie on every request to `/`, `/static/*`, `/api/*`. If missing or invalid, redirect to login.
- `/api/health` remains public (Render health checks).
- Use Python's `hmac` module for cookie signing. No external auth library.

**What NOT to build:** No user accounts. No registration. No email/password. No OAuth. No roles. One shared password.
**Risk:** Cookie must be HttpOnly, Secure, SameSite=Strict. Signing key from env var, never hardcoded.
**Demoable outcome:** Share the Render URL with someone. They see a login page. Correct password grants access.
**Dependency:** Milestone 1A (no point securing ephemeral data).

---

## Phase 2: Property Configuration

Goal: A host can configure their property from the panel instead of editing files.

### Milestone 2A: Property Data in Database

**Size:** Medium
**Goal:** Property configuration and knowledge base stored in the database.
**Why now:** This is the foundation for multi-property. Currently adding a property requires filesystem access and a redeploy.

**Scope:**
- New table `properties`: id, client_id, name, city, country, contact_name, contact_phone, default_language, created_at, updated_at.
- New table `knowledge_entries`: id, property_id, topic, content, updated_at. Topics: faq, checkin, house_rules, emergencies, host_notes, local_tips.
- Migration helper: on startup, if `properties` table is empty but filesystem knowledge exists, auto-import into DB.
- New read endpoint: `GET /api/properties/{id}` returns property profile + all knowledge entries.

**What NOT to build:** No property creation from the panel yet. No editor UI. Just the data layer.
**Risk:** Must coexist with filesystem loading during transition.
**Demoable outcome:** `GET /api/properties/1` returns the full property profile and knowledge base from the database.

### Milestone 2B: Property Editor Panel

**Size:** Medium
**Goal:** Host can edit property details and knowledge base from the panel.
**Why now:** The property data is in the DB (2A). The host needs a UI to edit it.

**Scope:**
- New page: `static/property.html` — shows property profile fields (editable inputs) and knowledge sections (editable text areas).
- Each section has a Save button.
- New write endpoints: `PATCH /api/properties/{id}` for profile fields, `PUT /api/properties/{id}/knowledge/{topic}` for knowledge content.
- Add "Properties" link to nav bar.

**What NOT to build:** No property creation wizard. No image upload. No map. No amenity tags. Just the 6 existing knowledge topics + profile fields.
**Risk:** None significant. Straightforward CRUD.
**Demoable outcome:** Host opens the panel, navigates to property, changes the wifi password, clicks Save. Done.
**Dependency:** Milestone 2A.

### Milestone 2C: Bot Reads Property Context from Database

**Size:** Large (this is the key refactor)
**Goal:** `process_message()` loads property context dynamically per conversation, not from startup globals.
**Why now:** This is the wall between "one bot per property" and "one bot serving many properties." It must be done before multi-property goes live.

**Scope:**
- New function in `services/property_manager.py`: `get_property_context_from_db(property_id)` that reads from the `properties` and `knowledge_entries` tables.
- Modify `services/processor.py`: `process_message()` accepts property context as a parameter instead of reading from config globals.
- Modify `bot.py`: before calling `process_message()`, look up the property context from DB using the conversation's `property_id`.
- System prompt is templated per-request with the property's context, not once at startup.
- Filesystem loading remains as fallback when `DATABASE_URL` is not set.

**What NOT to build:** No multi-property bot routing yet. The bot still serves one property per instance. But the processing pipeline no longer assumes a single property.
**Risk:** This touches the core processing pipeline. Thorough testing required. Classification tests (22 cases) must still pass.
**Demoable outcome:** Edit a property's FAQ in the panel. Send a guest message about that topic. Bot uses the updated knowledge in its reply. No redeploy needed.
**Dependency:** Milestone 2A, 2B.

---

## Phase 3: Pilot-Ready

Goal: System works reliably for one real host with 1-3 properties.

### Milestone 3A: Bot Health Monitoring

**Size:** Small
**Goal:** Detect and auto-recover when bot.py crashes silently.
**Why now:** The bot runs in background. If it crashes, nobody knows until a guest stops getting replies.

**Scope:**
- bot.py writes a `last_bot_poll` timestamp to the database on every polling cycle.
- `/api/health` checks this timestamp. If older than 90 seconds, returns unhealthy status.
- Render's built-in health check restarts the service when unhealthy.

**What NOT to build:** No complex process manager. No supervisor. Just a timestamp check.
**Risk:** Minimal. One write per poll cycle, one read per health check.
**Demoable outcome:** Kill bot.py manually. Within 90 seconds, Render restarts the service. Bot resumes.

### Milestone 3B: Manual Reservations

**Size:** Medium
**Goal:** Host can enter guest reservations. Bot knows who is staying and when.
**Why now:** This transforms the bot from "generic assistant" to "guest-aware concierge."

**Scope:**
- New table `reservations`: id, property_id, guest_name, guest_contact, channel, channel_contact_id, check_in, check_out, status (confirmed, checked_in, checked_out), notes, created_at.
- New panel page: `static/reservations.html` — table with Add/Edit forms. Date inputs, no calendar widget.
- New endpoints: `GET /api/reservations`, `POST /api/reservations`, `PATCH /api/reservations/{id}`.
- bot.py: before processing, look up active reservation for the chat_id. If found, include guest name and stay dates in the system prompt.

**What NOT to build:** No PMS integration. No iCal sync. No calendar UI. Manual entry only.
**Risk:** Matching chat_id to reservation requires the host to enter the guest's Telegram contact when creating the reservation. This is a UX friction point to monitor.
**Demoable outcome:** Host creates a reservation for "John, checking in March 15." John sends a Telegram message. Bot's reply references his name and stay dates.
**Dependency:** Milestone 2C (bot must load property context dynamically).

### Milestone 3C: Operator-Initiated Messages

**Size:** Medium
**Goal:** Host can reply to a guest directly from the panel.
**Why now:** When the bot escalates, the host currently has no way to respond from the panel. They have to open Telegram separately.

**Scope:**
- New table: `outbound_messages` — id, conversation_id, message_text, status (pending, sent, failed), created_at, sent_at.
- Conversation detail page: add a text input + Send button below the timeline.
- New endpoint: `POST /api/conversations/{id}/send` — writes to outbound_messages.
- bot.py: on each polling cycle, check for pending outbound messages. Send via channel. Mark as sent.

**What NOT to build:** No real-time delivery. No read receipts. No typing indicators. The message appears in the panel after the next bot poll cycle (up to 30 seconds).
**Risk:** The API does not directly access the Telegram channel. Messages go through the outbound queue. This is intentional — it keeps the API and bot cleanly separated.
**Demoable outcome:** Host opens a conversation in the panel, types a reply, clicks Send. Guest receives it on Telegram within 30 seconds.
**Dependency:** Milestone 2C.

### Milestone 3D: Email Alerts

**Size:** Small
**Goal:** Host gets email notification when urgent incidents occur.
**Why now:** Telegram alerts to staff already work. Email is universal — every host has email.

**Scope:**
- New env var: `ALERT_EMAIL`.
- New file: `services/notifications.py` with `send_email_alert(subject, body)` using SMTP or a free-tier service (SendGrid free: 100 emails/day).
- In `services/database.py`: after creating an alert with `urgent=True`, call `send_email_alert()`.

**What NOT to build:** No email templates. No HTML email. Plain text. No configurable alert rules.
**Risk:** SMTP can be slow or blocked. Send in a thread or fire-and-forget to avoid blocking the bot.
**Demoable outcome:** Guest sends urgent message. Host receives email notification within seconds.
**Dependency:** Milestone 1A (need persistent DB to avoid duplicate alerts on restart).

---

## Phase 4: Multi-Property SaaS

Goal: One account manages multiple properties from a single panel.

### Milestone 4A: Multi-Property Inbox

**Size:** Medium
**Goal:** Inbox shows conversations from all properties, filterable by property.

**Scope:**
- Property filter dropdown in the inbox.
- API: `GET /api/conversations` accepts optional `property_id` query parameter.
- API: `GET /api/properties` returns list of all properties for the client.
- Panel nav: add Properties section.

**Dependency:** Milestone 2B (property editor exists).

### Milestone 4B: Multi-Token Bot Routing

**Size:** Large
**Goal:** One bot instance polls multiple Telegram tokens (one per property).

**Scope:**
- Store Telegram bot token per property in the `properties` table.
- bot.py: on startup, load all properties with tokens. Poll each in round-robin.
- Each token maps to a property. When a message arrives on token X, route to property X.
- Per-token error handling (one expired token doesn't crash all).

**Risk:** Most complex change in the roadmap. Each token has its own update offset. Rate limiting must be per-token. Thorough testing required.
**Dependency:** Milestone 2C, 3A.

### Milestone 4C: Property Creation from Panel

**Size:** Small
**Goal:** Host can add a new property entirely from the panel.

**Scope:**
- "Add Property" button on properties page.
- Creates DB row with empty knowledge entries.
- Host fills in profile and knowledge through the existing editor (Milestone 2B).

**Dependency:** Milestone 2B, 4A.

---

## Phase 5: Channel Expansion

Goal: Guests communicate via WhatsApp.

### Milestone 5A: Generalize Channel Contact ID

**Size:** Medium (migration)
**Goal:** Database supports multiple channel types, not just Telegram.

**Scope:**
- Rename `telegram_chat_id` to `channel_contact_id` in all tables.
- Add `channel` column to `conversations` (telegram, whatsapp, email).
- Update all queries, API responses, and panel references.

**Note:** This rename is easier to do early (less data). Consider doing it during Phase 2 or 3 to reduce future migration pain.

### Milestone 5B: Webhook Receiver

**Size:** Medium
**Goal:** API can receive incoming messages from webhook-based channels.

**Scope:**
- New endpoint: `POST /api/webhooks/{channel}` — receives messages from WhatsApp, etc.
- Extract `process_message()` into a shared service callable from both bot.py (polling) and api.py (webhook).
- This is the refactor that unifies polling and push channels.

**Dependency:** Milestone 5A, 2C.

### Milestone 5C: WhatsApp Integration

**Size:** Large
**Goal:** Guests message via WhatsApp. Bot replies. Host sees it in the inbox.

**Scope:**
- Implement `channels/whatsapp.py` extending BaseChannel.
- WhatsApp Business API integration (Meta Cloud API).
- Template message approval for proactive messaging.
- Channel icon in inbox cards.

**Dependency:** Milestone 5A, 5B. Also requires Meta Business API approval (external dependency, weeks of lead time).

---

## Unavoidable Refactors

| Refactor | When | Why |
|----------|------|-----|
| `config.py` dynamic property loading | Phase 2 (Milestone 2C) | Without this, one bot = one property forever |
| `telegram_chat_id` to `channel_contact_id` | Phase 2-3 (or Phase 5A) | Gets harder with more data. Do it before pilot if possible. |
| `process_message()` callable from API | Phase 5 (Milestone 5B) | Webhook channels need the API to process messages |
| Bot polling loop supports multiple tokens | Phase 4 (Milestone 4B) | Multi-property requires multi-token polling |

## Features Explicitly Considered Premature

| Feature | Why premature | When it becomes relevant |
|---------|---------------|------------------------|
| PMS/iCal integration | Every PMS has a different API. Manual entry validates the concept first. | After manual reservations are validated with a real host. |
| Automated scheduled messages | Requires reservations + templates + scheduler. | After operator-initiated messaging works. |
| Analytics dashboard | Hosts with 3 properties don't need charts. | When managing 10+ properties. |
| AI fine-tuning per property | Base model with good KB context is sufficient. | When reply quality becomes a competitive issue. |
| Multi-language panel UI | Host language is known. Hardcode one. | When selling to non-Spanish-speaking markets. |
| Mobile native app | Responsive web panel is adequate. | When mobile usage justifies the maintenance cost. |
| Complex RBAC | Simple password auth first. | When multiple team members need different access levels. |
| Docker/containerization | Render's native Python runtime works. | When deployment complexity requires it. |
| Migration framework (Alembic) | 3 tables don't need migration tooling. | When schema has 15+ tables. |
| Facebook Messenger / Booking.com | WhatsApp covers 80%+ of the market. | After WhatsApp integration is validated. |

## Dependency Graph

```
Phase 0 (COMPLETE)
    |
    v
1A: PostgreSQL ─────────────────────────────────┐
    |                                            |
    v                                            |
1B: Auth ────────────────────────┐               |
    |                            |               |
    v                            v               v
2A: Property Data in DB    3D: Email Alerts    3A: Bot Health
    |
    v
2B: Property Editor
    |
    v
2C: Dynamic Property Context (KEY REFACTOR)
    |
    ├──────────────────┐
    v                  v
3B: Reservations    3C: Operator Messages
    |                  |
    v                  v
4A: Multi-Property Inbox
    |
    v
4B: Multi-Token Bot
    |
    v
4C: Property Creation
    |
    v
5A: Channel Contact ID (can be done earlier)
    |
    v
5B: Webhook Receiver
    |
    v
5C: WhatsApp
```

## Next Concrete Action

**Milestone 1A: PostgreSQL migration.** Everything else is blocked by ephemeral data.
