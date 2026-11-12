"""Archivo de los informes y libros de la web como dataset, fuera del espacio (105:RF-28 a RF-33).

La carpeta la elige cada máquina en ``config/archivo.json`` (``{"ruta": "G:/Mi unidad/ConverterSmartGrid"}``), local y
fuera de git; sin ella no se archiva nada (P13: ninguna ruta por defecto). La carpeta del usuario es una unidad de Google
Drive, que bloquea un fichero mientras lo sincroniza: se copia a un temporal en la misma carpeta y se renombra, con
reintentos. Nunca se borra ni se sobrescribe nada del archivo: es el dataset.

``archivar(fichero, tipo, ambito, periodo)`` sirve para cualquier informe (estudio, factibilidad, PIDE); en la spec 105 lo
usa el libro de evolución de los clientes fijos.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

from .runtime_paths import raiz_local

#: Intentos y espera inicial (se dobla en cada uno) ante un fichero bloqueado por la sincronización.
REINTENTOS = 5
ESPERA_S = 0.5


class ArchivoError(RuntimeError):
    """La copia al archivo no se pudo hacer; el informe de la salida del espacio sigue intacto."""


def ruta_config() -> Path:
    return raiz_local() / 'config' / 'archivo.json'


def carpeta_archivo() -> Path | None:
    """La carpeta de archivo de esta máquina, o ``None`` si no hay (105:RF-28)."""
    try:
        datos = json.loads(ruta_config().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    ruta = str((datos or {}).get('ruta') or '').strip() if isinstance(datos, dict) else ''
    return Path(ruta) if ruta else None


def guardar_carpeta(ruta: str | None) -> Path | None:
    """Pone o quita la carpeta de archivo (105:RF-29). Una ruta que no es una carpeta existente se rechaza."""
    destino = ruta_config()
    texto = (ruta or '').strip().strip('"')
    if not texto:
        destino.unlink(missing_ok=True)
        return None
    carpeta = Path(texto)
    if not carpeta.is_absolute() or not carpeta.is_dir():
        raise ArchivoError(f'{texto}: no es una carpeta de esta máquina.')
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({'ruta': carpeta.as_posix()}, ensure_ascii=False) + '\n', encoding='utf-8')
    return carpeta


def _parte(texto: str) -> str:
    """Un tramo de la ruta del archivo, sin separadores ni caracteres que Windows no admite."""
    limpio = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', str(texto)).strip(' .')
    if not limpio:
        raise ArchivoError(f'«{texto}» no sirve como carpeta del archivo.')
    return limpio


def _huella(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for trozo in iter(lambda: f.read(1 << 20), b''):
            h.update(trozo)
    return h.hexdigest()


def _con_reintentos(accion, reintentos: int, espera: float):
    for intento in range(reintentos):
        try:
            return accion()
        except FileExistsError:
            raise
        except OSError:
            if intento == reintentos - 1:
                raise
            time.sleep(espera * 2 ** intento)
    return None


def archivar(fichero: Path | str, tipo: str, ambito: str, periodo: str, *, raiz: Path | None = None,
             reintentos: int = REINTENTOS, espera: float = ESPERA_S) -> Path | None:
    """Copia ``fichero`` a ``<raíz>/informes/<tipo>/<ámbito>/<periodo>/`` y devuelve dónde quedó (105:RF-30 a RF-33).

    Sin carpeta de archivo devuelve ``None``. Un fichero igual ya archivado no se copia otra vez; uno distinto con el
    mismo nombre lo reemplaza (RF-40, cambia RF-32); los demás ficheros de la carpeta no se tocan. Si no se puede,
    ``ArchivoError``.
    """
    origen = Path(fichero)
    base = raiz if raiz is not None else carpeta_archivo()
    if base is None:
        return None
    if not base.is_dir():
        raise ArchivoError(f'La carpeta de archivo {base} no está disponible (¿unidad desconectada?).')
    carpeta = base / 'informes' / _parte(tipo) / _parte(ambito) / _parte(periodo)
    huella = _huella(origen)
    temporal = carpeta / f'.{origen.name}.{os.getpid()}.parcial'
    try:
        _con_reintentos(lambda: carpeta.mkdir(parents=True, exist_ok=True), reintentos, espera)
        destino = carpeta / origen.name
        if destino.is_file() and _huella(destino) == huella:
            return destino
        _con_reintentos(lambda: shutil.copyfile(origen, temporal), reintentos, espera)
        # 105:RF-40 (usuario, 2026-11-12: «solo la versión vigente, la última»; «a otros archivos no deben reemplazar,
        # solo si es el mismo archivo»): el mismo nombre se reemplaza de una vez con ``os.replace``, sin copias «(2)»;
        # ningún otro fichero de la carpeta se toca. Si el reemplazo falla, queda entera la versión anterior.
        _con_reintentos(lambda: os.replace(temporal, destino), reintentos, espera)
        return destino
    except OSError as exc:
        raise ArchivoError(f'No se pudo archivar {origen.name} en {carpeta}: {exc}') from exc
    finally:
        # El temporal es solo de esta copia: no es parte del archivo.
        try:
            temporal.unlink(missing_ok=True)
        except OSError:
            pass
