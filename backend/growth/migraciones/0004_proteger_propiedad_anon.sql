-- CanchaLibre · 0004 · La anon key YA NO puede apropiarse de una cancha (C3).
--
-- Hallazgo crítico (auditoría 26-oct-2026): el APK escribe pichangol_canchas
-- con la anon key y la política es `for all to anon using (true)`. Cualquiera
-- que extraiga la anon key del APK podía poner `verificada = true` o cambiar el
-- `dueno` de una cancha ajena, saltándose TODO el flujo de propiedad (reclamo →
-- aprobación en la torre).
--
-- Este trigger NO cambia las políticas (los APKs en la calle siguen
-- funcionando): solo neutraliza, para los roles anon/authenticated, las
-- columnas que decide el BACKEND (rol postgres):
--   * verificada: anon nunca la sube a true (INSERT → false; UPDATE → se
--     conserva la anterior). La aprobación sigue llegando por el backend.
--   * dueno: anon solo puede ponerlo cuando está VACÍO (reclamar un legado /
--     registrar una cancha nueva); una vez asignado, no lo cambia.
-- Bajar `verificada` (reclamo rechazado) también lo hace el backend.
--
-- Plan de despliegue: correr en QAS, probar registrar/editar/reclamar desde
-- el APK, y recién ahí en PRD (con autorización del director). Idempotente.

create or replace function public.cl_proteger_propiedad_anon() returns trigger
language plpgsql as $$
begin
  if current_user not in ('anon', 'authenticated') then
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.verificada := false;
    return new;
  end if;
  new.verificada := old.verificada;
  if coalesce(old.dueno, '') <> '' then
    new.dueno := old.dueno;
  end if;
  return new;
end $$;

drop trigger if exists trg_cl_proteger_propiedad_anon on public.pichangol_canchas;
create trigger trg_cl_proteger_propiedad_anon
  before insert or update on public.pichangol_canchas
  for each row execute function public.cl_proteger_propiedad_anon();

insert into public.cl_schema_migraciones (version, descripcion)
values ('0004', 'anon no cambia verificada ni un dueno asignado en pichangol_canchas')
on conflict (version) do nothing;
