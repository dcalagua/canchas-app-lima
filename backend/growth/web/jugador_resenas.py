"""Calificar después de jugar, desde la WEB (revisión de QAS, 29-oct-2026: la
web mostraba las ★ pero solo se podía calificar en el app).

- Misma tabla que el APK (`pichangol_resenas`, una por cancha y autor; volver
  a calificar la reemplaza), así el promedio es uno solo.
- Solo quien YA JUGÓ en ese local (reserva pasada, no cancelada ni no-show)
  puede calificarlo: el APK deja a cualquiera con sesión; aquí evitamos
  reseñas de quien nunca fue.
- Sin texto libre (regla del director): estrellas + chips de lo que te gustó o
  no. Las etiquetas viajan en `comentario` ("Cancha en buen estado · Buena
  atención"), que el APK ya muestra tal cual.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from web import datos, horarios, sesion
from web.ui import e

router = APIRouter()

# Lo que el jugador puede marcar (sin texto libre).
ETIQUETAS_BIEN = ["Cancha en buen estado", "Buena iluminación", "Vestuarios limpios", "Buena atención",
                  "Puntuales con el turno", "Fácil de llegar"]
ETIQUETAS_MAL = ["Cancha desgastada", "Poca luz", "Vestuarios sucios", "Demoraron el turno", "Difícil estacionar"]
ETIQUETAS = ETIQUETAS_BIEN + ETIQUETAS_MAL


def jugo_en_el_local(email: str, cancha: dict) -> bool:
    """¿Este correo tiene una reserva PASADA y válida en alguna cancha del local?"""
    club = (cancha.get("club") or "").strip().lower()
    ids = {cancha["id"]}
    if club:
        ids |= {c["id"] for c in datos.canchas_publicas() if (c.get("club") or "").strip().lower() == club}
    hoy = horarios.ahora_local("PE").date().isoformat()
    for r in datos.reservas_de_usuario(email):
        if (r.get("cancha_id") in ids and str(r.get("fecha") or "") < hoy
                and str(r.get("estado") or "") not in ("cancelada", "noShow", "no_show", "nueva")):
            return True
    return False


@router.post("/web/resena")
def calificar(request: Request, body: dict = Body(None)):
    ses = sesion.de_request(request)
    if not ses or not ses.get("email"):
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    b = body or {}
    cid = str(b.get("cancha_id") or "").strip()
    c = datos.cancha(cid) if cid else None
    if not c:
        return JSONResponse({"ok": False, "error": "cancha"}, status_code=404)
    try:
        est = int(b.get("estrellas") or 0)
    except (TypeError, ValueError):
        est = 0
    if not 1 <= est <= 5:
        return JSONResponse({"ok": False, "error": "estrellas", "mensaje": "Elige de 1 a 5 estrellas."}, status_code=400)
    etiquetas = [t for t in (b.get("etiquetas") or []) if t in ETIQUETAS][:6]
    email = ses["email"].strip().lower()
    if (c.get("dueno") or "").strip().lower() == email:
        return JSONResponse({"ok": False, "error": "propia", "mensaje": "No puedes calificar tu propio local."}, status_code=400)
    if not jugo_en_el_local(email, c):
        return JSONResponse({"ok": False, "error": "sin_reserva",
                             "mensaje": "Puedes calificar un local después de jugar ahí."}, status_code=403)
    if not datos.guardar_resena(cid, email, ses.get("nombre") or "", est, " · ".join(etiquetas)):
        return JSONResponse({"ok": False, "error": "no_guardado", "mensaje": "No pudimos guardar tu calificación. Inténtalo de nuevo."},
                            status_code=503)
    return {"ok": True, "estrellas": est}


def boton(cancha_id: str, local: str, mis_est: int = 0) -> str:
    """Botón "⭐ Califica" para una tarjeta de reserva pasada (va dentro del <a>)."""
    txt = f"Tu calificación {'★' * mis_est}" if mis_est else "⭐ Califica"
    return (f"<span class='lnk calificar' role='button' tabindex='0' data-cancha='{e(cancha_id)}' data-local='{e(local)}' "
            f"data-est='{int(mis_est)}'>{txt}</span>")


def seccion_ficha(ids: list[str]) -> str:
    """Reseñas recientes del local para la ficha pública."""
    rs = datos.resenas_de(ids, 6)
    if not rs:
        return ""
    prom = sum(r["estrellas"] for r in rs) / len(rs)
    items = "".join(
        f"<li><div class='rs-cab'><span class='rs-av'>{e((r['autor_nombre'] or '?')[:1].upper())}</span>"
        f"<b>{e((r['autor_nombre'] or 'Jugador').split(' ')[0])}</b><span class='rs-est' aria-label='{r['estrellas']} de 5'>"
        f"{'★' * r['estrellas']}<span style='opacity:.25'>{'★' * (5 - r['estrellas'])}</span></span></div>"
        + (f"<div class='rs-txt'>{e(r['comentario'])}</div>" if r["comentario"] else "") + "</li>"
        for r in rs)
    return ("<section class='panel rs' id='resenas' style='margin-top:18px'>"
            f"<h2 style='margin:0 0 4px'>★ {prom:.1f} · Lo que dicen los jugadores</h2>"
            "<p class='sub' style='margin:0 0 10px'>Calificaciones de quienes ya jugaron aquí.</p>"
            f"<ul class='rs-lista'>{items}</ul></section>")


CSS = """
.rs-lista{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(260px,100%),1fr));gap:12px}
.rs-lista li{border:1px solid var(--trazo);border-radius:var(--r-sm);padding:12px}
.rs-cab{display:flex;align-items:center;gap:8px}.rs-av{width:30px;height:30px;border-radius:50%;background:var(--tinte);color:var(--teal);display:inline-flex;align-items:center;justify-content:center;font-weight:800}
.rs-est{margin-left:auto;color:var(--dorado-txt);letter-spacing:1px}.rs-txt{margin-top:6px;font-size:13.5px;color:var(--tenue)}
.cal-ov{position:fixed;inset:0;background:rgba(15,27,45,.45);z-index:80;display:flex;align-items:center;justify-content:center;padding:16px}
.cal{background:#fff;border-radius:24px;max-width:440px;width:100%;padding:22px;max-height:calc(100dvh - 32px);overflow:auto}
.cal h3{margin:0 0 4px}.cal-est{display:flex;gap:6px;margin:14px 0 6px}
.cal-est button{width:48px;height:48px;border-radius:50%;border:1px solid var(--trazo);background:#fff;font-size:24px;color:#C8CED6;cursor:pointer}
.cal-est button.on{color:var(--dorado-txt);border-color:var(--dorado-txt);background:#FFF8E1}
.cal .chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}.cal .chip.sel{background:var(--tinte);border-color:var(--esmeralda)}
.cal .acciones{margin-top:16px;display:flex;gap:10px;justify-content:flex-end}
"""

JS = r"""
(function(){
  var BIEN = ⟦BIEN⟧, MAL = ⟦MAL⟧;
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function abrir(btn){
    var est = parseInt(btn.dataset.est || '0', 10) || 0, sel = {};
    var ov = document.createElement('div'); ov.className = 'cal-ov';
    function chips(lst){ return lst.map(function(t){ return '<button type="button" class="chip" data-t="' + esc(t) + '">' + esc(t) + '</button>'; }).join(''); }
    ov.innerHTML = '<div class="cal" role="dialog" aria-modal="true" aria-labelledby="calTit"><h3 id="calTit">¿Cómo te fue en ' + esc(btn.dataset.local) + '?</h3>' +
      '<p class="sub" style="margin:0">Tu calificación ayuda a otros jugadores y al local.</p>' +
      '<div class="cal-est" role="radiogroup" aria-label="Estrellas">' + [1,2,3,4,5].map(function(n){ return '<button type="button" data-n="' + n + '" aria-label="' + n + ' de 5">★</button>'; }).join('') + '</div>' +
      '<b style="font-size:14px">Lo que te gustó</b><div class="chips">' + chips(BIEN) + '</div>' +
      '<b style="font-size:14px;display:block;margin-top:12px">Lo que se puede mejorar</b><div class="chips">' + chips(MAL) + '</div>' +
      '<div class="acciones"><button type="button" class="btn sec" data-x>Ahora no</button><button type="button" class="btn" data-ok disabled>Enviar</button></div></div>';
    document.body.appendChild(ov);
    function pintar(){ ov.querySelectorAll('.cal-est button').forEach(function(b){ b.classList.toggle('on', +b.dataset.n <= est); });
      ov.querySelector('[data-ok]').disabled = !est; }
    pintar();
    function cerrar(){ ov.remove(); btn.focus && btn.focus(); }
    ov.addEventListener('click', function(ev){
      var t = ev.target;
      if(t === ov || t.closest('[data-x]')) return cerrar();
      var s = t.closest('.cal-est button'); if(s){ est = +s.dataset.n; pintar(); return; }
      var c = t.closest('.chip[data-t]'); if(c){ var k = c.dataset.t; if(sel[k]) delete sel[k]; else sel[k] = 1; c.classList.toggle('sel', !!sel[k]); return; }
      if(t.closest('[data-ok]')){
        window.pcgCargando && pcgCargando('Enviando…');
        fetch('/web/resena', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({cancha_id: btn.dataset.cancha, estrellas: est, etiquetas: Object.keys(sel)})})
          .then(function(r){ return r.json(); }).then(function(j){
            window.pcgCargando && pcgCargando(false);
            if(!j.ok){ pcgAvisar({titulo: 'No se pudo enviar', icono: '⭐', mensaje: j.mensaje || 'Inténtalo de nuevo.'}); return; }
            btn.dataset.est = est; btn.textContent = 'Tu calificación ' + '★'.repeat(est);
            cerrar(); window.pcgToast && pcgToast('¡Gracias por calificar!');
          }).catch(function(){ window.pcgCargando && pcgCargando(false); pcgAvisar({titulo: 'Sin conexión', icono: '📶', mensaje: 'Inténtalo de nuevo.'}); });
      }
    });
    document.addEventListener('keydown', function esc_(ev){ if(ev.key === 'Escape'){ document.removeEventListener('keydown', esc_); cerrar(); } });
    ov.querySelector('.cal-est button').focus();
  }
  document.addEventListener('click', function(ev){ var b = ev.target.closest && ev.target.closest('.calificar'); if(!b) return;
    ev.preventDefault(); ev.stopPropagation(); abrir(b); });
  document.addEventListener('keydown', function(ev){ var b = ev.target.closest && ev.target.closest('.calificar');
    if(b && (ev.key === 'Enter' || ev.key === ' ')){ ev.preventDefault(); abrir(b); } });
})();
"""


def js() -> str:
    from web.ui import json_js
    return JS.replace("⟦BIEN⟧", json_js(ETIQUETAS_BIEN)).replace("⟦MAL⟧", json_js(ETIQUETAS_MAL))
