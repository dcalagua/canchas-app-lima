// Edge Function: places-cerca
// Proxy server-side de la Places API (New) para Pichangol. Mantiene la API key
// FUERA del APK (secret de Supabase: PLACES_API_KEY) y además resuelve las
// FOTOS reales de Google (photoUri público) para cada lugar, así la app las
// muestra sin que el dueño tenga que subirlas.
//
// Deploy:
//   supabase functions deploy places-cerca --no-verify-jwt
//   supabase secrets set PLACES_API_KEY=tu_key

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const KEY = Deno.env.get("PLACES_API_KEY") ?? "";
// CACHÉ de consultas (oct-2026, factura de Google): tabla
// `pichangol_places_consultas` (SQL docs/piloto/supabase_places_consultas.sql).
// Cada llamada sin caché son ~18 "Text Search Pro" (≈ USD 0.60). Con caché,
// cualquier punto a ≤ PLACES_CACHE_KM (secret de la Edge, default 20 km;
// decisión del director, 2-oct-2026: "súbelo a 20 km") de una zona consultada
// en los últimos 30 días
// (1 día si pide fotos) reusa la respuesta: APK nuevo, APK viejo y web.
// Sin la tabla o sin service role, la función sigue como antes (fail-open).
const SB_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const TABLA = "pichangol_places_consultas";
const CACHE_KM = Math.max(1, Number(Deno.env.get("PLACES_CACHE_KM") ?? "20") || 20);
const CACHE_DIAS = 30;
const CACHE_DIAS_FOTOS = 1;

function kmEntre(a: number, b: number, c: number, d: number): number {
  const r = Math.PI / 180;
  const x = Math.sin(((c - a) * r) / 2) ** 2 +
    Math.cos(a * r) * Math.cos(c * r) * Math.sin(((d - b) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(x));
}

// deno-lint-ignore no-explicit-any
async function leerCache(region: string, lat: number, lng: number, radio: number, dias: number, fotos: boolean | null): Promise<any[] | null> {
  if (!SB_URL || !SB_KEY) return null;
  try {
    const d = CACHE_KM / 111 + 0.01; // caja de búsqueda ≈ CACHE_KM
    const dLng = d / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
    const desde = new Date(Date.now() - dias * 86400000).toISOString();
    const q = new URLSearchParams();
    q.set("select", "lat,lng,radio,places");
    q.set("region", `eq.${region}`);
    q.append("lat", `gte.${lat - d}`);
    q.append("lat", `lte.${lat + d}`);
    q.append("lng", `gte.${lng - dLng}`);
    q.append("lng", `lte.${lng + dLng}`);
    q.set("creado_en", `gte.${desde}`);
    if (fotos !== null) q.set("fotos", `eq.${fotos}`);
    q.set("order", "creado_en.desc");
    q.set("limit", "100");
    const r = await fetch(`${SB_URL}/rest/v1/${TABLA}?${q}`, {
      headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}` },
    });
    if (!r.ok) return null;
    // deno-lint-ignore no-explicit-any
    const filas: any[] = await r.json();
    // La consulta guardada MÁS CERCANA dentro del radio de reuso.
    // deno-lint-ignore no-explicit-any
    let mejor: any = null, mejorKm = Infinity;
    for (const f of filas) {
      if (Number(f.radio) < radio * 0.75) continue;
      const km = kmEntre(lat, lng, Number(f.lat), Number(f.lng));
      if (km <= CACHE_KM && km < mejorKm) { mejor = f; mejorKm = km; }
    }
    return mejor ? (Array.isArray(mejor.places) ? mejor.places : []) : null;
  } catch (_) {
    return null;
  }
}

async function guardarCache(region: string, lat: number, lng: number, radio: number, fotos: boolean, places: unknown[]): Promise<void> {
  if (!SB_URL || !SB_KEY) return;
  try {
    await fetch(`${SB_URL}/rest/v1/${TABLA}`, {
      method: "POST",
      headers: {
        apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`,
        "Content-Type": "application/json", Prefer: "return=minimal",
      },
      body: JSON.stringify({ region, lat, lng, radio, fotos, places }),
    });
    if (Math.random() < 0.02) {
      // Limpieza ocasional de lo vencido.
      const viejo = new Date(Date.now() - (CACHE_DIAS + 5) * 86400000).toISOString();
      await fetch(`${SB_URL}/rest/v1/${TABLA}?creado_en=lt.${viejo}`, {
        method: "DELETE",
        headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}` },
      });
    }
  } catch (_) {
    // fail-open: sin caché la respuesta igual sale
  }
}

// 10 consultas (antes 19): las quitadas se solapaban casi al 100% con estas.
// Cada consulta = 1 request de cuota SearchText de Places.
const CONSULTAS = [
  "canchas de fútbol",
  "campo deportivo",
  "pichanga", // jerga PE: locales llamados "La Pichanga" solo salen con esto
  "grass sintético",
  "complejo deportivo",
  "cancha de tenis",
  "club de tenis",
  "cancha de pádel",
  "cancha de vóley",
  "cancha de básquet",
  "club deportivo",
  "country club",
];

// Cuántos lugares y fotos resolvemos (control de latencia/cuota).
const MAX_LUGARES_CON_FOTO = 16;
const MAX_FOTOS = 3;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

function json(obj: unknown, status = 200): Response {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}

// deno-lint-ignore no-explicit-any
async function resolverFotos(place: any): Promise<string[]> {
  // Resuelve las fotos en PARALELO (antes era secuencial) para bajar latencia.
  const phs = (place.photos ?? []).slice(0, MAX_FOTOS);
  const urls = await Promise.all(
    // deno-lint-ignore no-explicit-any
    phs.map(async (ph: any): Promise<string | null> => {
      try {
        const u =
          `https://places.googleapis.com/v1/${ph.name}/media` +
          `?maxWidthPx=800&skipHttpRedirect=true&key=${KEY}`;
        const r = await fetch(u);
        if (!r.ok) return null;
        const j = await r.json();
        return j.photoUri ?? null; // URL pública (sin key)
      } catch (_) {
        return null; // ignora esta foto
      }
    }),
  );
  return urls.filter((u): u is string => !!u);
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (!KEY) return json({ places: [], error: "missing PLACES_API_KEY" });

  try {
    // Acepta POST (body JSON, como la app) o GET (?lat=&lng=&radius=) para
    // poder probar pegando una URL en el navegador.
    let lat: number, lng: number, radius: number | undefined;
    let conFotos = false; // por defecto NO resuelve fotos (respuesta rápida)
    let region = "PE"; // país para el regionCode de Google (lo manda el APK)
    if (req.method === "GET") {
      const u = new URL(req.url);
      lat = Number(u.searchParams.get("lat"));
      lng = Number(u.searchParams.get("lng"));
      radius = Number(u.searchParams.get("radius")) || undefined;
      const f = u.searchParams.get("fotos");
      conFotos = f === "1" || f === "true";
      const r = u.searchParams.get("region");
      if (r && r.trim()) region = r.trim().toUpperCase();
    } else {
      const b = await req.json();
      lat = b.lat;
      lng = b.lng;
      radius = b.radius;
      conFotos = b.fotos === true;
      if (typeof b.region === "string" && b.region.trim()) {
        region = b.region.trim().toUpperCase();
      }
    }
    const radio = Number(radius ?? 4000);
    // 1) CACHÉ: con fotos, una respuesta con fotos de ≤1 día; sin fotos,
    //    cualquiera de ≤30 días (sin las URLs de fotos, que caducan).
    if (conFotos) {
      const c = await leerCache(region, lat, lng, radio, CACHE_DIAS_FOTOS, true);
      if (c) return json({ places: c, diag: { cache: "fotos" } });
    }
    const cacheBase = await leerCache(region, lat, lng, radio, CACHE_DIAS, null);
    if (cacheBase && !conFotos) {
      // deno-lint-ignore no-explicit-any
      return json({ places: cacheBase.map((p: any) => { const { fotos: _f, ...r } = p; return r; }), diag: { cache: "zona" } });
    }
    // Las consultas de texto salen en PARALELO. Además de los lugares, capturamos
    // el STATUS y el primer error crudo de Google (diag): antes un rechazo
    // (billing, key inválida, API no habilitada) se tragaba en silencio y la
    // función respondía places:[] sin pista alguna de la causa.
    const diag: { statuses: Record<string, number>; primerError: string } = {
      statuses: {},
      primerError: "",
    };
    // Cada consulta devuelve como máximo 20 lugares (los MÁS cercanos). En
    // zonas densas eso deja fuera locales a 2-4 km ("Campo deportivo Edu Jr.",
    // sep-2026): las consultas AMPLIAS siguen `nextPageToken` hasta 3 páginas.
    const PAGINAS_EXTRA: Record<string, number> = {
      "canchas de fútbol": 2, "campo deportivo": 2, "complejo deportivo": 1, "grass sintético": 1,
    };
    const respuestas = cacheBase ? [{ places: cacheBase }] : await Promise.all(
      CONSULTAS.map(async (q) => {
        const places: unknown[] = [];
        let pageToken: string | undefined;
        const paginas = 1 + (PAGINAS_EXTRA[q] ?? 0);
        for (let i = 0; i < paginas; i++) {
          try {
            const r = await fetch(
              "https://places.googleapis.com/v1/places:searchText",
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "X-Goog-Api-Key": KEY,
                  "X-Goog-FieldMask":
                    "places.id,places.displayName,places.location,places.formattedAddress,places.types,places.photos,nextPageToken",
                },
                body: JSON.stringify({
                  textQuery: q,
                  languageCode: "es",
                  regionCode: region,
                  pageSize: 20,
                  ...(pageToken ? { pageToken } : {}),
                  // Rankear por DISTANCIA: devuelve las canchas MÁS CERCANAS
                  // primero (no las más "populares").
                  rankPreference: "DISTANCE",
                  locationBias: {
                    circle: {
                      center: { latitude: lat, longitude: lng },
                      radius: radius ?? 4000,
                    },
                  },
                }),
              },
            );
            diag.statuses[String(r.status)] =
              (diag.statuses[String(r.status)] ?? 0) + 1;
            if (!r.ok) {
              if (!diag.primerError) {
                diag.primerError = (await r.text()).slice(0, 500);
              }
              break;
            }
            const body = await r.json();
            places.push(...(body.places ?? []));
            pageToken = body.nextPageToken;
            if (!pageToken) break;
          } catch (e) {
            if (!diag.primerError) diag.primerError = `fetch: ${e}`;
            break;
          }
        }
        return { places };
      }),
    );

    const porId = new Map<string, unknown>();
    for (const body of respuestas) {
      for (const p of body.places ?? []) porId.set(p.id, p);
    }

    const lista = [...porId.values()];

    // Modo rápido (default): devuelve las canchas SIN resolver fotos. La app las
    // muestra al instante y vuelve a pedir con fotos=true para enriquecerlas.
    // `diag` viaja siempre: la app lo ignora y el Test del dashboard lo muestra.
    // Nunca se guarda una respuesta con error de Google (cuota, facturación):
    // quedaría vacía 30 días.
    const sinError = !!cacheBase || !diag.primerError;
    if (!conFotos) {
      if (sinError) await guardarCache(region, lat, lng, radio, false, lista);
      return json({ places: lista, diag });
    }

    // Modo con fotos: resuelve las fotos reales de los primeros lugares.
    const conFoto = await Promise.all(
      // deno-lint-ignore no-explicit-any
      lista.slice(0, MAX_LUGARES_CON_FOTO).map(async (p: any) => ({
        ...p,
        fotos: await resolverFotos(p),
      })),
    );
    const resto = lista.slice(MAX_LUGARES_CON_FOTO);

    const conTodo = [...conFoto, ...resto];
    if (sinError) await guardarCache(region, lat, lng, radio, true, conTodo);
    return json({ places: conTodo, diag });
  } catch (e) {
    return json({ places: [], error: String(e) }, 500);
  }
});
