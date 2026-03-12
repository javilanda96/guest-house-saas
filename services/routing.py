"""
Constantes de enrutamiento y helpers de detección para el procesador de mensajes.

Contiene:
- Palabras clave de urgencia y hints por categoría
- Listas de afirmativos/negativos y saludos
- Mapa de KB files y caché
- Funciones de carga de knowledge base
- Funciones de detección: is_urgent, is_yes_no, is_greeting
- Función de selección de KB: choose_kb_key
"""

from pathlib import Path
from typing import Dict

from config import CLIENT_ID, PROPERTY_ID

# =========================================================
# Paths
# =========================================================

PROPERTY_BASE_PATH = Path(f"knowledge/clients/{CLIENT_ID}/properties/{PROPERTY_ID}")

# =========================================================
# Keyword lists
# =========================================================

URGENT_KEYWORDS = [
    "fire",
    "gas leak",
    "carbon monoxide",
    "explosion",
    "ambulance",
    "police",
    "unconscious",
    "bleeding",
    "water leak",
    "flood",
    "electric shock",
    "sparks",
    "short circuit",
    "incendio",
    "fuga de gas",
    "monóxido",
    "explosión",
    "ambulancia",
    "policía",
    "inconsciente",
    "sangrando",
    "fuga de agua",
    "inundación",
    "chispa",
    "cortocircuito",
]

CHECKIN_HINTS = [
    "check in", "check-in", "checkin",
    "check out", "check-out", "checkout",
    "acceso", "entrar", "entrada", "llave", "keys", "key",
    "parking", "aparcamiento", "park",
]

RULES_HINTS = [
    "normas", "rules", "smoke", "fumar", "mascota", "pet", "party", "fiesta",
    "guests", "huéspedes", "noise", "ruido",
    "dog", "dogs", "cat", "cats", "perro", "perros", "gato", "gatos", "animal", "animals",
]

LOCAL_TIPS_HINTS = [
    "restaurant", "restaurants", "restaurante", "restaurantes",
    "eat", "comer",
    "supermarket", "supermercado",
    "beach", "playa",
    "golf",
    "walk", "pasear", "park", "parque",
]

AFFIRMATIVE = {
    "sí", "si", "sii", "vale", "ok", "okay", "yes", "yep", "ya", "claro", "perfecto", "de acuerdo"
}
NEGATIVE = {"no", "nope", "nah"}

GREETING_HINTS = {
    "hi", "hello", "hola", "hey",
    "good morning", "good afternoon", "good evening",
}

# =========================================================
# KB routing
# =========================================================

KB_FILES = {
    "faq": "knowledge_base/faq.txt",
    "checkin": "knowledge_base/checkin.txt",
    "house_rules": "knowledge_base/house_rules.txt",
    "local_tips": "knowledge_base/local_tips.txt",
    "emergencies": "knowledge_base/emergencies.txt",
    "host_notes": "knowledge_base/host_notes.txt",
}

_kb_cache: Dict[str, str] = {}


def load_relevant_knowledge(base_path: Path, kb_key: str) -> str:
    cache_key = f"{base_path}:{kb_key}"
    if cache_key in _kb_cache:
        return _kb_cache[cache_key]

    kb_relative_path = KB_FILES.get(kb_key)
    if not kb_relative_path:
        return ""

    kb_path = base_path / kb_relative_path
    if not kb_path.exists():
        return ""

    content = kb_path.read_text(encoding="utf-8").strip()
    _kb_cache[cache_key] = content
    return content


def choose_kb_key(category: str, text: str) -> str:
    t = (text or "").lower()

    if category in {"incident", "emergency", "complaint"}:
        return "emergencies"

    if "smoke" in t or "fumar" in t:
        return "house_rules"

    if any(h in t for h in RULES_HINTS):
        return "house_rules"

    if any(h in t for h in LOCAL_TIPS_HINTS):
        return "local_tips"

    if any(h in t for h in CHECKIN_HINTS):
        return "checkin"

    if category == "ambiguous":
        return "faq"

    if category == "operational":
        return "checkin"

    return "faq"


# =========================================================
# Detection helpers
# =========================================================

def is_urgent(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in URGENT_KEYWORDS)


def is_yes_no(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in AFFIRMATIVE or t in NEGATIVE


def is_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in GREETING_HINTS
