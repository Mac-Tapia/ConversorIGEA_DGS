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


def test_los_datos_reales_no_van_a_github():
    """102:RF-15 — el fichero de variables está fuera de git y el flujo no nombra ninguna variable de datos reales."""
    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert not any(v in flujo for v in PC.VARIABLES)
    salida = subprocess.run(['git', 'check-ignore', str(PC.FICHERO_VARIABLES)], cwd=RAIZ, capture_output=True, text=True)
    assert salida.returncode == 0
