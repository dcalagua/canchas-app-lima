-- Pichangol · pichangol_canchas COMPLETA (todas las columnas que escribe el APK)
-- -----------------------------------------------------------------------------
-- El guardado de la cancha va EN PAQUETE: si falta UNA sola de estas columnas,
-- el primer upsert falla y el fail-safe reintenta SIN el paquete de columnas
-- nuevas (seña, tipo de piso, amenidades, hora feliz, servicios, barrio…). Como
-- la regla de sync es "la nube manda", lo local se pisa después y "se desmarca".
-- Este script asegura TODAS las columnas de una sola vez. Idempotente.
--
-- Ejecutar en Supabase → SQL Editor.

-- 1) Columnas (base + nuevas). "if not exists" = seguro correrlo mil veces.
alter table public.pichangol_canchas add column if not exists nombre            text not null default 'Cancha';
alter table public.pichangol_canchas add column if not exists club              text not null default '';
alter table public.pichangol_canchas add column if not exists distrito          text not null default 'sanBorja';
alter table public.pichangol_canchas add column if not exists deporte           text not null default 'futbol';
alter table public.pichangol_canchas add column if not exists precio_hora       numeric not null default 0;
alter table public.pichangol_canchas add column if not exists lat               double precision;
alter table public.pichangol_canchas add column if not exists lng               double precision;
alter table public.pichangol_canchas add column if not exists club_fundador     boolean not null default false;
alter table public.pichangol_canchas add column if not exists digitalizada      boolean not null default true;
alter table public.pichangol_canchas add column if not exists direccion         text;
alter table public.pichangol_canchas add column if not exists registrada        boolean not null default true;
alter table public.pichangol_canchas add column if not exists foto_url          text;
alter table public.pichangol_canchas add column if not exists fotos             jsonb not null default '[]'::jsonb;
alter table public.pichangol_canchas add column if not exists dueno             text not null default '';
alter table public.pichangol_canchas add column if not exists verificada        boolean not null default false;
alter table public.pichangol_canchas add column if not exists hora_apertura     text not null default '07:00';
alter table public.pichangol_canchas add column if not exists hora_cierre       text not null default '23:00';
alter table public.pichangol_canchas add column if not exists duracion_slot_min integer not null default 60;
alter table public.pichangol_canchas add column if not exists eliminada         boolean not null default false;
alter table public.pichangol_canchas add column if not exists amenidades        jsonb not null default '[]'::jsonb;
alter table public.pichangol_canchas add column if not exists superficie        text not null default '';
alter table public.pichangol_canchas add column if not exists deportes          jsonb not null default '[]'::jsonb;
alter table public.pichangol_canchas add column if not exists moneda            text not null default '';
alter table public.pichangol_canchas add column if not exists servicios_extra   jsonb not null default '[]'::jsonb;
alter table public.pichangol_canchas add column if not exists descuento_valle   integer not null default 0;
alter table public.pichangol_canchas add column if not exists sena_pct          integer not null default 0;
alter table public.pichangol_canchas add column if not exists barrio            text not null default '';

-- 2) RLS: para que el guardado persista, el APK (anon) necesita poder INSERTAR
--    y ACTUALIZAR. Solo crea la política si NO existe ninguna para ese verbo
--    (no pisa las tuyas si ya las definiste distinto).
do $$
begin
  if not exists (select 1 from pg_policies
                  where schemaname = 'public'
                    and tablename = 'pichangol_canchas' and cmd = 'INSERT') then
    create policy canchas_insert_app on public.pichangol_canchas
      for insert to anon, authenticated with check (true);
  end if;
  if not exists (select 1 from pg_policies
                  where schemaname = 'public'
                    and tablename = 'pichangol_canchas' and cmd = 'UPDATE') then
    create policy canchas_update_app on public.pichangol_canchas
      for update to anon, authenticated using (true) with check (true);
  end if;
end $$;

-- 3) VERIFICACIÓN — corre estos SELECT y revisa:
-- 3a) Deben salir TODAS las columnas de arriba.
select column_name
  from information_schema.columns
 where table_schema = 'public' and table_name = 'pichangol_canchas'
 order by column_name;

-- 3b) Políticas RLS vigentes (debe haber al menos INSERT y UPDATE).
select policyname, cmd, roles
  from pg_policies
 where schemaname = 'public' and tablename = 'pichangol_canchas';

-- 3c) TU cancha en vivo (cambia el texto por el nombre de tu local): mira si
--     sena_pct y superficie tienen lo que guardaste, y cuántas FILAS salen
--     (si salen varias del mismo lugar, hay duplicados → dedupe_canchas.sql).
select id, nombre, club, sena_pct, superficie, descuento_valle,
       duracion_slot_min, eliminada, dueno
  from public.pichangol_canchas
 where club ilike '%golazo%' or nombre ilike '%golazo%';
