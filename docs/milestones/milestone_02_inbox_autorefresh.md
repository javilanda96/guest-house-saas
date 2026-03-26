# Milestone 02 — Auto-refresco del inbox (Polling)

**Estado:** COMPLETADO
**Archivo afectado:** `static/index.html`
**Cambios de backend:** ninguno

---

## Descripción general

El inbox del panel de administración actualiza automáticamente la lista de conversaciones cada 15 segundos sin recargar la página. El operador siempre ve el estado real sin intervención manual.

---

## Comportamiento

- La lista de conversaciones se refresca cada **15 segundos**.
- Si no hay cambios en el payload, **no se rerenderiza nada** (sin parpadeo).
- Si hay cambios, se actualizan las tabs, el conteo de cada tab y la lista completa.
- El tab activo **se conserva** entre refrescos.
- El valor del campo de búsqueda **se conserva** entre refrescos.
- Las conversaciones no se duplican.
- Los errores de red en el polling son **silenciosos**: no interrumpen la UI ni muestran mensajes de error.

---

## Implementación técnica

**Estrategia:** polling via `setInterval` reutilizando el pipeline de render existente.

| Elemento | Detalle |
|---|---|
| Intervalo | 15.000 ms |
| Endpoint | `GET /api/conversations?limit=200` |
| Guarda de concurrencia | `_pollInProgress` (boolean de módulo) — evita solicitudes solapadas |
| Fingerprint | `JSON.stringify(data.conversations)` comparado contra `_lastFingerprint` |
| Pipeline de render | `sortConversations() → renderTabs() → renderList()` (sin cambios) |
| DOM update | Reconstrucción completa del contenido de `#content` solo si el fingerprint cambia |
| Errores | `catch(_)` silencioso con `finally` garantizando reset de `_pollInProgress` |

**Flujo del poll:**

```
pollInbox()
  └─ _pollInProgress? → return
  └─ _pollInProgress = true
  └─ GET /api/conversations?limit=200
      └─ fp = JSON.stringify(data.conversations)
      └─ fp === _lastFingerprint? → return (sin render)
      └─ _lastFingerprint = fp
      └─ allConvs = data.conversations
      └─ sortConversations() → renderTabs() → renderList()
  └─ finally: _pollInProgress = false
```

---

## Escenarios validados

- Inbox carga correctamente en el arranque.
- Polling se activa y ejecuta cada 15 s.
- Sin cambios: no hay parpadeo visual ni render innecesario.
- Nuevo mensaje entrante: la conversación aparece o actualiza su posición.
- Cambio de estado (e.g. `bot_resolved` → `host_pending`): la conversación cambia de tab automáticamente.
- El orden (recencia + estado) se recalcula correctamente.
- El campo de búsqueda activo no se resetea.
- El tab activo no cambia.
- No aparecen conversaciones duplicadas.
- Un error de red puntual no rompe la UI.

---

## Garantías

- **Sin recarga de página** en ningún escenario.
- **Sin append incremental** al DOM: el render siempre parte de `allConvs` completo.
- **Sin requests solapados**: la guarda `_pollInProgress` lo previene.
- **Sin renders innecesarios**: el fingerprint evita trabajo cuando el payload no cambia.
- **Sin cambios de backend**: el endpoint `/api/conversations` ya existía.

---

## Limitaciones conocidas

- El polling consume una request por intervalo incluso en sesiones inactivas. No hay pausa automática por inactividad del usuario.
- El fingerprint compara el JSON completo serializado. Si el backend devuelve campos con orden variable, podría generar falsos positivos (renders innecesarios). No se ha observado este comportamiento con el backend actual.
- El intervalo de 15 s es fijo. No hay backoff ni ajuste dinámico.
- Alertas y detalle de conversación no tienen auto-refresco (fuera de scope de este milestone).
