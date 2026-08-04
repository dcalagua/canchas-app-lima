-- ============================================================================
-- Pichangol · DEJAR EN VIRGEN TOTAL  (⚠️ BORRA TODOS LOS DATOS DE SUPABASE)
-- ----------------------------------------------------------------------------
-- Vacía TODAS las tablas de datos de Pichangol + el snapshot del backend
-- (growth_state) + los archivos de Storage (fotos). NO borra las tablas ni las
-- políticas: solo su CONTENIDO, así la app sigue funcionando pero desde cero.
--
-- Úsalo cuando quieras dejar el ambiente REALMENTE virgen (piloto/pruebas).
-- Idempotente y a prueba de tablas faltantes (solo vacía las que existan).
--
-- Corre esto en Supabase → SQL Editor del proyecto de Pichangol.
-- NO recupera lo borrado. Asegúrate de estar en el proyecto correcto.
-- ============================================================================

-- 1) Vaciar todas las tablas de datos (TRUNCATE CASCADE: rápido y respeta FKs)
do $$
declare
  t text;
  tablas text[] := array[
    'pichangol_academias', 'pichangol_agenda', 'pichangol_avisos',
    'pichangol_bloqueos', 'pichangol_bonos', 'pichangol_bonos_comprados',
    'pichangol_campeonatos', 'pichangol_canal_posts', 'pichangol_canal_seguidores',
    'pichangol_canales', 'pichangol_canchas', 'pichangol_descuentos_slot',
    'pichangol_espera', 'pichangol_estados', 'pichangol_estados_vistas',
    'pichangol_grupo_miembros', 'pichangol_grupos', 'pichangol_invitaciones',
    'pichangol_lecturas', 'pichangol_matriculas', 'pichangol_mensajes',
    'pichangol_niveles', 'pichangol_partidos', 'pichangol_perfiles',
    'pichangol_presencia', 'pichangol_productos', 'pichangol_push_tokens',
    'pichangol_reacciones', 'pichangol_referidos', 'pichangol_resenas',
    'pichangol_reservas', 'pichangol_ubicacion_vivo', 'pichangol_verificaciones',
    -- snapshot del backend growth (reclamos de propiedad, pagos, saldos, etc.)
    'growth_state'
  ];
begin
  foreach t in array tablas loop
    if to_regclass('public.' || t) is not null then
      execute 'truncate table public.' || quote_ident(t) || ' cascade';
      raise notice 'Vaciada: %', t;
    end if;
  end loop;
end $$;

-- 2) Storage (fotos): Supabase NO permite borrar `storage.objects` por SQL
--    (error 42501). Las fotos quedan HUÉRFANAS e INVISIBLES (ya borramos las
--    filas que las referenciaban), así que no molestan. Si quieres borrarlas de
--    verdad, hazlo desde el dashboard: Storage → cada bucket (canchas, productos,
--    canales, estados, chat) → seleccionar archivos → Delete.

-- 3) Verificación rápida (todo debe dar 0):
select 'canchas' as tabla, count(*) from public.pichangol_canchas
union all select 'academias', count(*) from public.pichangol_academias
union all select 'campeonatos', count(*) from public.pichangol_campeonatos
union all select 'reservas', count(*) from public.pichangol_reservas
union all select 'growth_state', count(*) from public.growth_state;
