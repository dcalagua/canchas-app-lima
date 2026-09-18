-- ============================================================================
-- Pichangol · search_path fijo en las funciones trigger de push (sep-2026)
-- ----------------------------------------------------------------------------
-- `notificar_push_mensaje`, `notificar_push_aviso` y `notificar_push_matricula`
-- son SECURITY DEFINER y llaman a `net.http_post` (pg_net). Sin `search_path`
-- fijo, el linter de Supabase avisa "function_search_path_mutable": una
-- función con permisos de dueño que resuelve nombres por el search_path del
-- que la llama. Fijarlo a `public, net` cierra ese aviso.
--
-- Idempotente y tolerante: solo altera las funciones que existan (en QAS no
-- hay `notificar_push_aviso()`: ahí el aviso va por Database Webhook).
-- ORDEN: primero QAS → mandar un mensaje/matrícula reales y confirmar que la
-- notificación llega → recién entonces PRD (con autorización del director).
-- ============================================================================

do $$
declare f text;
begin
  foreach f in array array['notificar_push_mensaje', 'notificar_push_aviso', 'notificar_push_matricula'] loop
    if to_regprocedure('public.' || f || '()') is not null then
      execute format('alter function public.%I() set search_path = public, net', f);
      raise notice 'search_path fijado: %', f;
    else
      raise notice 'no existe (se omite): %', f;
    end if;
  end loop;
end $$;

-- Verificación: `proconfig` debe mostrar {search_path=public, net} en todas.
select p.proname, p.prosecdef as security_definer, p.proconfig,
       (select count(*) from pg_trigger t where t.tgfoid = p.oid and not t.tgisinternal) as triggers_activos
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname like 'notificar_push_%' order by 1;
