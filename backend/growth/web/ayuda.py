"""CENTRO DE AYUDA (`/ayuda`, plan de mejoras ronda 2, P2-6): preguntas
frecuentes de jugadores y dueños con lo que la plataforma hace DE VERDAD hoy
(pago directo al club, comprobantes, cancelación, lista de espera, favoritos,
calificaciones, puntos). Antes "Centro de ayuda" llevaba a un ancla de la
portada. Lleva JSON-LD `FAQPage` para que Google muestre las respuestas."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import config
from config import MARCA
from web import sesion, ui
from web.ui import e

router = APIRouter()


def _preguntas() -> list[tuple[str, list[tuple[str, str]]]]:
    horas = f"{config.WEB_CANCELACION_HORAS:g}"
    return [
        ("Reservar", [
            ("¿Cómo reservo una cancha?",
             "Busca por zona o deporte, abre el local, elige el día y uno o más turnos seguidos y paga en línea. "
             "La reserva queda en «Mis reservas» y el comprobante llega a tu correo."),
            ("¿A quién le pago?",
             f"Muchos clubes cobran directo: con su propia cuenta de tarjeta/Yape o con un comprobante (Yape, Plin o transferencia) "
             f"que el club confirma. {MARCA} solo cobra una comisión al club; tu dinero va al local."),
            ("Pagué con comprobante, ¿cuándo queda confirmada?",
             "Cuando el club revisa tu comprobante. Mientras tanto la verás como «Pago en revisión del club» y el horario queda "
             "apartado para ti. Si el club lo rechaza, verás el motivo en «Mis reservas»."),
            ("Un turno que quiero está ocupado, ¿qué hago?",
             "Tócalo y elige «Avísame»: entras a la lista de espera. Si lo cancelan, te llega un aviso y lo reserva el primero que entre."),
            ("¿Puedo guardar canchas para después?",
             "Sí: toca el ♥ de cualquier local. Con tu sesión iniciada se guarda en tu cuenta y lo ves en «Mis favoritos» desde cualquier equipo."),
        ]),
        ("Cancelar y devoluciones", [
            ("¿Puedo cancelar una reserva?",
             f"Sí, desde «Mis reservas» o desde tu comprobante, antes de que empiece. Cada club define con cuántas horas de anticipación "
             f"se devuelve (por defecto {horas} h); lo ves en la ficha del local y en tu comprobante."),
            ("¿Cómo me devuelven el dinero?",
             f"A tu saldo {MARCA} al instante (100 %), o al mismo medio con el que pagaste. Los detalles están en la "
             "política de cambios y devoluciones."),
        ]),
        ("Tu cuenta", [
            ("¿Cómo califico un local?",
             "Después de jugar, en «Mis reservas» → «Dónde has jugado» o en tu comprobante toca «⭐ Califica». Elige las estrellas y lo que te "
             "gustó; solo califican quienes jugaron ahí."),
            ("¿Qué son los puntos?",
             "Ganas 1 punto por cada sol que pagas en línea. Cada 100 puntos son un descuento al pagar en línea tu próxima reserva."),
            ("¿Dónde veo mis avisos?",
             "En el menú ☰ → «Notificaciones»: reservas confirmadas, turnos que se liberan, retos, pagos y más."),
        ]),
        ("Si tienes una cancha", [
            ("¿Cómo publico mi cancha?",
             "Entra a «Modo anfitrión» → «Pon tu cancha»: datos del local, punto en el mapa, deportes, precio, horario y al menos 3 fotos tuyas. "
             "Confirmamos que eres el dueño y tu cancha empieza a recibir reservas."),
            ("¿Cómo cobro las reservas?",
             "En «Cobros del club» conecta tu propia cuenta de tarjeta/Yape o agrega tus medios (Yape, Plin, transferencia). "
             "Los comprobantes que suben los jugadores los apruebas en «Pagos por confirmar»."),
            ("¿Puedo poner mis reglas?",
             "Sí, en «Reglas de reserva»: horario por día, días cerrados, precios por franja, recargo de luz, turnos mínimos y máximos y "
             "horas para cancelar."),
        ]),
    ]


@router.get("/ayuda", response_class=HTMLResponse)
def pagina_ayuda(request: Request) -> HTMLResponse:
    import empresa
    em = empresa.datos()
    secciones = _preguntas()
    html = ""
    for titulo, qs in secciones:
        html += f"<h2 style='margin-top:26px'>{e(titulo)}</h2>" + "".join(
            f"<details class='faq'><summary>{e(p)}</summary><p>{e(r)}</p></details>" for p, r in qs)
    jsonld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": p, "acceptedAnswer": {"@type": "Answer", "text": r}}
        for _t, qs in secciones for p, r in qs]}, ensure_ascii=False)
    cuerpo = (
        "<style>.faq{border:1px solid var(--trazo);border-radius:var(--r-sm);margin:8px 0;background:#fff}"
        ".faq summary{cursor:pointer;padding:14px 16px;font-weight:700;list-style:none;display:flex;justify-content:space-between;gap:12px;min-height:48px;align-items:center}"
        ".faq summary::after{content:'+';font-size:20px;color:var(--tenue)}.faq[open] summary::after{content:'−'}"
        ".faq p{margin:0;padding:0 16px 14px;color:var(--tenue);line-height:1.55}</style>"
        "<div style='max-width:760px;margin:0 auto;padding-top:18px'><h1 class='anf-hola' style='margin-top:6px'>Centro de ayuda</h1>"
        f"<p class='sub'>Respuestas rápidas sobre cómo reservar, pagar y administrar tu cancha en {e(MARCA)}.</p>{html}"
        "<div class='panel' style='margin-top:26px'><h2 style='margin-top:0'>¿No encontraste tu respuesta?</h2>"
        f"<p class='sub'>Escríbenos a <a href='mailto:{em['correo']}'>{em['correo']}</a>"
        + (f" o por <a href='{em['wa_url']}' target='_blank' rel='noopener'>WhatsApp</a>" if em.get("wa_url") else "")
        + f". Horario: {em.get('horario') or ''}.</p>"
        "<p class='sub' style='margin:0'><a href='/legal/devoluciones'>Política de cambios y devoluciones</a> · "
        "<a href='/legal/terminos'>Términos</a> · <a href='/libro-de-reclamaciones'>Libro de Reclamaciones</a></p></div></div>")
    return ui.shell("Centro de ayuda", cuerpo, sesion=sesion.de_request(request), titulo_tab=f"Centro de ayuda · {MARCA}",
                    desc=f"Preguntas frecuentes de {MARCA}: reservar, pagar, cancelar, lista de espera y cómo publicar tu cancha.",
                    jsonld=jsonld, canonical="/ayuda")
