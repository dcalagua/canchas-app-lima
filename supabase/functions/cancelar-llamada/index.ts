// Edge Function: cancelar-llamada
// Cuando un usuario CONTESTA (o rechaza) una llamada en UN dispositivo, el APK
// invoca esta función para APAGAR el timbre en los OTROS dispositivos de la
// misma cuenta ("contestada en otro dispositivo", estilo WhatsApp).
//
// La invoca el APK directamente (supabase.functions.invoke), con el body:
//   { room: "<sala>", email: "<mi correo>", excluir_token: "<mi token FCM>" }
// Busca los tokens de esa cuenta (menos el propio) y les manda un push DATA
// `{ tipo: "cancelar_llamada", room }` de alta prioridad; el APK, al recibirlo,
// cierra la pantalla de llamada entrante (CallKit) de esa sala.
//
// Secrets: FCM_SERVICE_ACCOUNT (igual que push-mensaje). SUPABASE_URL y
// SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase.
//
// Fail-safe: ante cualquier error responde 200.

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

function b64url(data: Uint8Array): string {
  const s = btoa(String.fromCharCode(...data));
  return s.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlStr(s: string): string {
  return b64url(new TextEncoder().encode(s));
}

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
    const room = String(body.room ?? "");
    const email = String(body.email ?? "").toLowerCase();
    const excluir = String(body.excluir_token ?? "");
    if (!room || !email) return ok({ skip: "faltan room/email" });

    // Tokens de la MISMA cuenta (todos sus dispositivos).
    const filas = await sb(
      `pichangol_push_tokens?email=eq.${encodeURIComponent(email)}&select=token`,
    );
    const tokens: string[] = filas
      .map((f) => f.token)
      .filter((t: string) => t && t !== excluir); // no a mí mismo
    if (tokens.length === 0) return ok({ skip: "sin otros dispositivos" });

    const sa = JSON.parse(SA_RAW);
    const access = await getAccessToken(sa);
    if (!access) return ok({ error: "sin access token" });

    const url =
      `https://fcm.googleapis.com/v1/projects/${sa.project_id}/messages:send`;
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
              data: { tipo: "cancelar_llamada", room },
              android: { priority: "high" },
            },
          }),
        }).then((r) => r.status).catch(() => 0)
      ),
    );
    return ok({
      cancelados: resultados.filter((s) => s === 200).length,
      total: tokens.length,
    });
  } catch (e) {
    return ok({ error: String(e) });
  }
});
