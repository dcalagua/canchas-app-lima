-- ============================================================================
-- Pichangol · Endurecer las funciones trigger de push (sep-2026)
-- ----------------------------------------------------------------------------
-- `notificar_push_mensaje`, `notificar_push_aviso` y `notificar_push_matricula`
-- son SECURITY DEFINER (llaman a pg_net para invocar la Edge Function de push)
-- y nacieron con EXECUTE para PUBLIC/anon/authenticated. Eso las deja
-- invocables desde `POST /rest/v1/rpc/notificar_push_*` con la anon key (el
-- linter de Supabase lo marca). Fuera de un trigger fallan ("trigger functions
-- can only be called as triggers"), pero no hay motivo para exponerlas.
--
-- Revocar EXECUTE NO afecta a los triggers: Postgres exige EXECUTE al CREAR el
-- trigger, no al dispararlo. Se comprobó en una tabla desechable (INSERT como
-- `anon` → el trigger disparó igual; la llamada directa como `anon` →
-- "permission denied"). Los triggers siguen corriendo como dueño (postgres)
-- por ser SECURITY DEFINER.
--
-- OJO: no todos los proyectos tienen las tres funciones (en QAS el push de
-- avisos va por Database Webhook y `notificar_push_aviso()` NO existe; el
-- SQL Editor corre todo en UNA transacción, así que un "does not exist"
-- anula el script entero). Por eso se revoca solo lo que exista.
-- Idempotente. Aplicado en PRD el 12-sep-2026.
-- ============================================================================

do $$
declare f text;
begin
  foreach f in array array['notificar_push_mensaje', 'notificar_push_aviso', 'notificar_push_matricula'] loop
    if to_regprocedure('public.' || f || '()') is not null then
      execute format('revoke execute on function public.%I() from public, anon, authenticated', f);
      raise notice 'revocado: %', f;
    else
      raise notice 'no existe (se omite): %', f;
    end if;
  end loop;
end $$;

-- Verificación: la ACL de las que existan ya no debe listar `anon=`,
-- `authenticated=` ni `=X` (solo postgres y service_role).
select p.proname, p.prosecdef as security_definer, array_to_string(p.proacl, ' | ') as acl,
       (select count(*) from pg_trigger t where t.tgfoid = p.oid and not t.tgisinternal) as triggers_activos
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname like 'notificar_push_%' order by 1;
