"""DIgSILENT de cualquier versión instalada (spec 103)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from convertersmartgrid import powerfactory_env as pe


def _instalar(raiz: Path, nombre: str, pythons: tuple[str, ...]) -> Path:
    """Una PowerFactory simulada: su carpeta y una carpeta ``Python\\3.x`` con la API por cada versión."""
    carpeta = raiz / 'DIgSILENT' / nombre
    for v in pythons:
        api = carpeta / 'Python' / v
        api.mkdir(parents=True)
        (api / 'powerfactory.pyd').write_bytes(b'')
    return carpeta


@pytest.fixture
def maquina(tmp_path):
    """2021 con 3.9, 2022 SP1 con 3.9 y 3.10, 2024 con 3.8 a 3.12 y, en otra unidad, 2025 con 3.10 a 3.13."""
    c = tmp_path / 'C' / 'Program Files'
    d = tmp_path / 'D' / 'Program Files'
    _instalar(c, 'PowerFactory 2021 SP3', ('3.9',))
    _instalar(c, 'PowerFactory 2022 SP1', ('3.9', '3.10'))
    _instalar(c, 'PowerFactory 2024', ('3.8', '3.9', '3.10', '3.11', '3.12'))
    _instalar(d, 'PowerFactory 2025', ('3.10', '3.11', '3.12', '3.13'))
    return [c / 'DIgSILENT', d / 'DIgSILENT']


def _interpretes(*versiones):
    """Solo hay intérprete para estas versiones."""
    return lambda v: (Path(f'C:/python{v}/python.exe'), f'prueba {v}') if v in versiones else (None, f'sin {v}')


def test_103_rf1_encuentra_todas_las_instalaciones(maquina):
    """103:RF-1 — en cada unidad, con su año y service pack, y las carpetas de API que traen la extensión."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    assert [i.nombre for i in encontradas] == ['PowerFactory 2025', 'PowerFactory 2024', 'PowerFactory 2022 SP1',
                                              'PowerFactory 2021 SP3']
    assert encontradas[0].version == (2025, 0) and encontradas[2].version == (2022, 1)
    assert [a.name for a in encontradas[1].apis] == ['3.12', '3.11', '3.10', '3.9', '3.8']


def test_103_rf1_lee_las_que_registra_windows(tmp_path):
    """103:RF-1 — una instalación fuera de las carpetas habituales se encuentra por el registro, sin repetirse."""
    fuera = _instalar(tmp_path / 'Otra', 'PowerFactory 2023 SP5', ('3.11',))
    encontradas = pe.instalaciones(raices=[fuera.parent], registro=[str(fuera) + '\\'])
    assert [i.nombre for i in encontradas] == ['PowerFactory 2023 SP5']


def test_103_rf2_elige_la_api_que_tiene_interprete(maquina):
    """103:RF-2 — 2025 trae 3.13, pero con el Python 3.12 del programa se elige su carpeta 3.12, no la más alta."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    api, interprete, _motivo = pe.elegir_api(encontradas[0], _interpretes('3.12'))
    assert api.name == '3.12' and interprete == Path('C:/python3.12/python.exe')
    # 2021 solo trae 3.9: con un 3.9 embebido carga; sin él, no hay carpeta que sirva.
    assert pe.elegir_api(encontradas[3], _interpretes('3.12', '3.9'))[0].name == '3.9'
    assert pe.elegir_api(encontradas[3], _interpretes('3.12')) is None


def test_103_rf2_el_python_del_programa_primero(maquina, monkeypatch):
    """103:RF-2 — si el Python del programa encaja, se usa ese antes que cualquier otro."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    actual = f'{pe.sys.version_info.major}.{pe.sys.version_info.minor}'
    api, interprete, motivo = pe.elegir_api(encontradas[1], pe.interprete_para)
    assert api.name == actual and interprete == Path(pe.sys.executable) and 'actual' in motivo


def test_103_rf2_los_embebidos_del_instalador(tmp_path, monkeypatch):
    """103:RF-2, RF-6 — un Python embebido en la carpeta del programa sirve para su versión."""
    embebido = tmp_path / pe.CARPETA_PYTHON_EMBEBIDOS / '3.9' / 'python.exe'
    embebido.parent.mkdir(parents=True)
    embebido.write_bytes(b'')
    monkeypatch.setattr(pe, 'raiz_programa', lambda: tmp_path)
    monkeypatch.setattr(pe, '_sondear_py', lambda _v: None)
    assert pe.interprete_para('3.9')[0] == embebido


def test_103_rf4_el_diagnostico_dice_lo_instalado_y_lo_que_falta(maquina, monkeypatch):
    """103:RF-4 — sin versión fija: cada PowerFactory con su API, o el Python que le falta."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    lineas = pe.resumen_instalaciones(encontradas, _interpretes('3.12'))
    assert lineas[0] == 'PowerFactory 2025: API 3.12 con prueba 3.12.'
    assert lineas[-1] == 'PowerFactory 2021 SP3: falta un intérprete de Python 3.9 para cargar su API.'
    from convertersmartgrid.web import doctor
    monkeypatch.setattr(pe, 'resumen_instalaciones', lambda: [])
    c = doctor._digsilent(lambda: None)
    assert '2024' not in c.arreglo and '3.12' not in c.arreglo and '2021 o posterior' in c.arreglo


def test_103_rf4_ningun_mensaje_con_una_version_fija():
    """103:RF-4 — ni rutas ni mensajes que pidan una versión concreta de PowerFactory o de Python."""
    raiz = Path(__file__).resolve().parents[1]
    prohibidos = (r'PowerFactory 2024\Python', 'PF 2024 pide', 'Abra PF 2024', 'PowerFactory 2024 con su Python')
    for fichero in ('src/convertersmartgrid/powerfactory_env.py', 'src/convertersmartgrid/web/doctor.py',
                    'tools/check_pf_license.py', 'tools/powerfactory_acceptance.py'):
        texto = (raiz / fichero).read_text(encoding='utf-8')
        assert not [p for p in prohibidos if p in texto], fichero


def test_103_rf7_sin_digsilent_se_sigue_convirtiendo(monkeypatch):
    """103:RF-7 — sin ninguna PowerFactory el diagnóstico no lo pone como obligatorio y dice que el DGS sigue."""
    from convertersmartgrid.web import doctor
    monkeypatch.setattr(pe, 'resumen_instalaciones', lambda: [])
    c = doctor._digsilent(lambda: None)
    assert c.ok is False and c.obligatoria is False and 'Convertir a DGS sigue funcionando' in c.afecta


# ------------------------------------------------------------------ 103:RF-5

RAIZ = Path(__file__).resolve().parents[1]
#: Los guiones que corren con el Python de PowerFactory, y el comprobador de licencia y la aceptación.
GUIONES_PF = sorted([*(RAIZ / 'tools').glob('*_pf.py'), RAIZ / 'tools/powerfactory_acceptance.py',
                     RAIZ / 'tools/check_pf_license.py'])
#: Las de la biblioteca posteriores a 3.9 que ya aparecieron (2026-11-11): rompían 12 de los 22 guiones en 3.9.
POSTERIORES_A_39 = (re.compile(r'\bfrom itertools import [^\n]*\bpairwise\b'), re.compile(r'\bzip\([^)]*\bstrict='),
                    re.compile(r'\bfrom typing import [^\n]*\b(?:TypeAlias|ParamSpec|Self|TypeGuard)\b'),
                    re.compile(r'\bimport tomllib\b'), re.compile(r'\bdatetime\.UTC\b|from datetime import [^\n]*\bUTC\b'))


def _cierre_de_los_guiones() -> list[Path]:
    """Los ficheros del repositorio que cargan los guiones, con un Python sin librerías de terceros."""
    codigo = ('import importlib, os, sys\n'
              f"sys.path[:0] = [{str(RAIZ / 'src')!r}, {str(RAIZ / 'tools')!r}]\n"
              f'for m in {[g.stem for g in GUIONES_PF]!r}:\n'
              '    try:\n        importlib.import_module(m)\n'
              '    except ModuleNotFoundError as exc:\n'
              "        if exc.name != 'numpy': print('FALTA', m, exc.name)\n"
              'for mod in list(sys.modules.values()):\n'
              "    f = getattr(mod, '__file__', None)\n"
              '    if f: print(os.path.abspath(f))\n')
    salida = subprocess.run([sys.executable, '-S', '-c', codigo], capture_output=True, text=True, check=True).stdout
    faltan = [linea for linea in salida.splitlines() if linea.startswith('FALTA')]
    assert not faltan, f'librerías de terceros en los guiones de DIgSILENT: {faltan}'
    raiz = os.path.normcase(str(RAIZ))
    return sorted({Path(linea) for linea in salida.splitlines()
                   if os.path.normcase(linea).startswith(raiz) and 'site-packages' not in linea})


def test_103_rf5_los_guiones_cargan_con_python_39():
    """103:RF-5 — sin sintaxis ni funciones posteriores a 3.9 y sin más librerías de terceros que numpy."""
    cierre = _cierre_de_los_guiones()
    assert len(cierre) > len(GUIONES_PF)
    # compat_pf usa los nativos solo en 3.10 o posterior: es el único sitio donde pueden ir.
    usadas = [f'{f.relative_to(RAIZ)}: {p.pattern}' for f in cierre if f.name != 'compat_pf.py' for p in POSTERIORES_A_39
              if p.search(f.read_text(encoding='utf-8'))]
    assert not usadas, usadas
    ruff = Path(sys.executable).with_name('ruff.exe' if os.name == 'nt' else 'ruff')
    if ruff.is_file():
        r = subprocess.run([str(ruff), 'check', '--target-version', 'py39', '--select', 'F401', '--output-format', 'concise',
                            *map(str, cierre)], capture_output=True, text=True, check=False)
        assert 'invalid-syntax' not in r.stdout, r.stdout


def test_103_rf5_cargan_de_verdad_con_un_python_39():
    """103:RF-5 — con el Python 3.9 real (el embebido de python.org), cada guion carga; numpy va con el instalador."""
    py39 = os.environ.get('CSG_PF_PYTHON_39') or ''
    if not Path(py39).is_file():
        py39 = str(pe.interprete_para('3.9')[0] or '')
    if not Path(py39).is_file():
        pytest.skip('sin intérprete Python 3.9: CSG_PF_PYTHON_39 (embebido oficial de python.org)')
    fallan = []
    for guion in GUIONES_PF:
        codigo = (f"import sys; sys.path[:0] = [{str(RAIZ / 'src')!r}, {str(RAIZ / 'tools')!r}]\n"
                  f'try:\n    import {guion.stem}\n'
                  "except ModuleNotFoundError as exc:\n    if exc.name != 'numpy': raise\n")
        r = subprocess.run([py39, '-c', codigo], capture_output=True, text=True, check=False)
        if r.returncode:
            fallan.append(f'{guion.stem}: {(r.stderr.strip().splitlines() or ["?"])[-1]}')
    assert not fallan, fallan


def test_103_rf5_compatibilidad_de_pairwise_y_zip_estricto():
    """103:RF-5 — los equivalentes dan lo mismo que los nativos y el estricto falla con largos distintos."""
    from convertersmartgrid.compat_pf import pairwise, zip_estricto
    assert list(pairwise([1, 2, 3])) == [(1, 2), (2, 3)] and list(pairwise([])) == []
    assert list(zip_estricto([1, 2], 'ab')) == [(1, 'a'), (2, 'b')]
    with pytest.raises(ValueError):
        list(zip_estricto([1, 2], 'a'))


# ------------------------------------------------------------------ 103:RF-3

def test_103_rf3_la_eleccion_del_operador_se_recuerda(maquina, tmp_path, monkeypatch):
    """103:RF-3 — la más nueva que funciona por defecto; la elegida, recordada; PF_PYTHON por encima de todo."""
    encontradas = pe.instalaciones(raices=maquina, registro=())
    monkeypatch.delenv('PF_PYTHON', raising=False)
    monkeypatch.setattr(pe, 'instalaciones', lambda *a, **k: encontradas)
    monkeypatch.setattr(pe, 'interprete_para', _interpretes('3.12', '3.9'))
    monkeypatch.setattr(pe, 'ruta_eleccion', lambda: tmp_path / 'config' / 'powerfactory.json')
    assert pe.pf_python_dir() == encontradas[0].carpeta / 'Python' / '3.12'           # la 2025, por su 3.12
    antigua = encontradas[3].carpeta / 'Python' / '3.9'
    pe.guardar_eleccion(antigua)
    assert pe.pf_python_dir() == antigua
    monkeypatch.setenv('PF_PYTHON', str(encontradas[1].apis[0]))
    assert pe.pf_python_dir() == encontradas[1].apis[0]
    monkeypatch.delenv('PF_PYTHON')
    pe.guardar_eleccion(None)
    assert pe.pf_python_dir() == encontradas[0].carpeta / 'Python' / '3.12'
    # Una elección que ya no existe (se desinstaló) no se usa.
    (tmp_path / 'config' / 'powerfactory.json').write_text('{"carpeta_api": "Z:/no/existe/Python/3.9"}', encoding='utf-8')
    assert pe.pf_python_dir() == encontradas[0].carpeta / 'Python' / '3.12'


def test_103_rf3_la_web_lista_y_elige(maquina, tmp_path, monkeypatch):
    """103:RF-3 — la web lista las encontradas, acepta una de ellas y rechaza una carpeta ajena."""
    from fastapi.testclient import TestClient

    from convertersmartgrid.web.app import create_app
    encontradas = pe.instalaciones(raices=maquina, registro=())
    monkeypatch.delenv('PF_PYTHON', raising=False)
    monkeypatch.setattr(pe, 'instalaciones', lambda *a, **k: encontradas)
    monkeypatch.setattr(pe, 'interprete_para', _interpretes('3.12', '3.9'))
    monkeypatch.setattr(pe, 'python_for_pf', lambda d: _interpretes('3.12', '3.9')(d.name))
    monkeypatch.setattr(pe, 'ruta_eleccion', lambda: tmp_path / 'config' / 'powerfactory.json')
    monkeypatch.setenv('CSG_WEB_FRONTEND', str(tmp_path / 'sin_front'))
    from convertersmartgrid.web import services
    monkeypatch.setattr(services, 'pf_python_dir', pe.pf_python_dir)
    monkeypatch.setattr(services, 'python_for_pf', pe.python_for_pf)
    with TestClient(create_app(tmp_path / 'web')) as c:
        r = c.get('/api/powerfactory/instalaciones').json()
        assert [i['nombre'] for i in r['instalaciones']][0] == 'PowerFactory 2025' and r['eleccion'] is None
        antigua = str(encontradas[3].carpeta / 'Python' / '3.9')
        r = c.post('/api/powerfactory/instalaciones', json={'carpeta_api': antigua}).json()
        assert r['eleccion'] == antigua and r['en_uso'] == antigua
        assert c.post('/api/powerfactory/instalaciones', json={'carpeta_api': 'C:/otra/Python/3.12'}).status_code == 422
        assert c.post('/api/powerfactory/instalaciones', json={'carpeta_api': None}).json()['eleccion'] is None


# ------------------------------------------------------------------ 103:RF-2, RF-6 (el proceso del guion)

def test_103_rf6_el_entorno_pone_las_librerias_del_interprete_antes_que_el_paquete(tmp_path):
    """103:RF-6 — con otro intérprete: la API, sus librerías y luego el paquete; con el del programa, solo la API."""
    api = tmp_path / 'PowerFactory 2021 SP3' / 'Python' / '3.9'
    otro = tmp_path / 'python_pf' / '3.9' / 'python.exe'
    rutas = pe.pf_subprocess_env(api, otro)['PYTHONPATH'].split(os.pathsep)
    assert rutas[:3] == [str(api), str(otro.parent / 'Lib' / 'site-packages'), str(pe.carpeta_del_paquete())]
    assert pe.pf_subprocess_env(api, Path(sys.executable))['PYTHONPATH'].split(os.pathsep)[0] == str(api)
    assert str(pe.carpeta_del_paquete()) not in pe.pf_subprocess_env(api, Path(sys.executable))['PYTHONPATH'].split(os.pathsep)
    # 103:RF-6: el PYTHONHOME del lanzador (el del 3.12) no pasa a otro intérprete.
    import unittest.mock
    with unittest.mock.patch.dict(os.environ, {'PYTHONHOME': 'D:/programa/python'}):
        otro_env = pe.pf_subprocess_env(api, otro)
        assert 'PYTHONHOME' not in otro_env and otro_env['PYTHONNOUSERSITE'] == '1'
        assert pe.pf_subprocess_env(api, Path(sys.executable))['PYTHONHOME'] == 'D:/programa/python'


def test_103_rf6_el_guion_carga_su_numpy_y_el_paquete_con_otro_python(tmp_path):
    """103:RF-6 — un proceso con el Python 3.9 embebido carga su numpy (no el del programa) y el paquete del conversor."""
    py39 = os.environ.get('CSG_PF_PYTHON_39') or ''
    if not Path(py39).is_file():
        pytest.skip('sin intérprete Python 3.9: CSG_PF_PYTHON_39 (embebido oficial de python.org con su numpy)')
    env = pe.pf_subprocess_env(tmp_path / 'api', Path(py39))
    r = subprocess.run([py39, '-c', 'import sys, numpy, convertersmartgrid.valle as v; '
                        'print(sys.version_info[:2], numpy.__file__, v.__file__)'],
                       capture_output=True, text=True, env=env, check=False)
    assert r.returncode == 0, r.stderr
    assert '(3, 9)' in r.stdout and str(Path(py39).parent).lower() in r.stdout.lower()
    assert str(pe.carpeta_del_paquete()).lower() in r.stdout.lower()


def _herramienta(nombre):
    import importlib.util
    sys.path.insert(0, str(RAIZ / 'tools'))
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / 'tools' / f'{nombre}.py')
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_103_rf6_el_candidato_trae_los_python_de_powerfactory_y_se_instalan(tmp_path):
    """103:RF-6 — el candidato lleva cada Python sin ._pth y su numpy como rueda; al instalar, por su huella."""
    import hashlib
    import json
    import zipfile
    cc, ic = _herramienta('construir_candidato'), _herramienta('instalar_candidato')
    origen = tmp_path / 'origen'
    origen.mkdir()
    with zipfile.ZipFile(origen / 'python-3.9.13-embed-amd64.zip', 'w') as z:
        z.writestr('python.exe', b'')
        z.writestr('python39._pth', 'python39.zip\n.\n')
    with zipfile.ZipFile(origen / 'numpy-2.0.2-cp39-cp39-win_amd64.whl', 'w') as z:
        z.writestr('numpy/__init__.py', '__version__ = "2.0.2"\n')
    sha = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in origen.iterdir()}
    fijados = {'3.9': {'zip': 'python-3.9.13-embed-amd64.zip', 'sha256': sha['python-3.9.13-embed-amd64.zip'],
                       'numpy': 'numpy-2.0.2-cp39-cp39-win_amd64.whl', 'numpy_sha256': sha['numpy-2.0.2-cp39-cp39-win_amd64.whl']}}
    candidato = tmp_path / 'candidato'
    componentes = cc.empaquetar_python_pf(origen, candidato / 'terceros', fijados)
    pf = candidato / 'terceros' / 'python_pf'
    assert (pf / '3.9' / 'python.exe').is_file() and not list((pf / '3.9').glob('*._pth'))
    assert not (pf / '3.9' / 'Lib' / 'site-packages' / 'numpy').exists()          # va como rueda: datos .npz vedados
    assert {c['name'] for c in componentes} == {'CPython', 'numpy'}
    version = tmp_path / 'instalado' / 'versiones' / '1.0.0'
    ic._instalar_python_pf(candidato, version)
    assert (version / 'python_pf' / '3.9' / 'Lib' / 'site-packages' / 'numpy' / '__init__.py').is_file()
    # Una rueda alterada no se instala.
    with zipfile.ZipFile(pf / 'ruedas' / 'numpy-2.0.2-cp39-cp39-win_amd64.whl', 'a') as z:
        z.writestr('numpy/otro.py', 'x = 1\n')
    with pytest.raises(ic.ErrorInstalacion, match='huella'):
        ic._instalar_python_pf(candidato, tmp_path / 'otra' / 'versiones' / '1.0.0')
    assert json.loads((pf / 'huellas.json').read_text(encoding='utf-8'))['3.9']['numpy'].startswith('numpy-2.0.2')


def test_103_rf6_un_zip_que_no_es_el_fijado_no_entra(tmp_path):
    """103:RF-6 — un Python que no tiene el SHA-256 de config/entrega.json no se usa."""
    import zipfile
    cc = _herramienta('construir_candidato')
    falso = tmp_path / 'python-3.9.13-embed-amd64.zip'
    with zipfile.ZipFile(falso, 'w') as z:
        z.writestr('python.exe', b'otro')
    with pytest.raises(cc.CE.EntregaError, match='SHA-256'):
        cc.extraer_python_pf(falso, tmp_path / 'destino', sha_zip='0' * 64)


def test_103_rf6_el_diagnostico_lista_los_python_de_powerfactory(tmp_path, monkeypatch):
    """103:RF-6 — el diagnóstico dice qué Python trae el programa para las otras PowerFactory."""
    for v in ('3.11', '3.9', '3.10'):
        exe = tmp_path / pe.CARPETA_PYTHON_EMBEBIDOS / v / 'python.exe'
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b'')
    monkeypatch.setattr(pe, 'raiz_programa', lambda: tmp_path)
    assert pe.interpretes_embebidos() == ['3.9', '3.10', '3.11']
    api = tmp_path / 'PowerFactory 2024' / 'Python' / '3.12'
    api.mkdir(parents=True)
    (api / 'powerfactory.pyd').write_bytes(b'')
    from convertersmartgrid.web import doctor
    monkeypatch.setattr(pe, 'resumen_instalaciones', lambda: [])
    assert 'Python para otras PowerFactory: 3.9, 3.10, 3.11.' in doctor._digsilent(lambda: api).detalle
