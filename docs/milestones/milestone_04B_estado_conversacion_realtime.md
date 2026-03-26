# Milestone 04B: Estado de conversación en tiempo real

**Estado:** COMPLETADA
**Fecha:** 2026-03-26
**Archivo afectado:** `static/conversation.html`
**Cambios de backend:** ninguno

---

## Resumen

Este milestone cierra el estado en tiempo real de la vista de conversación. Cubre tres sub-features:

1. **Header refresh durante polling** — status y owner se actualizan en cada ciclo de 15 s sin recargar la página.
2. **Indicador flotante de mensajes nuevos** — aparece cuando llegan mensajes mientras el usuario está leyendo hacia arriba.
3. **Separador visual de mensajes nuevos** — marca el inicio de los mensajes recibidos durante la sesión activa.

Las sub-features 2 y 3 fueron implementadas en el commit `1468f0a` sin milestone doc propio. Este documento las formaliza junto al fix de header.

---

## Comportamiento

### Header refresh
- El header (propiedad, Telegram Chat, conteo, estado, owner) se refresca en cada ciclo de polling.
- Si otro operador toma la conversación o el bot la cierra, el cambio es visible en máximo 15 s.

### Indicador flotante
- `↓ Nuevos mensajes` aparece en la esquina inferior derecha cuando llegan mensajes y el usuario no está cerca del fondo.
- Click: desplaza al fondo y oculta el indicador.
- Se oculta automáticamente cuando el usuario hace scroll hasta cerca del fondo.

### Separador visual
- `Mensajes nuevos` se inserta antes del primer mensaje recibido en la sesión activa.
- Solo aparece cuando el usuario no estaba cerca del fondo en el momento de llegada.

---

## Implementación técnica

### Header refresh — cambio aplicado

```javascript
// pollConversation() — antes
const data = await API.get(`/api/conversations/${convId}/interactions`);
if (data.total === _lastTotal) return;

// pollConversation() — después
const data = await API.get(`/api/conversations/${convId}/interactions`);
renderHeader(data);
if (data.total === _lastTotal) return;
```

`renderHeader(data)` se invoca antes del early-return. El endpoint ya devolvía `status`, `owner`, `property_id`, `telegram_chat_id` y `total` — no fue necesario ningún cambio de backend.

### Indicador flotante
- DOM: `<div id="new-msg-indicator">` fuera de `#content`, sobrevive rerenders.
- `showIndicator()` / `hideIndicator()`: helpers de una línea.
- Activado en `pollConversation()` rama `!wasNearBottom`.
- Desactivado via `scroll` listener cuando `isNearBottom()` es verdadero.

### Separador visual
- `renderMessages(msgs, newFrom = undefined)`: parámetro opcional.
- Separador insertado en el índice `newFrom` del bucle de render.
- `newFrom = _lastTotal` capturado antes de actualizar el contador; se pasa solo si `!wasNearBottom`.

---

## Escenarios validados

- Operador externo toma la conversación → header actualiza `owner` en el siguiente ciclo
- Bot cierra conversación → header actualiza `status` sin recargar
- Mensajes nuevos con usuario al fondo → auto-scroll, sin indicador, sin separador
- Mensajes nuevos con usuario leyendo → posición preservada, indicador visible, separador insertado
- Click en indicador → scroll al fondo, indicador desaparece
- Scroll manual al fondo → indicador desaparece automáticamente
- Acciones Tomar / Cerrar → llaman `load()`, que limpia el indicador y re-renderiza el header

---

## Garantías

- El header no muestra estado obsoleto por más de 15 segundos.
- El indicador no causa reflow ni flicker.
- El separador se inserta exactamente una vez por lote de mensajes nuevos.
- El comportamiento de auto-scroll (Milestone 04A) no se ve afectado.
- No se introdujo estado adicional más allá de `_lastTotal` y `_pollConvInProgress`.

---

## Limitaciones conocidas

- El header se reescribe como `innerHTML` en cada ciclo de poll: el foco de teclado sobre los botones se pierde si coincide con el rerender. Aceptable en MVP.
- El separador refleja el último límite de mensajes nuevos, no el primero, si llegan varios lotes antes de que el usuario llegue al fondo.
- El estado del indicador es en memoria: se pierde al recargar la página.
