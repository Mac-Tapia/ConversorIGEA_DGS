"""Spec 086, F5: el programa fuera del repositorio, el candidato, instalar y volver atrás, doctor, registro y soporte.

La rueda se construye de verdad, una vez por módulo, y corre en otro proceso fuera del repositorio. Instalar con el Python
embebido no se repite aquí: tarda minutos y baja su zip. Su evidencia está en las tareas de la spec, y estas pruebas cubren su
lógica (qué pasa si falla cada paso) sin él.
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apoyo import cargar_herramienta
from synthetic_export import ExportSpec, write_export

from convertersmartgrid import __version__, notas_de_la_version, runtime_paths
from convertersmartgrid.batch import convert_selection
from convertersmartgrid.cli import _parser, main as cli_main
from convertersmartgrid.dataset import CymdistDataset
from convertersmartgrid.edicion import es_edicion_producto
from convertersmartgrid.registro_rotativo import configurar_registro
from convertersmartgrid.web import doctor as DR, runtime as RT, soporte as SP
from convertersmartgrid.web.app import create_app

CC = cargar_herramienta('construir_candidato.py')
CE = CC.CE
IC = cargar_herramienta('instalar_candidato.py')
RAIZ = CE.RAIZ


@pytest.fixture(scope='module')
def manifiesto():
    return CE.leer_manifiesto()


@pytest.fixture(scope='module')
def terminos(manifiesto):
    return CE.cargar_terminos(RAIZ, manifiesto, lista_local=None)


@pytest.fixture(scope='module')
def rueda(tmp_path_factory, manifiesto, terminos):
    """La rueda de verdad, con un front mínimo: compilarlo pide Node y aquí no se prueba el front."""
    base = tmp_path_factory.mktemp('rueda')
    dist = base / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<!doctype html><title>x</title>', encoding='utf-8')
    return CC.construir_rueda(RAIZ, base / 'salida', manifiesto, terminos, dist=dist)[0]


@pytest.fixture(scope='module')
def fuera(rueda, tmp_path_factory):
    """El paquete instalado sin dependencias, en una carpeta fuera del repositorio."""
    destino = tmp_path_factory.mktemp('fuera')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index', '--no-compile', '--disable-pip-version-check',
                    '--target', str(destino), str(rueda)], check=True, capture_output=True)
    return destino


def _en_el_programa(fuera: Path, tmp_path: Path, codigo: str, **entorno) -> str:
    """Corre fuera del repositorio; las librerías de terceros siguen siendo las del entorno de pruebas."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('CSG_')}
    env.update(PYTHONPATH=str(fuera), CSG_DATOS_HOME=str(tmp_path / 'datos'), PYTHONDONTWRITEBYTECODE='1', **entorno)
    r = subprocess.run([sys.executable, '-c', codigo], cwd=tmp_path, env=env, capture_output=True, text=True, encoding='utf-8', check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


# --------------------------------------------------------------------------- RF-36: fuera del repositorio
def test_rueda_conserva_textos_de_licencias_del_front(rueda):
    """086:RF-39 — instalar solo la rueda también conserva los permisos del frontend compilado."""
    with zipfile.ZipFile(rueda) as z:
        texto = z.read('convertersmartgrid/_programa/frontend/dist/THIRD_PARTY_NOTICES.txt').decode('utf-8')
    for paquete in ('react 19.3.0', 'react-dom 19.3.0', 'scheduler 0.28.0'):
        assert paquete in texto
    assert 'Permission is hereby granted, free of charge' in texto


def test_fuera_del_repositorio_encuentra_lo_suyo(fuera, tmp_path):
    """086:RF-36 — el fallo real: instalado, `parents[2]` era site-packages y no había ni tools/ ni config/ ni el front."""
    salida = _en_el_programa(fuera, tmp_path, """
import json, convertersmartgrid as c
from convertersmartgrid.libros_informe import COSTES_REFERENCIALES
from convertersmartgrid.perfil_empresa import perfiles_disponibles, ruta_perfil_activo
from convertersmartgrid.powerfactory_env import project_root, tools_dir
from convertersmartgrid.edicion import es_edicion_producto
from convertersmartgrid.asistente import reranker
r = project_root()
print(json.dumps({'paquete': c.__file__, 'raiz': str(r), 'guiones': sorted(p.name for p in tools_dir().glob('*.py')),
                  'pide': (r / 'config' / 'pide_universal_2017.json').is_file(), 'vnr': (r / 'config' / 'vnr_dgs_profile.json').is_file(),
                  'costes': COSTES_REFERENCIALES.is_file(), 'front': (r / 'frontend' / 'dist' / 'index.html').is_file(),
                  'modelos': reranker.CATALOGO.is_file(), 'perfiles': perfiles_disponibles(), 'perfil': str(ruta_perfil_activo()),
                  'producto': es_edicion_producto(), 'notas': bool(c.notas_de_la_version())}))
""")
    d = json.loads(salida)
    assert Path(d['paquete']).parent.parent == fuera.resolve() or Path(d['paquete']).is_relative_to(fuera)
    assert 'powerfactory_acceptance.py' in d['guiones'] and 'sistema_web.py' in d['guiones']
    assert all(d[k] for k in ('pide', 'vnr', 'costes', 'front', 'modelos', 'notas', 'producto'))
    assert d['perfiles'] == ['ficticia', 'plantilla']
    assert Path(d['perfil']).is_relative_to(tmp_path), 'el perfil de la empresa no puede vivir en la carpeta del programa'


def test_la_plantilla_vnr_se_encuentra_sin_estar_en_la_carpeta_del_programa(fuera, tmp_path):
    """086:RF-36 — `config/vnr_dgs_profile.json` era relativa al directorio de trabajo; instalado, este es el de datos."""
    assert 'ok' in _en_el_programa(fuera, tmp_path, """
from vnr_etl.application.services import VnrApplicationService
assert VnrApplicationService()._profile('dgs') is not None
print('ok')
""")


def _huellas_del_motor(tmp_path: Path, layout: str, workers: int) -> dict[str, str]:
    red, carga, equipo = write_export(ExportSpec(feeders=3, sections_per_feeder=6, loads_per_feeder=3, layout=layout, seed=11), tmp_path / 'e')
    ds = CymdistDataset.from_files(red, carga, equipo)
    convert_selection(ds, None, str(tmp_path / 'o'), all_feeders=True, aliases={}, strict=False, include_geography=False, workers=workers)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((tmp_path / 'o').rglob('*.dgs'))}


@pytest.mark.parametrize('layout', ['reducido', 'completo'])
@pytest.mark.parametrize('workers', [1, 2])
def test_la_rueda_da_los_mismos_dgs_que_el_arbol(fuera, tmp_path, layout, workers):
    """086:RF-36; 001:RF-14 — neutralizar comentarios y mover recursos no cambia un byte, con las dos disposiciones y en paralelo."""
    (tmp_path / 'arbol').mkdir()
    (tmp_path / 'instalado').mkdir()
    esperado = _huellas_del_motor(tmp_path / 'arbol', layout, workers)
    assert esperado
    salida = _en_el_programa(fuera, tmp_path / 'instalado', f"""
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).parent)!r})
from synthetic_export import ExportSpec, write_export
import convertersmartgrid
from convertersmartgrid.batch import convert_selection
from convertersmartgrid.dataset import CymdistDataset
if __name__ == '__main__':
    assert '_programa' not in convertersmartgrid.__file__ and {str(RAIZ)!r} not in convertersmartgrid.__file__
    t = Path('.').resolve()
    red, carga, equipo = write_export(ExportSpec(feeders=3, sections_per_feeder=6, loads_per_feeder=3, layout={layout!r}, seed=11), t / 'e')
    ds = CymdistDataset.from_files(red, carga, equipo)
    convert_selection(ds, None, str(t / 'o'), all_feeders=True, aliases={{}}, strict=False, include_geography=False, workers={workers})
    print(json.dumps({{p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((t / 'o').rglob('*.dgs'))}}))
""")
    assert json.loads(salida.strip().splitlines()[-1]) == esperado


def test_lo_que_lanza_la_web_entra_en_la_entrega(manifiesto):
    """086:RF-36; 086:RF-34 — el fallo real: `powerfactory_acceptance.py`, el que importa en DIgSILENT, estaba excluido de la lista."""
    guiones = re.findall(r"_script\('([\w.]+)'\)", (RAIZ / 'src/convertersmartgrid/web/services.py').read_text(encoding='utf-8'))
    # Lo de entrenar lo niega la edición de producto antes de llegar aquí (086:RF-15).
    no_vendidos = {'digital_twin_entrenar.py', 'digital_twin_temporal_entrenar.py', 'asistente_entrenar.py'}
    assert guiones
    faltan = sorted({g for g in guiones if not CE.entra(f'tools/{g}', manifiesto)} - no_vendidos)
    assert not faltan, faltan


def test_los_guiones_entregados_no_importan_uno_excluido(manifiesto):
    """086:RF-36 — un guion que se entrega y arrastra uno que no da `ModuleNotFoundError` en casa del cliente."""
    herramientas = {p.stem for p in (RAIZ / 'tools').glob('*.py')}
    entregadas = {h for h in herramientas if CE.entra(f'tools/{h}.py', manifiesto)}
    faltan = {}
    for h in sorted(entregadas):
        arbol = ast.parse((RAIZ / 'tools' / f'{h}.py').read_text(encoding='utf-8'))
        nombres = {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
        nombres |= {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module and not n.level}
        if (nombres & herramientas) - entregadas:
            faltan[h] = sorted((nombres & herramientas) - entregadas)
    assert not faltan, faltan


def test_lo_instalado_es_de_producto_sin_que_nadie_lo_diga(monkeypatch, tmp_path):
    """086:RF-36; 086:RF-15 — abrirlo sin el lanzador no destapa el entrenamiento; en el árbol, sin la variable, sigue siendo desarrollo."""
    monkeypatch.delenv('CSG_EDICION', raising=False)
    assert es_edicion_producto() is False
    instalado = tmp_path / 'convertersmartgrid' / '_programa'
    instalado.mkdir(parents=True)
    assert runtime_paths.es_programa_instalado(instalado)
    assert not runtime_paths.es_programa_instalado(RAIZ)
    monkeypatch.setattr('convertersmartgrid.edicion.raiz_programa', lambda: instalado)
    assert es_edicion_producto() is True
    monkeypatch.setenv('CSG_EDICION', 'desarrollo')
    assert es_edicion_producto() is False


# --------------------------------------------------------------------------- RF-38: programa y datos
def _programa_falso(tmp_path: Path) -> Path:
    programa = tmp_path / 'sitio' / 'convertersmartgrid' / '_programa'
    programa.mkdir(parents=True)
    return programa


def test_programa_y_datos_separados(tmp_path):
    """086:RF-38 — instalado, los datos, la identidad y el runtime no están en la carpeta que sustituye una actualización."""
    programa = _programa_falso(tmp_path)
    env = {'CSG_DATOS_HOME': str(tmp_path / 'datos'), 'LOCALAPPDATA': str(tmp_path / 'local')}
    assert runtime_paths.raiz_local(programa, env) == tmp_path / 'datos'
    rutas = runtime_paths.rutas_runtime(programa, env)
    assert rutas.runtime == (tmp_path / 'datos' / 'runtime').resolve()
    assert not rutas.runtime.is_relative_to(programa)
    assert runtime_paths.raiz_local(programa, {'LOCALAPPDATA': str(tmp_path / 'local')}) == tmp_path / 'local' / 'ConverterSmartGrid' / 'datos'


def test_en_desarrollo_el_local_es_el_repositorio(tmp_path):
    """086:RF-38 — el árbol de desarrollo no cambia: su perfil sigue en config/ y su raíz en la de siempre."""
    assert runtime_paths.raiz_local(tmp_path, {}) == tmp_path
    assert runtime_paths.rutas_runtime(tmp_path, {}).runtime.parent.name == '.convertersmartgrid-runtime'


def test_la_identidad_sobrevive_a_sustituir_el_programa(tmp_path, monkeypatch):
    """086:RF-38; 086:RF-7 — con el programa nuevo, la misma identidad y los mismos datos."""
    programa = _programa_falso(tmp_path)
    monkeypatch.setenv('CSG_DATOS_HOME', str(tmp_path / 'datos'))
    primero = runtime_paths.rutas_runtime(programa)
    runtime_paths.fijar_identidad(primero)
    assert not (programa / runtime_paths.FICHERO_INSTALACION).exists()
    assert (tmp_path / 'datos' / runtime_paths.FICHERO_INSTALACION).is_file()
    shutil.rmtree(programa)
    programa.mkdir()
    assert runtime_paths.rutas_runtime(programa).identidad == primero.identidad


def test_la_copia_de_una_instalacion_lleva_perfil_y_catalogos(tmp_path, monkeypatch):
    """086:RF-38; 086:RF-10 — las fichas del operador están en input/ y son datos: una actualización no puede dejarlas sin copia."""
    from convertersmartgrid.web.copia_datos import raices_de_datos

    programa = _programa_falso(tmp_path)
    monkeypatch.setenv('CSG_DATOS_HOME', str(tmp_path / 'datos'))
    (tmp_path / 'datos' / 'input').mkdir(parents=True)
    raices = raices_de_datos(programa)
    assert raices['config'] == tmp_path / 'datos' / 'config'
    assert raices['input'] == tmp_path / 'datos' / 'input'


def _candidato(tmp_path: Path, version: str = '9.9.9') -> Path:
    c = tmp_path / f'cand-{version}'
    (c / 'terceros').mkdir(parents=True)
    (c / 'terceros' / 'dato.txt').write_text('x', encoding='utf-8')
    ficheros = [{'ruta': 'terceros/dato.txt', 'sha256': hashlib.sha256(b'x').hexdigest(), 'bytes': 1}]
    (c / 'manifiesto_candidato.json').write_text(json.dumps({'version': version, 'ficheros': ficheros}), encoding='utf-8')
    return c


@pytest.fixture()
def instalador_sin_motor(monkeypatch):
    """Sin pip ni Python embebido: lo que se prueba es cuándo cambia el puntero."""
    def preparar(candidato, destino, manifiesto):
        python = destino / 'versiones' / manifiesto['version'] / 'python' / 'python.exe'
        python.parent.mkdir(parents=True)
        python.write_text('', encoding='utf-8')
        return python

    llamadas = {'copias': 0}

    def copiar(python, carpeta):
        llamadas['copias'] += 1
        return {'ruta': 'copia-previa'}

    monkeypatch.setattr(IC, '_preparar_version', preparar)
    monkeypatch.setattr(IC, '_doctor', lambda python: {'pendientes': 0})
    monkeypatch.setattr(IC, '_copiar_datos', copiar)
    monkeypatch.setattr(IC, '_web_escuchando', lambda puerto: False)
    return llamadas


def test_actualizar_copia_los_datos_y_deja_a_que_volver(tmp_path, instalador_sin_motor):
    """086:RF-38 — la primera instalación no copia nada; la actualización, sí, y conserva la versión anterior."""
    destino = tmp_path / 'app'
    assert IC.instalar(_candidato(tmp_path, '1.0'), destino)['anterior'] is None
    assert instalador_sin_motor['copias'] == 0
    r = IC.instalar(_candidato(tmp_path, '1.1'), destino)
    assert (r['anterior'], r['copia']) == ('1.0', 'copia-previa')
    assert IC.estado(destino) == {'actual': '1.1', 'anterior': '1.0', 'versiones': ['1.0', '1.1']}
    assert IC.instalar(_candidato(tmp_path, '1.2'), destino)['anterior'] == '1.1'
    assert IC.estado(destino)['versiones'] == ['1.1', '1.2'], 'una versión pesa cientos de MB: solo la actual y a la que volver'


@pytest.mark.parametrize('paso', ['_doctor', '_copiar_datos'])
def test_si_la_version_nueva_falla_sigue_la_anterior(tmp_path, instalador_sin_motor, monkeypatch, paso):
    """086:RF-38 — ni el doctor ni la copia pueden dejar el puntero en una versión a medias."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato(tmp_path, '1.0'), destino)

    def falla(*_):
        raise IC.ErrorInstalacion('falla')

    monkeypatch.setattr(IC, paso, falla)
    with pytest.raises(IC.ErrorInstalacion):
        IC.instalar(_candidato(tmp_path, '1.1'), destino)
    assert IC.estado(destino) == {'actual': '1.0', 'anterior': None, 'versiones': ['1.0']}


def test_no_actualiza_con_el_programa_abierto(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-38 — la web guarda sus espacios en memoria: al salir pisaría lo restaurado."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato(tmp_path, '1.0'), destino)
    IC.instalar(_candidato(tmp_path, '1.1'), destino)
    monkeypatch.setattr(IC, '_web_escuchando', lambda puerto: True)
    with pytest.raises(IC.ErrorInstalacion, match='abierto'):
        IC.instalar(_candidato(tmp_path, '1.2'), destino)
    with pytest.raises(IC.ErrorInstalacion, match='abierto'):
        IC.volver(destino)
    assert IC.estado(destino)['actual'] == '1.1'


def test_volver_cambia_el_puntero_y_restaura_la_copia(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-38 — vuelve a la versión anterior y a sus datos; si no se puede restaurar, no cambia de versión."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato(tmp_path, '1.0'), destino)
    IC.instalar(_candidato(tmp_path, '1.1'), destino)
    ordenes = []

    class Resultado:
        returncode = 1
        stdout = stderr = 'fallo'

    monkeypatch.setattr(IC.subprocess, 'run', lambda orden, **kw: ordenes.append(orden) or Resultado())
    with pytest.raises(IC.ErrorInstalacion, match='sigue la versión 1.1'):
        IC.volver(destino)
    assert IC.estado(destino)['actual'] == '1.1'
    assert 'restaurar' in ordenes[0] and 'copia-previa' in ordenes[0]
    Resultado.returncode = 0
    r = IC.volver(destino)
    assert r == {'version': '1.0', 'dejada': '1.1', 'datos_restaurados_de': 'copia-previa'}
    assert IC.estado(destino)['anterior'] == '1.1'


def test_volver_sin_version_anterior(tmp_path, instalador_sin_motor):
    """086:RF-38 — con una sola versión no hay a qué volver, y lo dice."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato(tmp_path, '1.0'), destino)
    with pytest.raises(IC.ErrorInstalacion, match='anterior'):
        IC.volver(destino)


def test_ruta_demasiado_larga_se_dice_al_instalar(tmp_path, monkeypatch):
    """086:RF-36 — el fallo real: con una carpeta larga, pyproj y shapely daban «nombre demasiado largo» solo al importarlos."""
    c = _candidato(tmp_path)
    (c / 'terceros' / 'python').mkdir()
    (c / 'terceros' / 'wheels').mkdir()
    (c / 'terceros' / 'wheels' / 'pip-1-py3-none-any.whl').write_bytes(b'')

    class Bien:
        returncode = 0
        stdout = stderr = ''

    monkeypatch.setattr(IC.subprocess, 'run', lambda *a, **k: Bien())
    destino = tmp_path / 'app'
    carpeta = destino / 'versiones' / '9.9.9' / 'python' / 'Lib'
    copia = shutil.copytree

    def copiar(origen, dest, **kw):
        copia(origen, dest, **kw)
        carpeta.mkdir(parents=True)
        (carpeta / 'a.pyd').write_bytes(b'')

    monkeypatch.setattr(IC.shutil, 'copytree', copiar)
    monkeypatch.setattr(IC, 'LONGITUD_MAXIMA_RUTA', 10)
    with pytest.raises(IC.ErrorInstalacion, match='demasiado larga'):
        IC._preparar_version(c, destino, {'version': '9.9.9'})


# --------------------------------------------------------------------------- RF-39: huellas y nunca al arrancar
def test_candidato_alterado_no_se_instala(tmp_path):
    """086:RF-39 — cada fichero contra su huella, antes de tocar nada."""
    c = _candidato(tmp_path)
    assert IC.verificar_candidato(c)['version'] == '9.9.9'
    (c / 'terceros' / 'dato.txt').write_text('y', encoding='utf-8')
    with pytest.raises(IC.ErrorInstalacion, match='otra huella'):
        IC.verificar_candidato(c)
    (c / 'terceros' / 'dato.txt').unlink()
    with pytest.raises(IC.ErrorInstalacion, match='falta'):
        IC.verificar_candidato(c)


def test_instala_sin_red_y_con_huellas(tmp_path, monkeypatch):
    """086:RF-39; 086:RF-36 — pip sin índice, con `--require-hashes`, y sin el entorno de otro Python del equipo."""
    c = _candidato(tmp_path)
    (c / 'terceros' / 'python').mkdir()
    (c / 'terceros' / 'wheels').mkdir()
    (c / 'terceros' / 'wheels' / 'pip-1-py3-none-any.whl').write_bytes(b'')
    visto = {}

    class Bien:
        returncode = 0
        stdout = stderr = ''

    def correr(orden, env=None, **kw):
        visto.update(orden=orden, env=env)
        return Bien()

    monkeypatch.setattr(IC.subprocess, 'run', correr)
    monkeypatch.setenv('PIP_INDEX_URL', 'https://ajeno/')
    monkeypatch.setenv('PYTHONPATH', 'ajeno')
    python = IC._preparar_version(c, tmp_path / 'app', {'version': '9.9.9'})
    assert '--no-index' in visto['orden'] and '--require-hashes' in visto['orden']
    assert visto['env']['PIP_NO_INDEX'] == '1' and 'PIP_INDEX_URL' not in visto['env']
    assert visto['env']['PYTHONPATH'].endswith('.whl'), 'solo pip, desde su rueda'
    # Sin PYTHONHOME, en un equipo con otro 3.12 este Python cargaba DLL de aquel, por el registro de Windows.
    assert visto['env']['PYTHONHOME'] == str(python.parent)


def _lineas_que_se_ejecutan(texto: str) -> list[str]:
    return [l.strip() for l in texto.splitlines() if l.strip() and not l.strip().lower().startswith(('rem ', 'echo ', '@echo'))]


def test_arrancar_no_instala(tmp_path):
    """086:RF-39 — ni el lanzador de desarrollo ni el del programa instalan nada; pueden decir cómo hacerlo."""
    desarrollo = _lineas_que_se_ejecutan((RAIZ / 'run_gui.bat').read_bytes().decode('ascii'))
    producto = _lineas_que_se_ejecutan(IC._CABECERA_CMD + IC._PIE_WEB + IC._PIE_ORDEN)
    for linea in (*desarrollo, *producto):
        assert not re.search(r'pip\s+install|-m\s+pip|npm\s+(ci|install)', linea), linea
    assert not any('npm' in l for l in producto)


def test_lanzador_del_programa_no_lee_otro_python(tmp_path):
    """086:RF-36 — PYTHONHOME propio, nada de PYTHONPATH de la máquina, sin lo del usuario y sin la carpeta de trabajo en la ruta."""
    texto = IC._CABECERA_CMD + IC._PIE_WEB
    assert 'set "PYTHONHOME=%PYDIR%"' in texto and 'set "PYTHONPATH="' in texto and 'PYTHONNOUSERSITE=1' in texto
    assert '-P -m convertersmartgrid.web' in texto
    IC._escribir_lanzadores(tmp_path)
    assert (tmp_path / 'ConverterSmartGrid.cmd').read_bytes().count(b'\r\n') > 5, 'cmd.exe exige CRLF'
    assert {'csg.cmd', 'volver_atras.cmd', 'copia_datos.cmd'} <= {p.name for p in tmp_path.iterdir()}


def test_el_lock_lleva_una_huella_por_rueda():
    """086:RF-39 — sin versión exacta y huella, `--require-hashes` no instala."""
    texto = (RAIZ / 'requirements-nucleo.lock').read_text(encoding='utf-8')
    filas = re.findall(r'^([a-z0-9._-]+)==(\S+) \\\n    --hash=sha256:([0-9a-f]{64})$', texto, flags=re.M)
    lineas = [l for l in texto.splitlines() if l and not l.startswith(('#', '    '))]
    assert filas and len(filas) == len(lineas)
    assert 'pip' in {f[0] for f in filas}, 'instalar el complemento de IA necesita pip'


def test_el_lock_sigue_las_versiones_fijadas(manifiesto):
    """086:RF-39 — el lock solo se aparta de las versiones probadas en lo que un aviso de seguridad obliga, y lo declara."""
    fijadas = dict(re.findall(r'^([a-z0-9._-]+)==(\S+)', (RAIZ / 'constraints-python312-win.txt').read_text(encoding='utf-8'), flags=re.M))
    lock = dict(re.findall(r'^([a-z0-9._-]+)==(\S+) ', (RAIZ / 'requirements-nucleo.lock').read_text(encoding='utf-8'), flags=re.M))
    distintas = {n: v for n, v in lock.items() if n in fijadas and fijadas[n] != v}
    seguridad = manifiesto['candidato']['versiones_de_seguridad']
    assert distintas == {n: v for n, v in seguridad.items() if fijadas.get(n) != v}
    assert all(lock.get(n) == v for n, v in seguridad.items())


def test_limites_con_seguridad():
    """086:RF-39 — la versión de seguridad sustituye a la fijada; el resto no se toca."""
    texto = CC.limites_con_seguridad('pillow==12.3.0 ; python_version == "3.12"\nnumpy==2.4.6 ; python_version == "3.12"\n# nota\n', {'pillow': '13.0.0'})
    assert 'pillow==12.3.0' not in texto and 'pillow==13.0.0' in texto and 'numpy==2.4.6' in texto


# --------------------------------------------------------------------------- RF-37: núcleo sin torch
def test_nucleo_sin_torch_ni_pruebas(manifiesto):
    """086:RF-37; 086:RF-36 — ni torch ni pytest en lo que se instala."""
    nombres = set(re.findall(r'^([a-z0-9._-]+)==', (RAIZ / 'requirements-nucleo.lock').read_text(encoding='utf-8'), flags=re.M))
    assert not nombres & set(manifiesto['candidato']['fuera_del_nucleo'])
    assert 'fastapi' in nombres and 'geopandas' in nombres


def test_complemento_de_ia_aparte():
    """086:RF-37 — declarado, con torch; y los pesos y lo de entrenar, fuera."""
    filas = [l.split('#')[0].strip() for l in (RAIZ / 'requirements-complemento-ia.txt').read_text(encoding='utf-8').splitlines()]
    nombres = {re.split(r'[<>=]', f)[0] for f in filas if f}
    assert 'torch' in nombres and 'transformers' in nombres
    assert not nombres & {'peft', 'bitsandbytes', 'optuna', 'torch-geometric', 'neuralforecast'}


def test_la_web_arranca_sin_torch(tmp_path):
    """086:RF-37 — con torch inalcanzable se crea la aplicación y responde el doctor."""
    r = subprocess.run([sys.executable, '-c', f"""
import sys
sys.modules['torch'] = None
sys.modules['transformers'] = None
sys.path.insert(0, {str(RAIZ / 'src')!r})
from pathlib import Path
from convertersmartgrid import sesion_web
sesion_web.EXIGIR_SEGURIDAD = False
from convertersmartgrid.web.app import create_app
from fastapi.testclient import TestClient
with TestClient(create_app(Path({str(tmp_path / 'web')!r}))) as c:
    d = c.get('/api/sistema/diagnostico').json()
    ia = next(f for f in d['comprobaciones'] if f['clave'] == 'complemento_ia')
    assert c.get('/api/health').status_code == 200
    print('sin torch', ia['obligatoria'])
"""], capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'CSG_RUNTIME_HOME': str(tmp_path / 'rt'), 'CSG_WEB_FRONTEND': str(tmp_path / 'sin')}, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'sin torch False' in r.stdout


# --------------------------------------------------------------------------- comprobar el candidato (RF-33, RF-34, RF-36)
def _paquete(tmp_path: Path, rueda: Path, *, manipular=None) -> Path:
    c = tmp_path / 'candidato'
    (c / 'programa').mkdir(parents=True)
    (c / 'terceros' / 'wheels').mkdir(parents=True)
    (c / 'documentos').mkdir()
    shutil.copyfile(rueda, c / 'programa' / rueda.name)
    (c / 'documentos' / 'LEEME.md').write_text('Sin nombres.\n', encoding='utf-8')
    with zipfile.ZipFile(c / 'terceros' / 'wheels' / 'numpy-1-py3-none-any.whl', 'w') as z:
        z.writestr('numpy/__init__.py', 'x = 1\n')
    if manipular:
        manipular(c)
    ficheros = [{'ruta': rel, 'sha256': CE._sha256(r), 'bytes': r.stat().st_size} for r, rel in CE._recorrer(c)]
    (c / 'manifiesto_candidato.json').write_text(json.dumps({'version': '1', 'ficheros': ficheros}), encoding='utf-8')
    return c


def _meter_en_la_rueda(c: Path, nombre: str, contenido: str) -> None:
    rueda = next((c / 'programa').glob('*.whl'))
    with zipfile.ZipFile(rueda, 'a') as z:
        z.writestr(nombre, contenido)


def _empresa() -> str:
    manifiesto = CE.leer_manifiesto()
    perfil = next(r for r in sorted((RAIZ / 'config' / 'perfiles').glob('*.json'))
                  if not CE.entra(f'config/perfiles/{r.name}', manifiesto) and not r.name.endswith('.estructura.json'))
    return json.loads(perfil.read_text(encoding='utf-8'))['empresa']


def test_la_rueda_real_pasa_la_comprobacion(tmp_path, rueda, manifiesto, terminos):
    """086:RF-33; 086:RF-34 — mirando dentro de la rueda: sin términos, ni en comentarios, sin pesos y sin nada fuera de la lista."""
    informe = CE.comprobar(RAIZ, manifiesto, terminos, candidato=_paquete(tmp_path, rueda))
    assert not informe.rechazado, informe.resumen()['rechazos'] or informe.resumen()['por_zona_y_clase']
    assert informe.ficheros > 100 and informe.ruedas_propias == 1 and informe.terceros == 1


def test_comprobar_una_rueda_sola(rueda, manifiesto, terminos):
    """086:RF-33 — `--candidato` también acepta la rueda, no solo carpetas."""
    assert not CE.comprobar(RAIZ, manifiesto, terminos, candidato=rueda).rechazado
    assert CE.main(['--candidato', str(rueda)]) == 0


@pytest.mark.parametrize('nombre,contenido,motivo', [
    ('convertersmartgrid/_programa/tests/test_x.py', 'x = 1\n', 'no está en la lista'),
    ('convertersmartgrid/_programa/config/perfil_empresa.json', '{}', 'no está en la lista'),
    ('convertersmartgrid/modelo.safetensors', 'x', 'peso no declarado'),
    ('convertersmartgrid/_programa/tools/red.dgs', 'x', 'no está en la lista'),
    ('convertersmartgrid/red.dgs', 'x', 'fichero de datos'),
])
def test_lo_que_no_debe_ir_dentro_de_la_rueda_se_rechaza(tmp_path, rueda, manifiesto, terminos, nombre, contenido, motivo):
    """086:RF-34; 086:RF-33 — lo prohibido se ve aunque vaya dentro de la rueda."""
    c = _paquete(tmp_path, rueda, manipular=lambda c: _meter_en_la_rueda(c, nombre, contenido))
    informe = CE.comprobar(RAIZ, manifiesto, terminos, candidato=c)
    assert informe.rechazado and any(motivo in m for _, m in informe.rechazos), informe.rechazos


def test_un_nombre_dentro_de_la_rueda_se_rechaza(tmp_path, rueda, manifiesto, terminos):
    """086:RF-33 — en el código o en los metadatos."""
    empresa = _empresa()
    for nombre, contenido in (('convertersmartgrid/motor_x.py', f'NOMBRE = "{empresa}"\n'),
                              ('convertersmartgrid-1.dist-info/METADATA', f'Description: {empresa}\n')):
        destino = tmp_path / nombre.replace('/', '_')
        destino.mkdir()
        c = _paquete(destino, rueda, manipular=lambda c, n=nombre, t=contenido: _meter_en_la_rueda(c, n, t))
        assert CE.comprobar(RAIZ, manifiesto, terminos, candidato=c).hallazgos, nombre


def test_torch_en_el_nucleo_se_rechaza(tmp_path, rueda, manifiesto, terminos):
    """086:RF-37 — una rueda de torch colada en el paquete lo rechaza."""
    def colar(c):
        with zipfile.ZipFile(c / 'terceros' / 'wheels' / 'torch-2-cp312-win_amd64.whl', 'w') as z:
            z.writestr('torch/__init__.py', '')

    informe = CE.comprobar(RAIZ, manifiesto, terminos, candidato=_paquete(tmp_path, rueda, manipular=colar))
    assert any('núcleo' in m for _, m in informe.rechazos), informe.rechazos


@pytest.mark.parametrize('cambio,motivo', [('alterar', 'huella distinta'), ('quitar', 'ausente'), ('añadir', 'sin anotar')])
def test_manifiesto_del_candidato(tmp_path, rueda, manifiesto, terminos, cambio, motivo):
    """086:RF-39 — el paquete tiene que coincidir con su manifiesto, fichero a fichero."""
    c = _paquete(tmp_path, rueda)
    leeme = c / 'documentos' / 'LEEME.md'
    if cambio == 'alterar':
        leeme.write_text('otro\n', encoding='utf-8')
    elif cambio == 'quitar':
        leeme.unlink()
    else:
        (c / 'documentos' / 'NUEVO.md').write_text('x\n', encoding='utf-8')
    informe = CE.comprobar(RAIZ, manifiesto, terminos, candidato=c)
    assert any(motivo in m for _, m in informe.rechazos), informe.rechazos


def test_neutralizar_conserva_el_codigo(terminos):
    """086:RF-33 — D5: se va el nombre del caso, se queda el motivo y el código no cambia."""
    empresa = _empresa()
    texto = (f'"""Viene de {empresa}, en la entrega de marzo."""\n'
             f'# Porque en {empresa.upper()} faltaba el dato.\n'
             'VALOR = 1  # Sin relación.\n')
    nuevo, n = CE.neutralizar('a.py', texto, terminos)
    assert n >= 2 and '[caso]' in nuevo and 'faltaba el dato' in nuevo
    assert not CE.buscar_en_texto('a.py', nuevo, terminos)
    assert 'VALOR = 1' in nuevo and ast.dump(ast.parse(nuevo).body[1]) == ast.dump(ast.parse(texto).body[1])


def test_neutralizar_no_toca_un_nombre_en_el_codigo(terminos):
    """086:RF-33 — eso es un hallazgo que hay que arreglar, no algo que tapar."""
    empresa = _empresa()
    texto = f'NOMBRE = "{empresa}"\n'
    assert CE.neutralizar('a.py', texto, terminos) == (texto, 0)
    assert [h.clase for h in CE.buscar_en_texto('a.py', texto, terminos)] == ['codigo'] * len(CE.buscar_en_texto('a.py', texto, terminos))


# --------------------------------------------------------------------------- RF-40: doctor
def _sin(*faltan):
    def importar(nombre):
        if nombre in faltan:
            raise ImportError(f'No se pudo cargar {nombre}')
        return object()

    return importar


def _doctor(tmp_path, importer=None, drivers=None, pf=None, **kw):
    programa = tmp_path / 'programa'
    (programa / 'frontend' / 'dist').mkdir(parents=True, exist_ok=True)
    (programa / 'frontend' / 'dist' / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    return DR.diagnosticar(importer=importer or _sin(), drivers=drivers or (lambda: tuple(RT.DRIVERS_POR_CAPACIDAD.values())),
                           version=(3, 12), carpeta_pf=pf or (lambda: None), programa=programa,
                           buscar_modulo=kw.pop('buscar_modulo', lambda n: None), buscar_programa=kw.pop('buscar_programa', lambda n: None), **kw)


@pytest.fixture()
def _sin_entorno_frontend(monkeypatch, tmp_path):
    monkeypatch.delenv('CSG_WEB_FRONTEND', raising=False)
    monkeypatch.delenv('CSG_TESSERACT', raising=False)
    # 091:RF-32: el buscador también mira Program Files; la simulación sin OCR
    # debe aislar esa vía, además del PATH que ya inyecta _doctor.
    monkeypatch.setattr('convertersmartgrid.documentos_solicitud.tesseract', lambda: None)
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'sin_perfil.json'))
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'rt'))


def _fila(informe, clave):
    return next(c for c in informe['comprobaciones'] if c['clave'] == clave)


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_con_todo_esta_listo(tmp_path):
    """086:RF-40 — sin nada que falte, listo; lo opcional que no hay se cuenta sin bloquear."""
    informe = _doctor(tmp_path)
    assert informe['listo'] is True
    assert informe['version'] == __version__


@pytest.mark.usefixtures('_sin_entorno_frontend')
@pytest.mark.parametrize('capacidad', sorted(DR._CAPACIDADES))
def test_quitar_cada_libreria_dice_que_funcion_afecta(tmp_path, capacidad):
    """086:RF-40 — quitar cada requisito dice qué falta, qué función afecta y cómo arreglarlo."""
    modulo = next(m for m in RT.MODULOS_POR_CAPACIDAD[capacidad])
    informe = _doctor(tmp_path, importer=_sin(modulo))
    fila = _fila(informe, capacidad)
    assert fila['ok'] is False and modulo in fila['detalle'] and fila['afecta'] and fila['arreglo']
    assert 'No se pudo cargar' in fila['detalle'], 'el error real ayuda a soporte'
    # Una librería viene en el paquete: si no carga, la instalación está mal.
    assert informe['listo'] is False


@pytest.mark.usefixtures('_sin_entorno_frontend')
@pytest.mark.parametrize('capacidad,driver', sorted(RT.DRIVERS_POR_CAPACIDAD.items()))
def test_quitar_un_driver_avisa_sin_bloquear(tmp_path, capacidad, driver):
    """086:RF-40 — el driver es del equipo y es opcional: el resto del programa sigue."""
    informe = _doctor(tmp_path, drivers=lambda: ())
    fila = _fila(informe, capacidad)
    assert not fila['ok'] and not fila['obligatoria'] and driver in fila['detalle'] and 'Instale' in fila['arreglo']
    assert informe['listo'] is True


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_sin_digsilent_avisa_y_se_puede_convertir(tmp_path):
    """086:RF-40 — sin su API, dice qué se queda sin hacer; convertir a DGS no la necesita."""
    fila = _fila(_doctor(tmp_path), 'digsilent')
    assert not fila['ok'] and not fila['obligatoria'] and 'calibrar' in fila['afecta'] and 'PF_PYTHON' in fila['arreglo']
    (tmp_path / 'pf').mkdir()
    assert 'powerfactory.pyd' in _fila(_doctor(tmp_path, pf=lambda: tmp_path / 'pf'), 'digsilent')['detalle']
    (tmp_path / 'pf' / 'powerfactory.pyd').write_bytes(b'')
    assert _fila(_doctor(tmp_path, pf=lambda: tmp_path / 'pf'), 'digsilent')['ok']


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_doctor_no_conecta_con_digsilent(tmp_path):
    """086:RF-40 — mira si está, sin importar la API: abrir DIgSILENT gastaría licencia."""
    vistos = []

    def importar(nombre):
        vistos.append(nombre)
        return object()

    _doctor(tmp_path, importer=importar)
    assert 'powerfactory' not in vistos


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_sin_interfaz_no_esta_listo(tmp_path):
    """086:RF-40 — sin su compilación, solo respondería la API; y dice cómo compilarla en desarrollo."""
    informe = _doctor(tmp_path)
    (tmp_path / 'programa' / 'frontend' / 'dist' / 'index.html').unlink()
    informe = DR.diagnosticar(importer=_sin(), drivers=lambda: (), version=(3, 12), carpeta_pf=lambda: None, programa=tmp_path / 'programa',
                              buscar_modulo=lambda n: None, buscar_programa=lambda n: None)
    fila = _fila(informe, 'interfaz')
    assert not fila['ok'] and fila['obligatoria'] and informe['listo'] is False and 'npm ci' in fila['arreglo']


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_otro_python_no_esta_listo(tmp_path):
    """086:RF-40 — la API de DIgSILENT solo carga en 3.12."""
    informe = DR.diagnosticar(importer=_sin(), drivers=lambda: (), version=(3, 13), carpeta_pf=lambda: None, programa=tmp_path / 'p',
                              buscar_modulo=lambda n: None, buscar_programa=lambda n: None)
    assert not _fila(informe, 'python')['ok'] and informe['listo'] is False


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_opcionales_ia_y_tesseract(tmp_path):
    """086:RF-40; 086:RF-37 — el complemento de IA y Tesseract avisan, dicen qué afectan, y no bloquean."""
    informe = _doctor(tmp_path)
    for clave, palabra in (('complemento_ia', 'asistente'), ('tesseract', 'escaneado')):
        fila = _fila(informe, clave)
        assert not fila['ok'] and not fila['obligatoria'] and palabra in fila['afecta'] and fila['arreglo']
    otro = _doctor(tmp_path, buscar_modulo=lambda n: object(), buscar_programa=lambda n: 'x')
    assert _fila(otro, 'complemento_ia')['ok'] and _fila(otro, 'tesseract')['ok']


@pytest.mark.usefixtures('_sin_entorno_frontend')
def test_perfil_con_un_error_avisa(tmp_path, monkeypatch):
    """086:RF-40 — un valor imposible afecta a los informes; no impide convertir."""
    malo = tmp_path / 'malo.json'
    malo.write_text(json.dumps({'crs_origen': 5}), encoding='utf-8')
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(malo))
    fila = _fila(_doctor(tmp_path), 'perfil')
    assert not fila['ok'] and not fila['obligatoria'] and 'validar-perfil' in fila['arreglo']


def test_sin_espacio_y_sin_poder_escribir(tmp_path, monkeypatch):
    """086:RF-40 — una carpeta de datos que no se puede usar es imprescindible; poco espacio, un aviso."""
    programa = tmp_path / 'p'
    programa.mkdir()
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'rt'))
    filas = {c.clave: c for c in DR._carpeta_datos(programa, espacio_minimo_mb=1 << 40)}
    assert filas['carpeta_datos'].ok and not filas['espacio_libre'].ok and not filas['espacio_libre'].obligatoria
    (tmp_path / 'fichero').write_text('', encoding='utf-8')
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'fichero' / 'hijo'))
    mala = DR._carpeta_datos(programa)[0]
    assert not mala.ok and mala.obligatoria and 'CSG_DATOS_HOME' in mala.arreglo


def test_orden_doctor(capsys, monkeypatch, tmp_path):
    """086:RF-40 — la orden: texto o JSON, y sale con 1 si falta algo imprescindible."""
    monkeypatch.setattr('convertersmartgrid.web.doctor.diagnosticar',
                        lambda: {'version': 'v', 'listo': False, 'pendientes': 1, 'instalado': False, 'python': '3.12', 'comprobaciones': [
                            {'clave': 'x', 'nombre': 'Cosa', 'ok': False, 'obligatoria': True, 'detalle': 'mal', 'afecta': 'Algo', 'arreglo': 'Hágalo'}]})
    assert cli_main(['doctor']) == 1
    salida = capsys.readouterr().out
    assert 'FALTA' in salida and 'Afecta a: Algo' in salida and 'Cómo arreglarlo: Hágalo' in salida
    assert cli_main(['doctor', '--json']) == 1
    assert json.loads(capsys.readouterr().out)['listo'] is False


def test_pantalla_del_doctor_y_la_version_por_la_api(tmp_path, monkeypatch):
    """086:RF-40; 086:RF-43 — la pantalla pide esto: mismo informe y misma versión que la orden."""
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    with TestClient(create_app(tmp_path / 'web')) as c:
        d = c.get('/api/sistema/diagnostico')
        assert d.status_code == 200, d.text
        assert d.json()['version'] == __version__ and _fila(d.json(), 'interfaz')['ok'] is False
        v = c.get('/api/sistema/version').json()
        assert v['version'] == __version__ and v['notas'] == notas_de_la_version()
        assert c.get('/api/health').json()['version'] == __version__


def test_la_pantalla_muestra_lo_que_dice_el_doctor():
    """086:RF-40; 086:RF-43 — la versión de la cabecera abre las notas y el doctor."""
    texto = (RAIZ / 'frontend/src/components/AcercaDe.tsx').read_text(encoding='utf-8')
    for campo in ('c.afecta', 'c.arreglo', 'c.detalle', 'api.diagnostico', 'api.versionPrograma'):
        assert campo in texto, campo
    assert '<AcercaDe version={health.version}' in (RAIZ / 'frontend/src/App.tsx').read_text(encoding='utf-8')


# --------------------------------------------------------------------------- RF-41: registro rotativo
@pytest.fixture()
def registro_limpio():
    """El registro es global del proceso: al salir, los manejadores se van y sus ficheros se cierran."""
    import convertersmartgrid.registro_rotativo as RR

    antes = {n: list(logging.getLogger(n).handlers) for n in RR._REGISTROS}
    niveles = {n: logging.getLogger(n).level for n in RR._REGISTROS}
    yield RR
    for n in RR._REGISTROS:
        registro = logging.getLogger(n)
        for h in list(registro.handlers):
            if h not in antes[n]:
                registro.removeHandler(h)
        registro.setLevel(niveles[n])
    for h in RR._manejadores.values():
        h.close()
    RR._manejadores.clear()


def test_el_registro_rota_y_conserva_copias(tmp_path, registro_limpio):
    """086:RF-41 — ficheros rotativos, con su tope."""
    ruta = configurar_registro('web', carpeta=tmp_path, tamano=400, copias=2)
    registro = logging.getLogger('convertersmartgrid.prueba')
    for i in range(200):
        registro.warning('línea número %d del registro, con tilde', i)
    ficheros = sorted(p.name for p in tmp_path.iterdir())
    assert ficheros == ['web.log', 'web.log.1', 'web.log.2'], ficheros
    assert all((tmp_path / f).stat().st_size <= 500 for f in ficheros)
    assert 'número 199' in ruta.read_text(encoding='utf-8')


def test_el_registro_recoge_tambien_al_servidor(tmp_path, registro_limpio):
    """086:RF-41 — el fallo real: crear la configuración de uvicorn le quita sus manejadores; volver a llamar los repone sin duplicar."""
    import uvicorn

    ruta = configurar_registro('web', carpeta=tmp_path)
    uvicorn.Config('convertersmartgrid.web.app:create_app', factory=True, log_level='info')
    configurar_registro('web', carpeta=tmp_path)
    logging.getLogger('uvicorn.error').info('servidor en marcha')
    assert ruta.read_text(encoding='utf-8').count('servidor en marcha') == 1


def test_el_registro_sigue_si_otro_proceso_tiene_el_fichero(tmp_path, registro_limpio, capsys):
    """086:RF-41 — dos webs comparten carpeta y Windows no deja renombrar: se sigue escribiendo, sin trazas en la consola."""
    ruta = configurar_registro('web', carpeta=tmp_path, tamano=200, copias=1)
    registro = logging.getLogger('convertersmartgrid.prueba')
    registro.warning('primero')
    with ruta.open('r', encoding='utf-8'):
        for i in range(30):
            registro.warning('línea %d', i)
    registro.warning('final')
    assert 'final' in ''.join(p.read_text(encoding='utf-8') for p in tmp_path.iterdir())
    assert 'PermissionError' not in capsys.readouterr().err


def test_sin_carpeta_para_el_registro_el_programa_sigue(tmp_path, registro_limpio):
    """086:RF-41 — quedarse sin registro no impide convertir."""
    (tmp_path / 'fichero').write_text('', encoding='utf-8')
    assert configurar_registro('web', carpeta=tmp_path / 'fichero' / 'hijo') is None


def test_la_web_y_la_orden_escriben_su_registro():
    """086:RF-41 — los dos puntos de entrada lo configuran."""
    for rel in ('src/convertersmartgrid/web/__main__.py', 'src/convertersmartgrid/cli.py'):
        assert 'configurar_registro(' in (RAIZ / rel).read_text(encoding='utf-8'), rel


def test_el_registro_no_va_en_la_carpeta_del_programa(tmp_path, monkeypatch):
    """086:RF-41; 086:RF-38 — sobrevive a una actualización, y no escribe en una carpeta que puede ser de solo lectura."""
    from convertersmartgrid.registro_rotativo import carpeta_de_registros

    programa = _programa_falso(tmp_path)
    monkeypatch.delenv('CSG_RUNTIME_HOME', raising=False)
    monkeypatch.setenv('CSG_DATOS_HOME', str(tmp_path / 'datos'))
    carpeta = carpeta_de_registros(programa)
    assert carpeta.is_relative_to((tmp_path / 'datos').resolve()) and not carpeta.is_relative_to(programa)


# --------------------------------------------------------------------------- RF-42: paquete de soporte
SECRETOS = {'empresa': 'Compania Inventada del Sur', 'cliente': 'Agricola Tres Vientos', 'alimentador': 'XJ4821', 'ruta': r'D:\Clientes\Secreto\red.txt',
            'correo': 'ana@inventada.example', 'ip': '10.20.30.40', 'usuario': 'ingeniera_ana'}


def _preparar_soporte(tmp_path: Path) -> tuple[Path, Path]:
    registros = tmp_path / 'registros'
    registros.mkdir()
    (registros / 'web.log').write_text(
        f'2026-11-04 INFO convertersmartgrid: Cargado {SECRETOS["ruta"]} del alimentador {SECRETOS["alimentador"]}\n'
        f'2026-11-04 WARNING convertersmartgrid: Cliente «{SECRETOS["cliente"]}» de {SECRETOS["empresa"]}\n'
        f'2026-11-04 ERROR uvicorn.error: fallo desde {SECRETOS["ip"]} avisar a {SECRETOS["correo"]} tras 12,5 s\n'
        f'2026-11-04 INFO convertersmartgrid: usuario {SECRETOS["usuario"]}\n', encoding='utf-8')
    (registros / 'web.log.1').write_text(f'antiguo con {SECRETOS["alimentador"]}\n', encoding='utf-8')
    (registros / 'otra_cosa.xlsx').write_bytes(b'datos de un cliente')
    perfil = tmp_path / 'perfil.json'
    perfil.write_text(json.dumps({'empresa': SECRETOS['empresa'], 'crs_origen': 'EPSG:32718', 'informes': {'firma': SECRETOS['usuario']}}), encoding='utf-8')
    return registros, perfil


INFORME_FALSO = {'version': 'v', 'listo': True, 'pendientes': 1, 'instalado': True, 'python': '3.12',
                 'comprobaciones': [{'clave': 'c', 'nombre': 'Carpeta', 'ok': True, 'obligatoria': True, 'detalle': r'C:\Users\ana\datos',
                                     'afecta': 'Algo', 'arreglo': f'Dé permiso sobre {SECRETOS["ruta"]}'}]}


def test_el_paquete_de_soporte_no_lleva_datos_del_cliente(tmp_path):
    """086:RF-42 — ni un nombre, ruta, código de red, correo o IP, con los registros y el diagnóstico sembrados de ellos."""
    registros, perfil = _preparar_soporte(tmp_path)
    ruta = SP.crear_paquete(tmp_path / 'salida', carpeta_registros=registros, ruta_perfil=perfil, informe=INFORME_FALSO)
    with zipfile.ZipFile(ruta) as z:
        nombres = set(z.namelist())
        textos = {n: z.read(n).decode('utf-8') for n in nombres}
    assert nombres == {'doctor.json', 'perfil_forma.json', 'versiones.json', 'registros/web.log', 'registros/web.log.1', 'LEAME.txt'}
    todo = '\n'.join(textos.values())
    for clave, secreto in SECRETOS.items():
        assert secreto not in todo, clave
    assert 'ana' not in textos['doctor.json']
    # Sigue sirviendo para algo: el mensaje y las cifras se conservan.
    assert 'tras 12,5 s' in textos['registros/web.log'] and 'Cargado' in textos['registros/web.log']
    assert json.loads(textos['perfil_forma.json'])['claves'] == ['crs_origen', 'empresa', 'informes']
    assert 'EPSG' not in textos['perfil_forma.json']


def test_soporte_solo_mete_lo_de_su_lista(tmp_path):
    """086:RF-42 — un espacio de trabajo o un libro junto a los registros no entra: se arma con una lista, no quitando."""
    registros, perfil = _preparar_soporte(tmp_path)
    (registros / 'espacio.json').write_text('{}', encoding='utf-8')
    ruta = SP.crear_paquete(tmp_path / 'salida', carpeta_registros=registros, ruta_perfil=perfil, informe=INFORME_FALSO)
    assert not [n for n in zipfile.ZipFile(ruta).namelist() if 'espacio' in n or n.endswith('.xlsx')]


def test_soporte_sin_registros_ni_perfil(tmp_path):
    """086:RF-42 — en una instalación recién hecha también sale, y dice lo que no hay."""
    ruta = SP.crear_paquete(tmp_path / 's', carpeta_registros=tmp_path / 'no', ruta_perfil=tmp_path / 'no.json', informe=INFORME_FALSO)
    with zipfile.ZipFile(ruta) as z:
        assert json.loads(z.read('perfil_forma.json')) == {'existe': False}


@pytest.mark.parametrize('linea,sale,queda', [
    (r'Abriendo C:\Users\ana\Documents\red.txt ya', r'C:\Users', 'Abriendo'),
    ('Fichero /home/ana/datos/red.txt listo', '/home/ana', 'listo'),
    ('El alimentador AB123 falló', 'AB123', 'falló'),
    ('SET "Las Palmeras" sin datos', 'Palmeras', 'sin datos'),
])
def test_anonimizar(linea, sale, queda):
    """086:RF-42 — rutas de cualquier sistema, códigos y lo entrecomillado."""
    resultado = SP.anonimizar(linea)
    assert sale not in resultado and queda in resultado


def test_orden_soporte(capsys, tmp_path, monkeypatch):
    """086:RF-42 — la orden escribe donde se le dice y recuerda revisarlo: no envía nada."""
    monkeypatch.setattr('convertersmartgrid.web.soporte.diagnosticar', lambda: INFORME_FALSO)
    monkeypatch.setenv('CSG_PERFIL_EMPRESA', str(tmp_path / 'no.json'))
    assert cli_main(['soporte', '--destino', str(tmp_path / 's')]) == 0
    assert 'Revíselo' in capsys.readouterr().out
    assert list((tmp_path / 's').glob('csg-soporte-*.zip'))


def test_soporte_no_abre_la_red():
    """086:RF-42 — se arma en local: el código no sabe enviar nada."""
    arbol = ast.parse((RAIZ / 'src/convertersmartgrid/web/soporte.py').read_text(encoding='utf-8'))
    importados = {a.name.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    importados |= {n.module.split('.')[0] for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module and not n.level}
    assert not importados & {'requests', 'urllib', 'http', 'smtplib', 'httpx'}


# --------------------------------------------------------------------------- RF-43: una sola versión
def _version_en_front(version: str) -> str:
    return re.sub(r'(\d)(a|b|rc)(\d)', lambda m: f'{m[1]}-{ {"a": "alpha", "b": "beta", "rc": "rc"}[m[2]]}.{m[3]}', version)


def test_una_sola_version():
    """086:RF-43 — el paquete la dice; pyproject la lee de ahí, y el front, el lock y el contrato coinciden."""
    proyecto = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'version' not in proyecto['project'] and 'version' in proyecto['project']['dynamic']
    assert proyecto['tool']['setuptools']['dynamic']['version'] == {'attr': 'convertersmartgrid.__version__'}
    front = _version_en_front(__version__)
    assert json.loads((RAIZ / 'frontend/package.json').read_text(encoding='utf-8'))['version'] == front
    lock = json.loads((RAIZ / 'frontend/package-lock.json').read_text(encoding='utf-8'))
    assert lock['version'] == front and lock['packages']['']['version'] == front
    assert json.loads((RAIZ / 'docs/asistente/openapi.json').read_text(encoding='utf-8'))['info']['version'] == __version__


def test_la_rueda_lleva_esa_version(rueda):
    """086:RF-43 — la del nombre del fichero y la de sus metadatos."""
    assert rueda.name.split('-')[1] == __version__
    with zipfile.ZipFile(rueda) as z:
        meta = z.read(next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))).decode('utf-8')
    assert f'Version: {__version__}\n' in meta.replace('\r\n', '\n')


def test_notas_de_la_version():
    """086:RF-43 — hay notas, y hablan de esta versión."""
    assert __version__ in notas_de_la_version()


def test_orden_version(capsys):
    """086:RF-43 — la orden dice versión y notas."""
    assert cli_main(['version']) == 0
    salida = capsys.readouterr().out
    assert __version__ in salida and 'Notas' in salida


def test_ensayar_otra_version(tmp_path, manifiesto, terminos):
    """086:RF-43 — construir con otra versión solo cambia ese dato: es como se ensaya una actualización."""
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<!doctype html>', encoding='utf-8')
    arbol = tmp_path / 'arbol'
    CC.preparar_arbol(RAIZ, arbol, manifiesto, terminos, version='7.7.7', dist=dist)
    assert "__version__ = '7.7.7'" in (arbol / 'src/convertersmartgrid/__init__.py').read_text(encoding='utf-8')
    assert (arbol / 'src/convertersmartgrid/_programa/tools/cargas_pf.py').is_file()
    assert not (arbol / 'src/convertersmartgrid/_programa/tests').exists()
    # El README del repositorio habla de casos reales: a los metadatos de la rueda va otro.
    assert (arbol / 'README.md').read_text(encoding='utf-8') == CC._LEEME_RUEDA


# --------------------------------------------------------------------------- RF-44: documentos
def test_los_documentos_existen_y_no_llevan_nombres(terminos):
    """086:RF-44 — manuales, hoja de seguridad y lista de IA, y pasan la misma lista de términos que el código."""
    for rel in CC.DOCUMENTOS:
        ruta = RAIZ / rel
        assert ruta.is_file(), rel
        assert not CE.buscar_en_texto(rel, ruta.read_text(encoding='utf-8'), terminos), rel


def test_el_manual_cita_ordenes_que_existen():
    """086:RF-44 — el manual dice `csg.cmd doctor`: lo que cita tiene que responder."""
    ordenes = _parser()._subparsers._group_actions[0].choices
    for orden in ('doctor', 'soporte', 'validar-perfil', 'version', 'web', 'convert'):
        assert orden in ordenes, orden
    manual = (RAIZ / 'docs/MANUAL_INSTALACION.md').read_text(encoding='utf-8')
    for texto in ('csg.cmd" doctor', 'csg.cmd soporte', 'volver_atras.cmd', 'copia_datos.cmd', 'CSG_DATOS_HOME', 'requirements-complemento-ia.txt'):
        assert texto in manual, texto


def test_la_hoja_de_seguridad_dice_cada_salida_a_la_red():
    """086:RF-44; 086:RF-22 — una salida declarada en el código y no en la hoja sería una omisión ante el cliente."""
    from convertersmartgrid.salidas_red import SALIDAS

    hoja = (RAIZ / 'docs/SEGURIDAD_Y_PRIVACIDAD.md').read_text(encoding='utf-8')
    faltan = [s.variable for s in SALIDAS.values() if s.variable not in hoja]
    assert not faltan, faltan


def test_manual_de_comandos_sin_ordenes_rotas():
    """086:RF-44 — el fallo real: un heredoc dejó bytes de control donde había `tools\\b…` y `tools\\a…`."""
    crudo = (RAIZ / 'docs/MANUAL_COMANDOS.md').read_bytes()
    assert not re.search(rb'[\x00-\x08\x0b\x0c\x0e-\x1f]', crudo)
    texto = crudo.decode('utf-8')
    citadas = set(re.findall(r'tools[\\/]([A-Za-z_0-9]+\.py)', texto))
    assert citadas
    assert not [c for c in sorted(citadas) if not (RAIZ / 'tools' / c).is_file()]


def test_el_readme_no_dice_lo_de_antes():
    """086:RF-44 — ni que el lanzador instala, ni la orden sin lock, ni el motor de hace un año en el título."""
    texto = (RAIZ / 'README.md').read_text(encoding='utf-8')
    assert 'npm install' not in texto and 'instala `requirements.txt` si faltan' not in texto
    assert texto.startswith('# ConverterSmartGrid') and 'MANUAL_INSTALACION.md' in texto
    assert 'npm install' not in (RAIZ / 'docs/MANUAL_DE_USO.md').read_text(encoding='utf-8')


def _rueda_de_terceros(tmp_path: Path, nombre: str, **meta) -> Path:
    ruta = tmp_path / f'{nombre}-1.0-py3-none-any.whl'
    cabecera = f'Metadata-Version: 2.4\nName: {nombre}\nVersion: 1.0\n' + ''.join(f'{k}: {v}\n' for k, v in meta.items())
    with zipfile.ZipFile(ruta, 'w') as z:
        z.writestr(f'{nombre}-1.0.dist-info/METADATA', cabecera)
        z.writestr(f'{nombre}-1.0.dist-info/licenses/LICENSE', 'Texto de la licencia')
    return ruta


def test_inventario_de_terceros(tmp_path):
    """086:RF-44 — licencia y texto, de cualquier forma en que la rueda los declare; lo que no declara se ve, no se supone."""
    meta, textos = CC.leer_metadatos_de_rueda(_rueda_de_terceros(tmp_path, 'a', **{'License-Expression': 'MIT'}))
    assert meta['license'] == 'MIT' and textos[0][1] == 'Texto de la licencia'
    assert CC.leer_metadatos_de_rueda(_rueda_de_terceros(tmp_path, 'b', Classifier='License :: OSI Approved :: BSD License'))[0]['license'] == 'BSD License'
    assert CC.leer_metadatos_de_rueda(_rueda_de_terceros(tmp_path, 'c'))[0]['license'] == 'desconocida'
    bom = CC.sbom([{**meta, 'sha256': 'ab'}], '1', 'rev')
    assert bom['bomFormat'] == 'CycloneDX' and bom['components'][0]['purl'] == 'pkg:pypi/a@1.0'
    assert bom['components'][0]['hashes'] == [{'alg': 'SHA-256', 'content': 'ab'}]
    avisos = CC._avisos([meta], {'a 1.0': textos})
    assert 'a 1.0' in avisos and 'Texto de la licencia' in avisos and 'no es una opinión legal' in avisos


def test_python_embebido_solo_el_312(tmp_path):
    """086:RF-36 — con otro, la API de DIgSILENT no carga y no se ve hasta la primera importación."""
    with pytest.raises(CE.EntregaError, match='3.12'):
        CC.extraer_python(tmp_path / 'python-3.13.1-embed-amd64.zip', tmp_path / 'p')


def test_sin_pth_el_python_embebido_lee_pythonpath(tmp_path):
    """086:RF-36 — el fallo evitado: con `._pth`, un guion no encontraría la API de DIgSILENT, que le llega por PYTHONPATH."""
    z = tmp_path / 'python-3.12.10-embed-amd64.zip'
    with zipfile.ZipFile(z, 'w') as f:
        f.writestr('python.exe', '')
        f.writestr('python312._pth', 'python312.zip\n.\n')
    assert CC.extraer_python(z, tmp_path / 'p') == '3.12.10'
    assert not list((tmp_path / 'p').glob('*._pth')) and (tmp_path / 'p' / 'Lib' / 'site-packages').is_dir()


def test_el_guion_del_instalador_no_sale_a_internet():
    """086:RF-36; 086:RF-39 — el .iss solo copia su candidato y llama a instalar_candidato.py; por usuario, y sin borrar datos."""
    iss = (RAIZ / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    assert 'PrivilegesRequired=lowest' in iss and 'instalar_candidato.py' in iss
    assert not re.search(r'https?://|DownloadTemporaryFile|pip install|npm', iss, flags=re.I)
    borra = [l for l in iss.splitlines() if l.startswith('Type:')]
    assert borra and all('{app}' in l for l in borra), 'desinstalar no toca la carpeta de datos'


def test_avisos_del_front_con_textos_y_huellas_del_lock(tmp_path):
    """086:RF-39 — el candidato conserva el texto íntegro de cada dependencia compilada."""
    front = tmp_path / 'frontend'
    licenses = front / 'licencias'
    licenses.mkdir(parents=True)
    texto = 'Permiso completo de ejemplo.\n'
    (licenses / 'MIT.txt').write_text(texto, encoding='utf-8')
    paquete = {'name':'ejemplo','version':'1.0.0','integrity':'sha512-origen',
               'license_file':'MIT.txt','license_sha256':hashlib.sha256((licenses / 'MIT.txt').read_bytes()).hexdigest()}
    (licenses / 'manifest.json').write_text(json.dumps({'packages':[paquete]}), encoding='utf-8')
    (front / 'package-lock.json').write_text(json.dumps({'packages':{
        'node_modules/ejemplo':{'version':'1.0.0','integrity':'sha512-origen','license':'MIT'}}}), encoding='utf-8')
    componentes = CC._componentes_del_front(tmp_path)
    textos = CC._licencias_del_front(tmp_path, componentes)
    assert texto.strip() in CC._avisos(componentes, textos)
    assert 'ejemplo 1.0.0' in textos
    (licenses / 'MIT.txt').write_text('alterado', encoding='utf-8')
    with pytest.raises(CE.EntregaError, match='huella|licencia'):
        CC._licencias_del_front(tmp_path, componentes)


def test_licencias_del_front_no_aceptan_un_lock_distinto(tmp_path):
    """086:RF-39 — actualizar una dependencia obliga a revisar sus avisos, sin descargar en el build."""
    shutil.copytree(RAIZ / 'frontend/licencias', tmp_path / 'frontend/licencias')
    lock = json.loads((RAIZ / 'frontend/package-lock.json').read_text(encoding='utf-8'))
    lock['packages']['node_modules/react']['version'] = '999.0.0'
    (tmp_path / 'frontend/package-lock.json').write_text(json.dumps(lock), encoding='utf-8')
    with pytest.raises(CE.EntregaError, match='licencia|versión|lock'):
        CC._licencias_del_front(tmp_path, CC._componentes_del_front(tmp_path))


def test_avisos_incluyen_licencia_embebida_con_prefijo(tmp_path):
    """086:RF-44 — MIT-LICENSE se recoge como LICENSE, sin perder el texto del titular."""
    rueda = tmp_path / 'ejemplo-1.0-py3-none-any.whl'
    nombre = 'ejemplo-1.0.dist-info/licenses/MIT-LICENSE'
    texto = 'Copyright titular de prueba\nTexto de licencia del contrato.\n'
    with zipfile.ZipFile(rueda, 'w') as z:
        z.writestr('ejemplo-1.0.dist-info/METADATA',
                   'Name: ejemplo\nVersion: 1.0\nLicense-Expression: MIT\n')
        z.writestr(nombre, texto)
    meta, textos = CC.leer_metadatos_de_rueda(rueda)
    assert meta['license'] == 'MIT'
    assert (nombre, texto) in textos


def test_inventario_front_incluye_transitivas_de_ejecucion(tmp_path):
    """086:RF-44 — una dependencia compilada transitiva no desaparece del inventario."""
    front = tmp_path / 'frontend'
    front.mkdir()
    (front / 'package.json').write_text(json.dumps({'dependencies': {'react-dom': '19.3.0'}}), encoding='utf-8')
    (front / 'package-lock.json').write_text(json.dumps({'packages': {
        '': {'dependencies': {'react-dom': '19.3.0'}},
        'node_modules/react-dom': {'version': '19.3.0', 'license': 'MIT', 'dependencies': {'scheduler': '0.28.0'}},
        'node_modules/scheduler': {'version': '0.28.0', 'license': 'MIT'},
        'node_modules/vite': {'version': '6.4.0', 'license': 'MIT', 'dev': True},
    }}), encoding='utf-8')
    componentes = CC._componentes_del_front(tmp_path)
    assert {c['name'] for c in componentes} == {'react-dom', 'scheduler'}
    assert all(c['license'] == 'MIT' and c['origen'] == 'front' for c in componentes)
