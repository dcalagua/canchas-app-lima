"""BARRIDO DE HUÉRFANOS EN SUPABASE STORAGE (herramienta del operador).

El APK ya borra cada archivo cuando muere su dueño lógico (cancha eliminada,
historia vencida, avatar reemplazado…). Esto es para lo ACUMULADO ANTES de esa
versión: archivos cuyo dueño ya no existe y que nadie va a borrar nunca.

Cómo funciona: busca los huérfanos por SQL contra `storage.objects` (precisión
total, sin paginar el API) y borra cada uno por el **Storage API** (borrado
físico real, no solo la fila). Requiere `DATABASE_URL` y las policies de DELETE
por bucket (docs/piloto/supabase_storage_limpieza.sql).

Siempre en dos tiempos: primero `analizar()` (dry-run: qué borraría) y solo si
el operador confirma, `limpiar()`. Nada aquí rompe el servicio: si falta la BD
o el storage responde mal, devuelve el detalle y sigue.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request

import config
from db import pg

# Carpetas del bucket `canchas` que NUNCA se tocan, pase lo que pase.
# recargas/     = constancias de pago (registro contable/antifraude).
# ilustraciones/, afiches/, bodega/packshot* = arte generado y COMPARTIDO por
# todo el sistema: no pertenece a ninguna fila, así que ninguna consulta de
# "huérfanos" debe poder alcanzarlo.
PROTEGIDAS = ("recargas/", "ilustraciones/", "afiches/", "bodega/packshot")

# PRINCIPIO DE ESTE MÓDULO: **nunca borrar lo que no se reconoce.**
#
# La primera versión hacía lo contrario: asumía que toda carpeta del bucket
# `canchas` era la galería de una cancha, salvo una lista de excepciones. Bastó
# que el backend empezara a guardar fondos de afiche en `afiches/` para que ese
# arte quedara marcado como huérfano. Por eso ahora cada consulta parte de una
# fila CONOCIDA (join contra la tabla dueña) y solo marca el archivo cuando esa
# fila dice explícitamente que murió. Un archivo que no corresponde a nada
# conocido NO se borra: se REPORTA aparte (`desconocidos`) para que el operador
# lo mire con calma.
#
# Los archivos referenciados por URL (media de posts y de chats) se cruzan
# contra la URL guardada en su fila, no adivinando ids desde el nombre.
_CONSULTAS: dict[str, str] = {
    # Clips del entrenador: el análisis los borra solo; >1 h = quedó colgado.
    # Efímeros por diseño, así que aquí sí vale la regla por antigüedad.
    "entrenador": """
        select 'canchas', o.name from storage.objects o
        where o.bucket_id = 'canchas' and o.name like 'entrenador/%'
          and o.created_at < now() - interval '1 hour'
    """,
    # Portada de una cancha BORRADA (`<id>.jpg` en la raíz). El join exige que
    # la cancha exista y esté marcada eliminada: un archivo suelto que no
    # corresponde a ninguna cancha se ignora.
    "canchas_portada": """
        select 'canchas', o.name from storage.objects o
        join pichangol_canchas c on c.id::text = replace(o.name, '.jpg', '')
        where o.bucket_id = 'canchas' and position('/' in o.name) = 0
          and coalesce(c.eliminada, false) = true
    """,
    # Galería de una cancha BORRADA (`<id>/<algo>.jpg`). Como el join es contra
    # el id real de la cancha, una carpeta del sistema (afiches/, recargas/…)
    # nunca puede colarse: no existe una cancha con ese id.
    "canchas_galeria": """
        select 'canchas', o.name from storage.objects o
        join pichangol_canchas c on c.id::text = split_part(o.name, '/', 1)
        where o.bucket_id = 'canchas' and position('/' in o.name) > 0
          and coalesce(c.eliminada, false) = true
    """,
    "bodega": """
        select 'canchas', o.name from storage.objects o
        join pichangol_bodega_productos p
          on p.id::text = replace(replace(o.name, 'bodega/', ''), '.jpg', '')
        where o.bucket_id = 'canchas' and o.name like 'bodega/%'
          and o.name not like 'bodega/packshot%'
          and coalesce(p.eliminado, false) = true
    """,
    "campeonatos": """
        select 'canchas', o.name from storage.objects o
        join pichangol_campeonatos t
          on t.id::text = replace(replace(o.name, 'campeonatos/', ''), '.jpg', '')
        where o.bucket_id = 'canchas' and o.name like 'campeonatos/%'
          and coalesce(t.eliminado, false) = true
    """,
    # Historias: la fila vive 24 h y luego se borra; su media debe morir con
    # ella. Efímeras por diseño = la regla por antigüedad es la correcta.
    "estados": """
        select 'estados', o.name from storage.objects o
        left join pichangol_estados e
               on e.id::text = regexp_replace(o.name, '\\.(jpg|mp4)$', '')
              and e.creado_en >= now() - interval '24 hours'
        where o.bucket_id = 'estados' and e.id is null
    """,
    # Marketplace: la fila se borra de verdad (no lógico), y el bucket sólo
    # tiene fotos de producto, sin carpetas de sistema.
    "productos": """
        select 'productos', o.name from storage.objects o
        left join pichangol_productos p on p.id::text = replace(o.name, '.jpg', '')
        where o.bucket_id = 'productos' and position('/' in o.name) = 0
          and p.id is null
    """,
    # Avatares: sobrevive el que el PERFIL realmente apunta, no "el más nuevo".
    # Antes se conservaba siempre el último archivo de cada usuario, así que la
    # foto quedaba para siempre aunque el perfil se hubiera borrado o ya no la
    # usara. Una imagen que ninguna fila referencia no se ve en ningún lado del
    # app: es basura (y, si es la foto de una persona, además un dato personal
    # que no corresponde conservar).
    "avatares": """
        select 'chat', o.name from storage.objects o
        left join pichangol_perfiles p on p.foto_url like '%' || o.name
        where o.bucket_id = 'chat' and o.name like 'perfiles/%'
          and position('/' in o.name) > 0 and p.email is null
    """,
    # Media de chats cuyos mensajes ya no existen (se borró la conversación).
    # Se cruza contra la URL guardada en el mensaje —incluida la de una cita—,
    # no adivinando el hilo desde el nombre de la carpeta.
    "chat_media": """
        select 'chat', o.name from storage.objects o
        left join pichangol_mensajes m
               on m.media_url like '%' || o.name
               or m.resp_media like '%' || o.name
        where o.bucket_id = 'chat' and o.name not like 'perfiles/%'
          and position('/' in o.name) > 0 and m.id is null
    """,
    # Portada de un canal que ya no existe.
    "canales_portada": """
        select 'canales', o.name from storage.objects o
        left join pichangol_canales c on c.id::text = split_part(o.name, '/', 1)
        where o.bucket_id = 'canales' and o.name like '%/portada.jpg'
          and c.id is null
    """,
    # Media de publicaciones de canal borradas (o de canales que ya no están).
    "canales_posts": """
        select 'canales', o.name from storage.objects o
        left join pichangol_canal_posts p on p.media_url like '%' || o.name
        where o.bucket_id = 'canales' and position('/' in o.name) > 0
          and o.name not like '%/portada.jpg' and p.id is null
    """,
    # Foto de un grupo que ya no existe.
    "grupos": """
        select 'grupos', o.name from storage.objects o
        left join pichangol_grupos g on g.id::text = replace(o.name, '.jpg', '')
        where o.bucket_id = 'grupos' and position('/' in o.name) = 0
          and g.id is null
    """,
    # Doc/selfie de identidad que ya nadie referencia (minimización, Ley 29733).
    "verificacion": """
        select 'verificacion', o.name from storage.objects o
        left join pichangol_verificaciones v on o.name in (v.doc_path, v.selfie_path)
        where o.bucket_id = 'verificacion' and v.email is null
    """,
}

# Archivos del bucket `canchas` que no son de ninguna cancha ni de una carpeta
# de sistema conocida. NO se borran: se muestran en la torre para que el
# operador decida. Es la contracara del principio: lo desconocido se reporta.
_SQL_DESCONOCIDOS = """
    select o.name from storage.objects o
    left join pichangol_canchas c
           on c.id::text = case when position('/' in o.name) > 0
                                then split_part(o.name, '/', 1)
                                else replace(o.name, '.jpg', '') end
    where o.bucket_id = 'canchas' and c.id is null
      and split_part(o.name, '/', 1) not in
          ('entrenador', 'bodega', 'campeonatos', 'recargas', 'ilustraciones',
           'afiches')
    limit 25
"""


def _protegido(bucket: str, name: str) -> bool:
    """Cinturón de seguridad final: aunque una consulta se equivoque, estas
    rutas no se borran nunca."""
    return bucket == "canchas" and name.startswith(PROTEGIDAS)


def _radiografia(cur) -> dict:
    """Qué ALCANZA A VER el barrido. Sin esto, un "0 huérfanos" es ambiguo: no
    se distingue "todo limpio" de "no veo ni un archivo" (permisos/RLS sobre
    `storage.objects`, o `DATABASE_URL` apuntando a otra base). Con esto el
    operador —y quien depure— lo ve de inmediato."""
    info: dict = {}
    try:
        cur.execute("select current_database()")
        info["base"] = cur.fetchone()[0]
    except Exception as e:  # noqa: BLE001
        info["base"] = f"?: {str(e)[:80]}"
    try:
        cur.execute("select bucket_id, count(*) from storage.objects "
                    "group by bucket_id order by bucket_id")
        info["objetos_por_bucket"] = {b: n for b, n in cur.fetchall()}
        info["objetos_vistos"] = sum(info["objetos_por_bucket"].values())
    except Exception as e:  # noqa: BLE001
        info["objetos_vistos"] = -1  # -1 = ni siquiera se pudo leer
        info["error_storage"] = str(e)[:160]
    return info


def analizar() -> dict:
    """DRY-RUN: cuántos huérfanos hay por familia y unos ejemplos. No borra.
    Incluye una radiografía de lo que el barrido alcanza a ver."""
    if not pg.habilitado:
        return {"ok": False, "error": "sin_base_de_datos"}
    por_familia: dict[str, dict] = {}
    total = 0
    radiografia: dict = {}
    try:
        with pg._conn() as conn, conn.cursor() as cur:
            radiografia = _radiografia(cur)
            for familia, sql in _CONSULTAS.items():
                try:
                    cur.execute(sql)
                    filas = [(b, n) for b, n in cur.fetchall()
                             if not _protegido(b, n)]
                except Exception as e:  # noqa: BLE001
                    # Una tabla que aún no existe en este ambiente no debe
                    # tumbar el barrido completo: se reporta y se sigue.
                    por_familia[familia] = {"error": str(e)[:160], "n": 0}
                    conn.rollback()
                    continue
                por_familia[familia] = {
                    "n": len(filas),
                    "ejemplos": [f"{b}/{n}" for b, n in filas[:5]],
                }
                total += len(filas)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "radiografia": radiografia}
    return {"ok": True, "total": total, "familias": por_familia,
            "radiografia": radiografia}


def _borrar_objeto(bucket: str, name: str) -> bool:
    """DELETE al Storage API (borrado físico). Requiere la policy del bucket."""
    base = (config.SUPABASE_URL or "").rstrip("/")
    if not base or not config.SUPABASE_ANON_KEY:
        return False
    if _protegido(bucket, name):
        return False
    ruta = urllib.parse.quote(name)
    req = urllib.request.Request(
        f"{base}/storage/v1/object/{bucket}/{ruta}",
        method="DELETE",
        headers={
            "apikey": config.SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {config.SUPABASE_ANON_KEY}",
        })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            r.read()
        return True
    except urllib.error.HTTPError as e:
        # 404 = ya no estaba: para el operador es el mismo resultado.
        return e.code == 404
    except Exception:  # noqa: BLE001
        return False


def limpiar(tope: int = 2000) -> dict:
    """Borra de verdad los huérfanos (hasta [tope] por corrida, para no colgar
    la request). Devuelve cuántos se borraron y cuántos fallaron."""
    prev = analizar()
    if not prev.get("ok"):
        return prev
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        return {"ok": False, "error": "sin_supabase"}
    borrados, fallidos, pendientes = 0, 0, 0
    with pg._conn() as conn, conn.cursor() as cur:
        for sql in _CONSULTAS.values():
            try:
                cur.execute(sql)
                filas = cur.fetchall()
            except Exception:  # noqa: BLE001
                conn.rollback()
                continue
            for bucket, name in filas:
                if _protegido(bucket, name):
                    continue
                if borrados + fallidos >= tope:
                    pendientes += 1
                    continue
                if _borrar_objeto(bucket, name):
                    borrados += 1
                else:
                    fallidos += 1
    return {"ok": True, "borrados": borrados, "fallidos": fallidos,
            "pendientes": pendientes, "detectados": prev.get("total", 0)}
