"""Spec 107 T6 — la red del área en pandapower y la matriz estudio × motor (107:RF-3, 107:RF-5)."""
from __future__ import annotations

import pytest

from datos_pit import perfil_a, perfil_b

from convertersmartgrid.dominio.pit.ambito import PitError, areas_del_perfil, reunir
from convertersmartgrid.adaptadores.pit.motores import ESTUDIOS, capacidad, ejecutar, elegir_motor
from convertersmartgrid.aplicacion.pit.red_area import desde_ambito

SEMILLAS = (4, 23)


def _red_y_cargas(caso):
    area = areas_del_perfil(caso['perfil'], caso['area'])[0]
    red = desde_ambito(reunir(area, caso['elementos']))
    anio = caso['anios'][0]
    alim_set = {a: s for s, alims in area.set_alimentadores.items() for a in alims}
    cargas: dict[str, list[float]] = {}
    barras = red.barras_de_carga()
    for f in caso['proyeccion']:
        if f['anio_calendario'] == anio:
            p, q = cargas.setdefault(barras[alim_set[f['alimentador']]], [0.0, 0.0])
            cargas[barras[alim_set[f['alimentador']]]] = [p + f['p_kw'] / 1000, q + f['q_kvar'] / 1000]
    return red, {b: tuple(v) for b, v in cargas.items()}


@pytest.mark.parametrize('fabrica', (perfil_a, perfil_b), ids=('A', 'B'))
@pytest.mark.parametrize('seed', SEMILLAS)
def test_flujo_converge_con_pandapower_y_nombra_su_motor(fabrica, seed):
    """107:RF-3 — el flujo de los dos perfiles converge con el motor abierto; el resultado dice su motor."""
    red, cargas = _red_y_cargas(fabrica(seed))
    r = ejecutar('flujo', red, cargas)
    assert r['motor'] == 'abierto' and r['disponible']
    flujo = r['resultado']
    assert flujo.converge and flujo.motor == 'abierto' and flujo.p_sin_servir_mw == 0
    assert all(0.85 < v < 1.15 for v in flujo.tensiones_pu.values())
    assert set(flujo.cargabilidad_pct) == {e['id'] for t in ('linea', 'trafo2', 'trafo3') for e in red.de_tipo(t)}
    assert flujo.perdidas_mw > 0


@pytest.mark.parametrize('seed', SEMILLAS)
def test_tres_devanados_y_compensacion_del_perfil_b(seed):
    """107:RF-3 — el transformador de tres devanados se carga, y el banco capacitivo sube la tensión de su barra."""
    caso = perfil_b(seed)
    red, cargas = _red_y_cargas(caso)
    con = ejecutar('tension', red, cargas)['resultado']
    q = red.de_tipo('compensacion')[0]
    sin = ejecutar('tension', red, cargas, fuera=[q['id']])['resultado']
    assert con.cargabilidad_pct[caso['pistas']['trafo3']] > 0
    assert con.tensiones_pu[q['barra']] > sin.tensiones_pu[q['barra']]


@pytest.mark.parametrize('seed', SEMILLAS)
def test_contingencia_de_la_radial_deja_carga_sin_servir(seed):
    """107:RF-3 — sin la línea radial, la SET que cuelga de ella queda sin tensión y su carga sin servir."""
    caso = perfil_b(seed)
    red, cargas = _red_y_cargas(caso)
    r = ejecutar('n_1', red, cargas, fuera=[caso['pistas']['radial']])['resultado']
    assert r.converge and r.p_sin_servir_mw > 0 and r.sin_tension
    anillo = ejecutar('n_1', red, cargas, fuera=[caso['pistas']['anillo'][0]])['resultado']
    assert anillo.converge and anillo.p_sin_servir_mw == 0


def test_sin_licencia_cortocircuito_y_comrel3_no_disponibles():
    """107:RF-5 — lo que el motor abierto no calcula se dice: no se inventa."""
    red, cargas = _red_y_cargas(perfil_a(1))
    cc = ejecutar('cortocircuito', red, cargas)
    assert cc['disponible'] is False and 'no disponible con el motor abierto' in cc['texto']
    conf = capacidad('abierto', 'confiabilidad')
    assert conf.alcance == 'reducido' and 'ComRel3' in conf.texto and 'no disponible con el motor abierto' in conf.texto
    assert all(capacidad('digsilent', e).alcance == 'completo' for e in ESTUDIOS)


def test_eleccion_del_motor():
    """107:RF-5 — el abierto por defecto, DIgSILENT si hay licencia; pedirlo sin ella es un error."""
    assert elegir_motor(None, licencia=False) == 'abierto'
    assert elegir_motor(None, licencia=True) == 'abierto'
    assert elegir_motor('digsilent', licencia=True) == 'digsilent'
    with pytest.raises(PitError, match='no está disponible'):  # 107:RF-23: disponible, no licencia
        elegir_motor('digsilent', licencia=False)
