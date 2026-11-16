"""Kit de VISTAS del modo anfitrión (rediseño del diseñador, 16-nov-2026).

Las 30 capturas de `Downloads/Soluciones EBIM_2` repiten las mismas piezas;
aquí viven UNA vez para que todas las vistas queden iguales (plan en
`docs/plan/REDISENO_ANFITRION.md`). Todo devuelve HTML ya escapado donde
corresponde; los textos que llegan como `html` NO se escapan (el que llama
arma el HTML con `ui.e`).

Piezas:
- `cabecera(titulo, sub, volver=…, acciones=…)`: "‹ Título" + subtítulo +
  acción principal a la derecha (o migas "‹ Roles" arriba del título).
- `kpis([...])` + `kpi(ico, titulo, valor, …)`: tarjetas de cifras con ícono
  en cuadrado de color.
- `panel(html, titulo, sub, acciones)`: tarjeta blanca.
- `pasos([...])`: las tres tarjetas "1. … 2. … 3. …" de Reservas fijas, Bonos…
- `segmentado([...])`, `pill(texto, tono)`, `vacio(...)`, `aviso(...)`.
- `lista_lateral(canchas, sel, href)`: columna "CANCHAS" agrupada por local
  (Mis canchas, Reglas, Disponibilidad, Llenar cancha).
- `tabla(cabeceras, filas)`: tabla que en el celular se apila por fila.
- `icono(clave, color)`: ícono de línea blanco en cuadrado de color.

Colores: SOLO tokens (`--azul`, `--anf-*` en `ui.TOKENS`).
"""

from __future__ import annotations

import html as _html

from web import estilos_v_academia, estilos_v_canchas, estilos_v_club, estilos_v_comercio, estilos_v_negocio, estilos_v_perfil

TONOS = {"ok", "warn", "bad", "info", "gris", "azul"}
# color de fondo de los cuadrados de ícono (tokens)
COLORES = {"azul": "var(--azul)", "verde": "var(--anf-verde)", "naranja": "var(--anf-naranja)", "rojo": "var(--anf-rojo)",
           "morado": "var(--anf-morado)", "claro": "var(--azul-tinte)", "tinta": "var(--anf-texto)"}


def e(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def icono(clave: str, color: str = "azul", tam: int = 18, suave: bool = False) -> str:
    """Ícono de línea (`web/iconos.py`) en un cuadrado de color. [suave] =
    fondo celeste con el ícono azul (las tarjetas de "pasos")."""
    from web import iconos
    if suave:
        return f"<span class='va-ic suave'>{iconos.svg(clave, tam, grueso=2.2)}</span>"
    return f"<span class='va-ic' style='background:{COLORES.get(color, color)}'>{iconos.svg(clave, tam, grueso=2.2)}</span>"


def cabecera(titulo: str, sub: str = "", *, volver: str = "/anfitrion", volver_txt: str = "", acciones: str = "") -> str:
    """Encabezado de una vista. Por defecto "‹ Título" (el ‹ vuelve a
    [volver]); con [volver_txt] ("Roles", "Perfil") va como miga pequeña arriba
    del título, como en las capturas de Soy boleador / Verificador / Pro."""
    if volver_txt:
        tit = (f"<a class='va-miga' href='{e(volver)}'>‹ {e(volver_txt)}</a><h1>{e(titulo)}</h1>")
    else:
        tit = (f"<h1><a class='va-volver' href='{e(volver)}' aria-label='Volver'>‹</a>{e(titulo)}</h1>")
    return (f"<header class='va-cab'><div class='va-cab-t'>{tit}" + (f"<p>{e(sub)}</p>" if sub else "") + "</div>"
            + (f"<div class='va-cab-acc'>{acciones}</div>" if acciones else "") + "</header>")


def kpi(ico: str, titulo: str, valor: str, *, color: str = "azul", sub: str = "", enlace: str = "", href: str = "",
        tono: str = "") -> str:
    """Tarjeta de cifra. [valor] es HTML (ya escapado por quien llama).
    [tono] pinta el valor: "warn" (dorado, por cobrar) · "bad" · "ok"."""
    pie = ""
    if enlace and href:
        pie = f"<a class='va-kpi-ir' href='{e(href)}'>{e(enlace)} ›</a>"
    elif sub:
        pie = f"<small>{e(sub)}</small>"
    return (f"<div class='va-kpi'><div class='va-kpi-c'>{icono(ico, color)}<span>{e(titulo)}</span></div>"
            f"<div class='va-kpi-v'><b class='{e(tono)}'>{valor}</b>{pie}</div></div>")


def kpis(items: list[str]) -> str:
    return f"<div class='va-kpis'>{''.join(items)}</div>"


def panel(contenido: str, titulo: str = "", sub: str = "", *, acciones: str = "", clase: str = "", id_: str = "") -> str:
    cab = ""
    if titulo or acciones:
        cab = ("<div class='va-panel-cab'><div>" + (f"<h2>{e(titulo)}</h2>" if titulo else "")
               + (f"<p>{e(sub)}</p>" if sub else "") + "</div>" + (f"<div class='va-panel-acc'>{acciones}</div>" if acciones else "") + "</div>")
    return f"<section class='va-panel {e(clase)}'" + (f" id='{e(id_)}'" if id_ else "") + f">{cab}{contenido}</section>"


def pasos(items: list[tuple[str, str, str]]) -> str:
    """[(ícono, "1. Elige cancha, día y hora", "Ej.: …"), …]"""
    return ("<div class='va-pasos'>" + "".join(
        f"<div class='va-paso'>{icono(ico, suave=True)}<div><b>{e(t)}</b><small>{e(s)}</small></div></div>" for ico, t, s in items)
        + "</div>")


def pill(texto: str, tono: str = "gris", ico: str = "") -> str:
    from web import iconos
    t = tono if tono in TONOS else "gris"
    return f"<span class='va-pill {t}'>{iconos.svg(ico, 13, grueso=2.6) if ico else ''}{e(texto)}</span>"


def segmentado(opciones: list[tuple[str, str, bool]], *, etiqueta: str = "Vista", contar: dict | None = None) -> str:
    """[(href, texto, seleccionado)] → pastilla segmentada de enlaces
    (Semana/Día, Hoy/Mañana, Por revisar/Resueltos…). [contar] = {texto: n}."""
    contar = contar or {}
    return (f"<nav class='va-seg' aria-label='{e(etiqueta)}'>" + "".join(
        f"<a href='{e(h)}' class='{'sel' if s else ''}'" + (" aria-current='page'" if s else "") + f">{e(t)}"
        + (f"<i>{contar[t]}</i>" if t in contar else "") + "</a>" for h, t, s in opciones) + "</nav>")


def vacio(ico: str, titulo: str, texto: str = "", cta: str = "") -> str:
    return (f"<div class='va-vacio'><span class='va-vacio-ic'>{_svg(ico, 30)}</span><b>{e(titulo)}</b>"
            + (f"<p>{e(texto)}</p>" if texto else "") + cta + "</div>")


def aviso(html_txt: str, tono: str = "info", acciones: str = "", ico: str = "") -> str:
    """Franja de aviso ("3 de tus locales necesitan fotos tuyas · Subir fotos ›")."""
    t = tono if tono in TONOS else "info"
    return (f"<div class='va-aviso {t}' role='status'>" + (f"<span class='va-aviso-ic'>{_svg(ico, 18)}</span>" if ico else "")
            + f"<div class='va-aviso-t'>{html_txt}</div>" + (f"<div class='va-aviso-acc'>{acciones}</div>" if acciones else "") + "</div>")


def _svg(clave: str, tam: int) -> str:
    from web import iconos
    return iconos.svg(clave, tam, grueso=2.2) if clave else ""


def lista_lateral(canchas: list[dict], sel: str, href, *, titulo: str = "Canchas", contar: str = "", sub=None,
                  insignia=None, pie: str = "", filtro: bool = False) -> str:
    """Columna izquierda "CANCHAS" agrupada por LOCAL (`club`).
    [href](cancha) → enlace; [sub](cancha) → línea gris (por defecto deporte ·
    horario · turno); [insignia](cancha) → píldora a la derecha ("Con reglas");
    [filtro] = caja "Filtrar canchas o deportes…" (filtra en el navegador)."""
    from web import horarios
    grupos: dict[str, list[dict]] = {}
    for c in canchas:
        grupos.setdefault(c.get("club") or c.get("nombre") or "Local", []).append(c)

    def _sub(c: dict) -> str:
        if sub:
            return sub(c)
        dep = (c.get("deportes") or [c.get("deporte") or ""])
        dep = dep[0] if isinstance(dep, list) and dep else (dep or "")
        return " · ".join(x for x in (str(dep).capitalize(), f"{c.get('hora_apertura') or '07:00'}–{c.get('hora_cierre') or '23:00'}",
                                      f"turnos de {int(c.get('duracion_slot_min') or 60)} min") if x)
    _ = horarios
    cuerpo = ""
    for local, cs in grupos.items():
        cuerpo += f"<div class='va-lat-g'><small>{e(local)}</small>"
        for c in cs:
            s = c["id"] == sel
            ins = insignia(c) if insignia else ""
            cuerpo += (f"<a class='va-lat-it{' sel' if s else ''}' href='{e(href(c))}'" + (" aria-current='true'" if s else "")
                       + f" data-q='{e((c.get('nombre') or '') + ' ' + local + ' ' + _sub(c)).lower()}'>"
                       f"{icono('cancha', 'claro' if not s else 'azul', 16)}<span class='tx'><b>{e(c.get('nombre') or 'Cancha')}</b>"
                       f"<small>{e(_sub(c))}</small></span>{ins}</a>")
        cuerpo += "</div>"
    caja = ("<label class='va-lat-buscar'><span class='vh'>Filtrar canchas</span>"
            f"{_svg('lupa', 18)}<input type='search' placeholder='Filtrar canchas o deportes…' data-va-filtro></label>" if filtro else "")
    return (f"<aside class='va-lat' aria-label='{e(titulo)}'><div class='va-lat-cab'><b>{e(titulo)}</b><small>{e(contar)}</small></div>"
            f"{caja}{cuerpo}{pie}</aside>")


def tabla(cabeceras: list[str], filas: list[list[str]], *, clase: str = "", vacia: str = "") -> str:
    """Tabla del diseño (cabecera en mayúsculas pequeñas). Celdas = HTML. En
    el celular cada fila es una tarjeta con la etiqueta de su columna."""
    if not filas:
        return vacia
    cab = "".join(f"<th scope='col'>{e(c)}</th>" for c in cabeceras)
    cuerpo = "".join("<tr>" + "".join(f"<td data-et='{e(cabeceras[i] if i < len(cabeceras) else '')}'>{v}</td>" for i, v in enumerate(f))
                     + "</tr>" for f in filas)
    return f"<div class='va-tabla-w'><table class='va-tabla {e(clase)}'><thead><tr>{cab}</tr></thead><tbody>{cuerpo}</tbody></table></div>"


def vista(contenido: str, clase: str = "") -> str:
    """Envoltorio de toda vista rediseñada (ancho 1120 px como el diseño)."""
    return f"<div class='va {e(clase)}'>{contenido}</div>"


JS = r"""
(function(){
  document.addEventListener('input', function(ev){
    var q = ev.target.closest && ev.target.closest('[data-va-filtro]'); if(!q) return;
    var t = q.value.trim().toLowerCase(), lat = q.closest('.va-lat'); if(!lat) return;
    lat.querySelectorAll('.va-lat-it').forEach(function(a){ a.hidden = !!t && (a.dataset.q || '').indexOf(t) < 0; });
    lat.querySelectorAll('.va-lat-g').forEach(function(g){ g.hidden = !g.querySelector('.va-lat-it:not([hidden])'); });
  });
})();
"""

CSS = r"""
/* ═════════ MODO ANFITRIÓN · kit de vistas (diseñador, 16-nov-2026) ═════════ */
.va{max-width:1120px;margin:0 auto;padding:28px 0 48px;color:var(--anf-texto)}
.va h2{font-size:18px;margin:0;color:var(--anf-texto);font-weight:700}
.va-cab{display:flex;align-items:flex-end;justify-content:space-between;gap:16px 24px;flex-wrap:wrap;margin-bottom:24px}
.va-cab-t{min-width:0;flex:1 1 420px}
.va-cab h1{font-size:30px;line-height:1.15;margin:0;color:var(--anf-texto);letter-spacing:-.01em;display:flex;align-items:center;gap:10px}
.va-cab p{margin:6px 0 0;color:var(--anf-tenue);font-size:15px}
.va-volver{color:var(--azul);text-decoration:none;font-size:30px;line-height:1;display:inline-flex;align-items:center;min-width:24px;min-height:44px}
.va-miga{display:inline-flex;align-items:center;min-height:32px;color:var(--azul);font-weight:700;font-size:13px;text-decoration:none}
.va-cab-acc{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.va .btn{border-radius:10px;padding:11px 18px;font-size:15px;min-height:44px;background:var(--azul);color:#fff}
.va .btn:hover{background:var(--azul-osc)}
.va .btn.sec{background:#fff;color:var(--anf-texto);border:1px solid var(--anf-borde)}
.va .btn.sec:hover{background:var(--anf-fondo)}
.va .btn.suave{background:var(--azul-tinte);color:var(--azul-osc);border:0}
.va .btn.peligro{background:#fff;color:var(--anf-rojo);border:1px solid var(--bad-bg)}
.va .btn.oscuro{background:var(--anf-texto);color:#fff}
.va-ic{width:34px;height:34px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;color:#fff;flex:none}
.va-ic.suave{background:var(--azul-tinte);color:var(--azul)}
.va-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:16px;margin-bottom:16px}
.va-kpi{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:16px 18px;min-width:0;display:flex;flex-direction:column;gap:10px}
.va-kpi-c{display:flex;align-items:center;gap:12px;font-size:14px;color:var(--anf-tenue)}
.va-kpi-v{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
.va-kpi-v b{font-size:26px;line-height:1.1;color:var(--anf-texto)}
.va-kpi-v b.warn{color:var(--warn-fg)}.va-kpi-v b.bad{color:var(--anf-rojo)}.va-kpi-v b.ok{color:var(--ok-fg)}
.va-kpi-v small{font-size:12px;color:var(--anf-tenue)}
.va-kpi-ir{font-weight:700;font-size:14px;color:var(--azul);text-decoration:none;white-space:nowrap}
.va-panel{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:20px 22px;min-width:0;margin-bottom:16px}
.va-panel-cab{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.va-panel-cab p{margin:4px 0 0;color:var(--anf-tenue);font-size:13.5px}
.va-panel-acc{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.va-pasos{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr));gap:16px;margin-bottom:16px}
.va-paso{background:#fff;border:1px solid var(--anf-borde);border-radius:14px;padding:16px 18px;display:flex;gap:14px;align-items:center;min-width:0}
.va-paso b{display:block;font-size:14.5px}.va-paso small{display:block;font-size:12.5px;color:var(--anf-tenue);margin-top:2px}
.va-pill{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 10px;font-size:12px;font-weight:700;line-height:1.2;white-space:nowrap}
.va-pill.ok{background:var(--ok-bg);color:var(--ok-fg)}.va-pill.warn{background:var(--warn-bg);color:var(--warn-fg)}
.va-pill.bad{background:var(--bad-bg);color:var(--bad-fg)}.va-pill.info,.va-pill.azul{background:var(--azul-tinte);color:var(--azul-osc)}
.va-pill.gris{background:var(--anf-linea);color:var(--anf-tenue)}
.va-seg{display:inline-flex;background:var(--anf-linea);border-radius:12px;padding:4px;gap:2px;max-width:100%;overflow-x:auto}
.va-seg a{display:inline-flex;align-items:center;gap:8px;padding:8px 16px;border-radius:9px;color:var(--anf-tenue);font-weight:700;font-size:14px;text-decoration:none;white-space:nowrap;min-height:38px}
.va-seg a.sel{background:#fff;color:var(--anf-texto);box-shadow:0 1px 3px rgba(20,33,90,.08)}
.va-seg a i{font-style:normal;background:var(--azul-tinte);color:var(--azul-osc);border-radius:999px;padding:1px 8px;font-size:12px}
.va-vacio{text-align:center;padding:36px 16px;display:flex;flex-direction:column;align-items:center;gap:8px}
.va-vacio-ic{width:68px;height:68px;border-radius:50%;background:var(--azul-tinte);color:var(--azul);display:flex;align-items:center;justify-content:center;margin-bottom:6px}
.va-vacio b{font-size:17px}.va-vacio p{margin:0 0 8px;color:var(--anf-tenue);font-size:14px;max-width:460px}
.va-aviso{display:flex;align-items:center;gap:12px;border-radius:12px;padding:12px 16px;margin-bottom:16px;flex-wrap:wrap;font-size:14px}
.va-aviso.info{background:var(--azul-tinte);color:var(--anf-texto)}.va-aviso.warn{background:var(--warn-bg);color:var(--anf-texto)}
.va-aviso.bad{background:var(--bad-bg);color:var(--anf-texto)}.va-aviso.ok{background:var(--ok-bg);color:var(--anf-texto)}
.va-aviso-ic{width:26px;height:26px;border-radius:50%;background:var(--azul);color:#fff;display:inline-flex;align-items:center;justify-content:center;flex:none}
.va-aviso.warn .va-aviso-ic{background:var(--warn-fg)}.va-aviso.bad .va-aviso-ic{background:var(--anf-rojo)}
.va-aviso-t{flex:1;min-width:200px}.va-aviso-acc{display:flex;gap:16px;flex-wrap:wrap}
.va-aviso-acc a{font-weight:700;color:var(--azul);text-decoration:none;font-size:14px;min-height:32px;display:inline-flex;align-items:center}
.va-lat{background:#fff;border:1px solid var(--anf-borde);border-radius:16px;padding:16px 12px;min-width:0;align-self:start}
.va-lat-cab{display:flex;justify-content:space-between;align-items:baseline;padding:0 6px 10px}
.va-lat-cab b{font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--anf-tenue)}
.va-lat-cab small{font-size:12px;color:var(--anf-tenue)}
.va-lat-buscar{display:flex;align-items:center;gap:8px;background:var(--anf-fondo);border-radius:10px;padding:0 12px;margin:0 4px 10px;color:var(--anf-tenue)}
.va-lat-buscar input{border:0;background:transparent;font:inherit;font-size:14px;padding:10px 0;min-height:42px;flex:1;min-width:0;width:auto}
.va-lat-buscar input:focus{outline:none}.va-lat-buscar:focus-within{box-shadow:var(--foco)}
.va-lat-g{margin-bottom:8px}.va-lat-g>small{display:block;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--anf-tenue);padding:8px 8px 4px}
.va-lat-it{display:flex;align-items:center;gap:10px;padding:9px 8px;border-radius:10px;text-decoration:none;color:var(--anf-texto);position:relative;min-height:44px}
.va-lat-it .va-ic{width:30px;height:30px;color:var(--azul)}.va-lat-it.sel .va-ic{color:#fff}
.va-lat-it .tx{flex:1;min-width:0;display:flex;flex-direction:column}
.va-lat-it .tx b{font-size:14.5px}.va-lat-it .tx small{font-size:12px;color:var(--anf-tenue);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.va-lat-it:hover{background:var(--anf-fondo)}
.va-lat-it.sel{background:var(--azul-tinte)}.va-lat-it.sel:before{content:"";position:absolute;left:-12px;top:8px;bottom:8px;width:3px;border-radius:3px;background:var(--azul)}
.va-lat-it.sel .tx b{color:var(--azul-osc)}
.va-tabla-w{overflow-x:auto;margin:0 -4px}
.va-tabla{width:100%;border-collapse:collapse;font-size:14px}
.va-tabla th{text-align:left;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--anf-tenue);font-weight:700;padding:10px 8px;border-bottom:1px solid var(--anf-borde);white-space:nowrap}
.va-tabla td{padding:14px 8px;border-bottom:1px solid var(--anf-linea);vertical-align:middle}
.va-tabla tr:last-child td{border-bottom:0}
.va-tabla td small{display:block;color:var(--anf-tenue);font-size:12.5px}
.va-dos{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,360px);gap:16px;align-items:start}
.va-lado{display:grid;grid-template-columns:minmax(0,280px) minmax(0,1fr);gap:16px;align-items:start}
.va-tres{display:grid;grid-template-columns:minmax(0,280px) minmax(0,1fr) minmax(0,300px);gap:16px;align-items:start}
@media(max-width:1000px){.va-dos,.va-tres{grid-template-columns:minmax(0,1fr)}.va-tres{grid-template-columns:minmax(0,1fr)}}
@media(max-width:860px){.va-lado{grid-template-columns:minmax(0,1fr)}}
@media(max-width:600px){
  .va{padding-top:18px}.va-cab h1{font-size:24px}.va-cab{align-items:flex-start}
  .va-cab-acc{width:100%}.va-cab-acc .btn{flex:1}
  .va-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.va-kpi{padding:14px}.va-kpi-v b{font-size:21px}
  .va-panel{padding:16px}
  .va-tabla thead{display:none}.va-tabla,.va-tabla tbody,.va-tabla tr,.va-tabla td{display:block;width:100%}
  .va-tabla tr{border:1px solid var(--anf-borde);border-radius:12px;padding:6px 12px;margin-bottom:10px}
  .va-tabla td{border:0;padding:6px 0;display:flex;justify-content:space-between;gap:12px;text-align:right}
  .va-tabla td:before{content:attr(data-et);font-size:12px;font-weight:700;color:var(--anf-tenue);text-transform:uppercase;text-align:left}
  .va-tabla td[data-et='']:before{display:none}
}
"""

# Hojas de cada grupo de vistas (una por frente de trabajo; cada una la escribe
# solo quien es dueño de esos archivos). Van DESPUÉS del kit y ganan.
CSS_TODO = (CSS + estilos_v_canchas.CSS + estilos_v_club.CSS + estilos_v_negocio.CSS + estilos_v_comercio.CSS
            + estilos_v_academia.CSS + estilos_v_perfil.CSS)
