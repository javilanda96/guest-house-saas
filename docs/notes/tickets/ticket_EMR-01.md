# EMR-01 — fix: respuesta al huésped insuficiente en emergencias reales

**Estado:** IMPLEMENTADO — pendiente re-test en producción
**Prioridad:** Bloqueante (4A Pilot Readiness)
**Milestone:** 4A — Pilot Readiness (1 property)
**Fecha:** 2026-03-23

---

## Contexto

Durante la ejecución manual de la test matrix de Milestone 4A se detectó un fallo bloqueante en el manejo de emergencias reales. El escalado interno y las alertas al encargado funcionan correctamente, pero la respuesta enviada al huésped es operativamente insuficiente.

---

## Caso de prueba

**Guest message:**
> "There is smoke in the kitchen and I think something is burning."

---

## Comportamiento actual

| Campo | Valor |
|-------|-------|
| category | `emergency` |
| action | `alert_staff_urgent` |
| Alerta al encargado | ✅ correcta |
| Conversación en panel | ✅ registrada |
| Respuesta al huésped | ❌ `"Please contact Ana directly as soon as possible to address the situation. Thank you!"` |

---

## Problema

Para un caso de humo / posible incendio, derivar al huésped únicamente a Ana es **operativamente incorrecto**. En una emergencia real, el bot debe priorizar instrucciones de seguridad inmediata — evacuación, llamada a emergencias — antes de mencionar al contacto humano.

La respuesta actual no causa ningún daño a la lógica interna (escalado, panel, persistencia funcionan), pero es un **riesgo operativo alto** si el sistema se usa en producción.

---

## Impacto

- Bloqueante para 4A: no se puede dar GO al piloto mientras EMR-01 esté en FAIL
- Riesgo reputacional y de seguridad en uso real con huéspedes
- El resto de la test matrix 4A ya ha pasado (FAQ-01, INC-01, COM-01, HOF-Resolve)

---

## Objetivo

Corregir la respuesta saliente al huésped para `category=emergency` / `action=alert_staff_urgent` de forma que:

1. Priorice seguridad inmediata (evacuar, llamar a emergencias si aplica)
2. Sea breve, clara y sin ambigüedad
3. Mencione a Ana como contacto adicional, no como sustituto de emergencias
4. No cambie el escalado interno, el alert text al encargado, ni el panel

---

## Respuesta esperada (ejemplo aceptable)

> "If there is smoke or something may be burning, leave the area immediately and call emergency services now if there is any immediate danger. Then contact Ana as soon as possible."

---

## Localización probable del bug

La respuesta al huésped en casos `alert_staff_urgent` viene del campo `ack_text`, generado en `handle_sensitive_case()` en `services/processor.py` mediante `ack_in_user_language()` (en `services/openai_client.py`). El problema es que el prompt de ack no diferencia entre urgencia real (emergency) y alertas estándar (complaint/incident) — genera siempre un ack genérico de derivación al host, sin instrucciones de seguridad.

**Archivos probables a tocar:**
- `services/openai_client.py` — función `ack_in_user_language()`
- `services/processor.py` — `handle_sensitive_case()`, para separar el ack según `action`
- `prompts/` — si el ack se genera desde un prompt externo

---

## Alcance del fix

- Cambio mínimo y quirúrgico
- No refactorizar el flujo completo
- No tocar: escalado al encargado, alert text interno, persistencia, panel, heartbeat
- Solo corregir el texto saliente al huésped para `action=alert_staff_urgent`

---

## Tareas

1. [x] Localizar dónde se genera `ack_text` para `alert_staff_urgent`
2. [x] Identificar por qué no incluye instrucciones de seguridad
3. [x] Aplicar parche mínimo (prompt o lógica condicional según `action` o `urgent`)
4. [x] Verificar que el alert al encargado sigue intacto
5. [ ] Re-test manual del caso EMR-01
6. [ ] Cerrar ticket y actualizar estado de 4A

---

## Criterio de aceptación

Re-test de:
> "There is smoke in the kitchen and I think something is burning."

- [ ] Alerta al encargado sigue llegando correctamente
- [ ] Panel registra la conversación con status `urgent`
- [ ] El huésped recibe una respuesta de seguridad inmediata adecuada (instrucción + emergencias + Ana)
- [ ] EMR-01 pasa a **PASS**

---

## Estado de la test matrix 4A

| Test | Estado |
|------|--------|
| FAQ-01 | ✅ PASS |
| INC-01 | ✅ PASS |
| COM-01 | ✅ PASS |
| EMR-01 | ❌ FAIL — este ticket |
| HOF-Resolve | ✅ PASS |
| HOF-Tomar | ⏳ pendiente de validar |
