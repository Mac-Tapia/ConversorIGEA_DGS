"""El paquete de soporte: lo que hace falta para entender un fallo, sin datos del cliente (086:RF-42).

Se arma con una lista cerrada de lo que entra, no quitando de todo lo que hay: un resto olvidado en un espacio de
trabajo no llega al paquete porque nadie lo pone en él. Lleva el informe del doctor, las versiones, la forma del
perfil (sus claves, no sus valores) y los registros, en los que cada línea pasa antes por ``anonimizar``.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import socket
import time
import zipfile
from collections.abc import Iterable, Iterator
from importlib import metadata
from pathlib import Path
from typing import Any

from .. import __version__
from ..perfil_empresa import ruta_perfil_activo
from ..registro_rotativo import carpeta_de_registros
from .doctor import diagnosticar

_RUTA_WINDOWS = re.compile(r'(?:[A-Za-z]:|\\\\[^\\/\s]+)[\\/][^\s"\'<>|«»,;]*')
_RUTA_POSIX = re.compile(r'(?<![\w.:/])/(?:[\w.\- ]+/)+[\w.\-]*')
_CORREO = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_IP = re.compile(r'\b(?!127\.0\.0\.1\b)\d{1,3}(?:\.\d{1,3}){3}\b')
#: Códigos de red y de alimentador de cualquier empresa: letras y cifras juntas, en mayúsculas.
_CODIGO = re.compile(r'\b[A-ZÑ]{1,6}[-_]?\d{1,6}[A-Z0-9_-]*\b')
#: Lo escrito entre comillas suele ser un nombre: de un cliente, de una SET o de un fichero.
_ENTRECOMILLADO = re.compile(r'«[^»]*»|"[^"]*"|\'[^\']*\'')


def _terminos_del_perfil(ruta: Path) -> set[str]:
    """Los textos del perfil de esta empresa, que pueden salir en cualquier mensaje."""
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return set()

    def textos(x: Any) -> Iterator[str]:
        if isinstance(x, dict):
            for v in x.values():
                yield from textos(v)
        elif isinstance(x, list):
            for v in x:
                yield from textos(v)
        elif isinstance(x, str) and len(x.strip()) >= 3:
            yield x.strip()

    return set(textos(datos))


def _identidad_del_equipo() -> set[str]:
    salida = {socket.gethostname()}
    try:
        salida.add(getpass.getuser())
    except (OSError, KeyError, ImportError):
        pass
    salida |= {os.environ.get(n, '') for n in ('USERNAME', 'USER', 'COMPUTERNAME', 'USERDOMAIN')}
    return {s for s in salida if len(s) >= 3}


def anonimizar(linea: str, terminos: Iterable[str] = ()) -> str:
    """Sustituye lo que pueda identificar al cliente, al operador o su red; conserva el mensaje y la cifra."""
    salida = linea
    # Los más largos primero: «Empresa Norte» antes que «Norte».
    for termino in sorted(set(terminos), key=len, reverse=True):
        salida = re.sub(re.escape(termino), '<nombre>', salida, flags=re.IGNORECASE)
    salida = _RUTA_WINDOWS.sub('<ruta>', salida)
    salida = _RUTA_POSIX.sub('<ruta>', salida)
    salida = _CORREO.sub('<correo>', salida)
    salida = _IP.sub('<ip>', salida)
    salida = _ENTRECOMILLADO.sub('<texto>', salida)
    return _CODIGO.sub('<codigo>', salida)


def _forma_del_perfil(ruta: Path) -> dict[str, Any]:
    """Qué claves trae el perfil, sin un solo valor: basta para saber qué falta."""
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'existe': False}
    except (OSError, ValueError) as exc:
        return {'existe': True, 'legible': False, 'error': type(exc).__name__}
    return {'existe': True, 'legible': True, 'claves': sorted(str(k) for k in datos) if isinstance(datos, dict) else []}


def _versiones() -> dict[str, str]:
    """Solo las de las librerías; sus rutas, no."""
    return dict(sorted((d.metadata['Name'] or '?', d.version) for d in metadata.distributions() if d.metadata['Name']))


def _informe_anonimo(informe: dict[str, Any], terminos: set[str]) -> dict[str, Any]:
    return {**informe, 'comprobaciones': [{k: anonimizar(v, terminos) if k in ('detalle', 'arreglo') else v for k, v in c.items()}
                                          for c in informe['comprobaciones']]}


def crear_paquete(destino: Path, *, carpeta_registros: Path | None = None, ruta_perfil: Path | None = None,
                  informe: dict[str, Any] | None = None, ahora: float | None = None) -> Path:
    """Escribe ``<destino>/csg-soporte-<fecha>.zip`` y devuelve su ruta."""
    momento = time.time() if ahora is None else ahora
    perfil = ruta_perfil_activo() if ruta_perfil is None else ruta_perfil
    registros = carpeta_de_registros() if carpeta_registros is None else carpeta_registros
    terminos = _terminos_del_perfil(perfil) | _identidad_del_equipo()
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"csg-soporte-{time.strftime('%Y%m%dT%H%M%S', time.localtime(momento))}.zip"
    contenido: list[str] = []
    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        def escribir(nombre: str, texto: str) -> None:
            z.writestr(nombre, texto)
            contenido.append(nombre)

        escribir('doctor.json', json.dumps(_informe_anonimo(diagnosticar() if informe is None else informe, terminos),
                                           ensure_ascii=False, indent=2))
        escribir('perfil_forma.json', json.dumps(_forma_del_perfil(perfil), ensure_ascii=False, indent=2))
        escribir('versiones.json', json.dumps({'programa': __version__, 'librerias': _versiones()}, ensure_ascii=False, indent=2))
        for fichero in sorted(registros.glob('*.log*')) if registros.is_dir() else ():
            try:
                texto = fichero.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            escribir(f'registros/{fichero.name}', '\n'.join(anonimizar(l, terminos) for l in texto.splitlines()) + '\n')
        escribir('LEAME.txt', 'Paquete de soporte de ConverterSmartGrid.\n'
                              'No lleva espacios de trabajo, redes, cargas, demandas ni informes: solo lo que aparece en esta lista.\n'
                              'En los registros, las rutas, los nombres entre comillas y los códigos de red están sustituidos.\n'
                              'Revíselo antes de enviarlo.\n\n' + '\n'.join(contenido) + '\n')
    return ruta
