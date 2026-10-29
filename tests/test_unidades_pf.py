"""Spec 035: el ajuste lee las unidades del proyecto de DIgSILENT antes de escribir."""
from __future__ import annotations

import pytest
from apoyo import cargar_herramienta
from test_ajuste_cabecera_guion import _app, _carga, _plan


@pytest.fixture(scope='module')
def guion():
    return cargar_herramienta('ajuste_cabecera_pf.py', 'ajuste_cabecera_pf_unidades',
                              tools_en_path=True)


class _Obj:
    def __init__(self, unidades):
        self.unidades = unidades

    def GetAttributeUnit(self, a):  # noqa: N802 - API de DIgSILENT
        return self.unidades[a]


class _App:
    def __init__(self, carga, banco):
        self.objs = {'ElmLod': [_Obj(carga)], 'ElmShnt': [_Obj(banco)] if banco else []}

    def GetCalcRelevantObjects(self, patron):  # noqa: N802 - API de DIgSILENT
        return self.objs[patron.split('.')[-1]]


def test_las_unidades_del_proyecto_se_leen_y_se_comparan(guion):
    """035:RF-14, 035:RF-16 — MW y Mvar son las correctas; en kW, el motivo dice cuál y dónde."""
    cargas_pf = guion.unidades_del_proyecto.__globals__
    bien = cargas_pf['unidades_del_proyecto'](_App({'plini': 'MW', 'qlini': 'Mvar'}, {'qcapn': 'Mvar'}))
    assert bien['correctas'] and bien['leidas'] == {'plini': 'MW', 'qlini': 'Mvar', 'qcapn': 'Mvar'}
    assert cargas_pf['error_de_unidades'](bien) is None
    mal = cargas_pf['unidades_del_proyecto'](_App({'plini': 'kW', 'qlini': 'kvar'}, None))
    assert not mal['correctas'] and mal['distintas'] == {'plini': 'kW', 'qlini': 'kvar'}
    assert mal['leidas']['qcapn'] is None, 'sin bancos, su unidad no se sabe y no decide'
    motivo = cargas_pf['error_de_unidades'](mal)
    assert 'kW (plini)' in motivo and 'Ajustes del proyecto' in motivo and '035:RF-15' in motivo


def test_en_un_proyecto_en_kw_no_se_escribe_nada(guion, monkeypatch):
    """035:RF-15 — con las cargas en kW, el ajuste se detiene antes de escribir y lo dice."""
    app = _app()
    antes = {c.loc_name: (c.plini, c.qlini, c.scale0) for c in app.proyecto.GetContents('*.ElmLod', 1)}
    monkeypatch.setitem(guion.ejecutar.__globals__, 'unidades_del_proyecto',
                        lambda _app: {'leidas': {'plini': 'kW', 'qlini': 'kvar', 'qcapn': None},
                                      'esperadas': {}, 'correctas': False,
                                      'distintas': {'plini': 'kW', 'qlini': 'kvar'}})
    informe, rc = guion.ejecutar(app, _plan())
    assert rc == 2 and '035:RF-15' in informe['error']
    assert informe['unidades']['distintas'] == {'plini': 'kW', 'qlini': 'kvar'}
    despues = {c.loc_name: (c.plini, c.qlini, c.scale0) for c in app.proyecto.GetContents('*.ElmLod', 1)}
    assert despues == antes
    assert _carga(app, 'F1_S1').plini == antes['F1_S1'][0]


def test_el_informe_dice_las_unidades_leidas(guion):
    """035:RF-16 — en un proyecto normal, el informe lleva las unidades que leyó."""
    informe, rc = guion.ejecutar(_app(), _plan())
    assert rc == 0, informe
    assert 'unidades' in informe and informe['unidades']['correctas']
