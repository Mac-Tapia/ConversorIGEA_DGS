"""El entorno debe ser Python 3.12, y el límite superior importa tanto como el inferior.

Por qué existe esta prueba. `powerfactory.pyd` de PowerFactory 2024 es una extensión
binaria compilada contra CPython 3.12: no carga en 3.11 ni en 3.13, y cuando falla lo
hace con «DLL load failed while importing powerfactory», un mensaje que no menciona la
versión de Python y manda a cualquiera a buscar un problema de DLL que no existe.

Este repositorio llegó a tener tres Python en juego a la vez: un `.venv` propio en
3.14 —incapaz de hablar con DIgSILENT—, un intérprete 3.11 heredado de otro proyecto
que era el que resolvía `python` en el intérprete de órdenes, y el 3.12 que la API pide.
De ahí venía toda la maquinaria de buscar un intérprete compatible y lanzar subprocesos.

Con el entorno fijado en 3.12 esa maquinaria sigue existiendo —hace falta en máquinas
donde el conversor y PowerFactory no comparten intérprete—, pero aquí resuelve al propio
proceso y deja de ser un punto de fallo.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

#: Versión exacta que exige la API de PowerFactory 2024.
VERSION_PF = (3, 12)


def test_el_interprete_que_corre_las_pruebas_es_312():
    assert sys.version_info[:2] == VERSION_PF, (
        f'Las pruebas corren en {sys.version_info.major}.{sys.version_info.minor}. '
        'Este proyecto se fija en 3.12 porque es la versión contra la que está '
        'compilado powerfactory.pyd de PowerFactory 2024.\n'
        'Recree el entorno:  py -3.12 -m venv .venv'
    )


def test_pyproject_fija_312_por_arriba_y_por_abajo():
    """Un «>=3.12» abierto deja instalar 3.14, que no carga la API."""
    datos = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    requiere = datos['project']['requires-python']
    assert '>=3.12' in requiere, requiere
    assert '<3.13' in requiere, (
        f'requires-python = {requiere!r} no tiene tope superior. PowerFactory 2024 no '
        'carga en 3.13 ni en 3.14, así que el tope es parte de la restricción real.'
    )


def test_hay_un_python_version_con_312():
    fichero = RAIZ / '.python-version'
    assert fichero.is_file(), 'falta .python-version en la raíz'
    assert fichero.read_text(encoding='utf-8').strip() == '3.12'


def test_el_venv_del_proyecto_es_312_si_existe():
    """Si hay un .venv en la raíz, debe ser el correcto, no uno olvidado."""
    cfg = RAIZ / '.venv' / 'pyvenv.cfg'
    if not cfg.is_file():
        pytest.skip('no hay .venv en la raíz del proyecto')
    version = ''
    for linea in cfg.read_text(encoding='utf-8').splitlines():
        if linea.strip().startswith('version'):
            version = linea.split('=', 1)[1].strip()
            break
    assert version.startswith('3.12'), (
        f'.venv es Python {version}. Con esa versión el conversor no puede importar '
        'powerfactory. Recréelo con:  py -3.12 -m venv .venv'
    )


def test_la_api_de_powerfactory_es_alcanzable_desde_este_interprete():
    """No comprueba que PowerFactory esté abierto, solo que la extensión cargaría."""
    carpeta = Path(r'C:\Program Files\DIgSILENT')
    if not carpeta.is_dir():
        pytest.skip('PowerFactory no está instalado en esta máquina')
    pyd = list(carpeta.glob('PowerFactory */Python/3.*/powerfactory.pyd'))
    if not pyd:
        pytest.skip('no se encontró powerfactory.pyd')
    # La carpeta que contiene la extensión nombra la versión que exige.
    versiones = {p.parent.name for p in pyd}
    actual = f'{sys.version_info.major}.{sys.version_info.minor}'
    assert actual in versiones, (
        f'PowerFactory trae la API para {sorted(versiones)} y este intérprete es '
        f'{actual}. No podrán hablarse en el mismo proceso.'
    )


def test_la_eleccion_de_carpeta_ordena_por_numero_y_no_por_texto():
    """«3.9» ordena después de «3.12» como texto; ese fallo elegía la carpeta mala."""
    from igea_dgs.powerfactory_env import version_key

    carpetas = [Path(n) for n in ('3.8', '3.9', '3.10', '3.11', '3.12')]
    mayor = max(carpetas, key=version_key)
    assert mayor.name == '3.12', (
        f'la carpeta elegida sería {mayor.name}; ordenar como texto da «3.9»'
    )
