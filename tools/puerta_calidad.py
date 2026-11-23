"""Puerta de calidad del repositorio (spec 102): ningún commit ni subida con la suite en rojo.

El 2026-11-08 dos commits entraron en ``main`` con tres pruebas en rojo porque nada corría la suite: no había CI y los
ganchos solo regeneraban el catálogo de la arquitectura. Esta herramienta la corren los ganchos y GitHub Actions.

Uso:
    python tools/puerta_calidad.py --commit      # gancho pre-commit: gobierno y las pruebas del commit
    python tools/puerta_calidad.py --push        # gancho pre-push: suite completa, sin fallidas ni omitidas
    python tools/puerta_calidad.py --ci          # GitHub Actions: suite sintética
    python tools/puerta_calidad.py --arbol       # suite entera del árbol del índice; deja su veredicto (102:RF-11)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
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
#: 106:RF-13: ficheros que cambian en casi todos los commits y que ya juzgan las pruebas de GOBIERNO (la trazabilidad,
#: el inventario y la arquitectura). Por su nombre elegirían una docena de pruebas del asistente que solo los citan
#: como texto de su corpus (medido el 2026-11-13: de 8 a 27 pruebas en bd4cc7d2 y de 41 a 53 en c83a1aab).
NOMBRADOS_POR_EL_GOBIERNO = frozenset({'README.md', 'ARQUITECTURA_CATALOGO.md', 'CODIGO_FUENTE.md', 'CLAUDE.md',
                                       'spec.md', 'plan.md', 'tasks.md'})

GOBIERNO = ('tests/test_inventario.py', 'tests/test_trazabilidad_specs.py', 'tests/test_auditoria_raiz.py',
            'tests/test_trazabilidad_candidato.py',
            # 102:RF-21: los procedimientos citan líneas de src/; un cambio en services.py las movió y solo lo vio
            # GitHub Actions (2026-11-11), porque ninguna prueba del commit los leía.
            'tests/test_procedimientos.py',
            # 106:RF-13: las entradas de docs/regresiones citan pruebas que deben existir (081:RF-47). 2026-11-13: la
            # edición ccb81aa8 quitó cuatro que citaba una entrada y ninguna puerta lo vio, porque el commit no tocaba
            # docs/regresiones ni nada que nombrara test_regresiones.
            'tests/test_regresiones.py',
            # 106:RF-13: lo que mira el árbol entero (capas y ciclos, 002:RF-2/3; ningún nombre anterior, 058) tampoco lo elige
            # el commit que lo rompe. 2026-11-14: cad225d0 dejó un ciclo indice -> evaluacion_rag -> embeddings -> indice y una
            # ruta con el nombre anterior en CLAUDE.md, y 38dc1581 otro ciclo y módulos sin capa; ninguna de sus puertas lo vio.
            'tests/test_capas.py', 'tests/test_dominio_numeros_medidos.py', 'tests/test_nombre_converter_smart_grid.py')

#: Las variables de datos reales de la suite completa (CLAUDE.md, «Pruebas»): sin una, la suite omite pruebas.
#: 102:RF-23: la puerta pasa solo las de esta lista; ``CSG_PF_PYTHON_39`` (spec 103) estaba en el fichero local y no
#: aquí, y la suite de la T31 de la 086 (2026-11-12) habría omitido las dos pruebas del Python 3.9.
VARIABLES = ('CSG_RED', 'CSG_LOADS', 'CSG_EQUIPMENT', 'CSG_MDB', 'CSG_EQUIPMENT_MDB', 'CSG_DEMANDA_DIR',
             'CSG_VNR_BAK', 'CSG_SOLICITUD_PDF', 'CSG_SOLICITUD_DIR', 'CSG_EVIDENCIA_NATIVA', 'CSG_MCP_PYTHON',
             'CSG_PF_PYTHON_39', 'CSG_ASISTENTE_REAL', 'CSG_CATALOGO_PROYECTO',
             'CSG_SICODI', 'CSG_INTERRUPCIONES', 'CSG_TERMINOS_PROHIBIDOS')

#: 106:RF-13: lo que cambia lo que ven todas las pruebas: con uno de estos, la puerta del commit corre la suite entera.
DE_TODA_LA_SUITE = ('tests/conftest.py', 'pyproject.toml')

#: PUERTA-CAPAS (c3 vía 82, 15-11): un pyproject.toml que SOLO cambia las capas (registrar un módulo en
#: [tool.convertersmartgrid.capas.modulos]) no toca lo que ven las pruebas; corre lo elegido por los ficheros, las de
#: gobierno y estas, las estructurales de la pre-puerta del integrador (la lista fija de su prepuerta y los ficheros de
#: las pruebas que tumbaron puertas el 15-11). Se toman solo las que existen en el repositorio.
ESTRUCTURALES_DE_CAPAS = (
    'tests/test_capas.py', 'tests/test_arquitectura_generada.py', 'tests/test_interactive_architecture.py',
    'tests/test_inventario.py', 'tests/test_json_atomico.py', 'tests/test_instalacion_programa.py',
    'tests/test_entrega_universal.py', 'tests/test_trazabilidad_specs.py', 'tests/test_contrato_api.py',
    'tests/test_pf_servidor.py', 'tests/test_pf_arnes_sin_atajos.py', 'tests/test_flexibility_and_scale.py',
    'tests/test_asistente_textos_del_plan.py', 'tests/test_pit_registro.py', 'tests/test_vad_costos.py',
    'tests/test_vad_tablas_resultados.py')


def _tabla_de_capas(datos: dict) -> tuple[dict, object]:
    """El pyproject sin la tabla de capas, y la tabla de capas (con sus subtablas)."""
    import copy

    resto = copy.deepcopy(datos)
    propia = resto.get('tool', {}).get('convertersmartgrid', {})
    capas = propia.pop('capas', None) if isinstance(propia, dict) else None
    return resto, capas


def pyproject_cambia_solo_capas(raiz: Path = RAIZ) -> bool:
    """True si pyproject.toml del índice difiere del de HEAD SOLO en [tool.convertersmartgrid.capas*]. Ante cualquier
    duda (sin git, sin HEAD, TOML ilegible, ningún cambio o un cambio fuera de las capas) es False: la suite entera."""
    import tomllib

    def version(ref: str) -> dict:
        salida = subprocess.run(['git', 'show', f'{ref}pyproject.toml'], cwd=raiz, capture_output=True, check=True)
        return tomllib.loads(salida.stdout.decode('utf-8'))

    try:
        antes, despues = version('HEAD:'), version(':')
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    resto_antes, capas_antes = _tabla_de_capas(antes)
    resto_despues, capas_despues = _tabla_de_capas(despues)
    return resto_antes == resto_despues and capas_antes != capas_despues


#: 077:RF-76: lo que cambia el servidor MCP. Un commit con uno de estos corre su prueba real con su intérprete y no la
#: tolera omitida: hasta el 2026-11-14 la puerta del commit corría sin ``CSG_MCP_PYTHON`` y la omitía callada.
DEL_MCP = ('tools/mcp_conversor.py', 'requirements-mcp.txt', 'tests/test_mcp_conversor.py', 'docs/MCP_CONVERSOR.md',
           'src/convertersmartgrid/aplicacion/asistente/lectura_proyecto.py')
#: 077:RF-76: las pruebas del servidor MCP real. Sin ellas aprobadas, la suite de ``main``, la que precede a la etiqueta, no
#: se da por buena, aunque nadie las elija o se omitan.
MCP_REAL = ('tests.test_mcp_conversor::test_servidor_real_por_stdio',
            'tests.test_mcp_conversor::test_servidor_real_y_sus_datos_locales')
#: 077:RF-76: el intérprete propio del MCP, si no se indica otro (docs/MCP_CONVERSOR.md).
VENV_MCP = ('.venv_mcp/Scripts/python.exe', '.venv_mcp/bin/python')

#: 106:RF-15: cuántas de las más lentas guarda el resultado, y el umbral de ``faulthandler_timeout`` de pyproject.toml.
LENTAS_GUARDADAS = 30
UMBRAL_PRUEBA_LENTA_S = 1800.0

#: El fichero local de las variables, fuera de git (102:RF-6, RF-15).
FICHERO_VARIABLES = Path('config') / 'suite_completa.json'

#: 102:RF-11 (aclaración del 2026-11-15, PUERTA-ESPECULATIVA): el veredicto de un ÁRBOL (``git write-tree``), que deja
#: ``--arbol`` en ``.git/puerta_calidad/arbol_<árbol>.json``, vale como mucho estas horas. La suite entera tarda ~80 min
#: y el integrador monta y comete el mismo grupo en pocas horas; pasado el tope, los datos, SQL Server o el controlador
#: de la GPU pueden ser otros y se repite. Se cambia con :data:`VARIABLE_HORAS_VEREDICTO`.
HORAS_VEREDICTO_ARBOL = 12.0
VARIABLE_HORAS_VEREDICTO = 'CSG_PUERTA_HORAS_VEREDICTO'
#: La forma del veredicto de árbol: otra forma no se interpreta, se repite la suite.
FORMATO_VEREDICTO_ARBOL = 1
#: 102:RF-11 v2 (condición de 0d, 2026-11-15): las únicas ramas en las que el gancho del commit reutiliza un veredicto
#: de árbol: la rama de trabajo y la del integrador (wt_integra comete en ella y la funde por avance rápido en la de
#: trabajo). En main, en cualquier otra rama o sin rama, nunca: «main exige la completa»; y la subida a main
#: (:func:`puerta_push`) no consulta los veredictos de árbol.
RAMAS_CON_VEREDICTO_DE_ARBOL = ('trabajo/puerta-por-ramas', 'trabajo/integra-capas-suite')

#: 102:RF-5 (aclaración del 2026-11-15, PUERTA-XDIST): la suite entera de la puerta, repartida en N procesos de CPU.
#: Memoria de un proceso de pytest de la suite. PROVISIONAL mientras :data:`MEDIDA_T20` sea ``None``: en los ensayos de
#: la 106:RF-16 del 2026-11-14 con -n 2 y sin datos reales, el mayor pico de un trabajador fue 2,74 GiB (y 5,97 GiB el
#: árbol entero). La T20 lo fija con el pico medido de la suite entera (``tools/comparar_suite_repartida.py --fijar``).
#: Se cambia con VARIABLE_GIB_POR_PROCESO.
GIB_POR_PROCESO = 3.0
VARIABLE_GIB_POR_PROCESO = 'CSG_PUERTA_GIB_POR_PROCESO'
#: Lo que se deja libre al equipo: las reglas de recursos piden ≥ 2 GiB libres al lanzar (y 0d, ≥ 1,5 GiB en el pico).
RESERVA_GIB = 2.0
#: Tope de procesos. UNO mientras :data:`MEDIDA_T20` sea ``None`` (auditoría de c2, 2026-11-16: sin medida, hay pruebas
#: que caían con -n 2): todas las puertas corren la suite en una sola sesión, como antes. La T20 de la spec 102 compara
#: la suite entera con -n 1, 2 y 3 sobre el mismo árbol y, solo si da «iguales», ``comparar_suite_repartida.py --fijar``
#: escribe aquí el N medido, su GIB_POR_PROCESO y su medida. Para ensayar 2 o 3 procesos, VARIABLE_PROCESOS; la memoria
#: y las CPU lo siguen limitando.
PROCESOS_MAXIMOS = 1
#: 102 T20: la medida con la que se fijaron PROCESOS_MAXIMOS y GIB_POR_PROCESO (el árbol, las N comparadas, los picos y
#: el informe), o ``None`` si aún no se midió. Lo escribe ``tools/comparar_suite_repartida.py --fijar``; una prueba
#: comprueba que el tope y la memoria por proceso son los de esta medida (lección A7: ningún cambio sin su medida).
MEDIDA_T20 = None
VARIABLE_PROCESOS = 'CSG_PUERTA_PROCESOS'
#: Las tres partes de la suite repartida (marcas de tests/conftest.py, ``EN_SERIE``, y la ``gpu`` de 106:RF-6): «serie»,
#: una sesión sola con lo que no admite paralelo, a la vez que «reparto», con xdist; después, «a_solas», sin nada más.
#: Las tres juntas son la suite entera: toda prueba cae en una y solo una.
SELECCION_SERIE = '(gpu or serie) and not a_solas'
SELECCION_REPARTO = 'not gpu and not serie and not a_solas'
SELECCION_A_SOLAS = 'a_solas'
#: Código de pytest sin pruebas que elegir: en una parte de la suite repartida no es un fallo (el junit lo confirma).
_SIN_PRUEBAS = 5


def _hay_xdist() -> bool:
    import importlib.util

    return importlib.util.find_spec('xdist') is not None


def _memoria_libre_gib() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    return psutil.virtual_memory().available / 2**30


def procesos_de_la_suite(entorno: Mapping[str, str] | None = None) -> tuple[int, str]:
    """102:RF-5 (PUERTA-XDIST): cuántos procesos usa la suite entera, y por qué. Sale de la memoria libre medida al
    arrancar, menos :data:`RESERVA_GIB`, entre :data:`GIB_POR_PROCESO`, con el tope de procesos y el de CPU. Sin
    pytest-xdist, sin psutil o con poca memoria: 1, la suite en una sola sesión, como siempre."""
    entorno = os.environ if entorno is None else entorno
    if not _hay_xdist():
        return 1, 'pytest-xdist no está instalado: la suite entera en una sola sesión (N=1)'
    libre = _memoria_libre_gib()
    if libre is None:
        return 1, 'sin psutil no se mide la memoria libre: la suite entera en una sola sesión (N=1)'
    try:
        por_proceso = float(entorno.get(VARIABLE_GIB_POR_PROCESO) or GIB_POR_PROCESO)
        tope = int(entorno.get(VARIABLE_PROCESOS) or PROCESOS_MAXIMOS)
    except ValueError:
        return 1, f'{VARIABLE_GIB_POR_PROCESO} o {VARIABLE_PROCESOS} no es un número: una sola sesión (N=1)'
    cpus = os.cpu_count() or 1
    por_memoria = int((libre - RESERVA_GIB) // por_proceso) if por_proceso > 0 else 1
    n = max(1, min(tope, por_memoria, cpus))
    return n, (f'{libre:.1f} GiB libres, {por_proceso:g} GiB por proceso y {RESERVA_GIB:g} GiB de reserva, tope {tope} '
               f'y {cpus} CPU: N={n}')
#: El lock de las dependencias del núcleo; su sha256 va en la firma del entorno del veredicto.
LOCK_DE_DEPENDENCIAS = 'requirements-nucleo.lock'

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
        # PUERTA-CAPAS: si lo único común que cambia es la tabla de capas de pyproject, no hace falta la suite.
        if 'tests/conftest.py' not in ficheros and pyproject_cambia_solo_capas(raiz):
            propias = pruebas_del_commit([f for f in ficheros if f != 'pyproject.toml'], raiz)
            extra = [e for e in ESTRUCTURALES_DE_CAPAS if (raiz / e).is_file()]
            return list(dict.fromkeys(propias + extra))
        # 106:RF-13: el conftest de la 106 cambió lo que ven todas las pruebas y la puerta corrió solo 16 ficheros.
        return ['tests']
    elegidas = [g for g in GOBIERNO if (raiz / g).is_file()]
    nombres = set()
    ficheros_nombrados: set[str] = set()
    for f in ficheros:
        ruta = Path(f)
        if f.startswith('tests/') and ruta.name.startswith('test_') and ruta.suffix == '.py' and (raiz / f).is_file():
            elegidas.append(f)
        elif f.startswith(('src/', 'tools/')) and ruta.suffix == '.py' and ruta.stem != '__init__':
            nombres.add(ruta.stem)
        elif f.startswith('tests/') and ruta.suffix == '.py' and ruta.parent.as_posix() == 'tests':
            # 106:RF-13: un ayudante de pruebas (apoyo, fake_pf…) elige las pruebas que lo nombran.
            nombres.add(ruta.stem)
        elif ruta.suffix != '.py' and ruta.name not in NOMBRADOS_POR_EL_GOBIERNO:
            # 106:RF-13: un fichero que no es un módulo de Python (el .iss del instalador, un .json, un .ts…) elige las
            # pruebas que nombran su fichero. 2026-11-13: un commit cambió el .iss y su puerta no eligió
            # test_instalador_qa, que lo lee; la regresión entró y la rama quedó en rojo.
            ficheros_nombrados.add(ruta.name)
    partes = [r'\b' + re.escape(n) + r'\b' for n in sorted(nombres)]
    partes += [r'(?<![\w.-])' + re.escape(n) + r'(?![\w-])' for n in sorted(ficheros_nombrados)]
    if partes:
        patron = re.compile('|'.join(partes))
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


def veredicto(junit: Path, exigidas: Iterable[str] = ()) -> dict:
    """Fallidas y omitidas del XML de JUnit de pytest, cada una con su motivo (102:RF-8, RF-9).

    077:RF-76: ``exigidas`` son pruebas que tienen que haber corrido y pasado (o cada caso de su parametrización); las
    que no, van a ``exigidas_sin_correr``.
    """
    try:
        arbol = ET.parse(junit)
    except (OSError, ET.ParseError) as exc:
        raise PuertaError(f'pytest no dejó su resultado ({junit.name}): {exc}') from exc
    fallidas, omitidas, total, tiempos = [], [], 0, []
    aprobadas: dict[str, bool] = {}
    for caso in arbol.iter('testcase'):
        total += 1
        nombre = f"{caso.get('classname', '')}::{caso.get('name', '')}"
        base = nombre.split('[', 1)[0]
        aprobadas[base] = aprobadas.get(base, True) and not any(caso.find(e) is not None
                                                                 for e in ('failure', 'error', 'skipped'))
        try:
            tiempos.append((float(caso.get('time') or 0), nombre))
        except ValueError:
            pass
        for etiqueta, lista in (('failure', fallidas), ('error', fallidas), ('skipped', omitidas)):
            nodo = caso.find(etiqueta)
            if nodo is not None:
                motivo = (nodo.get('message') or (nodo.text or '')).strip().splitlines()
                lista.append({'prueba': nombre, 'motivo': motivo[0][:300] if motivo else ''})
                break
    # 106:RF-15: las más lentas quedan en el resultado guardado; el junit se borra con su temporal y la suite de
    # 10a80812 (2026-11-12) se quedó sin tiempos que mirar.
    tiempos.sort(key=lambda x: (-x[0], x[1]))
    lentas = [{'prueba': p, 'segundos': round(s, 1)} for s, p in tiempos[:LENTAS_GUARDADAS]]
    return {'total': total, 'fallidas': fallidas, 'omitidas': omitidas, 'lentas': lentas,
            'mas_de_umbral': [x for x in lentas if x['segundos'] > UMBRAL_PRUEBA_LENTA_S],
            'exigidas_sin_correr': [e for e in exigidas if not aprobadas.get(e)]}


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
             'aprobada': not juicio['fallidas'] and not juicio['omitidas'] and not juicio.get('exigidas_sin_correr'),
             **juicio}
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return ruta


# ----------------------------------------------------------------- 102:RF-11: el veredicto de un árbol (especulativa)

def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with Path(ruta).open('rb') as f:
        for bloque in iter(lambda: f.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def _variables_del_fichero(raiz: Path) -> dict[str, str]:
    """Todas las variables del fichero local (las de la puerta y las que añade la máquina, como las de los carriles), con
    el entorno por encima; ``{}`` si no hay fichero o no se lee."""
    try:
        datos = json.loads((raiz / FICHERO_VARIABLES).read_text(encoding='utf-8'))
        leidas = {k: str(v) for k, v in (datos.get('variables') or {}).items() if v not in (None, '')}
    except (OSError, ValueError, AttributeError):
        return {}
    return {k: os.environ.get(k) or v for k, v in leidas.items()}


def _entorno_de_pytest(entorno: Mapping[str, str]) -> dict[str, str]:
    """El entorno que recibe pytest: el del proceso sin las ``GIT_*`` del gancho (102:RF-19) y, encima, ``entorno``."""
    return {**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')}, **entorno}


def variables_de_la_firma(raiz: Path, entorno_pytest: Mapping[str, str]) -> dict[str, str]:
    """Las variables de datos reales que ve la suite: las de la puerta (:data:`VARIABLES`) y las del fichero local, con
    el valor que les llega a pytest. Un veredicto solo vale con exactamente las mismas, nombre y valor."""
    nombres = set(VARIABLES) | set(_variables_del_fichero(raiz))
    return {k: str(entorno_pytest[k]) for k in sorted(nombres) if entorno_pytest.get(k)}


def entorno_de_la_firma(raiz: Path) -> dict[str, str]:
    """La versión del entorno: el Python, el sha256 del lock de dependencias y el de los paquetes instalados (nombre y
    versión), que es lo que de verdad importa la suite."""
    from importlib import metadata

    lock = raiz / LOCK_DE_DEPENDENCIAS
    paquetes = sorted({f"{(d.metadata.get('Name') or '').lower()}=={d.version}" for d in metadata.distributions()})
    return {'python': f'{platform.python_implementation()} {platform.python_version()}',
            'lock': _sha256(lock) if lock.is_file() else '',
            'paquetes': hashlib.sha256('\n'.join(paquetes).encode('utf-8')).hexdigest()}


def firma_de_la_puerta() -> str:
    """El sha256 de esta herramienta, la que juzga: otra versión de la puerta no reutiliza el veredicto."""
    return _sha256(Path(__file__))


def arbol_del_indice(raiz: Path = RAIZ) -> str:
    """El árbol que se cometería (``git write-tree``). En el gancho, git pone GIT_INDEX_FILE: es el índice del commit."""
    return _git('write-tree', raiz=raiz).strip()


def rama_actual(raiz: Path = RAIZ) -> str:
    """La rama de HEAD (la que recibe el commit), o '' sin rama (HEAD separado) o si git no responde."""
    try:
        return _git('symbolic-ref', '--short', '-q', 'HEAD', raiz=raiz).strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def ruta_veredicto_de_arbol(arbol: str, raiz: Path = RAIZ) -> Path:
    return _carpeta_resultados(raiz) / f'arbol_{arbol}.json'


def indice_igual_al_disco(raiz: Path = RAIZ) -> bool:
    """Lo del disco es el índice: nada sin preparar en lo versionado ni ficheros nuevos de código, pruebas o specs."""
    for linea in _git('status', '--porcelain', raiz=raiz).splitlines():
        ruta = linea[3:].strip().strip('"')
        if linea.startswith('??'):
            if ruta.startswith(('src/', 'tools/', 'tests/', 'specs/', 'config/')):
                return False
        elif linea[1:2] != ' ':
            return False
    return True


def _edad_horas(fecha: str, ahora: datetime | None) -> float:
    momento = datetime.fromisoformat(fecha)
    if momento.tzinfo is None:
        momento = momento.astimezone()
    return ((ahora or datetime.now().astimezone()) - momento).total_seconds() / 3600


def veredicto_de_arbol(arbol: str, raiz: Path = RAIZ, entorno_pytest: Mapping[str, str] | None = None,
                       ahora: datetime | None = None) -> tuple[dict | None, str]:
    """102:RF-11: el veredicto del árbol si vale para ESTE gancho, o ``(None, motivo)``. Ante cualquier duda, no vale.

    Vale solo si: es de este árbol y de esta forma; lo dio esta misma puerta (sha256); con las mismas variables, nombre
    y valor; con el mismo Python, lock y paquetes; aprobado, sin fallidas ni omitidas; con fecha y dentro del tope de
    horas; y cada junit existe, cuadra con su sha256 y, releído, da el mismo total sin fallidas ni omitidas.
    """
    ruta = ruta_veredicto_de_arbol(arbol, raiz)
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None, 'no hay veredicto de este árbol'
    except (OSError, ValueError) as exc:
        return None, f'veredicto ilegible: {exc}'
    try:
        if not isinstance(datos, dict) or datos.get('formato') != FORMATO_VEREDICTO_ARBOL:
            return None, 'otra forma de veredicto'
        if datos.get('arbol') != arbol:
            return None, f"es de otro árbol ({str(datos.get('arbol'))[:8]})"
        if datos.get('puerta') != firma_de_la_puerta():
            return None, 'lo dio otra versión de tools/puerta_calidad.py'
        esperadas = variables_de_la_firma(raiz, os.environ if entorno_pytest is None else entorno_pytest)
        guardadas = datos.get('variables') or {}
        faltan = [k for k in VARIABLES if not guardadas.get(k)]
        if faltan:
            return None, f"la suite corrió sin {', '.join(faltan)}"
        if guardadas != esperadas:
            distintas = sorted(k for k in set(guardadas) | set(esperadas) if guardadas.get(k) != esperadas.get(k))
            return None, f"otras variables: {', '.join(distintas)}"
        entorno = entorno_de_la_firma(raiz)
        if datos.get('entorno') != entorno:
            distintas = sorted(k for k in entorno if (datos.get('entorno') or {}).get(k) != entorno[k])
            return None, f"otro entorno: {', '.join(distintas) or 'forma'}"
        if datos.get('aprobada') is not True or datos.get('fallidas') or datos.get('omitidas'):
            return None, (f"la suite no aprobó: {len(datos.get('fallidas') or [])} fallidas, "
                          f"{len(datos.get('omitidas') or [])} omitidas")
        tope = float(os.environ.get(VARIABLE_HORAS_VEREDICTO) or HORAS_VEREDICTO_ARBOL)
        edad = _edad_horas(datos['fecha'], ahora)
        if not 0 <= edad <= tope:
            return None, f'veredicto de hace {edad:.1f} h, fuera de 0 a {tope:g} h'
        carpeta, total = _carpeta_resultados(raiz), 0
        junits = datos.get('junits') or []
        if not junits:
            return None, 'sin junit'
        for j in junits:
            nombre = str(j['fichero'])
            if Path(nombre).name != nombre:
                return None, f'junit fuera de la carpeta: {nombre}'
            junit = carpeta / nombre
            if not junit.is_file() or _sha256(junit) != j['sha256']:
                return None, f'el junit {nombre} no cuadra con su sha256'
            relectura = veredicto(junit)
            if relectura['fallidas'] or relectura['omitidas']:
                return None, f'el junit {nombre} trae fallidas u omitidas'
            total += relectura['total']
        if total != datos.get('total') or not total:
            return None, f"el junit da {total} pruebas y el veredicto {datos.get('total')}"
    except (KeyError, TypeError, ValueError, AttributeError, OSError, PuertaError) as exc:
        return None, f'veredicto mal formado: {type(exc).__name__}: {exc}'
    return datos, ''


def _veredicto_del_indice(raiz: Path) -> tuple[str, dict | None, str]:
    """El árbol del índice y su veredicto válido para el gancho (102:RF-11), o el motivo por el que no vale."""
    try:
        arbol = arbol_del_indice(raiz)
    except (OSError, subprocess.CalledProcessError) as exc:
        return '', None, f'sin árbol del índice: {exc}'
    datos, motivo = veredicto_de_arbol(arbol, raiz, _entorno_de_pytest({}))
    return arbol, datos, motivo


def puerta_arbol(raiz: Path = RAIZ) -> int:
    """102:RF-11 (PUERTA-ESPECULATIVA): la suite entera sobre el árbol del índice, con los datos reales, y su veredicto en
    ``.git/puerta_calidad/arbol_<árbol>.json``, firmado. Se corre fuera de wt_integra, en un worktree con el mismo montaje;
    el gancho del commit con ese mismo árbol lo reutiliza y no repite la suite."""
    if not indice_igual_al_disco(raiz):
        print('Veredicto del árbol: el disco no es el índice (cambios sin preparar o ficheros nuevos de código, pruebas '
              'o specs); la suite probaría otra cosa que el árbol. Prepare el montaje entero con git add.')
        return 1
    arbol = arbol_del_indice(raiz)
    try:
        entorno = {**_variables_del_fichero(raiz), **variables_de_la_suite(raiz)}
    except PuertaError as exc:
        print(f'Veredicto del árbol: {exc}')
        return 1
    previo, _motivo = veredicto_de_arbol(arbol, raiz, _entorno_de_pytest(entorno))
    if previo:
        print(f'Veredicto del árbol: {arbol[:8]} ya tiene un veredicto válido ({ruta_veredicto_de_arbol(arbol, raiz)}).')
        return 0
    carpeta = _carpeta_resultados(raiz)
    carpeta.mkdir(parents=True, exist_ok=True)
    print(f'Veredicto del árbol: suite entera de {arbol} con los datos reales.')
    juicio = _pytest([], entorno, raiz, conservar=carpeta / f'arbol_{arbol}', procesos=_procesos_de_la_suite_entera())
    if arbol_del_indice(raiz) != arbol or not indice_igual_al_disco(raiz):
        print(f'Veredicto del árbol: el árbol cambió durante la suite; no se deja veredicto de {arbol[:8]}.')
        return 1
    ruta = ruta_veredicto_de_arbol(arbol, raiz)
    datos = {'formato': FORMATO_VEREDICTO_ARBOL, 'arbol': arbol,
             'fecha': datetime.now().astimezone().isoformat(timespec='seconds'),
             'puerta': firma_de_la_puerta(), 'variables': variables_de_la_firma(raiz, _entorno_de_pytest(entorno)),
             'entorno': entorno_de_la_firma(raiz),
             'aprobada': not juicio['fallidas'] and not juicio['omitidas'], **juicio}
    from convertersmartgrid.dominio import util

    util.write_json_atomic(ruta, datos)              # 001:RF-5: la escritura atómica única, después de los junit
    aprobada = _informar(juicio, omitidas_cuentan=True)
    print(f'Veredicto del árbol {arbol[:8]}: {"aprobado" if aprobada else "NO aprobado"} ({ruta}).')
    return 0 if aprobada else 1


def _procesos_de_la_suite_entera() -> int:
    """102:RF-5: los procesos de la suite entera, dicho en la salida (con poca memoria o sin xdist, 1)."""
    procesos, motivo = procesos_de_la_suite()
    print(f'Puerta: {motivo}.', flush=True)
    return procesos


def _orden_pytest(junit: Path, argumentos: list[str]) -> list[str]:
    return [sys.executable, '-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', f'--junitxml={junit}', *argumentos]


def _partes_de_la_suite(procesos: int) -> list[list[tuple[str, list[str]]]]:
    """102:RF-5 (PUERTA-XDIST): las sesiones de la suite, por tandas (las de una tanda corren a la vez). Con un proceso,
    una sola sesión, la de siempre. Con N: «serie» (una sesión) a la vez que «reparto» (N-1 procesos: con xdist y
    ``--dist loadfile`` desde dos, que mantiene juntas las pruebas de un fichero y sus fixtures de módulo); después,
    «a_solas»."""
    if procesos <= 1:
        return [[('suite', [])]]
    reparto = ['-m', SELECCION_REPARTO] + (['-n', str(procesos - 1), '--dist', 'loadfile'] if procesos > 2 else [])
    return [[('serie', ['-m', SELECCION_SERIE]), ('reparto', reparto)], [('a_solas', ['-m', SELECCION_A_SOLAS])]]


def _unir(juicios: list[dict]) -> dict:
    """El juicio de la suite repartida: la suma de los de sus sesiones; las lentas, otra vez las 30 mayores."""
    if len(juicios) == 1:
        return juicios[0]
    lentas = sorted((x for j in juicios for x in j.get('lentas') or []), key=lambda x: (-x['segundos'], x['prueba']))
    lentas = lentas[:LENTAS_GUARDADAS]
    unido = {'total': sum(j['total'] for j in juicios),
             'fallidas': [f for j in juicios for f in j['fallidas']],
             'omitidas': [o for j in juicios for o in j['omitidas']], 'lentas': lentas,
             'mas_de_umbral': [x for x in lentas if x['segundos'] > UMBRAL_PRUEBA_LENTA_S]}
    if any('junits' in j for j in juicios):
        unido['junits'] = [x for j in juicios for x in j.get('junits') or []]
    return unido


def _pytest(argumentos: list[str], entorno: Mapping[str, str], raiz: Path, exigidas: Iterable[str] = (), *,
            conservar: Path | None = None, procesos: int = 1) -> dict:
    """pytest con su junit; ``conservar`` (ruta sin extensión) guarda una copia de cada junit, ``<nombre>.<sesión>.junit.xml``,
    y su sha256 va en ``juicio['junits']`` (102:RF-11). ``procesos`` > 1 reparte la suite entera (102:RF-5,
    :func:`procesos_de_la_suite`); con 1, la orden de siempre."""
    from convertersmartgrid.aplicacion.trabajadores_ml import SALIDA_SIN_TURNO_GPU, quien_tiene_la_gpu

    # 102:RF-19: sin las variables que git pone al gancho (GIT_INDEX_FILE, GIT_DIR…): heredadas, el «git worktree add»
    # de las pruebas del asistente usaba el índice de este repositorio y fallaba solo dentro de la puerta (2026-11-11).
    limpio = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env = {**limpio, **entorno}
    tandas = _partes_de_la_suite(procesos)
    if procesos > 1:
        con_xdist = f', xdist -n {procesos - 1} --dist loadfile' if procesos > 2 else ''
        print(f'Puerta: suite entera repartida en {procesos} procesos: «serie» ({SELECCION_SERIE}) a la vez '
              f'que «reparto» ({SELECCION_REPARTO}{con_xdist}); después «a_solas» ({SELECCION_A_SOLAS}).', flush=True)
    juicios = []
    with tempfile.TemporaryDirectory() as tmp:
        resultados = []
        for tanda in tandas:
            if procesos <= 1:
                junit = Path(tmp) / 'junit.xml'
                resultados.append(('suite', junit, subprocess.run(_orden_pytest(junit, argumentos), cwd=raiz,
                                                                  env=env).returncode))
                continue
            lanzados = []
            for sesion, extra in tanda:
                junit = Path(tmp) / f'junit.{sesion}.xml'
                lanzados.append((sesion, junit, subprocess.Popen(_orden_pytest(junit, [*extra, *argumentos]), cwd=raiz,
                                                                 env=env)))
            resultados += [(sesion, junit, proceso.wait()) for sesion, junit, proceso in lanzados]
        for sesion, junit, rc in resultados:
            if rc == SALIDA_SIN_TURNO_GPU:
                # 106:RF-8: sin el turno de GPU no hay veredicto, y eso es un fallo con su dueño, nunca «0 fallidas».
                from convertersmartgrid.aplicacion.training_coordinator import ruta_guardia_gpu

                dueno = quien_tiene_la_gpu(ruta_guardia_gpu(env))   # la misma que calculó el conftest
                return {'total': 0, 'omitidas': [],
                        'fallidas': [{'prueba': 'pytest', 'motivo': f'sin el turno de GPU en su plazo: la tiene {dueno}'}]}
            if not junit.is_file():
                raise PuertaError(f'pytest ({sesion}) terminó con el código {rc} sin dejar resultado.')
            juicio = veredicto(junit, exigidas)
            if conservar is not None:
                copia = conservar.with_name(f'{conservar.name}.{sesion}.junit.xml')
                shutil.copyfile(junit, copia)
                juicio['junits'] = [{'fichero': copia.name, 'sha256': _sha256(copia)}]
            # 106:RF-16: un código distinto de 0 sin ninguna prueba fallida es una sesión que falló por algo que no es una
            # prueba (una línea de pruebas en un registro real de la web, por ejemplo). Antes solo contaban los códigos
            # distintos de 0 y 1, y con 1 y el junit limpio la puerta daba «0 fallidas» y aprobaba (auditoría del
            # 2026-11-13). En la suite repartida, una parte sin pruebas que elegir (código 5, junit vacío) no lo es.
            sin_pruebas = sesion != 'suite' and rc == _SIN_PRUEBAS and juicio['total'] == 0
            if rc != 0 and not juicio['fallidas'] and not sin_pruebas:
                donde = '' if sesion == 'suite' else f' (sesión «{sesion}»)'
                juicio['fallidas'].append({'prueba': 'pytest', 'motivo': f'terminó con el código {rc}{donde} sin ninguna '
                                           'prueba fallida: mire su salida (p. ej., una prueba que escribió en un '
                                           'registro real)'})
            juicios.append(juicio)
    return _unir(juicios)


def _informar(juicio: dict, *, omitidas_cuentan: bool) -> bool:
    for x in juicio.get('mas_de_umbral') or []:
        # 106:RF-15: no falla (faulthandler solo vuelca la pila), pero se dice: o la prueba se cuelga o el umbral es corto.
        print(f"LENTA {x['prueba']}: {x['segundos']:.0f} s, más que los {UMBRAL_PRUEBA_LENTA_S:.0f} s del volcado de pila.")
    for f in juicio['fallidas']:
        print(f"FALLA {f['prueba']}: {f['motivo']}")
    if omitidas_cuentan:
        for o in juicio['omitidas']:
            print(f"OMITIDA {o['prueba']}: {o['motivo']}")
    for e in juicio.get('exigidas_sin_correr') or []:
        print(f'SIN CORRER {e}: la puerta la exige corrida y aprobada.')
    malas = (len(juicio['fallidas']) + (len(juicio['omitidas']) if omitidas_cuentan else 0)
             + len(juicio.get('exigidas_sin_correr') or []))
    print(f"Puerta de calidad: {juicio['total']} pruebas, {len(juicio['fallidas'])} fallidas, "
          f"{len(juicio['omitidas'])} omitidas.")
    return malas == 0


def toca_el_frontend(ficheros: Iterable[str]) -> bool:
    """102:RF-24: el commit cambia algo de ``frontend/``, y entonces pasa también el lint de fronteras."""
    return any(f.replace('\\', '/').startswith('frontend/') for f in ficheros)


def lint_del_frontend(raiz: Path = RAIZ) -> tuple[bool, str]:
    """102:RF-24: las fronteras del frontend (``npm run lint``, que es ``node scripts/fronteras.mjs``).

    Se llama a node directamente, sin npm: es lo mismo que hace el script y no depende de que npm esté en el PATH del
    gancho. Sin node no se da por bueno: el commit se detiene y lo dice (H13, auditoría del 2026-11-14: el lint no corría
    ni en la CI ni en los ganchos, y 002 T11 quedaba sin vigilar).
    """
    carpeta = raiz / 'frontend'
    try:
        r = subprocess.run(['node', 'scripts/fronteras.mjs'], cwd=carpeta, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', check=False)
    except FileNotFoundError:
        return False, 'no se encuentra node para pasar el lint de fronteras del frontend'
    if r.returncode != 0:
        salida = (r.stdout + r.stderr).strip()
        if 'ERR_MODULE_NOT_FOUND' in salida:
            # Un worktree sin frontend/node_modules: el lint no se puede pasar, y no se da por bueno.
            return False, 'faltan las dependencias del frontend: ejecute «npm ci» en frontend/'
        return False, salida or f'el lint de fronteras salió con {r.returncode}'
    return True, ''


def exigencias_mcp(ficheros: Iterable[str], raiz: Path = RAIZ,
                   entorno: Mapping[str, str] | None = None) -> tuple[dict[str, str], tuple[str, ...]]:
    """077:RF-76: si el commit cambia el servidor MCP, su intérprete para pytest y las pruebas reales que exige.

    El intérprete sale del entorno, del fichero local de variables o del ``.venv_mcp`` del repositorio, en ese orden.
    Sin ninguno que exista: :class:`PuertaError` con lo que hay que poner.
    """
    if not any(f.replace('\\', '/') in DEL_MCP for f in ficheros):
        return {}, ()
    entorno = os.environ if entorno is None else entorno
    python = entorno.get('CSG_MCP_PYTHON') or ''
    if not python and (raiz / FICHERO_VARIABLES).is_file():
        try:
            python = str((json.loads((raiz / FICHERO_VARIABLES).read_text(encoding='utf-8')).get('variables') or {})
                         .get('CSG_MCP_PYTHON') or '')
        except ValueError as exc:
            raise PuertaError(f'{FICHERO_VARIABLES} no es JSON válido: {exc}') from exc
    if python and not Path(python).is_file():
        raise PuertaError(f'CSG_MCP_PYTHON={python} no existe: el commit cambia el servidor MCP.')
    if not python:
        python = next((str(raiz / v) for v in VENV_MCP if (raiz / v).is_file()), '')
    if not python:
        raise PuertaError('El commit cambia el servidor MCP y falta su intérprete: ponga CSG_MCP_PYTHON o cree .venv_mcp '
                          'con la orden de docs/MCP_CONVERSOR.md.')
    return {'CSG_MCP_PYTHON': python}, MCP_REAL


def puerta_commit(raiz: Path = RAIZ) -> int:
    """102:RF-1 a RF-4; 077:RF-76."""
    ficheros = [f for f in _git('diff', '--cached', '--name-only', '--diff-filter=ACMR', raiz=raiz).splitlines() if f]
    pruebas = pruebas_del_commit(ficheros, raiz)
    print(f'Puerta del commit: {len(pruebas)} ficheros de prueba.')
    if toca_el_frontend(ficheros):
        ok, motivo = lint_del_frontend(raiz)
        if not ok:
            print(f'Commit detenido: el lint de fronteras del frontend falla: {motivo}')
            return 1
    if not pruebas:
        # Un repositorio sin pruebas de gobierno (el de las pruebas de los ganchos de la 090): sin pruebas que
        # elegir, pytest correría todo el árbol y saldría con «ninguna prueba» (código 5).
        return 0
    try:
        entorno, exigidas = exigencias_mcp(ficheros, raiz)
    except PuertaError as exc:
        print(f'Commit detenido: {exc}')
        return 1
    if exigidas and 'tests/test_mcp_conversor.py' not in pruebas and 'tests' not in pruebas:
        pruebas.append('tests/test_mcp_conversor.py')
    # 102:RF-11 (aclaración, PUERTA-ESPECULATIVA): si este mismo árbol ya pasó la suite ENTERA con los datos reales,
    # firmada por esta puerta y en su plazo, lo que elegiría el commit ya está probado; no se repite y se cita.
    arbol, aprobado, motivo = _veredicto_del_indice(raiz)
    rama = rama_actual(raiz)
    if aprobado and rama not in RAMAS_CON_VEREDICTO_DE_ARBOL:
        # 102:RF-11 v2: fuera de la rama de trabajo (main, otra rama o sin rama) la suite corre fresca.
        aprobado, motivo = None, (f"en la rama «{rama or 'sin rama'}» no se reutiliza: solo en "
                                  f"{', '.join(RAMAS_CON_VEREDICTO_DE_ARBOL)}")
    if aprobado:
        junits = ', '.join(j['sha256'][:12] for j in aprobado['junits'])
        print(f"Puerta del commit: el árbol {arbol} ya pasó la suite entera el {aprobado['fecha']}, sin fallidas ni "
              f"omitidas (veredicto {ruta_veredicto_de_arbol(arbol, raiz)}; junit sha256 {junits}; puerta "
              f"{aprobado['puerta'][:12]}); no se repite.")
        _informar({'total': aprobado['total'], 'fallidas': [], 'omitidas': []}, omitidas_cuentan=True)
        return 0
    if arbol and ruta_veredicto_de_arbol(arbol, raiz).exists():
        print(f'Puerta del commit: el veredicto del árbol {arbol[:8]} no vale ({motivo}); se corren las pruebas.')
    procesos = _procesos_de_la_suite_entera() if pruebas == ['tests'] else 1
    if not _informar(_pytest(pruebas, entorno, raiz, exigidas=exigidas, procesos=procesos), omitidas_cuentan=False):
        print('Commit detenido: corrija las pruebas que fallan.')
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
        print(f'Puerta de la subida: {cabeza[:8]} ya pasó la suite completa sin omitidas.')
        return 0
    try:
        entorno = variables_de_la_suite(raiz)
    except PuertaError as exc:
        print(f'Subida detenida: {exc}')
        return 1
    # 102:RF-11 v2: aquí nunca se consulta un veredicto de árbol (arbol_<T>.json): main exige la suite completa.
    print(f'Puerta de la subida: suite completa de {cabeza[:8]} con los datos reales; main exige la suite completa y '
          'aquí no vale ningún veredicto de árbol.')
    juicio = _pytest([], entorno, raiz, exigidas=MCP_REAL, procesos=_procesos_de_la_suite_entera())
    ruta = guardar_resultado(cabeza, juicio, raiz)
    if not _informar(juicio, omitidas_cuentan=True):
        print(f'Subida detenida: la suite completa no pasa sin fallidas ni omitidas. Detalle: {ruta}')
        return 1
    return 0


#: 102:RF-32: dónde deja la CI su JUnit y su veredicto, que el flujo sube como artefacto (``/resultados_ci/`` en .gitignore).
VARIABLE_EVIDENCIA_CI = 'CSG_CI_EVIDENCIA'


def puerta_ci(raiz: Path = RAIZ) -> int:
    """102:RF-12, RF-14: la suite sintética; allí no hay datos reales y sus pruebas se omiten (RF-15).

    102:RF-32 (auditoría del 18-11, H07): el JUnit se conserva en ``CSG_CI_EVIDENCIA`` (por defecto
    ``<raíz>/resultados_ci``) con su sha256, y ``veredicto.json`` se escribe también si la suite falla: antes el JUnit
    vivía en un temporal y la corrida solo dejaba la consola."""
    carpeta = Path(os.environ.get(VARIABLE_EVIDENCIA_CI) or raiz / 'resultados_ci')
    carpeta.mkdir(parents=True, exist_ok=True)
    juicio = _pytest([], {}, raiz, conservar=carpeta / 'ci', procesos=_procesos_de_la_suite_entera())
    ok = _informar(juicio, omitidas_cuentan=False)
    (carpeta / 'veredicto.json').write_text(json.dumps({'ok': ok, **juicio}, indent=2, ensure_ascii=False) + '\n',
                                            encoding='utf-8')
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Puerta de calidad del repositorio (spec 102).')
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument('--commit', action='store_true', help='gancho pre-commit: gobierno y las pruebas del commit')
    modo.add_argument('--push', action='store_true', help='gancho pre-push: suite completa sin fallidas ni omitidas; '
                      'lee de la entrada estándar las líneas del gancho')
    modo.add_argument('--ci', action='store_true', help='GitHub Actions: suite sintética')
    modo.add_argument('--arbol', action='store_true', help='suite entera del árbol del índice con los datos reales; deja '
                      'su veredicto para el gancho del commit con ese mismo árbol (102:RF-11)')
    args = parser.parse_args(argv)
    try:
        if args.commit:
            return puerta_commit()
        if args.arbol:
            return puerta_arbol()
        if args.push:
            lineas = [] if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read().splitlines()
            if not lineas:                        # a mano, sin el gancho: la revisión actual, como al integrar
                return puerta_push([_git('rev-parse', 'HEAD').strip()])
            a_main, otras = revisiones_por_destino(lineas)
            for rama in otras:
                print(f'Puerta de la subida: {rama} es una rama de trabajo; sube sin la suite completa, que se exige al '
                      f'integrar en {RAMA_PRINCIPAL}. GitHub Actions corre la sintética.')
            return puerta_push(a_main) if a_main else 0
        return puerta_ci()
    except PuertaError as exc:
        print(f'Puerta de calidad: {exc}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
