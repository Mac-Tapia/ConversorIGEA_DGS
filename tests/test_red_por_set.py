"""Spec 022: la red unida colgada de sus SET (barras, interruptores de cabecera)."""
from __future__ import annotations

import os
import random

from igea_dgs.combine import combine_models, estructurar
from igea_dgs.estructura import asignar, estructura_de_dict
from igea_dgs.model import Node
from test_combine import _alimentador

SEMILLA = int(os.environ.get('IGEA_SCALE_SEED', random.randrange(1 << 30)))


def _proyecto(rng):
    """Alimentadores sorteados en SET sorteadas de zonales sorteados; algunos a 22,9 kV y
    alguno fuera de la estructura. Cada SET tiene su punto: sus cabeceras coinciden."""
    zonales, modelos, n = [], [], 0
    for z in range(rng.randint(1, 3)):
        sets = []
        for s in range(rng.randint(1, 3)):
            codigo, punto = f'SET {z}{s}', (rng.uniform(4e5, 5e5), rng.uniform(8e6, 8.5e6))
            alis = []
            for _ in range(rng.randint(1, 4)):
                n += 1
                nombre, kv = f'F{n:03d}', rng.choice([10.0, 22.9])
                m = _alimentador(nombre, kv, [f'{nombre}_H', f'{nombre}_N1', f'{nombre}_N2'])
                m.nodes[f'{nombre}_H'] = Node(f'{nombre}_H', *punto)
                modelos.append(m)
                alis.append({'codigo': nombre, 'sistema': f'SE{z}'})
            sets.append({'codigo': codigo, 'nombre': f'Nombre {z}{s}', 'alimentadores': alis})
        zonales.append({'nombre': f'Zonal {z}', 'sets': sets})
    modelos.append(_alimentador('NUEVO', 10.0, ['NUEVO_H', 'NUEVO_N1']))
    return estructura_de_dict({'zonales': zonales, 'sistemas': {}}), modelos


def test_barras_de_set_e_interruptores_de_cabecera():
    """022:RF-10, 022:RF-11, 022:RF-12, 022:RF-13, 022:RF-19 — una barra por SET y tensión
    con sus alimentadores; cada uno unido a ella por un interruptor cerrado en su nodo de
    cabecera; el que no está en la estructura, «Sin SET»."""
    rng = random.Random(SEMILLA)
    e, modelos = _proyecto(rng)
    red, _ = combine_models(modelos)
    avisos = estructurar(red, e)
    info = red.combined
    esperadas = {(e.set_de(m.name).codigo, m.nominal_kv) for m in modelos if m.name != 'NUEVO'}
    assert {(b.set_codigo, b.nominal_kv) for b in info.barras_set} == esperadas
    for b in info.barras_set:
        assert b.node_id in red.nodes and info.node_kv[b.node_id] == b.nominal_kv
        assert all(e.set_de(f).codigo == b.set_codigo for f in b.feeders)
    cabeceras = {c.feeder: c for c in info.cabeceras}
    assert set(cabeceras) == {m.name for m in modelos} - {'NUEVO'}
    acopladores = {c.name: c for c in red.couplers}
    for m in modelos:
        if m.name == 'NUEVO':
            continue
        c = cabeceras[m.name]
        assert c.node_cabecera == m.source_node
        a = acopladores[c.coupler]
        assert a.on_off == 1 and a.kind == 'cabecera' and {a.node_a, a.node_b} == {c.node_set, c.node_cabecera}
    assert info.sin_set == ['NUEVO'] and any('022:RF-19' in x for x in avisos)
    assert info.zonal_de['NUEVO'] == ''


def test_la_barra_en_las_coordenadas_de_sus_cabeceras():
    """022:RF-17, 022:RF-18, 022:RF-18b — la barra en las coordenadas de sus cabeceras; si no
    coinciden, en las de la de menor código, y se avisa."""
    e = estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': ['A1', 'A2']}]}]})
    a1 = _alimentador('A1', 10.0, ['A1_H', 'A1_N'])
    a2 = _alimentador('A2', 10.0, ['A2_H', 'A2_N'])
    a1.nodes['A1_H'] = Node('A1_H', 450000.0, 8400000.0)
    a2.nodes['A2_H'] = Node('A2_H', 450000.0, 8400000.0)
    red, _ = combine_models([a1, a2])
    assert estructurar(red, e) == []
    [b] = red.combined.barras_set
    assert (red.nodes[b.node_id].x, red.nodes[b.node_id].y) == (450000.0, 8400000.0)
    a2.nodes['A2_H'] = Node('A2_H', 451000.0, 8400000.0)
    red, _ = combine_models([a1, a2])
    avisos = estructurar(red, e)
    assert any('022:RF-18b' in x and 'A1' in x for x in avisos)


def test_una_set_con_dos_tensiones_y_lo_que_no_tiene_redes():
    """022:RF-10, 022:RF-21, 022:RF-25b — una SET con alimentadores de 10 y 22,9 kV tiene dos
    barras; una SET sin alimentadores en la entrega no se escribe."""
    e = estructura_de_dict({'zonales': [{'nombre': 'Z', 'sets': [
        {'codigo': 'SET 1', 'nombre': 'Uno', 'alimentadores': ['A1', 'A2']},
        {'codigo': 'SET 2', 'nombre': 'Dos', 'alimentadores': ['B1']}]}]})
    red, _ = combine_models([_alimentador('A1', 10.0, ['A1_H', 'A1_N']),
                             _alimentador('A2', 22.9, ['A2_H', 'A2_N'])])
    estructurar(red, e, asignar(e, ['A1', 'A2']))
    assert sorted((b.set_codigo, b.nominal_kv) for b in red.combined.barras_set) == [
        ('SET 1', 10.0), ('SET 1', 22.9)]
    assert asignar(e, ['A1', 'A2']).omitidos['sets'] == ['SET 2']
