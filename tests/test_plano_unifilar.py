"""111:RF-23 (T23): el unifilar automático del plano, con la misma regla que el unifilar del PIT (107:RF-15).

- La disposición por anchura desde la fuente es una sola función (``dominio.disposicion_unifilar``); el PIT la usa con
  el orden de entrada y sus hojas no cambian (se compara con la regla de antes en grafos sorteados).
- Cada vista del plano lleva su cabecera y su unifilar con los mismos códigos de barra, sin tocar vértices ni datos.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import random
from collections import deque

import pytest

from convertersmartgrid.adaptadores.geography import build_geography, geography_to_dict
from convertersmartgrid.dominio.model import build_feeder_model
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export


def _disposicion():
    assert importlib.util.find_spec('convertersmartgrid.dominio.disposicion_unifilar') is not None, \
        'falta convertersmartgrid.dominio.disposicion_unifilar (111:RF-23)'
    return importlib.import_module('convertersmartgrid.dominio.disposicion_unifilar')


def _niveles_de_antes(vecinos, raices):
    """La regla del unifilar del PIT antes de 111:RF-23, copiada aquí como referencia: orden de entrada."""
    nivel, cola = {}, deque()
    for r in raices:
        if r in vecinos and r not in nivel:
            nivel[r] = 0
            cola.append(r)
    while cola:
        x = cola.popleft()
        for y in vecinos[x]:
            if y not in nivel:
                nivel[y] = nivel[x] + 1
                cola.append(y)
    ultimo = max(nivel.values(), default=-1) + 1
    for b in vecinos:
        nivel.setdefault(b, ultimo)
    orden, pos = {}, {}
    for b in vecinos:
        n = nivel[b]
        pos[b] = (n, orden.get(n, 0))
        orden[n] = orden.get(n, 0) + 1
    return pos


def _grafo(rng: random.Random) -> tuple[dict[str, list[str]], list[str]]:
    n = rng.randint(1, 40)
    nodos = [f'B{i}' for i in rng.sample(range(1000), n)]
    vecinos = {b: [] for b in nodos}
    for i in range(1, n):
        if rng.random() < 0.9:  # alguno queda suelto: sin camino desde la fuente
            a, z = nodos[i], nodos[rng.randrange(i)]
            vecinos[a].append(z)
            vecinos[z].append(a)
    return vecinos, [nodos[0]]


def test_111_rf23_por_anchura_desde_la_fuente_con_dos_ordenes():
    d = _disposicion()
    vecinos = {'A': ['C', 'B'], 'B': ['A', 'D'], 'C': ['A'], 'D': ['B'], 'X': []}
    entrada = d.niveles_por_anchura(vecinos, ['A'], orden='entrada')
    descubrimiento = d.niveles_por_anchura(vecinos, ['A'], orden='descubrimiento')
    assert entrada == {'A': (0, 0), 'B': (1, 0), 'C': (1, 1), 'D': (2, 0), 'X': (3, 0)}
    # Descubrimiento: C se alcanza antes que B desde A, y la barra sin camino va al final.
    assert descubrimiento == {'A': (0, 0), 'C': (1, 0), 'B': (1, 1), 'D': (2, 0), 'X': (3, 0)}
    with pytest.raises(ValueError):
        d.niveles_por_anchura(vecinos, ['A'], orden='otro')


def test_111_rf23_el_unifilar_del_pit_no_cambia_con_la_regla_comun():
    """107:RF-15: el PIT usa la regla común con el orden de entrada y da lo mismo que antes, grafo a grafo."""
    d = _disposicion()
    semilla = random.SystemRandom().randrange(1, 2 ** 31)
    rng = random.Random(semilla)
    for _ in range(200):
        vecinos, raices = _grafo(rng)
        assert d.niveles_por_anchura(vecinos, raices, orden='entrada') == _niveles_de_antes(vecinos, raices), \
            f'semilla={semilla}'
    from convertersmartgrid.adaptadores.pit import unifilar
    assert 'niveles_por_anchura' in unifilar._niveles.__code__.co_names, 'el PIT no usa la regla común'


def _vistas(tmp_path, seed: int):
    from convertersmartgrid.adaptadores import plano_red
    spec = ExportSpec(feeders=random.Random(seed).randint(2, 4), seed=seed, layout='completo')
    ds = load_export(spec, tmp_path / f'red_{seed}')
    for net in ds.feeder_ids():
        modelo = build_feeder_model(ds, net, strict=True, include_geography=True)
        geo = geography_to_dict(build_geography(ds, modelo, source_crs=CRS_SINTETICO), modelo)
        yield modelo, plano_red.vista(modelo, geo)


def test_111_rf23_cada_vista_lleva_su_unifilar_con_los_mismos_codigos(tmp_path):
    _disposicion()
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    print(f'semilla={seed}')
    vistas = list(_vistas(tmp_path, seed))
    assert vistas, f'semilla={seed}'
    for modelo, v in vistas:
        assert 'unifilar' in v and 'fuente' in v, 'la vista no trae su unifilar (111:RF-23)'
        u = v['unifilar']
        assert v['fuente'] == modelo.source_node and u['fuente'] == modelo.source_node, f'semilla={seed}'
        assert {b['codigo'] for b in u['barras']} == {b['codigo'] for b in v['barras']}, 'otros códigos que el plano (111:RF-2)'
        nivel = {b['codigo']: b['nivel'] for b in u['barras']}
        assert nivel[modelo.source_node] == 0
        alcanzadas = set(nivel) - set(u['sin_alcanzar'])
        for t in v['tramos']:
            if t['desde'] in alcanzadas and t['hasta'] in alcanzadas:
                # Por anchura, dos barras conectadas están en el mismo nivel o en niveles seguidos.
                assert abs(nivel[t['desde']] - nivel[t['hasta']]) <= 1, (t['codigo'], f'semilla={seed}')
        orden = {(b['nivel'], b['orden']) for b in u['barras']}
        assert len(orden) == len(u['barras']), 'dos barras en el mismo sitio del unifilar'


def test_111_rf23_el_unifilar_no_toca_vertices_ni_datos(tmp_path):
    d = _disposicion()
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    for _modelo, v in _vistas(tmp_path, seed):
        sin = {k: val for k, val in v.items() if k != 'unifilar'}
        antes = copy.deepcopy(sin)
        assert d.unifilar_de_vista(sin) == v['unifilar'], f'semilla={seed}'
        assert sin == antes, f'el unifilar cambió la vista (vértices o datos), semilla={seed}'


def test_111_rf23_el_contrato_de_la_vista_declara_el_unifilar():
    from convertersmartgrid.presentacion.web import api_contract as c
    campos = c.VistaPlanoRespuesta.model_fields
    assert 'unifilar' in campos and 'fuente' in campos, 'el contrato de la API no declara el unifilar (111:RF-23)'
    assert set(c.UnifilarPlanoRespuesta.model_fields) >= {'fuente', 'barras', 'niveles', 'ancho', 'sin_alcanzar'}
