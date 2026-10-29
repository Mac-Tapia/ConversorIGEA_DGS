"""Contrato final de aceptación universal hasta carga y estudio nativos.

Spec 034: 034:RF-24.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from apoyo import cargar_herramienta


def _module():
    return cargar_herramienta('accept_three_sources.py', 'accept_native_load_sources')


def _binding():
    return {
        'project': 'P', 'source_run_id': 'run-txt', 'source_mode': 'txt',
        'source_fingerprint': 'f' * 64, 'feeders': ['A1'],
        'native_inventory_sha256': 'n' * 64,
        'native_reread': {'status': 'VERIFICADO_PERSISTENCIA'},
    }


def test_evidence_bundle_covers_source_banks_loads_and_native_study():
    mod = _module()
    evidence = mod.build_native_load_evidence(
        source_audit={'status': 'OK', 'counts': {'capacitor_settings': 3}},
        source_audit_sha256='a' * 64,
        conversion_result={'summary': {'ok': 1}},
        powerfactory_reports=[{
            'feeder': 'A1',
            'feeder_metadata': {
                'status': 'assigned', 'written': 42, 'reread_count': 42,
                'reread_verified': True, 'by_feeder': {'A1': 42},
            },
            'capacitor_reread': {
                'status': 'AVISO_PERSISTENCIA_CORREGIDA', 'expected': 3,
                'corrections': [{
                    'node': 'N10', 'before_kvar': 100.0, 'after_kvar': 300.0,
                    'catalog_kvar': 300.0, 'nominal_kv': 10.0,
                }],
                'banks': [{'node': 'N10', 'q_kvar': 300.0}],
            },
            'project_binding': _binding(),
            'effective_reread': {'comldf_executed': True, 'comldf_valid': True},
        }],
        adjustments=[{
            'plan': {
                'feeder': 'A1', 'periodo': {
                    'status': 'CLIENT_PERIOD_MATCH', 'maxima': '2026-04',
                    'clientes': '2026-04',
                },
                'client_evidence': {'fingerprint': 'c' * 64, 'file': 'clientes.xlsx'},
                'fixed_load_evidence': [{
                    'sed': 'SE1', 'p_kw': 100.0, 'q_kvar': 30.0, 'fp': 0.9578,
                    'derivaciones': ['POT', 'Q=Pot*ERI/EA'],
                }],
            },
            'result': {'informe': {
                'feeder': 'A1', 'status': 'AVISO_KVAR', 'cuadrado': True,
                'objetivo': {'kw': 1000.0, 'kvar': 300.0},
                'cabecera': {'kw': 1000.5, 'kvar': 360.0},
                'kvar_no_bloqueante': {
                    'status': 'AVISO_KVAR', 'diferencia_kvar': 60.0, 'bloquea': False,
                },
                'sed': [
                    {'sed': 'SE1', 'origen': 'cliente'},
                    {'sed': 'SE2', 'origen': 'kva'},
                ],
                'relectura_cargas_nativas': {
                    'status': 'VERIFICADO_PERSISTENCIA',
                    'despues': [{'sed': 'SE1', 'p_kw': 100.0, 'q_kvar': 30.0,
                                 'fp': 0.9578, 'outserv': 0, 'i_scale': 0}],
                },
            }},
        }],
        studies=[{
            'project': 'P', 'medidas': [{
                'alimentador': 'A1', 'converge': True, 'vm_min': 0.97,
                'cargabilidad_max': 72.0,
            }],
            'violaciones': [],
        }],
    )

    assert evidence['schema_version'] == 'igea-dgs-three-source-native-load-v1'
    assert evidence['source_audit']['sha256'] == 'a' * 64
    assert evidence['capacitors']['expected'] == 3
    assert evidence['capacitors']['corrections'][0]['node'] == 'N10'
    assert evidence['metadata_assignment']['written'] == 42
    assert evidence['project_bindings'][0]['source_run_id'] == 'run-txt'
    assert evidence['client_periods'][0]['periodo']['maxima'] == '2026-04'
    assert evidence['loads']['fixed_seds'] == 1
    assert evidence['loads']['scaled_seds'] == 1
    assert evidence['loads']['native_reread'][0]['status'] == 'VERIFICADO_PERSISTENCIA'
    assert evidence['head_balance'][0]['native']['kw'] == 1000.5
    assert evidence['head_balance'][0]['kvar_difference']['bloquea'] is False
    assert evidence['load_flow']['all_valid'] is True
    assert evidence['physical_violations'] == []
    assert evidence['status'] == 'AVISO_KVAR'


def test_dgs_only_summary_has_explicit_not_run_native_contract(tmp_path):
    mod = _module()
    summary = mod.run_three_sources(mod.AcceptanceConfig(audit_dir=tmp_path / 'audit'))

    assert summary['schema_version'] == 'igea-dgs-three-source-native-load-v1'
    assert all(row['native_load_contract']['status'] == 'NOT_RUN'
               for row in summary['sources'])


def test_runner_reuses_public_adjustment_and_study_services(tmp_path, monkeypatch):
    mod = _module()
    header = tmp_path / 'cabecera.xlsx'
    header.write_bytes(b'fixture')
    plan_path = tmp_path / 'ajuste.json'
    calls = []
    workspace = SimpleNamespace(
        pf_projects={'A1': 'P'}, cargas_planes={},
    )

    monkeypatch.setattr(mod.services, 'demanda_asignar',
                        lambda *_a: calls.append('demanda_asignar'))
    monkeypatch.setattr(mod.services, 'demanda_cabecera', lambda *_a: {
        'resultados': [{'alimentador': 'A1', 'medidor': 'M1', 'kw': 1000.0,
                        'kvar': 300.0, 'fecha': '2026-04-16 11:00:00'}],
    })

    def adjustment_plan(*_args):
        calls.append('ajuste_plan')
        plan_path.write_text(json.dumps({'feeder': 'A1'}), encoding='utf-8')
        workspace.cargas_planes['adjust'] = {'path': str(plan_path)}
        return {'token': 'adjust'}

    monkeypatch.setattr(mod.services, 'ajuste_plan', adjustment_plan)
    monkeypatch.setattr(mod.services, 'ajuste_ejecutar', lambda *_a, **_k: (
        calls.append('ajuste_ejecutar') or {'project': 'P', 'informes': [
            {'feeder': 'A1', 'variacion': 'Ajuste_A1', 'cuadrado': True},
        ]}
    ))
    monkeypatch.setattr(mod.services, 'estudios_plan', lambda *_a: (
        calls.append('estudios_plan') or {'token': 'study'}
    ))
    monkeypatch.setattr(mod.services, 'estudios_ejecutar', lambda *_a: (
        calls.append('estudios_ejecutar') or {'project': 'P', 'medidas': [],
                                              'violaciones': []}
    ))

    adjustments, studies = mod._run_native_load_contract(
        workspace, object(),
        mod.AcceptanceConfig(
            audit_dir=tmp_path / 'audit', cabecera=header,
            meters_by_feeder=(('A1', 'M1'),),
        ),
        ['A1'],
    )

    assert calls == [
        'demanda_asignar', 'ajuste_plan', 'ajuste_ejecutar',
        'estudios_plan', 'estudios_ejecutar',
    ]
    assert adjustments[0]['plan']['feeder'] == 'A1'
    assert studies[0]['project'] == 'P'


def test_verified_summary_rejects_blocking_kvar():
    mod = _module()
    rows = []
    for mode in ('txt', 'mdb', 'vnr'):
        contract = mod.build_native_load_evidence()
        contract['head_balance'] = [{
            'kvar_difference': {'status': 'AVISO_KVAR', 'bloquea': True},
        }]
        rows.append({
            'mode': mode, 'status': 'DGS_READY', 'source_run_id': mode,
            'input_files': [], 'dgs_files': [], 'native_load_contract': contract,
        })

    import pytest
    with pytest.raises(ValueError, match='diferencia de kVAR'):
        mod.validate_summary({'sources': rows})
