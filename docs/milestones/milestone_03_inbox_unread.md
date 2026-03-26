# Milestone 03 — Estado no-leído en el inbox

**Estado:** COMPLETADO
**Archivo afectado:** `static/index.html`
**Cambios de backend:** ninguno

---

## Descripción general

El inbox muestra qué conversaciones han tenido actividad nueva desde la última vez que el operador las abrió. Los contadores por tab reflejan el número de conversaciones no-leídas en tiempo real. El estado se mantiene en memoria durante la sesión.

---

## Comportamiento

- Una conversación se marca como **no-leída** cuando su contenido cambia entre ciclos de polling.
- Las conversaciones no-leídas muestran un **borde verde** en la carta del inbox.
- Cada tab muestra un badge secundario con el conteo de no-leídos **solo si es > 0**.
- Al hacer click en una carta, la conversación se marca como **leída antes de navegar**.
- Al volver al inbox, el estado no-leído actualizado ya está reflejado.
- Los filtros de tab y la búsqueda **preservan el estado no-leído** sin resetearlo.
- La carga inicial **no marca nada como no-leído**: solo el polling posterior lo hace.

---

## Implementación técnica

**Estrategia:** diff per-conversación sobre el fingerprint existente del ciclo de polling.

| Elemento | Detalle |
|---|---|
| `_unreadIds` | `Set` de IDs de conversaciones con actividad nueva; persiste hasta click del operador |
| `_prevConvMap` | `Map<id, JSON.stringify(conv)>` para detectar cambios por conversación |
| Trigger de no-leído | Solo `pollInbox()` cuando el fingerprint global cambia |
| Estrategia de diff | `JSON.stringify(conv) !== _prevConvMap.get(conv.id)` — mismo mecanismo que el fingerprint global |
| Marca visual | Clase CSS `.inbox-card-unread` → `border-left: 3px solid #4caf50` |
| Contadores por tab | Calculados en `renderTabs()` filtrando `allConvs` contra `_unreadIds` |
| Marcar como leído | `openConv(id)`: `_unreadIds.delete(id)` → `renderTabs()` → `location.href` |

**Flujo de detección en poll:**

```
pollInbox()
  └─ fp !== _lastFingerprint (cambio global detectado)
  └─ data.conversations.forEach(c):
      └─ JSON.stringify(c) !== _prevConvMap.get(c.id)? → _unreadIds.add(c.id)
      └─ _prevConvMap.set(c.id, JSON.stringify(c))
  └─ allConvs = data.conversations
  └─ sortConversations() → renderTabs() → renderList()
```

**Flujo de marcar como leído:**

```
openConv(id)
  └─ _unreadIds.delete(id)
  └─ renderTabs()   ← actualiza contadores inmediatamente
  └─ location.href → /static/conversation.html?id=...
```

---

## Escenarios validados

- Conversación existente recibe mensaje nuevo → carta marcada con borde verde; contador del tab incrementa.
- Conversación nueva aparece en el inbox → marcada como no-leída.
- Contadores por tab aumentan correctamente al detectar cambios.
- Marcador visual (borde) aparece en la carta correspondiente.
- Click en carta: borde desaparece, contador del tab decrece, navegación idéntica a antes.
- Vuelta al inbox: estado no-leído actualizado sin recarga de página.
- Búsqueda activa: las cartas no-leídas mantienen su clase durante el filtrado.
- Cambio de tab: los contadores se recalculan correctamente por tab.
- Polling continúa sin parpadeo ni duplicados.

---

## Garantías

- **Sin cambios de backend**: el endpoint `/api/conversations` no fue modificado.
- **Sin regresión en polling**: la detección de no-leídos se inserta en el bloque ya existente de cambio de fingerprint global; si el fingerprint no cambia, no se ejecuta ningún diff.
- **Sin renders adicionales**: `renderTabs()` y `renderList()` ya se llamaban en cada poll con cambio.
- **Sin estado transitorio**: no hay timers, `setTimeout`, ni clases temporales. El estado es binario: leído o no-leído.
- **Navegación idéntica**: `openConv(id)` reemplaza el `onclick` inline; el destino y el comportamiento de navegación son los mismos.

---

## Limitaciones conocidas

- El estado no-leído **no persiste entre recargas de página** (in-memory only).
- Si el operador navega directamente a `conversation.html` por URL (sin pasar por `openConv`), el ID permanece en `_unreadIds` hasta que el siguiente poll modifique esa conversación.
- `openConv()` llama a `renderTabs()` antes de navegar, lo que produce un render extra imperceptible del DOM de tabs en cada click.
- No existe estado visual explícito de "leído" (e.g. color grisado). Las cartas leídas simplemente no tienen el borde verde.
