"""REPROGRAMAR una reserva desde la web (plan de mejoras ronda 2, P2-4).

Antes solo se podía cancelar y volver a reservar. Ahora el titular puede
CAMBIAR el horario de su reserva con estas reglas (sin tocar la plata):

- con la MISMA anticipación con la que puede cancelar con devolución
  (`devoluciones.horas_minimas(c)`: la del club o la global);
- misma cancha, misma cantidad de turnos seguidos y el MISMO precio total
  (si el nuevo horario cuesta distinto: cancela y reserva de nuevo);
- no aplica a reservas con comprobante en revisión ni con boleador (el
  boleador aceptó ESE horario).

Se mueven las MISMAS filas (`datos.mover_reservas`, una transacción): pagos,
liquidación, canjes y comprobante siguen ligados a los mismos ids. Avisa al
dueño por push y a la lista de espera del horario que se liberó.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import MARCA
from web import datos, horarios, sesion, ui
from web.ui import e

router = APIRouter()


def _inicio(c: dict, fecha: str, hora: str) -> datetime | None:
    try:
        from web.router import _pais_de
        tz = horarios.ahora_local(_pais_de(c)).tzinfo
        d = datetime.fromisoformat(f"{fecha}T{hora}")
        return d.replace(tzinfo=tz)
    except (ValueError, TypeError):
        return None


def puede(filas: list[dict], c: dict | None, email: str) -> str:
    """'' si se puede reprogramar; si no, el motivo para el jugador."""
    from pagos import devoluciones as _dev
    from web.router import _pais_de
    if not filas or not c:
        return "No encontramos esta reserva."
    if any(str(f.get("usuario") or "").strip().lower() != email for f in filas):
        return "Solo quien hizo la reserva puede cambiarla."
    if any(str(f.get("estado") or "") != "confirmada" for f in filas):
        return "Esta reserva no está confirmada: no se puede cambiar el horario."
    if any(any((x or {}).get("clave") == "boleador" for x in (f.get("extras") or [])) for f in filas):
        return "Esta reserva tiene boleador: para cambiarla, cancélala y reserva de nuevo."
    if len({f.get("cancha_id") for f in filas}) != 1:
        return "Esta reserva no se puede cambiar desde aquí."
    ini = _inicio(c, str(filas[0].get("fecha")), str(filas[0].get("hora_inicio")))
    horas = _dev.horas_minimas(c)
    ahora = horarios.ahora_local(_pais_de(c))
    if not ini or ini - ahora < timedelta(hours=horas):
        return f"Solo puedes cambiar el horario con más de {horas:g} h de anticipación."
    return ""


def bloque_nuevo(c: dict, fecha: str, hora: str, n: int) -> tuple[list[dict], str]:
    """Los n turnos seguidos desde [hora] ese día, o el motivo si no se puede."""
    from reservas import reglas as _reglas
    from web import router as wr
    d_min, d_max = wr._fechas_validas(wr._pais_de(c))
    if not (wr._es_iso(fecha) and d_min <= fecha <= d_max):
        return [], "Esa fecha no se puede reservar."
    slots = wr._slots_del_dia(c, fecha)
    idx = next((i for i, s in enumerate(slots) if s["hora"] == hora), None)
    if idx is None or idx + n > len(slots):
        return [], "Ese horario no está disponible."
    bloque = slots[idx: idx + n]
    for a, b in zip(bloque, bloque[1:]):
        if a["fin"] != b["hora"]:
            return [], "Los turnos deben ser seguidos."
    if any(s.get("ocupado") for s in bloque):
        return [], "Ese horario ya está ocupado."
    err = _reglas.validar_bloque(_reglas.cancha_del_dia(c, fecha), n)
    if err:
        return [], "El club no acepta esa cantidad de turnos ese día."
    return bloque, ""


@router.post("/web/reprogramar")
def reprogramar(request: Request, body: dict = Body(None)):
    from web import router as wr
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    b = body or {}
    ref, fecha, hora = str(b.get("ref") or ""), str(b.get("fecha") or ""), str(b.get("hora") or "")
    email = ses["email"].strip().lower()
    filas = sorted(wr._filas_comprobante(ref), key=lambda f: (f.get("fecha"), f.get("hora_inicio")))
    c = datos.cancha(filas[0]["cancha_id"]) if filas else None
    motivo = puede(filas, c, email)
    if motivo:
        return JSONResponse({"ok": False, "error": "no_permitido", "mensaje": motivo}, status_code=400)
    bloque, motivo = bloque_nuevo(c, fecha, hora, len(filas))
    if motivo:
        return JSONResponse({"ok": False, "error": "horario", "mensaje": motivo}, status_code=409)
    antes = sum(int(f.get("precio") or 0) for f in filas)
    despues = sum(int(round(float(s.get("precio") or 0))) for s in bloque)
    if antes != despues:
        return JSONResponse({"ok": False, "error": "precio_distinto",
                             "mensaje": "Ese horario tiene otro precio. Para cambiarlo, cancela y reserva de nuevo."}, status_code=409)
    cambios = [(str(f["id"]), s.get("fecha") or fecha, s["hora"], s["fin"]) for f, s in zip(filas, bloque)]
    viejos = [(str(f.get("cancha_id")), str(f.get("fecha")), str(f.get("hora_inicio"))) for f in filas]
    if not datos.mover_reservas(cambios, email):
        return JSONResponse({"ok": False, "error": "no_movida", "mensaje": "Alguien tomó ese horario recién. Elige otro."}, status_code=409)
    print(f"[reprogramar] {email} {ref}: {viejos[0][1]} {viejos[0][2]} → {cambios[0][1]} {cambios[0][2]}", flush=True)
    try:
        from pagos import router as pr
        from web import jugador_espera as _je
        local = wr._titulo_local(c)
        pr._aviso_push_usuario(str(c.get("dueno") or ""), "Reserva reprogramada 🔁",
                               f"{filas[0].get('jugador') or email} movió su reserva en {local} del {horarios.fecha_larga(viejos[0][1])} "
                               f"{viejos[0][2]} al {horarios.fecha_larga(cambios[0][1])} {cambios[0][2]}.", "reserva")
        _je.avisar_liberados(viejos, salvo=email)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "url": f"/reserva/{ref}?cambiada=1"}


_JS = r"""
(function(){
  var C = window.__rp, $ = function(id){ return document.getElementById(id); }, dia = C.dias[0].iso;
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function dias(){ $('rpDias').innerHTML = C.dias.map(function(d){ return '<button type="button" class="chip' + (d.iso === dia ? ' sel' : '') + '" data-iso="' + d.iso + '"><b>' + esc(d.t) + '</b><small>' + esc(d.s) + '</small></button>'; }).join(''); }
  function cargar(){
    dias(); $('rpSlots').innerHTML = '<span class="skel"></span><span class="skel"></span>';
    fetch('/web/disponibilidad/' + encodeURIComponent(C.cancha) + '?fecha=' + dia).then(function(r){ return r.json(); }).then(function(j){
      var s = (j && j.slots) || [], out = [];
      for(var i = 0; i + C.n <= s.length; i++){
        var b = s.slice(i, i + C.n), ok = b.every(function(x, k){ return !x.ocupado && (k === 0 || b[k - 1].fin === x.hora); });
        var total = b.reduce(function(a, x){ return a + Math.round(x.precio); }, 0);
        if(ok && total === C.total && !(dia === C.fecha && b[0].hora === C.hora)) out.push(b);
      }
      $('rpSlots').innerHTML = out.length ? out.map(function(b){ return '<button type="button" class="slot" data-h="' + b[0].hora + '" data-f="' + (b[0].fecha || dia) + '"><b>' + b[0].hora + ' <small>– ' + b[b.length - 1].fin + '</small></b><span class="pr">mismo precio</span></button>'; }).join('')
        : '<p class="sub">No hay horarios libres con el mismo precio ese día. Prueba otro día.</p>';
    });
  }
  document.addEventListener('click', function(ev){
    var d = ev.target.closest('#rpDias [data-iso]'); if(d){ dia = d.dataset.iso; cargar(); return; }
    var s = ev.target.closest('#rpSlots .slot'); if(!s) return;
    pcgConfirmar({titulo: '¿Cambiar a este horario?', icono: '🔁', mensaje: 'Tu reserva pasa al ' + s.dataset.f + ' a las ' + s.dataset.h + '. El horario anterior queda libre.', confirmar: 'Cambiar horario'})
      .then(function(ok){ if(!ok) return; pcgCargando('Cambiando tu reserva…');
        fetch('/web/reprogramar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ref: C.ref, fecha: dia, hora: s.dataset.h})})
          .then(function(r){ return r.json(); }).then(function(j){
            if(j.ok){ pcgIr(j.url, 'Listo…'); return; }
            pcgCargando(false); pcgAvisar({titulo: 'No se pudo cambiar', icono: '🔁', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); cargar(); });
      });
  });
  cargar();
})();
"""


@router.get("/reserva/{ref}/cambiar", response_class=HTMLResponse)
def pagina_cambiar(ref: str, request: Request) -> HTMLResponse:
    from web import router as wr
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        from urllib.parse import quote
        return HTMLResponse("", status_code=302, headers={"Location": f"/entrar?volver={quote(f'/reserva/{ref}/cambiar', safe='')}"})
    filas = sorted(wr._filas_comprobante(ref), key=lambda f: (f.get("fecha"), f.get("hora_inicio")))
    c = datos.cancha(filas[0]["cancha_id"]) if filas else None
    motivo = puede(filas, c, ses["email"].strip().lower())
    if motivo:
        cuerpo = (f"<div class='panel' style='max-width:520px;margin:40px auto;text-align:center'><h1 style='font-size:22px'>No se puede cambiar</h1>"
                  f"<p class='sub'>{e(motivo)}</p><div class='acciones' style='justify-content:center'>"
                  f"<a class='btn' href='/reserva/{e(ref)}'>Volver a mi reserva</a></div></div>")
        return ui.shell("Cambiar horario", cuerpo, sesion=ses)
    hoy = horarios.ahora_local(wr._pais_de(c)).date()
    dias = []
    for i in range(14):
        d = hoy + timedelta(days=i)
        dias.append({"iso": d.isoformat(), "t": "Hoy" if i == 0 else ("Mañana" if i == 1 else horarios.fecha_larga(d.isoformat()).split(" ")[0]),
                     "s": f"{d.day}/{d.month}"})
    total = sum(int(f.get("precio") or 0) for f in filas)
    cfg = {"ref": ref, "cancha": c["id"], "n": len(filas), "total": total, "dias": dias,
           "fecha": str(filas[0].get("fecha")), "hora": str(filas[0].get("hora_inicio"))}
    actual = f"{horarios.fecha_larga(str(filas[0]['fecha']))} · {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"
    cuerpo = (f"<div style='max-width:720px;margin:0 auto;padding-top:18px'><a class='anf-back' href='/reserva/{e(ref)}'>‹ Mi reserva</a>"
              f"<h1 class='anf-hola' style='margin-top:6px'>Cambiar horario</h1>"
              f"<p class='sub'><b>{e(wr._titulo_local(c))}</b> · {e(c.get('nombre') or '')}<br>Ahora: {e(actual)} · "
              f"{len(filas)} turno{'s' if len(filas) != 1 else ''}.</p>"
              "<p class='sub' style='font-size:13px'>Elige otro horario con el mismo precio en esta cancha. Tu pago se mantiene; "
              "el horario anterior queda libre.</p>"
              "<div class='strip' id='rpDias' style='margin:14px 0'></div><div class='slots-grid' id='rpSlots'></div></div>"
              f"<script>window.__rp={ui.json_js(cfg)};</script><script>{_JS}</script>")
    return ui.shell("Cambiar horario", cuerpo, sesion=ses, titulo_tab=f"Cambiar horario · {MARCA}")


def boton(ref: str, clase: str = "btn sec") -> str:
    return f"<a class='{clase}' href='/reserva/{e(ref)}/cambiar'>🔁 Cambiar horario</a>"
