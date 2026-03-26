# Milestone 05: Modelo de no-leído correcto

**Estado:** COMPLETADA
**Fecha:** 2026-03-26
**Archivo afectado:** `static/index.html`
**Cambios de backend:** ninguno

---

## Problema resuelto

El modelo anterior marcaba una conversación como «nueva» ante cualquier cambio
en el objeto completo de la conversación (comparación via `JSON.stringify`).
Esto generaba falsos positivos: un cambio de `status` (bot cierra la conversación),
un cambio de `owner` (operador toma la conversación) o la resolución de una alerta
hacían aparecer el badge «nuevo» sin que hubiera ningún mensaje sin leer.

---

## Comportamiento tras el cambio

- El badge «nuevo» aparece **únicamente** cuando `message_count` de una conversación
  es mayor que el valor registrado en el ciclo anterior.
- Los cambios de `status`, `owner` u otros metadatos **no activan** el badge.
- Una conversación nueva que aparece por primera vez en el payload se marca
  automáticamente como no leída (valor anterior `undefined` ≠ `message_count` actual).
- Al abrir una conversación, el badge desaparece exactamente igual que antes.

---

## Implementación técnica

`_prevConvMap` pasa de almacenar `JSON.stringify(c)` a almacenar solo `c.message_count`.

### load() — inicialización

```javascript
// antes
allConvs.forEach(c => _prevConvMap.set(c.id, JSON.stringify(c)));

// después
allConvs.forEach(c => _prevConvMap.set(c.id, c.message_count));
```

### pollInbox() — detección de cambio

```javascript
// antes
data.conversations.forEach(c => {
  if (JSON.stringify(c) !== _prevConvMap.get(c.id)) _unreadIds.add(c.id);
  _prevConvMap.set(c.id, JSON.stringify(c));
});

// después
data.conversations.forEach(c => {
  if (c.message_count !== _prevConvMap.get(c.id)) _unreadIds.add(c.id);
  _prevConvMap.set(c.id, c.message_count);
});
```

---

## Garantías

- Los falsos positivos por cambios de `status` u `owner` desaparecen.
- El comportamiento de `openConv()`, `renderTabs()` y `renderList()` no se ve afectado.
- El polling y el fingerprint global (`_lastFingerprint`) permanecen intactos.
- `message_count` ya estaba disponible en el payload (usado en el render de tarjetas).

---

## Limitaciones conocidas

- `message_count` incluye tanto mensajes del huésped como respuestas automáticas del bot.
  Si el bot responde mientras el operador está en otra vista, el badge puede aparecer
  aunque no haya contenido nuevo que requiera atención. Corrección exacta requeriría
  un campo `last_guest_message_at` en backend — fuera de scope en este milestone.
- El estado no-leído es en memoria: se pierde al recargar la página.
