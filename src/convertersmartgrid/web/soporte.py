"""El paquete de soporte: lo que hace falta para entender un fallo, sin datos del cliente (086:RF-42).

Se arma con una lista cerrada de lo que entra, no quitando de todo lo que hay: un resto olvidado en un espacio de
trabajo no llega al paquete porque nadie lo pone en él. Lleva el informe del doctor, las versiones, la forma del
perfil (sus claves, no sus valores) y los registros, en los que cada línea pasa antes por ``anonimizar``.
"""
from __future__ import annotations

import getpass
import json
import os
import socket
import time
import zipfile
from importlib import metadata
from pathlib import Path
from typing import Any

from .. import __version__, privacidad
from ..perfil_empresa import ruta_perfil_activo
from ..registro_rotativo import carpeta_de_registros
from .doctor import diagnosticar


def _identidad_del_equipo() -> set[str]:
    salida = {socket.gethostname()}
    try:
        salida.add(getpass.getuser())
    except (OSError, KeyError, ImportError):
        pass
    salida |= {os.environ.get(n, '') for n in ('USERNAME', 'USER', 'COMPUTERNAME', 'USERDOMAIN')}
    return {s for s in salida if len(s) >= 3}


#: 112:RF-2: los patrones y la función viven en ``privacidad`` (una vía, P5); soporte los usa tal cual.
anonimizar = privacidad.anonimizar


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


#: Lo que sustituye a un texto libre cuando el perfil no se lee y no se sabe qué nombres tapar.
OMITIDO = '<omitido: perfil ilegible>'


def _informe_anonimo(informe: dict[str, Any], terminos: set[str] | None) -> dict[str, Any]:
    """El diagnóstico con su texto libre tapado; sin términos conocidos (``None``), el texto libre no va."""
    def tapar(v: Any) -> Any:
        return OMITIDO if terminos is None else anonimizar(v, terminos)

    return {**informe, 'comprobaciones': [{k: tapar(v) if k in ('detalle', 'arreglo') else v for k, v in c.items()}
                                          for c in informe['comprobaciones']]}


def crear_paquete(destino: Path, *, carpeta_registros: Path | None = None, ruta_perfil: Path | None = None,
                  informe: dict[str, Any] | None = None, ahora: float | None = None) -> Path:
    """Escribe ``<destino>/csg-soporte-<fecha>.zip`` y devuelve su ruta."""
    momento = time.time() if ahora is None else ahora
    perfil = ruta_perfil_activo() if ruta_perfil is None else ruta_perfil
    registros = carpeta_de_registros() if carpeta_registros is None else carpeta_registros
    # 112:RF-4: con el perfil ilegible no se conocen los nombres de la empresa. El paquete sale igual (sirve justo cuando
    # algo falla), pero sin lo que no se puede tapar: los registros y el texto libre del diagnóstico.
    terminos: set[str] | None
    try:
        terminos, ilegible = privacidad.terminos_del_perfil(perfil) | _identidad_del_equipo(), ''
    except privacidad.PerfilIlegible as exc:
        terminos, ilegible = None, exc.causa
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
        for fichero in sorted(registros.glob('*.log*')) if registros.is_dir() and terminos is not None else ():
            try:
                texto = fichero.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            tapar = terminos or set()               # nunca None aquí: sin términos conocidos, los registros no van
            escribir(f'registros/{fichero.name}', '\n'.join(anonimizar(l, tapar) for l in texto.splitlines()) + '\n')
        escribir('LEAME.txt', 'Paquete de soporte de ConverterSmartGrid.\n'
                              'No lleva espacios de trabajo, redes, cargas, demandas ni informes: solo lo que aparece en esta lista.\n'
                              'En los registros, las rutas, los nombres entre comillas y los códigos de red están sustituidos.\n'
                              'Revíselo antes de enviarlo.\n'
                              + (f'\nEl perfil de la empresa es ilegible ({ilegible}): no se sabe qué nombres tapar, así '
                                 'que no van los registros ni el texto de las comprobaciones del diagnóstico. Arregle el '
                                 'perfil y vuelva a crear el paquete.\n' if terminos is None else '')
                              + '\n' + '\n'.join(contenido) + '\n')
    return ruta
