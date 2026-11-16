"""La entrada de la nube: una copia inmutable con su huella, nunca el fichero remoto (109:RF-3, RF-5, RF-6).

Cada estudio se calcula sobre una copia fija: el fichero remoto puede cambiar en cualquier momento. La copia va en
``<espacio>/nube/copias/<sha256>/<nombre>`` con ``copia.json`` (proveedor, id, revisión, formato de origen y
exportado, SHA-256, tamaño y hora). Se descarga en un staging del mismo volumen y se publica con ``os.replace`` solo
si todo cuadró (P6):

- la revisión es la misma antes y después de descargar (el ``cTag`` en Graph, que no cambia con los metadatos);
- si el proveedor da la huella del contenido (SHA-256 o MD5), coincide con la local;
- un corte se reanuda desde donde iba, con la misma revisión; si no se puede, no queda copia.

Una copia nunca se reescribe: la misma huella es el mismo contenido, y la que ya está se reutiliza.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ...adaptadores.nube.google_drive import EXPORTACIONES
from ...adaptadores.nube.proveedor import CambioAMitad, DescargaCortada, ErrorNube, Item, ProveedorNube
from ...runtime_paths import staging_publicacion
from ...util import write_json_atomic

FICHA = 'copia.json'
_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS = frozenset({'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                         *(f'LPT{i}' for i in range(1, 10))})


@dataclass(frozen=True)
class Copia:
    carpeta: Path
    ruta: Path
    ficha: dict


def nombre_seguro(nombre: str) -> str:
    """El nombre remoto, válido en Windows y sin rutas: «../x» o «C:\\x» no salen de la carpeta de la copia."""
    limpio = _PROHIBIDOS.sub('_', Path(str(nombre).replace('\\', '/')).name).strip(' .')
    if not limpio or limpio.split('.')[0].upper() in _RESERVADOS:
        limpio = f'fichero_{limpio}' if limpio else 'fichero'
    return limpio[:180]


def leer_ficha(carpeta: Path) -> dict:
    return json.loads((carpeta / FICHA).read_text(encoding='utf-8'))


class _Escritor:
    """Escribe en el staging, calcula la huella al vuelo y deja cancelar entre bloques (P7)."""

    def __init__(self, fh: BinaryIO, ctx, total: int | None) -> None:
        self.fh, self.ctx, self.total = fh, ctx, total
        self.sha = hashlib.sha256()
        self.md5 = hashlib.md5()  # noqa: S324 - para comparar con la que da Google, no como seguridad
        self.bytes = 0

    def write(self, bloque: bytes) -> int:
        if self.ctx is not None:
            self.ctx.check_cancel()
        self.fh.write(bloque)
        self.sha.update(bloque)
        self.md5.update(bloque)
        self.bytes += len(bloque)
        if self.ctx is not None and self.total:
            self.ctx.progress(min(self.bytes, self.total), self.total, 'descargando')
        return len(bloque)


def importar(proveedor: ProveedorNube, item_id: str, raiz: Path, ctx=None, *, reintentos: int = 3) -> Copia:
    """109:RF-3: descarga ``item_id`` y deja su copia fija en ``raiz``; si algo no cuadra, ninguna copia y la causa."""
    antes = proveedor.metadatos(item_id)
    if antes.carpeta:
        raise ErrorNube(f'«{antes.nombre}» es una carpeta: elija los ficheros.')
    raiz = Path(raiz)
    raiz.mkdir(parents=True, exist_ok=True)
    provisional = raiz / f'.importando-{hashlib.sha256(f"{antes.proveedor}|{item_id}".encode()).hexdigest()[:16]}'
    with staging_publicacion(provisional) as temporal:
        temporal.mkdir()
        nombre, formato_exportado = nombre_seguro(antes.nombre), None
        if antes.nativo:
            ext = EXPORTACIONES.get(antes.tipo, ('', ''))[1]
            nombre = nombre_seguro(Path(antes.nombre).stem + ext) if ext else nombre
        with (temporal / nombre).open('wb') as fh:
            escritor = _Escritor(fh, ctx, antes.tamano)
            if antes.nativo:
                _origen, formato_exportado = proveedor.exportar(antes, escritor)
            else:
                _descargar_reanudando(proveedor, antes, escritor, fh, reintentos)
        despues = proveedor.metadatos(item_id)
        if despues.revision != antes.revision:
            raise CambioAMitad(f'«{antes.nombre}» cambió en la nube mientras se descargaba (revisión {antes.revision} '
                               f'→ {despues.revision}): no queda copia. Vuelva a importarlo.')
        sha256 = escritor.sha.hexdigest()
        _comprobar_huella(antes, sha256, escritor.md5.hexdigest(), escritor.bytes)
        ficha = {'version': 1, 'proveedor': antes.proveedor, 'id': antes.id, 'nombre_remoto': antes.nombre,
                 'nombre': nombre, 'revision': antes.revision, 'modificado_remoto': antes.modificado,
                 'formato_origen': antes.tipo or Path(antes.nombre).suffix.lower(),
                 'formato_exportado': formato_exportado, 'sha256': sha256, 'tamano': escritor.bytes,
                 'importado': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        write_json_atomic(temporal / FICHA, ficha)   # 001:RF-5: ni dentro del staging queda a medias
        if ctx is not None:
            ctx.check_cancel()           # cancelado al final: tampoco queda copia (P7)
        final = raiz / sha256
        if final.is_dir() and (final / FICHA).is_file():
            # Misma huella, mismo contenido: la copia que ya está no se reescribe (RF-8).
            existente = leer_ficha(final)
            return Copia(final, final / existente['nombre'], existente)
        os.replace(temporal, final)
    return Copia(final, final / nombre, ficha)


def _descargar_reanudando(proveedor: ProveedorNube, item: Item, escritor: _Escritor, fh: BinaryIO,
                          reintentos: int) -> None:
    cortes = 0
    while True:
        try:
            proveedor.descargar(item, escritor, desde=escritor.bytes)
            return
        except DescargaCortada:
            cortes += 1
            actual = proveedor.metadatos(item.id)
            if actual.revision != item.revision:
                raise CambioAMitad(f'«{item.nombre}» cambió en la nube mientras se descargaba: no queda copia.') \
                    from None
            if cortes > reintentos:
                raise DescargaCortada(f'La descarga de «{item.nombre}» se cortó {cortes} veces: no queda copia. '
                                      'Compruebe la conexión e inténtelo otra vez.') from None
            fh.flush()


def _comprobar_huella(item: Item, sha256: str, md5: str, tamano: int) -> None:
    if item.nativo:
        return
    if item.tamano is not None and item.tamano != tamano:
        raise CambioAMitad(f'«{item.nombre}» llegó con {tamano} bytes y la nube dice {item.tamano}: no queda copia.')
    for clave, local in (('sha256', sha256), ('md5', md5)):
        remota = item.huellas.get(clave)
        if remota and remota.lower() != local:
            raise CambioAMitad(f'La huella de «{item.nombre}» no coincide con la que da la nube ({clave}): '
                               'no queda copia.')
