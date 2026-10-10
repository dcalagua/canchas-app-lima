"""PLAN ACADEMIA = suscripción tipo Spotify (decisión del director, 10-oct-2026).

Las ACADEMIAS ya no pagan comisión por cobro: pagan a Pichangol una
suscripción mensual fija (S/ 11.50 · $ 3.00 · Bs 21.00, editables en la torre)
con 30 días de prueba gratis. Sus alumnos les pagan DIRECTO (Yape de la
academia): Pichangol NO maneja plata ajena.

Tres piezas:

1. **Plan** (`stores.planes_academia[academia_id]`): prueba → activa →
   vencida. Se paga con el SALDO del dueño (como Pichangol Pro) en la moneda
   de la academia; renueva solo desde el saldo si el dueño ya pagó alguna vez y
   no apagó la renovación. Avisos al dueño (push + correo) 3 días antes, 1 día
   antes, el día y al vencer. Sin plan vigente la academia se queda con su
   ficha pública: sin matrícula nueva, sin recordatorios ni panel.

2. **Pago directo con el código de seguridad de Yape**: la academia registra
   su Yape (`Academia.cobroDirecto = {yape, titular}`); el alumno yapea, pone
   en Pichangol los 3 dígitos del código de seguridad (y el N.º de operación)
   y la cuota queda "por confirmar"; la academia compara los 3 dígitos con la
   notificación de su Yape y confirma (o rechaza) con un toque. La fase 2
   confirmará sola leyendo la notificación en el celular de la academia.

3. **Recordatorios a los alumnos** (beneficio del plan): push + correo 3 días
   antes del vencimiento de cada cuota, el día y al vencer. Una vez por etapa
   (`stores.recordatorios_cuotas`).

Las MISMAS funciones las usan la web y el APK (endpoints `/academias/*`).
"""
from __future__ import annotations

import re
import threading
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db.store import stores

router = APIRouter(tags=["academias"])

MONEDAS = ("PEN", "USD", "BOB")
SIMBOLO = {"PEN": "S/", "USD": "$", "BOB": "Bs"}
PRECIO_DEFECTO = {"PEN": "11.50", "USD": "3.00", "BOB": "21.00"}
DIAS_PERIODO = 30
AVISO_DIAS = (3, 1, 0)  # avisos al dueño antes del vencimiento
_LOCK = threading.RLock()


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _hoy_lima(ahora: datetime | None = None) -> date:
    return ((ahora or _ahora()) - timedelta(hours=5)).date()


def _de_iso(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fecha_txt(s) -> str:
    d = _de_iso(s)
    if not d:
        return ""
    d = d - timedelta(hours=5)
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
    return f"{d.day} {meses[d.month - 1]} {d.year}"


# ── Configuración (torre) ─────────────────────────────────────────────────────

def modelo() -> str:
    m = (stores.cfg("acad_modelo") or "suscripcion").strip().lower()
    return m if m in ("suscripcion", "comision") else "suscripcion"


def es_suscripcion() -> bool:
    return modelo() == "suscripcion"


def precio_centimos(moneda: str) -> int:
    moneda = (moneda or "PEN").upper()
    val = stores.cfg(f"acad_plan_precio_{moneda}") or PRECIO_DEFECTO.get(moneda, "11.50")
    try:
        return max(0, int(round(float(val) * 100)))
    except (TypeError, ValueError):
        return int(round(float(PRECIO_DEFECTO.get(moneda, "11.50")) * 100))


def prueba_dias() -> int:
    try:
        return max(0, min(365, int(float(stores.cfg("acad_plan_prueba_dias") or 30))))
    except (TypeError, ValueError):
        return 30


def config_publica() -> dict:
    return {"modelo": modelo(), "prueba_dias": prueba_dias(), "periodo_dias": DIAS_PERIODO,
            "precios": {m: precio_centimos(m) / 100.0 for m in MONEDAS},
            "simbolos": dict(SIMBOLO)}


def set_config(*, modelo_nuevo: str | None = None, precios: dict | None = None,
               prueba: int | None = None) -> dict:
    """Torre → Cobros → Plan Academia. Valida y guarda en `stores.config`."""
    if modelo_nuevo is not None:
        m = str(modelo_nuevo).strip().lower()
        if m not in ("suscripcion", "comision"):
            raise ValueError("Modelo inválido.")
        stores.config["acad_modelo"] = m
    for mon, val in (precios or {}).items():
        mon = str(mon).upper()
        if mon not in MONEDAS:
            raise ValueError(f"Moneda inválida: {mon}")
        try:
            v = round(float(val), 2)
        except (TypeError, ValueError):
            raise ValueError(f"Precio inválido para {mon}.") from None
        if v < 0 or v > 1000:
            raise ValueError(f"El precio en {mon} debe estar entre 0 y 1000.")
        stores.config[f"acad_plan_precio_{mon}"] = f"{v:.2f}"
    if prueba is not None:
        p = int(prueba)
        if p < 0 or p > 365:
            raise ValueError("La prueba debe estar entre 0 y 365 días.")
        stores.config["acad_plan_prueba_dias"] = str(p)
    return config_publica()


# ── Moneda de la academia ─────────────────────────────────────────────────────

def moneda_de(a: dict) -> str:
    """ISO de la moneda de la academia = la de su sede (la misma que muestra su
    tarifario en la web)."""
    try:
        from web.academia import _moneda
        return _moneda(a)[1]
    except Exception:  # noqa: BLE001
        sim = (a.get("moneda") or "").strip()
        return {"S/": "PEN", "$": "USD", "Bs": "BOB"}.get(sim, "PEN")


def pais_de_moneda(moneda: str) -> str:
    return {"PEN": "PE", "USD": "EC", "BOB": "BO"}.get((moneda or "PEN").upper(), "PE")


# ── Estado del plan ───────────────────────────────────────────────────────────

def _reg(academia_id: str) -> dict | None:
    return stores.planes_academia.get(str(academia_id))


def asegurar(a: dict, ahora: datetime | None = None) -> dict:
    """Registro del plan de la academia; la primera vez arranca la PRUEBA
    gratis (desde hoy). Idempotente."""
    aid = str(a.get("id") or "")
    ahora = ahora or _ahora()
    with _LOCK:
        r = stores.planes_academia.get(aid)
        if r is None:
            r = {"academia_id": aid, "dueno": str(a.get("dueno") or "").strip().lower(),
                 "nombre": str(a.get("nombre") or ""), "moneda": moneda_de(a),
                 "prueba_desde": ahora.isoformat(),
                 "prueba_hasta": (ahora + timedelta(days=prueba_dias())).isoformat(),
                 "hasta": None, "auto_renovar": True, "pagado": False, "avisos": {}}
            stores.planes_academia[aid] = r
        else:
            # El dueño / nombre / moneda pueden cambiar (edición de la academia).
            if a.get("dueno"):
                r["dueno"] = str(a["dueno"]).strip().lower()
            if a.get("nombre"):
                r["nombre"] = str(a["nombre"])
            r["moneda"] = moneda_de(a) if (a.get("lat") or a.get("moneda")) else r.get("moneda", "PEN")
        return r


def vence(r: dict) -> datetime | None:
    """Fin del acceso: lo último entre la prueba y lo pagado."""
    fechas = [d for d in (_de_iso(r.get("prueba_hasta")), _de_iso(r.get("hasta"))) if d]
    return max(fechas) if fechas else None


def estado(a: dict, ahora: datetime | None = None) -> dict:
    """{estado: libre|prueba|activa|vencida, beneficios, vence, dias_restantes,
    precio, moneda, simbolo, auto_renovar, pagado}."""
    ahora = ahora or _ahora()
    moneda = moneda_de(a)
    base = {"modelo": modelo(), "moneda": moneda, "simbolo": SIMBOLO.get(moneda, "S/"),
            "precio": precio_centimos(moneda) / 100.0, "precio_centimos": precio_centimos(moneda),
            "prueba_dias": prueba_dias()}
    if not es_suscripcion():
        return {**base, "estado": "libre", "beneficios": True, "vence": None, "dias_restantes": None,
                "auto_renovar": False, "pagado": False}
    r = asegurar(a, ahora)
    v = vence(r)
    hasta_pago = _de_iso(r.get("hasta"))
    if v and v > ahora:
        est = "activa" if (hasta_pago and hasta_pago > ahora) else "prueba"
    else:
        est = "vencida"
    dias = max(0, (v - ahora).days + (1 if (v - ahora).seconds > 0 else 0)) if v and v > ahora else 0
    return {**base, "estado": est, "beneficios": est in ("prueba", "activa"),
            "vence": v.isoformat() if v else None, "vence_txt": fecha_txt(v.isoformat()) if v else "",
            "dias_restantes": dias, "auto_renovar": bool(r.get("auto_renovar", True)),
            "pagado": bool(r.get("pagado"))}


def beneficios(a: dict | None) -> bool:
    """¿La academia tiene el plan vigente (prueba o pagado)? Sin suscripción
    (modelo comisión) siempre True."""
    if not a:
        return False
    return bool(estado(a).get("beneficios"))


# ── Pagar / renovar ───────────────────────────────────────────────────────────

def pagar(a: dict, email: str, ahora: datetime | None = None, *, automatico: bool = False) -> dict:
    """Paga 1 mes del plan con el SALDO del dueño, en la moneda de la academia.
    Extiende desde el vencimiento vigente (prueba o pagado): no se pierden días."""
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    dueno = str(a.get("dueno") or "").strip().lower()
    if not email or email != dueno:
        return {"ok": False, "error": "no_dueno", "mensaje": "Solo el dueño de la academia puede pagar su plan."}
    if not es_suscripcion():
        return {"ok": False, "error": "sin_plan", "mensaje": "El Plan Academia no está activo."}
    moneda = moneda_de(a)
    precio = precio_centimos(moneda)
    sim = SIMBOLO.get(moneda, "S/")
    try:
        from pagos.router import moneda_billetera
        mon_billetera = moneda_billetera(email)
    except Exception:  # noqa: BLE001
        mon_billetera = moneda
    if mon_billetera != moneda:
        return {"ok": False, "error": "moneda_distinta",
                "mensaje": f"Tu billetera está en {SIMBOLO.get(mon_billetera, mon_billetera)} y el plan de esta academia se paga en {sim}."}
    with _LOCK:
        saldo = stores.saldo_centimos(email)
        if saldo < precio:
            return {"ok": False, "error": "falta_saldo", "falta_saldo": True,
                    "requerido_centimos": precio, "saldo_centimos": saldo,
                    "mensaje": f"Necesitas {sim} {precio / 100:.2f} de saldo. Recarga con Yape y vuelve a intentar."}
        r = asegurar(a, ahora)
        base = max([d for d in (vence(r), ahora) if d])
        r["hasta"] = (base + timedelta(days=DIAS_PERIODO)).isoformat()
        r["pagado"] = True
        r["ultimo_pago"] = ahora.isoformat()
        if not automatico:
            r["auto_renovar"] = True
        if precio > 0:
            stores.debitar(email, precio)
            stores.registrar_pago(tipo="suscripcion_academia", monto_centimos=precio, moneda=moneda, estado="aprobado",
                                  dueno_id=email, email=email,
                                  concepto=f"Plan Academia · {a.get('nombre') or ''} (1 mes)"[:120])
    print(f"[plan-academia] {a.get('id')} pagado por {email} hasta {r['hasta']}"
          + (" (renovación automática)" if automatico else ""), flush=True)
    return {"ok": True, "hasta": r["hasta"], "estado": estado(a, ahora),
            "saldo_centimos": stores.saldo_centimos(email)}


def cambiar_renovacion(a: dict, email: str, renovar: bool) -> dict:
    email = (email or "").strip().lower()
    if email != str(a.get("dueno") or "").strip().lower():
        return {"ok": False, "error": "no_dueno", "mensaje": "Solo el dueño de la academia puede cambiar esto."}
    r = asegurar(a)
    r["auto_renovar"] = bool(renovar)
    return {"ok": True, "auto_renovar": bool(renovar)}


def extender_cortesia(academia_id: str, dias: int, a: dict | None = None) -> dict:
    """Torre: días extra de cortesía (marcha blanca / soporte)."""
    dias = max(1, min(365, int(dias)))
    r = stores.planes_academia.get(academia_id)
    if r is None:
        if not a:
            raise ValueError("Academia sin plan registrado.")
        r = asegurar(a)
    ahora = _ahora()
    base = max([d for d in (vence(r), ahora) if d])
    r["hasta"] = (base + timedelta(days=dias)).isoformat()
    r.setdefault("cortesias", []).append({"dias": dias, "en": ahora.isoformat()})
    return {"ok": True, "hasta": r["hasta"]}


def _avisar_dueno(r: dict, titulo: str, cuerpo: str, clave: str) -> None:
    dueno = r.get("dueno") or ""
    if not dueno:
        return
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(dueno, titulo, cuerpo, tipo="academia")
    except Exception:  # noqa: BLE001
        pass
    try:
        import correos
        correos.encolar("aviso", datos={"para": dueno, "clave": clave, "titulo": titulo, "intro": cuerpo,
                                         "boton": ["Ver mi Plan Academia", "/anfitrion/academia/plan"],
                                         "etiqueta": "Plan Academia"})
    except Exception:  # noqa: BLE001
        pass


def procesar(ahora: datetime | None = None, academias: list[dict] | None = None) -> dict:
    """Cron horario: (1) arranca la prueba de las academias que aún no tienen
    registro, (2) renueva desde el saldo a las que ya pagaron alguna vez y
    tienen la renovación prendida, (3) avisa al dueño antes y al vencer."""
    ahora = ahora or _ahora()
    if not es_suscripcion():
        return {"ok": True, "modelo": modelo()}
    if academias is None:
        try:
            from web import datos
            academias = datos.academias_publicas()
        except Exception:  # noqa: BLE001
            academias = []
    renovadas, avisos = 0, 0
    hoy = _hoy_lima(ahora)
    for a in academias or []:
        if not a.get("id") or not a.get("dueno"):
            continue
        r = asegurar(a, ahora)
        v = vence(r)
        if v and v <= ahora and r.get("pagado") and r.get("auto_renovar", True):
            res = pagar(a, r["dueno"], ahora, automatico=True)
            if res.get("ok"):
                renovadas += 1
                sim = SIMBOLO.get(r.get("moneda") or "PEN", "S/")
                _avisar_dueno(r, "Plan Academia renovado ✅",
                              f"Renovamos el plan de {r.get('nombre')} con tu saldo ({sim} {precio_centimos(r.get('moneda') or 'PEN') / 100:.2f}). "
                              f"Vigente hasta el {fecha_txt(r['hasta'])}.", f"plan_renovado:{r['academia_id']}:{r['hasta'][:10]}")
                continue
        v = vence(r)
        if not v:
            continue
        dias = (v.astimezone(timezone(timedelta(hours=-5))).date() - hoy).days
        en_prueba = not r.get("pagado")
        etapa = None
        if dias < 0:
            etapa = "vencido"
        elif dias in AVISO_DIAS:
            etapa = f"d{dias}"
        if not etapa:
            continue
        clave = f"{etapa}:{v.date().isoformat()}"
        if clave in (r.get("avisos") or {}):
            continue
        if etapa == "vencido" and (hoy - v.astimezone(timezone(timedelta(hours=-5))).date()).days > 7:
            r.setdefault("avisos", {})[clave] = ahora.isoformat()
            continue  # vencida hace mucho: no se insiste
        sim = SIMBOLO.get(r.get("moneda") or "PEN", "S/")
        precio = f"{sim} {precio_centimos(r.get('moneda') or 'PEN') / 100:.2f}"
        nombre = r.get("nombre") or "tu academia"
        renueva = r.get("pagado") and r.get("auto_renovar", True)
        if etapa == "vencido":
            titulo = "Tu Plan Academia venció"
            cuerpo = (f"{nombre} quedó solo con su ficha pública: sin matrículas nuevas ni recordatorios a tus alumnos. "
                      f"Reactívalo por {precio} al mes con tu saldo.")
        else:
            cuando = "hoy" if dias == 0 else ("mañana" if dias == 1 else f"en {dias} días")
            que = "Tu prueba gratis" if en_prueba else "Tu Plan Academia"
            if renueva:
                cuerpo = (f"{que} de {nombre} vence {cuando}. Lo renovaremos con tu saldo ({precio}); "
                          f"asegúrate de tener saldo suficiente.")
            else:
                cuerpo = (f"{que} de {nombre} vence {cuando}. Para seguir con los recordatorios automáticos a tus alumnos y "
                          f"las matrículas en línea, activa el plan por {precio} al mes.")
            titulo = f"{que} vence {cuando}"
        _avisar_dueno(r, titulo, cuerpo, f"plan:{r['academia_id']}:{clave}")
        r.setdefault("avisos", {})[clave] = ahora.isoformat()
        for d in AVISO_DIAS:  # al avisar una etapa, las anteriores quedan cubiertas
            if d > dias:
                r["avisos"].setdefault(f"d{d}:{v.date().isoformat()}", ahora.isoformat())
        avisos += 1
    return {"ok": True, "renovadas": renovadas, "avisos": avisos}


# ── Pago directo a la academia (código de seguridad de Yape) ─────────────────

def cobro_directo(a: dict | None) -> dict | None:
    """{yape, titular} si la academia registró su Yape (número peruano válido)."""
    if not a:
        return None
    cd = a.get("cobroDirecto") or {}
    if not isinstance(cd, dict):
        return None
    yape = re.sub(r"\D", "", str(cd.get("yape") or ""))
    if not re.fullmatch(r"9\d{8}", yape):
        return None
    return {"yape": yape, "titular": str(cd.get("titular") or "").strip()[:60]}


def validar_cobro_directo(cd: dict | None) -> dict:
    """Valida lo que el dueño escribe en su editor. {} = sin Yape (permitido)."""
    if not cd:
        return {}
    yape = re.sub(r"\D", "", str(cd.get("yape") or ""))
    titular = re.sub(r"\s+", " ", str(cd.get("titular") or "")).strip()[:60]
    if not yape and not titular:
        return {}
    if not re.fullmatch(r"9\d{8}", yape):
        raise ValueError("El Yape debe ser un celular peruano de 9 dígitos que empiece con 9.")
    if len(titular) < 3:
        raise ValueError("Escribe el nombre que sale en tu Yape (así lo reconocen tus alumnos).")
    return {"yape": yape, "titular": titular}


def _es_del_alumno(m: dict, email: str) -> bool:
    email = (email or "").strip().lower()
    return bool(email) and email in (str(m.get("email") or "").strip().lower(),
                                     str(m.get("emailAlumno") or "").strip().lower())


def _sim_de(a: dict) -> str:
    return SIMBOLO.get(moneda_de(a), "S/")


def reportar_pago(alumno_id: str, email: str, cuota_ids: list[str], codigo: str, operacion: str = "",
                  ahora: datetime | None = None) -> dict:
    """El alumno (o quien paga) avisa que YAPEÓ a la academia: las cuotas
    quedan "por confirmar" con el código de seguridad (3 dígitos) y el N.º de
    operación. Pichangol no toca la plata: la academia confirma."""
    from web import datos
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    codigo = re.sub(r"\D", "", str(codigo or ""))
    operacion = re.sub(r"[^0-9A-Za-z-]", "", str(operacion or ""))[:20]
    ids = [str(c) for c in (cuota_ids or []) if str(c).strip()][:24]
    if not re.fullmatch(r"\d{3}", codigo):
        return {"ok": False, "error": "codigo", "mensaje": "Escribe los 3 dígitos del código de seguridad que sale en tu Yape."}
    if not ids:
        return {"ok": False, "error": "cuotas", "mensaje": "Elige qué cuota pagaste."}
    m0 = datos.matricula(alumno_id)
    if not m0 or not _es_del_alumno(m0, email):
        return {"ok": False, "error": "no_encontrado", "mensaje": "No encontramos esa matrícula en tu cuenta."}
    a = datos.academia(m0.get("academiaId") or "")
    if not a:
        return {"ok": False, "error": "academia", "mensaje": "La academia ya no está disponible."}
    sim = _sim_de(a)

    def fn(data: dict):
        hechas = []
        for c in data.get("cuotas") or []:
            if not isinstance(c, dict) or str(c.get("id") or "") not in ids:
                continue
            if c.get("pagada"):
                continue
            rep = c.get("reporte") or {}
            if rep.get("estado") == "por_confirmar":
                continue
            c["reporte"] = {"codigo": codigo, "operacion": operacion, "monto": float(c.get("monto") or 0),
                            "fecha": ahora.isoformat(), "por": email, "estado": "por_confirmar", "medio": "yape"}
            hechas.append(dict(c))
        return hechas or None

    hechas = datos.mutar_matricula(alumno_id, fn)
    if not hechas:
        return {"ok": False, "error": "nada", "mensaje": "Esas cuotas ya están pagadas o esperando confirmación."}
    total = sum(float(c.get("monto") or 0) for c in hechas)
    dueno = str(a.get("dueno") or "").strip().lower()
    if dueno:
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(dueno, "Pago por confirmar 💜",
                                f"{m0.get('nombre') or 'Un alumno'} dice que te yapeó {sim} {total:.2f} · código {codigo}. "
                                f"Compáralo con tu Yape y confírmalo.", tipo="academia")
        except Exception:  # noqa: BLE001
            pass
    if dueno:
        # Fase 2: si la academia tiene la confirmación automática, la
        # notificación de su Yape quizá ya llegó → se concilia al instante.
        try:
            import yape_auto
            yape_auto.conciliar_en_segundo_plano(dueno)
        except Exception:  # noqa: BLE001
            pass
    print(f"[pago-directo] {alumno_id} reporta {len(hechas)} cuota(s) {sim} {total:.2f} cód {codigo}", flush=True)
    return {"ok": True, "cuotas": [c["id"] for c in hechas], "total": total}


def resolver_pago(academia_id: str, alumno_id: str, cuota_ids: list[str], email: str, aceptar: bool,
                  motivo: str = "", ahora: datetime | None = None, *, auto: bool = False) -> dict:
    """La ACADEMIA confirma (la cuota queda pagada, `operacionId` = el N.º de
    operación de Yape) o rechaza (vuelve a pendiente con el motivo)."""
    from web import datos
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    a = datos.academia(academia_id)
    if not a or str(a.get("dueno") or "").strip().lower() != email:
        return {"ok": False, "error": "no_dueno", "mensaje": "Solo la academia puede confirmar sus pagos."}
    ids = [str(c) for c in (cuota_ids or []) if str(c).strip()]
    motivo = re.sub(r"\s+", " ", str(motivo or "")).strip()[:120]

    def fn(data: dict):
        hechas = []
        for c in data.get("cuotas") or []:
            if not isinstance(c, dict) or (ids and str(c.get("id") or "") not in ids):
                continue
            rep = c.get("reporte") or {}
            if rep.get("estado") != "por_confirmar" or c.get("pagada"):
                continue
            if aceptar:
                c["pagada"] = True
                c["fechaPago"] = ahora.astimezone(timezone(timedelta(hours=-5))).replace(tzinfo=None).isoformat()
                op = rep.get("operacion") or ""
                c["operacionId"] = f"yape:{op}" if op else f"yape-cod:{rep.get('codigo') or ''}"
                c["medioPago"] = "yape_directo"
                rep["estado"] = "confirmado"
            else:
                rep["estado"] = "rechazado"
                rep["motivo"] = motivo or "La academia no encontró ese yapeo."
            rep["resuelto"] = ahora.isoformat()
            rep["resuelto_por"] = email
            if auto:
                # Fase 2: lo confirmó la notificación de Yape del celular de
                # la academia (`yape_auto.py`), no un toque del dueño.
                rep["auto"] = "yape_notificacion"
            c["reporte"] = rep
            hechas.append(dict(c))
        return (hechas, data) if hechas else None

    res = datos.mutar_matricula(alumno_id, fn, academia_id=academia_id)
    if not res:
        return {"ok": False, "error": "nada", "mensaje": "Ese pago ya fue resuelto."}
    hechas, data = res
    sim = _sim_de(a)
    total = sum(float(c.get("monto") or 0) for c in hechas)
    destinos = {str(data.get("email") or "").strip().lower(), str(data.get("emailAlumno") or "").strip().lower()} - {""}
    nombre_a = a.get("nombre") or "la academia"
    if aceptar and auto:
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(email, "Pago confirmado solo ✅",
                                f"Tu Yape recibió {sim} {total:.2f} de {data.get('nombre') or 'un alumno'} con el código "
                                f"{(hechas[0].get('reporte') or {}).get('codigo') or ''}: lo marcamos como pagado.",
                                tipo="academia")
        except Exception:  # noqa: BLE001
            pass
    if aceptar:
        titulo, cuerpo = ("Pago confirmado ✅",
                          f"{nombre_a} confirmó tu pago de {sim} {total:.2f} ({', '.join(str(c.get('concepto') or '') for c in hechas)[:120]}).")
    else:
        titulo, cuerpo = ("Pago no confirmado",
                          f"{nombre_a} no encontró tu yapeo de {sim} {total:.2f}: {motivo or 'revisa el código de seguridad'}. "
                          f"Vuelve a reportarlo o escríbele a la academia.")
    for d in destinos:
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(d, titulo, cuerpo, tipo="academia")
        except Exception:  # noqa: BLE001
            pass
        if aceptar:
            try:
                import correos
                correos.encolar("aviso", datos={
                    "para": d, "clave": f"pago_directo:{alumno_id}:{','.join(c['id'] for c in hechas)}:{d}",
                    "titulo": f"Recibo de pago · {nombre_a}", "intro": cuerpo,
                    "datos": [["Academia", nombre_a], ["Alumno", str(data.get("nombre") or "")],
                              ["Medio", "Yape directo a la academia"],
                              ["N.º de operación", ", ".join(sorted({str((c.get('reporte') or {}).get('operacion') or (c.get('reporte') or {}).get('codigo') or '') for c in hechas}))]],
                    "lineas": [[str(c.get("concepto") or "Cuota"), f"{sim} {float(c.get('monto') or 0):.2f}"] for c in hechas],
                    "total": ["Total pagado", f"{sim} {total:.2f}"],
                    "boton": ["Ver mis clases", "/mis-clases"], "etiqueta": "Recibo",
                    "nota": f"Pagaste directo a {nombre_a}. Pichangol solo registra el pago y te lo recuerda."})
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True, "cuotas": [c["id"] for c in hechas], "aceptado": bool(aceptar), "total": total}


def por_confirmar(academias: list[dict]) -> list[dict]:
    """Pagos reportados por los alumnos que la academia aún no confirma."""
    from web import datos
    por_id = {str(a.get("id")): a for a in academias if a.get("id")}
    if not por_id:
        return []
    out = []
    for m in datos.matriculas_de_academias(list(por_id)):
        a = por_id.get(str(m.get("academiaId")))
        if not a:
            continue
        grupo: dict[str, dict] = {}
        for c in m.get("cuotas") or []:
            rep = (c or {}).get("reporte") or {}
            if not isinstance(c, dict) or c.get("pagada") or rep.get("estado") != "por_confirmar":
                continue
            k = f"{rep.get('codigo')}|{rep.get('operacion')}|{str(rep.get('fecha') or '')[:16]}"
            g = grupo.setdefault(k, {"academia_id": a["id"], "academia": a.get("nombre") or "", "alumno_id": m.get("id"),
                                     "alumno": m.get("nombre") or "", "pagador": rep.get("por") or m.get("email") or "",
                                     "codigo": rep.get("codigo") or "", "operacion": rep.get("operacion") or "",
                                     "fecha": rep.get("fecha") or "", "simbolo": _sim_de(a), "cuotas": [], "total": 0.0})
            g["cuotas"].append({"id": c.get("id"), "concepto": c.get("concepto") or "", "monto": float(c.get("monto") or 0)})
            g["total"] = round(g["total"] + float(c.get("monto") or 0), 2)
        out.extend(grupo.values())
    out.sort(key=lambda x: x["fecha"], reverse=True)
    return out


# ── Recordatorios a los alumnos (beneficio del plan) ─────────────────────────

ETAPAS_ALUMNO = {"antes": 3, "hoy": 0, "vencida": -1}


def _venc_dia(c: dict) -> date | None:
    s = str(c.get("vencimiento") or "")
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def recordatorios_alumnos(ahora: datetime | None = None, academias: list[dict] | None = None) -> dict:
    """Push + correo al alumno / apoderado: 3 días antes, el día y al día
    siguiente de vencer cada cuota pendiente. Solo academias con el plan
    vigente; desde las 9:00 de Lima; una vez por etapa."""
    from web import datos
    ahora = ahora or _ahora()
    if (ahora - timedelta(hours=5)).hour < 9:
        return {"ok": True, "enviados": 0, "motivo": "temprano"}
    hoy = _hoy_lima(ahora)
    if academias is None:
        academias = datos.academias_publicas()
    vigentes = {str(a["id"]): a for a in academias or [] if a.get("id") and beneficios(a)}
    if not vigentes:
        return {"ok": True, "enviados": 0}
    enviados = 0
    for m in datos.matriculas_de_academias(list(vigentes)):
        a = vigentes.get(str(m.get("academiaId")))
        if not a:
            continue
        sim = _sim_de(a)
        cd = cobro_directo(a)
        destinos = {str(m.get("email") or "").strip().lower(), str(m.get("emailAlumno") or "").strip().lower()} - {""}
        if not destinos:
            continue
        for c in m.get("cuotas") or []:
            if not isinstance(c, dict) or c.get("pagada") or c.get("autoDebito"):
                continue
            if ((c.get("reporte") or {}).get("estado")) == "por_confirmar":
                continue
            d = _venc_dia(c)
            if not d:
                continue
            falta = (d - hoy).days
            etapa = next((e for e, n in ETAPAS_ALUMNO.items() if n == falta), None)
            if not etapa:
                continue
            k = f"{m.get('id')}|{c.get('id')}"
            hechas = stores.recordatorios_cuotas.setdefault(k, [])
            if etapa in hechas:
                continue
            monto = float(c.get("monto") or 0)
            concepto = str(c.get("concepto") or "tu mensualidad")
            como = (f" Yapea a {cd['titular']} ({cd['yape'][:3]} {cd['yape'][3:6]} {cd['yape'][6:]}) y reporta el código de seguridad en Pichangol."
                    if cd else " Coordina el pago con la academia.")
            if etapa == "antes":
                titulo = f"Tu cuota de {a.get('nombre')} vence en 3 días"
                cuerpo = f"{m.get('nombre')}: {concepto} · {sim} {monto:.2f} vence el {d.day}/{d.month}.{como}"
            elif etapa == "hoy":
                titulo = f"Hoy vence tu cuota de {a.get('nombre')}"
                cuerpo = f"{m.get('nombre')}: {concepto} · {sim} {monto:.2f}.{como}"
            else:
                titulo = f"Tu cuota de {a.get('nombre')} está vencida"
                cuerpo = f"{m.get('nombre')}: {concepto} · {sim} {monto:.2f} venció ayer.{como}"
            for dest in destinos:
                try:
                    from pagos.router import _aviso_push_usuario
                    _aviso_push_usuario(dest, titulo, cuerpo, tipo="academia")
                except Exception:  # noqa: BLE001
                    pass
                try:
                    import correos
                    datos_c = [["Academia", str(a.get("nombre") or "")], ["Alumno", str(m.get("nombre") or "")],
                               ["Vence", f"{d.day}/{d.month}/{d.year}"]]
                    if cd:
                        datos_c.append(["Yape de la academia", f"{cd['yape']} · {cd['titular']}"])
                    correos.encolar("aviso", datos={
                        "para": dest, "clave": f"recordatorio:{k}:{etapa}:{dest}", "titulo": titulo, "intro": cuerpo,
                        "datos": datos_c, "lineas": [[concepto, f"{sim} {monto:.2f}"]],
                        "boton": ["Pagar mi cuota", "/mis-clases"], "etiqueta": "Recordatorio de pago"})
                except Exception:  # noqa: BLE001
                    pass
            hechas.append(etapa)
            enviados += 1
    return {"ok": True, "enviados": enviados}


# ── API (APK) ─────────────────────────────────────────────────────────────────

def _deps():
    from fastapi import Depends
    from pagos.router import _require_app_key
    return [Depends(_require_app_key)]


def _req_usuario(email: str, token: str | None) -> None:
    from pagos.router import _require_usuario
    _require_usuario(email, token)


def _academia_o_404(academia_id: str) -> dict:
    from web import datos
    a = datos.academia(academia_id)
    if not a:
        raise HTTPException(status_code=404, detail="academia_no_encontrada")
    a.setdefault("id", academia_id)
    return a


@router.get("/config/academias")
def get_config_academias() -> dict:
    """Público: modelo de cobro de academias y precio del plan por moneda."""
    return config_publica()


@router.get("/academias/plan/{academia_id}", dependencies=_deps())
def get_plan(academia_id: str) -> dict:
    a = _academia_o_404(academia_id)
    est = estado(a)
    est["cobro_directo"] = cobro_directo(a)
    return est


class PlanPagarReq(BaseModel):
    email: str


@router.post("/academias/plan/{academia_id}/pagar", dependencies=_deps())
def post_plan_pagar(academia_id: str, req: PlanPagarReq, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(req.email, x_user_token)
    return pagar(_academia_o_404(academia_id), req.email)


class PlanRenovacionReq(BaseModel):
    email: str
    renovar: bool


@router.post("/academias/plan/{academia_id}/renovacion", dependencies=_deps())
def post_plan_renovacion(academia_id: str, req: PlanRenovacionReq, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(req.email, x_user_token)
    return cambiar_renovacion(_academia_o_404(academia_id), req.email, req.renovar)


class ReportarReq(BaseModel):
    alumno_id: str
    email: str
    cuota_ids: list[str]
    codigo: str
    operacion: str = ""


@router.post("/academias/pago-directo/reportar", dependencies=_deps())
def post_reportar(req: ReportarReq, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(req.email, x_user_token)
    return reportar_pago(req.alumno_id, req.email, req.cuota_ids, req.codigo, req.operacion)


class ResolverReq(BaseModel):
    academia_id: str
    alumno_id: str
    email: str
    cuota_ids: list[str] = []
    aceptar: bool
    motivo: str = ""


@router.post("/academias/pago-directo/resolver", dependencies=_deps())
def post_resolver(req: ResolverReq, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(req.email, x_user_token)
    return resolver_pago(req.academia_id, req.alumno_id, req.cuota_ids, req.email, req.aceptar, req.motivo)


@router.get("/academias/pago-directo/pendientes", dependencies=_deps())
def get_pendientes(email: str, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(email, x_user_token)
    from web import datos
    acads = datos.academias_de_dueno(email)
    for a in acads:
        a.setdefault("dueno", email.strip().lower())
    return {"pagos": por_confirmar(acads)}
