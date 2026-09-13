// Edge Function: push-aprobacion
// Envía un PUSH "¡Tu cancha fue aprobada!" al RECLAMANTE cuando el operador
// aprueba/activa su reclamo de propiedad.
//
// La INVOCA el backend growth (Railway) al aprobar el reclamo — el growth NO
// hace FCM, delega en Supabase. Body:
//   { email, cancha_nombre?, cancha_id? }
//
// Auth: si PUSH_APROBACION_SECRET está seteado, se exige el header
//   X-Push-Secret: <secreto>   (para que no cualquiera dispare notificaciones).
//
// Tokens del reclamante: pichangol_push_tokens (por email). Envía FCM v1 con
// tipo "reclamo_aprobado" y tap → "Mis canchas".
//
// Secrets:
//   FCM_SERVICE_ACCOUNT   = JSON de la cuenta de servicio de Firebase
//   PUSH_APROBACION_SECRET= secreto compartido con el backend growth (opcional)
// SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase.
//
// Fail-safe: ante cualquier error responde 200 (no reintenta en bucle).

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SA_RAW = Deno.env.get("FCM_SERVICE_ACCOUNT") ?? "";
const PUSH_SECRET = Deno.env.get("PUSH_APROBACION_SECRET") ?? "";

function ok(obj: unknown) {
  return new Response(JSON.stringify(obj), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

// --- base64url helpers -------------------------------------------------------
function b64url(data: Uint8Array): string {
  const s = btoa(String.fromCharCode(...data));
  return s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlStr(s: string): string {
  return b64url(new TextEncoder().encode(s));
}

// --- OAuth token de la cuenta de servicio (para FCM v1) ----------------------
async function importKey(pem: string): Promise<CryptoKey> {
  const body = pem
    .replace(/-----BEGIN PRIVATE KEY-----/, "")
    .replace(/-----END PRIVATE KEY-----/, "")
    .replace(/\s+/g, "");
  const der = Uint8Array.from(atob(body), (c) => c.charCodeAt(0));
  return crypto.subtle.importKey(
    "pkcs8",
    der.buffer,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"],
  );
}

async function getAccessToken(sa: any): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const claim = {
    iss: sa.client_email,
    scope: "https://www.googleapis.com/auth/firebase.messaging",
    aud: "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  };
  const unsigned = `${b64urlStr(JSON.stringify(header))}.${
    b64urlStr(JSON.stringify(claim))
  }`;
  const key = await importKey(sa.private_key);
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key,
    new TextEncoder().encode(unsigned),
  );
  const jwt = `${unsigned}.${b64url(new Uint8Array(sig))}`;
  const resp = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body:
      "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=" + jwt,
  });
  const j = await resp.json();
  return j.access_token;
}

// --- consultas a Supabase (REST con service role) ----------------------------
async function sb(path: string): Promise<any[]> {
  const r = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: { apikey: SERVICE_ROLE, Authorization: `Bearer ${SERVICE_ROLE}` },
  });
  if (!r.ok) return [];
  return await r.json();
}

serve(async (req) => {
  try {
    if (!SA_RAW) return ok({ skip: "sin FCM_SERVICE_ACCOUNT" });
    // Secreto compartido con el backend growth (si está configurado).
    if (PUSH_SECRET && req.headers.get("x-push-secret") !== PUSH_SECRET) {
      return ok({ skip: "secreto inválido" });
    }
    const body = await req.json().catch(() => ({}));
    const email = String(body.email ?? "").trim().toLowerCase();
    if (!email) return ok({ skip: "sin email" });
    const canchaNombre = String(body.cancha_nombre ?? "tu cancha").trim() ||
      "tu cancha";
    const canchaId = String(body.cancha_id ?? "").trim();

    // Tokens del reclamante (multi-dispositivo).
    const tks = await sb(
      `pichangol_push_tokens?email=eq.${encodeURIComponent(email)}&select=token`,
    );
    const tokens: string[] = tks.map((f) => f.token).filter(Boolean);
    if (tokens.length === 0) return ok({ skip: "sin tokens", email });

    // Access token FCM.
    const sa = JSON.parse(SA_RAW);
    const access = await getAccessToken(sa);
    if (!access) return ok({ error: "sin access token" });

    const titulo = "¡Cancha aprobada! ✅";
    const cuerpo =
      `${canchaNombre} ya está verificada. Ya puedes recibir reservas.`;
    const url =
      `https://fcm.googleapis.com/v1/projects/${sa.project_id}/messages:send`;
    const collapse = canchaId || email;
    const resultados = await Promise.all(
      tokens.map((token) =>
        fetch(url, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${access}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            message: {
              token,
              notification: { title: titulo, body: cuerpo },
              data: { tipo: "reclamo_aprobado", cancha_id: canchaId },
              android: { priority: "high", collapse_key: collapse },
            },
          }),
        }).then((r) => r.status).catch(() => 0)
      ),
    );
    return ok({
      enviados: resultados.filter((s) => s === 200).length,
      total: tokens.length,
    });
  } catch (e) {
    return ok({ error: String(e) });
  }
});
