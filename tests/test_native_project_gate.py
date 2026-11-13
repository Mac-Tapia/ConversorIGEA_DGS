"""Una sola puerta fuente/proyecto para toda acción nativa PowerFactory."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


class _NoSubprocess:
    def __init__(self):
        self.cancel = SimpleNamespace(is_set=lambda: False)

    def run_process(self, *_args, **_kwargs):  # pragma: no cover - debe bloquear antes
        raise AssertionError('se lanzó un subproceso antes de validar el proyecto')

    def log(self, *_args):
        pass

    def progress(self, *_args):
        pass


def _workspace(tmp_path):
    from convertersmartgrid.web.workspace import Workspace

    ws = Workspace(id='gate', root=tmp_path)
    ws.active_run_id = 'run-active'
    ws.loaded_run_id = 'run-active'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = SimpleNamespace(feeder_ids=lambda: ['A1', 'A2'])
    return ws


def _maxima():
    return [{'medidor': 'M1', 'alimentador': 'A1', 'fecha': '2026-04-16 11:00:00',
             'kw': 1000.0, 'kvar': 300.0, 'error': None}]


class _LlegoAlTrabajo(Exception):
    """La acción pasó la puerta del proyecto y llegó a DIgSILENT."""


class _CtxQueAnota(_NoSubprocess):
    def run_process(self, *_args, **_kwargs):
        raise _LlegoAlTrabajo()


@pytest.mark.parametrize('invoke', [
    lambda s, w: s.cargas_plan(w, 'P', ['A1'], None, None),
    lambda s, w: s.ajuste_plan(w, 'P', _maxima(), '', .01),
    lambda s, w: s.obras_bibliotecas(w, _CtxQueAnota(), 'P', ['A1']),
    lambda s, w: s.obras_ejecutar(w, _CtxQueAnota(), 'P', ['A1'], None, '', simular=True),
    lambda s, w: s.estudios_plan(w, 'P', ['A1'], ['flujo'], None),
    lambda s, w: s.transferencia_ejecutar(
        w, _CtxQueAnota(), 'P', ['A1', 'A2'], ['sin'], None),
])
def test_018_rf19_ninguna_accion_nativa_se_detiene_por_el_vinculo(tmp_path, invoke):
    """018:RF-19 — regla del usuario (2026-11-13): se trabaja sobre cualquier proyecto de DIgSILENT, convertido o no por
    el conversor. Antes esta prueba exigía lo contrario («toda acción nativa rechaza el proyecto sin vínculo»); una
    acción puede seguir fallando por otra causa (falta de calibración, de datos…), pero nunca por PROJECT_BINDING_*."""
    from convertersmartgrid.web import services

    try:
        invoke(services, _workspace(tmp_path))
    except _LlegoAlTrabajo:
        return
    except Exception as exc:                                   # noqa: BLE001
        assert 'PROJECT_BINDING' not in str(exc), exc


def test_018_rf19_sin_vinculo_el_contexto_se_arma_con_el_proyecto_y_lo_avisa(tmp_path):
    """018:RF-19 — sin vínculo, el contexto nativo lleva un vínculo de origen «proyecto», firmado, y la causa como aviso
    informativo; nunca «se importó a mano»."""
    from convertersmartgrid.native_action import verify_native_action_context
    from convertersmartgrid.web import services

    feeders = ['A1', 'A2']
    contexto = services.native_action_context(_workspace(tmp_path), 'P', feeders, 'ajuste')
    assert contexto['binding']['origen'] == 'proyecto' and contexto['binding']['project'] == 'P'
    assert contexto['binding']['feeders'] == feeders
    assert [a['code'] for a in contexto['binding_warnings']] == ['PROJECT_BINDING_MISSING']
    assert 'propio proyecto de DIgSILENT' in contexto['binding_warnings'][0]['message']
    assert 'a mano' not in contexto['binding_warnings'][0]['message']
    plan = {'project': 'P', 'feeders': feeders, 'native_action_context': contexto}
    assert verify_native_action_context(plan, 'ajuste')['project'] == 'P'


def test_native_action_context_carries_one_signed_binding(tmp_path):
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding
    from convertersmartgrid.web import services

    ws = _workspace(tmp_path)
    binding = PowerFactoryProjectBinding(
        project='P', folder='ConverterSmartGrid', source_run_id='run-active',
        source_mode='txt', source_fingerprint='f' * 64, feeders=('A1', 'A2'),
        dgs_sha256={'A1': 'a' * 64, 'A2': 'b' * 64}, native_inventory_sha256='n' * 64,
        native_reread={'status': 'VERIFICADO_PERSISTENCIA'}, accepted_at=1.0,
    )
    ws.pf_project_bindings['P'] = binding.as_dict()
    ws.pf_inventory = {'projects': [{
        'name': 'P', 'path': 'P', 'feeders': ['A1', 'A2'],
        'native_inventory_sha256': 'n' * 64,
    }]}

    context = services.native_action_context(ws, 'P', ['A2', 'A1', 'A1'], 'estudios')

    assert context['action'] == 'estudios'
    assert context['feeders'] == ['A1', 'A2']
    assert context['binding']['source_run_id'] == 'run-active'
    assert context['context_sha256']


def test_native_action_context_signs_nonblocking_project_warnings(tmp_path):
    """014:RF-17 — la acción nativa se autoriza con las modificaciones manuales como aviso."""
    from convertersmartgrid.native_action import verify_native_action_context
    from convertersmartgrid.powerfactory_binding import PowerFactoryProjectBinding
    from convertersmartgrid.web import services

    ws = _workspace(tmp_path)
    binding = PowerFactoryProjectBinding(
        project='P', folder='ConverterSmartGrid', source_run_id='run-previous',
        source_mode='txt', source_fingerprint='f' * 64, feeders=('A1',),
        dgs_sha256={'A1': 'a' * 64}, native_inventory_sha256='n' * 64,
        native_reread={'status': 'VERIFICADO_PERSISTENCIA'}, accepted_at=1.0,
    )
    ws.pf_project_bindings['P'] = binding.as_dict()
    ws.pf_inventory = {'projects': [{
        'name': 'P', 'path': 'P', 'feeders': ['A1'],
        'native_inventory_sha256': 'x' * 64,
    }]}

    context = services.native_action_context(ws, 'P', ['A1'], 'estudios')
    verified = verify_native_action_context({
        'project': 'P', 'feeders': ['A1'], 'native_action_context': context,
    }, 'estudios')

    assert [item['code'] for item in verified['binding_warnings']] == [
        'PROJECT_BINDING_SOURCE_RUN_CHANGED', 'PROJECT_BINDING_NATIVE_MODIFIED',
    ]


@pytest.mark.parametrize(('evidence', 'expected'), [
    ({'ok': True}, 'OK'),
    ({'status': 'AVISO_KVAR'}, 'AVISO_KVAR'),
    ({'persistence_corrected': True}, 'AVISO_PERSISTENCIA_CORREGIDA'),
    ({'persistence_warning': True}, 'AVISO_PERSISTENCIA_NO_CORREGIDA'),
    ({'data_error': 'sin periodo'}, 'BLOQUEADO_DATOS'),
    ({'persistence_error': 'no releyó'}, 'BLOQUEADO_PERSISTENCIA'),
    ({'converged': False}, 'NO_CONVERGE'),
    ({'physical_violations': [{'kind': 'voltage'}]}, 'VIOLACION_FISICA'),
    ({'not_applicable': 'sin interruptor'}, 'NO_APLICA'),
])
def test_status_vocabulary_never_returns_generic_fail(evidence, expected):
    from convertersmartgrid.native_action import native_result_status

    status = native_result_status(evidence)
    assert status == expected
    assert status != 'FAIL'


def test_q_warning_is_nonblocking_for_studies():
    from convertersmartgrid.native_action import status_blocks_studies

    assert status_blocks_studies('AVISO_KVAR') is False
    assert status_blocks_studies('AVISO_PERSISTENCIA_CORREGIDA') is False
    assert status_blocks_studies('BLOQUEADO_DATOS') is True


def test_native_tool_rejects_unsigned_plan_before_powerfactory(tmp_path):
    from apoyo import cargar_herramienta

    tool = cargar_herramienta('verificar_pf.py', 'verificar_pf_gate', tools_en_path=True)
    plan = tmp_path / 'plan.json'
    output = tmp_path / 'output.json'
    plan.write_text(json.dumps({'project': 'P', 'feeders': ['A1']}), encoding='utf-8')

    assert tool.main(['--plan', str(plan), '--output-json', str(output)]) == 2
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['status'] == 'BLOQUEADO_DATOS'
    assert 'native_action_context' in report['error']


def test_015_rf70_sin_conversion_vinculada_se_calibra_sin_exigir_el_caso_base(tmp_path):
    """015:RF-70 — un proyecto sin ninguna conversión vinculada no tiene contra qué verificar su «Caso base»: la
    calibración no se detiene por eso y lo dice en sus avisos (regla del usuario, 2026-11-13)."""
    from convertersmartgrid.web import services

    plan = services.ajuste_plan(_workspace(tmp_path), 'P', _maxima(), '', .01)
    avisos = ' '.join(str(a) for a in plan.get('avisos') or [])
    assert '015:RF-70' in avisos
