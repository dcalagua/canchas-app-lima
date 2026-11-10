"""ELO de los RETOS aplicado en el SERVIDOR (1-oct-2026).

Antes lo calculaba el APK (`AppState.aplicarEloDeRetos`) en el teléfono de
cada jugador, SOLO al abrir "Mis retos", con un conjunto local de "ya
aplicados" (`retos_elo_aplicados`); la web nunca lo aplicaba. Resultado: el
nivel dependía de qué dispositivo abrió qué pantalla. Ahora se aplica UNA sola
vez por reto, aquí, en cuanto el reto pasa a JUGADO (confirmado por el rival,
auto-confirmado por plazo o sin doble confirmación), y app y web leen el mismo
`pichangol_niveles`.

Fórmula = `Nivel.calcularElo` del APK (ESPEJO, no cambiar uno solo):
    esperado = 1 / (1 + 10 ** ((rival − mi) / 2))
    nuevo    = clamp(mi + K · (real − esperado), 1.0, 7.0)   con K = 0.15
y, como `registrarResultadoNivel`, suma 1 partido y 1 victoria al ganador.
Sin fila de nivel se parte de 3.0 (default de `Nivel`). Solo SINGLES: el
dobles se omite, igual que el APK.

Diferencia buscada con el APK: los DOS niveles nuevos se calculan con los
niveles de ANTES del partido (en el APK cada teléfono usaba el nivel del rival
que encontrara, ya movido o no según quién abriera primero).

Migración: solo entran los retos que pasan a JUGADO desde este cambio
(`marcar_jugado`, llamado en la transición). Los que ya estaban jugados antes
del despliegue NUNCA se aplican aquí: esos ya los aplicó el APK en el teléfono
de cada jugador (su conjunto local), así no se cuentan dos veces.

Idempotencia: `stores.retos_elo[str(id)]` (snapshot) = pendiente | aplicado |
omitido. Si la base no está disponible queda `pendiente` y se reintenta al
listar retos (`aplicar_pendientes`).
"""

from __future__ import annotations

import threading

from db import pg
from db.store import Reto, ahora, stores

K = 0.15
NIVEL_INICIAL = 3.0

_lock = threading.Lock()


def calcular_elo(mi_nivel: float, rival_nivel: float, gane: bool, k: float = K) -> float:
    """`Nivel.calcularElo` del APK."""
    esperado = 1 / (1 + 10 ** ((rival_nivel - mi_nivel) / 2))
    real = 1.0 if gane else 0.0
    nuevo = mi_nivel + k * (real - esperado)
    return max(1.0, min(7.0, nuevo))


def nuevos_niveles(ganador: dict, perdedor: dict) -> tuple[dict, dict]:
    """Filas nuevas {nivel, partidos, victorias} de ganador y perdedor, a partir
    de sus filas de ANTES del partido (sin fila = 3.0, 0, 0)."""
    ng, np_ = float(ganador.get("nivel", NIVEL_INICIAL)), float(perdedor.get("nivel", NIVEL_INICIAL))
    g = {"nivel": calcular_elo(ng, np_, True),
         "partidos": int(ganador.get("partidos", 0)) + 1,
         "victorias": int(ganador.get("victorias", 0)) + 1}
    p = {"nivel": calcular_elo(np_, ng, False),
         "partidos": int(perdedor.get("partidos", 0)) + 1,
         "victorias": int(perdedor.get("victorias", 0))}
    return g, p


def _aplicar_en_base(deporte: str, ganador: str, perdedor: str) -> dict | None:
    """Lee (con bloqueo de fila) y escribe los dos niveles en UNA transacción
    de `pichangol_niveles` (misma fila que `NivelesRepo.guardar`: clave
    email+deporte; conserva `confiabilidad`). None si no hay base o falló."""
    if not pg.habilitado:
        return None
    try:
        with pg.conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT lower(email), nivel, partidos, victorias FROM pichangol_niveles "
                "WHERE lower(email) = ANY(%s) AND deporte = %s FOR UPDATE",
                ([ganador, perdedor], deporte))
            filas = {f[0]: {"nivel": float(f[1] if f[1] is not None else NIVEL_INICIAL),
                            "partidos": int(f[2] or 0), "victorias": int(f[3] or 0)}
                     for f in cur.fetchall()}
            antes_g = filas.get(ganador) or {"nivel": NIVEL_INICIAL, "partidos": 0, "victorias": 0}
            antes_p = filas.get(perdedor) or {"nivel": NIVEL_INICIAL, "partidos": 0, "victorias": 0}
            g, p = nuevos_niveles(antes_g, antes_p)
            for email, fila in ((ganador, g), (perdedor, p)):
                cur.execute(
                    "INSERT INTO pichangol_niveles (email, deporte, nivel, partidos, victorias, "
                    "confiabilidad, actualizado) VALUES (%s, %s, %s, %s, %s, 1.0, now()) "
                    "ON CONFLICT (email, deporte) DO UPDATE SET nivel = EXCLUDED.nivel, "
                    "partidos = EXCLUDED.partidos, victorias = EXCLUDED.victorias, actualizado = now()",
                    (email, deporte, round(fila["nivel"], 4), fila["partidos"], fila["victorias"]))
            return {ganador: {"antes": antes_g["nivel"], "despues": round(g["nivel"], 4)},
                    perdedor: {"antes": antes_p["nivel"], "despues": round(p["nivel"], 4)}}
    except Exception as ex:  # noqa: BLE001
        print(f"[elo] no se pudo guardar el nivel ({deporte}): {ex}", flush=True)
        return None


def marcar_jugado(r: Reto) -> None:
    """Llamar cuando el reto PASA a jugado (las 3 transiciones de
    `retos/router.py`). Lo deja pendiente y lo intenta aplicar ya."""
    clave = str(r.id)
    if clave not in stores.retos_elo:
        stores.retos_elo[clave] = {"estado": "pendiente", "en": ahora().isoformat()}
    aplicar(r)


def aplicar(r: Reto) -> str:
    """Aplica el ELO del reto si está pendiente. Devuelve el estado final."""
    clave = str(r.id)
    with _lock:
        info = stores.retos_elo.get(clave)
        if info is None or info.get("estado") != "pendiente":
            return (info or {}).get("estado", "")
        if r.estado != "jugado" or not r.ganador_email:
            # Lo disputaron/re-reportaron después: no cuenta mientras no vuelva a jugado.
            return "pendiente"
        retador, retado = r.retador_email.lower(), r.retado_email.lower()
        ganador = r.ganador_email.lower()
        if (r.modalidad or "singles") == "dobles" or not r.deporte or ganador not in (retador, retado):
            info.update(estado="omitido", en=ahora().isoformat())
            return "omitido"
        perdedor = retado if ganador == retador else retador
        cambios = _aplicar_en_base(r.deporte, ganador, perdedor)
        if cambios is None:
            return "pendiente"
        info.update(estado="aplicado", en=ahora().isoformat(), cambios=cambios)
        print(f"[elo] reto {r.id} {r.deporte}: {ganador} {cambios[ganador]} · "
              f"{perdedor} {cambios[perdedor]}", flush=True)
        return "aplicado"


def aplicar_pendientes() -> int:
    """Reintenta los retos que quedaron pendientes (base caída). Barato si no
    hay ninguno."""
    pend = {k for k, v in stores.retos_elo.items() if v.get("estado") == "pendiente"}
    if not pend:
        return 0
    n = 0
    for r in stores.retos:
        if str(r.id) in pend and aplicar(r) == "aplicado":
            n += 1
    return n
