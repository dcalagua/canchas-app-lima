-- ============================================================================
-- Pichangol · Permitir que la app GUARDE academias/matrículas en la nube
-- ----------------------------------------------------------------------------
-- Síntoma que resuelve: el profe edita su academia, da Guardar, y al reingresar
-- vuelve a salir lo viejo (la nube no aceptó el cambio y la recarga lo revirtió).
--
-- Causas típicas y su arreglo (todo idempotente; puedes correrlo varias veces):
--   1) `id` no es único  -> el upsert (onConflict: id) no puede ACTUALIZAR la
--      fila y falla / duplica. Aquí le ponemos un UNIQUE.
--   2) RLS sin política de UPDATE/INSERT -> Supabase rechaza el guardado con la
--      llave anon del APK. Aquí abrimos políticas permisivas para el PILOTO.
--
-- Corre esto en Supabase -> SQL Editor del proyecto de Pichangol.
-- Nota: son políticas PERMISIVAS (piloto). Se endurecen luego con auth real.
-- ============================================================================

-- === 1) Unicidad de `id` (necesaria para el upsert por id) ==================
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'pichangol_academias_id_key'
  ) then
    alter table public.pichangol_academias
      add constraint pichangol_academias_id_key unique (id);
  end if;
exception when others then
  -- si ya hay filas duplicadas, primero corre docs/piloto/limpiar_pruebas.sql
  raise notice 'No se pudo crear UNIQUE(id): %', sqlerrm;
end $$;

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'pichangol_matriculas_id_key'
  ) then
    alter table public.pichangol_matriculas
      add constraint pichangol_matriculas_id_key unique (id);
  end if;
exception when others then
  raise notice 'No se pudo crear UNIQUE(id) en matriculas: %', sqlerrm;
end $$;

-- === 2) RLS: permitir leer/escribir con la llave anon (piloto) ==============
alter table public.pichangol_academias  enable row level security;
alter table public.pichangol_matriculas enable row level security;

-- Academias: una sola política ALL (select/insert/update/delete) permisiva.
drop policy if exists pichangol_academias_todo on public.pichangol_academias;
create policy pichangol_academias_todo
  on public.pichangol_academias
  for all
  using (true)
  with check (true);

-- Matrículas: idem.
drop policy if exists pichangol_matriculas_todo on public.pichangol_matriculas;
create policy pichangol_matriculas_todo
  on public.pichangol_matriculas
  for all
  using (true)
  with check (true);

-- === 3) Verificación rápida =================================================
-- Debe listar las políticas recién creadas.
select tablename, policyname, cmd
from pg_policies
where tablename in ('pichangol_academias', 'pichangol_matriculas')
order by tablename, policyname;
