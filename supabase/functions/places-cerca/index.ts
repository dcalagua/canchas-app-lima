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
  const fotos: string[] = [];
  for (const ph of (place.photos ?? []).slice(0, MAX_FOTOS)) {
    try {
      const u =
        `https://places.googleapis.com/v1/${ph.name}/media` +
        `?maxWidthPx=800&skipHttpRedirect=true&key=${KEY}`;
      const r = await fetch(u);
      if (!r.ok) continue;
      const j = await r.json();
      if (j.photoUri) fotos.push(j.photoUri); // URL pública (sin key)
    } catch (_) { /* ignora esta foto */ }
  }
  return fotos;
}

serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (!KEY) return json({ places: [], error: "missing PLACES_API_KEY" });

  try {
    const { lat, lng, radius } = await req.json();
    const porId = new Map<string, unknown>();

    for (const q of CONSULTAS) {
      const resp = await fetch(
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
            regionCode: "PE",
            maxResultCount: 20,
            locationBias: {
              circle: {
                center: { latitude: lat, longitude: lng },
                radius: radius ?? 4000,
              },
            },
          }),
        },
      );
      if (!resp.ok) continue;
      const body = await resp.json();
      for (const p of body.places ?? []) porId.set(p.id, p);
    }

    const lista = [...porId.values()];
    // Resuelve fotos reales para los primeros lugares (cover + galería).
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
