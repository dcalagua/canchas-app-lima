-- Semilla del BARRIDO WEB (CI y base local de Docker). Datos de DEMOSTRACIÓN:
-- ids con prefijo demo_ y correos @e2e.canchalibre.test. NUNCA en QAS/PRD
-- (preparar_db.py se niega a correr fuera de localhost).
--
-- Fechas RELATIVAS a hoy en Lima (pg_temp.d(n) = hoy + n días) para que las
-- reservas "próximas" lo sigan siendo en cada corrida de CI.
-- {{BASE}} = URL del servidor bajo prueba (fotos servidas por el propio backend,
-- sin depender de internet).
--
-- Cuentas (WEB_USUARIOS_PRUEBA del job):
--   dueno@e2e.canchalibre.test    dueño de "CanchaLibre Arena Miraflores" y la academia
--   jugador@e2e.canchalibre.test  jugador con reservas en "La Bombonera" (otro dueño)

create or replace function pg_temp.d(n int) returns text language sql as
  $$ select to_char((now() at time zone 'America/Lima')::date + n, 'YYYY-MM-DD') $$;
create or replace function pg_temp.dm(n int) returns text language sql as
  $$ select to_char((now() at time zone 'America/Lima')::date + n, 'DD/MM') $$;

-- Idempotente: se puede volver a correr sobre la misma base.
delete from cl_pagos_manuales where id like 'demo\_%';
delete from cl_medios_pago_club where dueno like '%@e2e.canchalibre.test';
delete from pichangol_reservas where id like 'demo\_%';
delete from pichangol_bloqueos where cancha_id like 'demo\_%';
delete from pichangol_resenas where id like 'demo\_%';
delete from pichangol_canchas where id like 'demo\_%';
delete from pichangol_productos where id like 'demo\_%';
delete from pichangol_bonos where id like 'demo\_%';
delete from pichangol_partidos where id like 'demo\_%';
delete from pichangol_matriculas where id like 'demo\_%';
delete from pichangol_academias where id like 'demo\_%';
delete from pichangol_mensajes where id like 'demo\_%';
delete from pichangol_avisos where email like '%@e2e.canchalibre.test';
delete from pichangol_niveles where email like '%@e2e.canchalibre.test';
delete from pichangol_perfiles where email like '%@e2e.canchalibre.test';

-- ── locales y canchas ───────────────────────────────────────────────────────
insert into pichangol_canchas (id, nombre, club, distrito, deporte, deportes, precio_hora, lat, lng, direccion, registrada,
  foto_url, fotos, dueno, verificada, hora_apertura, hora_cierre, duracion_slot_min, amenidades, superficie, moneda, barrio,
  servicios_extra, sena_pct, descuento_valle, valle_desde, valle_hasta, reglas_reserva, permite_boleadores)
values
 ('demo_arena_f7', 'Fútbol 7', 'CanchaLibre Arena Miraflores', '', 'futbol', '["futbol"]', 150, -12.1189, -77.0342,
  'Av. Arequipa 4820, Miraflores', true, '{{BASE}}/static/brand/portada_facebook_820.png',
  '["{{BASE}}/static/brand/portada_facebook_820.png", "{{BASE}}/static/brand/portada_facebook.png"]',
  'dueno@e2e.canchalibre.test', true, '07:00', '23:00', 60, '["vestuario","duchas","parking","luces","cafeteria"]',
  'Grass sintético', 'S/', 'Miraflores',
  '[{"clave":"arbitro","precio":30,"nombre":"Árbitro","emoji":"🧑‍⚖️","tipo":"reserva","ambito":"cancha"},
    {"clave":"hidratacion","precio":3,"nombre":"Hidratación","emoji":"💧","tipo":"persona","ambito":"local"}]',
  0, 15, '07:00', '12:00',
  '{"cancelacion_horas": 12, "min_turnos": 1, "max_turnos": 3, "recargo_luz": {"desde": "18:00", "monto": 15}}', true),
 ('demo_arena_f5', 'Fútbol 5', 'CanchaLibre Arena Miraflores', '', 'futbol', '["futbol"]', 100, -12.1190, -77.0340,
  'Av. Arequipa 4820, Miraflores', true, '{{BASE}}/static/brand/portada_facebook.png', '["{{BASE}}/static/brand/portada_facebook.png"]',
  'dueno@e2e.canchalibre.test', true, '07:00', '23:00', 60, '["vestuario","parking","luces"]', 'Grass sintético', 'S/',
  'Miraflores', '[]', 0, 0, '', '', '{}', true),
 ('demo_raqueta_t1', 'Tenis 1', 'Club Raqueta San Isidro', '', 'tenis', '["tenis"]', 70, -12.0975, -77.0365,
  'Calle Los Laureles 365, San Isidro', true, '{{BASE}}/static/brand/portada_facebook_820.png',
  '["{{BASE}}/static/brand/portada_facebook_820.png"]', 'dueno@e2e.canchalibre.test', true, '06:00', '22:00', 60,
  '["vestuario","luces","alquiler"]', 'Arcilla', 'S/', 'San Isidro',
  '[{"clave":"pelotero","precio":25,"nombre":"Pelotero","emoji":"🎾","tipo":"turno","ambito":"cancha"}]', 30, 10,
  '06:00', '09:00', '{}', true),
 ('demo_bombo_f1', 'Cancha Principal', 'Complejo La Bombonera', '', 'futbol', '["futbol"]', 120, -12.0890, -77.0010,
  'Av. San Luis 2150, San Borja', true, '{{BASE}}/static/brand/portada_facebook.png', '["{{BASE}}/static/brand/portada_facebook.png"]',
  'club.bombonera@e2e.canchalibre.test', true, '08:00', '23:00', 60, '["vestuario","parking","luces"]', 'Grass sintético',
  'S/', 'San Borja', '[]', 0, 0, '', '', '{}', true);

-- ── perfiles y niveles ──────────────────────────────────────────────────────
insert into pichangol_perfiles (email, nombre, celular) values
 ('dueno@e2e.canchalibre.test', 'Dueño E2E', '987654321'),
 ('jugador@e2e.canchalibre.test', 'Jugador E2E', '987111222'),
 ('club.bombonera@e2e.canchalibre.test', 'Club La Bombonera', '986555666'),
 ('lucia@e2e.canchalibre.test', 'Lucía Ramírez', '987333444')
on conflict (email) do nothing;
insert into pichangol_niveles (email, deporte, nivel, partidos, victorias) values
 ('jugador@e2e.canchalibre.test', 'futbol', 3.4, 12, 7),
 ('jugador@e2e.canchalibre.test', 'tenis', 2.8, 5, 2),
 ('lucia@e2e.canchalibre.test', 'tenis', 3.1, 9, 4)
on conflict do nothing;

-- ── reservas ────────────────────────────────────────────────────────────────
-- Jugador en La Bombonera: próxima de 2 turnos (grupo), próxima en efectivo y dos pasadas.
insert into pichangol_reservas (id, cancha_id, jugador, fecha, dia, hora_inicio, hora_fin, estado, traida_por_app, precio,
  pagado, usuario, deporte, extras, telefono, grupo_reserva_id, moneda, medio_pago, created_at) values
 ('demo_r_0001', 'demo_bombo_f1', 'Jugador E2E', pg_temp.d(2), pg_temp.dm(2), '20:00', '21:00', 'confirmada', true, 120, true,
  'jugador@e2e.canchalibre.test', 'futbol', '[]', '987111222', 'grp_demo_g_0001', 'S/', 'tarjeta', now() - interval '1 day'),
 ('demo_r_0002', 'demo_bombo_f1', 'Jugador E2E', pg_temp.d(2), pg_temp.dm(2), '21:00', '22:00', 'confirmada', true, 120, true,
  'jugador@e2e.canchalibre.test', 'futbol', '[]', '987111222', 'grp_demo_g_0001', 'S/', 'tarjeta', now() - interval '1 day'),
 ('demo_r_0003', 'demo_bombo_f1', 'Jugador E2E', pg_temp.d(7), pg_temp.dm(7), '19:00', '20:00', 'confirmada', true, 120, false,
  'jugador@e2e.canchalibre.test', 'futbol', '[]', '987111222', '', 'S/', 'efectivo', now() - interval '1 day'),
 ('demo_r_0004', 'demo_bombo_f1', 'Jugador E2E', pg_temp.d(-5), pg_temp.dm(-5), '21:00', '22:00', 'confirmada', true, 120, true,
  'jugador@e2e.canchalibre.test', 'futbol', '[]', '987111222', '', 'S/', 'yape', now() - interval '7 days'),
 ('demo_r_0005', 'demo_arena_f7', 'Jugador E2E', pg_temp.d(-9), pg_temp.dm(-9), '08:00', '09:00', 'confirmada', true, 150, true,
  'jugador@e2e.canchalibre.test', 'futbol', '[]', '987111222', '', 'S/', 'efectivo', now() - interval '11 days');

-- Agenda del dueño: hoy, mañana, la semana y pasadas (online, efectivo, manual, no-show).
insert into pichangol_reservas (id, cancha_id, jugador, fecha, dia, hora_inicio, hora_fin, estado, traida_por_app, precio,
  pagado, usuario, deporte, extras, telefono, grupo_reserva_id, moneda, medio_pago, created_at) values
 ('demo_r_0101', 'demo_arena_f7', 'Lucía Ramírez', pg_temp.d(0), pg_temp.dm(0), '22:00', '23:00', 'confirmada', true, 165, true,
  'lucia@e2e.canchalibre.test', 'futbol',
  '[{"clave":"arbitro","precio":30,"unitario":30,"cantidad":1,"nombre":"Árbitro","emoji":"🧑‍⚖️","tipo":"reserva"}]',
  '987333444', '', 'S/', 'yape', now() - interval '2 days'),
 ('demo_r_0102', 'demo_arena_f7', 'Carlos Mendoza', pg_temp.d(1), pg_temp.dm(1), '19:00', '20:00', 'confirmada', true, 165, false,
  'carlos@e2e.canchalibre.test', 'futbol', '[]', '987555666', '', 'S/', 'efectivo', now() - interval '1 day'),
 ('demo_man_0103', 'demo_arena_f5', 'Diego Torres', pg_temp.d(1), pg_temp.dm(1), '20:00', '21:00', 'confirmada', false, 100, false,
  '', 'futbol', '[]', '987777888', '', 'S/', 'manual', now() - interval '1 day'),
 ('demo_r_0104', 'demo_raqueta_t1', 'Lucía Ramírez', pg_temp.d(3), pg_temp.dm(3), '07:00', '08:00', 'confirmada', true, 63, true,
  'lucia@e2e.canchalibre.test', 'tenis', '[]', '987333444', '', 'S/', 'tarjeta', now() - interval '1 day'),
 ('demo_r_0105', 'demo_arena_f7', 'Carlos Mendoza', pg_temp.d(-2), pg_temp.dm(-2), '20:00', '21:00', 'confirmada', true, 165, true,
  'carlos@e2e.canchalibre.test', 'futbol', '[]', '987555666', '', 'S/', 'tarjeta', now() - interval '4 days'),
 ('demo_r_0106', 'demo_arena_f5', 'Diego Torres', pg_temp.d(-3), pg_temp.dm(-3), '18:00', '19:00', 'noShow', true, 100, false,
  'diego@e2e.canchalibre.test', 'futbol', '[]', '987777888', '', 'S/', 'efectivo', now() - interval '5 days'),
 ('demo_v_0107', 'demo_arena_f7', 'Lucía Ramírez', pg_temp.d(4), pg_temp.dm(4), '18:00', '19:00', 'nueva', true, 165, false,
  'lucia@e2e.canchalibre.test', 'futbol', '[]', '987333444', '', 'S/', 'voucher', now());

insert into pichangol_bloqueos (cancha_id, fecha, hora) values ('demo_arena_f7', pg_temp.d(1), '12:00') on conflict do nothing;

-- ── cobro directo del club: medios + un comprobante por confirmar ────────────
insert into cl_medios_pago_club (dueno, tipo, titular, numero, banco, cuenta, cci, nota, activo, orden) values
 ('dueno@e2e.canchalibre.test', 'yape', 'CanchaLibre Arena SAC', '987654321', '', '', '', 'Pon tu nombre en el mensaje', true, 0),
 ('dueno@e2e.canchalibre.test', 'transferencia', 'CanchaLibre Arena SAC', '', 'BCP', '19123456789012', '00219100123456789012', '',
  true, 1);
insert into cl_pagos_manuales (id, reserva_ref, reserva_ids, cancha_id, dueno, jugador_email, jugador_nombre, monto_centimos,
  moneda, medio, operacion, voucher_img, voucher_mime, voucher_hash, estado, vence_en) values
 ('demo_pgm_1', 'demo_v_0107', '["demo_v_0107"]', 'demo_arena_f7', 'dueno@e2e.canchalibre.test', 'lucia@e2e.canchalibre.test',
  'Lucía Ramírez', 16500, 'PEN', 'yape', '84512367',
  decode('/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4pLSwzOko+MzZGNywtQFdBRkxOUlNSMj5aYVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAARCABAADADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDAooor2jvCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//2Q==', 'base64'),
  'image/jpeg', 'demo_e2e_1', 'en_revision', now() + interval '7 days');

-- ── reseñas ─────────────────────────────────────────────────────────────────
insert into pichangol_resenas (id, cancha_id, autor_email, autor_nombre, estrellas, comentario, creado) values
 ('demo_res_1', 'demo_arena_f7', 'lucia@e2e.canchalibre.test', 'Lucía Ramírez', 5, 'Excelente cancha, buena iluminación.',
  now() - interval '10 days'),
 ('demo_res_2', 'demo_arena_f7', 'carlos@e2e.canchalibre.test', 'Carlos Mendoza', 4, 'Vestuarios limpios.', now() - interval '20 days'),
 ('demo_res_3', 'demo_bombo_f1', 'lucia@e2e.canchalibre.test', 'Lucía Ramírez', 5, 'Muy buena atención.', now() - interval '3 days');

-- ── Mi tienda / marketplace y bonos ─────────────────────────────────────────
insert into pichangol_productos (id, vendedor_email, vendedor_nombre, nombre, descripcion, precio, moneda, categoria, foto_url,
  stock, activo) values
 ('demo_prod_1', 'dueno@e2e.canchalibre.test', 'Dueño E2E', 'Pelota talla 5', 'Pelota de fútbol para grass sintético.', 89,
  'S/', 'pelotas', '{{BASE}}/static/brand/logo_pichangol.png', 12, true),
 ('demo_prod_2', 'dueno@e2e.canchalibre.test', 'Dueño E2E', 'Tubo de pelotas x3', 'Pelotas de tenis.', 25, 'S/', 'pelotas',
  null, null, true);
insert into pichangol_bonos (id, dueno, club, nombre, horas, precio, activo) values
 ('demo_bono_1', 'dueno@e2e.canchalibre.test', 'CanchaLibre Arena Miraflores', 'Pack 5 horas', 5, 650, true);

-- ── Juega ya ────────────────────────────────────────────────────────────────
insert into pichangol_partidos (id, creador_email, creador_nombre, deporte, titulo, fecha, hora, sede_nombre, lat, lng, cupos,
  tipo, modalidad, nivel, etiquetas, cancha_id) values
 ('demo_part_1', 'lucia@e2e.canchalibre.test', 'Lucía Ramírez', 'futbol', 'Fut 7 · CanchaLibre Arena Miraflores', pg_temp.d(1),
  '20:00', 'CanchaLibre Arena Miraflores', -12.1189, -77.0342, 6, 'partido', '', 'intermedio', '["cancha_reservada"]',
  'demo_arena_f7'),
 ('demo_part_2', 'lucia@e2e.canchalibre.test', 'Lucía Ramírez', 'tenis', 'Singles de tenis · Club Raqueta San Isidro',
  pg_temp.d(2), '07:00', 'Club Raqueta San Isidro', -12.0975, -77.0365, 2, 'partner', 'singles', 'intermedio',
  '["llevo_pelotas"]', 'demo_raqueta_t1');

-- ── academia + alumnos (el jugador está matriculado) ────────────────────────
insert into pichangol_academias (id, dueno, data) values ('demo_ac_raqueta', 'dueno@e2e.canchalibre.test', jsonb_build_object(
  'id', 'demo_ac_raqueta', 'nombre', 'Academia Raqueta San Isidro', 'deporte', 'tenis', 'dueno', 'dueno@e2e.canchalibre.test',
  'descripcion', 'Tenis para niños y adultos.', 'sedeClub', 'Club Raqueta San Isidro', 'lat', -12.0975, 'lng', -77.0365,
  'zona', 'San Isidro', 'whatsapp', '987654321', 'moneda', 'S/', 'logoUrl', '{{BASE}}/static/brand/logo_pin.png',
  'fotos', jsonb_build_array('{{BASE}}/static/brand/portada_facebook_820.png'),
  'redes', jsonb_build_object('instagram', '@raqueta.e2e'),
  'planes', jsonb_build_array(
    jsonb_build_object('id', 'Bola Roja | 2x', 'nombre', 'Bola Roja · 2x/sem', 'tipo', 'mensual', 'precioMes', 220, 'meses', 1,
                       'programa', 'Bola Roja', 'frecuenciaSemana', 2, 'duracionClase', '1 h', 'horario', 'Mar y Jue 4pm'),
    jsonb_build_object('id', 'Adultos | 2x', 'nombre', 'Adultos · 2x/sem', 'tipo', 'mensual', 'precioMes', 280, 'meses', 1,
                       'programa', 'Adultos', 'frecuenciaSemana', 2, 'duracionClase', '1 h 30', 'horario', 'Mar y Jue 7pm')),
  'recargoInvitado', 50, 'descuentoHermano2', 10, 'descuentoHermano3', 15, 'descuentoPrepago', 5, 'mesesMinPrepago', 3,
  'descuentoFamiliar', true, 'cobroDirecto', jsonb_build_object('yape', '987654321', 'titular', 'Academia Raqueta SAC'),
  'sedes', '[]'::jsonb, 'horarios', '{}'::jsonb, 'preciosSede', '{}'::jsonb, 'partidos', '[]'::jsonb, 'categorias', '{}'::jsonb));
insert into pichangol_matriculas (id, academia_id, email, data) values
 ('demo_al_1', 'demo_ac_raqueta', 'jugador@e2e.canchalibre.test', jsonb_build_object(
   'id', 'demo_al_1', 'academiaId', 'demo_ac_raqueta', 'nombre', 'Jugador E2E', 'email', 'jugador@e2e.canchalibre.test',
   'whatsapp', '987111222', 'esSocioSede', true, 'ordenHermano', 1, 'sedeId', '',
   'cuotas', jsonb_build_array(
     jsonb_build_object('id', 'demo_cu_1_0', 'academiaId', 'demo_ac_raqueta', 'alumnoId', 'demo_al_1',
                        'concepto', 'Adultos · 2x/sem · mes anterior', 'monto', 280,
                        'vencimiento', pg_temp.d(-25) || 'T10:00:00.000', 'pagada', true,
                        'fechaPago', pg_temp.d(-26) || 'T12:00:00.000', 'operacionId', 'yape:demo1', 'medioPago', 'yape_directo'),
     jsonb_build_object('id', 'demo_cu_1_1', 'academiaId', 'demo_ac_raqueta', 'alumnoId', 'demo_al_1',
                        'concepto', 'Adultos · 2x/sem · este mes', 'monto', 280,
                        'vencimiento', pg_temp.d(5) || 'T10:00:00.000', 'pagada', false)))),
 ('demo_al_2', 'demo_ac_raqueta', 'lucia@e2e.canchalibre.test', jsonb_build_object(
   'id', 'demo_al_2', 'academiaId', 'demo_ac_raqueta', 'nombre', 'Mateo Ramírez', 'email', 'lucia@e2e.canchalibre.test',
   'edad', 9, 'apoderadoNombre', 'Lucía Ramírez', 'apoderadoWhatsapp', '987333444', 'parentesco', 'hijo',
   'esSocioSede', true, 'ordenHermano', 1, 'sedeId', '',
   'cuotas', jsonb_build_array(
     jsonb_build_object('id', 'demo_cu_2_0', 'academiaId', 'demo_ac_raqueta', 'alumnoId', 'demo_al_2',
                        'concepto', 'Bola Roja · 2x/sem · este mes', 'monto', 220,
                        'vencimiento', pg_temp.d(-3) || 'T10:00:00.000', 'pagada', false))));

-- ── chat jugador ↔ local y avisos ───────────────────────────────────────────
insert into pichangol_mensajes (id, hilo, academia_id, cuenta_email, autor_email, autor_nombre, es_profe, texto, creado, tipo, ref_id) values
 ('demo_msg_1', 'cancha_club.bombonera@e2e.canchalibre.test|jugador@e2e.canchalibre.test', '', 'jugador@e2e.canchalibre.test',
  'jugador@e2e.canchalibre.test', 'Jugador E2E', false, 'Hola, ¿tienen pecheras?', now() - interval '2 hours', 'cancha', 'club.bombonera@e2e.canchalibre.test'),
 ('demo_msg_2', 'cancha_club.bombonera@e2e.canchalibre.test|jugador@e2e.canchalibre.test', '', 'jugador@e2e.canchalibre.test',
  'club.bombonera@e2e.canchalibre.test', 'Club La Bombonera', true, 'Sí, te las dejamos en la cancha.',
  now() - interval '1 hour', 'cancha', 'club.bombonera@e2e.canchalibre.test'),
 ('demo_msg_3', 'cancha_dueno@e2e.canchalibre.test|lucia@e2e.canchalibre.test', '', 'lucia@e2e.canchalibre.test',
  'lucia@e2e.canchalibre.test', 'Lucía Ramírez', false, 'Ya mandé el comprobante del Yape.', now() - interval '30 minutes',
  'cancha', 'dueno@e2e.canchalibre.test');
insert into pichangol_avisos (email, titulo, cuerpo, tipo) values
 ('jugador@e2e.canchalibre.test', 'Reserva confirmada ⚽', 'Tu reserva en Complejo La Bombonera quedó confirmada.', 'reserva'),
 ('dueno@e2e.canchalibre.test', 'Nueva reserva 📅', 'Lucía reservó Fútbol 7 hoy a las 22:00.', 'reserva');
