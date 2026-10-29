"""Spec 013, RF-30 a RF-32: el libro de clientes del ajuste, del mes de la máxima."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest


def test_periodo_de_fecha_is_month_stable():
    """013:RF-11 — el mes de una fecha, en cualquiera de sus formas."""
    from igea_dgs.demanda_medida import periodo_de_fecha

    assert periodo_de_fecha(datetime(2026, 4, 16, 11)) == '2026-04'
    assert periodo_de_fecha('2026-04-16 11:00:00') == '2026-04'
    assert periodo_de_fecha('16/04/2026 11:00') == '2026-04'


def _workspace(tmp_path, *, client_period='2026-04', with_client_book=True):
    from igea_dgs.powerfactory_binding import PowerFactoryProjectBinding
    from igea_dgs.web.workspace import Workspace

    tmp_path.mkdir(parents=True, exist_ok=True)
    ws = Workspace(id='period', root=tmp_path)
    ws.active_run_id = 'run-active'
    ws.loaded_run_id = 'run-active'
    ws.loaded_source_mode = 'txt'
    ws.loaded_source_fingerprint = 'f' * 64
    ws.dataset = SimpleNamespace(feeder_ids=lambda: [])
    binding = PowerFactoryProjectBinding(
        project='P', folder='Conversor IGEA-DGS', source_run_id='run-active',
        source_mode='txt', source_fingerprint='f' * 64, feeders=('A1',),
        dgs_sha256={'A1': 'd' * 64}, native_inventory_sha256='n' * 64,
        # Spec 015: el «Caso base» de A1, verificado.
        native_reread={'status': 'VERIFICADO_PERSISTENCIA',
                       'caso_base': {'A1': {'status': 'VERIFICADO', 'fallos': []}}},
        accepted_at=1.0,
    )
    ws.pf_project_bindings['P'] = binding.as_dict()
    ws.pf_inventory = {'projects': [{
        'name': 'P', 'path': 'P', 'feeders': ['A1'],
        'native_inventory_sha256': 'n' * 64,
    }]}
    if with_client_book:
        book = tmp_path / 'clientes.xlsx'
        book.write_bytes(b'client-book')
        ws.demanda['clientes'] = {
            'path': str(book), 'name': book.name, 'origin': 'server',
            'source_kind': 'file',
            'catalogo': [{
                'nombre': book.name, 'mes': client_period,
                'origen_mes': 'manual' if client_period else 'sin_mes',
                'activo': True, 'avisos': [],
            }],
        }
    return ws


def _maxima(fecha='2026-04-16 11:00:00'):
    return [{
        'medidor': 'L-A1', 'alimentador': 'A1', 'fecha': fecha,
        'kw': 1000.0, 'kvar': 300.0, 'fp': None, 'error': None,
    }]


def test_matching_client_month_produces_v2_immutable_evidence(tmp_path, monkeypatch):
    """013:RF-32 — el plan guarda los dos meses, el libro con su huella y el vínculo."""
    from igea_dgs.web import services

    ws = _workspace(tmp_path)
    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'Conversor IGEA-DGS')
    plan = services.ajuste_plan(ws, 'P', _maxima(), '', .01)
    payload = __import__('json').loads(
        __import__('pathlib').Path(ws.cargas_planes[plan['token']]['path']).read_text(encoding='utf-8')
    )
    assert payload['schema'] == 'igea-dgs-ajuste-cabecera-v2'
    assert payload['periodo']['maxima'] == payload['periodo']['clientes'] == '2026-04'
    assert payload['periodo']['status'] == 'CLIENT_PERIOD_MATCH'
    assert payload['client_evidence']['fingerprint']
    assert payload['client_evidence']['file'] == 'clientes.xlsx'
    assert payload['project_binding']['source_run_id'] == 'run-active'
    assert payload['source']['source_fingerprint'] == 'f' * 64
    assert plan['periodo']['status'] == 'CLIENT_PERIOD_MATCH'
    assert plan['project_binding']['native_reread']['status'] == 'VERIFICADO_PERSISTENCIA'


def test_different_client_month_warns_and_unknown_blocks_plan(tmp_path, monkeypatch):
    """013:RF-30, 035:RF-19 — un libro de otro mes no bloquea: hay plan, con el libro, los dos
    meses y el aviso; un libro sin mes demostrable sigue sin plan."""
    from igea_dgs.web import services

    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'Conversor IGEA-DGS')
    plan = services.ajuste_plan(_workspace(tmp_path / 'different', client_period='2026-03'),
                                'P', _maxima(), '', .01)
    assert plan['periodo'] == {'status': 'CLIENT_PERIOD_MISMATCH', 'maxima': '2026-04',
                               'clientes': '2026-03'}
    assert any('035:RF-19' in a and '2026-03' in a for a in plan['avisos'])
    with pytest.raises(services.UserError, match='CLIENT_PERIOD_UNKNOWN'):
        services.ajuste_plan(_workspace(tmp_path / 'unknown', client_period=None),
                             'P', _maxima(), '', .01)


def test_unknown_peak_month_blocks_only_when_client_book_exists(tmp_path, monkeypatch):
    """013:RF-31 / 013:RF-13 — sin mes de la máxima solo bloquea si hay libro; sin libro,
    plan con aviso."""
    from igea_dgs.web import services

    monkeypatch.setattr(services, 'carpeta_pf', lambda: 'Conversor IGEA-DGS')
    with pytest.raises(services.UserError, match='MAXIMUM_PERIOD_UNKNOWN'):
        services.ajuste_plan(_workspace(tmp_path / 'with'), 'P', _maxima(None), '', .01)

    plan = services.ajuste_plan(
        _workspace(tmp_path / 'without', with_client_book=False), 'P', _maxima(None), '', .01,
    )
    assert any('Sin libro de clientes importantes' in warning for warning in plan['avisos'])
