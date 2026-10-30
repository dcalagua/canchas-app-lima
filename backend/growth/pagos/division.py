"""CADA UNO PAGA SU PARTE (ronda 3 de la web, oct-2026): dividir el pago de una
reserva web entre amigos, con el dinero DIRECTO al club.

Flujo (todo lo decide el servidor; el navegador solo muestra):

1. El organizador elige turnos en la ficha y "Dividir el pago" entre N personas
   (2…12, él incluido). `/web/asegurar` aparta los turnos con un hold LARGO
   (`medio_pago = 'division'`) y crea la división: `cl_division_pago` + N filas
   en `cl_division_partes` (migración 0006).
2. Reparto (céntimos exactos, nunca se pierde uno): cada amigo paga
   ⌊total ÷ N⌋ y la parte 0 —la del organizador— lleva el resto. S/ 100 entre 3
   = 33.34 (organizador) + 33.33 + 33.33. Cada parte ≥ `MIN_PARTE_CENTIMOS`.
3. Plazo: `vence_en` = min(ahora + `dividir_horas` (2 h), inicio del primer
   turno − `dividir_margen_min` (60 min, para que el club sepa a tiempo si la
   reserva va)). Si quedan menos de `VENTANA_MIN_MINUTOS` (30) no se ofrece.
   El hold de las filas tiene un tope duro en SQL (`datos.HOLD_DIVISION_MAX_SEGUNDOS`
   = 2 h 10 min desde que se apartó) por si esta división se perdiera.
4. Cada persona abre `/dividir/{token}` (login con Google), TOMA una parte
   (`cobrando`, 15 min) y la paga con los medios DEL CLUB: su Culqi (cargo con
   la llave secreta cifrada del club; `cobro_id = chr_…#n`) o un voucher que el
   club aprueba en "Pagos por confirmar" (`cl_pagos_manuales`, ref
   `div_…#n`, mismo anti-fraude por nº de operación e imagen). Un amigo paga a
   lo sumo UNA parte (índice único); el organizador puede cubrir "lo que falta".
5. Conservador: un voucher EN REVISIÓN no cuenta como pagado ni alarga el
   plazo. La división se completa recién cuando TODAS las partes están
   `pagada`; eso se decide con la fila de la división bloqueada (`FOR UPDATE`),
   así dos amigos que pagan la última parte a la vez no la confirman dos veces.
6. Completa → la reserva se confirma con `cobro_directo_web.confirmar_directo`
   (las MISMAS filas de `pichangol_reservas`, `medio_pago = 'dividido'`, el cobro
   `cobro_directo` por el TOTAL con `culqi_charge_id = div:<id>` y UNA comisión
   al dueño sobre la reserva completa: saldo o deuda, como cualquier cobro
   directo). Sin cargo por servicio: el cobro directo no lo lleva hoy.
7. Vence (o el organizador cancela) sin completarse → el horario se suelta y
   cada parte con plata se DEVUELVE: Culqi del club → reembolso por API con su
   llave (`reembolsada`; si falla, `devolver`); voucher aprobado → `devolver`
   (el club devuelve a mano y lo marca en Cobros del club); voucher sin revisar
   → se cierra y queda `devolver` con nota `sin_revisar` (el club devuelve si lo
   recibió o marca "No lo recibí"). 30 min antes del vencimiento el organizador
   recibe "Faltan N partes · Pagar lo que falta".
8. Reserva ya confirmada que se cancela (política normal de `_cancelar_reserva`)
   → `devolver_por_cancelacion`: lo que corresponde se reparte proporcional a
   lo que pagó cada uno y vuelve a cada pagador por su medio.

9. A prueba de fallas (revisión oct-2026): un error de la base al leer el
   apartado NO cuenta como "apartado perdido" (lectura estricta, se reintenta);
   si las filas no se confirman, la división sigue `completa` sin cobrar
   comisión; un cierre que se corta a mitad lo retoma el barrido
   (`cerradas_pendientes`); cada cargo se devuelve UNA vez y en UNA llamada
   aunque cubra varias partes (`cl_division_cargos_devueltos`, también ignora
   webhooks tardíos); el webhook exige que la división sea del club del webhook,
   en soles y con el cargo capturado; un comprobante que llega con la parte ya
   suelta se retoma o queda como pago tardío para que el club lo devuelva
   (`cl_division_tardios`); la devolución proporcional nunca pasa lo pagado.

Persistencia: tablas Postgres (`RepoPG`, migraciones 0006 + 0007); los tests
inyectan `RepoMemoria` (`usar_repo`). Sin las tablas la opción NO se ofrece
(`disponible()`).
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

MIN_PARTES, MAX_PARTES = 2, 12
MIN_PARTE_CENTIMOS = 300          # cada parte ≥ S/ 3 · $ 3 · Bs 3 (Culqi exige ≥ 1; abajo de 3 no vale la pena)
HORAS_DEFECTO = 2.0               # plazo para juntar las partes
MARGEN_MIN_DEFECTO = 60           # el plazo cierra al menos 1 h antes del turno
VENTANA_MIN_MINUTOS = 30          # con menos de esto no se ofrece dividir
AVISO_MIN = 30                    # aviso al organizador antes del vencimiento
TOMA_MAX_MIN = 15                 # una parte "tomada" sin pagar vuelve a quedar libre
MEDIO_RESERVA = "dividido"        # medio_pago de las filas ya confirmadas
PREFIJO_COBRO = "div:"            # culqi_charge_id del cobro_directo total
VIVOS = ("cobrando", "en_revision", "pagada")

_ERRORES = {
    "dividir_no_disponible": "Este club no permite dividir el pago por ahora.",
    "dividir_partes": f"Elige entre {MIN_PARTES} y {MAX_PARTES} personas.",
    "dividir_monto": "El total es muy bajo para dividirlo entre tantas personas.",
    "dividir_muy_tarde": "Falta muy poco para el turno: ya no da tiempo de juntar las partes. Paga la reserva completa.",
    "dividir_no_combinable": "El pago dividido no se combina con seña, bono, puntos, premio de fidelidad ni boleador.",
    "sesion_requerida": "Inicia sesión con Google para dividir el pago.",
    "cerrada": "Este pago dividido ya se cerró.",
    "sin_partes": "Ya se tomaron todas las partes. Si alguien no paga a tiempo, vuelve a quedar libre.",
    "ya_pagaste": "Ya tienes tu parte de esta reserva.",
    "no_tomada": "Esa parte ya no está reservada para ti. Vuelve a intentarlo.",
    "solo_organizador": "Solo quien organiza la reserva puede hacer esto.",
}


def mensaje(err: str) -> str:
    return _ERRORES.get(err, "No pudimos completar la acción. Inténtalo de nuevo.")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_num(clave: str, defecto: float, lo: float, hi: float) -> float:
    try:
        from db.store import stores
        v = float(stores.config.get(clave, defecto))
    except (TypeError, ValueError, ImportError):
        v = defecto
    return max(lo, min(hi, v))


def horas_plazo() -> float:
    # Tope 2 h: el hold de las filas vence en SQL a las 2 h 10 (datos.HOLD_DIVISION_MAX_SEGUNDOS).
    return _cfg_num("dividir_horas", HORAS_DEFECTO, 0.5, 2.0)


def margen_min() -> float:
    return _cfg_num("dividir_margen_min", MARGEN_MIN_DEFECTO, 0, 240)


# ── reglas puras ─────────────────────────────────────────────────────────────

def calcular_partes(total_centimos: int, n: int) -> list[int]:
    """[parte del organizador, parte de cada amigo…]. Suma EXACTA = total."""
    total_centimos, n = int(total_centimos), int(n)
    base = total_centimos // n
    return [total_centimos - base * (n - 1)] + [base] * (n - 1)


def max_partes(total_centimos: int) -> int:
    return max(0, min(MAX_PARTES, int(total_centimos) // MIN_PARTE_CENTIMOS))


def vence_para(inicio: datetime | None, ahora: datetime | None = None) -> datetime | None:
    """Plazo de la división o None si ya no da tiempo."""
    if inicio is None:
        return None
    ahora = ahora or _ahora()
    v = min(ahora + timedelta(hours=horas_plazo()), inicio - timedelta(minutes=margen_min()))
    return v if (v - ahora) >= timedelta(minutes=VENTANA_MIN_MINUTOS) else None


def aviso_desde(div: dict) -> datetime:
    """Desde cuándo se avisa al organizador que faltan partes."""
    ventana = div["vence_en"] - div["creado_en"]
    return div["vence_en"] - min(timedelta(minutes=AVISO_MIN), ventana / 2)


def es_ref(ref: str) -> bool:
    """¿Es la referencia de un voucher de una PARTE (`div_…#n`)?"""
    r = str(ref or "")
    return r.startswith("div_") and "#" in r


def id_de_cobro(cobro_id: str) -> str:
    """`div:<id>` (cobro_directo total) → id de la división ('' si no es)."""
    c = str(cobro_id or "")
    return c[len(PREFIJO_COBRO):] if c.startswith(PREFIJO_COBRO) else ""


# ── repositorios ─────────────────────────────────────────────────────────────

_COLS_DIV = ["id", "token", "reserva_ref", "reserva_ids", "cancha_id", "dueno", "organizador_email",
             "organizador_nombre", "moneda", "total_centimos", "partes", "parte_centimos", "estado", "motivo",
             "vence_en", "aviso_en", "creado_en", "cerrado_en"]
_COLS_PARTE = ["id", "division_id", "n", "monto_centimos", "estado", "pagador_email", "pagador_nombre",
               "por_organizador", "medio", "cobro_id", "pago_manual_id", "refund_id", "devolver_centimos", "nota",
               "tomada_en", "pagada_en", "resuelta_en"]
_LIBRE = {"estado": "libre", "pagador_email": "", "pagador_nombre": "", "por_organizador": False, "medio": "",
          "tomada_en": None}


def _pendiente_de_devolver(div: dict, p: dict) -> bool:
    """¿Esta parte de una división YA CERRADA aún espera su devolución? (el
    cierre se cortó a mitad: lo retoma el barrido). Tras cancelar una reserva
    confirmada, una parte pagada solo espera si se le asignó monto a devolver."""
    if p["estado"] in ("cobrando", "en_revision"):
        return True
    if p["estado"] != "pagada":
        return False
    return div.get("motivo") != "reserva_cancelada" or int(p.get("devolver_centimos") or 0) > 0


def _tardio_como_parte(t: dict) -> dict:
    """Un comprobante tardío con la misma forma que una parte por devolver."""
    return {"id": t["id"], "division_id": t["division_id"], "n": int(t.get("n") or 0),
            "monto_centimos": int(t["monto_centimos"]), "devolver_centimos": int(t["monto_centimos"]),
            "estado": t["estado"], "pagador_email": t["pagador_email"], "pagador_nombre": t.get("pagador_nombre") or "",
            "medio": t.get("medio") or "", "nota": t.get("nota") or "", "pago_manual_id": t.get("pago_manual_id") or "",
            "cobro_id": "", "refund_id": "", "por_organizador": False, "tardio": True}


class RepoMemoria:
    """Mismo contrato que `RepoPG`, en memoria (tests). Un solo candado hace de
    `FOR UPDATE` de la fila de la división."""

    def __init__(self):
        self.divs: dict[str, dict] = {}
        self.partes_: dict[str, dict] = {}
        self.devueltos: dict[str, dict] = {}     # cl_division_cargos_devueltos
        self.tardios: dict[str, dict] = {}       # cl_division_tardios
        self._lock = threading.RLock()

    def disponible(self) -> bool:
        return True

    def _p(self, div_id):
        return sorted((p for p in self.partes_.values() if p["division_id"] == div_id), key=lambda p: p["n"])

    def crear(self, div, partes):
        with self._lock:
            if any(d["reserva_ref"] == div["reserva_ref"] and d["estado"] in ("abierta", "completa", "confirmada")
                   for d in self.divs.values()):
                return "ya_existe"
            self.divs[div["id"]] = dict(div)
            for p in partes:
                self.partes_[p["id"]] = dict(p)
            return ""

    def por_token(self, token):
        d = next((d for d in self.divs.values() if d["token"] == token), None)
        return dict(d) if d else None

    def por_id(self, div_id):
        d = self.divs.get(div_id)
        return dict(d) if d else None

    def partes(self, div_id):
        return [dict(p) for p in self._p(div_id)]

    def partes_por_pm(self, pm_id):
        return [dict(p) for p in self.partes_.values() if p["pago_manual_id"] == pm_id]

    def tomar(self, div_id, email, nombre, organizador, lo_que_falta, ahora):
        with self._lock:
            d = self.divs.get(div_id)
            if not d or d["estado"] != "abierta" or d["vence_en"] <= ahora:
                return "cerrada", []
            ps = self._p(div_id)

            def _toma(p, por_org):
                p.update(estado="cobrando", pagador_email=email, pagador_nombre=nombre, por_organizador=por_org,
                         tomada_en=ahora)
            if lo_que_falta:
                mias = [p for p in ps if p["estado"] == "cobrando" and p["pagador_email"] == email]
                for p in ps:
                    if p["estado"] == "libre":
                        _toma(p, p["n"] != 0)
                        mias.append(p)
                return ("", [dict(p) for p in sorted(mias, key=lambda p: p["n"])]) if mias else ("sin_partes", [])
            if organizador:
                p = ps[0]
                if p["estado"] == "libre":
                    _toma(p, False)
                    return "", [dict(p)]
                if p["estado"] == "cobrando" and p["pagador_email"] == email:
                    return "", [dict(p)]
                return ("ya_pagaste" if p["pagador_email"] == email else "sin_partes"), []
            mia = next((p for p in ps if p["pagador_email"] == email and not p["por_organizador"]
                        and p["estado"] in VIVOS), None)
            if mia:
                return ("", [dict(mia)]) if mia["estado"] == "cobrando" else ("ya_pagaste", [])
            libre = next((p for p in ps if p["estado"] == "libre" and p["n"] != 0), None)
            if not libre:
                return "sin_partes", []
            _toma(libre, False)
            return "", [dict(libre)]

    def retomar(self, div_id, ids, email, nombre, organizador, ahora):
        """Vuelve a tomar partes CONCRETAS que siguen libres (la toma de 15 min
        venció mientras el amigo pagaba). Mismas reglas que `tomar`."""
        with self._lock:
            d = self.divs.get(div_id)
            if not d or d["estado"] != "abierta" or d["vence_en"] <= ahora:
                return False
            ps = [self.partes_.get(i) for i in dict.fromkeys(ids)]
            if not ps or any(not p or p["division_id"] != div_id or p["estado"] != "libre" for p in ps):
                return False
            if not organizador:
                if len(ps) != 1 or ps[0]["n"] == 0 or any(
                        x["pagador_email"] == email and not x["por_organizador"] and x["estado"] in VIVOS
                        for x in self._p(div_id)):
                    return False
            for p in ps:
                p.update(estado="cobrando", pagador_email=email, pagador_nombre=nombre,
                         por_organizador=bool(organizador and p["n"] != 0), tomada_en=ahora)
            return True

    def cargo_devuelto(self, charge_id):
        d = self.devueltos.get(charge_id)
        return dict(d) if d else None

    def marcar_cargo_devuelto(self, charge_id, division_id, monto, refund_id, motivo):
        with self._lock:
            self.devueltos.setdefault(charge_id, {"charge_id": charge_id, "division_id": division_id,
                                                  "monto_centimos": int(monto), "refund_id": refund_id,
                                                  "motivo": motivo, "creado_en": _ahora()})
            return True

    def crear_tardio(self, t):
        with self._lock:
            self.tardios[t["id"]] = dict(t)
            return True

    def tardio_por_pm(self, pm_id):
        t = next((t for t in self.tardios.values() if pm_id and t["pago_manual_id"] == pm_id), None)
        return dict(t) if t else None

    def set_tardio(self, tid, desde, campos):
        with self._lock:
            t = self.tardios.get(tid)
            if not t or t["estado"] not in desde:
                return False
            t.update(campos)
            return True

    def cerradas_pendientes(self, corte):
        out = []
        for d in self.divs.values():
            if d["estado"] not in ("vencida", "cancelada") or (d.get("cerrado_en") or d["vence_en"]) > corte:
                continue
            if any(_pendiente_de_devolver(d, p) for p in self._p(d["id"])):
                out.append(dict(d))
        return out

    def soltar(self, div_id, ids, email):
        with self._lock:
            n = 0
            for i in ids:
                p = self.partes_.get(i)
                if p and p["division_id"] == div_id and p["estado"] == "cobrando" and p["pagador_email"] == email:
                    p.update(_LIBRE)
                    n += 1
            return n

    def a_revision(self, div_id, ids, email, pm_id, medio):
        with self._lock:
            d = self.divs.get(div_id)
            ps = [self.partes_.get(i) for i in ids]
            if not d or d["estado"] != "abierta" or any(
                    not p or p["division_id"] != div_id or p["estado"] != "cobrando" or p["pagador_email"] != email
                    for p in ps):
                return False
            for p in ps:
                p.update(estado="en_revision", pago_manual_id=pm_id, medio=medio)
            return True

    def pagar(self, div_id, ids, email, cobros, medio, desde):
        with self._lock:
            d = self.divs.get(div_id)
            ps = [self.partes_.get(i) for i in ids]
            if not d or any(not p or p["division_id"] != div_id for p in ps):
                return "no_tomada"
            if all(p["estado"] == "pagada" and p["cobro_id"] == cobros.get(p["id"]) for p in ps):
                return "completa" if d["estado"] in ("completa", "confirmada") else "ok"
            if d["estado"] != "abierta":
                return "cerrada"
            if any(p["estado"] not in desde or (email and p["pagador_email"] != email) for p in ps):
                return "no_tomada"
            usados = {p["cobro_id"] for p in self.partes_.values() if p["cobro_id"]}
            if any(cobros.get(p["id"]) in usados for p in ps):
                return "no_tomada"
            for p in ps:
                p.update(estado="pagada", cobro_id=cobros[p["id"]], medio=medio, pagada_en=_ahora())
            if all(p["estado"] == "pagada" for p in self._p(div_id)):
                d.update(estado="completa", cerrado_en=_ahora())
                return "completa"
            return "ok"

    def liberar_revision(self, pm_id):
        with self._lock:
            out = []
            for p in self.partes_.values():
                if p["pago_manual_id"] == pm_id and p["estado"] == "en_revision":
                    d = self.divs.get(p["division_id"])
                    if d and d["estado"] == "abierta":
                        p.update(_LIBRE, pago_manual_id="")
                        out.append(dict(p))
            return out

    def transicion(self, div_id, desde, hasta, motivo=""):
        with self._lock:
            d = self.divs.get(div_id)
            if not d or d["estado"] not in desde:
                return False
            d.update(estado=hasta, motivo=motivo or d["motivo"], cerrado_en=d.get("cerrado_en") or _ahora())
            return True

    def set_parte(self, parte_id, desde, campos):
        with self._lock:
            p = self.partes_.get(parte_id)
            if not p or p["estado"] not in desde:
                return False
            p.update(campos)
            return True

    def marcar_aviso(self, div_id):
        with self._lock:
            d = self.divs.get(div_id)
            if not d or d["aviso_en"] is not None:
                return False
            d["aviso_en"] = _ahora()
            return True

    def en_estado(self, estados):
        return [dict(d) for d in self.divs.values() if d["estado"] in estados]

    def tomas_viejas(self, corte):
        return [dict(p) for p in self.partes_.values() if p["estado"] == "cobrando" and p["tomada_en"]
                and p["tomada_en"] < corte]

    def de_email(self, email, limite=30):
        ids = {d["id"] for d in self.divs.values() if d["organizador_email"] == email}
        ids |= {p["division_id"] for p in self.partes_.values() if p["pagador_email"] == email}
        return sorted((dict(self.divs[i]) for i in ids), key=lambda d: d["creado_en"], reverse=True)[:limite]

    def devoluciones_de(self, dueno):
        out = []
        for p in self.partes_.values():
            d = self.divs.get(p["division_id"])
            if d and d["dueno"] == dueno and p["estado"] == "devolver":
                out.append({**dict(p), "division": dict(d)})
        for t in self.tardios.values():
            d = self.divs.get(t["division_id"])
            if d and d["dueno"] == dueno and t["estado"] == "devolver":
                out.append({**_tardio_como_parte(t), "division": dict(d)})
        return sorted(out, key=lambda x: (x["division"]["creado_en"], x["n"]))


class RepoPG:
    """Tablas de la migración 0006 (rol del backend; la anon key no las ve)."""

    def __init__(self):
        self._ok: bool | None = None
        self._t = 0.0

    def disponible(self) -> bool:
        from db import pg
        if not pg.habilitado:
            return False
        if self._ok is True or (self._ok is False and time.time() - self._t < 300):
            return bool(self._ok)
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute("select to_regclass('public.cl_division_pago') is not null "
                            "and to_regclass('public.cl_division_partes') is not null "
                            "and to_regclass('public.cl_division_cargos_devueltos') is not null "
                            "and to_regclass('public.cl_division_tardios') is not null")
                self._ok = bool(cur.fetchone()[0])
        except Exception:  # noqa: BLE001
            self._ok = False
        self._t = time.time()
        return bool(self._ok)

    # utilidades
    @staticmethod
    def _div(f) -> dict | None:
        if not f:
            return None
        d = dict(zip(_COLS_DIV, f))
        if isinstance(d.get("reserva_ids"), str):
            d["reserva_ids"] = json.loads(d["reserva_ids"] or "[]")
        d["reserva_ids"] = list(d.get("reserva_ids") or [])
        return d

    @staticmethod
    def _parte(f) -> dict:
        return dict(zip(_COLS_PARTE, f))

    _SEL_DIV = "select " + ", ".join(_COLS_DIV) + " from cl_division_pago "
    _SEL_PARTE = "select " + ", ".join(_COLS_PARTE) + " from cl_division_partes "

    def _uno(self, sql, args):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            return self._div(cur.fetchone())

    def _partes(self, where, args):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(self._SEL_PARTE + "where " + where, args)
            return [self._parte(f) for f in cur.fetchall()]

    def crear(self, div, partes):
        from db import pg
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cols = [c for c in _COLS_DIV if c not in ("aviso_en", "cerrado_en")]
                cur.execute(f"insert into cl_division_pago ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                            [json.dumps(div[c]) if c == "reserva_ids" else div[c] for c in cols])
                pc = ["id", "division_id", "n", "monto_centimos"]
                cur.executemany(f"insert into cl_division_partes ({', '.join(pc)}) values (%s, %s, %s, %s)",
                                [[p[c] for c in pc] for p in partes])
            return ""
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "uq_cl_div_ref_viva" in msg:
                return "ya_existe"
            print("[dividir] crear error:", msg[:200], flush=True)
            return "error"

    def por_token(self, token):
        return self._uno(self._SEL_DIV + "where token = %s", (token,))

    def por_id(self, div_id):
        return self._uno(self._SEL_DIV + "where id = %s", (div_id,))

    def partes(self, div_id):
        return self._partes("division_id = %s order by n", (div_id,))

    def partes_por_pm(self, pm_id):
        return self._partes("pago_manual_id = %s order by n", (pm_id,))

    def _bloquear(self, cur, div_id):
        cur.execute("select estado, vence_en, organizador_email from cl_division_pago where id = %s for update", (div_id,))
        return cur.fetchone()

    def tomar(self, div_id, email, nombre, organizador, lo_que_falta, ahora):
        from db import pg
        ret = self._SEL_PARTE.replace("select ", "").split(" from ")[0]
        with pg.conexion() as conn, conn.cursor() as cur:
            f = self._bloquear(cur, div_id)
            if not f or f[0] != "abierta" or f[1] <= ahora:
                return "cerrada", []
            if lo_que_falta:
                cur.execute("update cl_division_partes set estado = 'cobrando', pagador_email = %s, pagador_nombre = %s, "
                            "por_organizador = (n <> 0), tomada_en = %s, actualizado_en = now() "
                            "where division_id = %s and estado = 'libre'", (email, nombre, ahora, div_id))
                cur.execute(self._SEL_PARTE + "where division_id = %s and estado = 'cobrando' "
                            "and lower(pagador_email) = %s order by n", (div_id, email))
                mias = [self._parte(x) for x in cur.fetchall()]
                return ("", mias) if mias else ("sin_partes", [])
            if organizador:
                cur.execute(self._SEL_PARTE + "where division_id = %s and n = 0", (div_id,))
                p = self._parte(cur.fetchone())
                if p["estado"] == "libre":
                    cur.execute(f"update cl_division_partes set estado = 'cobrando', pagador_email = %s, pagador_nombre = %s, "
                                f"por_organizador = false, tomada_en = %s, actualizado_en = now() where id = %s returning {ret}",
                                (email, nombre, ahora, p["id"]))
                    return "", [self._parte(cur.fetchone())]
                if p["estado"] == "cobrando" and p["pagador_email"].lower() == email:
                    return "", [p]
                return ("ya_pagaste" if p["pagador_email"].lower() == email else "sin_partes"), []
            cur.execute(self._SEL_PARTE + "where division_id = %s and lower(pagador_email) = %s and not por_organizador "
                        "and estado = any(%s) limit 1", (div_id, email, list(VIVOS)))
            m = cur.fetchone()
            if m:
                mia = self._parte(m)
                return ("", [mia]) if mia["estado"] == "cobrando" else ("ya_pagaste", [])
            cur.execute(f"update cl_division_partes set estado = 'cobrando', pagador_email = %s, pagador_nombre = %s, "
                        f"por_organizador = false, tomada_en = %s, actualizado_en = now() "
                        f"where id = (select id from cl_division_partes where division_id = %s and estado = 'libre' "
                        f"and n <> 0 order by n limit 1 for update skip locked) returning {ret}",
                        (email, nombre, ahora, div_id))
            g = cur.fetchone()
            return ("", [self._parte(g)]) if g else ("sin_partes", [])

    def retomar(self, div_id, ids, email, nombre, organizador, ahora):
        from db import pg
        ids = list(dict.fromkeys(ids))
        with pg.conexion() as conn, conn.cursor() as cur:
            f = self._bloquear(cur, div_id)
            if not f or f[0] != "abierta" or f[1] <= ahora:
                return False
            cur.execute(self._SEL_PARTE + "where division_id = %s and id = any(%s) order by n for update", (div_id, ids))
            ps = [self._parte(x) for x in cur.fetchall()]
            if not ps or len(ps) != len(ids) or any(p["estado"] != "libre" for p in ps):
                return False
            if not organizador and (len(ps) != 1 or ps[0]["n"] == 0):
                return False
            try:
                cur.execute("update cl_division_partes set estado = 'cobrando', pagador_email = %s, pagador_nombre = %s, "
                            "por_organizador = (%s and n <> 0), tomada_en = %s, actualizado_en = now() "
                            "where division_id = %s and id = any(%s) and estado = 'libre'",
                            (email, nombre, bool(organizador), ahora, div_id, ids))
                if cur.rowcount != len(ids):
                    conn.rollback()
                    return False
            except Exception as e:  # noqa: BLE001 — ya tiene otra parte viva (uq_cl_divp_pagador)
                conn.rollback()
                print("[dividir] retomar rechazado:", str(e)[:160], flush=True)
                return False
            return True

    def cargo_devuelto(self, charge_id):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("select charge_id, division_id, monto_centimos, refund_id, motivo from cl_division_cargos_devueltos "
                        "where charge_id = %s", (charge_id,))
            f = cur.fetchone()
            return dict(zip(["charge_id", "division_id", "monto_centimos", "refund_id", "motivo"], f)) if f else None

    def marcar_cargo_devuelto(self, charge_id, division_id, monto, refund_id, motivo):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("insert into cl_division_cargos_devueltos (charge_id, division_id, monto_centimos, refund_id, motivo) "
                        "values (%s, %s, %s, %s, %s) on conflict (charge_id) do nothing",
                        (charge_id, division_id, int(monto), refund_id, motivo))
            return True

    _COLS_TARDIO = ["id", "division_id", "n", "pagador_email", "pagador_nombre", "monto_centimos", "medio",
                    "pago_manual_id", "estado", "nota", "creado_en", "resuelta_en"]

    def crear_tardio(self, t):
        from db import pg
        cols = [c for c in self._COLS_TARDIO if c not in ("creado_en", "resuelta_en")]
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"insert into cl_division_tardios ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))})",
                        [t[c] for c in cols])
            return True

    def tardio_por_pm(self, pm_id):
        from db import pg
        if not pm_id:
            return None
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("select " + ", ".join(self._COLS_TARDIO) + " from cl_division_tardios where pago_manual_id = %s "
                        "order by creado_en limit 1", (pm_id,))
            f = cur.fetchone()
            return dict(zip(self._COLS_TARDIO, f)) if f else None

    def set_tardio(self, tid, desde, campos):
        from db import pg
        cols = [c for c in campos if c in self._COLS_TARDIO and c not in ("id", "division_id")]
        if not cols:
            return False
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"update cl_division_tardios set {', '.join(c + ' = %s' for c in cols)} "
                        "where id = %s and estado = any(%s)", [campos[c] for c in cols] + [tid, list(desde)])
            return cur.rowcount == 1

    def cerradas_pendientes(self, corte):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(self._SEL_DIV + "d where d.estado in ('vencida', 'cancelada') "
                        "and coalesce(d.cerrado_en, d.vence_en) <= %s and exists (select 1 from cl_division_partes p "
                        "where p.division_id = d.id and (p.estado in ('cobrando', 'en_revision') or (p.estado = 'pagada' "
                        "and (d.motivo <> 'reserva_cancelada' or p.devolver_centimos > 0)))) "
                        "order by d.vence_en limit 200", (corte,))
            return [self._div(f) for f in cur.fetchall()]

    def soltar(self, div_id, ids, email):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("update cl_division_partes set estado = 'libre', pagador_email = '', pagador_nombre = '', "
                        "por_organizador = false, medio = '', tomada_en = null, actualizado_en = now() "
                        "where division_id = %s and id = any(%s) and estado = 'cobrando' and lower(pagador_email) = %s",
                        (div_id, list(ids), email))
            return cur.rowcount

    def a_revision(self, div_id, ids, email, pm_id, medio):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            f = self._bloquear(cur, div_id)
            if not f or f[0] != "abierta":
                return False
            cur.execute("update cl_division_partes set estado = 'en_revision', pago_manual_id = %s, medio = %s, "
                        "actualizado_en = now() where division_id = %s and id = any(%s) and estado = 'cobrando' "
                        "and lower(pagador_email) = %s", (pm_id, medio, div_id, list(ids), email))
            if cur.rowcount != len(set(ids)):
                conn.rollback()
                return False
            return True

    def pagar(self, div_id, ids, email, cobros, medio, desde):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            f = self._bloquear(cur, div_id)
            if not f:
                return "no_tomada"
            cur.execute(self._SEL_PARTE + "where division_id = %s and id = any(%s) order by n for update",
                        (div_id, list(ids)))
            ps = [self._parte(x) for x in cur.fetchall()]
            if len(ps) != len(set(ids)):
                return "no_tomada"
            if all(p["estado"] == "pagada" and p["cobro_id"] == cobros.get(p["id"]) for p in ps):
                return "completa" if f[0] in ("completa", "confirmada") else "ok"
            if f[0] != "abierta":
                return "cerrada"
            if any(p["estado"] not in desde or (email and p["pagador_email"].lower() != email) for p in ps):
                return "no_tomada"
            try:
                for p in ps:
                    cur.execute("update cl_division_partes set estado = 'pagada', cobro_id = %s, medio = %s, "
                                "pagada_en = now(), actualizado_en = now() where id = %s", (cobros[p["id"]], medio, p["id"]))
            except Exception as e:  # noqa: BLE001 — cobro ya usado en otra parte (uq_cl_divp_cobro)
                conn.rollback()
                print("[dividir] pagar rechazado:", str(e)[:160], flush=True)
                return "no_tomada"
            cur.execute("select count(*) from cl_division_partes where division_id = %s and estado <> 'pagada'", (div_id,))
            if int(cur.fetchone()[0]) == 0:
                cur.execute("update cl_division_pago set estado = 'completa', cerrado_en = now() where id = %s", (div_id,))
                return "completa"
            return "ok"

    def liberar_revision(self, pm_id):
        from db import pg
        ret = self._SEL_PARTE.replace("select ", "").split(" from ")[0]
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("select distinct division_id from cl_division_partes where pago_manual_id = %s", (pm_id,))
            divs = [x[0] for x in cur.fetchall()]
            out = []
            for d in divs:
                f = self._bloquear(cur, d)
                if not f or f[0] != "abierta":
                    continue
                cur.execute(f"update cl_division_partes set estado = 'libre', pagador_email = '', pagador_nombre = '', "
                            f"por_organizador = false, medio = '', pago_manual_id = '', tomada_en = null, actualizado_en = now() "
                            f"where division_id = %s and pago_manual_id = %s and estado = 'en_revision' returning {ret}",
                            (d, pm_id))
                out += [self._parte(x) for x in cur.fetchall()]
            return out

    def transicion(self, div_id, desde, hasta, motivo=""):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("update cl_division_pago set estado = %s, motivo = case when %s = '' then motivo else %s end, "
                        "cerrado_en = coalesce(cerrado_en, now()) where id = %s and estado = any(%s)",
                        (hasta, motivo, motivo, div_id, list(desde)))
            return cur.rowcount == 1

    def set_parte(self, parte_id, desde, campos):
        from db import pg
        cols = [c for c in campos if c in _COLS_PARTE and c not in ("id", "division_id", "n")]
        if not cols:
            return False
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(f"update cl_division_partes set {', '.join(c + ' = %s' for c in cols)}, actualizado_en = now() "
                        "where id = %s and estado = any(%s)", [campos[c] for c in cols] + [parte_id, list(desde)])
            return cur.rowcount == 1

    def marcar_aviso(self, div_id):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("update cl_division_pago set aviso_en = now() where id = %s and aviso_en is null", (div_id,))
            return cur.rowcount == 1

    def en_estado(self, estados):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(self._SEL_DIV + "where estado = any(%s) order by vence_en limit 500", (list(estados),))
            return [self._div(f) for f in cur.fetchall()]

    def tomas_viejas(self, corte):
        return self._partes("estado = 'cobrando' and tomada_en < %s", (corte,))

    def de_email(self, email, limite=30):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(self._SEL_DIV + "where lower(organizador_email) = %s or id in (select division_id from "
                        "cl_division_partes where lower(pagador_email) = %s) order by creado_en desc limit %s",
                        (email, email, int(limite)))
            return [self._div(f) for f in cur.fetchall()]

    def devoluciones_de(self, dueno):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("select " + ", ".join("p." + c for c in _COLS_PARTE) + ", " + ", ".join("d." + c for c in _COLS_DIV)
                        + " from cl_division_partes p join cl_division_pago d on d.id = p.division_id "
                        "where d.dueno = %s and p.estado = 'devolver' order by d.creado_en, p.n", (dueno,))
            out = []
            for f in cur.fetchall():
                p = self._parte(f[:len(_COLS_PARTE)])
                p["division"] = self._div(f[len(_COLS_PARTE):])
                out.append(p)
            cur.execute("select " + ", ".join("t." + c for c in self._COLS_TARDIO) + ", " + ", ".join("d." + c for c in _COLS_DIV)
                        + " from cl_division_tardios t join cl_division_pago d on d.id = t.division_id "
                        "where d.dueno = %s and t.estado = 'devolver' order by d.creado_en, t.n", (dueno,))
            k = len(self._COLS_TARDIO)
            for f in cur.fetchall():
                t = _tardio_como_parte(dict(zip(self._COLS_TARDIO, f[:k])))
                t["division"] = self._div(f[k:])
                out.append(t)
            return sorted(out, key=lambda x: (x["division"]["creado_en"], x["n"]))


_repo = RepoPG()


def usar_repo(repo) -> None:
    """Tests: inyecta un repositorio (p. ej. `RepoMemoria()`)."""
    global _repo
    _repo = repo


def repo():
    return _repo


def disponible() -> bool:
    try:
        return bool(_repo.disponible())
    except Exception:  # noqa: BLE001
        return False


# ── utilidades de dominio ────────────────────────────────────────────────────

def _wr():
    from web import router as wr
    return wr


def _cdw():
    from web import cobro_directo_web as cdw
    return cdw


def _avisar(email: str, titulo: str, texto: str) -> None:
    if not email:
        return
    try:
        from pagos.router import _aviso_push_usuario
        _aviso_push_usuario(email, titulo, texto, tipo="reserva")
    except Exception:  # noqa: BLE001 — un aviso nunca rompe un pago
        pass


def _plata(centimos: int, iso: str) -> str:
    from paises import simbolo_de_moneda
    from web import ui
    return ui.monto(int(centimos or 0) / 100.0, simbolo_de_moneda(iso))


def _cuando(div: dict) -> str:
    from web import datos, horarios
    filas = datos.reservas_de(list(div["reserva_ids"])) if div.get("reserva_ids") else []
    if not filas:
        return ""
    return f"{horarios.fecha_larga(str(filas[0]['fecha']))} {filas[0]['hora_inicio']}–{filas[-1]['hora_fin']}"


def _base_charge(cobro_id: str) -> str:
    return str(cobro_id or "").split("#")[0]


def url(div: dict) -> str:
    return f"/dividir/{div['token']}"


# ── crear (lo llama /web/asegurar) ───────────────────────────────────────────

def validar(*, c: dict, directo: dict, n: int, total_centimos: int, inicio: datetime | None,
            incompatibles: bool, con_sesion: bool) -> str:
    """'' si se puede dividir este bloque; si no, el código de error."""
    if not con_sesion:
        return "sesion_requerida"
    if not disponible() or not (directo or {}).get("directo"):
        return "dividir_no_disponible"
    if incompatibles:
        return "dividir_no_combinable"
    if not (MIN_PARTES <= int(n) <= MAX_PARTES):
        return "dividir_partes"
    if int(n) > max_partes(total_centimos):
        return "dividir_monto"
    if vence_para(inicio) is None:
        return "dividir_muy_tarde"
    return ""


def crear(*, filas: list[dict], c: dict, email: str, nombre: str, n: int, total_centimos: int,
          inicio: datetime) -> dict:
    """Crea la división de un bloque YA apartado (`medio_pago = 'division'`)."""
    wr = _wr()
    _sim, iso = wr._moneda_de(c)
    ahora = _ahora()
    vence = vence_para(inicio, ahora)
    if vence is None:
        return {"ok": False, "error": "dividir_muy_tarde"}
    montos = calcular_partes(total_centimos, n)
    did = f"div_{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    div = {"id": did, "token": secrets.token_urlsafe(18), "reserva_ref": wr._ref_de(filas),
           "reserva_ids": [str(f["id"]) for f in filas], "cancha_id": c["id"],
           "dueno": (c.get("dueno") or "").strip().lower(), "organizador_email": email,
           "organizador_nombre": (nombre or "")[:80], "moneda": iso, "total_centimos": int(total_centimos),
           "partes": int(n), "parte_centimos": montos[1], "estado": "abierta", "motivo": "", "vence_en": vence,
           "aviso_en": None, "creado_en": ahora, "cerrado_en": None}
    partes = [{"id": f"{did}_{i}", "division_id": did, "n": i, "monto_centimos": m, **_LIBRE, "cobro_id": "",
               "pago_manual_id": "", "refund_id": "", "devolver_centimos": 0, "nota": "", "pagada_en": None,
               "resuelta_en": None} for i, m in enumerate(montos)]
    err = _repo.crear(div, partes)
    if err:
        return {"ok": False, "error": err}
    print(f"[dividir] {did} {div['reserva_ref']} {email} {n} partes total={total_centimos} vence={vence.isoformat()}", flush=True)
    return {"ok": True, "id": did, "token": div["token"], "url": url(div), "partes": montos,
            "vence_en": vence.isoformat(), "moneda": iso}


# ── vista ────────────────────────────────────────────────────────────────────

def _nombre_corto(nombre: str, email: str) -> str:
    """'Ana Pérez' → 'Ana P.' (nunca el correo de otra persona)."""
    p = (nombre or "").split()
    if not p:
        return "Un amigo"
    return p[0][:20] + (f" {p[1][0]}." if len(p) > 1 and p[1] else "")


def vista(div: dict, email: str) -> dict:
    """Estado público de la división para quien mira el enlace (sin correos ajenos)."""
    partes = _repo.partes(div["id"])
    email = (email or "").strip().lower()
    org = div["organizador_email"].lower() == email
    lista = []
    for p in partes:
        mia = p["pagador_email"].lower() == email and bool(email)
        quien = ("Tú" if mia else _nombre_corto(p["pagador_nombre"], p["pagador_email"])) if p["pagador_email"] else ""
        lista.append({"id": p["id"], "n": p["n"], "monto_centimos": p["monto_centimos"], "estado": p["estado"],
                      "quien": quien, "mia": mia, "organizador": p["n"] == 0, "por_organizador": p["por_organizador"],
                      "devolver_centimos": p["devolver_centimos"], "refund_id": bool(p["refund_id"])})
    pagadas = sum(1 for p in partes if p["estado"] == "pagada")
    revision = sum(1 for p in partes if p["estado"] == "en_revision")
    falta = sum(p["monto_centimos"] for p in partes if p["estado"] == "libre")
    seg = max(0, int((div["vence_en"] - _ahora()).total_seconds())) if div["estado"] == "abierta" else 0
    huella = "|".join(f"{p['n']}:{p['estado']}" for p in partes) + f"|{div['estado']}"
    return {"ok": True, "estado": div["estado"], "motivo": div.get("motivo") or "", "organizador": org,
            "organizador_nombre": _nombre_corto(div["organizador_nombre"], ""), "moneda": div["moneda"],
            "total_centimos": div["total_centimos"], "n": div["partes"], "pagadas": pagadas, "en_revision": revision,
            "falta_centimos": falta, "partes": lista, "vence_en": div["vence_en"].isoformat(), "segundos": seg,
            "version": huella}


# ── tomar / soltar ───────────────────────────────────────────────────────────

def tomar(div: dict, email: str, nombre: str, lo_que_falta: bool = False) -> dict:
    org = div["organizador_email"].lower() == email
    if lo_que_falta and not org:
        return {"ok": False, "error": "solo_organizador"}
    err, partes = _repo.tomar(div["id"], email, (nombre or "")[:80], org, bool(lo_que_falta), _ahora())
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "partes": [p["id"] for p in partes], "monto_centimos": sum(p["monto_centimos"] for p in partes),
            "n": [p["n"] for p in partes], "segundos": TOMA_MAX_MIN * 60}


def soltar(div: dict, email: str, ids: list[str]) -> dict:
    return {"ok": True, "soltadas": _repo.soltar(div["id"], ids, email)}


def _mis_partes(div: dict, email: str, ids: list[str], estados=("cobrando",)) -> list[dict]:
    ps = {p["id"]: p for p in _repo.partes(div["id"])}
    out = [ps.get(i) for i in dict.fromkeys(ids)]
    if not out or any(p is None or p["estado"] not in estados or p["pagador_email"].lower() != email for p in out):
        return []
    return out


# ── pagar con el Culqi DEL CLUB ──────────────────────────────────────────────

def pagar_culqi(div: dict, email: str, nombre: str, ids: list[str], token: str, medio: str) -> dict:
    from pagos import cobro_directo as cd
    from pagos import culqi
    from web import datos
    partes = _mis_partes(div, email, ids)
    if not partes:
        return {"ok": False, "error": "no_tomada", "mensaje": mensaje("no_tomada")}
    c = datos.cancha(div["cancha_id"]) or {}
    llave = cd.llave_secreta(div["dueno"])
    if div["moneda"] != "PEN" or not llave or cd.suspendido(div["dueno"], div["moneda"]):
        return {"ok": False, "error": "pago_no_disponible", "mensaje": "El pago en línea de este club no está disponible. Paga con comprobante."}
    monto = sum(p["monto_centimos"] for p in partes)
    from db.store import stores
    from paises import pais_de_coordenadas
    cliente = stores.cliente_de(email, nombre=nombre, telefono="", pais=(pais_de_coordenadas(c.get("lat"), c.get("lng")) or ""))
    desc = f"Parte de reserva {c.get('nombre', 'cancha')} {div['reserva_ref'][-12:]}"
    cargo = culqi.crear_cargo(token=token, monto_centimos=monto, email=email, descripcion=desc[:80], moneda="PEN",
                              cliente=cliente, llave=llave,
                              metadata={"canal": "division", "division_id": div["id"],
                                        "partes": ",".join(p["id"] for p in partes), "email": email})
    if not cargo.get("ok"):
        _repo.soltar(div["id"], [p["id"] for p in partes], email)
        msg = str(cargo.get("error") or "")
        return {"ok": False, "error": "cargo_rechazado",
                "mensaje": "El pago fue rechazado por tu banco o billetera. No se te cobró nada; puedes intentarlo de nuevo."
                           + (f" ({msg[:80]})" if msg else "")}
    charge_id = str(cargo.get("charge_id") or "")
    medio = "yape" if medio == "yape" else "tarjeta"
    return _registrar_cargo(div, partes, email, charge_id, monto, medio, llave)


def _reembolsar_cargo(div: dict, charge_id: str, monto: int, motivo: str, llave: str) -> dict:
    """Devuelve [monto] de un cargo del Culqi del club UNA sola vez. Lo ya
    devuelto queda en `cl_division_cargos_devueltos`: un barrido que se reanuda
    tras un error no vuelve a llamar a Culqi, y un webhook tardío de ese cargo
    se ignora (`conciliar_cargo`)."""
    from pagos import culqi
    previo = _repo.cargo_devuelto(charge_id)
    if previo:
        return {"ok": True, "refund_id": previo.get("refund_id") or "", "previo": True}
    r = culqi.reembolsar(charge_id=charge_id, monto_centimos=int(monto), motivo="solicitud_comprador", llave=llave)
    if r.get("ok"):
        try:
            _repo.marcar_cargo_devuelto(charge_id, div["id"], int(monto), str(r.get("refund_id") or "")[:80], motivo[:60])
        except Exception as e:  # noqa: BLE001 — el reembolso ya salió: solo queda sin registro
            print(f"[dividir] {div['id']} reembolso de {charge_id} OK pero no se registró: {str(e)[:120]}", flush=True)
    return r


def _registrar_cargo(div: dict, partes: list[dict], email: str, charge_id: str, monto: int, medio: str, llave: str) -> dict:
    cobros = {p["id"]: f"{charge_id}#{p['n']}" for p in partes}
    r = _repo.pagar(div["id"], [p["id"] for p in partes], email, cobros, medio, ("cobrando",))
    if r in ("cerrada", "no_tomada"):
        # El plazo cerró (o la parte se soltó) MIENTRAS Culqi cobraba: se devuelve ya, en el servidor.
        rr = _reembolsar_cargo(div, charge_id, monto, "sin_parte", llave)
        print(f"[dividir] {div['id']} cargo {charge_id} sin parte viva ({r}) → reembolso "
              f"{'ok' if rr.get('ok') else rr.get('error')}", flush=True)
        return {"ok": False, "error": "cerrada" if r == "cerrada" else "no_tomada",
                "mensaje": "Esta división ya se cerró antes de confirmar tu pago. Te devolvimos el dinero."
                           if rr.get("ok") else "Esta división ya se cerró. El club te devolverá el dinero; te avisamos."}
    if r == "completa":
        confirmar(div["id"])
    return {"ok": True, "estado": r, "charge_id": charge_id}


def _capturado(info: dict) -> bool:
    """¿El cargo entró de verdad? (capturado y, si Culqi lo informa, venta exitosa)."""
    raw = info.get("raw") if isinstance(info.get("raw"), dict) else {}
    if "capture" in raw and not raw.get("capture"):
        return False
    outcome = raw.get("outcome") if isinstance(raw.get("outcome"), dict) else {}
    if outcome.get("type") and str(outcome["type"]) != "venta_exitosa":
        return False
    return bool(info.get("capturado"))


def conciliar_cargo(info: dict, charge_id: str, llave: str, dueno: str = "") -> dict:
    """Webhook de la cuenta Culqi del club con `canal = division`: si el cargo
    entró pero la conexión se cortó antes de registrar la parte, aquí se
    registra (idempotente por `cobro_id`); si ya no hay parte que pagar, se
    devuelve. [dueno] = el club dueño de la cuenta Culqi del webhook: la
    metadata del cargo NO basta (la escribe quien crea el cargo)."""
    meta = info.get("metadata") or {}
    div = _repo.por_id(str(meta.get("division_id") or ""))
    ids = [x for x in str(meta.get("partes") or "").split(",") if x]
    email = str(meta.get("email") or "").strip().lower()
    if not div or not ids or not email:
        return {"ok": True, "ignorado": "sin_division"}
    if not dueno or (div.get("dueno") or "").strip().lower() != dueno.strip().lower():
        print(f"[dividir] webhook {charge_id}: la división {div['id']} no es del club del webhook", flush=True)
        return {"ok": True, "ignorado": "otro_club"}
    if _repo.cargo_devuelto(charge_id) or int(info.get("reembolsado_centimos") or 0) > 0:
        return {"ok": True, "ignorado": "reembolsado"}
    if div["moneda"] != "PEN" or str(info.get("moneda") or "").upper() != "PEN":
        print(f"[dividir] webhook {charge_id}: moneda {info.get('moneda')!r}, se deja al operador", flush=True)
        return {"ok": True, "ignorado": "moneda"}
    if not _capturado(info):
        return {"ok": True, "ignorado": "no_capturado"}
    partes = {p["id"]: p for p in _repo.partes(div["id"])}
    sel = [partes.get(i) for i in ids]
    if any(p is None for p in sel):
        return {"ok": True, "ignorado": "partes"}
    monto = int(info.get("monto_centimos") or 0)
    if monto != sum(p["monto_centimos"] for p in sel):
        print(f"[dividir] webhook {charge_id}: monto distinto, se deja al operador", flush=True)
        return {"ok": True, "ignorado": "monto"}
    if all(p["cobro_id"] == f"{charge_id}#{p['n']}" for p in sel):
        return {"ok": True, "duplicado": True}
    r = _registrar_cargo(div, sel, email, charge_id, monto, "tarjeta", llave)
    return {"ok": True, "registrado": bool(r.get("ok"))}


# ── voucher de una parte ─────────────────────────────────────────────────────

_TXT_TARDIO = {
    "toma_vencida": "Tu parte ya no estaba reservada para ti (pasaron los 15 minutos para pagarla)",
    "division_cerrada": "Esta reserva dividida ya se cerró",
}


def _voucher_tardio(div: dict, email: str, nombre: str, sel: list[dict], medio: str, operacion: str,
                    imagen_b64: str, motivo: str) -> dict:
    """El amigo YA pagó al club (Yape, Plin…) pero su parte ya no es suya. El
    pago no cuenta para la reserva; el comprobante se guarda y el club lo
    revisa: si el dinero llegó (o vence sin revisar) queda en Devoluciones."""
    from pagos import cobro_directo as cd
    from web import datos
    c = datos.cancha(div["cancha_id"]) or {}
    monto = sum(int(p["monto_centimos"]) for p in sel)
    filas = datos.reservas_de(list(div["reserva_ids"]))
    r = cd.registrar_voucher(filas=filas, c=c, email=email,
                             nombre=f"{(nombre or email)[:50]} · pago fuera de plazo (pago dividido)",
                             medio=medio, operacion=operacion, imagen_b64=imagen_b64, monto_centimos=monto,
                             iso=div["moneda"], ref=f"{div['id']}#t{secrets.token_hex(4)}")
    if not r.get("ok"):
        return r
    try:
        _repo.crear_tardio({"id": f"dvt_{int(time.time() * 1000)}_{secrets.token_hex(3)}", "division_id": div["id"],
                            "n": min(int(p["n"]) for p in sel), "pagador_email": email,
                            "pagador_nombre": (nombre or "")[:80], "monto_centimos": monto,
                            "medio": f"voucher_{(medio or '').strip().lower()}", "pago_manual_id": r["pago_id"],
                            "estado": "en_revision", "nota": motivo})
    except Exception as e:  # noqa: BLE001 — sin el registro el club igual ve el comprobante en su bandeja
        print(f"[dividir] {div['id']} no se pudo guardar el pago tardío {r['pago_id']}: {str(e)[:120]}", flush=True)
    _avisar(div["dueno"], "Revisa un pago fuera de plazo 🧾",
            f"{nombre or email} subió un comprobante de una reserva dividida en {c.get('nombre', '')} cuando su parte ya "
            "no estaba reservada. No cuenta para la reserva: si te llegó el dinero, apruébalo y devuélveselo.")
    print(f"[dividir] {div['id']} comprobante tardío ({motivo}) de {email} por {monto}", flush=True)
    return {"ok": True, "pago_id": r["pago_id"], "tardio": True,
            "mensaje": f"{_TXT_TARDIO.get(motivo, _TXT_TARDIO['division_cerrada'])}, así que este pago no cuenta para la "
                       "reserva. Guardamos tu comprobante: el club lo revisará y, si recibió tu dinero, te lo devolverá. "
                       "Te avisamos."}


def subir_voucher(div: dict, email: str, nombre: str, ids: list[str], medio: str, operacion: str, imagen_b64: str) -> dict:
    from pagos import cobro_directo as cd
    from web import datos
    partes = _mis_partes(div, email, ids)
    if not partes:
        # La toma de 15 min venció mientras pagaba (o la división se cerró). Si la
        # parte sigue libre y hay plazo, se vuelve a tomar; si no, el comprobante
        # igual se guarda para que el club devuelva lo que ya recibió.
        todas = {p["id"]: p for p in _repo.partes(div["id"])}
        sel = [todas.get(i) for i in dict.fromkeys(ids)]
        if not sel or any(p is None for p in sel):
            return {"ok": False, "error": "no_tomada", "mensaje": mensaje("no_tomada")}
        if any(p["pagador_email"].lower() == email and p["estado"] in ("en_revision", "pagada") for p in sel):
            return {"ok": False, "error": "ya_pagaste", "mensaje": mensaje("ya_pagaste")}
        org = div["organizador_email"].lower() == email
        if _repo.retomar(div["id"], [p["id"] for p in sel], email, (nombre or "")[:80], org, _ahora()):
            partes = _mis_partes(div, email, ids)
        if not partes:
            actual = _repo.por_id(div["id"]) or div
            cerrada = actual["estado"] != "abierta" or actual["vence_en"] <= _ahora()
            return _voucher_tardio(actual, email, nombre, sel, medio, operacion, imagen_b64,
                                   "division_cerrada" if cerrada else "toma_vencida")
    c = datos.cancha(div["cancha_id"]) or {}
    filas = datos.reservas_de(list(div["reserva_ids"]))
    etiqueta = ("parte" if len(partes) == 1 else "partes") + " " + ", ".join(str(p["n"] + 1) for p in partes)
    r = cd.registrar_voucher(filas=filas, c=c, email=email,
                             nombre=f"{(nombre or email)[:50]} · {etiqueta} de {div['partes']} (pago dividido)",
                             medio=medio, operacion=operacion, imagen_b64=imagen_b64,
                             monto_centimos=sum(p["monto_centimos"] for p in partes), iso=div["moneda"],
                             ref=f"{div['id']}#{partes[0]['n']}", vence_en=div["vence_en"])
    if not r.get("ok"):
        return r
    if not _repo.a_revision(div["id"], [p["id"] for p in partes], email, r["pago_id"], f"voucher_{medio}"):
        # La división se cerró entre la toma y el envío: el comprobante queda como
        # pago tardío (vence con la división → Devoluciones "sin revisar").
        try:
            _repo.crear_tardio({"id": f"dvt_{int(time.time() * 1000)}_{secrets.token_hex(3)}", "division_id": div["id"],
                                "n": partes[0]["n"], "pagador_email": email, "pagador_nombre": (nombre or "")[:80],
                                "monto_centimos": sum(p["monto_centimos"] for p in partes),
                                "medio": f"voucher_{medio}", "pago_manual_id": r["pago_id"], "estado": "en_revision",
                                "nota": "division_cerrada"})
        except Exception as e:  # noqa: BLE001
            print(f"[dividir] {div['id']} no se pudo guardar el pago tardío {r['pago_id']}: {str(e)[:120]}", flush=True)
        _repo.soltar(div["id"], [p["id"] for p in partes], email)
        return {"ok": True, "pago_id": r["pago_id"], "tardio": True,
                "mensaje": f"{_TXT_TARDIO['division_cerrada']}, así que este pago no cuenta para la reserva. Guardamos tu "
                           "comprobante: el club lo revisará y, si recibió tu dinero, te lo devolverá. Te avisamos."}
    _avisar(div["dueno"], "Confirma un pago 🧾",
            f"{nombre or email} reportó su parte de una reserva dividida en {c.get('nombre', '')}. Revísalo en Pagos por confirmar.")
    return {"ok": True, "pago_id": r["pago_id"],
            "mensaje": "Recibimos tu comprobante. El club lo confirmará; tu parte cuenta como pagada cuando lo apruebe."}


def _tardio_resuelto(p: dict, estado: str, nota: str = "") -> dict | None:
    """Resuelve el registro de un comprobante tardío (si [p] es uno)."""
    t = _repo.tardio_por_pm(p["id"])
    if not t:
        return None
    campos = {"estado": estado, "resuelta_en": _ahora() if estado != "devolver" else None}
    if nota:
        campos["nota"] = nota
    _repo.set_tardio(t["id"], ("en_revision",), campos)
    return t


def voucher_aprobado(p: dict, email: str) -> dict:
    """El club aprueba el voucher de una parte (`cobro_directo_web.aprobar_voucher`)."""
    from pagos import cobro_directo as cd
    partes = _repo.partes_por_pm(p["id"])
    if not partes and _repo.tardio_por_pm(p["id"]):
        # Comprobante tardío: aprobar = "me llegó el dinero" → hay que devolverlo.
        if not cd.repo().resolver_pago_manual(p["id"], "aprobado", email):
            return {"ok": False, "error": "ya_resuelto"}
        t = _tardio_resuelto(p, "devolver", "aprobado_tarde")
        div = _repo.por_id(t["division_id"]) if t else None
        moneda = div["moneda"] if div else str(p.get("moneda") or "PEN")
        _avisar(p["dueno"], "Devuelve un pago 💸",
                f"Confirmaste el pago fuera de plazo de {p.get('jugador_nombre') or p.get('jugador_email')}. Devuélvele "
                f"{_plata(int(p['monto_centimos']), moneda)} y márcalo en Pagos por confirmar → Devoluciones.")
        _avisar(p["jugador_email"], "El club recibió tu pago 💸",
                "Tu pago llegó fuera de plazo y no cuenta para la reserva dividida: el club te lo devolverá.")
        return {"ok": True, "aviso": "division_cerrada"}
    div = _repo.por_id(partes[0]["division_id"]) if partes else None
    if not div:
        return {"ok": False, "error": "no_encontrado"}
    if not cd.repo().resolver_pago_manual(p["id"], "aprobado", email):
        return {"ok": False, "error": "ya_resuelto"}
    cobros = {x["id"]: f"pm:{p['id']}#{x['n']}" for x in partes}
    r = _repo.pagar(div["id"], [x["id"] for x in partes], None, cobros, f"voucher_{p['medio']}", ("en_revision",))
    if r in ("cerrada", "no_tomada"):
        # Aprobó tarde (el plazo ya se cerró): el club recibió la plata y la devuelve.
        for x in partes:
            _repo.set_parte(x["id"], ("en_revision", "libre", "devolver"),
                            {"estado": "devolver", "devolver_centimos": x["monto_centimos"], "nota": "aprobado_tarde",
                             "cobro_id": cobros[x["id"]], "medio": f"voucher_{p['medio']}"})
        _avisar(div["dueno"], "Devuelve un pago 💸",
                f"Aprobaste el pago de {p.get('jugador_email')} cuando la reserva dividida ya había vencido. "
                f"Devuélvele {_plata(int(p['monto_centimos']), div['moneda'])} y márcalo en Pagos por confirmar → Devoluciones.")
        return {"ok": True, "aviso": "division_cerrada"}
    _avisar(p["jugador_email"], "Tu parte quedó pagada ✅", "El club confirmó tu pago de la reserva dividida.")
    if r == "completa":
        confirmar(div["id"])
    return {"ok": True}


def voucher_rechazado(p: dict, email: str, motivo: str = "") -> dict:
    from pagos import cobro_directo as cd
    if not cd.repo().resolver_pago_manual(p["id"], "rechazado", email, motivo):
        return {"ok": False, "error": "ya_resuelto"}
    if _tardio_resuelto(p, "rechazado"):
        _avisar(p["jugador_email"], "Pago no confirmado",
                "El club no reconoció el comprobante que subiste fuera de plazo. Si sí pagaste, escríbele al club.")
        return {"ok": True}
    _repo.liberar_revision(p["id"])
    _avisar(p["jugador_email"], "Pago no confirmado",
            "El club no pudo confirmar el comprobante de tu parte. Tu parte quedó libre: si no pagaste, vuelve a intentarlo; "
            "si ya pagaste, escríbele al club.")
    return {"ok": True}


def voucher_vencido(p: dict) -> bool:
    """El voucher de una parte venció sin revisión (su plazo = el de la división):
    la parte queda para devolver si la división se cerró; si no, vuelve a libre."""
    from pagos import cobro_directo as cd
    if not cd.repo().resolver_pago_manual(p["id"], "vencido", "sistema", "sin_revision"):
        return False
    if _tardio_resuelto(p, "devolver", "sin_revisar"):
        return True   # pago tardío nunca revisado: el club devuelve si lo recibió
    partes = _repo.partes_por_pm(p["id"])
    div = _repo.por_id(partes[0]["division_id"]) if partes else None
    if div and div["estado"] == "abierta" and div["vence_en"] > _ahora():
        _repo.liberar_revision(p["id"])   # aún hay plazo: la parte vuelve a quedar libre
        return True
    # Sin plazo: el amigo pudo haber pagado → el club devuelve si lo recibió.
    for x in partes:
        _repo.set_parte(x["id"], ("en_revision",), {"estado": "devolver", "devolver_centimos": x["monto_centimos"],
                                                     "nota": "sin_revisar"})
    return True


# ── confirmar (todas pagadas) ────────────────────────────────────────────────

_lock_conf = threading.Lock()


def _leer_filas(ids: list[str]) -> list[dict] | None:
    """Filas del apartado o None si la base no respondió (NUNCA [] por un error:
    "no pude leer" no es "el apartado se perdió")."""
    from web import datos
    try:
        return datos.reservas_de(list(ids), estricto=True)
    except Exception as e:  # noqa: BLE001
        print(f"[dividir] no se pudo leer el apartado: {str(e)[:120]}", flush=True)
        return None


def confirmar(div_id: str) -> dict:
    """Todas las partes pagadas: confirma la reserva con el MISMO camino que un
    cobro directo (filas, cobro total `div:<id>`, una comisión, avisos). Si la
    base falla, la división sigue `completa` y el barrido reintenta."""
    from web import datos
    with _lock_conf:
        div = _repo.por_id(div_id)
        if not div or div["estado"] != "completa":
            return {"ok": False, "error": "no_completa"}
        filas = _leer_filas(div["reserva_ids"])
        if filas is None:
            return {"ok": False, "error": "lectura_fallo"}
        completas = len(filas) == len(div["reserva_ids"])
        c = datos.cancha(div["cancha_id"]) or {}
        if completas and all(f.get("estado") == "confirmada" and f.get("medio_pago") == MEDIO_RESERVA for f in filas):
            # Ya confirmada (p. ej. un error cortó el paso anterior a mitad): se
            # completa el libro y la comisión si faltan (ambos idempotentes).
            if _wr()._cobro_web(_wr()._ref_de(filas)) is None:
                out = _cdw().confirmar_directo(filas, c, div["organizador_email"], plan=_wr().plan_cobro_reserva(filas),
                                               medio=MEDIO_RESERVA, cobro_id=f"{PREFIJO_COBRO}{div_id}",
                                               monto_centimos=int(div["total_centimos"]))
                if not out.get("ok"):
                    return {"ok": False, "error": out.get("error") or "confirmar_fallo"}
            _repo.transicion(div_id, ("completa",), "confirmada")
            return {"ok": True, "ya": True}
        if not completas or any(f.get("estado") != "nueva" for f in filas):
            # Lectura correcta y el apartado ya no está (o lo tomó otra reserva): se devuelve todo.
            print(f"[dividir] {div_id} completa pero sin apartado → devolución", flush=True)
            cerrar_y_devolver(div, "vencida", "apartado_perdido", desde=("completa",))
            return {"ok": False, "error": "apartado_perdido"}
        plan = _wr().plan_cobro_reserva(filas)
        if int(plan["base_cobro"]) * 100 != int(div["total_centimos"]):
            print(f"[dividir] {div_id} el total cambió ({plan['base_cobro']} vs {div['total_centimos']}): se confirma "
                  "con lo cobrado", flush=True)
        out = _cdw().confirmar_directo(filas, c, div["organizador_email"], plan=plan, medio=MEDIO_RESERVA,
                                       cobro_id=f"{PREFIJO_COBRO}{div_id}", monto_centimos=int(div["total_centimos"]))
        if not out.get("ok"):
            print(f"[dividir] {div_id} no se pudo confirmar ({out.get('error')}): queda completa, se reintenta", flush=True)
            return {"ok": False, "error": out.get("error") or "confirmar_fallo"}
        _repo.transicion(div_id, ("completa",), "confirmada")
    cuando = _cuando(div)
    vistos = set()
    for p in _repo.partes(div_id):
        e = p["pagador_email"].lower()
        if e and e not in vistos:
            vistos.add(e)
            _avisar(e, "¡Reserva confirmada! ✅", f"Todos pagaron su parte: {c.get('nombre', 'la cancha')} {cuando} quedó confirmada.")
    print(f"[dividir] {div_id} confirmada", flush=True)
    return {"ok": True}


# ── devolver ────────────────────────────────────────────────────────────────

def repartir_devolucion(montos: list[int], monto_dev: int) -> list[int]:
    """Reparte [monto_dev] proporcional a lo que pagó cada uno, en céntimos
    exactos (resto mayor) y SIN pasar nunca lo que pagó cada parte."""
    montos = [max(0, int(m)) for m in montos]
    total = sum(montos)
    monto_dev = max(0, min(int(monto_dev), total))
    if total <= 0 or monto_dev <= 0:
        return [0] * len(montos)
    cuotas = [m * monto_dev // total for m in montos]
    resto = monto_dev - sum(cuotas)
    for i in sorted(range(len(montos)), key=lambda i: (-(montos[i] * monto_dev % total), -montos[i], i)):
        if resto <= 0:
            break
        if cuotas[i] < montos[i]:
            cuotas[i] += 1
            resto -= 1
    return cuotas


def _devolver_simple(p: dict, monto: int, nota: str) -> str:
    """Partes que no se devuelven por la API de Culqi (o no tienen plata)."""
    from pagos import cobro_directo as cd
    if p["estado"] == "cobrando":
        _repo.set_parte(p["id"], ("cobrando",), dict(_LIBRE))
        return "libre"
    if p["estado"] == "en_revision":
        if p["pago_manual_id"]:
            cd.repo().resolver_pago_manual(p["pago_manual_id"], "vencido", "sistema", "division_" + nota)
        _repo.set_parte(p["id"], ("en_revision",), {"estado": "devolver", "devolver_centimos": p["monto_centimos"],
                                                     "nota": "sin_revisar"})
        return "devolver"
    if p["estado"] != "pagada" or monto <= 0:
        return p["estado"]
    _repo.set_parte(p["id"], ("pagada",), {"estado": "devolver", "devolver_centimos": int(monto), "nota": nota})
    return "devolver"


def _devolver_partes(div: dict, items: list[tuple[dict, int]], nota: str, llave: str) -> list[str]:
    """Devuelve cada (parte, monto) y da el estado final de cada una (mismo
    orden). Las partes pagadas con el MISMO cargo de Culqi ("Pagar lo que
    falta": `chr_X#0`, `chr_X#2`…) se devuelven en UNA sola llamada por la
    suma; la contabilidad sigue por parte."""
    fins: list[str] = [""] * len(items)
    grupos: dict[str, list[int]] = {}
    for i, (p, monto) in enumerate(items):
        cobro = str(p.get("cobro_id") or "")
        if p["estado"] == "pagada" and int(monto) > 0 and cobro.startswith("chr_") and llave:
            grupos.setdefault(_base_charge(cobro), []).append(i)
        else:
            fins[i] = _devolver_simple(p, int(monto), nota)
    for charge, idx in grupos.items():
        r = _reembolsar_cargo(div, charge, sum(int(items[i][1]) for i in idx), nota, llave)
        if not r.get("ok"):
            print(f"[dividir] reembolso de {charge} ({len(idx)} parte(s)) falló: {r.get('error')}", flush=True)
        for i in idx:
            p, monto = items[i]
            if r.get("ok"):
                _repo.set_parte(p["id"], ("pagada",), {"estado": "reembolsada", "refund_id": str(r.get("refund_id") or "")[:80],
                                                        "devolver_centimos": int(monto), "nota": nota, "resuelta_en": _ahora()})
                fins[i] = "reembolsada"
            else:
                _repo.set_parte(p["id"], ("pagada",), {"estado": "devolver", "devolver_centimos": int(monto),
                                                        "nota": f"{nota} · reembolso_fallo"})
                fins[i] = "devolver"
    return fins


def _devolver_parte(div: dict, p: dict, monto: int, nota: str, llave: str) -> str:
    """Devuelve [monto] de una parte. Devuelve el estado final de la parte."""
    return _devolver_partes(div, [(p, int(monto))], nota, llave)[0]


def _devolver_pendientes(div: dict, motivo: str, cerrando: bool) -> dict:
    """Suelta el horario y devuelve las partes de una división CERRADA que aún
    tienen plata (o una toma / un voucher vivos). Re-ejecutable: cada parte se
    mueve con `set_parte(desde=…)` y cada cargo se devuelve una sola vez, así
    el barrido retoma un cierre que se cortó a mitad."""
    from pagos import cobro_directo as cd
    from web import datos
    cuando = _cuando(div)
    cancelada = div.get("motivo") == "reserva_cancelada" or motivo == "reserva_cancelada"
    if not cancelada:   # una reserva confirmada cancelada ya soltó sus filas (`_cancelar_reserva`)
        _wr().soltar_bloque(list(div["reserva_ids"]))
    llave = cd.llave_secreta(div["dueno"])
    partes = [p for p in _repo.partes(div["id"]) if _pendiente_de_devolver(div, p)]
    items = [(p, int(p["devolver_centimos"]) if cancelada and p["estado"] == "pagada" else int(p["monto_centimos"]))
             for p in partes]
    fins = _devolver_partes(div, items, motivo, llave)
    res = {"reembolsada": fins.count("reembolsada"), "devolver": fins.count("devolver")}
    pagadores: dict[str, list[str]] = {}
    for p, fin in zip(partes, fins):
        if fin in res:
            pagadores.setdefault(p["pagador_email"].lower(), []).append(fin)
    c = datos.cancha(div["cancha_id"]) or {}
    lugar = f"{c.get('nombre', 'la cancha')} {cuando}".strip()
    for e, fs in pagadores.items():
        txt = ("Te devolvimos tu parte al mismo medio de pago (3 a 7 días hábiles)." if all(f == "reembolsada" for f in fs)
               else "El club te devolverá lo que pagaste; te avisamos.")
        if cancelada:
            msg = f"{lugar}: se canceló la reserva dividida. {txt}"
        elif motivo == "vencida":
            msg = f"{lugar}: no se juntaron todas las partes a tiempo y el horario se liberó. {txt}"
        else:
            msg = f"{lugar}: el pago dividido se canceló y el horario se liberó. {txt}"
        _avisar(e, "El pago dividido no se completó" if not cancelada else "Reserva cancelada", msg)
    if cerrando and div["organizador_email"].lower() not in pagadores:
        _avisar(div["organizador_email"], "El pago dividido no se completó",
                f"{lugar}: el horario se liberó porque no se pagaron todas las partes.")
    if res["devolver"]:
        _avisar(div["dueno"], "Devuelve pagos 💸",
                f"Una reserva dividida de {lugar} no se completó: devuelve {res['devolver']} pago(s) recibido(s) y márcalos "
                "en Pagos por confirmar → Devoluciones.")
    print(f"[dividir] {div['id']} {div.get('estado')} ({motivo}) reembolsadas={res['reembolsada']} "
          f"a_devolver={res['devolver']}{'' if cerrando else ' (reanudado)'}", flush=True)
    return {"ok": True, **res}


def cerrar_y_devolver(div: dict, estado: str, motivo: str, desde=("abierta",)) -> dict:
    """Vence / se cancela sin completarse: suelta el horario y devuelve cada parte.
    Si algo falla a mitad, el barrido retoma lo que quedó (`cerradas_pendientes`)."""
    if not _repo.transicion(div["id"], desde, estado, motivo):
        return {"ok": False, "error": "cerrada"}
    return _devolver_pendientes({**div, "estado": estado, "motivo": motivo}, motivo, cerrando=True)


def cancelar(div: dict, email: str) -> dict:
    """El organizador suelta la reserva antes de completarla."""
    if div["organizador_email"].lower() != email:
        return {"ok": False, "error": "solo_organizador"}
    r = cerrar_y_devolver(div, "cancelada", "cancelada")
    return r if r.get("ok") else {**r, "mensaje": mensaje("cerrada")}


def devolver_por_cancelacion(div_id: str, monto_dev_centimos: int) -> tuple[str, str]:
    """La reserva YA confirmada se cancela (`web.router._cancelar_reserva`): lo
    que corresponde devolver se reparte proporcional a lo que pagó cada uno y
    vuelve a cada pagador por SU medio. Devuelve (reembolso, detalle):
    'reembolsado' si todo salió por la API del club, 'manual' si el club debe
    devolver alguna parte, 'sin_reembolso' si no corresponde nada."""
    from pagos import cobro_directo as cd
    div = _repo.por_id(div_id)
    if not div or not _repo.transicion(div_id, ("confirmada", "completa"), "cancelada", "reserva_cancelada"):
        return "manual", "division_no_encontrada"
    partes = [p for p in _repo.partes(div_id) if p["estado"] == "pagada"]
    total = sum(p["monto_centimos"] for p in partes)
    monto_dev = max(0, min(int(monto_dev_centimos), total))
    if monto_dev <= 0 or not partes:
        return "sin_reembolso", ""
    cuotas = repartir_devolucion([p["monto_centimos"] for p in partes], monto_dev)
    # Primero se ANOTA cuánto toca a cada parte: si algo falla a mitad, el
    # barrido retoma con esos montos (nunca devuelve de más ni de menos).
    for p, q in zip(partes, cuotas):
        if q > 0:
            _repo.set_parte(p["id"], ("pagada",), {"devolver_centimos": int(q)})
    llave = cd.llave_secreta(div["dueno"])
    items = [(p, q) for p, q in zip(partes, cuotas) if q > 0]
    fins = _devolver_partes(div, items, "reserva_cancelada", llave)
    vistos = set()
    for (p, q), fin in zip(items, fins):
        e = p["pagador_email"].lower()
        if e and e != div["organizador_email"].lower() and e not in vistos:
            vistos.add(e)
            _avisar(e, "Reserva cancelada",
                    f"{div['organizador_nombre'] or 'El organizador'} canceló la reserva dividida. "
                    + ("Te devolvimos tu parte al mismo medio de pago." if fin == "reembolsada" else "El club te devolverá tu parte; te avisamos."))
    if "devolver" in fins:
        _avisar(div["dueno"], "Devuelve pagos 💸",
                f"Se canceló una reserva dividida: devuelve {fins.count('devolver')} pago(s) y márcalos en Pagos por confirmar → Devoluciones.")
        return "manual", f"division:{div_id}"
    return "reembolsado", f"division:{div_id}"


def resolver_devolucion(parte_id: str, dueno: str, accion: str) -> dict:
    """El club marca una parte (o un pago tardío) como devuelta, o "no recibí
    ese pago" si el comprobante nunca se revisó."""
    if accion not in ("devuelta", "no_recibido"):
        return {"ok": False, "error": "accion"}
    p = next((x for x in _repo.devoluciones_de(dueno) if x["id"] == parte_id), None)
    if not p:
        return {"ok": False, "error": "no_encontrado"}
    if accion == "no_recibido" and p["nota"] != "sin_revisar":
        return {"ok": False, "error": "accion"}
    if p.get("tardio"):
        hecho = _repo.set_tardio(parte_id, ("devolver",), {"estado": accion, "resuelta_en": _ahora()})
    else:
        hecho = _repo.set_parte(parte_id, ("devolver",), {"estado": accion, "resuelta_en": _ahora()})
    if not hecho:
        return {"ok": False, "error": "ya_resuelto"}
    if accion == "devuelta":
        _avisar(p["pagador_email"], "Te devolvieron tu parte 💸",
                f"El club marcó como devuelto tu pago de {_plata(p['devolver_centimos'], p['division']['moneda'])}.")
    return {"ok": True}


def devoluciones_pendientes(dueno: str) -> list[dict]:
    if not dueno or not disponible():
        return []
    try:
        return _repo.devoluciones_de(dueno)
    except Exception:  # noqa: BLE001
        return []


def de_email(email: str) -> list[dict]:
    if not email or not disponible():
        return []
    try:
        return _repo.de_email(email)
    except Exception:  # noqa: BLE001
        return []


# ── barrido (cron de 1 min de main.py) ───────────────────────────────────────

REANUDAR_TRAS_MIN = 1   # un cierre a medio camino se retoma pasado este tiempo


def barrer(ahora: datetime | None = None) -> dict:
    """Avisa al organizador antes de vencer, suelta partes tomadas sin pagar,
    vence lo que no se completó (devolviendo), retoma devoluciones que se
    cortaron a mitad y reintenta confirmar. Un error en una división no frena
    a las demás."""
    if not disponible():
        return {}
    ahora = ahora or _ahora()
    out = {"avisos": 0, "soltadas": 0, "vencidas": 0, "confirmadas": 0, "reanudadas": 0, "errores": 0}

    def _seguro(fn, div_id):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            out["errores"] += 1
            print(f"[dividir] barrido {div_id}: {type(e).__name__} {str(e)[:160]}", flush=True)
            return None

    for p in _repo.tomas_viejas(ahora - timedelta(minutes=TOMA_MAX_MIN)):
        if _seguro(lambda p=p: _repo.set_parte(p["id"], ("cobrando",), dict(_LIBRE)), p["id"]):
            out["soltadas"] += 1
    for div in _repo.en_estado(("abierta",)):
        if div["vence_en"] <= ahora:
            if (_seguro(lambda div=div: cerrar_y_devolver(div, "vencida", "vencida"), div["id"]) or {}).get("ok"):
                out["vencidas"] += 1
        elif div.get("aviso_en") is None and ahora >= aviso_desde(div):
            if _seguro(lambda div=div: _avisar_faltan(div, ahora), div["id"]):
                out["avisos"] += 1
    for div in _repo.cerradas_pendientes(ahora - timedelta(minutes=REANUDAR_TRAS_MIN)):
        if (_seguro(lambda div=div: _devolver_pendientes(div, div.get("motivo") or div["estado"], cerrando=False),
                    div["id"]) or {}).get("ok"):
            out["reanudadas"] += 1
    for div in _repo.en_estado(("completa",)):
        if (_seguro(lambda div=div: confirmar(div["id"]), div["id"]) or {}).get("ok"):
            out["confirmadas"] += 1
    return out


def _avisar_faltan(div: dict, ahora: datetime) -> bool:
    if not _repo.marcar_aviso(div["id"]):
        return False
    faltan = [p for p in _repo.partes(div["id"]) if p["estado"] != "pagada"]
    if not faltan:
        return False
    mins = max(1, int((div["vence_en"] - ahora).total_seconds() // 60))
    _avisar(div["organizador_email"], "Faltan partes por pagar ⏳",
            f"Faltan {len(faltan)} de {div['partes']} partes y quedan {mins} min. Entra a tu enlace y toca "
            f"\"Pagar lo que falta\" ({_plata(sum(p['monto_centimos'] for p in faltan), div['moneda'])}) o el horario se libera.")
    return True
