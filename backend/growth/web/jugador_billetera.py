"""BILLETERA DEL JUGADOR EN LA WEB (pedido del director, 29-sep-2026: "en la
web implementa las mismas funcionalidades que existen en el app"). Espejo de
cuatro pantallas del APK, con los MISMOS datos y la MISMA plata:

- `GET /mi-billetera` = `cuenta_screen.dart` (Mi billetera): saldo real
  (`stores.saldo_centimos`) + saldo de REGALO (`saldo_promo_centimos`), la
  moneda del saldo (= `AppState.paisBilletera`), "Por recibir", cuenta de cobro
  (→ /anfitrion/ingresos), recargas por QR en revisión, banner del bono de
  recarga, acciones rápidas, cupón y los movimientos de `GET /pagos/movimientos`
  (`pagos.router.movimientos_de`) con el mismo mapeo de tipos del APK. RECARGAR:
  chips por país (`PaisConfig.recargas`) + "Otro monto" (`recargaMin/Max`),
  resumen `pcgResumenPago` y Culqi Checkout v4 (SOLO PEN: la recarga web pasa
  por `pagos.router.post_recarga`, que cobra, acredita, aplica el bono y es
  idempotente por cargo). En $ / Bs se muestra la pasarela del país y "hazlo
  desde la app" (PayPhone y Libélula viven en el APK).
- `GET /mi-billetera/estado-de-cuenta` = PDF "Estado de cuenta" del APK
  (versión imprimible: "Imprimir / guardar PDF").
- `GET /mis-pagos` = `mis_pagos_screen.dart`: bonos comprados + reservas
  (pagadas / con bono / por pagar en la cancha) como el APK, y además las
  cuotas de academia, las compras del marketplace y las recargas, con enlace al
  comprobante web cuando existe.
- `GET /mis-puntos` = `mis_puntos_screen.dart`: disponibles
  (`datos.puntos_de`, = `misPuntosDisponibles`), por confirmar
  (`misPuntosPendientes`), canjeados e historial (reservas traídas por la app
  de los últimos 12 meses, bodega pagada con saldo, canjes).
- `GET /mi-pais` + `POST /web/mi-pais` = Perfil → "Mi país" (`selector_pais.
  dart` + `AppState.cambiarPaisCasa`): solo con saldo y regalo en 0.

PAÍS DE LA BILLETERA (`pais_billetera`), misma precedencia que el APK:
moneda congelada por la última RECARGA (salvo que después se haya cambiado el
país con saldo 0) → país de su primera cancha (coordenadas) → país de casa
elegido → Perú (la web no tiene el GPS del teléfono). El país de casa del APK
vive solo en SharedPreferences; en la nube no hay columna para él, así que la
web lo guarda de forma ADITIVA en la ficha del cliente del snapshot
(`stores.clientes_pago[correo]["pais_casa" | "pais_casa_en"]`, privada y
persistida). El APK lo lee y escribe con `GET/POST /pagos/pais-casa`
(`AppState.sincronizarPaisCasa`), así el país de casa es el mismo en web y app.

Todo endpoint que escribe exige la sesión de Google (`web/sesion.py`) y opera
solo sobre el correo de esa sesión.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

import config
from db import pg
from db.store import stores
from paises import pais_de_coordenadas
from pagos import cuentas_cobro as _cc
from pagos import culqi
from pagos import router as _pagos
from web import datos, sesion, ui
from web.ui import PLAY_URL, e

router = APIRouter()

# ── Países (espejo de `PaisConfig` en lib/config/pais.dart) ───────────────────
PAISES: dict[str, dict] = {
    "PE": {"iso": "PE", "nombre": "Perú", "moneda": "S/", "iso_mon": "PEN", "pasarela": "culqi",
           "pasarela_nombre": "Culqi (Yape · tarjeta)", "recargas": [20, 50, 100, 200], "min": 10, "max": 1000},
    "BO": {"iso": "BO", "nombre": "Bolivia", "moneda": "Bs", "iso_mon": "BOB", "pasarela": "libelula",
           "pasarela_nombre": "Libélula (QR · tarjeta · Tigo Money)", "recargas": [50, 100, 200, 500], "min": 20, "max": 3000},
    "EC": {"iso": "EC", "nombre": "Ecuador", "moneda": "$", "iso_mon": "USD", "pasarela": "payphone",
           "pasarela_nombre": "PayPhone (tarjeta · saldo PayPhone)", "recargas": [5, 10, 20, 50], "min": 1, "max": 300},
}
_ISO_POR_MONEDA = {"PEN": "PE", "BOB": "BO", "USD": "EC"}
SIMBOLO = {"PEN": "S/", "BOB": "Bs", "USD": "$"}
# `cuenta_screen._saldoBajo`: con 15 o menos el dueño deja de salir destacado.
SALDO_BAJO = 15


_LIMA = timezone(timedelta(hours=-5))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _parse(s) -> datetime | None:
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    txt = str(s or "").strip()
    if len(txt) == 10:
        # Fecha sola (fecha de juego de una reserva): es un día de Lima, no medianoche UTC.
        try:
            return datetime.combine(date.fromisoformat(txt), datetime.min.time()).replace(tzinfo=_LIMA)
        except ValueError:
            return None
    try:
        d = datetime.fromisoformat(str(s or "").replace("Z", "+00:00"))
    except ValueError:
        try:
            d = datetime.combine(date.fromisoformat(str(s or "")[:10]), datetime.min.time())
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _dinero(sim: str, v: float) -> str:
    return f"{sim} {float(v or 0):,.2f}"


# ── País / moneda de la billetera ─────────────────────────────────────────────

def _pais_casa(email: str) -> tuple[str, datetime | None]:
    f = stores.clientes_pago.get(email) or {}
    iso = str(f.get("pais_casa") or "").upper()
    return (iso if iso in PAISES else ""), _parse(f.get("pais_casa_en"))


def _ultima_recarga(email: str):
    ult = None
    for p in stores.pagos:
        if p.tipo == "recarga" and p.estado == "aprobado" and p.dueno_id == email:
            if ult is None or p.creado_en >= ult.creado_en:
                ult = p
    return ult


def pais_billetera(email: str, canchas: list[dict] | None = None) -> tuple[str, str]:
    """(ISO del país, fuente) de la billetera = `AppState.paisBilletera`.
    Fuente: 'recarga' | 'cancha' | 'elegido' | 'defecto'."""
    email = (email or "").strip().lower()
    casa, casa_en = _pais_casa(email)
    rec = _ultima_recarga(email)
    if rec is not None:
        en = _parse(rec.creado_en)
        # Cambiar de país (con saldo 0) DESCONGELA la moneda, como en el APK.
        if not (casa and casa_en and en and casa_en > en):
            return _ISO_POR_MONEDA.get(_pagos.moneda_iso(rec.moneda), "PE"), "recarga"
    if canchas is None:
        canchas = datos.canchas_de_dueno(email)
    for c in canchas or []:
        if c.get("lat") is not None and c.get("lng") is not None:
            return pais_de_coordenadas(c.get("lat"), c.get("lng")), "cancha"
    if casa:
        return casa, "elegido"
    return "PE", "defecto"


def puede_cambiar_pais(email: str) -> bool:
    """= `AppState.puedeCambiarPaisCasa`: saldo real y regalo en cero."""
    return stores.saldo_centimos(email) <= 0 and stores.saldo_promo_centimos(email) <= 0


# ── Movimientos (mismo mapeo de tipos que `AppState.sincronizarSaldo`) ────────
_CONSUMO = {"comision_reserva", "suscripcion", "suscripcion_pro", "inscripcion_torneo",
            # Egresos que el backend ya manda en negativo (el APK los pinta como
            # recarga por un switch incompleto; aquí van como gasto, que es lo que son).
            "bodega_pago", "aporte_equipo"}
_LIQUIDACION = {"liquidacion_online", "liquidacion_full", "venta_producto", "inscripcion_torneo_ingreso",
                "liquidacion_boleador", "venta_bodega"}
_MEDIO = {"yape": "Yape", "tarjeta": "Tarjeta", "sena": "Seña", "saldo": "Saldo"}


def movimientos(email: str) -> list[dict]:
    """Movimientos del backend (`pagos.router.movimientos_de`, la MISMA fuente
    que `GET /pagos/movimientos/{email}` del APK) ya clasificados."""
    try:
        crudos = _pagos.movimientos_de(email)
    except Exception:  # noqa: BLE001
        crudos = []
    out = []
    for m in crudos:
        t = str(m.get("tipo") or "recarga")
        clase = "consumo" if t in _CONSUMO else ("liquidacion" if t in _LIQUIDACION else "recarga")
        concepto = str(m.get("concepto") or "")
        fuente = ""
        if t == "liquidacion_online":
            fuente, concepto = "transaccion", concepto or "Reserva online"
        elif t == "liquidacion_full":
            fuente = "saldo"
            concepto = f"{concepto} · recibes 100%" if concepto else "Reserva online · recibes 100%"
        elif t == "inscripcion_torneo_ingreso":
            fuente, concepto = "transaccion", concepto or "Inscripción a torneo"
        elif t == "liquidacion_boleador":
            fuente, concepto = "transaccion", concepto or "Boleo · neto por recibir"
        elif t in ("venta_producto", "venta_bodega"):
            fuente, concepto = "transaccion", concepto or "Venta"
        elif t == "comision_reserva":
            fuente, concepto = "saldo", concepto or "Comisión de reserva"
        elif not concepto:
            concepto = "Consumo de saldo" if clase == "consumo" else "Recarga de saldo"
        monto = float(m.get("monto_soles") or 0)
        iso = _pagos.moneda_iso(m.get("moneda"))
        out.append({
            "tipo": t, "clase": clase, "concepto": concepto, "fuente": fuente,
            "monto": abs(monto), "moneda": SIMBOLO.get(iso, "S/"), "iso": iso,
            "bruto": float(m.get("bruto_soles") or 0),
            "comision": abs(monto) if t == "comision_reserva" else float(m.get("comision_soles") or 0),
            "liquidado": bool(m.get("liquidado", False)), "medio": str(m.get("medio") or ""),
            "comprobante": m.get("comprobante"), "creado_en": str(m.get("creado_en") or ""),
        })
    return out


def por_recibir(movs: list[dict]) -> dict[str, float]:
    """Neto pendiente por moneda (= suma de liquidaciones no liquidadas del APK)."""
    tot: dict[str, float] = {}
    for m in movs:
        if m["clase"] == "liquidacion" and not m["liquidado"]:
            tot[m["moneda"]] = round(tot.get(m["moneda"], 0.0) + m["monto"], 2)
    return {k: v for k, v in tot.items() if v > 0}


def _fecha_rel(iso: str) -> str:
    d = _parse(iso)
    if not d:
        return ""
    lima = timezone(timedelta(hours=-5))
    dia, hoy = d.astimezone(lima).date(), _ahora().astimezone(lima).date()
    diff = (hoy - dia).days
    if diff <= 0:
        return "Hoy"
    if diff == 1:
        return "Ayer"
    return dia.strftime("%d/%m")


def _fecha_larga(iso: str) -> str:
    d = _parse(iso)
    if not d:
        return ""
    return d.astimezone(timezone(timedelta(hours=-5))).strftime("%d/%m/%Y · %H:%M")


# ── Consultas propias (mismas tablas del APK; fail-safe) ──────────────────────

def bonos_comprados(email: str) -> list[dict]:
    """`BonosRepo.comprasDe`: créditos de horas que compró el jugador."""
    e_ = (email or "").strip().lower()
    if not pg.habilitado or not e_:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, club, horas_total, horas_usadas, precio, creado FROM pichangol_bonos_comprados "
                        "WHERE lower(comprador) = %s ORDER BY creado DESC LIMIT 200", (e_,))
            return [{"id": str(f[0]), "club": str(f[1] or ""), "horas_total": int(f[2] or 0),
                     "horas_usadas": int(f[3] or 0), "precio": float(f[4] or 0), "creado": f[5]}
                    for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def monedas_de_clubes(clubes: list[str]) -> dict[str, str]:
    """`AppState.monedaDeClub`: moneda por las coordenadas de una cancha del local."""
    clubes = sorted({c for c in clubes if c})
    if not pg.habilitado or not clubes:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT club, lat, lng FROM pichangol_canchas WHERE club = ANY(%s) "
                        "AND coalesce(eliminada,false) = false", (clubes,))
            out: dict[str, str] = {}
            for club, lat, lng in cur.fetchall():
                if club not in out and lat is not None and lng is not None:
                    out[club] = PAISES[pais_de_coordenadas(lat, lng)]["moneda"]
            return out
    except Exception:  # noqa: BLE001
        return {}


def nombres_de_canchas(ids: list[str]) -> dict[str, dict]:
    ids = sorted({i for i in ids if i})
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, nombre, club FROM pichangol_canchas WHERE id = ANY(%s)", (ids,))
            return {str(f[0]): {"nombre": str(f[1] or ""), "club": str(f[2] or "")} for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


def matriculas_que_pago(email: str) -> list[dict]:
    """Matrículas que PAGA este correo (titular, pareja, hijos): sus cuotas."""
    e_ = (email or "").strip().lower()
    if not pg.habilitado or not e_:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, data FROM pichangol_matriculas WHERE lower(email) = %s "
                        "AND coalesce(eliminada,false) = false ORDER BY id DESC LIMIT 100", (e_,))
            out = []
            for mid, aid, data in cur.fetchall():
                d = data if isinstance(data, dict) else (json.loads(data) if isinstance(data, str) and data else {})
                out.append({"id": str(mid), "academia_id": str(aid or ""), "data": d or {}})
            return out
    except Exception:  # noqa: BLE001
        return []


def reservas_para_puntos(email: str) -> list[dict]:
    """Reservas TRAÍDAS POR LA APP de los últimos 12 meses (base de `_puntosDe`),
    sin no-show ni retenciones web sin pagar."""
    e_ = (email or "").strip().lower()
    if not pg.habilitado or not e_:
        return []
    lim = (_ahora() - timedelta(days=365)).date().isoformat()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, cancha_id, fecha, hora_inicio, precio, extras, coalesce(pagado,false) "
                "FROM pichangol_reservas WHERE lower(usuario) = %s AND coalesce(traida_por_app, true) "
                "AND coalesce(estado, '') NOT IN ('noShow', 'no_show') "
                "AND NOT (coalesce(estado,'') = 'nueva' AND NOT coalesce(pagado,false)) "
                "AND fecha >= %s ORDER BY fecha DESC, hora_inicio DESC LIMIT 400", (e_, lim))
            out = []
            for rid, cid, fecha, hi, precio, extras, pagado in cur.fetchall():
                ex = extras if isinstance(extras, list) else (json.loads(extras) if isinstance(extras, str) and extras else [])
                tot = float(precio or 0) + sum(float((x or {}).get("precio") or 0) for x in ex if isinstance(x, dict))
                out.append({"id": str(rid), "cancha_id": str(cid or ""), "fecha": str(fecha or ""),
                            "hora_inicio": str(hi or ""), "puntos": int(round(tot)), "pagado": bool(pagado)})
            return out
    except Exception:  # noqa: BLE001
        return []


def bodega_para_puntos(email: str) -> list[dict]:
    """`BodegaRepo.puntosBodegaCliente`: pedidos pagados con saldo y entregados."""
    e_ = (email or "").strip().lower()
    if not pg.habilitado or not e_:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, items, total, creado FROM pichangol_bodega_pedidos WHERE lower(cliente) = %s "
                        "AND pagado AND estado = 'entregado' AND creado >= %s ORDER BY creado DESC LIMIT 200",
                        (e_, _ahora() - timedelta(days=365)))
            out = []
            for pid, items, total, creado in cur.fetchall():
                its = items if isinstance(items, list) else (json.loads(items) if isinstance(items, str) and items else [])
                resumen = " + ".join(f"{int((i or {}).get('cantidad') or 1)} {(i or {}).get('nombre') or ''}".strip()
                                     for i in its if isinstance(i, dict))
                out.append({"id": str(pid), "resumen": resumen or "Pedido", "puntos": int(round(float(total or 0))),
                            "creado": creado})
            return out
    except Exception:  # noqa: BLE001
        return []


def canjes_de_puntos(email: str) -> list[dict]:
    e_ = (email or "").strip().lower()
    if not pg.habilitado or not e_:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT puntos, soles, referencia, creado FROM pichangol_puntos_canjes "
                        "WHERE lower(email) = %s ORDER BY creado DESC LIMIT 100", (e_,))
            return [{"puntos": int(f[0] or 0), "soles": float(f[1] or 0), "referencia": str(f[2] or ""),
                     "creado": f[3]} for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


# ── Piezas comunes de página ──────────────────────────────────────────────────

_CSS = """
.bil{max-width:760px;margin:18px auto 80px}
.bil h1{font-size:28px;margin:0 0 6px;letter-spacing:-.3px}
.bil-nav{display:flex;gap:8px;overflow-x:auto;padding:4px 2px 12px;margin:0 0 6px;scrollbar-width:none}
.bil-nav::-webkit-scrollbar{display:none}
.bil-nav a{flex:none;border:1px solid #E4E4E4;background:#fff;border-radius:999px;padding:8px 14px;font-weight:700;font-size:14px;color:var(--noche);text-decoration:none;box-shadow:0 1px 3px rgba(0,0,0,.06);white-space:nowrap}
.bil-nav a.sel{background:#EBEBEB;border-color:#D6D6D6}
.bil-saldo{background:linear-gradient(135deg,#128C7E,#075E54);color:#fff;border-radius:22px;padding:22px;box-shadow:0 8px 18px rgba(7,94,84,.35)}
.bil-saldo .top{display:flex;align-items:center;gap:10px}
.bil-saldo .top span{opacity:.8;font-size:15px}
.bil-saldo .pill{margin-left:auto;background:rgba(255,255,255,.16);color:#fff;border-radius:99px;padding:5px 10px;font-size:12px;font-weight:800;white-space:nowrap}
.bil-saldo .monto{font-size:38px;font-weight:800;margin:14px 0 4px;overflow-wrap:anywhere}
.bil-saldo .txt{opacity:.7;font-size:13px;line-height:1.4}
.bil-saldo .btn{width:100%;margin-top:18px;background:#fff;color:#0B8A3E}
.bil-card{border-radius:16px;padding:14px;display:flex;gap:10px;align-items:center;margin-top:12px;border:1px solid var(--trazo);background:#fff;color:inherit;text-decoration:none;min-width:0}
.bil-card .em{font-size:22px;flex:none}
.bil-card .tx{flex:1;min-width:0;font-size:13.5px;line-height:1.35}
.bil-card .tx b{display:block;font-size:14.5px}
.bil-card .val{font-weight:800;font-size:17px;white-space:nowrap}
.bil-card.regalo{background:#EEF8E4;border-color:#7CB518;color:#14463A;font-weight:600}
.bil-card.bajo{background:#FFF1EC;border-color:#F3B8A5;color:#8F2A10}
.bil-card.recibir{background:#E6F4EA;border-color:#9ED2B0}
.bil-card.recibir .val{color:#067A38}
.bil-card.warn{background:var(--warn-bg);border-color:#EAD28F;color:var(--warn-fg)}
.bil-card.promo{background:linear-gradient(90deg,#FFF6D8,#FFEFC2);border-color:#E8D9A0;color:#7A5C00;font-weight:800}
.bil-acc{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin:18px 0 6px}
.bil-acc a,.bil-acc button{display:flex;flex-direction:column;align-items:center;gap:6px;background:none;border:0;font:inherit;color:inherit;text-decoration:none;cursor:pointer;padding:6px 2px;border-radius:14px;position:relative}
.bil-acc .bur{width:52px;height:52px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px}
.bil-acc small{font-size:12px;font-weight:700;text-align:center;line-height:1.15}
.bil-acc .ins{position:absolute;top:0;left:calc(50% + 12px);background:#B08908;color:#fff;border:1.5px solid #fff;border-radius:99px;font-size:10px;font-weight:800;padding:2px 6px}
.bil-cupon{margin:6px 0 4px;text-align:center}
.bil-cupon summary{display:inline-block;cursor:pointer;color:#14463A;font-weight:700;list-style:none;padding:8px}
.bil-cupon summary::-webkit-details-marker{display:none}
.bil-cupon form{display:flex;gap:8px;max-width:420px;margin:6px auto 0}
.bil-cupon input{flex:1;min-width:0;text-transform:uppercase;letter-spacing:1px}
.bil h2{font-size:19px;margin:26px 0 4px}
.bil .h2sub{color:var(--tenue);font-size:13.5px;margin:0 0 10px}
.bil-rec{background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(0,0,0,.08);padding:18px;margin-top:22px}
.bil-rec h2{margin-top:0}
.bil-rec .otro{display:none;margin-top:12px;gap:8px;align-items:center}
.bil-rec .otro.on{display:flex}
.bil-rec .otro input{max-width:180px}
.bil-rec .bono{margin-top:10px;font-size:13.5px;font-weight:700;color:#7A5C00;display:none}
.bil-rec .err{color:var(--bad-fg);font-size:13.5px;margin-top:10px;display:none}
.bil-rec .btn.lg{margin-top:14px}
.bmov{border:1px solid var(--trazo);border-radius:16px;margin-bottom:10px;background:#fff}
.bmov>summary{list-style:none;display:flex;gap:12px;align-items:center;padding:12px;cursor:pointer}
.bmov>summary::-webkit-details-marker{display:none}
.bmov .ic{width:40px;height:40px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:18px}
.bmov .tx{flex:1;min-width:0}
.bmov .tx b{display:block;font-size:14.5px;overflow-wrap:anywhere}
.bmov .tx small{color:var(--tenue);font-size:12.5px}
.bmov .der{text-align:right;flex:none}
.bmov .der b{font-size:15.5px;white-space:nowrap}
.bmov .der small{display:block;color:var(--tenue);font-size:11.5px}
.bmov .rec{margin:0 12px 12px 64px;background:#F6F7F6;border-radius:10px;padding:8px 10px;font-size:13px}
.bmov .rec div{display:flex;justify-content:space-between;gap:10px;padding:2px 0}
.bmov .rec div b{white-space:nowrap}
.bmov .rec hr{border:0;border-top:1px solid #E2E2E2;margin:5px 0}
.bil-vacio{text-align:center;padding:34px 16px;color:var(--tenue)}
.bil-vacio .em{font-size:54px;display:block;margin-bottom:8px}
.bil-vacio b{display:block;color:var(--noche);font-size:17px;margin-bottom:4px}
.pag-dia{font-size:13px;font-weight:700;color:var(--tenue);margin:16px 0 6px}
.pag{display:flex;gap:12px;align-items:center;border:1px solid var(--trazo);border-radius:16px;padding:12px;margin-bottom:10px;background:#fff;color:inherit;text-decoration:none}
.pag .ic{width:40px;height:40px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;font-size:19px}
.pag .tx{flex:1;min-width:0}
.pag .tx b{display:block;font-size:14.5px;overflow-wrap:anywhere;line-height:1.3}
.pag .tx small{color:var(--tenue);font-size:12.5px;display:block}
.pag .mt{font-weight:800;font-size:15px;white-space:nowrap;text-align:right}
.pag .mt small{display:block;font-weight:600;font-size:11.5px;color:var(--tenue)}
.pag-res{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;background:#F4F7F5;border-radius:14px;padding:12px;margin:10px 0}
.pag-res small{display:block;color:var(--tenue);font-size:12px}
.pag-res b{font-size:15px;overflow-wrap:anywhere}
.pts-top{background:#14463A;color:#fff;border-radius:18px;padding:20px;text-align:center}
.pts-top .t{opacity:.75;font-weight:700;font-size:13px}
.pts-top .n{font-size:44px;font-weight:900;line-height:1.1;margin:6px 0}
.pts-top .v{font-size:14px}
.pts-top .c{opacity:.75;font-size:12.5px;margin-top:4px}
.pts-pend{background:#FBEAD2;color:#8A5A00;border-radius:12px;padding:10px 12px;font-weight:700;font-size:13px;margin-top:10px;line-height:1.35}
.pts-como{background:#EEF8E4;border-radius:14px;padding:14px;margin-top:14px;font-size:13px;line-height:1.55}
.pts-como b{font-size:14px}
.pts-it{display:flex;gap:10px;align-items:center;border:1px solid var(--trazo);border-radius:12px;padding:10px 14px;margin-bottom:8px;background:#fff}
.pts-it .em{font-size:20px;flex:none}
.pts-it .tx{flex:1;min-width:0}
.pts-it .tx b{display:block;font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pts-it .tx small{color:var(--tenue);font-size:11.5px}
.pts-it .n{font-weight:900;font-size:15px;color:#14463A;white-space:nowrap}
.pts-it .n.gris{color:var(--tenue)}.pts-it .n.rojo{color:#C0392B}
.pais-actual{display:flex;align-items:center;gap:14px;background:#fff;border-radius:20px;box-shadow:0 6px 20px rgba(0,0,0,.08);padding:18px}
.pais-actual .flag{width:44px;height:30px;border-radius:5px;flex:none}
.pais-actual b{font-size:19px;display:block}
.pais-actual small{color:var(--tenue);font-size:13.5px}
.pais-chips{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:18px 0}
.pais-chips button{display:inline-flex;align-items:center;gap:8px;background:#fff;border:1px solid #E4E4E4;border-radius:22px;padding:12px 18px;font:inherit;font-weight:700;font-size:15px;color:#222;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.pais-chips button.sel{background:#EBEBEB;border-color:#D6D6D6;box-shadow:none}
.pais-chips button:disabled{opacity:.45;cursor:not-allowed}
.pais-chips .flag{width:24px;height:16px;border-radius:3px}
.est-tabla{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:12px}
.est-tabla th,.est-tabla td{padding:8px 6px;border-bottom:1px solid #EEE;text-align:left;vertical-align:top}
.est-tabla td.m{text-align:right;white-space:nowrap;font-weight:700}
.est-wrap{overflow-x:auto}
@media(max-width:560px){.bil h1{font-size:24px}.bil-saldo .monto{font-size:32px}.bmov .rec{margin-left:12px}.pag-res{grid-template-columns:minmax(0,1fr)}.bil-rec{padding:16px 14px}}
@media print{.cab,header,footer,.bil-nav,.no-print{display:none!important}.bil{margin:0;max-width:none}body{background:#fff}}
"""


def _nav(sel: str) -> str:
    items = (("billetera", "/mi-billetera", "👛 Mi billetera"), ("pagos", "/mis-pagos", "🧾 Mis pagos"),
             ("puntos", "/mis-puntos", "⭐ Mis puntos"), ("pais", "/mi-pais", "🌎 Mi país"))
    return "<nav class='bil-nav' aria-label='Billetera'>" + "".join(
        f"<a href='{h}'{' class=sel aria-current=page' if k == sel else ''}>{t}</a>" for k, h, t in items) + "</nav>"


def _gate(request: Request, ruta: str, titulo: str, en_app: str):
    """(sesión, None) o (None, respuesta): sin sesión → /entrar; sin login web → 'está en la app'."""
    ses = sesion.de_request(request)
    if ses and ses.get("email"):
        return ses, None
    if sesion.activo():
        from urllib.parse import quote
        return None, HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(ruta, safe='')}"})
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
              f"<h1 style='font-size:22px'>{e(titulo)}</h1>"
              f"<p class='sub'>En esta web aún no está activo el inicio de sesión. {e(en_app)}</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    return None, ui.shell(titulo, cuerpo, sesion=None)


def _email(ses: dict) -> str:
    return (ses.get("email") or "").strip().lower()


def _sesion_json(request: Request) -> str:
    ses = sesion.de_request(request)
    email = _email(ses) if ses else ""
    if not email:
        raise HTTPException(status_code=401, detail="sesion_requerida")
    return email


# ── /mi-billetera ─────────────────────────────────────────────────────────────

def _fila_mov(m: dict) -> str:
    sim = m["moneda"]
    liq = m["clase"] == "liquidacion"
    rec = m["clase"] == "recarga"
    pagada = liq and m["liquidado"]
    con_recibo = liq and m["bruto"] > 0
    color = "#7CB518" if rec else (("#0B8A3E" if pagada else "#067A38") if liq else "#C13515")
    ic = "⬇️" if rec else (("✅" if pagada else "👛") if liq else "⬆️")
    signo = "+" if (rec or liq) else "−"
    medio = f" · {_MEDIO[m['medio']]}" if m["medio"] in _MEDIO else ""
    cuando = _fecha_rel(m["creado_en"])
    if liq:
        sub = f"{cuando}{medio} · {'recibido' if pagada else 'por recibir'}"
    elif m["clase"] == "consumo" and m["fuente"] == "saldo":
        sub = f"{cuando} · de tu saldo"
    else:
        sub = cuando
    grande = _dinero(sim, m["bruto"]) if con_recibo else f"{signo} {_dinero(sim, m['monto'])}"
    recibo = ""
    if con_recibo:
        recibo = (f"<div><span>Cobrado al cliente</span><b>{e(_dinero(sim, m['bruto']))}</b></div>"
                  f"<div><span>Comisión Pichangol</span><b style='color:#C13515'>−{e(_dinero(sim, m['comision']))}</b></div><hr>"
                  f"<div><span>{'Recibiste' if pagada else 'Recibes'}</span><b style='color:{color}'>{e(_dinero(sim, m['monto']))}</b></div>")
    detalle = (recibo
               + f"<div><span>Fecha</span><b>{e(_fecha_larga(m['creado_en']))}</b></div>"
               + (f"<div><span>N.º de comprobante</span><b>{e(m['comprobante'])}</b></div>" if m.get("comprobante") else "")
               + (f"<div><span>Medio</span><b>{e(_MEDIO[m['medio']])}</b></div>" if m["medio"] in _MEDIO else ""))
    return (f"<details class='bmov'><summary><span class='ic' style='background:{color}1F'>{ic}</span>"
            f"<span class='tx'><b>{e(m['concepto'])}</b><small>{e(sub)}</small></span>"
            f"<span class='der'><b style='color:{'var(--noche)' if con_recibo else color}'>{e(grande)}</b>"
            + ("<small>cobrado</small>" if con_recibo else "") + "</span></summary>"
            f"<div class='rec'>{detalle}</div></details>")


_JS_BILLETERA = r"""
(function(){
  var C = window.__billetera || {}, $ = function(id){ return document.getElementById(id); };
  var st = {monto: (C.recargas || [])[1] || (C.recargas || [])[0] || 0, otro: false};
  function fmt(n){ return C.moneda + ' ' + Number(n || 0).toFixed(2); }
  function err(t){ var x = $('recErr'); if(!x) return; x.textContent = t || ''; x.style.display = t ? 'block' : 'none'; }
  function bono(m){ var b = C.bono; if(!b || !(b.pct > 0) || m < b.min) return 0; var v = Math.round(m * b.pct) / 100; if(b.tope > 0) v = Math.min(v, b.tope); return v; }
  function pintar(){
    document.querySelectorAll('#recChips [data-monto]').forEach(function(ch){ ch.classList.toggle('sel', !st.otro && Number(ch.dataset.monto) === st.monto); });
    var co = $('chipOtro'); if(co) co.classList.toggle('sel', st.otro);
    var ot = $('recOtro'); if(ot) ot.classList.toggle('on', st.otro);
    var ok = st.monto >= C.min && st.monto <= C.max && Math.floor(st.monto) === st.monto;
    var bt = $('btnRecargar'); if(bt){ bt.disabled = !ok; bt.textContent = ok ? ('Pagar ' + fmt(st.monto)) : ('Entre ' + C.moneda + ' ' + C.min + ' y ' + C.moneda + ' ' + C.max); }
    var bb = $('recBono'), bv = ok ? bono(st.monto) : 0;
    if(bb){ bb.style.display = bv > 0 ? 'block' : 'none'; bb.textContent = '🎁 Con esta recarga te regalamos +' + fmt(bv) + ' extra.'; }
  }
  document.querySelectorAll('#recChips [data-monto]').forEach(function(ch){ ch.addEventListener('click', function(){ st.otro = false; st.monto = Number(ch.dataset.monto); err(''); pintar(); }); });
  var co = $('chipOtro'); if(co) co.addEventListener('click', function(){ st.otro = true; var i = $('montoOtro'); st.monto = Number(i.value || 0); pintar(); i.focus(); });
  var mi = $('montoOtro'); if(mi) mi.addEventListener('input', function(){ st.monto = Number(mi.value || 0); err(''); pintar(); });
  function recargar(){
    err('');
    if(!(st.monto >= C.min && st.monto <= C.max && Math.floor(st.monto) === st.monto)){ err('Entre ' + C.moneda + ' ' + C.min + ' y ' + C.moneda + ' ' + C.max + ', sin decimales.'); return; }
    if(!C.pk || !window.Culqi){ err('El pago en línea no está disponible por ahora.'); return; }
    var m = window.pcgMedioPago ? pcgMedioPago() : 'yape', monto = st.monto, bv = bono(monto);
    pcgResumenPago({moneda: C.moneda, medio: m, lineas: [{t: 'Recarga de saldo Pichangol', m: monto}], total: monto,
                    nota: (bv > 0 ? '🎁 Además recibes +' + fmt(bv) + ' de bono (lo pone Pichangol). ' : '') + 'El saldo se acredita al instante en tu billetera, la misma de la app.'})
      .then(function(ok){
        if(!ok) return;
        Culqi.publicKey = C.pk;
        Culqi.settings({title: 'Pichangol', currency: 'PEN', amount: Math.round(monto * 100)});
        Culqi.options({lang: 'es', installments: false,
          paymentMethods: {yape: m === 'yape', tarjeta: m === 'tarjeta', bancaMovil: false, agente: false, billetera: false, cuotealo: false},
          style: {logo: '', bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Pagar', buttonTextColor: '#FFFFFF'}});
        window.culqi = function(){
          if(Culqi.token){
            var token = Culqi.token.id, medio = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
            Culqi.close(); pcgCargando('Acreditando tu recarga…');
            fetch('/web/billetera/recargar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({monto: monto, token: token, medio: medio})})
              .then(function(r){ return r.json(); })
              .then(function(p){
                pcgCargando(false);
                if(p.ok){
                  pcgAvisar({titulo: '¡Recarga exitosa! ✅', icono: '👛', confirmar: 'Listo',
                             mensaje: 'Se acreditaron ' + fmt(monto) + (p.bono_soles > 0 ? ' + ' + fmt(p.bono_soles) + ' de bono 🎁' : '') + ' a tu saldo. Nuevo saldo: ' + fmt(p.saldo_soles) + '.'})
                    .then(function(){ pcgRecargar('Actualizando tu billetera…'); });
                } else { err(p.mensaje || 'El pago no se pudo procesar. No se te cobró nada.'); }
              }).catch(function(){ pcgCargando(false); err('No pudimos confirmar la recarga. Si te cobraron, escríbenos con tu correo y la revisamos.'); });
          } else if(Culqi.order){ err('Este medio de pago no está habilitado. Usa Yape o tarjeta.'); }
          else { err((Culqi.error && Culqi.error.user_message) || 'No se pudo procesar el pago.'); }
        };
        Culqi.open();
      });
  }
  var br = $('btnRecargar'); if(br) br.addEventListener('click', recargar);
  // Cupón (código de campaña): acredita al instante.
  var fc = $('formCupon');
  if(fc) fc.addEventListener('submit', function(ev){
    ev.preventDefault();
    var cod = ($('codCupon').value || '').trim();
    if(!cod){ pcgToast('Escribe el código del cupón.'); return; }
    pcgCargando('Canjeando…', {demora: 250});
    fetch('/web/billetera/cupon', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({codigo: cod})})
      .then(function(r){ return r.json(); })
      .then(function(p){
        pcgCargando(false);
        if(p.ok){ pcgAvisar({titulo: '¡Cupón canjeado! 🎁', icono: '🎟️', confirmar: 'Listo', mensaje: '+' + fmt(p.valor_soles) + ' a tu saldo Pichangol.'}).then(function(){ pcgRecargar(); }); }
        else { pcgAvisar({titulo: 'No se pudo canjear', icono: '🎟️', confirmar: 'Entendido', mensaje: p.mensaje || 'Código inválido o vencido. Revísalo e intenta de nuevo.'}); }
      }).catch(function(){ pcgCargando(false); pcgToast('Sin conexión. Intenta de nuevo.'); });
  });
  // Lo que vive en la app (tarjetas guardadas, recarga en $/Bs): modal, nunca un enlace roto.
  document.querySelectorAll('[data-app]').forEach(function(b){ b.addEventListener('click', function(ev){ ev.preventDefault();
    pcgConfirmar({titulo: b.dataset.titulo, mensaje: b.dataset.app, icono: b.dataset.em || '📱', confirmar: 'Abrir la app', cancelar: 'Ahora no'})
      .then(function(ok){ if(ok) window.open(C.play, '_blank', 'noopener'); }); }); });
  pintar();
})();
"""


@router.get("/mi-billetera", response_class=HTMLResponse)
def pagina_billetera(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/mi-billetera", "Mi billetera", "Tu saldo, recargas y movimientos están en la app.")
    if resp:
        return resp
    email = _email(ses)
    canchas = datos.canchas_de_dueno(email)
    iso, _fuente = pais_billetera(email, canchas)
    P = PAISES[iso]
    sim = P["moneda"]
    saldo = stores.saldo_centimos(email) / 100.0
    regalo = stores.saldo_promo_centimos(email) / 100.0
    movs = movimientos(email)
    pend = por_recibir(movs)
    pct, minimo, tope = _pagos._promo_bono_cfg()
    qr_pend = [r for r in stores.recargas_qr if r.get("email") == email and r.get("estado") == "pendiente"]
    cuenta = stores.cuenta_cobro(email)
    res_cc = _cc.resumen(cuenta)
    try:
        puntos = int(datos.puntos_de(email).get("disponibles") or 0)
    except Exception:  # noqa: BLE001
        puntos = 0

    destacado = saldo > 0
    tarjeta = (
        "<div class='bil-saldo'><div class='top'><span>Saldo Pichangol</span>"
        f"<span class='pill'>{'⭐ Destacado' if destacado else '⏸ Pausado'}</span></div>"
        f"<div class='monto'>{e(_dinero(sim, saldo))}</div>"
        "<div class='txt'>Es tu saldo único: el mismo de la app, para tus reservas, tus canchas y academias. "
        "Las comisiones de cada reserva se descuentan de aquí.</div>"
        "<a class='btn' href='#recargar'>＋ Recargar saldo</a></div>")
    avisos = ""
    if regalo > 0:
        avisos += (f"<div class='bil-card regalo'><span class='em'>🎁</span><span class='tx'>Tienes {e(_dinero(sim, regalo))} de saldo "
                   "de REGALO por unirte a Pichangol: tus comisiones se descuentan de aquí primero, sin tocar tu plata.</span></div>")
    # "Saldo bajo" habla de salir destacado: solo aplica a quien tiene canchas.
    if canchas and saldo <= SALDO_BAJO and regalo <= 0:
        avisos += ("<div class='bil-card bajo'><span class='em'>⚠️</span><span class='tx'>Saldo bajo: si llega a 0 dejas de "
                   "aparecer destacado. Recarga para seguir recibiendo reservas.</span></div>")
    for mon, v in pend.items():
        avisos += (f"<a class='bil-card recibir' href='/anfitrion/ingresos'><span class='em'>👛</span><span class='tx'>"
                   f"<b>Por recibir</b>De reservas online, ventas y torneos (Pichangol te transfiere aparte).</span>"
                   f"<span class='val'>{e(_dinero(mon, v))}</span></a>")
    if pend or res_cc.get("tiene"):
        urgente = bool(pend) and not res_cc.get("tiene")
        tit = "Recibes tus liquidaciones en" if res_cc.get("tiene") else "Registra tu cuenta de cobro"
        txt = (res_cc.get("etiqueta") or "") if res_cc.get("tiene") else "Tienes plata por recibir y aún no sabemos dónde transferirte."
        avisos += (f"<a class='bil-card{' warn' if urgente else ''}' href='/anfitrion/ingresos'><span class='em'>"
                   f"{'🏦' if res_cc.get('tipo') not in ('yape', 'plin') and res_cc.get('tiene') else ('📱' if res_cc.get('tiene') else '💳')}</span>"
                   f"<span class='tx'><small>{e(tit)}</small><b>{e(txt)}</b></span><span class='val'>›</span></a>")
    for r in qr_pend:
        avisos += (f"<div class='bil-card warn'><span class='em'>⏳</span><span class='tx'>Recarga por Yape (QR) de "
                   f"{e(_dinero(sim, float(r.get('monto_soles') or 0)))} en revisión. Te avisamos apenas se acredite.</span></div>")
    if pct > 0:
        avisos += (f"<div class='bil-card promo'><span class='em'>🎁</span><span class='tx'>Recarga {e(sim)} {minimo:.0f} o más y te "
                   f"regalamos {pct:.0f}% extra (hasta {e(sim)} {tope:.0f}).</span></div>")

    ins = f"<span class='ins'>{'999+' if puntos > 999 else puntos}</span>" if puntos > 0 else ""
    acciones = (
        "<div class='bil-acc'>"
        "<a href='#recargar'><span class='bur' style='background:#7CB51824'>➕</span><small>Recargar</small></a>"
        "<a href='/cuenta/tarjetas'>"
        "<span class='bur' style='background:#14463A1F'>💳</span><small>Tarjetas</small></a>"
        f"<a href='/mis-puntos'><span class='bur' style='background:#B089081F'>⭐</span>{ins}<small>Puntos</small></a>"
        "<a href='/mi-billetera/estado-de-cuenta'><span class='bur' style='background:#067A381F'>🧾</span><small>Estado<br>de cuenta</small></a>"
        "</div>")
    cupon = ("<details class='bil-cupon'><summary>🎟️ ¿Tienes un cupón? Canjéalo aquí</summary>"
             "<form id='formCupon' autocomplete='off'><input id='codCupon' maxlength='24' placeholder='CÓDIGO' aria-label='Código del cupón'>"
             "<button class='btn' type='submit'>Canjear</button></form></details>")

    # Recargar: chips por país + "Otro monto"; cobro web solo en soles (Culqi).
    if P["pasarela"] == "culqi" and config.CULQI_PUBLIC_KEY and culqi.disponible():
        chips = "".join(f"<button type='button' class='chip' data-monto='{m}'>{e(sim)} {m}</button>" for m in P["recargas"])
        recargar = (
            "<section class='bil-rec' id='recargar'><h2>Recargar saldo</h2>"
            "<p class='h2sub'>¿Cuánto quieres recargar?</p>"
            f"<div class='chips' id='recChips'>{chips}<button type='button' class='chip' id='chipOtro'>Otro monto</button></div>"
            f"<div class='otro' id='recOtro'><span>{e(sim)}</span><input id='montoOtro' type='number' inputmode='numeric' "
            f"min='{P['min']}' max='{P['max']}' step='1' placeholder='{P['recargas'][0]}' aria-label='Otro monto'>"
            f"<small class='sub' style='font-size:12.5px'>Entre {e(sim)} {P['min']} y {e(sim)} {P['max']}, sin decimales.</small></div>"
            "<div class='bono' id='recBono'></div>"
            f"<div style='margin-top:16px'>{ui.selector_medio_pago()}</div>"
            "<div class='err' id='recErr' role='alert'></div>"
            "<button class='btn lg' id='btnRecargar' disabled>Elige un monto</button></section>")
    elif P["pasarela"] == "culqi":
        recargar = ("<section class='bil-rec' id='recargar'><h2>Recargar saldo</h2>"
                    "<p class='h2sub'>El pago en línea no está disponible en la web por ahora. Puedes recargar desde la app.</p>"
                    f"<a class='btn sec' href='{PLAY_URL}' target='_blank' rel='noopener'>Recargar en la app</a></section>")
    else:
        recargar = ("<section class='bil-rec' id='recargar'><h2>Recargar saldo</h2>"
                    f"<p class='h2sub'>Tu billetera es de {ui.bandera(iso)} {e(P['nombre'])} ({e(sim)}). En {e(P['nombre'])} se recarga con "
                    f"{e(P['pasarela_nombre'])} desde la app: montos desde {e(sim)} {P['min']} hasta {e(sim)} {P['max']}.</p>"
                    f"<a class='btn' href='{PLAY_URL}' target='_blank' rel='noopener'>Recargar en la app</a></section>")

    liqs = [m for m in movs if m["clase"] == "liquidacion"]
    mios = [m for m in movs if m["clase"] != "liquidacion"]
    if not movs:
        lista = ("<div class='bil-vacio'><span class='em'>👛</span><b>Aún no hay movimientos</b>"
                 "Recarga tu saldo o recibe pagos y aparecerán aquí.</div>")
    else:
        lista = ""
        if liqs:
            lista += ("<h2>Por recibir</h2><p class='h2sub'>Pagos de tus clientes: reservas online, bonos y ventas. "
                      "Pichangol te transfiere el neto.</p>" + "".join(_fila_mov(m) for m in liqs))
        if mios:
            lista += ("<h2>Mi saldo</h2><p class='h2sub'>Tu monedero: recargas y gastos (comisiones, servicios, Pro).</p>"
                      + "".join(_fila_mov(m) for m in mios))
    cfg = {"moneda": sim, "recargas": P["recargas"], "min": P["min"], "max": P["max"], "pk": config.CULQI_PUBLIC_KEY,
           "bono": {"pct": pct, "min": minimo, "tope": tope}, "play": PLAY_URL}
    cuerpo = (f"<style>{_CSS}</style><div class='bil'>{_nav('billetera')}<h1>Mi billetera</h1>"
              + tarjeta + avisos + acciones + cupon + recargar
              + f"<h2 style='margin-top:30px'>Movimientos</h2>{lista}"
              + "<p class='sub' style='font-size:13px;margin-top:18px'>¿Buscas lo que pagaste en reservas y academias? "
                "Está en <a href='/mis-pagos'>Mis pagos</a>.</p></div>"
              + f"<script>window.__billetera={json.dumps(cfg)};</script><script>{_JS_BILLETERA}</script>")
    head = "<script src='https://checkout.culqi.com/js/v4'></script>" if "btnRecargar" in recargar else ""
    return ui.shell("Mi billetera", cuerpo, sesion=ses, titulo_tab="Mi billetera · Pichangol", extra_head=head)


@router.get("/mi-billetera/estado-de-cuenta", response_class=HTMLResponse)
def pagina_estado_cuenta(request: Request) -> HTMLResponse:
    """= "Estado de cuenta" (PDF) de la billetera del APK: imprimible."""
    ses, resp = _gate(request, "/mi-billetera/estado-de-cuenta", "Estado de cuenta", "Tu estado de cuenta está en la app.")
    if resp:
        return resp
    email = _email(ses)
    movs = movimientos(email)
    iso, _ = pais_billetera(email)
    sim = PAISES[iso]["moneda"]
    filas = "".join(
        f"<tr><td>{e(_fecha_larga(m['creado_en']))}</td><td>{e(m['concepto'])}"
        + (f"<br><small class='sub'>N.º {e(m['comprobante'])}</small>" if m.get("comprobante") else "")
        + f"</td><td>{'Por recibir' if m['clase'] == 'liquidacion' and not m['liquidado'] else ('Recibido' if m['clase'] == 'liquidacion' else ('Gasto' if m['clase'] == 'consumo' else 'Ingreso'))}</td>"
        f"<td class='m'>{'−' if m['clase'] == 'consumo' else '+'} {e(_dinero(m['moneda'], m['monto']))}</td></tr>" for m in movs)
    tabla = (f"<div class='est-wrap'><table class='est-tabla'><thead><tr><th>Fecha</th><th>Concepto</th><th>Tipo</th><th style='text-align:right'>Monto</th></tr></thead>"
             f"<tbody>{filas}</tbody></table></div>") if movs else "<div class='bil-vacio'><span class='em'>👛</span><b>Aún no hay movimientos</b></div>"
    cuerpo = (f"<style>{_CSS}</style><div class='bil'>{_nav('billetera')}<h1>Estado de cuenta</h1>"
              f"<p class='sub'>{e(ses.get('nombre') or email)} · {e(email)} · generado el {e(_fecha_larga(_ahora().isoformat()))}</p>"
              f"<div class='pag-res'><div><small>Saldo</small><b>{e(_dinero(sim, stores.saldo_centimos(email) / 100.0))}</b></div>"
              f"<div><small>Regalo</small><b>{e(_dinero(sim, stores.saldo_promo_centimos(email) / 100.0))}</b></div>"
              f"<div><small>Movimientos</small><b>{len(movs)}</b></div></div>"
              "<div class='no-print' style='display:flex;gap:10px;flex-wrap:wrap'><button class='btn' onclick='window.print()'>🖨️ Imprimir / guardar PDF</button>"
              "<a class='btn sec' href='/mi-billetera'>‹ Volver a Mi billetera</a></div>"
              f"{tabla}<p class='sub' style='font-size:12px;margin-top:14px'>Documento generado por Pichangol. No es un comprobante tributario.</p></div>")
    return ui.shell("Estado de cuenta", cuerpo, sesion=ses, titulo_tab="Estado de cuenta · Pichangol")


@router.post("/web/billetera/recargar")
def recargar_web(request: Request, body: dict = Body(...)) -> JSONResponse:
    """Recarga con Culqi (Yape/tarjeta) = `POST /pagos/recarga` del APK: cobra,
    acredita a la billetera del CORREO DE LA SESIÓN, aplica el bono de recarga
    y es idempotente por cargo. Solo billeteras en soles."""
    try:
        email = _sesion_json(request)
    except HTTPException:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para recargar."}, status_code=401)
    iso, _ = pais_billetera(email)
    P = PAISES[iso]
    if P["pasarela"] != "culqi":
        return JSONResponse({"ok": False, "error": "pais_no_soportado",
                             "mensaje": f"Tu billetera es de {P['nombre']} ({P['moneda']}): recárgala desde la app."}, status_code=409)
    token = str((body or {}).get("token") or "").strip()
    try:
        monto = float((body or {}).get("monto") or 0)
    except (TypeError, ValueError):
        monto = 0
    if not token:
        return JSONResponse({"ok": False, "error": "token_requerido", "mensaje": "Falta el pago."}, status_code=400)
    if monto != int(monto) or not (P["min"] <= monto <= P["max"]):
        return JSONResponse({"ok": False, "error": "monto_invalido",
                             "mensaje": f"El monto va entre {P['moneda']} {P['min']} y {P['moneda']} {P['max']}, sin decimales."}, status_code=400)
    ses = sesion.de_request(request) or {}
    nombre = (ses.get("nombre") or "").strip()
    try:
        tel = datos.celular_de_perfil(email)
    except Exception:  # noqa: BLE001
        tel = ""
    try:
        r = _pagos.post_recarga(_pagos.RecargaReq(token=token, dueno_id=email, email=email, monto_soles=int(monto),
                                                  nombre=nombre, telefono=tel, pais="PE"))
    except HTTPException as ex:
        return JSONResponse({"ok": False, "error": str(ex.detail),
                             "mensaje": "El pago en línea no está disponible por ahora." if ex.status_code == 503 else "Monto inválido."},
                            status_code=ex.status_code)
    if not r.get("ok"):
        return JSONResponse({"ok": False, "error": r.get("error", "cargo_rechazado"),
                             "mensaje": r.get("merchant") or "El pago no se pudo procesar. No se te cobró nada."})
    print(f"[billetera] recarga web {email} {P['moneda']} {int(monto)} {r.get('charge_id')}", flush=True)
    return JSONResponse({"ok": True, "saldo_soles": r.get("saldo_soles"), "bono_soles": r.get("bono_soles", 0),
                         "charge_id": r.get("charge_id")})


_MSJ_CUPON = {"ya_lo_canjeaste": "Ese cupón ya lo canjeaste antes.", "cupon_agotado": "Ese cupón ya se agotó 😔",
              "cupon_solo_soles": "Los cupones son en soles: tu billetera es de otro país."}


@router.post("/web/billetera/cupon")
def canjear_cupon_web(request: Request, body: dict = Body(...)) -> JSONResponse:
    """Canje de cupón = `POST /pagos/cupon/canjear` (misma lógica,
    `pagos.router.canjear_cupon`) sobre el correo de la sesión."""
    try:
        email = _sesion_json(request)
    except HTTPException:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión para canjear."}, status_code=401)
    codigo = str((body or {}).get("codigo") or "").strip()[:40]
    if not codigo:
        return JSONResponse({"ok": False, "error": "cupon_invalido", "mensaje": "Escribe el código del cupón."})
    # Los cupones valen en SOLES (`valor_soles`, pago en PEN): no se mezclan con un saldo en $ o Bs.
    iso, _ = pais_billetera(email)
    if iso != "PE":
        return JSONResponse({"ok": False, "error": "cupon_solo_soles", "mensaje": _MSJ_CUPON["cupon_solo_soles"]})
    r = _pagos.canjear_cupon(email, codigo)
    if not r.get("ok"):
        err = r.get("error", "cupon_invalido")
        return JSONResponse({"ok": False, "error": err,
                             "mensaje": _MSJ_CUPON.get(err, "Código inválido o vencido. Revísalo e intenta de nuevo.")})
    return JSONResponse(r)


# ── /mis-pagos ────────────────────────────────────────────────────────────────

def _dia_label(d: date, hoy: date) -> str:
    diff = (hoy - d).days
    if diff == 0:
        return "Hoy"
    if diff == 1:
        return "Ayer"
    if diff == -1:
        return "Mañana"
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
    return f"{d.day} {meses[d.month - 1]}" + (f" {d.year}" if d.year != hoy.year else "")


def armar_pagos(email: str) -> list[dict]:
    """= `_MisPagosScreenState._armar` (bonos + reservas) + cuotas de academia,
    compras del marketplace y recargas. Cada item: fecha, titulo, sub, moneda,
    monto, estado ('pagado' | 'bono' | 'pendiente'), href, em."""
    from web.router import _agrupar_reservas
    out: list[dict] = []
    bonos = bonos_comprados(email)
    mon_club = monedas_de_clubes([b["club"] for b in bonos])
    for b in bonos:
        d = _parse(b["creado"]) or _ahora()
        out.append({"fecha": d, "titulo": f"Bono de {b['horas_total']} horas", "sub": b["club"],
                    "moneda": mon_club.get(b["club"], "S/"), "monto": b["precio"], "estado": "pagado", "href": "", "em": "🎟️"})
    filas = [r for r in datos.reservas_de_usuario(email) if str(r.get("estado") or "") not in ("noShow", "no_show")]
    canchas = nombres_de_canchas([r.get("cancha_id") for r in filas])
    for r in _agrupar_reservas(filas):
        c = canchas.get(str(r.get("cancha_id") or "")) or {}
        lugar = c.get("club") or c.get("nombre") or "Cancha"
        grupo = r.get("_filas") or [r]
        total = sum(float(f.get("precio") or 0) + sum(float((x or {}).get("precio") or 0) for x in (f.get("extras") or []) if isinstance(x, dict))
                    + float(f.get("cargo_servicio") or 0) for f in grupo)
        es_bono = str(r.get("medio_pago") or "") == "bono"
        pagado = all(bool(f.get("pagado")) for f in grupo)
        ref = r.get("grupo_reserva_id") or r.get("id")
        fecha = _parse(r.get("fecha")) or _ahora()
        con_comp = pagado or str(r.get("estado") or "") == "confirmada"
        turnos = int(r.get("turnos") or 1)
        out.append({"fecha": fecha, "titulo": f"Reserva · {lugar}",
                    "sub": f"{_dia_label(fecha.date(), _hoy())} {r.get('hora_inicio') or ''}–{r.get('hora_fin') or ''}"
                           + (f" · {turnos} turnos" if turnos > 1 else ""),
                    "moneda": r.get("moneda") or "S/", "monto": 0.0 if es_bono else total,
                    "estado": "bono" if es_bono else ("pagado" if pagado else "pendiente"),
                    "href": f"/reserva/{ref}" if (con_comp and ref) else "", "em": "🎾"})
    from web.academia import _moneda as _mon_aca
    acas: dict[str, dict] = {}
    for m in matriculas_que_pago(email):
        aid = m["academia_id"]
        if aid not in acas:
            acas[aid] = datos.academia(aid) or {}
        a = acas[aid]
        sim = _mon_aca(a)[0] if a else "S/"
        alumno = str(m["data"].get("nombre") or "")
        for cu in m["data"].get("cuotas") or []:
            if not isinstance(cu, dict):
                continue
            pagada = bool(cu.get("pagada"))
            d = _parse(cu.get("fechaPago") if pagada else cu.get("vencimiento")) or _ahora()
            # Pendientes: solo las ya vencidas o del mes (lo que toca pagar), como "Mis clases".
            if not pagada and d > _ahora() + timedelta(days=31):
                continue
            monto = float(cu.get("monto") or 0) + float(cu.get("cargoServicio") or 0)
            out.append({"fecha": d, "titulo": f"{a.get('nombre') or 'Academia'} · {cu.get('concepto') or 'Cuota'}",
                        "sub": alumno, "moneda": sim, "monto": monto, "estado": "pagado" if pagada else "pendiente_aca",
                        "href": f"/academia/{aid}/matricula/{m['id']}", "em": "🎓"})
    for v in stores.ventas:
        if (v.comprador_email or "").strip().lower() == email:
            out.append({"fecha": _parse(v.creado_en) or _ahora(), "titulo": f"Compra · {v.producto_nombre}",
                        "sub": f"Vende {v.vendedor_nombre or v.vendedor_email}", "moneda": "S/", "monto": float(v.monto_soles or 0),
                        "estado": "pagado", "href": "", "em": "🛍️"})
    for p in stores.pagos:
        if p.tipo == "recarga" and p.estado == "aprobado" and p.dueno_id == email:
            out.append({"fecha": _parse(p.creado_en) or _ahora(), "titulo": "Recarga de saldo",
                        "sub": f"Comprobante N.º {p.id}", "moneda": SIMBOLO.get(_pagos.moneda_iso(p.moneda), "S/"),
                        "monto": p.monto_centimos / 100.0, "estado": "pagado", "href": "/mi-billetera", "em": "👛"})
    out.sort(key=lambda x: x["fecha"], reverse=True)
    return out


def _hoy() -> date:
    return _ahora().astimezone(timezone(timedelta(hours=-5))).date()


def _tarjeta_pago(p: dict) -> str:
    sim = p["moneda"]
    if p["estado"] == "bono":
        color, ic, mt, sub = "#067A38", "🎟️", "Con bono", f"{p['sub']} · descontado de tu bono"
    elif p["estado"] == "pendiente":
        color, ic, mt, sub = "#C13515", "⏳", _dinero(sim, p["monto"]), f"{p['sub']} · por pagar en la cancha"
    elif p["estado"] == "pendiente_aca":
        color, ic, mt, sub = "#C13515", "⏳", _dinero(sim, p["monto"]), f"{p['sub']} · por pagar" if p["sub"] else "Por pagar"
    else:
        color, ic, mt, sub = "#0B8A3E", p.get("em") or "✅", f"− {_dinero(sim, p['monto'])}", p["sub"]
    inner = (f"<span class='ic' style='background:{color}1F'>{ic}</span><span class='tx'><b>{e(p['titulo'])}</b>"
             f"<small>{e(sub)}</small></span><span class='mt' style='color:{color}'>{e(mt)}"
             + ("<small>Comprobante ›</small>" if p["href"] and p["href"] != "/mi-billetera" else "") + "</span>")
    return f"<a class='pag' href='{e(p['href'])}'>{inner}</a>" if p["href"] else f"<div class='pag'>{inner}</div>"


@router.get("/mis-pagos", response_class=HTMLResponse)
def pagina_mis_pagos(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/mis-pagos", "Mis pagos", "El historial de tus pagos está en la app.")
    if resp:
        return resp
    email = _email(ses)
    pagos = armar_pagos(email)
    hoy = _hoy()
    if not pagos:
        lista = ("<div class='bil-vacio'><span class='em'>🧾</span><b>Aún no tienes pagos</b>"
                 "Aquí verás tus compras de bonos y tus reservas, con lo que pagaste en cada una.</div>")
        resumen = ""
    else:
        pag: dict[str, float] = {}
        pen: dict[str, float] = {}
        for p in pagos:
            if p["estado"] == "bono":
                continue
            dst = pen if p["estado"].startswith("pendiente") else pag
            dst[p["moneda"]] = dst.get(p["moneda"], 0.0) + p["monto"]
        fmt = lambda d: " · ".join(_dinero(k, v) for k, v in d.items()) or "—"  # noqa: E731
        resumen = (f"<div class='pag-res'><div><small>Total pagado</small><b>{e(fmt(pag))}</b></div>"
                   f"<div><small>Por pagar</small><b style='color:#C13515'>{e(fmt(pen))}</b></div>"
                   f"<div><small>Movimientos</small><b>{len(pagos)}</b></div></div>")
        lista, dia = "", None
        for p in pagos:
            dl = _dia_label(p["fecha"].astimezone(timezone(timedelta(hours=-5))).date(), hoy)
            if dl != dia:
                dia = dl
                lista += f"<div class='pag-dia'>{e(dl)}</div>"
            lista += _tarjeta_pago(p)
    cuerpo = (f"<style>{_CSS}</style><div class='bil'>{_nav('pagos')}<h1>Mis pagos</h1>"
              "<p class='sub' style='font-size:14px'>Tu estado de cuenta: bonos que compraste, reservas (pagadas en línea, con bono "
              "o por pagar en la cancha), cuotas de academia, compras y recargas.</p>"
              + resumen
              + ("<div class='no-print' style='margin:4px 0 6px'><button class='btn sec chico' onclick='window.print()'>🖨️ Imprimir / guardar PDF</button></div>" if pagos else "")
              + lista + "<p class='sub' style='font-size:12px;margin-top:16px'>Documento generado por Pichangol. No es un comprobante tributario.</p></div>")
    return ui.shell("Mis pagos", cuerpo, sesion=ses, titulo_tab="Mis pagos · Pichangol")


# ── /mis-puntos ───────────────────────────────────────────────────────────────

def _fecha_corta(v) -> str:
    d = _parse(v)
    if not d:
        return str(v or "")
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
    return f"{d.day} {meses[d.month - 1]}"


@router.get("/mis-puntos", response_class=HTMLResponse)
def pagina_mis_puntos(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/mis-puntos", "Mis puntos", "Tus puntos Pichangol están en la app.")
    if resp:
        return resp
    email = _email(ses)
    tot = datos.puntos_de(email)
    disponibles, canjeados = int(tot.get("disponibles") or 0), int(tot.get("canjeados") or 0)
    reservas = reservas_para_puntos(email)
    bodega = bodega_para_puntos(email)
    canjes = canjes_de_puntos(email)
    pendientes = sum(r["puntos"] for r in reservas if not r["pagado"])
    valor = disponibles * 3 / 100
    iso, _ = pais_billetera(email)
    canchas = nombres_de_canchas([r["cancha_id"] for r in reservas])

    hist: list[tuple[datetime, str]] = []
    for r in reservas:
        c = canchas.get(r["cancha_id"]) or {}
        nom = c.get("club") or c.get("nombre") or "Reserva"
        hist.append((_parse(r["fecha"]) or _ahora(),
                     f"<div class='pts-it'><span class='em'>{'🎾' if r['pagado'] else '⏳'}</span><span class='tx'><b>{e(nom)}</b>"
                     f"<small>{e(_fecha_corta(r['fecha']))} · {e(r['hora_inicio'])}{'' if r['pagado'] else ' · por confirmar'}</small></span>"
                     f"<span class='n{'' if r['pagado'] else ' gris'}'>+{r['puntos']}</span></div>"))
    for p in bodega:
        hist.append((_parse(p["creado"]) or _ahora(),
                     f"<div class='pts-it'><span class='em'>🧃</span><span class='tx'><b>Bodega · {e(p['resumen'])}</b>"
                     f"<small>{e(_fecha_corta(p['creado']))} · pagado con saldo 💳</small></span><span class='n'>+{p['puntos']}</span></div>"))
    for c in canjes:
        hist.append((_parse(c["creado"]) or _ahora(),
                     f"<div class='pts-it'><span class='em'>🎁</span><span class='tx'><b>Canje · S/ {c['soles']:.2f} de descuento</b>"
                     f"<small>{e(_fecha_corta(c['creado']))} · en tu reserva</small></span><span class='n rojo'>−{c['puntos']}</span></div>"))
    hist.sort(key=lambda x: x[0], reverse=True)
    lista = "".join(h for _, h in hist) if hist else (
        "<div class='bil-vacio'><span class='em'>⭐</span><b>Aún no tienes puntos</b>Reserva y paga por la app o la web "
        "(o paga tu pedido de bodega con saldo) para empezar a acumular. Cada sol pagado es un punto.</div>")
    otra = ("" if iso == "PE" else
            f"<br>• Tus reservas en {e(PAISES[iso]['moneda'])} también suman (1 punto por cada {e(PAISES[iso]['moneda'])} 1); "
            "el canje hoy aplica al pagar en línea reservas en soles (Perú).")
    cuerpo = (
        f"<style>{_CSS}</style><div class='bil'>{_nav('puntos')}<h1>Mis puntos</h1>"
        f"<div class='pts-top'><div class='t'>⭐ Puntos Pichangol</div><div class='n'>{disponibles}</div>"
        f"<div class='v'>Valen S/ {valor:.2f} en descuentos al reservar en línea</div>"
        + (f"<div class='c'>Ya canjeaste {canjeados} puntos 🎉</div>" if canjeados > 0 else "") + "</div>"
        + (f"<div class='pts-pend'>⏳ +{pendientes} por confirmar: pídele al local que marque tu pago en efectivo para acreditarlos.</div>"
           if pendientes > 0 else "")
        + "<div class='pts-como'><b>Cómo funcionan</b><br>"
          "• Ganas 1 punto por cada S/ 1 que pagas por la app o la web (últimos 12 meses).<br>"
          "• Pago en línea: puntos al instante. Efectivo: cuando el local confirma tu pago.<br>"
          "• Los pedidos de bodega pagados con tu SALDO Pichangol también suman (al entregarse). En efectivo no acumulan.<br>"
          "• Cada 100 puntos = S/ 3 de descuento al pagar en línea tu próxima reserva en la app (el descuento lo pone Pichangol, no el local)."
        + otra + "</div>"
        "<h2>Historial (últimos 12 meses)</h2>" + lista
        + "<p class='sub' style='font-size:13px;margin-top:18px'><a href='/mis-reservas'>Mis reservas</a> · "
          "<a href='/mi-billetera'>Mi billetera</a></p></div>")
    return ui.shell("Mis puntos", cuerpo, sesion=ses, titulo_tab="Mis puntos · Pichangol")


# ── /mi-pais ──────────────────────────────────────────────────────────────────

@router.get("/mi-pais", response_class=HTMLResponse)
def pagina_mi_pais(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/mi-pais", "Mi país", "Tu país se cambia en la app (Perfil → Mi país).")
    if resp:
        return resp
    email = _email(ses)
    canchas = datos.canchas_de_dueno(email)
    iso, fuente = pais_billetera(email, canchas)
    P = PAISES[iso]
    puede = puede_cambiar_pais(email)
    nota = {"recarga": "Tu saldo quedó en esta moneda con tu última recarga.",
            "cancha": "Sigue el país de tu cancha mientras no hayas recargado.",
            "elegido": "Lo elegiste tú.", "defecto": "Aún no lo has elegido."}[fuente]
    if puede:
        aviso = ("<p class='sub' style='text-align:center'>Define la moneda de tu billetera y cómo recargas "
                 "(Yape/tarjeta, PayPhone o Libélula). El país que exploras en el mapa se elige en el buscador.</p>")
    else:
        aviso = (f"<div class='bil-card warn'><span class='em'>👛</span><span class='tx'><b>Tu billetera tiene saldo</b>"
                 f"Tienes saldo en {e(P['moneda'])}. Para cambiar tu país primero úsalo o solicita su liquidación; después podrás "
                 "elegir otro país y tu próxima recarga será en su moneda.</span></div>")
    chips = "".join(
        f"<button type='button' data-iso='{k}' class='{'sel' if k == iso else ''}'{'' if puede else ' disabled'}>"
        f"{ui.bandera(k)} {e(v['nombre'])}{' ✓' if k == iso else ''}</button>" for k, v in PAISES.items())
    extra = ("<p class='sub' style='font-size:12.5px;text-align:center'>Tienes canchas registradas: mientras no recargues, "
             "tu billetera sigue la moneda del país de tu cancha.</p>" if canchas else "")
    cuerpo = (
        f"<style>{_CSS}</style><div class='bil'>{_nav('pais')}<h1>Mi país</h1>"
        f"<div class='pais-actual'>{ui.bandera(iso)}<div><b>{e(P['nombre'])} · {e(P['moneda'])}</b>"
        f"<small>{e(nota)} Recargas con {e(P['pasarela_nombre'])}.</small></div></div>"
        f"<div style='margin-top:14px'>{aviso}</div><div class='pais-chips'>{chips}</div>{extra}</div>"
        "<script>(function(){ document.querySelectorAll('.pais-chips [data-iso]').forEach(function(b){ b.addEventListener('click', function(){\n"
        "  if(b.classList.contains('sel') || b.disabled) return;\n"
        "  var nom = b.textContent.replace('✓','').trim();\n"
        "  pcgConfirmar({titulo: 'Cambiar a ' + nom, icono: '🌎', confirmar: 'Sí, cambiar', cancelar: 'Cancelar',\n"
        "                mensaje: 'Tu billetera pasará a la moneda de ' + nom + ' y tu próxima recarga será en esa moneda.'}).then(function(ok){\n"
        "    if(!ok) return; pcgCargando('Guardando…');\n"
        "    fetch('/web/mi-pais', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({iso: b.dataset.iso})})\n"
        "      .then(function(r){ return r.json(); }).then(function(p){ pcgCargando(false);\n"
        "        if(p.ok){ pcgAvisar({titulo: 'Listo', icono: '✅', confirmar: 'Entendido', mensaje: p.mensaje}).then(function(){ pcgRecargar(); }); }\n"
        "        else { pcgAvisar({titulo: 'No se pudo cambiar', icono: '👛', confirmar: 'Entendido', mensaje: p.mensaje || 'Intenta de nuevo.'}); }\n"
        "      }).catch(function(){ pcgCargando(false); pcgToast('Sin conexión. Intenta de nuevo.'); });\n"
        "  }); }); }); })();</script>")
    return ui.shell("Mi país", cuerpo, sesion=ses, titulo_tab="Mi país · Pichangol")


@router.post("/web/mi-pais")
def cambiar_mi_pais(request: Request, body: dict = Body(...)) -> JSONResponse:
    """= `AppState.cambiarPaisCasa`: solo con saldo y regalo en 0; descongela
    la moneda del saldo (la próxima recarga la fija en la nueva)."""
    try:
        email = _sesion_json(request)
    except HTTPException:
        return JSONResponse({"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión."}, status_code=401)
    iso = str((body or {}).get("iso") or "").strip().upper()
    if iso not in PAISES:
        return JSONResponse({"ok": False, "error": "pais_invalido", "mensaje": "Elige Perú, Bolivia o Ecuador."}, status_code=400)
    if not puede_cambiar_pais(email):
        actual, _ = pais_billetera(email)
        return JSONResponse({"ok": False, "error": "tiene_saldo",
                             "mensaje": f"Tienes saldo en {PAISES[actual]['moneda']}. Para cambiar tu país primero úsalo o "
                                        "solicita su liquidación."}, status_code=409)
    ficha = stores.clientes_pago.setdefault(email, {})
    ficha["pais_casa"] = iso
    ficha["pais_casa_en"] = _ahora().isoformat()
    efectivo, fuente = pais_billetera(email)
    P = PAISES[efectivo]
    msj = f"Tu billetera ahora es de {P['nombre']} ({P['moneda']})."
    if efectivo != iso and fuente == "cancha":
        msj = (f"Guardamos {PAISES[iso]['nombre']} como tu país. Como tienes canchas en {P['nombre']}, tu billetera sigue en "
               f"{P['moneda']} hasta tu próxima recarga.")
    return JSONResponse({"ok": True, "iso": iso, "efectivo": efectivo, "mensaje": msj})
