"""INICIO del modo anfitrión = tablero (rediseño del diseñador, 16-nov-2026).

Captura "CanchaLibre Anfitrión" (`Downloads/Soluciones EBIM_2`): lo primero que
se ve al tocar "Modo anfitrión" (`GET /anfitrion`). Reemplaza al menú de
tarjetas: los módulos ahora viven en la barra (`web/nav_anfitrion.py`).

Piezas, todas con datos reales (nada de los "—" del diseño):
1. franja azul "Modo anfitrión" + 4 cifras: Reservas de hoy · Pagos por
   confirmar · Cobrado hoy · Ocupación de hoy (misma regla que Caja del día,
   `anfitrion_negocio.caja_dia`; el cobrado va POR MONEDA, nunca se suman soles
   con dólares);
2. calendario semanal compacto de UNA cancha (selector), con reservas
   pagadas / por cobrar, bloqueos, días cerrados por reglas y la línea de
   "ahora"; "Abrir calendario" lleva al operativo;
3. Pendientes de hoy (comprobantes, próximas reservas, solicitudes);
4. Ingresos de los últimos 7 días (barras, moneda principal);
5. Accesos rápidos.

Recepción (solo encargado) ve agenda y comprobantes, nunca plata. Sin canchas
(una academia, un organizador nuevo) el tablero muestra la bienvenida para
registrar la primera.
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from config import MARCA

_ICO = {  # cuadrado de color de cada cifra / fila (mismos colores que la barra)
    "reservas": ("#3056ED", "calendario"), "pagos": ("#EE8A12", "recibo"), "cobrado": ("#16A15A", "billete"),
    "ocupacion": ("#3056ED", "reloj"), "proximas": ("#3056ED", "reloj"), "solicitudes": ("#7E98FF", "campana"),
}
ACCESOS = (("Mis canchas", "/anfitrion/mis-canchas", "cancha"), ("Clientes", "/anfitrion/clientes", "comparar"),
           ("Academia", "/anfitrion/academia", "academias"), ("Disponibilidad", "/anfitrion/disponibilidad", "calendario"))


def _e(s) -> str:
    from web.ui import e
    return e(s)


def _ic(clave: str, tam: int = 18) -> str:
    from web import iconos
    color, ico = _ICO[clave]
    return f"<span class='ai-ic' style='background:{color}'>{iconos.svg(ico, tam, grueso=2.3)}</span>"


def _monto(v: float, sim: str) -> str:
    return f"{sim} {v:,.0f}".replace(",", " ")


def _kpi(clave: str, titulo: str, valor: str, enlace: str, href: str, extra: str = "", aria: str = "") -> str:
    return (f"<div class='ai-kpi'>{_ic(clave)}<div class='ai-kpi-t'><span>{_e(titulo)}</span>"
            f"<div class='ai-kpi-v'><b{(' aria-label=' + chr(39) + _e(aria) + chr(39)) if aria else ''}>{valor}</b><a href='{href}'>{_e(enlace)} ›</a></div>{extra}</div></div>")


def _fila_pend(clave: str, titulo: str, sub: str, href: str) -> str:
    return (f"<a class='ai-pend' href='{href}'>{_ic(clave, 16)}<span class='tx'><b>{_e(titulo)}</b><small>{_e(sub)}</small></span>"
            "<span class='ir' aria-hidden='true'>›</span></a>")


# ── calendario semanal compacto ─────────────────────────────────────────────

def _calendario(c: dict, canchas: list[dict], hoy: date, ahora_min: int) -> str:
    """Semana de la cancha `c` (4 días antes de hoy → 2 después, como el
    diseño), con la MISMA regla de turnos que el calendario operativo:
    horario del día por las reglas del club, madrugada = fecha real."""
    from reservas import reglas as _reglas
    from web import datos, horarios
    dias = [hoy + timedelta(days=i) for i in range(-4, 3)]
    isos = [d.isoformat() for d in dias]
    sig = (dias[-1] + timedelta(days=1)).isoformat()
    filas = datos.reservas_de_canchas([c["id"]], isos[0], sig)
    bloq = datos.bloqueos_de([c["id"]], isos + [sig])
    paso = int(c.get("duracion_slot_min") or 60)
    cdias = {d: _reglas.cancha_del_dia(c, d.isoformat()) for d in dias}
    # (fecha real, hora) → (columna, minuto en la línea de tiempo del día base).
    pos: dict[tuple[str, str], tuple[int, int]] = {}
    ini_min, fin_min = 24 * 60, 0
    for i, d in enumerate(dias):
        cd = cdias[d]
        for h in horarios.slots_de(cd):
            fr = horarios.fecha_real(d.isoformat(), cd["hora_apertura"], cd["hora_cierre"], h)
            m = (horarios.hora_en_minutos(h) or 0) + (1440 if fr != d.isoformat() else 0)
            pos[(fr, h)] = (i, m)
            ini_min, fin_min = min(ini_min, m), max(fin_min, m + paso)
    if fin_min <= ini_min:
        ini_min, fin_min = 8 * 60, 22 * 60
    ini_min = (ini_min // 60) * 60
    fin_min = -(-fin_min // 60) * 60
    rango = fin_min - ini_min

    def _pct(m: int) -> float:
        return round((m - ini_min) * 100 / rango, 3)

    bloques: list[list[str]] = [[] for _ in dias]
    hoy_txt: list[tuple[str, str]] = []
    for r in filas:
        h = str(r.get("hora_inicio") or "")
        p = pos.get((str(r.get("fecha") or "")[:10], h))
        if p is None:
            continue
        i, m = p
        fin = horarios.hora_en_minutos(str(r.get("hora_fin") or "")) or 0
        dur = (fin - (horarios.hora_en_minutos(h) or 0)) % 1440 or paso
        pag = bool(r.get("pagado"))
        nombre = (str(r.get("jugador") or r.get("usuario") or "").strip().split(" ") or [""])[0] or "Reserva"
        bloques[i].append(f"<a class='ai-ev{'' if pag else ' ef'}' href='/anfitrion/calendario?cancha={quote(c['id'])}' "
                          f"style='top:{_pct(m)}%;height:{max(dur * 100 / rango, 3.2):.3f}%' "
                          f"title='{_e(h)} · {_e(nombre)} · {'pagada' if pag else 'cobrar en cancha'}'>{_e(nombre)}</a>")
        if dias[i] == hoy:
            hoy_txt.append((h, nombre))
    for (cid, f, h) in bloq:
        p = pos.get((f, h))
        if cid != c["id"] or p is None:
            continue
        i, m = p
        bloques[i].append(f"<span class='ai-ev bl' style='top:{_pct(m)}%;height:{max(paso * 100 / rango, 3.2):.3f}%'>Bloqueado</span>")
    cab = ""
    cols = ""
    for i, d in enumerate(dias):
        es_hoy = d == hoy
        txt = f"{horarios.DIAS[d.weekday()]} {d.day}"
        lejos = " ai-lejos" if i < 3 else ""
        cab += f"<div class='ai-cd{' hoy' if es_hoy else ''}{lejos}'>{('<b>' + _e(txt) + '</b>') if es_hoy else _e(txt)}</div>"
        cerr = cdias[d].get("_cerrado")
        linea = ""
        if es_hoy and ini_min <= ahora_min <= fin_min:
            linea = f"<i class='ai-ahora' style='top:{_pct(ahora_min)}%' aria-hidden='true'></i>"
        cols += (f"<div class='ai-col{' hoy' if es_hoy else ''}{lejos}'>"
                 + ("<span class='ai-cerr'>Cerrado</span>" if cerr else "") + "".join(bloques[i]) + linea + "</div>")
    horas = "".join(f"<span style='top:{_pct(m)}%'>{m // 60 % 24:02d}</span>" for m in range(ini_min, fin_min, 120))
    filas_h = rango // 60
    hoy_txt.sort()
    resumen = (f"Hoy en esta cancha: {len(hoy_txt)} {'reserva' if len(hoy_txt) == 1 else 'reservas'}"
               + (" · " + ", ".join(f"{h} {n}" for h, n in hoy_txt[:3]) if hoy_txt else ""))
    opciones = "".join(f"<option value='{_e(x['id'])}'{' selected' if x['id'] == c['id'] else ''}>{_e(x.get('nombre') or 'Cancha')}"
                       + (f" · {_e(x.get('club'))}" if x.get("club") and len({y.get('club') for y in canchas}) > 1 else "")
                       + "</option>" for x in canchas)
    def _rango_de(a: date, b: date) -> str:
        if a.month == b.month:
            return f"{a.day} – {b.day} {horarios.MESES[b.month - 1]}"
        return f"{a.day} {horarios.MESES[a.month - 1]} – {b.day} {horarios.MESES[b.month - 1]}"
    rango_txt = _rango_de(dias[0], dias[-1])
    rango_mov = _rango_de(dias[3], dias[-1])   # en el celular se ven 4 días
    return (
        "<section class='ai-panel ai-cal' aria-labelledby='aiCalT'>"
        "<div class='ai-cal-cab'><h2 id='aiCalT'>Calendario</h2>"
        f"<form method='get' action='/anfitrion' class='ai-sel'><label class='vh' for='aiCancha'>Cancha</label>"
        f"<select id='aiCancha' name='cancha' onchange='this.form.submit()'>{opciones}</select>"
        "<noscript><button type='submit' class='btn sec'>Ver</button></noscript></form>"
        f"<span class='ai-rango'><span class='ai-r-esc'>{_e(rango_txt)}</span><span class='ai-r-mov'>{_e(rango_mov)}</span></span>"
        f"<a class='ai-link' href='/anfitrion/calendario?cancha={quote(c['id'])}'>Abrir calendario ›</a></div>"
        f"<div class='ai-grid-cal'><div></div>{cab}"
        f"<div class='ai-horas' style='height:{filas_h * 30}px'>{horas}</div>"
        f"<div class='ai-cols' style='height:{filas_h * 30}px'>{cols}</div></div>"
        "<div class='ai-cal-pie'><span class='ai-ley'><i class='ok'></i>Pagada</span><span class='ai-ley'><i class='ef'></i>Cobrar en cancha</span>"
        f"<span class='ai-ley'><i class='bl'></i>Bloqueado</span><b>{_e(resumen)}</b></div></section>")


# ── ingresos 7 días ─────────────────────────────────────────────────────────

def _ingresos(filas: list[dict], canchas: list[dict], hoy: date, sim: str) -> str:
    from web import horarios
    from web.anfitrion_negocio import caja_dia
    dias = [hoy - timedelta(days=i) for i in range(6, -1, -1)]
    vals = [caja_dia(filas, d.isoformat(), canchas)["cobrado"] for d in dias]
    tope = max(vals) or 0
    # escala "redonda" para las líneas guía (0 · mitad · tope)
    paso = 1
    for p in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000):
        paso = p
        if p * 4 >= tope:
            break
    techo = max(paso * 4, 1)
    guias = "".join(f"<span style='bottom:{v * 100 / techo:.2f}%'>{v:,}</span>".replace(",", " ") for v in (0, techo // 2, techo))
    barras = ""
    for d, v in zip(dias, vals):
        etq = "Hoy" if d == hoy else horarios.DIAS[d.weekday()]
        barras += (f"<div class='ai-bar{' hoy' if d == hoy else ''}' title='{_e(etq)}: {_e(_monto(v, sim))}'>"
                   f"<i style='height:{max(v * 100 / techo, 1.5 if v else 0):.2f}%'></i><small>{_e(etq)}</small></div>")
    total = sum(vals)
    leyenda = "; ".join(f"{'hoy' if d == hoy else horarios.DIAS[d.weekday()]} {_monto(v, sim)}" for d, v in zip(dias, vals))
    return ("<section class='ai-panel ai-ing' aria-labelledby='aiIngT'>"
            f"<div class='ai-ing-cab'><h2 id='aiIngT'>Ingresos <small>(últimos 7 días)</small></h2><b>{_e(_monto(total, sim))}</b></div>"
            f"<div class='ai-chart' role='img' aria-label='Cobrado por día: {_e(leyenda)}'><div class='ai-guias'>{guias}</div>"
            f"<div class='ai-barras'>{barras}</div></div>"
            "<a class='ai-link' href='/anfitrion/reportes'>Ver reportes ›</a></section>")


# ── página ──────────────────────────────────────────────────────────────────

def _accesos(solo_encargado: bool) -> str:
    from web import iconos
    its = [a for a in ACCESOS if not (solo_encargado and a[1] in ("/anfitrion/clientes", "/anfitrion/disponibilidad"))]
    return ("<section class='ai-panel ai-acc' aria-labelledby='aiAccT'><h2 id='aiAccT'>Accesos rápidos</h2><div class='ai-acc-g'>"
            + "".join(f"<a href='{h}'><span>{iconos.svg(ico, 22, grueso=2.2)}</span>{_e(t)}</a>" for t, h, ico in its)
            + "</div></section>")


def _hero(_nombre: str = "") -> str:
    return ("<section class='ai-hero'><div class='wrap-xl'><h1>Modo anfitrión</h1>"
            "<p>Publica tu cancha o academia y recibe reservas y alumnos.</p></div></section>")


def render(ses: dict, enc_html: str, n_vouchers: int, cancha_id: str = ""):
    """HTML del tablero (lo llama `anfitrion.pagina_menu`)."""
    from web import anfitrion as a
    from web import datos, encargados, horarios, permisos, ui
    from web.anfitrion_negocio import _monedas, caja_dia, reservas_dueno
    email = ses["email"]
    nombre = (ses.get("nombre") or "").split(" ")[0]
    solo = permisos.es_solo_encargado(email)
    canchas = permisos.canchas_para(email, permisos.VER_AGENDA) if solo else datos.canchas_de_dueno(email)
    invit = encargados.invitaciones_de(email) if encargados.disponible() else []
    enc = f"<div class='ai-enc' id='invitaciones'>{enc_html}</div>" if enc_html else ""
    if not canchas:
        cuerpo = (_hero(nombre) + "<div class='ai-cuerpo'>" + enc
                  + "<section class='ai-panel ai-bienv'><h2>Registra tu primera cancha</h2>"
                  f"<p>Con esta cuenta todavía no tienes canchas. En {_e(MARCA)} tu local recibe reservas y pagos en línea, "
                  "y lo administras desde aquí y desde la app.</p>"
                  "<ol><li><b>Regístrala</b> con fotos tuyas y la ubicación del local.</li>"
                  "<li><b>Verifícala</b>: confirmamos que eres el dueño.</li>"
                  "<li><b>Recibe reservas</b>: agenda, cobros y reportes aquí.</li></ol>"
                  "<div class='acciones'><a class='btn' href='/anfitrion/nueva'>Registrar mi cancha</a>"
                  "<a class='btn sec' href='/anfitrion/academia'>Tengo una academia</a></div>"
                  "<p class='sub'>¿Registraste tu cancha con otro correo? Entra con ese mismo correo de Google.</p></section>"
                  + _accesos(solo) + "</div>")
        return ui.shell("Modo anfitrión", f"<div class='ai'>{cuerpo}</div>", sesion=ses, ancho=True,
                        titulo_tab=f"Modo anfitrión · {MARCA}")
    ahora = horarios.ahora_local(a._pais_de(canchas[0]))
    hoy = ahora.date()
    ids = [c["id"] for c in canchas]
    filas = reservas_dueno(ids, (hoy - timedelta(days=6)).isoformat(), hoy.isoformat())
    total_hoy = caja_dia(filas, hoy.isoformat(), canchas)
    # Cobrado POR MONEDA (un dueño con locales en dos países ve cada una por separado).
    monedas = _monedas(canchas)
    por_mon = []
    for iso, sim in monedas:
        sub = [c for c in canchas if a._moneda_de(c)[1] == iso]
        sub_ids = {c["id"] for c in sub}
        f_sub = [r for r in filas if r.get("cancha_id") in sub_ids]
        por_mon.append((iso, sim, sub, f_sub, caja_dia(f_sub, hoy.isoformat(), sub)["cobrado"]))
    _iso0, sim0, can0, fil0, cob0 = por_mon[0]
    extra_mon = "".join(f"<small>+ {_e(_monto(v, s))}</small>" for _i, s, _c, _f, v in por_mon[1:] if v)
    kpis = (_kpi("reservas", "Reservas de hoy", str(total_hoy["reservas"]), "Ver calendario", "/anfitrion/calendario")
            + _kpi("pagos", "Pagos por confirmar", str(n_vouchers), "Revisar", "/anfitrion/pagos-por-confirmar",
                   aria=f"{n_vouchers} por revisar"))
    if not solo:
        kpis += (_kpi("cobrado", "Cobrado hoy", _e(_monto(cob0, sim0)), "Caja del día", "/anfitrion/caja", extra_mon)
                 + _kpi("ocupacion", "Ocupación de hoy", f"{total_hoy['ocupacion']} %", "Ver reportes", "/anfitrion/ocupacion"))
    # Pendientes de hoy
    ahora_hhmm = f"{ahora.hour:02d}:{ahora.minute:02d}"
    nombres = {c["id"]: c.get("nombre") or "Cancha" for c in canchas}
    prox = sorted((r for r in total_hoy["lista"] if r["hora_inicio"] >= ahora_hhmm), key=lambda r: r["hora_inicio"])
    prox_txt = (", ".join(f"{r['hora_inicio']} {(r['jugador'] or 'Reserva').split(' ')[0]} · {nombres.get(r['cancha_id'], '')}" for r in prox[:2])
                if prox else "No hay más reservas hoy")
    en_verif = [c for c in canchas if not c.get("verificada") and permisos.es_dueno_de(email, c)]
    sol = []
    if invit:
        sol.append(f"{len(invit)} {'invitación' if len(invit) == 1 else 'invitaciones'} de encargado")
    if en_verif:
        sol.append(f"{len(en_verif)} {'cancha' if len(en_verif) == 1 else 'canchas'} en verificación")
    sol_href = "#invitaciones" if invit else (f"/anfitrion/verificacion/{quote(en_verif[0]['id'])}" if en_verif else "/anfitrion/mis-canchas")
    pend = ("<section class='ai-panel ai-pends' aria-labelledby='aiPendT'><div class='ai-p-cab'><h2 id='aiPendT'>Pendientes de hoy</h2>"
            "<a class='ai-link' href='/anfitrion/mis-canchas'>Ver todos ›</a></div>"
            + _fila_pend("pagos", "Pagos por confirmar",
                         f"{n_vouchers} {'comprobante' if n_vouchers == 1 else 'comprobantes'} por revisar" if n_vouchers else "Nada por revisar",
                         "/anfitrion/pagos-por-confirmar")
            + _fila_pend("proximas", "Próximas reservas", prox_txt, "/anfitrion/mis-canchas")
            + _fila_pend("solicitudes", "Solicitudes nuevas", " · ".join(sol) if sol else "Sin solicitudes nuevas", sol_href)
            + "</section>")
    c_sel = next((c for c in canchas if c["id"] == cancha_id), canchas[0])
    cal = _calendario(c_sel, canchas, hoy, ahora.hour * 60 + ahora.minute)
    lateral = pend + ("" if solo else _ingresos(fil0, can0, hoy, sim0)) + _accesos(solo)
    cuerpo = (_hero(nombre) + f"<div class='ai-kpis'>{kpis}</div><div class='ai-cuerpo'>{enc}"
              f"<div class='ai-grid'><div class='ai-izq'>{cal}</div><div class='ai-der'>{lateral}</div></div></div>")
    return ui.shell("Modo anfitrión", f"<div class='ai'>{cuerpo}</div>", sesion=ses, ancho=True,
                    titulo_tab=f"Modo anfitrión · {MARCA}")


CSS = r"""
/* ═════════ MODO ANFITRIÓN · inicio = tablero (diseñador, 16-nov-2026) ═════════ */
.ai{position:relative;padding-bottom:40px}
.ai h2{font-size:18px;margin:0;color:var(--anf-texto);font-weight:700}
.ai-hero{margin:0 calc(50% - 50vw);background:var(--azul);color:#fff;border-radius:0 0 40px 40px;padding:32px 0 92px;position:relative;overflow:hidden}
.ai-hero:after{content:"";position:absolute;right:12%;top:-30px;width:300px;height:220px;background:url(/static/brand/cl_icono_blanco.png) no-repeat center/contain;opacity:.1;transform:rotate(-12deg);pointer-events:none}
.ai-hero h1{font-size:34px;margin:0 0 6px;color:#fff;letter-spacing:-.01em}
.ai-hero p{margin:0;font-size:17px;color:rgba(255,255,255,.92)}
.ai-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:16px;margin-top:-64px;position:relative;z-index:1}
.ai-kpi{background:#fff;border-radius:16px;box-shadow:0 6px 22px rgba(20,33,90,.08);border:1px solid var(--anf-borde);padding:18px 20px;display:flex;gap:14px;align-items:flex-start;min-width:0}
.ai-kpi .ai-kpi-t{display:flex;flex-direction:column;gap:8px;min-width:0;flex:1}
.ai-kpi-v{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}
.ai-kpi .ai-kpi-t span{font-size:15px;color:var(--anf-texto)}
.ai-kpi .ai-kpi-t b{font-size:28px;color:var(--anf-texto);line-height:1.1}
.ai-kpi .ai-kpi-t small{font-size:13px;color:var(--anf-tenue)}
.ai-kpi-v a{font-weight:700;font-size:14px;color:var(--azul);text-decoration:none;white-space:nowrap;min-height:32px;display:inline-flex;align-items:center}
.ai-kpi-v a:hover{text-decoration:underline}
.ai-ic{width:34px;height:34px;border-radius:9px;display:inline-flex;align-items:center;justify-content:center;color:#fff;flex:none}
.ai-cuerpo{position:relative;margin-top:24px}
.ai-cuerpo:before{content:"";position:absolute;right:-40px;bottom:-30px;width:520px;height:230px;background:url(/static/brand/cl_apilado_azul.png) no-repeat right bottom/contain;opacity:.07;pointer-events:none;z-index:0}
.ai-enc{position:relative;z-index:1;margin-bottom:16px}
.ai-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,370px);gap:20px;position:relative;z-index:1;align-items:start}
.ai-der{display:flex;flex-direction:column;gap:16px;min-width:0}
.ai-panel{background:#fff;border-radius:16px;border:1px solid var(--anf-borde);box-shadow:0 1px 2px rgba(20,33,90,.04);padding:20px 22px;min-width:0}
.ai-link{color:var(--azul);font-weight:700;font-size:14px;text-decoration:none;white-space:nowrap}
.ai-link:hover{text-decoration:underline}
/* calendario */
.ai-cal-cab{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:14px}
.ai-cal-cab .ai-link{margin-left:auto}
.ai-sel select{background:var(--azul-tinte);border:0;border-radius:10px;font:inherit;font-weight:700;font-size:15px;color:var(--anf-texto);padding:9px 36px 9px 14px;min-height:42px;max-width:300px;width:auto}
.ai-sel{margin:0}.ai-sel label.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.ai-rango{color:var(--anf-tenue);font-weight:600;font-size:15px}
.ai-r-mov{display:none}
.ai-grid-cal{display:grid;grid-template-columns:34px repeat(7,minmax(0,1fr));column-gap:0}
.ai-cd{text-align:center;font-size:14px;color:var(--anf-tenue);padding:6px 2px 10px;border-bottom:1px solid var(--anf-borde);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ai-cd.hoy b{display:inline-block;background:var(--azul);color:#fff;border-radius:999px;padding:3px 12px;font-weight:700}
.ai-horas{position:relative}
.ai-horas span{position:absolute;left:0;font-size:12px;color:var(--anf-tenue);transform:translateY(-1px)}
.ai-cols{grid-column:2 / -1;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));background:repeating-linear-gradient(to bottom,var(--anf-linea) 0 1px,transparent 1px 30px)}
.ai-col{position:relative;border-left:1px solid var(--anf-linea);min-width:0}
.ai-col.hoy{background:rgba(48,86,237,.05)}
.ai-ev{position:absolute;left:3px;right:3px;background:var(--ok-bg);border-left:3px solid var(--anf-verde);color:var(--ok-fg);border-radius:4px;font-size:12px;font-weight:700;padding:2px 6px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;text-decoration:none;line-height:1.3;min-height:18px}
.ai-ev.ef{background:var(--warn-bg);border-left-color:var(--anf-naranja);color:var(--warn-fg)}
.ai-ev.bl{background:var(--gris);border-left-color:var(--trazo);color:var(--anf-tenue);font-weight:600}
.ai-ev:hover{filter:brightness(.96)}
.ai-cerr{position:absolute;inset:6px 3px;display:flex;align-items:center;justify-content:center;background:repeating-linear-gradient(135deg,var(--anf-linea) 0 8px,var(--gris) 8px 16px);border-radius:6px;font-size:13px;font-weight:700;color:var(--anf-tenue)}
.ai-ahora{position:absolute;left:0;right:0;height:2px;background:var(--anf-rojo);z-index:2}
.ai-ahora:before{content:"";position:absolute;left:-4px;top:-3px;width:8px;height:8px;border-radius:50%;background:var(--anf-rojo)}
.ai-cal-pie{display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin-top:14px;font-size:14px;color:var(--anf-tenue)}
.ai-cal-pie b{margin-left:auto;color:var(--anf-texto);font-size:14px}
.ai-ley{display:inline-flex;align-items:center;gap:6px}
.ai-ley i{width:10px;height:10px;border-radius:50%;background:var(--anf-verde);display:inline-block}
.ai-ley i.ef{background:var(--anf-naranja)}.ai-ley i.bl{background:var(--trazo)}
/* pendientes */
.ai-p-cab{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.ai-pend{display:flex;align-items:center;gap:12px;padding:10px 0;text-decoration:none;color:var(--anf-texto);border-bottom:1px solid var(--anf-linea);min-height:44px}
.ai-pend:last-child{border-bottom:0}
.ai-pend .tx{flex:1;min-width:0;display:flex;flex-direction:column}
.ai-pend .tx b{font-size:15px}.ai-pend .tx small{font-size:13px;color:var(--anf-tenue);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ai-pend .ir{color:var(--anf-tenue);font-size:20px}
.ai-pend:hover .tx b{color:var(--azul)}
/* ingresos */
.ai-ing-cab{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:12px}
.ai-ing-cab small{font-weight:500;font-size:13px;color:var(--anf-tenue)}
.ai-ing-cab b{font-size:16px;color:var(--anf-texto);white-space:nowrap}
.ai-chart{position:relative;height:150px;padding-left:40px;margin-bottom:10px}
.ai-guias{position:absolute;left:0;right:0;top:0;bottom:22px}
.ai-guias span{position:absolute;left:0;right:0;border-top:1px solid var(--anf-linea);font-size:12px;color:var(--anf-tenue);line-height:0;padding-top:0}
.ai-guias span{text-indent:0}
.ai-barras{position:absolute;left:40px;right:0;top:0;bottom:0;display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}
.ai-bar{display:flex;flex-direction:column;justify-content:flex-end;align-items:center;min-width:0}
.ai-bar i{display:block;width:100%;max-width:30px;background:var(--azul-claro);border-radius:6px 6px 2px 2px;margin-bottom:6px}
.ai-bar.hoy i{background:var(--azul)}
.ai-bar small{font-size:12px;color:var(--anf-tenue);height:16px;line-height:16px}
.ai-bar.hoy small{color:var(--azul);font-weight:700}
.ai-ing .ai-link{display:inline-block;margin-top:4px}
/* accesos */
.ai-acc-g{display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:12px;margin-top:14px}
.ai-acc-g a{display:flex;flex-direction:column;align-items:center;gap:8px;font-size:13px;color:var(--anf-tenue);text-decoration:none;text-align:center}
.ai-acc-g a span{width:100%;max-width:84px;height:46px;border-radius:10px;background:var(--azul);color:#fff;display:flex;align-items:center;justify-content:center}
.ai-acc-g a:hover span{background:var(--azul-osc)}.ai-acc-g a:hover{color:var(--anf-texto)}
/* sin canchas */
.ai-bienv p{color:var(--anf-tenue)}.ai-bienv ol{padding-left:20px;color:var(--anf-texto);line-height:1.7}
.ai-bienv{margin-bottom:16px;position:relative;z-index:1}
.ai-cuerpo>.ai-acc{position:relative;z-index:1}
@media(max-width:1000px){.ai-grid{grid-template-columns:minmax(0,1fr)}.ai-cuerpo:before{display:none}}
@media(max-width:600px){
  .ai-hero{padding:24px 0 84px;border-radius:0 0 28px 28px}.ai-hero h1{font-size:26px}.ai-hero p{font-size:15px}
  .ai-kpis{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .ai-kpi{padding:14px;flex-direction:column;gap:10px}
  .ai-kpi .ai-kpi-t b{font-size:22px}.ai-kpi .ai-kpi-t span{font-size:13.5px}
  .ai-panel{padding:16px}
  /* celular: 4 días (ayer, hoy y los 2 siguientes); la semana entera está en "Abrir calendario" */
  .ai-grid-cal{grid-template-columns:28px repeat(4,minmax(0,1fr))}
  .ai-cols{grid-template-columns:repeat(4,minmax(0,1fr))}
  .ai-lejos,.ai-r-esc{display:none}.ai-r-mov{display:inline}
  .ai-cd{font-size:13px}.ai-cd.hoy b{padding:2px 10px}
  .ai-ev{font-size:12px;padding:1px 3px;left:1px;right:1px}
  .ai-cal-cab .ai-link{margin-left:0}
}
"""
