-- CanchaLibre · 0002 · REGLAS DE RESERVA por cancha (plan nocturno A2).
-- Horario por día, cierres, franjas de precio, recargo de luz, ventana de
-- anticipación, turnos mín./máx., tope por jugador y cancelación del club.
-- Lo escribe SOLO el backend (`PUT /reservas/reglas`, dueño verificado); el APK
-- la LEE. Una cancha sin reglas (`{}`) se comporta exactamente como antes.
-- Idempotente.
alter table public.pichangol_canchas
  add column if not exists reglas_reserva jsonb not null default '{}'::jsonb;

-- El APK escribe pichangol_canchas con la anon key: que NO pueda pisar las
-- reglas (solo el backend). Trigger en vez de permisos por columna para no
-- romper los upsert del APK que mandan la fila completa.
create or replace function public.cl_reglas_solo_backend() returns trigger
language plpgsql as $$
begin
  if current_user in ('anon', 'authenticated') then
    if tg_op = 'INSERT' then
      new.reglas_reserva := '{}'::jsonb;
    else
      new.reglas_reserva := old.reglas_reserva;
    end if;
  end if;
  return new;
end $$;
drop trigger if exists trg_cl_reglas_solo_backend on public.pichangol_canchas;
create trigger trg_cl_reglas_solo_backend
  before insert or update on public.pichangol_canchas
  for each row execute function public.cl_reglas_solo_backend();

insert into public.cl_schema_migraciones (version, descripcion)
values ('0002', 'reglas_reserva por cancha') on conflict (version) do nothing;
