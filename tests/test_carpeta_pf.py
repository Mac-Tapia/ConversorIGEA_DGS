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
    """La búsqueda de antes de la spec 005: todo el árbol del proyecto."""
    return sorted({f.loc_name for f in prj.GetContents('*.ElmFeeder', 1)})


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
