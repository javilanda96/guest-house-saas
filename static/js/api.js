/**
 * Helper minimo para llamadas a la API.
 * Todas las paginas importan este archivo.
 */

const API = {
  async get(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
    return res.json();
  },

  async patch(path, body = null) {
    const opts = {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `PATCH ${path}: ${res.status}`);
    }
    return res.json();
  },
};

/** Formatea ISO timestamp a fecha legible corta */
function fmtDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Devuelve clase CSS para un status */
function statusClass(status) {
  const map = {
    open: "badge-blue",
    bot_resolved: "badge-green",
    host_pending: "badge-orange",
    urgent: "badge-red",
  };
  return map[status] || "badge-gray";
}

/** Devuelve tiempo relativo legible: "2 min ago", "3h ago", "5d ago" */
function timeAgo(iso) {
  if (!iso) return "";
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60)   return "ahora";
  if (secs < 3600) return Math.floor(secs / 60) + " min";
  if (secs < 86400) return Math.floor(secs / 3600) + "h";
  return Math.floor(secs / 86400) + "d";
}

/** Formatea property_id a nombre legible: "apt_centro_01" → "Apt Centro 01" */
function fmtProperty(id) {
  if (!id) return "";
  return id.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

/** Etiqueta legible para status */
function statusLabel(status) {
  const map = {
    open: "Activa",
    bot_resolved: "Resuelta",
    host_pending: "Pendiente",
    urgent: "Urgente",
  };
  return map[status] || status;
}

/** Trunca texto a max caracteres */
function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max) + "…" : s;
}

/** Escapa HTML para prevenir XSS */
function esc(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}
