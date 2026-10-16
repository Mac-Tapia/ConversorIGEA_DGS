"""Los bancos presentes solo en DIgSILENT también forman parte de la aceptación."""

from __future__ import annotations

from types import SimpleNamespace


class _Terminal:
    def __init__(self, name: str, voltage: float):
        self.loc_name = name
        self.uknom = voltage

    def GetClassName(self):
        return 'ElmTerm'


class _Cubicle:
    def __init__(self, name: str, terminal: _Terminal):
        self.loc_name = name
        self.cterm = terminal


class _Shunt:
    def __init__(self, name: str, node: str, voltage: float, qcapn: float):
        self.loc_name = name
        self.ctech = 1
        self.shtype = 2
        self.qcapn = qcapn
        self.ncapx = 1
        self.ncapa = 1
        self.ushnm = voltage
        self.outserv = 0
        self.bus1 = _Cubicle(f'{node}\\Cub_2', _Terminal(node, voltage))

    def GetClassName(self):
        return 'ElmShnt'

    def GetAttribute(self, name):
        return getattr(self, name, None)

    def SetAttribute(self, name, value):
        setattr(self, name, value)
        return 0

    def GetParent(self):
        return None


def _run(banks):
    from apoyo import cargar_herramienta

    reread = cargar_herramienta('powerfactory_acceptance.py').reread_capacitors
    app = SimpleNamespace(
        GetCalcRelevantObjects=lambda pattern: banks if pattern == '*.ElmShnt' else [],
    )
    return reread(app, [])


def test_discovers_native_only_banks_and_preserves_valid_catalog_rating():
    banks = [
        # PowerFactory almacena Float32 y relee 0.3000000119 para un nominal 0.3.
        _Shunt('Banco 1', 'N1', 10.0, .30000001192092896),
        _Shunt('Banco 2', 'N2', 10.0, .3),
        _Shunt('Banco 3', 'N3', 10.0, .3),
    ]

    result = _run(banks)

    assert result['status'] == 'VERIFICADO_PERSISTENCIA'
    assert result['expected'] == 0
    assert result['reread'] == 3
    assert [item['terminal'] for item in result['banks']] == ['N1', 'N2', 'N3']
    assert [item['cubicle'] for item in result['banks']] == [
        'N1\\Cub_2', 'N2\\Cub_2', 'N3\\Cub_2',
    ]
    assert all(item['catalog_kvar'] == 300.0 for item in result['banks'])
    assert result['corrections'] == []


def test_native_only_bank_uses_voltage_catalog_and_never_blocks():
    bank = _Shunt('Banco incorrecto', 'N10', 10.0, .45)

    result = _run([bank])

    assert result['status'] == 'AVISO_PERSISTENCIA_CORREGIDA'
    assert result['blocks_conversion'] is False
    assert bank.qcapn == .3
    assert result['banks'][0]['total_native_mvar'] == .3
    assert result['corrections'][0]['catalog_kvar'] == 300.0
    assert 'N10' in result['corrections'][0]['message']


def test_native_only_229kv_bank_uses_450_kvar_catalog():
    bank = _Shunt('Banco 22.9', 'N229', 22.9, .45)

    result = _run([bank])

    assert result['status'] == 'VERIFICADO_PERSISTENCIA'
    assert result['banks'][0]['catalog_kvar'] == 450.0
    assert result['banks'][0]['total_native_mvar'] == .45

