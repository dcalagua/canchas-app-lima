-- Limpieza: fusiona los chats duplicados por llamadas (Pichangol)
--
-- Antes, una llamada hecha desde un chat de academia/cancha quedaba en ESE
-- hilo, y aparecía como un chat separado del chat DIRECTO con la misma persona
-- (dos entradas del mismo usuario en el inbox). Desde el build nuevo, las
-- llamadas 1:1 siempre van al hilo directo; este SQL limpia las VIEJAS.
--
-- Qué hace: borra los AVISOS de llamada ("📹 Videollamada" / "📞 Llamada de voz")
-- que quedaron en hilos NO directos (academia/cancha/grupo). No toca ningún
-- mensaje de texto ni los avisos de llamada que ya están en el chat directo.
--
-- Correr en: Supabase → SQL Editor (con el proyecto del piloto).
-- Seguro e idempotente. Revisa primero con el SELECT, luego corre el DELETE.

-- 1) VER qué se va a borrar (opcional, para revisar):
select id, tipo, hilo, autor_email, cuenta_email, texto, creado
from pichangol_mensajes
where tipo <> 'directo'
  and (texto like '%Videollamada%' or texto like '%Llamada de voz%')
order by creado desc;

-- 2) BORRAR (esto es lo que limpia el inbox):
delete from pichangol_mensajes
where tipo <> 'directo'
  and (texto like '%Videollamada%' or texto like '%Llamada de voz%');
