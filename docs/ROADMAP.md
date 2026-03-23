# Roadmap

Última actualización: 2026-03-12

## Estructura de milestones

El roadmap está organizado en fases, cada una con pequeños bloques de implementación. Cada bloque tiene un alcance claro, un resultado demostrable y límites explícitos sobre qué NO construir.

Estimaciones de tamaño:
- **Pequeño** = 1-2 archivos modificados, < 1 sesión de trabajo concentrado
- **Medio** = 3-5 archivos modificados, 1-2 sesiones
- **Grande** = 5+ archivos modificados o refactoring significativo, 2+ sesiones

---

## Fase 0: Despliegue en la nube (COMPLETADA)

Bot para una sola propiedad + bandeja de entrada operativa + despliegue en Render.

Qué se construyó:
- Bot de Telegram con clasificación IA y generación de respuestas
- Capa de persistencia SQLite (conversaciones, interacciones, alertas)
- API FastAPI con endpoints de lectura y escritura
- Panel de administración: vista de bandeja de entrada (tarjetas), timeline de conversación con alertas inline, página de alertas
- CSS responsive para móvil
- Servicio único en Render ejecutando bot + API juntos via start.sh
- Seeding de datos demo para bases de datos vacías

---

## Fase 1: Base de datos

Objetivo: Hacer el sistema suficientemente fiable para un piloto real.

### Milestone 1A: Migración a PostgreSQL

**Tamaño:** Medio
**Objetivo:** Los datos persisten entre deploys y reinicios.
**Por qué ahora:** Cada deploy en Render borra el archivo SQLite. Nada más importa hasta que los datos sobrevivan.

**Alcance:**
- Añadir `psycopg2-binary` a requirements.txt
- Modificar `services/database.py`: detectar variable de entorno `DATABASE_URL`. Si existe, usar PostgreSQL. Si no, usar SQLite como fallback (desarrollo local sin cambios).
- Ajustar sintaxis SQL: `?` a `%s` para parámetros, `AUTOINCREMENT` a `SERIAL`, `datetime('now')` a `NOW()`, booleanos `INTEGER` a `BOOLEAN` donde corresponda.
- Actualizar `seed_demo.py` para funcionar con ambos backends.
- Añadir `DATABASE_URL` a las variables de entorno de Render (Render lo proporciona al adjuntar una instancia PostgreSQL).
- Test: desplegar, enviar mensajes, redesplegar, verificar que los datos sobreviven.

**Qué NO construir:** Sin ORM. Sin Alembic. Sin framework de migraciones. 3 tablas no necesitan herramientas de migración.
**Riesgo:** Diferencias de dialecto SQL entre SQLite y PostgreSQL. Pequeño pero debe testearse.
**Resultado demostrable:** Redesplegar el servicio. Todas las conversaciones siguen en el panel.

### Milestone 1B: Autenticación del panel

**Tamaño:** Pequeño
**Objetivo:** Los datos de huéspedes no son públicamente accesibles.
**Por qué ahora:** La URL del panel es pública. Cualquiera puede leer todas las conversaciones. Es un problema legal y de confianza.

**Alcance:**
- Añadir variables de entorno `PANEL_PASSWORD` y `SECRET_KEY`.
- Crear página de login (`static/login.html`): un input de contraseña, un botón.
- Añadir middleware FastAPI: verificar cookie HTTP-only firmada en cada solicitud a `/`, `/static/*`, `/api/*`. Si falta o es inválida, redirigir al login.
- `/api/health` permanece público (health checks de Render).
- Usar el módulo `hmac` de Python para firma de cookies. Sin biblioteca de autenticación externa.

**Qué NO construir:** Sin cuentas de usuario. Sin registro. Sin email/contraseña. Sin OAuth. Sin roles. Una contraseña compartida.
**Riesgo:** La cookie debe ser HttpOnly, Secure, SameSite=Strict. Clave de firma desde variable de entorno, nunca hardcodeada.
**Resultado demostrable:** Compartir la URL de Render con alguien. Ven una página de login. La contraseña correcta da acceso.
**Dependencia:** Milestone 1A (no tiene sentido asegurar datos efímeros).

---

## Fase 2: Configuración de propiedades

Objetivo: Un anfitrión puede configurar su propiedad desde el panel en lugar de editar archivos.

### Milestone 2A: Datos de propiedad en base de datos

**Tamaño:** Medio
**Objetivo:** Configuración de propiedad y base de conocimiento almacenadas en la base de datos.
**Por qué ahora:** Esta es la base para multi-propiedad. Actualmente añadir una propiedad requiere acceso al sistema de archivos y un redespliegue.

**Alcance:**
- Nueva tabla `properties`: id, client_id, name, city, country, contact_name, contact_phone, default_language, created_at, updated_at.
- Nueva tabla `knowledge_entries`: id, property_id, topic, content, updated_at. Topics: faq, checkin, house_rules, emergencies, host_notes, local_tips.
- Helper de migración: al arrancar, si la tabla `properties` está vacía pero existe conocimiento en el sistema de archivos, auto-importar a la DB.
- Nuevo endpoint de lectura: `GET /api/properties/{id}` devuelve el perfil de la propiedad + todas las entradas de conocimiento.

**Qué NO construir:** Sin creación de propiedades desde el panel todavía. Sin UI de editor. Solo la capa de datos.
**Riesgo:** Debe coexistir con la carga desde sistema de archivos durante la transición.
**Resultado demostrable:** `GET /api/properties/1` devuelve el perfil completo de la propiedad y la base de conocimiento desde la base de datos.

### Milestone 2B: Panel editor de propiedades

**Tamaño:** Medio
**Objetivo:** El anfitrión puede editar los detalles de la propiedad y la base de conocimiento desde el panel.
**Por qué ahora:** Los datos de propiedad están en la DB (2A). El anfitrión necesita una UI para editarlos.

**Alcance:**
- Nueva página: `static/property.html` — muestra campos del perfil de propiedad (inputs editables) y secciones de conocimiento (áreas de texto editables).
- Cada sección tiene un botón de Guardar.
- Nuevos endpoints de escritura: `PATCH /api/properties/{id}` para campos de perfil, `PUT /api/properties/{id}/knowledge/{topic}` para contenido de conocimiento.
- Añadir enlace "Propiedades" a la barra de navegación.

**Qué NO construir:** Sin asistente de creación de propiedades. Sin subida de imágenes. Sin mapa. Sin etiquetas de comodidades. Solo los 6 topics de conocimiento existentes + campos de perfil.
**Riesgo:** Ninguno significativo. CRUD directo.
**Resultado demostrable:** El anfitrión abre el panel, navega a la propiedad, cambia la contraseña del wifi, hace clic en Guardar. Listo.
**Dependencia:** Milestone 2A.

### Milestone 2C: El bot lee el contexto de propiedad desde la base de datos

**Tamaño:** Grande (este es el refactor clave)
**Objetivo:** `process_message()` carga el contexto de propiedad dinámicamente por conversación, no desde variables globales de inicio.
**Por qué ahora:** Este es el muro entre "un bot por propiedad" y "un bot sirviendo muchas propiedades". Debe hacerse antes de que multi-propiedad entre en producción.

**Alcance:**
- Nueva función en `services/property_manager.py`: `get_property_context_from_db(property_id)` que lee de las tablas `properties` y `knowledge_entries`.
- Modificar `services/processor.py`: `process_message()` acepta el contexto de propiedad como parámetro en lugar de leer variables globales de configuración.
- Modificar `bot.py`: antes de llamar a `process_message()`, buscar el contexto de propiedad en la DB usando el `property_id` de la conversación.
- El prompt del sistema se construye con plantilla por solicitud con el contexto de la propiedad, no una vez al arrancar.
- La carga desde sistema de archivos permanece como fallback cuando `DATABASE_URL` no está definido.

**Qué NO construir:** Sin enrutamiento multi-bot todavía. El bot sigue sirviendo una sola propiedad por instancia. Pero el pipeline de procesamiento ya no asume una sola propiedad.
**Riesgo:** Esto toca el pipeline central de procesamiento. Se requieren tests exhaustivos. Los tests de clasificación (22 casos) deben seguir pasando.
**Resultado demostrable:** Editar el FAQ de una propiedad en el panel. Enviar un mensaje de huésped sobre ese tema. El bot usa el conocimiento actualizado en su respuesta. Sin redespliegue.
**Dependencia:** Milestone 2A, 2B.

---

## Fase 3: Listo para piloto

Objetivo: El sistema funciona de forma fiable para un anfitrión real con 1-3 propiedades.

### Milestone 3A: Monitorización del bot

**Tamaño:** Pequeño
**Objetivo:** Detectar y recuperar automáticamente cuando bot.py se cae silenciosamente.
**Por qué ahora:** El bot se ejecuta en segundo plano. Si se cae, nadie lo sabe hasta que los huéspedes dejan de recibir respuestas.

**Alcance:**
- bot.py escribe un timestamp `last_bot_poll` en la base de datos en cada ciclo de polling.
- `/api/health` comprueba este timestamp. Si es más antiguo de 90 segundos, devuelve estado no saludable.
- El health check integrado de Render reinicia el servicio cuando está no saludable.

**Qué NO construir:** Sin gestor de procesos complejo. Sin supervisor. Solo una comprobación de timestamp.
**Riesgo:** Mínimo. Una escritura por ciclo de polling, una lectura por health check.
**Resultado demostrable:** Matar bot.py manualmente. En 90 segundos, Render reinicia el servicio. El bot se reanuda.

### Milestone 3B: Reservas manuales

**Tamaño:** Medio
**Objetivo:** El anfitrión puede registrar reservas de huéspedes. El bot sabe quién se hospeda y cuándo.
**Por qué ahora:** Esto transforma el bot de "asistente genérico" a "conserje consciente del huésped".

**Alcance:**
- Nueva tabla `reservations`: id, property_id, guest_name, guest_contact, channel, channel_contact_id, check_in, check_out, status (confirmed, checked_in, checked_out), notes, created_at.
- Nueva página del panel: `static/reservations.html` — tabla con formularios de añadir/editar. Inputs de fecha, sin widget de calendario.
- Nuevos endpoints: `GET /api/reservations`, `POST /api/reservations`, `PATCH /api/reservations/{id}`.
- bot.py: antes de procesar, buscar la reserva activa para el chat_id. Si existe, incluir nombre del huésped y fechas de estancia en el prompt del sistema.

**Qué NO construir:** Sin integración con PMS. Sin sincronización iCal. Sin UI de calendario. Solo entrada manual.
**Riesgo:** Vincular el chat_id a la reserva requiere que el anfitrión introduzca el contacto de Telegram del huésped al crear la reserva. Este es un punto de fricción en la UX a monitorizar.
**Resultado demostrable:** El anfitrión crea una reserva para "Juan, check-in el 15 de marzo". Juan envía un mensaje de Telegram. La respuesta del bot hace referencia a su nombre y fechas de estancia.
**Dependencia:** Milestone 2C (el bot debe cargar el contexto de propiedad dinámicamente).

### Milestone 3C: Mensajes iniciados por el operador

**Tamaño:** Medio
**Objetivo:** El anfitrión puede responder a un huésped directamente desde el panel.
**Por qué ahora:** Cuando el bot escala, el anfitrión actualmente no tiene forma de responder desde el panel. Tiene que abrir Telegram por separado.

**Alcance:**
- Nueva tabla: `outbound_messages` — id, conversation_id, message_text, status (pending, sent, failed), created_at, sent_at.
- Página de detalle de conversación: añadir un input de texto + botón Enviar debajo del timeline.
- Nuevo endpoint: `POST /api/conversations/{id}/send` — escribe en outbound_messages.
- bot.py: en cada ciclo de polling, comprobar mensajes salientes pendientes. Enviar via canal. Marcar como enviado.

**Qué NO construir:** Sin entrega en tiempo real. Sin confirmaciones de lectura. Sin indicadores de escritura. El mensaje aparece en el panel después del siguiente ciclo de polling del bot (hasta 30 segundos).
**Riesgo:** La API no accede directamente al canal de Telegram. Los mensajes pasan por la cola de salida. Esto es intencional — mantiene la API y el bot limpiamente separados.
**Resultado demostrable:** El anfitrión abre una conversación en el panel, escribe una respuesta, hace clic en Enviar. El huésped la recibe en Telegram en 30 segundos.
**Dependencia:** Milestone 2C.

### Milestone 3D: Alertas por email

**Tamaño:** Pequeño
**Objetivo:** El anfitrión recibe notificación por email cuando ocurren incidencias urgentes.
**Por qué ahora:** Las alertas de Telegram al equipo ya funcionan. El email es universal — todos los anfitriones tienen email.

**Alcance:**
- Nueva variable de entorno: `ALERT_EMAIL`.
- Nuevo archivo: `services/notifications.py` con `send_email_alert(subject, body)` usando SMTP o un servicio gratuito (SendGrid gratuito: 100 emails/día).
- En `services/database.py`: después de crear una alerta con `urgent=True`, llamar a `send_email_alert()`.

**Qué NO construir:** Sin plantillas de email. Sin email HTML. Solo texto plano. Sin reglas de alerta configurables.
**Riesgo:** SMTP puede ser lento o bloqueado. Enviar en un hilo o de forma fire-and-forget para no bloquear el bot.
**Resultado demostrable:** El huésped envía un mensaje urgente. El anfitrión recibe notificación por email en segundos.
**Dependencia:** Milestone 1A (se necesita DB persistente para evitar alertas duplicadas al reiniciar).

---

## Fase 4: SaaS multi-propiedad

Objetivo: Una cuenta gestiona múltiples propiedades desde un único panel.

### Milestone 4A: Bandeja de entrada multi-propiedad

**Tamaño:** Medio
**Objetivo:** La bandeja de entrada muestra conversaciones de todas las propiedades, filtrable por propiedad.

**Alcance:**
- Dropdown de filtro de propiedad en la bandeja de entrada.
- API: `GET /api/conversations` acepta parámetro de query opcional `property_id`.
- API: `GET /api/properties` devuelve lista de todas las propiedades del cliente.
- Navegación del panel: añadir sección Propiedades.

**Dependencia:** Milestone 2B (el editor de propiedades existe).

### Milestone 4B: Enrutamiento multi-token del bot

**Tamaño:** Grande
**Objetivo:** Una instancia del bot hace polling de múltiples tokens de Telegram (uno por propiedad).

**Alcance:**
- Almacenar el token del bot de Telegram por propiedad en la tabla `properties`.
- bot.py: al arrancar, cargar todas las propiedades con tokens. Hacer polling de cada una en round-robin.
- Cada token se mapea a una propiedad. Cuando llega un mensaje en el token X, enrutar a la propiedad X.
- Manejo de errores por token (un token expirado no tumba todos).

**Riesgo:** El cambio más complejo del roadmap. Cada token tiene su propio update offset. El rate limiting debe ser por token. Se requieren tests exhaustivos.
**Dependencia:** Milestone 2C, 3A.

### Milestone 4C: Creación de propiedades desde el panel

**Tamaño:** Pequeño
**Objetivo:** El anfitrión puede añadir una nueva propiedad completamente desde el panel.

**Alcance:**
- Botón "Añadir propiedad" en la página de propiedades.
- Crea una fila en la DB con entradas de conocimiento vacías.
- El anfitrión rellena el perfil y el conocimiento mediante el editor existente (Milestone 2B).

**Dependencia:** Milestone 2B, 4A.

---

## Fase 5: Expansión de canales

Objetivo: Los huéspedes se comunican via WhatsApp.

### Milestone 5A: Generalizar el contact ID de canal

**Tamaño:** Medio (migración)
**Objetivo:** La base de datos soporta múltiples tipos de canal, no solo Telegram.

**Alcance:**
- Renombrar `telegram_chat_id` a `channel_contact_id` en todas las tablas.
- Añadir columna `channel` a `conversations` (telegram, whatsapp, email).
- Actualizar todas las consultas, respuestas de la API y referencias del panel.

**Nota:** Este renombrado es más fácil de hacer pronto (menos datos). Considerar hacerlo durante la Fase 2 o 3 para reducir el dolor de migración futuro.

### Milestone 5B: Receptor de webhooks

**Tamaño:** Medio
**Objetivo:** La API puede recibir mensajes entrantes de canales basados en webhooks.

**Alcance:**
- Nuevo endpoint: `POST /api/webhooks/{channel}` — recibe mensajes de WhatsApp, etc.
- Extraer `process_message()` en un servicio compartido llamable tanto desde bot.py (polling) como desde api.py (webhook).
- Este es el refactor que unifica los canales de polling y push.

**Dependencia:** Milestone 5A, 2C.

### Milestone 5C: Integración con WhatsApp

**Tamaño:** Grande
**Objetivo:** Los huéspedes se comunican via WhatsApp. El bot responde. El anfitrión lo ve en la bandeja de entrada.

**Alcance:**
- Implementar `channels/whatsapp.py` extendiendo BaseChannel.
- Integración con la API de WhatsApp Business (Meta Cloud API).
- Aprobación de mensajes plantilla para mensajería proactiva.
- Icono de canal en las tarjetas de la bandeja de entrada.

**Dependencia:** Milestone 5A, 5B. También requiere aprobación de Meta Business API (dependencia externa, semanas de tiempo de espera).

---

## Refactors inevitables

| Refactor | Cuándo | Por qué |
|----------|------|-----|
| Carga dinámica de propiedad en `config.py` | Fase 2 (Milestone 2C) | Sin esto, un bot = una propiedad para siempre |
| `telegram_chat_id` → `channel_contact_id` | Fase 2-3 (o Fase 5A) | Se complica con más datos. Hacerlo antes del piloto si es posible. |
| `process_message()` llamable desde la API | Fase 5 (Milestone 5B) | Los canales webhook necesitan que la API procese mensajes |
| Bucle de polling del bot con soporte multi-token | Fase 4 (Milestone 4B) | Multi-propiedad requiere polling multi-token |

## Funcionalidades explícitamente consideradas prematuras

| Funcionalidad | Por qué es prematura | Cuándo se vuelve relevante |
|---------|---------------|------------------------|
| Integración PMS/iCal | Cada PMS tiene una API diferente. La entrada manual valida el concepto primero. | Tras validar las reservas manuales con un anfitrión real. |
| Mensajes programados automatizados | Requiere reservas + plantillas + scheduler. | Tras implementar la mensajería iniciada por el operador. |
| Dashboard de analítica | Los anfitriones con 3 propiedades no necesitan gráficos. | Al gestionar 10+ propiedades. |
| Fine-tuning de IA por propiedad | El modelo base con buen contexto de KB es suficiente. | Cuando la calidad de las respuestas se convierte en un problema competitivo. |
| Panel UI multiidioma | El idioma del anfitrión es conocido. Hardcodear uno. | Al vender a mercados no hispanohablantes. |
| App móvil nativa | El panel web responsive es adecuado. | Cuando el uso móvil justifique el coste de mantenimiento. |
| RBAC complejo | Primero autenticación simple con contraseña. | Cuando varios miembros del equipo necesiten niveles de acceso diferentes. |
| Docker/contenedorización | El runtime Python nativo de Render funciona. | Cuando la complejidad del despliegue lo requiera. |
| Framework de migraciones (Alembic) | 3 tablas no necesitan herramientas de migración. | Cuando el esquema tenga 15+ tablas. |
| Facebook Messenger / Booking.com | WhatsApp cubre más del 80% del mercado. | Tras validar la integración con WhatsApp. |

## Grafo de dependencias

```
Fase 0 (COMPLETADA)
    |
    v
1A: PostgreSQL ─────────────────────────────────┐
    |                                            |
    v                                            |
1B: Autenticación ───────────────┐               |
    |                            |               |
    v                            v               v
2A: Datos de propiedad en DB    3D: Alertas email    3A: Salud del bot
    |
    v
2B: Editor de propiedades
    |
    v
2C: Contexto dinámico de propiedad (REFACTOR CLAVE)
    |
    ├──────────────────┐
    v                  v
3B: Reservas    3C: Mensajes del operador
    |                  |
    v                  v
4A: Bandeja de entrada multi-propiedad
    |
    v
4B: Bot multi-token
    |
    v
4C: Creación de propiedades
    |
    v
5A: Channel Contact ID (puede hacerse antes)
    |
    v
5B: Receptor de webhooks
    |
    v
5C: WhatsApp
```

## Próxima acción concreta

**Milestone 1A: Migración a PostgreSQL.** Todo lo demás está bloqueado por los datos efímeros.
