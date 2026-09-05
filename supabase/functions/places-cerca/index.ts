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
    // Las consultas de texto salen en PARALELO. Además de los lugares, capturamos
    // el STATUS y el primer error crudo de Google (diag): antes un rechazo
    // (billing, key inválida, API no habilitada) se tragaba en silencio y la
    // función respondía places:[] sin pista alguna de la causa.
    const diag: { statuses: Record<string, number>; primerError: string } = {
      statuses: {},
      primerError: "",
    };
    const respuestas = await Promise.all(
      CONSULTAS.map(async (q) => {
        try {
          const r = await fetch(
            "https://places.googleapis.com/v1/places:searchText",
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": KEY,
                "X-Goog-FieldMask":
                  "places.id,places.displayName,places.location,places.formattedAddress,places.types,places.photos",
              },
              body: JSON.stringify({
                textQuery: q,
                languageCode: "es",
                regionCode: region,
                maxResultCount: 20,
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
          if (r.ok) return await r.json();
          if (!diag.primerError) {
            diag.primerError = (await r.text()).slice(0, 500);
          }
          return { places: [] };
        } catch (e) {
          if (!diag.primerError) diag.primerError = `fetch: ${e}`;
          return { places: [] };
        }
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
    if (!conFotos) return json({ places: lista, diag });

    // Modo con fotos: resuelve las fotos reales de los primeros lugares.
    const conFoto = await Promise.all(
      // deno-lint-ignore no-explicit-any
      lista.slice(0, MAX_LUGARES_CON_FOTO).map(async (p: any) => ({
        ...p,
        fotos: await resolverFotos(p),
      })),
    );
    const resto = lista.slice(MAX_LUGARES_CON_FOTO);

    return json({ places: [...conFoto, ...resto], diag });
  } catch (e) {
    return json({ places: [], error: String(e) }, 500);
  }
});
