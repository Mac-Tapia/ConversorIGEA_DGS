"""Pruebas del motor base de conversión.

Spec 034: 034:RF-23.
"""
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


class _Terminal:
    loc_name = 'N1'

    def GetClassName(self):
        return 'ElmTerm'


class _Cubicle:
    cterm = _Terminal()


class _Shunt:
    loc_name = 'BC_450'
    ctech = 1
    shtype = 2
    qcapn = .15
    ncapx = 3
    ncapa = 3
    ushnm = 10
    outserv = 0
    bus1 = _Cubicle()

    def GetClassName(self):
        return 'ElmShnt'

    def GetAttribute(self, name):
        return getattr(self, name, None)

    def SetAttribute(self, name, value):
        setattr(self, name, value)
        return 0


def test_native_capacitor_reread_matches_every_required_attribute():
    from apoyo import cargar_herramienta

    reread_capacitors = cargar_herramienta('powerfactory_acceptance.py').reread_capacitors

    app = SimpleNamespace(
        GetCalcRelevantObjects=lambda pattern: [_Shunt()] if pattern == '*.ElmShnt' else [],
    )
    expected = [{
        'loc_name': 'BC_450', 'terminal': 'N1', 'ctech': 1, 'shtype': 2,
        'qcapn': .15, 'ncapx': 3, 'ncapa': 3, 'ushnm': 10, 'outserv': 0,
    }]

    result = reread_capacitors(app, expected)

    assert result['status'] == 'VERIFICADO_PERSISTENCIA'
    assert result['banks'][0]['total_native_mvar'] == .45
    assert result['mismatches'] == []


def test_native_capacitor_mismatch_is_corrected_reread_and_nonblocking():
    from apoyo import cargar_herramienta

    reread_capacitors = cargar_herramienta('powerfactory_acceptance.py').reread_capacitors

    app = SimpleNamespace(
        GetCalcRelevantObjects=lambda pattern: [_Shunt()] if pattern == '*.ElmShnt' else [],
    )
    result = reread_capacitors(app, [{
        'loc_name': 'BC_450', 'terminal': 'N1', 'ctech': 1, 'shtype': 2,
        'qcapn': .3, 'ncapx': 3, 'ncapa': 3, 'ushnm': 10, 'outserv': 0,
    }])

    assert result['status'] == 'AVISO_PERSISTENCIA_CORREGIDA'
    assert result['blocks_conversion'] is False
    assert result['banks'][0]['qcapn'] == .3
    assert result['banks'][0]['terminal'] == 'N1'
    assert result['corrections'][0]['field'] == 'qcapn'
    assert result['corrections'][0]['before'] == .15
    assert result['corrections'][0]['after'] == .3
    assert result['mismatches'] == []


def test_bank_panel_uses_server_totals_without_recalculating_power():
    types = (ROOT / 'frontend/src/types.ts').read_text(encoding='utf-8')
    panel = (ROOT / 'frontend/src/components/FeedersPanel.tsx').read_text(encoding='utf-8')

    assert 'capacitor_banks:' in types
    assert 'capacitor_reread:' in types
    assert 'total_native_mvar' in panel
    assert 'corrections' in panel and 'mismatches' in panel
    assert 'BLOQUEADO_PERSISTENCIA' not in types
    assert 'qcapn *' not in panel
    assert 'qcapn*' not in panel
