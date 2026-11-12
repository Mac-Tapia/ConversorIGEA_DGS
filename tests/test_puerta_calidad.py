"""Spec 102: la puerta de calidad. El 2026-11-08 dos commits entraron en ``main`` con tres pruebas en rojo."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def herramienta():
    spec = importlib.util.spec_from_file_location('puerta_calidad', RAIZ / 'tools' / 'puerta_calidad.py')
    modulo = importlib.util.module_from_spec(spec)
    sys.modules['puerta_calidad'] = modulo
    spec.loader.exec_module(modulo)
    return modulo


PC = herramienta()


def _repo(tmp_path: Path) -> Path:
    (tmp_path / 'tests').mkdir()
    for g in PC.GOBIERNO:
        (tmp_path / g).write_text('def test_x():\n    pass\n', encoding='utf-8')
    (tmp_path / 'tests' / 'test_motor.py').write_text('from convertersmartgrid import motor_red\n', encoding='utf-8')
    (tmp_path / 'tests' / 'test_otro.py').write_text('import json\n# motor_redes no es motor_red\n', encoding='utf-8')
    (tmp_path / 'tests' / 'test_guion.py').write_text("GUION = 'tools/ajuste_cabecera_pf.py'\n", encoding='utf-8')
    return tmp_path


def test_commit_corre_gobierno_y_las_pruebas_de_lo_que_cambia(tmp_path):
    """102:RF-1, 102:RF-2 — las de gobierno, las del commit y las que nombran el módulo o la herramienta."""
    raiz = _repo(tmp_path)
    elegidas = PC.pruebas_del_commit(['src/convertersmartgrid/motor_red.py', 'tools/ajuste_cabecera_pf.py',
                                      'tests/test_otro.py'], raiz)
    assert elegidas[:len(PC.GOBIERNO)] == list(PC.GOBIERNO)
    assert set(elegidas[len(PC.GOBIERNO):]) == {'tests/test_otro.py', 'tests/test_motor.py', 'tests/test_guion.py'}
    assert len(elegidas) == len(set(elegidas))


def test_commit_sin_codigo_corre_solo_gobierno(tmp_path):
    """102:RF-4 — un documento o un fichero del frontend no arrastra pruebas de módulos."""
    raiz = _repo(tmp_path)
    assert PC.pruebas_del_commit(['docs/NOTA.md', 'src/convertersmartgrid/__init__.py'], raiz) == list(PC.GOBIERNO)


def test_las_variables_vienen_del_fichero_local_y_del_entorno(tmp_path):
    """102:RF-6, 102:RF-7 — el entorno vale sobre el fichero; una que falta o sin ruta, se nombra."""
    (tmp_path / 'config').mkdir()
    datos = tmp_path / 'datos'
    datos.mkdir()
    variables = {k: str(datos) for k in PC.VARIABLES}
    (tmp_path / PC.FICHERO_VARIABLES).write_text(
        __import__('json').dumps({'variables': {k: v for k, v in variables.items() if k != 'CSG_RED'}}), encoding='utf-8')
    with pytest.raises(PC.PuertaError, match='CSG_RED'):
        PC.variables_de_la_suite(tmp_path, {})
    assert PC.variables_de_la_suite(tmp_path, {'CSG_RED': str(datos)})['CSG_RED'] == str(datos)
    with pytest.raises(PC.PuertaError, match='CSG_RED=.*no_existe'):
        PC.variables_de_la_suite(tmp_path, {'CSG_RED': str(tmp_path / 'no_existe')})


def test_el_veredicto_nombra_fallidas_y_omitidas_con_su_motivo(tmp_path):
    """102:RF-8, 102:RF-9 — del XML de JUnit, no del texto de pytest."""
    junit = tmp_path / 'junit.xml'
    junit.write_text(
        '<testsuites><testsuite>'
        '<testcase classname="tests.test_a" name="test_bien"/>'
        '<testcase classname="tests.test_a" name="test_mal"><failure message="assert 1 == 2">tb</failure></testcase>'
        '<testcase classname="tests.test_b" name="test_err"><error message="ImportError: x"/></testcase>'
        '<testcase classname="tests.test_c" name="test_sin_datos">'
        '<skipped message="falta CSG_VNR_BAK" type="pytest.skip"/></testcase>'
        '</testsuite></testsuites>', encoding='utf-8')
    juicio = PC.veredicto(junit)
    assert juicio['total'] == 4
    assert [f['prueba'] for f in juicio['fallidas']] == ['tests.test_a::test_mal', 'tests.test_b::test_err']
    assert juicio['omitidas'] == [{'prueba': 'tests.test_c::test_sin_datos', 'motivo': 'falta CSG_VNR_BAK'}]
    with pytest.raises(PC.PuertaError):
        PC.veredicto(tmp_path / 'no_hay.xml')


def _git_repo(tmp_path: Path) -> Path:
    for args in (['init', '-q'], ['config', 'user.email', 'puerta@ejemplo'], ['config', 'user.name', 'puerta']):
        subprocess.run(['git', *args], cwd=tmp_path, check=True)
    (tmp_path / 'a.txt').write_text('a', encoding='utf-8')
    subprocess.run(['git', 'add', 'a.txt'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-q', '-m', 'a'], cwd=tmp_path, check=True)
    return tmp_path


def test_el_resultado_se_guarda_por_revision_y_no_se_repite(tmp_path, monkeypatch):
    """102:RF-10, 102:RF-11 — aprobada con el árbol limpio, la misma revisión no vuelve a correr la suite."""
    raiz = _git_repo(tmp_path)
    cabeza = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz, capture_output=True, text=True).stdout.strip()
    corridas = []
    monkeypatch.setattr(PC, '_pytest', lambda *a, **k: corridas.append(a) or {'total': 1, 'fallidas': [], 'omitidas': []})
    monkeypatch.setattr(PC, 'variables_de_la_suite', lambda *_a, **_k: {})
    assert PC.puerta_push([cabeza], raiz) == 0 and len(corridas) == 1
    assert PC.resultado_guardado(cabeza, raiz)['aprobada']
    assert PC.puerta_push([cabeza], raiz) == 0 and len(corridas) == 1
    (raiz / 'a.txt').write_text('cambio', encoding='utf-8')
    assert not PC.arbol_limpio(raiz) and PC.puerta_push([cabeza], raiz) == 1


def test_una_omitida_detiene_la_subida(tmp_path, monkeypatch, capsys):
    """102:RF-5, 102:RF-9 — la regla de la suite: sin ninguna omitida; y no queda como aprobada."""
    raiz = _git_repo(tmp_path)
    cabeza = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz, capture_output=True, text=True).stdout.strip()
    monkeypatch.setattr(PC, '_pytest', lambda *a, **k: {'total': 2, 'fallidas': [],
                                                         'omitidas': [{'prueba': 't::x', 'motivo': 'sin SQL Server'}]})
    monkeypatch.setattr(PC, 'variables_de_la_suite', lambda *_a, **_k: {})
    assert PC.puerta_push([cabeza], raiz) == 1
    assert 'OMITIDA t::x: sin SQL Server' in capsys.readouterr().out
    assert PC.resultado_guardado(cabeza, raiz) is None


def test_sin_variables_la_subida_se_detiene(tmp_path, monkeypatch, capsys):
    """102:RF-7 — sin los datos reales no se sube."""
    raiz = _git_repo(tmp_path)
    cabeza = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz, capture_output=True, text=True).stdout.strip()
    # La suite completa corre con las variables en el entorno (la propia puerta las pone): aquí no deben estar.
    for variable in PC.VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(PC, '_pytest', lambda *a, **k: pytest.fail('no debe correr'))
    assert PC.puerta_push([cabeza], raiz) == 1
    assert 'Faltan variables de datos reales' in capsys.readouterr().out


def test_un_fallo_detiene_el_commit(tmp_path, monkeypatch, capsys):
    """102:RF-3 — el commit se detiene y nombra la prueba."""
    raiz = _git_repo(tmp_path)
    (raiz / 'tests').mkdir()
    (raiz / PC.GOBIERNO[0]).write_text('def test_x():\n    pass\n', encoding='utf-8')
    monkeypatch.setattr(PC, '_pytest', lambda *a, **k: {'total': 1, 'omitidas': [],
                                                         'fallidas': [{'prueba': 't::y', 'motivo': 'assert'}]})
    assert PC.puerta_commit(raiz) == 1
    assert 'FALLA t::y' in capsys.readouterr().out


def test_los_ganchos_llaman_a_la_puerta():
    """102:RF-16 — los ganchos de .githooks, que activa --instalar-ganchos (090:RF-11)."""
    commit = (RAIZ / '.githooks' / 'pre-commit').read_text(encoding='utf-8')
    push = (RAIZ / '.githooks' / 'pre-push').read_text(encoding='utf-8')
    assert 'regenerar.sh' in commit and commit.index('regenerar.sh') < commit.index('puerta_calidad.py" --commit')
    assert 'puerta_calidad.py" --push' in push
    assert "'core.hooksPath', '.githooks'" in (RAIZ / 'tools' / 'generar_arquitectura.py').read_text(encoding='utf-8')


def test_github_corre_la_suite_sintetica_y_el_frontend():
    """102:RF-12, 102:RF-13, 102:RF-14 — en Windows con Python 3.12; un paso que falla deja el flujo en rojo."""
    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert 'windows-latest' in flujo and "python-version: '3.12'" in flujo
    assert 'python tools/puerta_calidad.py --ci' in flujo and 'continue-on-error' not in flujo
    assert 'npm run build' in flujo and 'npm test' in flujo


def test_github_tiene_el_entorno_de_desarrollo_y_solo_omite_la_falta_de_gpu(monkeypatch):
    """102:RF-17 — .venv, extra ml y frontend en el flujo; la omisión es solo SinGPU, y fuera de GitHub nunca."""
    import conftest
    from convertersmartgrid.training_coordinator import SinGPU

    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert 'python -m venv .venv' in flujo and '-e ".[ml]"' in flujo and 'npm ci' in flujo
    assert '1fd1de97d3e8e48c298f6ccf5ac91cbfc417b42c61262c08d193fd14117e9098' in flujo     # Ipopt de la 048
    assert f"{conftest.VARIABLE_CI_SIN_GPU}: '1'" in flujo
    try:
        raise SinGPU('No hay GPU CUDA')
    except SinGPU as causa:
        try:
            raise RuntimeError('el modelo no entrena') from causa
        except RuntimeError as encadenada:
            assert conftest._por_falta_de_gpu(encadenada)
    assert not conftest._por_falta_de_gpu(RuntimeError('otro fallo'))
    assert not conftest._por_falta_de_gpu(AssertionError('GPU'))
    monkeypatch.delenv(conftest.VARIABLE_CI_SIN_GPU, raising=False)
    assert not conftest._ci_sin_cuda()


def test_los_datos_reales_no_van_a_github():
    """102:RF-15 — el fichero de variables está fuera de git y el flujo no nombra ninguna variable de datos reales."""
    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert not any(v in flujo for v in PC.VARIABLES)
    salida = subprocess.run(['git', 'check-ignore', str(PC.FICHERO_VARIABLES)], cwd=RAIZ, capture_output=True, text=True)
    assert salida.returncode == 0


def test_una_rama_de_trabajo_sube_sin_suite_y_main_la_exige(monkeypatch, capsys):
    """102:RF-5, 102:RF-18 — la suite completa, solo para lo que llega a main; un borrado de rama no sube nada."""
    sha_a, sha_b, cero = 'a' * 40, 'b' * 40, '0' * 40
    lineas = [f'refs/heads/trabajo/x {sha_a} refs/heads/trabajo/x {cero}',
              f'refs/heads/main {sha_b} refs/heads/main {cero}',
              f'(delete) {cero} refs/heads/vieja {sha_a}']
    assert PC.revisiones_por_destino(lineas) == ([sha_b], ['trabajo/x'])
    corridas = []
    monkeypatch.setattr(PC, 'puerta_push', lambda revs, *a, **k: corridas.append(list(revs)) or 0)
    monkeypatch.setattr(PC.sys, 'stdin', __import__('io').StringIO(lineas[0] + '\n'))
    assert PC.main(['--push']) == 0 and corridas == []
    assert 'rama de trabajo' in capsys.readouterr().out
    monkeypatch.setattr(PC.sys, 'stdin', __import__('io').StringIO('\n'.join(lineas[:2]) + '\n'))
    assert PC.main(['--push']) == 0 and corridas == [[sha_b]]
    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert "branches: ['**']" in flujo


def test_102_rf19_las_pruebas_no_heredan_las_variables_del_gancho(tmp_path, monkeypatch):
    """102:RF-19 — GIT_INDEX_FILE y las demás GIT_* del gancho no llegan a pytest; el resto del entorno sí."""
    vistos = {}
    monkeypatch.setenv('GIT_INDEX_FILE', str(tmp_path / 'index.lock'))
    monkeypatch.setenv('GIT_DIR', str(tmp_path))

    class Corrida:
        returncode = 0

    def correr(cmd, cwd, env):
        vistos.update(env)
        (tmp_path / 'junit.xml').write_text('<testsuites><testsuite/></testsuites>', encoding='utf-8')
        junit = next(a.split('=', 1)[1] for a in cmd if a.startswith('--junitxml='))
        __import__('shutil').copy(tmp_path / 'junit.xml', junit)
        return Corrida()

    monkeypatch.setattr(PC.subprocess, 'run', correr)
    PC._pytest([], {'CSG_X': '1'}, tmp_path)
    assert not any(k.startswith('GIT_') for k in vistos) and vistos['CSG_X'] == '1' and 'PATH' in vistos


def test_102_rf20_el_entorno_vuelve_como_estaba():
    """102:RF-20 — lo que escribe el lanzador de la web en el entorno no queda para la prueba siguiente."""
    import os

    from conftest import entorno_restituido

    previo = os.environ.get('CSG_WEB_HOST')
    with entorno_restituido():
        os.environ['CSG_WEB_HOST'] = '0.0.0.0'
        os.environ['CSG_PRUEBA_102_RF20'] = '1'
    assert os.environ.get('CSG_WEB_HOST') == previo and 'CSG_PRUEBA_102_RF20' not in os.environ


def test_102_rf20_el_cierre_registrado_no_pasa_a_otra_prueba():
    """102:RF-20 — el lanzador registra el cierre de la web; la prueba siguiente empieza sin él (paso 1 de 2)."""
    from convertersmartgrid.web import app as app_mod

    app_mod.al_pedir_cierre(lambda: None)
    assert app_mod._cierre


def test_102_rf20_el_cierre_registrado_no_pasa_a_otra_prueba_2():
    """102:RF-20 — paso 2 de 2: sin el cierre de la prueba anterior."""
    from convertersmartgrid.web import app as app_mod

    assert app_mod._cierre == []


def test_102_rf21_la_puerta_corre_los_procedimientos():
    """102:RF-21 — las citas de línea de los procedimientos se comprueban en cada commit."""
    assert 'tests/test_procedimientos.py' in PC.GOBIERNO


def test_102_rf22_cada_prueba_con_su_guardia_de_gpu(tmp_path):
    """102:RF-22 — la guardia de la prueba no es la de la máquina: un entrenamiento real no tumba la puerta."""
    from convertersmartgrid.training_coordinator import ruta_guardia_gpu

    guardia = ruta_guardia_gpu()
    assert guardia == tmp_path / 'gpu.lock'
    assert guardia != ruta_guardia_gpu({'LOCALAPPDATA': 'C:/Users/x/AppData/Local'})


def test_102_rf23_la_puerta_pasa_todas_las_variables_que_las_pruebas_piden():
    """102:RF-23 — una variable que una prueba nombra al omitirse, o que trae el ejemplo, la pasa la puerta."""
    import json
    import re

    nombradas = set()
    for prueba in (RAIZ / 'tests').rglob('*.py'):
        for linea in prueba.read_text(encoding='utf-8').splitlines():
            if 'skip' in linea:
                nombradas.update(re.findall(r'\bCSG_[A-Z0-9_]+', linea))
    ejemplo = json.loads((RAIZ / 'config' / 'suite_completa.example.json').read_text(encoding='utf-8'))
    del_ejemplo = set(ejemplo['variables'])
    assert 'CSG_PF_PYTHON_39' in nombradas      # el caso que la motivó
    assert nombradas - set(PC.VARIABLES) == set()
    assert del_ejemplo == set(PC.VARIABLES)