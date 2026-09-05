-- Limpieza: fusiona los chats DIRECTOS duplicados (Pichangol)
--
-- Causa real: algunos mensajes directos viejos quedaron con el `hilo` en un
-- ORDEN de correos distinto al canónico (p. ej. `directo_B|A` en vez de
-- `directo_A|B`). Como la app agrupa por el string del hilo, la misma persona
-- aparece en DOS chats.
--
-- Solución: normalizar TODOS los hilos de mensajes DIRECTOS al formato canónico
-- `directo_<correo_menor>|<correo_mayor>` (correos en minúscula y ordenados),
-- igual que lo calcula la app. Así todo lo de dos personas cae en UN hilo.
-- Seguro e idempotente (solo re-ordena el hilo; no borra ni mezcla personas).
--
-- Correr en: Supabase → SQL Editor (proyecto del piloto).

-- 1) DIAGNÓSTICO: ¿hay más de un hilo entre dos personas? (ej. dcalagua/grupoebim)
select hilo, tipo, count(*) as n
from pichangol_mensajes
where lower(trim(autor_email)) in ('dcalagua@ebim.pe','grupoebim@gmail.com')
  and lower(trim(cuenta_email)) in ('dcalagua@ebim.pe','grupoebim@gmail.com')
group by hilo, tipo
order by n desc;

-- 2) NORMALIZAR todos los hilos directos al formato canónico (esto fusiona):
update pichangol_mensajes m
set hilo = 'directo_'
         || least(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
         || '|'
         || greatest(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
where m.tipo = 'directo'
  and coalesce(trim(m.autor_email), '') <> ''
  and coalesce(trim(m.cuenta_email), '') <> ''
  and lower(trim(m.autor_email)) <> lower(trim(m.cuenta_email))
  and m.hilo <> 'directo_'
         || least(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
         || '|'
         || greatest(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)));

-- 3) (Opcional) Llamadas 1:1 que quedaron como NO directo (academia/cancha):
--    mándalas también al hilo directo con la persona.
update pichangol_mensajes m
set tipo = 'directo', academia_id = '', ref_id = '',
    hilo = 'directo_'
         || least(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
         || '|'
         || greatest(lower(trim(m.autor_email)), lower(trim(m.cuenta_email)))
where m.tipo <> 'directo'
  and (m.texto like '%Videollamada%' or m.texto like '%Llamada de voz%'
       or m.texto like '%inició una llamada%')
  and m.texto not like '%grupal%'
  and coalesce(trim(m.autor_email), '') <> ''
  and coalesce(trim(m.cuenta_email), '') <> ''
  and lower(trim(m.autor_email)) <> lower(trim(m.cuenta_email));

-- ─────────────────────────────────────────────────────────────────────────────
-- 4) BORRAR chats de la academia DEMO "Jartur El Bosque" (seed_jartur_elbosque).
--    Era data de prueba y causaba una segunda entrada del mismo usuario.
--    (Ver primero, luego borrar.)

-- Ver:
select id, tipo, hilo, autor_email, cuenta_email, texto, creado
from pichangol_mensajes
where academia_id = 'seed_jartur_elbosque'
   or hilo like 'seed_jartur_elbosque|%';

-- Borrar:
delete from pichangol_mensajes
where academia_id = 'seed_jartur_elbosque'
   or hilo like 'seed_jartur_elbosque|%';

-- (Opcional) Si TODAS las academias 'seed_' son demo y quieres limpiar sus chats:
-- delete from pichangol_mensajes
-- where tipo = 'academia' and hilo like 'seed_%';
