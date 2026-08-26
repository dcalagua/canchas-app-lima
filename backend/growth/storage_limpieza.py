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
# recargas/    = constancias de pago (registro contable/antifraude).
# ilustraciones/, bodega/packshot* = arte compartido, sin dueño individual.
PROTEGIDAS = ("recargas/", "ilustraciones/", "bodega/packshot")

# Una consulta por "familia" de archivos. Cada una devuelve (bucket, name) de lo
# que ya NO tiene dueño. Se escriben con LEFT JOIN (no NOT IN) a propósito: con
# NOT IN, un solo NULL en la subconsulta haría que NO devuelva NADA en silencio.
_CONSULTAS: dict[str, str] = {
    # Clips del entrenador: el análisis los borra solo; >1 h = quedó colgado.
    "entrenador": """
        select 'canchas', o.name from storage.objects o
        where o.bucket_id = 'canchas' and o.name like 'entrenador/%'
          and o.created_at < now() - interval '1 hour'
    """,
    # Foto de portada de cancha: `<id>.jpg` en la raíz del bucket.
    "canchas_portada": """
        select 'canchas', o.name from storage.objects o
        left join pichangol_canchas c
               on c.id::text = replace(o.name, '.jpg', '')
              and coalesce(c.eliminada, false) = false
        where o.bucket_id = 'canchas' and position('/' in o.name) = 0
          and c.id is null
    """,
    # Galería de cancha: `<id>/<algo>.jpg`.
    "canchas_galeria": """
        select 'canchas', o.name from storage.objects o
        left join pichangol_canchas c
               on c.id::text = split_part(o.name, '/', 1)
              and coalesce(c.eliminada, false) = false
        where o.bucket_id = 'canchas' and position('/' in o.name) > 0
          and split_part(o.name, '/', 1) not in
              ('entrenador', 'bodega', 'campeonatos', 'recargas', 'ilustraciones')
          and c.id is null
    """,
    "bodega": """
        select 'canchas', o.name from storage.objects o
        left join pichangol_bodega_productos p
               on p.id::text = replace(replace(o.name, 'bodega/', ''), '.jpg', '')
              and coalesce(p.eliminado, false) = false
        where o.bucket_id = 'canchas' and o.name like 'bodega/%'
          and o.name not like 'bodega/packshot%'
          and p.id is null
    """,
    "campeonatos": """
        select 'canchas', o.name from storage.objects o
        left join pichangol_campeonatos t
               on t.id::text = replace(replace(o.name, 'campeonatos/', ''), '.jpg', '')
              and coalesce(t.eliminado, false) = false
        where o.bucket_id = 'canchas' and o.name like 'campeonatos/%'
          and t.id is null
    """,
    # Historias: la fila vive 24 h; su media debe morir con ella.
    "estados": """
        select 'estados', o.name from storage.objects o
        left join pichangol_estados e
               on e.id::text = regexp_replace(o.name, '\\.(jpg|mp4)$', '')
              and e.creado_en >= now() - interval '24 hours'
        where o.bucket_id = 'estados' and e.id is null
    """,
    "productos": """
        select 'productos', o.name from storage.objects o
        left join pichangol_productos p
               on p.id::text = replace(o.name, '.jpg', '')
        where o.bucket_id = 'productos' and p.id is null
    """,
    # Avatares: se versionan por timestamp; sobrevive solo el más nuevo de cada
    # usuario (la media de los chats NO entra: es historia compartida).
    "avatares_viejos": """
        select 'chat', o.name from storage.objects o
        where o.bucket_id = 'chat' and o.name like 'perfiles/%'
          and o.name <> (
            select max(o2.name) from storage.objects o2
            where o2.bucket_id = 'chat' and o2.name like 'perfiles/%'
              and split_part(o2.name, '/', 2) = split_part(o.name, '/', 2))
    """,
    # Doc/selfie de identidad que ya nadie referencia (minimización, Ley 29733).
    "verificacion": """
        select 'verificacion', o.name from storage.objects o
        left join pichangol_verificaciones v
               on o.name in (v.doc_path, v.selfie_path)
        where o.bucket_id = 'verificacion' and v.email is null
    """,
}


def _protegido(bucket: str, name: str) -> bool:
    """Cinturón de seguridad final: aunque una consulta se equivoque, estas
    rutas no se borran nunca."""
    return bucket == "canchas" and name.startswith(PROTEGIDAS)


def analizar() -> dict:
    """DRY-RUN: cuántos huérfanos hay por familia y unos ejemplos. No borra."""
    if not pg.habilitado:
        return {"ok": False, "error": "sin_base_de_datos"}
    por_familia: dict[str, dict] = {}
    total = 0
    try:
        with pg._conn() as conn, conn.cursor() as cur:
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
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True, "total": total, "familias": por_familia}


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
