// Edge Function: places-cerca
// Proxy server-side de la Places API (New) para Pichangol. Mantiene la API key
// FUERA del APK (se guarda como secret de Supabase: PLACES_API_KEY).
//
// Deploy:
//   supabase functions deploy places-cerca --no-verify-jwt
//   supabase secrets set PLACES_API_KEY=tu_key
//
// La app la invoca con supabase.functions.invoke('places-cerca',
//   body: { lat, lng, radius }). Devuelve { places: [...] } con el mismo shape
// de Google (id, displayName, location, formattedAddress, types).

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const KEY = Deno.env.get("PLACES_API_KEY") ?? "";

const CONSULTAS = [
  "canchas de fútbol",
  "cancha sintética de fútbol",
  "club de tenis",
  "cancha de pádel",
];

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
              "places.id,places.displayName,places.location,places.formattedAddress,places.types",
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

    return json({ places: [...porId.values()] });
  } catch (e) {
    return json({ places: [], error: String(e) }, 500);
  }
});
