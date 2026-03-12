"""
Cliente de OpenAI para el chatbot.

Este módulo encapsula todas las llamadas a la API de OpenAI utilizadas
por el sistema.

Funciones principales:
- Clasificar mensajes del huésped.
- Generar respuestas automáticas del bot.
- Traducir mensajes al español para el equipo.
- Detectar idioma del huésped.
- Verificar y corregir el idioma de salida del bot.
"""
import json
import re
import time
from typing import List, Optional
from lingua import Language, LanguageDetectorBuilder

LANG_DETECTOR = LanguageDetectorBuilder.from_languages(
    Language.ENGLISH,
    Language.SPANISH,
    Language.FRENCH,
    Language.GERMAN,
    Language.ITALIAN,
    Language.PORTUGUESE,
    Language.DUTCH
).build()

_LANG_MAP = {
    Language.ENGLISH: "en",
    Language.SPANISH: "es",
    Language.FRENCH: "fr",
    Language.GERMAN: "de",
    Language.ITALIAN: "it",
    Language.PORTUGUESE: "pt",
    Language.DUTCH: "nl",
}

# Umbrales para detección de idioma con confianza
_MIN_DETECT_LENGTH = 12    # Textos más cortos son demasiado ambiguos para lingua
_MIN_CONFIDENCE = 0.65     # Confianza mínima para confiar en la detección


from config import CONTACT_NAME


MODEL_NAME = "gpt-4.1-mini"


def _retry(fn, attempts: int = 2, delay: float = 1.0):
    """Reintenta fn hasta `attempts` veces en caso de error transitorio."""
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(delay)
    raise last_err


def _safe_output_text(resp) -> str:
    return (getattr(resp, "output_text", "") or "").strip()


def _normalize_lang_code(value: str, fallback: str = "en") -> str:
    if not value:
        return fallback

    value = value.strip().lower()
    match = re.match(r"^[a-z]{2}", value)
    if match:
        return match.group(0)

    return fallback


def classify_with_ai(client, system_classifier: str, message: str) -> dict:
    """
    Clasifica el mensaje del huésped y devuelve:
    {
        "category": ...,
        "reason": ...
    }
    """
    allowed_categories = {
        "faq",
        "operational",
        "incident",
        "emergency",
        "complaint",
        "ambiguous",
        "smalltalk",
    }

    try:
        resp = _retry(lambda: client.responses.create(
            model=MODEL_NAME,
            temperature=0,
            input=[
                {"role": "system", "content": system_classifier},
                {"role": "user", "content": message},
            ],
            text={"format": {"type": "json_object"}},
        ))

        raw = _safe_output_text(resp)
        data = json.loads(raw)

        category = data.get("category")
        reason = data.get("reason", "")

        if category not in allowed_categories:
            return {
                "category": "ambiguous",
                "reason": "Invalid category returned by classifier",
            }

        # Normalización para mantener coherencia con processor.py
        if category == "smalltalk":
            return {
                "category": "faq",
                "reason": reason or "Classifier returned smalltalk; normalized to faq",
            }

        return {
            "category": category,
            "reason": reason,
        }

    except Exception:
        return {
            "category": "ambiguous",
            "reason": "Classification error (fail closed)",
        }


def generate_reply(client, history: List[dict]) -> str:
    resp = _retry(lambda: client.responses.create(
        model=MODEL_NAME,
        temperature=0.2,
        input=history,
    ))
    return _safe_output_text(resp)


def detect_language(text: str) -> str:
    """Detección simple (best-effort). Usada por funciones que no necesitan confianza."""
    try:
        lang = LANG_DETECTOR.detect_language_of(text)
        if lang is None:
            return "en"
        return _LANG_MAP.get(lang, "en")
    except Exception:
        return "en"


def _detect_confident(text: str) -> Optional[str]:
    """
    Detección con umbral de confianza.
    Devuelve None si el texto es demasiado corto o lingua no está seguro.
    Usada por ensure_reply_language para evitar traducciones erróneas.
    """
    if len(text.strip()) < _MIN_DETECT_LENGTH:
        return None
    try:
        results = LANG_DETECTOR.compute_language_confidence_values(text)
        if not results:
            return None
        top = results[0]
        if top.value < _MIN_CONFIDENCE:
            return None
        return _LANG_MAP.get(top.language)
    except Exception:
        return None


def translate_to_spanish(client, text: str) -> str:
    try:
        resp = client.responses.create(
            model=MODEL_NAME,
            temperature=0,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Traduce el texto al español de España. "
                        "Devuelve SOLO la traducción, sin explicaciones."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        out = _safe_output_text(resp)
        return out if out else "(Traducción vacía)"
    except Exception:
        return "(No se pudo traducir el mensaje)"


def translate_to_language(client, text: str, target_language: str) -> str:
    target_language = _normalize_lang_code(target_language, fallback="en")

    try:
        resp = client.responses.create(
            model=MODEL_NAME,
            temperature=0,
            input=[
                {
                    "role": "system",
                    "content": (
                        f"Translate the text into language code '{target_language}'. "
                        "Return only the translated text. "
                        "Do not explain anything."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        out = _safe_output_text(resp)
        return out if out else text
    except Exception:
        return text


def ensure_reply_language(client, user_text: str, reply_text: str) -> str:
    """
    Red de seguridad de idioma: traduce el reply solo si lingua está
    suficientemente seguro de que hay un mismatch real de idioma.

    Si la confianza es baja en cualquiera de las dos detecciones,
    no traduce — evita el caso de lingua confundiendo "wifi password"
    con italiano o "check-out" con francés.
    """
    if not reply_text:
        return reply_text

    try:
        user_lang = _detect_confident(user_text)
        if user_lang is None:
            return reply_text   # No hay confianza suficiente → no arriesgar

        reply_lang = _detect_confident(reply_text)
        if reply_lang is None:
            return reply_text   # No hay confianza suficiente → no arriesgar

        if reply_lang != user_lang:
            print(f"[LANG] Mismatch detectado: user={user_lang}, reply={reply_lang}. Traduciendo a {user_lang}.")
            return translate_to_language(client, reply_text, user_lang)

        return reply_text

    except Exception:
        return reply_text


def ack_in_user_language(client, user_text: str) -> str:
    """
    Genera un acuse corto en el idioma del huésped.
    Además, corrige idioma si el modelo contesta mal.
    """
    fallback = f"Please contact {CONTACT_NAME} directly as soon as possible."

    try:
        resp = client.responses.create(
            model=MODEL_NAME,
            temperature=0,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Write a short, natural, human message telling the guest "
                        f"to contact {CONTACT_NAME} directly as soon as possible. "
                        "Be polite, brief, and clear. "
                        "Reply in the same language as the guest message."
                    ),
                },
                {
                    "role": "user",
                    "content": user_text,
                },
            ],
        )
        out = _safe_output_text(resp)
        out = out if out else fallback
        return ensure_reply_language(client, user_text, out)
    except Exception:
        return fallback