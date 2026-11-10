"""COBRO DIRECTO AL CLUB (plan nocturno A4 + A5 + A6, oct-2026).

Decisión del usuario (26-oct-2026): el dinero de las reservas va DIRECTO al
club, y la plataforma vive SOLO de la comisión por reserva. Cada club (su
dueño, identificado por su correo verificado) configura:

- **Su cuenta Culqi** (A4): llave pública + secreta. La secreta se guarda
  CIFRADA (Fernet, `PAGOS_ENC_KEY`; sin clave no se guarda nada) en
  `cl_pasarela_club` y JAMÁS vuelve a un cliente (solo `sk_…••••1234`). El
  cargo se hace con la llave del club, así la plata cae en SU cuenta.
- **Sus medios manuales** (A5): Yape/Plin/transferencia (Perú) o QR /
  transferencia / billetera (Ecuador, Bolivia). El jugador ve esos datos en
  el checkout, paga y sube el VOUCHER; la reserva queda apartada `en_revision`
  hasta que el club confirma o rechaza, o vence sola (`VOUCHER_PLAZO_MIN`).
  Anti-fraude: mismo nº de operación o misma imagen no pagan dos reservas del
  club (índices únicos en `cl_pagos_manuales`). La imagen es dato personal:
  se guarda comprimida en la base, nunca en un bucket público.
- **La comisión** (A6): como la plata no pasa por la plataforma, se cobra del
  SALDO prepago del dueño (primero el saldo de regalo); lo que no alcanza queda
  como DEUDA (`PagoRegistro.tipo == "comision_deuda"`) que se salda sola en su
  siguiente recarga. Con deuda sobre el tope de su moneda
  (`comision_deuda_tope_<ISO>`) el club queda SUSPENDIDO para cobros directos
  (online y voucher) hasta regularizar; el pago en la cancha sigue.

Persistencia: tablas Postgres (migración 0003) vía `RepoPG`; los tests
inyectan `RepoMemoria` (`usar_repo`). Saldos y libro de comisiones siguen en
`stores` (mismo lugar que el resto de la billetera).
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import config

TIPOS_MEDIO = ("yape", "plin", "transferencia", "billetera", "qr")
MEDIOS_POR_PAIS = {"PE": ("yape", "plin", "transferencia"),
                   "EC": ("qr", "transferencia", "billetera"),
                   "BO": ("qr", "transferencia", "billetera")}
ETIQUETA_MEDIO = {"yape": "Yape", "plin": "Plin", "transferencia": "Transferencia bancaria",
                  "billetera": "Billetera digital", "qr": "QR"}
MAX_MEDIOS = 6
VOUCHER_MAX_BYTES = 6 * 1024 * 1024
VOUCHER_LADO_MAX = 1600
TOPE_DEUDA_DEFECTO = {"PEN": 50.0, "USD": 15.0, "BOB": 100.0}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ── cifrado de la llave secreta ──────────────────────────────────────────────

def _fernet():
    if not config.PAGOS_ENC_KEY:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(config.PAGOS_ENC_KEY.encode())
    except Exception:  # noqa: BLE001 — clave mal formada = sin cifrado = no se guarda
        return None


def cifrado_disponible() -> bool:
    return _fernet() is not None


def _cifrar(texto: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("cifrado_no_configurado")
    return f.encrypt(texto.encode()).decode()


def _descifrar(enc: str) -> str:
    f = _fernet()
    if f is None or not enc:
        return ""
    try:
        return f.decrypt(enc.encode()).decode()
    except Exception:  # noqa: BLE001
        return ""


# ── repositorios ─────────────────────────────────────────────────────────────

class RepoMemoria:
    """Mismo contrato que `RepoPG`, en memoria (tests)."""

    def __init__(self):
        self.pasarelas: dict[str, dict] = {}
        self.medios: dict[str, list[dict]] = {}
        self.pagos: dict[str, dict] = {}
        self._lock = threading.Lock()

    def disponible(self) -> bool:
        return True

    def pasarela_de(self, dueno):
        p = self.pasarelas.get(dueno)
        return dict(p) if p else None

    def pasarela_por_ref(self, ref):
        return next((dict(p) for p in self.pasarelas.values() if p["webhook_ref"] == ref), None)

    def guardar_pasarela(self, p):
        self.pasarelas[p["dueno"]] = dict(p)
        return True

    def borrar_pasarela(self, dueno):
        return self.pasarelas.pop(dueno, None) is not None

    def medios_de(self, dueno):
        return [dict(m) for m in self.medios.get(dueno, []) if m.get("activo", True)]

    def reemplazar_medios(self, dueno, medios):
        self.medios[dueno] = [dict(m, id=i + 1, activo=True) for i, m in enumerate(medios)]
        return True

    def crear_pago_manual(self, p):
        with self._lock:
            vivos = [x for x in self.pagos.values() if x["estado"] in ("en_revision", "aprobado")]
            if any(x["reserva_ref"] == p["reserva_ref"] for x in vivos):
                return "ya_existe"
            if p["operacion"] and any(x["dueno"] == p["dueno"] and x["medio"] == p["medio"]
                                      and x["operacion"] == p["operacion"] for x in vivos):
                return "operacion_repetida"
            if p["voucher_hash"] and any(x["dueno"] == p["dueno"] and x["voucher_hash"] == p["voucher_hash"]
                                         for x in vivos):
                return "voucher_repetido"
            self.pagos[p["id"]] = dict(p)
            return ""

    def pago_manual(self, pid):
        p = self.pagos.get(pid)
        return {k: v for k, v in p.items() if k != "voucher_img"} if p else None

    def pago_manual_de_ref(self, ref):
        return next(({k: v for k, v in p.items() if k != "voucher_img"} for p in self.pagos.values()
                     if p["reserva_ref"] == ref and p["estado"] in ("en_revision", "aprobado")), None)

    def pagos_manuales_de_jugador(self, email, limite=50):
        return sorted(({k: v for k, v in p.items() if k != "voucher_img"} for p in self.pagos.values()
                       if p["jugador_email"] == email), key=lambda p: p["creado_en"], reverse=True)[:limite]

    def pagos_manuales_de(self, dueno, estados):
        return sorted(({k: v for k, v in p.items() if k != "voucher_img"} for p in self.pagos.values()
                       if p["dueno"] == dueno and p["estado"] in estados),
                      key=lambda p: p["creado_en"], reverse=True)

    def imagen_voucher(self, pid):
        p = self.pagos.get(pid)
        return (p.get("voucher_img"), p.get("voucher_mime")) if p else (None, "")

    def resolver_pago_manual(self, pid, estado, por, motivo=""):
        with self._lock:
            p = self.pagos.get(pid)
            if not p or p["estado"] != "en_revision":
                return False
            p.update(estado=estado, resuelto_por=por, motivo_rechazo=motivo, resuelto_en=_ahora())
            return True

    def reabrir_pago_manual(self, pid):
        """Deshace una aprobación cuyo apartado no se pudo confirmar (error de
        la base): el voucher vuelve a la bandeja para aprobarlo de nuevo."""
        with self._lock:
            p = self.pagos.get(pid)
            if not p or p["estado"] != "aprobado":
                return False
            p.update(estado="en_revision", resuelto_por="", motivo_rechazo="", resuelto_en=None)
            return True

    def vencidos(self, ahora):
        return [{k: v for k, v in p.items() if k != "voucher_img"} for p in self.pagos.values()
                if p["estado"] == "en_revision" and p["vence_en"] <= ahora]


class RepoPG:
    """Tablas de la migración 0003 (rol del backend; la anon key no las ve)."""

    _COLS_PM = ["id", "reserva_ref", "reserva_ids", "cancha_id", "dueno", "jugador_email", "jugador_nombre",
                "monto_centimos", "moneda", "medio", "operacion", "voucher_mime", "voucher_hash", "estado",
                "motivo_rechazo", "vence_en", "creado_en", "resuelto_en", "resuelto_por"]
    _COLS_PAS = ["dueno", "proveedor", "public_key", "secret_key_cifrada", "secret_key_ult4", "modo",
                 "webhook_ref", "activo", "verificada", "actualizado_en"]
    _COLS_MED = ["id", "tipo", "titular", "numero", "banco", "cuenta", "cci", "qr_url", "nota", "activo", "orden"]

    def disponible(self) -> bool:
        from db import pg
        return pg.habilitado

    def _uno(self, sql, args, cols):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            f = cur.fetchone()
            return dict(zip(cols, f)) if f else None

    def _varios(self, sql, args, cols):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            return [dict(zip(cols, f)) for f in cur.fetchall()]

    def _exec(self, sql, args) -> int:
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(sql, args)
            n = cur.rowcount
            conn.commit()
            return n

    def pasarela_de(self, dueno):
        from db import pg
        if pg.memo_request() is None:
            return self._pasarela_de(dueno)
        self._precargar_club(dueno)
        return pg.memo_leer(("cl_pasarela", dueno), lambda: self._pasarela_de(dueno))

    def _pasarela_de(self, dueno):
        return self._uno(f"select {', '.join(self._COLS_PAS)} from cl_pasarela_club where dueno = %s",
                         (dueno,), self._COLS_PAS)

    def _precargar_club(self, dueno) -> None:
        """La ficha y el panel piden la pasarela Y los medios del club, uno
        tras otro: en una request GET se leen juntos (un viaje) y quedan en la
        memoria de la request. Si falla, cada uno se lee como siempre."""
        from db import pg
        if pg.memo_tiene(("cl_pasarela", dueno)) or pg.memo_tiene(("cl_medios", dueno)):
            return
        np_, nm = len(self._COLS_PAS), len(self._COLS_MED)
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(
                    "select p.hay, " + ", ".join(f"p.{c}" for c in self._COLS_PAS) + ", m.hay, "
                    + ", ".join(f"m.{c}" for c in self._COLS_MED) + " from (select 1) uno "
                    f"left join lateral (select {', '.join(self._COLS_PAS)}, true as hay from cl_pasarela_club "
                    "where dueno = %s) p on true "
                    f"left join lateral (select {', '.join(self._COLS_MED)}, true as hay from cl_medios_pago_club "
                    "where dueno = %s and activo order by orden, id) m on true "
                    "order by m.orden, m.id", (dueno, dueno))
                filas = cur.fetchall()
        except Exception:  # noqa: BLE001
            return
        if not filas:
            return
        f0 = filas[0]
        pg.memo_guardar(("cl_pasarela", dueno), dict(zip(self._COLS_PAS, f0[1:1 + np_])) if f0[0] else None)
        im = 1 + np_
        pg.memo_guardar(("cl_medios", dueno),
                        [dict(zip(self._COLS_MED, f[im + 1:im + 1 + nm])) for f in filas if f[im]])

    def pasarela_por_ref(self, ref):
        return self._uno(f"select {', '.join(self._COLS_PAS)} from cl_pasarela_club where webhook_ref = %s",
                         (ref,), self._COLS_PAS)

    def guardar_pasarela(self, p):
        cols = [c for c in self._COLS_PAS if c != "actualizado_en"]
        upd = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("dueno", "webhook_ref"))
        self._exec(f"insert into cl_pasarela_club ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                   f"on conflict (dueno) do update set {upd}, actualizado_en = now()",
                   [p[c] for c in cols])
        return True

    def borrar_pasarela(self, dueno):
        return self._exec("delete from cl_pasarela_club where dueno = %s", (dueno,)) > 0

    def medios_de(self, dueno):
        from db import pg
        if pg.memo_request() is None:
            return self._medios_de(dueno)
        self._precargar_club(dueno)
        return pg.memo_leer(("cl_medios", dueno), lambda: self._medios_de(dueno))

    def _medios_de(self, dueno):
        return self._varios(f"select {', '.join(self._COLS_MED)} from cl_medios_pago_club "
                            "where dueno = %s and activo order by orden, id", (dueno,), self._COLS_MED)

    def reemplazar_medios(self, dueno, medios):
        from db import pg
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute("update cl_medios_pago_club set activo = false, actualizado_en = now() "
                        "where dueno = %s and activo", (dueno,))
            for i, m in enumerate(medios):
                cur.execute("insert into cl_medios_pago_club (dueno, tipo, titular, numero, banco, cuenta, cci, "
                            "qr_url, nota, orden) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (dueno, m["tipo"], m["titular"], m["numero"], m["banco"], m["cuenta"], m["cci"],
                             m["qr_url"], m["nota"], i))
            conn.commit()
        return True

    def crear_pago_manual(self, p):
        from db import pg
        cols = self._COLS_PM[:-3] + ["voucher_img"]
        cols = [c for c in cols if c != "creado_en"]
        vals = [json.dumps(p[c]) if c == "reserva_ids" else p.get(c) for c in cols]
        try:
            with pg.conexion() as conn, conn.cursor() as cur:
                cur.execute(f"insert into cl_pagos_manuales ({', '.join(cols)}) values "
                            f"({', '.join(['%s'] * len(cols))})", vals)
                conn.commit()
            return ""
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "uq_cl_pm_operacion" in msg:
                return "operacion_repetida"
            if "uq_cl_pm_voucher" in msg:
                return "voucher_repetido"
            if "uq_cl_pm_reserva_viva" in msg:
                return "ya_existe"
            print("cobro_directo.crear_pago_manual error:", msg[:200])
            return "error"

    def _pm(self, where, args):
        filas = self._varios(f"select {', '.join(self._COLS_PM)} from cl_pagos_manuales where {where}",
                             args, self._COLS_PM)
        for f in filas:
            if isinstance(f.get("reserva_ids"), str):
                f["reserva_ids"] = json.loads(f["reserva_ids"] or "[]")
        return filas

    def pago_manual(self, pid):
        f = self._pm("id = %s", (pid,))
        return f[0] if f else None

    def pago_manual_de_ref(self, ref):
        f = self._pm("reserva_ref = %s and estado in ('en_revision', 'aprobado')", (ref,))
        return f[0] if f else None

    def pagos_manuales_de_jugador(self, email, limite=50):
        return self._pm("jugador_email = %s order by creado_en desc limit %s", (email, int(limite)))

    def pagos_manuales_de(self, dueno, estados):
        return self._pm("dueno = %s and estado = any(%s) order by creado_en desc limit 200", (dueno, list(estados)))

    def imagen_voucher(self, pid):
        f = self._uno("select voucher_img, voucher_mime from cl_pagos_manuales where id = %s", (pid,),
                      ["voucher_img", "voucher_mime"])
        return (bytes(f["voucher_img"]) if f and f["voucher_img"] is not None else None, (f or {}).get("voucher_mime", ""))

    def resolver_pago_manual(self, pid, estado, por, motivo=""):
        return self._exec("update cl_pagos_manuales set estado = %s, resuelto_por = %s, motivo_rechazo = %s, "
                          "resuelto_en = now() where id = %s and estado = 'en_revision'",
                          (estado, por, motivo, pid)) == 1

    def reabrir_pago_manual(self, pid):
        return self._exec("update cl_pagos_manuales set estado = 'en_revision', resuelto_por = '', motivo_rechazo = '', "
                          "resuelto_en = null where id = %s and estado = 'aprobado'", (pid,)) == 1

    def vencidos(self, ahora):
        return self._pm("estado = 'en_revision' and vence_en <= %s", (ahora,))


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


# ── cuenta Culqi del club (A4) ───────────────────────────────────────────────

_PK = re.compile(r"^pk_(test|live)_[A-Za-z0-9]{8,}$")
_SK = re.compile(r"^sk_(test|live)_[A-Za-z0-9]{8,}$")


def guardar_culqi(dueno: str, public_key: str, secret_key: str) -> dict:
    """Valida, comprueba con Culqi y guarda CIFRADA la cuenta del club."""
    pk, sk = (public_key or "").strip(), (secret_key or "").strip()
    mp, ms = _PK.match(pk), _SK.match(sk)
    if not mp or not ms:
        return {"ok": False, "error": "llaves_invalidas"}
    if mp.group(1) != ms.group(1):
        return {"ok": False, "error": "llaves_de_distinto_modo"}
    if not cifrado_disponible():
        return {"ok": False, "error": "cifrado_no_configurado"}
    if not disponible():
        return {"ok": False, "error": "base_no_disponible"}
    from pagos import culqi
    ver = culqi.verificar_llave(sk)
    if ver.get("valida") is False:
        return {"ok": False, "error": "llave_rechazada_por_culqi"}
    previo = _repo.pasarela_de(dueno)
    _repo.guardar_pasarela({
        "dueno": dueno, "proveedor": "culqi", "public_key": pk, "secret_key_cifrada": _cifrar(sk),
        "secret_key_ult4": sk[-4:], "modo": ms.group(1),
        "webhook_ref": (previo or {}).get("webhook_ref") or "wh_" + secrets.token_urlsafe(18),
        "activo": True, "verificada": ver.get("valida") is True,
    })
    return {"ok": True, **resumen_pasarela(dueno)}


def resumen_pasarela(dueno: str, base_url: str = "") -> dict:
    """Lo que el DUEÑO ve de su cuenta (sin la secreta)."""
    p = _repo.pasarela_de(dueno) if disponible() else None
    if not p:
        return {"configurada": False}
    base = (base_url or config.PUBLIC_BASE_URL or "").rstrip("/")
    url = f"{base}/pagos/culqi/webhook/club/{p['webhook_ref']}"
    return {"configurada": True, "activa": bool(p["activo"]), "modo": p["modo"],
            "public_key": p["public_key"], "secret_key": f"sk_{p['modo']}_••••{p['secret_key_ult4']}",
            "verificada": bool(p["verificada"]), "webhook_url": url}


def borrar_culqi(dueno: str) -> bool:
    return disponible() and _repo.borrar_pasarela(dueno)


def llave_secreta(dueno: str) -> str:
    """sk del club en claro (SOLO para llamar a Culqi). '' si no tiene."""
    if not dueno or not disponible():
        return ""
    p = _repo.pasarela_de(dueno)
    if not p or not p["activo"]:
        return ""
    return _descifrar(p["secret_key_cifrada"])


def llave_publica(dueno: str) -> str:
    if not dueno or not disponible():
        return ""
    p = _repo.pasarela_de(dueno)
    return p["public_key"] if p and p["activo"] and _descifrar(p["secret_key_cifrada"]) else ""


# ── medios manuales del club (A5) ────────────────────────────────────────────

def _txt(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _digitos(v, n: int) -> str:
    return re.sub(r"\D", "", str(v or ""))[:n]


def normalizar_medios(medios: list, pais: str) -> tuple[list[dict], str]:
    """(medios válidos, error). Cada país admite sus tipos (`MEDIOS_POR_PAIS`)."""
    permitidos = MEDIOS_POR_PAIS.get((pais or "PE").upper(), MEDIOS_POR_PAIS["PE"])
    out: list[dict] = []
    for m in (medios or [])[:MAX_MEDIOS]:
        if not isinstance(m, dict):
            continue
        tipo = str(m.get("tipo") or "").strip().lower()
        if tipo not in permitidos:
            return [], f"medio_no_permitido:{tipo}"
        d = {"tipo": tipo, "titular": _txt(m.get("titular"), 80), "numero": _digitos(m.get("numero"), 15),
             "banco": _txt(m.get("banco"), 60), "cuenta": _txt(m.get("cuenta"), 30),
             "cci": _digitos(m.get("cci"), 20), "qr_url": _txt(m.get("qr_url"), 400), "nota": _txt(m.get("nota"), 140)}
        if len(d["titular"]) < 3:
            return [], "titular_requerido"
        if tipo in ("yape", "plin") and not re.fullmatch(r"9\d{8}", d["numero"]):
            return [], "celular_invalido"
        if tipo == "transferencia" and not (d["banco"] and (d["cuenta"] or d["cci"])):
            return [], "cuenta_requerida"
        if tipo == "transferencia" and d["cci"] and pais == "PE" and len(d["cci"]) != 20:
            return [], "cci_invalido"
        if tipo in ("qr", "billetera") and not (d["qr_url"].startswith("https://") or d["numero"]):
            return [], "qr_o_numero_requerido"
        out.append(d)
    return out, ""


def guardar_medios(dueno: str, medios: list, pais: str) -> dict:
    if not disponible():
        return {"ok": False, "error": "base_no_disponible"}
    norm, err = normalizar_medios(medios, pais)
    if err:
        return {"ok": False, "error": err}
    _repo.reemplazar_medios(dueno, norm)
    return {"ok": True, "medios": medios_publicos(dueno)}


def medios_publicos(dueno: str) -> list[dict]:
    if not dueno or not disponible():
        return []
    out = []
    for m in _repo.medios_de(dueno):
        out.append({k: m.get(k, "") for k in ("tipo", "titular", "numero", "banco", "cuenta", "cci", "qr_url", "nota")}
                   | {"etiqueta": ETIQUETA_MEDIO.get(m["tipo"], m["tipo"])})
    return out


# ── comisión con dinero directo al club (A6) ─────────────────────────────────

def _tope_deuda_centimos(iso: str) -> int:
    from db.store import stores
    try:
        v = float(stores.config.get(f"comision_deuda_tope_{iso}", TOPE_DEUDA_DEFECTO.get(iso, 50.0)))
    except (TypeError, ValueError):
        v = TOPE_DEUDA_DEFECTO.get(iso, 50.0)
    return int(round(max(v, 0) * 100))


def deuda_centimos(dueno: str, iso: str = "") -> int:
    from db.store import stores
    return sum(p.monto_centimos for p in stores.pagos
               if p.tipo == "comision_deuda" and p.estado == "pendiente" and p.dueno_id == dueno
               and (not iso or (p.moneda or "PEN") == iso))


def suspendido(dueno: str, iso: str) -> bool:
    """Deuda de comisión SOBRE el tope → sin cobros directos hasta pagar."""
    tope = _tope_deuda_centimos(iso)
    return tope > 0 and deuda_centimos(dueno, iso) > tope


def _saldo_en_moneda(dueno: str, iso: str) -> bool:
    try:
        from pagos.router import moneda_billetera
        return moneda_billetera(dueno) == iso
    except Exception:  # noqa: BLE001
        return iso == "PEN"


def cobrar_comision(dueno: str, ref: str, base_centimos: int, iso: str, origen: str, concepto: str = "") -> dict:
    """Comisión de una reserva cobrada DIRECTO por el club. Idempotente por
    `ref`. Sale del saldo (regalo primero) en la moneda de la billetera; lo que
    no alcanza queda como deuda pendiente."""
    from db.store import stores
    from pagos.router import comision_centimos
    clave = f"cd:{ref}"
    if any(p.culqi_charge_id in (clave, f"deuda:{ref}") for p in stores.pagos
           if p.tipo in ("comision_reserva", "comision_deuda")):
        return {"ok": True, "duplicada": True}
    total = comision_centimos(base_centimos / 100.0, iso) if base_centimos > 0 else 0
    if total <= 0 or not dueno:
        return {"ok": True, "comision_centimos": 0, "deuda_centimos": 0}
    cobrado = 0
    promo = 0
    if _saldo_en_moneda(dueno, iso):
        disponible_c = stores.saldo_centimos(dueno) + stores.saldo_promo_centimos(dueno)
        cobrado = min(total, disponible_c)
        if cobrado > 0:
            promo, _nuevo = stores.debitar_comision(dueno, cobrado)
            stores.registrar_pago(tipo="comision_reserva", monto_centimos=cobrado, moneda=iso, estado="aprobado",
                                  dueno_id=dueno, culqi_charge_id=clave, medio=origen,
                                  concepto=(concepto or "Comisión de reserva") + " · cobro directo")
    deuda = total - cobrado
    if deuda > 0:
        stores.registrar_pago(tipo="comision_deuda", monto_centimos=deuda, moneda=iso, estado="pendiente",
                              dueno_id=dueno, culqi_charge_id=f"deuda:{ref}", medio=origen,
                              concepto=(concepto or "Comisión de reserva") + " · por pagar")
    return {"ok": True, "comision_centimos": total, "cobrado_centimos": cobrado, "promo_centimos": promo,
            "deuda_centimos": deuda, "suspendido": suspendido(dueno, iso)}


def saldar_deudas(dueno: str) -> int:
    """Tras una RECARGA: paga las deudas de comisión (las más viejas primero)
    que alcancen con el saldo. Devuelve cuántos céntimos se saldaron."""
    from db.store import stores
    pagado = 0
    for p in sorted((p for p in stores.pagos if p.tipo == "comision_deuda" and p.estado == "pendiente"
                     and p.dueno_id == dueno), key=lambda p: p.id):
        if not _saldo_en_moneda(dueno, p.moneda or "PEN"):
            continue
        if stores.saldo_centimos(dueno) + stores.saldo_promo_centimos(dueno) < p.monto_centimos:
            break
        stores.debitar_comision(dueno, p.monto_centimos)
        p.estado = "saldada"
        stores.registrar_pago(tipo="comision_reserva", monto_centimos=p.monto_centimos, moneda=p.moneda,
                              estado="aprobado", dueno_id=dueno, culqi_charge_id=f"saldo:{p.culqi_charge_id}",
                              medio=p.medio, concepto=(p.concepto or "").replace("por pagar", "saldada"))
        pagado += p.monto_centimos
    return pagado


def revertir_comision(ref: str) -> int:
    """Reserva directa cancelada con devolución total: la comisión vuelve al
    saldo del dueño y la deuda pendiente se anula. Devuelve céntimos devueltos."""
    from db.store import stores
    devuelto = 0
    for p in stores.pagos:
        if p.culqi_charge_id == f"deuda:{ref}" and p.estado == "pendiente":
            p.estado = "anulada"
        elif p.culqi_charge_id == f"cd:{ref}" and p.tipo == "comision_reserva" and p.estado == "aprobado":
            p.estado = "revertida"
            stores.acreditar(p.dueno_id, p.monto_centimos)
            devuelto += p.monto_centimos
    return devuelto


# ── qué puede usar el jugador en el checkout ────────────────────────────────

def checkout(c: dict, iso: str) -> dict:
    """Medios de cobro DIRECTO del club de esta cancha (vacío = flujo de
    siempre: cuenta de la plataforma o pago en la cancha)."""
    dueno = (c.get("dueno") or "").strip().lower()
    if not dueno or not disponible():
        return {"directo": False}
    pk = llave_publica(dueno) if iso == "PEN" else ""   # Culqi cobra solo en soles
    medios = medios_publicos(dueno)
    if not pk and not medios:
        return {"directo": False}
    if suspendido(dueno, iso):
        return {"directo": False, "suspendido": True}
    return {"directo": True, "culqi_public_key": pk, "medios": medios,
            "voucher_plazo_min": config.VOUCHER_PLAZO_MIN}


# ── vouchers (A5) ────────────────────────────────────────────────────────────

def _normalizar_imagen(datos: bytes) -> tuple[bytes, str, str]:
    """(jpeg comprimido, mime, sha256 del ORIGINAL). Lanza ValueError si no es imagen."""
    if not datos or len(datos) > VOUCHER_MAX_BYTES:
        raise ValueError("imagen_invalida")
    huella = hashlib.sha256(datos).hexdigest()
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(datos))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((VOUCHER_LADO_MAX, VOUCHER_LADO_MAX))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80, optimize=True)
        return out.getvalue(), "image/jpeg", huella
    except Exception as e:  # noqa: BLE001
        raise ValueError("imagen_invalida") from e


def pagos_del_jugador(email: str, limite: int = 50) -> list[dict]:
    """Comprobantes que subió el jugador (todos los estados, el más nuevo
    primero), sin la imagen. Para "Mis reservas" y el comprobante web."""
    email = (email or "").strip().lower()
    if not email or not disponible():
        return []
    try:
        return _repo.pagos_manuales_de_jugador(email, limite)
    except Exception:  # noqa: BLE001 — sin la tabla (0003) no hay comprobantes
        return []


def estado_pago_de_ref(email: str, ref: str) -> dict | None:
    """El ÚLTIMO comprobante del jugador para esa reserva (en revisión,
    aprobado, rechazado o vencido) o None."""
    return next((p for p in pagos_del_jugador(email) if p.get("reserva_ref") == ref), None)


def normalizar_operacion(op: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(op or "")).upper()[:30]


_contador = {"n": 0}


def registrar_voucher(*, filas: list[dict], c: dict, email: str, nombre: str, medio: str, operacion: str,
                      imagen_b64: str, monto_centimos: int, iso: str, ref: str,
                      vence_en: datetime | None = None) -> dict:
    """El jugador reporta su pago manual. Las filas ya están apartadas por
    `/web/asegurar` (monto calculado por el servidor). [vence_en] = plazo de
    revisión propio (la parte de un pago dividido vence con su división)."""
    dueno = (c.get("dueno") or "").strip().lower()
    medio = (medio or "").strip().lower()
    if medio not in {m["tipo"] for m in medios_publicos(dueno)}:
        return {"ok": False, "error": "medio_no_disponible"}
    if suspendido(dueno, iso):
        return {"ok": False, "error": "club_suspendido"}
    op = normalizar_operacion(operacion)
    if len(op) < 3:
        return {"ok": False, "error": "operacion_requerida"}
    try:
        raw = base64.b64decode((imagen_b64 or "").split(",")[-1], validate=False)
        img, mime, huella = _normalizar_imagen(raw)
    except (ValueError, TypeError):
        return {"ok": False, "error": "imagen_invalida"}
    _contador["n"] = (_contador["n"] + 1) % 100000
    pid = f"pgm_{int(time.time() * 1000)}_{_contador['n']}"
    p = {"id": pid, "reserva_ref": ref, "reserva_ids": [str(f["id"]) for f in filas], "cancha_id": c["id"],
         "dueno": dueno, "jugador_email": email, "jugador_nombre": (nombre or "")[:80],
         "monto_centimos": int(monto_centimos), "moneda": iso, "medio": medio, "operacion": op,
         "voucher_img": img, "voucher_mime": mime, "voucher_hash": huella, "estado": "en_revision",
         "motivo_rechazo": "", "vence_en": vence_en or (_ahora() + timedelta(minutes=config.VOUCHER_PLAZO_MIN)),
         "creado_en": _ahora(), "resuelto_en": None, "resuelto_por": ""}
    err = _repo.crear_pago_manual(p)
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "pago_id": pid, "vence_en": p["vence_en"].isoformat()}


def vista_pago(p: dict) -> dict:
    """Lo que el dueño ve en su bandeja (sin la imagen; va por su endpoint)."""
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in p.items()
            if k not in ("voucher_img", "voucher_hash")}
