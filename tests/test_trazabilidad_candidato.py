"""065:RF-1/20/21/24 — evidencia reproducible sin confundir citas con aceptación."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from apoyo import cargar_herramienta

ES = cargar_herramienta('estado_specs.py')


@pytest.fixture
def candidato(tmp_path):
    raiz = tmp_path / 'candidato'
    carpeta = raiz / 'specs' / '065-ejemplo'
    carpeta.mkdir(parents=True)
    (carpeta / 'spec.md').write_text('''# Ejemplo
Estado: aprobada
- RF-1: EL SISTEMA registra.
- RF-2: EL SISTEMA verifica.
- RF-3: EL SISTEMA conserva.
- RF-4: EL SISTEMA compara.
''', encoding='utf-8')
    (carpeta / 'tasks.md').write_text('- [ ] T1 [DIgSILENT] Validación nativa. (RF-1 a RF-4)\n  Hecho cuando: reapertura real.\n', encoding='utf-8')
    (raiz / 'src').mkdir()
    (raiz / 'src' / 'motor.py').write_text('"""065:RF-1 a RF-4 — implementa el contrato."""\n', encoding='utf-8')
    (raiz / 'tests').mkdir()
    (raiz / 'tests' / 'test_motor.py').write_text('''"""065:RF-3 — una cita de módulo no atribuye pruebas."""
class TestMotor:
    """065:RF-4 — una cita de clase no atribuye pruebas."""
    def test_funciona(self):
        """065:RF-1 — verifica el valor observado."""
        assert 2 + 2 == 4

def test_vacia():
    """065:RF-2 — cita sin aserción."""
    pass
''', encoding='utf-8')
    (raiz / 'CODIGO_FUENTE.md').write_text('| `src/motor.py` | Motor. | 065 (RF-1 a RF-4) |\n', encoding='utf-8')
    return raiz


def herramienta():
    return cargar_herramienta('trazabilidad_candidato.py')


def test_lector_canonico_rangos_letras_barras_y_citas_vacias():
    """065:RF-20 — rangos y citas vacías no inventan RF ni cantidades."""
    definidos = {'065': {'1', '2', '2b', '3'}}
    assert ES.citas_en_texto('"065:RF-1 a RF-3"; 065:RF-2/2b; 065:RF-', definidos) == definidos
    assert ES.citas_en_texto('065:RF-2b a RF-2d', {'065': {'2b', '2c', '2d'}}) == {'065': {'2b', '2c', '2d'}}
    assert ES.citas_en_texto('sin referencia; 065:RF-') == {}
    assert ES.citas_en_texto('065:RF-9/10') == {'065': {'9', '10'}}
    assert ES.citas_en_texto('011:RF-1 a 011:RF-5') == {'011': {'1', '5'}}
    assert ES.citas_en_texto('065:RF-20 a RF-24', {'065': {'20', '21', '22', '23', '24'}}) == {'065': {'20', '21', '22', '23', '24'}}


def test_matriz_distingue_funciones_aserciones_y_docstrings(candidato):
    """065:RF-20/21 — inventario y docstrings no prueban el dominio."""
    informe = herramienta().construir_matriz(candidato)
    filas = {f['requirement']: f for f in informe['rows']}
    assert len(filas) == 4
    assert filas['065:RF-1']['tests'][0]['nodeid'] == 'tests/test_motor.py::TestMotor::test_funciona'
    assert filas['065:RF-1']['tests'][0]['has_assertion'] is True
    assert filas['065:RF-2']['tests'][0]['has_assertion'] is False
    assert not filas['065:RF-3']['tests'] and not filas['065:RF-4']['tests']
    assert {c['scope'] for c in informe['formal_citations']} >= {'module', 'class', 'function'}
    assert all('aceptacion_nativa_pendiente' in f['pending'] for f in filas.values())
    assert all(f['acceptance'] == 'pendiente_revision_semantica' for f in filas.values())


def test_lectura_formal_excluye_fixtures_y_guia_no_prueba_dominio(candidato):
    """065:RF-20/21 — las guías y cadenas de ejemplo conservan su naturaleza."""
    (candidato / 'docs').mkdir()
    (candidato / 'docs' / 'guia.md').write_text('Guía de 2026-11-02, sin ejecutar el motor.', encoding='utf-8')
    (candidato / 'CODIGO_FUENTE.md').write_text('| `docs/guia.md` | Guía. | 065 (RF-2), 2026-11-02 |\n', encoding='utf-8')
    (candidato / 'src' / 'motor.py').write_text('DATO = "065:RF-99"\n', encoding='utf-8')
    informe = herramienta().construir_matriz(candidato)
    assert not informe['errors']
    assert 'implementacion_rf_sin_vinculo_explicito' in informe['rows'][1]['pending']
    assert informe['rows'][1]['implementation'][0]['role'] == 'documentacion_configuracion_no_ejecucion_dominio'


def test_citas_canonicas_retienen_docstring_y_comentario_no_fixture(candidato):
    """065:RF-20 — las guardas conservan citas genuinas sin atribuir datos de ejemplo."""
    ruta = candidato / 'tests' / 'test_citas.py'
    ruta.write_text('''"""065:RF-1 — contrato de módulo."""
# 065:RF-2 — comentario de trazabilidad genuino.
DATO_NEGATIVO = "065:RF-99"
def test_real():
    """065:RF-3 — contrato de función."""
    assert True
''', encoding='utf-8')
    assert ES.citas_de_pruebas(candidato) == {'065': {'1', '2', '3', '4'}}


def test_hash_incluye_cambios_relevantes_y_excluye_runtime(candidato):
    """065:RF-1/24 — el candidato cambia con código/config, no con cachés/evidencia."""
    tc = herramienta()
    antes = tc.hash_candidato(candidato)
    (candidato / 'output').mkdir()
    (candidato / 'output' / 'evidencia.json').write_text('{}', encoding='utf-8')
    (candidato / 'src' / '__pycache__').mkdir()
    (candidato / 'src' / '__pycache__' / 'dato.py').write_text('CAMBIO = 1', encoding='utf-8')
    assert tc.hash_candidato(candidato) == antes
    (candidato / 'config').mkdir()
    (candidato / 'config' / 'politica.json').write_text('{"limite": 1}', encoding='utf-8')
    assert tc.hash_candidato(candidato)[0] != antes[0]


@pytest.mark.parametrize('relativo', [
    'requirements-nucleo.lock', 'requirements-complemento-ia.txt',
    'requirements-mcp.txt', 'requirements-motores.txt', 'requirements-madrl.txt',
    'constraints-python312-win.txt', 'instalador/ConverterSmartGrid.iss',
    'frontend/licencias/react-19.3.0-LICENSE.txt', 'LICENSE',
    'output/linea_base_001.json', 'output/linea_base_001_mdb.json',
    'tests_ml/test_validacion_cuda.py', 'docs/MODELOS_IA_LOCK.json',
    'docs/UPSTREAM_IA_LOCK.json',
])
def test_cambiar_entrada_de_entrega_o_referencia_invalida_huella(candidato, relativo):
    """065:RF-1/24 — cambiar dependencias, instalación o referencias invalida el candidato observado."""
    tc = herramienta()
    ruta = candidato / relativo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b'entrada anterior\n')
    antes, _ = tc.hash_candidato(candidato)
    ruta.write_bytes(b'entrada diferente\n')
    despues, archivos = tc.hash_candidato(candidato)
    assert antes != despues, f'Una entrada de la entrega cambia sin invalidar su evidencia: {relativo}'
    assert relativo in archivos
    ruta.unlink()
    assert tc.hash_candidato(candidato)[0] != despues


def junit(raiz, estados=('pass',)):
    ruta = raiz.parent / 'resultados.xml'
    nombres = ['TestMotor.test_funciona', 'test_vacia', 'test_omitida', 'test_xfail']
    cuerpos = {'pass': '', 'fail': '<failure message="falló"/>', 'skip': '<skipped/>', 'xfail': '<skipped type="pytest.xfail"/>'}
    ruta.write_text('<testsuite>' + ''.join(f'<testcase classname="tests.test_motor{(".TestMotor" if i == 0 else "")}" name="{nombres[i].split(".")[-1]}">{cuerpos[e]}</testcase>' for i, e in enumerate(estados)) + '</testsuite>', encoding='utf-8')
    return ruta


def ejecutar_pytest_real(raiz, nombre='pytest-real'):
    """Observa el candidato antes de ejecutar y conserva JUnit y salida auténticos."""
    tc = herramienta()
    antes, _ = tc.hash_candidato(raiz)
    xml = raiz.parent / f'{nombre}.xml'
    comando = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               '--basetemp', str(raiz.parent / f'{nombre}-tmp'), '--junitxml', str(xml),
               'tests/test_motor.py::TestMotor::test_funciona']
    resultado = subprocess.run(comando, cwd=raiz, capture_output=True, text=True, encoding='utf-8')
    (raiz.parent / f'{nombre}.log').write_text(resultado.stdout + resultado.stderr, encoding='utf-8')
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return xml, subprocess.list2cmdline(comando), antes


def test_repro_r5_impide_manifiesto_posthoc_sin_observacion_anterior(candidato):
    """065:RF-20/24 — JUnit genuino previo no acredita un test cambiado después."""
    tc = herramienta()
    xml, comando, antes = ejecutar_pytest_real(candidato, 'r5-genuino')
    ruta = candidato / 'tests' / 'test_motor.py'
    ruta.write_text(ruta.read_text(encoding='utf-8').replace('assert 2 + 2 == 4', 'assert False'), encoding='utf-8')
    assert antes != tc.hash_candidato(candidato)[0]
    with pytest.raises(ValueError, match='anterior'):
        tc.manifiesto_ejecucion(candidato, xml, comando, tc.revision(candidato))
    datos = tc.manifiesto_ejecucion(candidato, xml, comando, tc.revision(candidato), source_hash_before=antes)
    manifest = candidato.parent / 'r5-observado.json'
    manifest.write_text(json.dumps(datos), encoding='utf-8')
    informe = tc.construir_matriz(candidato, [xml], [manifest])
    assert informe['errors']
    assert informe['executions'][0]['verified'] is False
    assert informe['rows'][0]['test_evidence'] == 'pendiente'


@pytest.mark.parametrize('campo', ['source_hash_before', 'source_hash_after'])
@pytest.mark.parametrize('valor', [None, '', 'invalido', '0' * 64])
def test_r5_exige_ambas_observaciones_hash_validas(candidato, campo, valor):
    """065:RF-20/24 — antes/después ausentes, inválidos o diferentes fallan cerrados."""
    tc = herramienta()
    xml, comando, antes = ejecutar_pytest_real(candidato, 'r5-hashes')
    datos = tc.manifiesto_ejecucion(candidato, xml, comando, tc.revision(candidato), source_hash_before=antes)
    if valor is None:
        datos.pop(campo)
    else:
        datos[campo] = valor
    manifest = candidato.parent / 'r5-incompleto.json'
    manifest.write_text(json.dumps(datos), encoding='utf-8')
    informe = tc.construir_matriz(candidato, [xml], [manifest])
    assert informe['errors']
    assert informe['executions'][0]['verified'] is False


def test_r5_identidad_observada_no_certifica_semantica(candidato):
    """065:RF-20/21/24 — un pass real con hashes iguales conserva aceptación pendiente."""
    tc = herramienta()
    xml, comando, antes = ejecutar_pytest_real(candidato, 'r5-mismo-codigo')
    datos = tc.manifiesto_ejecucion(candidato, xml, comando, tc.revision(candidato), source_hash_before=antes)
    assert antes == datos['source_hash_after'] == datos['candidate_sha256']
    manifest = candidato.parent / 'r5-valido.json'
    manifest.write_text(json.dumps(datos), encoding='utf-8')
    informe = tc.construir_matriz(candidato, [xml], [manifest])
    assert not informe['errors']
    assert informe['executions'][0]['verified'] is True
    assert informe['rows'][0]['test_evidence'] == 'ejecucion_verificada'
    assert informe['rows'][0]['acceptance'] == 'pendiente_revision_semantica'
    assert 'aceptacion_nativa_pendiente' in informe['rows'][0]['pending']


def test_ejecucion_exige_manifest_mismo_hash_y_entradas(candidato):
    """065:RF-1/20/24 — un pass sin identidad o de otro código queda pendiente."""
    tc = herramienta()
    xml = junit(candidato)
    sin = tc.construir_matriz(candidato, junit_paths=[xml])
    assert not sin['rows'][0]['tests'][0]['executions'][0]['verified']
    manifiesto = candidato.parent / 'ejecucion.json'
    manifiesto.write_text(json.dumps(tc.manifiesto_ejecucion(candidato, xml, 'python -m pytest', 'revision-prueba', source_hash_before=tc.hash_candidato(candidato)[0])), encoding='utf-8')
    bueno = tc.construir_matriz(candidato, junit_paths=[xml], manifest_paths=[manifiesto])
    assert bueno['rows'][0]['tests'][0]['executions'][0]['verified']
    assert bueno['rows'][0]['test_evidence'] == 'ejecucion_verificada'
    assert bueno['rows'][0]['acceptance'] == 'pendiente_revision_semantica'
    datos = json.loads(manifiesto.read_text(encoding='utf-8'))
    datos.pop('command')
    manifiesto.write_text(json.dumps(datos), encoding='utf-8')
    assert not tc.construir_matriz(candidato, junit_paths=[xml], manifest_paths=[manifiesto])['rows'][0]['tests'][0]['executions'][0]['verified']
    manifiesto.write_text(json.dumps(tc.manifiesto_ejecucion(candidato, xml, 'pytest', 'revision-prueba', source_hash_before=tc.hash_candidato(candidato)[0])), encoding='utf-8')
    (candidato / 'src' / 'motor.py').write_text('CAMBIO = True\n', encoding='utf-8')
    cambiado = tc.construir_matriz(candidato, junit_paths=[xml], manifest_paths=[manifiesto])
    assert not cambiado['rows'][0]['tests'][0]['executions'][0]['verified']
    assert any('candidato' in e for e in cambiado['errors'])


def test_junit_conserva_resultados_y_repeticiones(candidato):
    """065:RF-20/24 — no se ocultan fail, skip, xfail ni ejecuciones repetidas."""
    tc = herramienta()
    xml = junit(candidato, ('pass', 'fail', 'skip', 'xfail'))
    resultados = tc.leer_junit(xml)
    assert [r['outcome'] for r in resultados] == ['pass', 'fail', 'skip', 'xfail']
    assert len(tc.construir_matriz(candidato, junit_paths=[xml, xml])['rows'][0]['tests'][0]['executions']) == 2


@pytest.mark.parametrize('campo', ['junit_sha256', 'inputs', 'revision', 'candidate_sha256'])
def test_manifest_incompleto_nunca_aprueba_y_falla_comprobacion(candidato, campo):
    """065:RF-1/20/24 — no se ignoran manifiestos incompletos entregados explícitamente."""
    tc = herramienta()
    xml = junit(candidato)
    datos = tc.manifiesto_ejecucion(candidato, xml, 'pytest', 'revision-prueba', source_hash_before=tc.hash_candidato(candidato)[0])
    datos.pop(campo)
    manifest = candidato.parent / 'incompleto.json'
    manifest.write_text(json.dumps(datos), encoding='utf-8')
    informe = tc.construir_matriz(candidato, junit_paths=[xml], manifest_paths=[manifest])
    assert informe['errors']
    assert not informe['rows'][0]['tests'][0]['executions'][0]['verified']


def test_un_fallo_repetido_no_desaparece_por_un_pass_posterior(candidato):
    """065:RF-20/24 — una ejecución fallida se conserva aunque otro XML pase."""
    tc = herramienta()
    xml1 = junit(candidato, ('fail',))
    fallo = candidato.parent / 'fallo.xml'
    fallo.write_bytes(xml1.read_bytes())
    xml2 = junit(candidato)
    manifests = []
    for i, xml in enumerate([fallo, xml2]):
        manifest = candidato.parent / f'run-{i}.json'
        manifest.write_text(json.dumps(tc.manifiesto_ejecucion(candidato, xml, 'pytest', 'revision-prueba', source_hash_before=tc.hash_candidato(candidato)[0])), encoding='utf-8')
        manifests.append(manifest)
    informe = tc.construir_matriz(candidato, junit_paths=[fallo, xml2], manifest_paths=manifests)
    assert [e['outcome'] for e in informe['rows'][0]['tests'][0]['executions']] == ['fail', 'pass']
    assert informe['rows'][0]['test_evidence'] == 'pendiente'


@pytest.mark.parametrize('clase', ['archivo', 'requisito', 'prueba'])
def test_comprobar_rechaza_enlaces_invalidos(candidato, clase):
    """065:RF-20 — enlaces inexistentes o sin función fallan cerrados."""
    tc = herramienta()
    if clase == 'archivo':
        (candidato / 'CODIGO_FUENTE.md').write_text('| `src/fantasma.py` | Motor. | 065 (RF-1) |\n', encoding='utf-8')
    elif clase == 'requisito':
        with (candidato / 'tests' / 'test_motor.py').open('a', encoding='utf-8') as f:
            f.write('\ndef test_fantasma():\n    """065:RF-99 — no existe."""\n    assert True\n')
    else:
        vinculos = candidato.parent / 'vinculos.json'
        vinculos.write_text(json.dumps([{'requirement': '065:RF-1', 'implementation': 'src/motor.py', 'tests': ['tests/test_motor.py::TestMotor']}]), encoding='utf-8')
    args = ['--root', str(candidato), '--output-dir', str(candidato.parent / 'salida'), '--comprobar']
    if clase == 'prueba':
        args += ['--vinculos', str(vinculos)]
    assert tc.main(args) == 1


def test_cli_salida_externa_y_manifiesto_de_entradas(candidato):
    """065:RF-1/20/24 — JSON/CSV y hashes van fuera de los checkouts."""
    tc = herramienta()
    with pytest.raises(ValueError, match='extern'):
        tc.validar_salida(candidato / 'salida', candidato)
    salida = candidato.parent / 'salida'
    assert tc.main(['--root', str(candidato), '--output-dir', str(salida)]) == 0
    informe = json.loads((salida / 'trazabilidad.json').read_text(encoding='utf-8'))
    assert informe['candidate']['inputs']['src/motor.py']
    assert (salida / 'trazabilidad.csv').read_text(encoding='utf-8').count('\n') == 5
    assert (salida / 'manifest.json').is_file()
    resultado = subprocess.run([sys.executable, '-B', str(Path(ES.__file__).with_name('trazabilidad_candidato.py')), '--help'], capture_output=True, text=True)
    assert resultado.returncode == 0 and '--junit' in resultado.stdout


RAIZ = Path(__file__).resolve().parents[1]
FASES_DEL_PLAN = [f'M{n}' for n in range(11)]
ESTADOS_DEL_PROTOCOLO = {'pendiente', 'listo', 'en curso', 'revisión', 'bloqueado', 'integrado', 'archivado'}


def _registro_de_fases(texto: str) -> list[list[str]]:
    bloque = texto.split('<!-- registro-fases -->')[1].split('<!-- /registro-fases -->')[0]
    filas = [[c.strip() for c in linea.strip().strip('|').split('|')]
             for linea in bloque.splitlines() if linea.startswith('|')]
    return filas[2:]


def test_registro_tiene_candidato_responsable_cambios_dependencias_y_evidencia_por_fase():
    """065:RF-1 — el registro decía «M1–M10 pendientes» con todo implementado: cada fase responde de lo suyo."""
    texto = (RAIZ / 'docs/implementacion065/progreso.md').read_text(encoding='utf-8')
    assert 'feat/065-cierre' in texto or 'integracion/065' in texto, 'Falta el candidato'
    filas = _registro_de_fases(texto)
    assert [f[0] for f in filas] == FASES_DEL_PLAN
    for fase, responsable, cambios, dependencias, evidencia, estado in filas:
        assert responsable and dependencias, fase
        assert estado in ESTADOS_DEL_PROTOCOLO, fase
        # Un fichero citado que no existe es un registro que miente: se comprueba, no se lee.
        for columna in (cambios, evidencia):
            rutas = re.findall(r'`([^`]+)`', columna)
            assert rutas, fase
            assert [r for r in rutas if not (RAIZ / r).is_file()] == [], fase


def test_el_registro_no_da_por_hechas_las_fases_con_tarea_abierta():
    """065:RF-1, 065:RF-21 — mientras T12 o T13 sigan abiertas, M9 y M10 no constan como hechas."""
    filas = {f[0]: f[-1] for f in _registro_de_fases(
        (RAIZ / 'docs/implementacion065/progreso.md').read_text(encoding='utf-8'))}
    tareas = (RAIZ / 'specs/065-cierre-de-auditoria-integral/tasks.md').read_text(encoding='utf-8')
    if '- [ ] T12 ' in tareas:
        assert filas['M9'] not in {'integrado', 'revisión'}
    if '- [ ] T13 ' in tareas:
        assert filas['M10'] not in {'integrado', 'revisión'}


def test_matriz_real_enlaza_cada_rf_de_la_spec_sin_dar_aceptacion():
    """065:RF-20, 065:RF-21 — en el repositorio, no en un ejemplo: cada RF con código y prueba, y nada aceptado."""
    informe = herramienta().construir_matriz(RAIZ)
    assert informe['errors'] == []
    filas = [f for f in informe['rows'] if f['requirement'].startswith('065:')]
    spec = next(s for s in ES.leer_specs(RAIZ) if s.numero == '065')
    assert len(filas) == len(spec.rf)
    for fila in filas:
        assert fila['implementation'], fila['requirement']
        # RF-9 pide que las pruebas del frontend den lo mismo en cualquier ruta: lo que lo implementa son
        # las propias pruebas, y la matriz no cuenta una prueba como código. Es la única excepción.
        if fila['requirement'] != '065:RF-9':
            assert 'implementacion_rf_sin_vinculo_explicito' not in fila['pending'], fila['requirement']
        assert any(t['has_assertion'] for t in fila['tests']), fila['requirement']
        # Sin una ejecución vinculada por hash, la matriz sigue diciendo que falta: citar no es ejecutar.
        assert 'ejecucion_del_candidato_pendiente_o_no_aprobada' in fila['pending'], fila['requirement']
        assert fila['acceptance'] == 'pendiente_revision_semantica', fila['requirement']
    # La T12 de DIgSILENT del RF-21 se retiró el 2026-11-08 por orden del usuario y pasó a la 086 (R1 a R5):
    # con una tarea de DIgSILENT vigente, la aceptación nativa queda pendiente; sin ella, sigue sin aceptarse.
    rf21 = next(f for f in filas if f['requirement'] == '065:RF-21')
    if any(t.digsilent and '21' in ES.rf_de_texto(t.texto) for t in spec.tareas):
        assert 'aceptacion_nativa_pendiente' in rf21['pending']
    assert rf21['acceptance'] == 'pendiente_revision_semantica'
