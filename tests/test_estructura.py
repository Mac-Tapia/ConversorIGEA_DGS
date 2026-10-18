"""Spec 022, T1: la estructura de la empresa (zonales, SET y alimentadores)."""
from __future__ import annotations

import json
import os
import random

import pytest

from igea_dgs import estructura as es

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _tabla(rng):
    """Estructura sorteada: zonales, SET con siglas y alimentadores, con su sistema."""
    sistemas = {f'SE{i:04d}': {'nombre': f'Sistema {i}', 'sector': str(rng.choice([2, 3, 4])),
                               'norma': rng.choice(['NTCSE', 'NTCSER'])}
                for i in range(rng.randint(1, 6))}
    zonales, n_set, n_ali = [], 0, 0
    for z in range(rng.randint(1, 5)):
        sets = []
        for _ in range(rng.randint(1, 4)):
            n_set += 1
            alis = []
            for _ in range(rng.randint(1, 8)):
                n_ali += 1
                alis.append({'codigo': f'X{n_ali:03d}', 'sistema': rng.choice(list(sistemas))})
            sets.append({'codigo': f'SET {n_set}', 'nombre': f'Nombre {n_set}',
                         'siglas': [f'S{n_set}'], 'alimentadores': alis})
        zonales.append({'nombre': f'Zonal {z}', 'sets': sets})
    return {'zonales': zonales, 'sistemas': sistemas}


def test_estructura_del_perfil():
    """022:RF-1, 022:RF-2 — zonales, SET y alimentadores con su sistema, sector y norma."""
    rng = random.Random(SEMILLA)
    datos = _tabla(rng)
    e = es.estructura_de_dict(datos)
    assert e.zonales == [z['nombre'] for z in datos['zonales']]
    for z in datos['zonales']:
        for st in z['sets']:
            for a in st['alimentadores']:
                assert e.set_de(a['codigo']).rotulo == f"{st['codigo'].upper()} {st['nombre']}"
                assert e.set_de(a['codigo']).zonal == z['nombre']
                s = e.sistemas[e.alimentadores[a['codigo']].sistema]
                assert s.norma == datos['sistemas'][a['sistema']]['norma']
            assert e.set_de_siglas(st['siglas'][0].lower()).codigo == st['codigo'].upper()


def test_la_estructura_va_en_un_json_aparte(tmp_path):
    """022:RF-1 — el perfil puede nombrar un JSON junto a él; sin estructura, None (RF-6)."""
    datos = _tabla(random.Random(SEMILLA))
    (tmp_path / 'e.json').write_text(json.dumps(datos), encoding='utf-8')
    assert es.estructura_de_perfil({'estructura': 'e.json'}, tmp_path).alimentadores
    assert es.estructura_de_perfil({}) is None
    with pytest.raises(es.EstructuraError):
        es.estructura_de_perfil({'estructura': 'no.json'}, tmp_path)


@pytest.mark.parametrize('mal, dice', [
    ('repetido', 'repetido'), ('sin_set', 'no tiene SET'), ('sin_zonal', 'no tiene zonal'),
])
def test_tabla_mal_formada(mal, dice):
    """022:RF-5 — alimentador repetido, sin SET o SET sin zonal: error que nombra la fila."""
    datos = {'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET 1', 'nombre': 'A', 'alimentadores': [{'codigo': 'A101'}]}]}]}
    if mal == 'repetido':
        datos['zonales'][0]['sets'].append({'codigo': 'SET 2', 'alimentadores': [{'codigo': 'a101'}]})
    elif mal == 'sin_set':
        datos['zonales'][0]['sets'].append({'codigo': '', 'alimentadores': [{'codigo': 'B1'}]})
    else:
        datos['zonales'].append({'nombre': '', 'sets': [{'codigo': 'SET 3', 'alimentadores': ['C1']}]})
    with pytest.raises(es.EstructuraError, match=dice) as exc:
        es.estructura_de_dict(datos)
    assert 'fila' in str(exc.value)


def test_tabla_en_excel_como_la_publica_la_empresa(tmp_path):
    """022:RF-4, 022:RF-5 — la tabla en Excel con los encabezados de la tabla pública, la SET
    con su nombre en la misma celda; una fila repetida se nombra."""
    from openpyxl import Workbook

    rng = random.Random(SEMILLA)
    datos = _tabla(rng)
    wb = Workbook()
    h = wb.active
    h.append(['SISTEMAS ELÉCTRICOS'])
    h.append(['Zonal', 'Codigo Sist. Elect.', 'Nombre Sist. Elect.', 'Aplicación Final 2023-2026',
              'Codigo SET', 'Siglas', 'Codigo VNR Alimentador', 'OBSERVACION'])
    for z in datos['zonales']:
        for st in z['sets']:
            for a in st['alimentadores']:
                s = datos['sistemas'][a['sistema']]
                h.append([z['nombre'], a['sistema'], s['nombre'], s['sector'],
                          f"{st['codigo']} {st['nombre'].upper()}", st['siglas'][0], a['codigo'],
                          'FUERA DE SERVICIO'])
    wb.save(tmp_path / 't.xlsx')
    e = es.leer_tabla_excel(tmp_path / 't.xlsx')
    primero = datos['zonales'][0]['sets'][0]
    st = e.set_de(primero['alimentadores'][0]['codigo'])
    assert (st.codigo, st.nombre) == (primero['codigo'].upper(), primero['nombre'].upper())
    assert len(e.alimentadores) == sum(len(s['alimentadores']) for z in datos['zonales'] for s in z['sets'])
    h.append([datos['zonales'][0]['nombre'], '', '', '', 'SET 99 OTRA', '',
              primero['alimentadores'][0]['codigo']])
    wb.save(tmp_path / 't.xlsx')
    with pytest.raises(es.EstructuraError, match=r'fila \d+.*repetido'):
        es.leer_tabla_excel(tmp_path / 't.xlsx')


def test_asignar_la_entrega():
    """022:RF-19, 022:RF-20, 022:RF-25b — los de la entrega con su SET; los que no están en
    la estructura, «Sin SET»; los de la estructura que no vienen, faltan; SET, zonales y
    sistemas sin redes, omitidos."""
    rng = random.Random(SEMILLA)
    e = es.estructura_de_dict(_tabla(rng))
    todos = sorted(e.alimentadores)
    entrega = rng.sample(todos, rng.randint(1, len(todos))) + ['NUEVO1', 'nuevo2']
    a = es.asignar(e, entrega)
    assert a.sin_set == ['NUEVO1', 'NUEVO2']
    assert set(a.set_de) == {x for x in entrega if x in e.alimentadores}
    assert sorted(a.faltan) == sorted(set(todos) - set(entrega))
    assert set(a.sets) | set(a.omitidos['sets']) == set(e.sets)
    assert all(e.sets[s].zonal in a.zonales for s in a.sets)
    assert not set(a.zonales) & set(a.omitidos['zonales'])
    assert set(a.sistemas) == {e.alimentadores[x].sistema for x in a.set_de}
