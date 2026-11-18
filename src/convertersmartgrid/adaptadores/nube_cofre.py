"""El cofre de las credenciales de la nube: DPAPI de Windows, por usuario, espacio y proveedor (109:RF-2, RF-14).

Solo guarda el token de refresco; el de acceso vive en memoria y caduca en una hora. Va en
``raiz_local()/secretos/nube/<espacio>/<proveedor>-<huella de la cuenta>.dpapi``, fuera del espacio de trabajo y de
``config/``: ``web/copia_datos.raices_de_datos`` copia los dos a Drive (086:RF-85), y un token copiado así abriría la
cuenta desde otro equipo. ``secretos/`` está en ``.gitignore``.

DPAPI (``CryptProtectData`` con el ámbito del usuario) lo cifra con la clave de la sesión de Windows: otro usuario
del mismo puesto no lo abre, ni una copia restaurada en otro equipo, que tiene que volver a conectar. La entropía lleva
el espacio y el proveedor: el cofre de una empresa no se descifra con la de otra aunque se copie el fichero (P13).
Descartados ``keyring`` (una dependencia más y un tope de 2560 bytes por credencial) y Fernet (la clave quedaría en
un fichero junto al cifrado); ver el plan de la spec 109.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from ..dominio.runtime_paths import raiz_local
from ..dominio.util import publicar_duradero

_ESPACIO = re.compile(r'^[A-Za-z0-9_-]{1,80}$')
_PROVEEDORES = ('google', 'microsoft')
_SIN_INTERFAZ = 0x1          # CRYPTPROTECT_UI_FORBIDDEN: nunca abre una ventana de Windows


class CofreIlegible(RuntimeError):
    """DPAPI no pudo descifrarlo: otro usuario, otro equipo, otra entropía o un fichero dañado."""


class CofreNoDisponible(RuntimeError):
    """Fuera de Windows no hay DPAPI: la nube no se ofrece y lo local sigue (P8)."""


@dataclass(frozen=True)
class Credencial:
    cuenta: str
    refresco: str

    def __repr__(self) -> str:          # nunca el token en un registro o una traza
        return f'Credencial(cuenta={self.cuenta!r}, refresco=<oculto>)'


def ruta_cofre(raiz: Path | None = None) -> Path:
    return (raiz_local() if raiz is None else Path(raiz)) / 'secretos'


def _carpeta(wid: str, raiz: Path | None) -> Path:
    if not _ESPACIO.fullmatch(wid or ''):
        raise ValueError(f'Identificador de espacio no válido para el cofre: {wid!r}.')
    return ruta_cofre(raiz) / 'nube' / wid


def _proveedor(proveedor: str) -> str:
    if proveedor not in _PROVEEDORES:
        raise ValueError(f'Proveedor desconocido: {proveedor!r}.')
    return proveedor


def entropia(wid: str, proveedor: str) -> bytes:
    return f'convertersmartgrid|nube|{wid}|{_proveedor(proveedor)}'.encode('utf-8')


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', ctypes.c_uint32), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _blob(datos: bytes) -> tuple[_Blob, ctypes.Array]:
    memoria = ctypes.create_string_buffer(datos, len(datos))
    return _Blob(len(datos), ctypes.cast(memoria, ctypes.POINTER(ctypes.c_char))), memoria


def _dpapi(cifrar: bool, datos: bytes, extra: bytes) -> bytes:
    if sys.platform != 'win32':
        raise CofreNoDisponible('El cofre de la nube usa DPAPI de Windows; en este sistema la nube no se ofrece.')
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    entrada, _m1 = _blob(datos)
    sal, _m2 = _blob(extra)
    salida = _Blob()
    funcion = crypt32.CryptProtectData if cifrar else crypt32.CryptUnprotectData
    ok = funcion(ctypes.byref(entrada), None, ctypes.byref(sal), None, None, _SIN_INTERFAZ, ctypes.byref(salida))
    if not ok:
        raise CofreIlegible('No se pudo abrir el cofre de la nube con esta sesión de Windows: vuelva a conectar '
                            'la cuenta.' if not cifrar else 'Windows no pudo cifrar la credencial de la nube.')
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        kernel32.LocalFree(salida.pbData)


def cifrar(datos: bytes, extra: bytes) -> bytes:
    return _dpapi(True, datos, extra)


def descifrar(datos: bytes, extra: bytes) -> bytes:
    return _dpapi(False, datos, extra)


def _fichero(wid: str, proveedor: str, cuenta: str, raiz: Path | None) -> Path:
    huella = hashlib.sha256(cuenta.strip().lower().encode('utf-8')).hexdigest()[:16]
    return _carpeta(wid, raiz) / f'{_proveedor(proveedor)}-{huella}.dpapi'


def guardar(wid: str, proveedor: str, cuenta: str, refresco: str, *, raiz: Path | None = None) -> Path:
    """Guarda la credencial de una cuenta; la de otra cuenta del mismo proveedor y espacio se retira (una por par)."""
    destino = _fichero(wid, proveedor, cuenta, raiz)
    claro = json.dumps({'cuenta': cuenta, 'refresco': refresco}, ensure_ascii=False).encode('utf-8')
    publicar_duradero(destino, cifrar(claro, entropia(wid, proveedor)))
    for otro in destino.parent.glob(f'{proveedor}-*.dpapi'):
        if otro != destino:
            otro.unlink(missing_ok=True)
    return destino


def leer(wid: str, proveedor: str, *, raiz: Path | None = None) -> Credencial | None:
    """La credencial del espacio y el proveedor; ninguna si no hay o no se puede abrir con esta entropía."""
    carpeta = _carpeta(wid, raiz)
    for ruta in sorted(carpeta.glob(f'{_proveedor(proveedor)}-*.dpapi')):
        try:
            datos = json.loads(descifrar(ruta.read_bytes(), entropia(wid, proveedor)))
        except (CofreIlegible, OSError, ValueError):
            continue
        if isinstance(datos, dict) and datos.get('refresco'):
            return Credencial(str(datos.get('cuenta') or ''), str(datos['refresco']))
    return None


def borrar(wid: str, proveedor: str, *, raiz: Path | None = None) -> bool:
    """109:RF-14: retira la credencial del espacio y el proveedor; las copias y los recibos no están aquí."""
    borrados = False
    for ruta in _carpeta(wid, raiz).glob(f'{_proveedor(proveedor)}-*.dpapi'):
        ruta.unlink(missing_ok=True)
        borrados = True
    return borrados
