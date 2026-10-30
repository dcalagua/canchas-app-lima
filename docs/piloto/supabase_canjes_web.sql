-- =====================================================================
-- Pichangol · CANJES DE LA RESERVA WEB: bono de horas y puntos Pichangol
-- (pedido del director, 1-oct-2026: "en la web el jugador debe poder usar
-- su bono y sus puntos al reservar, igual que en el app").
--
-- Libro de los beneficios que la reserva web APARTA mientras el jugador
-- paga (hold de 10 min) y que se confirman con el pago:
--   * tipo 'bono'   → horas descontadas de `pichangol_bonos_comprados`
--                      (en la MISMA transacción que este registro; `detalle`
--                      guarda {credito_id: horas} para devolverlas exactas).
--   * tipo 'puntos' → 100 puntos = S/ 3. Mientras está 'reservado' no pasa
--                      por `pichangol_puntos_canjes` (la tabla del APK): ahí
--                      se escribe recién con el pago aprobado, y una
--                      devolución por cancelación suma una fila negativa.
-- Estados: reservado → usado | devuelto. Un hold vencido, liberado o con el
-- pago rechazado vuelve a 'devuelto' y el jugador recupera lo apartado.
--
-- Solo lo usa el backend (rol postgres, dueño de la tabla): RLS activo SIN
-- políticas → la llave anon no la ve. Sin esta tabla la web no ofrece bono
-- ni puntos en el checkout (fail-safe); el app no la necesita.
-- Ejecutar en Supabase → SQL Editor (QAS y, con autorización, PRD).
-- IDEMPOTENTE.
-- =====================================================================

create table if not exists public.pichangol_canjes_web (
  id           text        primary key,
  tipo         text        not null check (tipo in ('bono', 'puntos')),
  email        text        not null,
  cancha_id    text        not null default '',
  club         text        not null default '',
  dueno        text        not null default '',
  reserva_ref  text        not null,
  reserva_ids  jsonb       not null default '[]'::jsonb,
  horas        int         not null default 0,      -- bono: turnos cubiertos
  puntos       int         not null default 0,      -- puntos: 100
  descuento    numeric     not null default 0,      -- soles: precio cubierto (bono) o 3.00 (puntos)
  moneda       text        not null default 'PEN',
  detalle      jsonb       not null default '{}'::jsonb,
  estado       text        not null default 'reservado' check (estado in ('reservado', 'usado', 'devuelto')),
  canal        text        not null default 'web',
  creado       timestamptz not null default now(),
  actualizado  timestamptz not null default now()
);

-- Un solo beneficio vivo de cada tipo por reserva.
create unique index if not exists uniq_canje_web_ref_tipo
  on public.pichangol_canjes_web (reserva_ref, tipo) where estado <> 'devuelto';
create index if not exists idx_canjes_web_email on public.pichangol_canjes_web (email, tipo, estado);
create index if not exists idx_canjes_web_estado on public.pichangol_canjes_web (estado, creado);

alter table public.pichangol_canjes_web enable row level security;

-- Verificación:
select column_name, data_type from information_schema.columns
 where table_schema = 'public' and table_name = 'pichangol_canjes_web'
 order by ordinal_position;
