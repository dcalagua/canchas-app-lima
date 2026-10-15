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

2-bis. **Pago directo por QR con MONTO ÚNICO** (Ecuador y Bolivia, pedido
   del director, 12-oct-2026: "el usuario escanea el código, paga, le llega al
   dueño y el sistema lo registra automáticamente"): la academia sube la
   imagen de su QR de cobro y elige su app (`cobroDirecto = {tipo: qr,
   qr_url, app, titular}`). Al pagar, Pichangol crea una INTENCIÓN
   (`stores.qr_intenciones`) con un monto único = lo que debe + unos centavos
   que nadie más está usando con esa academia (p. ej. $ 30.00 → $ 30.03). El
   celular de la academia lee la notificación de SU app de cobros
   (`yape_auto.py`, paquete elegido por el dueño) y, si el monto calza con UNA
   sola intención viva, la cuota queda pagada sola. Sin el celular vinculado,
   el alumno toca "Ya pagué" y la academia confirma a mano.

3. **Recordatorios a los alumnos** (beneficio del plan): push + correo 3 días
   antes del vencimiento de cada cuota, el día y al vencer. Una vez por etapa
   (`stores.recordatorios_cuotas`).

Las MISMAS funciones las usan la web y el APK (endpoints `/academias/*`).
"""
from __future__ import annotations

import re
import secrets
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


PAISES = ("PE", "EC", "BO")
NOMBRE_PAIS = {"PE": "Perú", "EC": "Ecuador", "BO": "Bolivia"}


def paises_habilitados() -> list[str]:
    """Países donde las academias EXISTEN para el público (decisión del
    director, 10-oct-2026: "ocultamos las academias para Bolivia y Ecuador").
    `acad_paises` en la torre; vacío = ninguno."""
    raw = stores.config.get("acad_paises")
    raw = "PE" if raw is None else str(raw)
    return [p for p in PAISES if p in {x.strip().upper() for x in raw.split(",")}]


def pais_habilitado(iso: str) -> bool:
    return (iso or "").strip().upper() in paises_habilitados()


def pais_de(a: dict | None) -> str:
    """País de la academia = el de su sede (por la moneda que ya resuelve la
    ficha: coordenadas de la sede o moneda congelada)."""
    return pais_de_moneda(moneda_de(a or {}))


def habilitada(a: dict | None) -> bool:
    """¿Esta academia se muestra al público y acepta matrículas?"""
    return bool(a) and pais_habilitado(pais_de(a))


def config_publica() -> dict:
    return {"modelo": modelo(), "prueba_dias": prueba_dias(), "periodo_dias": DIAS_PERIODO,
            "precios": {m: precio_centimos(m) / 100.0 for m in MONEDAS},
            "simbolos": dict(SIMBOLO), "paises": paises_habilitados(),
            "qr_apps": {p: [{"clave": k, "nombre": n} for k, n in apps] for p, apps in QR_APPS.items()},
            "qr_vida_horas": qr_vida_horas()}


def set_config(*, modelo_nuevo: str | None = None, precios: dict | None = None,
               prueba: int | None = None, paises: list | None = None) -> dict:
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
    if paises is not None:
        lista = [str(x).strip().upper() for x in (paises if isinstance(paises, list) else str(paises).split(","))]
        malos = [x for x in lista if x and x not in PAISES]
        if malos:
            raise ValueError("País no válido: " + ", ".join(malos))
        stores.config["acad_paises"] = ",".join(p for p in PAISES if p in lista)
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
    try:
        vencer_qr(ahora)
    except Exception as ex:  # noqa: BLE001
        print(f"[pago-qr] vencer falló: {ex}", flush=True)
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

# Apps donde la academia recibe pagos por QR (selección, sin texto libre).
QR_APPS: dict[str, list[tuple[str, str]]] = {
    "EC": [("deuna", "DeUna!"), ("pichincha", "Banco Pichincha"), ("guayaquil", "Banco Guayaquil"),
           ("pacifico", "Banco del Pacífico"), ("produbanco", "Produbanco"), ("cooperativa", "Cooperativa"),
           ("otro", "Otro banco")],
    "BO": [("simple", "QR Simple (cualquier banco)"), ("bnb", "BNB"), ("bmsc", "Banco Mercantil Santa Cruz"),
           ("bcp", "BCP Bolivia"), ("union", "Banco Unión"), ("ganadero", "Banco Ganadero"), ("bisa", "Banco BISA"),
           ("fie", "Banco FIE"), ("otro", "Otro banco")],
}


def medio_cobro_de_pais(pais: str) -> str:
    """Perú cobra por Yape (código de seguridad); Ecuador y Bolivia por QR."""
    return "yape" if (pais or "PE") == "PE" else "qr"


def _app_nombre(pais: str, app: str) -> str:
    return next((n for k, n in QR_APPS.get(pais, []) if k == app), "")


def _qr_url_valida(url: str) -> bool:
    """Imagen subida a NUESTRO Storage (nunca un enlace de afuera)."""
    url = str(url or "").strip()
    if not url.startswith("https://") or "/storage/v1/object/public/" not in url or len(url) > 400:
        return False
    import config
    base = str(getattr(config, "SUPABASE_URL", "") or "").strip()
    if base:
        host = re.sub(r"^https?://", "", base).split("/")[0]
        return url.startswith(f"https://{host}/")
    return True


def cobro_directo(a: dict | None) -> dict | None:
    """Cómo le pagan los alumnos DIRECTO a la academia, según su país:
    · Perú → {tipo: yape, yape, titular} (número peruano válido).
    · Ecuador / Bolivia → {tipo: qr, qr_url, app, app_nombre, titular}.
    None si no registró nada válido."""
    if not a:
        return None
    cd = a.get("cobroDirecto") or {}
    if not isinstance(cd, dict):
        return None
    pais = pais_de(a)
    titular = str(cd.get("titular") or "").strip()[:60]
    if medio_cobro_de_pais(pais) == "yape":
        yape = re.sub(r"\D", "", str(cd.get("yape") or ""))
        if not re.fullmatch(r"9\d{8}", yape):
            return None
        out = {"tipo": "yape", "yape": yape, "titular": titular}
        # QR de Yape/Plin OPCIONAL: el alumno lo escanea en vez de tipear el número.
        if _qr_url_valida(cd.get("qr_url")):
            out["qr_url"] = str(cd["qr_url"]).strip()
        return out
    app = str(cd.get("app") or "")
    if not _qr_url_valida(cd.get("qr_url")) or not _app_nombre(pais, app) or len(titular) < 3:
        return None
    return {"tipo": "qr", "qr_url": str(cd["qr_url"]).strip(), "app": app, "app_nombre": _app_nombre(pais, app),
            "titular": titular}


def validar_cobro_directo(cd: dict | None, pais: str = "PE") -> dict:
    """Valida lo que el dueño registra en su editor (web o APK) según el país
    de la sede. {} = sin cobro directo (permitido: coordina por WhatsApp)."""
    if not cd:
        return {}
    titular = re.sub(r"\s+", " ", str(cd.get("titular") or "")).strip()[:60]
    if medio_cobro_de_pais(pais) == "yape":
        yape = re.sub(r"\D", "", str(cd.get("yape") or ""))
        if not yape and not titular:
            return {}
        if not re.fullmatch(r"9\d{8}", yape):
            raise ValueError("El Yape debe ser un celular peruano de 9 dígitos que empiece con 9.")
        if len(titular) < 3:
            raise ValueError("Escribe el nombre que sale en tu Yape (así lo reconocen tus alumnos).")
        qr_url = str(cd.get("qr_url") or "").strip()
        if qr_url and not _qr_url_valida(qr_url):
            raise ValueError("Vuelve a subir la imagen de tu QR de Yape.")
        return {"yape": yape, "titular": titular, **({"qr_url": qr_url} if qr_url else {})}
    qr_url = str(cd.get("qr_url") or "").strip()
    app = str(cd.get("app") or "")
    if not qr_url and not app and not titular:
        return {}
    if not _qr_url_valida(qr_url):
        raise ValueError("Sube la imagen de tu código QR de cobro.")
    if not _app_nombre(pais, app):
        raise ValueError("Elige la app o banco donde recibes los pagos.")
    if len(titular) < 3:
        raise ValueError("Escribe el nombre del titular como sale al escanear tu QR (así lo reconocen tus alumnos).")
    return {"tipo": "qr", "qr_url": qr_url, "app": app, "titular": titular}


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
    cd = cobro_directo(a)
    if cd and cd.get("tipo") == "qr":
        return {"ok": False, "error": "usa_qr", "mensaje": "Esta academia cobra por QR: toca «Pagar con QR»."}
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
                  motivo: str = "", ahora: datetime | None = None, *, auto: bool = False,
                  intencion: str = "", silencioso: bool = False) -> dict:
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
            if rep.get("estado") not in ("por_confirmar", "esperando_pago") or c.get("pagada"):
                continue
            if intencion and rep.get("intencion") != intencion:
                continue
            if aceptar:
                c["pagada"] = True
                c["fechaPago"] = ahora.astimezone(timezone(timedelta(hours=-5))).replace(tzinfo=None).isoformat()
                if rep.get("medio") == "qr":
                    c["operacionId"] = f"qr:{rep.get('intencion') or ''}"
                    c["medioPago"] = "qr_directo"
                else:
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
                # Fase 2: lo confirmó la notificación de la app de cobros del
                # celular de la academia (`yape_auto.py`), no un toque del dueño.
                rep["auto"] = "qr_notificacion" if rep.get("medio") == "qr" else "yape_notificacion"
            c["reporte"] = rep
            hechas.append(dict(c))
        return (hechas, data) if hechas else None

    res = datos.mutar_matricula(alumno_id, fn, academia_id=academia_id)
    if not res:
        return {"ok": False, "error": "nada", "mensaje": "Ese pago ya fue resuelto."}
    hechas, data = res
    sim = _sim_de(a)
    total = sum(float(c.get("monto") or 0) for c in hechas)
    es_qr = any((c.get("reporte") or {}).get("medio") == "qr" for c in hechas)
    for iid in {str((c.get("reporte") or {}).get("intencion") or "") for c in hechas} - {""}:
        _cerrar_intencion(iid, "confirmado" if aceptar else "rechazado", ahora)
    if silencioso:
        # Una intención con varias personas avisa una sola vez (confirmar_qr).
        return {"ok": True, "cuotas": [c["id"] for c in hechas], "aceptado": bool(aceptar), "total": total,
                "data": data, "hechas": hechas}
    if aceptar and auto and not es_qr:
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(email, "Pago confirmado solo ✅",
                                f"Tu Yape recibió {sim} {total:.2f} de {data.get('nombre') or 'un alumno'} con el código "
                                f"{(hechas[0].get('reporte') or {}).get('codigo') or ''}: lo marcamos como pagado.",
                                tipo="academia")
        except Exception:  # noqa: BLE001
            pass
    _avisar_resultado(a, data, hechas, aceptar, motivo, alumno_id)
    return {"ok": True, "cuotas": [c["id"] for c in hechas], "aceptado": bool(aceptar), "total": total}


def _avisar_resultado(a: dict, data: dict, hechas: list[dict], aceptar: bool, motivo: str, alumno_id: str) -> None:
    """Push + recibo por correo a quien pagó y al alumno con correo propio."""
    from web import datos  # noqa: F401
    sim = _sim_de(a)
    total = sum(float(c.get("monto") or 0) for c in hechas)
    es_qr = any((c.get("reporte") or {}).get("medio") == "qr" for c in hechas)
    destinos = {str(data.get("email") or "").strip().lower(), str(data.get("emailAlumno") or "").strip().lower()} - {""}
    nombre_a = a.get("nombre") or "la academia"
    # En QR se pagó el MONTO ÚNICO (cuota + centavos de identificación).
    pagado = round(sum(float((c.get("reporte") or {}).get("pagado") or 0) for c in hechas), 2) if es_qr else 0.0
    if es_qr and pagado <= 0:
        intenciones = {str((c.get("reporte") or {}).get("intencion") or "") for c in hechas} - {""}
        pagado = round(sum((stores.qr_intenciones.get(i) or {}).get("monto_c", 0) for i in intenciones) / 100.0, 2)
    extra = round(pagado - total, 2) if es_qr and pagado > total else 0.0
    if aceptar:
        titulo, cuerpo = ("Pago confirmado ✅",
                          f"{nombre_a} confirmó tu pago de {sim} {total:.2f} ({', '.join(str(c.get('concepto') or '') for c in hechas)[:120]}).")
    else:
        titulo, cuerpo = ("Pago no confirmado",
                          f"{nombre_a} no encontró tu {'pago' if es_qr else 'yapeo'} de {sim} {total:.2f}: "
                          f"{motivo or ('revisa el monto que pagaste' if es_qr else 'revisa el código de seguridad')}. "
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
                              ["Medio", ("QR directo a la academia" if es_qr else "Yape directo a la academia")],
                              ["N.º de operación", ", ".join(sorted({str((c.get('reporte') or {}).get('intencion') or (c.get('reporte') or {}).get('operacion') or (c.get('reporte') or {}).get('codigo') or '') for c in hechas}))]],
                    "lineas": [[str(c.get("concepto") or "Cuota"), f"{sim} {float(c.get('monto') or 0):.2f}"] for c in hechas]
                              + ([["Centavos de identificación del pago", f"{sim} {extra:.2f}"]] if extra > 0 else []),
                    "total": ["Total pagado", f"{sim} {(total + extra):.2f}"],
                    "boton": ["Ver mis clases", "/mis-clases"], "etiqueta": "Recibo",
                    "nota": f"Pagaste directo a {nombre_a}. Pichangol solo registra el pago y te lo recuerda."})
            except Exception:  # noqa: BLE001
                pass


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
            k = (f"qr|{rep.get('intencion')}" if rep.get("medio") == "qr"
                 else f"{rep.get('codigo')}|{rep.get('operacion')}|{str(rep.get('fecha') or '')[:16]}")
            g = grupo.setdefault(k, {"academia_id": a["id"], "academia": a.get("nombre") or "", "alumno_id": m.get("id"),
                                     "alumno": m.get("nombre") or "", "pagador": rep.get("por") or m.get("email") or "",
                                     "codigo": rep.get("codigo") or "", "operacion": rep.get("operacion") or "",
                                     "fecha": rep.get("fecha") or "", "simbolo": _sim_de(a), "cuotas": [], "total": 0.0,
                                     "medio": rep.get("medio") or "yape", "intencion": rep.get("intencion") or "",
                                     "monto_unico": rep.get("pagado") or None})
            g["cuotas"].append({"id": c.get("id"), "concepto": c.get("concepto") or "", "monto": float(c.get("monto") or 0)})
            g["total"] = round(g["total"] + float(c.get("monto") or 0), 2)
        out.extend(grupo.values())
    out.sort(key=lambda x: x["fecha"], reverse=True)
    return out


# ── Pago por QR con MONTO ÚNICO (Ecuador y Bolivia) ─────────────────────────

QR_VIDA_HORAS = 48        # una intención sin pagar vence y libera sus centavos
QR_CENTIMOS_MAX = 49      # centavos de identificación: 0.01 … 0.49
QR_VIVAS = ("esperando", "reportado")


def _cfg_int(clave: str, defecto: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(stores.config.get(clave) or defecto))))
    except (TypeError, ValueError):
        return defecto


def qr_vida_horas() -> int:
    return _cfg_int("qr_vida_horas", QR_VIDA_HORAS, 1, 168)


def qr_centimos_max() -> int:
    return _cfg_int("qr_centimos_max", QR_CENTIMOS_MAX, 5, 99)


def _viva(i: dict, ahora: datetime) -> bool:
    if i.get("estado") not in QR_VIVAS:
        return False
    if i.get("estado") == "esperando":
        v = _de_iso(i.get("vence"))
        return bool(v and v > ahora)
    return True  # "Ya pagué": vive hasta que la academia o la notificación lo resuelvan


def _cerrar_intencion(iid: str, estado_nuevo: str, ahora: datetime) -> None:
    with _LOCK:
        i = stores.qr_intenciones.get(iid)
        if i and i.get("estado") in QR_VIVAS:
            i["estado"] = estado_nuevo
            i["cerrada"] = ahora.isoformat()


def _vista_intencion(i: dict, a: dict | None = None) -> dict:
    """Lo que ve el alumno (app y web): QR, app, titular y el monto EXACTO."""
    sim = SIMBOLO.get(i.get("moneda") or "PEN", "S/")
    monto = i["monto_c"] / 100.0
    extra = i.get("extra_c", 0) / 100.0
    return {"id": i["id"], "estado": i.get("estado"), "academia_id": i.get("academia_id"),
            "academia": i.get("academia") or "", "simbolo": sim, "moneda": i.get("moneda"),
            "monto": monto, "monto_txt": f"{sim} {monto:.2f}", "base": i.get("base_c", 0) / 100.0,
            "extra": extra, "extra_txt": f"{sim} {extra:.2f}", "qr_url": i.get("qr_url") or "",
            "app_nombre": i.get("app_nombre") or "", "titular": i.get("titular") or "",
            "vence": i.get("vence"), "creada": i.get("creada"),
            "items": [{"alumno_id": x["alumno_id"], "cuotas": list(x["cuotas"])} for x in i.get("items") or []]}


def vencer_qr(ahora: datetime | None = None) -> int:
    """Intenciones "esperando" pasadas su vida: vencen y sus cuotas vuelven a
    pendientes (sus centavos quedan libres). Las "Ya pagué" no vencen: las
    resuelve la academia."""
    from web import datos
    ahora = ahora or _ahora()
    vencidas = []
    with _LOCK:
        for i in stores.qr_intenciones.values():
            v = _de_iso(i.get("vence"))
            if i.get("estado") == "esperando" and v and v <= ahora:
                i["estado"] = "vencido"
                i["cerrada"] = ahora.isoformat()
                vencidas.append(dict(i))
        # Poda: se guardan 30 días de historia.
        corte = ahora - timedelta(days=30)
        for k in [k for k, i in stores.qr_intenciones.items()
                  if i.get("estado") not in QR_VIVAS and (_de_iso(i.get("cerrada") or i.get("creada")) or ahora) < corte]:
            stores.qr_intenciones.pop(k, None)
    for i in vencidas:
        for x in i.get("items") or []:
            def fn(data: dict, iid=i["id"]):
                cambio = False
                for c in data.get("cuotas") or []:
                    rep = (c or {}).get("reporte") or {}
                    if isinstance(c, dict) and not c.get("pagada") and rep.get("intencion") == iid \
                            and rep.get("estado") == "esperando_pago":
                        c.pop("reporte", None)
                        cambio = True
                return True if cambio else None
            try:
                datos.mutar_matricula(x["alumno_id"], fn)
            except Exception:  # noqa: BLE001
                pass
    return len(vencidas)


def iniciar_pago_qr(email: str, items: list[dict], ahora: datetime | None = None) -> dict:
    """El alumno (o quien paga) elige qué cuotas paga por QR. Crea (o devuelve,
    si ya existe para lo mismo) una intención con MONTO ÚNICO entre las vivas
    del dueño en esa moneda. `items` = [{alumno_id, cuota_ids}] de la MISMA
    academia (pago familiar en un solo QR)."""
    from web import datos
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    items = [x for x in (items or []) if isinstance(x, dict) and str(x.get("alumno_id") or "").strip()][:8]
    if not items:
        return {"ok": False, "error": "cuotas", "mensaje": "Elige qué cuota vas a pagar."}
    vencer_qr(ahora)
    a, pedidos = None, []
    for x in items:
        m = datos.matricula(str(x["alumno_id"]))
        if not m or not _es_del_alumno(m, email):
            return {"ok": False, "error": "no_encontrado", "mensaje": "No encontramos esa matrícula en tu cuenta."}
        aid = str(m.get("academiaId") or "")
        if a is None:
            a = datos.academia(aid)
            if not a:
                return {"ok": False, "error": "academia", "mensaje": "La academia ya no está disponible."}
            a.setdefault("id", aid)
        elif str(a.get("id")) != aid:
            return {"ok": False, "error": "academias", "mensaje": "Paga una academia a la vez: cada una tiene su propio QR."}
        ids = {str(c) for c in (x.get("cuota_ids") or []) if str(c).strip()}
        cuotas = [c for c in m.get("cuotas") or [] if isinstance(c, dict) and str(c.get("id")) in ids and not c.get("pagada")]
        if ids and cuotas:
            pedidos.append((m, cuotas))
    if not pedidos:
        return {"ok": False, "error": "nada", "mensaje": "Esas cuotas ya están pagadas."}
    cd = cobro_directo(a)
    if not cd or cd.get("tipo") != "qr":
        return {"ok": False, "error": "sin_qr", "mensaje": "Esta academia aún no registró su QR de cobro: coordina el pago con ella."}
    dueno = str(a.get("dueno") or "").strip().lower()
    moneda = moneda_de(a)
    clave = sorted(f"{m['id']}:{c['id']}" for m, cs in pedidos for c in cs)
    with _LOCK:
        # Lo MISMO ya tiene una intención viva → se devuelve (doble clic, otra pestaña).
        for i in stores.qr_intenciones.values():
            if _viva(i, ahora) and i.get("clave") == clave and i.get("por") == email:
                return {"ok": True, "intencion": _vista_intencion(i), "reusada": True}
        # Una cuota en otra intención "esperando" → esa se reemplaza (el alumno cambió la selección).
        mias = {k for k in clave}
        for i in stores.qr_intenciones.values():
            if i.get("estado") == "esperando" and mias & set(i.get("clave") or []):
                i["estado"] = "reemplazado"
                i["cerrada"] = ahora.isoformat()
        en_uso = {i["monto_c"] for i in stores.qr_intenciones.values()
                  if i.get("dueno") == dueno and i.get("moneda") == moneda and _viva(i, ahora)}
        base_c = int(round(sum(float(c.get("monto") or 0) for _m, cs in pedidos for c in cs) * 100))
        extra_c = next((x for x in range(1, qr_centimos_max() + 1) if base_c + x not in en_uso), None)
        if extra_c is None:
            return {"ok": False, "error": "ocupado", "mensaje": "La academia tiene muchos pagos en curso: inténtalo en unos minutos."}
        iid = "pq_" + format(int(ahora.timestamp() * 1000), "x") + secrets.token_hex(2)
        i = {"id": iid, "dueno": dueno, "academia_id": a["id"], "academia": a.get("nombre") or "", "moneda": moneda,
             "items": [{"alumno_id": m["id"], "cuotas": [c["id"] for c in cs]} for m, cs in pedidos],
             "clave": clave, "base_c": base_c, "extra_c": extra_c, "monto_c": base_c + extra_c, "por": email,
             "creada": ahora.isoformat(), "vence": (ahora + timedelta(hours=qr_vida_horas())).isoformat(),
             "estado": "esperando", "qr_url": cd["qr_url"], "app_nombre": cd["app_nombre"], "titular": cd["titular"]}
        stores.qr_intenciones[iid] = i
    pagado = (base_c + extra_c) / 100.0
    for m, cs in pedidos:
        ids = {c["id"] for c in cs}

        def fn(data: dict, ids=ids):
            hechas = []
            for c in data.get("cuotas") or []:
                if isinstance(c, dict) and str(c.get("id")) in ids and not c.get("pagada"):
                    c["reporte"] = {"medio": "qr", "estado": "esperando_pago", "intencion": iid,
                                    "monto": float(c.get("monto") or 0), "pagado": pagado, "fecha": ahora.isoformat(),
                                    "por": email, "vence": i["vence"]}
                    hechas.append(c["id"])
            return hechas or None
        datos.mutar_matricula(m["id"], fn)
    print(f"[pago-qr] {iid} {dueno} {moneda} {base_c / 100:.2f} → {pagado:.2f}", flush=True)
    return {"ok": True, "intencion": _vista_intencion(i)}


def _mi_intencion(iid: str, email: str) -> dict | None:
    i = stores.qr_intenciones.get(str(iid or ""))
    if not i:
        return None
    email = (email or "").strip().lower()
    return i if email and email in (i.get("por"), i.get("dueno")) else None


def estado_qr(iid: str, email: str) -> dict:
    i = _mi_intencion(iid, email)
    if not i:
        return {"ok": False, "error": "no_encontrado", "mensaje": "Ese pago ya no existe."}
    if i.get("estado") == "esperando":
        v = _de_iso(i.get("vence"))
        if v and v <= _ahora():
            vencer_qr()
    return {"ok": True, "intencion": _vista_intencion(i)}


def marcar_pagado_qr(iid: str, email: str, ahora: datetime | None = None) -> dict:
    """"Ya pagué": la intención queda reportada y las cuotas "por confirmar"
    (la academia la ve en su lista y puede confirmar a mano si su celular no
    está vinculado). Si la notificación ya llegó, se concilia al instante."""
    from web import datos
    ahora = ahora or _ahora()
    with _LOCK:
        i = _mi_intencion(iid, email)
        if not i or i.get("por") != (email or "").strip().lower():
            return {"ok": False, "error": "no_encontrado", "mensaje": "Ese pago ya no existe."}
        if i.get("estado") not in QR_VIVAS:
            return {"ok": True, "intencion": _vista_intencion(i)}
        i["estado"] = "reportado"
        i["reportada"] = ahora.isoformat()
    for x in i.get("items") or []:
        def fn(data: dict):
            n = 0
            for c in data.get("cuotas") or []:
                rep = (c or {}).get("reporte") or {}
                if isinstance(c, dict) and rep.get("intencion") == iid and rep.get("estado") == "esperando_pago":
                    rep["estado"] = "por_confirmar"
                    rep["reportado"] = ahora.isoformat()
                    n += 1
            return n or None
        datos.mutar_matricula(x["alumno_id"], fn)
    sim = SIMBOLO.get(i.get("moneda") or "PEN", "S/")
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(i["dueno"], "Pago por confirmar 💜",
                            f"Un alumno dice que te pagó {sim} {i['monto_c'] / 100:.2f} por QR. "
                            f"Si tu celular está vinculado se confirma solo; si no, revísalo en tu app de cobros.",
                            tipo="academia")
    except Exception:  # noqa: BLE001
        pass
    try:
        import yape_auto
        yape_auto.conciliar_en_segundo_plano(i["dueno"])
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "intencion": _vista_intencion(i)}


def confirmar_qr(iid: str, ahora: datetime | None = None, *, auto: bool = True) -> dict:
    """La notificación de la app de cobros calzó con esta intención: todas sus
    cuotas quedan pagadas (con el correo del dueño, como si confirmara él)."""
    from web import datos
    ahora = ahora or _ahora()
    i = stores.qr_intenciones.get(iid)
    if not i or i.get("estado") not in QR_VIVAS:
        return {"ok": False, "error": "no_viva"}
    a = datos.academia(i["academia_id"])
    if not a:
        return {"ok": False, "error": "academia"}
    a.setdefault("id", i["academia_id"])
    total, hechas_todas = 0.0, []
    for x in i.get("items") or []:
        r = resolver_pago(i["academia_id"], x["alumno_id"], list(x["cuotas"]), i["dueno"], True,
                          ahora=ahora, auto=auto, intencion=iid, silencioso=True)
        if r.get("ok"):
            total += float(r.get("total") or 0)
            hechas_todas.append((x["alumno_id"], r["data"], r["hechas"]))
    if not hechas_todas:
        return {"ok": False, "error": "nada"}
    _cerrar_intencion(iid, "confirmado", ahora)
    sim = SIMBOLO.get(i.get("moneda") or "PEN", "S/")
    nombres = ", ".join(str(d.get("nombre") or "") for _al, d, _h in hechas_todas)[:80]
    if auto:
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(i["dueno"], "Pago confirmado solo ✅",
                                f"Recibiste {sim} {i['monto_c'] / 100:.2f} por QR de {nombres or 'un alumno'}: "
                                f"lo marcamos como pagado.", tipo="academia")
        except Exception:  # noqa: BLE001
            pass
    for al, data, hechas in hechas_todas:
        _avisar_resultado(a, data, hechas, True, "", al)
    print(f"[pago-qr] {iid} confirmado {'solo' if auto else 'a mano'} {sim} {i['monto_c'] / 100:.2f}", flush=True)
    return {"ok": True, "total": total}


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
            if cd and cd.get("tipo") == "qr":
                como = " Págala con el QR de la academia desde Pichangol (Mis clases): se confirma sola."
            elif cd:
                como = (f" Yapea a {cd['titular']} ({cd['yape'][:3]} {cd['yape'][3:6]} {cd['yape'][6:]}) "
                        f"y reporta el código de seguridad en Pichangol.")
            else:
                como = " Coordina el pago con la academia."
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
                    if cd and cd.get("tipo") == "qr":
                        datos_c.append(["Paga con", f"QR de {cd['app_nombre']} · {cd['titular']}"])
                    elif cd:
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


class PagoQrReq(BaseModel):
    email: str
    items: list[dict] = []
    alumno_id: str = ""
    cuota_ids: list[str] = []


@router.post("/academias/pago-qr/iniciar", dependencies=_deps())
def post_qr_iniciar(req: PagoQrReq, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(req.email, x_user_token)
    items = req.items or ([{"alumno_id": req.alumno_id, "cuota_ids": req.cuota_ids}] if req.alumno_id else [])
    return iniciar_pago_qr(req.email, items)


class PagoQrEmailReq(BaseModel):
    email: str


@router.post("/academias/pago-qr/{iid}/pagado", dependencies=_deps())
def post_qr_pagado(iid: str, req: PagoQrEmailReq, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(req.email, x_user_token)
    return marcar_pagado_qr(iid, req.email)


@router.get("/academias/pago-qr/{iid}", dependencies=_deps())
def get_qr(iid: str, email: str, x_user_token: str | None = Header(default=None)) -> dict:
    _req_usuario(email, x_user_token)
    return estado_qr(iid, email)
