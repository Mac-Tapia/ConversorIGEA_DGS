"""Spec 107 T4 — el ámbito de un área de demanda, sin mezclarla con otra (107:RF-2, 107:RF-11).

Los casos son los dos sintéticos de ``datos_pit`` (A: un titular; B: varios, con un elemento compartido sin asignar).
"""
from __future__ import annotations

import pytest

from datos_pit import perfil_a, perfil_b

from convertersmartgrid.adaptadores.perfil_esquema import validar_perfil
from convertersmartgrid.dominio.pit.ambito import PitError, areas_del_perfil, reunir

SEMILLAS = (3, 17, 42)


def _area(caso):
    return next(a for a in areas_del_perfil(caso['perfil']) if a.codigo == caso['area'])


@pytest.mark.parametrize('seed', SEMILLAS)
def test_perfil_a_reune_su_area_y_deja_fuera_la_media_tension(seed):
    """107:RF-2 — las SET, transformadores, celdas y líneas del área; la línea de MT fuera de las SET, con su motivo."""
    caso = perfil_a(seed)
    amb = reunir(_area(caso), caso['elementos'])
    ids = {e['id'] for e in amb.elementos}
    assert set(caso['pistas']['radiales']) <= ids
    assert {f'T-{s}' for s in caso['pistas']['sets']} <= ids
    assert {f'C-{s}' for s in caso['pistas']['sets']} <= ids
    fuera = caso['pistas']['fuera_por_tension']
    assert fuera not in ids and fuera in amb.excluidos and 'tensión' in amb.excluidos[fuera]
    assert not amb.compartidos_sin_asignar


@pytest.mark.parametrize('seed', SEMILLAS)
def test_perfil_b_no_mezcla_areas_y_marca_el_compartido(seed):
    """107:RF-2 — lo de otra área no entra; el compartido sin asignar entra marcado y con aviso."""
    caso = perfil_b(seed)
    p = caso['pistas']
    amb = reunir(_area(caso), caso['elementos'])
    ids = {e['id'] for e in amb.elementos}
    assert p['solo_otra'] not in ids
    assert p['compartida'] in ids and p['compartida'] in amb.compartidos_sin_asignar
    assert any(p['compartida'] in a for a in amb.avisos)
    assert p['trafo3'] in ids and set(p['anillo']) <= ids
    otra = next(a for a in areas_del_perfil(caso['perfil']) if a.codigo == p['otra_area'])
    amb_otra = reunir(otra, caso['elementos'])
    assert {e['id'] for e in amb_otra.elementos} == {p['solo_otra'], p['compartida']}


@pytest.mark.parametrize('seed', SEMILLAS)
def test_compartido_asignado_entra_en_una_sola_area(seed):
    """107:RF-2 — con la asignación en el perfil, el compartido es de un área y sale de la otra con su motivo."""
    caso = perfil_b(seed)
    p = caso['pistas']
    for a in caso['perfil']['pit']['areas']:
        a['compartidos'] = {p['compartida']: p['otra_area']}
    propia = reunir(_area(caso), caso['elementos'])
    assert p['compartida'] not in {e['id'] for e in propia.elementos}
    assert p['otra_area'] in propia.excluidos[p['compartida']]
    otra = next(a for a in areas_del_perfil(caso['perfil']) if a.codigo == p['otra_area'])
    assert p['compartida'] in {e['id'] for e in reunir(otra, caso['elementos']).elementos}
    assert not propia.compartidos_sin_asignar


def test_area_sin_tension_minima_es_un_error_que_la_nombra():
    """107:RF-11 — la tensión mínima del ámbito no tiene valor por defecto: sin ella, un error que la nombra."""
    caso = perfil_a(5)
    del caso['perfil']['pit']['areas'][0]['tension_min_kv']
    with pytest.raises(PitError, match='tension_min_kv'):
        areas_del_perfil(caso['perfil'])


def test_area_que_no_esta_en_el_perfil():
    """107:RF-2 — pedir un área que el perfil no declara es un error, no un ámbito vacío."""
    caso = perfil_a(5)
    with pytest.raises(PitError, match='no declara'):
        areas_del_perfil(caso['perfil'], 'NO-EXISTE')


@pytest.mark.parametrize('fabrica', (perfil_a, perfil_b), ids=('A', 'B'))
def test_seccion_pit_del_perfil_valida(fabrica):
    """107:RF-11 — la sección `pit` del perfil está en su esquema: ni errores ni claves desconocidas."""
    r = validar_perfil(fabrica(11)['perfil'])
    assert r.errores == [] and not [c for c in r.desconocidas if c.startswith('pit')]
    assert 'pit.areas' in {f.clave for f in validar_perfil({}).faltan}
