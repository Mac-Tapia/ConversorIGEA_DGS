"""La aceptación consumida pertenece a la invocación actual (065:RF-6, 065:RF-7)."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from convertersmartgrid import batch
from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding
from convertersmartgrid.util import sha256_file
from convertersmartgrid.web import services
from convertersmartgrid.web.workspace import Workspace
from synthetic_export import ExportSpec, load_export


@pytest.mark.parametrize('modo', ['rc3_sin', 'rc0_sin', 'roto', 'hash', 'source', 'feeder', 'ruta',
                                 'project', 'binding_source', 'binding_dgs', 'binding_modificado',
                                 'relectura_invalida', 'actual', 'flujo_fallido'])
def test_informe_actual_o_nada_de_mutacion(tmp_path, monkeypatch, modo):
    """065:RF-6, 065:RF-7 — el proceso real de borde no habilita evidencia histórica/ajena."""
    ds = load_export(ExportSpec(feeders=1, sections_per_feeder=6, loads_per_feeder=3, seed=6536),
                     tmp_path / 'fuente')
    ws = Workspace(id='fresh', root=tmp_path / 'espacio')
    ws.active_run_id = ws.loaded_run_id = 'run-current'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = ds
    ws.active_run = lambda: SimpleNamespace(run_id='run-current', mode='txt', fingerprint='f' * 64)
    man = batch.convert_selection(ds, ds.feeder_ids(), ws.out_dir, include_geography=False, workers=1)
    target = man['feeders'][0]['feeder']
    dgs = ws.out_dir / f'{target}.dgs'
    metadata_path = dgs.with_name(f'{target}_feeder_metadata.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    metadata.update(source_run_id='run-current', source_mode='txt', source_fingerprint='f' * 64)
    metadata_path.write_text(json.dumps(metadata), encoding='utf-8')
    ws.conversions['red'] = {'feeder': target, 'capacitor_reread': {'original': True}}
    anterior = ws.out_dir / f'{target}_powerfactory_acceptance.json'
    anterior.write_text(json.dumps({'import': {'project_path': 'PROYECTO_ANTERIOR'},
                                    'capacitor_reread': {'historico': True}}), encoding='utf-8')
    hash_anterior = sha256_file(anterior)
    estado = copy.deepcopy(ws.conversions)
    logs, ordenes = [], []
    script = tmp_path / 'borde_sin_motor.py'
    script.write_text(
        'import json,os,sys\nfrom pathlib import Path\n'
        'destino=Path(sys.argv[sys.argv.index("--output-json")+1])\n'
        'dato=os.environ["REPORTE_UNITARIO"]\n'
        'if dato != "AUSENTE": destino.write_text(dato,encoding="utf-8")\n'
        'raise SystemExit(int(os.environ["RC_UNITARIO"]))\n', encoding='utf-8')
    monkeypatch.setenv('CSG_TEMP_HOME', str(tmp_path / 'temporales'))
    monkeypatch.setattr(services, '_script', lambda *_: script)
    monkeypatch.setattr(services, '_require_pf', lambda: (tmp_path, Path(sys.executable)))
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'PRUEBA')
    monkeypatch.setattr(services, 'pf_subprocess_env', lambda *_: os.environ.copy())
    monkeypatch.setattr(services, 'powerfactory_status', lambda: {'interpreter_reason': 'proceso de borde sin motor'})

    def ejecutar(cmd, **kwargs):
        ordenes.append(cmd)
        fijado = Path(cmd[cmd.index('--import-dgs') + 1])
        runtime_ok = modo != 'flujo_fallido'
        binding = PowerFactoryProjectBinding(
            project='PROYECTO_ACTUAL' if modo != 'project' else 'PROYECTO_AJENO', folder='PRUEBA',
            source_run_id='run-current' if modo != 'binding_source' else 'run-ajeno',
            source_mode='txt', source_fingerprint='f' * 64,
            feeders=(target,), dgs_sha256={target: sha256_file(fijado) if modo != 'binding_dgs' else 'b' * 64},
            native_inventory_sha256='a' * 64,
            native_reread={'status': 'VERIFICADO_PERSISTENCIA' if runtime_ok else 'CASO_BASE_NO_VERIFICADO'},
        ).as_dict()
        dato = {'feeder': target, 'powerfactory_runtime_pass': runtime_ok,
                'load_flow': {'requested': True, 'return_code': 0, 'ldf_valid': True},
                'import': {'ok': True, 'dgs': str(fijado), 'project_path': 'PROYECTO_ACTUAL',
                           'project_folder': 'PRUEBA'},
                'source_verification': {'status': 'VERIFIED_BEFORE_MUTATION',
                                        'source_run_id': 'run-current', 'source_mode': 'txt',
                                        'source_fingerprint': 'f' * 64, 'dgs_sha256': sha256_file(fijado),
                                        'metadata_file': metadata_path.name, 'feeders': [target]},
                'project_binding': binding, 'capacitor_reread': {'actual': True}}
        if modo == 'hash':
            dato['source_verification']['dgs_sha256'] = 'b' * 64
        if modo == 'source':
            dato['source_verification']['source_run_id'] = 'run-ajeno'
        if modo == 'feeder':
            dato['feeder'] = 'OTRA_RED'
        if modo == 'ruta':
            dato['import']['dgs'] = str(tmp_path / fijado.name)
        if modo == 'relectura_invalida':
            dato['capacitor_reread'] = 'estructura inválida'
        if modo == 'binding_modificado':
            dato['project_binding']['project'] = 'PROYECTO_AJENO'
        rc = 3 if modo == 'rc3_sin' else 2 if modo == 'flujo_fallido' else 0
        texto = 'AUSENTE' if modo.endswith('_sin') else '{roto' if modo == 'roto' else json.dumps(dato)
        kwargs['env'].update(REPORTE_UNITARIO=texto, RC_UNITARIO=str(rc))
        return subprocess.run(cmd, **kwargs).returncode

    ctx = SimpleNamespace(job=SimpleNamespace(id='job-fresh'), log=logs.append, progress=lambda *_: None,
                          check_cancel=lambda: None, run_process=ejecutar)
    resultado = services.powerfactory_flow(ws, ctx, [target])
    valido = modo in {'actual', 'flujo_fallido'}
    assert len(ordenes) == 1
    salida_actual = Path(ordenes[0][ordenes[0].index('--output-json') + 1])
    assert salida_actual != anterior
    assert salida_actual.parent.is_relative_to(ws.out_dir)
    if valido:
        assert ws.pf_projects[target] == 'PROYECTO_ACTUAL'
        assert ws.conversions['red']['capacitor_reread'] == {'actual': True}
        assert 'PROYECTO_ACTUAL' in ws.pf_project_bindings
        assert any(p != anterior and sha256_file(p) == hash_anterior for p in ws.out_dir.rglob('*.json'))
        assert json.loads(anterior.read_text(encoding='utf-8'))['import']['project_path'] == 'PROYECTO_ACTUAL'
        assert resultado['ok'] == int(modo == 'actual')
        if modo == 'actual':
            otra = services.powerfactory_flow(ws, ctx, [target])
            assert otra['invocation_id'] != resultado['invocation_id']
            assert otra['reports'][0]['report'] != resultado['reports'][0]['report']
            assert salida_actual.is_file()  # Repetir el mismo job nunca sustituye evidencia previa.
    else:
        assert ws.pf_projects == {}
        assert ws.pf_project_bindings == {}
        assert ws.conversions == estado
        assert sha256_file(anterior) == hash_anterior
        assert resultado['ok'] == 0 and resultado['failed'] == 1
        assert any('INFORME' in linea for linea in resultado['lines'])
