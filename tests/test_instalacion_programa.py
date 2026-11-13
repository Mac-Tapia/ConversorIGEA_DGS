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
def test_rueda_incluye_adaptador_vnr_y_ambos_launchers_sin_instalar(rueda, tmp_path):
    """002:RF-6/22; 086:RF-36: la rueda real conserva el CLI sin depender del checkout."""
    import configparser

    with zipfile.ZipFile(rueda) as z:
        nombres = z.namelist()
        assert 'vnr_etl.py' in nombres
        assert not any(n.startswith('vnr_etl/') for n in nombres)
        assert 'convertersmartgrid/adaptadores/entrada/vnr/models/canonical.py' in nombres
        assert 'convertersmartgrid/adaptadores/entrada/vnr/cli.py' in nombres
        assert sum(n.startswith('convertersmartgrid/adaptadores/entrada/vnr/') and n.endswith('.py')
                   for n in nombres) == 50
        cfg = configparser.ConfigParser()
        cfg.read_string(z.read(next(n for n in nombres if n.endswith('.dist-info/entry_points.txt'))).decode('utf-8'))
        nuevo = cfg['console_scripts']['vnr-etl']
        assert nuevo == 'convertersmartgrid.adaptadores.entrada.vnr.cli:main'
        declarados = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))[
            'project']['entry-points']['convertersmartgrid.modulos']
        assert dict(cfg['convertersmartgrid.modulos']) == declarados
    for destino in (nuevo, 'vnr_etl.cli:main'):
        codigo = (
            'from importlib.metadata import EntryPoint\n'
            f"main = EntryPoint(name='vnr-etl', value={destino!r}, group='console_scripts').load()\n"
            'import sys\n'
            "assert '.whl' in sys.modules[main.__module__].__file__\n"
            "raise SystemExit(main(['--version']))\n"
        )
        assert 'vnr_etl 1.6.0' in _en_el_programa(rueda, tmp_path, codigo)
    env = {**os.environ, 'PYTHONPATH': str(rueda)}
    r = subprocess.run([sys.executable, '-B', '-m', 'vnr_etl', '--help'], cwd=tmp_path,
                       env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and 'ETL universal' in r.stdout, r.stdout + r.stderr


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
from convertersmartgrid.adaptadores.entrada.vnr.application.services import VnrApplicationService
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


def test_rechazar_version_preexistente_conserva_arbol_y_punteros(tmp_path, monkeypatch):
    """086:RF-38/39: rechazar rc6 retenida tras rollback no autoriza a borrarla."""
    destino = tmp_path / 'app'
    retenida = destino / 'versiones' / '1.0.0rc6'
    retenida.mkdir(parents=True)
    (retenida / 'testigo.bin').write_bytes(b'version retenida propia; conservar')
    anterior = destino / 'versiones' / '1.0.0rc5'
    anterior.mkdir()
    (anterior / 'testigo.bin').write_bytes(b'base de rollback propia')
    for nombre, contenido in (('actual.txt', '1.0.0rc5'), ('anterior.txt', '1.0.0rc6'),
                               ('ultima_copia.json', '{"copia":"propia"}'), ('csg.cmd', 'lanzador previo')):
        (destino / nombre).write_text(contenido, encoding='utf-8')
    antes = {p.relative_to(destino).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in destino.rglob('*') if p.is_file()}
    monkeypatch.setattr(IC, '_web_escuchando', lambda *a: False)
    with pytest.raises(IC.ErrorInstalacion, match='ya está'):
        IC.instalar(_candidato(tmp_path, '1.0.0rc6'), destino)
    despues = {p.relative_to(destino).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in destino.rglob('*') if p.is_file()}
    assert despues == antes, 'el rechazo no debe retirar la versión preexistente ni cambiar punteros'


def test_preparar_version_fallida_retira_solo_su_propia_creacion(tmp_path):
    """086:RF-38/39: el preparador limpia su reserva exclusiva al fallar, sin pip ni entorno nuevo."""
    candidato = _candidato(tmp_path, '1.0.0rc6')
    (candidato / 'terceros' / 'python').mkdir()
    (candidato / 'terceros' / 'python' / 'testigo.txt').write_text('fixture propia', encoding='utf-8')
    destino = tmp_path / 'app'
    with pytest.raises(IC.ErrorInstalacion, match='pip'):
        IC._preparar_version(candidato, destino, {'version': '1.0.0rc6'})
    assert not (destino / 'versiones' / '1.0.0rc6').exists()


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
    # 086:RF-100: la que se deja no pasa a ser la anterior; volver otra vez no alterna entre las dos. Su programa se aparta.
    assert IC.estado(destino) == {'actual': '1.0', 'anterior': None, 'versiones': ['1.0', '1.1']}


def test_volver_usa_el_lector_actual_para_su_formato_de_copia(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-38 — la versión anterior puede desconocer el formato que guardó la actual."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato(tmp_path, '1.0'), destino)
    IC.instalar(_candidato(tmp_path, '1.1'), destino)
    calls = []
    class Result:
        stdout = '{}'
        stderr = 'La versión anterior desconoce el formato nuevo'
        returncode = 0
    def restore(command, **_kwargs):
        calls.append(command)
        result = Result()
        result.returncode = 0 if Path(command[0]) == IC._python_de(destino, '1.1') else 1
        return result
    monkeypatch.setattr(IC.subprocess, 'run', restore)
    result = IC.volver(destino)
    assert result['version'] == '1.0'
    assert calls and Path(calls[0][0]) == IC._python_de(destino, '1.1')


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
    texto = (RAIZ / 'frontend/src/app/AcercaDe.tsx').read_text(encoding='utf-8')
    for campo in ('c.afecta', 'c.arreglo', 'c.detalle', 'api.diagnostico', 'api.versionPrograma'):
        assert campo in texto, campo
    assert '<AcercaDe version={health.version}' in (RAIZ / 'frontend/src/app/App.tsx').read_text(encoding='utf-8')


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


def test_086_rf60_digsilent_bien_escrito():
    """086:RF-60 — «DIgSILENT», con la I mayúscula, en la web, el registro, el código y los manuales.

    rc5 (2026-11-12): el botón «Cargar en … + flujo» y el registro «--- Fin … ---» lo escribían con la i minúscula. Los nombres en
    mayúsculas o minúsculas enteras (``TANDA_DIGSILENT``, ``confirmar_en_digsilent``) son identificadores, no texto.
    """
    errata = re.compile('Dig' + r'(?:SILENT|[Ss]ilent)')
    ficheros = [p for carpeta in ('frontend/src', 'src/convertersmartgrid', 'tools', 'tests', 'instalador')
                for p in (RAIZ / carpeta).rglob('*') if p.is_file() and p.suffix in {'.py', '.ts', '.tsx', '.iss', '.bat', '.cmd', '.md'}]
    ficheros += [RAIZ / 'README.md', *sorted((RAIZ / 'docs').glob('*.md'))]
    con_errata = [f'{p.relative_to(RAIZ).as_posix()}:{n}' for p in ficheros
                  for n, linea in enumerate(p.read_text(encoding='utf-8', errors='replace').splitlines(), 1) if errata.search(linea)]
    assert not con_errata, con_errata


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


def test_complemento_separado_con_huellas_y_rechazo_de_alteracion(tmp_path, monkeypatch):
    """086:RF-37, 086:RF-39 — paquete separado verificable; una rueda alterada se rechaza."""
    source = tmp_path / 'fuente'
    source.mkdir()
    (source / 'requirements-complemento-ia.txt').write_text('torch==1.0\n', encoding='utf-8')
    (source / 'requirements-nucleo.lock').write_text('pip==1.0 ' + chr(92) + '\n --hash=sha256:' + 'a' * 64 + '\n', encoding='utf-8')
    cache = tmp_path / 'cache'
    cache.mkdir()
    wheel = _rueda_de_terceros(cache, 'torch', **{'License-Expression':'BSD-3-Clause'})
    def descargar(*args):
        destino = Path(args[args.index('-d') + 1])
        shutil.copyfile(wheel, destino / wheel.name)
    monkeypatch.setattr(CC, '_pip', descargar)
    salida = tmp_path / 'complemento'
    manifest = CC.construir_complemento_ia(source, salida, cache=cache, version='1.0.0rc3')
    assert manifest['tipo'] == 'complemento-ia' and manifest['pesos_del_proyecto_incluidos'] is False
    assert '--hash=sha256:' in (salida / 'instalacion.lock').read_text(encoding='utf-8')
    assert 'Texto de la licencia' in (salida / 'THIRD_PARTY_NOTICES.txt').read_text(encoding='utf-8')
    assert 'sin pruebas ni torch' not in (salida / 'instalacion.lock').read_text(encoding='utf-8')
    assert IC.verificar_candidato(salida)['version'] == '1.0.0rc3'
    (salida / 'wheels' / wheel.name).write_bytes(b'alterado')
    with pytest.raises(IC.ErrorInstalacion, match='alterado'):
        IC.verificar_candidato(salida)
    witness = salida / 'conservar.txt'
    witness.write_text('original', encoding='utf-8')
    with pytest.raises(CE.EntregaError, match='vacía'):
        CC.construir_complemento_ia(source, salida, cache=cache, version='1.0.0rc3')
    assert witness.read_text(encoding='utf-8') == 'original'


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


def test_086_rf57_el_motivo_del_fallo_queda_en_su_fichero(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-57 — con --registro, el motivo por el que no se instala queda en un fichero que el .iss puede leer.

    rc5 (2026-11-12): con /VERYSILENT el registro de Inno solo decía «Resultado: 1»; el motivo, el programa abierto en
    el puerto 8765, salía por la consola oculta y se perdía.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato(tmp_path, '1.0'), destino)
    monkeypatch.setattr(IC, '_web_escuchando', lambda puerto: True)
    motivo = tmp_path / 'motivo.txt'
    assert IC.main(['instalar', '--candidato', str(_candidato(tmp_path, '1.1')), '--destino', str(destino),
                    '--registro', str(motivo)]) == 1
    assert motivo.read_bytes().startswith('﻿'.encode('utf-8')), 'Inno lee el UTF-8 sin dudas con su BOM'
    assert 'abierto en el puerto 8765' in motivo.read_text(encoding='utf-8-sig')
    monkeypatch.setattr(IC, '_web_escuchando', lambda puerto: False)
    assert IC.main(['instalar', '--candidato', str(_candidato(tmp_path, '1.2')), '--destino', str(destino),
                    '--registro', str(motivo)]) == 0
    assert not motivo.exists(), 'un motivo viejo no puede pasar por el de una instalación que salió bien'


def _codigo_del_iss() -> str:
    return (RAIZ / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8').split('[Code]', 1)[1]


def test_086_rf57_el_iss_pasa_el_fichero_y_dice_su_motivo():
    """086:RF-57 — el .iss pide el motivo con --registro, lo lee y lo pone en su registro y en el aviso, también en silencio."""
    codigo = _codigo_del_iss()
    fichero = re.search(r"FicheroMotivo\s*=\s*'([^']+)'", codigo)
    assert fichero, 'el nombre del fichero del motivo, en un solo sitio'
    llamada = re.search(r"Exec\(.*?instalar_candidato\.py.*?CodigoProceso\)", codigo, flags=re.S)
    assert llamada and '--registro' in llamada.group(0) and 'FicheroMotivo' in llamada.group(0)
    assert re.search(r"LoadStringsFromFile\(ExpandConstant\('\{tmp\}\\' \+ FicheroMotivo\)", codigo)
    assert re.search(r"Log\([^;]*Motivo", codigo), 'el motivo va al registro de Inno'
    aviso = re.search(r"SuppressibleMsgBox\([^;]*Motivo[^;]*;", codigo, flags=re.S)
    assert aviso, 'el aviso al operador lleva el motivo'
    assert 'if not WizardSilent then' not in codigo, ('con /VERYSILENT también se avisa; quien automatiza lo calla con '
                                                     '/SUPPRESSMSGBOXES')


def test_086_rf58_no_se_reutiliza_una_carpeta_temporal_o_vacia():
    """086:RF-58 — quien actualiza sigue en su carpeta; una carpeta en la temporal o sin el programa no se reutiliza.

    rc5 (2026-11-12): Inno reutilizó la carpeta registrada por un ensayo del rc1, %TEMP%\\csgp, y el programa quedó allí.
    """
    iss = (RAIZ / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    assert re.search(r'^UsePreviousAppDir=yes$', iss, flags=re.M), 'una actualización válida sigue en su carpeta'
    codigo = _codigo_del_iss()
    inicio = re.search(r'procedure InitializeWizard;.*?\nend;', codigo, flags=re.S)
    assert inicio, 'la carpeta se revisa al abrir el asistente, antes de instalar'
    cuerpo = inicio.group(0)
    assert "{param:DIR|}" in cuerpo, 'la carpeta pedida con /DIR manda'
    assert "GetEnv('TEMP')" in cuerpo and "{localappdata}\\Temp" in cuerpo, 'la temporal, con su nombre corto o largo'
    assert "'actual.txt'" in cuerpo, 'una carpeta sin el puntero de versión ya no tiene el programa'
    assert "WizardForm.DirEdit.Text := ExpandConstant('{#DirectorioApp}')" in cuerpo
    assert re.search(r'Log\(', cuerpo), 'el cambio de carpeta queda anotado'


def test_subprocesos_del_instalador_no_importan_modulos_del_directorio_actual(tmp_path, monkeypatch):
    """086:RF-39 — pip y doctor tampoco importan un json.py ajeno desde su directorio de trabajo."""
    monkeypatch.delenv('PYTHONSAFEPATH', raising=False)
    witness = tmp_path / 'importado.txt'
    (tmp_path / 'json.py').write_text(
        'from pathlib import Path\nPath(__file__).with_name("importado.txt").write_text("ejecutado")\n'
        'raise RuntimeError("modulo del directorio actual")\n', encoding='utf-8')
    python = Path(sys._base_executable)
    result = subprocess.run([str(python),'-B','-c','import json;print(json.dumps({"ok":True}))'],
        cwd=tmp_path, env=IC._entorno_limpio(python), capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'ok':True}
    assert not witness.exists()


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


def test_086_rf55_el_doctor_avisa_un_perfil_sin_fichas_ni_bancos(tmp_path, monkeypatch):
    """086:RF-55 — sin fichas de transformadores ni bancos por tensión, aviso con lo que afecta; con ellas, bien."""
    import json

    from convertersmartgrid.perfil_empresa import VARIABLE_RUTA

    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text(json.dumps({'calibracion': {'bancos_kvar_por_tension': None, 'transformadores_sed': None}}),
                      encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))
    c = DR._calibracion_del_perfil()
    # 020:RF-63: las fichas del conversor cubren las que faltan en el perfil; solo faltan los bancos.
    assert not c.ok and not c.obligatoria and 'transformadores_sed' not in c.detalle and 'bancos_kvar_por_tension' in c.detalle
    assert 'NTP 370.400' in c.arreglo and 'SED sobrecargada' in c.afecta
    perfil.write_text(json.dumps({'calibracion': {'bancos_kvar_por_tension': {'10': 300},
                                                  'transformadores_sed': {'tablas': [{'fichas': {'50': [1, 2, 3, 4]}}]}}}),
                      encoding='utf-8')
    assert DR._calibracion_del_perfil().ok


def test_020_rf63_las_fichas_del_conversor_cuando_el_perfil_no_las_trae(tmp_path, monkeypatch):
    """020:RF-63 — sin fichas en el perfil, las NTP 370.400 del conversor (con su origen); con fichas propias, las suyas."""
    import json

    from convertersmartgrid.perfil_empresa import VARIABLE_RUTA, seccion_transformadores_sed, transformadores_sed

    perfil = tmp_path / 'perfil_empresa.json'
    perfil.write_text('{}', encoding='utf-8')
    monkeypatch.setenv(VARIABLE_RUTA, str(perfil))
    del_conversor = seccion_transformadores_sed()
    assert del_conversor['origen'] == 'conversor' and len(del_conversor['tablas']) == 2
    assert all('NTP 370.400' in t['norma'] for t in del_conversor['tablas'])
    leidas = transformadores_sed({'calibracion': {'transformadores_sed': del_conversor}})   # la misma lectura que la calibración
    assert leidas and leidas['tablas'] and not leidas['avisos']
    propia = {'umbral_carga_pct': 70, 'tablas': [{'norma': 'propia', 'kv_min': 0, 'kv_max': 36, 'fichas': {'50': '1 2 3 4'}}]}
    perfil.write_text(json.dumps({'calibracion': {'transformadores_sed': propia}}), encoding='utf-8')
    assert seccion_transformadores_sed() == propia


# --------------------------------------------------------------------------- 1.0: manuales, versión y vuelta atrás (2026-11-13)
def _seccion_del_iss(nombre: str) -> list[str]:
    """Las líneas de una sección del .iss, sin comentarios."""
    texto = (RAIZ / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    bloque = re.search(rf'^\[{re.escape(nombre)}\]\n(.*?)(?=^\[|\Z)', texto, flags=re.M | re.S)
    return [l for l in (bloque.group(1).splitlines() if bloque else ()) if l.strip() and not l.lstrip().startswith(';')]


def test_086_rf89_el_iss_instala_los_documentos_fuera_de_la_entrega():
    """086:RF-89, 086:RF-97 — los documentos llegan con el candidato a «_entrega» y los publica instalar_candidato.py.

    rc5 (2026-11-12): el candidato se copiaba a {app}\\_entrega con «deleteafterinstall» y los manuales se iban con él.
    Inno procesa [InstallDelete] y [Files] antes de ssPostInstall: si el .iss vaciara o copiara {app}\\documentos, una
    instalación que luego falla dejaría al programa anterior sin sus documentos, o con los de la versión nueva.
    """
    assert not [l for l in _seccion_del_iss('Files') if 'documentos' in l], 'el .iss no copia los documentos por su cuenta'
    assert not [l for l in _seccion_del_iss('InstallDelete') if 'documentos' in l], 'ni los borra antes de saber si se instala'
    desinstalar = ' '.join(_seccion_del_iss('UninstallDelete'))
    for carpeta in ('documentos', 'documentos.preparando', 'documentos.anterior', 'documentos.retirar'):
        assert f'Name: "{{app}}\\{carpeta}"' in desinstalar, carpeta


def test_086_rf90_el_menu_inicio_abre_el_manual_de_instalacion():
    """086:RF-90 — un acceso en el menú Inicio al manual de instalación instalado, que abre el Bloc de notas de Windows."""
    accesos = [l for l in _seccion_del_iss('Icons') if 'MANUAL_INSTALACION.md' in l]
    assert len(accesos) == 1, _seccion_del_iss('Icons')
    acceso = accesos[0]
    assert acceso.startswith('Name: "{autoprograms}\\')
    assert '{app}\\documentos\\MANUAL_INSTALACION.md' in acceso
    assert 'Filename: "{win}\\notepad.exe"' in acceso, 'un Windows limpio no tiene programa asociado a «.md»'


def _raiz_de_mentira(tmp_path: Path, version: str, *, faltan: tuple[str, ...] = ()) -> Path:
    """Un árbol con solo lo que el candidato copia a «documentos/», y ficheros de mentira."""
    raiz = tmp_path / 'raiz'
    for rel in CC.documentos_del_candidato(version):
        if rel not in faltan:
            (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
            (raiz / rel).write_text(f'De mentira: {rel}\n', encoding='utf-8')
    return raiz


def test_086_rf89_el_candidato_lleva_los_manuales_y_las_notas_de_su_version(tmp_path):
    """086:RF-89 — el candidato lleva los cuatro documentos que se instalan; las notas, las de la publicación de su versión."""
    assert CC.publicacion('1.0.0rc6') == '1.0.0' and CC.publicacion('1.0.0') == '1.0.0' and CC.publicacion('2.1.3rc1') == '2.1.3'
    pedidos = set(CC.documentos_del_candidato('1.0.0rc6'))
    assert {'docs/MANUAL_INSTALACION.md', 'docs/MANUAL_COMANDOS.md', 'docs/GUIA_PRUEBA_PERSONA_AJENA.md',
            'docs/NOTAS_VERSION_1.0.0.md'} <= pedidos
    assert set(CC.DOCUMENTOS) <= pedidos
    raiz = _raiz_de_mentira(tmp_path, '1.0.0rc6')
    destino = tmp_path / 'documentos'
    CC.copiar_documentos(raiz, destino, '1.0.0rc6')
    assert {p.name for p in destino.iterdir()} == {Path(r).name for r in pedidos}
    assert (destino / 'NOTAS_VERSION_1.0.0.md').read_text(encoding='utf-8') == 'De mentira: docs/NOTAS_VERSION_1.0.0.md\n'


def test_086_rf91_sin_un_manual_no_se_arma_el_candidato(tmp_path):
    """086:RF-91 — si falta un documento que se instala, el candidato no se arma, y se dice cuál falta."""
    raiz = _raiz_de_mentira(tmp_path, '1.0.0rc6', faltan=('docs/GUIA_PRUEBA_PERSONA_AJENA.md', 'docs/NOTAS_VERSION_1.0.0.md'))
    with pytest.raises(CE.EntregaError, match=r'GUIA_PRUEBA_PERSONA_AJENA\.md.*NOTAS_VERSION_1\.0\.0\.md'):
        CC.copiar_documentos(raiz, tmp_path / 'documentos', '1.0.0rc6')
    assert not (tmp_path / 'documentos').exists(), 'nada a medias'


def test_086_rf92_la_version_sale_de_un_solo_sitio():
    """086:RF-92 — pyproject, el constructor del candidato y el .iss toman la versión del paquete, sin escribirla otra vez.

    rc5 (2026-11-12): el paquete decía 1.0.0rc1, el candidato se armó con «--version 1.0.0rc5» y el .iss la recibió a mano
    con «/DVersion»: tres sitios para un dato.
    """
    pyproject = tomllib.loads((RAIZ / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'version' not in pyproject['project'] and 'version' in pyproject['project']['dynamic']
    assert pyproject['tool']['setuptools']['dynamic']['version'] == {'attr': 'convertersmartgrid.__version__'}
    assert CC.version_del_paquete(RAIZ) == __version__
    iss = (RAIZ / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    assert not re.search(r'\d+\.\d+\.\d+', iss), 'ninguna versión escrita en el .iss'
    assert re.search(r'^#ifdef Version\s*\n\s*#error', iss, flags=re.M), 'pasarla con /DVersion sería un segundo sitio'
    # La versión del .iss es la de la rueda del candidato, que la toma del paquete.
    assert re.search(r'FindFirst\(.*"programa\\" \+ PrefijoRueda \+ "\*\.whl"', iss)
    assert re.search(r'^#define Version ', iss, flags=re.M)
    assert re.search(r'^AppVersion=\{#Version\}$', iss, flags=re.M)


def test_086_rf92_la_version_del_iss_es_la_de_la_rueda():
    """086:RF-92 — lo que el preprocesador de Inno saca del nombre de la rueda es la versión del paquete.

    Se repite en Python la misma cuenta del .iss (Copy, Pos y Len de ISPP, base 1) sobre el nombre que da setuptools.
    """
    iss = (RAIZ / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    prefijo = re.search(r'#define PrefijoRueda "([^"]+)"', iss).group(1)
    assert re.search(r'#define RestoRueda Copy\(Rueda, Len\(PrefijoRueda\) \+ 1\)', iss)
    assert re.search(r'#define Version Copy\(RestoRueda, 1, Pos\("-", RestoRueda\) - 1\)', iss)
    rueda = f'{prefijo}{__version__}-py3-none-any.whl'
    resto = rueda[len(prefijo):]                                   # Copy(Rueda, Len(PrefijoRueda) + 1)
    assert resto[:resto.index('-')] == __version__                 # Copy(Resto, 1, Pos("-", Resto) - 1)
    assert prefijo == 'convertersmartgrid-'


def test_086_rf93_acerca_de_muestra_las_notas_de_la_version_instalada():
    """086:RF-93 — las notas del paquete empiezan por su versión, y «Acerca de» solo enseña esa.

    rc5 (2026-11-12): «Acerca de» del rc5 instalado decía «1.0.0rc1 (candidata, sin aceptar)».
    """
    texto = (RAIZ / 'src/convertersmartgrid/recursos/NOTAS_VERSION.md').read_text(encoding='utf-8')
    apartados = re.findall(r'^## (\S+)', texto, flags=re.M)
    assert apartados and apartados[0] == __version__, apartados
    notas = notas_de_la_version()
    assert f'## {__version__}' in notas
    assert not [v for v in apartados[1:] if f'## {v}' in notas], 'las de otras versiones no se enseñan'


def test_086_rf93_sin_notas_de_su_version_no_se_arma():
    """086:RF-93 — el candidato no se arma si las notas del paquete no tienen el apartado de su versión."""
    assert CC.comprobar_notas('# Notas\n\n## 1.0.0rc6 (candidata)\n\nAlgo.\n', '1.0.0rc6') is None
    with pytest.raises(CE.EntregaError, match='1.0.0rc6'):
        CC.comprobar_notas('# Notas\n\n## 1.0.0rc1\n\nOtra.\n', '1.0.0rc6')
    with pytest.raises(CE.EntregaError, match='1.0.0rc6'):
        CC.comprobar_notas('# Notas\n\n## 1.0.0rc1\n\nOtra.\n\n## 1.0.0rc6\n\nTarde.\n', '1.0.0rc6')


def _instalada(destino: Path, version: str) -> None:
    python = destino / 'versiones' / version / 'python' / 'python.exe'
    python.parent.mkdir(parents=True)
    python.write_text('', encoding='utf-8')


def test_086_rf94_instalar_sobre_un_rc_sin_anterior_la_registra(tmp_path, instalador_sin_motor):
    """086:RF-94 — sobre un rc que nunca registró anterior.txt, la versión que estaba queda como la anterior, y se vuelve a ella.

    Así está el rc5 de este equipo (2026-11-13): actual.txt, versiones/1.0.0rc5 y ningún anterior.txt.
    """
    destino = tmp_path / 'app'
    _instalada(destino, '1.0.0rc5')
    (destino / 'actual.txt').write_text('1.0.0rc5\n', encoding='utf-8')
    assert not (destino / 'anterior.txt').exists()
    r = IC.instalar(_candidato(tmp_path, '1.0.0rc6'), destino)
    assert r['anterior'] == '1.0.0rc5'
    assert IC.estado(destino) == {'actual': '1.0.0rc6', 'anterior': '1.0.0rc5', 'versiones': ['1.0.0rc5', '1.0.0rc6']}
    assert instalador_sin_motor['copias'] == 1, 'cambiar de versión copia antes los datos'
    assert IC.volver(destino, restaurar=False)['version'] == '1.0.0rc5'
    assert IC.estado(destino)['actual'] == '1.0.0rc5'


def test_086_rf95_sin_puntero_valido_se_toma_la_instalada_mas_reciente(tmp_path, instalador_sin_motor):
    """086:RF-95 — sin actual.txt, o con uno que nombra una versión sin su Python, la anterior es la instalada más reciente.

    Antes se tomaba por una primera instalación: no se copiaban los datos, no quedaba anterior y se retiraba esa versión.
    """
    destino = tmp_path / 'app'
    for v in ('1.0.0rc4', '1.0.0rc5', '1.0.0rc10'):
        _instalada(destino, v)
    (destino / 'versiones' / '1.0.0rc3').mkdir()                   # sin Python: no es una versión a la que volver
    r = IC.instalar(_candidato(tmp_path, '1.0.0'), destino)
    assert r['anterior'] == '1.0.0rc10', 'rc10 es más reciente que rc5, aunque por orden de letras vaya antes'
    assert IC.estado(destino)['anterior'] == '1.0.0rc10' and instalador_sin_motor['copias'] == 1
    assert set(IC.estado(destino)['versiones']) == {'1.0.0rc10', '1.0.0'}
    # Un puntero roto tampoco borra a qué volver.
    otro = tmp_path / 'otro'
    _instalada(otro, '1.0.0rc5')
    (otro / 'actual.txt').write_text('1.0.0rc9\n', encoding='utf-8')
    assert IC.instalar(_candidato(tmp_path, '1.0.0rc6'), otro)['anterior'] == '1.0.0rc5'
    assert IC.estado(otro)['versiones'] == ['1.0.0rc5', '1.0.0rc6']


def test_086_rf96_el_iss_anota_a_que_version_se_puede_volver():
    """086:RF-96 — tras actualizar, el registro del instalador dice a qué versión se puede volver, o que no queda ninguna."""
    codigo = _codigo_del_iss()
    assert re.search(r"LoadStringFromFile\(ExpandConstant\('\{app\}\\anterior\.txt'\)", codigo)
    assert re.search(r"Log\([^;]*volver", codigo, flags=re.I)
    previa = re.search(r'if CurStep = ssInstall then\s*\n\s*VersionPrevia := ', codigo)
    assert previa, 'la versión que estaba se lee antes de copiar nada'


def _candidato_con_documentos(tmp_path: Path, version: str) -> Path:
    """Un candidato de prueba con «documentos/» propios de su versión, en su manifiesto con huella."""
    c = _candidato(tmp_path, version)
    ficheros = json.loads((c / 'manifiesto_candidato.json').read_text(encoding='utf-8'))['ficheros']
    for nombre in ('MANUAL_INSTALACION.md', f'NOTAS_VERSION_{version}.md'):
        contenido = f'{nombre} de la {version}\n'.encode('utf-8')
        (c / 'documentos').mkdir(exist_ok=True)
        (c / 'documentos' / nombre).write_bytes(contenido)
        ficheros.append({'ruta': f'documentos/{nombre}', 'sha256': hashlib.sha256(contenido).hexdigest(), 'bytes': len(contenido)})
    (c / 'manifiesto_candidato.json').write_text(json.dumps({'version': version, 'ficheros': ficheros}), encoding='utf-8')
    return c


def _documentos(destino: Path, nombre: str = 'documentos') -> dict[str, str]:
    carpeta = destino / nombre
    return {p.name: p.read_text(encoding='utf-8') for p in carpeta.iterdir()} if carpeta.is_dir() else {}


def test_086_rf97_una_instalacion_que_termina_publica_los_documentos_nuevos(tmp_path, instalador_sin_motor):
    """086:RF-97 — al terminar bien, {app}\\documentos tiene solo los de la versión nueva, sin restos de la preparación."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    assert _documentos(destino) == {'MANUAL_INSTALACION.md': 'MANUAL_INSTALACION.md de la 1.0\n',
                                    'NOTAS_VERSION_1.0.md': 'NOTAS_VERSION_1.0.md de la 1.0\n'}
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    assert _documentos(destino) == {'MANUAL_INSTALACION.md': 'MANUAL_INSTALACION.md de la 1.1\n',
                                    'NOTAS_VERSION_1.1.md': 'NOTAS_VERSION_1.1.md de la 1.1\n'}, 'las notas de la 1.0 no se quedan'
    assert not (destino / 'documentos.preparando').exists() and not (destino / 'documentos.retirar').exists()
    # 086:RF-99: se guardan los de la versión anterior, para volver con ellos, y nada más.
    assert _documentos(destino, 'documentos.anterior') == {'MANUAL_INSTALACION.md': 'MANUAL_INSTALACION.md de la 1.0\n',
                                                           'NOTAS_VERSION_1.0.md': 'NOTAS_VERSION_1.0.md de la 1.0\n'}
    IC.instalar(_candidato_con_documentos(tmp_path, '1.2'), destino)
    assert _documentos(destino, 'documentos.anterior') == {'MANUAL_INSTALACION.md': 'MANUAL_INSTALACION.md de la 1.1\n',
                                                           'NOTAS_VERSION_1.1.md': 'NOTAS_VERSION_1.1.md de la 1.1\n'}
    assert sorted(p.name for p in destino.iterdir() if p.name.startswith('documentos')) == ['documentos', 'documentos.anterior']


@pytest.mark.parametrize('paso', ['_doctor', '_copiar_datos', 'puntero'])
def test_086_rf97_una_instalacion_que_falla_deja_los_documentos_anteriores(tmp_path, instalador_sin_motor, monkeypatch, paso):
    """086:RF-97 — si instalar_candidato.py falla a mitad, el programa que sigue conserva sus documentos, intactos.

    Antes, Inno vaciaba {app}\\documentos en [InstallDelete] y copiaba los nuevos en [Files], los dos antes de saber si
    instalar_candidato.py terminaba: tras un fallo, el programa anterior se quedaba con los documentos de la versión nueva.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    antes = _documentos(destino)

    def falla(*_):
        raise IC.ErrorInstalacion('falla')

    if paso == 'puntero':
        # El último paso: los documentos nuevos ya estaban en su sitio y tienen que volver los anteriores.
        publicar = IC._publicar
        monkeypatch.setattr(IC, '_publicar', lambda ruta, texto: falla() if ruta.name == IC.ACTUAL else publicar(ruta, texto))
    else:
        monkeypatch.setattr(IC, paso, falla)
    with pytest.raises(IC.ErrorInstalacion):
        IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    assert _documentos(destino) == antes
    assert IC.estado(destino)['actual'] == '1.0'
    assert not (destino / 'documentos.preparando').exists() and not (destino / 'documentos.anterior').exists()


def _huella_del_arbol(destino: Path) -> dict[str, str]:
    """Cada fichero y carpeta de la instalación con su huella: lo que «no tocar nada» tiene que dejar igual."""
    return {p.relative_to(destino).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'carpeta')
            for p in sorted(destino.rglob('*'))}


def _docs_de(version: str) -> dict[str, str]:
    return {'MANUAL_INSTALACION.md': f'MANUAL_INSTALACION.md de la {version}\n',
            f'NOTAS_VERSION_{version}.md': f'NOTAS_VERSION_{version}.md de la {version}\n'}


def test_086_rf98_volver_atras_trae_la_version_anterior_con_sus_documentos(tmp_path, instalador_sin_motor):
    """086:RF-98 — instalar A, luego B y volver atrás: el programa y los documentos son los de A.

    «Acerca de» lo enseña el paquete de la versión que nombra actual.txt, que es la que arranca el lanzador.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    assert IC.volver(destino, restaurar=False)['version'] == '1.0'
    assert IC.estado(destino)['actual'] == '1.0'
    assert _documentos(destino) == _docs_de('1.0')
    assert 'actual.txt' in (destino / IC.LANZADOR).read_text(encoding='cp1252'), 'el lanzador arranca la versión de actual.txt'
    # 086:RF-99: sin anterior, no se guardan documentos de ninguna; los de la 1.1 se retiran (su programa se aparta).
    assert sorted(p.name for p in destino.iterdir() if p.name.startswith('documentos')) == ['documentos']


def test_086_rf100_volver_dos_veces_la_segunda_no_tiene_a_cual(tmp_path, instalador_sin_motor):
    """086:RF-100 — la segunda vuelta atrás dice que no hay anterior y no toca nada; antes alternaba entre las dos."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    IC.volver(destino, restaurar=False)
    antes = _huella_del_arbol(destino)
    with pytest.raises(IC.ErrorInstalacion, match='No hay una versión anterior'):
        IC.volver(destino, restaurar=False)
    assert _huella_del_arbol(destino) == antes


def _falla_al_escribir(monkeypatch, nombre: str) -> None:
    publicar = IC._publicar

    def publicar_o_fallar(ruta, texto):
        if ruta.name == nombre:
            raise OSError(f'no se pudo escribir {nombre}')
        publicar(ruta, texto)

    monkeypatch.setattr(IC, '_publicar', publicar_o_fallar)


def test_086_rf100_volver_tras_una_instalacion_fallida(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-100 — tras una instalación que falló sigue la versión de antes con sus documentos y su anterior.

    El fallo es el último paso, el puntero: antes, anterior.txt y ultima_copia.json ya se habían escrito con la versión
    que estaba, y volver atrás iba a esa misma versión y no restauraba los datos.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    antes = _huella_del_arbol(destino)
    with monkeypatch.context() as m:
        _falla_al_escribir(m, IC.ACTUAL)
        with pytest.raises(OSError):
            IC.instalar(_candidato_con_documentos(tmp_path, '1.2'), destino)
    assert _huella_del_arbol(destino) == antes, 'punteros, nota de la copia, documentos y versiones, como antes de intentarlo'
    assert IC.estado(destino)['actual'] == '1.1' and IC.estado(destino)['anterior'] == '1.0'
    assert _documentos(destino) == _docs_de('1.1') and _documentos(destino, 'documentos.anterior') == _docs_de('1.0')
    assert IC.volver(destino, restaurar=False)['version'] == '1.0'
    assert _documentos(destino) == _docs_de('1.0')


def test_086_rf100_sin_anterior_tras_una_instalacion_fallida_no_se_toca_nada(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-100 — con una sola versión y una actualización fallida no hay a cuál volver: se dice y no se toca nada."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    with monkeypatch.context() as m:
        m.setattr(IC, '_doctor', lambda python: (_ for _ in ()).throw(IC.ErrorInstalacion('falla')))
        with pytest.raises(IC.ErrorInstalacion):
            IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    antes = _huella_del_arbol(destino)
    assert IC.estado(destino) == {'actual': '1.0', 'anterior': None, 'versiones': ['1.0']}
    with pytest.raises(IC.ErrorInstalacion, match='No hay una versión anterior'):
        IC.volver(destino, restaurar=False)
    assert _huella_del_arbol(destino) == antes and _documentos(destino) == _docs_de('1.0')


@pytest.mark.parametrize('fallo', ['documentos', 'anterior.txt', 'actual.txt'])
def test_086_rf101_un_fallo_a_mitad_de_volver_deja_lo_que_habia(tmp_path, instalador_sin_motor, monkeypatch, fallo):
    """086:RF-101 — si volver atrás falla a mitad, la instalación queda byte a byte como estaba."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    antes = _huella_del_arbol(destino)
    if fallo == 'documentos':
        # El segundo renombrado: los de la 1.1 ya se apartaron y los de la 1.0 no llegan a su sitio.
        reemplazar = IC.os.replace

        def reemplazar_o_fallar(origen, hacia, *a, **k):
            if Path(origen).name == IC.DOCUMENTOS_ANTERIORES:
                raise OSError('carpeta en uso')
            return reemplazar(origen, hacia, *a, **k)

        monkeypatch.setattr(IC.os, 'replace', reemplazar_o_fallar)
    elif fallo == 'anterior.txt':
        # Quitar anterior.txt es el primer puntero: falla y ni él ni los documentos cambian.
        desvincular = Path.unlink

        def desvincular_o_fallar(self, *a, **k):
            if self.name == IC.ANTERIOR:
                raise OSError('fichero en uso')
            return desvincular(self, *a, **k)

        monkeypatch.setattr(Path, 'unlink', desvincular_o_fallar)
    else:
        _falla_al_escribir(monkeypatch, IC.ACTUAL)
    with pytest.raises(OSError):
        IC.volver(destino, restaurar=False)
    monkeypatch.undo()
    assert _huella_del_arbol(destino) == antes
    assert IC.estado(destino)['actual'] == '1.1' and IC.estado(destino)['anterior'] == '1.0'


def test_086_rf102_reinstalar_la_version_apartada_la_vuelve_a_poner_en_uso(tmp_path, instalador_sin_motor):
    """086:RF-102 — A, B, volver atrás y reinstalar B: B en uso con sus documentos, A como anterior; volver otra vez deja A.

    Antes, tras volver atrás, reinstalar B decía «ya está» porque su carpeta seguía apartada en versiones/, y para volver a
    ella había que desinstalar.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    IC.volver(destino, restaurar=False)
    apartada = (destino / 'versiones' / '1.1' / 'python' / 'python.exe').read_bytes()
    copias = instalador_sin_motor['copias']
    r = IC.instalar(_candidato_con_documentos(tmp_path / 'otra', '1.1'), destino)
    assert (r['version'], r['anterior'], r['reactivada']) == ('1.1', '1.0', True)
    assert IC.estado(destino) == {'actual': '1.1', 'anterior': '1.0', 'versiones': ['1.0', '1.1']}
    assert _documentos(destino) == _docs_de('1.1') and _documentos(destino, 'documentos.anterior') == _docs_de('1.0')
    assert instalador_sin_motor['copias'] == copias + 1, 'los datos se copian como en cualquier actualización'
    assert (destino / 'versiones' / '1.1' / 'python' / 'python.exe').read_bytes() == apartada, 'la apartada no se pisa'
    assert IC.volver(destino, restaurar=False)['version'] == '1.0'
    assert IC.estado(destino)['actual'] == '1.0' and _documentos(destino) == _docs_de('1.0')


def test_086_rf102_ya_esta_solo_si_es_la_que_se_usa(tmp_path, instalador_sin_motor):
    """086:RF-102 — «ya está» se dice solo de la versión en uso, y entonces no se toca nada."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    antes = _huella_del_arbol(destino)
    with pytest.raises(IC.ErrorInstalacion, match='ya es la instalada'):
        IC.instalar(_candidato_con_documentos(tmp_path / 'otra', '1.1'), destino)
    assert _huella_del_arbol(destino) == antes


@pytest.mark.parametrize('paso', ['_doctor', '_copiar_datos', 'puntero'])
def test_086_rf102_un_fallo_al_reactivar_deja_todo_como_estaba(tmp_path, instalador_sin_motor, monkeypatch, paso):
    """086:RF-102 — si poner de nuevo en uso la versión apartada falla a mitad, el árbol queda igual, también la apartada."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    IC.volver(destino, restaurar=False)
    antes = _huella_del_arbol(destino)
    if paso == 'puntero':
        _falla_al_escribir(monkeypatch, IC.ACTUAL)
    else:
        def falla(*_):
            raise IC.ErrorInstalacion('falla')

        monkeypatch.setattr(IC, paso, falla)
    with pytest.raises((IC.ErrorInstalacion, OSError)):
        IC.instalar(_candidato_con_documentos(tmp_path / 'otra', '1.1'), destino)
    assert _huella_del_arbol(destino) == antes
    assert IC.estado(destino) == {'actual': '1.0', 'anterior': None, 'versiones': ['1.0', '1.1']}


def _en_uso(ruta) -> PermissionError:
    """El error que da Windows al renombrar una carpeta con un fichero abierto dentro (WinError 32, errno EACCES)."""
    return PermissionError(13, 'El proceso no tiene acceso al archivo porque está siendo utilizado por otro proceso', str(ruta))


def test_086_rf103_un_fallo_al_deshacer_no_corta_el_resto_ni_tapa_el_original(tmp_path, instalador_sin_motor, monkeypatch, capsys):
    """086:RF-103 — falla el puntero y, al deshacer, el segundo paso: se reponen el primero y los demás, y el error trae los dos.

    Antes, el fallo de un paso del deshacer salía como una excepción nueva: tapaba la original y dejaba sin deshacer los
    renombrados de los documentos, que es el estado mezclado que RF-97 y RF-98 quieren impedir.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    anterior_antes = (destino / IC.ANTERIOR).read_bytes()
    publicar = IC._publicar
    veces = {IC.ULTIMA_COPIA: 0}

    def publicar_o_fallar(ruta, texto):
        if ruta.name == IC.ACTUAL:
            raise OSError('no se pudo escribir actual.txt')                   # el fallo original
        if ruta.name == IC.ULTIMA_COPIA:
            veces[IC.ULTIMA_COPIA] += 1
            if veces[IC.ULTIMA_COPIA] == 2:                                    # la segunda es la reposición
                raise OSError('ultima_copia.json bloqueado por el antivirus')
        publicar(ruta, texto)

    monkeypatch.setattr(IC, '_publicar', publicar_o_fallar)
    capsys.readouterr()
    with pytest.raises(OSError, match='no se pudo escribir actual.txt') as error:
        IC.instalar(_candidato_con_documentos(tmp_path / 'otra', '1.2'), destino)
    notas = '\n'.join(getattr(error.value, '__notes__', []))
    assert 'ultima_copia.json bloqueado por el antivirus' in notas, 'la nota lleva el fallo del deshacer'
    # El primer paso del deshacer (anterior.txt) y los renombrados de los documentos se repusieron igual.
    assert (destino / IC.ANTERIOR).read_bytes() == anterior_antes
    assert _documentos(destino) == _docs_de('1.1') and _documentos(destino, 'documentos.anterior') == _docs_de('1.0')
    assert IC.estado(destino)['actual'] == '1.1'
    aviso = capsys.readouterr().err
    assert str(destino / IC.ULTIMA_COPIA) in aviso and 'a mano' in aviso, 'el aviso dice qué quedó a medias y dónde'


def test_086_rf103_el_motivo_del_registro_lleva_las_notas_del_deshacer(tmp_path, monkeypatch):
    """086:RF-103 — el instalador lee el motivo del fichero de registro: ahí tienen que estar también las notas."""
    def instalar(*_a, **_k):
        exc = OSError('no se pudo escribir actual.txt')
        exc.add_note('No se pudo deshacer: reponer ultima_copia.json')
        raise exc

    monkeypatch.setattr(IC, 'instalar', instalar)
    registro = tmp_path / 'motivo.txt'
    assert IC.main(['instalar', '--candidato', str(tmp_path), '--destino', str(tmp_path / 'app'), '--registro', str(registro)]) == 1
    motivo = registro.read_text(encoding='utf-8-sig')
    assert 'no se pudo escribir actual.txt' in motivo and 'reponer ultima_copia.json' in motivo


def test_086_rf104_un_documento_abierto_un_momento_no_impide_instalar(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-104 — os.replace de la carpeta de documentos falla dos veces por un fichero abierto y después pasa: se instala.

    Windows no deja renombrar una carpeta con un fichero abierto dentro (WinError 32): el manual en un visor, Defender o
    la sincronización de OneDrive o Drive lo tienen abierto un momento.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    esperas: list[float] = []
    monkeypatch.setattr(IC, '_esperar', esperas.append, raising=False)
    reemplazar = IC.os.replace
    fallos = {'n': 0}

    def reemplazar_tras_dos(origen, hacia, *a, **k):
        if Path(origen).name == IC.DOCUMENTOS_PREPARANDO and fallos['n'] < 2:
            fallos['n'] += 1
            raise _en_uso(origen)
        return reemplazar(origen, hacia, *a, **k)

    monkeypatch.setattr(IC.os, 'replace', reemplazar_tras_dos)
    assert IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)['version'] == '1.1'
    assert _documentos(destino) == _docs_de('1.1') and _documentos(destino, 'documentos.anterior') == _docs_de('1.0')
    assert len(esperas) == 2 and esperas[1] > esperas[0], 'espera creciente entre intentos'


def test_086_rf104_un_documento_que_sigue_abierto_falla_con_que_hacer_y_deshace(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-104 — si la carpeta sigue en uso tras los intentos, se dice que se cierren los documentos y no cambia nada."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    antes = _huella_del_arbol(destino)
    esperas: list[float] = []
    monkeypatch.setattr(IC, '_esperar', esperas.append, raising=False)
    reemplazar = IC.os.replace

    def siempre_en_uso(origen, hacia, *a, **k):
        if Path(origen).name == IC.DOCUMENTOS_PREPARANDO:
            raise _en_uso(origen)
        return reemplazar(origen, hacia, *a, **k)

    monkeypatch.setattr(IC.os, 'replace', siempre_en_uso)
    with pytest.raises(IC.ErrorInstalacion, match=r'[Cc]ierre los documentos de ConverterSmartGrid abiertos \(manual, notas\) y vuelva a intentarlo'):
        IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    assert len(esperas) == IC.INTENTOS_RENOMBRAR - 1 and sum(esperas) < 10, 'acotado: unos segundos, no minutos'
    monkeypatch.undo()
    assert _huella_del_arbol(destino) == antes
    assert IC.estado(destino) == {'actual': '1.0', 'anterior': None, 'versiones': ['1.0']}


def test_086_rf105_si_no_se_pueden_borrar_los_documentos_retirados_se_avisa(tmp_path, instalador_sin_motor, monkeypatch, capsys):
    """086:RF-105 — documentos.retirar que no se deja borrar: la instalación termina y el registro lo dice.

    Antes, shutil.rmtree(..., ignore_errors=True) lo callaba y la carpeta se quedaba sin que nadie lo supiera.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    borrar = IC.shutil.rmtree

    def borrar_o_no(ruta, *a, **k):
        if Path(ruta).name == IC.DOCUMENTOS_RETIRAR and Path(ruta).exists():
            manejador = k.get('onexc')
            assert manejador is not None, 'los fallos al borrar se recogen, no se ignoran'
            manejador(IC.os.rmdir, str(ruta), _en_uso(ruta))
            return None
        return borrar(ruta, *a, **k)

    monkeypatch.setattr(IC.shutil, 'rmtree', borrar_o_no)
    capsys.readouterr()
    assert IC.instalar(_candidato_con_documentos(tmp_path, '1.2'), destino)['version'] == '1.2'
    aviso = capsys.readouterr().err
    assert str(destino / IC.DOCUMENTOS_RETIRAR) in aviso, 'el aviso nombra la carpeta que quedó'
    assert (destino / IC.DOCUMENTOS_RETIRAR).is_dir()


def test_086_rf105_los_avisos_quedan_en_el_registro_aunque_se_instale(tmp_path, monkeypatch):
    """086:RF-105 — con la instalación bien, los avisos van al fichero de registro que el instalador vuelca en su log."""
    def instalar(*_a, **_k):
        IC._avisar('No se pudo borrar C:/app/documentos.retirar; bórrela a mano.')
        return {'version': '1.1'}

    monkeypatch.setattr(IC, 'instalar', instalar)
    registro = tmp_path / 'motivo.txt'
    assert IC.main(['instalar', '--candidato', str(tmp_path), '--destino', str(tmp_path / 'app'), '--registro', str(registro)]) == 0
    assert 'documentos.retirar' in registro.read_text(encoding='utf-8-sig')


def test_086_rf105_el_iss_copia_a_su_registro_los_avisos_de_una_instalacion_buena():
    """086:RF-105 — con la instalación bien, el .iss lee el mismo fichero y deja sus avisos en el registro de Inno."""
    codigo = _codigo_del_iss()
    rama_buena = codigo.split('Motivo := MotivoDelFallo', 1)[1].split('AnotarVueltaAtras', 1)[0]
    assert re.search(r"Log\('Avisos de instalar_candidato\.py: ' \+ MotivoDelFallo\)", rama_buena)


def _reemplazo_en_uso(monkeypatch, nombre: str, veces: int | None):
    """Doble de os.replace: el fichero temporal de ``nombre`` está en uso ``veces`` veces (``None``: siempre)."""
    reemplazar = IC.os.replace
    fallos = {'n': 0}

    def reemplazar_o_fallar(origen, hacia, *a, **k):
        if Path(origen).name == nombre + '.nuevo' and (veces is None or fallos['n'] < veces):
            fallos['n'] += 1
            raise _en_uso(hacia)
        return reemplazar(origen, hacia, *a, **k)

    monkeypatch.setattr(IC.os, 'replace', reemplazar_o_fallar)
    return fallos


def test_086_rf104_un_puntero_en_uso_un_momento_no_impide_instalar(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-104 — _publicar reintenta igual que las carpetas: actual.txt en uso dos veces y luego libre, se instala."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    esperas: list[float] = []
    monkeypatch.setattr(IC, '_esperar', esperas.append, raising=False)
    _reemplazo_en_uso(monkeypatch, IC.ACTUAL, 2)
    assert IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)['version'] == '1.1'
    assert IC.estado(destino)['actual'] == '1.1' and len(esperas) == 2


def test_086_rf104_un_puntero_que_sigue_en_uso_falla_con_que_hacer_y_deja_lo_que_habia(tmp_path, instalador_sin_motor, monkeypatch):
    """086:RF-104 — actual.txt en uso siempre: se pide cerrar los documentos, se deshace y no queda el «.nuevo»."""
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    antes = _huella_del_arbol(destino)
    monkeypatch.setattr(IC, '_esperar', lambda s: None, raising=False)
    _reemplazo_en_uso(monkeypatch, IC.ACTUAL, None)
    with pytest.raises(IC.ErrorInstalacion, match=r'[Cc]ierre los documentos de ConverterSmartGrid abiertos \(manual, notas\)'):
        IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    monkeypatch.undo()
    assert _huella_del_arbol(destino) == antes, 'sin actual.txt.nuevo ni nada a medias'


def _rmtree_que_no_borra(monkeypatch, nombre: str) -> None:
    """Doble de shutil.rmtree: la carpeta ``nombre`` tiene un fichero abierto y no se deja borrar."""
    borrar = IC.shutil.rmtree

    def borrar_o_no(ruta, *a, **k):
        if Path(ruta).name == nombre and Path(ruta).exists():
            manejador = k.get('onexc')
            assert manejador is not None, f'los fallos al borrar {nombre} se recogen, no se ignoran'
            manejador(IC.os.rmdir, str(ruta), _en_uso(ruta))
            return None
        return borrar(ruta, *a, **k)

    monkeypatch.setattr(IC.shutil, 'rmtree', borrar_o_no)


def test_086_rf105_documentos_preparando_que_no_se_borra_se_avisa(tmp_path, instalador_sin_motor, monkeypatch, capsys):
    """086:RF-105 — falla el puntero, los documentos nuevos vuelven a «documentos.preparando» y esta no se deja borrar.

    El error sigue siendo el del puntero; el aviso nombra la carpeta que quedó.
    """
    destino = tmp_path / 'app'
    IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)
    _falla_al_escribir(monkeypatch, IC.ACTUAL)
    _rmtree_que_no_borra(monkeypatch, IC.DOCUMENTOS_PREPARANDO)
    capsys.readouterr()
    with pytest.raises(OSError, match='no se pudo escribir actual.txt'):
        IC.instalar(_candidato_con_documentos(tmp_path, '1.1'), destino)
    assert str(destino / IC.DOCUMENTOS_PREPARANDO) in capsys.readouterr().err
    assert IC.estado(destino)['actual'] == '1.0'


def test_086_rf105_documentos_anterior_que_no_se_borra_se_avisa(tmp_path, instalador_sin_motor, monkeypatch, capsys):
    """086:RF-105 — primera instalación sobre unos «documentos» sueltos: su «documentos.anterior» no se deja borrar.

    La instalación termina; el aviso nombra la carpeta.
    """
    destino = tmp_path / 'app'
    (destino / IC.DOCUMENTOS).mkdir(parents=True)
    (destino / IC.DOCUMENTOS / 'resto.md').write_text('de una instalación que se cortó\n', encoding='utf-8')
    _rmtree_que_no_borra(monkeypatch, IC.DOCUMENTOS_ANTERIORES)
    capsys.readouterr()
    assert IC.instalar(_candidato_con_documentos(tmp_path, '1.0'), destino)['version'] == '1.0'
    assert str(destino / IC.DOCUMENTOS_ANTERIORES) in capsys.readouterr().err
