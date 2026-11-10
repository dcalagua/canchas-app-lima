"""Íconos de línea del rediseño azul (nov-2026, PDF del diseñador).

SVG en línea, 24×24, trazo 2 y `currentColor`: toman el color del texto que los
rodea (azul en las pastillas de deporte y el buscador, blanco en las franjas
azules). Reemplazan a los emoji en la cabecera y en las secciones de la
portada; los emoji siguen donde el diseño no dice nada (menús, avisos).

Uso: `iconos.svg("futbol")` o `iconos.svg("tenis", 20, clase="ico")`. Una
clave desconocida devuelve "" (quien llama decide el respaldo).
"""

from __future__ import annotations

# Solo el contenido del <svg> (paths); `svg()` pone el envoltorio.
_I: dict[str, str] = {
    # ── deportes (pastillas de la cabecera) ──
    "todas": "<rect x='3.5' y='3.5' width='7' height='7' rx='1.6'/><rect x='13.5' y='3.5' width='7' height='7' rx='1.6'/>"
             "<rect x='3.5' y='13.5' width='7' height='7' rx='1.6'/><rect x='13.5' y='13.5' width='7' height='7' rx='1.6'/>",
    "futbol": "<circle cx='12' cy='12' r='9'/><path d='M12 7.6l3.6 2.6-1.4 4.2H9.8L8.4 10.2z'/>"
              "<path d='M12 7.6V3M15.6 10.2l4.3-1.4M14.2 14.4l2.7 3.7M9.8 14.4l-2.7 3.7M8.4 10.2L4.1 8.8'/>",
    "tenis": "<circle cx='12' cy='12' r='9'/><path d='M5.7 5.6c3.4 3.6 3.4 9.2 0 12.8M18.3 5.6c-3.4 3.6-3.4 9.2 0 12.8'/>",
    "padel": "<rect x='6' y='2.5' width='12' height='13.5' rx='6'/><path d='M10.6 16v5.5h2.8V16'/><path d='M10 7h.01M14 7h.01M12 9.5h.01M10 12h.01M14 12h.01' stroke-width='2.4'/>",
    "futsal": "<circle cx='14' cy='12' r='6.5'/><path d='M14 8.6l2.4 1.8-.9 2.8h-3l-.9-2.8z'/><path d='M2.5 9h4M2 12.5h4.5M3 16h4'/>",
    "pickleball": "<rect x='4' y='2.5' width='11' height='12.5' rx='4.2'/><path d='M8.2 15v5.5h2.6V15'/><circle cx='18.5' cy='17.5' r='3'/><path d='M17.6 16.6h.01M19.4 18.4h.01' stroke-width='2.2'/>",
    "voley": "<circle cx='12' cy='12' r='9'/><path d='M12 3c-1 4.5.2 8 4.2 10.6M20.6 9.5c-4.4-.6-8 1-10.4 4.8M7.4 19.8c.9-4.4 3.4-7.6 7.6-8.6'/>",
    "basquet": "<circle cx='12' cy='12' r='9'/><path d='M12 3v18M3 12h18M5.6 5.6c2.7 2.8 2.7 10 0 12.8M18.4 5.6c-2.7 2.8-2.7 10 0 12.8'/>",
    "natacion": "<path d='M3 16c1.5 1 3 1 4.5 0s3-1 4.5 0 3 1 4.5 0 3-1 4.5 0M3 20c1.5 1 3 1 4.5 0s3-1 4.5 0 3 1 4.5 0 3-1 4.5 0'/>"
                "<circle cx='16' cy='6' r='2'/><path d='M6 13l4-5 3 3 3-1'/>",
    "academias": "<path d='M2.5 9.2L12 4.5l9.5 4.7L12 14z'/><path d='M6.5 11.4v4.4c0 1.4 2.5 3.2 5.5 3.2s5.5-1.8 5.5-3.2v-4.4M21.5 9.2v5.3'/>",
    # ── buscador ──
    "pin": "<path d='M12 21s-6.5-6-6.5-11.2A6.5 6.5 0 0 1 12 3.3a6.5 6.5 0 0 1 6.5 6.5C18.5 15 12 21 12 21z'/><circle cx='12' cy='9.8' r='2.4'/>",
    "calendario": "<rect x='3.5' y='5' width='17' height='15.5' rx='2.2'/><path d='M3.5 9.8h17M8 3v4M16 3v4'/>"
                  "<path d='M8 13.5h.01M12 13.5h.01M16 13.5h.01M8 17h.01M12 17h.01' stroke-width='2.6'/>",
    "reloj": "<circle cx='12' cy='12' r='9'/><path d='M12 7v5.2l3.4 2'/>",
    "lupa": "<circle cx='11' cy='11' r='6.5'/><path d='M20 20l-4.2-4.2'/>",
    "filtros": "<path d='M4 6.5h9M17 6.5h3M4 17.5h3M11 17.5h9'/><circle cx='15' cy='6.5' r='2.2'/><circle cx='9' cy='17.5' r='2.2'/>",
    "mapa": "<path d='M9 4.5l-5.5 2v13l5.5-2 6 2 5.5-2v-13l-5.5 2z'/><path d='M9 4.5v13M15 6.5v13'/>",
    "chat": "<path d='M20.5 12a8 8 0 0 1-11.7 7.1L3.5 20.5l1.4-4.9A8 8 0 1 1 20.5 12z'/>",
    "bodega": "<path d='M4 8.5h16l-1.3 11a1.6 1.6 0 0 1-1.6 1.4H6.9a1.6 1.6 0 0 1-1.6-1.4z'/><path d='M8.5 8.5V7a3.5 3.5 0 0 1 7 0v1.5'/>",
    "flecha": "<path d='M5 12h14M13 6l6 6-6 6'/>",
    # ── secciones de la portada ──
    "cerca": "<rect x='6.5' y='2.5' width='11' height='19' rx='2.4'/><path d='M12 15.4s-3-2.7-3-5a3 3 0 0 1 6 0c0 2.3-3 5-3 5z'/><path d='M10.5 18.6h3'/>",
    "horario": "<rect x='3' y='4.5' width='13.5' height='13' rx='2'/><path d='M3 8.8h13.5M7 2.8v3.4M12.5 2.8v3.4'/>"
               "<circle cx='17' cy='16.5' r='4.5'/><path d='M17 14.6v2.1l1.4.9'/>",
    "silbato": "<path d='M9 9.5h11.5v3.2l-6 1.8a5 5 0 1 1-5.5-5z'/><circle cx='9' cy='14.5' r='1.6'/><path d='M14 4.5l.8 2.4M18.5 4.8l-1.4 2.2M10.4 5.2l1.6 1.9'/>",
    "comparar": "<circle cx='8.5' cy='8' r='3.2'/><path d='M3 19.5c.6-3.3 2.8-5 5.5-5s4.9 1.7 5.5 5'/><circle cx='16.5' cy='9' r='2.6'/><path d='M15 14.4c2.6-.4 4.9 1.2 5.6 4.6'/>",
    "tarjeta": "<rect x='2.5' y='5' width='19' height='14' rx='2.2'/><path d='M2.5 9.5h19M6 15h4'/>",
    "escudo": "<path d='M12 3l7.5 3v5.5c0 4.6-3.2 8.3-7.5 9.5-4.3-1.2-7.5-4.9-7.5-9.5V6z'/><path d='M8.6 12.2l2.4 2.4 4.6-4.8'/>",
    "recibo": "<path d='M6 2.8h12v18.4l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4-2 1.4z'/><path d='M9 8h6M9 11.5h6M9 15h3.5'/>",
    "estrella": "<path d='M12 3.5l2.6 5.3 5.9.8-4.3 4.2 1 5.8L12 16.8l-5.2 2.8 1-5.8-4.3-4.2 5.9-.8z'/>",
    "bono": "<rect x='3' y='6.5' width='18' height='11' rx='2'/><path d='M9 6.5v11' stroke-dasharray='2 2'/><path d='M13 12h4.5'/>",
    "whatsapp": "<path d='M20.5 11.7a8.4 8.4 0 0 1-12.4 7.4L3.5 20.4l1.3-4.4a8.4 8.4 0 1 1 15.7-4.3z'/>"
                "<path d='M9 8.6c.2 2.8 2.4 5.6 5.6 6.4l1.3-1.4-1.9-1.2-.9.8c-1-.4-2-1.4-2.4-2.4l.8-.9-1.1-1.9z'/>",
    "libro": "<path d='M12 6.5c-2-1.6-5-2-8.5-1.5v13c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5v-13C17 4.5 14 4.9 12 6.5z'/><path d='M12 6.5v13'/>",
    # ── amenidades (chips rápidos) ──
    "cafeteria": "<path d='M4 9h12v4.5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z'/><path d='M16 10.5h1.5a2.3 2.3 0 0 1 0 4.6H16M8 3.5c-.8 1 .8 1.8 0 3M12 3.5c-.8 1 .8 1.8 0 3'/>",
    "duchas": "<path d='M4 20V8a4 4 0 0 1 8 0'/><path d='M9 8.5h6M9.5 12v.01M12 13v.01M14.5 12v.01M10.5 15.5v.01M13.5 15.5v.01' stroke-width='2.4'/>",
    "parking": "<rect x='3.5' y='3.5' width='17' height='17' rx='3'/><path d='M9.5 17V7.5h3.4a2.9 2.9 0 0 1 0 5.8H9.5'/>",
    "vestuario": "<path d='M8.5 3.5L4 6.5l2 3.5 2-1.2V20.5h8V8.8l2 1.2 2-3.5-4.5-3c-.6 1.4-2 2.3-3.5 2.3s-2.9-.9-3.5-2.3z'/>",
    "luces": "<path d='M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z'/>",
    "techado": "<path d='M2.5 11L12 4l9.5 7'/><path d='M5 9.5V20h14V9.5'/>",
    "wifi": "<path d='M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.6 16a5 5 0 0 1 6.8 0'/><path d='M12 19.5h.01' stroke-width='3'/>",
    "alquiler": "<circle cx='9' cy='9' r='5.5'/><path d='M12.9 12.9L19 19M16.5 6.5l2 2'/>",
}

# Amenidades del catálogo (claves del APP y de la web) → ícono.
AMENIDAD = {"cafeteria": "cafeteria", "duchas": "duchas", "parking": "parking", "estacionamiento": "parking",
            "vestuario": "vestuario", "vestuarios": "vestuario", "luces": "luces", "iluminacion": "luces",
            "techado": "techado", "techada": "techado", "wifi": "wifi", "alquiler": "alquiler"}


def svg(nombre: str, tam: int = 22, clase: str = "ic-l", grueso: float = 2.0) -> str:
    """El ícono `nombre` como <svg> en línea (vacío si no existe)."""
    cuerpo = _I.get(nombre)
    if not cuerpo:
        return ""
    return (f"<svg class='{clase}' viewBox='0 0 24 24' width='{tam}' height='{tam}' fill='none' stroke='currentColor' "
            f"stroke-width='{grueso}' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'>{cuerpo}</svg>")


def existe(nombre: str) -> bool:
    return nombre in _I
