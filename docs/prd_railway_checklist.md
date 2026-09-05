# PRD · Checklist del servicio Railway `pg-backend-prd`

> **ESTADO (24-ago-2026): pasos 1 y 2 YA EJECUTADOS por Claude vía el
> conector de Railway.** Servicio `pg-backend-prd` creado (rama `prd`, root
> `backend/growth`), 35 variables cargadas (los secretos compartidos como
> referencias `${{pg-backend.VAR}}`; tokens ADMIN/APP/WEBHOOK nuevos ya
> generados y puestos), dominio `pg-backend-prd-production.up.railway.app`,
> deploy SUCCESS y `/health` 200. Las 8 Edge Functions de PCG-PRD también
> están desplegadas y los triggers de push cableados.
> **Falta (manual):** `DATABASE_URL` (contraseña de la BD de PCG-PRD),
> secrets `FCM_SERVICE_ACCOUNT` / `PUSH_APROBACION_SECRET` / `PLACES_API_KEY`
> en PCG-PRD → Edge Functions, llaves Culqi live, corte de dominio (paso 4)
> y APK PRD (paso 5).

Estado del resto del PRD: Supabase **PCG-PRD** ya creado y migrado
(org GRUPO EBIM, ref `xjoqotzfgniinxyxvhxj`, São Paulo): 40 tablas con RLS,
7 buckets, realtime y triggers de push listos. La rama **`prd`** del repo ya
existe: es la que despliega producción (la rama de desarrollo sigue
redeployando solo el piloto).

> Regla de oro: **PRD despliega SOLO desde la rama `prd`.** Promover una
> versión estable = `git push origin <commit>:prd` (o merge a `prd`). Nunca
> apuntar PRD a la rama de desarrollo.

## 1) Crear el servicio (5 min, en el MISMO proyecto Railway)

1. Railway → proyecto actual → **New → GitHub Repo** → `dcalagua/canchas-app-lima`.
2. Nombre del servicio: **`pg-backend-prd`**.
3. Settings → **Root Directory**: `backend/growth`.
4. Settings → **Branch**: `prd` (¡no la rama de desarrollo!). "Wait for CI": off.
5. Todavía **NO** mover el dominio (paso 4).

## 2) Variables del servicio PRD

**Copiar de `pg-backend` (mismo valor):** `FACTILIZA_API_TOKEN`,
`CIPHERBYTE_API_TOKEN`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
`TWILIO_FROM`, `TWILIO_MESSAGING_SERVICE_SID`, `TWILIO_WHATSAPP_FROM`,
`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_OTP_TEMPLATE`,
`OTP_CANAL_PREFERIDO`, `PICHANGOL_ADMIN_WHATSAPP`, `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY` / `REPLICATE_API_TOKEN` (ilustraciones/packshots),
`COMISION_PORC`, `COMISION_MIN_SOLES`, `META_*` (dejar `META_MODO=sandbox`).

**CAMBIAR (valores propios de PRD):**

| Variable | Valor PRD |
|---|---|
| `DATABASE_URL` | Pooler de sesión de **PCG-PRD** (Supabase → Connect → Session pooler) + `?sslmode=require`. La contraseña de la BD: Database Settings → Reset si no la tienes. |
| `SUPABASE_URL` | `https://xjoqotzfgniinxyxvhxj.supabase.co` |
| `SUPABASE_ANON_KEY` | anon key de PCG-PRD (Settings → API) |
| `ADMIN_PANEL_TOKEN` | **NUEVO** (nunca el del piloto) |
| `ADMIN_PANEL_USUARIOS` | operadores reales |
| `APP_API_KEY` | **NUEVO** (debe coincidir con el dart-define del APK PRD) |
| `CULQI_SECRET_KEY` / `CULQI_PUBLIC_KEY` | `sk_live_…` / `pk_live_…` |
| `CULQI_WEBHOOK_TOKEN` | **NUEVO** |
| `LANDING_BASE_URL` | `https://www.pichangol.app` |
| `PUBLIC_BASE_URL` | `https://www.pichangol.app` |
| `PAGOS_AUTH_USUARIO` | `1` (endurecimiento PROD de la billetera) |
| `PUSH_APROBACION_URL` | `https://xjoqotzfgniinxyxvhxj.supabase.co/functions/v1/push-aprobacion` |
| `PUSH_APROBACION_SECRET` | **NUEVO** (el mismo se pone como secret de esa Edge Function) |

**Dejar VACÍAS:** `RECARGA_YAPE_QR_URL`, `RECARGA_YAPE_NUMERO` (standby hasta
tener Yape Empresa).

## 3) Secrets de Supabase PCG-PRD (una vez)

- Edge Functions → Secrets → **`FCM_SERVICE_ACCOUNT`** = el MISMO JSON de
  Firebase del proyecto dev (sin esto no hay push).
- `places-cerca` necesita su key de Google (mismo secret que en dev).

## 4) Corte del dominio (al final, cuando PRD esté validado)

1. `pg-backend` (piloto) → Settings → Networking → **quitar** `www.pichangol.app`.
2. `pg-backend-prd` → Networking → **agregar** `www.pichangol.app`.
3. El piloto queda con `pg.ebim.pe` + su host `*.up.railway.app`.

## 5) APK de PRD (fase siguiente, lo arma Claude)

Variante del workflow CI con dart-defines de PRD: `SUPABASE_URL`/
`SUPABASE_ANON_KEY` de PCG-PRD, `GROWTH_API_URL=https://www.pichangol.app`,
`APP_API_KEY` nuevo, `ENTORNO=prod` → AAB para Play Store
(`pe.ebim.pichangol`).

## 6) Validación antes de invitar dueños

- [ ] `/admin` PRD abre con el token nuevo (y el viejo NO funciona).
- [ ] Reclamo → aprobar → push "cancha aprobada" llega.
- [ ] Reserva online con tarjeta real (monto chico) → push al dueño +
      liquidación en la torre; reembolso de prueba.
- [ ] Chat + pedido de bodega + puntos con saldo.
- [ ] Backups: PCG-PRD (plan pago) tiene backups diarios — verificar en
      Database → Backups.
