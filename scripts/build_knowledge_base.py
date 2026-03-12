from pathlib import Path
import re

def clean_text(text: str) -> str:
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text

BASE_PATH = Path("knowledge/clients/cliente_demo/properties/Emilias_cabin")

MAP = {
    "checkin.txt": [
        "CHECK-IN/Acceso.txt",
        "CHECK-IN/CheckIn_CheckOut.txt",
        "CHECK-IN/Parking.txt",
    ],
    "house_rules.txt": [
        "CASA/ReglasCasa.txt",
        "CASA/Basuras.txt",
        "CASA/Cocina_Aseo.txt",
    ],
    "faq.txt": [
        "CASA/General.txt",
        "CASA/Wifi.txt",
    ],
    "local_tips.txt": [
        "TURISMO/RecomendacionesLocales.txt",
    ],
    "emergencies.txt": [
        "INCIDENCIAS/Emergencias.txt",
        "INCIDENCIAS/Incidentes.txt",
    ],
    "host_notes.txt": [
        "MENSAJES_HOST/Mensajes.txt",
    ],
}

KB_PATH = BASE_PATH / "knowledge_base"


def read_file(path: Path):
    if not path.exists():
        print(f"WARNING: Missing source file -> {path}")
        return ""
    return clean_text(path.read_text(encoding="utf-8"))

def build():
    KB_PATH.mkdir(exist_ok=True)

    for target, sources in MAP.items():
        content_parts = []
        included_sources = 0

        content_parts.append(
            f"KNOWLEDGE FILE: {target.upper()}\n"
            "This file contains structured information used by the AI assistant to answer guest questions.\n"
        )
        for src in sources:
            src_path = BASE_PATH / src
            text = read_file(src_path)

            if text:
                included_sources += 1
                header = f"\n\n===== SOURCE: {src_path.stem.upper()} =====\n\n"
                content_parts.append(header + text)

        output = "\n".join(content_parts).strip()
        
        if not output:
            print(f"Skipped {target} (no content)")
            continue

        out_file = KB_PATH / target
        out_file.write_text(output, encoding="utf-8")

        print(f"Generated {target} ({included_sources} sources)")


if __name__ == "__main__":
    build()