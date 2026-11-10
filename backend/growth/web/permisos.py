"""PERMISOS del modo anfitrión: UN solo lugar decide quién opera qué cancha.

- El DUEÑO (`pichangol_canchas.dueno` = su correo) puede todo en sus canchas
  (sus chequeos de siempre no cambian).
- Un ENCARGADO con rol Recepción (`web/encargados.py`) puede, SOLO en las
  canchas del local que le asignaron, las acciones de `ACCIONES["recepcion"]`.
  Cualquier otra cosa (plata, editar, cobros del club, cancelar con
  devolución, invitar a otros…) sigue pasando por los chequeos de dueño y le
  responde 404/403.

Uso en los endpoints: `canchas_para(email, accion)` (lista de canchas que ese
correo opera para esa acción) o `puede(email, cancha_id, accion)`; y, tras una
acción hecha por un encargado, `auditar(...)` la deja en su bitácora.
"""

from __future__ import annotations

import fidelidad
from web import datos, encargados

DUENO = "dueno"
# Acciones de la Recepción (claves estables: van en la bitácora).
VER_AGENDA = "ver_agenda"            # Hoy · Calendario · Reservas (con nombre/celular del jugador)
RESERVA_MANUAL = "reserva_manual"
QUITAR_MANUAL = "quitar_manual"      # deshacer una reserva MANUAL (no mueve plata)
BLOQUEAR = "bloquear"                # bloquear / desbloquear turnos
MARCAR_PAGO = "marcar_pago"          # cobrada en efectivo / por cobrar
NOSHOW = "noshow"
VOUCHERS = "vouchers"                # Pagos por confirmar: ver, aprobar, rechazar
ACCIONES = {
    encargados.ROL_RECEPCION: frozenset({VER_AGENDA, RESERVA_MANUAL, QUITAR_MANUAL, BLOQUEAR, MARCAR_PAGO, NOSHOW, VOUCHERS}),
}
# Pestañas de la cabecera del modo anfitrión que la Recepción NO usa.
TABS_SOLO_DUENO = frozenset({"ingresos", "canchas"})
# Ítems del menú /anfitrion que son del NEGOCIO del dueño (se ocultan a quien
# solo es encargado: Recepción no ve plata ni configura el club).
MENU_SOLO_DUENO = frozenset({"cobros-club", "reglas", "disponibilidad", "fijas", "reportes", "caja", "clientes",
                             "llenar", "recordatorios", "bonos"})


def _norm(email) -> str:
    return encargados.normalizar_correo(email)


def canchas_del_encargo(enc: dict, canchas_dueno: list[dict] | None = None) -> list[dict]:
    """Canchas del local de un encargo: las del dueño con el mismo
    `local_key` o con el `local_key` actual de las canchas ancla (si el dueño
    renombró el local, el encargo lo sigue). Solo canchas que HOY siguen
    siendo del dueño del encargo."""
    propias = canchas_dueno if canchas_dueno is not None else datos.canchas_de_dueno(enc["dueno"])
    propias = [c for c in propias if _norm(c.get("dueno")) == enc["dueno"]]
    anclas = set(enc.get("cancha_ids") or [])
    claves = {enc["local_key"]} | {fidelidad.local_key(c) for c in propias if c["id"] in anclas}
    return [c for c in propias if fidelidad.local_key(c) in claves]


def _delegadas(email: str) -> list[tuple[dict, dict]]:
    """[(cancha, encargo)] de los locales donde este correo es encargado activo."""
    out: list[tuple[dict, dict]] = []
    por_dueno: dict[str, list[dict]] = {}
    for enc in encargados.activos_de(email):
        if enc["dueno"] not in por_dueno:
            por_dueno[enc["dueno"]] = datos.canchas_de_dueno(enc["dueno"])
        for c in canchas_del_encargo(enc, por_dueno[enc["dueno"]]):
            out.append((c, enc))
    return out


def canchas_operables(email: str) -> dict[str, str]:
    """{cancha_id: rol} de todo lo que este correo opera: "dueno" en las suyas,
    el rol del encargo en las de los locales donde ayuda."""
    email = _norm(email)
    if not email:
        return {}
    out = {c["id"]: DUENO for c in datos.canchas_de_dueno(email)}
    for c, enc in _delegadas(email):
        out.setdefault(c["id"], enc["rol"])
    return out


def permitido(rol: str | None, accion: str) -> bool:
    if rol == DUENO:
        return True
    return bool(rol) and accion in ACCIONES.get(rol, frozenset())


def canchas_para(email: str, accion: str) -> list[dict]:
    """Canchas que este correo opera para [accion]: las suyas primero (mismo
    orden que `canchas_de_dueno`) y luego las de los locales donde ayuda."""
    email = _norm(email)
    if not email:
        return []
    out = list(datos.canchas_de_dueno(email))
    vistos = {c["id"] for c in out}
    for c, enc in _delegadas(email):
        if c["id"] not in vistos and permitido(enc["rol"], accion):
            out.append(c)
            vistos.add(c["id"])
    return out


def alcance_delegado(email: str, accion: str) -> dict[str, set[str]]:
    """{dueño: {cancha_id…}} de los locales AJENOS donde este correo puede
    [accion] (sin las suyas). Para lo que se guarda por dueño (vouchers)."""
    email = _norm(email)
    out: dict[str, set[str]] = {}
    for c, enc in _delegadas(email):
        if enc["dueno"] != email and permitido(enc["rol"], accion):
            out.setdefault(enc["dueno"], set()).add(c["id"])
    return out


def encargo_en(email: str, cancha_id: str) -> dict | None:
    """El encargo ACTIVO que le da a este correo acceso a esa cancha (None si
    no es encargado ahí; el dueño no tiene encargo)."""
    for c, enc in _delegadas(_norm(email)):
        if c["id"] == cancha_id:
            return enc
    return None


def rol_en(email: str, cancha_id: str) -> str | None:
    return canchas_operables(email).get(cancha_id)


def puede(email: str, cancha_id: str, accion: str) -> bool:
    return permitido(rol_en(email, cancha_id), accion)


def es_dueno_de(email: str, c: dict | None) -> bool:
    return bool(c) and _norm(c.get("dueno")) == _norm(email)


def es_solo_encargado(email: str) -> bool:
    """Ayuda en algún local y NO tiene canchas propias: ve el modo anfitrión
    recortado (sin plata ni configuración). Barato para el dueño común: si no
    tiene encargos activos no consulta sus canchas."""
    email = _norm(email)
    if not email or not encargados.activos_de(email):
        return False
    return not datos.canchas_de_dueno(email)


def tabs_ocultas(email: str) -> frozenset:
    return TABS_SOLO_DUENO if es_solo_encargado(email) else frozenset()


def auditar(actor: str, cancha: dict | None, accion: str, ref: str = "", detalle: dict | None = None) -> None:
    """Si [actor] hizo [accion] en [cancha] como ENCARGADO (no como dueño),
    queda en la bitácora del dueño. Best-effort."""
    if not cancha or es_dueno_de(actor, cancha):
        return
    enc = encargo_en(actor, cancha["id"])
    if enc is None:
        return
    encargados.registrar_accion(encargado_id=enc["id"], dueno=enc["dueno"], actor=actor, accion=accion,
                                cancha_id=cancha["id"], ref=ref, detalle=detalle)
