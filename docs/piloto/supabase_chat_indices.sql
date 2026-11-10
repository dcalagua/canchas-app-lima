-- Rendimiento del CHAT a escala. Correr en QAS y luego en PROD.
-- Con estos índices, "los últimos N mensajes de este hilo" es instantáneo
-- aunque la tabla tenga millones de filas (el app pagina de a 50, DESC + limit).

-- Hilo directo / grupo / cancha (columna `hilo`) -----------------------------
create index if not exists ix_msg_hilo_creado
  on public.pichangol_mensajes (hilo, creado desc);

-- Bandeja del profe por academia --------------------------------------------
create index if not exists ix_msg_academia_creado
  on public.pichangol_mensajes (academia_id, creado desc);

-- Inbox de directos/cancha por participante ----------------------------------
create index if not exists ix_msg_autor    on public.pichangol_mensajes (autor_email);
create index if not exists ix_msg_cuenta   on public.pichangol_mensajes (cuenta_email);

-- ─────────────────────────────────────────────────────────────────────────────
-- RETENCIÓN (control de costo). El costo grande NO es el texto (una fila ~200 B,
-- 1 millón ≈ 200-300 MB) sino la MEDIA en Storage (bucket `chat`: fotos + notas
-- de voz). Estrategia sugerida (ejecutar a mano o por cron cuando haya volumen):
--
--   -- 1) Borra mensajes de texto muy viejos (opcional, la nube sigue siendo el
--   --    respaldo del usuario mientras no exportemos a su Drive):
--   -- delete from public.pichangol_mensajes
--   --   where creado < now() - interval '12 months';
--
--   -- 2) La media vieja del bucket `chat` se poda desde Storage (por fecha del
--   --    path microsegundos) o con una función. Ese es el mayor ahorro.
-- ─────────────────────────────────────────────────────────────────────────────
