"""PREFERENCIAS DE AVISOS por correo de la cuenta (rediseño "Mi perfil" del
modo anfitrión, 16-nov-2026).

Cuatro interruptores que el dueño maneja en `/anfitrion/perfil`:

- `reservas`  · Nuevas reservas (push "Nueva reserva 📅/🎟️/🎁" al dueño).
- `pagos`     · Pagos por confirmar (push "Confirma un pago 🧾": un jugador
  subió su comprobante del cobro directo o de su parte de un pago dividido).
- `academia`  · Cuotas de la academia (push al profe: "Nuevo alumno 🎓",
  "N alumnos nuevos 🎓", "Cuota pagada 💰", "Pago por confirmar 💜",
  "Pago confirmado solo ✅").
- `novedades` · Novedades de la marca (todo aviso con `tipo` novedades /
  marketing / promo, y los correos `aviso` que se encolen con
  `datos["categoria"] = "novedades"`).

Se guardan en `stores.avisos_prefs[correo]` (viaja en el snapshot, sin SQL).
Por defecto TODO encendido: una cuenta sin fila recibe todo.

Qué NUNCA se apaga (lo necesita para operar la plata del jugador): recibos y
constancias de pago por correo (`correos.al_pago`), devoluciones que el dueño
debe hacer ("Devuelve un pago 💸"), pagos que vencieron sin revisar, reservas
canceladas o reprogramadas, avisos del Plan Academia, y todo lo que el usuario
recibe como JUGADOR o alumno ("Reserva confirmada", recordatorios de su propia
cuota…). Por eso la clasificación va por el TÍTULO exacto del aviso al dueño,
no por el `tipo` (el mismo `tipo="reserva"` lleva avisos al jugador).

Límite conocido: los push que el APK escribe directo desde el teléfono en
`pichangol_avisos` (reservas hechas en el app) no pasan por aquí.
"""

from __future__ import annotations

from datetime import datetime, timezone

TIPOS = ("reservas", "pagos", "academia", "novedades")
# Lo operativo nace encendido; las NOVEDADES (promociones) nacen APAGADAS: se
# envían solo con consentimiento expreso (Ley 29733, decisión del 16-nov-2026).
DEFECTO = {"novedades": False}

# (prefijo del título, categoría). Prefijos EXACTOS de los avisos al dueño;
# `tests/test_anfitrion_perfil.py` fija cada uno contra el código que lo envía.
_TITULOS: tuple[tuple[str, str], ...] = (
    ("Nueva reserva", "reservas"),
    ("Confirma un pago", "pagos"),
    ("Nuevo alumno", "academia"),
    ("Cuota pagada", "academia"),
    ("Pago por confirmar", "academia"),
    ("Pago confirmado solo", "academia"),
)
_TIPOS_NOVEDADES = {"novedades", "marketing", "promo"}


def _store():
    from db.store import stores
    return stores


def _norm(email) -> str:
    return str(email or "").strip().lower()


def prefs(email: str) -> dict[str, bool]:
    """{tipo: bool} con los cuatro tipos (lo que no está guardado = encendido)."""
    fila = _store().avisos_prefs.get(_norm(email)) or {}
    return {t: (fila[t] is not False) if t in fila else DEFECTO.get(t, True) for t in TIPOS}


def quiere(email: str, tipo: str) -> bool:
    """¿La cuenta quiere este tipo de aviso? Tipo desconocido = sí (nunca se
    calla un aviso por un error de clasificación)."""
    if tipo not in TIPOS:
        return True
    try:
        return prefs(email).get(tipo, True)
    except Exception:  # noqa: BLE001 — un fallo nunca apaga avisos
        return True


def guardar(email: str, cambios: dict) -> dict[str, bool]:
    """Aplica {tipo: bool}; ignora claves desconocidas. Devuelve el estado."""
    em = _norm(email)
    if not em or "@" not in em:
        raise ValueError("correo")
    st = _store()
    fila = dict(st.avisos_prefs.get(em) or {})
    for t, v in (cambios or {}).items():
        if t in TIPOS:
            fila[t] = bool(v)
    fila["t"] = datetime.now(timezone.utc).isoformat()
    st.avisos_prefs[em] = fila
    return prefs(em)


def categoria_push(titulo: str, tipo: str = "") -> str | None:
    """Categoría de un push (o None = siempre se envía)."""
    if (tipo or "").strip().lower() in _TIPOS_NOVEDADES:
        return "novedades"
    t = (titulo or "").strip()
    for pre, cat in _TITULOS:
        if t.startswith(pre):
            return cat
    # "3 alumnos nuevos 🎓" (matrícula familiar): el número va delante.
    if (tipo or "") == "academia" and "alumnos nuevos" in t:
        return "academia"
    return None


def silenciado(email: str, titulo: str, tipo: str = "") -> bool:
    """True si este push NO debe enviarse por la preferencia del destinatario."""
    try:
        cat = categoria_push(titulo, tipo)
        return bool(cat) and not quiere(email, cat)
    except Exception:  # noqa: BLE001
        return False
