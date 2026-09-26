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
# Los SERVICIOS EXTRA ya no son un catálogo fijo: viven en `servicios_extra.py`
# (catálogo global editable desde la torre, `GET /config/servicios-extra`).

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


# ── Marketplace (`Producto.categorias`) ──
CATEGORIAS_PRODUCTO = {
    "raquetas": ("Raquetas", "🎾"), "pelotas": ("Pelotas", "⚽"), "indumentaria": ("Indumentaria", "👕"),
    "calzado": ("Calzado", "👟"), "accesorios": ("Accesorios", "🎒"), "nutricion": ("Nutrición", "🥤"),
    "otros": ("Otros", "📦"),
}
MONEDAS = ["S/", "$", "Bs"]

# ── Academias (`deportesAcademia`, `TipoPlan`, redes de `crear_academia_screen`) ──
DEPORTES_ACADEMIA = ["futbol", "tenis", "pickleball", "voley", "basquet", "natacion"]
TIPOS_PLAN = {"mensual": "Mensualidad", "prepago": "Paquete de meses", "porClase": "Por clase"}
MESES_PREPAGO = [2, 3, 6, 12]
FRECUENCIAS = [0, 1, 2, 3, 4, 5]          # veces por semana (0 = plan simple)
DURACIONES_CLASE = ["45 min", "1 h", "1 h 30 min", "2 h"]
REDES = {"instagram": "Instagram", "facebook": "Facebook", "tiktok": "TikTok", "youtube": "YouTube", "web": "Web"}
DESCUENTOS_ACADEMIA = [0, 5, 10, 15, 20, 25]   # % hermanos / prepago
MESES_MIN_PREPAGO = [1, 2, 3, 6]
TEL_LONGITUD = {"PE": 9, "BO": 8, "EC": 9}      # `PaisConfig.telLongitud`
TEL_PREFIJO = {"PE": "51", "BO": "591", "EC": "593"}
GEO_LABELS = {"PE": ["Departamento", "Provincia", "Distrito"], "BO": ["Departamento", "Provincia", "Municipio"],
              "EC": ["Provincia", "Cantón", "Parroquia"]}


# ── Campeonatos (`crear_campeonato_screen`, `FormatoTorneo`, `Natacion`) ──
# El asistente del app ofrece TODOS los deportes de `Deporte.values` (incluido pádel).
DEPORTES_CAMPEONATO = ["futbol", "tenis", "padel", "pickleball", "voley", "basquet", "natacion"]
DEPORTES_CIRCUITO = ["tenis", "padel", "pickleball"]
# (etiqueta, edadMin, edadMax) = `catalogoCategorias`.
CATEGORIAS_CAMPEONATO = [
    ("Sub-8", None, 8), ("Sub-10", None, 10), ("Sub-12", None, 12), ("Sub-14", None, 14), ("Sub-16", None, 16),
    ("Sub-18", None, 18), ("Sub-21", None, 21), ("Sub-23", None, 23),
    ("+35 (Máster)", 35, None), ("+40 (Máster)", 40, None), ("+45 (Máster)", 45, None), ("+50 (Máster)", 50, None),
    ("Abierta / Libre", None, None),
]
# Formato por defecto y formatos ofrecidos por deporte (`_formatoDe` / `_formatosDe`).
def formato_por_defecto(deporte: str) -> str:
    return "tiempos" if deporte == "natacion" else ("liga" if deporte == "futbol" else "eliminacion")


def formatos_de(deporte: str) -> list[str]:
    return ["tiempos"] if deporte == "natacion" else ["eliminacion", "liga", "grupos"]


FORMATO_SUB = {"eliminacion": "Llave: el ganador avanza (ideal tenis/pádel).",
               "liga": "Todos contra todos + tabla (ideal fútbol).",
               "grupos": "Fase de grupos (cada equipo juega al menos 2 o 3 partidos) y luego llave con los 2 primeros de cada grupo.",
               "tiempos": "Cada nadador registra su TIEMPO por prueba; se rankea del más rápido al más lento."}
# Temas del arte IA del afiche (`_cambiarFondo`): clave → etiqueta.
AFICHE_TEMAS = [("", "Nocturno ⭐"), ("claro", "Fondo claro"), ("cancha", "Solo la cancha"), ("amanecer", "Amanecer"), ("celebracion", "Celebración")]
AFICHE_VARIANTES = 5
