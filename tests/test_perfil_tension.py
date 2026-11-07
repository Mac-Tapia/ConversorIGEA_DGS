"""Spec 094: perfil de tensión de un alimentador y bancos ubicados según el perfil, en redes sintéticas sorteadas."""
from __future__ import annotations

import os
import random

import pytest

from convertersmartgrid import perfil_tension as pt

SEMILLA = int(os.environ.get('CSG_SCALE_SEED', random.randrange(1 << 30)))
PRE = 'Red:\\P\\'


def _id(n: str) -> str:
    return f'ElmTerm:{PRE}{n}.ElmTerm'


def _red(rng: random.Random):
    """Una troncal S–T1…Tn con ramales sorteados; cada tramo con su largo y una carga por barra."""
    n = rng.randint(8, 30)
    nodos = {_id('S'): {'kv': 22.9, 'fuente': True}}
    ramas, previo = [], 'S'
    for i in range(1, n + 1):
        nodos[_id(f'T{i}')] = {'kv': 22.9, 'fuente': False}
        ramas.append({'id': f'ElmLne:{PRE}L{i}.ElmLne', 'desde': _id(previo), 'hasta': _id(f'T{i}'),
                      'largo_km': rng.uniform(0.2, 1.5), 'cerrada': True})
        if rng.random() < 0.3:
            nodos[_id(f'R{i}')] = {'kv': 22.9, 'fuente': False}
            ramas.append({'id': f'ElmLne:{PRE}LR{i}.ElmLne', 'desde': _id(f'T{i}'), 'hasta': _id(f'R{i}'),
                          'largo_km': rng.uniform(0.1, 0.8), 'cerrada': True})
            nodos[_id(f'R{i}_BT')] = {'kv': 0.38, 'fuente': False}
            ramas.append({'id': f'ElmTr2:{PRE}TR{i}.ElmTr2', 'desde': _id(f'R{i}'), 'hasta': _id(f'R{i}_BT'),
                          'cerrada': True})
        previo = f'T{i}'
    # Tensión que cae con la distancia: lo que da un flujo en una troncal cargada.
    dist = pt.distancias({'nodos': nodos, 'ramas': ramas})
    u = {pt.nombre(k): 1.0 - 0.0025 * km for k, km in dist.items()}
    return {'nodos': nodos, 'ramas': ramas}, u, n


def test_perfil_por_distancia_electrica_solo_media():
    """094:RF-1 — cada barra de media del alimentador con su distancia por el camino eléctrico y su tensión; las de
    baja quedan fuera; ordenado de la cabecera al final."""
    rng = random.Random(SEMILLA)
    g, u, n = _red(rng)
    perfil = pt.perfil(g, u)
    nombres = [p['barra'] for p in perfil]
    assert 'S' not in nombres and not any(b.endswith('_BT') for b in nombres)
    assert [p['km'] for p in perfil] == sorted(p['km'] for p in perfil)
    t_n = next(p for p in perfil if p['barra'] == f'T{n}')
    largo = sum(r['largo_km'] for r in g['ramas'] if r['id'].endswith(tuple(f'\\L{i}.ElmLne' for i in range(1, n + 1))))
    assert t_n['km'] == pytest.approx(largo) and t_n['u'] == pytest.approx(u[f'T{n}'])


def test_camino_a_la_barra_mas_baja_y_reglas_de_ubicacion():
    """094:RF-4, 094:RF-6 — sobre el camino de la cabecera a la barra más baja: por caída igual, por 2i/(2n+1) de la
    distancia y uno por tramo; ningún par a menos de la separación mínima."""
    rng = random.Random(SEMILLA)
    g, u, n = _red(rng)
    todos = pt.ejes(g, pt.perfil(g, u), ramal_largo_km=0.5)
    camino = todos[0]                                                  # la troncal: el camino más largo
    assert camino[-1]['km'] == max(p['km'] for p in pt.perfil(g, u)) and camino[0]['km'] < camino[-1]['km']
    assert all(e[0]['barra'] in {p['barra'] for p in camino} or e[0]['barra'].startswith('R') for e in todos[1:])
    largo = camino[-1]['km'] - camino[0]['km']
    for regla in pt.REGLAS:
        barras = pt.ubicaciones(camino, 3, regla, separacion_km=0.0)
        assert len(barras) == len(set(barras)) <= 3 and all(b in {p['barra'] for p in camino} for b in barras)
    dos = pt.ubicaciones(camino, 3, 'dos_n_mas_uno', separacion_km=0.0)
    km = {p['barra']: p['km'] for p in camino}
    for i, b in enumerate(dos, start=1):
        assert abs(km[b] - camino[0]['km'] - largo * 2 * i / 7) <= max(r.get('largo_km') or 0 for r in g['ramas'])
    sep = pt.ubicaciones(camino, 5, 'caida_igual', separacion_km=largo / 3)
    assert all(abs(km[a] - km[b]) >= largo / 3 - 1e-9 for i, a in enumerate(sep) for b in sep[i + 1:])


def test_bancos_hasta_el_objetivo_o_hasta_que_no_mejora_o_el_valle():
    """094:RF-8, 094:RF-9 — se añade un banco cada vez, ubicado por el perfil, hasta el objetivo; si no mejora o el
    valle se pasa, se para y dice por qué y cuánto alcanzó."""
    camino = [{'barra': f'B{i}', 'km': float(i), 'u': 1.0 - 0.005 * i} for i in range(1, 21)]

    def medir(barras):          # cada banco sube 0,01 p.u. hasta un techo de 0,95 + 0,03
        return min(0.90 + 0.01 * len(barras), 0.93), 100.0 - len(barras)

    r = pt.bancos_hasta_objetivo([camino], medir, objetivo=0.92, mejora_minima=0.001, valle=lambda b: (True, 1.0))
    assert len(r['barras']) == 2 and r['motivo'] == 'objetivo' and r['v_min'] == pytest.approx(0.92)
    r = pt.bancos_hasta_objetivo([camino], medir, objetivo=1.0, mejora_minima=0.001, valle=lambda b: (True, 1.0))
    assert r['motivo'] == 'sin_mejora' and r['v_min'] == pytest.approx(0.93) and len(r['barras']) == 3
    r = pt.bancos_hasta_objetivo([camino], medir, objetivo=1.0, mejora_minima=0.001,
                                 valle=lambda b: (len(b) < 2, 1.06 if len(b) >= 2 else 1.0))
    assert r['motivo'] == 'valle' and len(r['barras']) == 1 and r['valle_max'] == pytest.approx(1.0)


def test_ramas_de_largo_cero_no_cuelgan_el_camino():
    """094:RF-4 — transformadores y acopladores sin largo (0 km) dejan nodos a la misma distancia; el camino a la barra
    más baja termina igual. AL209 (2026-11-06): la calibración quedó en un bucle sin fin al buscar el camino."""
    import threading
    nodos = {_id('S'): {'kv': 22.9, 'fuente': True}, _id('A'): {'kv': 22.9}, _id('A2'): {'kv': 22.9},
             _id('B'): {'kv': 22.9}, _id('B_BT'): {'kv': 0.38}}
    # El acoplador va antes que la línea que llega desde la fuente: así lo leía DIgSILENT en AL209.
    ramas = [{'id': 'C1', 'desde': _id('A'), 'hasta': _id('A2')},                       # acoplador, 0 km
             {'id': 'L1', 'desde': _id('S'), 'hasta': _id('A'), 'largo_km': 1.0},
             {'id': 'L2', 'desde': _id('A2'), 'hasta': _id('B'), 'largo_km': 2.0},
             {'id': 'T1', 'desde': _id('B'), 'hasta': _id('B_BT')}]
    g = {'nodos': nodos, 'ramas': ramas}
    u = {'A': 0.99, 'A2': 0.99, 'B': 0.97, 'B_BT': 0.95}
    salida = {}
    hilo = threading.Thread(target=lambda: salida.setdefault('c', pt.ejes(g, pt.perfil(g, u), ramal_largo_km=0.5)[0]), daemon=True)
    hilo.start()
    hilo.join(5)
    assert not hilo.is_alive(), 'el árbol no termina con ramas de largo cero'
    assert [p['barra'] for p in salida['c']][-1] == 'B'


def test_la_comparacion_del_perfil_antes_y_despues_de_una_propuesta():
    """094:RF-13, 094:RF-14 — el perfil completo antes y después, con su mínima, su máxima, las barras fuera de límite y
    las pérdidas, también en el valle; mejora solo si sube la mínima sin dejar más barras fuera."""
    import random

    rnd = random.Random(94013)
    barras = [f'N{i}' for i in range(rnd.randint(6, 30))]
    antes = {b: rnd.uniform(0.92, 1.0) for b in barras}
    despues = {b: min(1.04, u + rnd.uniform(0.005, 0.03)) for b, u in antes.items()}
    c = pt.comparar(antes, despues, limite_min=0.95, limite_max=1.05, perdidas_antes=120.0, perdidas_despues=110.0,
                    valle_antes=1.01, valle_despues=1.03)
    assert c['antes']['u'] == antes and c['despues']['u'] == despues
    assert c['antes']['v_min'] == min(antes.values()) and c['despues']['v_max'] == max(despues.values())
    assert c['antes']['bajo_limite'] == sum(1 for u in antes.values() if u < 0.95)
    assert c['despues']['bajo_limite'] <= c['antes']['bajo_limite'] and c['mejora']
    assert c['valle'] == {'antes': 1.01, 'despues': 1.03}
    peor = {b: (1.06 if b == barras[0] else u) for b, u in despues.items()}
    assert not pt.comparar(antes, peor, limite_min=0.95, limite_max=1.05, perdidas_antes=120.0,
                           perdidas_despues=110.0)['mejora']


def test_el_perfil_de_la_propuesta_queda_en_el_espacio(tmp_path):
    """094:RF-13 — el perfil antes y después queda guardado por proyecto y alimentador; un fichero roto no tumba nada."""
    from types import SimpleNamespace

    from convertersmartgrid.web import services

    ws = SimpleNamespace(out_dir=tmp_path / 'salida')
    c = pt.comparar({'A': 0.94}, {'A': 0.97}, limite_min=0.95, limite_max=1.05, perdidas_antes=1.0, perdidas_despues=0.9)
    services._guardar_perfil_de_propuesta(ws, 'P', 'F1', c)
    import json

    assert json.loads((ws.out_dir / 'perfil_propuestas.json').read_text(encoding='utf-8'))['P']['F1']['mejora'] is True
    (ws.out_dir / 'perfil_propuestas.json').write_text('{roto', encoding='utf-8')
    services._guardar_perfil_de_propuesta(ws, 'P', 'F1', c)          # se avisa en el registro de la web, sin error
