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


def test_lo_comun_a_todas_las_pruebas_corre_la_suite_entera(tmp_path, monkeypatch):
    """106:RF-13 — un cambio en el conftest o en pyproject.toml corre todas las pruebas; un ayudante, las que lo nombran."""
    from apoyo import cargar_herramienta

    puerta = cargar_herramienta('puerta_calidad.py', 'puerta_comun', tools_en_path=True)
    raiz = Path(__file__).resolve().parents[1]
    # PUERTA-CAPAS: el caso «solo capas» se prueba aparte, en un repositorio propio; aquí no depende del índice vivo
    # (en la puerta, un commit solo de capas está en el índice).
    monkeypatch.setattr(puerta, 'pyproject_cambia_solo_capas', lambda raiz=None: False, raising=False)
    assert puerta.pruebas_del_commit(['tests/conftest.py'], raiz) == ['tests']
    assert puerta.pruebas_del_commit(['pyproject.toml', 'src/convertersmartgrid/naming.py'], raiz) == ['tests']
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
                                           (['src/convertersmartgrid/model.py', 'tests/test_x.py'], False), ([], False)])
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
