-- Limpieza: consolida los chats duplicados por llamadas (Pichangol)
--
-- Problema: versiones anteriores posteaban el aviso de llamada 1:1 con un hilo
-- distinto (o "X inició una llamada"), y aparecía como un chat SEPARADO del chat
-- directo con la misma persona (el usuario sale 2 veces en el inbox).
--
-- Solución: re-apuntar TODOS los avisos de llamada 1:1 al hilo DIRECTO entre las
-- dos personas (autor_email ↔ cuenta_email). Así se fusionan en un solo chat.
-- NO borra nada: solo cambia hilo/tipo del aviso. Seguro e idempotente.
--
-- Correr en: Supabase → SQL Editor (proyecto del piloto).
-- Revisa primero con el SELECT (1), luego corre el UPDATE (2) y refresca la app.

-- 1) VER los avisos de llamada 1:1 y su hilo actual (para revisar):
select id, tipo, hilo, autor_email, cuenta_email, texto, creado
from pichangol_mensajes
where (texto like '%Videollamada%'
       or texto like '%Llamada de voz%'
       or texto like '%inició una llamada%')
  and texto not like '%grupal%'                 -- deja las llamadas de grupo
order by creado desc;

-- 2) CONSOLIDAR: manda cada aviso de llamada 1:1 al hilo directo de esas dos
--    personas (así se fusiona con su chat directo).
update pichangol_mensajes m
set tipo = 'directo',
    academia_id = '',
    ref_id = '',
    hilo = 'directo_'
         || least(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
         || '|'
         || greatest(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
where (m.texto like '%Videollamada%'
       or m.texto like '%Llamada de voz%'
       or m.texto like '%inició una llamada%')
  and m.texto not like '%grupal%'               -- no tocar llamadas de grupo
  and coalesce(trim(m.autor_email), '') <> ''
  and coalesce(trim(m.cuenta_email), '') <> ''
  and lower(trim(m.autor_email)) <> lower(trim(m.cuenta_email));

-- Nota: si algún aviso viejo NO tiene cuenta_email (columna vacía), no se puede
-- deducir con quién era la llamada; ese quedará igual. Si ves filas así en el
-- SELECT (1), pásame el resultado y te doy el ajuste exacto.
