-- Pichangol · CANJE de puntos del jugador (economía aprobada por el director:
-- 100 puntos = S/ 3 de descuento en la próxima reserva ONLINE; 1 canje por
-- reserva; el dueño recibe su bruto completo — el descuento lo absorbe PCG de
-- su comisión del 5%).
-- ----------------------------------------------------------------------------
-- Los puntos GANADOS se derivan de las reservas (no hay contador); esta tabla
-- registra solo lo CANJEADO: disponibles = ganados − canjeados.
-- Idempotente. Ejecutar en Supabase → SQL Editor.

create table if not exists public.pichangol_puntos_canjes (
  id          bigint generated always as identity primary key,
  email       text        not null,
  puntos      integer     not null,            -- puntos consumidos (100)
  soles       numeric     not null default 0,  -- descuento aplicado (3.00)
  referencia  text        not null default '', -- cancha_fecha_hora de la reserva
  creado      timestamptz not null default now()
);

create index if not exists idx_puntos_canjes_email
  on public.pichangol_puntos_canjes (email);

alter table public.pichangol_puntos_canjes enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies
                  where schemaname = 'public'
                    and tablename = 'pichangol_puntos_canjes'
                    and cmd = 'SELECT') then
    create policy puntos_canjes_select on public.pichangol_puntos_canjes
      for select to anon, authenticated using (true);
  end if;
  if not exists (select 1 from pg_policies
                  where schemaname = 'public'
                    and tablename = 'pichangol_puntos_canjes'
                    and cmd = 'INSERT') then
    create policy puntos_canjes_insert on public.pichangol_puntos_canjes
      for insert to anon, authenticated with check (true);
  end if;
end $$;

-- Verificación:
select column_name from information_schema.columns
 where table_schema = 'public' and table_name = 'pichangol_puntos_canjes';
