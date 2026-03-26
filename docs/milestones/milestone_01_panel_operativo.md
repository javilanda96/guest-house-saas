# Milestone Ticket 1: Panel operativo v1 (COMPLETADA)

**Estado:** COMPLETADA
**Fecha:** 2026-03-26
**Alcance:** Limpieza operativa del panel de administración — sin rediseño, sin cambios de backend salvo los estrictamente necesarios.

---

## Cambios aplicados

### static/index.html
- Eliminado badge de `owner` de las tarjetas de conversación
- Eliminado texto `Chat {telegram_chat_id}` de las tarjetas

### static/conversation.html
- Eliminado bloque "Borrador sugerido" + botón "Copiar" de alertas inline
- Eliminada función `copyDraft()` y la variable `_draftTexts`
- Eliminado badge de `category` del bloque meta de cada mensaje
- Añadido mapa `ACTION_LABELS` con etiquetas legibles en español para las acciones internas
- Añadido `escalate_host: "Escalado"` al mapa de etiquetas
- Eliminado `${badges.join(" ")}` (flags internos `urgente`/`escalado`) del bloque meta
- Cabecera: añadida propiedad formateada (`fmtProperty`), restaurado Telegram Chat ID, eliminado Conversation ID interno
- Botón "Resolver" renombrado a "Cerrar conversación"

### static/alerts.html
- Filtro por defecto cambiado de `null` (Todas) a `"pending"` (Pendientes)
- Eliminada columna "Borrador" de la tabla
- Eliminada columna "Chat ID" de la tabla
- Propiedad ahora actúa como enlace a la conversación
- Bloque de traducción suprimido cuando el mensaje original ya está en español (`showTranslation`)

### services/database.py
- `get_conversation_interactions()`: añadido `property_id` al SELECT y al dict de retorno
- `get_alerts()`: añadido JOIN con `interactions` para exponer `user_message` (necesario para supresión de traducción)
