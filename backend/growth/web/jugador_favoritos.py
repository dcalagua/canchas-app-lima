"""Favoritos en la CUENTA (revisión de QAS, 29-oct-2026: el ♥ del explorador
vivía solo en el `localStorage` de ese navegador y se perdía al cambiar de
equipo).

- `stores.favoritos_web[correo] = {"ids": [...], "t": iso}` (snapshot, sin SQL
  nuevo). Los ids son los de la tarjeta del explorador (1.ª cancha del local).
- `GET /web/favoritos` → ids de la cuenta; `POST /web/favoritos {id, on}`
  marca/desmarca; `POST /web/favoritos/unir {ids}` suma los que el navegador
  tenía guardados antes de iniciar sesión (migración sin perder nada).
- `GET /mis-favoritos` → los locales guardados con la misma tarjeta del
  explorador; quitar el ♥ ahí también los saca.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import MARCA
from db.store import stores
from web import datos, sesion, ui
from web.jugador_billetera import _email, _gate
from web.ui import e

router = APIRouter()

MAX_FAVORITOS = 200


def favoritos_de(email: str) -> list[str]:
    return list((stores.favoritos_web.get(email) or {}).get("ids") or [])


def _guardar(email: str, ids: list[str]) -> list[str]:
    limpios = list(dict.fromkeys(str(i).strip()[:80] for i in ids if str(i or "").strip()))[-MAX_FAVORITOS:]
    stores.favoritos_web[email] = {"ids": limpios, "t": datetime.now(timezone.utc).isoformat()}
    return limpios


def _email_json(request: Request) -> str:
    ses = sesion.de_request(request)
    return _email(ses) if ses and ses.get("email") else ""


@router.get("/web/favoritos")
def ver_favoritos(request: Request):
    email = _email_json(request)
    if not email:   # 200: el explorador lo pide en cada visita, también sin sesión
        return {"ok": False, "error": "sesion_requerida"}
    return {"ok": True, "ids": favoritos_de(email)}


@router.post("/web/favoritos")
def marcar_favorito(request: Request, body: dict = Body(None)):
    email = _email_json(request)
    if not email:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    cid = str((body or {}).get("id") or "").strip()
    if not cid:
        return JSONResponse({"ok": False, "error": "id_requerido"}, status_code=400)
    ids = [i for i in favoritos_de(email) if i != cid]
    if (body or {}).get("on", True):
        ids.append(cid)
    return {"ok": True, "ids": _guardar(email, ids)}


@router.post("/web/favoritos/unir")
def unir_favoritos(request: Request, body: dict = Body(None)):
    email = _email_json(request)
    if not email:
        return JSONResponse({"ok": False, "error": "sesion_requerida"}, status_code=401)
    nuevos = [str(i) for i in ((body or {}).get("ids") or []) if isinstance(i, str)][:MAX_FAVORITOS]
    return {"ok": True, "ids": _guardar(email, favoritos_de(email) + nuevos)}


_JS = r"""
document.addEventListener('click', function(ev){
  var b = ev.target.closest('.corazon'); if(!b) return;
  ev.preventDefault(); ev.stopPropagation();
  var card = b.closest('.lst'), id = card.dataset.id;
  fetch('/web/favoritos', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: id, on: false})})
    .then(function(r){ return r.json(); }).then(function(j){
      if(!j.ok) return;
      try { var f = JSON.parse(localStorage.getItem('pcg_fav') || '{}') || {}; delete f[id]; localStorage.setItem('pcg_fav', JSON.stringify(f)); } catch(e){}
      card.remove();
      if(!document.querySelector('#favGrid .lst')) location.reload();
      window.pcgToast && pcgToast('Quitado de tus favoritos');
    });
});
"""


@router.get("/mis-favoritos", response_class=HTMLResponse)
def pagina_favoritos(request: Request) -> HTMLResponse:
    ses, resp = _gate(request, "/mis-favoritos", "Mis favoritos", "Tus favoritos se guardan en la app.")
    if resp:
        return resp
    email = _email(ses)
    ids = favoritos_de(email)
    from web import router as wr
    todas = [c for c in datos.canchas_publicas() if datos.reservable(c)]
    por_id = {c["id"]: c for c in todas}
    grupos: list[list[dict]] = []
    vistos: set[str] = set()
    for fid in reversed(ids):   # el último guardado, primero
        c = por_id.get(fid)
        if not c:
            continue
        club = (c.get("club") or "").strip().lower()
        clave = f"club:{club}" if club else f"id:{c['id']}"
        if clave in vistos:
            continue
        vistos.add(clave)
        grupo = [c] + [x for x in todas if x["id"] != c["id"] and club and (x.get("club") or "").strip().lower() == club]
        grupos.append(grupo)
    if grupos:
        ratings = datos.ratings([x["id"] for g in grupos for x in g])
        tarjetas = "".join(wr._tarjeta(g, ratings) for g in grupos)
        lista = (f"<div class='lst-grid' id='favGrid'>{tarjetas}</div>"
                 "<script>document.querySelectorAll('#favGrid .corazon').forEach(function(b){ b.classList.add('on'); });</script>")
    else:
        lista = ("<div class='vacio' style='margin-top:24px'><div style='font-size:46px'>♡</div><h3>Aún no guardas canchas</h3>"
                 "<p class='sub'>Toca el ♡ de cualquier local en el explorador y lo encuentras aquí, en cualquier equipo.</p>"
                 "<div class='acciones' style='justify-content:center'><a class='btn' href='/'>Explorar canchas</a></div></div>")
    cuerpo = ("<div style='padding-top:18px'><h1 class='anf-hola' style='margin-top:6px'>Mis favoritos</h1>"
              f"<p class='sub'>Los locales que guardaste con ♥. Quedan en tu cuenta de {e(MARCA)}.</p>"
              f"{lista}</div><script>{_JS}</script>")
    return ui.shell("Mis favoritos", cuerpo, sesion=ses, ancho=True, titulo_tab=f"Mis favoritos · {MARCA}")
