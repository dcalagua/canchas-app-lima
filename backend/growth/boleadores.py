"""BOLEADORES (sparring por turno como servicio extra; docs/diseno-boleadores.md).

Un jugador con identidad verificada se registra como boleador (categoría de la
Liga Pichangol, tarifa por turno, locales donde atiende, disponibilidad). El
cliente lo contrata al reservar (SOLO pago en línea); el boleador recibe push y
ACEPTA o RECHAZA (decisión del director, 28-sep-2026: puede estar ocupado). Al
aceptar nace su liquidación (`liquidacion_boleador`: monto − comisión FIJA por
turno S/ 2 · $ 0.50 · Bs 3) en la MISMA cola "por recibir" que los dueños; se
libera cuando el turno terminó. Si rechaza o no responde a tiempo, se devuelve
al cliente la parte del boleador + su cargo proporcional al medio original.

Fuente de verdad: este módulo (app y web llaman a `/boleadores/*` o a las
funciones internas). Datos en Postgres vía `web/datos.py`; contabilidad en
`stores.pagos`; pushes vía `pichangol_avisos` (tipo `boleador`).
"""

from __future__ import annotations

import hashlib
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

import config
import paises
from db.store import ahora, stores
from web import datos, horarios

router = APIRouter(prefix="/boleadores", tags=["boleadores"])

# Categorías = las de la Liga Pichangol (decisión del director, 28-sep-2026).
CATEGORIAS = ["5P", "5A", "5B", "4ta", "3ra", "2da", "1ra"]
DEPORTES = ["tenis", "padel"]
ETIQUETAS = ["Peloteo", "Partido de práctica", "Clases a niños", "Principiantes bienvenidos",
             "Dobles", "Alta intensidad", "Zurdo", "Saque fuerte"]
TARIFAS_SUGERIDAS = {"PEN": [15, 20, 25, 30, 40, 50], "USD": [5, 8, 10, 12, 15, 20], "BOB": [30, 40, 50, 60, 80, 100]}
TARIFA_MAX = {"PEN": 300.0, "USD": 100.0, "BOB": 700.0}
ESTADOS_VIVOS = ("pendiente", "aceptada")
FALTAS_PAUSA = 2          # faltas en 90 días → perfil pausado
FALTAS_VENTANA_DIAS = 90


def _require_app_key(x_app_key: str | None = Header(default=None)) -> None:
    if not config.APP_API_KEY:
        return
    if x_app_key != config.APP_API_KEY:
        raise HTTPException(status_code=401, detail="app_key_invalida")


_APP = [Depends(_require_app_key)]


# ── Reglas de negocio ──────────────────────────────────────────────────────────

def activo() -> bool:
    return stores.cfg("boleadores_activo") != "0"


def nombre_por_pais(iso: str) -> str:
    """Perú dice "boleador"; Ecuador y Bolivia, "sparring"."""
    return "Boleador" if (iso or "PE").upper() == "PE" else "Sparring"


def comision_centimos(moneda: str) -> int:
    """Comisión FIJA por turno en céntimos de la moneda (config de la torre;
    default = mínimo de comisión por moneda)."""
    iso = _iso(moneda)
    raw = stores.cfg(f"boleador_comision_{iso}")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = config.comision_min(iso)
    if v <= 0:
        v = config.comision_min(iso)
    return int(round(v * 100))


def horas_para_aceptar() -> float:
    try:
        return max(0.25, float(stores.cfg("boleador_aceptar_horas")))
    except (TypeError, ValueError):
        return 2.0


def _iso(moneda: str) -> str:
    m = (moneda or "PEN").strip().upper()
    return {"S/": "PEN", "$": "USD", "BS": "BOB"}.get(m, m if m in ("PEN", "USD", "BOB") else "PEN")


def slug_de(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:12]


def publico(b: dict, *, con_email: bool = False) -> dict:
    """Lo que ve el cliente (sin correo)."""
    iso = _iso(b.get("moneda"))
    st = b.get("stats") or {}
    out = {
        "slug": b.get("slug") or slug_de(b.get("email", "")),
        "nombre": b.get("nombre") or "",
        "foto": b.get("foto") or "",
        "categoria": b.get("categoria") or "",
        "deporte": b.get("deporte") or "tenis",
        "tarifa": float(b.get("tarifa") or 0),
        "moneda": iso,
        "simbolo": paises.simbolo_de_moneda(iso),
        "etiquetas": list(b.get("etiquetas") or []),
        "aceptadas": int(st.get("aceptadas") or 0),
        "activo": bool(b.get("activo")),
    }
    if con_email:
        out["email"] = b.get("email", "")
    return out


def _cfg_publica(pais: str = "PE") -> dict:
    iso = paises.moneda_de_pais(pais)
    return {
        "activo": activo(), "nombre": nombre_por_pais(pais), "categorias": CATEGORIAS, "deportes": DEPORTES,
        "etiquetas": ETIQUETAS, "tarifas": TARIFAS_SUGERIDAS.get(iso, TARIFAS_SUGERIDAS["PEN"]),
        "tarifa_max": TARIFA_MAX.get(iso, 300.0), "moneda": iso, "simbolo": paises.simbolo_de_moneda(iso),
        "comision": comision_centimos(iso) / 100.0, "horas_aceptar": horas_para_aceptar(),
        "requiere_verificacion": True,
    }


# ── Perfil ─────────────────────────────────────────────────────────────────────

class PerfilReq(BaseModel):
    email: str
    nombre: str = ""
    foto: str = ""
    celular: str = ""
    deporte: str = "tenis"
    categoria: str = ""
    tarifa: float = 0
    canchas: list[str] = []
    disponibilidad: dict = {}
    etiquetas: list[str] = []
    activo: bool = True


def validar_perfil(req: PerfilReq) -> tuple[str | None, dict]:
    """Devuelve (error, campos). Todo por selección: categoría del catálogo,
    canchas verificadas de Pichangol, disponibilidad por días/franja."""
    email = req.email.strip().lower()
    if not email:
        return "correo_requerido", {}
    if not datos.esta_verificado(email):
        return "verificacion_requerida", {}
    dep = (req.deporte or "tenis").strip().lower()
    if dep not in DEPORTES:
        return "deporte_invalido", {}
    cat = (req.categoria or "").strip()
    if cat not in CATEGORIAS:
        return "categoria_requerida", {}
    ids = []
    for cid in req.canchas or []:
        cid = str(cid or "").strip()
        if cid and cid not in ids:
            ids.append(cid)
    if not ids:
        return "canchas_requeridas", {}
    locales, iso = [], None
    vistos = set()
    for cid in ids:
        c = datos.cancha(cid)
        if not c or not datos.reservable(c):
            return "cancha_invalida", {}
        if iso is None:
            iso = paises.moneda_de_pais(paises.pais_de_coordenadas(c.get("lat"), c.get("lng")))
        club = str(c.get("club") or c.get("nombre") or "")
        if club.lower() not in vistos:
            vistos.add(club.lower())
            locales.append({"club": club, "lat": c.get("lat"), "lng": c.get("lng"), "zona": str(c.get("barrio") or c.get("distrito") or "")})
    iso = iso or "PEN"
    try:
        tarifa = round(float(req.tarifa), 2)
    except (TypeError, ValueError):
        return "tarifa_invalida", {}
    if tarifa <= 0 or tarifa > TARIFA_MAX.get(iso, 300.0):
        return "tarifa_invalida", {}
    disp = req.disponibilidad or {}
    dias = sorted({int(d) for d in (disp.get("dias") or []) if str(d).isdigit() and 1 <= int(d) <= 7}) or [1, 2, 3, 4, 5, 6, 7]
    desde = str(disp.get("desde") or "06:00")
    hasta = str(disp.get("hasta") or "23:00")
    if horarios.hora_en_minutos(desde) is None or horarios.hora_en_minutos(hasta) is None:
        return "horario_invalido", {}
    etiquetas = [x for x in (req.etiquetas or []) if x in ETIQUETAS][:6]
    data = {
        "slug": slug_de(email), "nombre": (req.nombre or "").strip()[:80], "foto": (req.foto or "").strip()[:400],
        "celular": "".join(ch for ch in (req.celular or "") if ch.isdigit())[:15],
        "canchas": ids, "locales": locales, "disponibilidad": {"dias": dias, "desde": desde, "hasta": hasta},
        "etiquetas": etiquetas,
    }
    return None, {"email": email, "deporte": dep, "categoria": cat, "tarifa": tarifa, "moneda": iso,
                  "activo": bool(req.activo), "data": data}


def guardar_perfil(req: PerfilReq) -> dict:
    err, campos = validar_perfil(req)
    if err:
        return {"ok": False, "error": err}
    previo = datos.boleador(campos["email"]) or {}
    data = dict(campos["data"])
    data["stats"] = previo.get("stats") or {"aceptadas": 0, "rechazadas": 0, "faltas": 0, "faltas_fechas": []}
    if not data["nombre"]:
        data["nombre"] = previo.get("nombre") or campos["email"].split("@")[0]
    ok = datos.guardar_boleador(campos["email"], deporte=campos["deporte"], categoria=campos["categoria"],
                                tarifa=campos["tarifa"], moneda=campos["moneda"], activo=campos["activo"], data=data)
    if not ok:
        return {"ok": False, "error": "no_guardado"}
    return {"ok": True, "boleador": datos.boleador(campos["email"])}


# ── Disponibilidad ─────────────────────────────────────────────────────────────

def _fin_de(hora: str, turnos: int, paso: int) -> str:
    m = horarios.hora_en_minutos(hora) or 0
    return horarios.minutos_en_hora(m + max(1, int(turnos)) * max(paso, 1))


def _en_franja(b: dict, fecha: str, hora: str, fin: str) -> bool:
    d = b.get("disponibilidad") or {}
    try:
        wd = date.fromisoformat(fecha).isoweekday()
    except ValueError:
        return False
    dias = d.get("dias") or [1, 2, 3, 4, 5, 6, 7]
    if wd not in dias:
        return False
    ini = horarios.hora_en_minutos(hora)
    fm = horarios.hora_en_minutos(fin)
    de = horarios.hora_en_minutos(str(d.get("desde") or "00:00")) or 0
    ha = horarios.hora_en_minutos(str(d.get("hasta") or "24:00"))
    if ha is None:
        ha = 24 * 60
    if ini is None or fm is None:
        return False
    if fm <= ini:
        fm += 24 * 60  # turno que cruza medianoche
    if ha <= de:
        ha += 24 * 60
    return de <= ini and fm <= ha


def disponibles(cancha_id: str, fecha: str, hora: str, turnos: int = 1, deporte: str = "") -> list[dict]:
    """Boleadores que pueden atender esa reserva: atienden en la cancha, el
    local los permite, la franja cae en su disponibilidad y no tienen otra
    solicitud viva que se cruce."""
    if not activo():
        return []
    c = datos.cancha(cancha_id)
    if not c or not datos.permite_boleadores(cancha_id):
        return []
    deps = [str(x).lower() for x in (c.get("deportes") or [c.get("deporte")]) if x]
    dep = (deporte or "").strip().lower() or (deps[0] if deps else "")
    if dep and dep not in DEPORTES:
        return []
    paso = int(c.get("duracion_slot_min") or 60)
    fin = _fin_de(hora, turnos, paso)
    out = []
    for b in datos.boleadores_de_cancha(cancha_id, dep):
        if not _en_franja(b, fecha, hora, fin):
            continue
        if datos.solicitudes_cruce(b["email"], fecha, hora, fin):
            continue
        out.append(publico(b))
    return out


# ── Solicitudes ────────────────────────────────────────────────────────────────

def _vence_en(c: dict | None, fecha: str, hora: str) -> datetime:
    """Plazo para aceptar: `horas_para_aceptar` desde ahora, pero nunca después
    de 1 h antes del turno; y al menos 10 min."""
    ahora_utc = datetime.now(timezone.utc)
    limite = ahora_utc + timedelta(hours=horas_para_aceptar())
    try:
        pais = paises.pais_de_coordenadas((c or {}).get("lat"), (c or {}).get("lng"))
        tz = horarios.ahora_local(pais).tzinfo
        ini = datetime.fromisoformat(f"{fecha}T{hora}:00").replace(tzinfo=tz) - timedelta(hours=1)
        limite = min(limite, ini.astimezone(timezone.utc))
    except (ValueError, TypeError):
        pass
    return max(limite, ahora_utc + timedelta(minutes=10))


def _fin_turno_utc(c: dict | None, fecha: str, hora_fin: str, hora_inicio: str) -> datetime | None:
    try:
        pais = paises.pais_de_coordenadas((c or {}).get("lat"), (c or {}).get("lng"))
        tz = horarios.ahora_local(pais).tzinfo
        f = datetime.fromisoformat(f"{fecha}T{hora_fin}:00").replace(tzinfo=tz)
        if (horarios.hora_en_minutos(hora_fin) or 0) <= (horarios.hora_en_minutos(hora_inicio) or 0):
            f += timedelta(days=1)  # termina pasada la medianoche
        return f.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def linea_reserva(b: dict, turnos: int) -> dict:
    """Línea `extras` de la reserva (mismo formato que los demás servicios
    extra: `precio` = TOTAL de la línea) + quién es el boleador."""
    tarifa = float(b.get("tarifa") or 0)
    n = max(1, int(turnos))
    return {"clave": "boleador", "precio": round(tarifa * n, 2), "unitario": tarifa, "cantidad": n,
            "nombre": f"Boleador · {b.get('nombre') or 'Boleador'}", "emoji": "🎾", "tipo": "turno",
            "boleador": b.get("slug") or slug_de(b.get("email", "")), "categoria": b.get("categoria") or "",
            "estado": "pendiente"}


def crear_solicitud(*, boleador: dict, cliente_email: str, cliente_nombre: str, reserva_ids: list[str],
                    reserva_ref: str, cancha: dict | None, fecha: str, hora_inicio: str, hora_fin: str,
                    turnos: int, charge_id: str = "", cargo_centimos: int = 0, medio: str = "",
                    canal: str = "app") -> dict | None:
    """Registra la solicitud tras el PAGO y avisa al boleador (push) y al
    cliente. Devuelve la solicitud o None si no se pudo guardar."""
    iso = _iso(boleador.get("moneda"))
    n = max(1, int(turnos))
    monto = int(round(float(boleador.get("tarifa") or 0) * 100)) * n
    com = comision_centimos(iso) * n
    if com >= monto:
        com = max(0, monto - 1)  # una tarifa menor que la comisión nunca deja neto negativo
    sol = {
        "id": f"bs_{int(time.time() * 1_000_000)}", "boleador_email": boleador["email"],
        "cliente_email": (cliente_email or "").strip().lower(), "cliente_nombre": (cliente_nombre or "").strip()[:80],
        "reserva_ref": reserva_ref, "cancha_id": (cancha or {}).get("id") or "", "club": str((cancha or {}).get("club") or (cancha or {}).get("nombre") or ""),
        "fecha": fecha, "hora_inicio": hora_inicio, "hora_fin": hora_fin, "turnos": n,
        "monto_centimos": monto, "comision_centimos": com, "moneda": iso, "estado": "pendiente",
        "canal": canal, "charge_id": charge_id or "", "vence_en": _vence_en(cancha, fecha, hora_inicio),
        "respondido_en": None,
        "data": {"reserva_ids": list(reserva_ids), "cargo_centimos": int(cargo_centimos or 0), "medio": medio or "",
                 "cancha": str((cancha or {}).get("nombre") or ""), "boleador_nombre": boleador.get("nombre") or ""},
    }
    if not datos.insertar_solicitud(sol):
        return None
    sim = paises.simbolo_de_moneda(iso)
    _push(boleador["email"], "Te contrataron 🎾",
          f"{sol['cliente_nombre'] or 'Un jugador'} · {sol['club']} · {horarios.fecha_larga(fecha)} {hora_inicio}–{hora_fin} · "
          f"ganas {sim} {(monto - com) / 100.0:.2f}. Tienes {_plazo_txt(sol['vence_en'])} para aceptar.")
    if sol["cliente_email"]:
        _push(sol["cliente_email"], "Esperando al boleador ⏳",
              f"Le avisamos a {boleador.get('nombre') or 'tu boleador'} para el {horarios.fecha_larga(fecha)} {hora_inicio}. "
              "Si no puede, te devolvemos su parte automáticamente.")
    sol["vence_en"] = sol["vence_en"].isoformat()
    return sol


def _plazo_txt(vence_en: datetime) -> str:
    mins = int((vence_en - datetime.now(timezone.utc)).total_seconds() // 60)
    if mins >= 90:
        return f"{round(mins / 60)} h"
    return f"{max(mins, 1)} min"


def _push(email: str, titulo: str, cuerpo: str) -> None:
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(email, titulo, cuerpo, tipo="boleador")
    except Exception:  # noqa: BLE001
        pass


def _ids_de(sol: dict) -> list[str]:
    ids = [str(x) for x in ((sol.get("data") or {}).get("reserva_ids") or []) if x]
    if ids:
        return ids
    ref = sol.get("reserva_ref") or ""
    if ref.startswith("grp_"):
        return [str(r["id"]) for r in datos.reservas_por_grupo(ref)]
    return [ref] if ref else []


def _cancha_de(sol: dict) -> dict | None:
    return datos.cancha(sol.get("cancha_id") or "") if sol.get("cancha_id") else None


def aceptar(sol_id: str, email: str) -> dict:
    """El boleador acepta: nace su liquidación (neto = monto − comisión fija ×
    turnos), liberada al terminar el turno; la reserva marca el boleador como
    confirmado; push al cliente."""
    sol = datos.solicitud(sol_id)
    if not sol:
        return {"ok": False, "error": "no_existe"}
    if sol["boleador_email"] != (email or "").strip().lower():
        return {"ok": False, "error": "ajena"}
    if sol["estado"] == "aceptada":
        return {"ok": True, "solicitud": sol, "ya": True}
    if sol["estado"] != "pendiente":
        return {"ok": False, "error": sol["estado"]}
    if sol.get("vence_en"):
        try:
            if datetime.fromisoformat(sol["vence_en"]) < datetime.now(timezone.utc):
                vencer_pendientes()
                return {"ok": False, "error": "vencida"}
        except ValueError:
            pass
    if not datos.actualizar_solicitud(sol_id, estado="aceptada", respondida=True, solo_si_estado=("pendiente",)):
        return {"ok": False, "error": "no_actualizada"}
    c = _cancha_de(sol)
    clave = f"bol:{sol_id}"
    if stores.pago_por_charge(clave) is None:
        stores.registrar_pago(
            tipo="liquidacion_boleador", monto_centimos=sol["monto_centimos"], moneda=sol["moneda"], estado="aprobado",
            dueno_id=sol["boleador_email"], culqi_charge_id=clave, cargo_id=(sol.get("charge_id") or None),
            comision_centimos=sol["comision_centimos"], medio=(sol.get("data") or {}).get("medio") or "",
            concepto=f"🎾 Boleador · {(sol.get('data') or {}).get('boleador_nombre') or sol['boleador_email']} · "
                     f"{sol['club'] or (sol.get('data') or {}).get('cancha') or 'cancha'} · {sol['fecha']} {sol['hora_inicio']}",
            disponible_en=_fin_turno_utc(c, sol["fecha"], sol["hora_fin"], sol["hora_inicio"]))
    datos.marcar_extra_boleador(_ids_de(sol), "aceptada")
    b = datos.boleador(sol["boleador_email"]) or {}
    st = dict(b.get("stats") or {})
    st["aceptadas"] = int(st.get("aceptadas") or 0) + 1
    datos.actualizar_boleador(sol["boleador_email"], data_merge={"stats": st})
    if sol.get("cliente_email"):
        _push(sol["cliente_email"], "Boleador confirmado ✅",
              f"{b.get('nombre') or 'Tu boleador'} ({b.get('categoria') or ''}) te espera el {horarios.fecha_larga(sol['fecha'])} "
              f"{sol['hora_inicio']} en {sol['club'] or 'la cancha'}. Escríbele por el chat si necesitas coordinar.")
    print(f"[boleador] aceptada {sol_id} {sol['boleador_email']} {sol['fecha']} {sol['hora_inicio']} neto={sol['monto_centimos'] - sol['comision_centimos']}", flush=True)
    return {"ok": True, "solicitud": datos.solicitud(sol_id) or {**sol, "estado": "aceptada"}}


def rechazar(sol_id: str, email: str, motivo: str = "") -> dict:
    sol = datos.solicitud(sol_id)
    if not sol:
        return {"ok": False, "error": "no_existe"}
    if sol["boleador_email"] != (email or "").strip().lower():
        return {"ok": False, "error": "ajena"}
    if sol["estado"] != "pendiente":
        return {"ok": False, "error": sol["estado"]}
    r = _cerrar_sin_boleador(sol, "rechazada", motivo=motivo[:120])
    b = datos.boleador(sol["boleador_email"]) or {}
    st = dict(b.get("stats") or {})
    st["rechazadas"] = int(st.get("rechazadas") or 0) + 1
    datos.actualizar_boleador(sol["boleador_email"], data_merge={"stats": st})
    return r


def vencer_pendientes() -> int:
    """Cron: las pendientes cuyo plazo pasó se cierran como `vencida` y se
    devuelve la parte al cliente. Devuelve cuántas cerró."""
    n = 0
    for sol in datos.solicitudes_vencidas():
        r = _cerrar_sin_boleador(sol, "vencida", motivo="sin respuesta a tiempo")
        if r.get("ok"):
            n += 1
    return n


def _cerrar_sin_boleador(sol: dict, estado: str, motivo: str = "") -> dict:
    """Rechazada / vencida / cancelada por el boleador: la reserva sigue SIN
    boleador y se devuelve su parte (+ cargo proporcional) al cliente."""
    if not datos.actualizar_solicitud(sol["id"], estado=estado, respondida=True,
                                      data_merge={"motivo": motivo} if motivo else None,
                                      solo_si_estado=ESTADOS_VIVOS):
        return {"ok": False, "error": "no_actualizada"}
    dev = _devolver_parte(sol, estado)
    datos.marcar_extra_boleador(_ids_de(sol), estado)
    sim = paises.simbolo_de_moneda(sol["moneda"])
    nombre = (sol.get("data") or {}).get("boleador_nombre") or "El boleador"
    if sol.get("cliente_email"):
        txt = {"reembolsado": f"Te devolvemos {sim} {dev['monto_centimos'] / 100.0:.2f} al mismo medio de pago (3 a 7 días hábiles).",
               "manual": f"Te devolvemos {sim} {dev['monto_centimos'] / 100.0:.2f}; te escribimos para coordinar.",
               "fallo": "Tu devolución está en proceso; te escribimos en breve.",
               "no_aplica": ""}.get(dev["estado"], "")
        quien = {"rechazada": f"{nombre} no puede ese día.", "vencida": f"{nombre} no respondió a tiempo.",
                 "cancelada_boleador": f"{nombre} canceló."}.get(estado, "")
        _push(sol["cliente_email"], "Sin boleador esta vez 😕",
              f"{quien} Tu reserva del {horarios.fecha_larga(sol['fecha'])} {sol['hora_inicio']} sigue en pie. {txt}".strip())
    print(f"[boleador] {estado} {sol['id']} {sol['boleador_email']} dev={dev}", flush=True)
    return {"ok": True, "estado": estado, "devolucion": dev}


def _devolver_parte(sol: dict, estado: str) -> dict:
    """Devuelve al medio ORIGINAL la parte del boleador + su cargo proporcional
    (culpa del boleador → 100 % con cargo). Sin cargo ligado → `manual` y queda
    en Cancelaciones web de la torre. Idempotente por solicitud."""
    from pagos import culqi
    clave = f"devbol:{sol['id']}"
    previo = stores.pago_por_charge(clave)
    if previo is not None:
        return {"estado": previo.estado, "monto_centimos": previo.monto_centimos}
    monto = int(sol["monto_centimos"]) + int((sol.get("data") or {}).get("cargo_centimos") or 0)
    if monto <= 0:
        return {"estado": "no_aplica", "monto_centimos": 0}
    charge = str(sol.get("charge_id") or "")
    est, refund_id, detalle = "manual", None, ""
    if charge.startswith("chr_"):
        r = culqi.reembolsar(charge_id=charge, monto_centimos=monto, motivo="solicitud_comprador")
        if r.get("ok"):
            est, refund_id = "reembolsado", r.get("refund_id")
        else:
            est, detalle = "fallo", str(r.get("error") or "")[:160]
    stores.registrar_pago(tipo="devolucion_boleador", monto_centimos=monto, moneda=sol["moneda"], estado=est,
                          dueno_id=sol.get("cliente_email") or None, culqi_charge_id=clave, cargo_id=(charge or None),
                          concepto=f"Devolución boleador ({estado}) · {sol['club']} · {sol['fecha']} {sol['hora_inicio']}")
    if est in ("manual", "fallo"):
        # Queda a la vista del operador en /admin → Cobros → Cancelaciones web.
        stores.cancelaciones_web.append({
            "id": stores.next_id("cancelacion_web"), "ref": sol.get("reserva_ref") or sol["id"], "ids": _ids_de(sol),
            "usuario": sol.get("cliente_email") or "", "cancha_id": sol.get("cancha_id") or "",
            "cancha": (sol.get("data") or {}).get("cancha") or "", "club": sol.get("club") or "", "fecha": sol["fecha"],
            "hora_inicio": sol["hora_inicio"], "hora_fin": sol["hora_fin"], "turnos": sol["turnos"],
            "monto": monto / 100.0, "moneda": paises.simbolo_de_moneda(sol["moneda"]), "moneda_iso": sol["moneda"],
            "pagado": True, "horas_antes": 0, "reembolso": est, "refund_id": refund_id, "detalle": detalle or f"boleador {estado}",
            "deuda_dueno_centimos": 0, "dueno": sol["boleador_email"], "creado_en": ahora().isoformat(),
            "motivo": f"boleador_{estado}", "medio_devolucion": "original", "monto_devuelto_centimos": monto,
            "cargo_centimos": int((sol.get("data") or {}).get("cargo_centimos") or 0), "incluye_cargo": True,
            "cancela_anfitrion": False, "quien": sol["boleador_email"], "costo_pasarela_centimos": 0, "boleador": True})
    return {"estado": est, "monto_centimos": monto, "refund_id": refund_id, "detalle": detalle}


def _anular_liquidacion(sol: dict, sim: str) -> int:
    """Reversa contable del boleador: sin pagar → anulada; ya pagada → deuda
    (`ajuste_cancelacion`). Devuelve la deuda en céntimos."""
    liq = stores.pago_por_charge(f"bol:{sol['id']}")
    if liq is None or liq.estado != "aprobado":
        return 0
    if not liq.liquidado:
        liq.estado = "anulado"
        return 0
    deuda = liq.monto_centimos - int(liq.comision_centimos or 0)
    if deuda > 0:
        stores.registrar_pago(tipo="ajuste_cancelacion", monto_centimos=deuda, moneda=liq.moneda, estado="pendiente",
                              dueno_id=sol["boleador_email"], culqi_charge_id=f"bol:{sol['id']}_ajuste",
                              concepto=f"Descuento por boleo cancelado · {sol['club']} · {sol['fecha']} {sol['hora_inicio']}")
    return deuda


def cancelar_por_reserva(ref: str, ids: list[str], *, quien: str = "cliente") -> dict | None:
    """El CLIENTE (o el local) canceló la reserva: la solicitud viva pasa a
    `cancelada`, se revierte la liquidación del boleador y se le avisa. La
    devolución al cliente la hace la política de la reserva (incluye la línea
    del boleador). Lo llama `_cancelar_reserva`."""
    sol = None
    for r in ([ref] + list(ids)):
        s = datos.solicitud_por_reserva(r)
        if s and s["estado"] in ESTADOS_VIVOS:
            sol = s
            break
    if not sol:
        return None
    if not datos.actualizar_solicitud(sol["id"], estado="cancelada", respondida=True,
                                      data_merge={"motivo": f"reserva cancelada por {quien}"}, solo_si_estado=ESTADOS_VIVOS):
        return None
    sim = paises.simbolo_de_moneda(sol["moneda"])
    deuda = _anular_liquidacion(sol, sim)
    _push(sol["boleador_email"], "Boleo cancelado 📅",
          f"{sol.get('cliente_nombre') or 'El jugador'} canceló la reserva del {horarios.fecha_larga(sol['fecha'])} "
          f"{sol['hora_inicio']} en {sol['club'] or 'la cancha'}. Ese turno vuelve a estar libre para ti.")
    print(f"[boleador] cancelada {sol['id']} por {quien} deuda={deuda}", flush=True)
    return {"id": sol["id"], "deuda_centimos": deuda}


def cancelar_boleador(sol_id: str, email: str, motivo: str = "") -> dict:
    """El BOLEADOR cancela después de aceptar: se devuelve al cliente su parte
    + cargo, se revierte la liquidación y cuenta como FALTA (2 en 90 días →
    perfil pausado)."""
    sol = datos.solicitud(sol_id)
    if not sol:
        return {"ok": False, "error": "no_existe"}
    if sol["boleador_email"] != (email or "").strip().lower():
        return {"ok": False, "error": "ajena"}
    if sol["estado"] == "pendiente":
        return rechazar(sol_id, email, motivo)
    if sol["estado"] != "aceptada":
        return {"ok": False, "error": sol["estado"]}
    r = _cerrar_sin_boleador(sol, "cancelada_boleador", motivo=motivo[:120])
    if not r.get("ok"):
        return r
    _anular_liquidacion(sol, paises.simbolo_de_moneda(sol["moneda"]))
    r["pausado"] = registrar_falta(sol["boleador_email"])
    return r


def registrar_falta(email: str) -> bool:
    """Suma una falta; con FALTAS_PAUSA en la ventana, pausa el perfil y avisa.
    Devuelve True si quedó pausado."""
    b = datos.boleador(email)
    if not b:
        return False
    st = dict(b.get("stats") or {})
    hoy = date.today()
    fechas = [f for f in (st.get("faltas_fechas") or []) if _dias_desde(f) <= FALTAS_VENTANA_DIAS]
    fechas.append(hoy.isoformat())
    st["faltas"] = int(st.get("faltas") or 0) + 1
    st["faltas_fechas"] = fechas[-10:]
    st["ultima_falta"] = hoy.isoformat()
    pausar = len(fechas) >= FALTAS_PAUSA
    datos.actualizar_boleador(email, activo=(False if pausar else None), data_merge={"stats": st})
    if pausar:
        _push(email, "Tu perfil de boleador quedó pausado ⏸️",
              f"Cancelaste {len(fechas)} boleos ya aceptados en {FALTAS_VENTANA_DIAS} días. Escríbenos si fue un error; "
              "puedes reactivarlo desde tu perfil cuando estés listo.")
    return pausar


def _dias_desde(iso: str) -> int:
    try:
        return (date.today() - date.fromisoformat(iso)).days
    except ValueError:
        return 10 ** 6


def estado_visible(sol: dict | None) -> str:
    """Texto corto para reservas y comprobantes."""
    if not sol:
        return ""
    return {"pendiente": "Esperando confirmación", "aceptada": "Confirmado ✅", "rechazada": "No disponible · devuelto",
            "vencida": "No respondió · devuelto", "cancelada": "Cancelado", "cancelada_boleador": "Canceló · devuelto"}.get(sol.get("estado", ""), "")


# ── Endpoints (APK; la web usa las funciones con su sesión) ────────────────────

@router.get("/config")
def get_config(pais: str = "PE") -> dict:
    """Catálogos para el registro (público)."""
    return _cfg_publica((pais or "PE").upper())


@router.get("/disponibles")
def get_disponibles(cancha_id: str, fecha: str, hora: str, turnos: int = 1, deporte: str = "") -> dict:
    """Boleadores que pueden atender esa reserva (público: la ficha web lo
    llama sin llave; no expone correos)."""
    return {"ok": True, "boleadores": disponibles(cancha_id, fecha, hora, turnos, deporte)}


@router.get("/perfil/{email}", dependencies=_APP)
def get_perfil(email: str) -> dict:
    b = datos.boleador(email)
    return {"ok": True, "boleador": b, "verificado": datos.esta_verificado(email),
            "config": _cfg_publica(_pais_de_boleador(b))}


def _pais_de_boleador(b: dict | None) -> str:
    if not b:
        return "PE"
    return {"PEN": "PE", "USD": "EC", "BOB": "BO"}.get(_iso(b.get("moneda")), "PE")


@router.post("/perfil", dependencies=_APP)
def post_perfil(req: PerfilReq) -> dict:
    return guardar_perfil(req)


class ActivoReq(BaseModel):
    email: str
    activo: bool


@router.post("/perfil/activo", dependencies=_APP)
def post_activo(req: ActivoReq) -> dict:
    b = datos.boleador(req.email)
    if not b:
        return {"ok": False, "error": "no_existe"}
    return {"ok": datos.actualizar_boleador(req.email, activo=req.activo)}


class SolicitarReq(BaseModel):
    slug: str
    cliente_email: str
    cliente_nombre: str = ""
    reserva_ids: list[str]
    reserva_ref: str = ""
    cancha_id: str
    fecha: str
    hora_inicio: str
    hora_fin: str
    turnos: int = 1
    charge_id: str = ""
    cargo_centimos: int = 0
    medio: str = ""


@router.post("/solicitar", dependencies=_APP)
def post_solicitar(req: SolicitarReq) -> dict:
    """El APK, tras cobrar la reserva con boleador, registra la solicitud
    (idempotente por reserva)."""
    b = datos.boleador_por_slug(req.slug)
    if not b or not b.get("activo"):
        return {"ok": False, "error": "boleador_no_disponible"}
    ref = req.reserva_ref or (req.reserva_ids[0] if req.reserva_ids else "")
    prev = datos.solicitud_por_reserva(ref)
    if prev and prev["estado"] in ESTADOS_VIVOS:
        return {"ok": True, "solicitud": prev, "ya": True}
    c = datos.cancha(req.cancha_id)
    sol = crear_solicitud(boleador=b, cliente_email=req.cliente_email, cliente_nombre=req.cliente_nombre,
                          reserva_ids=req.reserva_ids, reserva_ref=ref, cancha=c, fecha=req.fecha,
                          hora_inicio=req.hora_inicio, hora_fin=req.hora_fin, turnos=req.turnos,
                          charge_id=req.charge_id, cargo_centimos=req.cargo_centimos, medio=req.medio, canal="app")
    if not sol:
        return {"ok": False, "error": "no_guardada"}
    return {"ok": True, "solicitud": sol}


@router.get("/solicitudes", dependencies=_APP)
def get_solicitudes(email: str) -> dict:
    """Lo mío: como boleador (pendientes y aceptadas primero) y como cliente."""
    email = (email or "").strip().lower()
    como_bol = datos.solicitudes_de_boleador(email)
    como_cli = datos.solicitudes_de_cliente(email)
    for s in como_bol + como_cli:
        s["estado_visible"] = estado_visible(s)
        s["neto_centimos"] = int(s["monto_centimos"]) - int(s["comision_centimos"])
    return {"ok": True, "como_boleador": como_bol, "como_cliente": como_cli,
            "pendientes": sum(1 for s in como_bol if s["estado"] == "pendiente")}


class RespuestaReq(BaseModel):
    email: str
    motivo: str = ""


@router.post("/solicitudes/{sol_id}/aceptar", dependencies=_APP)
def post_aceptar(sol_id: str, req: RespuestaReq) -> dict:
    return aceptar(sol_id, req.email)


@router.post("/solicitudes/{sol_id}/rechazar", dependencies=_APP)
def post_rechazar(sol_id: str, req: RespuestaReq) -> dict:
    return rechazar(sol_id, req.email, req.motivo)


@router.post("/solicitudes/{sol_id}/cancelar", dependencies=_APP)
def post_cancelar(sol_id: str, req: RespuestaReq) -> dict:
    return cancelar_boleador(sol_id, req.email, req.motivo)
