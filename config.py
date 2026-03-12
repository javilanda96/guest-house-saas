"""
Configuración centralizada del chatbot.

Este módulo contiene:
- claves de API
- parámetros de comportamiento
- contexto SaaS (cliente y propiedad)
- carga de property.json
- carga de knowledge base
- prompts del sistema
"""
from services.property_manager import get_property_context
import json
import os


# =========================
# Environment / API keys
# =========================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALERT_CHAT_IDS = [
    int(x.strip())
    for x in os.environ.get("TELEGRAM_ALERT_CHAT_IDS", "").split(",")
    if x.strip().lstrip("-").isdigit()
]


# =========================
# Runtime settings
# =========================
POLL_TIMEOUT_SECONDS = 30
HTTP_TIMEOUT_SECONDS = 60
POST_LOOP_SLEEP = 0.2
SEND_ACK_ON_SENSITIVE = True
MAX_HISTORY_MESSAGES = 14
MAX_PROCESSED_KEYS = 2000


# =========================
# SaaS identifiers
# =========================
CLIENT_ID = os.environ.get("CLIENT_ID", "cliente_demo").strip()
PROPERTY_ID = os.environ.get("PROPERTY_ID", "emilias_cabin").strip()

CLIENT_NAME = "Cliente Demo"


# =========================
# Load property context
# =========================
PROPERTY_DATA = get_property_context(CLIENT_ID, PROPERTY_ID)
PROPERTY_CONFIG = PROPERTY_DATA["config"]
PROPERTY_KNOWLEDGE = PROPERTY_DATA["knowledge"]

PROPERTY_NAME = PROPERTY_CONFIG["property_name"]
CONTACT_NAME = PROPERTY_CONFIG["contact_name"]
CONTACT_PHONE = PROPERTY_CONFIG["contact_phone"]
DEFAULT_LANGUAGE = PROPERTY_CONFIG["default_language"]
PROPERTY_CITY = PROPERTY_CONFIG["city"]
PROPERTY_COUNTRY = PROPERTY_CONFIG["country"]

# =========================
# Paths
# =========================
KNOWLEDGE_DIR = f"knowledge/clients/{CLIENT_ID}/properties/{PROPERTY_ID}"
PROPERTY_CONFIG_PATH = f"{KNOWLEDGE_DIR}/property.json"

# =========================
# Context objects
# =========================
CLIENT_CONTEXT = {
    "client_id": CLIENT_ID,
    "client_name": CLIENT_NAME,
}

PROPERTY_CONTEXT = {
    "client_id": CLIENT_ID,
    "property_id": PROPERTY_ID,
    "property_name": PROPERTY_NAME,
    "contact_name": CONTACT_NAME,
    "contact_phone": CONTACT_PHONE,
    "default_language": DEFAULT_LANGUAGE,
    "city": PROPERTY_CITY,
    "country": PROPERTY_COUNTRY,
    "knowledge_dir": KNOWLEDGE_DIR,
}


# =========================
# Validation
# =========================
def validate_config() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("Falta OPENAI_API_KEY en variables de entorno.")

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en variables de entorno.")

    for prompt_file in ("system_reply.txt", "system_classifier.txt"):
        prompt_path = os.path.join(_PROMPTS_DIR, prompt_file)
        if not os.path.isfile(prompt_path):
            raise RuntimeError(f"Falta archivo de prompt: {prompt_path}")

    if not os.path.isdir(KNOWLEDGE_DIR):
        raise RuntimeError(
            f"No existe la propiedad para CLIENT_ID='{CLIENT_ID}' "
            f"y PROPERTY_ID='{PROPERTY_ID}': {KNOWLEDGE_DIR}"
        )

    if not os.path.isfile(PROPERTY_CONFIG_PATH):
        raise RuntimeError(
            f"Falta property.json en la propiedad: {PROPERTY_CONFIG_PATH}"
        )

    kb_path = os.path.join(KNOWLEDGE_DIR, "knowledge_base")

    if not os.path.isdir(kb_path):
        raise RuntimeError(
            f"No existe la carpeta knowledge_base en la propiedad: {kb_path}"
        )

    if not PROPERTY_KNOWLEDGE:
        raise RuntimeError(
            f"La knowledge_base está vacía para {CLIENT_ID}/{PROPERTY_ID}"
        )


# =========================
# Knowledge loading
# =========================
def load_apartment_info() -> str:
    parts = []

    for section_name, content in PROPERTY_KNOWLEDGE.items():
        if content:
            formatted_name = section_name.replace("_", " ").upper()
            parts.append(f"[{formatted_name}]\n{content}")

    if not parts:
        raise RuntimeError(f"No knowledge found for {CLIENT_ID}/{PROPERTY_ID}")

    return "\n\n".join(parts)


# =========================
# Prompts
# =========================
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_prompt(filename: str, **kwargs) -> str:
    path = os.path.join(_PROMPTS_DIR, filename)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return content.format(**kwargs) if kwargs else content


SYSTEM_REPLY = _load_prompt(
    "system_reply.txt",
    property_name=PROPERTY_CONTEXT["property_name"],
    city=PROPERTY_CONTEXT["city"],
    country=PROPERTY_CONTEXT["country"],
    contact_name=PROPERTY_CONTEXT["contact_name"],
    contact_phone=PROPERTY_CONTEXT["contact_phone"],
)
SYSTEM_CLASSIFIER = _load_prompt("system_classifier.txt")


# =========================
# Unified runtime context
# =========================
RUNTIME_CONTEXT = {
    "client": CLIENT_CONTEXT,
    "property": PROPERTY_CONTEXT,
    "paths": {
        "knowledge_dir": KNOWLEDGE_DIR,
        "property_config_path": PROPERTY_CONFIG_PATH,
    },
    "settings": {
        "default_language": DEFAULT_LANGUAGE,
        "max_history_messages": MAX_HISTORY_MESSAGES,
        "send_ack_on_sensitive": SEND_ACK_ON_SENSITIVE,
    },
}