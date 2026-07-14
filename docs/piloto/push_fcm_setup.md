# Push del chat (Etapa B · FCM) — guía de activación

El código ya está listo y es **fail-safe**: mientras no completes estos pasos, el
APK compila igual y el push simplemente queda **desactivado** (el chat en vivo de
la Etapa A sigue funcionando). Cuando termines, las notificaciones llegan aunque
la app esté cerrada.

Necesitas una cuenta de **Firebase** (gratis) y ~15 min. Todo por dashboard.

## 1) Crear el proyecto Firebase + app Android
1. https://console.firebase.google.com → **Agregar proyecto** (puedes usar el
   mismo proyecto de Google Cloud donde ya tienes las Maps/Places keys).
2. Dentro del proyecto → **Agregar app** → **Android**.
   - **Nombre del paquete Android:** `pe.ebim.pichangol` (¡exacto!).
3. Descarga el **`google-services.json`** que te da.

## 2) Cargar `google-services.json` como secret de GitHub (build del APK)
El APK se compila en GitHub Actions, así que el archivo va como secret en base64:
```bash
base64 -w0 google-services.json      # Linux
base64 -i google-services.json       # macOS
```
Copia TODO el resultado y en GitHub → repo → **Settings → Secrets and variables →
Actions → New repository secret**:
- **Name:** `GOOGLE_SERVICES_JSON_B64`
- **Value:** (el base64 pegado)

En el próximo build, el paso "Configurar plataforma" lo detecta y activa Firebase
en el APK (si el secret no está, no pasa nada: push off).

## 3) Cuenta de servicio para ENVIAR el push (Edge Function)
1. Firebase Console → ⚙️ **Configuración del proyecto → Cuentas de servicio →
   Generar nueva clave privada**. Descarga el JSON.
2. Supabase → tu proyecto → **Edge Functions → Secrets** (o **Project Settings →
   Edge Functions**): crea un secret:
   - **Name:** `FCM_SERVICE_ACCOUNT`
   - **Value:** pega el **contenido completo** del JSON de la cuenta de servicio.

> `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` ya los inyecta Supabase solo; no
> los toques.

## 4) Desplegar la Edge Function `push-mensaje`
Desde el dashboard: **Edge Functions → Deploy a new function** → nómbrala
`push-mensaje` y pega el contenido de `supabase/functions/push-mensaje/index.ts`.
(Si prefieres, pídeme el archivo completo para copiar-pegar como con `places-cerca`.)

## 5) Crear la tabla de tokens (SQL)
En Supabase → **SQL Editor**, corre el bloque de `pichangol_push_tokens` que está
al final de `docs/piloto/supabase_mensajes.sql` (es idempotente).

## 6) Conectar el webhook: mensaje nuevo → enviar push
Supabase → **Database → Webhooks → Create a new hook**:
- **Table:** `pichangol_mensajes`
- **Events:** `Insert`
- **Type:** `Supabase Edge Functions` → función `push-mensaje`
- Guardar.

## 6-bis) Alternativa: TRIGGER SQL (si el webhook da "schema supabase_functions does not exist")

En algunos proyectos, el webhook del dashboard (paso 6) falla con
`schema "supabase_functions" does not exist`. La vía robusta es un **trigger SQL**
que llama a la Edge Function con `pg_net`. Pega esto en **SQL Editor**, cambiando
`TU-PROYECTO` por el ref de tu proyecto y usando tu **anon key** (la pública, la
misma del APK — NO hace falta el service role: la función usa su propio service
role interno para consultar):

```sql
-- Extensión para llamar HTTP desde Postgres.
create extension if not exists pg_net with schema extensions;

create or replace function public.notificar_push_mensaje()
returns trigger
language plpgsql
security definer
as $$
begin
  perform net.http_post(
    url     := 'https://TU-PROYECTO.supabase.co/functions/v1/push-mensaje',
    headers := jsonb_build_object(
      'Content-Type',  'application/json',
      'Authorization', 'Bearer TU_ANON_KEY'
    ),
    body    := jsonb_build_object('record', to_jsonb(NEW))
  );
  return NEW;
end;
$$;

drop trigger if exists trg_push_mensaje on public.pichangol_mensajes;
create trigger trg_push_mensaje
  after insert on public.pichangol_mensajes
  for each row execute function public.notificar_push_mensaje();
```

Verificar: inserta un mensaje de prueba y revisa **Edge Functions → push-mensaje →
Logs**: debe responder `200` (`{"enviados":N}` o `{"skip":"sin tokens"}` si aún no
hay tokens registrados — ambos significan que el trigger llegó bien).
> Si usaste el trigger, NO configures además el webhook del paso 6 (dispararía el
> push dos veces).

## 7) Reconstruir el APK
Cualquier push a la rama dispara el build. Con el secret del paso 2 ya presente,
el APK sale con Firebase activo. Instálalo, inicia sesión (el token se guarda
solo) y prueba: manda un mensaje desde otra cuenta con la app cerrada → llega la
notificación. 🎉

---

### Cómo funciona (resumen técnico)
- **App:** `PushService` (fail-safe) pide permiso, obtiene el token FCM y lo
  guarda en `pichangol_push_tokens` (asociado a tu correo) al iniciar sesión; lo
  borra al cerrar sesión.
- **Envío:** el webhook llama a `push-mensaje` en cada mensaje nuevo. La función
  decide el **destinatario** (si escribió el profe → la cuenta del alumno; si
  escribió el alumno → el dueño de la academia), busca sus tokens y manda el push
  por **FCM HTTP v1** (autenticado con la cuenta de servicio).
- **Costo:** FCM es **gratis**. No hay costo por notificación.
