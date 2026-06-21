"""Retención mínima: verificar y NO retener.

Los documentos personales (DNI, recibo, selfie) se procesan en memoria o en un
archivo TEMPORAL que se ELIMINA siempre (incluso ante error). Si por excepción se
decide conservar algo, debe ir CIFRADO y con un TTL de eliminación.
"""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from typing import Iterator

# TTL del único dato que sí persiste: el RESULTADO (bool + score + fecha).
TTL_RESULTADO = timedelta(days=int(os.getenv("VERIF_TTL_DIAS", "365")))


@contextmanager
def documento_temporal(contenido: bytes) -> Iterator[str]:
    """Procesa un documento personal en un archivo temporal y GARANTIZA su
    borrado al salir (verificar y no retener). Nunca toca la base de datos.

    Uso:
        with documento_temporal(bytes_dni) as ruta:
            ... extraer señales (OCR/visión) ...
        # aquí el archivo ya fue eliminado
    """
    fd, ruta = tempfile.mkstemp(prefix="verif_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
        yield ruta
    finally:
        try:
            os.remove(ruta)
        except FileNotFoundError:
            pass


def cifrar(data: bytes, key: bytes | None = None) -> bytes:
    """STUB de cifrado en reposo. Si se decide conservar algo, va cifrado + TTL.

    En producción: usar Fernet/KMS con `VERIF_ENCRYPTION_KEY`.
        from cryptography.fernet import Fernet
        return Fernet(key or os.environ["VERIF_ENCRYPTION_KEY"]).encrypt(data)
    """
    # Stub: no-op marcado para reemplazo (NO usar en producción con datos reales).
    return data
