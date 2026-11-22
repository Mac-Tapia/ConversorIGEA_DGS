"""Spec 058, RF-6 (T6) — la carpeta principal se muda a ``ConverterSmartGrid`` sin perder los worktrees, sus uniones, el
``.venv``, la configuración, las variables, los accesos directos ni los espacios de trabajo (su identidad)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'tools'))


def _m():
    """La herramienta de la T6: su ausencia es la falla de la aserción, no un error al importar."""
    import importlib.util
    assert importlib.util.find_spec('mudar_carpeta_principal') is not None, 'falta tools/mudar_carpeta_principal.py (058:RF-6)'
    import mudar_carpeta_principal
    return mudar_carpeta_principal


def _git(*a, cwd):
    r = subprocess.run(['git', *a], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _Maquina(procesos=(), entorno=None, accesos=()):
    """La máquina de la prueba: anota lo que se tocaría fuera de la carpeta, sin tocarlo."""
    M = _m()
    m = M.Maquina()
    m.puesto, m.escritos, m.reinstalado = {}, [], []
    m.procesos = lambda origen: list(procesos)
    m.entorno = lambda: dict(entorno or {})
    m.poner_entorno = lambda k, v: m.puesto.__setitem__(k, v)
    m.accesos = lambda origen: list(accesos)
    m.escribir_acceso = lambda ruta, obj, carpeta: m.escritos.append((ruta, obj, carpeta))
    m.reinstalar = lambda destino: (m.reinstalado.append(destino), subprocess.CompletedProcess([], 0, '', ''))[1]
    m.importar = lambda destino: str(destino / 'src' / 'convertersmartgrid' / '__init__.py')
    return m


def _repo(tmp_path):
    M = _m()
    origen = tmp_path / 'Conversor_viejo'
    origen.mkdir()
    _git('init', '-q', cwd=origen)
    (origen / 'src' / 'convertersmartgrid').mkdir(parents=True)
    (origen / 'src' / 'convertersmartgrid' / '__init__.py').write_text('', encoding='utf-8')
    (origen / 'frontend' / 'node_modules').mkdir(parents=True)
    (origen / 'config').mkdir()
    (origen / 'config' / 'suite.json').write_text(json.dumps({'red': str(origen / 'datos' / 'red.txt')}), encoding='utf-8')
    (origen / 'config' / 'otra.json').write_text('{"nada": 1}', encoding='utf-8')
    (origen / M.FICHERO_INSTALACION).write_text(json.dumps({'id': 'a' * 16}), encoding='utf-8')
    for e in ('e1', 'e2'):
        (origen / 'output' / 'web' / e).mkdir(parents=True)
        for nombre in ('workspace.json', 'conversiones.json'):
            (origen / 'output' / 'web' / e / nombre).write_text(json.dumps({'id': e}), encoding='utf-8')
    (origen / '.venv' / 'Scripts').mkdir(parents=True)
    (origen / '.venv' / 'Scripts' / 'activate.bat').write_text(f'set "VIRTUAL_ENV={origen}\\.venv"\n', encoding='utf-8')
    _git('-c', 'user.email=x@y', '-c', 'user.name=x', 'add', '-A', cwd=origen)
    _git('-c', 'user.email=x@y', '-c', 'user.name=x', 'commit', '-qm', 'base', cwd=origen)
    wt = tmp_path / 'wt_uno'
    _git('worktree', 'add', '-q', '--detach', str(wt), cwd=origen)
    # Uno dentro de la carpeta (como .worktrees/…): se muda con ella y se repara en su ruta nueva.
    _git('worktree', 'add', '-q', '--detach', str(origen / '.worktrees' / 'dentro'), cwd=origen)
    return origen, wt


def test_058_rf6_reemplazar_ruta_en_sus_tres_formas():
    """058:RF-6 — la ruta vieja se cambia escrita con «\\», con «/» y escapada en JSON, y la unidad sin distinguir."""
    M = _m()
    o, d = Path('D:/c/Viejo'), Path('D:/c/ConverterSmartGrid')
    texto = 'a=D:\\c\\Viejo\\x b=D:/c/Viejo/y c="D:\\\\c\\\\Viejo\\\\z" d=d:\\c\\Viejo\\w e=D:/c/Otro'
    nuevo = M.reemplazar_ruta(texto, o, d)
    assert nuevo == ('a=D:\\c\\ConverterSmartGrid\\x b=D:/c/ConverterSmartGrid/y '
                     'c="D:\\\\c\\\\ConverterSmartGrid\\\\z" d=D:\\c\\ConverterSmartGrid\\w e=D:/c/Otro')
    assert json.loads(M.reemplazar_ruta(json.dumps({'k': 'D:\\c\\Viejo\\f'}), o, d)) == {'k': 'D:\\c\\ConverterSmartGrid\\f'}


def test_058_rf6_no_se_muda_si_algo_lo_impide(tmp_path):
    """058:RF-6 — sin la identidad (los espacios quedarían en otra carpeta), con el destino ya creado o con un programa
    corriendo desde la carpeta, no se toca nada y se dice por qué."""
    M = _m()
    origen, _ = _repo(tmp_path)
    destino = tmp_path / M.NOMBRE_NUEVO
    destino.mkdir()
    (origen / M.FICHERO_INSTALACION).unlink()
    plan = M.planear(origen, destino, _Maquina(procesos=['77\tpython.exe']))
    texto = ' | '.join(plan.impedimentos)
    assert 'ya existe' in texto and M.FICHERO_INSTALACION in texto and '1 programas corren' in texto
    pasos = M.aplicar(plan, _Maquina())
    assert pasos == [{'paso': 'comprobar', 'ok': False, 'detalle': texto.replace(' | ', '; ')}]
    assert origen.is_dir()


@pytest.mark.skipif(os.name != 'nt', reason='las uniones de directorio son de Windows')
def test_058_rf6_mudar_de_punta_a_punta(tmp_path):
    """058:RF-6 — se renombra; el worktree responde a git; su unión de node_modules apunta a la carpeta nueva; el .venv
    se reinstala y su activación lleva la ruta nueva; la configuración, las variables y los accesos directos cambian
    de ruta; la identidad (y con ella los espacios de trabajo) es la misma."""
    M = _m()
    import _winapi
    origen, wt = _repo(tmp_path)
    (wt / 'frontend').mkdir(exist_ok=True)
    union = wt / 'frontend' / 'node_modules'
    if union.exists():
        os.rmdir(union)
    _winapi.CreateJunction(str(origen / 'frontend' / 'node_modules'), str(union))
    destino = tmp_path / M.NOMBRE_NUEVO
    acceso = tmp_path / 'Escritorio' / 'Conversor viejo.lnk'
    acceso.parent.mkdir()
    acceso.write_bytes(b'lnk')
    m = _Maquina(entorno={'CSG_SUITE': str(origen / 'suite'), 'OTRA': 'C:/x'},
                 accesos=[{'acceso': str(acceso), 'objetivo': str(origen / 'run_gui.bat'), 'carpeta': str(origen)}])
    plan = M.planear(origen, destino, m)
    assert plan.impedimentos == [] and plan.ficheros == [str(Path('config') / 'suite.json')]
    assert [Path(u['enlace']) for u in plan.uniones] == [union]
    pasos = M.aplicar(plan, m)
    assert [p['paso'] for p in pasos if not p['ok']] == [], pasos
    assert destino.is_dir() and not origen.exists()
    assert _git('status', '--short', cwd=wt) == ''
    raiz = _git('rev-parse', '--show-toplevel', cwd=destino / '.worktrees' / 'dentro').strip()
    assert Path(raiz).resolve() == (destino / '.worktrees' / 'dentro').resolve()
    assert Path(os.readlink(union).removeprefix('\\\\?\\')) == destino / 'frontend' / 'node_modules'
    assert m.reinstalado == [destino]
    assert f'{destino}\\.venv' in (destino / '.venv' / 'Scripts' / 'activate.bat').read_text(encoding='utf-8')
    assert json.loads((destino / 'config' / 'suite.json').read_text(encoding='utf-8')) == \
        {'red': str(destino / 'datos' / 'red.txt')}
    assert m.puesto == {'CSG_SUITE': str(destino / 'suite')}
    assert m.escritos == [(acceso.with_name(M.ACCESO_NUEVO), str(destino / 'run_gui.bat'), str(destino))]
    assert not acceso.exists()
    assert M.identidad(destino) == 'a' * 16


def test_058_rf6_la_foto_de_los_espacios_y_su_respaldo_fuera(tmp_path):
    """058:RF-6 (086 T9, pasos 2, 3 y 10) — el plan hace la foto de los espacios de trabajo, y el respaldo de sus
    workspace.json y conversiones.json no puede ir dentro de la carpeta que se muda."""
    M = _m()
    assert hasattr(M, 'espacios_de'), 'falta la foto de los espacios (058:RF-6)'
    origen, _ = _repo(tmp_path)
    plan = M.planear(origen, tmp_path / M.NOMBRE_NUEVO, _Maquina(), respaldo=origen / 'respaldo')
    assert plan.espacios == ['e1', 'e2']
    assert any('va fuera de la carpeta que se muda' in i for i in plan.impedimentos), plan.impedimentos
    assert M.respaldar_espacios(origen, plan.espacios, tmp_path / 'fuera') == 4
    assert json.loads((tmp_path / 'fuera' / 'e2' / 'conversiones.json').read_text(encoding='utf-8')) == {'id': 'e2'}


@pytest.mark.skipif(os.name != 'nt', reason='las uniones de directorio son de Windows')
def test_058_rf6_la_mudanza_no_se_da_por_buena_si_falta_un_espacio_de_la_foto(tmp_path):
    """058:RF-6 (086 T9, «la web abre con los mismos espacios que la foto») — se respaldan antes de renombrar, y si
    después falta uno, la verificación falla y lo nombra."""
    M = _m()
    assert hasattr(M, 'espacios_de'), 'falta la foto de los espacios (058:RF-6)'
    origen, _ = _repo(tmp_path)
    destino = tmp_path / M.NOMBRE_NUEVO
    m = _Maquina()
    perdido = []

    def importar(d):
        import shutil
        shutil.rmtree(d / 'output' / 'web' / 'e1')
        perdido.append('e1')
        return str(d / 'src' / 'convertersmartgrid' / '__init__.py')
    m.importar = importar
    plan = M.planear(origen, destino, m, respaldo=tmp_path / 'respaldo')
    assert plan.impedimentos == []
    pasos = {p['paso']: p for p in M.aplicar(plan, m)}
    assert pasos['respaldo']['ok'] and (tmp_path / 'respaldo' / 'e1' / 'workspace.json').is_file()
    assert perdido and not pasos['verificar']['ok'] and "faltan ['e1']" in pasos['verificar']['detalle']
