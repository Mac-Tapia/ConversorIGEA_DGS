"""Spec 102: la puerta de calidad. El 2026-11-08 dos commits entraron en ``main`` con tres pruebas en rojo."""
from __future__ import annotations

import importlib.util
import re
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
    from convertersmartgrid.aplicacion.training_coordinator import SinGPU

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
    from convertersmartgrid.presentacion.web import app as app_mod

    app_mod.al_pedir_cierre(lambda: None)
    assert app_mod._cierre


def test_102_rf20_el_cierre_registrado_no_pasa_a_otra_prueba_2():
    """102:RF-20 — paso 2 de 2: sin el cierre de la prueba anterior."""
    from convertersmartgrid.presentacion.web import app as app_mod

    assert app_mod._cierre == []


def test_102_rf21_la_puerta_corre_los_procedimientos():
    """102:RF-21 — las citas de línea de los procedimientos se comprueban en cada commit."""
    assert 'tests/test_procedimientos.py' in PC.GOBIERNO


def test_102_rf22_cada_prueba_con_su_guardia_de_gpu(tmp_path):
    """102:RF-22 — la guardia de la prueba no es la de la máquina: un entrenamiento real no tumba la puerta."""
    from convertersmartgrid.aplicacion.training_coordinator import ruta_guardia_gpu

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


def test_lo_comun_a_todas_las_pruebas_corre_la_suite_entera(tmp_path, monkeypatch):
    """106:RF-13 — un cambio en el conftest o en pyproject.toml corre todas las pruebas; un ayudante, las que lo nombran."""
    from apoyo import cargar_herramienta

    puerta = cargar_herramienta('puerta_calidad.py', 'puerta_comun', tools_en_path=True)
    raiz = Path(__file__).resolve().parents[1]
    # PUERTA-CAPAS: el caso «solo capas» se prueba aparte, en un repositorio propio; aquí no depende del índice vivo
    # (en la puerta, un commit solo de capas está en el índice).
    monkeypatch.setattr(puerta, 'pyproject_cambia_solo_capas', lambda raiz=None: False, raising=False)
    assert puerta.pruebas_del_commit(['tests/conftest.py'], raiz) == ['tests']
    assert puerta.pruebas_del_commit(['pyproject.toml', 'src/convertersmartgrid/dominio/naming.py'], raiz) == ['tests']
    con_fake = puerta.pruebas_del_commit(['tests/fake_pf.py'], raiz)
    propias = [p for p in con_fake if p not in puerta.GOBIERNO]
    assert con_fake != ['tests'] and propias
    assert all('fake_pf' in (raiz / p).read_text(encoding='utf-8') for p in propias)
    # Un repositorio sin tests/ (el de las pruebas de los ganchos de la 090) no pide la suite: 102:RF-16.
    assert puerta.pruebas_del_commit(['pyproject.toml'], tmp_path) == []


def test_el_resultado_guarda_las_mas_lentas_y_avisa_de_las_del_umbral(tmp_path, capsys):
    """106:RF-15 — el junit da los tiempos; el resultado guarda las 30 más lentas y avisa, sin fallar, de las que pasan
    del umbral de faulthandler_timeout, que es el mismo de pyproject.toml."""
    import tomllib

    casos = ''.join(f'<testcase classname="tests.test_t" name="p{i}" time="{i}"/>' for i in range(40))
    casos += '<testcase classname="tests.test_t" name="colgada" time="2000.5"/>'
    junit = tmp_path / 'junit.xml'
    junit.write_text(f'<testsuites><testsuite>{casos}</testsuite></testsuites>', encoding='utf-8')
    juicio = PC.veredicto(junit)
    assert len(juicio['lentas']) == PC.LENTAS_GUARDADAS == 30
    assert juicio['lentas'][0] == {'prueba': 'tests.test_t::colgada', 'segundos': 2000.5}
    assert juicio['lentas'][1]['prueba'] == 'tests.test_t::p39'
    assert juicio['mas_de_umbral'] == [juicio['lentas'][0]]
    assert PC._informar(juicio, omitidas_cuentan=True) is True
    assert 'LENTA tests.test_t::colgada' in capsys.readouterr().out
    ini = tomllib.loads((Path(__file__).resolve().parents[1] / 'pyproject.toml').read_text(encoding='utf-8'))
    assert ini['tool']['pytest']['ini_options']['faulthandler_timeout'] == PC.UMBRAL_PRUEBA_LENTA_S



def test_106_rf13_un_fichero_que_no_es_codigo_elige_las_pruebas_que_lo_nombran(tmp_path):
    """106:RF-13 — un cambio en un fichero que no es un módulo de Python (el .iss del instalador, un .json de
    configuración…) elige las pruebas que lo nombran. 2026-11-13: un commit cambió el .iss del instalador y su puerta no
    eligió test_instalador_qa, que lo lee; la regresión entró y la rama quedó en rojo."""
    raiz = _repo(tmp_path)
    (raiz / 'instalador').mkdir()
    (raiz / 'instalador' / 'Programa.iss').write_text('#define X "1"\n', encoding='utf-8')
    (raiz / 'tests' / 'test_instalador.py').write_text("ISS = RAIZ / 'instalador' / 'Programa.iss'\n", encoding='utf-8')
    elegidas = PC.pruebas_del_commit(['instalador/Programa.iss'], raiz)
    assert 'tests/test_instalador.py' in elegidas
    assert 'tests/test_otro.py' not in elegidas


def test_106_rf16_un_codigo_de_error_sin_pruebas_fallidas_no_aprueba(tmp_path, monkeypatch):
    """106:RF-16 — pytest con el código 1 y un junit sin ninguna fallida (la sesión falló por algo que no es una prueba,
    como una línea de pruebas en un registro real de la web) no se da por bueno: antes la puerta solo miraba los códigos
    distintos de 0 y 1, y con 1 decía «0 fallidas» y aprobaba."""

    class Corrida:
        returncode = 1

    def correr(cmd, cwd, env):
        junit = next(a.split('=', 1)[1] for a in cmd if a.startswith('--junitxml='))
        Path(junit).write_text('<testsuites><testsuite tests="3" failures="0" errors="0" skipped="0">'
                               '<testcase classname="t" name="a"/><testcase classname="t" name="b"/>'
                               '<testcase classname="t" name="c"/></testsuite></testsuites>', encoding='utf-8')
        return Corrida()

    monkeypatch.setattr(PC.subprocess, 'run', correr)
    juicio = PC._pytest([], {}, tmp_path)
    assert juicio['fallidas'], juicio
    assert 'código 1' in juicio['fallidas'][0]['motivo'] and 'una prueba que escribió en un registro real' in juicio['fallidas'][0]['motivo']


_PYPROJECT = """[project]
name = "x"
dependencies = ["a>=1"]

[tool.pytest.ini_options]
filterwarnings = ["error"]

[tool.convertersmartgrid.capas]
reglas = "r"

[tool.convertersmartgrid.capas.modulos]
"x.uno" = "dominio"
"""


def _repo_git_capas(tmp_path: Path, cambio: str | None) -> Path:
    """Un repositorio con pyproject.toml en HEAD y, en el índice, el pyproject cambiado con ``cambio`` (texto añadido o
    sustitución «viejo=>nuevo»), más las pruebas de gobierno y las estructurales de capas como ficheros vacíos."""
    raiz = _repo(tmp_path)
    for e in getattr(PC, 'ESTRUCTURALES_DE_CAPAS', ()):  # en el rojo aún no existe: falla la aserción, no un AttributeError
        (raiz / e).write_text('def test_x():\n    pass\n', encoding='utf-8')
    (raiz / 'pyproject.toml').write_text(_PYPROJECT, encoding='utf-8', newline='\n')
    git = ['git', '-c', 'user.name=prueba', '-c', 'user.email=prueba@ejemplo.invalid', '-c', 'commit.gpgsign=false']
    subprocess.run(['git', 'init', '-q'], cwd=raiz, check=True)
    subprocess.run(git + ['add', '-A'], cwd=raiz, check=True)
    subprocess.run(git + ['commit', '-q', '-m', 'base'], cwd=raiz, check=True)
    if cambio is not None:
        texto = _PYPROJECT
        for parte in cambio.split('||'):
            viejo, _, nuevo = parte.partition('=>')
            texto = texto.replace(viejo, nuevo) if nuevo else texto + viejo
        (raiz / 'pyproject.toml').write_text(texto, encoding='utf-8', newline='\n')
        subprocess.run(git + ['add', 'pyproject.toml'], cwd=raiz, check=True)
    return raiz


def test_puerta_capas_solo_capas_no_corre_la_suite_entera(tmp_path):
    """102:RF-1 (PUERTA-CAPAS) — registrar un módulo en [tool.convertersmartgrid.capas.modulos] y nada más en pyproject
    no corre la suite entera: corre las de gobierno y las estructurales de la pre-puerta."""
    raiz = _repo_git_capas(tmp_path, '"x.dos" = "aplicacion"\n')
    elegidas = PC.pruebas_del_commit(['pyproject.toml'], raiz)
    assert elegidas != ['tests'], elegidas
    assert set(PC.GOBIERNO) <= set(elegidas) and set(PC.ESTRUCTURALES_DE_CAPAS) <= set(elegidas), elegidas
    assert 'tests/test_capas.py' in elegidas and 'tests/test_interactive_architecture.py' in elegidas


@pytest.mark.parametrize('cambio', [
    'filterwarnings = ["error"]=>filterwarnings = ["error", "ignore::DeprecationWarning"]',
    'dependencies = ["a>=1"]=>dependencies = ["a>=1", "b>=2"]',
    'dependencies = ["a>=1"]=>dependencies = ["a>=2"]||"x.uno" = "dominio"=>"x.uno" = "aplicacion"',
], ids=['filterwarnings', 'dependencias', 'mixto'])
def test_puerta_capas_otro_cambio_de_pyproject_corre_la_suite_entera(tmp_path, cambio):
    """102:RF-1, 106:RF-13 (PUERTA-CAPAS) — un cambio de pyproject fuera de las capas (los avisos, las dependencias) o
    mixto (capas y otra cosa) sigue corriendo la suite entera."""
    raiz = _repo_git_capas(tmp_path, cambio)
    assert PC.pruebas_del_commit(['pyproject.toml'], raiz) == ['tests']


def test_puerta_capas_con_el_conftest_o_sin_cambio_corre_la_suite_entera(tmp_path):
    """106:RF-13 (PUERTA-CAPAS) — con el conftest en el commit, aunque pyproject solo cambie las capas, la suite entera;
    y un pyproject sin cambios reales en el índice (o ilegible) no se toma por «solo capas»."""
    raiz = _repo_git_capas(tmp_path, '"x.dos" = "aplicacion"\n')
    assert PC.pruebas_del_commit(['tests/conftest.py', 'pyproject.toml'], raiz) == ['tests']
    (tmp_path / 'b').mkdir()
    sin_cambio = _repo_git_capas(tmp_path / 'b', None)
    assert PC.pruebas_del_commit(['pyproject.toml'], sin_cambio) == ['tests']


def test_102_rf24_github_corre_el_lint_del_frontend():
    """102:RF-24 — GitHub Actions pasa también las fronteras del frontend (``npm run lint``), no solo el build y las
    pruebas (H13, auditoría del 2026-11-14: 102:RF-13 solo pedía esos dos)."""
    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert 'npm run lint' in flujo


@pytest.mark.parametrize('ficheros,toca', [(['frontend/src/app/App.tsx'], True), (['frontend/package.json'], True),
                                           (['src/convertersmartgrid/dominio/model.py', 'tests/test_x.py'], False), ([], False)])
def test_102_rf24_el_commit_que_toca_el_frontend_pasa_sus_fronteras(ficheros, toca):
    """102:RF-24 — la puerta del commit ejecuta el lint de fronteras solo si el commit cambia algo de ``frontend/``."""
    assert PC.toca_el_frontend(ficheros) is toca


def test_102_rf24_lint_que_falla_detiene_el_commit(tmp_path, monkeypatch):
    """102:RF-24 — un lint de fronteras en rojo, o sin node, detiene el commit con su motivo; en verde, sigue."""
    (tmp_path / 'frontend' / 'scripts').mkdir(parents=True)
    llamadas = []

    def falso(argumentos, **kw):
        llamadas.append((argumentos, kw.get('cwd')))
        return subprocess.CompletedProcess(argumentos, codigo, stdout='', stderr='frontera rota: features/a → features/b')

    monkeypatch.setattr(PC.subprocess, 'run', falso)
    codigo = 1
    ok, motivo = PC.lint_del_frontend(tmp_path)
    assert not ok and 'frontera rota' in motivo
    assert llamadas[-1][0][-1].endswith('fronteras.mjs') and str(llamadas[-1][1]).endswith('frontend')
    codigo = 0
    assert PC.lint_del_frontend(tmp_path) == (True, '')

    def sin_node(argumentos, **kw):
        raise FileNotFoundError('node')

    monkeypatch.setattr(PC.subprocess, 'run', sin_node)
    ok, motivo = PC.lint_del_frontend(tmp_path)
    assert not ok and 'node' in motivo


def test_102_rf24_sin_dependencias_del_frontend_lo_dice(tmp_path, monkeypatch):
    """102:RF-24 — en un worktree sin ``node_modules`` el lint no se da por bueno y dice que falta ``npm ci``."""
    (tmp_path / 'frontend').mkdir()

    def sin_paquetes(argumentos, **kw):
        return subprocess.CompletedProcess(argumentos, 1, stdout='', stderr="Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'typescript'")

    monkeypatch.setattr(PC.subprocess, 'run', sin_paquetes)
    ok, motivo = PC.lint_del_frontend(tmp_path)
    assert not ok and 'npm ci' in motivo


# Ampliación de CI de H13 (hallazgos H-CI1 a H-CI5 del auditor 3e y del integrador 50, 2026-11-14).
def _flujo_ci() -> dict:
    import yaml

    return yaml.safe_load((RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8'))


def _pasos_que_usan(flujo: dict, accion: str) -> list[tuple[str, dict]]:
    return [(trabajo, paso) for trabajo, cuerpo in flujo['jobs'].items() for paso in cuerpo['steps']
            if str(paso.get('uses', '')).split('@')[0] == accion]


def test_102_rf25_cada_accion_va_fijada_por_su_sha_con_la_etiqueta_al_lado():
    """102:RF-25 — cada ``uses:`` lleva el SHA completo del commit (40 hex) y la etiqueta en un comentario; ninguna
    acción queda en una etiqueta movible como ``@v4``."""
    import re

    texto = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    usos = [linea.strip() for linea in texto.splitlines() if re.match(r'\s*-?\s*uses:', linea)]
    assert usos, 'el flujo no usa ninguna acción'
    fijada = re.compile(r'^-?\s*uses: [\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$')
    sueltas = [u for u in usos if not fijada.match(u)]
    assert not sueltas, f'102:RF-25: acciones sin fijar por SHA con su etiqueta: {sueltas}'
    flujo = _flujo_ci()
    assert len(_pasos_que_usan(flujo, 'actions/checkout')) == 2
    assert len(_pasos_que_usan(flujo, 'actions/setup-python')) == 1
    assert len(_pasos_que_usan(flujo, 'actions/setup-node')) == 2


def test_102_rf26_el_flujo_solo_lee_el_repositorio():
    """102:RF-26 — el flujo declara en lo más alto ``permissions: contents: read`` y ningún trabajo pide más."""
    flujo = _flujo_ci()
    assert flujo.get('permissions') == {'contents': 'read'}
    assert all('permissions' not in cuerpo for cuerpo in flujo['jobs'].values())


def test_102_rf27_los_checkout_no_guardan_credenciales():
    """102:RF-27 — los dos ``actions/checkout`` llevan ``persist-credentials: false``; el del backend conserva
    ``fetch-depth: 0`` (la puerta compara con la historia)."""
    pasos = dict(_pasos_que_usan(_flujo_ci(), 'actions/checkout'))
    assert set(pasos) == {'backend', 'frontend'}
    assert all(paso.get('with', {}).get('persist-credentials') is False for paso in pasos.values())
    assert pasos['backend']['with'].get('fetch-depth') == 0


def test_102_rf28_el_backend_pasa_ruff_con_los_errores_de_sintaxis_y_nombres():
    """102:RF-28 — el trabajo del backend corre ``ruff check --select E9,F63,F7,F82 .`` con el ``.venv`` del flujo,
    después de instalar las dependencias y antes de la suite; ruff viene de ``requirements.txt``."""
    pasos = _flujo_ci()['jobs']['backend']['steps']
    ordenes = [str(paso.get('run', '')) for paso in pasos]
    con_ruff = [i for i, orden in enumerate(ordenes) if 'ruff check --select E9,F63,F7,F82 .' in orden]
    assert len(con_ruff) == 1, ordenes
    assert r'.venv\Scripts\python -m ruff check' in ordenes[con_ruff[0]]
    dependencias = next(i for i, orden in enumerate(ordenes) if 'pip install -r requirements.txt' in orden)
    suite = next(i for i, orden in enumerate(ordenes) if 'puerta_calidad.py --ci' in orden)
    assert dependencias < con_ruff[0] < suite
    assert 'continue-on-error' not in pasos[con_ruff[0]]
    assert any(linea.strip().lower().startswith('ruff')
               for linea in (RAIZ / 'requirements.txt').read_text(encoding='utf-8').splitlines())
    assert 'frontend' not in ordenes[con_ruff[0]]       # solo el backend: el frontend no tiene Python


def test_102_rf29_una_peticion_de_fusion_no_corre_dos_veces():
    """102:RF-29 — la subida a la rama y la petición de fusión de esa rama comparten grupo de concurrencia
    (``head_ref`` en el PR, ``ref_name`` en la subida), y la corrida nueva cancela la que sigue en marcha."""
    flujo = _flujo_ci()
    disparadores = flujo.get('on', flujo.get(True))       # YAML 1.1 lee «on» como True
    assert disparadores['push']['branches'] == ['**']
    assert disparadores['pull_request']['branches'] == ['main']
    concurrencia = flujo['concurrency']
    assert concurrencia['group'] == 'ci-${{ github.head_ref || github.ref_name }}'
    # Aclaración de 102:RF-29 (auditor 3e): en main no se cancela; cada commit de main conserva su corrida entera
    # como evidencia de la etiqueta.
    assert concurrencia['cancel-in-progress'] == "${{ github.ref != 'refs/heads/main' }}"


def _junit_mcp(tmp_path: Path, casos: dict[str, str]) -> Path:
    """Un JUnit con las pruebas del servidor MCP real en el estado de cada una: «bien», «omitida» o «falla»."""
    cuerpo = {'bien': '', 'omitida': '<skipped message="sin CSG_MCP_PYTHON" type="pytest.skip"/>',
              'falla': '<failure message="assert">tb</failure>'}
    filas = ''.join(f'<testcase classname="tests.test_mcp_conversor" name="{n}">{cuerpo[e]}</testcase>'
                    for n, e in casos.items())
    junit = tmp_path / 'junit.xml'
    junit.write_text(f'<testsuites><testsuite>{filas}</testsuite></testsuites>', encoding='utf-8')
    return junit


@pytest.mark.parametrize('casos, sin_correr', [
    ({'test_servidor_real_por_stdio': 'omitida', 'test_servidor_real_y_sus_datos_locales[opciones0-False]': 'bien',
      'test_servidor_real_y_sus_datos_locales[opciones1-True]': 'bien'}, ['test_servidor_real_por_stdio']),
    ({'test_ayuda_sin_el_paquete': 'bien'}, ['test_servidor_real_por_stdio', 'test_servidor_real_y_sus_datos_locales']),
    ({'test_servidor_real_por_stdio': 'bien', 'test_servidor_real_y_sus_datos_locales[opciones0-False]': 'bien',
      'test_servidor_real_y_sus_datos_locales[opciones1-True]': 'falla'}, ['test_servidor_real_y_sus_datos_locales']),
    ({'test_servidor_real_por_stdio': 'bien', 'test_servidor_real_y_sus_datos_locales[opciones0-False]': 'bien',
      'test_servidor_real_y_sus_datos_locales[opciones1-True]': 'bien'}, []),
])
def test_077_rf76_la_puerta_no_aprueba_sin_el_servidor_mcp_real(tmp_path, capsys, casos, sin_correr):
    """077:RF-76 — omitida, sin elegir o fallida, la prueba del servidor MCP real queda «sin correr», y eso detiene la
    puerta aunque no cuenten las omitidas: la suite de main, que precede a la etiqueta, no se da por buena sin ella."""
    juicio = PC.veredicto(_junit_mcp(tmp_path, casos), PC.MCP_REAL)
    assert juicio['exigidas_sin_correr'] == [f'tests.test_mcp_conversor::{n}' for n in sin_correr]
    assert PC._informar(juicio, omitidas_cuentan=False) is not sin_correr
    if sin_correr:
        assert 'la puerta la exige corrida y aprobada' in capsys.readouterr().out
    assert PC.veredicto(_junit_mcp(tmp_path, casos))['exigidas_sin_correr'] == []


def test_077_rf76_la_subida_a_main_exige_el_servidor_mcp_real(tmp_path, monkeypatch):
    """077:RF-76 — la suite completa pide las pruebas del servidor real y, sin ellas, ni aprueba ni queda guardada."""
    raiz = _git_repo(tmp_path)
    cabeza = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=raiz, capture_output=True, text=True).stdout.strip()
    pedidas = []
    monkeypatch.setattr(PC, '_pytest', lambda *a, **k: pedidas.append(k.get('exigidas')) or {
        'total': 5, 'fallidas': [], 'omitidas': [], 'exigidas_sin_correr': [PC.MCP_REAL[0]]})
    monkeypatch.setattr(PC, 'variables_de_la_suite', lambda *_a, **_k: {})
    assert PC.puerta_push([cabeza], raiz) == 1
    assert pedidas == [PC.MCP_REAL] and PC.resultado_guardado(cabeza, raiz) is None


def test_077_rf76_un_commit_del_mcp_corre_su_prueba_real_con_su_interprete(tmp_path):
    """077:RF-76 — un commit que cambia el servidor MCP pasa su intérprete a pytest y exige la prueba real; sin
    intérprete, se detiene y dice cuál poner. Un commit que no lo toca sigue como antes."""
    assert PC.exigencias_mcp(['src/convertersmartgrid/motor_red.py'], tmp_path, {}) == ({}, ())
    for fichero in PC.DEL_MCP:
        with pytest.raises(PC.PuertaError, match='falta su intérprete: ponga CSG_MCP_PYTHON'):
            PC.exigencias_mcp([fichero], tmp_path, {})
    python = tmp_path / 'python_mcp.exe'
    python.write_bytes(b'')
    esperado = ({'CSG_MCP_PYTHON': str(python)}, PC.MCP_REAL)
    assert PC.exigencias_mcp(['tools/mcp_conversor.py'], tmp_path, {'CSG_MCP_PYTHON': str(python)}) == esperado
    with pytest.raises(PC.PuertaError, match='no existe'):
        PC.exigencias_mcp(['tools/mcp_conversor.py'], tmp_path, {'CSG_MCP_PYTHON': str(tmp_path / 'no_hay.exe')})
    (tmp_path / 'config').mkdir()
    (tmp_path / PC.FICHERO_VARIABLES).write_text(
        '{"variables": {"CSG_MCP_PYTHON": "%s"}}' % python.as_posix(), encoding='utf-8')
    assert PC.exigencias_mcp(['requirements-mcp.txt'], tmp_path, {}) == ({'CSG_MCP_PYTHON': python.as_posix()}, PC.MCP_REAL)
    (tmp_path / PC.FICHERO_VARIABLES).unlink()
    propio = tmp_path / '.venv_mcp' / 'Scripts' / 'python.exe'
    propio.parent.mkdir(parents=True)
    propio.write_bytes(b'')
    assert PC.exigencias_mcp(['tests/test_mcp_conversor.py'], tmp_path, {}) == ({'CSG_MCP_PYTHON': str(propio)}, PC.MCP_REAL)



# ----------------------------------------------------------------- PUERTA-ESPECULATIVA (102:RF-11, aclaración del 15-11)

_RUN_REAL = subprocess.run
_CASOS_VERDES = ''.join(f'<testcase classname="tests.test_a" name="test_{i}" time="0.1"/>' for i in range(3))
#: La subida exige además las pruebas reales del MCP (077:RF-76, H10H13): una suite real las trae aprobadas.
_CASOS_SUBIDA = _CASOS_VERDES + ''.join(
    f'<testcase classname="{c}" name="{n}" time="0.1"/>' for c, n in (x.split('::') for x in PC.MCP_REAL))


def _pytest_falso(monkeypatch, corridas: list, casos: str = _CASOS_VERDES, durante=None):
    """Sustituye SOLO el pytest que lanza la puerta: deja un junit con ``casos`` y sale con 0; git sigue siendo real."""
    def correr(cmd, *args, **kwargs):
        if len(cmd) > 2 and list(cmd[1:3]) == ['-m', 'pytest']:
            corridas.append(list(cmd))
            junit = next(a.split('=', 1)[1] for a in cmd if a.startswith('--junitxml='))
            Path(junit).write_text(f'<testsuites><testsuite>{casos}</testsuite></testsuites>', encoding='utf-8')
            if durante is not None:
                durante()
            return subprocess.CompletedProcess(cmd, 0)
        return _RUN_REAL(cmd, *args, **kwargs)

    monkeypatch.setattr(PC.subprocess, 'run', correr)


def _git_t(raiz: Path, *args: str) -> str:
    return _RUN_REAL(['git', *args], cwd=raiz, capture_output=True, text=True, check=True).stdout.strip()


def _arbol_para_la_puerta(tmp_path: Path, monkeypatch) -> Path:
    """Un repositorio con las pruebas de gobierno, el lock de dependencias y un cambio del conftest preparado (la puerta
    del commit corre entonces la suite entera, 106:RF-13), con las variables de datos reales en el entorno, como las
    exportan los guiones del integrador."""
    raiz = tmp_path / 'repo'
    raiz.mkdir()
    _git_repo(raiz)
    (raiz / 'tests').mkdir()
    for g in PC.GOBIERNO:
        (raiz / g).write_text('def test_x():\n    pass\n', encoding='utf-8')
    (raiz / 'tests' / 'conftest.py').write_text('\n', encoding='utf-8')
    (raiz / 'requirements-nucleo.lock').write_text('paquete==1.0\n', encoding='utf-8')
    _git_t(raiz, 'add', '-A')
    _git_t(raiz, 'commit', '-q', '-m', 'base')
    # 102:RF-11 v2: el veredicto de árbol solo se reutiliza en la rama de trabajo.
    _git_t(raiz, 'branch', '-M', 'trabajo/puerta-por-ramas')
    (raiz / 'tests' / 'conftest.py').write_text('# cambio común a toda la suite\n', encoding='utf-8')
    _git_t(raiz, 'add', 'tests/conftest.py')
    datos = tmp_path / 'datos'
    datos.mkdir()
    variables = {k: str(datos) for k in PC.VARIABLES}
    for k, v in variables.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(PC, 'variables_de_la_suite', lambda *_a, **_k: dict(variables))
    # PUERTA-XDIST (la tarjeta siguiente): aquí, una sola sesión de pytest, la de hoy.
    monkeypatch.setattr(PC, 'procesos_de_la_suite', lambda *_a, **_k: (1, 'una sola sesión (prueba)'), raising=False)
    return raiz


#: Lo que traen PUERTA-ESPECULATIVA y PUERTA-XDIST. Sus pruebas lo exigen primero: sin ello caen por aserción, no por
#: AttributeError (rojo VALIDO, lección B1 del 2026-11-16).
LO_NUEVO_DE_LA_PUERTA = ('veredicto_de_arbol', 'puerta_arbol', 'arbol_del_indice', 'ruta_veredicto_de_arbol',
                         'indice_igual_al_disco', 'procesos_de_la_suite', 'PROCESOS_MAXIMOS', 'VARIABLE_PROCESOS',
                         'GIB_POR_PROCESO', 'RESERVA_GIB', 'SELECCION_A_SOLAS', 'RAMAS_CON_VEREDICTO_DE_ARBOL',
                         'HORAS_VEREDICTO_ARBOL')


def _exige_lo_nuevo() -> None:
    faltan = [n for n in LO_NUEVO_DE_LA_PUERTA if not hasattr(PC, n)]
    assert not faltan, f'falta en tools/puerta_calidad.py: {faltan}'


def test_102_rf11_un_commit_con_el_arbol_ya_aprobado_no_repite_la_suite(tmp_path, monkeypatch, capsys):
    """102:RF-11 (aclaración, PUERTA-ESPECULATIVA) — la suite entera ya pasada fuera de wt_integra sobre el MISMO árbol
    (write-tree), con las mismas variables y la misma puerta, sin fallidas ni omitidas, deja su veredicto; el gancho del
    commit con ese índice no la repite, lo cita y da la línea de siempre. Hasta el 15-11 la repetía: ~80 min por puerta."""
    _exige_lo_nuevo()
    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    corridas: list = []
    _pytest_falso(monkeypatch, corridas)
    getattr(PC, 'puerta_arbol', lambda _raiz: None)(raiz)
    antes = len(corridas)
    capsys.readouterr()
    assert PC.puerta_commit(raiz) == 0
    salida = capsys.readouterr().out
    assert len(corridas) == antes, f'el gancho repitió la suite sobre el mismo árbol ({len(corridas) - antes} corrida)'
    arbol = _git_t(raiz, 'write-tree')
    assert f'arbol_{arbol}.json' in salida and 'no se repite' in salida, salida
    assert re.search(r'^Puerta de calidad: 3 pruebas, 0 fallidas, 0 omitidas\.$', salida, re.M), salida


@pytest.mark.parametrize('rama', ['main', 'otra/rama', 'sin_rama'], ids=['main', 'otra_rama', 'sin_rama'])
def test_102_rf11_fuera_de_la_rama_de_trabajo_el_gancho_no_reutiliza_el_veredicto(tmp_path, monkeypatch, capsys, rama):
    """102:RF-11 v2 (PUERTA-ESPECULATIVA, condición de 0d) — «main exige la completa»: el veredicto de árbol vale solo en
    la rama de trabajo (y en la del integrador que se funde en ella); en main, en otra rama o sin rama, el gancho corre
    la suite aunque el veredicto sea válido. Hasta la v2 lo reutilizaba en cualquier rama."""
    _exige_lo_nuevo()
    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    corridas: list = []
    _pytest_falso(monkeypatch, corridas)
    getattr(PC, 'puerta_arbol', lambda _raiz: None)(raiz)
    antes = len(corridas)
    if rama == 'sin_rama':
        _git_t(raiz, 'update-ref', '--no-deref', 'HEAD', _git_t(raiz, 'rev-parse', 'HEAD'))   # HEAD separado, sin checkout
    else:
        _git_t(raiz, 'branch', '-M', rama)
    capsys.readouterr()
    assert PC.puerta_commit(raiz) == 0
    assert len(corridas) == antes + 1, f'en «{rama}» el gancho reutilizó el veredicto del árbol y no corrió la suite'
    assert corridas[-1][-1] == 'tests', corridas[-1]


def test_102_rf11_el_pre_push_a_main_corre_siempre_la_suite_fresca(tmp_path, monkeypatch, capsys):
    """102:RF-5, 102:RF-11 v2 (PUERTA-ESPECULATIVA) — con un veredicto de árbol válido del mismo árbol que HEAD, la subida
    a main corre la suite entera de nuevo: allí nunca se reutiliza un veredicto de árbol."""
    _exige_lo_nuevo()
    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    corridas: list = []
    _pytest_falso(monkeypatch, corridas, _CASOS_SUBIDA)
    _git_t(raiz, 'commit', '-q', '-m', 'el conftest')
    assert PC.puerta_arbol(raiz) == 0 and len(corridas) == 1
    cabeza = _git_t(raiz, 'rev-parse', 'HEAD')
    assert PC.veredicto_de_arbol(_git_t(raiz, 'rev-parse', 'HEAD^{tree}'), raiz, dict(PC.os.environ))[0]
    linea = f'refs/heads/main {cabeza} refs/heads/main {"0" * 40}'
    assert PC.revisiones_por_destino([linea]) == ([cabeza], [])
    assert PC.puerta_push([cabeza], raiz) == 0
    assert len(corridas) == 2, 'el pre-push a main no corrió la suite fresca'
    assert 'main exige la suite completa' in capsys.readouterr().out


def _alterar(raiz: Path, campo: str, monkeypatch) -> None:
    """Cambia UNA cosa del veredicto o de lo que el gancho compara con él."""
    import json
    from datetime import datetime, timedelta

    carpeta = PC._carpeta_resultados(raiz)
    ruta = carpeta / f"arbol_{_git_t(raiz, 'write-tree')}.json"
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if campo == 'arbol':
        (raiz / 'tests' / 'conftest.py').write_text('# otro cambio\n', encoding='utf-8')
        _git_t(raiz, 'add', 'tests/conftest.py')
        return
    if campo == 'variables':
        otra = raiz.parent / 'otros_datos'
        otra.mkdir()
        monkeypatch.setenv('CSG_RED', str(otra))
        return
    if campo == 'junit':
        junit = carpeta / datos['junits'][0]['fichero']
        junit.write_text(junit.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        return
    ahora = datetime.now().astimezone()
    cambios = {
        'formato': lambda d: d.update(formato=99),
        'puerta': lambda d: d.update(puerta='0' * 64),
        'lock': lambda d: d['entorno'].update(lock='0' * 64),
        'python': lambda d: d['entorno'].update(python='CPython 3.0.0'),
        'paquetes': lambda d: d['entorno'].update(paquetes='0' * 64),
        'sha_del_junit': lambda d: d['junits'][0].update(sha256='0' * 64),
        'fallidas': lambda d: d.update(fallidas=[{'prueba': 't::x', 'motivo': 'assert'}]),
        'omitidas': lambda d: d.update(omitidas=[{'prueba': 't::y', 'motivo': 'sin datos'}]),
        'aprobada': lambda d: d.update(aprobada=False),
        'total': lambda d: d.update(total=d['total'] + 1),
        'viejo': lambda d: d.update(fecha=(ahora - timedelta(hours=PC.HORAS_VEREDICTO_ARBOL + 1)).isoformat()),
        'futuro': lambda d: d.update(fecha=(ahora + timedelta(hours=1)).isoformat()),
        'sin_fecha': lambda d: d.pop('fecha'),
    }
    cambios[campo](datos)
    ruta.write_text(json.dumps(datos), encoding='utf-8')


@pytest.mark.parametrize('campo', ['arbol', 'formato', 'puerta', 'variables', 'lock', 'python', 'paquetes', 'junit',
                                   'sha_del_junit', 'fallidas', 'omitidas', 'aprobada', 'total', 'viejo', 'futuro',
                                   'sin_fecha'])
def test_102_rf11_ante_cualquier_duda_el_gancho_corre_la_suite_entera(tmp_path, monkeypatch, capsys, campo):
    """102:RF-11 (aclaración, PUERTA-ESPECULATIVA) — otro árbol, otra versión de la puerta, otras variables, otro lock,
    otro Python u otros paquetes, un junit que no cuadra con su sha, un veredicto con F u omitidas, o viejo, o del futuro:
    cada campo alterado, uno por uno, fuerza la suite entera."""
    _exige_lo_nuevo()
    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    corridas: list = []
    _pytest_falso(monkeypatch, corridas)
    assert PC.puerta_arbol(raiz) == 0 and len(corridas) == 1
    datos, motivo = PC.veredicto_de_arbol(_git_t(raiz, 'write-tree'), raiz, dict(PC.os.environ))
    assert datos and not motivo, motivo
    _alterar(raiz, campo, monkeypatch)
    capsys.readouterr()
    assert PC.puerta_commit(raiz) == 0
    assert len(corridas) == 2, f'«{campo}» alterado y el gancho no corrió la suite'
    assert corridas[-1][-1] == 'tests', corridas[-1]


@pytest.mark.parametrize('casos', [
    '<testcase classname="t" name="a"/><testcase classname="t" name="b"><failure message="assert 1 == 2"/></testcase>',
    '<testcase classname="t" name="a"/><testcase classname="t" name="b"><skipped message="sin SQL Server"/></testcase>',
], ids=['con_F', 'con_omitidas'])
def test_102_rf11_una_suite_con_fallidas_u_omitidas_no_aprueba_el_arbol(tmp_path, monkeypatch, casos):
    """102:RF-9, 102:RF-11 (PUERTA-ESPECULATIVA) — el veredicto de una suite con F u omitidas queda guardado, pero no
    aprueba el árbol: el gancho corre la suite."""
    _exige_lo_nuevo()
    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    corridas: list = []
    _pytest_falso(monkeypatch, corridas, casos=casos)
    assert PC.puerta_arbol(raiz) == 1
    datos, motivo = PC.veredicto_de_arbol(_git_t(raiz, 'write-tree'), raiz, dict(PC.os.environ))
    assert datos is None and motivo, motivo
    _pytest_falso(monkeypatch, corridas)
    assert PC.puerta_commit(raiz) == 0 and len(corridas) == 2


def test_102_rf11_el_veredicto_del_arbol_se_publica_con_la_escritura_atomica(tmp_path, monkeypatch):
    """001:RF-5, 102:RF-11 (PUERTA-ESPECULATIVA) — el json del veredicto va por la escritura atómica única del proyecto
    (un corte no deja un veredicto truncado), y se publica después de su junit."""
    _exige_lo_nuevo()
    from convertersmartgrid.dominio import util

    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    _pytest_falso(monkeypatch, [])
    publicados = []
    real = util.write_json_atomic
    monkeypatch.setattr(util, 'write_json_atomic',
                        lambda ruta, datos, **k: publicados.append((Path(ruta), datos)) or real(ruta, datos, **k))
    assert PC.puerta_arbol(raiz) == 0
    arbol = _git_t(raiz, 'write-tree')
    assert [r.name for r, _ in publicados] == [f'arbol_{arbol}.json']
    datos = publicados[0][1]
    junit = PC._carpeta_resultados(raiz) / datos['junits'][0]['fichero']
    assert junit.is_file() and datos['arbol'] == arbol and datos['aprobada'] is True
    assert {'puerta', 'variables', 'entorno', 'fecha', 'total'} <= set(datos)
    assert {'python', 'lock', 'paquetes'} <= set(datos['entorno'])
    assert set(PC.VARIABLES) <= set(datos['variables'])


def test_102_rf11_el_arbol_solo_se_juzga_con_el_disco_igual_al_indice(tmp_path, monkeypatch):
    """102:RF-11 (PUERTA-ESPECULATIVA) — un cambio sin preparar o un fichero nuevo de código haría probar otra cosa que el
    árbol T: no se corre ni se deja veredicto; y si el árbol cambia durante la suite, tampoco se aprueba."""
    _exige_lo_nuevo()
    import json

    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    corridas: list = []
    _pytest_falso(monkeypatch, corridas)
    (raiz / 'tests' / 'conftest.py').write_text('# sin preparar\n', encoding='utf-8')
    assert PC.puerta_arbol(raiz) == 1 and corridas == []
    _git_t(raiz, 'add', 'tests/conftest.py')
    (raiz / 'tests' / 'test_nuevo.py').write_text('def test_n():\n    pass\n', encoding='utf-8')
    assert PC.puerta_arbol(raiz) == 1 and corridas == []
    (raiz / 'tests' / 'test_nuevo.py').unlink()

    def cambia_el_arbol():
        (raiz / PC.GOBIERNO[0]).write_text('def test_y():\n    pass\n', encoding='utf-8')
        _git_t(raiz, 'add', PC.GOBIERNO[0])

    _pytest_falso(monkeypatch, corridas, durante=cambia_el_arbol)
    arbol = _git_t(raiz, 'write-tree')
    assert PC.puerta_arbol(raiz) == 1 and len(corridas) == 1
    ruta = PC._carpeta_resultados(raiz) / f'arbol_{arbol}.json'
    assert not ruta.exists() or json.loads(ruta.read_text(encoding='utf-8')).get('aprobada') is not True



# ----------------------------------------------------------------- PUERTA-XDIST (102:RF-5, aclaración del 15-11)

_POPEN_REAL = subprocess.Popen


def _sesiones_falsas(monkeypatch, lanzadas: list, rc_de=None):
    """Sustituye SOLO el pytest de la puerta, por ``subprocess.run`` y por ``subprocess.Popen``: cada sesión deja su junit
    con dos casos propios y sale con 0, o con lo que diga ``rc_de(cmd) -> (rc, casos)``; git sigue siendo real."""
    def lanzar(cmd) -> int:
        rc, n = rc_de(cmd) if rc_de else (0, 2)
        junit = next(a.split('=', 1)[1] for a in cmd if a.startswith('--junitxml='))
        indice = len(lanzadas)
        Path(junit).write_text('<testsuites><testsuite>' + ''.join(
            f'<testcase classname="tests.test_s{indice}" name="t{i}"/>' for i in range(n)) + '</testsuite></testsuites>',
            encoding='utf-8')
        lanzadas.append(list(cmd))
        return rc

    def correr(cmd, *args, **kwargs):
        if len(cmd) > 2 and list(cmd[1:3]) == ['-m', 'pytest']:
            return subprocess.CompletedProcess(cmd, lanzar(cmd))
        return _RUN_REAL(cmd, *args, **kwargs)

    class Proceso:
        def __init__(self, rc):
            self.returncode = rc

        def wait(self, timeout=None):
            return self.returncode

        def poll(self):
            return self.returncode

    def abrir(cmd, *args, **kwargs):
        # subprocess.run de git usa Popen por dentro: solo el pytest de la puerta es falso.
        if len(cmd) > 2 and list(cmd[1:3]) == ['-m', 'pytest']:
            return Proceso(lanzar(cmd))
        return _POPEN_REAL(cmd, *args, **kwargs)

    monkeypatch.setattr(PC.subprocess, 'run', correr)
    monkeypatch.setattr(PC.subprocess, 'Popen', abrir)


def _memoria(monkeypatch, gib: float, *, xdist: bool = True, cpus: int = 8) -> None:
    """La memoria libre que mide la puerta al arrancar (psutil), simulada; y si pytest-xdist está instalado."""
    import types

    import psutil

    monkeypatch.setattr(psutil, 'virtual_memory', lambda: types.SimpleNamespace(available=int(gib * 2**30),
                                                                                total=64 * 2**30))
    monkeypatch.setattr(PC, '_hay_xdist', lambda: xdist, raising=False)
    monkeypatch.setattr(PC.os, 'cpu_count', lambda: cpus)
    for variable in ('CSG_PUERTA_PROCESOS', 'CSG_PUERTA_GIB_POR_PROCESO'):
        monkeypatch.delenv(variable, raising=False)


def _con(cmd: list, opcion: str) -> str | None:
    """El valor de una opción de la orden, después de «python -m pytest»."""
    resto = cmd[3:]
    return resto[resto.index(opcion) + 1] if opcion in resto else None


def test_102_rf5_la_suite_entera_se_reparte_con_memoria_y_no_con_poca(tmp_path, monkeypatch, capsys):
    """102:RF-5 (aclaración, PUERTA-XDIST) — con memoria para varios procesos y pytest-xdist, la suite entera de la puerta
    se reparte: lo que no admite paralelo en una sesión «serie», el resto a la vez con -n y --dist loadfile, y lo que mide
    tiempos o el árbol entero a solas al final; el juicio suma los junit. Con poca memoria, una sola sesión: la de hoy."""
    _exige_lo_nuevo()
    lanzadas: list = []
    _sesiones_falsas(monkeypatch, lanzadas)
    _memoria(monkeypatch, 64.0)
    monkeypatch.setenv(PC.VARIABLE_PROCESOS, '3')   # FIX-XDIST-UNO: el reparto se pide hasta que la T20 mida
    assert PC.puerta_ci(tmp_path) == 0
    con_n = [c for c in lanzadas if '-n' in c]
    assert len(con_n) == 1, f'con 64 GiB libres y xdist la suite no se repartió: {lanzadas}'
    reparto = con_n[0]
    assert _con(reparto, '--dist') == 'loadfile' and int(_con(reparto, '-n') or 0) >= 2, reparto
    selecciones = sorted(_con(c, '-m') or '' for c in lanzadas)
    assert selecciones == sorted([PC.SELECCION_SERIE, PC.SELECCION_REPARTO, PC.SELECCION_A_SOLAS]), selecciones
    assert len({_con(c, '-p') for c in lanzadas}) == 1 and all('-rs' in c for c in lanzadas)
    assert len({a for c in lanzadas for a in c if a.startswith('--junitxml=')}) == 3, 'cada sesión con su junit'
    salida = capsys.readouterr().out
    assert re.search(r'^Puerta de calidad: 6 pruebas, 0 fallidas, 0 omitidas\.$', salida, re.MULTILINE), salida

    lanzadas.clear()
    _memoria(monkeypatch, 3.0)
    assert PC.puerta_ci(tmp_path) == 0
    assert len(lanzadas) == 1, lanzadas
    junit = next(a for a in lanzadas[0] if a.startswith('--junitxml='))
    assert lanzadas[0] == [PC.sys.executable, '-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', junit], (
        'con poca memoria, la orden de hoy, sin -n ni -m')


@pytest.mark.parametrize('sobra, xdist, cpus, tope, esperado', [
    (5, True, 8, '3', 3), (2, True, 8, '3', 2), (1, True, 8, '3', 1), (0, True, 8, '3', 1), (-1, True, 8, '3', 1),
    (5, False, 8, '3', 1), (5, True, 2, '3', 2), (5, True, 8, '2', 2), (5, True, 8, '1', 1),
], ids=['mucha', 'dos', 'uno', 'justa', 'menos_que_la_reserva', 'sin_xdist', 'dos_cpu', 'tope_2', 'tope_1'])
def test_102_rf5_la_memoria_libre_decide_cuantos_procesos(monkeypatch, sobra, xdist, cpus, tope, esperado):
    """102:RF-5 (PUERTA-XDIST) — N sale de la memoria libre al arrancar, menos la reserva, entre la memoria de un proceso,
    con el tope de procesos y de CPU; sin pytest-xdist, N=1 y lo dice."""
    _exige_lo_nuevo()
    libre = PC.RESERVA_GIB + sobra * PC.GIB_POR_PROCESO + 0.1
    _memoria(monkeypatch, libre, xdist=xdist, cpus=cpus)
    if tope:
        monkeypatch.setenv(PC.VARIABLE_PROCESOS, tope)
    n, motivo = PC.procesos_de_la_suite()
    assert n == esperado, (n, motivo)
    if not xdist:
        assert 'pytest-xdist' in motivo and 'N=1' in motivo, motivo
    else:
        assert f'N={n}' in motivo and 'GiB' in motivo, motivo


def test_102_rf5_sin_la_variable_la_suite_va_en_una_sola_sesion(monkeypatch):
    """102:RF-5 (FIX-XDIST-UNO) — hasta que la T20 mida, sin CSG_PUERTA_PROCESOS la puerta usa UN proceso aunque sobren
    memoria, CPU y xdist; con la variable, se puede ensayar el reparto."""
    _exige_lo_nuevo()
    _memoria(monkeypatch, PC.RESERVA_GIB + 5 * PC.GIB_POR_PROCESO + 0.1, xdist=True, cpus=8)
    monkeypatch.delenv(PC.VARIABLE_PROCESOS, raising=False)
    assert PC.PROCESOS_MAXIMOS == 1
    n, motivo = PC.procesos_de_la_suite()
    assert n == 1 and 'N=1' in motivo, motivo
    monkeypatch.setenv(PC.VARIABLE_PROCESOS, '3')
    assert PC.procesos_de_la_suite()[0] == 3


def test_102_rf5_lo_que_no_admite_paralelo_va_en_serie():
    """102:RF-5 (PUERTA-XDIST) — la tabla del conftest: cada fichero existe y dice su recurso y su motivo; la marca
    ``serie`` (y ``a_solas``) se pone sola; la GPU va en serie por su marca ``gpu`` (106:RF-6); y todo fichero que
    restaura la copia real de VNR-GIS en SQL Server está en la tabla."""
    _exige_lo_nuevo()
    import conftest

    assert conftest.EN_SERIE
    for fichero, (recurso, motivo) in conftest.EN_SERIE.items():
        assert (RAIZ / 'tests' / fichero).is_file(), fichero
        assert recurso in conftest.RECURSOS_EN_SERIE and len(motivo) > 20, (fichero, recurso, motivo)

    class Item:
        def __init__(self, nombre):
            self.path, self.marcas = RAIZ / 'tests' / nombre, []

        def add_marker(self, marca):
            self.marcas.append(marca.name)

    items = [Item('test_vnr_sqlserver.py'), Item('test_flexibility_and_scale.py'), Item('test_util.py')]
    conftest.marcar_en_serie(items)
    assert [i.marcas for i in items] == [['serie'], ['serie', 'a_solas'], []]
    assert 'gpu or serie' in PC.SELECCION_SERIE and 'not gpu' in PC.SELECCION_REPARTO
    senal = 'cargar_' + 'copia('
    for prueba in sorted((RAIZ / 'tests').glob('test_*.py')):
        texto = prueba.read_text(encoding='utf-8', errors='replace')
        if senal in texto and 'CSG_VNR_BAK' in texto:
            assert conftest.EN_SERIE.get(prueba.name, ('',))[0] == 'sqlserver', prueba.name


def test_102_rf5_cada_sesion_repartida_se_juzga_por_su_cuenta(tmp_path, monkeypatch, capsys):
    """102:RF-5, 106:RF-8, 106:RF-16 (PUERTA-XDIST) — sin el turno de GPU la serie no da veredicto y es un fallo con su
    dueño; una sesión sin pruebas que elegir (código 5, junit vacío) no es un fallo; otro código sin fallidas, sí."""
    _exige_lo_nuevo()
    from convertersmartgrid.aplicacion.trabajadores_ml import SALIDA_SIN_TURNO_GPU

    _memoria(monkeypatch, 64.0)
    monkeypatch.setenv(PC.VARIABLE_PROCESOS, '3')   # FIX-XDIST-UNO: el reparto se pide hasta que la T20 mida

    def rc_de(cmd):
        return {PC.SELECCION_A_SOLAS: (5, 0), PC.SELECCION_REPARTO: (0, 2)}.get(_con(cmd, '-m'), (0, 2))

    lanzadas: list = []
    _sesiones_falsas(monkeypatch, lanzadas, rc_de)
    assert PC.puerta_ci(tmp_path) == 0 and len(lanzadas) == 3
    assert 'Puerta de calidad: 4 pruebas, 0 fallidas, 0 omitidas.' in capsys.readouterr().out

    lanzadas.clear()
    _sesiones_falsas(monkeypatch, lanzadas, lambda c: (1, 2) if _con(c, '-m') == PC.SELECCION_REPARTO else (0, 2))
    juicio = PC._pytest([], {}, tmp_path, procesos=3)
    assert [f['prueba'] for f in juicio['fallidas']] == ['pytest'] and 'reparto' in juicio['fallidas'][0]['motivo']

    lanzadas.clear()
    _sesiones_falsas(monkeypatch, lanzadas,
                     lambda c: (SALIDA_SIN_TURNO_GPU, 0) if _con(c, '-m') == PC.SELECCION_SERIE else (0, 2))
    juicio = PC._pytest([], {}, tmp_path, procesos=3)
    assert juicio['fallidas'] and 'sin el turno de GPU' in juicio['fallidas'][0]['motivo'], juicio


def test_102_rf5_rf11_una_suite_repartida_deja_un_veredicto_que_el_gancho_reutiliza(tmp_path, monkeypatch):
    """102:RF-5, 102:RF-11 (PUERTA-XDIST sobre PUERTA-ESPECULATIVA) — repartida, el veredicto del árbol lleva un junit
    por sesión, cada uno con su sha256, y el gancho del commit con ese árbol no repite la suite."""
    _exige_lo_nuevo()
    raiz = _arbol_para_la_puerta(tmp_path, monkeypatch)
    monkeypatch.setattr(PC, 'procesos_de_la_suite', lambda *_a, **_k: (3, 'tres procesos (prueba)'))
    lanzadas: list = []
    _sesiones_falsas(monkeypatch, lanzadas)
    assert PC.puerta_arbol(raiz) == 0 and len(lanzadas) == 3
    arbol = _git_t(raiz, 'write-tree')
    datos, motivo = PC.veredicto_de_arbol(arbol, raiz, dict(PC.os.environ))
    assert datos and not motivo, motivo
    assert [j['fichero'] for j in datos['junits']] == [f'arbol_{arbol}.{f}.junit.xml'
                                                       for f in ('serie', 'reparto', 'a_solas')]
    assert datos['total'] == 6
    assert PC.puerta_commit(raiz) == 0 and len(lanzadas) == 3


#: 102:RF-30: lo que tardó la suite sintética en el runner en sus últimas corridas completas (17-11: de 76 a 80 min).
DURACION_MEDIDA_MIN = 80


def test_102_rf30_la_suite_sintetica_tiene_margen_sobre_lo_que_tarda():
    """102:RF-30 — el tope del trabajo de la suite sintética es al menos 1,5 veces su duración medida: con 90 min, la
    corrida de main se cortó sin ningún fallo."""
    import re

    flujo = (RAIZ / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert 'name: Suite sintética' in flujo
    tope = re.search(r'timeout-minutes:\s*(\d+)', flujo.split('name: Suite sintética', 1)[1])
    assert tope, 'el trabajo de la suite sintética no tiene timeout-minutes'
    assert int(tope.group(1)) >= 1.5 * DURACION_MEDIDA_MIN, (tope.group(1), DURACION_MEDIDA_MIN)
