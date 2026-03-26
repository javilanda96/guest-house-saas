# Milestone 04A — Polling y scroll inteligente en conversación

**Estado:** COMPLETADO
**Archivo afectado:** `static/conversation.html`
**Cambios de backend:** ninguno

---

## Descripción general

El detalle de conversación actualiza automáticamente los mensajes cada 15 segundos sin recargar la página. Al abrir la conversación, el panel hace scroll al mensaje más reciente. En actualizaciones posteriores, el comportamiento de scroll se adapta a la posición del operador: si está al fondo, avanza automáticamente; si está leyendo mensajes anteriores, conserva su posición de lectura.

---

## Comportamiento

- Los mensajes se actualizan automáticamente cada **15 segundos**.
- Si no hay mensajes nuevos, **no se rerenderiza nada**.
- Al abrir la conversación, el panel hace **scroll automático al fondo**.
- Si llegan mensajes nuevos y el operador está cerca del fondo (< 150 px), se hace **scroll automático al mensaje más reciente**.
- Si llegan mensajes nuevos y el operador está leyendo mensajes anteriores, la **posición de lectura se conserva** tras el re-render.
- Los errores de red en el polling son **silenciosos**: no interrumpen la UI ni muestran mensajes de error.
- Las solicitudes de polling no se solapan.

---

## Implementación técnica

| Elemento | Detalle |
|---|---|
| Intervalo | 15.000 ms |
| Endpoint | `GET /api/conversations/${convId}/interactions` |
| Detección de cambio | Comparación `data.total !== _lastTotal` |
| Guard de concurrencia | `_pollConvInProgress` (boolean) |
| Estado de tracking | `_lastTotal` — número de mensajes en el último render |
| Umbral "cerca del fondo" | `scrollHeight - scrollY - innerHeight < 150` |
| Scroll inicial | `requestAnimationFrame(() => window.scrollTo({ top: scrollHeight }))` |
| Restauración de posición | `distFromBottom` capturado antes del re-render; restaurado via rAF con `behavior: "auto"` |

**Flujo del poll:**

```
pollConversation()
  └─ _pollConvInProgress? → return
  └─ _lastTotal === 0? → return (load() aún no ha terminado)
  └─ _pollConvInProgress = true
  └─ GET /api/conversations/${convId}/interactions
      └─ data.total === _lastTotal? → return (sin render)
      └─ wasNearBottom = isNearBottom()
      └─ distFromBottom = scrollHeight - scrollY
      └─ renderMessages(data.messages)
      └─ _lastTotal = data.total
      └─ wasNearBottom?
          └─ sí → scrollToBottom()
          └─ no → rAF: scrollTo(scrollHeight - distFromBottom, "auto")
  └─ finally: _pollConvInProgress = false
```

**Lógica de scroll inicial en `load()`:**

```
load()
  └─ renderHeader(data)
  └─ renderMessages(data.messages)
  └─ _lastTotal = data.total
  └─ scrollToBottom()
```

---

## Escenarios validados

- Conversación abierta: scroll automático al mensaje más reciente.
- Nuevo mensaje llega mientras el operador está al fondo → scroll automático al nuevo mensaje.
- Nuevo mensaje llega mientras el operador lee mensajes anteriores → posición de lectura conservada sin salto.
- Sin mensajes nuevos: no hay re-render ni movimiento de scroll.
- Solicitudes solapadas prevenidas por `_pollConvInProgress`.
- Error de red en el poll: UI sin cambios, polling continúa en el siguiente ciclo.

---

## Garantías

- **Sin recarga de página** en ningún escenario.
- **Sin renders innecesarios**: solo se rerenderiza cuando `data.total` cambia.
- **Sin saltos de scroll**: la restauración de posición usa `requestAnimationFrame` para ejecutarse después del reflow del DOM.
- **Sin solicitudes solapadas**: el guard `_pollConvInProgress` previene concurrencia.
- **Sin cambios de backend**: el endpoint ya existía; no se añadió ningún campo nuevo.
- **`renderMessages()` sin modificar**: el polling reutiliza la función de render existente sin alterarla.

---

## Limitaciones conocidas

- `renderMessages()` reconstruye `#content.innerHTML` completo en cada poll con cambio. Si un botón está en estado intermedio (ej. "Resolviendo...") en el momento del poll, vuelve a su estado inicial.
- El header de la conversación (estado, owner) **no se actualiza** en el poll — solo los mensajes. Los cambios de estado se reflejan únicamente al realizar una acción (Tomar, Cerrar conversación) que llama a `load()`.
- `data.total` como indicador de cambio no detecta modificaciones en mensajes existentes, solo la llegada de mensajes nuevos.
- El estado de polling **no persiste** entre navegaciones: al volver a la conversación se reinicia.
