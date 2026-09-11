"""Catálogos de la CANCHA, ESPEJO de los del APK (`lib/models/models.dart`,
`lib/theme.dart`, `editar_cancha_screen.dart`). La web edita con las MISMAS
opciones que el app (regla del director: nada de campos de texto libre, todo
por selección con opciones curadas) y las mismas claves se guardan en
`pichangol_canchas`, así el app y la web leen lo mismo.

Al cambiar un catálogo en el app hay que cambiarlo aquí (y viceversa).
"""

from __future__ import annotations

# Deportes que el app OFRECE al dueño (`deportesActivos`): pádel se retiró del
# piloto pero sigue en datos viejos, por eso se acepta si la cancha ya lo tenía.
DEPORTES_ACTIVOS = ["futbol", "tenis", "pickleball", "voley", "basquet"]
DEPORTES_LEGADO = ["padel"]

# Tipo de piso por deporte (`superficiesDe`). Se guarda la ETIQUETA (texto) en
# `superficie`, igual que el app.
SUPERFICIES = {
    "futbol": ["Grass sintético", "Loza", "Grass natural"],
    "tenis": ["Arcilla", "Dura", "Césped", "Loza"],
    "padel": ["Cristal", "Muro"],
    "pickleball": ["Dura", "Loza"],
    "voley": ["Loza", "Arena", "Parquet"],
    "basquet": ["Loza", "Parquet", "Cemento"],
}

# Amenidades GRATIS del local (`amenidadesCatalogo`): clave → (nombre, ícono).
AMENIDADES = {
    "vestuario": ("Vestuario", "👕"),
    "duchas": ("Duchas", "🚿"),
    "parking": ("Estacionamiento", "🅿️"),
    "luces": ("Iluminación", "💡"),
    "techado": ("Techada", "🏠"),
    "cafeteria": ("Cafetería", "☕"),
    "wifi": ("Wi-Fi", "📶"),
    "alquiler": ("Alquiler de equipo", "🎾"),
}

# Servicios EXTRA de pago (`ServicioExtra.catalogo`): clave → (nombre, ícono).
SERVICIOS_EXTRA = {
    "arbitro": ("Árbitro", "🧑‍⚖️"),
    "pelotero": ("Pelotero (recoge pelotas)", "🏃"),
    "pelota": ("Alquiler de pelota", "🎾"),
    "pecheras": ("Petos / pecheras", "🦺"),
    "hidratacion": ("Hidratación", "💧"),
    "parrilla": ("Parrilla / grill", "🔥"),
}

# Chips del formulario del app.
DESCUENTOS_VALLE = [0, 10, 15, 20, 30]   # "hora feliz" (% de descuento)
SENAS = [0, 20, 30, 50]                 # seña (% del precio)
DURACIONES = [60, 90, 120]              # duración del turno (min)
HORAS = [f"{h:02d}:00" for h in range(24)]
MAX_FOTOS = 8
NOMBRE_MAX = 80


def deporte_principal(deportes: list[str]) -> str:
    """El deporte PRINCIPAL es el primero de `deportesActivos` que la cancha
    ofrece (espejo del getter `_deporte` del app)."""
    for d in DEPORTES_ACTIVOS:
        if d in deportes:
            return d
    return deportes[0] if deportes else "futbol"


def etiqueta_duracion(minutos: int) -> str:
    return {60: "1 hora", 90: "1h 30min", 120: "2 horas"}.get(minutos, f"{minutos} min")
