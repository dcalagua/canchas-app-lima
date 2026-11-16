"""RESERVA WEB (sep-2026). Páginas públicas del dominio de marca, con el mismo
look & feel del APK (`web/ui.py`):

- GET  /canchas                    → catálogo de canchas verificadas (por país,
                                     filtro por deporte y buscador).
- GET  /reservar/{cancha_id}       → ficha + día (tira de 14 días) + horarios
                                     libres con precio + datos + extras + pago
                                     (Culqi Checkout: Yape y tarjeta) con
                                     "Resumen de tu reserva" fijo.
- GET  /web/disponibilidad/{id}    → JSON de slots del día (precio, ocupado).
- POST /web/asegurar               → toma los slots (INSERT 'nueva', hold 10 min).
- POST /web/pagar                  → cargo Culqi → confirma, liquida al dueño
                                     y le avisa.
- POST /web/liberar                → el cliente cerró sin pagar: libera el hold.
- GET  /reserva/{id}               → comprobante (por id o por grupo).
- GET  /reserva/{id}.ics           → evento para el calendario del cliente.

Misma base y mismas reglas que el APK: las filas van a `pichangol_reservas`
con el esquema que lee el dueño en su app, el UNIQUE del slot evita la doble
reserva, la contabilidad usa `/pagos/liquidacion-online` (billetera-first) y
el dueño recibe el push "Nueva reserva 📅".

MULTI-PAÍS: en soles se cobra con Culqi en la misma página; en \\$ y Bs con
la pasarela HOSPEDADA del país (`web/pago_hospedado.py`: Ecuador por la
fachada `pagos/pasarela_ec.py`, Bolivia por Libélula). Sin pasarela
configurada, en producción la ficha manda a reservar por la app.

DÓNDE ESTÁ CADA COSA (oct-2026, este archivo se partió en módulos sin cambiar
el comportamiento; aquí solo se arma el `router` y se re-exporta todo):

- `web/comun.py`          constantes, país/moneda de la cancha, firma del
                          bloque, pasarela por moneda, fotos, galería, 404.
- `web/explorador.py`     `/`, `/canchas`, `/canchas/{deporte}/{zona}`,
                          `/web/descubrir`; JS del explorador, tarjetas.
- `web/entrar.py`         `/web/sesion` (+ `/prueba`), `/web/salir`, `/entrar`.
- `web/lugares.py`        `/web/lugares`, `/web/foto`.
- `web/disponibilidad.py` fechas válidas, turnos del día,
                          `/web/disponibilidad/{id}`, `/web/libres`.
- `web/ficha.py`          `/lugar/{id}`, `/reservar/{id}`; JS de la reserva.
- `web/reserva_pago.py`   `/web/cotizar`, `/web/asegurar`, `/web/fidelidad`,
                          `/web/beneficios`, `/web/liberar`, `/web/pagar`,
                          `plan_cobro_reserva`, `confirmar_reserva_pagada`…
- `web/cancelacion.py`    `estado_cancelacion`, `_cancelar_reserva`,
                          `/web/cancelar`, modal y JS de cancelar.
- `web/mis_reservas.py`   `/mis-reservas`.
- `web/perfil.py`         `/perfil`.
- `web/comprobante.py`    `/reserva/{ref}.ics`, `/reserva/{ref}`.

Cada módulo tiene su propio `APIRouter`; aquí se incluyen EN EL MISMO ORDEN en
que estaban las rutas (importa para `/reserva/{ref}.ics` antes de
`/reserva/{ref}`). Todo nombre que vivía aquí se re-exporta: el resto del
código y los tests siguen usando `web.router.<nombre>` / `wr.<nombre>`. Para
parchear una función en un test, parchéala en el módulo que la DEFINE (las
demás funciones la buscan ahí, no aquí).
"""

from __future__ import annotations

# Importes de siempre: se conservan para quien lee `web.router.<módulo>`
# (p. ej. `R._cd` en `pago_hospedado`, `wr.descubrir` en los tests).
import hashlib
import hmac
import json
from typing import Any
import servicios_extra as _se
import re
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import config
import empresa
from paises import _CAJAS, pais_de_coordenadas, moneda_de_pais, simbolo_de_moneda
from pagos import culqi
from pagos import cargo_servicio as _cs
from pagos import devoluciones as _dev
from web import beneficios, catalogos, datos, descubrir, horarios, marca, miniaturas, osm, pago_hospedado, sesion, ui
from reservas import reglas as _reglas
from pagos import cobro_directo as _cd
from web import dividir_pago as _dividir_web
from web.ui import e
import academia_plan as _ap
from config import MARCA  # noqa: E402 — nombre y dominio de marca (un solo lugar)

# Módulos en que se partió este archivo (orden = el de sus rutas).
from web import (comun as _comun, explorador as _explorador, entrar as _entrar, lugares as _lugares,
                 disponibilidad as _disponibilidad, ficha as _ficha, reserva_pago as _reserva_pago,
                 cancelacion as _cancelacion, mis_reservas as _mis_reservas, perfil as _perfil,
                 comprobante as _comprobante)  # noqa: E402

router = APIRouter()
router.include_router(_explorador.router)
router.include_router(_entrar.router)
router.include_router(_lugares.router)
router.include_router(_disponibilidad.router)
router.include_router(_ficha.router)
router.include_router(_reserva_pago.router)
router.include_router(_cancelacion.router)
router.include_router(_mis_reservas.router)
router.include_router(_perfil.router)
router.include_router(_comprobante.router)

# Re-exportes: TODO lo que antes se definía aquí (mismos objetos, una sola
# instancia de cada caché / contador / constante).
from web.comun import (AMENIDAD_NOMBRE, CIUDAD_DEFECTO, DEPORTES, DIAS_ADELANTE, DIAS_TIRA, EXTRAS_NOMBRE, MAX_SLOTS,
                       NOMBRE_PAIS, PLAY_URL, _deporte, _deportes_de, _es_osm, _firma, _firma_ok, _foto_card, _fotos,
                       _fotos_crudas, _galeria, _maps, _moneda_de, _no_encontrada, _pago_web_disponible, _pais_de,
                       _pasarela_web, _secreto, _sin_google, _zona)  # noqa: E402,F401
from web.explorador import (AMENIDAD_ICONO, CATEGORIAS, LEAFLET, _CORAZON, _JS_EXPLORAR, _LUPA, _RECOMENDADAS, _RED_SVG,
                            _agrupar_locales, _amenidades_de, _barra_filtros, _botones_redes, _explorar, _hm_min,
                            _landing_lista, _modal_filtros, _n_locales, _nav_explorar, _tarjeta, _tarjeta_academia,
                            _url_red, _zonas_sugeridas, descubrir_web, pagina_canchas, pagina_inicio, pagina_zona,
                            paginas_zona, slug)  # noqa: E402,F401
from web.entrar import (SesionPruebaReq, SesionReq, _MOTIVOS_ENTRAR, _motivo_entrar, _revision_intentos, _volver_seguro,
                        abrir_sesion, abrir_sesion_prueba, cerrar_sesion, pagina_entrar, ver_sesion)  # noqa: E402,F401
from web.lugares import _minis, foto_web, lugares_web  # noqa: E402,F401
from web.disponibilidad import (_es_iso, _fechas_validas, _hora_libre, _slots_del_dia, disponibilidad, libres)  # noqa: E402,F401
from web.ficha import (_DIA_NOMBRE, _JS_RESERVA, _MESES_CORTOS, _acciones_local, _ayuda_turnos, _ficha, _hermanas,
                       _jsonld_cancha, _num_txt, _politica_html, _rango_dias, _resenas_ficha, _tira_dias, _titulo_local,
                       pagina_lugar, pagina_reservar)  # noqa: E402,F401
from web.reserva_pago import (AsegurarReq, HoraReq, LiberarReq, PagarReq, _contador, _cotizacion_reserva, _nuevo_id,
                              _sesion_o_token, asegurar, concepto_reserva, confirmar_reserva_pagada, liberar, pagar,
                              plan_cobro_reserva, sena_de, soltar_bloque, web_beneficios, web_cotizar, web_fidelidad)  # noqa: E402,F401
from web.cancelacion import (CancelarReq, JS_CANCELAR, _MODAL_CANCELAR, _boton_cancelar, _cancelar_reserva, _cargo_app,
                             _cargo_pagado, _cobro_web, _es_cargo_culqi, _es_directo, _filas_de_ref, _horas_desde_pago,
                             _inicio_reserva, _reembolsar_ec, _reembolso_ec_posible, _ref_de, _saldo_en_moneda,
                             _total_de, _url_comprobante, cancelar, estado_cancelacion)  # noqa: E402,F401
from web.mis_reservas import (ESTADO_RESERVA, MOTIVO_RECHAZO, _agrupar_reservas, _jr_css, _jr_js, _seccion_espera,
                              _tarjeta_viaje, pagina_mis_reservas)  # noqa: E402,F401
from web.perfil import _CSS_PERFIL, _EMOJI_DEP, _item_perfil, pagina_perfil  # noqa: E402,F401
from web.comprobante import (_boton_cambiar, _cabecera_revision, _calificar_comprobante, _filas_comprobante, _ics,
                             _pagina_pago_caido, comprobante_ics, pagina_comprobante)  # noqa: E402,F401
