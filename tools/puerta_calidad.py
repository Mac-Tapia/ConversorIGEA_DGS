"""Puerta de calidad del repositorio (spec 102): ningún commit ni subida con la suite en rojo.

El 2026-11-08 dos commits entraron en ``main`` con tres pruebas en rojo porque nada corría la suite: no había CI y los
ganchos solo regeneraban el catálogo de la arquitectura. Esta herramienta la corren los ganchos y GitHub Actions.

Uso:
    python tools/puerta_calidad.py --commit      # gancho pre-commit: gobierno y las pruebas del commit
    python tools/puerta_calidad.py --push        # gancho pre-push: suite completa, sin fallidas ni omitidas
    python tools/puerta_calidad.py --ci          # GitHub Actions: suite sintética
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# 106:RF-11: la puerta importa el código del árbol que juzga. Con el .venv del árbol principal, su paquete instalado
# apunta al src del principal: en un worktree, la puerta de la 106 (2026-11-12) importó trabajadores_ml del principal y
# cayó con ImportError; peor aún, podía juzgar la rama con funciones de otro árbol.
if str(RAIZ / 'src') not in sys.path:
    sys.path.insert(0, str(RAIZ / 'src'))

#: Las pruebas de gobierno: inventario, trazabilidad y estado de las specs, auditoría de raíz (102:RF-1).
GOBIERNO = ('tests/test_inventario.py', 'tests/test_trazabilidad_specs.py', 'tests/test_auditoria_raiz.py',
            'tests/test_trazabilidad_candidato.py',
            # 102:RF-21: los procedimientos citan líneas de src/; un cambio en services.py las movió y solo lo vio
            # GitHub Actions (2026-11-11), porque ninguna prueba del commit los leía.
            'tests/test_procedimientos.py')

#: Las variables de datos reales de la suite completa (CLAUDE.md, «Pruebas»): sin una, la suite omite pruebas.
#: 102:RF-23: la puerta pasa solo las de esta lista; ``CSG_PF_PYTHON_39`` (spec 103) estaba en el fichero local y no
#: aquí, y la suite de la T31 de la 086 (2026-11-12) habría omitido las dos pruebas del Python 3.9.
VARIABLES = ('CSG_RED', 'CSG_LOADS', 'CSG_EQUIPMENT', 'CSG_MDB', 'CSG_EQUIPMENT_MDB', 'CSG_DEMANDA_DIR',
             'CSG_VNR_BAK', 'CSG_SOLICITUD_PDF', 'CSG_SOLICITUD_DIR', 'CSG_EVIDENCIA_NATIVA', 'CSG_MCP_PYTHON',
             'CSG_PF_PYTHON_39')

#: 106:RF-13: lo que cambia lo que ven todas las pruebas: con uno de estos, la puerta del commit corre la suite entera.
DE_TODA_LA_SUITE = ('tests/conftest.py', 'pyproject.toml')

#: El fichero local de las variables, fuera de git (102:RF-6, RF-15).
FICHERO_VARIABLES = Path('config') / 'suite_completa.json'

_CERO = '0' * 40


class PuertaError(Exception):
    """La puerta no puede juzgar: falta una variable, una ruta o el resultado de pytest."""


def pruebas_del_commit(ficheros: Iterable[str], raiz: Path = RAIZ) -> list[str]:
    """Las pruebas que corre el commit (102:RF-1, RF-2, RF-4), sin repetir y en orden estable.

    Las de gobierno siempre; además, los ficheros de prueba del commit y las pruebas que nombran un módulo de ``src/``
    o una herramienta de ``tools/`` del commit.
    """
    ficheros = [f.replace('\\', '/') for f in ficheros]
    # Sin carpeta de pruebas (el repositorio de las pruebas de los ganchos, 102:RF-16) no hay suite que correr.
    if any(f in DE_TODA_LA_SUITE for f in ficheros) and (raiz / 'tests').is_dir():
        # 106:RF-13: el conftest de la 106 cambió lo que ven todas las pruebas y la puerta corrió solo 16 ficheros.
        return ['tests']
    elegidas = [g for g in GOBIERNO if (raiz / g).is_file()]
    nombres = set()
    for f in ficheros:
        ruta = Path(f)
        if f.startswith('tests/') and ruta.name.startswith('test_') and ruta.suffix == '.py' and (raiz / f).is_file():
            elegidas.append(f)
        elif f.startswith(('src/', 'tools/')) and ruta.suffix == '.py' and ruta.stem != '__init__':
            nombres.add(ruta.stem)
        elif f.startswith('tests/') and ruta.suffix == '.py' and ruta.parent.as_posix() == 'tests':
            # 106:RF-13: un ayudante de pruebas (apoyo, fake_pf…) elige las pruebas que lo nombran.
            nombres.add(ruta.stem)
    if nombres:
        patron = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, nombres))) + r')\b')
        for prueba in sorted((raiz / 'tests').glob('test_*.py')):
            try:
                if patron.search(prueba.read_text(encoding='utf-8', errors='replace')):
                    elegidas.append(prueba.relative_to(raiz).as_posix())
            except OSError:
                continue
    return list(dict.fromkeys(elegidas))


def variables_de_la_suite(raiz: Path = RAIZ, entorno: Mapping[str, str] | None = None) -> dict[str, str]:
    """Las variables de datos reales del fichero local y del entorno, con cada ruta comprobada (102:RF-6, RF-7).

    Lo que diga el entorno vale sobre el fichero. Falta una o su ruta no existe: :class:`PuertaError` con su nombre.
    """
    entorno = os.environ if entorno is None else entorno
    fichero = raiz / FICHERO_VARIABLES
    leidas: dict[str, str] = {}
    if fichero.is_file():
        try:
            datos = json.loads(fichero.read_text(encoding='utf-8'))
        except ValueError as exc:
            raise PuertaError(f'{FICHERO_VARIABLES} no es JSON válido: {exc}') from exc
        leidas.update({k: str(v) for k, v in (datos.get('variables') or {}).items()})
    leidas.update({k: entorno[k] for k in VARIABLES if entorno.get(k)})
    faltan = [k for k in VARIABLES if not leidas.get(k)]
    if faltan:
        raise PuertaError(f"Faltan variables de datos reales: {', '.join(faltan)}. Póngalas en {FICHERO_VARIABLES} "
                          f'(ejemplo en config/suite_completa.example.json) o en el entorno.')
    sin_ruta = [f'{k}={leidas[k]}' for k in VARIABLES if not Path(leidas[k]).exists()]
    if sin_ruta:
        raise PuertaError('Rutas que no existen: ' + '; '.join(sin_ruta))
    return {k: leidas[k] for k in VARIABLES}


def veredicto(junit: Path) -> dict:
    """Fallidas y omitidas del XML de JUnit de pytest, cada una con su motivo (102:RF-8, RF-9)."""
    try:
        arbol = ET.parse(junit)
    except (OSError, ET.ParseError) as exc:
        raise PuertaError(f'pytest no dejó su resultado ({junit.name}): {exc}') from exc
    fallidas, omitidas, total = [], [], 0
    for caso in arbol.iter('testcase'):
        total += 1
        nombre = f"{caso.get('classname', '')}::{caso.get('name', '')}"
        for etiqueta, lista in (('failure', fallidas), ('error', fallidas), ('skipped', omitidas)):
            nodo = caso.find(etiqueta)
            if nodo is not None:
                motivo = (nodo.get('message') or (nodo.text or '')).strip().splitlines()
                lista.append({'prueba': nombre, 'motivo': motivo[0][:300] if motivo else ''})
                break
    return {'total': total, 'fallidas': fallidas, 'omitidas': omitidas}


def _git(*args: str, raiz: Path = RAIZ) -> str:
    return subprocess.run(['git', *args], cwd=raiz, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', check=True).stdout


def _carpeta_resultados(raiz: Path) -> Path:
    comun = Path(_git('rev-parse', '--git-common-dir', raiz=raiz).strip())
    return (comun if comun.is_absolute() else raiz / comun) / 'puerta_calidad'


def arbol_limpio(raiz: Path = RAIZ) -> bool:
    """Sin cambios en lo versionado ni ficheros nuevos de código, pruebas o specs: lo probado es la revisión."""
    for linea in _git('status', '--porcelain', raiz=raiz).splitlines():
        ruta = linea[3:].strip().strip('"')
        if not linea.startswith('??') or ruta.startswith(('src/', 'tools/', 'tests/', 'specs/', 'config/')):
            return False
    return True


def resultado_guardado(revision: str, raiz: Path = RAIZ) -> dict | None:
    """El resultado aprobado de una revisión (102:RF-11), o ``None``."""
    ruta = _carpeta_resultados(raiz) / f'{revision}.json'
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return datos if datos.get('aprobada') else None


def guardar_resultado(revision: str, juicio: dict, raiz: Path = RAIZ) -> Path:
    """El resultado de la suite completa con la revisión que se probó (102:RF-10)."""
    carpeta = _carpeta_resultados(raiz)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f'{revision}.json'
    datos = {'revision': revision, 'fecha': datetime.now().isoformat(timespec='seconds'),
             'aprobada': not juicio['fallidas'] and not juicio['omitidas'], **juicio}
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return ruta


def _pytest(argumentos: list[str], entorno: Mapping[str, str], raiz: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / 'junit.xml'
        cmd = [sys.executable, '-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', f'--junitxml={junit}',
               *argumentos]
        # 102:RF-19: sin las variables que git pone al gancho (GIT_INDEX_FILE, GIT_DIR…): heredadas, el «git worktree add»
        # de las pruebas del asistente usaba el índice de este repositorio y fallaba solo dentro de la puerta (2026-11-11).
        limpio = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        rc = subprocess.run(cmd, cwd=raiz, env={**limpio, **entorno}).returncode
        from convertersmartgrid.trabajadores_ml import SALIDA_SIN_TURNO_GPU, quien_tiene_la_gpu

        if rc == SALIDA_SIN_TURNO_GPU:
            # 106:RF-8: sin el turno de GPU no hay veredicto, y eso es un fallo con su dueño, nunca «0 fallidas».
            from convertersmartgrid.training_coordinator import ruta_guardia_gpu

            dueno = quien_tiene_la_gpu(ruta_guardia_gpu({**limpio, **entorno}))   # la misma que calculó el conftest
            return {'total': 0, 'omitidas': [],
                    'fallidas': [{'prueba': 'pytest', 'motivo': f'sin el turno de GPU en su plazo: la tiene {dueno} (106:RF-8)'}]}
        if not junit.is_file():
            raise PuertaError(f'pytest terminó con el código {rc} sin dejar resultado.')
        juicio = veredicto(junit)
    if rc not in (0, 1) and not juicio['fallidas']:
        juicio['fallidas'].append({'prueba': 'pytest', 'motivo': f'terminó con el código {rc}'})
    return juicio


def _informar(juicio: dict, *, omitidas_cuentan: bool) -> bool:
    for f in juicio['fallidas']:
        print(f"FALLA {f['prueba']}: {f['motivo']}")
    if omitidas_cuentan:
        for o in juicio['omitidas']:
            print(f"OMITIDA {o['prueba']}: {o['motivo']}")
    malas = len(juicio['fallidas']) + (len(juicio['omitidas']) if omitidas_cuentan else 0)
    print(f"Puerta de calidad: {juicio['total']} pruebas, {len(juicio['fallidas'])} fallidas, "
          f"{len(juicio['omitidas'])} omitidas.")
    return malas == 0


def puerta_commit(raiz: Path = RAIZ) -> int:
    """102:RF-1 a RF-4."""
    ficheros = [f for f in _git('diff', '--cached', '--name-only', '--diff-filter=ACMR', raiz=raiz).splitlines() if f]
    pruebas = pruebas_del_commit(ficheros, raiz)
    print(f'Puerta del commit: {len(pruebas)} ficheros de prueba.')
    if not pruebas:
        # Un repositorio sin pruebas de gobierno (el de las pruebas de los ganchos de la 090): sin pruebas que
        # elegir, pytest correría todo el árbol y saldría con «ninguna prueba» (código 5).
        return 0
    if not _informar(_pytest(pruebas, {}, raiz), omitidas_cuentan=False):
        print('Commit detenido: corrija las pruebas que fallan (102:RF-3).')
        return 1
    return 0


#: La rama que integra: lo que llega a ella pasa la suite completa con los datos reales (102:RF-18).
RAMA_PRINCIPAL = 'main'


def revisiones_por_destino(lineas: Iterable[str]) -> tuple[list[str], list[str]]:
    """102:RF-18: de las líneas del gancho pre-push (``ref_local sha_local ref_remota sha_remota``), las revisiones que
    van a la rama principal y los nombres de las ramas de trabajo.

    El usuario (2026-11-10): «cada vez que voy a hacer un trabajo voy a hacer commit, subir a GitHub y hacer la suite
    completa; eso no sería viable». La suite completa, ~80 min, se corre al integrar en ``main``, no en cada subida.
    """
    a_main, otras = [], []
    for linea in lineas:
        partes = linea.split()
        if len(partes) < 4 or partes[1] == _CERO:      # un borrado de rama no sube código
            continue
        if partes[2] == f'refs/heads/{RAMA_PRINCIPAL}':
            a_main.append(partes[1])
        else:
            otras.append(partes[2].removeprefix('refs/heads/'))
    return a_main, otras


def puerta_push(revisiones: Iterable[str], raiz: Path = RAIZ) -> int:
    """102:RF-5 a RF-11. ``revisiones``: las que se suben (de la entrada del gancho pre-push)."""
    revisiones = [r for r in revisiones if r and r != _CERO]
    if not revisiones:
        return 0
    cabeza = _git('rev-parse', 'HEAD', raiz=raiz).strip()
    otras = [r for r in revisiones if r != cabeza]
    if otras:
        print(f"Subida detenida: se prueba el árbol de HEAD ({cabeza[:8]}) y se sube {', '.join(r[:8] for r in otras)}. "
              'Cambie a esa revisión y vuelva a subir.')
        return 1
    if not arbol_limpio(raiz):
        print('Subida detenida: el árbol tiene cambios sin commit; la suite probaría otra cosa que la revisión.')
        return 1
    if resultado_guardado(cabeza, raiz):
        print(f'Puerta de la subida: {cabeza[:8]} ya pasó la suite completa sin omitidas (102:RF-11).')
        return 0
    try:
        entorno = variables_de_la_suite(raiz)
    except PuertaError as exc:
        print(f'Subida detenida: {exc} (102:RF-7)')
        return 1
    print(f'Puerta de la subida: suite completa de {cabeza[:8]} con los datos reales.')
    juicio = _pytest([], entorno, raiz)
    ruta = guardar_resultado(cabeza, juicio, raiz)
    if not _informar(juicio, omitidas_cuentan=True):
        print(f'Subida detenida: la suite completa no pasa sin fallidas ni omitidas (102:RF-8, RF-9). Detalle: {ruta}')
        return 1
    return 0


def puerta_ci(raiz: Path = RAIZ) -> int:
    """102:RF-12, RF-14: la suite sintética; allí no hay datos reales y sus pruebas se omiten (RF-15)."""
    return 0 if _informar(_pytest([], {}, raiz), omitidas_cuentan=False) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Puerta de calidad del repositorio (spec 102).')
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument('--commit', action='store_true', help='gancho pre-commit: gobierno y las pruebas del commit')
    modo.add_argument('--push', action='store_true', help='gancho pre-push: suite completa sin fallidas ni omitidas; '
                      'lee de la entrada estándar las líneas del gancho')
    modo.add_argument('--ci', action='store_true', help='GitHub Actions: suite sintética')
    args = parser.parse_args(argv)
    try:
        if args.commit:
            return puerta_commit()
        if args.push:
            lineas = [] if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read().splitlines()
            if not lineas:                        # a mano, sin el gancho: la revisión actual, como al integrar
                return puerta_push([_git('rev-parse', 'HEAD').strip()])
            a_main, otras = revisiones_por_destino(lineas)
            for rama in otras:
                print(f'Puerta de la subida: {rama} es una rama de trabajo; sube sin la suite completa, que se exige al '
                      f'integrar en {RAMA_PRINCIPAL} (102:RF-18). GitHub Actions corre la sintética.')
            return puerta_push(a_main) if a_main else 0
        return puerta_ci()
    except PuertaError as exc:
        print(f'Puerta de calidad: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
