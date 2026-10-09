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
