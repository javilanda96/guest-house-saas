# Visión del producto

Última actualización: 2026-03-12

## Qué es esto

Una plataforma de mensajería con IA para operadores de alojamientos turísticos. El sistema gestiona automáticamente las comunicaciones con huéspedes (preguntas, solicitudes, incidencias) a través de canales de mensajería, escala situaciones sensibles al anfitrión y proporciona un panel operativo para monitorización e intervención.

## Para quién es

- Anfitriones de Airbnb que gestionan entre 1 y 10 propiedades
- Pequeños gestores de propiedades
- Operadores de hospitalidad que quieren automatizar la comunicación con huéspedes sin perder el control

Estos usuarios se preocupan por: problemas de huéspedes, incidencias en propiedades, conversaciones sin resolver, situaciones urgentes y qué requiere atención humana. No les interesan las métricas técnicas ni los internals del sistema.

## Concepto central del producto

Una **bandeja de entrada operativa** — no un dashboard, no una herramienta de analítica. El anfitrión abre el panel, ve inmediatamente qué necesita atención, inspecciona conversaciones, resuelve incidencias e interviene cuando la IA no puede gestionar algo. El objetivo es tener visibilidad situacional en menos de 10 segundos.

## Estado actual (MVP)

Funcionando de extremo a extremo:
- El bot de Telegram recibe mensajes de huéspedes y responde automáticamente
- La IA clasifica los mensajes y los enruta a los topics relevantes de la base de conocimiento
- Las situaciones sensibles se escalan con alertas
- El panel de administración muestra las conversaciones como una bandeja de entrada operativa
- Las alertas aparecen inline en el timeline de conversación
- El panel y el bot se despliegan juntos en Render

Una sola propiedad, un solo canal, un solo usuario. Sin autenticación, sin persistencia entre deploys, sin soporte multi-propiedad.

## Módulos de la plataforma a largo plazo

La plataforma madura incluirá estos módulos, listados en orden de dependencia:

### 1. Propiedades
Crear y configurar propiedades desde el panel. Cada propiedad tiene: perfil (nombre, ubicación, contactos), base de conocimiento (FAQ, check-in, normas, emergencias, consejos). La base de conocimiento alimenta las respuestas de la IA. Editar el conocimiento de una propiedad cambia inmediatamente el comportamiento del bot para esa propiedad.

### 2. Bandeja de entrada
Gestión de conversaciones entre propiedades. Todas las conversaciones de todas las propiedades en una bandeja unificada, filtrable por propiedad, estado y urgencia. Esta es la vista operativa principal.

### 3. Reservas
Saber qué huéspedes están alojados actualmente, en qué propiedad y cuándo hacen check-in/out. Inicialmente entrada manual. Más adelante: integración con PMS (Guesty, Hostaway, Beds24) y sincronización iCal (Airbnb, Booking.com). Los datos de reserva permiten al bot personalizar las respuestas con contexto del huésped.

### 4. Perfiles de huéspedes
Vinculados automáticamente desde las reservas. Cuando llega un mensaje, el sistema identifica: huésped activo, huésped anterior o contacto desconocido. No se necesita un módulo de contactos independiente — esto emerge naturalmente de los datos de reserva.

### 5. Canales
Mensajería multicanal. Telegram (actual), WhatsApp (necesidad principal del mercado), email. Todos los canales convergen en la misma bandeja de entrada. La abstracción de canal ya existe en el código (interfaz BaseChannel).

### 6. Mensajería proactiva
Dos niveles:
- **Iniciada por el operador:** El anfitrión envía un mensaje a un huésped desde el panel (por ejemplo, "tu habitación está lista").
- **Automatizada:** El sistema envía mensajes preconfigurados a check-in menos 24h, día de check-in, checkout menos 2h, etc. Requiere datos de reserva y plantillas de mensajes.

### 7. Notificaciones
Alertas externas al equipo cuando ocurren incidencias. Las alertas de Telegram ya funcionan. Las notificaciones por email son la siguiente adición útil. Configurable por cliente: qué canales, qué direcciones, qué niveles de urgencia.

### 8. Informes
Resúmenes operativos, no dashboards de analítica. Útiles solo cuando existe suficiente datos: conversaciones por semana, tasa de resolución bot vs humano, tiempos de respuesta, alertas por propiedad. Una única línea de resumen en la bandeja de entrada es más valiosa en etapas tempranas que una página completa de informes.

### 9. Autenticación y equipos
Login de cliente, claves de API, miembros del equipo con roles (propietario, gestor, limpiador). Diferentes permisos por rol. Necesario para SaaS multi-cliente pero no para un piloto con un solo cliente.

## Principios de diseño

1. **Bandeja de entrada primero.** El panel es una bandeja de conversaciones, no un dashboard.
2. **Claridad operativa.** Los problemas urgentes deben ser obvios de inmediato.
3. **Mínima carga cognitiva.** Comprensible sin formación.
4. **Orientado a la acción.** Cada elemento importante lleva a una acción clara.
5. **Contexto de propiedad.** Cada conversación pertenece a una propiedad.
6. **Responsabilidad.** Claro quién es responsable: bot, anfitrión o equipo.
7. **Simplicidad de implementación.** Sin frameworks frontend complejos. HTML + CSS + JS vanilla.

## Explícitamente pospuesto

Estas funcionalidades han sido consideradas y diferidas explícitamente:

- **Dashboards de analítica** — los anfitriones con 2-3 propiedades no necesitan gráficos. Necesitan la bandeja de entrada.
- **Fine-tuning de IA por propiedad** — el modelo base con buen contexto de base de conocimiento es suficiente.
- **App móvil nativa** — el panel web responsive es adecuado. Las apps son caras de mantener.
- **Panel UI multiidioma** — el idioma del anfitrión es conocido. Hardcodear uno. Traducir más adelante.
- **Facebook Messenger / mensajería de Booking.com** — WhatsApp cubre más del 80% del mercado. Otros canales pueden esperar.
- **SMS** — poco valor comparado con WhatsApp, alto coste por mensaje.
- **Business intelligence / métricas de marketing** — esto es una consola de operaciones, no un producto de analítica.
- **Control de acceso basado en roles complejo** — primero autenticación con contraseña simple, luego equipos con un rol, luego RBAC mucho más adelante.
- **Docker / contenedorización** — el runtime Python nativo de Render es suficiente para la escala actual.

## Decisiones arquitectónicas clave por delante

1. **Migración a PostgreSQL** — necesaria para la persistencia de datos. SQLite es efímero en Render.
2. **Carga dinámica del contexto de propiedad** — actualmente `config.py` carga los datos de propiedad al arrancar. Para multi-propiedad, `process_message()` debe cargar el contexto de propiedad por conversación desde la base de datos. Este es el refactor más importante.
3. **Generalización del contact ID de canal** — `telegram_chat_id` debe convertirse en `channel_contact_id` antes del soporte multicanal. Es más fácil renombrarlo pronto con menos datos.
4. **Cola de mensajes salientes** — cuando el anfitrión envía mensajes desde el panel, deben pasar por una tabla de cola que bot.py recoja, en lugar de dar a la API acceso directo al canal.
