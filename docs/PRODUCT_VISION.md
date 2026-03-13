# Product Vision

Last updated: 2026-03-12

## What This Is

An AI-powered guest messaging platform for vacation rental operators. The system automatically handles guest communications (questions, requests, incidents) via messaging channels, escalates sensitive situations to the host, and provides an operational panel for monitoring and intervention.

## Who It's For

- Airbnb hosts managing 1-10 properties
- Small property managers
- Hospitality operators who want to automate guest communication without losing control

These users care about: guest problems, property incidents, unresolved conversations, urgent situations, and what requires human attention. They do not care about technical metrics or system internals.

## Core Product Concept

An **operational inbox** — not a dashboard, not an analytics tool. The host opens the panel, immediately sees what needs attention, inspects conversations, resolves incidents, and intervenes when the AI cannot handle something. The goal is situational awareness in under 10 seconds.

## Current State (MVP)

Working end-to-end:
- Telegram bot receives guest messages and replies automatically
- AI classifies messages and routes to appropriate knowledge base topics
- Sensitive situations are escalated with alerts
- Admin panel shows conversations as an operational inbox
- Alerts appear inline in the conversation timeline
- Panel and bot deployed together on Render

Single-property, single-channel, single-user. No authentication, no persistence across deploys, no multi-property support.

## Long-Term Platform Modules

The mature platform will include these modules, listed in dependency order:

### 1. Properties
Create and configure properties through the panel. Each property has: profile (name, location, contacts), knowledge base (FAQ, check-in, rules, emergencies, tips). The knowledge base feeds the AI's replies. Editing a property's knowledge immediately changes the bot's behavior for that property.

### 2. Inbox
Cross-property conversation management. All conversations from all properties in one unified inbox, filterable by property, status, and urgency. This is the primary operational view.

### 3. Reservations
Know which guests are currently staying, at which property, and when they check in/out. Initially manual entry. Later: PMS integration (Guesty, Hostaway, Beds24) and iCal sync (Airbnb, Booking.com). Reservation data enables the bot to personalize replies with guest context.

### 4. Guest Profiles
Automatically linked from reservations. When a message arrives, the system identifies: active guest, past guest, or unknown contact. No standalone contacts module needed — this emerges naturally from reservation data.

### 5. Channels
Multi-channel messaging. Telegram (current), WhatsApp (primary market need), email. All channels converge into the same inbox. The channel abstraction already exists in the codebase (BaseChannel interface).

### 6. Proactive Messaging
Two levels:
- **Operator-initiated:** Host sends a message to a guest from the panel (e.g., "your room is ready").
- **Automated:** System sends pre-configured messages at check-in minus 24h, check-in day, checkout minus 2h, etc. Requires reservation data and message templates.

### 7. Notifications
External alerts to staff when incidents occur. Telegram alerts already work. Email notifications are the next useful addition. Configurable per client: which channels, which addresses, which urgency levels.

### 8. Reporting
Operational summaries, not analytics dashboards. Useful only after enough data exists: conversations per week, bot vs human resolution rate, response times, alerts by property. A single summary line in the inbox is more valuable early than a full reporting page.

### 9. Auth and Teams
Client login, API keys, team members with roles (owner, manager, cleaner). Different permissions per role. Required for multi-client SaaS but not for single-client pilot.

## Design Principles

1. **Inbox-first.** The panel is a conversation inbox, not a dashboard.
2. **Operational clarity.** Urgent issues must be obvious immediately.
3. **Minimal cognitive load.** Understandable without training.
4. **Action-oriented.** Every important item leads to a clear action.
5. **Property context.** Every conversation belongs to a property.
6. **Ownership.** Clear who is responsible: bot, host, or staff.
7. **Implementation simplicity.** No complex frontend frameworks. HTML + CSS + vanilla JS.

## Intentionally Postponed

These features have been considered and explicitly deferred:

- **Analytics dashboards** — hosts with 2-3 properties don't need charts. They need the inbox.
- **AI fine-tuning per property** — the base model with good knowledge base context is sufficient.
- **Mobile native app** — the responsive web panel is adequate. Apps are expensive to maintain.
- **Multi-language panel UI** — the host's language is known. Hardcode one language. Translate later.
- **Facebook Messenger / Booking.com messaging** — WhatsApp covers 80%+ of the market. Other channels can wait.
- **SMS** — low value compared to WhatsApp, high per-message cost.
- **Business intelligence / marketing metrics** — this is an operations console, not an analytics product.
- **Complex role-based access control** — simple password auth first, then single-role teams, then RBAC much later.
- **Docker / containerization** — Render's native Python runtime is sufficient for the current scale.

## Key Architectural Decisions Ahead

1. **PostgreSQL migration** — required for data persistence. SQLite is ephemeral on Render.
2. **Dynamic property context loading** — currently `config.py` loads property data at startup. For multi-property, `process_message()` must load property context per conversation from the database. This is the single most important refactor.
3. **Channel contact ID generalization** — `telegram_chat_id` must become `channel_contact_id` before multi-channel support. Easier to rename early with less data.
4. **Outbound message queue** — when the host sends messages from the panel, they should go through a queue table that bot.py picks up, rather than giving the API direct channel access.
