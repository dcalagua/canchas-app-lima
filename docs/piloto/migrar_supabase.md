# Migrar Pichangol a otra cuenta / proyecto Supabase

No hay botón de "desconectar": la conexión a Supabase es solo por variables de
entorno. Re-apuntar esos valores al proyecto nuevo ES la desconexión (el viejo
deja de recibir tráfico). Son 3 conexiones + la Edge Function.

## Qué apunta a Supabase
| Qué | Dónde | Variable |
|-----|-------|----------|
| APK (datos: canchas/reservas) | GitHub → Secrets → Actions | `SUPABASE_URL`, `SUPABASE_ANON_KEY` |
| Backend growth (snapshot) | Railway → pg-backend → Variables | `DATABASE_URL` |
| Búsqueda de canchas cercanas | Edge Function en el proyecto Supabase | función `places-cerca` + secret `PLACES_API_KEY` |

## Pasos (hacer el proyecto NUEVO primero, luego flipear)

1. **Crear tablas** en el proyecto nuevo: correr `supabase_setup_nuevo_proyecto.sql`
   en el SQL Editor.
2. **Edge Function** `places-cerca` en el proyecto nuevo (necesita Supabase CLI,
   logueado en la cuenta NUEVA):
   ```bash
   supabase login                      # cuenta nueva
   supabase link --project-ref <REF_NUEVO>
   supabase functions deploy places-cerca
   supabase secrets set PLACES_API_KEY=<tu_key_de_google_places>
   ```
3. **GitHub → Settings → Secrets → Actions** (editar los existentes):
   - `SUPABASE_URL` → Project URL del proyecto nuevo
   - `SUPABASE_ANON_KEY` → anon key del proyecto nuevo
4. **Railway → pg-backend → Variables**:
   - `DATABASE_URL` → connection string del proyecto nuevo (pooler 6543 +
     `?sslmode=require`) → **redeploy**.
5. **Re-generar el APK** (push a la rama o correr el workflow): recién ahí el APK
   toma la URL/anon key nuevas (son compile-time por `--dart-define`). El APK ya
   instalado sigue apuntando al proyecto viejo hasta reinstalar el nuevo.
6. **Verificar**: abre la app, revisa que carguen canchas y que una reserva se
   guarde; en Railway, que el backend levante sin error de DB.
7. **Dar de baja el viejo**: una vez verificado, pausa o elimina el proyecto
   Supabase viejo. Eso es la "desconexión" definitiva.

## Notas
- El `ref` del proyecto está en la URL del dashboard: `app.supabase.com/project/<REF>`.
- Si migras data, primero importa (ver `backup_restore.md`) y luego flipea.
- El proyecto viejo y sus credenciales pegadas antes en el chat quedan obsoletos;
  puedes rotarlos/eliminarlos sin miedo una vez migrado.
