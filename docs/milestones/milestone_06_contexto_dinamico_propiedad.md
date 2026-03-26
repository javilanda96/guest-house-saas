# Milestone 06: Contexto dinámico por propiedad

**Estado:** COMPLETADA
**Fecha:** 2026-03-26
**Archivos afectados:** `services/routing.py`, `services/database.py`, `services/processor.py`, `bot.py`
**Cambios de schema:** ninguno
**Cambios de frontend:** ninguno

---

## Problema resuelto

El bot usaba un único `PROPERTY_BASE_PATH` global, calculado al arrancar el proceso
desde las variables de entorno `CLIENT_ID` y `PROPERTY_ID`. Todas las conversaciones,
independientemente del `property_id` almacenado en la tabla `conversations`, recibían
respuestas basadas en el mismo knowledge base. El sistema era funcionalmente
single-tenant aunque la DB ya soportaba múltiples propiedades.

---

## Comportamiento tras el cambio

- Para cada mensaje entrante, `bot.py` consulta `conversations` por `telegram_chat_id`
  para obtener el `property_id` de esa conversación.
- Si existe una conversación previa, se construye el path correcto al knowledge base
  de esa propiedad y se pasa a `process_message()`.
- Si el chat es nuevo (sin conversación previa), se usa `PROPERTY_ID` de config
  como fallback — idéntico al comportamiento anterior.
- El bot responde usando la knowledge base de la propiedad correcta.

---

## Implementación técnica

### services/routing.py — helper de path

```python
def build_property_path(client_id: str, property_id: str) -> Path:
    """Devuelve el base path del knowledge base para una propiedad."""
    return Path(f"knowledge/clients/{client_id}/properties/{property_id}")
```

`PROPERTY_BASE_PATH` (global de módulo) se mantiene intacto para backward compat.

### services/database.py — query de lookup

```python
def get_property_id_for_chat(client_id: str, telegram_chat_id: int) -> Optional[str]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT property_id FROM conversations "
            "WHERE client_id = ? AND telegram_chat_id = ? LIMIT 1",
            (client_id, telegram_chat_id),
        ).fetchone()
    return row["property_id"] if row else None
```

Filtra por `client_id` para seguridad cross-tenant. Devuelve `None` para chats nuevos.

### services/processor.py — parámetro opcional

```python
def process_message(
    *,
    ...
    property_base_path=None,      # ← añadido
) -> Dict:
    ...
    knowledge_text = load_relevant_knowledge(
        property_base_path or PROPERTY_BASE_PATH, kb_key   # ← modificado
    )
```

`None` mantiene el comportamiento anterior exacto. Retrocompatible con todos los
call sites existentes y los tests.

### bot.py — resolución por chat antes del procesado

```python
_prop_id = get_property_id_for_chat(CLIENT_ID, chat_id) or PROPERTY_ID
result = process_message(
    ...
    property_base_path=build_property_path(CLIENT_ID, _prop_id),
)
```

---

## Garantías

- Single-tenant: comportamiento idéntico al anterior. `get_property_id_for_chat`
  devuelve el mismo `PROPERTY_ID` que estaba almacenado; `build_property_path` produce
  el mismo path que `PROPERTY_BASE_PATH`.
- Multi-propiedad: el knowledge base correcto se selecciona en tiempo de ejecución
  sin reinicios ni cambios de configuración.
- Fuente de verdad: filesystem (`knowledge/clients/`). La migración a DB queda
  como milestone separado.
- El caché de knowledge (`_kb_cache` en routing.py) ya usa `{base_path}:{kb_key}`
  como clave — soporta múltiples propiedades sin cambios.
- Tests existentes: 3/3 pasan sin modificaciones.

---

## Limitaciones conocidas

- La fuente de datos sigue siendo el filesystem. Cambios en el knowledge base
  requieren actualizar archivos y reiniciar el proceso (el caché no se invalida en
  tiempo de ejecución).
- Para chats nuevos se usa `PROPERTY_ID` de config como fallback. En un despliegue
  multi-propiedad real, el routing de nuevos chats requiere lógica adicional
  (fuera de scope en este milestone).
- `get_property_id_for_chat` hace una query por mensaje. Coste despreciable en MVP.
