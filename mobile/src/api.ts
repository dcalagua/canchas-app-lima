// Cliente del backend de crecimiento (puntos, zonas, verificación física).
// La URL base se configura con EXPO_PUBLIC_GROWTH_API_URL (Expo public env).

const BASE_URL =
  process.env.EXPO_PUBLIC_GROWTH_API_URL ?? 'http://localhost:8000';

async function req(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data?.detail || data?.error || `HTTP ${res.status}`);
  return data;
}

export const api = {
  baseUrl: BASE_URL,

  // --- A. Puntos ---
  saldo: (usuarioId: string) => req(`/puntos/saldo/${usuarioId}`),
  movimientos: (usuarioId: string) => req(`/puntos/movimientos/${usuarioId}`),
  canjear: (body: {
    usuario_id: string; puntos_usados: number; tipo_premio?: string;
    fuente_financiamiento?: string;
  }, idemKey?: string) =>
    req('/puntos/canjear', {
      method: 'POST',
      headers: idemKey ? { 'Idempotency-Key': idemKey } : {},
      body: JSON.stringify(body),
    }),

  // --- B. Solicitudes ---
  pedirCancha: (body: {
    usuario_id: string; nombre_cancha_libre: string; direccion_texto: string;
    distrito?: string; lat?: number; lng?: number;
  }, idemKey?: string) =>
    req('/solicitudes', {
      method: 'POST',
      headers: idemKey ? { 'Idempotency-Key': idemKey } : {},
      body: JSON.stringify(body),
    }),
  ranking: (zona?: string) =>
    req(`/solicitudes/ranking${zona ? `?zona=${zona}` : ''}`),

  // --- C. Verificación física ---
  visitas: (zona?: string, verificadorId?: number) => {
    const q = new URLSearchParams();
    if (zona) q.set('zona', zona);
    if (verificadorId != null) q.set('verificador_id', String(verificadorId));
    const s = q.toString();
    return req(`/verificacion-fisica/visitas${s ? `?${s}` : ''}`);
  },
  captura: (vfId: number, body: {
    fotos_geo_urls: string[]; lat_sitio: number; lng_sitio: number;
    firma_verificador: string; observaciones?: string;
  }) =>
    req(`/verificacion-fisica/${vfId}/captura`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  verificadores: () => req('/verificacion-fisica/verificadores'),
};
