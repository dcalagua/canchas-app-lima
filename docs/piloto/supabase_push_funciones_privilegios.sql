-- ============================================================================
-- Pichangol · Endurecer las funciones trigger de push (sep-2026)
-- ----------------------------------------------------------------------------
-- `notificar_push_mensaje`, `notificar_push_aviso` y `notificar_push_matricula`
-- son SECURITY DEFINER (llaman a pg_net para invocar la Edge Function de push)
-- y nacieron con EXECUTE para PUBLIC/anon/authenticated. Eso las deja
-- invocables desde `POST /rest/v1/rpc/notificar_push_*` con la anon key (el
-- linter de Supabase lo marca). Hoy no hacen daño llamadas a mano (fuera de un
-- trigger fallan con "trigger functions can only be called as triggers"), pero
-- no hay motivo para exponerlas.
--
-- Revocar EXECUTE NO afecta a los triggers: Postgres exige EXECUTE al CREAR el
-- trigger, no al dispararlo, y estos triggers ya existen. Se comprobó en una
-- tabla desechable (INSERT como `anon` → el trigger disparó igual; la llamada
-- directa como `anon` → "permission denied"). Los triggers siguen corriendo
-- como dueño (postgres) por ser SECURITY DEFINER.
--
-- Orden: correr en QAS (Supabase "Pichangol", SQL Editor) y probar un push
-- real (mandar un mensaje en el chat y ver que llega la notificación); luego
-- en PCG-PRD. Idempotente.
-- ============================================================================

revoke execute on function public.notificar_push_mensaje()   from public, anon, authenticated;
revoke execute on function public.notificar_push_aviso()     from public, anon, authenticated;
revoke execute on function public.notificar_push_matricula() from public, anon, authenticated;

-- Verificación: la ACL ya no debe listar `anon=` ni `authenticated=` ni `=X`.
select p.proname, array_to_string(p.proacl, ' | ') as acl
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname like 'notificar_push_%' order by 1;
