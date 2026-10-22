"""STOCK del Marketplace: apartar / devolver una unidad ANTES de cobrar.

Una sola fuente para la web (`web/jugador_market.py`) y el APK
(`POST /pagos/venta/apartar|devolver`, `producto_detalle_screen._comprar`):

- `apartar_unidad(id)` = UPDATE ATÓMICO sobre `pichangol_productos`: solo si
  sigue publicado y con stock (stock NULL = ilimitado, no se toca). Dos
  compradores no se llevan la última unidad.
- `devolver_unidad(id)` = el cobro no pasó: la unidad vuelve al stock.

El APK cobra en OTRA request (Culqi/Libélula/PayPhone desde el teléfono), así
que su apartado es IDEMPOTENTE y con estado (`stores.apartados_stock[id]`,
en el snapshot): `apartado → vendido | devuelto | vencido`. Reintentar el
mismo `apartado_id` no descuenta dos veces ni devuelve dos veces. Si el APK
muere entre apartar y cobrar, `liberar_vencidos()` (cron) devuelve la unidad a
los `TTL_MIN` minutos, salvo que exista la venta de ese producto a ese
comprador (el pago sí pasó y solo faltó avisar): entonces queda `vendido`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db import pg

TTL_MIN = 30          # Yape/PayPhone pueden tardar unos minutos en aprobar
_MAX_REGISTROS = 2000  # poda de los cerrados más viejos


def apartar_unidad(producto_id: str) -> bool:
    """Aparta 1 unidad (atómico). False si no está publicado, se agotó o no
    hay base."""
    if not pg.habilitado or not producto_id:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_productos SET stock = CASE WHEN stock IS NULL THEN NULL ELSE stock - 1 END "
                        "WHERE id = %s AND activo = true AND (stock IS NULL OR stock > 0)", (producto_id,))
            n = cur.rowcount
            conn.commit()
            return n == 1
    except Exception:  # noqa: BLE001
        return False


def devolver_unidad(producto_id: str) -> None:
    """El cobro no pasó: la unidad apartada vuelve al stock."""
    if not pg.habilitado or not producto_id:
        return
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_productos SET stock = stock + 1 WHERE id = %s AND stock IS NOT NULL", (producto_id,))
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def leer_producto(producto_id: str) -> dict | None:
    """{id, vendedor_email, activo, stock} o None (sin base / no existe)."""
    if not pg.habilitado or not producto_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, vendedor_email, activo, stock FROM pichangol_productos WHERE id = %s", (producto_id,))
            f = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not f:
        return None
    return {"id": f[0], "vendedor_email": (f[1] or "").strip().lower(), "activo": bool(f[2]),
            "stock": None if f[3] is None else int(f[3])}


# ── Apartado con estado (APK) ────────────────────────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _parse(s) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _registros() -> dict:
    from db.store import stores
    return stores.apartados_stock


def _podar(reg: dict) -> None:
    if len(reg) <= _MAX_REGISTROS:
        return
    cerrados = sorted((k for k, v in reg.items() if v.get("estado") != "apartado"),
                      key=lambda k: str(reg[k].get("en") or ""))
    for k in cerrados[: len(reg) - _MAX_REGISTROS]:
        reg.pop(k, None)


MENSAJES = {
    "agotado": "Se agotó. No se te cobró nada.",
    "no_disponible": "Este producto ya no está publicado. No se te cobró nada.",
    "propio": "Este producto es tuyo.",
    "datos_invalidos": "Faltan datos del producto.",
    "sin_servicio": "No pudimos reservar tu unidad ahora. Intenta de nuevo en un momento.",
}


def apartar(apartado_id: str, producto_id: str, email: str) -> dict:
    """Aparta una unidad para [email] bajo [apartado_id] (idempotente)."""
    aid = (apartado_id or "").strip()[:120]
    pid = (producto_id or "").strip()
    email = (email or "").strip().lower()
    if not aid or not pid or not email:
        return {"ok": False, "error": "datos_invalidos", "mensaje": MENSAJES["datos_invalidos"]}
    reg = _registros()
    ya = reg.get(aid)
    if ya is not None:
        if ya.get("producto_id") != pid or ya.get("email") != email:
            return {"ok": False, "error": "datos_invalidos", "mensaje": MENSAJES["datos_invalidos"]}
        if ya.get("estado") in ("apartado", "vendido"):
            return {"ok": True, "duplicado": True, "estado": ya["estado"]}
        # Devuelto o vencido: el mismo id no vuelve a apartar (un nuevo intento
        # de compra usa un id nuevo).
        return {"ok": False, "error": "cerrado", "estado": ya.get("estado"),
                "mensaje": "Ese intento de compra ya se cerró. Vuelve a tocar Comprar."}
    liberar_vencidos()
    p = leer_producto(pid)
    if p is None:
        if not pg.habilitado:
            return {"ok": False, "error": "sin_servicio", "mensaje": MENSAJES["sin_servicio"]}
        return {"ok": False, "error": "no_disponible", "mensaje": MENSAJES["no_disponible"]}
    if p["vendedor_email"] == email:
        return {"ok": False, "error": "propio", "mensaje": MENSAJES["propio"]}
    if not p["activo"]:
        return {"ok": False, "error": "no_disponible", "mensaje": MENSAJES["no_disponible"]}
    if p["stock"] is not None and p["stock"] <= 0:
        return {"ok": False, "error": "agotado", "mensaje": MENSAJES["agotado"]}
    if not apartar_unidad(pid):
        return {"ok": False, "error": "agotado",
                "mensaje": "Se agotó justo ahora o el vendedor lo pausó. No se te cobró nada."}
    reg[aid] = {"producto_id": pid, "email": email, "estado": "apartado",
                "ilimitado": p["stock"] is None, "en": _ahora().isoformat()}
    _podar(reg)
    return {"ok": True, "duplicado": False, "estado": "apartado"}


def devolver(apartado_id: str, email: str) -> dict:
    """El cobro no pasó: la unidad vuelve al stock (una sola vez)."""
    aid = (apartado_id or "").strip()[:120]
    email = (email or "").strip().lower()
    ya = _registros().get(aid)
    if ya is None or ya.get("email") != email:
        return {"ok": False, "error": "no_encontrado"}
    if ya.get("estado") != "apartado":
        return {"ok": True, "duplicado": True, "estado": ya.get("estado")}
    if not ya.get("ilimitado"):
        devolver_unidad(ya["producto_id"])
    ya["estado"] = "devuelto"
    ya["cerrado_en"] = _ahora().isoformat()
    return {"ok": True, "duplicado": False, "estado": "devuelto"}


def marcar_vendido(apartado_id: str, email: str = "") -> bool:
    """La venta se registró (`/pagos/venta` con `apartado_id`)."""
    ya = _registros().get((apartado_id or "").strip()[:120])
    if ya is None or (email and ya.get("email") != email.strip().lower()):
        return False
    if ya.get("estado") == "apartado":
        ya["estado"] = "vendido"
        ya["cerrado_en"] = _ahora().isoformat()
    return ya.get("estado") == "vendido"


def _hubo_venta(r: dict) -> bool:
    from db.store import stores
    desde = _parse(r.get("en"))
    for v in stores.ventas:
        if v.producto_id == r.get("producto_id") and (v.comprador_email or "").lower() == r.get("email"):
            en = v.creado_en if isinstance(v.creado_en, datetime) else _parse(v.creado_en)
            if en is not None and en.tzinfo is None:
                en = en.replace(tzinfo=timezone.utc)
            if desde is None or en is None or en >= desde - timedelta(minutes=1):
                return True
    return False


def liberar_vencidos(ahora: datetime | None = None) -> int:
    """Apartados de más de `TTL_MIN` sin cerrar: si hubo venta → vendido; si
    no → la unidad vuelve al stock (`vencido`). Devuelve cuántos cambió."""
    ahora = ahora or _ahora()
    n = 0
    for r in list(_registros().values()):
        if r.get("estado") != "apartado":
            continue
        en = _parse(r.get("en"))
        if en is not None and ahora - en < timedelta(minutes=TTL_MIN):
            continue
        if _hubo_venta(r):
            r["estado"] = "vendido"
        else:
            if not r.get("ilimitado"):
                devolver_unidad(r["producto_id"])
            r["estado"] = "vencido"
        r["cerrado_en"] = ahora.isoformat()
        n += 1
    return n
