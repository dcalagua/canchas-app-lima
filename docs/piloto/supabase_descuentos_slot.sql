-- DESCUENTOS POR TURNO PUNTUAL (hora feliz de una hora concreta).
-- Lo usan el APK (lib/data/descuentos_repo.dart, "Llenar cancha") y la web
-- (web/horarios.py al cobrar, web/jugador_partidos.py → /anfitrion/llenar).
-- Faltaba en PCG-PRD (el APK fallaba en silencio). Mismo esquema de acceso que
-- pichangol_bloqueos (el APK escribe con la llave anon).
-- Idempotente. Correr en QAS ("Pichangol") si allí tampoco existe.

create table if not exists public.pichangol_descuentos_slot (
  cancha_id text not null,
  fecha     text not null,   -- 'YYYY-MM-DD'
  hora      text not null,   -- 'HH:MM'
  pct       int  not null check (pct between 0 and 100),
  primary key (cancha_id, fecha, hora)
);

alter table public.pichangol_descuentos_slot enable row level security;

do $$ begin
  if not exists (select 1 from pg_policy where polname = 'descuentos_slot_lectura'
                 and polrelid = 'public.pichangol_descuentos_slot'::regclass) then
    create policy descuentos_slot_lectura on public.pichangol_descuentos_slot
      for select to anon, authenticated using (true);
  end if;
  if not exists (select 1 from pg_policy where polname = 'descuentos_slot_write'
                 and polrelid = 'public.pichangol_descuentos_slot'::regclass) then
    create policy descuentos_slot_write on public.pichangol_descuentos_slot
      for all to anon, authenticated using (true) with check (true);
  end if;
end $$;
