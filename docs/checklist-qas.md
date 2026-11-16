# ✅ Checklist QAS — paso a paso (imprimible)

Para levantar el entorno **QAS** (pruebas con base de datos propia) de principio a
fin. Marca cada casilla. Tiempo estimado: ~15–20 min. Referencia técnica:
`docs/entornos-qas-prod.md`.

> **Regla de oro:** nunca pegues llaves/tokens en el chat de Claude ni en el
> código. Van directo en Supabase / Railway / GitHub.

---

## Antes de empezar — ten a la mano
- [ ] Acceso a **Supabase** (supabase.com), **Railway** (railway.app) y **GitHub**
      (repo `dcalagua/canchas-app-lima`, permisos de admin para Settings).
- [ ] Un bloc de notas para copiar temporalmente 4 valores (URL/keys de QAS).

---

## PASO 1 — Supabase QAS (la base de datos de pruebas)

- [ ] En supabase.com → **New project** → nombre `pichangol-qas` → elige región
      (South America / São Paulo) → crea una **contraseña de base de datos** y
      guárdala.
- [ ] Espera a que termine de aprovisionar (~2 min).
- [ ] Menú izquierdo → **SQL Editor** → **New query**.
- [ ] Abre el archivo del repo **`docs/piloto/supabase_QAS_completo.sql`**, copia
      **TODO** su contenido, pégalo y presiona **Run**. Debe decir *Success*.
      (Es idempotente: si lo corres 2 veces no pasa nada.)
- [ ] Menú → **Project Settings → API**. Copia:
  - [ ] **Project URL** → lo llamaremos `SUPABASE_URL` (QAS).
  - [ ] **Project API keys → `anon` `public`** → `SUPABASE_ANON_KEY` (QAS).
- [ ] Menú → **Project Settings → Database → Connection string → `Session pooler`**.
      Copia esa cadena y agrégale `?sslmode=require` al final →
      `DATABASE_URL` (QAS). *(Reemplaza `[YOUR-PASSWORD]` por la contraseña del
      primer paso.)*

**Tienes ahora:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL` (todos QAS).

---

## PASO 2 — Railway QAS (el backend de pruebas)

- [ ] En railway.app → tu proyecto → **New** → **GitHub Repo** →
      `dcalagua/canchas-app-lima` (o **New Service** si ya está conectado).
- [ ] En el servicio nuevo → **Settings**:
  - [ ] **Root Directory** = `backend/growth`
  - [ ] **Branch** = `claude/apk-google-maps-setup-fvpl9w`
  - [ ] Nómbralo `pg-backend-qas`.
- [ ] Pestaña **Variables** → agrega (mínimo para arrancar):
  - [ ] `DATABASE_URL` = el `DATABASE_URL` de QAS (Paso 1). ← crea la tabla
        `growth_state` sola al arrancar.
  - [ ] `ADMIN_PANEL_TOKEN` = inventa un token largo (para entrar a `/admin`).
  - [ ] `APP_API_KEY` = **usa el MISMO valor que el dev** (así no tienes que
        cambiarlo en GitHub). Es la llave app↔backend.
  - [ ] *(Opcional, según lo que quieras probar en QAS)* copia del dev:
        `FACTILIZA_API_TOKEN`, `PICHANGOL_ADMIN_WHATSAPP`, `CULQI_*`, `TWILIO_*`,
        `WHATSAPP_*`, `ANTHROPIC_API_KEY`, `OTP_CANAL_PREFERIDO`. Sin ellos el
        backend arranca igual; solo se desactivan esas funciones.
- [ ] Espera el **Deploy** (verde). En **Settings → Networking → Public
      Networking** → **Generate Domain** si no tiene. Copia esa URL →
      `GROWTH_API_URL` (QAS).
- [ ] Verifica que responde: abre `TU_URL_QAS/admin` en el navegador (debe pedir
      token) y entra con el `ADMIN_PANEL_TOKEN`.

**Tienes ahora:** `GROWTH_API_URL` (QAS).

---

## PASO 3 — GitHub Environment `qas` (para que el APK apunte a QAS)

- [ ] GitHub → repo → **Settings → Environments → New environment** → nombre
      exacto **`qas`** → **Configure environment**.
- [ ] En **Environment secrets → Add secret**, agrega SOLO estos (los demás caen
      solos a los del repo = dev):
  - [ ] `SUPABASE_URL` = SUPABASE_URL de QAS
  - [ ] `SUPABASE_ANON_KEY` = anon key de QAS
  - [ ] `GROWTH_API_URL` = URL pública de Railway QAS
  - [ ] *(solo si en el Paso 2 usaste un `APP_API_KEY` distinto al dev)*
        `APP_API_KEY` = el mismo que pusiste en Railway QAS
- [ ] **No** hace falta re-agregar `MAPS_API_KEY`, `PLACES_API_KEY`,
      `VERIF_API_URL`, ni los `ANDROID_KEYSTORE_*` (se heredan del repo).

---

## PASO 4 — Compilar y probar el APK QAS

- [ ] **Avísame en el chat "ya está el Environment qas"** y yo disparo el build.
      *(O tú mismo: GitHub → Actions → "Build app (Android)" → Run workflow →
      Branch = la rama, **entorno = `qas`** → Run.)*
- [ ] Cuando termine (~6 min): el run → **Artifacts** → descarga
      `pichangol-qas-apk` → adentro `pichangol-qas-<n>.apk`.
- [ ] Instálalo en el teléfono (convive con el dev; trae **banner "QAS"**).
- [ ] Verifica que **crea reservas/academias en la BD de QAS** (no toca dev):
      revísalo en Supabase QAS → **Table Editor**.

✅ **Listo: QAS funcionando con su propia base de datos.**

---

## PASO 5 — (Después) Publicar en Play Store · Prueba interna

> Hazlo cuando QAS esté sólido. Detalle completo en `docs/entornos-qas-prod.md`.

- [ ] Actions → Run workflow → **entorno = `prod`** (o `qas` para probar) →
      descarga el **AAB** desde Artifacts (`pichangol-<entorno>-<n>.aab`).
- [ ] Play Console → crea la app, package **`pe.ebim.pichangol`** (⚠️ irreversible)
      → track **Prueba interna** → sube el AAB → agrega correos de testers.
- [ ] Completa: política de privacidad (URL), *Data safety*, clasificación de
      contenido, público objetivo.
- [ ] ⚠️ **SHA-1 de Play App Signing** (Play Console → *Setup → App integrity*):
      cópialo y agrégalo en **Google Cloud → OAuth** (para Google Sign-In) y en
      la **restricción de la Maps key** (para el mapa). Sin esto, login y mapa
      fallan en la versión de Play.

---

## Resumen de los 4 valores QAS que generas
| Valor | De dónde sale | Dónde se pega |
|---|---|---|
| `SUPABASE_URL` | Supabase QAS → Settings → API | GitHub Env `qas` |
| `SUPABASE_ANON_KEY` | Supabase QAS → Settings → API | GitHub Env `qas` |
| `DATABASE_URL` | Supabase QAS → Settings → Database (pooler) | Railway QAS (Variables) |
| `GROWTH_API_URL` | Railway QAS → Networking (dominio) | GitHub Env `qas` |
