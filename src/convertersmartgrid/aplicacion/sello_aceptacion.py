"""El sello de una versión aceptada y los espacios de la aceptación (spec 100, RF-18 a RF-24).

Por qué. La matriz estudio × motor (100:RF-9) daba «validado» solo con todas las specs de su evidencia cumplidas, y 18
celdas citan la 100, que no se cumple hasta cerrar a mano su T4. El 26-11 pasaron los casos de la aceptación y la web
siguió en «Sin validar»; el 28-11 el usuario: «cada que valide se debe cerrar, se debe validar en la web». Ahora la
aceptación deja un sello duradero de la versión aceptada en la carpeta de datos del programa, y la web, al servir la
matriz, lo lee para la versión que corre ella: un sello de otra versión no vale.

En la misma carpeta queda la lista de los espacios de la web que usan los casos de la aceptación (RF-24). El 28-11 el
ciclo automático de aprendizaje eligió uno de ellos porque fue el del último trabajo de la web (050:RF-37, RF-49).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..dominio.util import write_json_atomic

#: ``CSG_ACEPTACION_DATA`` o ``_aceptacion`` junto a los espacios de la web, como los demás componentes.
VARIABLE_DATOS = 'CSG_ACEPTACION_DATA'
CARPETA = '_aceptacion'
ESQUEMA_SELLO = 'convertersmartgrid-sello-aceptacion-v1'
ESPACIOS = 'espacios.json'
#: Las variables de la matriz con el espacio de cada fuente (``config/aceptacion/matriz.json``).
_VARIABLE_ESPACIO = re.compile(r'CSG_ACEPTACION_[A-Z0-9]+_ESPACIO')
_HEX = re.compile(r'[0-9a-f]{7,40}')


class SelloInvalido(ValueError):
    """100:RF-20: el informe no da la versión por aceptada; dice qué casos lo impiden."""


def carpeta_aceptacion(programa: Path | None = None) -> Path:
    """Dónde viven los sellos y los espacios de la aceptación: los datos del programa, no el código (065:RF-10)."""
    env = os.environ.get(VARIABLE_DATOS, '').strip()
    if env:
        return Path(env)
    from ..dominio.runtime_paths import raiz_datos_web

    return raiz_datos_web(programa) / CARPETA


def _git(repo: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def version_en_uso(raiz: Path) -> str:
    """100:RF-21: la versión que corre: la revisión (40 cifras) del árbol en desarrollo; en el programa instalado, que
    no trae git, la versión de su paquete, la misma que dice ``/api/sistema/version``."""
    if (Path(raiz) / '.git').exists():
        revision = _git(Path(raiz), 'rev-parse', 'HEAD')
        if revision and re.fullmatch(r'[0-9a-f]{40}', revision):
            return revision
    from .. import __version__

    return __version__


def resolver_version(version: str, repo: Path) -> str:
    """La revisión completa de ``version`` si es un commit de ``repo``; si no (el programa instalado), tal cual."""
    completa = _git(Path(repo), 'rev-parse', '--verify', '--quiet', f'{version}^{{commit}}')
    return completa if completa and re.fullmatch(r'[0-9a-f]{40}', completa) else str(version)


def motivos_del_informe(informe: Mapping[str, Any], casos: Sequence[str]) -> list[str]:
    """100:RF-7, RF-20: lo que impide dar la versión del informe por aceptada; vacío si todos los casos de la matriz
    están aceptados sobre la misma revisión del informe. Se recalcula: el veredicto escrito no basta."""
    version = informe.get('version')
    if not version:
        return ['el informe no dice su versión']
    hechos = informe.get('casos') or {}
    motivos = []
    for c in casos:
        r = hechos.get(c)
        if not isinstance(r, Mapping):
            motivos.append(f'{c}: sin correr')
        elif r.get('revision') != version:
            motivos.append(f'{c}: aceptado sobre otra revisión ({str(r.get("revision"))[:12]})')
        elif r.get('estado') != 'aceptado':
            motivos.append(f'{c}: {r.get("estado")}: {r.get("causa") or ""}'.rstrip(': '))
    return motivos


def sellar(informe: Mapping[str, Any], casos: Sequence[str], *, repo: Path, carpeta: Path | None = None,
           origen: str | None = None) -> Path:
    """100:RF-18, RF-19, RF-20: el sello de la versión del informe, escrito de una vez; ``SelloInvalido`` si algún caso
    de la matriz no está aceptado sobre esa misma revisión, y entonces no se escribe nada."""
    motivos = motivos_del_informe(informe, casos)
    if motivos:
        raise SelloInvalido('la versión no está aceptada: ' + '; '.join(motivos))
    from .. import __version__

    version = resolver_version(str(informe['version']), repo)
    hechos = informe['casos']
    sello = {
        'esquema': ESQUEMA_SELLO,
        'veredicto': 'aceptada',
        'version': version,
        'version_pedida': str(informe['version']),
        'version_programa': __version__,
        'arbol': informe.get('arbol'),
        'fecha': informe.get('fin') or datetime.now(UTC).isoformat(timespec='seconds'),
        'sellado': datetime.now(UTC).isoformat(timespec='seconds'),
        'informe': origen,
        'casos': {c: {k: hechos[c].get(k) for k in ('estado', 'revision', 'fin', 'fuente', 'alcance')} for c in casos},
    }
    carpeta = Path(carpeta) if carpeta is not None else carpeta_aceptacion(repo)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f'sello_{re.sub(r"[^0-9A-Za-z._-]", "_", version)}.json'
    write_json_atomic(ruta, sello)
    return ruta


def _coincide(sello_version: str, version: str) -> bool:
    if sello_version == version:
        return True
    # Una revisión abreviada que git no pudo completar al sellar vale solo si es prefijo de la que corre.
    return bool(_HEX.fullmatch(sello_version) and re.fullmatch(r'[0-9a-f]{40}', version)
                and version.startswith(sello_version))


def sello_vigente(version: str, carpeta: Path | None = None) -> dict[str, Any] | None:
    """100:RF-21, RF-22: el sello aceptado de esa versión, o None; uno ilegible o de otra versión no cuenta."""
    carpeta = Path(carpeta) if carpeta is not None else carpeta_aceptacion()
    if not version or not carpeta.is_dir():
        return None
    validos = []
    for ruta in carpeta.glob('sello_*.json'):
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if (isinstance(datos, dict) and datos.get('esquema') == ESQUEMA_SELLO and datos.get('veredicto') == 'aceptada'
                and _coincide(str(datos.get('version') or ''), version)):
            validos.append(datos)
    return max(validos, key=lambda d: str(d.get('fecha') or '')) if validos else None


def registrar_espacios(espacios: Iterable[str], carpeta: Path | None = None) -> Path:
    """100:RF-24: añade a la lista los espacios de la web que usa la aceptación, sin quitar los que ya estaban."""
    carpeta = Path(carpeta) if carpeta is not None else carpeta_aceptacion()
    ruta = carpeta / ESPACIOS
    previos = set(espacios_registrados(carpeta))
    nuevos = previos | {str(e).strip() for e in espacios if str(e).strip()}
    if nuevos != previos or not ruta.is_file():
        carpeta.mkdir(parents=True, exist_ok=True)
        write_json_atomic(ruta, {'espacios': sorted(nuevos)})
    return ruta


def espacios_registrados(carpeta: Path | None = None) -> list[str]:
    carpeta = Path(carpeta) if carpeta is not None else carpeta_aceptacion()
    try:
        datos = json.loads((carpeta / ESPACIOS).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    lista = datos.get('espacios') if isinstance(datos, dict) else None
    return [str(e) for e in lista if isinstance(e, str)] if isinstance(lista, list) else []


def espacios_de_aceptacion(carpeta: Path | None = None, environ: Mapping[str, str] | None = None) -> set[str]:
    """050:RF-49, 100:RF-24: los espacios de la aceptación: los anotados por ella y los de sus variables, si la web
    las tiene en su entorno (``CSG_ACEPTACION_<FUENTE>_ESPACIO``)."""
    env = os.environ if environ is None else environ
    de_variables = {str(v).strip() for k, v in env.items() if _VARIABLE_ESPACIO.fullmatch(k) and str(v).strip()}
    return set(espacios_registrados(carpeta)) | de_variables
