"""065:RF-24; 086:RF-46 — una tanda parcial no acredita entrega integral."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from apoyo import cargar_herramienta


def herramienta():
    return cargar_herramienta('verificar_entrega_integral.py', 'entrega_integral', tools_en_path=True)


def comprobacion(tmp_path, *, kind='command', codigo='print("correcto")', **extra):
    return {'id': 'prueba', 'kind': kind, 'command': [sys.executable, '-c', codigo],
            'cwd': str(tmp_path), 'timeout_s': 5, **extra}


def test_planes_separan_frontend_y_ml_sin_omitirlos(tmp_path):
    """065:RF-24 — la edición completa añade ML, sin sustituir ninguna puerta del núcleo."""
    h = herramienta()
    core = h.plan_comprobaciones(tmp_path, Path(sys.executable), 'nucleo', tmp_path/'e')
    full = h.plan_comprobaciones(tmp_path, Path(sys.executable), 'completa', tmp_path/'e')
    base = {p['id'] for p in core}
    assert {'backend', 'frontend_tests', 'frontend_lint', 'frontend_types', 'frontend_build',
            'python_check', 'python_audit', 'frontend_audit'} <= base
    assert {p['id'] for p in full} == base | {'ml', 'campanas'}
    assert all(isinstance(p['command'], list) and p['command'] for p in full if p['kind'] != 'campanas')
    assert '--suite-completa' in next(p['command'] for p in full if p['id']=='backend')
    assert '--hash-datos' in next(p['command'] for p in full if p['id']=='backend')
    with pytest.raises(ValueError):
        h.plan_comprobaciones(tmp_path, Path(sys.executable), 'parcial', tmp_path/'e')


@pytest.mark.parametrize('ilicita', [False, True])
def test_lint_real_es_puerta_de_entrega_y_rechaza_cruces(tmp_path, ilicita):
    """002:RF-19; 065:RF-24 — el lint real bloquea la entrega por un cruce entre features."""
    h = herramienta()
    root = Path(__file__).resolve().parents[1]
    fixture = tmp_path/'frontend'
    (fixture/'src/features/uno').mkdir(parents=True)
    (fixture/'src/features/dos').mkdir()
    (fixture/'tsconfig.json').write_text('{"compilerOptions":{"moduleResolution":"bundler"}}', encoding='utf-8')
    (fixture/'src/features/dos/panel.ts').write_text('export const valor=1;', encoding='utf-8')
    texto = "import {valor} from '../dos/panel'; export const resultado=valor;" if ilicita else 'export const resultado=1;'
    (fixture/'src/features/uno/panel.ts').write_text(texto, encoding='utf-8')
    plan = h.plan_comprobaciones(root, Path(sys.executable), 'nucleo', tmp_path/'e')
    lint = next(p for p in plan if p['id']=='frontend_lint')
    lint['command'] += ['--raiz', str(fixture)]
    resultado = h.ejecutar_comprobacion(lint, tmp_path/'e')
    assert resultado['returncode'] == int(ilicita)
    assert resultado['state'] == ('rechazada' if ilicita else 'aprobada')
    entrega = h.evaluar_entrega([resultado], {'frontend_lint'})
    assert entrega['technical_checks_passed'] is (not ilicita)
    if ilicita:
        assert 'otro feature' in Path(resultado['stderr']).read_text(encoding='utf-8')


@pytest.mark.parametrize('caso', ['fallo', 'ausente', 'duplicado', 'no_ejecutado'])
def test_entrega_no_acepta_puertas_incompletas(caso):
    """065:RF-24 — cada puerta obligatoria debe existir una vez y haber pasado."""
    h = herramienta()
    resultado = [{'id':'a','state':'aprobada'}, {'id':'b','state':'aprobada'}]
    if caso=='fallo': resultado[1]['state']='rechazada'
    if caso=='ausente': resultado.pop()
    if caso=='duplicado': resultado.append(resultado[0].copy())
    if caso=='no_ejecutado': resultado[1]['state']='preparada'
    r = h.evaluar_entrega(resultado, {'a','b'})
    assert not r['technical_checks_passed'] and r['errors']
    assert r['production_ready_core'] is False


def test_pruebas_aprobadas_no_son_aceptacion_electrica():
    """065:RF-21/24 — regresión técnica completa conserva la aceptación externa pendiente."""
    r = herramienta().evaluar_entrega([{'id':'a','state':'aprobada'}], {'a'})
    assert r['technical_checks_passed']
    assert r['production_ready_core'] is False and r['project_complete'] is False
    assert 'aceptacion_electrica' in r['pending'] and 'aceptacion_operativa' in r['pending']


@pytest.mark.parametrize('codigo,esperado', [('print("correcto")','aprobada'),
    ('raise SystemExit(7)','rechazada')])
def test_procesos_reales_conservan_salida_y_codigo(tmp_path, codigo, esperado):
    """065:RF-24 — el exit real y los registros gobiernan el resultado."""
    r = herramienta().ejecutar_comprobacion(comprobacion(tmp_path,codigo=codigo), tmp_path/'e')
    assert r['state']==esperado and Path(r['stdout']).is_file() and Path(r['stderr']).is_file()
    assert r['returncode']==(0 if esperado=='aprobada' else 7)


def test_timeout_no_se_convierte_en_pase(tmp_path):
    """065:RF-24 — proceso propio agotado deja la evidencia y el estado rechazado."""
    c = comprobacion(tmp_path,codigo='import time; time.sleep(1)'); c['timeout_s']=0.05
    r = herramienta().ejecutar_comprobacion(c,tmp_path/'e')
    assert r['state']=='rechazada' and 'timeout' in r['errors']


def test_junit_ausente_no_pasa_con_exit_cero(tmp_path):
    """065:RF-24 — una orden que no produjo sus casos no ejecutó la suite exigida."""
    c = comprobacion(tmp_path,kind='pytest',artifact=str(tmp_path/'no.xml'))
    r = herramienta().ejecutar_comprobacion(c,tmp_path/'e')
    assert r['state']=='rechazada' and r['errors']


@pytest.mark.parametrize('marca', ['', '<skipped message="omitida"/>', '<failure message="fallo"/>'])
def test_junit_real_rechaza_skips_y_fallos(tmp_path,marca):
    """065:RF-24 — valida los testcases reales, incluso si el proceso devuelve cero."""
    skipped=int('skipped' in marca); failures=int('failure' in marca)
    xml=(f'<testsuites><testsuite name="s" tests="1" failures="{failures}" errors="0" skipped="{skipped}">'
         f'<testcase name="caso">{marca}</testcase></testsuite></testsuites>')
    path=tmp_path/'junit.xml';path.write_text(xml,encoding='utf-8')
    r=herramienta().ejecutar_comprobacion(comprobacion(tmp_path,kind='pytest',artifact=str(path)),tmp_path/'e')
    assert (r['state']=='aprobada') == (not marca)


@pytest.mark.parametrize('skip', [0,1])
def test_tap_rechaza_omisiones_aunque_node_salve_exit(skip,tmp_path):
    """065:RF-24 — Node puede devolver cero con omitidas; la entrega no las admite."""
    tap=f'TAP version 13\n# tests 1\n# pass {1-skip}\n# fail 0\n# cancelled 0\n# skipped {skip}\n# todo 0\n'
    r=herramienta().ejecutar_comprobacion(comprobacion(tmp_path,kind='tap',codigo=f'print({tap!r})'),tmp_path/'e')
    assert (r['state']=='aprobada') == (skip==0)


@pytest.mark.parametrize('dato', [{'dependencies':[]}, {'dependencies':[{'name':'p','version':'1','vulns':[{'id':'CVE-prueba'}]}]},
    {'dependencies':[{'name':'p','skip_reason':'no auditado'}]}, {'dependencies':[{'name':'p','version':'1','vulns':[]}]}])
def test_auditoria_python_completa_y_sin_avisos(tmp_path,dato):
    """086:RF-44; 065:RF-24 — lista vacía o dependencia no auditada no acreditan seguridad."""
    r=herramienta().ejecutar_comprobacion(comprobacion(tmp_path,kind='pip_audit',codigo=f'print({json.dumps(dato)!r})'),tmp_path/'e')
    assert (r['state']=='aprobada') == (dato=={'dependencies':[{'name':'p','version':'1','vulns':[]}]})


def test_fallo_temprano_deja_las_demas_puertas_pendientes(tmp_path):
    """065:RF-24 — interrupción no hereda resultados de una corrida anterior."""
    h=herramienta()
    c=comprobacion(tmp_path,codigo='raise SystemExit(2)')
    siguientes={**comprobacion(tmp_path),'id':'segunda'}
    r=h.ejecutar_plan([c,siguientes],tmp_path/'e')
    assert [x['state'] for x in r]==['rechazada','no_ejecutada']
    assert not (tmp_path/'e'/'segunda').exists()


def test_backend_sin_huella_no_se_acredita_por_resumen(tmp_path):
    """065:RF-1/24 — el resumen aprobado sin identidad del código no basta."""
    registro=tmp_path/'backend'/'intento';registro.mkdir(parents=True)
    (registro/'registro.json').write_text(json.dumps({'state':'regresion_aprobada',
        'scope':'suite_completa','data_hash_mode':'sha256','missing_inputs':[],
        'results':{'counts':{'pass':1,'fail':0,'error':0,'skip':0,'xfail':0}}}),encoding='utf-8')
    r=herramienta().ejecutar_comprobacion(comprobacion(tmp_path,kind='backend',
        artifact=str(registro.parent)),tmp_path/'e')
    assert r['state']=='rechazada'


@pytest.mark.parametrize('dato', [[], {}, {'error':{'message':'sin conexión'}},
    {'metadata':{'dependencies':{'total':1},'vulnerabilities':{'total':1}}},
    {'metadata':{'dependencies':{'total':1},'vulnerabilities':{'total':0}}}])
def test_auditoria_npm_incompleta_o_con_avisos_no_acredita_entrega(tmp_path,dato):
    """065:RF-24; 086:RF-44 — respuestas truncadas o avisos no son un pase."""
    r=herramienta().ejecutar_comprobacion(comprobacion(tmp_path,kind='npm_audit',
        codigo=f'print({json.dumps(dato)!r})'),tmp_path/'e')
    assert (r['state']=='aprobada') == (dato=={'metadata':{'dependencies':{'total':1},'vulnerabilities':{'total':0}}})


def _recibos_campanas(tmp_path, *, modo='runtime'):
    """Dobles CPU del contrato del lector; metadata runtime no es campaña científica."""
    import hashlib
    from test_harness_contratos import configuracion
    from convertersmartgrid.evaluacion_harness.contratos import MINIMAS, huella, sellar
    from convertersmartgrid.evaluacion_harness.ejecucion import ejecutar
    from convertersmartgrid.evaluacion_harness.publicacion import publicar

    refs = []
    for familia in MINIMAS:
        cfg = configuracion(familia)
        cfg['run_id'] = 'contrato-validador-' + familia
        for modelo in cfg['modelos'].values():
            modelo['artifacts'] = {'peso_sintetico.bin': '1' * 64}
        for suite in cfg['suites']:
            if suite['tipo'] == 'recuperacion':
                suite['parametros']['k'] = 1
                suite['puertas'] = {'recall@k': {'minimo': 0}}
                for caso in suite['casos']:
                    caso['esperado'] = {'documentos': ['D'], 'completo': True}
            elif suite['tipo'] == 'entidades':
                suite['puertas'] = {'precision': {'minimo': 0}}
                for caso in suite['casos']:
                    caso['esperado'] = {'entidades': [['dato', 'valor']]}
        cfg = sellar(cfg)
        def proveedor(modelo, suite, entrada):
            return {'prediccion': {'tarea': 'a', 'entidades': [['dato', 'valor']], 'documentos': ['D']},
                    'modelo_digest': modelo['digest'], 'config_hash': modelo['config_hash'],
                    'artifacts_hash': huella(modelo['artifacts']),
                    'backend': 'doble_sintetico_validador', 'dispositivo': 'cpu', 'clase_evidencia': 'real'}
        evaluadores = {s['tipo']: lambda *_: {'metricas': {'acierto': 1.}, 'aprobado': True,
                                             'clase_evidencia': 'real'} for s in cfg['suites']}
        informe = ejecutar(cfg, proveedor, modo=modo, evaluadores=evaluadores)
        ruta = tmp_path / (familia + '.json')
        publicar(ruta, informe)
        refs.append((familia, str(ruta), hashlib.sha256(ruta.read_bytes()).hexdigest()))
    return refs


def _alterar_recibo(ref, cambiar):
    import hashlib
    from convertersmartgrid.evaluacion_harness.contratos import huella
    from convertersmartgrid.evaluacion_harness.publicacion import leer_informe, publicar
    familia, nombre, _ = ref
    ruta = Path(nombre)
    dato = leer_informe(ruta)
    cambiar(dato)
    dato['sello_informe'] = huella({k: v for k, v in dato.items() if k != 'sello_informe'})
    publicar(ruta, dato)
    return familia, nombre, hashlib.sha256(ruta.read_bytes()).hexdigest()


def test_completa_sin_recibos_no_aprueba_solo_por_tests_ml(tmp_path):
    """065:RF-24 — la campaña es puerta propia; tests_ml no sustituye sus recibos."""
    h = herramienta()
    plan = h.plan_comprobaciones(tmp_path, Path(sys.executable), 'completa', tmp_path/'e')
    campanas = next(p for p in plan if p['id'] == 'campanas')
    r = h.ejecutar_comprobacion(campanas, tmp_path/'e')
    assert r['state'] == 'rechazada' and 'campanas' in ' '.join(r['errors'])
    aprobadas = [{'id': p['id'], 'state': 'aprobada'} for p in plan if p['id'] != 'campanas']
    entrega = h.evaluar_entrega(aprobadas + [r], {p['id'] for p in plan})
    assert not entrega['technical_checks_passed']


def test_recibos_integros_resumen_origen_modelos_y_operaciones_sin_certificar(tmp_path):
    """065:RF-24 — positivo sintético del contrato, sin ejecución ML ni aceptación real."""
    h = herramienta()
    refs = _recibos_campanas(tmp_path)
    r = h.admitir_campanas(refs)
    assert r['state'] == 'aprobada' and r['errors'] == []
    assert len(r['familias']) == 6
    for familia in r['familias']:
        assert familia['revision_captura'] == 'a' * 40
        assert familia['datos']['dataset_hash'] and familia['datos']['custodia']['sha256']
        assert familia['modelos']['candidato']['id'] == 'nuevo'
        assert familia['modelos']['referencia']['artifacts']['peso_sintetico.bin'] == '1' * 64
        assert familia['estados_modelos']['candidato']['registro'] == 'no_consultado'
        assert familia['estados_modelos']['referencia']['artefactos_verificados'] is False
        assert familia['operaciones'] and familia['integridad_antes'] == familia['integridad_despues']
        assert familia['aceptacion_cientifica'] is familia['aceptacion_electrica'] is False
        assert familia['aceptacion_operativa'] is False


@pytest.mark.parametrize('defecto', ['faltante', 'sha', 'alterado', 'incompleto', 'conteo_bool',
                                    'etapa_ausente', 'familia', 'promovido_solo'])
def test_recibos_faltantes_alterados_o_incompletos_bloquean(tmp_path, defecto):
    """065:RF-24 — ni resellar un resumen ni PROMOVIDO sustituyen cobertura real declarada."""
    h = herramienta()
    refs = _recibos_campanas(tmp_path)
    if defecto == 'faltante': refs.pop()
    elif defecto == 'sha': refs[0] = (*refs[0][:2], '0' * 64)
    elif defecto == 'alterado': Path(refs[0][1]).write_text('{}', encoding='utf-8')
    elif defecto == 'familia': refs[0] = ('optimizador', *refs[0][1:])
    elif defecto == 'promovido_solo':
        Path(refs[0][1]).write_text('{"status":"PROMOVIDO"}', encoding='utf-8')
        import hashlib
        refs[0] = (*refs[0][:2], hashlib.sha256(Path(refs[0][1]).read_bytes()).hexdigest())
    else:
        def cambiar(r):
            if defecto == 'incompleto': r['estado'] = 'INCOMPLETA'
            elif defecto == 'conteo_bool': r['fallidos'] = False
            elif defecto == 'etapa_ausente': r['suites'].pop(next(iter(r['suites'])))
        refs[0] = _alterar_recibo(refs[0], cambiar)
    r = h.admitir_campanas(refs)
    assert r['state'] == 'bloqueada' and r['errors']


@pytest.mark.parametrize('modo', ['contract', 'replay'])
def test_recibo_contract_o_replay_es_diagnostico_no_campana_ejecutada(tmp_path, modo):
    """065:RF-24 — conservar diagnóstico no lo convierte en ejecución runtime."""
    r = herramienta().admitir_campanas(_recibos_campanas(tmp_path, modo=modo))
    assert r['state'] == 'bloqueada' and len(r['familias']) == 6
    assert all(f['modo'] == modo for f in r['familias'])
    assert all('runtime' in f['errors'][0] for f in r['familias'])


def test_recibo_no_puede_cambiar_mientras_se_valida(tmp_path, monkeypatch):
    """065:RF-24 — la guarda canónica conserva el descriptor durante la validación."""
    from convertersmartgrid.evaluacion_harness import ejecucion
    refs = _recibos_campanas(tmp_path)
    ruta = Path(refs[0][1])
    antes = ruta.read_bytes()
    validar = ejecucion.validar_integridad
    def mutar(r):
        validar(r)
        if r['configuracion']['familia'] == refs[0][0]:
            ruta.write_text('{}', encoding='utf-8')
    monkeypatch.setattr(ejecucion, 'validar_integridad', mutar)
    r = herramienta().admitir_campanas(refs)
    assert r['state'] == 'bloqueada' and r['errors']
    assert ruta.read_bytes() == antes


@pytest.mark.parametrize('cambiar', [False, True])
def test_cli_materializa_estados_y_revalida_recibos_tras_las_puertas(tmp_path, monkeypatch, cambiar):
    """065:RF-24 — contrato CPU de consolidación; ningún pase simulado certifica entrega real."""
    from contextlib import nullcontext
    from types import SimpleNamespace
    h = herramienta()
    root = tmp_path/'candidato'
    (root/'tests').mkdir(parents=True)
    (root/'frontend').mkdir()
    (root/'frontend/package.json').write_text('{}', encoding='utf-8')
    recibos = tmp_path/'recibos'; recibos.mkdir()
    refs = _recibos_campanas(recibos)
    trace = SimpleNamespace(validar_salida=lambda p, _: p.resolve(), revision=lambda _: 'c' * 40,
                            hash_candidato=lambda _: ('d' * 64, {}))
    runner = SimpleNamespace(_git_local=nullcontext, _entorno=lambda *_: {},
                              _runtime=lambda *_: {'packages': {}})
    herramientas = {'trazabilidad_candidato': trace, 'verificar_candidato': runner,
                    'fijar_entorno': SimpleNamespace(leer_minimos_seguridad=lambda _: {})}
    monkeypatch.setattr(h, '_herramienta', herramientas.__getitem__)
    ejecutar = h.ejecutar_comprobacion
    modificado = []
    def puerta(c, evidencia, env):
        if c['kind'] == 'campanas': return ejecutar(c, evidencia, env)
        if cambiar and not modificado:
            Path(refs[0][1]).write_text('{}', encoding='utf-8')
            modificado.append(True)
        return {'id': c['id'], 'state': 'aprobada', 'counts': {'contrato_sintetico': 1}}
    monkeypatch.setattr(h, 'ejecutar_comprobacion', puerta)
    out = tmp_path/'salida'
    argv = ['--root', str(root), '--output-dir', str(out), '--edicion', 'completa', '--ejecutar']
    for ref in refs: argv += ['--campana', *ref]
    assert h.main(argv) == int(cambiar)
    registros = list(out.glob('*/resultado_entrega.json'))
    assert len(registros) == 1
    r = json.loads(registros[0].read_text(encoding='utf-8'))
    assert r['technical_checks_passed'] is (not cambiar)
    assert r['revision'] == 'c' * 40
    assert r['estados']['familias'][0]['revision_captura'] == 'a' * 40
    assert r['estados']['modelos'] and r['estados']['datos']
    assert r['estados']['pruebas']['ml']['estado'] == 'aprobada'
    assert r['production_ready_core'] is r['project_complete'] is False
    assert r['estados']['aceptacion_cientifica'] is r['estados']['aceptacion_operativa'] is False
    assert r['campanas_antes']['state'] == 'aprobada'
    assert r['campanas_despues']['state'] == ('bloqueada' if cambiar else 'aprobada')


@pytest.mark.parametrize('faltante', [False, True])
def test_backend_enlaza_inventarios_de_datos_por_sha_sin_recopiar_fuentes(tmp_path, faltante):
    """065:RF-24 — el resumen enlaza los recibos de datos de la propia corrida."""
    d = tmp_path/'backend'/'intento'; d.mkdir(parents=True)
    r = {'state': 'regresion_aprobada', 'scope': 'suite_completa', 'data_hash_mode': 'sha256',
         'missing_inputs': [], 'source_hash_before': 'a' * 64, 'source_hash_after': 'a' * 64,
         'returncode': 0, 'errors': [],
         'results': {'counts': {'pass': 1, 'fail': 0, 'error': 0, 'skip': 0, 'xfail': 0}}}
    (d/'registro.json').write_text(json.dumps(r), encoding='utf-8')
    for name in ('data_inputs_before.json', 'data_inputs_after.json'):
        if not faltante or name != 'data_inputs_after.json':
            (d/name).write_text('{"contrato_sintetico":true}', encoding='utf-8')
    c = {'kind': 'backend', 'artifact': str(d.parent)}
    if faltante:
        with pytest.raises(ValueError, match='inventario'):
            herramienta()._validar_resultado(c, tmp_path/'stdout')
    else:
        import hashlib
        datos = herramienta()._validar_resultado(c, tmp_path/'stdout')['artefactos_datos']
        assert len(datos) == 2
        for ref in datos.values():
            assert hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest() == ref['sha256']
