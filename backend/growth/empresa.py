"""DATOS DE LA EMPRESA (razón social, RUC, dirección, WhatsApp POR PAÍS,
correo, horario) — CONFIGURABLES desde la torre de control (`/admin` →
Comunicación → "Datos de la empresa"), por ambiente (cada torre guarda los
suyos en su snapshot `stores.config`, claves `empresa_*`; el WhatsApp usa las
claves `contacto_whatsapp_pe|ec|bo`, las MISMAS que el APK → una sola fuente).

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

# WhatsApp por país (regla multi-país del director): (clave iso, nombre,
# código internacional, bandera). Orden = orden en que se listan en la web.
PAISES: tuple[tuple[str, str, str, str], ...] = (
    ("pe", "Perú", "51", "🇵🇪"), ("ec", "Ecuador", "593", "🇪🇨"), ("bo", "Bolivia", "591", "🇧🇴"))
_CLAVE_WA = {iso: f"contacto_whatsapp_{iso}" for iso, *_ in PAISES}

# clave de config → (etiqueta en la torre, ayuda)
CAMPOS: dict[str, tuple[str, str]] = {
    "empresa_razon_social": ("Razón social", "Nombre legal del operador (sale en términos, pie y contacto)."),
    "empresa_doc_etiqueta": ("Tipo de documento fiscal", "RUC (Perú/Ecuador) o NIT (Bolivia)."),
    "empresa_ruc": ("Número de documento fiscal", "Solo dígitos (RUC de 11 en Perú, 13 en Ecuador; NIT en Bolivia)."),
    "empresa_direccion": ("Dirección fiscal", "Domicilio completo, con ciudad y país."),
    "empresa_ciudad": ("Ciudad (forma corta)", "Lo que va en el pie: p. ej. «San Isidro, Lima, Perú»."),
    "contacto_whatsapp_pe": ("WhatsApp Perú (+51)", "Número LOCAL sin código de país. El mismo que usa el app."),
    "contacto_whatsapp_ec": ("WhatsApp Ecuador (+593)", "Número LOCAL sin código de país; vacío = ese país no se muestra. El mismo que usa el app."),
    "contacto_whatsapp_bo": ("WhatsApp Bolivia (+591)", "Número LOCAL sin código de país; vacío = ese país no se muestra. El mismo que usa el app."),
    "empresa_correo": ("Correo de contacto", "Soporte, devoluciones y Libro de Reclamaciones."),
    "empresa_correo_privacidad": ("Correo de privacidad (opcional)", "Derechos ARCO y eliminar cuenta. Vacío = el de contacto."),
    "empresa_horario": ("Horario de atención", "Texto libre corto: «Lun a Sáb, 9:00 a 19:00»."),
    # Redes sociales OFICIALES de la marca (Culqi exige que los íconos de la web
    # lleven a perfiles reales y activos; vacío = el ícono NO se muestra).
    "empresa_instagram": ("Instagram oficial", "URL del perfil (https://www.instagram.com/…) o @usuario. Vacío = sin ícono."),
    "empresa_facebook": ("Facebook oficial", "URL de la página (https://www.facebook.com/…) o nombre de la página. Vacío = la página desde la que publica la torre (si hay una conectada); si no, sin ícono. Un enlace de búsqueda no vale."),
    "empresa_tiktok": ("TikTok oficial", "URL del perfil (https://www.tiktok.com/@…) o @usuario. Vacío = sin ícono."),
    "empresa_youtube": ("YouTube oficial", "URL del canal (https://www.youtube.com/@…) o @canal. Vacío = sin ícono."),
}

# (clave, nombre, dominios aceptados, cómo armar la URL desde un @usuario)
REDES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("instagram", "Instagram", ("instagram.com",), "https://www.instagram.com/{u}"),
    ("facebook", "Facebook", ("facebook.com", "fb.com", "fb.me"), "https://www.facebook.com/{u}"),
    ("tiktok", "TikTok", ("tiktok.com",), "https://www.tiktok.com/@{u}"),
    ("youtube", "YouTube", ("youtube.com", "youtu.be"), "https://www.youtube.com/@{u}"),
)

_EMAIL = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
_MAX = {"empresa_razon_social": 120, "empresa_doc_etiqueta": 12, "empresa_ruc": 20, "empresa_direccion": 200,
        "empresa_ciudad": 80, "contacto_whatsapp_pe": 12, "contacto_whatsapp_ec": 12, "contacto_whatsapp_bo": 12, "empresa_correo": 120, "empresa_correo_privacidad": 120,
        "empresa_horario": 80, "empresa_instagram": 200, "empresa_facebook": 200, "empresa_tiktok": 200,
        "empresa_youtube": 200}


def _url_red(red: str, valor: str) -> str:
    """URL del perfil oficial: acepta la URL completa o un @usuario. Devuelve
    "" si no se puede armar (y entonces el ícono no se muestra)."""
    v = (valor or "").strip()
    if not v:
        return ""
    nombre, dominios, plantilla = next((n, d, t) for r, n, d, t in REDES if r == red)
    if re.match(r"^https?://", v, re.I):
        sin_esquema = re.sub(r"^https?://", "", v, flags=re.I)
        host = sin_esquema.split("/")[0].lower()
        if not any(host == d or host.endswith("." + d) for d in dominios):
            return ""
        # Un enlace de BÚSQUEDA, login o "compartir" no es la página oficial (caso
        # real: el director pegó facebook.com/search/top?q=pichangol).
        ruta = sin_esquema.split("/", 1)[1].lower() if "/" in sin_esquema else ""
        if re.match(r"^(search|login|sharer|share|hashtag|explore|results|watch\?|dialog)\b", ruta) or ruta.startswith("search"):
            return ""
        return v
    usuario = v.lstrip("@").strip("/")
    if not re.match(r"^[A-Za-z0-9._-]{1,60}$", usuario):
        return ""
    return plantilla.format(u=usuario)


def redes() -> list[dict[str, str]]:
    """Redes oficiales configuradas, en orden, listas para el pie: [{red, nombre, url}]."""
    out = []
    for red, nombre, _d, _t in REDES:
        url = _url_red(red, _cfg(f"empresa_{red}"))
        if not url and red == "facebook":
            url = facebook_conectada()
        if url:
            out.append({"red": red, "nombre": nombre, "url": escape(url)})
    return out


def facebook_conectada() -> str:
    """URL de la página de Facebook desde la que PUBLICA la torre (`FB_PAGE_ID`):
    es la página oficial de Pichangol, así que sirve de respaldo cuando el
    operador no pegó una URL en Datos de la empresa. Usa el enlace real que
    devolvió Graph (`fb_page_link`, lo guarda `post_redes.estado_pagina`) y, si
    aún no se consultó, `facebook.com/<id>`, que Facebook siempre resuelve."""
    import config
    pid = (getattr(config, "FB_PAGE_ID", "") or "").strip()
    if not pid:
        return ""
    link = (stores.config.get("fb_page_link") or "").strip()
    if link and _url_red("facebook", link):
        return link
    return f"https://www.facebook.com/{pid}" if re.match(r"^[0-9]{5,}$", pid) else ""


def _cfg(clave: str) -> str:
    """Valor guardado (un "" guardado a propósito VALE, p. ej. correo de
    privacidad vacío = usar el de contacto); solo sin clave cae al default."""
    if clave in stores.config:
        return (stores.config.get(clave) or "").strip()
    return CONFIG_DEFAULT.get(clave, "").strip()


def valores() -> dict[str, str]:
    """Valores CRUDOS tal como están guardados (para el formulario de la torre)."""
    return {k: _cfg(k) for k in CAMPOS}


def _bonito(cod: str, local: str) -> str:
    """("51", "967923419") → «+51 967 923 419» (grupos de 3; si sobra un
    dígito, el primer grupo es de 4: «0991 234 567»)."""
    primero = 4 if len(local) % 3 == 1 else (2 if len(local) % 3 == 2 else 3)
    partes = [local[:primero]] + [local[i:i + 3] for i in range(primero, len(local), 3)]
    return f"+{cod} " + " ".join(p for p in partes if p)


def whatsapps() -> list[dict[str, str]]:
    """WhatsApp CONFIGURADOS por país, en orden PE·EC·BO, ya escapados:
    {iso, pais, bandera, cod, local, completo, bonito, url}. Los países sin
    número no salen (la web solo lista lo que existe)."""
    out = []
    for iso, nom, cod, bandera in PAISES:
        local = re.sub(r"\D", "", _cfg(_CLAVE_WA[iso]))
        if not local:
            continue
        out.append({"iso": iso, "pais": nom, "bandera": bandera, "cod": cod, "local": local,
                    "completo": cod + local, "bonito": _bonito(cod, local), "url": f"https://wa.me/{cod}{local}"})
    return out


def datos() -> dict[str, str]:
    """Datos LISTOS para pintar (ya escapados para HTML) + derivados:
    `wa_url` (https://wa.me/…), `whatsapp_bonito`, `correo_privacidad`
    (cae al de contacto), `anio` (© actual)."""
    v = valores()
    was = whatsapps()
    correo = v["empresa_correo"]
    return {
        "razon_social": escape(v["empresa_razon_social"]),
        "doc_etiqueta": escape(v["empresa_doc_etiqueta"] or "RUC"),
        "ruc": escape(v["empresa_ruc"]),
        "direccion": escape(v["empresa_direccion"]),
        "ciudad": escape(v["empresa_ciudad"] or v["empresa_direccion"]),
        "whatsapps": was,
        # Texto en línea con TODOS los países: «+51 967 923 419 (Perú) · +593 …».
        "whatsapp_bonito": " · ".join(f"{w['bonito']} ({w['pais']})" for w in was),
        "wa_url": was[0]["url"] if was else "",  # principal = primer país configurado
        "correo": escape(correo),
        "correo_privacidad": escape(v["empresa_correo_privacidad"] or correo),
        "horario": escape(v["empresa_horario"]),
        "anio": str(datetime.now(timezone.utc).year),
        "redes": redes(),
    }


def _bandera_html(w: dict[str, str]) -> str:
    """Bandera SVG de la web (`ui.bandera`; los emoji 🇵🇪 no se ven en Windows)."""
    try:
        from web.ui import bandera
        return bandera(w["iso"]) or w["bandera"]
    except Exception:  # noqa: BLE001
        return w["bandera"]


def _wa_inline(was: list[dict[str, str]]) -> str:
    """Para textos corridos: «<a>+51 967 923 419</a> (Perú) · <a>+593 …</a> (Ecuador)»."""
    return " · ".join(f"<span style=\"white-space:nowrap\"><a href=\"{w['url']}\">{w['bonito']}</a> ({w['pais']})</span>" for w in was) or "—"


def _wa_lista(was: list[dict[str, str]]) -> str:
    """Para la tarjeta de Contacto: una línea por país con su bandera."""
    if not was:
        return "—"
    if len(was) == 1:
        return f"<a href=\"{was[0]['url']}\">{was[0]['bonito']}</a>"
    return "<br>".join(f"<span style=\"white-space:nowrap\" title=\"{w['pais']}\">{_bandera_html(w)} <a href=\"{w['url']}\">{w['bonito']}</a> "
                       f"<small style=\"color:var(--tinta)\">{w['pais']}</small></span>" for w in was)


def _wa_botones(was: list[dict[str, str]]) -> str:
    """Botones «Escribir por WhatsApp» — uno por país cuando hay varios (cada
    jugador o dueño escribe al número de SU país)."""
    if not was:
        return ""
    if len(was) == 1:
        return f"<a class=\"cta\" href=\"{was[0]['url']}\">Escribir por WhatsApp</a>"
    return " ".join(f"<a class=\"cta\" href=\"{w['url']}\" style=\"margin:0 8px 8px 0\">{_bandera_html(w)} WhatsApp {w['pais']}</a>"
                    for w in was)


# Marcadores que acepta `legal/home.html` (y cualquier plantilla HTML).
def _marcadores() -> dict[str, str]:
    d = datos()
    return {
        "{{EMPRESA}}": d["razon_social"], "{{DOC_ETIQUETA}}": d["doc_etiqueta"], "{{RUC}}": d["ruc"],
        "{{DIRECCION}}": d["direccion"], "{{CIUDAD}}": d["ciudad"], "{{WA_URL}}": d["wa_url"],
        "{{WHATSAPP}}": _wa_inline(d["whatsapps"]), "{{WHATSAPP_LISTA}}": _wa_lista(d["whatsapps"]),
        "{{WA_BOTONES}}": _wa_botones(d["whatsapps"]), "{{CORREO}}": d["correo"],
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
        if clave.startswith("contacto_whatsapp_"):
            val = re.sub(r"\D", "", val)   # «+51 911 222 333» → 51911222333
            cod = next(c for iso, _, c, _ in PAISES if clave.endswith(iso))
            if val.startswith(cod) and len(val) > 10:   # pegó el número con código: se lo quitamos
                val = val[len(cod):]
            if val and not 7 <= len(val) <= 10:
                raise ValueError(f"{etiqueta}: escribe solo el número local (7 a 10 dígitos, sin +{cod})")
        if len(val) > _MAX[clave]:
            raise ValueError(f"{etiqueta}: máximo {_MAX[clave]} caracteres")
        elif clave == "empresa_ruc":
            val = re.sub(r"\s", "", val)
            if val and not val.isalnum():
                raise ValueError("Documento fiscal: solo letras y dígitos")
        elif clave in ("empresa_correo", "empresa_correo_privacidad"):
            val = val.lower()
            if val and not _EMAIL.match(val):
                raise ValueError(f"{etiqueta}: correo inválido")
        elif clave.startswith("empresa_") and clave[8:] in {r for r, *_ in REDES}:
            if val and not _url_red(clave[8:], val):   # con espacios adentro no es URL ni @usuario
                raise ValueError(f"{etiqueta}: pega la URL del perfil oficial (https://…) o el @usuario")
        if clave in ("empresa_razon_social", "empresa_correo", "empresa_ruc", "empresa_direccion") and not val:
            raise ValueError(f"{etiqueta}: es obligatorio (lo revisan Culqi e INDECOPI)")
        limpio[clave] = val
    return limpio


def guardar(cambios: dict[str, str]) -> dict[str, str]:
    """Valida y persiste en `stores.config` (el middleware guarda el snapshot)."""
    limpio = validar(cambios)
    stores.config.update(limpio)
    return valores()
