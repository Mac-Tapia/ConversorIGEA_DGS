"""El contrato de un proveedor de nube y sus errores tipados (109:RF-6, RF-16).

Cada error dice la causa en español, para el operador: «el permiso caducó», «el fichero cambió mientras se
descargaba». Un fallo nunca deja una copia por válida (RF-6); quien lo recibe decide si se reintenta.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal, Protocol

NombreProveedor = Literal['google', 'microsoft']
PROVEEDORES: tuple[NombreProveedor, ...] = ('google', 'microsoft')
NOMBRES_VISIBLES = {'google': 'Google Drive', 'microsoft': 'OneDrive'}


class ErrorNube(RuntimeError):
    """Un fallo de la nube, con su causa para el operador."""

    causa = 'error de la nube'

    def __init__(self, mensaje: str = '', *, causa: str | None = None) -> None:
        super().__init__(mensaje or self.causa)
        if causa:
            self.causa = causa


class SinConexion(ErrorNube):
    causa = 'sin conexión con el proveedor'


class SinAcceso(ErrorNube):
    """403: la cuenta no tiene permiso, o la carpeta es de solo lectura."""

    causa = 'sin permiso en el proveedor'


class NoEncontrado(ErrorNube):
    causa = 'el fichero ya no está en la nube'


class PermisoCaducado(ErrorNube):
    """401 o ``invalid_grant``: el acceso caducó o se revocó; hay que volver a conectar."""

    causa = 'el permiso caducó o se revocó'


class Limitado(ErrorNube):
    """429 o 5xx tras agotar los reintentos."""

    causa = 'el proveedor limita las peticiones'


class CambioAMitad(ErrorNube):
    causa = 'el fichero cambió mientras se descargaba'


class DescargaCortada(ErrorNube):
    causa = 'la descarga se cortó'


class DemasiadoGrande(ErrorNube):
    causa = 'el fichero supera el tope de bytes'


class YaExiste(ErrorNube):
    """409 o nombre repetido: nunca se sobrescribe lo que ya hay (109:RF-9)."""

    causa = 'ya existe un fichero con ese nombre'


class HostNoPermitido(ErrorNube):
    """Una URL, una redirección o un ``nextLink`` a un host que no es del proveedor (109:RF-16)."""

    causa = 'host no permitido'


@dataclass(frozen=True)
class Item:
    """Un fichero o carpeta remotos, con lo que hace falta para fijar su revisión (109:RF-3, RF-7)."""

    proveedor: NombreProveedor
    id: str
    nombre: str
    #: ``headRevisionId`` o ``version`` en Google, ``cTag`` en Graph (cambia solo con el contenido).
    revision: str
    tamano: int | None = None
    tipo: str = ''
    #: Huellas del contenido que da el proveedor: ``sha256``, ``md5`` o ``quickxor``.
    huellas: dict[str, str] = field(default_factory=dict)
    modificado: str = ''
    carpeta: bool = False
    #: Hoja de cálculo nativa del proveedor, que se exporta (109:RF-5).
    nativo: bool = False
    padre: str = ''
    solo_lectura: bool = False


@dataclass(frozen=True)
class Pagina:
    items: tuple[Item, ...]
    siguiente: str | None = None


class ProveedorNube(Protocol):
    """Lo que la entrada y la salida de la nube piden a cada proveedor."""

    nombre: NombreProveedor

    def metadatos(self, item_id: str) -> Item: ...

    def listar(self, carpeta_id: str, siguiente: str | None = None) -> Pagina: ...

    def descargar(self, item: Item, destino: BinaryIO, *, desde: int = 0) -> int: ...

    def exportar(self, item: Item, destino: BinaryIO) -> tuple[str, str]: ...

    def buscar_por_clave(self, carpeta_id: str, nombre: str, clave: str, sha256: str) -> Item | None: ...

    def subir(self, carpeta_id: str, nombre: str, origen: BinaryIO, tamano: int, *, clave: str) -> Item: ...

    def conceder_lectura(self, item_id: str, destinatarios: list[str]) -> list[dict]: ...

    def enlace_publico(self, item_id: str) -> dict: ...


# --------------------------------------------------------------------------- huellas
_ANCHO_QX = 160
_FILA_QX = _ANCHO_QX // 8 * 8          # 160 bytes: la posición de cada byte se repite cada 160 (mcd(11, 160) = 1)
_BLOQUE_QX = _FILA_QX * 8192


def _xor_filas(bloque: bytes) -> bytes:
    """El XOR de las filas de 160 bytes de ``bloque`` (longitud múltiplo de 160), plegando un entero grande."""
    x, filas = int.from_bytes(bloque, 'little'), len(bloque) // _FILA_QX
    while filas > 1:
        mitad = filas // 2
        bits = mitad * _FILA_QX * 8
        mascara = (1 << bits) - 1
        alto = x >> bits
        x = (x & mascara) ^ (alto & mascara) ^ ((alto >> bits) if filas % 2 else 0)
        filas = mitad
    return x.to_bytes(_FILA_QX, 'little')


def quickxor(fh: BinaryIO) -> str:
    """QuickXorHash de OneDrive (documentación de Microsoft Graph), en base64, sin recorrer byte a byte en Python.

    Cada byte i entra en el registro de 160 bits desplazado (11·i) mod 160; como el desplazamiento se repite cada 160
    bytes, se juntan primero por XOR los bytes con la misma posición y luego se rotan una sola vez.
    """
    acumulado = bytearray(_FILA_QX)
    total = 0
    resto = b''
    while True:
        leido = fh.read(_BLOQUE_QX)
        if not leido:
            break
        datos = resto + leido
        corte = len(datos) - len(datos) % _FILA_QX
        if corte:
            acumulado = bytearray(a ^ b for a, b in zip(acumulado, _xor_filas(datos[:corte])))
        resto = datos[corte:]
        total += len(leido)
    for k, b in enumerate(resto):
        acumulado[k] ^= b
    mascara = (1 << _ANCHO_QX) - 1
    h = 0
    for k, b in enumerate(acumulado):
        p = (k * 11) % _ANCHO_QX
        v = b << p
        h ^= (v | (v >> _ANCHO_QX)) & mascara
    h ^= total << 96
    return base64.b64encode((h & mascara).to_bytes(20, 'little')).decode('ascii')


def huellas_de(ruta: Path) -> dict[str, str]:
    """SHA-256 y QuickXorHash de un fichero local, para compararlos con los que da el proveedor (109:RF-13)."""
    sha = hashlib.sha256()
    with Path(ruta).open('rb') as fh:
        while bloque := fh.read(1024 * 1024):
            sha.update(bloque)
        fh.seek(0)
        qx = quickxor(fh)
    return {'sha256': sha.hexdigest(), 'quickxor': qx}
