from pathlib import Path
import json


BASE_PATH = Path("knowledge/clients")


def load_property(client_id: str, property_id: str) -> dict:
    """
    Carga la configuración de una propiedad desde property.json
    """

    property_path = BASE_PATH / client_id / "properties" / property_id
    config_path = property_path / "property.json"

    if not config_path.exists():
        raise FileNotFoundError(f"property.json not found for {client_id}/{property_id}")

    with open(config_path, "r", encoding="utf-8") as f:
        property_config = json.load(f)

    return property_config

def load_knowledge_base(client_id: str, property_id: str) -> dict:
    """
    Carga todos los archivos de knowledge_base de una propiedad
    y devuelve un diccionario con su contenido.
    """

    property_path = BASE_PATH / client_id / "properties" / property_id
    kb_path = property_path / "knowledge_base"

    knowledge = {}

    if not kb_path.exists():
        return knowledge

    for file in kb_path.glob("*.txt"):
        key = file.stem
        content = file.read_text(encoding="utf-8").strip()
        knowledge[key] = content

    return knowledge

def get_property_context(client_id: str, property_id: str) -> dict:
    """
    Devuelve toda la información relevante de una propiedad:
    configuración + knowledge base
    """
    property_config = load_property(client_id, property_id)
    knowledge = load_knowledge_base(client_id, property_id)

    return {
        "config": property_config,
        "knowledge": knowledge,
    }