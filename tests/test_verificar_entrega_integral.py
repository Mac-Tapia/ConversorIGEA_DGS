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
    assert {'backend', 'frontend_tests', 'frontend_types', 'frontend_build',
            'python_check', 'python_audit', 'frontend_audit'} <= base
    assert {p['id'] for p in full} == base | {'ml'}
    assert all(isinstance(p['command'], list) and p['command'] for p in full)
    assert '--suite-completa' in next(p['command'] for p in full if p['id']=='backend')
    assert '--hash-datos' in next(p['command'] for p in full if p['id']=='backend')
    with pytest.raises(ValueError):
        h.plan_comprobaciones(tmp_path, Path(sys.executable), 'parcial', tmp_path/'e')


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
