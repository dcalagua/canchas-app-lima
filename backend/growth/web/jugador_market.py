"""MARKETPLACE y BONOS del JUGADOR en la web (lado comprador, espejo del APK;
pedido del director, 29-sep-2026: "en la web implementa las mismas
funcionalidades que existen actualmente en el app").

- GET  /marketplace            = `marketplace_screen.dart`: feed GLOBAL de
  `pichangol_productos` activos (mismo filtro que `ProductosRepo.fetchActivos`:
  `activo = true`, más nuevos primero), buscador (nombre, vendedor, categoría),
  chips con las categorías PRESENTES, tarjetas con foto, precio en SU moneda,
  stock y "Vendedor verificado ✓" (`pichangol_verificaciones`). "Vender" →
  Mi tienda (`/anfitrion/tienda`), "Mis compras" → `/mis-ordenes`.
- GET  /marketplace/{id}       = `producto_detalle_screen.dart`: foto,
  precio, categoría, descripción, vendedor y "Comprar". En soles, Culqi
  Checkout v4 con el selector Yape/Tarjeta y el modal `pcgResumenPago`; en $
  o Bs, la pasarela HOSPEDADA del país (`POST /web/marketplace/comprar-
  pasarela` y `/web/bonos/comprar-pasarela`, fase 2 parte 2: la unidad se
  aparta ANTES de ir a pagar y vuelve si no se paga; tras el pago,
  `venta_pagada` / `bono_pagado`, las mismas que Culqi). Sin pasarela en
  PRD: "cómpralo en la app".
- POST /web/marketplace/comprar → aparta 1 unidad (UPDATE atómico, así dos
  compradores no se llevan la última), cobra (`culqi.crear_cargo(cliente=)`)
  y registra la venta EXACTAMENTE como el APK: `pagos.router.post_venta`
  (`VentaProductoReq`, idempotente por `venta_id` = N.º de operación de
  Culqi → neto "por recibir" del vendedor + ORDEN en escrow `stores.ventas`)
  y el push "¡Te compraron! 🛍️" (`AvisosService.ventaNueva`). Si Culqi
  rechaza, la unidad vuelve al stock.
- GET  /mis-ordenes            = `mis_ordenes_screen.dart` (modo comprador):
  órdenes del correo con estado (pagado · retenido / entregado / completado ·
  liberado / en disputa), "Confirmar recepción" (libera el pago) y
  "Problema" (disputa) → `ventas.router.marcar_recibido|abrir_disputa` + los
  mismos pushes del app. Coordinar la entrega: el APK abre el chat; la web
  ofrece el WhatsApp del vendedor si está en su perfil (`pichangol_perfiles`,
  solo al comprador y solo después de pagar) o "Chat en la app".
- GET  /mis-bonos              = `mis_bonos_screen.dart`: créditos de
  `pichangol_bonos_comprados` del correo (local, horas compradas, precio en
  la moneda del local, barra de consumo, saldo) + "Comprar más horas".
- GET  /bonos/{cancha_id}      = sección `_SeccionBonos` de la ficha del local
  en el app: packs activos del local (`pichangol_bonos`) y mi saldo ahí.
- POST /web/bonos/comprar      → cobra con Culqi y replica `_comprar` del app:
  crédito en `pichangol_bonos_comprados` (id `bono_<operación>`, upsert
  idempotente), contabilidad `post_venta` y push "¡Vendiste un bono! 🎟️".

El CANJE del bono (reservar descontando horas) está en la ficha del app
(`club_detalle._reservar` con `metodo == 'bono'`) y en la ficha web
/reservar (`web/beneficios.py`: "Usar mi bono" en el resumen, 1 hora = 1
turno, aparta las horas con el hold y las devuelve si no se paga o se
cancela a tiempo).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
import empresa
from db import pg
from pagos import culqi
from pagos.stock_productos import apartar_unidad, devolver_unidad  # noqa: F401 (tests los monkeypatchean aquí)
from web import catalogos, datos, sesion, ui
from web.router import PLAY_URL, _moneda_de, _no_encontrada, _pago_web_disponible, _pasarela_web

router = APIRouter()
e = ui.e

_ISO_POR_SIMBOLO = {"S/": "PEN", "S/.": "PEN", "PEN": "PEN", "$": "USD", "USD": "USD", "BS": "BOB", "BS.": "BOB", "BOB": "BOB"}
_SIMBOLO_POR_ISO = {"PEN": "S/", "USD": "$", "BOB": "Bs"}
_PAIS_POR_ISO = {"PEN": "PE", "USD": "EC", "BOB": "BO"}
_CODIGO_TEL = {"PE": "51", "BO": "591", "EC": "593"}  # `PaisConfig.codigoTel`


def _iso(moneda: str | None) -> str:
    return _ISO_POR_SIMBOLO.get((moneda or "").strip().upper(), "PEN")


def _sim(moneda: str | None) -> str:
    return _SIMBOLO_POR_ISO[_iso(moneda)]


def _monto(sim: str, v: float) -> str:
    return f"{sim} {float(v or 0):.2f}"


def _wa_de(celular: str, pais: str) -> str:
    """Número para wa.me: solo dígitos y con el prefijo del país si el
    celular del perfil viene en formato local (como `codigoTelActual`)."""
    d = re.sub(r"\D", "", celular or "")
    if len(d) < 7:
        return ""
    cc = _CODIGO_TEL.get(pais, "51")
    if d.startswith(cc) and len(d) > len(cc) + 7:
        return d
    return cc + d.lstrip("0")


# ── datos (Postgres directo, mismas tablas del APK; todo fail-safe) ──────────

def productos_activos() -> list[dict]:
    """Feed del comprador = `ProductosRepo.fetchActivos` (activos, nuevos primero)."""
    if not pg.habilitado:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(datos._COLS_PROD)} FROM pichangol_productos WHERE activo = true "
                        "ORDER BY creado_en DESC LIMIT 500")
            return [datos._norm_producto(pg._fila_a_dict(datos._COLS_PROD, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def producto(producto_id: str) -> dict | None:
    return datos.producto_por_id(producto_id)


def productos_por_ids(ids: list[str]) -> dict[str, dict]:
    ids = [i for i in {str(x) for x in ids} if i]
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(datos._COLS_PROD)} FROM pichangol_productos WHERE id = ANY(%s)", (ids,))
            return {p["id"]: p for p in (datos._norm_producto(pg._fila_a_dict(datos._COLS_PROD, f)) for f in cur.fetchall())}
    except Exception:  # noqa: BLE001
        return {}


def verificados(emails: list[str]) -> set[str]:
    """Correos con identidad verificada (espejo de `sincronizarVerificados`),
    en UNA consulta para todo el feed."""
    es = sorted({(x or "").strip().lower() for x in emails if x})
    if not pg.habilitado or not es:
        return set()
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT DISTINCT lower(email) FROM pichangol_verificaciones "
                        "WHERE lower(email) = ANY(%s) AND estado = 'verificado'", (es,))
            return {str(f[0]) for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return set()


def perfiles(emails: list[str]) -> dict[str, dict]:
    """Nombre, foto y celular públicos (`pichangol_perfiles`, = `cargarPerfiles`)."""
    es = sorted({(x or "").strip().lower() for x in emails if x})
    if not pg.habilitado or not es:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT email, nombre, foto_url, celular FROM pichangol_perfiles WHERE email = ANY(%s)", (es,))
            return {str(f[0]).lower(): {"nombre": f[1] or "", "foto_url": f[2] or "", "celular": f[3] or ""} for f in cur.fetchall()}
    except Exception:  # noqa: BLE001
        return {}


# Apartar / devolver la unidad vive en `pagos/stock_productos.py` (compartido
# con el APK: `POST /pagos/venta/apartar|devolver`).


_COLS_OFERTA = ["id", "dueno", "club", "nombre", "horas", "precio", "activo", "creado"]
_COLS_BONO = ["id", "bono_id", "dueno", "club", "comprador", "comprador_nombre", "horas_total",
              "horas_usadas", "precio", "venta_id", "creado"]


def _norm_oferta(d: dict) -> dict:
    d["horas"] = int(d.get("horas") or 0)
    d["precio"] = float(d.get("precio") or 0)
    d["activo"] = bool(d.get("activo"))
    for k in ("id", "dueno", "club", "nombre"):
        d[k] = str(d.get(k) or "")
    return d


def _norm_bono(d: dict) -> dict:
    d["horas_total"] = int(d.get("horas_total") or 0)
    d["horas_usadas"] = int(d.get("horas_usadas") or 0)
    d["precio"] = float(d.get("precio") or 0)
    d["saldo"] = max(0, min(d["horas_total"], d["horas_total"] - d["horas_usadas"]))  # = BonoComprado.saldo
    for k in ("id", "bono_id", "dueno", "club", "comprador", "comprador_nombre", "venta_id"):
        d[k] = str(d.get(k) or "")
    return d


def ofertas_de_local(club: str, dueno: str) -> list[dict]:
    """Packs ACTIVOS del local (= `BonosRepo.ofertasDeClub`, por horas). Se
    filtra también por el dueño de la cancha: dos locales con el mismo nombre
    no se mezclan."""
    dueno = (dueno or "").strip().lower()
    if not pg.habilitado or not club or not dueno:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_OFERTA)} FROM pichangol_bonos WHERE club = %s AND lower(dueno) = %s "
                        "AND activo = true ORDER BY horas ASC", (club, dueno))
            return [_norm_oferta(pg._fila_a_dict(_COLS_OFERTA, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def oferta(oferta_id: str) -> dict | None:
    if not pg.habilitado or not oferta_id:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_OFERTA)} FROM pichangol_bonos WHERE id = %s", (oferta_id,))
            f = cur.fetchone()
            return _norm_oferta(pg._fila_a_dict(_COLS_OFERTA, f)) if f else None
    except Exception:  # noqa: BLE001
        return None


def bonos_de(email: str) -> list[dict]:
    """Créditos del jugador (= `BonosRepo.comprasDe`, recientes primero)."""
    email = (email or "").strip().lower()
    if not pg.habilitado or not email:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLS_BONO)} FROM pichangol_bonos_comprados WHERE lower(comprador) = %s "
                        "ORDER BY creado DESC", (email,))
            return [_norm_bono(pg._fila_a_dict(_COLS_BONO, f)) for f in cur.fetchall()]
    except Exception:  # noqa: BLE001
        return []


def registrar_bono(fila: dict) -> bool:
    """= `BonosRepo.registrarCompra` (idempotente por id `bono_<operación>`)."""
    if not pg.habilitado:
        return False
    cols = ["id", "bono_id", "dueno", "club", "comprador", "comprador_nombre", "horas_total", "horas_usadas", "precio", "venta_id"]
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"INSERT INTO pichangol_bonos_comprados ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                        "ON CONFLICT (id) DO NOTHING", tuple(fila.get(c) for c in cols))
            conn.commit()
            return True
    except Exception:  # noqa: BLE001
        return False


def canchas_de_locales(pares: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """(club, dueño) → una cancha registrada de ese local (moneda, foto y
    enlace para comprar más horas). Una sola consulta."""
    clubs = sorted({c for c, _ in pares if c})
    if not pg.habilitado or not clubs:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, club, lower(dueno), moneda, foto_url, fotos, lat, lng, precio_hora, verificada FROM pichangol_canchas "
                        "WHERE club = ANY(%s) AND coalesce(eliminada, false) = false ORDER BY verificada DESC, id", (clubs,))
            out: dict[tuple[str, str], dict] = {}
            for f in cur.fetchall():
                k = (str(f[1] or ""), str(f[2] or ""))
                if k not in out:
                    fotos = datos._json_list(f[5])
                    out[k] = {"id": str(f[0]), "club": k[0], "dueno": k[1], "moneda": f[3] or "", "lat": f[6], "lng": f[7],
                              "foto": (f[4] or next((x for x in fotos if str(x).startswith("http")), "")) or "",
                              "precio_hora": float(f[8] or 0)}
            return out
    except Exception:  # noqa: BLE001
        return {}


# ── helpers de página ────────────────────────────────────────────────────────

def _sin_login(titulo: str, que: str) -> HTMLResponse:
    cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
              f"<h1 style='font-size:22px'>{e(titulo)}</h1>"
              f"<p class='sub'>En esta web aún no está activo el inicio de sesión. {e(que)}</p>"
              f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
    return ui.shell(titulo, cuerpo, sesion=None)


def _a_entrar(ruta: str) -> HTMLResponse:
    from urllib.parse import quote
    return HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(ruta, safe='')}"})


def _cat(clave: str) -> tuple[str, str]:
    return catalogos.CATEGORIAS_PRODUCTO.get(clave or "otros", catalogos.CATEGORIAS_PRODUCTO["otros"])


def _foto_producto(p: dict, clase: str = "ph") -> str:
    if (p.get("foto_url") or "").startswith("http"):
        return f"<img src='{e(p['foto_url'])}' alt='{e(p.get('nombre'))}' loading='lazy'>"
    return f"<span class='{clase}'>{_cat(p.get('categoria'))[1]}</span>"


def _stock_txt(p: dict) -> str:
    s = p.get("stock")
    if s is None:
        return ""
    if s <= 0:
        return "Agotado"
    return "Queda 1" if s == 1 else f"Quedan {s}"


_CSS = """<style>
.mk-h{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin:22px 0 6px}
.mk-h h1{margin:0}.mk-h .acc{display:flex;gap:8px;flex-wrap:wrap}.mk-h .acc .btn{padding:10px 16px;font-size:14px}
.mk-busca{position:relative;margin:14px 0 10px;max-width:640px}.mk-busca input{padding-left:42px;border-radius:999px;background:var(--gris);border-color:transparent}
.mk-busca span{position:absolute;left:15px;top:50%;transform:translateY(-50%);opacity:.6}
.mk-cats{display:flex;gap:8px;overflow-x:auto;padding:4px 0 10px;scrollbar-width:none}.mk-cats::-webkit-scrollbar{display:none}
.mk-cats .chip{flex:none}.mk-cats .chip.sel{background:var(--noche);color:#fff;border-color:var(--noche)}
.mk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(170px,100%),1fr));gap:22px 16px;margin-top:10px}
@media(max-width:560px){.mk-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px 12px}}
.mk-card{display:block;color:inherit;text-decoration:none;min-width:0}
.mk-card .f{position:relative;aspect-ratio:1;border-radius:14px;overflow:hidden;background:var(--gris);display:flex;align-items:center;justify-content:center}
.mk-card .f img{width:100%;height:100%;object-fit:cover;transition:transform .3s}.mk-card:hover .f img{transform:scale(1.03)}
.mk-card .ph{font-size:46px}.mk-card .tag{position:absolute;left:10px;top:10px;background:#fff;border-radius:999px;padding:4px 9px;font-size:11.5px;font-weight:800;box-shadow:0 1px 4px rgba(0,0,0,.12)}
.mk-card .tag.agot{background:var(--bad-bg);color:var(--bad-fg)}
.mk-card b.n{display:block;margin-top:9px;font-size:14.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mk-card .pr{font-weight:800;font-size:15px;margin-top:1px}.mk-card .vd{display:flex;gap:4px;align-items:center;color:var(--tenue);font-size:12.5px;margin-top:2px;min-width:0}
.mk-card .vd span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.vok{color:var(--esmeralda);font-weight:800;flex:none}
#mkGrid{padding-bottom:70px}.mk-vacio{text-align:center;padding:60px 16px;color:var(--tenue)}.mk-vacio .em{font-size:52px}.mk-vacio b{display:block;color:var(--noche);font-size:18px;margin-top:8px}
.mk-fab{position:fixed;right:20px;bottom:22px;z-index:25;box-shadow:var(--sombra2);border-radius:999px!important;padding:13px 20px!important}
.mk-foto{aspect-ratio:1;border-radius:var(--r-lg);overflow:hidden;background:var(--gris);display:flex;align-items:center;justify-content:center;max-width:560px}
.mk-foto img{width:100%;height:100%;object-fit:cover}.mk-foto .ph{font-size:80px}
.mk-vend{display:flex;gap:12px;align-items:center;padding:14px 0;border-top:1px solid var(--trazo);border-bottom:1px solid var(--trazo);margin-top:18px}
.mk-av{flex:none;width:46px;height:46px;border-radius:50%;background:var(--teal);color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;overflow:hidden;font-size:18px}
.mk-av img{width:100%;height:100%;object-fit:cover}
.mk-prot{display:flex;gap:10px;background:var(--gris);border-radius:12px;padding:12px 14px;margin-top:14px;font-size:13.5px}
.orden{background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:14px;margin-bottom:12px;box-shadow:var(--sombra);min-width:0}
.orden.nueva,.bono.nueva{box-shadow:0 0 0 2px var(--esmeralda)}
.orden .cab{display:flex;gap:12px;align-items:center;min-width:0}.orden .fo{flex:none;width:58px;height:58px;border-radius:12px;overflow:hidden;background:var(--gris);display:flex;align-items:center;justify-content:center;font-size:26px}
.orden .fo img{width:100%;height:100%;object-fit:cover}.orden .tx{flex:1;min-width:0}.orden .tx b{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}
.orden .mt{font-weight:800;flex:none}.orden .pie{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:10px}
.orden .pie .btn{padding:9px 14px;font-size:13.5px;flex:0 0 auto;min-width:0}.orden .pie .esp{flex:1}
.btn.rojo{background:#fff;color:var(--bad-fg);border:1px solid var(--bad-bg)}
.bono{background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:16px;margin-bottom:12px;box-shadow:var(--sombra);min-width:0}
.bono .cab{display:flex;gap:12px;align-items:center}.bono .ic{flex:none;width:44px;height:44px;border-radius:12px;background:var(--tinte);display:flex;align-items:center;justify-content:center;font-size:22px}
.bono.sin .ic{background:var(--gris)}.bono .tx{flex:1;min-width:0}.bono .tx b{display:block;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.barra{height:8px;border-radius:8px;background:#EEF1EF;overflow:hidden;margin-top:12px}.barra i{display:block;height:100%;background:var(--teal);border-radius:8px}
.bono.sin .barra i{background:#B7C0C6}.bono .fila{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:13.5px}
.bono .fila b{color:var(--teal)}.bono.sin .fila b{color:var(--tenue)}
.pack{display:flex;gap:12px;align-items:center;border:1px solid var(--trazo);border-radius:16px;padding:14px;margin-top:10px;background:#fff;min-width:0}
.pack .h{flex:none;min-width:54px;height:48px;border-radius:12px;background:var(--tinte);color:var(--teal);font-weight:800;display:flex;align-items:center;justify-content:center;font-size:16px;padding:0 8px}
.pack .tx{flex:1;min-width:0}.pack .tx b{display:block}.pack .btn{flex:none;padding:10px 14px;font-size:14px}
.pack.sel{box-shadow:0 0 0 2px var(--esmeralda);border-color:transparent}
.saldo{display:flex;gap:8px;align-items:center;background:var(--tinte);color:var(--teal);font-weight:800;border-radius:14px;padding:12px 14px;margin-top:12px}
.mk-wrap{max-width:760px}
</style>"""


def _js_culqi(cfg: dict) -> str:
    """Checkout común (producto y bono): pcgResumenPago → Culqi con el medio
    elegido (Yape por defecto) → POST al endpoint → redirige al comprobante.
    Con `cfg.pasarela` (cobro en $ / Bs, fase 2 parte 2) no hay Culqi: tras el
    resumen, POST a `cfg.urlPasarela` crea la orden y el navegador va a la
    pasarela hospedada del país (`web/pago_hospedado.py`)."""
    from web import pago_hospedado as ph
    hosp = bool(cfg.get("pasarela")) and cfg.get("pasarela") != "culqi"
    return (("" if hosp else "<script src='https://checkout.culqi.com/js/v4'></script>")
            + "<script>window.__mk=" + json.dumps(cfg, ensure_ascii=False) + ";</script><script>"
            + (sesion.JS_SESION if sesion.activo() else "") + (ph.JS_IR_PASARELA if hosp else "") + r"""
(function(){
  var C = window.__mk, $ = function(id){ return document.getElementById(id); };
  function error(m){ var el = $('mkErr'); if(el){ el.textContent = m; el.style.display = 'block'; } else if(window.pcgAvisar) pcgAvisar({titulo: 'No se pudo', mensaje: m, icono: '⚠️'}); }
  function botones(txt, dis){ document.querySelectorAll('[data-pagar]').forEach(function(b){ if(txt) b.textContent = txt; b.disabled = !!dis; }); }
  function pagar(ev){
    var btn = ev && ev.currentTarget; if(btn && btn.dataset.oferta){ C.oferta = btn.dataset.oferta; C.monto = +btn.dataset.monto; C.linea = btn.dataset.linea; }
    var el = $('mkErr'); if(el) el.style.display = 'none';
    if(C.login && !C.sesion){ error('Inicia sesión con Google para comprar.'); var lb = $('loginBox'); if(lb) lb.scrollIntoView({behavior: 'smooth', block: 'center'}); return; }
    var hosp = !!(C.pasarela && C.pasarela !== 'culqi');
    if(!C.pk && !hosp){ error('El pago en línea no está disponible por ahora.'); return; }
    var m = hosp ? C.pasarela : (window.pcgMedioPago ? pcgMedioPago() : 'yape');
    var montoC = Math.round(C.monto * 100);
    pcgResumenPago({moneda: C.moneda, medio: m, medioNombre: hosp ? C.pasarelaNombre : '', lineas: [{t: C.linea, m: C.monto}], total: C.monto,
                    nota: (C.nota || '') + (hosp ? ' Te llevamos a la página segura de ' + C.pasarelaNombre + '.' : '')}).then(function(ok){
      if(!ok) return;
      if(hosp){
        var cuerpo = Object.assign({}, C.cuerpo || {}); if(C.oferta) cuerpo.oferta_id = C.oferta;
        botones('Abriendo ' + C.pasarelaNombre + '…', true);
        pcgIrPasarela(C.urlPasarela, cuerpo, C.pasarelaNombre).then(function(p){
          if(p && p.ok) return;
          botones(C.boton, false);
          if(p && p.error === 'sesion_requerida'){ C.sesion = null; }
          error((p && p.mensaje) || 'No pudimos abrir el pago. Inténtalo de nuevo.');
        });
        return;
      }
      Culqi.publicKey = C.pk;
      Culqi.settings({ title: 'Pichangol', currency: 'PEN', amount: montoC });
      Culqi.options({ lang: 'es', installments: false,
        paymentMethods: { yape: m === 'yape', tarjeta: m === 'tarjeta', bancaMovil: false, agente: false, billetera: false, cuotealo: false },
        style: { logo: '', bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Pagar', buttonTextColor: '#FFFFFF' } });
      window.culqi = function(){
        if(Culqi.token){
          var body = Object.assign({token: Culqi.token.id, medio: (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape'}, C.cuerpo || {});
          if(C.oferta) body.oferta_id = C.oferta;
          Culqi.close(); botones('Confirmando tu pago…', true); pcgCargando(C.cargando || 'Confirmando tu compra…');
          fetch(C.url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
            .then(function(x){ return x.json(); })
            .then(function(p){
              if(p.ok){ if(p.aviso){ try{ sessionStorage.setItem('pcg_aviso', p.aviso); }catch(e){} } pcgIr(p.url, 'Listo…'); return; }
              pcgCargando(false); botones(C.boton, false);
              if(p.error === 'sesion_requerida'){ C.sesion = null; }
              error(p.mensaje || 'El pago no se pudo procesar. No se te cobró nada.');
            }).catch(function(){ pcgCargando(false); botones(C.boton, false); error('No pudimos confirmar el pago. Si te cobraron, escríbenos con tu correo.'); });
        } else if(Culqi.order){ error('Este medio de pago no está habilitado. Usa Yape o tarjeta.'); }
        else { error((Culqi.error && Culqi.error.user_message) || 'No se pudo procesar el pago.'); }
      };
      Culqi.open();
    });
  }
  document.querySelectorAll('[data-pagar]').forEach(function(b){ b.addEventListener('click', pagar); });
})();
</script>""")


def _login_box(volver: str, texto: str) -> str:
    return (f"<div class='login-box' id='loginBox' style='margin-top:14px'><b>Inicia sesión con Google para comprar</b>"
            f"<div class='sub' style='margin:4px 0 12px'>{e(texto)}</div>"
            f"{sesion.boton_google(volver=volver)}<div class='estado bad' id='sesionErr'></div></div>")


# ── 1) MARKETPLACE (feed) ────────────────────────────────────────────────────

@router.get("/marketplace", response_class=HTMLResponse)
def pagina_marketplace(request: Request) -> HTMLResponse:
    ses = sesion.de_request(request)
    prods = productos_activos()
    ok = verificados([p["vendedor_email"] for p in prods])
    presentes = {p.get("categoria") or "otros" for p in prods}
    chips = "<button type='button' class='chip sel' data-cat=''>Todo</button>" + "".join(
        f"<button type='button' class='chip' data-cat='{e(k)}'>{em} {e(n)}</button>"
        for k, (n, em) in catalogos.CATEGORIAS_PRODUCTO.items() if k in presentes)
    tarjetas = []
    for p in prods:
        sim = _sim(p.get("moneda"))
        st = _stock_txt(p)
        vend = p.get("vendedor_nombre") or "Vendedor"
        cat_n = _cat(p.get("categoria"))[0]
        q = " ".join((p.get("nombre") or "", vend, cat_n)).lower()
        tarjetas.append(
            f"<a class='mk-card' href='/marketplace/{e(p['id'])}' data-cat='{e(p.get('categoria') or 'otros')}' data-q='{e(q)}'>"
            f"<div class='f'>{_foto_producto(p)}"
            + (f"<span class='tag{' agot' if st == 'Agotado' else ''}'>{e(st)}</span>" if st else "")
            + f"</div><b class='n'>{e(p.get('nombre'))}</b><div class='pr'>{e(_monto(sim, p['precio']))}</div>"
            f"<div class='vd'><span>{e(vend)}</span>"
            + ("<em class='vok' title='Vendedor verificado'>✓</em>" if p["vendedor_email"].lower() in ok else "")
            + "</div></a>")
    grid = (f"<div class='mk-grid' id='mkGrid'>{''.join(tarjetas)}</div>"
            "<div class='mk-vacio' id='mkNada' style='display:none'><div class='em'>🔎</div><b>Sin resultados</b>Prueba con otra palabra o categoría.</div>"
            if tarjetas else
            "<div class='mk-vacio'><div class='em'>🏪</div><b>Aún no hay productos</b>"
            "Cuando los locales publiquen raquetas, pelotas y más, aparecerán aquí.</div>")
    cuerpo = (_CSS
              + "<div class='mk-h'><div><h1>Marketplace Pichangol</h1>"
              "<p class='sub'>Raquetas, pelotas e indumentaria de los locales y jugadores verificados. Pagas seguro y coordinas la entrega con el vendedor.</p></div>"
              "<div class='acc'><a class='btn sec' href='/mis-ordenes'>🛍️ Mis compras</a></div></div>"
              "<div class='mk-busca'><span>🔍</span><input id='mkQ' type='search' placeholder='Buscar producto o vendedor…' autocomplete='off' maxlength='60'></div>"
              + (f"<div class='mk-cats' id='mkCats'>{chips}</div>" if prods else "")
              + grid
              + "<a class='btn mk-fab' href='/anfitrion/tienda'>🏷️ Vender</a>"
              + r"""<script>(function(){
  var q = document.getElementById('mkQ'), cat = '', cards = [].slice.call(document.querySelectorAll('.mk-card'));
  var u = new URLSearchParams(location.search); if(u.get('q')) q.value = u.get('q'); cat = u.get('cat') || '';
  function sel(){ document.querySelectorAll('#mkCats .chip').forEach(function(c){ c.classList.toggle('sel', c.dataset.cat === cat); }); }
  function filtrar(){ var t = (q.value || '').trim().toLowerCase(), n = 0;
    cards.forEach(function(c){ var ok = (!cat || c.dataset.cat === cat) && (!t || c.dataset.q.indexOf(t) >= 0); c.style.display = ok ? '' : 'none'; if(ok) n++; });
    var nada = document.getElementById('mkNada'); if(nada) nada.style.display = (cards.length && !n) ? '' : 'none'; }
  q.addEventListener('input', filtrar);
  document.querySelectorAll('#mkCats .chip').forEach(function(c){ c.addEventListener('click', function(){ cat = c.dataset.cat; sel(); filtrar(); }); });
  sel(); filtrar();
})();</script>""")
    return ui.shell("Marketplace", cuerpo, sesion=ses, ancho=True, titulo_tab="Marketplace · Pichangol",
                    desc="Marketplace Pichangol: raquetas, pelotas, calzado e indumentaria deportiva con pago seguro.")


# ── 2) FICHA DEL PRODUCTO + compra ───────────────────────────────────────────

@router.get("/marketplace/{producto_id}", response_class=HTMLResponse)
def pagina_producto(request: Request, producto_id: str) -> HTMLResponse:
    ses = sesion.de_request(request)
    yo = ((ses or {}).get("email") or "").strip().lower()
    p = producto(producto_id)
    if not p or (not p.get("activo") and p.get("vendedor_email", "").lower() != yo):
        return _no_encontrada("Producto no disponible")
    vend_email = p["vendedor_email"].lower()
    sim, iso = _sim(p.get("moneda")), _iso(p.get("moneda"))
    perf = perfiles([vend_email]).get(vend_email, {})
    verif = datos.esta_verificado(vend_email)
    vend = p.get("vendedor_nombre") or perf.get("nombre") or "Vendedor"
    cat_n, cat_em = _cat(p.get("categoria"))
    st = _stock_txt(p)
    agotado = st == "Agotado"
    mio = bool(yo) and yo == vend_email
    precio = _monto(sim, p["precio"])
    av = (f"<img src='{e(perf['foto_url'])}' alt='' referrerpolicy='no-referrer'>" if perf.get("foto_url")
          else e((vend[:1] or "?").upper()))
    ficha = (f"<div class='mk-foto'>{_foto_producto(p)}</div>"
             f"<h1 style='margin-top:16px'>{e(p.get('nombre'))}</h1>"
             f"<div style='font-size:24px;font-weight:800;color:var(--esmeralda);margin-top:4px'>{e(precio)}</div>"
             f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:8px'><span class='pill'>{cat_em} {e(cat_n)}</span>"
             + (f"<span class='pill {'bad' if agotado else 'gris'}'>{e(st)}</span>" if st else "")
             + ("<span class='pill warn'>Pausado · solo tú lo ves</span>" if not p.get("activo") else "") + "</div>"
             + (f"<p style='margin-top:16px;line-height:1.55;white-space:pre-line'>{e(p.get('descripcion'))}</p>" if p.get("descripcion") else "")
             + f"<div class='mk-vend'><div class='mk-av'>{av}</div><div style='flex:1;min-width:0'><div class='sub' style='margin:0;font-size:12.5px'>Vendedor</div>"
             f"<b>{e(vend)}</b>" + (" <span class='vok'>Vendedor verificado ✓</span>" if verif else "") + "</div></div>"
             "<div class='mk-prot'><span>🛡️</span><span>Pago protegido por Pichangol: el vendedor recibe tu pago recién cuando confirmas que te llegó el producto. "
             "Después de pagar coordinas la entrega con el vendedor.</span></div>")
    puede = _pago_web_disponible(iso) and p["precio"] >= 1
    from web import pago_hospedado as ph
    pas = _pasarela_web(iso) if puede else ""
    hosp = bool(pas) and pas != "culqi"
    if mio:
        panel = ("<div class='panel'><h3 style='margin-top:0'>Este producto es tuyo</h3><p class='sub'>Así lo ven los compradores. Edítalo, pausa o cambia el stock en Mi tienda.</p>"
                 f"<div class='acciones'><a class='btn' href='/anfitrion/tienda/{e(p['id'])}/editar'>Editar en Mi tienda</a></div></div>")
        barra = ""
    elif agotado:
        panel = ("<div class='panel'><h3 style='margin-top:0'>Agotado</h3><p class='sub'>El vendedor no tiene stock por ahora. Mira otros productos del Marketplace.</p>"
                 "<div class='acciones'><a class='btn sec' href='/marketplace'>Volver al Marketplace</a></div></div>")
        barra = ""
    elif not puede:
        motivo = (f"Este producto se cobra en {e(sim)} y el pago en línea en esa moneda aún no está disponible en la web."
                  if iso != "PEN" else ("El monto mínimo para pagar en línea es S/ 1.00." if p["precio"] < 1 else "El pago en línea desde la web se está habilitando."))
        panel = (f"<div class='panel'><h3 style='margin-top:0'>Cómpralo en la app</h3><p class='sub'>{motivo} En la app Pichangol pagas con los medios de tu país y coordinas por chat.</p>"
                 f"<div class='acciones'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
        barra = ""
    else:
        login = _login_box(f"/marketplace/{p['id']}", "Como en la app: la compra queda a tu nombre y la ves en Mis compras.") if (sesion.activo() and not ses) else ""
        if not sesion.activo():
            panel = (f"<div class='panel'><h3 style='margin-top:0'>Cómpralo en la app</h3><p class='sub'>Para comprar necesitas tu cuenta: en la app Pichangol pagas y coordinas la entrega por chat.</p>"
                     f"<div class='acciones'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
            barra = ""
        else:
            panel = ("<div class='panel'><div class='sub' style='margin:0'>Total a pagar</div>"
                     f"<div style='font-size:26px;font-weight:800;margin-top:2px'>{e(precio)}</div>"
                     f"<div class='sub' style='margin-top:2px;font-size:13.5px'>{e(p.get('nombre'))} · 1 unidad</div>"
                     + login
                     + f"<div style='margin-top:14px'>{ph.selector(pas) if hosp else ui.selector_medio_pago()}</div>"
                     f"<div style='margin-top:14px'><button class='btn lg' data-pagar>Comprar · {e(precio)}</button></div>"
                     "<div class='estado bad' id='mkErr'></div>"
                     f"<div class='sub' style='font-size:12.5px;margin-top:12px'>Al pagar, la compra queda en Mis compras (web y app). Dudas: "
                     f"<a href='mailto:{e(empresa.valores()['empresa_correo'])}'>{e(empresa.valores()['empresa_correo'])}</a>.</div></div>")
            barra = (f"<div class='barra-fija'><div><div class='sub' style='font-size:12px;margin:0'>Total</div><div class='t'>{e(precio)}</div></div>"
                     f"{ui.medio_pago_mini(pas)}<button class='btn' data-pagar>Comprar</button></div>")
    cuerpo = (_CSS + "<div style='padding-top:18px'><a class='sub' href='/marketplace' style='text-decoration:none'>‹ Marketplace</a></div>"
              f"<div class='dos' style='margin-top:10px'><div>{ficha}</div><aside class='resumen'>{panel}</aside></div>{barra}")
    head = ""
    if barra:
        cfg = {"url": "/web/marketplace/comprar", "cuerpo": {"producto_id": p["id"]}, "moneda": sim, "monto": round(p["precio"], 2),
               "linea": e(p.get("nombre")), "pk": "" if hosp else config.CULQI_PUBLIC_KEY, "login": sesion.activo(), "sesion": bool(ses),
               "pasarela": pas, "pasarelaNombre": ph.nombre_pasarela(pas) if hosp else "", "urlPasarela": "/web/marketplace/comprar-pasarela",
               "boton": f"Comprar · {precio}", "cargando": "Confirmando tu compra…",
               "nota": "El vendedor recibe el pago cuando confirmes que te llegó."}
        cuerpo += _js_culqi(cfg)
        if sesion.activo() and not ses:
            head = sesion.GIS_SCRIPT
    return ui.shell(p.get("nombre") or "Producto", cuerpo, sesion=ses, con_barra=bool(barra), extra_head=head,
                    desc=f"{p.get('nombre')} · {precio} · Marketplace Pichangol",
                    og_image=p.get("foto_url") or "/static/brand/logo_pichangol.png")


class CompraReq(BaseModel):
    producto_id: str
    token: str
    medio: str = "yape"


def _ses_compra(request: Request | None) -> tuple[dict | None, dict | None]:
    if not sesion.activo():
        return None, {"ok": False, "error": "sin_login", "mensaje": "Por ahora compras desde la app Pichangol."}
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return None, {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google para comprar."}
    return ses, None


def _registrar_cobro_web(charge_id: str, monto_c: int, iso: str, email: str, medio: str, concepto: str) -> None:
    try:
        from db.store import stores
        stores.registrar_pago(tipo="cobro_web", monto_centimos=monto_c, moneda=iso, estado="aprobado", culqi_charge_id=charge_id,
                              email=email, medio="yape" if medio == "yape" else "tarjeta", concepto=concepto)
    except Exception:  # noqa: BLE001
        pass


def _push(email: str, titulo: str, cuerpo: str, tipo: str) -> None:
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(email, titulo, cuerpo, tipo=tipo)
    except Exception:  # noqa: BLE001
        pass


@router.post("/web/marketplace/comprar")
def comprar_producto(req: CompraReq, request: Request = None) -> dict:
    """= `ProductoDetalleScreen._comprar`: cobra y registra la venta como el app."""
    ses, err = _ses_compra(request)
    if err:
        return err
    email = ses["email"].strip().lower()
    p = producto(req.producto_id)
    if not p or not p.get("activo"):
        return {"ok": False, "error": "no_disponible", "mensaje": "Este producto ya no está publicado."}
    vend = p["vendedor_email"].strip().lower()
    if vend == email:
        return {"ok": False, "error": "propio", "mensaje": "Este producto es tuyo."}
    sim, iso = _sim(p.get("moneda")), _iso(p.get("moneda"))
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "moneda", "mensaje": "El pago en línea en esta moneda no está disponible en la web por ahora. Cómpralo desde la app."}
    if iso != "PEN":
        return {"ok": False, "error": "usa_pasarela", "mensaje": "Este producto se paga con la pasarela de su país. Recarga la página e inténtalo otra vez."}
    precio = round(float(p["precio"]), 2)
    monto_c = int(round(precio * 100))
    if monto_c < 100:
        return {"ok": False, "error": "monto", "mensaje": "El monto mínimo para pagar en línea es S/ 1.00."}
    if p.get("stock") is not None and p["stock"] <= 0:
        return {"ok": False, "error": "agotado", "mensaje": "Se agotó. No se te cobró nada."}
    if not apartar_unidad(p["id"]):
        return {"ok": False, "error": "agotado", "mensaje": "Se agotó justo ahora o el vendedor lo pausó. No se te cobró nada."}
    from db.store import stores
    nombre = (ses.get("nombre") or "").strip()
    cliente = stores.cliente_de(email, nombre=nombre or email.split("@")[0], telefono=datos.celular_de_perfil(email), pais=_PAIS_POR_ISO[iso])
    concepto = f"Compra: {p.get('nombre') or 'Producto'}"
    cargo = culqi.crear_cargo(token=req.token.strip(), monto_centimos=monto_c, email=email, descripcion=concepto[:80], moneda=iso,
                              cliente=cliente, metadata={"canal": "web", "producto_id": p["id"], "vendedor": vend})
    if not cargo.get("ok"):
        devolver_unidad(p["id"])
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada." + (f" ({msg[:80]})" if msg else "")}
    charge_id = str(cargo.get("charge_id") or "")
    return venta_pagada(producto_id=p["id"], producto_nombre=p.get("nombre") or "", vendedor=vend,
                        vendedor_nombre=p.get("vendedor_nombre") or "", moneda=p.get("moneda") or "S/", precio=precio,
                        email=email, nombre=nombre, charge_id=charge_id, medio=req.medio)


def venta_pagada(*, producto_id: str, producto_nombre: str, vendedor: str, vendedor_nombre: str, moneda: str, precio: float,
                 email: str, nombre: str, charge_id: str, medio: str, reintento: bool = False) -> dict:
    """Lo que pasa con la compra YA cobrada (Culqi o pasarela hospedada):
    `post_venta` (idempotente por `venta_id` = N.º de operación, comisión con
    el mínimo de la moneda del producto, ORDEN en escrow), `cobro_web` y el
    push "¡Te compraron!". Mismo código para los dos caminos."""
    from db.store import stores
    sim, iso = _sim(moneda), _iso(moneda)
    monto_c = int(round(float(precio) * 100))
    antes = len(stores.ventas)
    ya = stores.pago_por_charge(charge_id)
    aviso = ""
    try:
        from pagos.router import VentaProductoReq, post_venta
        post_venta(VentaProductoReq(vendedor_id=vendedor, monto_soles=precio, venta_id=charge_id, concepto=f"Venta: {producto_nombre}",
                                    charge_id=charge_id, producto_id=producto_id, producto_nombre=producto_nombre,
                                    comprador_email=email, comprador_nombre=nombre, vendedor_nombre=vendedor_nombre,
                                    moneda=moneda or "S/"))
    except Exception as ex:  # noqa: BLE001 — la contabilidad nunca deshace un cobro
        print(f"[market-web] venta {charge_id} sin registrar: {ex}", flush=True)
        if reintento:
            raise
        aviso = (f"Tu pago se procesó (operación {charge_id}) pero no pudimos registrar la orden. "
                 f"Escríbenos a {empresa.valores()['empresa_correo']} y la completamos.")
    if not (ya is not None and ya.tipo == "venta_producto"):
        _registrar_cobro_web(charge_id, monto_c, iso, email, medio, f"venta:{producto_id}")
        _push(vendedor, "¡Te compraron! 🛍️",
              f"{nombre or 'Un jugador'} compró \"{producto_nombre}\" ({_monto(sim, precio)}). Entrégalo y coordina por chat; "
              "el pago se libera cuando confirme la recepción.", "venta")
    nueva = stores.ventas[-1].id if len(stores.ventas) > antes else ""
    if not nueva:
        nueva = next((v.id for v in reversed(stores.ventas) if v.producto_id == producto_id
                      and (v.comprador_email or "").lower() == email), "") if ya is not None else ""
    print(f"[market-web] {email} compró {producto_id} a {vendedor} · {sim} {precio:.2f} · {charge_id}", flush=True)
    out = {"ok": True, "charge_id": charge_id, "venta_id": nueva, "url": f"/mis-ordenes?nueva={nueva}" if nueva else "/mis-ordenes"}
    if aviso:
        out["aviso"] = aviso
    return out


# ── 3) MIS COMPRAS (órdenes con escrow) ──────────────────────────────────────

_ESTADOS = {
    "pagado": ("Pagado · retenido", "warn", "🛍️"),
    "entregado": ("Entregado · por confirmar", "", "📦"),
    "recibido": ("Completado · liberado", "ok", "✅"),
    "disputado": ("En disputa", "bad", "⚠️"),
    "reembolsado": ("Reembolsado", "gris", "↩️"),
}


def _moneda_de_venta(v: dict, prod: dict | None) -> str:
    """La orden no guarda su moneda: la del producto o, para un bono, la del
    registro contable de esa venta (mismo vendedor y monto, ±10 min)."""
    if prod and prod.get("moneda"):
        return _sim(prod["moneda"])
    try:
        from db.store import stores
        t = datetime.fromisoformat(v["creado_en"])
        mc = int(round(float(v["monto_soles"]) * 100))
        for pg_ in stores.pagos:
            if (pg_.tipo == "venta_producto" and (pg_.dueno_id or "").lower() == v["vendedor_email"] and pg_.monto_centimos == mc
                    and abs((pg_.creado_en - t).total_seconds()) < 600):
                return _SIMBOLO_POR_ISO.get(pg_.moneda or "PEN", "S/")
    except Exception:  # noqa: BLE001
        pass
    return "S/"


@router.get("/mis-ordenes", response_class=HTMLResponse)
def pagina_mis_ordenes(request: Request, nueva: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _a_entrar("/mis-ordenes") if sesion.activo() else _sin_login("Mis compras", "Tus compras del Marketplace están en la app.")
    email = ses["email"].strip().lower()
    from ventas.router import _liberacion_dias, ventas_comprador
    ventas = ventas_comprador(email)["ventas"]
    prods = productos_por_ids([v.get("producto_id") for v in ventas])
    perf = perfiles([v["vendedor_email"] for v in ventas])
    dias = _liberacion_dias()
    tarjetas = []
    for v in ventas:
        prod = prods.get(v.get("producto_id") or "")
        sim = _moneda_de_venta(v, prod)
        et, cls, em = _ESTADOS.get(v["estado"], (v["estado"], "gris", "🧾"))
        es_bono = not v.get("producto_id") and str(v.get("producto_nombre") or "").startswith("Bono ")
        foto = (f"<img src='{e(prod['foto_url'])}' alt=''>" if prod and (prod.get("foto_url") or "").startswith("http")
                else ("🎟️" if es_bono else em))
        vend = v.get("vendedor_nombre") or perf.get(v["vendedor_email"], {}).get("nombre") or "—"
        try:
            fecha = datetime.fromisoformat(v["creado_en"]).strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            fecha = ""
        cel = perf.get(v["vendedor_email"], {}).get("celular") or ""
        wa = _wa_de(cel, _PAIS_POR_ISO[_iso(sim)])
        coord = (ui.boton_whatsapp(f"Hola {vend}, te compré \"{v.get('producto_nombre')}\" en Pichangol. ¿Coordinamos la entrega?",
                                   etiqueta="💬 WhatsApp del vendedor", clase="btn sec", tel=wa) if wa and v["estado"] in ("pagado", "entregado", "disputado")
                 else "<button type='button' class='btn sec' data-chat>💬 Chat en la app</button>")
        acciones = ""
        if v["estado"] in ("pagado", "entregado"):
            acciones = (f"<button type='button' class='btn' data-recibido='{v['id']}' data-prod='{e(v.get('producto_nombre'))}' data-vend='{e(vend)}'>✓ Confirmar recepción</button>"
                        f"<button type='button' class='btn rojo' data-problema='{v['id']}'>Problema</button>")
        nota = ""
        if v["estado"] in ("pagado", "entregado"):
            nota = f"<div class='sub' style='font-size:12.5px'>Si no confirmas ni reportas un problema, el pago se libera solo a los {dias} días.</div>"
        elif v["estado"] == "disputado":
            nota = "<div class='sub' style='font-size:12.5px'>El pago queda retenido mientras nuestro equipo revisa el caso con el vendedor.</div>"
        tarjetas.append(
            f"<div class='orden{' nueva' if str(v['id']) == nueva else ''}' id='o{v['id']}'><div class='cab'><div class='fo'>{foto}</div>"
            f"<div class='tx'><b>{e(v.get('producto_nombre') or 'Producto')}</b><div class='sub' style='margin:0;font-size:13px'>"
            + ("Bono de horas prepagadas" if es_bono else f"Vendedor: {e(vend)}")
            + (f" · {fecha}" if fecha else "") + "</div></div>"
            f"<div class='mt'>{e(_monto(sim, v['monto_soles']))}</div></div>"
            f"<div class='pie'><span class='pill {cls}'>{em} {e(et)}</span><span class='esp'></span>{coord}</div>"
            + (f"<div class='pie'>{acciones}</div>" if acciones else "") + nota
            + ("<div class='pie'><a class='btn sec' href='/mis-bonos'>🎟️ Ver mis bonos</a></div>" if es_bono else "")
            + "</div>")
    lista = "".join(tarjetas) if tarjetas else (
        "<div class='mk-vacio'><div class='em'>🛍️</div><b>Aún no tienes compras</b>"
        "Cuando compres algo en el Marketplace, aquí confirmas la recepción para liberar el pago."
        "<div style='margin-top:14px'><a class='btn' href='/marketplace'>Ir al Marketplace</a></div></div>")
    aviso_nueva = ""
    if nueva and any(str(v["id"]) == nueva for v in ventas):
        v = next(v for v in ventas if str(v["id"]) == nueva)
        aviso_nueva = (f"<div class='estado ok'>¡Compra realizada! ✓ Pagaste {e(_monto(_moneda_de_venta(v, prods.get(v.get('producto_id') or '')), v['monto_soles']))}. "
                       f"Ahora coordina la entrega con {e(v.get('vendedor_nombre') or 'el vendedor')}.</div>")
    cuerpo = (_CSS + "<div class='mk-wrap'><div class='mk-h'><div><h1>Mis compras</h1>"
              f"<p class='sub'>{e(ses.get('nombre') or email)} · las mismas que ves en la app.</p></div>"
              "<div class='acc'><a class='btn sec' href='/marketplace'>Marketplace</a></div></div>"
              "<div class='estado ok' id='avisoMk' style='display:none'></div>" + aviso_nueva
              + f"<div style='margin-top:14px'>{lista}</div></div>"
              + "<script>(function(){\n"
              "try{ var av = sessionStorage.getItem('pcg_aviso'); if(av){ var el = document.getElementById('avisoMk'); el.textContent = av; el.style.display = 'block'; sessionStorage.removeItem('pcg_aviso'); } }catch(e){}\n"
              f"var PLAY = {json.dumps(PLAY_URL)};\n"
              r"""document.querySelectorAll('[data-chat]').forEach(function(b){ b.addEventListener('click', function(){
  pcgConfirmar({titulo: 'Chat con el vendedor', mensaje: 'El chat para coordinar la entrega está en la app Pichangol, con la misma cuenta.', icono: '💬', confirmar: 'Abrir la app', cancelar: 'Ahora no'})
   .then(function(ok){ if(ok) window.open(PLAY, '_blank', 'noopener'); }); }); });
function accion(url, msg){ pcgCargando('Guardando…'); fetch(url, {method: 'POST'}).then(function(r){ return r.json(); }).then(function(j){
  if(j.ok){ try{ sessionStorage.setItem('pcg_aviso', msg); }catch(e){} pcgRecargar('Actualizando…'); }
  else { pcgCargando(false); pcgAvisar({titulo: 'No se pudo', mensaje: j.mensaje || 'Reintenta en un momento.', icono: '⚠️'}); } })
  .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'Reintenta en un momento.', icono: '⚠️'}); }); }
document.querySelectorAll('[data-recibido]').forEach(function(b){ b.addEventListener('click', function(){
  pcgConfirmar({titulo: '¿Recibiste el producto?', icono: '📦', confirmar: 'Sí, lo recibí', cancelar: 'Todavía no',
    mensaje: 'Al confirmar, se libera el pago a ' + b.dataset.vend + '. Hazlo solo cuando ya tengas "' + b.dataset.prod + '" en mano.'})
   .then(function(ok){ if(ok) accion('/web/ordenes/' + b.dataset.recibido + '/recibido', '¡Listo! Pago liberado al vendedor.'); }); }); });
document.querySelectorAll('[data-problema]').forEach(function(b){ b.addEventListener('click', function(){
  pcgConfirmar({titulo: 'Reportar un problema', icono: '⚠️', destructivo: true, confirmar: 'Reportar', cancelar: 'Cancelar',
    mensaje: 'Se marca la compra en disputa y el pago NO se libera hasta que se resuelva. Coordina primero con el vendedor.'})
   .then(function(ok){ if(ok) accion('/web/ordenes/' + b.dataset.problema + '/problema', 'Reportamos el problema. El pago queda retenido.'); }); }); });
var n = document.querySelector('.orden.nueva'); if(n) n.scrollIntoView({block: 'center'});
})();</script>""")
    return ui.shell("Mis compras", cuerpo, sesion=ses, titulo_tab="Mis compras · Pichangol")


def _orden_mia(request: Request | None, venta_id: int) -> tuple[dict | None, object, dict | None]:
    ses = sesion.de_request(request) if sesion.activo() else None
    if not ses or not ses.get("email"):
        return None, None, {"ok": False, "error": "sesion_requerida", "mensaje": "Inicia sesión con Google."}
    from db.store import stores
    v = next((x for x in stores.ventas if x.id == venta_id), None)
    if v is None or v.comprador_email != ses["email"].strip().lower():
        return ses, None, {"ok": False, "error": "no_encontrada", "mensaje": "No encontramos esa compra en tu cuenta."}
    return ses, v, None


@router.post("/web/ordenes/{venta_id}/recibido")
def orden_recibida(venta_id: int, request: Request = None) -> dict:
    """= `_confirmarRecepcion` del app: libera el pago al vendedor."""
    ses, v, err = _orden_mia(request, venta_id)
    if err:
        return err
    if v.estado not in ("pagado", "entregado"):
        return {"ok": False, "error": "estado", "mensaje": "Esta compra ya no se puede confirmar."}
    from ventas.router import PorEmailReq, marcar_recibido
    r = marcar_recibido(venta_id, PorEmailReq(por_email=ses["email"].strip().lower()))
    if r.get("ok"):
        _push(v.vendedor_email, "Pago liberado ✅",
              f"{ses.get('nombre') or 'El comprador'} confirmó la recepción de \"{v.producto_nombre}\". El neto ya es tuyo por cobrar.", "venta")
    return {"ok": bool(r.get("ok")), "estado": v.estado}


@router.post("/web/ordenes/{venta_id}/problema")
def orden_problema(venta_id: int, request: Request = None) -> dict:
    """= `_reportar` del app: disputa (el pago no se libera)."""
    ses, v, err = _orden_mia(request, venta_id)
    if err:
        return err
    if v.estado == "recibido":
        return {"ok": False, "error": "estado", "mensaje": "El pago de esta compra ya se liberó."}
    from ventas.router import PorEmailReq, abrir_disputa
    r = abrir_disputa(venta_id, PorEmailReq(por_email=ses["email"].strip().lower()))
    if r.get("ok"):
        _push(v.vendedor_email, "Problema con una venta ⚠️",
              f"{ses.get('nombre') or 'El comprador'} reportó un problema con \"{v.producto_nombre}\". El pago queda retenido. "
              "Coordinen por chat para resolverlo.", "venta")
    return {"ok": bool(r.get("ok")), "estado": v.estado}


# ── 4) MIS BONOS + compra de packs del local ────────────────────────────────

def _moneda_local(c: dict | None) -> tuple[str, str]:
    if not c:
        return "S/", "PEN"
    return _moneda_de(c)


@router.get("/mis-bonos", response_class=HTMLResponse)
def pagina_mis_bonos(request: Request, nuevo: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        return _a_entrar("/mis-bonos") if sesion.activo() else _sin_login("Mis bonos", "Tus bonos de horas están en la app.")
    email = ses["email"].strip().lower()
    bonos = bonos_de(email)
    locales = canchas_de_locales([(b["club"], b["dueno"].lower()) for b in bonos])
    tarjetas = []
    for b in bonos:
        c = locales.get((b["club"], b["dueno"].lower()))
        sim, _ = _moneda_local(c)
        sin = b["saldo"] <= 0
        pct = 0 if b["horas_total"] <= 0 else round(100 * b["horas_usadas"] / b["horas_total"])
        queda = "Sin saldo" if sin else ("Te queda 1 h" if b["saldo"] == 1 else f"Te quedan {b['saldo']} h")
        tarjetas.append(
            f"<div class='bono{' sin' if sin else ''}{' nueva' if b['id'] == nuevo else ''}'><div class='cab'><div class='ic'>🎟️</div>"
            f"<div class='tx'><b>{e(b['club'])}</b><div class='sub' style='margin:0;font-size:13px'>Compraste {b['horas_total']} h · {e(_monto(sim, b['precio']))}</div></div></div>"
            f"<div class='barra'><i style='width:{pct}%'></i></div>"
            f"<div class='fila'><span class='sub' style='margin:0'>Usaste {b['horas_usadas']} de {b['horas_total']} h</span>"
            f"<b>{queda}</b></div>"
            + (f"<div class='pie' style='display:flex;gap:8px;flex-wrap:wrap;margin-top:12px'><a class='btn sec' style='padding:9px 14px;font-size:13.5px' href='/bonos/{e(c['id'])}'>Comprar más horas</a>"
               f"<a class='btn sec' style='padding:9px 14px;font-size:13.5px' href='/reservar/{e(c['id'])}'>Ver el local</a></div>" if c else "")
            + "</div>")
    lista = "".join(tarjetas) if tarjetas else (
        "<div class='mk-vacio'><div class='em'>🎟️</div><b>Aún no tienes bonos</b>"
        "Compra un pack de horas en la ficha de una cancha y ahorra: pagas por adelantado y reservas descontando de tu bono.</div>")
    aviso = ("<div class='estado ok'>¡Bono activado! 🎟️ Tus horas ya están disponibles.</div>" if nuevo and any(b["id"] == nuevo for b in bonos) else "")
    cuerpo = (_CSS + "<div class='mk-wrap'><div class='mk-h'><div><h1>Mis bonos</h1>"
              "<p class='sub'>Paquetes de horas que compraste. Los pagaste una sola vez; al reservar con tu bono descuentas de aquí, sin volver a pagar.</p></div></div>"
              + aviso + f"<div style='margin-top:14px'>{lista}</div>"
              "<p class='sub' style='font-size:12.5px;margin-top:14px'>Para usar tus horas, reserva en ese local (aquí en la web con “Ver el local” "
              "o en la app con la misma cuenta) y marca <b>Usar mi bono</b> en el resumen: cada turno descuenta 1 hora. "
              "Si cancelas a tiempo, las horas vuelven a tu bono.</p></div>")
    return ui.shell("Mis bonos", cuerpo, sesion=ses, titulo_tab="Mis bonos · Pichangol")


@router.get("/bonos/{cancha_id}", response_class=HTMLResponse)
def pagina_bonos_local(request: Request, cancha_id: str) -> HTMLResponse:
    """= `_SeccionBonos` de la ficha del local: packs activos + mi saldo ahí."""
    ses = sesion.de_request(request)
    c = datos.cancha(cancha_id)
    if not c or not c.get("club") or c.get("eliminada"):
        return _no_encontrada("Local no disponible")
    club, dueno = c["club"], (c.get("dueno") or "").strip().lower()
    sim, iso = _moneda_local(c)
    ofertas = ofertas_de_local(club, dueno)
    yo = ((ses or {}).get("email") or "").strip().lower()
    saldo = sum(b["saldo"] for b in bonos_de(yo) if b["club"] == club and b["dueno"].lower() == dueno) if yo else 0
    mio = bool(yo) and yo == dueno
    puede = _pago_web_disponible(iso) and sesion.activo() and not mio and bool(c.get("verificada"))
    from web import pago_hospedado as ph_
    pas = _pasarela_web(iso) if puede else ""
    hosp = bool(pas) and pas != "culqi"
    tarifa = float(c.get("precio_hora") or 0)
    packs = []
    for o in ofertas:
        ph = o["precio"] / o["horas"] if o["horas"] > 0 else o["precio"]
        ahorro = round(100 * (1 - ph / tarifa)) if tarifa > 0 and ph < tarifa else 0
        titulo = o["nombre"] or f"{o['horas']} horas"
        btn = (f"<button type='button' class='btn' data-pagar data-oferta='{e(o['id'])}' data-monto='{o['precio']:.2f}' "
               f"data-linea='{e(titulo)} · {e(club)}'>{e(_monto(sim, o['precio']))}</button>" if (puede and o["precio"] >= 1)
               else f"<span style='font-weight:800'>{e(_monto(sim, o['precio']))}</span>")
        packs.append(f"<div class='pack'><div class='h'>{o['horas']}h</div><div class='tx'><b>{e(titulo)}</b>"
                     f"<div class='sub' style='margin:0;font-size:13px'>{e(_monto(sim, ph))}/hora" + (f" · ahorras {ahorro} %" if ahorro > 0 else "") + "</div></div>"
                     f"{btn}</div>")
    if not ofertas:
        cuerpo_packs = "<div class='mk-vacio'><div class='em'>🎟️</div><b>Este local aún no ofrece bonos</b>Cuando publique packs de horas aparecerán aquí.</div>"
    else:
        cuerpo_packs = "".join(packs)
    nota = ""
    if mio:
        nota = "<div class='estado warn'>Son los packs de tu local: así los ven los jugadores. Se administran desde la app (Mis canchas → Bonos).</div>"
    elif ofertas and not _pago_web_disponible(iso):
        nota = (f"<div class='estado warn'>Este local cobra en {e(sim)}: el pago en línea en esa moneda aún no está disponible en la web. "
                f"<a href='{PLAY_URL}'>Compra tu bono en la app</a>.</div>")
    elif ofertas and not sesion.activo():
        nota = f"<div class='estado warn'>Compra tu bono desde la app Pichangol. <a href='{PLAY_URL}'>Abrir la app</a></div>"
    elif ofertas and not c.get("verificada"):
        nota = "<div class='estado warn'>Este local aún está en verificación: sus bonos se podrán comprar cuando lo aprobemos.</div>"
    login = _login_box(f"/bonos/{cancha_id}", "Como en la app: el bono queda a tu nombre y lo ves en Mis bonos.") if (puede and not ses and ofertas) else ""
    cuerpo = (_CSS + "<div class='mk-wrap'>"
              f"<div style='padding-top:18px'><a class='sub' href='/reservar/{e(cancha_id)}' style='text-decoration:none'>‹ {e(club)}</a></div>"
              "<div class='mk-h'><div><h1>🎟️ Bonos de horas</h1>"
              f"<p class='sub'>{e(club)} · Paga por adelantado y ahorra: cada bono te da horas para reservar aquí.</p></div></div>"
              + (f"<div class='saldo'>✓ Tienes {saldo} {'hora' if saldo == 1 else 'horas'} de bono en este local</div>" if saldo > 0 else "")
              + nota + login + cuerpo_packs
              + (f"<div style='margin-top:16px'>{ph_.selector(pas) if hosp else ui.selector_medio_pago()}</div><div class='estado bad' id='mkErr'></div>" if (puede and ofertas) else "")
              + "<p class='sub' style='font-size:12.5px;margin-top:14px'>Tus horas quedan en <a href='/mis-bonos'>Mis bonos</a> y se canjean al reservar en este local, aquí en la web o en la app: marca “Usar mi bono” en el resumen.</p></div>")
    head = ""
    if puede and ofertas:
        cfg = {"url": "/web/bonos/comprar", "cuerpo": {"cancha_id": cancha_id}, "moneda": sim, "monto": 0, "linea": "",
               "pk": "" if hosp else config.CULQI_PUBLIC_KEY, "login": sesion.activo(), "sesion": bool(ses), "boton": "", "cargando": "Confirmando tu bono…",
               "pasarela": pas, "pasarelaNombre": ph_.nombre_pasarela(pas) if hosp else "", "urlPasarela": "/web/bonos/comprar-pasarela",
               "nota": "Pagas una sola vez; cada reserva con tu bono descuenta horas, sin volver a pagar."}
        cuerpo += _js_culqi(cfg)
        if not ses:
            head = sesion.GIS_SCRIPT
    return ui.shell(f"Bonos · {club}", cuerpo, sesion=ses, extra_head=head, titulo_tab=f"Bonos de horas · {club} · Pichangol")


class BonoReq(BaseModel):
    cancha_id: str
    oferta_id: str
    token: str
    medio: str = "yape"


@router.post("/web/bonos/comprar")
def comprar_bono(req: BonoReq, request: Request = None) -> dict:
    """= `_SeccionBonosState._comprar`: crédito + venta + push, como el app."""
    ses, err = _ses_compra(request)
    if err:
        return err
    email = ses["email"].strip().lower()
    c = datos.cancha(req.cancha_id)
    o = oferta(req.oferta_id)
    if not c or not o or not o["activo"] or o["club"] != c.get("club") or o["dueno"].lower() != (c.get("dueno") or "").strip().lower():
        return {"ok": False, "error": "no_disponible", "mensaje": "Este bono ya no está disponible."}
    if not c.get("verificada"):
        return {"ok": False, "error": "no_verificada", "mensaje": "Este local aún está en verificación."}
    dueno = o["dueno"].lower()
    if dueno == email:
        return {"ok": False, "error": "propio", "mensaje": "Es un bono de tu propio local."}
    sim, iso = _moneda_local(c)
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "moneda", "mensaje": "El pago en línea en esta moneda no está disponible en la web por ahora. Cómpralo desde la app."}
    if iso != "PEN":
        return {"ok": False, "error": "usa_pasarela", "mensaje": "Este bono se paga con la pasarela de su país. Recarga la página e inténtalo otra vez."}
    monto_c = int(round(o["precio"] * 100))
    if monto_c < 100:
        return {"ok": False, "error": "monto", "mensaje": "El monto mínimo para pagar en línea es S/ 1.00."}
    from db.store import stores
    nombre = (ses.get("nombre") or "").strip()
    concepto = f"Bono {o['horas']}h · {o['club']}"
    cliente = stores.cliente_de(email, nombre=nombre or email.split("@")[0], telefono=datos.celular_de_perfil(email), pais=_PAIS_POR_ISO[iso])
    cargo = culqi.crear_cargo(token=req.token.strip(), monto_centimos=monto_c, email=email, descripcion=concepto[:80], moneda=iso,
                              cliente=cliente, metadata={"canal": "web", "bono_id": o["id"], "cancha_id": c["id"]})
    if not cargo.get("ok"):
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada." + (f" ({msg[:80]})" if msg else "")}
    charge_id = str(cargo.get("charge_id") or "")
    return bono_pagado(oferta=o, dueno=dueno, email=email, nombre=nombre, sim=sim, charge_id=charge_id, medio=req.medio)


def bono_pagado(*, oferta: dict, dueno: str, email: str, nombre: str, sim: str, charge_id: str, medio: str,
                reintento: bool = False) -> dict:
    """Lo que pasa con el bono YA cobrado (Culqi o pasarela hospedada):
    crédito `bono_<operación>` (idempotente), `post_venta` (idempotente por
    `venta_id`, comisión con el mínimo de la moneda del local), `cobro_web` y
    push al dueño. Mismo código para los dos caminos."""
    from db.store import stores
    o = oferta
    iso = _iso(sim)
    monto_c = int(round(float(o["precio"]) * 100))
    concepto = f"Bono {o['horas']}h · {o['club']}"
    bono_id = f"bono_{charge_id}"
    ya = stores.pago_por_charge(charge_id)
    aviso = ""
    # 1) Crédito del jugador (= AppState.comprarBono).
    if not registrar_bono({"id": bono_id, "bono_id": o["id"], "dueno": dueno, "club": o["club"], "comprador": email,
                           "comprador_nombre": nombre, "horas_total": o["horas"], "horas_usadas": 0, "precio": o["precio"],
                           "venta_id": charge_id}):
        print(f"[bono-web] cobro {charge_id} sin crédito en pichangol_bonos_comprados ({email}, {o['id']})", flush=True)
        if reintento:
            raise RuntimeError("no se pudo registrar el crédito del bono")  # la orden se reintenta
        aviso = (f"Tu pago se procesó (operación {charge_id}) pero no pudimos activar el bono. "
                 f"Escríbenos a {empresa.valores()['empresa_correo']} y lo activamos.")
    # 2) Contabilidad de venta (por recibir del dueño − comisión), idempotente por venta_id.
    try:
        from pagos.router import VentaProductoReq, post_venta
        post_venta(VentaProductoReq(vendedor_id=dueno, monto_soles=o["precio"], venta_id=charge_id, concepto=concepto,
                                    charge_id=charge_id, moneda=sim, comprador_email=email, comprador_nombre=nombre))
    except Exception as ex:  # noqa: BLE001
        print(f"[bono-web] contabilidad de {charge_id} falló: {ex}", flush=True)
    if not (ya is not None and ya.tipo == "venta_producto"):
        _registrar_cobro_web(charge_id, monto_c, iso, email, medio, f"bono:{o['id']}")
        # 3) Push al dueño.
        _push(dueno, "¡Vendiste un bono! 🎟️", f"{nombre or 'Un jugador'} compró tu pack de {o['horas']} horas en {o['club']}.", "bono")
    print(f"[bono-web] {email} compró {o['id']} ({o['horas']}h) en {o['club']} · {sim} {o['precio']:.2f} · {charge_id}", flush=True)
    out = {"ok": True, "charge_id": charge_id, "bono": bono_id, "url": f"/mis-bonos?nuevo={bono_id}"}
    if aviso:
        out["aviso"] = aviso
    return out


# ── MARKETPLACE y BONOS en $ / Bs por PASARELA HOSPEDADA (fase 2 parte 2) ─────

class CompraPasarelaReq(BaseModel):
    producto_id: str


@router.post("/web/marketplace/comprar-pasarela")
def comprar_producto_pasarela(req: CompraPasarelaReq, request: Request = None) -> dict:
    """Producto en $ o Bs: mismas validaciones que el camino Culqi; la unidad
    se APARTA (UPDATE atómico) ANTES de ir a la pasarela y sigue apartada
    mientras la orden vive; vuelve al stock si se rechaza / cancela / vence
    (`al_soltar_hospedado`). Al confirmarse, `venta_pagada` (como Culqi)."""
    from web import pago_hospedado as ph
    ses, err = _ses_compra(request)
    if err:
        return err
    email = ses["email"].strip().lower()
    p = producto(req.producto_id)
    if not p or not p.get("activo"):
        return {"ok": False, "error": "no_disponible", "mensaje": "Este producto ya no está publicado."}
    vend = p["vendedor_email"].strip().lower()
    if vend == email:
        return {"ok": False, "error": "propio", "mensaje": "Este producto es tuyo."}
    sim, iso = _sim(p.get("moneda")), _iso(p.get("moneda"))
    if iso == "PEN":
        return {"ok": False, "error": "usa_culqi", "mensaje": "Este producto se paga con Yape o tarjeta en la misma página."}
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "moneda", "mensaje": "El pago en línea en esta moneda no está disponible en la web por ahora. Cómpralo desde la app."}
    precio = round(float(p["precio"]), 2)
    if int(round(precio * 100)) < 100:
        return {"ok": False, "error": "monto", "mensaje": f"El monto mínimo para pagar en línea es {sim} 1.00."}
    previa = ph.orden_viva(email, "market", p["id"])
    if previa is None and p.get("stock") is not None and p["stock"] <= 0:
        return {"ok": False, "error": "agotado", "mensaje": "Se agotó. No se te cobró nada."}
    nombre = (ses.get("nombre") or "").strip()

    def apartar():
        if not apartar_unidad(p["id"]):
            return {"ok": False, "error": "agotado", "mensaje": "Se agotó justo ahora o el vendedor lo pausó. No se te cobró nada."}
        return None

    accion = {"producto_id": p["id"], "producto_nombre": p.get("nombre") or "", "vendedor": vend,
              "vendedor_nombre": p.get("vendedor_nombre") or "", "moneda": p.get("moneda") or sim, "precio": precio,
              "comprador_nombre": nombre, "stock_apartado": True}
    return ph.abrir_orden(email=email, tipo="market", clave=p["id"], iso=iso, monto_centimos=int(round(precio * 100)),
                          concepto=f"Compra: {p.get('nombre') or 'Producto'}", accion=accion, nombre=nombre, request=request,
                          apartar=apartar, soltar=lambda: devolver_unidad(p["id"]))


class BonoPasarelaReq(BaseModel):
    cancha_id: str
    oferta_id: str


@router.post("/web/bonos/comprar-pasarela")
def comprar_bono_pasarela(req: BonoPasarelaReq, request: Request = None) -> dict:
    """Bono de un local que cobra en $ o Bs: mismas validaciones que el camino
    Culqi; al confirmarse, `bono_pagado` (crédito idempotente + venta)."""
    from web import pago_hospedado as ph
    ses, err = _ses_compra(request)
    if err:
        return err
    email = ses["email"].strip().lower()
    c = datos.cancha(req.cancha_id)
    o = oferta(req.oferta_id)
    if not c or not o or not o["activo"] or o["club"] != c.get("club") or o["dueno"].lower() != (c.get("dueno") or "").strip().lower():
        return {"ok": False, "error": "no_disponible", "mensaje": "Este bono ya no está disponible."}
    if not c.get("verificada"):
        return {"ok": False, "error": "no_verificada", "mensaje": "Este local aún está en verificación."}
    dueno = o["dueno"].lower()
    if dueno == email:
        return {"ok": False, "error": "propio", "mensaje": "Es un bono de tu propio local."}
    sim, iso = _moneda_local(c)
    if iso == "PEN":
        return {"ok": False, "error": "usa_culqi", "mensaje": "Este bono se paga con Yape o tarjeta en la misma página."}
    if not _pago_web_disponible(iso):
        return {"ok": False, "error": "moneda", "mensaje": "El pago en línea en esta moneda no está disponible en la web por ahora. Cómpralo desde la app."}
    monto_c = int(round(o["precio"] * 100))
    if monto_c < 100:
        return {"ok": False, "error": "monto", "mensaje": f"El monto mínimo para pagar en línea es {sim} 1.00."}
    nombre = (ses.get("nombre") or "").strip()
    accion = {"cancha_id": c["id"], "oferta": {k: o[k] for k in ("id", "horas", "precio", "club", "nombre")},
              "dueno": dueno, "sim": sim, "comprador_nombre": nombre}
    return ph.abrir_orden(email=email, tipo="bono", clave=o["id"], iso=iso, monto_centimos=monto_c,
                          concepto=f"Bono {o['horas']}h · {o['club']}", accion=accion, nombre=nombre, request=request)


def al_pagar_hospedado(o: dict) -> None:
    """La pasarela CONFIRMÓ el cobro de una orden del marketplace o de un bono:
    lo mismo que el camino Culqi tras el cargo, con los datos CONGELADOS en
    la orden y la referencia `<pasarela>:<id>` como N.º de operación."""
    from web import pago_hospedado as ph
    a = o["accion"]
    ref = ph.ref_cobro(o)
    if a.get("tipo") == "market":
        out = venta_pagada(producto_id=a["producto_id"], producto_nombre=a.get("producto_nombre") or "", vendedor=a["vendedor"],
                           vendedor_nombre=a.get("vendedor_nombre") or "", moneda=a.get("moneda") or "", precio=float(a["precio"]),
                           email=o["email"], nombre=a.get("comprador_nombre") or "", charge_id=ref, medio="tarjeta", reintento=True)
        a["stock_vendido"] = True
    else:
        out = bono_pagado(oferta=dict(a["oferta"]), dueno=a["dueno"], email=o["email"], nombre=a.get("comprador_nombre") or "",
                          sim=a.get("sim") or o.get("simbolo") or "", charge_id=ref, medio="tarjeta", reintento=True)
    o["estado"], o["url_resultado"] = "aprobado", out["url"]


def al_soltar_hospedado(o: dict) -> None:
    """La orden no se pagó (rechazo / cancelación / vencimiento): la unidad
    apartada vuelve al stock, una sola vez."""
    a = o.get("accion") or {}
    if a.get("tipo") == "market" and a.get("stock_apartado") and not a.get("stock_devuelto") and not a.get("stock_vendido"):
        devolver_unidad(a["producto_id"])
        a["stock_devuelto"] = True
