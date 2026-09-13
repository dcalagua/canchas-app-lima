"""DATOS DE LA EMPRESA (razón social, RUC, dirección, WhatsApp, correo,
horario) — CONFIGURABLES desde la torre de control (`/admin` → Comunicación →
"Datos de la empresa"), por ambiente (cada torre guarda los suyos en su
snapshot `stores.config`, claves `empresa_*`).

Es la fuente ÚNICA de esos datos para todo lo público: secciones de comercio
de la portada (`legal/home.html` lleva marcadores `{{EMPRESA}}`…), el pie de
todas las páginas web (`web/ui.footer`), las páginas legales (`legal/router`),
el Libro de Reclamaciones y los textos de "dudas" del checkout. Nada de esto
debe volver a escribirse a mano en HTML: Culqi/INDECOPI/Play revisan que la
razón social, el RUC y el contacto sean los reales y el director los cambia
desde la torre sin publicar código.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape

from db.store import CONFIG_DEFAULT, stores

# clave de config → (etiqueta en la torre, ayuda)
CAMPOS: dict[str, tuple[str, str]] = {
    "empresa_razon_social": ("Razón social", "Nombre legal del operador (sale en términos, pie y contacto)."),
    "empresa_doc_etiqueta": ("Tipo de documento fiscal", "RUC (Perú/Ecuador) o NIT (Bolivia)."),
    "empresa_ruc": ("Número de documento fiscal", "Solo dígitos (RUC de 11 en Perú, 13 en Ecuador; NIT en Bolivia)."),
    "empresa_direccion": ("Dirección fiscal", "Domicilio completo, con ciudad y país."),
    "empresa_ciudad": ("Ciudad (forma corta)", "Lo que va en el pie: p. ej. «San Isidro, Lima, Perú»."),
    "empresa_whatsapp": ("WhatsApp", "Número internacional SIN «+» ni espacios (51987654321)."),
    "empresa_correo": ("Correo de contacto", "Soporte, devoluciones y Libro de Reclamaciones."),
    "empresa_correo_privacidad": ("Correo de privacidad (opcional)", "Derechos ARCO y eliminar cuenta. Vacío = el de contacto."),
    "empresa_horario": ("Horario de atención", "Texto libre corto: «Lun a Sáb, 9:00 a 19:00»."),
}

_EMAIL = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
_MAX = {"empresa_razon_social": 120, "empresa_doc_etiqueta": 12, "empresa_ruc": 20, "empresa_direccion": 200,
        "empresa_ciudad": 80, "empresa_whatsapp": 15, "empresa_correo": 120, "empresa_correo_privacidad": 120,
        "empresa_horario": 80}


def _cfg(clave: str) -> str:
    """Valor guardado (un "" guardado a propósito VALE, p. ej. correo de
    privacidad vacío = usar el de contacto); solo sin clave cae al default."""
    if clave in stores.config:
        return (stores.config.get(clave) or "").strip()
    return CONFIG_DEFAULT.get(clave, "").strip()


def valores() -> dict[str, str]:
    """Valores CRUDOS tal como están guardados (para el formulario de la torre)."""
    return {k: _cfg(k) for k in CAMPOS}


def _bonito_whatsapp(digitos: str) -> str:
    """51967923419 → «+51 967 923 419» (código de país + grupos de 3)."""
    d = re.sub(r"\D", "", digitos)
    if not d:
        return ""
    for cod in ("593", "591", "51"):
        if d.startswith(cod) and len(d) > len(cod):
            local, pais = d[len(cod):], cod
            break
    else:
        pais, local = d[:2], d[2:]
    grupos = [local[i:i + 3] for i in range(0, len(local), 3)]
    return f"+{pais} " + " ".join(grupos)


def datos() -> dict[str, str]:
    """Datos LISTOS para pintar (ya escapados para HTML) + derivados:
    `wa_url` (https://wa.me/…), `whatsapp_bonito`, `correo_privacidad`
    (cae al de contacto), `anio` (© actual)."""
    v = valores()
    wa = re.sub(r"\D", "", v["empresa_whatsapp"])
    correo = v["empresa_correo"]
    return {
        "razon_social": escape(v["empresa_razon_social"]),
        "doc_etiqueta": escape(v["empresa_doc_etiqueta"] or "RUC"),
        "ruc": escape(v["empresa_ruc"]),
        "direccion": escape(v["empresa_direccion"]),
        "ciudad": escape(v["empresa_ciudad"] or v["empresa_direccion"]),
        "whatsapp": wa,
        "whatsapp_bonito": escape(_bonito_whatsapp(wa)),
        "wa_url": f"https://wa.me/{wa}" if wa else "",
        "correo": escape(correo),
        "correo_privacidad": escape(v["empresa_correo_privacidad"] or correo),
        "horario": escape(v["empresa_horario"]),
        "anio": str(datetime.now(timezone.utc).year),
    }


# Marcadores que acepta `legal/home.html` (y cualquier plantilla HTML).
def _marcadores() -> dict[str, str]:
    d = datos()
    return {
        "{{EMPRESA}}": d["razon_social"], "{{DOC_ETIQUETA}}": d["doc_etiqueta"], "{{RUC}}": d["ruc"],
        "{{DIRECCION}}": d["direccion"], "{{CIUDAD}}": d["ciudad"], "{{WA_URL}}": d["wa_url"],
        "{{WHATSAPP}}": d["whatsapp_bonito"], "{{CORREO}}": d["correo"],
        "{{CORREO_PRIVACIDAD}}": d["correo_privacidad"], "{{HORARIO}}": d["horario"], "{{ANIO}}": d["anio"],
    }


def rellenar(html: str) -> str:
    """Sustituye los marcadores `{{…}}` de una plantilla por los datos vigentes.
    Se hace con `replace` (no `str.format`): el HTML trae CSS con llaves."""
    for k, v in _marcadores().items():
        html = html.replace(k, v)
    return html


def validar(cambios: dict[str, str]) -> dict[str, str]:
    """Normaliza y valida lo que manda la torre. Devuelve {clave: valor}
    listo para guardar o lanza ValueError con el motivo (en español)."""
    limpio: dict[str, str] = {}
    for clave, (etiqueta, _) in CAMPOS.items():
        if clave not in cambios:
            continue
        val = " ".join(str(cambios[clave] or "").split())  # colapsa espacios y saltos
        if len(val) > _MAX[clave]:
            raise ValueError(f"{etiqueta}: máximo {_MAX[clave]} caracteres")
        if clave == "empresa_whatsapp":
            val = re.sub(r"\D", "", val)
            if val and not 8 <= len(val) <= 15:
                raise ValueError("WhatsApp: escribe el número internacional sin «+» (8 a 15 dígitos)")
        elif clave == "empresa_ruc":
            val = re.sub(r"\s", "", val)
            if val and not val.isalnum():
                raise ValueError("Documento fiscal: solo letras y dígitos")
        elif clave in ("empresa_correo", "empresa_correo_privacidad"):
            val = val.lower()
            if val and not _EMAIL.match(val):
                raise ValueError(f"{etiqueta}: correo inválido")
        if clave in ("empresa_razon_social", "empresa_correo", "empresa_ruc", "empresa_direccion") and not val:
            raise ValueError(f"{etiqueta}: es obligatorio (lo revisan Culqi e INDECOPI)")
        limpio[clave] = val
    return limpio


def guardar(cambios: dict[str, str]) -> dict[str, str]:
    """Valida y persiste en `stores.config` (el middleware guarda el snapshot)."""
    limpio = validar(cambios)
    stores.config.update(limpio)
    return valores()
