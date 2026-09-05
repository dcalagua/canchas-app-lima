// Edge Function: push-aviso
// Canal de push GENÉRICO. Envía una notificación FCM (HTTP v1) cuando entra una
// fila nueva en `pichangol_avisos`. Se dispara por un Database Webhook (INSERT).
//
// Lo usan los RETOS P2P (que viven en el backend growth, no en Supabase, así que
// el push del chat no los cubre): al retar / aceptar / reportar resultado, el
// cliente inserta una fila { email, titulo, cuerpo, data } y aquí se entrega.
//
// Destinatario: la columna `email`. Se buscan sus tokens en
// `pichangol_push_tokens` y se envía a cada dispositivo.
//
// Secrets necesarios (Supabase → Edge Functions → Secrets) — LOS MISMOS del chat:
//   FCM_SERVICE_ACCOUNT = JSON de la cuenta de servicio de Firebase (privado)
// SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase automáticamente.
//
// Todo es fail-safe: ante cualquier error responde 200 para no reintentar en bucle.

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const SA_RAW = Deno.env.get("FCM_SERVICE_ACCOUNT") ?? "";

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
  const unsigned = `${b64urlStr(JSON.stringify(header))}.${b64urlStr(JSON.stringify(claim))}`;
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
    const body = await req.json().catch(() => ({}));
    const a = body.record ?? body; // webhook: {type, table, record}
    const email = (a?.email ?? "").toLowerCase();
    const titulo = (a?.titulo ?? "Pichangol").toString();
    const cuerpo = (a?.cuerpo ?? "").toString();
    if (!email || !cuerpo) return ok({ skip: "aviso incompleto" });

    // Tokens del destinatario (puede tener varios dispositivos).
    const filas = await sb(
      `pichangol_push_tokens?email=eq.${encodeURIComponent(email)}&select=token`,
    );
    const tokens: string[] = filas.map((f) => f.token).filter(Boolean);
    if (tokens.length === 0) return ok({ skip: "sin tokens", email });

    // Access token FCM.
    const sa = JSON.parse(SA_RAW);
    const access = await getAccessToken(sa);
    if (!access) return ok({ error: "sin access token" });

    // data del aviso (solo strings para FCM v1).
    const data: Record<string, string> = { tipo: (a?.tipo ?? "aviso").toString() };
    if (a?.data && typeof a.data === "object") {
      for (const [k, v] of Object.entries(a.data)) data[k] = String(v);
    }

    const url = `https://fcm.googleapis.com/v1/projects/${sa.project_id}/messages:send`;
    // Captura el MOTIVO real de cada rechazo (SENDER_ID_MISMATCH, UNREGISTERED,
    // SERVICE_DISABLED…): se devuelve en la respuesta (el diagnóstico del APK lo
    // muestra) y se loguea (Supabase → Edge Functions → push-aviso → Logs).
    const errores: string[] = [];
    const resultados = await Promise.all(
      tokens.map(async (token) => {
        try {
          const r = await fetch(url, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${access}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              message: {
                token,
                notification: { title: titulo, body: cuerpo },
                data,
                android: { priority: "high" },
              },
            }),
          });
          if (r.status !== 200) {
            const txt = await r.text();
            let motivo = txt.slice(0, 300);
            try {
              const j = JSON.parse(txt);
              motivo = j?.error?.status ?? j?.error?.message ?? motivo;
            } catch (_) { /* respuesta no-JSON: se deja el texto crudo */ }
            errores.push(`${r.status} ${motivo} · token …${token.slice(-8)}`);
            console.log("FCM rechazo:", r.status, motivo);
          }
          return r.status;
        } catch (e) {
          errores.push(`fetch: ${String(e)}`);
          return 0;
        }
      }),
    );
    return ok({
      enviados: resultados.filter((s) => s === 200).length,
      total: tokens.length,
      proyecto: sa.project_id,
      ...(errores.length ? { fcm: errores } : {}),
    });
  } catch (e) {
    // 200 siempre: evita reintentos en bucle del webhook.
    return ok({ error: String(e) });
  }
});
