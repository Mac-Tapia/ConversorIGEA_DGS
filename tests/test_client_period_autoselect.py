"""Spec 013, RF-12: con un mes, el libro de ese mes de la carpeta (no se elige el mes)."""

from __future__ import annotations


def _workspace(tmp_path):
    from igea_dgs.web.workspace import Workspace

    source = tmp_path / 'clientes'
    source.mkdir()
    (source / '0326clientesImportantes.xlsx').write_bytes(b'march')
    (source / '0426clientesImportantes.xlsb').write_bytes(b'april')
    ws = Workspace(id='period-auto', root=tmp_path)
    ws.demanda['clientes'] = {
        'path': str(source),
        'source_kind': 'folder',
        'vigente': True,
        'catalogo': [
            {'nombre': '0326clientesImportantes.xlsx', 'mes': '2026-03',
             'origen_mes': 'nombre', 'activo': True, 'avisos': []},
            {'nombre': '0426clientesImportantes.xlsb', 'mes': '2026-04',
             'origen_mes': 'nombre', 'activo': True, 'avisos': []},
        ],
    }
    return ws


def test_periodo_clientes_selects_exact_peak_month_from_multi_month_folder(tmp_path):
    """013:RF-12 — de una carpeta de varios meses, el libro del mes pedido."""
    from igea_dgs.web.services import periodo_clientes_activo

    evidence = periodo_clientes_activo(_workspace(tmp_path), '2026-04')

    assert evidence.status == 'CLIENT_PERIOD_VERIFIED'
    assert evidence.period == '2026-04'
    assert evidence.file == '0426clientesImportantes.xlsb'
    assert evidence.fingerprint


def test_demanda_path_selects_exact_peak_month_without_mutating_catalog(tmp_path):
    """013:RF-12 — elegir el libro del mes no cambia el índice."""
    from igea_dgs.web.services import _demanda_ruta

    ws = _workspace(tmp_path)
    before = [dict(item) for item in ws.demanda['clientes']['catalogo']]

    selected = _demanda_ruta(ws, 'clientes', periodo='2026-04')

    assert selected.name == '0426clientesImportantes.xlsb'
    assert ws.demanda['clientes']['catalogo'] == before

