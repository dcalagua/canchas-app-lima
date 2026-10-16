"""MI BODEGA · capa de datos compartida por la web del DUEÑO
(`web/anfitrion_bodega.py`) y del JUGADOR (`web/jugador_bodega.py`).

Espejo exacto de `lib/data/bodega_repo.dart` sobre las MISMAS tablas de
Supabase (Postgres directo, sin RLS): `pichangol_bodega_productos`,
`pichangol_bodega_ventas`, `pichangol_bodega_pedidos`,
`pichangol_bodega_config` y `pichangol_bodega_cuentas` (SQL en
`docs/piloto/supabase_bodega*.sql`). Mismos ids (`bp_<µs>`, `bv_<µs>`,
`bpd_<µs>`, `bc_<µs>`), mismos JSON de ítems y los MISMOS candados de
concurrencia que el app (`cambiarEstadoPedidoSi`, `cerrarCuentaSi`,
`anotarACuenta`: UPDATE … WHERE estado = esperado → el primero gana).

Diferencias deliberadas (más correctas, compatibles con el app): el stock se
descuenta en el SERVIDOR con `greatest(stock - n, 0)` en la misma
transacción que la venta (el app manda el valor absoluto calculado en el
teléfono), y todo UPDATE lleva `lower(dueno) = <correo de la sesión>`.

Fail-safe: sin `DATABASE_URL` o ante un error → vacío / False / None.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone

from db import pg
from web import datos

ZONAS_DEFECTO = ["Cancha 1", "Cancha 2", "Mesa", "Mostrador"]
MEDIOS_CAJA = ("efectivo", "yape", "cortesia")
EXPIRA_MIN = 10  # un pendiente sin respuesta en 10 min se muestra EXPIRADO
TOPES = (50.0, 100.0, 200.0, 300.0, 0.0)  # chips del app (0 = sin tope)


# ── Utilidades ────────────────────────────────────────────────────────────────

def carta_id_de(email: str) -> str:
    """= `BodegaRepo.cartaIdDe`: FNV-1a de 32 bits, dos pasadas con seed
    distinta, sobre las unidades UTF-16 del correo en minúsculas. Estable
    entre app y web y NO expone el correo en `/b/{carta_id}`."""
    e = (email or "").strip().lower()
    unidades = [int.from_bytes(e.encode("utf-16-le")[i:i + 2], "little")
                for i in range(0, len(e.encode("utf-16-le")), 2)]

    def fnv(seed: int) -> int:
        h = (0x811C9DC5 ^ seed) & 0xFFFFFFFF
        for c in unidades:
            h ^= c
            h = (h * 0x01000193) & 0xFFFFFFFF
        return h

    return "b" + (f"{fnv(0):08x}" + f"{fnv(0x9E3779B9):08x}")[:12]


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}_{time.time_ns() // 1000}"


def _dt(v) -> datetime | None:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _items(v) -> list[dict]:
    out = []
    for i in datos._json_list(v):
        if not isinstance(i, dict):
            continue
        out.append({"producto_id": str(i.get("producto_id") or ""), "nombre": str(i.get("nombre") or ""),
                    "cantidad": int(i.get("cantidad") or 0), "precio": float(i.get("precio") or 0)})
    return out


def resumen(items: list[dict]) -> str:
    """= `PedidoBodega.resumen` / `CuentaBodega.resumen`: "2 Pilsen + 1 Agua"."""
    return " + ".join(f"{i['cantidad']} {i['nombre']}" for i in items)


def total_items(items: list[dict]) -> float:
    return round(sum(float(i["precio"]) * int(i["cantidad"]) for i in items), 2)


def expirado(p: dict) -> bool:
    """= `PedidoBodega.expirado`: pendiente sin respuesta hace ≥ 10 min."""
    c = p.get("creado")
    return p.get("estado") == "pendiente" and c is not None and (ahora() - c) >= timedelta(minutes=EXPIRA_MIN)


# ── Productos ─────────────────────────────────────────────────────────────────

_COLS_PROD = ["id", "dueno", "carta_id", "nombre", "categoria", "precio", "stock", "stock_min", "foto_url", "moneda"]


def _norm_prod(d: dict) -> dict:
    return {"id": d.get("id") or "", "dueno": (d.get("dueno") or "").lower(), "carta_id": d.get("carta_id") or "",
            "nombre": d.get("nombre") or "", "categoria": d.get("categoria") or "Otros",
            "precio": float(d.get("precio") or 0), "stock": int(d.get("stock") or 0),
            "stock_min": int(d.get("stock_min") or 0), "foto_url": d.get("foto_url") or "",
            "moneda": d.get("moneda") or "S/"}


def stock_bajo(p: dict) -> bool:
    return p["stock"] <= p["stock_min"]


def productos_de(dueno: str) -> list[dict]:
    """= `fetchProductos`: vigentes del dueño, orden categoría y nombre."""
    d = (dueno or "").strip().lower()
    if not pg.habilitado or not d:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_PROD)} FROM pichangol_bodega_productos "
                        "WHERE lower(dueno) = %s AND coalesce(eliminado,false) = false ORDER BY categoria, nombre", (d,))
            return [_norm_prod(pg._fila_a_dict(_COLS_PROD, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def producto_de(pid: str, dueno: str) -> dict | None:
    for p in productos_de(dueno):
        if p["id"] == pid:
            return p
    return None


def producto_existe_ajeno(pid: str, dueno: str) -> bool:
    """¿Existe ese id con OTRO dueño? (un upsert no debe pisar la fila ajena)."""
    if not pg.habilitado or not pid:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT lower(dueno) FROM pichangol_bodega_productos WHERE id = %s", (pid,))
            f = cur.fetchone()
            return bool(f) and (f[0] or "") != (dueno or "").strip().lower()
    except Exception:  # noqa: BLE001
        return False


def guardar_producto(p: dict) -> bool:
    """= `guardarProducto` (upsert por id). El ON CONFLICT solo actualiza si la
    fila es del MISMO dueño. Tolerante a schema drift: sin la columna `moneda`
    reintenta sin ella, como el app."""
    if not pg.habilitado:
        return False
    fila = {"id": p["id"], "dueno": p["dueno"], "carta_id": p["carta_id"], "nombre": p["nombre"],
            "categoria": p["categoria"], "precio": p["precio"], "stock": p["stock"], "stock_min": p["stock_min"],
            "foto_url": p.get("foto_url") or None, "moneda": p.get("moneda") or "S/", "eliminado": False}
    for intento in range(2):
        cols = [c for c in fila if not (intento == 1 and c == "moneda")]
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"INSERT INTO pichangol_bodega_productos ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                            f"ON CONFLICT (id) DO UPDATE SET {sets}, updated_at = now() "
                            "WHERE lower(pichangol_bodega_productos.dueno) = lower(EXCLUDED.dueno)",
                            [fila[c] for c in cols])
                ok = cur.rowcount > 0
                conn.commit()
                return ok
        except Exception:  # noqa: BLE001
            continue
    return False


def poner_foto(pid: str, dueno: str, url: str) -> bool:
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_bodega_productos SET foto_url = %s, updated_at = now() "
                        "WHERE id = %s AND lower(dueno) = %s", (url, pid, dueno.lower()))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception:  # noqa: BLE001
        return False


def eliminar_producto(pid: str, dueno: str) -> bool:
    """= `eliminarProducto`: borrado LÓGICO (sale de la carta y de la caja)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_bodega_productos SET eliminado = true, updated_at = now() "
                        "WHERE id = %s AND lower(dueno) = %s", (pid, dueno.lower()))
            ok = cur.rowcount > 0
            conn.commit()
            return ok
    except Exception:  # noqa: BLE001
        return False


def _descontar(cur, descuentos: dict[str, int], dueno: str) -> None:
    for pid, n in descuentos.items():
        if n > 0:
            cur.execute("UPDATE pichangol_bodega_productos SET stock = greatest(stock - %s, 0), updated_at = now() "
                        "WHERE id = %s AND lower(dueno) = %s", (int(n), pid, dueno.lower()))


def descuentos_de(items: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        if i["producto_id"]:
            out[i["producto_id"]] = out.get(i["producto_id"], 0) + int(i["cantidad"])
    return out


# ── Ventas ────────────────────────────────────────────────────────────────────

def registrar_venta(v: dict, descuentos: dict[str, int]) -> bool:
    """= `registrarVenta`: inserta la venta y DESCUENTA el stock (misma
    transacción). `descuentos` vacío = el stock ya bajó (cierre de cuenta)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO pichangol_bodega_ventas (id, dueno, items, total, medio_pago) "
                        "VALUES (%s, %s, %s::jsonb, %s, %s)",
                        (v["id"], v["dueno"], json.dumps(v["items"], ensure_ascii=False), v["total"], v["medio_pago"]))
            _descontar(cur, descuentos, v["dueno"])
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def descontar_stock(descuentos: dict[str, int], dueno: str) -> bool:
    """= `actualizarStock`: consumos anotados a una cuenta (la venta va al cierre)."""
    if not pg.habilitado or not descuentos:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            _descontar(cur, descuentos, dueno)
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def ventas_de(dueno: str, dias: int = 30) -> list[dict]:
    """= `fetchVentas` (más recientes primero, máx. 500)."""
    d = (dueno or "").strip().lower()
    if not pg.habilitado or not d:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, dueno, items, total, medio_pago, creado FROM pichangol_bodega_ventas "
                        "WHERE lower(dueno) = %s AND creado >= %s ORDER BY creado DESC LIMIT 500",
                        (d, ahora() - timedelta(days=dias)))
            return [{"id": f[0], "dueno": f[1], "items": _items(f[2]), "total": float(f[3] or 0),
                     "medio_pago": f[4] or "efectivo", "creado": _dt(f[5]) or ahora()} for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


# ── Configuración (pedidos a la cancha + cuenta abierta) ──────────────────────

def config_defecto(dueno: str) -> dict:
    return {"dueno": dueno, "acepta_pedidos": False, "zonas": list(ZONAS_DEFECTO),
            "permite_cuenta": False, "tope_cuenta": 100.0}


def config_de(dueno: str) -> dict:
    """= `fetchConfig`. Default: NO acepta pedidos (cada local decide)."""
    d = (dueno or "").strip().lower()
    cfg = config_defecto(d)
    if not pg.habilitado or not d:
        return cfg
    for cols in (["acepta_pedidos", "zonas", "permite_cuenta", "tope_cuenta"], ["acepta_pedidos", "zonas"]):
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_bodega_config WHERE lower(dueno) = %s LIMIT 1", (d,))
                f = cur.fetchone()
                if not f:
                    return cfg
                r = dict(zip(cols, f))
                zonas = [str(z) for z in datos._json_list(r.get("zonas")) if str(z).strip()]
                cfg.update(acepta_pedidos=bool(r.get("acepta_pedidos")), zonas=zonas or list(ZONAS_DEFECTO))
                if "permite_cuenta" in r:
                    cfg.update(permite_cuenta=bool(r.get("permite_cuenta")),
                               tope_cuenta=float(r["tope_cuenta"]) if r.get("tope_cuenta") is not None else 100.0)
                return cfg
        except Exception:  # noqa: BLE001
            continue
    return cfg


def guardar_config(cfg: dict) -> bool:
    """= `guardarConfig` (upsert). Sin las columnas de cuenta abierta reintenta
    sin ellas (y el llamador re-lee para avisar, como `_togglePermiteCuenta`)."""
    if not pg.habilitado:
        return False
    fila = {"dueno": cfg["dueno"], "acepta_pedidos": bool(cfg["acepta_pedidos"]),
            "zonas": json.dumps(cfg["zonas"], ensure_ascii=False),
            "permite_cuenta": bool(cfg["permite_cuenta"]), "tope_cuenta": float(cfg["tope_cuenta"])}
    for intento in range(2):
        cols = [c for c in fila if not (intento == 1 and c in ("permite_cuenta", "tope_cuenta"))]
        vals = ", ".join("%s::jsonb" if c == "zonas" else "%s" for c in cols)
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "dueno")
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"INSERT INTO pichangol_bodega_config ({', '.join(cols)}) VALUES ({vals}) "
                            f"ON CONFLICT (dueno) DO UPDATE SET {sets}, updated_at = now()", [fila[c] for c in cols])
                conn.commit()
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


# ── Pedidos a la cancha ───────────────────────────────────────────────────────

_COLS_PED = ["id", "dueno", "cliente", "cliente_nombre", "zona", "items", "total", "moneda", "estado", "creado", "pagado"]


def _norm_ped(d: dict) -> dict:
    return {"id": d.get("id") or "", "dueno": (d.get("dueno") or "").lower(), "cliente": (d.get("cliente") or "").lower(),
            "cliente_nombre": d.get("cliente_nombre") or "", "zona": d.get("zona") or "", "items": _items(d.get("items")),
            "total": float(d.get("total") or 0), "moneda": d.get("moneda") or "S/", "estado": d.get("estado") or "pendiente",
            "creado": _dt(d.get("creado")) or ahora(), "pagado": bool(d.get("pagado"))}


def _select_pedidos(where: str, params: tuple, limite: int) -> list[dict]:
    if not pg.habilitado:
        return []
    for cols in (_COLS_PED, _COLS_PED[:-1]):  # sin la columna `pagado` (falta supabase_bodega_pago.sql)
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"SELECT {', '.join(cols)} FROM pichangol_bodega_pedidos WHERE {where} "
                            f"ORDER BY creado DESC LIMIT {int(limite)}", params)
                return [_norm_ped(pg._fila_a_dict(cols, f)) for f in cur.fetchall()]
        except Exception:  # noqa: BLE001
            continue
    return []


def crear_pedido(p: dict) -> bool:
    """= `crearPedido`. Tolerante a la columna `pagado` SOLO si no va pagado:
    un pedido PAGADO es estricto (mejor no cobrar que cobrar dos veces)."""
    if not pg.habilitado:
        return False
    fila = {"id": p["id"], "dueno": p["dueno"], "cliente": p["cliente"], "cliente_nombre": p["cliente_nombre"],
            "zona": p["zona"], "items": json.dumps(p["items"], ensure_ascii=False), "total": p["total"],
            "moneda": p["moneda"], "estado": p.get("estado", "pendiente"), "pagado": bool(p.get("pagado"))}
    intentos = [list(fila)] + ([] if fila["pagado"] else [[c for c in fila if c != "pagado"]])
    for cols in intentos:
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                vals = ", ".join("%s::jsonb" if c == "items" else "%s" for c in cols)
                cur.execute(f"INSERT INTO pichangol_bodega_pedidos ({', '.join(cols)}) VALUES ({vals})", [fila[c] for c in cols])
                conn.commit()
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def pedidos_de_dueno(dueno: str) -> list[dict]:
    """= `fetchPedidosDueno`: últimos 2 días, máx. 100."""
    d = (dueno or "").strip().lower()
    if not d:
        return []
    return _select_pedidos("lower(dueno) = %s AND creado >= %s", (d, ahora() - timedelta(days=2)), 100)


def pedidos_de_cliente(cliente: str, dueno: str = "", dias: int = 30) -> list[dict]:
    """= `fetchPedidosCliente` (30 días, 50). Sin dueño = de todos los locales."""
    c = (cliente or "").strip().lower()
    if not c:
        return []
    if dueno:
        return _select_pedidos("lower(cliente) = %s AND lower(dueno) = %s AND creado >= %s",
                               (c, dueno.strip().lower(), ahora() - timedelta(days=dias)), 50)
    return _select_pedidos("lower(cliente) = %s AND creado >= %s", (c, ahora() - timedelta(days=dias)), 100)


def pedido(pid: str) -> dict | None:
    r = _select_pedidos("id = %s", (pid,), 1) if pid else []
    return r[0] if r else None


def cambiar_estado_si(pid: str, nuevo: str, *, desde: str, dueno: str = "", cliente: str = "") -> tuple[bool, str | None]:
    """= `cambiarEstadoPedidoSi`: cambia SOLO si sigue en [desde] (el primero
    gana). (True, None) = cambió; (False, actual) = otro le ganó; (False, None)
    = error / no existe. [dueno]/[cliente] restringen a filas propias."""
    if not pg.habilitado or not pid:
        return False, None
    extra, params = "", [nuevo, pid, desde]
    if dueno:
        extra += " AND lower(dueno) = %s"
        params.append(dueno.lower())
    if cliente:
        extra += " AND lower(cliente) = %s"
        params.append(cliente.lower())
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE pichangol_bodega_pedidos SET estado = %s, actualizado = now() "
                        f"WHERE id = %s AND estado = %s{extra} RETURNING estado", params)
            fila = cur.fetchone()
            conn.commit()
            if fila:
                return True, None
            cur.execute(f"SELECT estado FROM pichangol_bodega_pedidos WHERE id = %s{extra}", [pid] + params[3:])
            f = cur.fetchone()
            return False, (f[0] or "") if f else None
    except Exception:  # noqa: BLE001
        return False, None


def forzar_estado(pid: str, estado: str, dueno: str) -> bool:
    """= `actualizarEstadoPedido` (devolver a 'confirmado' si la venta no entró)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_bodega_pedidos SET estado = %s, actualizado = now() WHERE id = %s AND lower(dueno) = %s",
                        (estado, pid, dueno.lower()))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


# ── Cuenta abierta ────────────────────────────────────────────────────────────

_COLS_CTA = ["id", "dueno", "cliente", "cliente_nombre", "items", "total", "moneda", "estado", "medio_pago", "creado"]


def _norm_cta(d: dict) -> dict:
    return {"id": d.get("id") or "", "dueno": (d.get("dueno") or "").lower(), "cliente": (d.get("cliente") or "").lower(),
            "cliente_nombre": d.get("cliente_nombre") or "", "items": _items(d.get("items")),
            "total": float(d.get("total") or 0), "moneda": d.get("moneda") or "S/", "estado": d.get("estado") or "abierta",
            "medio_pago": d.get("medio_pago") or "", "creado": _dt(d.get("creado")) or ahora()}


def _select_cuentas(where: str, params: tuple, limite: int = 100) -> list[dict]:
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_CTA)} FROM pichangol_bodega_cuentas WHERE {where} "
                        f"ORDER BY creado DESC LIMIT {int(limite)}", params)
            return [_norm_cta(pg._fila_a_dict(_COLS_CTA, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def cuentas_de(dueno: str) -> list[dict]:
    """= `fetchCuentas`: últimos 30 días (abiertas y cerradas)."""
    d = (dueno or "").strip().lower()
    return _select_cuentas("lower(dueno) = %s AND creado >= %s", (d, ahora() - timedelta(days=30))) if d else []


def cuenta_abierta(cliente: str, dueno: str) -> dict | None:
    """= `fetchCuentaAbiertaCliente` ("llevas S/ X")."""
    c, d = (cliente or "").strip().lower(), (dueno or "").strip().lower()
    if not c or not d:
        return None
    r = _select_cuentas("lower(cliente) = %s AND lower(dueno) = %s AND estado = 'abierta'", (c, d), 1)
    return r[0] if r else None


def cuentas_abiertas_cliente(cliente: str) -> list[dict]:
    c = (cliente or "").strip().lower()
    return _select_cuentas("lower(cliente) = %s AND estado = 'abierta'", (c,), 20) if c else []


def anotar_a_cuenta(*, dueno: str, cliente: str, cliente_nombre: str, items: list[dict], moneda: str) -> dict | None:
    """= `anotarACuenta`: suma a la cuenta abierta (candado: solo si SIGUE
    abierta) o la crea. Devuelve la cuenta resultante o None."""
    if not pg.habilitado or not items:
        return None
    d, c = dueno.strip().lower(), cliente.strip().lower()
    agregado = total_items(items)
    abierta = cuenta_abierta(c, d)
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            if abierta is None:
                nueva = {"id": nuevo_id("bc"), "dueno": d, "cliente": c, "cliente_nombre": cliente_nombre,
                         "items": items, "total": agregado, "moneda": moneda, "estado": "abierta", "medio_pago": "",
                         "creado": ahora()}
                cur.execute("INSERT INTO pichangol_bodega_cuentas (id, dueno, cliente, cliente_nombre, items, total, moneda, estado, medio_pago) "
                            "VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, 'abierta', '')",
                            (nueva["id"], d, c, cliente_nombre, json.dumps(items, ensure_ascii=False), agregado, moneda))
                conn.commit()
                return nueva
            combinados = abierta["items"] + items
            total = round(abierta["total"] + agregado, 2)
            cur.execute("UPDATE pichangol_bodega_cuentas SET items = %s::jsonb, total = %s, actualizado = now() "
                        "WHERE id = %s AND estado = 'abierta' RETURNING id",
                        (json.dumps(combinados, ensure_ascii=False), total, abierta["id"]))
            ok = cur.fetchone() is not None
            conn.commit()
            if not ok:
                return None
            return dict(abierta, items=combinados, total=total)
    except Exception:  # noqa: BLE001
        return None


def cerrar_cuenta_si(cid: str, medio: str, dueno: str) -> bool:
    """= `cerrarCuentaSi`: solo si sigue abierta (con dos equipos, uno cobra)."""
    if not pg.habilitado:
        return False
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE pichangol_bodega_cuentas SET estado = 'cerrada', medio_pago = %s, cerrado = now(), actualizado = now() "
                        "WHERE id = %s AND estado = 'abierta' AND lower(dueno) = %s RETURNING id", (medio, cid, dueno.lower()))
            ok = cur.fetchone() is not None
            conn.commit()
            return ok
    except Exception:  # noqa: BLE001
        return False


def cuenta_de(cid: str, dueno: str) -> dict | None:
    r = _select_cuentas("id = %s AND lower(dueno) = %s", (cid, dueno.lower()), 1)
    return r[0] if r else None


# ── Clientes registrados del local (para abrir cuenta) y locales por dueño ────

def clientes_registrados(dueno: str, hoy: date | None = None) -> list[dict]:
    """= `_elegirClienteRegistrado`: quienes reservaron en SUS canchas (correo
    de la reserva), primero los que tienen reserva HOY (están en el local),
    luego los recientes (máx. 300)."""
    hoy = hoy or date.today()
    ids = [c["id"] for c in datos.canchas_de_dueno(dueno)]
    if not ids:
        return []
    rs = datos.reservas_de_canchas(ids, (hoy - timedelta(days=365)).isoformat(), (hoy + timedelta(days=60)).isoformat())
    rs.sort(key=lambda r: str(r.get("fecha") or ""), reverse=True)
    vistos: set[str] = set()
    de_hoy, otros = [], []
    for r in rs:
        e = str(r.get("usuario") or "").strip().lower()
        if not e or "@" not in e or e in vistos:
            continue
        vistos.add(e)
        nombre = str(r.get("jugador") or "").strip() or e
        item = {"email": e, "nombre": nombre, "hoy": str(r.get("fecha") or "") == hoy.isoformat()}
        (de_hoy if item["hoy"] else otros).append(item)
    return de_hoy + otros[:300]


def locales_de(duenos: list[str]) -> dict[str, dict]:
    """{dueño: {club, cancha_id, lat, lng}} = su local verificado (1.ª cancha)."""
    ds = sorted({(x or "").strip().lower() for x in duenos if x})
    if not pg.habilitado or not ds:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT lower(dueno), id, coalesce(nullif(club,''), nombre), lat, lng FROM pichangol_canchas "
                        "WHERE lower(dueno) = ANY(%s) AND coalesce(eliminada,false) = false "
                        "ORDER BY verificada DESC, nombre", (ds,))
            out: dict[str, dict] = {}
            for f in cur.fetchall():
                out.setdefault(f[0], {"cancha_id": f[1], "club": f[2] or "", "lat": float(f[3] or 0), "lng": float(f[4] or 0)})
            return out
    except Exception:  # noqa: BLE001
        return {}
