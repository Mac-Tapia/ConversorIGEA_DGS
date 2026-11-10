"""Utilidades de E/S y de números compartidas por el motor y la web.

Estaban copiadas hasta en siete sitios (diagnóstico del 2026-10-07, B5): el hash de
fichero en cuatro, la escritura atómica de JSON en tres con formatos que ya divergían.
``tests/test_util.py`` falla si alguna vuelve a copiarse en ``src/convertersmartgrid``.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
from types import ModuleType
from collections.abc import Iterable, Mapping
from typing import Any


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sincronizar_carpeta(carpeta: Path | str) -> None:
    """Hace duradero un ``replace`` en POSIX; Windows no deja abrir una carpeta para sincronizarla."""
    if os.name == 'nt':
        return
    descriptor = os.open(carpeta, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publicar_duradero(path: Path | str, contenido: str | bytes) -> None:
    """Escribe en un temporal, lo sincroniza y solo entonces sustituye el fichero (086:RF-1).

    ``replace`` sin ``fsync`` es atómico frente a un proceso que muere, pero no frente a un corte
    de luz: el sistema puede grabar el cambio de nombre antes que los datos, y deja un
    ``workspace.json`` vacío donde había uno bueno.
    """
    from .runtime_paths import staging_publicacion

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with staging_publicacion(path) as temporary:
        if isinstance(contenido, str):
            temporary.write_text(contenido, encoding='utf-8')
        else:
            temporary.write_bytes(contenido)
        with temporary.open('rb+') as escrito:
            os.fsync(escrito.fileno())
        _sustituir(temporary, path)
    sincronizar_carpeta(path.parent)


#: Esperas antes de cada reintento de ``replace`` (086:RF-54): en total, menos de dos segundos.
ESPERAS_SUSTITUIR_S = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8)


def _sustituir(temporal: Path, destino: Path) -> None:
    """``replace`` con reintentos ante un bloqueo pasajero de Windows (086:RF-54).

    En Windows, ``replace`` falla con ``PermissionError`` (WinError 5 o 32) si otro proceso tiene abierto el destino en
    ese instante, como el antivirus que lee cada JSON nuevo. Con la suite completa en marcha (2026-11-10) un trabajo de la
    web no llegó a encolarse una vez de 8 613 pruebas, y corrida suelta pasaba. Pasado el último intento, el error sube.
    """
    import time

    for espera in (*ESPERAS_SUSTITUIR_S, None):
        try:
            temporal.replace(destino)
            return
        except PermissionError:
            if espera is None or os.name != 'nt':
                raise
            time.sleep(espera)


def ruta_copia_anterior(path: Path | str) -> Path:
    """Dónde queda la versión anterior de un fichero de estado: ``workspace.json.bak``."""
    path = Path(path)
    return path.with_name(path.name + '.bak')


def _guardar_copia_anterior(path: Path) -> None:
    """Conserva la versión buena: un fichero ya dañado nunca pisa la copia que lo puede arreglar."""
    try:
        actual = path.read_bytes()
    except FileNotFoundError:
        return
    try:
        json.loads(actual)
    except ValueError:
        return
    publicar_duradero(ruta_copia_anterior(path), actual)


def write_json_atomic(path: Path, payload: Any, *, copia: bool = False) -> None:
    """Prepara fuera del checkout, sincroniza y publica en el mismo volumen con ``replace``.

    Se serializa antes de abrir el temporal, así que un error de serialización deja el
    fichero anterior intacto. ``default=str`` admite rutas y fechas en los manifiestos.
    Con ``copia``, la versión anterior queda en ``<nombre>.bak`` (086:RF-2).
    """
    contenido = json.dumps(payload, indent=2, ensure_ascii=False, default=str) + '\n'
    path = Path(path)
    if copia:
        _guardar_copia_anterior(path)
    publicar_duradero(path, contenido)


def finite_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def importar_opcional(modulo: str, error: Exception) -> ModuleType:
    """Importa una dependencia opcional o lanza ``error``, que elige quien llama.

    Cada vía conserva su excepción (``DownloadError``, ``ArcGISError``…) porque sus
    llamadores la capturan por tipo; lo común es solo el intento de importar.
    """
    try:
        return importlib.import_module(modulo)
    except ImportError as exc:
        raise error from exc


def nombre_seguro(texto: str, *, maximo: int | None = None, defecto: str = 'GRUPO') -> str:
    """Nombre apto para fichero y para PowerFactory: letras, dígitos, ``-`` y ``_``."""
    limpio = ''.join(c if c.isalnum() or c in '-_' else '_' for c in texto)
    return limpio[:maximo] or defecto


#: Prefijo de los esquemas guardados antes del cambio de nombre (058:RF-6, RF-9).
PREFIJO_ESQUEMA_ANTERIOR = 'igea-dgs-'  # legado-058

#: Lo que el sistema dejó dentro de los proyectos de DIgSILENT con el nombre anterior, que no se
#: renombra (058:RF-9): nombre de hoy → el de antes. El 2026-11-01, la optimización de NA203 +
#: NA205 no encontraba su «Con proyecto» ni la biblioteca de tipos de sus obras.
NOMBRES_ANTERIORES_PF = {
    'CSG_Biblioteca_tipos': 'IGEA_Biblioteca_tipos',  # legado-058
    'CSG_confiabilidad': 'IGEA_confiabilidad',  # legado-058
}


def esquema_vigente(valor: object) -> object:
    """El esquema de un fichero guardado, con el nombre de hoy (058:RF-6).

    El 2026-11-01, tras el cambio de nombre, la importación de NJA202 (Electro Oriente) falló con
    «vinculos_pf.json no tiene el esquema esperado»: el registro compartido y los vínculos de
    cada espacio, escritos antes, llevaban el prefijo anterior. Se lee cualquiera de los dos y
    se escribe siempre el nuevo; lo guardado no se reescribe, para que sus huellas sigan valiendo.
    """
    if isinstance(valor, str) and valor.startswith(PREFIJO_ESQUEMA_ANTERIOR):
        return 'convertersmartgrid-' + valor[len(PREFIJO_ESQUEMA_ANTERIOR):]
    return valor


def _texto_csv(v: Any) -> str:
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'sí' if v else 'no'
    if isinstance(v, float):
        return f'{v:.4f}'
    return str(v)


def escribir_csv(filas: Iterable[Mapping[str, Any]], columnas: tuple[str, ...], destino: Path) -> Path:
    """CSV con «;» y BOM, como las plantillas de cargas: Excel en español lo abre bien.

    Los decimales van con cuatro cifras fijas: así dos ejecuciones con las mismas medidas
    dan el mismo fichero byte a byte.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(columnas)
        for f in filas:
            w.writerow([_texto_csv(f.get(c)) for c in columnas])
    return destino
