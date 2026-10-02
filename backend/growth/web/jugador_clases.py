"""MIS CLASES Y PAGOS en la web (pedido del director, 29-sep-2026: "en la web
implementa las mismas funcionalidades que existen actualmente en el app") =
pantalla `lib/screens/mis_clases_screen.dart` del APK.

- GET  /mis-clases                               → las matrículas del correo con
  sesión: las que PAGA (`email`) y en las que es el alumno con correo propio
  (`data->>'emailAlumno'`), no eliminadas (= `AppState.misMatriculas` /
  `MatriculasRepo.deAlumno`). Por persona: academia (logo, nombre, WhatsApp),
  programa y horario, total pagado, débito automático ("Mes a mes activo" con
  Cancelar, = `_SuscripcionMesAMes`), PRÓXIMOS PAGOS con casillas (todas
  marcadas por defecto, = `_ProximosPagos`) y COMPROBANTES (modal =
  `_verComprobante`, + página imprimible = "Compartir / PDF").
  Arriba, "MI FAMILIA · UN SOLO PAGO" (= `_MiFamilia`): por moneda, cuando hay
  cuotas pendientes de 2+ personas.
- POST /web/mis-clases/pagar                      → cobra con Culqi (solo PEN)
  y registra EXACTAMENTE lo que hace el APK en `_pagarCuotas` /
  `_pagarFamilia`: UN cargo por la suma + cargo por servicio (cotización
  `academias`: con `deporte` en el pago de una persona, con `partes` por
  persona en el familiar), `post_matricula` POR ACADEMIA (`cuo_<acad>_<µs>`,
  con `charge_id` y su parte del cargo por `cargo_servicio.repartir`; el
  desglose y el ajuste van en la 1.ª) y las cuotas quedan pagadas en
  `pichangol_matriculas.data.cuotas` con el formato de
  `AppState.marcarCuotaPagada` (`pagada`, `fechaPago`, `operacionId` y, en la
  1.ª cuota, `cargoServicio` + `cargoPersonas` si > 1). El servidor revalida
  y recalcula TODO antes de cobrar (nunca cobra una cuota ya pagada) y solo
  toca filas que administra el correo de la sesión.
- POST /web/mis-clases/suscripcion/{alumno_id}/cancelar → corta el débito
  automático (= `PagosService.cancelarSuscripcionAlumno`), solo el pagador.
- GET  /mis-clases/comprobante/{alumno_id}/{cuota_id} → comprobante
  imprimible / "Guardar como PDF".

- POST /web/mis-clases/pagar-pasarela           → cuotas en $ o Bs por la
  pasarela HOSPEDADA del país (fase 2 parte 2, `web/pago_hospedado.py`): al
  confirmarse, `al_pagar_hospedado` revalida y marca TODO O NADA con
  `FOR UPDATE` (`marcar_cuotas_atomico`); si alguna cuota se pagó por otro
  lado mientras tanto, el pago se devuelve.

Multi-país: la moneda es la de la academia; soles con Culqi, $ / Bs con la
pasarela del país (sin ella en PRD: "Pagar en la app").
"""
from __future__ import annotations

import json
import threading
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
import empresa
from db import pg
from pagos import cargo_servicio as _cs
from pagos import culqi
from web import horarios, sesion, ui
from web.academia import _iso as _iso_academia
from web.academia import _moneda as _moneda_academia
from web.academia import _wa as _wa_academia
from web.router import PLAY_URL, _pago_web_disponible, _pasarela_web, e

router = APIRouter()

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
EMOJI_DEP = {"tenis": "🎾", "padel": "🎾", "futbol": "⚽", "futsal": "⚽", "voley": "🏐", "basquet": "🏀",
             "natacion": "🏊", "pickleball": "🏓", "frontenis": "🎾"}

# Un pago a la vez por cuenta: dos pestañas no pueden cobrar las mismas cuotas.
_candados: dict[str, threading.Lock] = {}
_candados_mu = threading.Lock()


def _candado(email: str) -> threading.Lock:
    with _candados_mu:
        return _candados.setdefault(email, threading.Lock())


# ── datos (Postgres directo, fail-safe) ──────────────────────────────────────

def _json_dict(v) -> dict:
    if isinstance(v, dict):
        return v
    try:
        j = json.loads(v) if v else {}
        return j if isinstance(j, dict) else {}
    except (TypeError, ValueError):
        return {}


def matriculas_de_usuario(email: str) -> list[dict]:
    """= `MatriculasRepo.deAlumno`: las que paga (`email`) y las que un familiar
    registró con su correo (`data->>emailAlumno`), no eliminadas."""
    em = (email or "").strip().lower()
    if not pg.habilitado or not em:
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, academia_id, email, data FROM pichangol_matriculas "
                        "WHERE (lower(email) = %s OR lower(data->>'emailAlumno') = %s) "
                        "AND coalesce(eliminada,false) = false ORDER BY id", (em, em))
            out = []
            for mid, aid, correo, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = mid
                d["academiaId"] = aid or d.get("academiaId") or ""
                d["email"] = correo or d.get("email") or ""
                out.append(d)
            return out
    except Exception as ex:  # noqa: BLE001
        print(f"[mis-clases] no se pudieron leer las matrículas: {ex}", flush=True)
        return []


def academias_por_id(ids: list[str]) -> dict[str, dict]:
    ids = sorted({i for i in ids if i})
    if not pg.habilitado or not ids:
        return {}
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, dueno, data FROM pichangol_academias WHERE id = ANY(%s) "
                        "AND coalesce(eliminada,false) = false", (ids,))
            out = {}
            for aid, dueno, data in cur.fetchall():
                d = _json_dict(data)
                d["id"] = aid
                d["dueno"] = dueno or d.get("dueno") or ""
                out[aid] = d
            return out
    except Exception:  # noqa: BLE001
        return {}


def aplicar_marcas(data: dict, marcas: dict[str, dict] | None, reconciliadas: dict[str, str] | None = None) -> list[str]:
    """Aplica sobre `data.cuotas` (en su lugar) el formato de
    `AppState.marcarCuotaPagada`: `pagada`, `fechaPago`, `operacionId` y, si
    vino, `cargoServicio` (+ `cargoPersonas` si > 1). Nunca toca una cuota ya
    pagada (el pago es "pegajoso", como en el app). Devuelve los ids marcados."""
    hechas = []
    for c in data.get("cuotas") or []:
        if not isinstance(c, dict) or c.get("pagada"):
            continue
        cid = str(c.get("id") or "")
        if cid in (marcas or {}):
            m = marcas[cid]
            c["pagada"] = True
            c["fechaPago"] = m["fechaPago"]
            if m.get("operacionId"):
                c["operacionId"] = m["operacionId"]
            if float(m.get("cargoServicio") or 0) > 0:
                c["cargoServicio"] = round(float(m["cargoServicio"]), 2)
                if int(m.get("cargoPersonas") or 1) > 1:
                    c["cargoPersonas"] = int(m["cargoPersonas"])
            hechas.append(cid)
        elif cid in (reconciliadas or {}):
            c["pagada"] = True
            c["fechaPago"] = reconciliadas[cid]
            hechas.append(cid)
    return hechas


def marcar_cuotas_pagadas(alumno_id: str, email: str, marcas: dict[str, dict], reconciliadas: dict[str, str] | None = None) -> list[str]:
    """Marca pagadas (en la MISMA transacción, con la fila bloqueada) las cuotas
    `marcas = {cuota_id: {operacionId, fechaPago, cargoServicio?, cargoPersonas?}}`
    de la matrícula `alumno_id`, SOLO si el correo la administra (paga o es el
    alumno) y la cuota sigue pendiente. `reconciliadas = {cuota_id: fechaPago}`
    = cuotas de débito automático que el backend ya cobró (sin operación).
    Devuelve los ids que quedaron pagados en esta llamada."""
    em = (email or "").strip().lower()
    if not pg.habilitado or not alumno_id or not em or not (marcas or reconciliadas):
        return []
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM pichangol_matriculas WHERE id = %s AND coalesce(eliminada,false) = false "
                        "AND (lower(email) = %s OR lower(data->>'emailAlumno') = %s) FOR UPDATE", (alumno_id, em, em))
            row = cur.fetchone()
            if not row:
                return []
            data = _json_dict(row[0])
            hechas = aplicar_marcas(data, marcas, reconciliadas)
            if not hechas:
                conn.rollback()
                return []
            cur.execute("UPDATE pichangol_matriculas SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                        (json.dumps(data), alumno_id))
            conn.commit()
            return hechas
    except Exception as ex:  # noqa: BLE001
        print(f"[mis-clases] no se pudo marcar cuotas de {alumno_id}: {ex}", flush=True)
        return []


# ── lógica (espejo del app) ──────────────────────────────────────────────────

def _fecha(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str(iso or "")[:19]) if iso else None
    except ValueError:
        return None


def _fecha_txt(iso: str | None, hora: bool = False) -> str:
    d = _fecha(iso)
    if not d:
        return ""
    t = f"{d.day} {MESES[d.month - 1]} {d.year}"
    return t + (f" · {d.hour:02d}:{d.minute:02d}" if hora else "")


def _cuotas(m: dict) -> list[dict]:
    out = []
    for c in m.get("cuotas") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        try:
            monto = float(c.get("monto") or 0)
        except (TypeError, ValueError):
            monto = 0.0
        out.append(dict(c, monto=monto))
    return out


def _reconciliar(m: dict) -> dict[str, str]:
    """= `AppState.reconciliarSuscripcionAlumno`: con débito automático, las
    primeras `1 + cobros_hechos` cuotas `autoDebito` ya las cobró el backend
    (signup + cron). Devuelve {cuota_id: fechaPago} de las que aún figuran
    pendientes (y las marca pagadas en `m` para mostrar/validar)."""
    from db.store import stores as _st
    sus = (_st.suscripciones_alumno or {}).get(m["id"])
    if not sus:
        return {}
    esperadas = 1 + int(sus.get("cobros_hechos") or 0)
    auto = sorted([c for c in (m.get("cuotas") or []) if isinstance(c, dict) and c.get("autoDebito")],
                  key=lambda c: str(c.get("vencimiento") or ""))
    ahora = datetime.now().isoformat()
    out = {}
    for c in auto[:esperadas]:
        if not c.get("pagada"):
            c["pagada"] = True
            c["fechaPago"] = ahora
            out[str(c["id"])] = ahora
    return out


def _suscripcion(alumno_id: str) -> dict | None:
    from db.store import stores as _st
    s = (_st.suscripciones_alumno or {}).get(alumno_id)
    return s if (s and s.get("estado") == "activa") else None


def _auto_bloqueada(c: dict, sus: dict | None) -> bool:
    """Una cuota de débito automático con la suscripción ACTIVA la cobra el cron
    en su fecha: no se ofrece pagarla a mano (evita el doble cobro)."""
    return bool(sus and c.get("autoDebito") and not c.get("pagada"))


def _quien_corto(m: dict) -> str:
    par = (m.get("parentesco") or "").strip()
    menor = bool((m.get("apoderadoNombre") or "").strip()) or par == "hijo"
    return " · familiar" if par == "familiar" else (" · hijo(a)" if menor else "")


def _quien(m: dict) -> str:
    t = _quien_corto(m)
    orden = int(m.get("ordenHermano") or 1)
    return t + (f" · {orden}.º de la familia" if orden > 1 else "")


def _programa(m: dict, a: dict | None) -> tuple[str, str]:
    """(programa, horario): el plan sale del concepto de sus cuotas
    ("Plan · Mes") y su horario del plan de la academia con ese nombre."""
    cs = sorted(_cuotas(m), key=lambda c: str(c.get("vencimiento") or ""), reverse=True)
    prog = ""
    for c in cs:
        con = str(c.get("concepto") or "")
        # "Plan · Mes" (mensual/prepago) o "N clases particulares · Plan" (por clase).
        if " · " not in con:
            prog = ""
        elif con[:1].isdigit() and "clase" in con.split(" · ")[0]:
            prog = con.split(" · ", 1)[1].strip()
        else:
            prog = con.rsplit(" · ", 1)[0].strip()
        if prog:
            break
    horario = ""
    for p in (a or {}).get("planes") or []:
        if isinstance(p, dict) and prog and str(p.get("nombre") or "").strip() == prog:
            horario = str(p.get("horario") or "")
            break
    return prog, horario or str((a or {}).get("horarioTexto") or "")


def _vista(email: str) -> tuple[list[dict], dict[str, dict]]:
    """Matrículas del correo + academias, ya reconciliadas con el débito
    automático (lo reconciliado se guarda en la fila, como el app al abrir)."""
    ms = matriculas_de_usuario(email)
    acs = academias_por_id([m["academiaId"] for m in ms])
    for m in ms:
        rec = _reconciliar(m)
        if rec:
            marcar_cuotas_pagadas(m["id"], email, {}, reconciliadas=rec)
    return ms, acs


# ── página ───────────────────────────────────────────────────────────────────

_CSS = """
.mcl{width:100%;max-width:760px;margin:18px auto 110px;box-sizing:border-box}
.mcl h1{font-size:30px;margin:0 0 4px;letter-spacing:-.3px}
.mcl .intro{color:#6a6a6a;margin:0 0 18px}
.mc-card{background:#fff;border:1px solid #EBEBEB;border-radius:18px;margin-bottom:16px;overflow:hidden;box-shadow:0 6px 20px rgba(0,0,0,.06)}
.mc-cab{display:flex;gap:12px;align-items:center;padding:16px;background:#EEF8E8}
.mc-logo{width:48px;height:48px;border-radius:12px;flex:none;background:#fff;display:flex;align-items:center;justify-content:center;font-size:24px;overflow:hidden}
.mc-logo img{width:100%;height:100%;object-fit:cover}
.mc-cab b{display:block;color:#067A38;font-size:16px;line-height:1.25;overflow-wrap:anywhere}
.mc-cab small{color:#6a6a6a;font-size:12.5px;overflow-wrap:anywhere}
.mc-cab .tx{min-width:0;flex:1}
.mc-body{padding:12px 16px 16px}
.mc-prog{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 8px}
.mc-prog span{background:#F4F7FA;border-radius:99px;padding:5px 10px;font-size:12.5px;font-weight:600;overflow-wrap:anywhere;max-width:100%}
.mc-tot{font-weight:800;color:#0B8A3E;font-size:14px}
.mc-sus{display:flex;gap:10px;align-items:center;background:#EEF8E8;border-radius:12px;padding:10px 12px;margin-top:10px;font-size:13px;color:#067A38}
.mc-sus .tx{flex:1;min-width:0}
.mc-sus button{border:0;background:none;color:#B3261E;font-weight:700;cursor:pointer;font:inherit;font-weight:700}
.mc-h{font-weight:800;font-size:13.5px;margin:14px 0 2px}
.mc-hs{color:#6a6a6a;font-size:12px;margin-bottom:4px}
.mc-f{display:flex;align-items:center;gap:10px;padding:7px 4px;border-radius:10px;cursor:pointer}
.mc-f:hover{background:#F7F7F7}
.mc-f input{width:18px;height:18px;flex:none;accent-color:#0B8A3E;margin:0}
.mc-f .tx{flex:1;min-width:0}
.mc-f .tx b{display:block;font-size:13.5px;font-weight:600;overflow-wrap:anywhere}
.mc-f .tx small{color:#6a6a6a;font-size:12px}
.mc-f .tx small.venc{color:#B3261E;font-weight:700}
.mc-f .m{font-weight:800;font-size:13.5px;white-space:nowrap;color:#B3261E}
.mc-f .m.ok{color:#0B8A3E}
.mc-f.bloq{cursor:default;opacity:.8}
.mc-f.comp .ic{font-size:16px;flex:none}
.mc-cargo{display:flex;justify-content:space-between;gap:10px;font-size:13px;margin-top:8px;color:#444}
.mc-ahorro{font-size:12.5px;color:#0B7A55;margin-top:4px}
.mc-pagar{width:100%;margin-top:10px}
.mc-nota{color:#6a6a6a;font-size:11.5px;margin-top:6px}
.mc-acc{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.mc-acc .btn{flex:1 1 auto}
.mc-fam .mc-cab{background:#EEF8E8}
.mc-per{font-weight:800;font-size:13px;margin-top:10px;overflow-wrap:anywhere}
.mc-vacio{text-align:center;padding:40px 20px}
.mc-vacio .em{font-size:52px}
.mc-medio{margin-top:6px}
.mc-info{border:1px solid #E4E4E4;background:#fff;border-radius:50%;width:20px;height:20px;line-height:18px;font-size:12px;cursor:pointer;padding:0;margin-left:4px;vertical-align:middle}
@media(max-width:600px){.mcl h1{font-size:24px}.mc-acc .btn{flex:1 1 100%}}
"""


def _logo(a: dict | None) -> str:
    url = str((a or {}).get("logoUrl") or "")
    if url.startswith("http"):
        emo = EMOJI_DEP.get(str((a or {}).get('deporte') or '').lower(), '🎓')
        return (f"<div class='mc-logo'><img src='{e(url)}' alt='' loading='lazy' referrerpolicy='no-referrer' "
                f"onerror=\"this.parentNode.textContent='{emo}'\"></div>")
    return f"<div class='mc-logo'>{EMOJI_DEP.get(str((a or {}).get('deporte') or '').lower(), '🎓')}</div>"


def _fila_pend(c: dict, sim: str, hoy: str, sus: dict | None, grupo: str, alumno_id: str, puede: bool) -> str:
    venc = str(c.get("vencimiento") or "")[:10]
    vencida = venc and venc < hoy
    bloq = _auto_bloqueada(c, sus)
    sub = (f"Se cobra automático el {_fecha_txt(c.get('vencimiento'))}" if bloq else
           (f"<small class='venc'>Vencida · venció el {_fecha_txt(c.get('vencimiento'))}</small>" if vencida
            else f"Vence {_fecha_txt(c.get('vencimiento'))}"))
    if not sub.startswith("<small"):
        sub = f"<small>{sub}</small>"
    caja = ("<span style='width:18px;flex:none;text-align:center'>🔁</span>" if bloq else
            "<span style='width:18px;flex:none'></span>" if not puede else
            f"<input type='checkbox' checked data-g='{e(grupo)}' data-al='{e(alumno_id)}' data-cu='{e(c['id'])}' data-m='{c['monto']:.2f}'>")
    tag = "div" if (bloq or not puede) else "label"
    return (f"<{tag} class='mc-f{' bloq' if bloq else ''}'>{caja}<span class='tx'><b>{e(c.get('concepto'))}</b>{sub}</span>"
            f"<span class='m'>{e(sim)} {c['monto']:.2f}</span></{tag}>")


def _bloque_pago(grupo: str, sim: str, puede: bool, iso: str, familia: bool = False) -> str:
    if not puede:
        motivo = (f"Esta academia cobra en {e(sim)}: el pago en línea en esa moneda aún no está disponible en la web."
                  if iso != "PEN" else "El pago en línea desde la web se está habilitando.")
        return (f"<div class='mc-nota' style='font-size:12.5px;margin-top:10px'>{motivo} Paga tus cuotas desde la app Pichangol.</div>"
                f"<a class='btn sec mc-pagar' href='{PLAY_URL}' target='_blank' rel='noopener'>Pagar en la app</a>")
    # En $ / Bs: la pasarela HOSPEDADA del país (un solo medio, sin Culqi).
    from web import pago_hospedado as ph
    pas = _pasarela_web(iso)
    hosp = bool(pas) and pas != "culqi"
    attr = (f" data-pasarela='{e(pas)}' data-pasarela-nombre='{e(ph.nombre_pasarela(pas))}'" if hosp else "")
    medio_txt = ph.nombre_pasarela(pas) if hosp else "tu Yape o tarjeta"
    return (f"<div class='mc-cargo' data-cargo='{e(grupo)}' hidden></div><div class='mc-ahorro' data-ahorro='{e(grupo)}' hidden></div>"
            + (f"<div class='mc-nota' style='font-size:12.5px'>Pagas con {e(ph.etiqueta_pasarela(pas))} (página segura de la pasarela).</div>" if hosp else "")
            + f"<button type='button' class='btn mc-pagar' data-pagar='{e(grupo)}' data-fam='{'1' if familia else ''}'{attr}>Pagar</button>"
            + (f"<div class='mc-nota'>Un solo cargo a {e(medio_txt)}; cada academia recibe lo suyo y todas las cuotas quedan con el mismo N.º de operación.</div>"
               if familia else ""))


def _grupos_familia(ms: list[dict], acs: dict[str, dict]) -> list[dict]:
    """= `_pendientesFamilia`: cuotas pendientes por moneda, solo si en esa
    moneda hay 2+ personas por pagar."""
    por_mon: dict[str, list[tuple[dict, dict, dict]]] = {}
    for m in ms:
        a = acs.get(m["academiaId"])
        if not a:
            continue
        sim, _iso = _moneda_academia(a)
        sus = _suscripcion(m["id"])
        pend = sorted([c for c in _cuotas(m) if not c.get("pagada") and not _auto_bloqueada(c, sus)],
                      key=lambda c: str(c.get("vencimiento") or ""))
        for c in pend:
            por_mon.setdefault(sim, []).append((c, m, a))
    return [{"moneda": k, "items": v} for k, v in por_mon.items() if len({x[1]["id"] for x in v}) >= 2]


def _tarjeta_familia(g: dict, hoy: str, k: int) -> str:
    sim = g["moneda"]
    a0 = g["items"][0][2]
    _s, iso = _moneda_academia(a0)
    puede = _pago_web_disponible(iso)
    grupo = f"fam{k}"
    por_persona: dict[str, list] = {}
    for c, m, a in g["items"]:
        por_persona.setdefault(m["id"], []).append((c, m, a))
    filas = ""
    for lista in por_persona.values():
        m, a = lista[0][1], lista[0][2]
        filas += f"<div class='mc-per'>{e(m.get('nombre'))}{e(_quien_corto(m))} · {e(a.get('nombre'))}</div>"
        filas += "".join(_fila_pend(c, sim, hoy, None, grupo, m["id"], puede) for c, _m, _a in lista)
    return (f"<div class='mc-card mc-fam' id='familia-{k}'><div class='mc-cab'><div class='mc-logo'>👨‍👩‍👧</div><div class='tx'>"
            f"<b>Mi familia · un solo pago</b><small>{len(por_persona)} personas · {len(g['items'])} cuotas pendientes. "
            "Paga todo junto en un solo pago.</small></div></div>"
            f"<div class='mc-body' data-grupo='{grupo}' data-mon='{e(sim)}' data-dep=''>{filas}{_bloque_pago(grupo, sim, puede, iso, familia=True)}</div></div>")


def _tarjeta_matricula(m: dict, a: dict | None, email: str, hoy: str) -> str:
    nombre_aca = (a or {}).get("nombre") or "Academia"
    if a:
        sim, iso = _moneda_academia(a)
    else:
        sim, iso = "S/", "PEN"
    puede = bool(a) and _pago_web_disponible(iso)
    cuotas = _cuotas(m)
    pagadas = sorted([c for c in cuotas if c.get("pagada")], key=lambda c: str(c.get("vencimiento") or ""), reverse=True)
    proximas = sorted([c for c in cuotas if not c.get("pagada")], key=lambda c: str(c.get("vencimiento") or ""))
    total_pagado = sum(c["monto"] for c in pagadas)
    sus = _suscripcion(m["id"])
    prog, horario = _programa(m, a)
    grupo = f"al-{m['id']}"
    chips = "".join(f"<span>{x}</span>" for x in (
        (f"📚 {e(prog)}" if prog else ""), (f"🕒 {e(horario)}" if horario else ""),
        (f"📍 {e(' · '.join(x for x in ((a or {}).get('sedeClub'), (a or {}).get('zona')) if x))}" if (a or {}).get("sedeClub") or (a or {}).get("zona") else "")) if x)
    h = (f"<div class='mc-card' id='m-{e(m['id'])}'><div class='mc-cab'>{_logo(a)}<div class='tx'><b>{e(nombre_aca)}</b>"
         f"<small>Alumno: {e(m.get('nombre'))}{e(_quien(m))}</small></div></div><div class='mc-body' data-grupo='{e(grupo)}' "
         f"data-mon='{e(sim)}' data-dep='{e(str((a or {}).get('deporte') or ''))}'>"
         + (f"<div class='mc-prog'>{chips}</div>" if chips else "")
         + f"<div class='mc-tot'>Total pagado: {e(sim)} {total_pagado:.2f}</div>")
    if sus:
        paga = (m.get("email") or "").strip().lower() == email
        h += (f"<div class='mc-sus'><span>🔁</span><span class='tx'>Mes a mes activo: {e(sim)} {int(sus.get('monto_centimos') or 0) / 100:.2f} automático cada mes."
              + (f" Próximo cobro: {_fecha_txt(sus.get('proximo_cobro'))}." if sus.get("proximo_cobro") else "") + "</span>"
              + (f"<button type='button' data-cancelar-sus='{e(m['id'])}'>Cancelar</button>" if paga else "") + "</div>")
    if proximas and a:
        h += ("<div class='mc-h'>Próximos pagos</div><div class='mc-hs'>Marca las que quieres pagar.</div>"
              + "".join(_fila_pend(c, sim, hoy, sus, grupo, m["id"], puede) for c in proximas))
        if any(not _auto_bloqueada(c, sus) for c in proximas):
            h += _bloque_pago(grupo, sim, puede, iso)
    h += "<div class='mc-h'>Comprobantes de pago</div>"
    if not pagadas:
        h += "<div class='mc-hs'>Aún no hay pagos registrados.</div>"
    for c in pagadas:
        det = {"academia": nombre_aca, "alumno": m.get("nombre") or "", "concepto": c.get("concepto") or "",
               "fecha": _fecha_txt(c.get("fechaPago") or c.get("vencimiento"), hora=True), "op": c.get("operacionId") or "",
               "monto": c["monto"], "cargo": float(c.get("cargoServicio") or 0), "personas": int(c.get("cargoPersonas") or 1),
               "moneda": sim, "logo": str((a or {}).get("logoUrl") or ""),
               "url": f"/mis-clases/comprobante/{m['id']}/{c['id']}"}
        h += (f"<button type='button' class='mc-f comp' style='width:100%;border:0;background:none;font:inherit;text-align:left;color:inherit' "
              f"data-comp='{e(json.dumps(det, ensure_ascii=False))}'><span class='ic'>🧾</span><span class='tx'><b>{e(c.get('concepto'))}</b>"
              f"<small>Pagado {_fecha_txt(c.get('fechaPago') or c.get('vencimiento'))}</small></span>"
              f"<span class='m ok'>{e(sim)} {c['monto']:.2f}</span></button>")
    tel = _wa_academia(a) if a else ""
    acc = ""
    if tel:
        acc += f"<a class='btn sec' href='{e(ui.enlace_whatsapp('Hola, soy ' + str(m.get('nombre') or '') + ', alumno de ' + nombre_aca + '. Te escribo desde Pichangol.', tel))}' target='_blank' rel='noopener'>💬 WhatsApp</a>"
    if a:
        acc += f"<a class='btn sec' href='/academia/{e(m['academiaId'])}'>Ver academia</a>"
        acc += f"<a class='btn sec' href='/academia/{e(m['academiaId'])}/matricula/{e(m['id'])}'>Mi matrícula</a>"
    return h + (f"<div class='mc-acc'>{acc}</div>" if acc else "") + "</div></div>"


@router.get("/mis-clases", response_class=HTMLResponse)
def pagina_mis_clases(request: Request, pagado: str = "") -> HTMLResponse:
    ses = sesion.de_request(request)
    if not ses:
        if sesion.activo():
            return HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=%2Fmis-clases"})
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'>"
                  "<h1 style='font-size:22px'>Mis clases y pagos</h1>"
                  "<p class='sub'>En esta web aún no está activo el inicio de sesión. Tus clases y pagos están en la app.</p>"
                  f"<div class='acciones' style='justify-content:center'><a class='btn' href='{PLAY_URL}'>Abrir Pichangol en Google Play</a></div></div>")
        return ui.shell("Mis clases y pagos", cuerpo, sesion=None)
    email = (ses.get("email") or "").strip().lower()
    ms, acs = _vista(email)
    hoy = horarios.ahora_local("PE").date().isoformat()
    if not ms:
        cuerpo = (f"<style>{_CSS}</style><div class='mcl'><h1>Mis clases y pagos</h1>"
                  "<div class='mc-card mc-vacio'><div class='em'>🎓</div><h2 style='margin:8px 0 4px'>Aún no tienes clases</h2>"
                  "<p class='sub'>Entra a «Academias» en Explorar y matricúlate, o únete con el código de tu profe en la app.</p>"
                  "<div class='acciones' style='justify-content:center'><a class='btn' href='/?deporte=academias'>Ver academias</a></div></div></div>")
        return ui.shell("Mis clases y pagos", cuerpo, sesion=ses, titulo_tab="Mis clases y pagos · Pichangol")
    familia = "".join(_tarjeta_familia(g, hoy, k) for k, g in enumerate(_grupos_familia(ms, acs)))
    tarjetas = "".join(_tarjeta_matricula(m, acs.get(m["academiaId"]), email, hoy) for m in ms)
    html_pagos = familia + tarjetas
    # Grupos que pagan con Culqi (soles) vs. con la pasarela hospedada ($ / Bs).
    n_pagar = html_pagos.count("data-pagar=")
    n_hosp = html_pagos.count("data-pasarela=")
    hay_culqi = n_pagar > n_hosp
    medio = (f"<div class='mc-card mc-medio' style='padding:14px 16px'>{ui.selector_medio_pago()}</div>" if hay_culqi else "")
    cfg = json.dumps({"pk": config.CULQI_PUBLIC_KEY, "cargo": _cs.activo("academias"),
                      "correo": empresa.valores()["empresa_correo"]}, ensure_ascii=False)
    # Volvió de la pasarela con el pago aplicado: aviso con el N.º de operación.
    aviso_ok = ""
    if pagado:
        from web import pago_hospedado as ph
        o = ph.orden(pagado)
        if o and o.get("email") == email and o.get("estado") == "aprobado" and (o.get("accion") or {}).get("tipo") == "cuotas":
            aviso_ok = str(o.get("mensaje") or "Pago registrado. ¡Gracias!")
    cuerpo = (f"<style>{_CSS}</style><div class='mcl'><h1>Mis clases y pagos</h1>"
              "<p class='intro'>Tus academias, tus cuotas y tus comprobantes. Lo mismo que ves en la app.</p>"
              f"<div class='estado' id='mcAviso' style='{'display:block' if aviso_ok else 'display:none'};background:#EEF8E8;color:#067A38;margin-bottom:14px'>{e(aviso_ok)}</div>"
              f"{familia}{medio}{tarjetas}</div>"
              f"<script>window.__misClases={cfg};</script>"
              + ("<script src='https://checkout.culqi.com/js/v4'></script>" if hay_culqi else "")
              + f"<script>{_ph_js() if n_hosp else ''}{_JS}</script>")
    return ui.shell("Mis clases y pagos", cuerpo, sesion=ses, titulo_tab="Mis clases y pagos · Pichangol")


def _ph_js() -> str:
    from web import pago_hospedado as ph
    return ph.JS_IR_PASARELA


_JS = r"""
(function(){
  var C = window.__misClases || {};
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function fmt(mon, v){ return mon + ' ' + (Math.round(v * 100) / 100).toFixed(2); }
  try{ var av = sessionStorage.getItem('pcg_aviso_clases'); if(av){ var el = document.getElementById('mcAviso'); el.textContent = av; el.style.display = 'block'; sessionStorage.removeItem('pcg_aviso_clases'); } }catch(e){}
  function body(g){ return document.querySelector('.mc-body[data-grupo="' + g + '"]'); }
  function sel(g){ return Array.prototype.slice.call(document.querySelectorAll('input[data-g="' + g + '"]:checked')); }
  // Cargo por servicio: lo cotiza el servidor (misma regla que al cobrar). En el pago
  // de UNA persona va con el deporte de la academia; en "Mi familia" con partes por persona.
  var cache = {}, timers = {};
  function claveCot(g){
    var b = body(g), s = sel(g), base = 0, partes = {};
    s.forEach(function(x){ var c = Math.round(parseFloat(x.dataset.m) * 100); base += c; partes[x.dataset.al] = (partes[x.dataset.al] || 0) + c; });
    var fam = !!document.querySelector('[data-pagar="' + g + '"][data-fam="1"]');
    var ps = fam ? Object.keys(partes).map(function(k){ return partes[k]; }) : [];
    return {base: base, partes: ps, dep: fam ? '' : (b.dataset.dep || ''), mon: b.dataset.mon, k: base + '|' + ps.join('.') + '|' + (fam ? '' : (b.dataset.dep || ''))};
  }
  function cotizar(g, cb){
    var q = claveCot(g);
    if(!C.cargo || q.base <= 0) return null;
    if(cache[q.k]) return cache[q.k];
    if(timers[g]) clearTimeout(timers[g]);
    timers[g] = setTimeout(function(){
      fetch('/web/cotizar?linea=academias&moneda=' + encodeURIComponent(q.mon) + '&base=' + q.base + '&deporte=' + encodeURIComponent(q.dep) + '&partes=' + q.partes.join(','))
        .then(function(r){ return r.json(); }).then(function(j){ if(j && j.ok){ cache[q.k] = j; pintar(g); if(cb) cb(); } }).catch(function(){});
    }, 120);
    return null;
  }
  function htmlDesglose(c, mon){
    var h = '<div style="text-align:left;display:grid;gap:8px">';
    (c.desglose || []).forEach(function(x){ h += '<div style="display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid #eee;padding:6px 0"><div><b>' + esc(x.nombre) + '</b><div style="color:#717171;font-size:12.5px">' + esc(x.detalle) + '</div></div><span style="white-space:nowrap;font-weight:700">' + fmt(mon, x.monto_centimos / 100) + '</span></div>'; });
    return h + '<div style="color:#717171;font-size:12px">' + esc(c.regla || '') + '. Un solo cargo por todo el pago. Lo de cada cuota va completo a la academia, menos su comisión.</div></div>';
  }
  function pintar(g){
    var b = body(g), s = sel(g), btn = document.querySelector('[data-pagar="' + g + '"]'); if(!btn) return;
    var mon = b.dataset.mon, total = 0, personas = {};
    s.forEach(function(x){ total += parseFloat(x.dataset.m); personas[x.dataset.al] = 1; });
    var np = Object.keys(personas).length, cg = cotizar(g), cargo = (cg && cg.activo && cg.cargo_centimos > 0) ? cg.cargo_centimos / 100 : 0;
    var lc = document.querySelector('[data-cargo="' + g + '"]'), la = document.querySelector('[data-ahorro="' + g + '"]');
    if(C.cargo && s.length){ lc.hidden = false; lc.innerHTML = '<span>Cargo por servicio Pichangol<button type="button" class="mc-info" data-info="' + g + '" aria-label="Qué incluye">ⓘ</button></span><b>' + (cg ? fmt(mon, cargo) : '…') + '</b>'; }
    else if(lc){ lc.hidden = true; }
    if(la){ var ah = cg && cg.ahorro_centimos > 0; la.hidden = !ah; if(ah) la.textContent = '🎉 Ahorras ' + fmt(mon, cg.ahorro_centimos / 100) + ' en el cargo por pagar en familia (un solo cobro).'; }
    btn.disabled = !s.length || btn.dataset.ocupado === '1';
    var fam = btn.dataset.fam === '1';
    btn.textContent = btn.dataset.ocupado === '1' ? 'Procesando…' : (!s.length ? 'Marca al menos una cuota' :
      (fam ? 'Pagar todo · ' : 'Pagar ') + fmt(mon, total + cargo) + (fam && np > 1 ? ' (' + np + ' personas)' : '') + (!fam && cargo > 0 ? ' (incluye cargo por servicio)' : ''));
  }
  document.querySelectorAll('[data-pagar]').forEach(function(b){ pintar(b.dataset.pagar); });
  document.addEventListener('change', function(ev){ var x = ev.target; if(x && x.dataset && x.dataset.g) pintar(x.dataset.g); });
  document.addEventListener('click', function(ev){
    var i = ev.target.closest && ev.target.closest('[data-info]');
    if(i){ ev.preventDefault(); var cg = cotizar(i.dataset.info); if(cg) pcgAvisar({titulo: cg.titulo || 'Cargo por servicio Pichangol', html: htmlDesglose(cg, body(i.dataset.info).dataset.mon), confirmar: 'Entendido', icono: '🛡️'}); return; }
    var c = ev.target.closest && ev.target.closest('[data-comp]');
    if(c){ comprobante(JSON.parse(c.dataset.comp)); return; }
    var s = ev.target.closest && ev.target.closest('[data-cancelar-sus]');
    if(s){ cancelarSus(s.dataset.cancelarSus); return; }
    var p = ev.target.closest && ev.target.closest('[data-pagar]');
    if(p){ pagar(p.dataset.pagar); }
  });
  function comprobante(d){
    var f = function(k, v, fuerte){ return '<div style="display:flex;gap:10px;padding:3px 0"><span style="width:110px;flex:none;color:#717171">' + k + '</span><span style="flex:1;min-width:0;overflow-wrap:anywhere;' + (fuerte ? 'font-weight:900;font-size:16px;color:#0B8A3E' : 'font-weight:600;color:#222') + '">' + v + '</span></div>'; };
    var h = '<div style="text-align:left;font-size:13.5px">' + (d.logo ? '<div style="text-align:center;margin-bottom:10px"><img src="' + esc(d.logo) + '" alt="" style="width:48px;height:48px;border-radius:10px;object-fit:cover" onerror="this.parentNode.remove()"></div>' : '');
    h += f('Academia', esc(d.academia)) + f('Alumno', esc(d.alumno)) + f('Concepto', esc(d.concepto)) + f('Fecha y hora', esc(d.fecha));
    if(d.op) h += f('N.º operación', esc(d.op));
    h += '<hr style="border:0;border-top:1px solid #eee;margin:8px 0">' + f('Monto', fmt(d.moneda, d.monto), !(d.cargo > 0));
    if(d.cargo > 0){ h += f('Cargo por servicio Pichangol', fmt(d.moneda, d.cargo)); if(d.personas > 1) h += '<div style="color:#717171;font-size:12px">Un solo cargo por las ' + d.personas + ' personas de ese pago.</div>'; h += f('Total pagado', fmt(d.moneda, d.monto + d.cargo), true); }
    h += '<div style="color:#717171;font-size:12px;margin-top:8px">Pago procesado por Pichangol.</div></div>';
    pcgConfirmar({titulo: 'Comprobante de pago', html: h, icono: '🧾', confirmar: 'Imprimir / PDF', cancelar: 'Cerrar'}).then(function(ok){ if(ok) window.open(d.url, '_blank', 'noopener'); });
  }
  function cancelarSus(id){
    pcgConfirmar({titulo: '¿Cancelar el débito automático?', mensaje: 'Dejarás de pagar automático cada mes. Podrás volver a matricularte cuando quieras.', confirmar: 'Sí, cancelar', cancelar: 'No', destructivo: true, icono: '💳'})
      .then(function(ok){ if(!ok) return; pcgCargando('Cancelando…');
        fetch('/web/mis-clases/suscripcion/' + encodeURIComponent(id) + '/cancelar', {method: 'POST'}).then(function(r){ return r.json(); })
          .then(function(j){ if(j.ok){ try{ sessionStorage.setItem('pcg_aviso_clases', 'Débito automático cancelado. Ya no se cobrará cada mes.'); }catch(e){} pcgRecargar('Actualizando…'); } else { pcgCargando(false); pcgAvisar({titulo: 'No se pudo cancelar', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); } })
          .catch(function(){ pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', mensaje: 'No pudimos cancelar. Inténtalo de nuevo.'}); }); });
  }
  function pagar(g, reintento){
    var b = body(g), s = sel(g), btn = document.querySelector('[data-pagar="' + g + '"]'), mon = b.dataset.mon;
    if(!s.length || btn.dataset.ocupado === '1') return;
    // $ / Bs: pasarela HOSPEDADA del país (PayPhone, Libélula o la de prueba en QAS).
    var hosp = btn.dataset.pasarela || '', hospNombre = btn.dataset.pasarelaNombre || '';
    if(!C.pk && !hosp){ pcgAvisar({titulo: 'Pago no disponible', mensaje: 'El pago en línea no está disponible por ahora. Paga desde la app.'}); return; }
    var cg = cotizar(g);
    if(C.cargo && !cg){ reintento = (reintento || 0) + 1; if(reintento > 24){ pcgAvisar({titulo: 'No pudimos calcular el total', mensaje: 'Recarga la página e inténtalo de nuevo.'}); return; } setTimeout(function(){ pagar(g, reintento); }, 250); return; }
    var total = 0, personas = {}, lineas = [];
    s.forEach(function(x){ total += parseFloat(x.dataset.m); personas[x.dataset.al] = 1;
      var fila = x.closest('.mc-f'), t = fila.querySelector('.tx b').textContent, per = '';
      var n = fila.previousElementSibling;
      while(n && !n.classList.contains('mc-per')) n = n.previousElementSibling; if(n) per = n.textContent.split(' · ')[0] + ' · ';
      lineas.push({t: esc(per + t), m: parseFloat(x.dataset.m)}); });
    var cargoC = (cg && cg.activo && cg.cargo_centimos > 0) ? cg.cargo_centimos : 0, montoC = Math.round(total * 100) + cargoC;
    var medio = hosp ? hosp : (window.pcgMedioPago ? pcgMedioPago() : 'yape');
    pcgResumenPago({moneda: mon, medio: medio, medioNombre: hospNombre, lineas: lineas, total: montoC / 100,
                    cargo: cargoC ? {monto: cargoC / 100, titulo: cg.titulo, html: htmlDesglose(cg, mon), ahorro: (cg.ahorro_centimos || 0) / 100} : null,
                    nota: hosp ? 'Te llevamos a la página segura de ' + hospNombre + ' y, al volver, tus cuotas quedan pagadas.' : ''})
      .then(function(ok){ if(!ok) return;
        if(hosp){
          btn.dataset.ocupado = '1'; pintar(g);
          pcgIrPasarela('/web/mis-clases/pagar-pasarela', {total_centimos: montoC, cuotas: s.map(function(x){ return {alumno_id: x.dataset.al, cuota_id: x.dataset.cu}; })}, hospNombre)
            .then(function(j){
              if(j && j.ok) return;
              btn.dataset.ocupado = ''; pintar(g);
              if(j && j.error === 'en_curso' && j.url){
                pcgConfirmar({titulo: 'Tienes un pago en curso', icono: '⏳', confirmar: 'Ver mi pago', cancelar: 'Ahora no', mensaje: j.mensaje})
                  .then(function(ok2){ if(ok2) pcgIr(j.url, 'Abriendo tu pago…'); });
                return;
              }
              pcgAvisar({titulo: (j && j.error === 'cambio') ? 'Tus cuotas cambiaron' : 'No se pudo abrir el pago', mensaje: (j && j.mensaje) || 'Inténtalo de nuevo.', icono: '⚠️'})
                .then(function(){ if(j && j.error === 'cambio') pcgRecargar(); });
            });
          return;
        }
        Culqi.publicKey = C.pk;
        Culqi.settings({title: 'Pichangol', currency: 'PEN', amount: montoC});
        Culqi.options({lang: 'es', installments: false, paymentMethods: {yape: medio === 'yape', tarjeta: medio === 'tarjeta', bancaMovil: false, agente: false, billetera: false, cuotealo: false},
                       style: {logo: '', bannerColor: '#0F1B2D', buttonBackground: '#0E8F67', buttonText: 'Pagar', buttonTextColor: '#FFFFFF'}});
        window.culqi = function(){
          if(Culqi.token){
            var token = Culqi.token.id, m = (Culqi.token.iin && Culqi.token.iin.card_brand) ? 'tarjeta' : 'yape';
            Culqi.close(); btn.dataset.ocupado = '1'; pintar(g); pcgCargando('Confirmando tu pago…');
            fetch('/web/mis-clases/pagar', {method: 'POST', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({token: token, medio: m, total_centimos: montoC, cuotas: s.map(function(x){ return {alumno_id: x.dataset.al, cuota_id: x.dataset.cu}; })})})
              .then(function(r){ return r.json(); })
              .then(function(j){
                if(j.ok){ try{ sessionStorage.setItem('pcg_aviso_clases', j.mensaje); }catch(e){} pcgRecargar('Actualizando tus pagos…'); return; }
                btn.dataset.ocupado = ''; pcgCargando(false); pintar(g);
                pcgAvisar({titulo: j.error === 'cambio' ? 'Tus cuotas cambiaron' : 'No se completó el pago', mensaje: j.mensaje || 'El pago no se pudo procesar. No se te cobró nada.', icono: '⚠️'})
                  .then(function(){ if(j.error === 'cambio' || j.error === 'guardar') pcgRecargar(); });
              }).catch(function(){ btn.dataset.ocupado = ''; pcgCargando(false); pintar(g);
                pcgAvisar({titulo: 'No pudimos confirmar el pago', mensaje: 'Si te cobraron, escríbenos a ' + C.correo + ' con tu correo.'}); });
          } else if(Culqi.order){ pcgAvisar({mensaje: 'Este medio de pago no está habilitado. Usa Yape o tarjeta.'}); }
          else { pcgAvisar({titulo: 'No se pudo procesar el pago', mensaje: (Culqi.error && Culqi.error.user_message) || 'Inténtalo de nuevo.'}); }
        };
        Culqi.open();
      });
  }
})();
"""


# ── pagar ────────────────────────────────────────────────────────────────────

class CuotaSel(BaseModel):
    alumno_id: str
    cuota_id: str


class PagarCuotasReq(BaseModel):
    token: str
    medio: str = "yape"
    cuotas: list[CuotaSel]
    total_centimos: int = 0  # lo que vio el cliente: si el servidor calcula otro, no cobra


def _json(ok: bool, **kw) -> dict:
    return {"ok": ok, **kw}


@router.post("/web/mis-clases/pagar")
def pagar_cuotas(req: PagarCuotasReq, request: Request = None) -> dict:
    """Cobra las cuotas pendientes elegidas (de UNA persona = `_pagarCuotas`, o
    de varias = `_pagarFamilia`) y las registra como el app (ver módulo)."""
    ses = sesion.de_request(request) if request is not None else None
    if not ses:
        return _json(False, error="sesion_requerida", mensaje="Inicia sesión con Google para pagar tus cuotas.")
    email = (ses.get("email") or "").strip().lower()
    pedidas = [(x.alumno_id.strip(), x.cuota_id.strip()) for x in (req.cuotas or []) if x.alumno_id and x.cuota_id]
    if not pedidas or not req.token.strip():
        return _json(False, error="vacio", mensaje="Marca al menos una cuota.")
    if len(pedidas) > 60 or len(set(pedidas)) != len(pedidas):
        return _json(False, error="cambio", mensaje="Tu selección no es válida. Recarga la página.")
    lock = _candado(email)
    if not lock.acquire(blocking=False):
        return _json(False, error="en_curso", mensaje="Ya hay un pago en curso con tu cuenta. Espera a que termine.")
    try:
        return _pagar(req, ses, email, pedidas)
    finally:
        lock.release()


def _validar_cuotas(email: str, pedidas: list[tuple[str, str]]) -> tuple[dict | None, dict | None]:
    """Relee (y reconcilia) las matrículas del correo y valida las cuotas
    pedidas: existen, son suyas, siguen pendientes, no son de débito
    automático activo, tienen monto y van en UNA moneda. Mismo orden que el
    app (persona por persona, por vencimiento). Devuelve (prep, None) o
    (None, error) SIN cobrar nada."""
    ms, acs = _vista(email)  # relee y reconcilia: nunca se cobra una cuota que ya se pagó
    por_id = {m["id"]: m for m in ms}
    orden_m = {m["id"]: i for i, m in enumerate(ms)}
    items: list[tuple[dict, dict, dict]] = []
    for alumno_id, cuota_id in pedidas:
        m = por_id.get(alumno_id)
        a = acs.get(m["academiaId"]) if m else None
        c = next((x for x in _cuotas(m) if str(x["id"]) == cuota_id), None) if m else None
        if not m or not a or not c:
            return None, _json(False, error="cambio", mensaje="Alguna cuota ya no está disponible. Recarga la página; no se te cobró nada.")
        if c.get("pagada"):
            return None, _json(False, error="cambio", mensaje=f"«{c.get('concepto')}» ya está pagada. Recarga la página; no se te cobró nada.")
        if _auto_bloqueada(c, _suscripcion(m["id"])):
            return None, _json(False, error="cambio", mensaje=f"«{c.get('concepto')}» se cobra automático cada mes. No se te cobró nada.")
        if c["monto"] <= 0:
            return None, _json(False, error="cambio", mensaje="Hay una cuota sin monto. Consulta con tu academia.")
        items.append((c, m, a))
    monedas = {_moneda_academia(a)[1] for _c, _m, a in items}
    if len(monedas) != 1:
        return None, _json(False, error="moneda", mensaje="Paga por separado las cuotas de cada moneda.")
    iso = monedas.pop()
    sim = _moneda_academia(items[0][2])[0]
    items.sort(key=lambda x: (orden_m[x[1]["id"]], str(x[0].get("vencimiento") or "")))
    personas = list(dict.fromkeys(m["id"] for _c, m, _a in items))
    return {"items": items, "iso": iso, "sim": sim, "personas": personas, "familia": len(personas) > 1,
            "base_c": sum(int(round(c["monto"] * 100)) for c, _m, _a in items)}, None


def _cotizar_cuotas(prep: dict) -> dict:
    """Cargo por servicio de las cuotas (cotización `academias`: con `deporte`
    en el pago de una persona, con `partes` por persona en el familiar).
    Devuelve un dict serializable (viaja en la orden de la pasarela)."""
    from pagos.router import cotizacion_para
    items, iso, base_c = prep["items"], prep["iso"], prep["base_c"]
    if prep["familia"]:
        partes = [sum(int(round(c["monto"] * 100)) for c, m, _a in items if m["id"] == pid) for pid in prep["personas"]]
        cot = cotizacion_para("academias", iso, base_c, medio=None, partes=partes)
    else:
        cot = cotizacion_para("academias", iso, base_c, medio=None, deporte=str(items[0][2].get("deporte") or ""))
    cargo_c = cot.cargo_centimos if cot.cargo_centimos > 0 else 0
    return {"cargo_centimos": int(cargo_c), "desglose": list(cot.desglose or []) if cargo_c else [],
            "ajuste": int(cot.ajuste_seguridad_centimos) if cargo_c else 0, "total_centimos": int(base_c + cargo_c)}


def _concepto_cuotas(prep: dict, cargo_c: int) -> str:
    items, n = prep["items"], len(prep["items"])
    if prep["familia"]:
        concepto = f"{n} cuota{'' if n == 1 else 's'} · {len(prep['personas'])} personas · Mi familia"
    else:
        concepto = items[0][0].get("concepto") if n == 1 else f"{n} cuotas · {items[0][2].get('nombre')}"
    return str(concepto) + (" + cargo por servicio" if cargo_c else "")


def _contabilizar_cuotas(prep: dict, cg: dict, email: str, charge_id: str, medio: str, marca: int) -> None:
    """Contabilidad POR ACADEMIA (= PagosService.registrarMatricula del app):
    `post_matricula` con `charge_id` y su parte del cargo (el desglose y el
    ajuste van en la 1.ª), idempotente por `cuo_<acad>_<marca>`, y el
    `cobro_web` por el total cobrado."""
    items, iso, familia = prep["items"], prep["iso"], prep["familia"]
    cargo_c = int(cg.get("cargo_centimos") or 0)
    por_aca: dict[str, list] = {}
    for it in items:
        por_aca.setdefault(it[2]["id"], []).append(it)
    subs = [sum(int(round(c["monto"] * 100)) for c, _m, _a in l) for l in por_aca.values()]
    reparto = _cs.repartir(cargo_c, subs)
    from pagos.router import MatriculaReq, post_matricula
    for k, (aid, lista) in enumerate(por_aca.items()):
        a = lista[0][2]
        sub = round(subs[k] / 100.0, 2)
        if familia:
            con = f"Cuotas {a.get('nombre')} · pago familiar"
        else:
            con = lista[0][0].get("concepto") if len(lista) == 1 else f"Cuotas {a.get('nombre')}"
        try:
            post_matricula(MatriculaReq(academia_id=aid, monto_soles=sub, matricula_id=f"cuo_{aid}_{marca}", pais=_iso_academia(a).lower(),
                                        concepto=con, charge_id=charge_id, cargo_servicio_centimos=reparto[k] if cargo_c else 0,
                                        cargo_desglose=(list(cg.get("desglose") or []) if (k == 0 and cargo_c) else []),
                                        cargo_ajuste_centimos=(int(cg.get("ajuste") or 0) if (k == 0 and cargo_c) else 0)))
        except Exception as ex:  # noqa: BLE001 — la contabilidad nunca deshace un cobro
            print(f"[mis-clases] contabilidad falló ({aid}, {charge_id}): {ex}", flush=True)
    try:
        from db.store import stores as _st
        if not any(p.tipo == "cobro_web" and p.culqi_charge_id == charge_id for p in _st.pagos[-500:]):
            _st.registrar_pago(tipo="cobro_web", monto_centimos=prep["base_c"] + cargo_c, moneda=iso, estado="aprobado", culqi_charge_id=charge_id,
                               email=email, medio=medio, concepto="cuotas:" + ",".join(c["id"] for c, _m, _a in items),
                               cargo_servicio_centimos=cargo_c, cargo_desglose=(list(cg["desglose"]) if (cargo_c and cg.get("desglose")) else None),
                               cargo_ajuste_centimos=int(cg.get("ajuste") or 0) if cargo_c else 0)
    except Exception:  # noqa: BLE001
        pass


def _marcas_cuotas(prep: dict, charge_id: str, ahora: str, cargo_c: int) -> dict[str, dict[str, dict]]:
    """{alumno_id: {cuota_id: marca}} con el formato de `AppState.
    marcarCuotaPagada`: el cargo, UNO por todo el pago, queda en la 1.ª."""
    cargo_soles = round(cargo_c / 100.0, 2)
    out: dict[str, dict[str, dict]] = {}
    primera = True
    for pid in prep["personas"]:
        marcas = {}
        for c, m, _a in prep["items"]:
            if m["id"] != pid:
                continue
            marcas[c["id"]] = {"operacionId": charge_id, "fechaPago": ahora,
                               "cargoServicio": cargo_soles if primera else 0,
                               "cargoPersonas": len(prep["personas"]) if prep["familia"] else 1}
            primera = False
        out[pid] = marcas
    return out


def _push_cuotas(prep: dict, email: str, no_marcadas: list[str]) -> None:
    """Push al dueño de cada academia (= _avisarCuotaPagada, una por cuota)."""
    try:
        from pagos.router import _aviso_push_usuario
        for c, m, a in prep["items"]:
            dueno = (a.get("dueno") or "").strip().lower()
            if dueno and dueno != email and c["id"] not in no_marcadas:
                _aviso_push_usuario(dueno, "Cuota pagada 💰", f"{m.get('nombre')} pagó {c.get('concepto')} · {prep['sim']} {c['monto']:.2f} ({a.get('nombre')}).", tipo="academia")
    except Exception:  # noqa: BLE001
        pass


def _mensaje_ok(prep: dict, charge_id: str) -> str:
    n = len(prep["items"])
    msg = (f"{n} cuotas de {len(prep['personas'])} personas pagadas en un solo pago. ¡Gracias!" if prep["familia"]
           else ("Cuota pagada. ¡Gracias!" if n == 1 else f"{n} cuotas pagadas. ¡Gracias!"))
    return f"{msg} N.º de operación: {charge_id}."


def _pagar(req: PagarCuotasReq, ses: dict, email: str, pedidas: list[tuple[str, str]]) -> dict:
    prep, err = _validar_cuotas(email, pedidas)
    if err:
        return err
    iso, sim, items = prep["iso"], prep["sim"], prep["items"]
    if not _pago_web_disponible(iso):
        return _json(False, error="moneda", mensaje=f"Las cuotas en {sim} se pagan desde la app: el pago en línea en esa moneda aún no está disponible en la web.")
    if iso != "PEN":
        return _json(False, error="usa_pasarela", mensaje=f"Las cuotas en {sim} se pagan con la pasarela de su país. Recarga la página e inténtalo otra vez.")
    cg = _cotizar_cuotas(prep)
    cargo_c = cg["cargo_centimos"]
    monto_cobro = cg["total_centimos"]
    if req.total_centimos and int(req.total_centimos) != monto_cobro:
        return _json(False, error="cambio", mensaje=f"El total cambió a {sim} {monto_cobro / 100:.2f}. Recarga la página; no se te cobró nada.")
    n = len(items)
    concepto = _concepto_cuotas(prep, cargo_c)
    from db.store import stores as _st
    titular = next((m for _c, m, _a in items if (m.get("email") or "").strip().lower() == email and not m.get("parentesco")), items[0][1])
    cliente = _st.cliente_de(email, nombre=(ses.get("nombre") or ""),
                             telefono=str(titular.get("whatsapp") or titular.get("apoderadoWhatsapp") or ""),
                             pais=str(_iso_academia(items[0][2]) or "").upper())
    cargo = culqi.crear_cargo(token=req.token.strip(), monto_centimos=monto_cobro, email=email, descripcion=str(concepto)[:80],
                              moneda=iso, cliente=cliente,
                              metadata={"canal": "web", "tipo": "cuotas_academia", "cuotas": n, "personas": len(prep["personas"]),
                                        "cargo_servicio_centimos": cargo_c})
    if not cargo.get("ok"):
        msg = str(cargo.get("error") or "")
        return _json(False, error="cargo_rechazado",
                     mensaje="El pago fue rechazado por tu banco o billetera. No se te cobró nada." + (f" ({msg[:80]})" if msg else ""))
    charge_id = str(cargo.get("charge_id") or "")
    medio = "yape" if req.medio == "yape" else "tarjeta"
    _contabilizar_cuotas(prep, cg, email, charge_id, medio, int(datetime.now().timestamp() * 1_000_000))

    # Cuotas pagadas (= AppState.marcarCuotaPagada): el cargo, UNO por todo el pago, queda en la 1.ª.
    no_marcadas = []
    for pid, marcas in _marcas_cuotas(prep, charge_id, datetime.now().isoformat(), cargo_c).items():
        hechas = marcar_cuotas_pagadas(pid, email, marcas)
        no_marcadas += [cid for cid in marcas if cid not in hechas]
    if no_marcadas:
        print(f"[mis-clases] cobro {charge_id} sin marcar cuotas {no_marcadas} ({email})", flush=True)
    _push_cuotas(prep, email, no_marcadas)
    print(f"[mis-clases] {email} pagó {n} cuota(s) de {len(prep['personas'])} persona(s) · {sim} {monto_cobro / 100:.2f} · {charge_id}", flush=True)
    if no_marcadas:
        return _json(False, error="guardar", charge_id=charge_id,
                     mensaje=(f"Tu pago se procesó (operación {charge_id}) pero no pudimos marcar todas las cuotas como pagadas. "
                              f"Escríbenos a {empresa.valores()['empresa_correo']} y lo completamos."))
    return _json(True, charge_id=charge_id, total=monto_cobro / 100.0, mensaje=_mensaje_ok(prep, charge_id))


# ── cuotas en $ / Bs por PASARELA HOSPEDADA (fase 2 parte 2, oct-2026) ───────

class PagarCuotasPasarelaReq(BaseModel):
    cuotas: list[CuotaSel]
    total_centimos: int = 0


def aplicar_pago_atomico(filas: dict[str, dict], pedidas: list[dict], sus_activas: set[str], operacion: str,
                         ahora: str, extras: dict[str, dict]) -> dict:
    """Regla del marcado TODO O NADA de una orden de cuotas (sobre las filas ya
    bloqueadas): cada cuota pedida debe existir, seguir pendiente (o ya estar
    pagada con ESTA misma operación: reintento), no ser de débito automático
    activo y tener el monto con el que se cobró. Si alguna falla, no se marca
    ninguna y se devuelven los conflictos. `extras[cuota_id]` = cargoServicio
    / cargoPersonas de la 1.ª cuota. Modifica `filas` en su lugar."""
    conflictos, a_marcar = [], []
    for p in pedidas:
        aid, cid = str(p["alumno_id"]), str(p["cuota_id"])
        d = filas.get(aid)
        c = next((x for x in (d or {}).get("cuotas") or [] if isinstance(x, dict) and str(x.get("id")) == cid), None)
        if d is None or c is None:
            conflictos.append({"cuota": cid, "motivo": "no_existe"})
        elif c.get("pagada"):
            if str(c.get("operacionId") or "") != operacion:
                conflictos.append({"cuota": cid, "motivo": "pagada"})
        elif c.get("autoDebito") and aid in sus_activas:
            conflictos.append({"cuota": cid, "motivo": "debito_automatico"})
        elif abs(float(c.get("monto") or 0) - float(p["monto"])) > 0.005:
            conflictos.append({"cuota": cid, "motivo": "monto"})
        else:
            a_marcar.append((aid, c))
    if conflictos:
        return {"ok": False, "conflictos": conflictos}
    cambiadas: set[str] = set()
    for aid, c in a_marcar:
        marca = {"operacionId": operacion, "fechaPago": ahora, **(extras.get(str(c["id"])) or {})}
        aplicar_marcas({"cuotas": [c]}, {str(c["id"]): marca})
        cambiadas.add(aid)
    return {"ok": True, "hechas": [str(c["id"]) for _a, c in a_marcar], "cambiadas": sorted(cambiadas)}


def marcar_cuotas_atomico(email: str, pedidas: list[dict], sus_activas: set[str], operacion: str,
                          ahora: str, extras: dict[str, dict]) -> dict | None:
    """Marca pagadas las cuotas de una orden de la pasarela en UNA transacción:
    bloquea (`FOR UPDATE`, en orden de id) todas las matrículas involucradas
    que administra el correo y aplica `aplicar_pago_atomico`. Devuelve su
    resultado, o None si la base no respondió (la orden se reintenta)."""
    em = (email or "").strip().lower()
    ids = sorted({str(p["alumno_id"]) for p in pedidas})
    if not pg.habilitado or not em or not ids:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, data FROM pichangol_matriculas WHERE id = ANY(%s) AND coalesce(eliminada,false) = false "
                        "AND (lower(email) = %s OR lower(data->>'emailAlumno') = %s) ORDER BY id FOR UPDATE", (ids, em, em))
            filas = {str(r[0]): _json_dict(r[1]) for r in cur.fetchall()}
            res = aplicar_pago_atomico(filas, pedidas, sus_activas, operacion, ahora, extras)
            if not res["ok"] or not res["cambiadas"]:
                conn.rollback()
                return res
            for aid in res["cambiadas"]:
                cur.execute("UPDATE pichangol_matriculas SET data = %s::jsonb, updated_at = now() WHERE id = %s",
                            (json.dumps(filas[aid]), aid))
            conn.commit()
            return res
    except Exception as ex:  # noqa: BLE001
        print(f"[mis-clases] no se pudo marcar la orden {operacion}: {ex}", flush=True)
        return None


@router.post("/web/mis-clases/pagar-pasarela")
def pagar_cuotas_pasarela(req: PagarCuotasPasarelaReq, request: Request = None) -> dict:
    """Cuotas de academias que cobran en $ o Bs: mismas validaciones que el
    camino Culqi (`_validar_cuotas`, total recalculado y comparado con lo que
    vio el cliente), y la orden va a la pasarela del país. Al confirmarse,
    `al_pagar_hospedado` revalida y marca TODO O NADA con `FOR UPDATE`."""
    from web import pago_hospedado as ph
    ses = sesion.de_request(request) if request is not None else None
    if not ses:
        return _json(False, error="sesion_requerida", mensaje="Inicia sesión con Google para pagar tus cuotas.")
    email = (ses.get("email") or "").strip().lower()
    pedidas = [(x.alumno_id.strip(), x.cuota_id.strip()) for x in (req.cuotas or []) if x.alumno_id and x.cuota_id]
    if not pedidas:
        return _json(False, error="vacio", mensaje="Marca al menos una cuota.")
    if len(pedidas) > 60 or len(set(pedidas)) != len(pedidas):
        return _json(False, error="cambio", mensaje="Tu selección no es válida. Recarga la página.")
    prep, err = _validar_cuotas(email, pedidas)
    if err:
        return err
    iso, sim = prep["iso"], prep["sim"]
    if iso == "PEN":
        return _json(False, error="usa_culqi", mensaje="Estas cuotas se pagan con Yape o tarjeta en la misma página.")
    if not _pago_web_disponible(iso):
        return _json(False, error="moneda", mensaje=f"Las cuotas en {sim} se pagan desde la app: el pago en línea en esa moneda aún no está disponible en la web.")
    # Una cuota no puede estar en dos pagos en curso a la vez (p. ej. la individual y la de "Mi familia").
    pedidas_set = {f"{a}|{c}" for a, c in pedidas}
    for o in ph.ordenes_vivas("cuotas"):
        if o.get("email") == email and not o.get("pagado") and pedidas_set & {f"{x['alumno_id']}|{x['cuota_id']}" for x in o["accion"].get("cuotas") or []}:
            if sorted(pedidas_set) == sorted(f"{x['alumno_id']}|{x['cuota_id']}" for x in o["accion"].get("cuotas") or []):
                break  # la misma selección: abrir_orden la reusa
            return _json(False, error="en_curso", orden=o["id"], url=f"/web/pago/{o['id']}",
                         mensaje="Alguna de esas cuotas ya tiene un pago en curso. Termínalo o cancélalo antes de pagarla otra vez.")
    cg = _cotizar_cuotas(prep)
    if req.total_centimos and int(req.total_centimos) != cg["total_centimos"]:
        return _json(False, error="cambio", mensaje=f"El total cambió a {sim} {cg['total_centimos'] / 100:.2f}. Recarga la página; no se te cobró nada.")
    items = prep["items"]
    acs = {}
    for _c, _m, a in items:
        acs[a["id"]] = {k: a.get(k) for k in ("id", "nombre", "dueno", "deporte", "lat", "lng", "moneda")}
    accion = {"cuotas": [{"alumno_id": m["id"], "cuota_id": c["id"], "monto": c["monto"], "concepto": c.get("concepto") or "",
                          "academia_id": a["id"], "nombre": m.get("nombre") or ""} for c, m, a in items],
              "personas": prep["personas"], "familia": prep["familia"], "academias": acs, "cg": cg,
              "marca": int(datetime.now().timestamp() * 1_000_000)}
    clave = ",".join(sorted(pedidas_set))
    r = ph.abrir_orden(email=email, tipo="cuotas", clave=clave, iso=iso, monto_centimos=cg["total_centimos"],
                       concepto=_concepto_cuotas(prep, cg["cargo_centimos"]), accion=accion,
                       nombre=str(ses.get("nombre") or ""), request=request)
    return r


def _prep_de_orden(acc: dict) -> dict:
    """Reconstruye el `prep` CONGELADO en la orden (sin volver a la base)."""
    acs = acc.get("academias") or {}
    items = []
    for x in acc.get("cuotas") or []:
        a = dict(acs.get(x["academia_id"]) or {"id": x["academia_id"]})
        items.append(({"id": x["cuota_id"], "monto": float(x["monto"]), "concepto": x.get("concepto") or ""},
                      {"id": x["alumno_id"], "nombre": x.get("nombre") or ""}, a))
    a0 = items[0][2] if items else {}
    sim, iso = _moneda_academia(a0) if a0 else ("S/", "PEN")
    return {"items": items, "iso": iso, "sim": sim, "personas": list(acc.get("personas") or []),
            "familia": bool(acc.get("familia")), "base_c": sum(int(round(c["monto"] * 100)) for c, _m, _a in items)}


def al_pagar_hospedado(o: dict) -> None:
    """La pasarela CONFIRMÓ el cobro de una orden de cuotas: se revalida y se
    marca TODO O NADA con las filas bloqueadas. Si alguna cuota se pagó por
    otro lado mientras tanto (o cambió), no se cobra dos veces: el pago se
    devuelve (saldo o manual, como el pago tardío). Luego la misma
    contabilidad y pushes que el camino Culqi."""
    from web import pago_hospedado as ph
    acc = o["accion"]
    prep = _prep_de_orden(acc)
    email = o["email"]
    ref = ph.ref_cobro(o)
    cg = dict(acc.get("cg") or {})
    cargo_c = int(cg.get("cargo_centimos") or 0)
    marcas = _marcas_cuotas(prep, ref, datetime.now().isoformat(), cargo_c)
    extras = {}
    for por_cuota in marcas.values():
        for cid, mk in por_cuota.items():
            ex = {}
            if float(mk.get("cargoServicio") or 0) > 0:
                ex["cargoServicio"] = mk["cargoServicio"]
                if int(mk.get("cargoPersonas") or 1) > 1:
                    ex["cargoPersonas"] = mk["cargoPersonas"]
            extras[cid] = ex
    sus_activas = {x["alumno_id"] for x in acc.get("cuotas") or [] if _suscripcion(x["alumno_id"])}
    res = marcar_cuotas_atomico(email, list(acc.get("cuotas") or []), sus_activas, ref, datetime.now().isoformat(), extras)
    if res is None:
        raise RuntimeError("base no disponible para marcar las cuotas")  # el barrido reintenta
    if not res.get("ok"):
        print(f"[mis-clases] orden {o['id']}: cuotas cambiaron mientras pagaba {res.get('conflictos')} → devolución", flush=True)
        ph.devolver_pago(o, motivo="cuotas_ya_pagadas")
        return
    _contabilizar_cuotas(prep, cg, email, ref, "tarjeta", int(acc.get("marca") or 0) or int(datetime.now().timestamp() * 1_000_000))
    _push_cuotas(prep, email, [])
    o["estado"] = "aprobado"
    o["url_resultado"] = f"/mis-clases?pagado={o['id']}"
    o["mensaje"] = _mensaje_ok(prep, ref)
    print(f"[mis-clases] {email} pagó {len(prep['items'])} cuota(s) por {o['pasarela']} · {prep['sim']} {o['monto_centimos'] / 100:.2f} · {ref}", flush=True)


# ── débito automático ────────────────────────────────────────────────────────

@router.post("/web/mis-clases/suscripcion/{alumno_id}/cancelar")
def cancelar_suscripcion(alumno_id: str, request: Request = None) -> dict:
    """= `PagosService.cancelarSuscripcionAlumno`. Solo quien PAGA esa matrícula
    (la tarjeta es suya) y solo sobre su propia suscripción."""
    ses = sesion.de_request(request) if request is not None else None
    if not ses:
        return _json(False, error="sesion_requerida", mensaje="Inicia sesión con Google.")
    email = (ses.get("email") or "").strip().lower()
    m = next((x for x in matriculas_de_usuario(email) if x["id"] == alumno_id), None)
    from db.store import stores as _st
    sus = (_st.suscripciones_alumno or {}).get(alumno_id)
    if not m or (m.get("email") or "").strip().lower() != email or not sus \
            or (sus.get("email") or "").strip().lower() not in ("", email):
        return _json(False, error="no_encontrada", mensaje="No encontramos ese débito automático en tu cuenta.")
    from pagos.router import del_suscripcion_alumno
    del_suscripcion_alumno(alumno_id)
    print(f"[mis-clases] {email} canceló el débito automático de {alumno_id}", flush=True)
    return _json(True)


# ── comprobante imprimible ("Compartir / PDF" del app) ───────────────────────

@router.get("/mis-clases/comprobante/{alumno_id}/{cuota_id}", response_class=HTMLResponse)
def comprobante_cuota(request: Request, alumno_id: str, cuota_id: str) -> HTMLResponse:
    ses = sesion.de_request(request)
    volver = f"/mis-clases/comprobante/{alumno_id}/{cuota_id}"
    if not ses:
        if sesion.activo():
            from urllib.parse import quote
            return HTMLResponse("", status_code=302, headers={"Location": "/entrar?volver=" + quote(volver, safe="")})
        return ui.shell("Comprobante", f"<div class='panel' style='text-align:center;margin-top:24px'><h1>Comprobante</h1><p class='sub'>Tus comprobantes están en la app.</p><a class='btn' href='{PLAY_URL}'>Abrir la app</a></div>", sesion=None)
    email = (ses.get("email") or "").strip().lower()
    m = next((x for x in matriculas_de_usuario(email) if x["id"] == alumno_id), None)
    c = next((x for x in _cuotas(m) if str(x["id"]) == cuota_id), None) if m else None
    if not m or not c or not c.get("pagada"):
        return ui.shell("Comprobante", "<div class='panel' style='text-align:center;margin-top:24px'><h1>Comprobante no encontrado</h1>"
                                       "<p class='sub'>Solo ves los comprobantes de tus propias clases.</p><a class='btn' href='/mis-clases'>Mis clases y pagos</a></div>", sesion=ses)
    a = academias_por_id([m["academiaId"]]).get(m["academiaId"]) or {}
    sim = _moneda_academia(a)[0] if a else "S/"
    cargo = float(c.get("cargoServicio") or 0)
    personas = int(c.get("cargoPersonas") or 1)

    def li(k: str, v: str, fuerte: bool = False) -> str:
        return (f"<div class='cp-l'><span>{k}</span><b{' class=fuerte' if fuerte else ''}>{v}</b></div>")
    cuerpo = ("<style>.cp{max-width:520px;margin:24px auto 80px}.cp-l{display:flex;gap:12px;padding:6px 0;border-bottom:1px solid #F0F0F0}"
              ".cp-l span{width:130px;flex:none;color:#6a6a6a}.cp-l b{flex:1;min-width:0;overflow-wrap:anywhere;font-weight:600}.cp-l b.fuerte{font-weight:900;font-size:17px;color:#0B8A3E}"
              ".cp-cab{display:flex;gap:12px;align-items:center;margin-bottom:6px}.cp-cab img{width:48px;height:48px;border-radius:10px;object-fit:cover}"
              "@media print{header,footer,.cab,.no-print,.barra-fija,#abrirApp{display:none!important}.cp{margin:0}}</style>"
              "<div class='cp panel'><div class='cp-cab'>"
              + (f"<img src='{e(a.get('logoUrl'))}' alt=''>" if str(a.get("logoUrl") or "").startswith("http") else "")
              + f"<div><b style='font-size:18px'>{e(a.get('nombre') or 'Academia')}</b><div class='sub'>Comprobante de pago</div></div></div>"
              + li("Alumno", e(m.get("nombre"))) + li("Concepto", e(c.get("concepto")))
              + li("Fecha y hora", e(_fecha_txt(c.get("fechaPago") or c.get("vencimiento"), hora=True)))
              + (li("N.º operación", e(c.get("operacionId"))) if c.get("operacionId") else "")
              + li("Monto", f"{e(sim)} {c['monto']:.2f}", fuerte=cargo <= 0)
              + ((li("Cargo por servicio Pichangol", f"{e(sim)} {cargo:.2f}")
                  + (f"<div class='sub' style='font-size:12px;margin-top:4px'>Un solo cargo por las {personas} personas de ese pago.</div>" if personas > 1 else "")
                  + li("Total pagado", f"{e(sim)} {c['monto'] + cargo:.2f}", fuerte=True)) if cargo > 0 else "")
              + f"<p class='sub' style='font-size:12px;margin-top:12px'>Pago procesado por Pichangol · {e(empresa.valores().get('empresa_razon_social') or '')}</p>"
              "<div class='acciones no-print' style='margin-top:14px'><button type='button' class='btn' onclick='window.print()'>Imprimir / Guardar PDF</button>"
              "<a class='btn sec' href='/mis-clases'>Volver</a></div></div>")
    return ui.shell("Comprobante de pago", cuerpo, sesion=ses, titulo_tab="Comprobante · Pichangol")
