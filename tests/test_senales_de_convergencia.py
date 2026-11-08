"""Toda señal de convergencia dice lo que devolvió DIgSILENT (spec 078, RF-1 a RF-28).

Los dos informes son los de los hallazgos, reconstruidos sin datos reales ni nombres de empresa: un proyecto
importado cuyo flujo no calcula (``convergence_pass: False`` con «OK» y «VERIFICADO» en la web) y uno bueno cuyo
``load_flow_loop`` es null (``NOT_CONVERGED`` con ``return_code`` 0).
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from apoyo import TOOLS, cargar_herramienta
from convertersmartgrid import batch
from convertersmartgrid.powerfactory_binding import (
    PowerFactoryProjectBinding, caso_base_verificado, fusionar_caso_base,
)
from convertersmartgrid.powerfactory_metadata import classify_convergence, estado_caso_base, estado_flujo
from convertersmartgrid.util import sha256_file
from convertersmartgrid.web import services
from convertersmartgrid.web.workspace import Workspace
from synthetic_export import ExportSpec, load_export

tool = cargar_herramienta('powerfactory_acceptance.py', 'pfa_078')
RAIZ = TOOLS.parent

_COMUN = {
    'feeder': 'AL101', 'powerfactory_runtime_pass': True, 'load_flow_loop': None, 'errors': [],
    'source_verification': {'status': 'VERIFIED_BEFORE_MUTATION'},
    'effective_reread': {'feeder_metadata': True, 'feeder_objects': 3, 'comldf_executed': True},
    'rollback': {'status': 'NOT_REQUIRED_ISOLATED_PROJECT', 'attempted': False},
}
NO_CALCULA = {
    **copy.deepcopy(_COMUN),
    'convergence_pass': False,
    'warnings': ['Load flow did not converge after correction intents'],
    'load_flow': {
        'requested': True, 'pass': False, 'return_code': 1, 'ldf_valid': False,
        'return_meaning': 'divergence of inner loops (often voltage stability / excess load)',
        'ajuste_de_cargas': {'pass': False, 'factor': None, 'cargas': 8,
                             'intentos': [{'factor': .9, 'converge': False}, {'factor': .1, 'converge': False}]},
    },
}
NO_CALCULA['effective_reread']['comldf_valid'] = False
BUENO = {
    **copy.deepcopy(_COMUN),
    'convergence_pass': True,
    'warnings': [],
    'load_flow': {'requested': True, 'pass': True, 'return_code': 0, 'ldf_valid': True},
}
BUENO['effective_reread']['comldf_valid'] = True


# ------------------------------------------------------------------ la lectura única

@pytest.mark.parametrize('ultimo, estado', [
    ({'return_code': 0, 'ldf_valid': True}, 'converge'),
    ({'return_code': None, 'ldf_valid': True}, 'converge'),
    ({'return_code': 1, 'ldf_valid': False}, 'no_converge'),
    ({'return_code': 2, 'ldf_valid': None}, 'no_converge'),
    ({'return_code': 0, 'ldf_valid': False}, 'no_converge'),
    ({'return_code': None, 'ldf_valid': None}, 'sin_dato'),
    ({'return_code': 0, 'ldf_valid': None}, 'sin_dato'),
    ({}, 'sin_dato'),
])
def test_lectura_de_los_tres_estados(ultimo, estado):
    """078:RF-1, 078:RF-2, 078:RF-3, 078:RF-4 — el código y la validez de DIgSILENT, y un dato ausente no es nada más que eso."""
    assert estado_flujo({'load_flow': {'requested': True, **ultimo}})['estado'] == estado
    assert estado_flujo({'load_flow': {'requested': True}, 'load_flow_loop': {'final_load_flow': ultimo}})['estado'] == estado


def test_lectura_de_los_dos_informes():
    """078:RF-1 — el mismo flujo, se escriba en un bucle o no."""
    assert estado_flujo(NO_CALCULA)['estado'] == 'no_converge'
    assert estado_flujo(BUENO)['estado'] == 'converge'
    assert estado_flujo({})['estado'] == 'sin_dato' and estado_flujo({})['solicitado'] is False


def test_lectura_con_la_demanda_reducida():
    """078:RF-5 — lo que cuenta es el último flujo, el de después de bajar la demanda, con su factor."""
    final = {'pass': True, 'return_code': 0, 'ldf_valid': True}
    r = {'load_flow': {'requested': True, 'pass': True, 'return_code': 1, 'ldf_valid': False,
                       'ajuste_de_cargas': {'pass': True, 'factor': .7, 'escenario': 'E', 'final_load_flow': final,
                                            'intentos': [{'factor': .7, 'converge': True}]}}}
    flujo = estado_flujo(r)
    assert flujo['estado'] == 'converge' and flujo['factor_demanda'] == .7
    assert '70.0 %' in flujo['motivo']


def test_lectura_dice_que_fallo():
    """078:RF-6 — código, significado, errores y diagnóstico."""
    r = copy.deepcopy(NO_CALCULA)
    r['load_flow']['errors'] = ['Load flow ComLdf.Execute returned 1']
    r['load_flow']['diagnostico'] = {'issues': ['Loads without terminal connection: [C1]']}
    flujo = estado_flujo(r)
    assert flujo['return_code'] == 1 and 'divergence of inner loops' in flujo['significado']
    assert 'return_code 1' in flujo['motivo'] and 'divergence of inner loops' in flujo['motivo']
    assert 'Load flow ComLdf.Execute returned 1' in flujo['fallos']
    assert 'Loads without terminal connection: [C1]' in flujo['fallos']
    sin = estado_flujo({'load_flow': {'requested': True, 'pass': False, 'return_code': None, 'ldf_valid': None,
                                      'errors': ['ComLdf not found/created in active study case']}})
    assert sin['estado'] == 'sin_dato' and 'ComLdf not found/created in active study case' in sin['fallos']
    assert 'no hay resultado' in sin['motivo']
    assert 'no se ejecutó' in estado_flujo({'load_flow': {'requested': False}})['motivo']


def test_lectura_con_su_historial():
    """078:RF-7 — los intentos de reducir la demanda, los del bucle y el historial que ya traiga el informe."""
    assert [h['factor'] for h in estado_flujo(NO_CALCULA)['historial']] == [.9, .1]
    bucle = {'load_flow': {'requested': True}, 'load_flow_loop': {
        'pass': False, 'final_load_flow': {'return_code': 1, 'ldf_valid': False},
        'attempts': [{'attempt': 0, 'phase': 'initial', 'load_flow': {'pass': False, 'return_code': 1}},
                     {'attempt': 1, 'intent': 'relaxed_ldf', 'load_flow': {'pass': False, 'return_code': 2}}]}}
    pasos = estado_flujo(bucle)['historial']
    assert [(h['accion'], h['return_code']) for h in pasos] == [('initial', 1), ('relaxed_ldf', 2)]
    propio = [{'flujo': 1, 'converge': False, 'motivo': 'ComLdf rc=1'}]
    assert estado_flujo({**NO_CALCULA, 'historial': propio})['historial'] == propio
    assert estado_flujo(BUENO)['historial'] == []


@pytest.mark.parametrize('informe, esperado', [(BUENO, True), (NO_CALCULA, False),
                                               ({'load_flow': {'requested': False}}, None)])
def test_lectura_en_convergence_pass(informe, esperado):
    """078:RF-8 — ``convergence_pass`` deja de decir False por un dato ausente."""
    r = copy.deepcopy(informe)
    tool.attach_source_evidence(r, {'status': 'VERIFIED_BEFORE_MUTATION'})
    assert r['convergence_pass'] is esperado and r['flujo']['estado'] == estado_flujo(r)['estado']


# ------------------------------------------------------------------ clasificación

def test_clasifica_los_dos_informes():
    """078:RF-10, 078:RF-11 — con return_code 0 no es NOT_CONVERGED; con el flujo que no calcula, sí."""
    assert classify_convergence(BUENO) == 'CONVERGED_ORIGINAL'
    assert classify_convergence(NO_CALCULA) == 'NOT_CONVERGED'


def test_clasifica_el_flujo_sin_dato():
    """078:RF-9 — un flujo que no se ejecutó no es «no convergió» ni «convergió»."""
    r = copy.deepcopy(BUENO)
    r['load_flow'] = {'requested': False, 'pass': None, 'return_code': None, 'ldf_valid': None}
    assert classify_convergence(r) == 'SIN_DATO'
    r['load_flow'] = {'requested': True, 'pass': False, 'return_code': None, 'ldf_valid': None}
    assert classify_convergence(r) == 'SIN_DATO'
    assert classify_convergence({'source_verification': {'status': 'NOT_REQUESTED'}}) == 'REJECTED_STALE_EVIDENCE'


def test_clasifica_la_demanda_reducida_para_revisar():
    """078:RF-12 — converge con la demanda cambiada: no es el original."""
    r = copy.deepcopy(BUENO)
    r['load_flow']['ajuste_de_cargas'] = {'pass': True, 'factor': .7, 'final_load_flow':
                                          {'return_code': 0, 'ldf_valid': True}}
    assert classify_convergence(r) == 'NEEDS_OPERATOR_REVIEW'


# ------------------------------------------------------------------ «Caso base»

_SIN_FALLOS = {'sin_capacidad': [], 'capacidad_distinta': [], 'a_corregir': [], 'no_en_archivo': []}
_FISICO = {'gps': {}, 'connectivity': {'valid_lines': 3, 'total_lines': 3}, 'connectivity_pass': True,
           'geographic_diagram_pass': True}


def _resumen(informe):
    return tool.resumen_caso_base({**_FISICO, **copy.deepcopy(informe)}, _SIN_FALLOS, [], [])


def test_caso_base_verificado_solo_con_flujo_convergido():
    """078:RF-13 — lo físico bien y el flujo convergido; lo físico mal sigue siendo no verificado."""
    assert _resumen(BUENO)['status'] == 'VERIFICADO'
    malo = {**copy.deepcopy(BUENO), 'connectivity_pass': False}
    assert _resumen(malo)['status'] == 'NO_VERIFICADO'
    assert _resumen({**NO_CALCULA, 'connectivity_pass': False})['status'] == 'NO_VERIFICADO'
    assert estado_caso_base(True, 'converge') == 'VERIFICADO'


def test_caso_base_no_converge_dice_que_fallo():
    """078:RF-14, 015:RF-40 — el informe del hallazgo: ni VERIFICADO ni escondido en una columna."""
    r = _resumen(NO_CALCULA)
    assert r['status'] == 'NO_CONVERGE'
    assert r['comprobaciones']['flujo']['pass'] is False
    assert any('return_code 1' in f for f in r['comprobaciones']['flujo']['fallos'])
    assert r['flujo']['estado'] == 'no_converge' and len(r['flujo']['historial']) == 2
    assert any('no converge' in a and 'return_code 1' in a for a in r['avisos'])
    assert any('RF-40' in a for a in r['avisos'])


def test_caso_base_sin_dato_lo_avisa():
    """078:RF-15, 015:RF-39 — sin flujo no hay comprobación de flujo, y se dice."""
    r = _resumen({'load_flow': {'requested': False}})
    assert r['status'] == 'SIN_DATO_DE_FLUJO' and 'flujo' not in r['comprobaciones']
    assert any('Sin dato de convergencia' in a for a in r['avisos'])
    pedido = _resumen({'load_flow': {'requested': True, 'pass': False, 'return_code': None, 'ldf_valid': None,
                                     'errors': ['ComLdf not found/created in active study case']}})
    assert pedido['status'] == 'SIN_DATO_DE_FLUJO' and pedido['comprobaciones']['flujo']['pass'] is False


def test_caso_base_actualizar_quita_el_aviso_de_sin_dato():
    """078:RF-14, 078:RF-15 — con el flujo de la importación, el aviso de que no lo había ya no vale."""
    r = _resumen({'load_flow': {'requested': False}})
    tool.actualizar_flujo_caso_base(r, NO_CALCULA)
    assert r['status'] == 'NO_CONVERGE'
    assert not any('Sin dato de convergencia' in a for a in r['avisos'])
    tool.actualizar_flujo_caso_base(r, BUENO)
    assert r['status'] == 'VERIFICADO' and not any('no converge' in a for a in r['avisos'] if 'return_code' in a)


def _vinculo(estado, *, status='CASO_BASE_NO_VERIFICADO', huella='f' * 64):
    return PowerFactoryProjectBinding(
        project='P', folder='F', source_run_id='r', source_mode='txt', source_fingerprint=huella, feeders=('AL101',),
        dgs_sha256={'AL101': 'd' * 64}, native_inventory_sha256='n' * 64,
        native_reread={'status': status, 'caso_base': {'AL101': estado}})


_IMPORTADO_MAL = {'status': 'NO_CONVERGE', 'comprobaciones': {'gps_barras': True, 'flujo': False}, 'fallos': ['flujo'],
                  'flujo': {'estado': 'no_converge', 'motivo': 'DIgSILENT devolvió return_code 1', 'return_code': 1}}
_IMPORTADO_BIEN = {'status': 'VERIFICADO', 'comprobaciones': {'gps_barras': True, 'flujo': True}, 'fallos': []}
_REVERIFICADO = {'status': 'SIN_DATO_DE_FLUJO', 'comprobaciones': {'gps_barras': True}, 'fallos': ['flujo sin dato']}


def test_caso_base_reverificar_conserva_el_flujo_registrado():
    """078:RF-16 — la cuarta señal: volver a verificar sin flujo no borra que no convergió."""
    junto = fusionar_caso_base(_vinculo(_IMPORTADO_MAL).as_dict(), _vinculo(_REVERIFICADO))
    estado = junto.native_reread['caso_base']['AL101']
    assert estado['status'] == 'NO_CONVERGE' and estado['comprobaciones']['flujo'] is False
    assert estado['fallos'] == ['flujo'] and estado['flujo']['arrastrado'] is True
    assert estado['flujo']['return_code'] == 1


def test_caso_base_reverificar_con_flujo_bueno_queda_verificado():
    """078:RF-13, 078:RF-16 — si convergió al importar, volver a verificar no le quita el estado."""
    junto = fusionar_caso_base(_vinculo(_IMPORTADO_BIEN, status='VERIFICADO_PERSISTENCIA').as_dict(), _vinculo(_REVERIFICADO))
    estado = junto.native_reread['caso_base']['AL101']
    assert estado['status'] == 'VERIFICADO' and estado['fallos'] == []
    assert junto.native_reread['status'] == 'VERIFICADO_PERSISTENCIA'


def test_caso_base_reverificar_arregla_lo_de_antes_de_la_spec():
    """078:RF-16 — un vínculo viejo con VERIFICADO y flujo ✗ también dice que no converge."""
    viejo = {'status': 'VERIFICADO', 'comprobaciones': {'gps_barras': True, 'flujo': False}, 'fallos': ['flujo']}
    estado = fusionar_caso_base(_vinculo(viejo).as_dict(), _vinculo(_REVERIFICADO)).native_reread['caso_base']['AL101']
    assert estado['status'] == 'NO_CONVERGE' and 'registrado' in estado['flujo']['motivo']


def test_caso_base_otra_fuente_no_arrastra_y_lo_fisico_manda():
    """078:RF-16, 015:RF-14 — otra fuente es otro modelo; y un fallo físico no se vuelve NO_CONVERGE."""
    otra = fusionar_caso_base(_vinculo(_IMPORTADO_MAL, huella='a' * 64).as_dict(), _vinculo(_REVERIFICADO))
    assert otra.native_reread['caso_base']['AL101']['status'] == 'SIN_DATO_DE_FLUJO'
    fisico = {'status': 'NO_VERIFICADO', 'comprobaciones': {'gps_barras': False}, 'fallos': ['gps_barras']}
    estado = fusionar_caso_base(_vinculo(_IMPORTADO_MAL).as_dict(), _vinculo(fisico)).native_reread['caso_base']['AL101']
    assert estado['status'] == 'NO_VERIFICADO' and estado['fallos'] == ['flujo', 'gps_barras']


@pytest.mark.parametrize('estado, bloquea', [('VERIFICADO', False), ('NO_CONVERGE', False),
                                             ('SIN_DATO_DE_FLUJO', False), ('NO_VERIFICADO', True)])
def test_caso_base_calibra_salvo_lo_fisico(estado, bloquea):
    """078:RF-17, 015:RF-13, 015:RF-40 — el flujo sigue sin bloquear; lo físico, sí."""
    ws = SimpleNamespace(pf_project_bindings={'P': _vinculo({'status': estado, 'fallos': ['x']}).as_dict()})
    assert bool(caso_base_verificado(ws, 'P', ['AL101'])) is bloquea


def _binding_de(report_json):
    return PowerFactoryProjectBinding.from_dict(report_json)


def test_caso_base_el_gemelo_solo_con_verificado(tmp_path, monkeypatch):
    """078:RF-16, 078:RF-18 — la web devuelve el estado fusionado, y sin flujo convergido no hay episodio «converged»."""
    guion = tmp_path / 'aceptacion_falsa.py'
    guion.write_text(
        'import json,sys\nfrom pathlib import Path\n'
        'Path(sys.argv[sys.argv.index("--output-json")+1]).write_text(sys.argv[sys.argv.index("--informe")+1],encoding="utf-8")\n',
        encoding='utf-8')
    capturas = []
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, Path(sys.executable)))
    monkeypatch.setattr(services, '_script', lambda *_: guion)
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda *_: os.environ.copy())
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'F')
    monkeypatch.setattr(services, 'alimentadores_pedidos', lambda _ws, f: list(f))
    monkeypatch.setattr(services, 'usar_ejecucion_del_vinculo', lambda *_a: None)
    monkeypatch.setattr(services, 'comprobar_dgs_vinculados', lambda *_a: None)
    monkeypatch.setattr(services, '_gemelo', lambda *a, **k: capturas.append(k))
    monkeypatch.setattr(services, 'dgs_jobs', lambda ws, fs: ([(f, ws.out_dir / f'{f}.dgs', ws.out_dir / f'{f}.json') for f in fs], []))
    monkeypatch.setattr(services, 'check_powerfactory_source_run', lambda ws, fs, **_k: {
        'source_run_id': 'r', 'source_mode': 'txt', 'source_fingerprint': 'f' * 64, 'targets': []})
    ws = Workspace(id='v', root=tmp_path / 'espacio')
    ws.out_dir.mkdir(parents=True, exist_ok=True)
    ws.pf_project_bindings['P'] = _vinculo(_IMPORTADO_MAL).as_dict()
    informe = {'caso_base': {'status': 'SIN_DATO_DE_FLUJO', 'comprobaciones': {'gps_barras': {'pass': True, 'fallos': []}},
                             'avisos': [tool.AVISO_SIN_FLUJO]},
               'project_binding': _vinculo(_REVERIFICADO).as_dict()}

    def ejecutar(cmd, **kw):
        return subprocess.run([*cmd, '--informe', json.dumps(informe)], **kw).returncode

    ctx = SimpleNamespace(job=SimpleNamespace(id='j'), log=lambda *_: None, progress=lambda *_: None,
                          check_cancel=lambda: None, run_process=ejecutar)
    monkeypatch.setattr('convertersmartgrid.powerfactory_binding.require_project_binding',
                        lambda ws_, p, f: _binding_de(ws_.pf_project_bindings[p]))
    res = services.pf_verificar_base(ws, ctx, 'P', ['AL101'])['feeders'][0]
    assert res['status'] == 'NO_CONVERGE' and capturas == []
    assert res['comprobaciones']['flujo']['pass'] is False
    assert any('return_code 1' in str(f) for f in res['comprobaciones']['flujo']['fallos'])
    assert tool.AVISO_SIN_FLUJO not in res['avisos'] and any('registrado' in a for a in res['avisos'])
    assert res['flujo']['estado'] == 'no_converge'
    assert ws.pf_project_bindings['P']['native_reread']['caso_base']['AL101']['status'] == 'NO_CONVERGE'

    ws.pf_project_bindings['P'] = _vinculo(_IMPORTADO_BIEN, status='VERIFICADO_PERSISTENCIA').as_dict()
    bien = services.pf_verificar_base(ws, ctx, 'P', ['AL101'])['feeders'][0]
    assert bien['status'] == 'VERIFICADO' and len(capturas) == 1


# ------------------------------------------------------------------ importar desde la web

def _importar(tmp_path, monkeypatch, flujo, rc=0):
    """Una importación por la web con el informe que dejaría el guion, sin DIgSILENT."""
    ds = load_export(ExportSpec(feeders=1, sections_per_feeder=6, loads_per_feeder=3, seed=7801), tmp_path / 'fuente')
    ws = Workspace(id='senales', root=tmp_path / 'espacio')
    ws.active_run_id = ws.loaded_run_id = 'run'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = ds
    ws.active_run = lambda: SimpleNamespace(run_id='run', mode='txt', fingerprint='f' * 64)
    man = batch.convert_selection(ds, ds.feeder_ids(), ws.out_dir, include_geography=False, workers=1)
    target = man['feeders'][0]['feeder']
    meta = ws.out_dir / f'{target}_feeder_metadata.json'
    datos = json.loads(meta.read_text(encoding='utf-8'))
    datos.update(source_run_id='run', source_mode='txt', source_fingerprint='f' * 64)
    meta.write_text(json.dumps(datos), encoding='utf-8')
    guion = tmp_path / 'borde.py'
    guion.write_text('import json,os,sys\nfrom pathlib import Path\n'
                     'Path(sys.argv[sys.argv.index("--output-json")+1]).write_text(os.environ["INFORME"],encoding="utf-8")\n'
                     'raise SystemExit(int(os.environ["RC"]))\n', encoding='utf-8')
    monkeypatch.setenv('CSG_TEMP_HOME', str(tmp_path / 'temporales'))
    monkeypatch.setattr(services, '_script', lambda *_: guion)
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, Path(sys.executable)))
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'F')
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda *_: os.environ.copy())
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'sin motor'})
    logs = []

    def ejecutar(cmd, **kw):
        fijado = Path(cmd[cmd.index('--import-dgs') + 1])
        binding = PowerFactoryProjectBinding(
            project='P', folder='F', source_run_id='run', source_mode='txt', source_fingerprint='f' * 64,
            feeders=(target,), dgs_sha256={target: sha256_file(fijado)}, native_inventory_sha256='a' * 64,
            native_reread={'status': 'x'}).as_dict()
        informe = {**copy.deepcopy(flujo), 'feeder': target, 'powerfactory_runtime_pass': rc == 0,
                   'import': {'ok': True, 'dgs': str(fijado), 'project_path': 'P', 'project_folder': 'F'},
                   'source_verification': {'status': 'VERIFIED_BEFORE_MUTATION', 'source_run_id': 'run', 'source_mode': 'txt',
                                           'source_fingerprint': 'f' * 64, 'dgs_sha256': sha256_file(fijado),
                                           'metadata_file': meta.name, 'feeders': [target]},
                   'project_binding': binding}
        kw['env'].update(INFORME=json.dumps(informe), RC=str(rc))
        return subprocess.run(cmd, **kw).returncode

    ctx = SimpleNamespace(job=SimpleNamespace(id='j'), log=logs.append, progress=lambda *_: None,
                          check_cancel=lambda: None, run_process=ejecutar)
    return services.powerfactory_flow(ws, ctx, [target]), ws, target, logs


def test_importacion_buena_dice_ok(tmp_path, monkeypatch):
    """078:RF-19 — rc 0 y flujo convergido: OK, con lo que lo prueba."""
    r, _ws, target, _logs = _importar(tmp_path, monkeypatch, {'load_flow': BUENO['load_flow']})
    assert (r['ok'], r['failed'], r['sin_aceptar']) == (1, 0, 0)
    assert r['lines'][0].startswith(f'OK {target}') and 'return_code 0' in r['lines'][0]
    assert r['reports'][0]['flujo']['estado'] == 'converge'


def test_importacion_que_no_calcula_no_dice_ok(tmp_path, monkeypatch):
    """078:RF-20, 078:RF-22, 078:RF-23, 078:RF-24 — el hallazgo: importado, sin aceptar, con la causa; el proyecto queda."""
    r, ws, target, logs = _importar(tmp_path, monkeypatch, {'load_flow': NO_CALCULA['load_flow'],
                                                            'convergence_pass': False})
    assert (r['ok'], r['failed'], r['sin_aceptar']) == (0, 0, 1)
    linea = r['lines'][0]
    assert linea.startswith(f'IMPORTADO_SIN_CONVERGENCIA {target}') and 'return_code 1' in linea
    assert not any(x.startswith('OK') for x in r['lines'])
    assert ws.pf_projects[target] == 'P' and 'P' in ws.pf_project_bindings
    assert any('factor' in x or '90.0 %' in x for x in logs if 'intento' in x)


def test_importacion_sin_dato_no_dice_ok(tmp_path, monkeypatch):
    """078:RF-21, 078:RF-22 — sin resultado de DIgSILENT no se da por aceptado ni por no convergido."""
    r, _ws, target, _logs = _importar(tmp_path, monkeypatch, {'load_flow': {'requested': True, 'pass': False}})
    assert (r['ok'], r['failed'], r['sin_aceptar']) == (0, 0, 1)
    assert r['lines'][0].startswith(f'IMPORTADO_SIN_DATO_DE_FLUJO {target}')


def test_importacion_con_la_demanda_reducida_lo_dice(tmp_path, monkeypatch):
    """078:RF-5, 078:RF-19 — converge y se acepta como hasta ahora, con su factor a la vista (015:RF-38)."""
    lf = {**NO_CALCULA['load_flow'], 'pass': True,
          'ajuste_de_cargas': {'pass': True, 'factor': .7, 'final_load_flow': {'return_code': 0, 'ldf_valid': True}}}
    r, _ws, _t, _logs = _importar(tmp_path, monkeypatch, {'load_flow': lf})
    assert r['ok'] == 1 and '70.0 %' in r['lines'][0]


def test_importacion_que_falla_sigue_igual(tmp_path, monkeypatch):
    """078:RF-19 — un error de ejecución sigue siendo un fallo, aunque el flujo haya convergido."""
    r, _ws, target, _logs = _importar(tmp_path, monkeypatch, {'load_flow': BUENO['load_flow']}, rc=2)
    assert (r['ok'], r['failed'], r['sin_aceptar']) == (0, 1, 0)
    assert r['lines'][0].startswith(f'BLOQUEADO_PERSISTENCIA {target}')


# ------------------------------------------------------------------ interfaz e informe

def test_interfaz_dice_cada_estado():
    """078:RF-25, 078:RF-26 — cada estado con su rótulo y su motivo; el vínculo viejo no sale «Verificado».

    Solo vigila el código fuente: verlo en el navegador es la T7."""
    fuente = (RAIZ / 'frontend/src/features/powerfactory/CargasTab.tsx').read_text(encoding='utf-8')
    for texto in ("'NO_CONVERGE'", "'SIN_DATO_DE_FLUJO'", 'No converge', 'Sin dato de flujo', "comprobaciones?.flujo === false",
                  'e.flujo?.motivo'):
        assert texto in fuente, texto
    tipos = (RAIZ / 'frontend/src/api/types.ts').read_text(encoding='utf-8')
    assert tipos.count("'NO_CONVERGE' | 'SIN_DATO_DE_FLUJO'") >= 2


def test_interfaz_cuenta_los_sin_aceptar():
    """078:RF-27 — el resumen de la importación los nombra."""
    assert 'r.sin_aceptar' in (RAIZ / 'frontend/src/app/App.tsx').read_text(encoding='utf-8')


def test_informe_de_texto_con_la_lectura(tmp_path):
    """078:RF-28 — el .txt dice lo mismo que el JSON, con el historial."""
    r = {**copy.deepcopy(NO_CALCULA), 'gps': {'valid': 0, 'total': 0, 'coverage_pct': 0.0},
         'connectivity': {'valid_lines': 0, 'total_lines': 0}, 'diagram': {'object_name': None, 'render_evidence': None}}
    tool.attach_source_evidence(r, {'status': 'VERIFIED_BEFORE_MUTATION'})
    tool._write_reports(r, tmp_path / 'a.json', tmp_path / 'a.txt')
    texto = (tmp_path / 'a.txt').read_text(encoding='utf-8')
    assert 'no_converge' in texto and 'return_code 1' in texto and 'demanda al 90.0 %' in texto
    assert 'Convergence PASS:          False' in texto
    assert json.loads((tmp_path / 'a.json').read_text(encoding='utf-8'))['convergence_classification'] == 'NOT_CONVERGED'
