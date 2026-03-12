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
