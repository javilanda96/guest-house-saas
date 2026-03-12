"""
Procesador principal de mensajes del chatbot.

Flujo:
1. Detectar urgencia.
2. Detectar saludo simple.
3. Clasificar el mensaje con IA.
4. Decidir acción.
5. Cargar SOLO la knowledge base relevante.
6. Generar respuesta, borrador o aclaración.
"""

from typing import Dict, List, Tuple

from services.logger import log_alert, log_classification, log_reply
from services.openai_client import (
    ack_in_user_language,
    classify_with_ai,
    ensure_reply_language,
    generate_reply,
    translate_to_spanish,
)
from services.routing import (
    PROPERTY_BASE_PATH,
    choose_kb_key,
    is_greeting,
    is_urgent,
    is_yes_no,
    load_relevant_knowledge,
)


# =========================================================
# Helpers
# =========================================================

def category_to_action(category: str) -> str:
    mapping = {
        "faq": "reply_guest",
        "operational": "reply_guest",
        "incident": "reply_and_alert",
        "emergency": "alert_staff_urgent",
        "complaint": "reply_and_alert",
        "ambiguous": "ask_clarification",
    }
    return mapping.get(category, "ask_clarification")


def determine_action(category: str, urgent: bool) -> Tuple[str, bool]:
    action = "alert_staff_urgent" if urgent else category_to_action(category)
    escalate = action in {"reply_and_alert", "alert_staff_urgent"}
    return action, escalate


def get_operational_status(action: str) -> Tuple[str, str, str]:
    if action == "reply_guest":
        return "bot_resolved", "bot", "normal"
    if action == "reply_and_alert":
        return "host_pending", "host", "normal"
    if action == "alert_staff_urgent":
        return "urgent", "host", "high"
    return "open", "bot", "normal"


def trim_history(history: List[dict], max_history_messages: int) -> List[dict]:
    if not history:
        return history

    if history[0].get("role") == "system":
        system = history[:1]
        rest = history[1:]
        if len(rest) > max_history_messages:
            rest = rest[-max_history_messages:]
        return system + rest

    if len(history) > max_history_messages:
        return history[-max_history_messages:]

    return history


# =========================================================
# Handlers
# =========================================================

def handle_greeting(
    *,
    client,
    history: List[dict],
    text: str,
    max_history_messages: int,
) -> Dict:
    updated_history = list(history)
    updated_history.append({"role": "user", "content": text})
    updated_history = trim_history(updated_history, max_history_messages)

    try:
        reply = generate_reply(client, updated_history).strip()
    except Exception:
        reply = "Hello! How can I help you?"

    reply = ensure_reply_language(client, text, reply)
    log_reply(reply)

    updated_history.append({"role": "assistant", "content": reply})
    updated_history = trim_history(updated_history, max_history_messages)

    status, owner, priority = get_operational_status("reply_guest")

    return {
        "category": "faq",
        "action": "reply_guest",
        "reason": "greeting detected",
        "urgent": False,
        "escalate": False,
        "reply_text": reply,
        "ack_text": None,
        "translated_text": None,
        "draft_text": None,
        "history": updated_history,
        "status": status,
        "priority": priority,
        "owner": owner,
    }


def handle_reply_guest(
    *,
    client,
    history: List[dict],
    text: str,
    category: str,
    reason: str,
    urgent: bool,
    escalate: bool,
    max_history_messages: int,
    knowledge_text: str,
    kb_key: str,
) -> Dict:
    updated_history = list(history)
    updated_history.append({"role": "user", "content": text})
    updated_history = trim_history(updated_history, max_history_messages)

    reply_history = list(updated_history)

    knowledge_guardrail = {
        "role": "system",
        "content": (
            f"RELEVANT KNOWLEDGE CATEGORY: {kb_key}\n\n"
            "Use the following knowledge base to answer the guest.\n"
            "Only use information explicitly present in the knowledge base.\n"
            "If the exact answer is not in the knowledge base, do not invent details.\n"
            "If needed, say briefly that Ana or the host can help.\n\n"
            f"KNOWLEDGE BASE:\n{knowledge_text or '(No relevant knowledge available)'}"
        ),
    }

    language_guardrail = {
        "role": "system",
        "content": (
            "Reply entirely in the same language as the guest's last message. "
            "Ignore the language of the knowledge base if needed.\n\n"
            f"Guest message:\n{text}"
        ),
    }

    insert_at = 1 if reply_history and reply_history[0].get("role") == "system" else 0
    reply_history.insert(insert_at, knowledge_guardrail)
    reply_history.insert(insert_at + 1, language_guardrail)

    try:
        reply = generate_reply(client, reply_history).strip()
    except Exception:
        reply = ""

    if not reply:
        reply = "Lo siento, ahora mismo no puedo responder. Ana te ayudará en breve."

    reply = ensure_reply_language(client, text, reply)
    log_reply(reply)

    updated_history.append({"role": "assistant", "content": reply})
    updated_history = trim_history(updated_history, max_history_messages)

    status, owner, priority = get_operational_status("reply_guest")

    return {
        "category": category,
        "action": "reply_guest",
        "reason": reason,
        "urgent": urgent,
        "escalate": escalate,
        "reply_text": reply,
        "ack_text": None,
        "translated_text": None,
        "draft_text": None,
        "history": updated_history,
        "status": status,
        "priority": priority,
        "owner": owner,
    }


def handle_sensitive_case(
    *,
    client,
    chat_id: int,
    history: List[dict],
    text: str,
    category: str,
    action: str,
    reason: str,
    urgent: bool,
    escalate: bool,
    max_history_messages: int,
    send_ack_on_sensitive: bool,
    knowledge_text: str = "",
) -> Dict:
    updated_history = list(history)
    updated_history.append({"role": "user", "content": text})
    updated_history = trim_history(updated_history, max_history_messages)

    log_alert(chat_id=chat_id, message=text)

    draft_history = list(updated_history)
    if knowledge_text:
        kb_guardrail = {
            "role": "system",
            "content": (
                "Use the following knowledge base to draft a suggested response for the host to review.\n"
                f"KNOWLEDGE BASE:\n{knowledge_text}"
            ),
        }
        insert_at = 1 if draft_history and draft_history[0].get("role") == "system" else 0
        draft_history.insert(insert_at, kb_guardrail)

    try:
        draft = generate_reply(client, draft_history).strip()
    except Exception:
        draft = "(No se pudo generar borrador por error técnico.)"

    try:
        translated = translate_to_spanish(client, text)
    except Exception:
        translated = text

    ack_text = None
    if send_ack_on_sensitive:
        try:
            ack_text = ack_in_user_language(client, text)
            ack_text = ensure_reply_language(client, text, ack_text)
        except Exception:
            ack_text = None

    status, owner, priority = get_operational_status(action)

    return {
        "category": category,
        "action": action,
        "reason": reason,
        "urgent": urgent,
        "escalate": escalate,
        "reply_text": None,
        "ack_text": ack_text,
        "translated_text": translated,
        "draft_text": draft,
        "history": updated_history,
        "status": status,
        "priority": priority,
        "owner": owner,
    }


def handle_clarification(
    *,
    client,
    history: List[dict],
    text: str,
    category: str,
    action: str,
    reason: str,
    urgent: bool,
    escalate: bool,
    max_history_messages: int,
) -> Dict:
    updated_history = list(history)
    updated_history.append({"role": "user", "content": text})
    updated_history = trim_history(updated_history, max_history_messages)

    clarification_history = list(updated_history)

    clarification_guardrail = {
        "role": "system",
        "content": (
            "Write a very short clarification message asking the guest to give a bit more detail. "
            "If the guest's language is clear, reply in that same language. "
            "If unclear, reply in English. Keep it short and natural."
        ),
    }

    insert_at = 1 if clarification_history and clarification_history[0].get("role") == "system" else 0
    clarification_history.insert(insert_at, clarification_guardrail)

    try:
        clarification_reply = generate_reply(client, clarification_history).strip()
    except Exception:
        clarification_reply = "Could you give me a bit more detail?"

    if not clarification_reply:
        clarification_reply = "Could you give me a bit more detail?"

    clarification_reply = ensure_reply_language(client, text, clarification_reply)

    updated_history.append({"role": "assistant", "content": clarification_reply})
    updated_history = trim_history(updated_history, max_history_messages)

    status, owner, priority = get_operational_status(action)

    return {
        "category": category,
        "reason": reason,
        "action": action,
        "urgent": urgent,
        "escalate": escalate,
        "reply_text": clarification_reply,
        "ack_text": None,
        "translated_text": None,
        "draft_text": None,
        "history": updated_history,
        "status": status,
        "priority": priority,
        "owner": owner,
    }


# =========================================================
# Main
# =========================================================

def process_message(
    *,
    client,
    chat_id: int,
    system_classifier: str,
    history: List[dict],
    text: str,
    max_history_messages: int,
    send_ack_on_sensitive: bool = True,
) -> Dict:
    urgent = is_urgent(text)

    if is_greeting(text):
        return handle_greeting(
            client=client,
            history=history,
            text=text,
            max_history_messages=max_history_messages,
        )

    c = classify_with_ai(client, system_classifier, text)
    category = c["category"]
    reason = c.get("reason", "")

    if category == "ambiguous" and is_yes_no(text):
        reason = "yes/no without enough context"

    if urgent:
        category = "emergency"
        reason = f"URGENT RULE + {reason}" if reason else "URGENT RULE (keywords)"

    action, escalate = determine_action(category, urgent)
    kb_key = choose_kb_key(category, text)
    knowledge_text = load_relevant_knowledge(PROPERTY_BASE_PATH, kb_key)

    log_classification(text, category, action)

    if action == "reply_guest":
        return handle_reply_guest(
            client=client,
            history=history,
            text=text,
            category=category,
            reason=reason,
            urgent=urgent,
            escalate=escalate,
            max_history_messages=max_history_messages,
            knowledge_text=knowledge_text,
            kb_key=kb_key,
        )

    if action in {"reply_and_alert", "alert_staff_urgent"}:
        return handle_sensitive_case(
            client=client,
            chat_id=chat_id,
            history=history,
            text=text,
            category=category,
            action=action,
            reason=reason,
            urgent=urgent,
            escalate=escalate,
            max_history_messages=max_history_messages,
            send_ack_on_sensitive=send_ack_on_sensitive,
            knowledge_text=knowledge_text,
        )

    return handle_clarification(
        client=client,
        history=history,
        text=text,
        category=category,
        action=action,
        reason=reason,
        urgent=urgent,
        escalate=escalate,
        max_history_messages=max_history_messages,
    )
