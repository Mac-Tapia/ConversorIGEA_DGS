"""Spec 017, T10: ``tools/transformador_set_pf.py`` con dobles mínimos de DIgSILENT.

Como AD08 (sonda del 2026-10-15): una carga por barra de SET (``LElCarmen10`` en
``CAR10A``) bajo un transformador de tres devanados. El doble del flujo da al devanado de
10 kV la potencia de la carga más una fija, para ver que el Δ entra y que la carga vuelve
a su P y Q. Los envoltorios de la API son objetos nuevos en cada llamada, como en
DIgSILENT: el guion no puede comparar barras con ``is``.
"""
from __future__ import annotations

import math

import pytest

from apoyo import cargar_herramienta

guion = cargar_herramienta('transformador_set_pf.py', 'transformador_set_t10', tools_en_path=True)


class _Obj:
    def __init__(self, clase, nombre, padre=None, **attrs):
        self._clase, self.loc_name, self._padre = clase, nombre, padre
        self.__dict__.update(attrs)

    def GetClassName(self):
        return self._clase

    def GetFullName(self):
        return (self._padre.GetFullName() + '\\' if self._padre else '') + f'{self.loc_name}.{self._clase}'

    def GetAttribute(self, attr):
        return self.resultados[attr]


class _Envoltorio:
    """Otro objeto Python para la misma barra, como da la API en cada ``GetParent``."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)


class _Cub:
    def __init__(self, barra):
        self._barra = barra

    def GetParent(self):
        return _Envoltorio(self._barra)


class _Caso(_Obj):
    def Activate(self):
        self.app.activo = self


class _App:
    def __init__(self, *, converge=True):
        red = _Obj('ElmNet', 'Red')
        self.b10 = _Obj('ElmTerm', 'CAR10A', red, uknom=10.0)
        self.b23 = _Obj('ElmTerm', 'CAR23A', red, uknom=23.0)
        self.b60 = _Obj('ElmTerm', 'EL CARMEN60', red, uknom=60.0)
        tipo = _Obj('TypTr3', 'tipo', strn3_h=30.0, strn3_m=10.0, strn3_l=20.0)
        self.trafo = _Obj('ElmTr3', 'TR1 EL CARMEN_N', red, typ_id=tipo, bushv=_Cub(self.b60),
                          busmv=_Cub(self.b23), buslv=_Cub(self.b10), resultados={})
        self.b10.GetConnectedElements = lambda: [self.trafo]
        self.carga = _Obj('ElmLod', 'LElCarmen10', red, plini=7.5, qlini=2.5, bus1=_Cub(self.b10))
        self.otra = _Obj('ElmLod', 'lod Suelta', red, plini=1.0, qlini=0.0, bus1=None)
        self.casos = [_Caso('IntCase', n, app=self) for n in ('2026_D', '2027_D')]
        self.activo = self.casos[0]
        self.converge = converge
        self.flujos = 0

    def GetCalcRelevantObjects(self, patron):
        return {'*.ElmLod': [self.carga, self.otra], '*.ElmTerm': []}[patron]

    def GetProjectFolder(self, _):
        return type('Estudios', (), {'GetContents': lambda _s, *_a: list(self.casos)})()

    def GetActiveStudyCase(self):
        return self.activo

    def GetFromStudyCase(self, _):
        app = self

        class _Ldf:
            def Execute(self):
                app.flujos += 1
                s10 = math.hypot(app.carga.plini, app.carga.qlini) + 1.0
                app.trafo.resultados = {'m:S:buslv': s10, 'c:loading': 100.0 * s10 / 20.0}
                return 0 if app.converge else 1
        return _Ldf()

    def IsLdfValid(self):
        return self.converge


def test_devanado_sin_y_con_el_delta_y_la_carga_vuelve():
    """017:RF-66, 017:RF-67, 017:RF-68 — el Δ entra solo en «con» y la carga queda como estaba."""
    app = _App()
    informe, codigo = guion.calcular(app, {'carga': 'LElCarmen10', 'caso': '2027_D',
                                           'delta_kw': 2000.0, 'delta_kvar': 500.0})
    assert codigo == 0, informe
    sin, con = informe['sin']['trafos'][0], informe['con']['trafos'][0]
    assert (sin['nombre'], sin['lado'], sin['kv']) == ('TR1 EL CARMEN_N', 'buslv', 10.0)
    assert sin['devanado_pct'] == pytest.approx(100 * (math.hypot(7.5, 2.5) + 1) / 20)
    assert con['devanado_pct'] == pytest.approx(100 * (math.hypot(9.5, 3.0) + 1) / 20)
    assert informe['restituida'] and (app.carga.plini, app.carga.qlini) == (7.5, 2.5)
    assert informe['caso'] == '2027_D' and app.activo is app.casos[0], 'vuelve el caso que estaba activo'
    assert app.flujos == 2, 'un flujo por estado, nada más'


def test_si_el_flujo_falla_la_carga_tambien_vuelve():
    """017:RF-68 — también si algo falla a mitad, la carga recupera su P y Q."""
    app = _App()

    def roto(*_a):
        raise RuntimeError('DIgSILENT se cayó')

    original = guion.medir
    llamadas = []

    def medir(a, c):
        llamadas.append(1)
        if len(llamadas) == 2:
            roto()
        return original(a, c)

    guion.medir = medir
    try:
        with pytest.raises(RuntimeError):
            guion.calcular(app, {'carga': 'LElCarmen10', 'delta_kw': 900.0, 'delta_kvar': 0.0})
    finally:
        guion.medir = original
    assert (app.carga.plini, app.carga.qlini) == (7.5, 2.5)


def test_carga_o_caso_que_no_existen_lo_dicen():
    """017:RF-70 — sin la carga o el caso, el informe dice por qué y no toca nada."""
    app = _App()
    informe, codigo = guion.calcular(app, {'carga': 'LCA101', 'delta_kw': 1.0})
    assert codigo == 2 and 'LCA101' in informe['error'] and app.flujos == 0
    informe, codigo = guion.calcular(app, {'carga': 'LElCarmen10', 'caso': '2040_D'})
    assert codigo == 2 and '2040_D' in informe['error']


def test_listar_da_las_cargas_con_transformador_y_los_casos():
    """017:RF-65b, 017:RF-95 — el operador elige la carga de la barra y el caso."""
    datos = guion.listar(_App())
    assert datos['casos'] == ['2026_D', '2027_D'] and datos['caso_activo'] == '2026_D'
    assert datos['cargas'] == [{'nombre': 'LElCarmen10', 'barra': 'CAR10A', 'kv': 10.0,
                                'trafos': ['TR1 EL CARMEN_N']}]


def test_ayuda():
    """009 — la herramienta responde a ``--help``."""
    with pytest.raises(SystemExit) as fin:
        guion.main(['--help'])
    assert fin.value.code == 0
