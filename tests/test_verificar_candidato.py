"""065:RF-1/20/21/24 — regresión reproducible con subprocess y evidencia conservada."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from apoyo import cargar_herramienta


def runner():
    return cargar_herramienta('verificar_candidato.py', tools_en_path=True)


@pytest.mark.parametrize('variable',[
    'CSG_WEB_DATA','CSG_ASISTENTE_DATA','CSG_TWIN_DATA','CSG_WEB_SESIONES','CSG_DATOS_HOME',
    'CSG_PERFIL_EMPRESA','NUMBA_CACHE_DIR','MPLCONFIGDIR','CUDA_CACHE_PATH','TORCH_EXTENSIONS_DIR',
])
def test_entorno_no_hereda_destinos_de_datos_o_cache_del_operador(tmp_path,monkeypatch,variable):
    """065:RF-1/24 — el verificador aísla destinos aunque herede un espacio activo del operador."""
    original=tmp_path/'datos_operador';original.mkdir()
    (original/'custodia.txt').write_text('conservar',encoding='utf-8')
    monkeypatch.setenv(variable,str(original))
    ev=tmp_path/'evidencia'
    fuente=tmp_path/'red_original.txt';fuente.write_text('fuente',encoding='utf-8')
    env=runner()._entorno(ev,{'CSG_RED':fuente})
    destino=Path(env[variable]).resolve()
    assert destino.is_relative_to(ev.resolve())
    assert env['CSG_RED']==str(fuente)
    assert (original/'custodia.txt').read_text(encoding='utf-8')=='conservar'
    assert len(list(original.iterdir()))==1
    if variable=='CSG_PERFIL_EMPRESA':
        assert destino.parent.is_dir() and not destino.exists()
    else:
        assert destino.is_dir()


@pytest.fixture
def candidato_minimo(tmp_path):
    raiz = tmp_path / 'candidato'
    carpeta = raiz / 'specs' / '065-ejemplo'
    carpeta.mkdir(parents=True)
    (carpeta / 'spec.md').write_text('# Ejemplo\nEstado: aprobada\n- RF-1: EL SISTEMA registra.\n', encoding='utf-8')
    (carpeta / 'tasks.md').write_text('- [ ] T1 [DIgSILENT] Reapertura. (RF-1)\n  Hecho cuando: lectura nativa.\n', encoding='utf-8')
    (raiz / 'src').mkdir()
    (raiz / 'src' / 'motor.py').write_text('VALOR = 42\n', encoding='utf-8')
    (raiz / 'tests').mkdir()
    (raiz / 'tests' / 'test_motor.py').write_text('def test_real():\n    """065:RF-1 — contrato mínimo."""\n    assert 6 * 7 == 42\n', encoding='utf-8')
    (raiz / 'CODIGO_FUENTE.md').write_text('| `src/motor.py` | Motor. | 065 (RF-1) |\n', encoding='utf-8')
    return raiz


def test_help_no_carga_motores_ni_crea_salida(tmp_path):
    """065:RF-24 — consultar ayuda no requiere backend, pytest ni conectores."""
    herramienta = Path(__file__).resolve().parents[1] / 'tools' / 'verificar_candidato.py'
    resultado = subprocess.run([sys.executable, '-I', '-S', '-B', str(herramienta), '--help'],
                               cwd=tmp_path, capture_output=True)
    assert resultado.returncode == 0, resultado.stderr
    assert b'--suite-completa' in resultado.stdout
    assert not list(tmp_path.iterdir())


def test_subproceso_no_escribe_en_almacen_heredado(tmp_path,monkeypatch,candidato_minimo):
    """065:RF-1/24 — la herencia se corta también al ejecutar pytest de verdad, conservando la fuente."""
    host=tmp_path/'almacen_activo';host.mkdir()
    (host/'conservar.json').write_text('original',encoding='utf-8')
    monkeypatch.setenv('CSG_ASISTENTE_DATA',str(host))
    fuente=tmp_path/'fuente.txt';fuente.write_text('fuente original',encoding='utf-8')
    codigo=('import os\nfrom pathlib import Path\n'
        'def test_destino():\n'
        '    """065:RF-1 — escritura de prueba aislada."""\n'
        '    assert Path(os.environ["CSG_RED"]).read_text(encoding="utf-8")=="fuente original"\n'
        '    (Path(os.environ["CSG_ASISTENTE_DATA"])/"nuevo.json").write_text("solo evidencia",encoding="utf-8")\n')
    (candidato_minimo/'tests/test_motor.py').write_text(codigo,encoding='utf-8')
    ev=tmp_path/'evidencia'
    assert runner().main(['--root',str(candidato_minimo),'--output-dir',str(ev),
        '--red',str(fuente),'--ejecutar'])==0
    run,=ev.iterdir()
    assert (run/'runtime/data/asistente/nuevo.json').read_text(encoding='utf-8')=='solo evidencia'
    assert [p.name for p in host.iterdir()]==['conservar.json']
    assert (host/'conservar.json').read_text(encoding='utf-8')=='original'
    assert fuente.read_text(encoding='utf-8')=='fuente original'


@pytest.mark.parametrize('manual', [False, True])
def test_caches_del_verificador_son_reconfigurables_sin_mover_sus_datos(tmp_path, monkeypatch, manual):
    """065:RF-10, 065:RF-24 — caché automática reubicable; override manual y datos aislados se conservan."""
    from convertersmartgrid.runtime_paths import configurar_entorno
    root = tmp_path / 'checkout'
    root.mkdir()
    env = runner()._entorno(tmp_path / 'ejecucion', {})
    for name, value in env.items():
        if name.startswith('CSG_') or name in ('HF_HOME','TORCH_HOME','RUFF_CACHE_DIR','npm_config_cache',
                'HF_HUB_CACHE','PYTHONPYCACHEPREFIX','TORCHINDUCTOR_CACHE_DIR','TRITON_CACHE_DIR'):
            monkeypatch.setenv(name, value)
    nueva = tmp_path / 'cache_nueva'
    monkeypatch.setenv('CSG_CACHE_HOME', str(nueva))
    custom = tmp_path / 'cache_manual'
    custom.mkdir()
    witness = custom / 'conservar.txt'
    witness.write_text('original', encoding='utf-8')
    if manual:
        monkeypatch.setenv('TORCH_HOME', str(custom))
    paths = configurar_entorno(root)
    assert Path(os.environ['HF_HOME']).is_relative_to(paths.cache)
    assert Path(os.environ['TORCH_HOME']) == (custom if manual else paths.cache / 'torch')
    assert os.environ['CSG_RUNTIME_HOME'] == env['CSG_RUNTIME_HOME']
    assert os.environ['CSG_WEB_DATA'] == env['CSG_WEB_DATA']
    assert witness.read_text(encoding='utf-8') == 'original'


def test_raiz_de_trabajo_corta_conserva_evidencia_larga(candidato_minimo, tmp_path, monkeypatch):
    """065:RF-1, 065:RF-24 — evidencia larga y scratch propio corto sin escribir dentro de las fuentes."""
    mod = runner()
    for name in mod.ENTRADAS.values():
        monkeypatch.delenv(name, raising=False)
    salida = tmp_path / ('e' * 70) / ('f' * 70) / 'evidencia'
    trabajo = tmp_path / 'trabajo'
    assert mod.main(['--root',str(candidato_minimo),'--output-dir',str(salida),
                     '--trabajo-root',str(trabajo)]) == 0
    registro, = salida.glob('*/registro.json')
    data = json.loads(registro.read_text(encoding='utf-8'))
    work = Path(data['working_root'])
    assert work.is_relative_to(trabajo) and not work.is_relative_to(salida)
    assert (work / 'owner.json').is_file()
    base = Path(data['command'][data['command'].index('--basetemp') + 1])
    assert base.is_relative_to(work)
    assert (work / 'runtime/data/asistente').is_dir()
    assert not (candidato_minimo / 'runtime').exists()


def test_raiz_de_trabajo_en_el_candidato_se_rechaza_sin_escribir(candidato_minimo, tmp_path):
    """065:RF-24 — el scratch no puede apuntar a código ni datos fuente."""
    salida = tmp_path / 'evidencia'
    assert runner().main(['--root',str(candidato_minimo),'--output-dir',str(salida),
        '--trabajo-root',str(candidato_minimo / 'scratch')]) == 1
    assert not salida.exists() and not (candidato_minimo / 'scratch').exists()


def test_consulta_runtime_acota_y_cierra_sus_hijos(tmp_path, monkeypatch):
    """065:RF-24 — intérprete bloqueado real: plazo y cierre del lanzador con su árbol propio."""
    import psutil
    import time
    mod = runner()
    pidfile = tmp_path / 'hijo.txt'
    code = ('import subprocess,sys,time;from pathlib import Path;'
        'p=subprocess.Popen([sys.executable,"-B","-c","import time;time.sleep(60)"]);'
        f'Path({str(pidfile)!r}).write_text(str(p.pid));time.sleep(60)')
    started = []

    def lanzar(_cmd, *, cwd, env):
        process = subprocess.Popen([sys.executable,'-B','-c',code], cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        started.append(process)
        return process

    monkeypatch.setattr(mod, '_lanzar_consulta_runtime', lanzar)
    before = time.monotonic()
    with pytest.raises(ValueError, match='tiempo|plazo'):
        mod._runtime(Path(sys.executable), tmp_path, mod._entorno(tmp_path / 'run', {}), tiempo_s=2)
    assert time.monotonic() - before < 10
    assert started[0].poll() is not None
    assert pidfile.is_file(), 'la prueba debe haber creado el hijo real'
    pid = int(pidfile.read_text())
    try:
        child = psutil.Process(pid)
        assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        pass


def test_consulta_runtime_con_error_nativo_no_pierde_bytes(tmp_path, monkeypatch):
    """065:RF-24 — stderr no UTF-8 no rompe hilos lectores ni se confunde con un runtime válido."""
    mod = runner()

    def lanzar(_cmd, *, cwd, env):
        return subprocess.Popen([sys.executable,'-B','-c',
            'import sys;sys.stderr.buffer.write(b"error nativo: \\xff");sys.exit(3)'],
            cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

    monkeypatch.setattr(mod, '_lanzar_consulta_runtime', lanzar)
    with pytest.raises(ValueError, match='intérprete') as error:
        mod._runtime(Path(sys.executable),tmp_path,mod._entorno(tmp_path/'run',{}),tiempo_s=5)
    assert '\\xff' in str(error.value)


@pytest.mark.parametrize('contenido,esperado', [
    ('<testsuites><testsuite tests="4" failures="1" errors="0" skipped="2">'
     '<testcase classname="tests.test_x" name="test_ok"/>'
     '<testcase classname="tests.test_x" name="test_fallo"><failure message="fallo"/></testcase>'
     '<testcase classname="tests.test_x" name="test_skip"><skipped type="pytest.skip" message="falta fuente"/></testcase>'
     '<testcase classname="tests.test_x" name="test_xfail"><skipped type="pytest.xfail" message="razón"/></testcase>'
     '</testsuite></testsuites>', {'pass': 1, 'fail': 1, 'error': 0, 'skip': 1, 'xfail': 1}),
    ('<testsuite tests="1" failures="0" errors="1" skipped="0"><testcase name="coleccion"><error message="importación"/></testcase></testsuite>',
     {'pass': 0, 'fail': 0, 'error': 1, 'skip': 0, 'xfail': 0}),
])
def test_junit_conserva_resultados_y_razones(tmp_path, contenido, esperado):
    """065:RF-1/24 — una omisión o error no se registra como prueba aprobada."""
    ruta = tmp_path / 'resultado.xml'
    ruta.write_text(contenido, encoding='utf-8')
    informe = runner().resumir_junit(ruta)
    assert informe['counts'] == esperado
    assert any(r['message'] for r in informe['cases'] if r['outcome'] != 'pass')


@pytest.mark.parametrize('xml', [
    '<testsuites>', '<ajeno/>', '<testsuites/>',
    '<testsuite tests="2" failures="0" errors="0" skipped="0"><testcase name="uno"/></testsuite>',
    '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="uno"><skipped/></testcase></testsuite>',
    '<testsuite><testcase name="uno"/></testsuite>',
])
def test_junit_incompleto_o_incoherente_falla(tmp_path, xml):
    """065:RF-24 — XML vacío, truncado o con contadores falsos rechaza evidencia."""
    ruta = tmp_path / 'invalido.xml'
    ruta.write_text(xml, encoding='utf-8')
    with pytest.raises(ValueError):
        runner().resumir_junit(ruta)


def test_suite_completa_exige_nueve_fuentes_antes_de_escribir(candidato_minimo, tmp_path, monkeypatch, capsys):
    """065:RF-24 — faltar una variable impide iniciar una suite declarada completa."""
    modulo = runner()
    for variable in modulo.ENTRADAS.values():
        monkeypatch.delenv(variable, raising=False)
    salida = tmp_path / 'evidencia_no_creada'
    codigo = modulo.main(['--root', str(candidato_minimo), '--output-dir', str(salida), '--suite-completa'])
    assert codigo != 0
    assert not salida.exists()
    mensaje = capsys.readouterr().err
    assert all(variable in mensaje for variable in modulo.ENTRADAS.values())


def test_fuente_con_tipo_invalido_no_prepara_evidencia(candidato_minimo, tmp_path):
    """065:RF-24 — RED debe ser fichero aunque exista un directorio con ese nombre."""
    salida = tmp_path / 'rechazada'
    assert runner().main(['--root', str(candidato_minimo), '--output-dir', str(salida), '--red', str(tmp_path)]) != 0
    assert not salida.exists()


def test_preparar_no_ejecuta_y_preserva_ejecuciones(candidato_minimo, tmp_path):
    """065:RF-1/20/21 — preparar mantiene pendiente la ejecución y la aceptación nativa."""
    prueba = candidato_minimo / 'tests' / 'test_motor.py'
    prueba.write_text('raise RuntimeError("no debe ejecutarse al preparar")\n', encoding='utf-8')
    salida = tmp_path / 'evidencia'
    modulo = runner()
    argumentos = ['--root', str(candidato_minimo), '--output-dir', str(salida)]
    assert modulo.main(argumentos) == 0
    assert modulo.main(argumentos) == 0
    ejecuciones = sorted(salida.iterdir())
    assert len(ejecuciones) == 2
    for ejecucion in ejecuciones:
        registro = json.loads((ejecucion / 'registro.json').read_text(encoding='utf-8'))
        assert registro['state'] == 'preparado'
        assert not (ejecucion / 'junit.xml').exists()
        matriz = json.loads((ejecucion / 'matriz' / 'trazabilidad.json').read_text(encoding='utf-8'))
        assert matriz['rows'][0]['acceptance'] == 'pendiente_revision_semantica'
        assert 'aceptacion_nativa_pendiente' in matriz['rows'][0]['pending']


@pytest.mark.parametrize('completa,esperado', [(False, []), (True, ['omisiones'])])
def test_omisiones_solo_impiden_declarar_suite_completa(completa, esperado):
    """065:RF-24 — una ejecución parcial puede conservar skips sin certificarse completa."""
    fallos = runner().evaluar_resultado(0, {'counts': {'pass': 1, 'fail': 0, 'error': 0, 'skip': 1, 'xfail': 1}},
                                         'igual', 'igual', {}, {}, completa)
    assert fallos == esperado


def test_cambio_del_candidato_y_datos_invalida_resultado():
    """065:RF-1/24 — un pytest verde no prueba el candidato si sus entradas cambiaron."""
    informe = {'counts': {'pass': 1, 'fail': 0, 'error': 0, 'skip': 0, 'xfail': 0}}
    assert runner().evaluar_resultado(0, informe, 'antes', 'despues', {'x': 1}, {'x': 2}, False) == [
        'candidato_modificado', 'datos_modificados']
    assert runner().evaluar_resultado(1, informe, 'igual', 'igual', {}, {}, False) == ['pytest_exit_1']


@pytest.mark.parametrize('mutacion,esperado', [(False, 0), (True, 1)])
def test_subprocess_real_vincula_o_rechaza_candidato(candidato_minimo, tmp_path, monkeypatch, mutacion, esperado):
    """065:RF-1/20/24 — captura hashes antes/después de un pytest real, sin motor simulado."""
    for variable in runner().ENTRADAS.values():
        monkeypatch.delenv(variable, raising=False)
    # El hijo detecta entornos Git/Python heredados aunque el padre pertenezca a otro checkout.
    monkeypatch.setenv('GIT_DIR', str(tmp_path / 'git_incorrecto'))
    monkeypatch.setenv('PYTEST_ADDOPTS', '--no-es-una-opcion')
    monkeypatch.setenv('PYTHONPATH', str(tmp_path / 'otro_checkout'))
    codigo = '''import os
from pathlib import Path
def test_control():
    """065:RF-1 — ejecución del hijo controlado."""
    assert 'GIT_DIR' not in os.environ
    assert 'PYTEST_ADDOPTS' not in os.environ
    assert 'PYTHONPATH' not in os.environ
    assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'
    assert os.environ['OMP_NUM_THREADS'] == '1'
'''
    if mutacion:
        codigo += '    Path("src/motor.py").write_text("VALOR = 43\\n", encoding="utf-8")\n'
    (candidato_minimo / 'tests' / 'test_motor.py').write_text(codigo, encoding='utf-8')
    salida = tmp_path / 'evidencia'
    assert runner().main(['--root', str(candidato_minimo), '--output-dir', str(salida), '--ejecutar']) == esperado
    ejecucion, = salida.iterdir()
    registro = json.loads((ejecucion / 'registro.json').read_text(encoding='utf-8'))
    manifiesto = json.loads((ejecucion / 'manifiesto_ejecucion.json').read_text(encoding='utf-8'))
    assert registro['results']['counts']['pass'] == 1
    assert registro['returncode'] == 0
    assert ('candidato_modificado' in registro['errors']) == mutacion
    assert (manifiesto['source_hash_before'] != manifiesto['source_hash_after']) == mutacion
    assert (ejecucion / 'stdout.log').is_file() and (ejecucion / 'stderr.log').is_file()
    assert not list(candidato_minimo.rglob('__pycache__'))
    assert '--basetemp' in registro['command']


def test_inventario_datos_hash_opcional_detecta_cambio(tmp_path):
    """065:RF-1/24 — los SHA de datos solo se calculan mediante opción explícita."""
    ruta = tmp_path / 'fuente.txt'
    ruta.write_text('primero', encoding='utf-8')
    modulo = runner()
    ligero = modulo.inventariar_datos({'CSG_RED': ruta}, False)
    completo = modulo.inventariar_datos({'CSG_RED': ruta}, True)
    assert 'sha256' not in ligero['CSG_RED']['files'][0]
    assert len(completo['CSG_RED']['files'][0]['sha256']) == 64
    ruta.write_text('segundo', encoding='utf-8')
    assert modulo.inventariar_datos({'CSG_RED': ruta}, True) != completo


def test_leer_la_fuente_no_cuenta_como_cambio(tmp_path, monkeypatch):
    """065:RF-1/24 — mover la hora de acceso al leer no es un cambio; cambiar el contenido durante el hash, sí."""
    import os
    from pathlib import Path

    ruta = tmp_path / 'fuente.txt'
    ruta.write_text('primero', encoding='utf-8')
    modulo = runner()
    abrir = Path.open

    def con_acceso(self, *a, **k):
        fichero = abrir(self, *a, **k)
        st = os.stat(self)
        os.utime(self, ns=(st.st_atime_ns + 10**9, st.st_mtime_ns))
        return fichero

    monkeypatch.setattr(Path, 'open', con_acceso)
    assert len(modulo.inventariar_datos({'CSG_RED': ruta}, True)['CSG_RED']['files'][0]['sha256']) == 64

    def con_escritura(self, *a, **k):
        fichero = abrir(self, *a, **k)
        st = os.stat(self)
        os.utime(self, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        return fichero

    monkeypatch.setattr(Path, 'open', con_escritura)
    with pytest.raises(ValueError, match='cambió durante su hash'):
        modulo.inventariar_datos({'CSG_RED': ruta}, True)


@pytest.mark.parametrize('cuerpo,outcome,codigo', [
    ('assert False, "fallo controlado"', 'fail', 1),
    ('pytest.skip("recurso explícitamente ausente")', 'skip', 0),
    ('pytest.xfail("defecto explícito")', 'xfail', 0),
])
def test_subprocess_real_preserva_fallos_y_exclusiones(candidato_minimo, tmp_path, monkeypatch, cuerpo, outcome, codigo):
    """065:RF-24 — el registro distingue fallo, skip y xfail de una ejecución real."""
    modulo = runner()
    for variable in modulo.ENTRADAS.values():
        monkeypatch.delenv(variable, raising=False)
    prueba = candidato_minimo / 'tests' / 'test_motor.py'
    prueba.write_text('import pytest\ndef test_resultado():\n    ' + cuerpo + '\n', encoding='utf-8')
    salida = tmp_path / 'evidencia'
    assert modulo.main(['--root', str(candidato_minimo), '--output-dir', str(salida), '--ejecutar']) == codigo
    ejecucion, = salida.iterdir()
    registro = json.loads((ejecucion / 'registro.json').read_text(encoding='utf-8'))
    assert registro['results']['counts'][outcome] == 1
    assert registro['results']['counts']['pass'] == 0
    assert registro['results']['cases'][0]['message']
    assert (ejecucion / 'junit.xml').is_file()
    assert (ejecucion / 'manifiesto_ejecucion.json').is_file()


def test_salida_sobre_directorio_de_fuentes_se_rechaza(candidato_minimo, tmp_path):
    """065:RF-1/24 — la evidencia no altera el inventario de las fuentes observadas."""
    fuente = tmp_path / 'solicitudes'
    fuente.mkdir()
    salida = fuente / 'evidencia'
    assert runner().main(['--root', str(candidato_minimo), '--output-dir', str(salida),
                          '--solicitud-dir', str(fuente)]) != 0
    assert not salida.exists()


def test_suite_completa_no_admite_seleccion_parcial(candidato_minimo, tmp_path):
    """065:RF-24 — declarar completa una selección de nodeids se rechaza antes de escribir."""
    salida = tmp_path / 'evidencia'
    assert runner().main(['--root', str(candidato_minimo), '--output-dir', str(salida),
                          '--suite-completa', '--prueba', 'tests/test_motor.py']) != 0
    assert not salida.exists()
