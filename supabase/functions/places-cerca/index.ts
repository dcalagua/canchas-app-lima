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

const CONSULTAS = [
  "canchas de fútbol",
  "cancha sintética de fútbol",
  "club de tenis",
  "cancha de pádel",
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
    if (req.method === "GET") {
      const u = new URL(req.url);
      lat = Number(u.searchParams.get("lat"));
      lng = Number(u.searchParams.get("lng"));
      radius = Number(u.searchParams.get("radius")) || undefined;
      const f = u.searchParams.get("fotos");
      conFotos = f === "1" || f === "true";
    } else {
      const b = await req.json();
      lat = b.lat;
      lng = b.lng;
      radius = b.radius;
      conFotos = b.fotos === true;
    }
    // Las 4 consultas de texto salen en PARALELO (antes, secuenciales).
    const respuestas = await Promise.all(
      CONSULTAS.map((q) =>
        fetch("https://places.googleapis.com/v1/places:searchText", {
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
            regionCode: "PE",
            maxResultCount: 20,
            locationBias: {
              circle: {
                center: { latitude: lat, longitude: lng },
                radius: radius ?? 4000,
              },
            },
          }),
        })
          .then((r) => (r.ok ? r.json() : { places: [] }))
          .catch(() => ({ places: [] }))
      ),
    );

    const porId = new Map<string, unknown>();
    for (const body of respuestas) {
      for (const p of body.places ?? []) porId.set(p.id, p);
    }

    const lista = [...porId.values()];

    // Modo rápido (default): devuelve las canchas SIN resolver fotos. La app las
    // muestra al instante y vuelve a pedir con fotos=true para enriquecerlas.
    if (!conFotos) return json({ places: lista });

    // Modo con fotos: resuelve las fotos reales de los primeros lugares.
    const conFoto = await Promise.all(
      // deno-lint-ignore no-explicit-any
      lista.slice(0, MAX_LUGARES_CON_FOTO).map(async (p: any) => ({
        ...p,
        fotos: await resolverFotos(p),
      })),
    );
    const resto = lista.slice(MAX_LUGARES_CON_FOTO);

    return json({ places: [...conFoto, ...resto] });
  } catch (e) {
    return json({ places: [], error: String(e) }, 500);
  }
});
