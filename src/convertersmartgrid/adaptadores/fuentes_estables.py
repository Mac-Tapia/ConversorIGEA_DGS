"""034:RF-20: descriptor de lectura con exclusión efectiva, sin copiar la fuente."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sys
from typing import BinaryIO, Iterator


@dataclass(frozen=True)
class LecturaEstable:
    """Identidad de los bytes que el consumidor lee mientras conserva la guarda."""

    path: Path
    stream: BinaryIO
    sha256: str
    size: int
    stat: os.stat_result


@contextmanager
def abrir_fuente_estable(path: Path | str) -> Iterator[LecturaEstable]:
    """Retiene la guarda Windows hasta que el lector termina, incluido ante error.

    Extraída de la guarda SQLite existente: compartir solo READ impide escritores
    ya abiertos, escrituras nuevas y reemplazos ABA. Los lectores legacy pueden
    abrir la ruta para lectura; los lectores de streams usan el mismo descriptor.
    """
    import ctypes
    from ctypes import wintypes

    if sys.platform != 'win32':
        raise OSError('No hay una guarda de solo lectura verificada para esta plataforma; '
                      'se requiere Windows o una exportación/snapshot coherente.')
    import msvcrt

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    abrir = kernel.CreateFileW
    abrir.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    abrir.restype = wintypes.HANDLE
    cerrar = kernel.CloseHandle
    cerrar.argtypes = [wintypes.HANDLE]
    cerrar.restype = wintypes.BOOL
    exacta = Path(path).resolve(strict=True)
    handle = abrir(str(exacta), 0x80000000, 0x00000001, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        cerrar(handle)
        raise
    # open_osfhandle transfiere la propiedad: cerrar el stream cierra handle una vez.
    with os.fdopen(descriptor, 'rb') as stream:
        stat = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        stream.seek(0)
        yield LecturaEstable(exacta, stream, digest, stat.st_size, stat)
