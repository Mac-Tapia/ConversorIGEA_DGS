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
    from igea_dgs.web.workspace import Workspace

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


@pytest.mark.parametrize('invoke', [
    lambda s, w: s.cargas_plan(w, 'P', ['A1'], None, None),
    lambda s, w: s.ajuste_plan(w, 'P', _maxima(), '', .01),
    lambda s, w: s.pf_verificar(w, _NoSubprocess(), 'P', ['A1']),
    lambda s, w: s.obras_bibliotecas(w, _NoSubprocess(), 'P', ['A1']),
    lambda s, w: s.obras_ejecutar(w, _NoSubprocess(), 'P', ['A1'], None, '', simular=True),
    lambda s, w: s.estudios_plan(w, 'P', ['A1'], ['flujo'], None),
    lambda s, w: s.transferencia_ejecutar(
        w, _NoSubprocess(), 'P', ['A1', 'A2'], ['sin'], None),
])
def test_every_native_action_rejects_unbound_project_before_work(tmp_path, invoke):
    from igea_dgs.web import services

    with pytest.raises(services.UserError, match='PROJECT_BINDING_MISSING'):
        invoke(services, _workspace(tmp_path))


def test_native_action_context_carries_one_signed_binding(tmp_path):
    from igea_dgs.powerfactory_binding import PowerFactoryProjectBinding
    from igea_dgs.web import services

    ws = _workspace(tmp_path)
    binding = PowerFactoryProjectBinding(
        project='P', folder='Conversor IGEA-DGS', source_run_id='run-active',
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
    from igea_dgs.native_action import native_result_status

    status = native_result_status(evidence)
    assert status == expected
    assert status != 'FAIL'


def test_q_warning_is_nonblocking_for_studies():
    from igea_dgs.native_action import status_blocks_studies

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
