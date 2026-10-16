"""INSCRIBIRSE A UN CAMPEONATO DESDE LA WEB (pedido del director, 1-oct-2026:
"en un campeonato, el jugador debe poder hacer en la web todo lo que hace en
el app, pagando de su saldo Pichangol").

Espejo de lo que hace el jugador en `campeonato_detalle_screen.dart`, con la
MISMA fila `pichangol_campeonatos.data` y la MISMA contabilidad del backend:

- Inscripción INDIVIDUAL (deportes que no son por equipos): yo o mi hijo(a)
  (apoderado + WhatsApp + consentimiento), con `exigeDni` + edad de la
  categoría (identidad verificada en `pichangol_verificaciones`, o el
  documento contra el registro del país: DNI/RENIEC en Perú, cédula en
  Ecuador; CI + fecha de nacimiento en Bolivia, como el app). La cuota se
  paga del SALDO con `pagos.router.post_torneo_inscribir` (los mismos pagos
  `inscripcion_torneo` del jugador e `inscripcion_torneo_ingreso` POR
  RECIBIR del organizador que genera el APK).
- FÚTBOL (la vaquita, `pagos/pozos.py`): crear mi equipo pagando primero mi
  parte del pozo, unirme a un equipo (por código, por el enlace del capitán
  `?equipo=` o tocando el equipo; pozo lleno = entro gratis) y completar lo
  que falta, con las reglas `puedeInscribirse` / `plantelAbierto` /
  `motivoPlantelCerrado` / `equipoLleno` del app (`campeonatos_logica`).
- Saldo insuficiente → modal con "Recargar saldo" (`/mi-billetera#recargar`).

Concurrencia: cada acción corre con la fila del campeonato BLOQUEADA
(`datos.mutar_campeonato`, `SELECT … FOR UPDATE`) y un candado por correo
(el mismo jugador en dos pestañas no gasta dos veces); el dinero se mueve
DENTRO de esa transacción y, si el JSON no se pudo guardar, se revierte
(`pozos.revertir_aporte` / `_revertir_inscripcion`).

Páginas: `GET /torneo/{id}[?equipo=CODIGO]` (panel del jugador; la página
pública `/c/{id}` enlaza aquí). JSON (sesión obligatoria):
`POST /web/torneo/{id}/documento`, `/inscribir`, `/equipo/crear`,
`/equipo/unirme`, `/equipo/{equipo_id}/completar`.
"""

from __future__ import annotations

import base64
import json
import re
import threading
import time
import urllib.parse

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

import paises
from db.store import stores
from pagos import pozos
from web import campeonatos_logica as L
from web import datos, sesion, ui
from web.anfitrion_campeonatos import _EMOJI, _NOMBRE, _estado_pill, _fecha_hora_corta, _moneda, _pais
from web.ui import e

router = APIRouter(tags=["web-jugador-campeonatos"])
BASE = "/torneo"
_DOC = {"PE": ("DNI", 8), "EC": ("cédula", 10), "BO": ("CI", None)}
_TOKEN_MIN = 30  # minutos que vale el documento verificado para inscribirse

_CANDADOS: dict[str, threading.Lock] = {}
_CANDADOS_LOCK = threading.Lock()


def _candado(email: str) -> threading.Lock:
    with _CANDADOS_LOCK:
        return _CANDADOS.setdefault(email, threading.Lock())


# ── helpers ───────────────────────────────────────────────────────────────────
def _iso(c: dict) -> str:
    """ISO de la moneda del campeonato (país de la sede; si no, la congelada)."""
    return paises.moneda_de_pais(_pais(c))


def _monto(c: dict, centimos: int) -> str:
    return f"{_moneda(c)} {L.fmt_monto(int(centimos))}"


def _es_dueno(c: dict, email: str) -> bool:
    return (c.get("dueno") or "").strip().lower() == (email or "").lower()


def _nombre(ses: dict) -> str:
    try:
        from web.jugador_liga import mi_nombre
        return mi_nombre(ses)
    except Exception:  # noqa: BLE001
        return (ses.get("nombre") or ses.get("email", "").split("@")[0]).strip()


def _foto(ses: dict) -> str | None:
    f = (ses.get("foto") or "").strip()
    return f or None


def _err(mensaje: str, status: int = 400, **extra) -> JSONResponse:
    return JSONResponse({"ok": False, "error": extra.pop("error", "invalido"), "mensaje": mensaje, **extra}, status_code=status)


def _sesion_json(request: Request):
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return None, _err("Inicia sesión para continuar.", 401, error="sesion_requerida")
    return ses, None


def _falta_saldo(c: dict, email: str, requerido: int) -> JSONResponse:
    saldo = stores.saldo_centimos(email)
    return _err(f"Esto cuesta {_monto(c, requerido)} y se paga de tu saldo Pichangol (tienes {_monto(c, saldo)}). "
                "Recarga y vuelve a intentarlo.", 402, error="falta_saldo", falta_saldo=True,
                requerido_centimos=requerido, saldo_centimos=saldo, recargar="/mi-billetera#recargar")


def _moneda_billetera_ok(c: dict, email: str) -> str:
    """'' si la billetera del jugador está en la moneda del campeonato; si no,
    el mensaje. El saldo es de UNA moneda (multi-país): un saldo en Bs no paga
    una cuota en soles."""
    try:
        from pagos.router import moneda_billetera
        mb = moneda_billetera(email)
    except Exception:  # noqa: BLE001
        return ""
    if mb == _iso(c):
        return ""
    sim = paises.simbolo_de_moneda(mb)
    return (f"Tu saldo Pichangol está en {sim} y este campeonato cobra en {_moneda(c)}. "
            "Solo se puede pagar con saldo de la misma moneda.")


def _revertir_inscripcion(email: str, cuota: int, nuevos: list) -> None:
    """Compensación técnica: el cobro de la inscripción salió pero el campeonato
    no se pudo guardar → devuelve la cuota al saldo y anula los dos pagos."""
    for p in nuevos:
        p.estado = "anulado"
    stores.acreditar(email, int(cuota))
    print(f"[torneo-web] inscripción revertida {email}: {cuota}", flush=True)


# ── Documento (exigeDni) ──────────────────────────────────────────────────────
def _token_doc(email: str, cid: str, para: str, nombre: str, edad: int | None) -> str:
    d = {"e": email, "c": cid, "p": para, "n": (nombre or "")[:120], "a": edad, "x": int(time.time()) + _TOKEN_MIN * 60}
    cuerpo = base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{cuerpo}.{sesion._firmar(('doc:' + cuerpo).encode())}"


def _leer_token_doc(tok, email: str, cid: str, para: str) -> dict | None:
    tok = str(tok or "")
    if "." not in tok:
        return None
    cuerpo, firma = tok.rsplit(".", 1)
    import hmac
    if not hmac.compare_digest(sesion._firmar(("doc:" + cuerpo).encode()), firma):
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)).decode())
    except Exception:  # noqa: BLE001
        return None
    if d.get("e") != email or d.get("c") != cid or d.get("p") != para or int(d.get("x") or 0) < time.time():
        return None
    return {"nombre": d.get("n") or "", "edad": d.get("a")}


def _rango_edad(c: dict) -> tuple[int | None, int | None]:
    def _i(v):
        try:
            return int(v) if v is not None and str(v) != "" else None
        except (TypeError, ValueError):
            return None
    return _i(c.get("edadMin")), _i(c.get("edadMax"))


def _error_edad(c: dict, edad: int | None, hijo: bool) -> str:
    """Mismos textos que `_gateDniDatos` del app."""
    if edad is None:
        return ""
    mn, mx = _rango_edad(c)
    quien = "Tu hijo(a) tiene" if hijo else "Tienes"
    if mn is not None and edad < mn:
        return f"{quien} {edad} años; la categoría es desde {mn}."
    if mx is not None and edad > mx:
        return f"{quien} {edad} años; la categoría es hasta {mx}."
    return ""


def _identidad(c: dict, email: str, para: str, token) -> tuple[dict | None, str]:
    """Gate `exigeDni` del app. Devuelve ({nombre, edad}, '') si puede seguir o
    (None, mensaje). "Yo" verificado pasa directo (como `jugadorVerificado`:
    la web no conoce su edad y, como el app sin edad, la identidad basta); si
    no, hace falta el token que emite `/documento`. El hijo SIEMPRE con el
    documento del menor."""
    if not c.get("exigeDni"):
        return {"nombre": "", "edad": None}, ""
    if para == "yo" and datos.esta_verificado(email):
        return {"nombre": "", "edad": None}, ""
    info = _leer_token_doc(token, email, c["id"], para)
    if info is None:
        doc = _DOC.get(_pais(c), ("DNI", 8))[0]
        return None, (f"Este campeonato exige {doc}: verifica " + ("el de tu hijo(a)" if para == "hijo" else f"tu {doc}") + " para continuar.")
    msg = _error_edad(c, info.get("edad"), para == "hijo")
    return (None, msg) if msg else (info, "")


@router.post("/web/torneo/{cid}/documento")
def verificar_documento(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """Paso del DNI/cédula/CI del COMPETIDOR (`_gateDniDatos` del app):
    Perú/Ecuador contra el registro oficial (yo → además queda VERIFICADO, con
    la regla 1 documento = 1 cuenta de `post_verificar_dni`; hijo → solo se
    consulta); Bolivia, CI declarado + fecha de nacimiento si la categoría es
    por edad. Valida la edad y devuelve un token firmado (30 min) que las
    acciones de inscripción aceptan."""
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    email = ses["email"].lower()
    b = b or {}
    c = datos.campeonato(cid)
    if c is None:
        return _err("Este campeonato no existe o fue eliminado.", 404)
    if not c.get("exigeDni"):
        return _err("Este campeonato no pide documento.")
    para = "hijo" if b.get("para") == "hijo" else "yo"
    pais = _pais(c)
    doc, largo = _DOC.get(pais, ("DNI", 8))
    from web.jugador_cuenta import _puede_intentar, edad_desde, registrar_verificado
    mn, mx = _rango_edad(c)
    con_edad = mn is not None or mx is not None
    numero = str(b.get("numero") or "").strip()
    if pais == "BO":
        if len(re.sub(r"\s", "", numero)) < 5:
            return _err(f"Escribe el {doc}.")
        edad = None
        if con_edad:
            edad = edad_desde(str(b.get("nacimiento") or ""))
            if edad is None:
                return _err("Selecciona la fecha de nacimiento.")
        msg = _error_edad(c, edad, para == "hijo")
        if msg:
            return _err(msg, error="edad")
        return JSONResponse({"ok": True, "nombre": "", "edad": edad, "token": _token_doc(email, cid, para, "", edad)})
    numero = re.sub(r"\D", "", numero)
    if len(numero) != largo:
        return _err(f"El {doc} son {largo} dígitos.")
    if not _puede_intentar(email):
        return _err("Hiciste varios intentos seguidos. Espera unos minutos y vuelve a probar.", 429)
    try:
        if para == "yo":
            from propiedad.router import VerificarDniReq, post_verificar_dni
            data = post_verificar_dni(VerificarDniReq(dni=numero, email=email, pais=pais))
        else:
            from propiedad import identidad
            data = identidad.consultar_cedula(numero) if pais == "EC" else identidad.consultar_dni(numero)
    except Exception:  # noqa: BLE001
        data = None
    if not data:
        return _err("No pudimos conectar con el registro. Intenta en un momento.", 502)
    if not data.get("ok"):
        e_ = data.get("error")
        msg = (f"Ese {doc} ya está verificado en otra cuenta. Cada persona verifica una sola cuenta." if e_ == "dni_en_uso"
               else "El servicio de verificación no está disponible ahora." if e_ == "no_configurado"
               else f"Ese {doc} no figura en el registro. Revísalo.")
        return _err(msg, error=str(e_ or "no_encontrado"))
    nombre = str(data.get("nombre_completo") or "").strip()
    edad = edad_desde(data.get("fecha_nacimiento"))
    if para == "yo":
        registrar_verificado(email, _nombre(ses))
    msg = _error_edad(c, edad, para == "hijo")
    if msg:
        return _err(msg, error="edad")
    return JSONResponse({"ok": True, "nombre": nombre, "edad": edad, "token": _token_doc(email, cid, para, nombre, edad)})


# ── Acciones con dinero ───────────────────────────────────────────────────────
def _mutar(cid: str, email: str, fn) -> tuple[bool, dict | None]:
    """Corre `fn(c, deshacer)` con la fila bloqueada y el candado del jugador;
    si algo falla después de mover plata, ejecuta las compensaciones."""
    deshacer: list = []
    with _candado(email):
        try:
            return datos.mutar_campeonato(cid, lambda c: fn(c, deshacer))
        except Exception as ex:  # noqa: BLE001
            for d in deshacer:
                try:
                    d()
                except Exception as ex2:  # noqa: BLE001
                    print(f"[torneo-web] ¡compensación falló! {ex2}", flush=True)
            print(f"[torneo-web] {cid} {email}: {ex}", flush=True)
            return True, {"_error": True}


def _resp(encontrado: bool, res: dict | None) -> JSONResponse:
    if not encontrado:
        return _err("Este campeonato no existe o fue eliminado.", 404)
    if isinstance(res, JSONResponse):
        return res
    if res is None or res.get("_error"):
        return _err("No pudimos guardar tu inscripción. No se te cobró nada; inténtalo de nuevo.", 503)
    return JSONResponse(res)


def _resultado(r) -> tuple[bool, dict | JSONResponse]:
    return False, r


def _aviso(email: str, titulo: str, cuerpo: str) -> None:
    def _fn():
        try:
            from pagos.router import _aviso_push_usuario
            _aviso_push_usuario(email, titulo, cuerpo, tipo="campeonato")
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_fn, daemon=True).start()


def _args_pozo(c: dict, email: str, equipo_id: str, equipo_nombre: str) -> dict:
    from pagos.router import comision_centimos
    return dict(email=email, campeonato_id=c["id"], equipo_id=equipo_id,
                cuota_equipo_soles=float(c.get("costoInscripcion") or 0), cupo=L.cupo_reparto(c),
                moneda=_iso(c), organizador=(c.get("dueno") or "").strip().lower(),
                campeonato_nombre=str(c.get("nombre") or "")[:80], equipo_nombre=str(equipo_nombre or "")[:80],
                comision_fn=comision_centimos)


def _aportar(c: dict, email: str, equipo_id: str, equipo_nombre: str, deshacer: list,
             completar: bool = False) -> tuple[int | None, JSONResponse | None]:
    """Mi parte (o lo que falta) del pozo del equipo, de mi saldo. Devuelve
    (céntimos aportados, None) o (None, respuesta de error)."""
    if not L.tiene_cuota_por_equipo(c):
        return 0, None
    msg = _moneda_billetera_ok(c, email)
    if msg:
        return None, _err(msg, 409, error="moneda_distinta")
    monto = None
    if completar:
        st = pozos.de_equipo(c["id"], equipo_id, float(c.get("costoInscripcion") or 0), L.cupo_reparto(c))
        monto = st["faltante_centimos"] / 100.0
        if monto <= 0:
            return 0, None
    r = pozos.aportar(**_args_pozo(c, email, equipo_id, equipo_nombre), monto_soles=monto)
    if not r.get("ok"):
        if r.get("falta_saldo"):
            return None, _falta_saldo(c, email, int(r.get("requerido_centimos") or 0))
        return None, _err("No pudimos registrar tu parte del pozo.", 409, error=str(r.get("error") or "pozo"))
    cent = int(r.get("aporte_centimos") or 0)
    if cent > 0:
        deshacer.append(lambda: pozos.revertir_aporte(campeonato_id=c["id"], equipo_id=equipo_id, email=email, centimos=cent))
    return cent, None


@router.post("/web/torneo/{cid}/inscribir")
def inscribir(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """`_inscribirme` + `AppState.inscribirseCampeonato` (deportes individuales)."""
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    email = ses["email"].lower()
    b = b or {}
    c0 = datos.campeonato(cid)
    if c0 is None:
        return _err("Este campeonato no existe o fue eliminado.", 404)
    if _es_dueno(c0, email):
        return _err("Eres el organizador de este campeonato: para probar como jugador entra con otra cuenta de Google.", 403, error="organizador")
    if c0.get("deporte") == "futbol":
        return _err("En fútbol se inscriben equipos: crea tu equipo o únete con el código de tu capitán.", error="por_equipos")
    hijo = b.get("quien") == "hijo"
    nombre_hijo = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:80]
    wa = re.sub(r"[^\d+ ]", "", str(b.get("whatsapp") or "")).strip()[:20]
    try:
        edad_hijo = int(str(b.get("edad") or "").strip()) if str(b.get("edad") or "").strip() else None
        edad_hijo = edad_hijo if edad_hijo is not None and 0 < edad_hijo < 100 else None
    except ValueError:
        edad_hijo = None
    info, msg = _identidad(c0, email, "hijo" if hijo else "yo", b.get("doc_token"))
    if info is None:
        return _err(msg, 403 if "exige" in msg else 400, error="documento_requerido" if "exige" in msg else "edad")
    if hijo:
        nombre_hijo = nombre_hijo or info.get("nombre") or ""
        if not nombre_hijo:
            return _err("Escribe el nombre del alumno.", error="nombre")
        if not b.get("consiente"):
            return _err("Marca la casilla: confirma que eres el apoderado.", error="consentimiento")
    yo_nombre = _nombre(ses)

    def fn(c: dict, deshacer: list):
        if not L.puede_inscribirse(c):
            return _resultado(_err("Las inscripciones están cerradas." if not c.get("partidos") else
                                   "El fixture ya fue generado; escribe al organizador.", 409, error="cerrado"))
        mias = L.mis_participaciones(c, email)
        if not hijo and mias:
            return _resultado(_err(f"Ya estás inscrito en {c.get('nombre') or 'este campeonato'}.", 409, error="ya_inscrito"))
        nombre_p = nombre_hijo if hijo else yo_nombre
        if L.ya_inscrito_con_nombre(c, email, nombre_p):
            return _resultado(_err(f"\"{nombre_p}\" ya está inscrito en {c.get('nombre')}.", 409, error="ya_inscrito"))
        costo = float(c.get("costoInscripcion") or 0)
        cuota = int(round(costo * 100))
        if cuota > 0:
            m = _moneda_billetera_ok(c, email)
            if m:
                return _resultado(_err(m, 409, error="moneda_distinta"))
            if stores.saldo_centimos(email) < cuota:
                return _resultado(_falta_saldo(c, email, cuota))
            from pagos import router as pr
            kw = dict(email=email, academia_dueno=(c.get("dueno") or ""), cuota_soles=costo,
                      concepto=f"Inscripción {c.get('nombre') or 'torneo'}")
            if "moneda" in getattr(pr.TorneoInscribirReq, "model_fields", {}):
                kw["moneda"] = _iso(c)
            n0 = len(stores.pagos)
            r = pr.post_torneo_inscribir(pr.TorneoInscribirReq(**kw))
            if not r.get("ok"):
                if r.get("falta_saldo"):
                    return _resultado(_falta_saldo(c, email, cuota))
                return _resultado(_err("No se pudo cobrar la inscripción.", 409, error=str(r.get("error") or "cobro")))
            nuevos = [p for p in stores.pagos[n0:]
                      if (p.tipo == "inscripcion_torneo" and p.dueno_id == email)
                      or (p.tipo == "inscripcion_torneo_ingreso" and email in (p.concepto or ""))]
            deshacer.append(lambda: _revertir_inscripcion(email, cuota, nuevos))
        p = L.agregar_inscripcion(c, email=email, nombre_usuario=yo_nombre, foto=_foto(ses),
                                  nombre_menor=nombre_hijo if hijo else "",
                                  edad=(info.get("edad") if c.get("exigeDni") else edad_hijo) if hijo else None, whatsapp=wa)
        return True, {"ok": True, "participante_id": p["id"], "cobrado_centimos": cuota,
                      "saldo_centimos": stores.saldo_centimos(email),
                      "mensaje": (f"Inscribiste a \"{nombre_p}\" en {c.get('nombre')}. 🏆" if hijo
                                  else f"Te inscribiste en {c.get('nombre')}. 🏆")}

    return _resp(*_mutar(cid, email, fn))


@router.post("/web/torneo/{cid}/equipo/crear")
def crear_equipo(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """`_crearEquipo`: el CAPITÁN pone su parte del pozo y recibe el código."""
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    email = ses["email"].lower()
    b = b or {}
    c0 = datos.campeonato(cid)
    if c0 is None:
        return _err("Este campeonato no existe o fue eliminado.", 404)
    if c0.get("deporte") != "futbol":
        return _err("Este torneo no es por equipos.")
    if _es_dueno(c0, email):
        return _err("Eres el organizador de este campeonato: para probar como jugador entra con otra cuenta de Google.", 403, error="organizador")
    nombre = re.sub(r"\s+", " ", str(b.get("nombre") or "")).strip()[:60]
    if not nombre:
        return _err("Ponle nombre al equipo.", error="nombre")
    info, msg = _identidad(c0, email, "yo", b.get("doc_token"))
    if info is None:
        return _err(msg, 403 if "exige" in msg else 400, error="documento_requerido" if "exige" in msg else "edad")
    yo_nombre = _nombre(ses)

    def fn(c: dict, deshacer: list):
        if not L.puede_inscribirse(c):
            return _resultado(_err("Las inscripciones están cerradas: ya no se crean equipos nuevos. Aún puedes unirte al plantel de un equipo.", 409, error="cerrado"))
        mio = next((p for p in (c.get("participantes") or []) if str(p.get("capitanEmail") or "").lower() == email), None)
        if mio is not None:
            return False, {"ok": True, "ya": True, "codigo": mio.get("codigo"), "equipo_id": mio.get("id"),
                           "mensaje": "Ya tienes un equipo aquí."}
        if L.mis_participaciones(c, email):
            return _resultado(_err("Ya juegas en un equipo de este campeonato.", 409, error="ya_inscrito"))
        if any(str(p.get("nombre") or "").strip().lower() == nombre.lower() for p in (c.get("participantes") or [])):
            return _resultado(_err(f"Ya hay un equipo llamado «{nombre}». Elige otro nombre.", 409, error="nombre_repetido"))
        equipo_id = f"eq_{int(time.time() * 1_000_000)}"
        cent, r = _aportar(c, email, equipo_id, nombre, deshacer)
        if r is not None:
            return _resultado(r)
        p = L.crear_equipo(c, equipo_id=equipo_id, nombre_equipo=nombre, email=email, nombre_usuario=yo_nombre,
                           foto=_foto(ses), aporte=cent or 0)
        return True, {"ok": True, "codigo": p["codigo"], "equipo_id": equipo_id, "aporte_centimos": cent or 0,
                      "saldo_centimos": stores.saldo_centimos(email), "mensaje": f"Equipo \"{nombre}\" creado."}

    return _resp(*_mutar(cid, email, fn))


@router.post("/web/torneo/{cid}/equipo/unirme")
def unirme_equipo(request: Request, cid: str, b: dict | None = Body(None)) -> JSONResponse:
    """`_confirmarYUnirme` + `unirseAEquipoPorCodigo`: por código (o tocando el
    equipo). Valida ANTES de cobrar (nunca se debita sin poder unirse)."""
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    email = ses["email"].lower()
    b = b or {}
    c0 = datos.campeonato(cid)
    if c0 is None:
        return _err("Este campeonato no existe o fue eliminado.", 404)
    if _es_dueno(c0, email):
        return _err("Eres el organizador de este campeonato. Para probar como jugador entra con otra cuenta de Google, o comparte el código/enlace del equipo.", 403, error="organizador")
    cod = re.sub(r"[^A-Za-z0-9]", "", str(b.get("codigo") or "")).upper()[:12]
    eid = str(b.get("equipo_id") or "").strip()[:64]
    if not cod and not eid:
        return _err("Escribe el código del equipo.", error="codigo")
    info, msg = _identidad(c0, email, "yo", b.get("doc_token"))
    if info is None:
        return _err(msg, 403 if "exige" in msg else 400, error="documento_requerido" if "exige" in msg else "edad")
    yo_nombre = _nombre(ses)

    def fn(c: dict, deshacer: list):
        eq = L.equipo_por_codigo(c, cod) if cod else L.participante(c, eid)
        if eq is None or not eq.get("codigo"):
            return _resultado(_err("Código no válido. Pídeselo a tu capitán." if cod else
                                   "Este equipo aún no tiene código de invitación: pídele al organizador que abra el campeonato para generarlo.",
                                   404, error="codigo"))
        motivo = L.motivo_plantel_cerrado(c)
        if not L.plantel_abierto(c):
            return _resultado(_err(motivo or "Las inscripciones cerraron.", 409, error="cerrado"))
        if any(str(i.get("email") or "").lower() == email for i in (eq.get("roster") or [])):
            return False, {"ok": True, "ya": True, "mensaje": f"Ya estás en \"{eq.get('nombre')}\"."}
        if L.mis_participaciones(c, email):
            return _resultado(_err("Ya juegas en otro equipo de este campeonato.", 409, error="ya_inscrito"))
        if L.equipo_lleno(c, eq):
            return _resultado(_err(f"\"{eq.get('nombre')}\" ya tiene el plantel completo ({L.max_jugadores(c)} jugadores).", 409, error="lleno"))
        cent = 0
        if L.aporte_siguiente(c, eq) > 0:
            cent, r = _aportar(c, email, eq["id"], str(eq.get("nombre") or ""), deshacer)
            if r is not None:
                return _resultado(r)
        L.unir_al_plantel(c, eq, email=email, nombre_usuario=yo_nombre, foto=_foto(ses), aporte=cent or 0)
        cap = str(eq.get("capitanEmail") or "").lower()
        if cap and cap != email:
            _aviso(cap, "Nuevo jugador en tu equipo ⚽", f"{yo_nombre} se unió a \"{eq.get('nombre')}\".")
        return True, {"ok": True, "equipo_id": eq["id"], "aporte_centimos": cent or 0,
                      "saldo_centimos": stores.saldo_centimos(email), "mensaje": f"Te uniste a \"{eq.get('nombre')}\". 🎽"}

    return _resp(*_mutar(cid, email, fn))


@router.post("/web/torneo/{cid}/equipo/{equipo_id}/completar")
def completar_pozo(request: Request, cid: str, equipo_id: str) -> JSONResponse:
    """"Completar S/ X": cualquiera del plantel (o el capitán) pone lo que
    falta del pozo y el equipo queda inscrito."""
    ses, err = _sesion_json(request)
    if err is not None:
        return err
    email = ses["email"].lower()

    def fn(c: dict, deshacer: list):
        eq = L.participante(c, equipo_id)
        if eq is None:
            return _resultado(_err("Equipo no encontrado.", 404, error="equipo"))
        if not L.tiene_cuota_por_equipo(c):
            return _resultado(_err("Este campeonato no cobra inscripción por equipo."))
        soy = (str(eq.get("capitanEmail") or "").lower() == email
               or any(str(i.get("email") or "").lower() == email for i in (eq.get("roster") or [])))
        if not soy:
            return _resultado(_err("Solo los jugadores del equipo pueden completar su pozo.", 403, error="no_es_tu_equipo"))
        cent, r = _aportar(c, email, equipo_id, str(eq.get("nombre") or ""), deshacer, completar=True)
        if r is not None:
            return _resultado(r)
        if not cent:
            return False, {"ok": True, "ya": True, "mensaje": f"\"{eq.get('nombre')}\" ya tiene el pozo completo."}
        L.registrar_aporte(eq, email, cent)
        return True, {"ok": True, "aporte_centimos": cent, "saldo_centimos": stores.saldo_centimos(email),
                      "mensaje": f"\"{eq.get('nombre')}\" quedó inscrito. 🏆"}

    return _resp(*_mutar(cid, email, fn))


# ── Página del jugador ────────────────────────────────────────────────────────
_CSS = """
.tn{max-width:780px;margin:0 auto;padding:8px 0 40px}
.tn h1{font-size:clamp(22px,4.5vw,30px);margin:6px 0 4px;line-height:1.15;overflow-wrap:anywhere}
.tn .meta{color:var(--tenue);font-size:14.5px;overflow-wrap:anywhere}
.tn .chs{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px}
.tn .chs span{background:var(--gris);border-radius:999px;padding:6px 12px;font-size:13px;font-weight:700;max-width:100%;overflow-wrap:anywhere}
.tn .card{background:#fff;border:1px solid var(--trazo);border-radius:18px;box-shadow:var(--sombra);padding:18px 18px;margin-top:16px;min-width:0}
.tn .card h2{font-size:18px;margin:0 0 6px}
.tn .card.invita{border:1.5px solid var(--esmeralda)}
.tn .card.ok{background:var(--ok-bg);border-color:transparent}
.tn .sub{color:var(--tenue);font-size:14px;margin:4px 0}
.tn .acc{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.tn .acc .btn{flex:1 1 220px;min-width:0;max-width:100%}
.tn label.l{display:block;font-weight:700;font-size:13.5px;margin:12px 0 6px}
.tn input[type=text],.tn input[type=tel],.tn input[type=date]{width:100%;border:1px solid var(--trazo);border-radius:12px;padding:12px 14px;font:inherit;font-size:15px}
.tn .seg{display:flex;gap:8px;flex-wrap:wrap}
.tn .seg button{flex:1 1 120px;border:1px solid var(--trazo);background:#fff;border-radius:999px;padding:10px 14px;font:inherit;font-weight:700;cursor:pointer;color:var(--noche)}
.tn .seg button.sel{background:var(--gris);border-color:var(--gris)}
.tn .seg button:disabled{opacity:.45;cursor:not-allowed}
.tn .chk{display:flex;gap:10px;align-items:flex-start;margin-top:12px;font-size:13.5px}
.tn .chk input{width:auto;flex:none;margin-top:3px}
.tn .err{color:var(--bad-fg);font-weight:700;font-size:13px;margin-top:8px;min-height:1px}
.tn .eqs{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:12px;margin-top:10px}
.tn .eq{background:#fff;border:1px solid var(--trazo);border-radius:16px;padding:14px;min-width:0}
.tn .eq b{font-size:16px;overflow-wrap:anywhere}
.tn .barra{height:8px;background:var(--gris);border-radius:99px;overflow:hidden;margin:8px 0 4px}
.tn .barra i{display:block;height:100%;background:var(--esmeralda)}
.tn .ros{list-style:none;padding:0;margin:8px 0 0;font-size:13.5px}
.tn .ros li{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid #F1F3F2}
.tn .ros li span:first-child{min-width:0;overflow-wrap:anywhere}
.tn .pg{color:var(--ok-fg);font-weight:700;font-size:12px;white-space:nowrap}
.tn .np{color:#B25E0A;font-weight:700;font-size:12px;white-space:nowrap}
.tn .motivo{background:#F4F7FA;border-radius:12px;padding:10px;color:var(--tenue);font-size:13px;margin-top:10px}
.tn .doc{background:#F4F7FA;border-radius:14px;padding:12px 14px;margin-top:12px}
.tn .doc.ok{background:var(--ok-bg);color:var(--ok-fg);font-weight:700}
.tn .cod{font-size:26px;font-weight:900;letter-spacing:4px;color:var(--teal)}
.tn .saldo{font-size:13.5px;color:var(--tenue);margin-top:6px}
"""


def _chips_info(c: dict) -> str:
    dep = str(c.get("deporte") or "")
    out = [f"{_EMOJI.get(dep, '🏆')} {_NOMBRE.get(dep, dep.capitalize())}", L.FORMATOS[L.formato_de(c)]]
    if c.get("categoria"):
        out.append(str(c["categoria"]))
    if c.get("fechas"):
        out.append(f"📅 {c['fechas']}")
    if c.get("sede"):
        out.append(f"📍 {c['sede']}")
    costo = float(c.get("costoInscripcion") or 0)
    if costo > 0:
        cents = int(round(costo * 100))
        if L.tiene_cuota_por_equipo(c):
            out.append(f"Inscripción {_monto(c, cents)} por equipo")
            if L.cupo_reparto(c) > 0:
                out.append(f"👥 {_monto(c, L.cuota_jugador_centimos(c))} por jugador (hasta {L.cupo_reparto(c)})")
        else:
            out.append(f"Inscripción {_monto(c, cents)}")
    else:
        out.append("Inscripción gratis")
    if c.get("inscripcionHasta"):
        out.append(f"🗓️ Cierre inscrip.: {_fecha_hora_corta(c['inscripcionHasta'])}")
    if c.get("exigeDni"):
        out.append(f"🪪 Exige {_DOC.get(_pais(c), ('DNI', 8))[0]}")
    mn, mx = _rango_edad(c) if c.get("exigeDni") else (None, None)
    if mn is not None or mx is not None:
        out.append("🎂 " + (f"desde {mn}" if mn is not None else "") + (f" hasta {mx} años" if mx is not None else ""))
    return "<div class='chs'>" + "".join(f"<span>{e(x.strip())}</span>" for x in out) + "</div>"


def _bloque_doc(c: dict, para: str) -> str:
    """Caja del documento (yo / hijo) para `exigeDni`. Bolivia: CI + fecha."""
    pais = _pais(c)
    doc, largo = _DOC.get(pais, ("DNI", 8))
    mn, mx = _rango_edad(c)
    fecha = ("<label class='l'>🎂 Fecha de nacimiento</label><input type='date' data-doc-nac>"
             if pais == "BO" and (mn is not None or mx is not None) else "")
    quien = f"el {doc} de tu hijo(a)" if para == "hijo" else f"tu {doc}"
    nota = ("Lo validamos contra el registro oficial: nombre y edad vienen de ahí." if pais != "BO"
            else "En Bolivia el CI es declarado (no hay registro en línea).")
    return (f"<div class='doc' data-doc='{para}'><b>🪪 Este campeonato exige {e(doc)}</b>"
            f"<p class='sub' style='margin:4px 0 0'>Ingresa {e(quien)}. {e(nota)}</p>"
            f"<label class='l'>Número de {e(doc)}</label><input type='text' inputmode='{'text' if pais == 'BO' else 'numeric'}' "
            f"maxlength='{largo or 15}' autocomplete='off' data-doc-num placeholder='{(str(largo) + ' dígitos') if largo else e(doc)}'>{fecha}"
            "<div class='err' data-doc-err></div></div>")


def _equipo_html(c: dict, eq: dict, email: str, es_dueno: bool, invitado: bool = False) -> str:
    roster = eq.get("roster") or []
    mx = L.max_jugadores(c)
    soy_cap = str(eq.get("capitanEmail") or "").lower() == email
    soy_del = any(str(i.get("email") or "").lower() == email for i in roster)
    cuota = L.tiene_cuota_por_equipo(c)
    puedo = (not es_dueno and not soy_del and not soy_cap and bool(eq.get("codigo")) and L.plantel_abierto(c)
             and not L.equipo_lleno(c, eq) and not L.mis_participaciones(c, email))
    motivo = ""
    if not puedo and not soy_del and not soy_cap:
        if es_dueno:
            motivo = "Eres el organizador de este campeonato. Para probar como jugador entra con otra cuenta de Google, o comparte el código/enlace del equipo."
        elif L.motivo_plantel_cerrado(c):
            motivo = L.motivo_plantel_cerrado(c)
        elif L.equipo_lleno(c, eq):
            motivo = f"Plantel completo ({mx} jugadores)."
        elif not eq.get("codigo"):
            motivo = "Este equipo aún no tiene código de invitación: pídele al organizador que abra el campeonato para generarlo."
        elif L.mis_participaciones(c, email):
            motivo = "Ya juegas en otro equipo de este campeonato."
    pozo = ""
    if cuota:
        cuota_eq = L.cuota_equipo_centimos(c)
        llevado = L.pozo_centimos(eq)
        pct = 100 if cuota_eq <= 0 else min(100, round(llevado * 100 / cuota_eq))
        estado = ("✅ Inscrito: pozo completo" if L.pozo_completo(c, eq)
                  else f"Llevan {_monto(c, llevado)} de {_monto(c, cuota_eq)} · faltan {_monto(c, L.faltante_pozo(c, eq))}")
        pozo = f"<div class='barra'><i style='width:{pct}%'></i></div><div class='sub' style='font-size:13px'>{e(estado)}</div>"
    filas = "".join(
        f"<li><span>{'✓ ' if i.get('email') else ''}{e(i.get('nombre') or 'Jugador')}"
        f"{' · Capitán' if str(i.get('email') or '').lower() == str(eq.get('capitanEmail') or '').lower() and i.get('email') else ''}</span>"
        + ((f"<span class='pg'>pagó {e(_monto(c, int(i.get('aporteCentimos') or 0)))}</span>" if int(i.get("aporteCentimos") or 0) > 0
            else "<span class='np'>sin pagar</span>") if cuota else "")
        + "</li>" for i in roster) or "<li><span class='sub'>Aún sin jugadores.</span></li>"
    botones = ""
    if puedo:
        parte = L.aporte_siguiente(c, eq)
        txt = f"Unirme · pones {_monto(c, parte)}" if parte > 0 else "Unirme a este equipo"
        botones += (f"<button type='button' class='btn' data-unirme='{e(eq['id'])}' data-nombre='{e(eq.get('nombre') or '')}' "
                    f"data-parte='{parte}' data-pozo='{L.pozo_centimos(eq)}'>{e(txt)}</button>")
    if cuota and not L.pozo_completo(c, eq) and (soy_cap or soy_del):
        falta = L.faltante_pozo(c, eq)
        botones += (f"<button type='button' class='btn sec' data-completar='{e(eq['id'])}' data-nombre='{e(eq.get('nombre') or '')}' "
                    f"data-falta='{falta}'>💰 Completar {e(_monto(c, falta))}</button>")
    cod = ""
    if soy_cap and eq.get("codigo"):
        cod = (f"<div class='sub' style='margin-top:8px'>Código para tus jugadores: <b style='letter-spacing:2px'>{e(eq['codigo'])}</b> · "
               f"<a href='{BASE}/{urllib.parse.quote(c['id'])}?equipo={urllib.parse.quote(str(eq['codigo']))}' data-copiar>Copiar enlace</a></div>")
    cab = (f"<div class='sub' style='margin:0 0 4px;color:var(--teal);font-weight:800'>Te invitaron a este equipo</div>" if invitado else "")
    borde = " style='border:1.5px solid var(--esmeralda)'" if invitado else ""
    return (f"<div class='eq'{borde} id='eq-{e(eq['id'])}'>{cab}"
            f"<b>{e(eq.get('nombre') or 'Equipo')}</b>"
            f"<div class='sub' style='font-size:13px'>Plantel ({len(roster)}{'/' + str(mx) if mx else ''})"
            f"{' · tu equipo' if (soy_cap or soy_del) else ''}</div>{pozo}<ul class='ros'>{filas}</ul>{cod}"
            + (f"<div class='motivo'>{e(motivo)}</div>" if motivo else "")
            + (f"<div class='acc'>{botones}</div>" if botones else "") + "</div>")


@router.get(BASE + "/{cid}", response_class=HTMLResponse)
def pagina_torneo(request: Request, cid: str, equipo: str = "") -> HTMLResponse:
    volver = f"{BASE}/{urllib.parse.quote(cid)}" + (f"?equipo={urllib.parse.quote(equipo[:16])}" if equipo else "")
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        from web.jugador_liga import sin_sesion
        return sin_sesion(request, volver, "Inscribirme al campeonato", "La inscripción")
    email = ses["email"].lower()
    c = datos.campeonato(cid)
    if c is None:
        cuerpo = ("<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><div style='font-size:46px'>🏆</div>"
                  "<h1 style='font-size:22px'>Campeonato no encontrado</h1><p class='sub'>Este campeonato no existe o fue eliminado.</p>"
                  "<a class='btn' href='/anfitrion/campeonatos'>Mis campeonatos</a></div>")
        resp = ui.shell("Campeonato", cuerpo, sesion=ses)
        resp.status_code = 404
        return resp
    es_dueno = _es_dueno(c, email)
    futbol = c.get("deporte") == "futbol"
    mias = L.mis_participaciones(c, email)
    solo_hijos = bool(mias) and all(L.es_menor(p) for p in mias)
    puede_ins = not es_dueno and L.puede_inscribirse(c)
    verificado = datos.esta_verificado(email) if c.get("exigeDni") else True
    saldo = stores.saldo_centimos(email)
    pais = _pais(c)
    nombre_del_dni = bool(c.get("exigeDni")) and pais in ("PE", "EC")
    pub = f"/c/{urllib.parse.quote(cid)}" + (f"?equipo={urllib.parse.quote(equipo[:16])}" if equipo else "")
    partes = [f"<a class='anf-back' href='/anfitrion/campeonatos' style='text-decoration:none;color:var(--tenue);font-weight:700'>‹ Mis campeonatos</a>",
              f"<div style='margin-top:10px'>{_estado_pill(c)}</div><h1>🏆 {e(c.get('nombre') or 'Campeonato')}</h1>",
              _chips_info(c),
              f"<div class='saldo'>👛 Tu saldo Pichangol: <b>{e(_monto(c, saldo))}</b> · <a href='/mi-billetera#recargar'>Recargar</a> · "
              f"<a href='{pub}'>Ver la página del torneo</a></div>"]
    if es_dueno:
        partes.append(f"<div class='card'><h2>Eres el organizador</h2><p class='sub'>Administra participantes, fixture y resultados desde Mis campeonatos. "
                      f"Para probar como jugador entra con otra cuenta de Google.</p><div class='acc'><a class='btn' href='/anfitrion/campeonatos/{e(cid)}'>Administrar</a></div></div>")
    # Ya inscrito (yo, mis hijos, mi equipo o un plantel donde juego).
    if mias and not es_dueno:
        lineas = "".join(
            f"<li>{'⚽ ' if L.es_equipo(p) else '🎽 '}{e(p.get('nombre') or '')}"
            f"{' (tu hijo/a)' if L.es_menor(p) else ''}{' · capitán' if str(p.get('capitanEmail') or '').lower() == email else ''}</li>"
            for p in mias)
        partes.append(f"<div class='card ok'><h2>✅ Ya estás inscrito</h2><ul style='margin:6px 0 0 18px;padding:0'>{lineas}</ul></div>")
    doc_yo = bool(c.get("exigeDni")) and not verificado
    # ── Individual ──
    if not futbol and puede_ins and (not mias or solo_hijos):
        costo = int(round(float(c.get("costoInscripcion") or 0) * 100))
        boton = f"Inscribirme · {_monto(c, costo)}" if costo > 0 else "Inscribirme"
        hijo_fijo = bool(mias)  # ya me inscribí yo o inscribí hijos → solo otro hijo
        campo_nombre = ("" if nombre_del_dni else
                        "<label class='l'>Nombre del alumno (niño/a)</label><input type='text' maxlength='80' data-f='nombre' autocomplete='off'>")
        partes.append(
            f"<div class='card' id='insc'><h2>{'Inscribir a otro hijo(a)' if hijo_fijo else 'Inscribirme'}</h2>"
            "<p class='sub'>Se paga de tu saldo Pichangol, como en la app. El organizador recibe tu inscripción al instante.</p>"
            "<label class='l'>¿Quién va a competir?</label><div class='seg' data-quien>"
            f"<button type='button' data-q='yo' class='{'' if hijo_fijo else 'sel'}'{' disabled' if hijo_fijo else ''}>Yo</button>"
            f"<button type='button' data-q='hijo' class='{'sel' if hijo_fijo else ''}'>Mi hijo(a)</button></div>"
            f"<div data-hijo style='display:{'block' if hijo_fijo else 'none'}'>{campo_nombre}"
            + ("" if c.get("exigeDni") else "<label class='l'>Edad (opcional)</label><input type='text' inputmode='numeric' maxlength='2' data-f='edad' autocomplete='off'>")
            + f"<label class='l'>Tu WhatsApp (apoderado)</label><input type='tel' maxlength='15' data-f='whatsapp' inputmode='tel'>"
            "<label class='chk'><input type='checkbox' data-f='consiente'> <span>Soy el apoderado y autorizo el registro del menor.</span></label>"
            + (_bloque_doc(c, "hijo") if c.get("exigeDni") else "") + "</div>"
            + (f"<div data-yo style='display:{'none' if hijo_fijo else 'block'}'>{_bloque_doc(c, 'yo')}</div>" if doc_yo else "")
            + f"<div class='err' id='insErr'></div><div class='acc'><button type='button' class='btn lg' id='btnIns' data-costo='{costo}'>{e(boton)}</button></div></div>")
    # ── Fútbol ──
    invitado = L.equipo_por_codigo(c, equipo) if (futbol and equipo) else None
    if futbol:
        if equipo and invitado is None:
            partes.append("<div class='card'><p class='sub' style='color:#B25E0A;margin:0'>El código de equipo del enlace ya no es válido: pídele a tu capitán el enlace actualizado.</p></div>")
        if invitado is not None:
            partes.append("<div class='card invita'><h2>Te invitaron al equipo «" + e(invitado.get("nombre") or "") + "»</h2>"
                          f"<div class='eqs' style='grid-template-columns:1fr'>{_equipo_html(c, invitado, email, es_dueno, invitado=True)}</div></div>")
        if doc_yo and not es_dueno and not mias:
            partes.append(f"<div class='card' id='docYo'>{_bloque_doc(c, 'yo')}</div>")
        if puede_ins and not mias:
            parte = L.aporte_siguiente(c, None)
            txt = f"Crear mi equipo · pones {_monto(c, parte)}" if parte > 0 else "Crear mi equipo"
            partes.append(
                "<div class='card'><h2>⚽ Crear mi equipo</h2>"
                + ("<p class='sub'>Como capitán pones tu parte del pozo de tu saldo; tus jugadores ponen la suya al entrar con tu código "
                   "y el equipo queda inscrito cuando el pozo se completa.</p>" if parte > 0 else
                   "<p class='sub'>Recibirás un código para que tus jugadores se unan al plantel.</p>")
                + "<label class='l'>Nombre del equipo</label><input type='text' maxlength='60' id='eqNombre' placeholder='Los Tigres FC' autocomplete='off'>"
                f"<div class='err' id='eqErr'></div><div class='acc'><button type='button' class='btn lg' id='btnCrear' data-parte='{parte}'>{e(txt)}</button></div></div>")
        if not es_dueno and not mias and L.plantel_abierto(c):
            nota = ("" if puede_ins else
                    ("El fixture ya está publicado, pero " if L.fixture_generado(c) else "Ya no se crean equipos nuevos, pero ")
                    + "aún puedes unirte al plantel de un equipo: toca el equipo o usa el código de tu capitán.")
            partes.append("<div class='card'><h2>Unirme a un equipo</h2>"
                          + (f"<p class='sub'>{e(nota)}</p>" if nota else "<p class='sub'>¿Tu capitán te pasó un código? Escríbelo aquí.</p>")
                          + "<div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:8px'><input type='text' id='codEq' maxlength='12' placeholder='Ej.: 4KZ9AB' "
                          "style='flex:1 1 160px;min-width:0;text-transform:uppercase;letter-spacing:.12em;font-weight:800' autocomplete='off'>"
                          "<button type='button' class='btn' id='btnCod' style='flex:0 0 auto'>Unirme</button></div><div class='err' id='codErr'></div></div>")
        elif not es_dueno and not mias and not puede_ins:
            partes.append(f"<div class='card'><p class='sub' style='margin:0'>{e(L.motivo_plantel_cerrado(c) or 'Las inscripciones cerraron.')}</p></div>")
        equipos = [p for p in (c.get("participantes") or []) if invitado is None or p.get("id") != invitado.get("id")]
        if equipos:
            partes.append(f"<h2 style='margin:26px 0 4px;font-size:18px'>Equipos ({len(c.get('participantes') or [])})</h2>"
                          f"<div class='eqs'>{''.join(_equipo_html(c, p, email, es_dueno) for p in equipos)}</div>")
    elif not puede_ins and not mias and not es_dueno:
        partes.append(f"<div class='card'><p class='sub' style='margin:0'>{'Las inscripciones cerraron. Espera el fixture.' if L.inscripcion_vencida(c) and not L.fixture_generado(c) else 'Las inscripciones de este campeonato están cerradas.'}</p></div>")
    if not futbol:
        ps = c.get("participantes") or []
        filas = "".join(f"<li>{e(p.get('nombre') or '')}</li>" for p in ps) or "<li class='sub'>Aún sin participantes.</li>"
        partes.append(f"<h2 style='margin:26px 0 4px;font-size:18px'>Participantes ({len(ps)})</h2><div class='card' style='margin-top:8px'><ol style='margin:0;padding-left:20px'>{filas}</ol></div>")
    cfg = {"id": cid, "moneda": _moneda(c), "saldo": saldo, "exigeDni": bool(c.get("exigeDni")), "docYo": doc_yo,
           "pais": pais, "nombreDelDni": nombre_del_dni, "nombre": c.get("nombre") or "", "recargar": "/mi-billetera#recargar",
           "costo": int(round(float(c.get("costoInscripcion") or 0) * 100)), "cuota": L.tiene_cuota_por_equipo(c),
           "cuotaEquipo": L.cuota_equipo_centimos(c), "cuotaJugador": L.cuota_jugador_centimos(c) if L.tiene_cuota_por_equipo(c) else 0}
    cuerpo = (f"<style>{_CSS}</style><div class='tn'>" + "".join(partes) + "</div>"
              "<script>window.TN=" + json.dumps(cfg).replace("<", "\\u003c") + ";</script><script>" + _JS + "</script>")
    return ui.shell(str(c.get("nombre") or "Campeonato"), cuerpo, sesion=ses, titulo_tab=f"{c.get('nombre') or 'Campeonato'} · Inscripción · Pichangol")


_JS = r"""
(function(){
var C = window.TN || {}, $ = function(i){ return document.getElementById(i); }, tok = {yo: '', hijo: ''};
function fmt(c){ var v = (c || 0) / 100; return C.moneda + ' ' + (Math.abs(v - Math.round(v)) < 0.005 ? Math.round(v) : v.toFixed(2)); }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(x){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]; }); }
function post(url, body){ return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})
  .then(function(r){ return r.json().catch(function(){ return {ok: false, mensaje: 'Respuesta inválida del servidor.'}; }).then(function(j){ j._st = r.status; return j; }); }); }
function sinSaldo(j){ return pcgConfirmar({titulo: 'Te falta saldo', icono: '👛', mensaje: j.mensaje || 'Recarga tu saldo y vuelve a intentarlo.', confirmar: 'Recargar saldo', cancelar: 'Ahora no'})
  .then(function(ok){ if(ok) pcgIr(j.recargar || C.recargar, 'Abriendo tu billetera…'); }); }
function fallo(j, errEl){ if(j && j._st === 401){ pcgIr('/entrar?volver=' + encodeURIComponent(location.pathname + location.search), 'Inicia sesión…'); return; }
  if(j && j.falta_saldo){ sinSaldo(j); return; }
  var m = (j && j.mensaje) || 'No se pudo completar. Revisa tu conexión e inténtalo de nuevo.';
  if(errEl) errEl.textContent = m;
  pcgAvisar({titulo: 'No se pudo', mensaje: m, icono: j && j.error === 'moneda_distinta' ? '💱' : '⚠️'}); }
function exito(j, titulo){ pcgCargando(false); return pcgAvisar({titulo: titulo || '¡Listo!', mensaje: j.mensaje || 'Listo.', icono: '🏆', confirmar: 'Ver mi inscripción'})
  .then(function(){ pcgRecargar('Actualizando…'); }); }
// Documento (exigeDni): valida contra el registro y confirma el nombre.
function documento(para){ if(tok[para]) return Promise.resolve(tok[para]);
  var box = document.querySelector("[data-doc='" + para + "']");
  if(!box) return Promise.resolve('');
  var num = box.querySelector('[data-doc-num]'), nac = box.querySelector('[data-doc-nac]'), err = box.querySelector('[data-doc-err]');
  err.textContent = '';
  if(!num.value.trim()){ err.textContent = 'Escribe el número del documento.'; num.focus(); box.scrollIntoView({behavior: 'smooth', block: 'center'}); return Promise.resolve(null); }
  pcgCargando('Verificando…');
  return post('/web/torneo/' + encodeURIComponent(C.id) + '/documento', {para: para, numero: num.value, nacimiento: nac ? nac.value : ''}).then(function(j){
    pcgCargando(false);
    if(!j.ok){ err.textContent = j.mensaje || 'No se pudo verificar.'; return null; }
    var conf = j.nombre ? pcgConfirmar({titulo: para === 'hijo' ? '¿Es tu hijo(a)?' : '¿Eres tú?', icono: '🪪',
        html: "<p class='sub' style='margin:0 0 8px'>El registro dice:</p><div style='background:#E6F4EA;border-radius:14px;padding:12px;text-align:left'><b>" + esc(j.nombre) + "</b>" +
              (j.edad != null ? "<div style='font-size:13px;color:#5F6F7A'>" + j.edad + " años</div>" : '') + "</div>",
        confirmar: para === 'hijo' ? 'Sí, es él/ella' : 'Sí, soy yo', cancelar: 'No, corregir'}) : Promise.resolve(true);
    return conf.then(function(ok){ if(!ok){ num.value = ''; num.focus(); return null; }
      tok[para] = j.token; box.classList.add('ok'); box.innerHTML = '✅ Documento verificado' + (j.nombre ? ': ' + esc(j.nombre) : '') + (j.edad != null ? ' · ' + j.edad + ' años' : '');
      if(para === 'hijo' && j.nombre) box.dataset.nombre = j.nombre;
      return j.token; });
  }).catch(function(){ pcgCargando(false); err.textContent = 'No pudimos conectar. Revisa tu conexión.'; return null; }); }
function docYo(){ return C.docYo ? documento('yo') : Promise.resolve(''); }
// ── Inscripción individual ──
var quien = document.querySelector('[data-quien] .sel'); quien = quien ? quien.dataset.q : 'yo';
document.querySelectorAll('[data-quien] button').forEach(function(b){ b.addEventListener('click', function(){ if(b.disabled) return; quien = b.dataset.q;
  document.querySelectorAll('[data-quien] button').forEach(function(x){ x.classList.toggle('sel', x === b); });
  var h = document.querySelector('[data-hijo]'), y = document.querySelector('[data-yo]'); if(h) h.style.display = quien === 'hijo' ? 'block' : 'none'; if(y) y.style.display = quien === 'yo' ? 'block' : 'none'; }); });
var bi = $('btnIns');
if(bi) bi.addEventListener('click', function(){
  var err = $('insErr'); err.textContent = '';
  var f = function(k){ return document.querySelector("[data-f='" + k + "']"); };
  var edad = f('edad') ? f('edad').value.replace(/\D/g, '') : '', nombre = f('nombre') ? f('nombre').value.trim() : '', wa = f('whatsapp') ? f('whatsapp').value.trim() : '', cons = f('consiente') ? f('consiente').checked : false;
  if(quien === 'hijo' && !C.nombreDelDni && !nombre){ err.textContent = 'Escribe el nombre del alumno.'; return; }
  if(quien === 'hijo' && !cons){ err.textContent = 'Marca la casilla: confirma que eres el apoderado.'; return; }
  var paso = (quien === 'hijo' && C.exigeDni) ? documento('hijo') : (quien === 'yo' ? docYo() : Promise.resolve(''));
  paso.then(function(t){ if(t === null) return;
    var costo = Number(bi.dataset.costo || 0);
    var conf = costo > 0 ? pcgConfirmar({titulo: 'Inscribirme · ' + C.nombre, icono: '🏆', mensaje: 'La inscripción cuesta ' + fmt(costo) + ' y se paga de tu saldo Pichangol (tienes ' + fmt(C.saldo) + ').', confirmar: 'Pagar ' + fmt(costo) + ' e inscribirme', cancelar: 'Cancelar'}) : Promise.resolve(true);
    conf.then(function(ok){ if(!ok) return; pcgCargando('Procesando tu inscripción…'); bi.disabled = true;
      post('/web/torneo/' + encodeURIComponent(C.id) + '/inscribir', {quien: quien, nombre: nombre, edad: edad, whatsapp: wa, consiente: cons, doc_token: t || tok[quien] || ''})
        .then(function(j){ bi.disabled = false; if(j.ok) return exito(j, '¡Inscrito! 🏆'); pcgCargando(false); fallo(j, err); })
        .catch(function(){ bi.disabled = false; pcgCargando(false); fallo(null, err); }); }); }); });
// ── Fútbol: crear equipo ──
var bc = $('btnCrear');
if(bc) bc.addEventListener('click', function(){ var err = $('eqErr'); err.textContent = ''; var n = ($('eqNombre').value || '').trim();
  if(!n){ err.textContent = 'Ponle nombre al equipo.'; $('eqNombre').focus(); return; }
  docYo().then(function(t){ if(t === null) return; var parte = Number(bc.dataset.parte || 0);
    var conf = parte > 0 ? pcgConfirmar({titulo: 'Crear «' + n + '»', icono: '⚽', mensaje: 'La inscripción es ' + fmt(C.cuotaEquipo) + ' por equipo. Como capitán pones ahora tu parte: ' + fmt(parte) + ' de tu saldo (tienes ' + fmt(C.saldo) + '). Tus jugadores ponen la suya al entrar con tu código y el equipo queda inscrito cuando el pozo se completa.', confirmar: 'Pagar mi parte y crear', cancelar: 'Cancelar'}) : Promise.resolve(true);
    conf.then(function(ok){ if(!ok) return; pcgCargando(parte > 0 ? 'Poniendo tu parte…' : 'Creando tu equipo…'); bc.disabled = true;
      post('/web/torneo/' + encodeURIComponent(C.id) + '/equipo/crear', {nombre: n, doc_token: t || tok.yo || ''}).then(function(j){ bc.disabled = false; pcgCargando(false);
        if(!j.ok) return fallo(j, err);
        var url = location.origin + '/torneo/' + encodeURIComponent(C.id) + '?equipo=' + encodeURIComponent(j.codigo || '');
        pcgAvisar({titulo: '¡Equipo creado! ⚽', icono: '🏆', confirmar: 'Listo', html: "<p class='sub'>Comparte este código con tus jugadores para que se unan a tu equipo:</p><div style='font-size:30px;font-weight:900;letter-spacing:4px;color:#067A38;margin:8px 0'>" + esc(j.codigo) + "</div><p class='sub' style='overflow-wrap:anywhere'>" + esc(url) + "</p>"})
          .then(function(){ pcgRecargar('Actualizando…'); });
      }).catch(function(){ bc.disabled = false; pcgCargando(false); fallo(null, err); }); }); }); });
// ── Fútbol: unirme (código o tocando el equipo) ──
function unirme(body, nombre, parte, pozo, errEl){
  docYo().then(function(t){ if(t === null) return;
    var msg = parte < 0 ? (C.cuota ? 'Si al equipo le falta pozo, pones tu parte (hasta ' + fmt(C.cuotaJugador) + ') de tu saldo Pichangol (tienes ' + fmt(C.saldo) + '). Quedas en el plantel con tu cuenta.' : 'Quedarás en el plantel con tu cuenta y tu capitán recibirá el aviso.') : C.cuota ? (parte > 0 ? 'Pones tu parte: ' + fmt(parte) + ' de tu saldo (el equipo lleva ' + fmt(pozo) + ' de ' + fmt(C.cuotaEquipo) + '; tienes ' + fmt(C.saldo) + '). Quedas en el plantel con tu cuenta.' : 'El pozo del equipo ya está completo: entras sin pagar.') : 'Quedarás en el plantel con tu cuenta y tu capitán recibirá el aviso.';
    pcgConfirmar({titulo: nombre ? 'Unirme a «' + nombre + '»' : 'Unirme al equipo', icono: '🎽', mensaje: msg, confirmar: parte > 0 ? 'Pagar ' + fmt(parte) + ' y unirme' : (parte < 0 && C.cuota ? 'Unirme y pagar mi parte' : 'Unirme'), cancelar: 'Cancelar'}).then(function(ok){
      if(!ok) return; pcgCargando(parte !== 0 && C.cuota ? 'Poniendo tu parte…' : 'Uniéndote…'); body.doc_token = t || tok.yo || '';
      post('/web/torneo/' + encodeURIComponent(C.id) + '/equipo/unirme', body).then(function(j){ if(j.ok) return exito(j, '¡Te uniste! 🎽'); pcgCargando(false); fallo(j, errEl); })
        .catch(function(){ pcgCargando(false); fallo(null, errEl); }); }); }); }
document.addEventListener('click', function(ev){
  var u = ev.target.closest('[data-unirme]'); if(u){ unirme({equipo_id: u.dataset.unirme}, u.dataset.nombre, Number(u.dataset.parte || 0), Number(u.dataset.pozo || 0)); return; }
  var k = ev.target.closest('[data-completar]');
  if(k){ var falta = Number(k.dataset.falta || 0);
    pcgConfirmar({titulo: 'Completar el pozo', icono: '💰', mensaje: 'Pones los ' + fmt(falta) + ' que faltan de tu saldo (tienes ' + fmt(C.saldo) + ') y «' + k.dataset.nombre + '» queda inscrito.', confirmar: 'Pagar ' + fmt(falta), cancelar: 'Cancelar'}).then(function(ok){
      if(!ok) return; pcgCargando('Completando el pozo…');
      post('/web/torneo/' + encodeURIComponent(C.id) + '/equipo/' + encodeURIComponent(k.dataset.completar) + '/completar', {}).then(function(j){ if(j.ok) return exito(j, '¡Pozo completo! 🏆'); pcgCargando(false); fallo(j); })
        .catch(function(){ pcgCargando(false); fallo(null); }); }); return; }
  var cp = ev.target.closest('[data-copiar]');
  if(cp){ ev.preventDefault(); var url = location.origin + cp.getAttribute('href'); (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(function(){ pcgToast('Enlace copiado'); }, function(){ pcgAvisar({titulo: 'Enlace de tu equipo', mensaje: url}); }); }
});
var bcod = $('btnCod');
if(bcod) bcod.addEventListener('click', function(){ var v = ($('codEq').value || '').replace(/[^A-Za-z0-9]/g, '').toUpperCase(); $('codErr').textContent = '';
  if(!v){ $('codErr').textContent = 'Escribe el código del equipo.'; return; }
  unirme({codigo: v}, '', -1, 0, $('codErr')); });
})();
"""
