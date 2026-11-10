"""CONFIRMACIÓN AUTOMÁTICA DEL YAPE DIRECTO (fase 2 del Plan Academia,
10-oct-2026, pedido del director: "seguimos con la fase 2").

En la fase 1 el alumno yapea a la academia y reporta en Pichangol los 3
dígitos del CÓDIGO DE SEGURIDAD de su comprobante; la academia lo compara con
la notificación de su Yape y confirma a mano. Yape no tiene API pública para
negocios, así que la fase 2 lee esa MISMA notificación en el celular Android
de la academia:

1. El dueño activa "Confirmar mis pagos automáticamente" en el APK (Plan
   Academia). El APK llama a `POST /academias/yape/vincular` (con su sesión) y
   recibe un TOKEN DE DISPOSITIVO aleatorio (aquí solo se guarda su SHA-256);
   luego pide el permiso de "Acceso a notificaciones" de Android.
2. Un `NotificationListenerService` nativo (inyectado por
   `tool/configure_platforms.py`) ve SOLO las notificaciones de los paquetes de
   Yape (`yape_paquetes`, configurable en la torre) y las manda tal cual
   (título + texto) a `POST /academias/yape/notificacion` con ese token. Sin red
   las guarda y las reintenta.
3. El backend las lee con expresiones regulares EDITABLES en la torre (monto,
   código de seguridad, nombre: así un cambio de texto de Yape se arregla sin
   publicar un APK) y CONCILIA: un pago reportado "por confirmar" de una
   academia del dueño se confirma solo si coinciden el código de 3 dígitos Y el
   monto total, dentro de la ventana (`yape_ventana_horas`, 48 h) y la
   coincidencia es ÚNICA en ambos sentidos. Ambiguo → queda para la academia.
   Cada notificación se usa UNA vez. Se concilia al llegar la notificación y al
   reportar el alumno (el orden no importa).

Nunca se confirma algo que la academia no habría podido confirmar a mano: se
llama al mismo `academia_plan.resolver_pago` con el correo del dueño. Las
notificaciones (texto recortado) se guardan 7 días en el snapshot para que la
torre vea qué se leyó y afine las expresiones.

PAGO POR QR (Ecuador y Bolivia, 11-oct-2026, pedido del director: "que el
usuario escanee el código, pague y el sistema lo registre automáticamente"):
la academia muestra su QR de cobro; el alumno inicia el pago en Pichangol y
recibe un MONTO ÚNICO (lo que debe + 1..49 centavos, `academia_plan.
iniciar_pago_qr`). El celular de la academia escucha, además de Yape, las apps
de cobro que el DUEÑO eligió de las instaladas (`POST /academias/yape/apps`,
DeUna!, su banco…). Una notificación de esas apps que trae un monto (y no es un
egreso: "pagaste", "enviaste"…) se concilia contra las intenciones vivas de ESE
dueño: monto exacto, misma moneda si la notificación la dice, llegada después
de crear la intención y coincidencia única en ambos sentidos → `academia_plan.
confirmar_qr` (todas las cuotas de esa intención pagadas, recibo al alumno).
"""
from __future__ import annotations

import hashlib
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db.store import stores

router = APIRouter(tags=["academias"])

_LOCK = threading.RLock()
RETENCION_DIAS = 7
MAX_NOTIFICACIONES = 1500
MAX_TEXTO = 300

DEFAULTS = {
    "yape_auto_activo": "1",
    "yape_paquetes": "com.bcp.innovacxion.yapeapp",
    # "Yape! Juan Pérez te envió un pago por S/ 50. El cód. de seguridad es: 427"
    "yape_regex_monto": r"S/\.?\s*([\d][\d,]*(?:\.\d{1,2})?)",
    "yape_regex_codigo": r"c[oó]d(?:igo)?\.?\s*(?:de\s+)?seguridad\D{0,15}(\d{3})\b",
    "yape_regex_nombre": r"(?:yape!?\s*)?([A-ZÁÉÍÓÚÑa-záéíóúñ][^\n]{1,60}?)\s+te\s+(?:envi[oó]|yape[oó])",
    "yape_ventana_horas": "48",
    # QR (EC/BO): "Recibiste $ 25.13 de JUAN PEREZ" / "Te transfirieron Bs 150,07".
    "qr_regex_monto": r"(?:US\$|USD|\$|Bs\.?|BOB)\s*([\d][\d.,]*)",
    # Notificaciones de SALIDA de plata: nunca confirman un cobro.
    "qr_regex_egreso": r"\b(?:pagaste|enviaste|transferiste|retiraste|retiro|d[eé]bito|debitad[oa]|compra|consumo|cargo)\b",
}
MAX_APPS_PROPIAS = 6


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _de_iso(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _cfg(clave: str) -> str:
    v = stores.config.get(clave)
    return DEFAULTS[clave] if v is None else str(v)


# ── Configuración (torre) ─────────────────────────────────────────────────────

def activo() -> bool:
    return _cfg("yape_auto_activo") != "0"


def paquetes() -> list[str]:
    return [p.strip() for p in re.split(r"[,\s]+", _cfg("yape_paquetes")) if p.strip()]


def ventana_horas() -> int:
    try:
        return max(1, min(24 * 7, int(float(_cfg("yape_ventana_horas")))))
    except ValueError:
        return 48


def config() -> dict:
    return {"activo": activo(), "paquetes": paquetes(), "ventana_horas": ventana_horas(),
            "regex_monto": _cfg("yape_regex_monto"), "regex_codigo": _cfg("yape_regex_codigo"),
            "regex_nombre": _cfg("yape_regex_nombre"), "qr_regex_monto": _cfg("qr_regex_monto"),
            "qr_regex_egreso": _cfg("qr_regex_egreso")}


def paquetes_propios(email: str) -> list[str]:
    d = stores.yape_dispositivos.get((email or "").strip().lower()) or {}
    return [str(p) for p in (d.get("paquetes") or []) if isinstance(p, str)]


def paquetes_de(email: str = "") -> list[str]:
    """Paquetes que escucha el celular de `email`: Yape (global) + las apps de
    cobro que él mismo eligió (QR en Ecuador/Bolivia)."""
    return list(dict.fromkeys(paquetes() + paquetes_propios(email)))


def config_publica(email: str = "") -> dict:
    """Lo que necesita el APK (sin las expresiones: se leen en el servidor)."""
    return {"activo": activo(), "paquetes": paquetes_de(email), "apps": paquetes_propios(email)}


def set_config(datos: dict) -> dict:
    nuevos: dict[str, str] = {}
    if "activo" in datos and datos["activo"] is not None:
        nuevos["yape_auto_activo"] = "1" if datos["activo"] else "0"
    if datos.get("paquetes") is not None:
        ps = datos["paquetes"]
        ps = ps if isinstance(ps, list) else re.split(r"[,\s]+", str(ps))
        ps = [p.strip() for p in ps if str(p).strip()]
        if not ps or any(not re.fullmatch(r"[A-Za-z][\w]*(\.[A-Za-z_][\w]*)+", p) for p in ps):
            raise ValueError("Escribe paquetes de Android válidos (p. ej. com.bcp.innovacxion.yapeapp).")
        nuevos["yape_paquetes"] = ",".join(dict.fromkeys(ps))
    for k in ("regex_monto", "regex_codigo", "regex_nombre", "qr_regex_monto", "qr_regex_egreso"):
        v = datos.get(k)
        if v is None:
            continue
        v = str(v).strip()
        clave = k if k.startswith("qr_") else "yape_" + k
        if not v:
            v = DEFAULTS[clave]
        try:
            rx = re.compile(v, re.IGNORECASE)
        except re.error as ex:
            raise ValueError(f"La expresión de {k.split('_')[1]} no es válida: {ex}") from None
        if rx.groups < 1 and k != "qr_regex_egreso":
            raise ValueError(f"La expresión de {k.split('_')[1]} debe tener un grupo ( ) con el dato.")
        nuevos[clave] = v
    if datos.get("ventana_horas") is not None:
        try:
            h = int(datos["ventana_horas"])
        except (TypeError, ValueError):
            raise ValueError("La ventana debe ser un número de horas.") from None
        if not 1 <= h <= 168:
            raise ValueError("La ventana debe estar entre 1 y 168 horas.")
        nuevos["yape_ventana_horas"] = str(h)
    stores.config.update(nuevos)
    return config()


# ── Lectura de la notificación ────────────────────────────────────────────────

def _monto(txt: str) -> float | None:
    try:
        return round(float(txt.replace(",", "")), 2)
    except ValueError:
        return None


def monto_flexible(txt: str) -> float | None:
    """"1,234.56" · "1.234,56" · "25,13" · "25.13" · "150" → número. El
    ÚLTIMO separador seguido de 1-2 dígitos es el decimal; el resto, miles."""
    t = re.sub(r"[^\d.,]", "", str(txt or "")).strip(".,")
    if not t:
        return None
    m = re.search(r"[.,](\d{1,2})$", t)
    if m:
        entero, dec = t[:m.start()], m.group(1)
    else:
        entero, dec = t, ""
    entero = re.sub(r"[.,]", "", entero)
    if not entero.isdigit():
        return None
    try:
        return round(float(f"{entero}.{dec or '0'}"), 2)
    except ValueError:
        return None


def _moneda_simbolo(txt: str) -> str | None:
    t = (txt or "").upper()
    if re.search(r"\bBS\b|BS\.|\bBOB\b", t):
        return "BOB"
    if "US$" in t or "USD" in t or "$" in t:
        return "USD"
    if "S/" in t or "PEN" in t:
        return "PEN"
    return None


def leer_qr(titulo: str, texto: str) -> dict:
    """{monto, moneda, egreso} de una notificación de la app de cobros (QR)."""
    todo = f"{titulo or ''}\n{texto or ''}".strip()
    out = {"monto": None, "moneda": None, "egreso": False}
    try:
        out["egreso"] = bool(re.search(_cfg("qr_regex_egreso"), todo, re.IGNORECASE))
    except re.error:
        pass
    try:
        m = re.search(_cfg("qr_regex_monto"), todo, re.IGNORECASE)
    except re.error:
        m = None
    if m:
        out["monto"] = monto_flexible(m.group(1) if m.groups() else m.group(0))
        out["moneda"] = _moneda_simbolo(m.group(0))
    return out


def leer(titulo: str, texto: str) -> dict:
    """{monto, codigo, nombre} de una notificación de Yape (None si no se halló)."""
    todo = f"{titulo or ''}\n{texto or ''}".strip()
    out = {"monto": None, "codigo": None, "nombre": None}
    for campo, clave in (("monto", "yape_regex_monto"), ("codigo", "yape_regex_codigo"),
                         ("nombre", "yape_regex_nombre")):
        try:
            m = re.search(_cfg(clave), todo, re.IGNORECASE)
        except re.error:
            m = None
        if not m:
            continue
        val = (m.group(1) or "").strip()
        if campo == "monto":
            out["monto"] = _monto(val)
        elif campo == "codigo":
            out["codigo"] = val if re.fullmatch(r"\d{3}", val) else None
        else:
            out["nombre"] = re.sub(r"\s+", " ", val)[:60] or None
    return out


# ── Dispositivo de la academia ────────────────────────────────────────────────

def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def vincular(email: str, modelo: str = "", ahora: datetime | None = None) -> dict:
    """Nuevo token de dispositivo (reemplaza al anterior: un celular por dueño)."""
    email = (email or "").strip().lower()
    if not email:
        return {"ok": False, "error": "email"}
    token = secrets.token_urlsafe(32)
    with _LOCK:
        previas = paquetes_propios(email)  # las apps elegidas siguen al cambiar de celular
        stores.yape_dispositivos[email] = {
            "token_sha": _sha(token), "creado": (ahora or _ahora()).isoformat(),
            "modelo": re.sub(r"[^\w .,-]", "", str(modelo or ""))[:40], "ultimo": None, "recibidas": 0,
            "paquetes": previas}
    return {"ok": True, "token": token, **config_publica(email)}


_PAQUETE_RX = re.compile(r"[A-Za-z][\w]*(\.[A-Za-z_][\w]*)+")
# Nunca se escucha a Pichangol mismo ni a mensajería/redes (privacidad).
_PAQUETES_PROHIBIDOS = ("pe.ebim.pichangol", "com.whatsapp", "com.facebook", "com.instagram",
                        "org.telegram", "com.google.android.gm", "com.android.mms",
                        "com.google.android.apps.messaging", "com.samsung.android.messaging")


def elegir_apps(email: str, paquetes_nuevos: list[str]) -> dict:
    """El dueño elige (de las apps instaladas) dónde recibe sus cobros por QR."""
    email = (email or "").strip().lower()
    ps = [str(p).strip() for p in (paquetes_nuevos or []) if str(p).strip()]
    ps = list(dict.fromkeys(ps))
    if len(ps) > MAX_APPS_PROPIAS:
        return {"ok": False, "error": "muchas", "mensaje": f"Elige hasta {MAX_APPS_PROPIAS} apps."}
    for p in ps:
        if not _PAQUETE_RX.fullmatch(p) or len(p) > 120:
            return {"ok": False, "error": "paquete", "mensaje": "Esa app no es válida."}
        if any(p == x or p.startswith(x + ".") for x in _PAQUETES_PROHIBIDOS):
            return {"ok": False, "error": "prohibida",
                    "mensaje": "Esa app no recibe pagos: elige tu banco o tu app de cobros."}
    with _LOCK:
        d = stores.yape_dispositivos.get(email)
        if d is None:
            return {"ok": False, "error": "no_vinculado", "mensaje": "Activa primero la confirmación automática."}
        d["paquetes"] = ps
    return {"ok": True, **config_publica(email)}


def desvincular(email: str) -> dict:
    with _LOCK:
        stores.yape_dispositivos.pop((email or "").strip().lower(), None)
    return {"ok": True}


def estado_dueno(email: str) -> dict:
    email = (email or "").strip().lower()
    d = stores.yape_dispositivos.get(email) or {}
    mias = [n for n in stores.yape_notificaciones if n.get("email") == email]
    return {"vinculado": bool(d), "creado": d.get("creado"), "ultimo": d.get("ultimo"),
            "recibidas": int(d.get("recibidas") or 0),
            "confirmadas": sum(1 for n in mias if n.get("usada")), **config_publica(email)}


def _dueno_del_token(email: str, token: str | None) -> dict:
    email = (email or "").strip().lower()
    d = stores.yape_dispositivos.get(email)
    if not d or not token or not secrets.compare_digest(d.get("token_sha") or "", _sha(token)):
        raise HTTPException(status_code=401, detail="dispositivo_no_vinculado")
    return d


# ── Notificaciones ────────────────────────────────────────────────────────────

def _podar(ahora: datetime) -> None:
    corte = ahora - timedelta(days=RETENCION_DIAS)
    stores.yape_notificaciones[:] = [
        n for n in stores.yape_notificaciones if (_de_iso(n.get("recibida")) or ahora) >= corte
    ][-MAX_NOTIFICACIONES:]


def registrar(email: str, paquete: str, titulo: str, texto: str, recibida_ms: int | None = None,
              ahora: datetime | None = None) -> dict:
    """Guarda una notificación leída en el celular de la academia y concilia."""
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    paquete = str(paquete or "").strip()
    if not activo():
        return {"ok": True, "ignorada": "apagado"}
    es_yape = paquete in paquetes()
    if not es_yape and paquete not in paquetes_propios(email):
        return {"ok": True, "ignorada": "paquete"}
    titulo = re.sub(r"\s+", " ", str(titulo or "")).strip()[:120]
    texto = re.sub(r"\s+", " ", str(texto or "")).strip()[:MAX_TEXTO]
    if not (titulo or texto):
        return {"ok": True, "ignorada": "vacia"}
    recibida = ahora
    if recibida_ms:
        try:
            r = datetime.fromtimestamp(int(recibida_ms) / 1000, tz=timezone.utc)
            # El reloj del teléfono puede mentir: solo se acepta si es razonable.
            if ahora - timedelta(days=3) <= r <= ahora + timedelta(minutes=10):
                recibida = r
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    huella = _sha(f"{email}|{paquete}|{titulo}|{texto}")[:24]
    if es_yape:
        leido = {**leer(titulo, texto), "tipo": "yape", "moneda": "PEN", "egreso": False}
        sin_datos = leido["monto"] is None or leido["codigo"] is None
    else:
        q = leer_qr(titulo, texto)
        leido = {"monto": q["monto"], "codigo": None, "nombre": None, "tipo": "qr", "moneda": q["moneda"],
                 "egreso": q["egreso"]}
        sin_datos = q["monto"] is None
    with _LOCK:
        _podar(ahora)
        for n in stores.yape_notificaciones:
            # Android re-publica la misma notificación al actualizarla: una vez.
            if n.get("huella") == huella and abs(((_de_iso(n.get("recibida")) or ahora) - recibida).total_seconds()) < 86400:
                return {"ok": True, "duplicada": True, "id": n["id"]}
        n = {"id": "yn_" + huella[:16] + format(int(ahora.timestamp() * 1000) % 100000, "05d"),
             "huella": huella, "email": email, "paquete": paquete, "titulo": titulo, "texto": texto,
             "recibida": recibida.isoformat(), "llego": ahora.isoformat(), **leido,
             "usada": None, "nota": ""}
        if sin_datos:
            n["nota"] = "sin_datos"
        elif leido["egreso"]:
            n["nota"] = "egreso"
        stores.yape_notificaciones.append(n)
        d = stores.yape_dispositivos.get(email)
        if d is not None:
            d["ultimo"] = ahora.isoformat()
            d["recibidas"] = int(d.get("recibidas") or 0) + 1
    print(f"[yape-auto] {email} {paquete} {leido['tipo']} monto={leido['monto']} {leido.get('moneda') or ''} "
          f"cod={leido['codigo']} nota={n['nota'] or '-'}", flush=True)
    if n["nota"]:
        return {"ok": True, "id": n["id"], "leido": leido, "confirmados": []}
    res = conciliar(email, ahora=ahora) if es_yape else conciliar_qr(email, ahora=ahora)
    return {"ok": True, "id": n["id"], "leido": leido, "confirmados": res.get("confirmados", [])}


def _pendientes_de(email: str) -> list[dict]:
    from web import datos
    import academia_plan as ap
    acads = []
    for a in datos.academias_de_dueno(email) or []:
        a.setdefault("dueno", email)
        # Beneficio del plan: sin plan vigente no hay confirmación automática.
        if ap.beneficios(a):
            acads.append(a)
    return ap.por_confirmar(acads) if acads else []


def conciliar(email: str, ahora: datetime | None = None) -> dict:
    """Confirma los pagos "por confirmar" de las academias de `email` que
    coinciden con UNA sola notificación de Yape (código + monto + ventana)."""
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    if not email or not activo():
        return {"confirmados": []}
    with _LOCK:
        libres = [n for n in stores.yape_notificaciones
                  if n.get("email") == email and not n.get("usada") and n.get("codigo") and n.get("monto") is not None
                  and n.get("tipo", "yape") == "yape"]
    if not libres:
        return {"confirmados": []}
    try:
        grupos = _pendientes_de(email)
    except Exception as ex:  # noqa: BLE001 — base caída: se reintenta en el próximo evento
        print(f"[yape-auto] no se pudo leer pendientes de {email}: {ex}", flush=True)
        return {"confirmados": [], "error": "base"}
    ventana = timedelta(hours=ventana_horas())

    def calza(n: dict, g: dict) -> bool:
        if str(g.get("codigo") or "") != n["codigo"] or abs(float(g.get("total") or 0) - float(n["monto"])) > 0.009:
            return False
        fg, fn = _de_iso(g.get("fecha")), _de_iso(n.get("recibida"))
        return bool(fg and fn and abs(fg - fn) <= ventana)

    confirmados = []
    import academia_plan as ap
    grupos = [g for g in grupos if g.get("medio", "yape") != "qr"]
    for g in grupos:
        cands = [n for n in libres if calza(n, g)]
        if len(cands) != 1:
            if len(cands) > 1:
                with _LOCK:
                    for n in cands:
                        n["nota"] = "ambigua"
            continue
        n = cands[0]
        rivales = [h for h in grupos if h is not g and calza(n, h)]
        if rivales:
            with _LOCK:
                n["nota"] = "ambigua"
            continue
        r = ap.resolver_pago(g["academia_id"], g["alumno_id"], [c["id"] for c in g["cuotas"]], email, True,
                             ahora=ahora, auto=True)
        if not r.get("ok"):
            continue
        with _LOCK:
            n["usada"] = {"academia_id": g["academia_id"], "alumno_id": g["alumno_id"],
                          "alumno": g.get("alumno") or "", "cuotas": r.get("cuotas") or [], "en": ahora.isoformat()}
            n["nota"] = ""
        libres.remove(n)
        confirmados.append({"alumno_id": g["alumno_id"], "alumno": g.get("alumno") or "",
                            "total": g.get("total"), "simbolo": g.get("simbolo")})
        print(f"[yape-auto] confirmado {g['alumno_id']} {g.get('simbolo')} {g.get('total')} cód {n['codigo']}",
              flush=True)
    return {"confirmados": confirmados}


def conciliar_qr(email: str, ahora: datetime | None = None) -> dict:
    """Confirma las intenciones de pago por QR vivas del dueño `email` que
    calzan con UNA sola notificación de su app de cobros (monto único exacto,
    misma moneda, llegó después de crear la intención) y viceversa."""
    import academia_plan as ap
    from web import datos
    ahora = ahora or _ahora()
    email = (email or "").strip().lower()
    if not email or not activo():
        return {"confirmados": []}
    ventana = timedelta(hours=ventana_horas())
    with _LOCK:
        libres = [n for n in stores.yape_notificaciones
                  if n.get("email") == email and n.get("tipo") == "qr" and not n.get("usada")
                  and n.get("monto") is not None and not n.get("egreso")]
        vivas = [dict(i) for i in stores.qr_intenciones.values()
                 if i.get("dueno") == email and ap._viva(i, ahora)]
    if not libres or not vivas:
        return {"confirmados": []}

    def calza(n: dict, i: dict) -> bool:
        if int(round(float(n["monto"]) * 100)) != int(i.get("monto_c") or 0):
            return False
        if n.get("moneda") and n["moneda"] != i.get("moneda"):
            return False
        fi, fn = _de_iso(i.get("creada")), _de_iso(n.get("recibida"))
        # La plata llega DESPUÉS de crear la intención (5 min de holgura de reloj).
        return bool(fi and fn and fi - timedelta(minutes=5) <= fn <= fi + ventana)

    confirmados = []
    beneficio: dict[str, bool] = {}
    for i in vivas:
        aid = str(i.get("academia_id") or "")
        if aid not in beneficio:
            try:
                a = datos.academia(aid)
            except Exception as ex:  # noqa: BLE001 — base caída: se reintenta luego
                print(f"[yape-auto] qr: no se pudo leer la academia {aid}: {ex}", flush=True)
                return {"confirmados": confirmados, "error": "base"}
            if a:
                a.setdefault("id", aid)
            beneficio[aid] = bool(a and ap.beneficios(a))
        if not beneficio[aid]:
            continue
        cands = [n for n in libres if calza(n, i)]
        if len(cands) != 1:
            if len(cands) > 1:
                with _LOCK:
                    for n in cands:
                        n["nota"] = "ambigua"
            continue
        n = cands[0]
        if any(j is not i and j["id"] != i["id"] and calza(n, j) for j in vivas):
            with _LOCK:
                n["nota"] = "ambigua"
            continue
        r = ap.confirmar_qr(i["id"], ahora=ahora, auto=True)
        if not r.get("ok"):
            continue
        with _LOCK:
            n["usada"] = {"intencion": i["id"], "academia_id": aid, "alumno": i.get("academia") or "",
                          "en": ahora.isoformat()}
            n["nota"] = ""
        libres.remove(n)
        confirmados.append({"intencion": i["id"], "total": i["monto_c"] / 100.0, "moneda": i.get("moneda")})
        print(f"[yape-auto] qr confirmado {i['id']} {i.get('moneda')} {i['monto_c'] / 100:.2f}", flush=True)
    return {"confirmados": confirmados}


_SINCRONO = False  # los tests concilian en el mismo hilo


def conciliar_en_segundo_plano(email: str) -> None:
    email = (email or "").strip().lower()
    if not email or not activo() or not stores.yape_dispositivos.get(email):
        return
    if _SINCRONO:
        conciliar(email)
        conciliar_qr(email)
        return

    def correr():
        try:
            conciliar(email)
            conciliar_qr(email)
        except Exception as ex:  # noqa: BLE001
            print(f"[yape-auto] conciliar {email} falló: {ex}", flush=True)
    threading.Thread(target=correr, daemon=True, name="pcg-yape-auto").start()


def resumen_torre(limite: int = 80) -> dict:
    ns = list(reversed(stores.yape_notificaciones))[:limite]
    tot = stores.yape_notificaciones
    return {"config": config(),
            "kpis": {"dispositivos": len(stores.yape_dispositivos), "recibidas": len(tot),
                     "leidas": sum(1 for n in tot if n.get("monto") is not None and (n.get("codigo") or n.get("tipo") == "qr")),
                     "qr": sum(1 for n in tot if n.get("tipo") == "qr"),
                     "intenciones_vivas": sum(1 for i in stores.qr_intenciones.values()
                                              if i.get("estado") in ("esperando", "reportado")),
                     "sin_datos": sum(1 for n in tot if n.get("nota") == "sin_datos"),
                     "confirmadas": sum(1 for n in tot if n.get("usada")),
                     "ambiguas": sum(1 for n in tot if n.get("nota") == "ambigua")},
            "notificaciones": [{k: n.get(k) for k in ("id", "email", "paquete", "titulo", "texto", "recibida",
                                                     "monto", "codigo", "nombre", "usada", "nota", "tipo", "moneda")} for n in ns],
            "dispositivos": [{"email": e, "creado": d.get("creado"), "ultimo": d.get("ultimo"),
                              "recibidas": d.get("recibidas", 0), "modelo": d.get("modelo", ""),
                              "apps": list(d.get("paquetes") or [])}
                             for e, d in sorted(stores.yape_dispositivos.items())]}


# ── API (APK) ─────────────────────────────────────────────────────────────────

def _deps():
    from fastapi import Depends
    from pagos.router import _require_app_key
    return [Depends(_require_app_key)]


class VincularReq(BaseModel):
    email: str
    modelo: str = ""


@router.get("/academias/yape/estado", dependencies=_deps())
def get_estado(email: str, x_user_token: str | None = Header(default=None)) -> dict:
    from pagos.router import _require_usuario
    _require_usuario(email, x_user_token)
    return estado_dueno(email)


@router.post("/academias/yape/vincular", dependencies=_deps())
def post_vincular(req: VincularReq, x_user_token: str | None = Header(default=None)) -> dict:
    from pagos.router import _require_usuario
    _require_usuario(req.email, x_user_token)
    if not activo():
        return {"ok": False, "error": "apagado", "mensaje": "La confirmación automática está pausada por ahora."}
    return vincular(req.email, req.modelo)


@router.post("/academias/yape/desvincular", dependencies=_deps())
def post_desvincular(req: VincularReq, x_user_token: str | None = Header(default=None)) -> dict:
    from pagos.router import _require_usuario
    _require_usuario(req.email, x_user_token)
    return desvincular(req.email)


class AppsReq(BaseModel):
    email: str
    paquetes: list[str] = []


@router.post("/academias/yape/apps", dependencies=_deps())
def post_apps(req: AppsReq, x_user_token: str | None = Header(default=None)) -> dict:
    """El dueño elige de sus apps instaladas dónde recibe los cobros por QR."""
    from pagos.router import _require_usuario
    _require_usuario(req.email, x_user_token)
    return elegir_apps(req.email, req.paquetes)


class NotificacionReq(BaseModel):
    email: str
    paquete: str
    titulo: str = ""
    texto: str = ""
    recibida_ms: int | None = None


@router.post("/academias/yape/notificacion", dependencies=_deps())
def post_notificacion(req: NotificacionReq, x_yape_token: str | None = Header(default=None)) -> dict:
    """Lo llama el servicio NATIVO del celular de la academia (sin sesión de
    Google: el token de dispositivo es la prueba)."""
    _dueno_del_token(req.email, x_yape_token)
    return registrar(req.email, req.paquete, req.titulo, req.texto, req.recibida_ms)
