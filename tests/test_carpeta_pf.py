"""Carpeta de DIgSILENT donde quedan los proyectos importados desde DGS (spec 005)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from igea_dgs.carpeta_pf import (
    CLAVE_PERFIL,
    NOMBRE_POR_DEFECTO,
    CarpetaError,
    nombre_de_perfil,
    validar_nombre,
)

RAIZ = Path(__file__).resolve().parents[1]


def _perfil(tmp_path: Path, datos) -> Path:
    ruta = tmp_path / 'perfil_empresa.json'
    ruta.write_text(datos if isinstance(datos, str) else json.dumps(datos), encoding='utf-8')
    return ruta


# --------------------------------------------------------------------------- nombre
def test_nombre_del_perfil(tmp_path):
    """005:RF-2 — el nombre de la carpeta sale del perfil de empresa."""
    ruta = _perfil(tmp_path, {CLAVE_PERFIL: 'Red de la empresa'})
    assert nombre_de_perfil(ruta) == 'Red de la empresa'


def test_nombre_del_perfil_sin_espacios_sobrantes(tmp_path):
    """005:RF-2 — los espacios de los extremos no forman parte del nombre."""
    ruta = _perfil(tmp_path, {CLAVE_PERFIL: '  Red  '})
    assert nombre_de_perfil(ruta) == 'Red'


@pytest.mark.parametrize('datos', [None, {}, {CLAVE_PERFIL: None}, {'otra_clave': 'x'}])
def test_nombre_por_defecto(tmp_path, datos):
    """005:RF-3 — sin perfil o sin la clave, la carpeta es «Conversor IGEA-DGS»."""
    ruta = tmp_path / 'no_existe.json' if datos is None else _perfil(tmp_path, datos)
    assert nombre_de_perfil(ruta) == NOMBRE_POR_DEFECTO == 'Conversor IGEA-DGS'


@pytest.mark.parametrize('malo', ['', '   ', 'x' * 41, 'a/b', 'a\\b', 'a.b', 'a:b', 'a*b',
                                  'a?b', 'a"b', 'a<b', 'a>b', 'a|b', 'a\nb'])
def test_nombre_invalido(malo):
    """005:RF-4 — un nombre vacío, largo o con caracteres no admitidos se rechaza y se nombra."""
    with pytest.raises(CarpetaError) as exc:
        validar_nombre(malo)
    assert repr(malo) in str(exc.value)


def test_nombre_de_40_caracteres_es_valido():
    """005:RF-4 — 40 caracteres es el máximo que admite DIgSILENT, y vale."""
    assert validar_nombre('x' * 40) == 'x' * 40


@pytest.mark.parametrize('malo', [{CLAVE_PERFIL: ''}, {CLAVE_PERFIL: 'a/b'}, {CLAVE_PERFIL: 7}])
def test_perfil_con_nombre_invalido(tmp_path, malo):
    """005:RF-4 — el perfil con un nombre inválido se rechaza al leerlo, sin abrir DIgSILENT."""
    with pytest.raises(CarpetaError):
        nombre_de_perfil(_perfil(tmp_path, malo))


@pytest.mark.parametrize('roto', ['{no es json', '["lista"]'])
def test_perfil_ilegible(tmp_path, roto):
    """005:RF-4 — un perfil que no es un objeto JSON se rechaza con un error que nombra el fichero."""
    ruta = _perfil(tmp_path, roto)
    with pytest.raises(CarpetaError) as exc:
        nombre_de_perfil(ruta)
    assert ruta.name in str(exc.value)


def test_ejemplo_del_perfil_es_valido():
    """005:RF-2 — el ejemplo versionado se lee y no lleva el nombre de ninguna empresa."""
    ejemplo = RAIZ / 'config' / 'perfil_empresa.example.json'
    assert nombre_de_perfil(ejemplo) == NOMBRE_POR_DEFECTO


# --------------------------------------------------------------------------- universal
def test_codigo_sin_carpeta_de_una_empresa():
    """005:RF-3 — ni el núcleo ni los guiones fijan la carpeta de una empresa (constitución P13)."""
    hallados = [
        str(f.relative_to(RAIZ))
        for carpeta in ('src', 'tools', 'frontend/src')
        for f in (RAIZ / carpeta).rglob('*')
        if f.suffix in {'.py', '.ts', '.tsx'}
        and 'sistemaeletricoeld' in f.read_text(encoding='utf-8', errors='ignore').lower()
    ]
    assert hallados == []


@pytest.mark.skipif(shutil.which('git') is None, reason='sin git')
def test_perfil_de_la_empresa_fuera_de_git():
    """005:RF-2 — el perfil local de la empresa no se versiona; el ejemplo sí."""
    def ignorado(rel: str) -> bool:
        return subprocess.run(['git', 'check-ignore', '-q', rel], cwd=RAIZ).returncode == 0

    assert ignorado('config/perfil_empresa.json')
    assert not ignorado('config/perfil_empresa.example.json')


# --------------------------------------------------------------------------- doble
# El doble de tests/fake_pf.py es lo único que ven estas pruebas de DIgSILENT: si imita
# mal la API, todo lo demás pasa sin probar nada. Estas fijan lo que se le pide.
def _importar(app, nombre):
    com = app.usuario.CreateObject('ComImport', 'imp')
    app.DefineTransferAttributes('ComImport', 'iopt_prj,targname,dgsFormat,fFile')
    com.SetAttributes([0, nombre, 'DGS File', 'x.dgs'])
    return com.Execute()


def test_doble_importa_en_la_raiz_del_usuario():
    from fake_pf import App

    app = App()
    assert _importar(app, 'SI213') == 0
    assert [p.loc_name for p in app.usuario.GetContents('*.IntPrj')] == ['SI213']
    assert _importar(app, 'SI213') == 1          # no crea dos con el mismo nombre


def test_doble_mueve_borra_y_activa():
    from fake_pf import App

    app = App()
    _importar(app, 'SI213')
    prj = app.importados[0]
    carpeta = app.usuario.CreateObject('IntFolder', 'Carpeta')
    assert carpeta.Move(prj) == 0
    assert prj.GetParent() is carpeta and app.usuario.GetContents('*.IntPrj') == []
    assert app.ActivateProject('SI213') == 1     # por nombre solo mira la raíz
    assert prj.Activate() == 0 and app.GetActiveProject() is prj
    app.fallar_mover = True
    assert app.usuario.Move(prj) == 1 and prj.GetParent() is carpeta
    assert prj.Delete() == 0 and carpeta.GetContents() == [] and app.GetActiveProject() is None


# --------------------------------------------------------------------------- árbol
import os
import random

from igea_dgs.carpeta_pf import (
    asegurar_carpeta,
    buscar_carpeta,
    nombre_libre,
    proyecto_por_ruta,
    proyectos_de,
)

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED') or random.SystemRandom().randrange(10**6))


def _app():
    from fake_pf import App

    return App()


def _proyecto(app, padre, nombre, **kw):
    from fake_pf import nuevo_proyecto

    return nuevo_proyecto(app, padre, nombre, **kw)


def _intocable(prj):
    """Hace que leer el contenido del proyecto falle: RF-13 no lo puede abrir."""
    def prohibido(*_a, **_k):
        raise AssertionError(f'se abrió el proyecto {prj.loc_name}')
    object.__setattr__(prj, 'GetContents', prohibido)
    return prj


def test_buscar_carpeta_solo_carpetas_de_la_raiz():
    """005:RF-1 — la carpeta es una IntFolder de la raíz del usuario, no otro objeto con su nombre."""
    app = _app()
    _proyecto(app, app.usuario, 'Red')                 # un proyecto que se llama igual
    assert buscar_carpeta(app.usuario, 'Red') is None
    otra = app.usuario.CreateObject('IntFolder', 'Otra')
    otra.CreateObject('IntFolder', 'Red')              # una subcarpeta tampoco vale
    assert buscar_carpeta(app.usuario, 'Red') is None
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    assert buscar_carpeta(app.usuario, 'Red') is carpeta


def test_asegurar_carpeta_la_crea_una_vez():
    """005:RF-5 — si no existe, se crea en la raíz del usuario; si existe, se reutiliza."""
    app = _app()
    carpeta = asegurar_carpeta(app.usuario, 'Red')
    assert carpeta.GetClassName() == 'IntFolder' and carpeta.GetParent() is app.usuario
    assert asegurar_carpeta(app.usuario, 'Red') is carpeta
    assert len(app.usuario.GetContents('*.IntFolder')) == 1


def test_asegurar_carpeta_que_no_se_puede_crear():
    """005:RF-9 — si DIgSILENT no crea la carpeta, el error la nombra."""
    from igea_dgs.carpeta_pf import CarpetaError

    app = _app()
    object.__setattr__(app.usuario, 'CreateObject', lambda *_a: None)
    with pytest.raises(CarpetaError, match='Red'):
        asegurar_carpeta(app.usuario, 'Red')


def test_nombre_libre_con_sufijos():
    """005:RF-7 — si el nombre está ocupado en la carpeta, el primero libre de _2, _3…"""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    assert nombre_libre(carpeta, 'SI213') == 'SI213'
    _proyecto(app, carpeta, 'SI213')
    assert nombre_libre(carpeta, 'SI213') == 'SI213_2'
    _proyecto(app, carpeta, 'si213_2')                 # DIgSILENT no distingue mayúsculas
    assert nombre_libre(carpeta, 'SI213') == 'SI213_3'
    _proyecto(app, app.usuario, 'OTRO')                # la raíz no cuenta (RF-20)
    assert nombre_libre(carpeta, 'OTRO') == 'OTRO'


def test_nombre_libre_no_pasa_de_40():
    """005:RF-7 — con el sufijo, el nombre sigue cabiendo en 40 caracteres."""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    largo = 'x' * 40
    _proyecto(app, carpeta, largo)
    libre = nombre_libre(carpeta, largo)
    assert libre == 'x' * 38 + '_2' and len(libre) == 40


def test_proyectos_de_con_subcarpetas_sorteadas():
    """005:RF-12 — cada proyecto con su ruta relativa, en subcarpetas sorteadas a varios niveles."""
    rng = random.Random(SEMILLA)
    app = _app()
    raiz = app.usuario.CreateObject('IntFolder', 'Red')
    esperado = []

    def poblar(carpeta, prefijo, nivel):
        for i in range(rng.randint(0, 4)):
            nombre = f'P{nivel}_{i}'
            _intocable(_proyecto(app, carpeta, nombre))
            esperado.append('/'.join([*prefijo, nombre]))
        if nivel < 3:
            for j in range(rng.randint(0, 3)):
                sub = carpeta.CreateObject('IntFolder', f'S{nivel}_{j}')
                poblar(sub, [*prefijo, sub.loc_name], nivel + 1)

    poblar(raiz, [], 0)
    rutas = [ruta for ruta, _prj in proyectos_de(raiz)]
    assert rutas == sorted(esperado, key=str.lower), f'semilla {SEMILLA}'


def test_proyectos_de_no_abre_ningun_proyecto():
    """005:RF-13 — busca proyectos en las subcarpetas sin entrar en ningún proyecto."""
    app = _app()
    raiz = app.usuario.CreateObject('IntFolder', 'Red')
    sub = raiz.CreateObject('IntFolder', '2026-10')
    _intocable(_proyecto(app, raiz, 'A'))
    _intocable(_proyecto(app, sub, 'B'))
    assert [r for r, _ in proyectos_de(raiz)] == ['2026-10/B', 'A']


def test_mismo_nombre_en_dos_subcarpetas():
    """005:RF-16 — dos proyectos con el mismo nombre en subcarpetas distintas son dos rutas."""
    app = _app()
    raiz = app.usuario.CreateObject('IntFolder', 'Red')
    a = _proyecto(app, raiz.CreateObject('IntFolder', 'Junio'), 'SI213')
    b = _proyecto(app, raiz.CreateObject('IntFolder', 'Julio'), 'SI213')
    assert [r for r, _ in proyectos_de(raiz)] == ['Julio/SI213', 'Junio/SI213']
    assert proyecto_por_ruta(raiz, 'Junio/SI213') is a
    assert proyecto_por_ruta(raiz, 'Julio/SI213') is b
    assert proyecto_por_ruta(raiz, 'SI213') is None
    assert proyecto_por_ruta(raiz, 'Agosto/SI213') is None


# --------------------------------------------------------------------------- alimentadores
from igea_dgs.carpeta_pf import alimentadores_de


def _carpeta_de(prj, tipo):
    return next(h for h in prj.GetContents('*.IntPrjfolder', 1) if getattr(h, 'iopt_typ', '') == tipo)


def _busqueda_completa(prj):
    """La búsqueda de antes de la spec 005 (``alimentadores_de`` de ``tools/pf_proyectos.py``):
    todo el árbol del proyecto, y sus ``ElmNet`` si no tiene ningún ``ElmFeeder``."""
    nombres = {f.loc_name for f in prj.GetContents('*.ElmFeeder', 1)}
    if not nombres:
        nombres = {n.loc_name for n in prj.GetContents('*.ElmNet', 1)
                   if 'summary' not in n.loc_name.lower()}
    return sorted(nombres)


def test_alimentadores_solo_en_los_datos_de_red():
    """005:RF-17 — no abre casos de estudio ni bibliotecas para buscar alimentadores."""
    app = _app()
    prj = _proyecto(app, app.usuario, 'P', alimentadores=('F2', 'F1'))
    for carpeta in [_carpeta_de(prj, 'study'), _carpeta_de(prj, 'lib')]:
        _intocable(carpeta)
    assert alimentadores_de(prj) == (['F1', 'F2'], None)


def test_alimentadores_sin_datos_de_red():
    """005:RF-18 — un proyecto sin datos de red se busca entero, y se anota."""
    app = _app()
    prj = _proyecto(app, app.usuario, 'Manual', alimentadores=('F1',), con_datos_de_red=False)
    feeders, nota = alimentadores_de(prj)
    assert feeders == ['F1']
    assert nota and 'Manual' in nota and 'datos de red' in nota


def test_alimentadores_misma_lista_que_la_busqueda_completa():
    """005:RF-19 — con datos de red, la misma lista que buscando en todo el proyecto."""
    rng = random.Random(SEMILLA)
    app = _app()
    for k in range(rng.randint(1, 6)):
        nombres = tuple(f'F{rng.randrange(1000)}' for _ in range(rng.randint(0, 30)))
        prj = _proyecto(app, app.usuario, f'P{k}', alimentadores=nombres)
        assert alimentadores_de(prj) == (_busqueda_completa(prj), None), f'semilla {SEMILLA}'


def test_alimentadores_de_un_proyecto_sin_elmfeeder():
    """005:RF-17 — sin ElmFeeder, se muestran sus redes (regla de la spec 004), sin la de resumen."""
    app = _app()
    prj = _proyecto(app, app.usuario, 'P', alimentadores=())
    datos = _carpeta_de(prj, 'netdat')
    datos.CreateObject('ElmNet', 'Summary Grid')
    datos.CreateObject('ElmNet', 'Norte')
    assert alimentadores_de(prj) == (['Norte', 'Red'], None)


# --------------------------------------------------------------------------- importación
def _mod_aceptacion():
    import importlib.util

    ruta = RAIZ / 'tools' / 'powerfactory_acceptance.py'
    spec = importlib.util.spec_from_file_location('powerfactory_acceptance', ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def dgs(tmp_path):
    ruta = tmp_path / 'SI213.dgs'
    ruta.write_text('DGS', encoding='ascii')
    return ruta


def _proyectos_en(objeto):
    return sorted(p.loc_name for p in objeto.GetContents('*.IntPrj'))


def test_importa_dentro_de_la_carpeta(dgs):
    """005:RF-6 — el proyecto importado queda en la carpeta, no en la raíz, y activo."""
    app = _app()
    info = _mod_aceptacion().import_dgs_file(app, dgs, project_name='SI213', carpeta='Red')
    carpeta = buscar_carpeta(app.usuario, 'Red')
    assert info['ok'] and info['errors'] == []
    assert _proyectos_en(carpeta) == ['SI213'] and _proyectos_en(app.usuario) == []
    assert app.GetActiveProject() is proyecto_por_ruta(carpeta, 'SI213')
    assert (info['project_name'], info['project_folder'], info['project_path']) == ('SI213', 'Red', 'SI213')


def test_crea_la_carpeta_antes_de_importar(dgs):
    """005:RF-5 — sin carpeta, se crea en la raíz del usuario antes de ComImport."""
    app = _app()
    app.fallar_importacion = True
    info = _mod_aceptacion().import_dgs_file(app, dgs, carpeta='Red')
    assert not info['ok']
    assert buscar_carpeta(app.usuario, 'Red') is not None


def test_nombre_ocupado_en_la_carpeta(dgs):
    """005:RF-7 — con el nombre ocupado se importa con el primero libre y se avisa."""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    _proyecto(app, carpeta, 'SI213')
    mod = _mod_aceptacion()
    info = mod.import_dgs_file(app, dgs, project_name='SI213', carpeta='Red')
    assert info['ok'] and info['project_name'] == 'SI213_2'
    assert any('SI213_2' in aviso for aviso in info['warnings'])
    info = mod.import_dgs_file(app, dgs, project_name='SI213', carpeta='Red')
    assert info['project_name'] == 'SI213_3'
    assert _proyectos_en(carpeta) == ['SI213', 'SI213_2', 'SI213_3']


def test_no_toca_los_proyectos_existentes(dgs):
    """005:RF-8 — importar no borra, sobrescribe ni mueve un proyecto que ya existía."""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    previos = [_proyecto(app, carpeta, 'SI213'), _proyecto(app, app.usuario, 'SI213')]
    padres = [p.GetParent() for p in previos]
    _mod_aceptacion().import_dgs_file(app, dgs, project_name='SI213', carpeta='Red')
    assert [p.GetParent() for p in previos] == padres
    assert not any(p in app.borrados for p in previos)
    assert all(obj not in previos for obj, _destino in app.movidos)


def test_los_anteriores_se_quedan_en_la_raiz(dgs):
    """005:RF-20 — los proyectos de la raíz, importados antes, siguen en la raíz."""
    app = _app()
    _proyecto(app, app.usuario, 'Antiguo')
    _mod_aceptacion().import_dgs_file(app, dgs, project_name='SI213', carpeta='Red')
    assert _proyectos_en(app.usuario) == ['Antiguo']


def test_si_no_se_puede_mover_no_queda_en_la_raiz(dgs):
    """005:RF-9 — si no se puede mover a la carpeta, falla nombrándola y no deja el proyecto."""
    app = _app()
    _proyecto(app, app.usuario, 'Antiguo')
    app.fallar_mover = True
    info = _mod_aceptacion().import_dgs_file(app, dgs, project_name='SI213', carpeta='Red')
    assert not info['ok'] and any("'Red'" in e for e in info['errors'])
    assert _proyectos_en(app.usuario) == ['Antiguo']
    assert _proyectos_en(buscar_carpeta(app.usuario, 'Red')) == []


def test_carpeta_del_perfil_por_defecto(dgs, tmp_path, monkeypatch):
    """005:RF-2 — sin carpeta explícita, la importación usa la del perfil de empresa."""
    import igea_dgs.carpeta_pf as cpf

    monkeypatch.setattr(cpf, 'ruta_perfil', lambda: _perfil(tmp_path, {CLAVE_PERFIL: 'Empresa'}))
    app = _app()
    info = _mod_aceptacion().import_dgs_file(app, dgs, project_name='SI213')
    assert info['ok'] and info['project_folder'] == 'Empresa'
    assert _proyectos_en(buscar_carpeta(app.usuario, 'Empresa')) == ['SI213']


def test_carpeta_invalida_no_abre_nada(dgs):
    """005:RF-4 — un nombre de carpeta inválido falla sin crear nada en DIgSILENT."""
    app = _app()
    info = _mod_aceptacion().import_dgs_file(app, dgs, carpeta='a/b')
    assert not info['ok'] and "'a/b'" in info['errors'][0]
    assert app.creados == [] and app.importados == []


# --------------------------------------------------------------------------- guiones
import ast
import sys

from igea_dgs.carpeta_pf import activar_proyecto

GUIONES_QUE_IMPORTAN = ('powerfactory_acceptance.py', 'build_system_grid.py',
                        'convertir_grupos_mdb.py', 'prueba_representacion.py',
                        'run_one_study.py')


def _llamadas(fichero: Path, funcion: str) -> list[ast.Call]:
    arbol = ast.parse(fichero.read_text(encoding='utf-8'))
    return [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
            and getattr(n.func, 'id', getattr(n.func, 'attr', None)) == funcion]


@pytest.mark.parametrize('guion', GUIONES_QUE_IMPORTAN)
def test_cada_guion_importa_en_la_carpeta(guion):
    """005:RF-10 — toda importación de los guiones pasa la carpeta y la ofrece en --pf-carpeta."""
    ruta = RAIZ / 'tools' / guion
    llamadas = _llamadas(ruta, 'import_dgs_file')
    assert llamadas, f'{guion} ya no importa: actualice la lista'
    assert all(any(k.arg == 'carpeta' for k in c.keywords) for c in llamadas), guion
    assert "'--pf-carpeta'" in ruta.read_text(encoding='utf-8')


@pytest.mark.parametrize('guion', [*GUIONES_QUE_IMPORTAN, 'base_scenario.py',
                                   'check_pf_license.py', 'show_pf_diagram.py', 'pf_proyectos.py'])
def test_ningun_guion_activa_por_nombre(guion):
    """005:RF-16 — ActivateProject(nombre) solo mira la raíz: ningún guion lo usa."""
    assert _llamadas(RAIZ / 'tools' / guion, 'ActivateProject') == []


@pytest.mark.parametrize('guion', [*GUIONES_QUE_IMPORTAN, 'base_scenario.py'])
def test_ayuda_de_los_guiones(guion):
    """005:RF-10 — la opción nueva no rompe la línea de órdenes."""
    salida = subprocess.run([sys.executable, str(RAIZ / 'tools' / guion), '--help'],
                            capture_output=True, text=True, cwd=RAIZ,
                            env={**os.environ, 'PYTHONPATH': str(RAIZ / 'src')})
    assert salida.returncode == 0, salida.stderr
    assert '--pf-carpeta' in salida.stdout


def test_activar_proyecto_de_la_carpeta():
    """005:RF-16 — se activa el proyecto de la ruta, aunque en la raíz haya otro con su nombre."""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    _proyecto(app, app.usuario, 'SI213')
    nuevo = _proyecto(app, carpeta.CreateObject('IntFolder', 'Oct'), 'SI213')
    assert activar_proyecto(app, 'Oct/SI213', 'Red') is nuevo
    assert app.GetActiveProject() is nuevo


def test_activar_proyecto_anterior_de_la_raiz():
    """005:RF-20 — un proyecto anterior, que sigue en la raíz, se puede seguir usando."""
    app = _app()
    antiguo = _proyecto(app, app.usuario, 'PIDE_A0')
    assert activar_proyecto(app, 'PIDE_A0', 'Red') is antiguo     # la carpeta ni existe
    assert activar_proyecto(app, 'No/Existe', 'Red') is None


# --------------------------------------------------------------------------- lectura
def _mod_proyectos():
    import importlib.util

    ruta = RAIZ / 'tools' / 'pf_proyectos.py'
    spec = importlib.util.spec_from_file_location('pf_proyectos', ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sin_cambios(app):
    return not (app.creados or app.escrituras or app.movidos or app.borrados)


def test_leer_solo_la_carpeta():
    """005:RF-11 — se listan los proyectos de la carpeta y subcarpetas, con sus alimentadores."""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    _proyecto(app, carpeta, 'SI213', alimentadores=('SI213',))
    _proyecto(app, carpeta.CreateObject('IntFolder', '2026-10'), 'PE104', alimentadores=('B', 'A'))
    _intocable(_proyecto(app, app.usuario, 'Ajeno'))           # la raíz ni se abre
    _intocable(app.usuario.CreateObject('IntFolder', 'Otra'))
    datos = _mod_proyectos().leer(app, 'Red')
    assert datos['folder'] == 'Red' and datos['exists'] is True and datos['aviso'] is None
    assert datos['projects'] == [
        {'name': 'PE104', 'path': '2026-10/PE104', 'feeders': ['A', 'B']},
        {'name': 'SI213', 'path': 'SI213', 'feeders': ['SI213']},
    ]


def test_leer_sin_carpeta():
    """005:RF-14 — sin carpeta, lista vacía con un aviso que la nombra y dice cuándo se crea."""
    app = _app()
    _proyecto(app, app.usuario, 'Ajeno')
    datos = _mod_proyectos().leer(app, 'Red')
    assert datos['projects'] == [] and datos['exists'] is False
    assert "'Red'" in datos['aviso'] and 'primer DGS' in datos['aviso']


def test_leer_carpeta_vacia_sin_aviso():
    """005:RF-14 — una carpeta que existe y está vacía no es «carpeta inexistente»."""
    app = _app()
    app.usuario.CreateObject('IntFolder', 'Red')
    datos = _mod_proyectos().leer(app, 'Red')
    assert datos == {'folder': 'Red', 'exists': True, 'aviso': None, 'projects': []}


def test_leer_no_cambia_nada():
    """005:RF-15 — leer no crea ni modifica nada en DIgSILENT, exista o no la carpeta."""
    mod = _mod_proyectos()
    app = _app()
    mod.leer(app, 'Red')
    assert _sin_cambios(app) and buscar_carpeta(app.usuario, 'Red') is None
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    _proyecto(app, carpeta, 'SI213')
    _proyecto(app, carpeta, 'Manual', con_datos_de_red=False)
    for lista in (app.creados, app.escrituras):
        lista.clear()
    mod.leer(app, 'Red')
    assert _sin_cambios(app) and app.GetActiveProject() is None


def test_leer_proyecto_danado():
    """005:RF-11 — un proyecto que no se puede leer sale sin alimentadores y no tumba la lista."""
    app = _app()
    carpeta = app.usuario.CreateObject('IntFolder', 'Red')
    _intocable(_proyecto(app, carpeta, 'Roto'))
    _proyecto(app, carpeta, 'Sano')
    datos = _mod_proyectos().leer(app, 'Red')
    assert [(p['path'], p['feeders']) for p in datos['projects']] == [('Roto', []), ('Sano', ['F1'])]


def test_leer_por_linea_de_ordenes_valida_la_carpeta(tmp_path):
    """005:RF-4 — con un nombre inválido el guion sale con 2 antes de buscar PowerFactory."""
    salida = subprocess.run(
        [sys.executable, str(RAIZ / 'tools' / 'pf_proyectos.py'), '--carpeta', 'a/b',
         '--output-json', str(tmp_path / 'p.json')],
        capture_output=True, text=True, cwd=RAIZ, env={**os.environ, 'PYTHONPATH': str(RAIZ / 'src')})
    assert salida.returncode == 2 and "'a/b'" in salida.stdout
    assert not (tmp_path / 'p.json').exists()


# --------------------------------------------------------------------------- web
from types import SimpleNamespace


@pytest.fixture
def web(tmp_path, monkeypatch):
    """Servicios de la web con DIgSILENT simulado: ``run`` anota cada orden lanzada."""
    from igea_dgs.web import services
    from igea_dgs.web.workspace import Workspace

    (tmp_path / 'config').mkdir()
    monkeypatch.setattr(services, 'project_root', lambda: tmp_path)
    monkeypatch.setattr(services, '_script', lambda nombre: tmp_path / nombre)
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, tmp_path / 'python.exe'))
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda _d: {})
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'prueba'})
    ws = Workspace(id='w', root=tmp_path / 'ws')
    ws.out_dir.mkdir(parents=True)
    ordenes: list[list[str]] = []

    def run_process(orden, **_kw):
        ordenes.append(orden)
        if '--output-json' in orden and orden[1].endswith('pf_proyectos.py'):
            Path(orden[orden.index('--output-json') + 1]).write_text(json.dumps(
                {'folder': 'x', 'exists': True, 'aviso': None,
                 'projects': [{'name': 'SI213', 'path': 'Oct/SI213', 'feeders': ['SI213']}]}),
                encoding='utf-8')
        return 0

    logs: list[str] = []
    ctx = SimpleNamespace(log=logs.append, progress=lambda *_a: None,
                          check_cancel=lambda: None, run_process=run_process)
    return SimpleNamespace(services=services, ws=ws, ctx=ctx, ordenes=ordenes, logs=logs,
                           perfil=tmp_path / 'config' / 'perfil_empresa.json')


def _valor(orden, opcion):
    return orden[orden.index(opcion) + 1]


def test_web_lee_la_carpeta_del_perfil(web):
    """005:RF-2 — «Leer proyectos» de la web pasa al guion la carpeta del perfil de empresa."""
    web.perfil.write_text(json.dumps({CLAVE_PERFIL: 'Empresa'}), encoding='utf-8')
    datos = web.services.pf_projects(web.ws, web.ctx)
    assert _valor(web.ordenes[0], '--carpeta') == 'Empresa'
    assert datos['projects'][0]['path'] == 'Oct/SI213'


def test_web_sin_perfil_usa_el_nombre_por_defecto(web):
    """005:RF-3 — sin perfil, la web usa «Conversor IGEA-DGS»."""
    web.services.pf_projects(web.ws, web.ctx)
    assert _valor(web.ordenes[0], '--carpeta') == NOMBRE_POR_DEFECTO


def test_web_carpeta_invalida_no_lanza_digsilent(web):
    """005:RF-4 — con el perfil inválido la web falla sin lanzar ningún guion de DIgSILENT."""
    web.perfil.write_text(json.dumps({CLAVE_PERFIL: 'a/b'}), encoding='utf-8')
    with pytest.raises(web.services.UserError, match="'a/b'"):
        web.services.pf_projects(web.ws, web.ctx)
    dgs = web.ws.out_dir / 'RED.dgs'
    dgs.write_text('DGS', encoding='ascii')
    dgs.with_name('RED_feeder_metadata.json').write_text('{}', encoding='utf-8')
    with pytest.raises(web.services.UserError, match="'a/b'"):
        web.services.check_powerfactory_flow(web.ws, ['RED'])
    assert web.ordenes == []


def test_web_importa_en_la_carpeta_y_guarda_la_ruta(web, monkeypatch):
    """005:RF-10 — la importación de la web pasa la carpeta; 005:RF-16 — guarda la ruta del proyecto."""
    web.perfil.write_text(json.dumps({CLAVE_PERFIL: 'Empresa'}), encoding='utf-8')
    dgs = web.ws.out_dir / 'RED.dgs'
    dgs.write_text('DGS', encoding='ascii')
    monkeypatch.setattr(web.services, 'dgs_jobs', lambda _ws, _f: ([('RED', dgs, None)], []))
    monkeypatch.setattr(web.services, 'pandapower_preflight',
                        lambda *_a: {'disponible': False, 'avisos': [], 'feeders': []})
    (web.ws.out_dir / 'RED_powerfactory_acceptance.json').write_text(json.dumps(
        {'import': {'project_name': 'RED_2', 'project_path': 'RED_2',
                    'project_folder': 'Empresa'}}), encoding='utf-8')
    web.services.powerfactory_flow(web.ws, web.ctx, ['RED'])
    assert _valor(web.ordenes[0], '--pf-carpeta') == 'Empresa'
    assert web.ws.pf_projects['RED'] == 'RED_2'


def test_web_avisa_si_no_existe_la_carpeta(web, monkeypatch):
    """005:RF-14 — el aviso de carpeta inexistente llega al registro del trabajo."""
    def sin_carpeta(orden, **_kw):
        Path(_valor(orden, '--output-json')).write_text(json.dumps(
            {'folder': 'x', 'exists': False, 'projects': [],
             'aviso': "No existe la carpeta 'x' en DIgSILENT; se crea al importar el primer DGS."}),
            encoding='utf-8')
        return 0
    web.ctx.run_process = sin_carpeta
    datos = web.services.pf_projects(web.ws, web.ctx)
    assert datos['projects'] == [] and any('primer DGS' in linea for linea in web.logs)


def test_web_red_unida_en_la_carpeta(web, tmp_path):
    """005:RF-10 — la red unida («Sistema completo») también se importa en la carpeta."""
    web.perfil.write_text(json.dumps({CLAVE_PERFIL: 'Empresa'}), encoding='utf-8')
    web.ws.options['input_mode'] = 'mdb'
    web.ws.inputs = {'mdb': {'path': str(tmp_path / 'base.mdb')}}
    orden = web.services.system_command(web.ws, 'grid')
    assert _valor(orden, '--pf-carpeta') == 'Empresa'


# --------------------------------------------------------------------------- front
def test_front_elige_el_proyecto_por_su_ruta():
    """005:RF-16 — el desplegable usa la ruta como valor; 005:RF-12 — la muestra con « / »;
    005:RF-14 — enseña el aviso de carpeta inexistente."""
    tab = (RAIZ / 'frontend' / 'src' / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
    assert 'value={ruta(p)}' in tab and 'value={p.name}' not in tab
    assert ".split('/').join(' / ')" in tab
    assert 'inventario?.aviso' in tab
    assert 'path?: string' in (RAIZ / 'frontend' / 'src' / 'types.ts').read_text(encoding='utf-8')
