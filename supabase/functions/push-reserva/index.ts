// Edge Function: push-reserva
// Envía una notificación PUSH DEDICADA al DUEÑO de la cancha cuando entra una
// reserva (aviso "fuera del chat", con su propio tipo y tap → pantalla de
// Reservas del dueño).
//
// La invoca el APK al confirmarse la reserva en el servidor, pasando SOLO el id
// de la reserva (o el del grupo, si son varias horas). Todo el contenido lo
// deriva el servidor a partir de ese id, para que NO se pueda falsificar el
// destinatario ni el texto:
//   body = { reserva_id }   ó   { grupo_id }
//
// Destinatario: el dueño de la cancha (pichangol_canchas.dueno). Sus tokens
// están en pichangol_push_tokens. Se omite si la reserva es MANUAL del dueño
// (traida_por_app=false) o si el que reservó es el propio dueño.
//
// Secrets (ya usados por push-mensaje/push-matricula):
//   FCM_SERVICE_ACCOUNT = JSON de la cuenta de servicio de Firebase
// SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase.
//
// Fail-safe: ante cualquier error responde 200 (no reintenta en bucle).

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
    const body = await req.json().catch(() => ({}));
    const reservaId = String(body.reserva_id ?? "").trim();
    const grupoId = String(body.grupo_id ?? "").trim();
    if (!reservaId && !grupoId) return ok({ skip: "sin id" });

    // 1) Reserva(s): por grupo (varias horas) o por id (una sola).
    const cols =
      "cancha_id,jugador,usuario,fecha,dia,hora_inicio,hora_fin,traida_por_app,moneda,precio";
    const filas = grupoId
      ? await sb(
        `pichangol_reservas?grupo_reserva_id=eq.${
          encodeURIComponent(grupoId)
        }&select=${cols}&order=hora_inicio.asc`,
      )
      : await sb(
        `pichangol_reservas?id=eq.${
          encodeURIComponent(reservaId)
        }&select=${cols}`,
      );
    if (filas.length === 0) return ok({ skip: "reserva no encontrada" });
    const r0 = filas[0];
    // Manual del dueño (cliente propio) → no se notifica a sí mismo.
    if (r0.traida_por_app === false) return ok({ skip: "reserva manual" });

    // 2) Dueño + nombre de la cancha.
    const cid = String(r0.cancha_id ?? "");
    if (!cid) return ok({ skip: "sin cancha" });
    const canchas = await sb(
      `pichangol_canchas?id=eq.${
        encodeURIComponent(cid)
      }&select=dueno,nombre,club`,
    );
    const dueno = (canchas[0]?.dueno ?? "").toLowerCase();
    if (!dueno) return ok({ skip: "sin dueño" });
    // El que reservó es el propio dueño → no avisar.
    if ((r0.usuario ?? "").toLowerCase() === dueno) {
      return ok({ skip: "el dueño reservó su cancha" });
    }
    const nombreCancha = (canchas[0]?.nombre ?? canchas[0]?.club ?? "tu cancha")
      .toString();

    // 3) Tokens del dueño (multi-dispositivo).
    const tks = await sb(
      `pichangol_push_tokens?email=eq.${
        encodeURIComponent(dueno)
      }&select=token`,
    );
    const tokens: string[] = tks.map((f) => f.token).filter(Boolean);
    if (tokens.length === 0) return ok({ skip: "sin tokens", dueno });

    // 4) Access token FCM.
    const sa = JSON.parse(SA_RAW);
    const access = await getAccessToken(sa);
    if (!access) return ok({ error: "sin access token" });

    // 5) Mensaje: un jugador, la fecha y el rango (primera–última hora).
    const jugador = (r0.jugador ?? "Un jugador").toString().trim() ||
      "Un jugador";
    const rN = filas[filas.length - 1];
    const rango = filas.length > 1
      ? `${r0.hora_inicio}–${rN.hora_fin}`
      : `${r0.hora_inicio}–${r0.hora_fin}`;
    const cuando = (r0.dia ?? "").toString();
    const titulo = "Nueva reserva 📅";
    const cuerpo = `${jugador} · ${cuando} ${r0.fecha} · ${rango} · ${nombreCancha}`;

    const url =
      `https://fcm.googleapis.com/v1/projects/${sa.project_id}/messages:send`;
    // Colapsa por grupo/reserva para que varias horas del mismo bloque no
    // apilen notificaciones repetidas.
    const collapse = grupoId || reservaId;
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
              data: { tipo: "reserva", cancha_id: cid },
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
