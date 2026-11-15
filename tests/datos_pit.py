"""Spec 107 — dos casos sintéticos del PIT, sorteados con semilla (107:RF-11).

Ningún número de área, titular, tensión ni año está fijo: todo sale del sorteo, y las pruebas leen lo que necesitan
de las pistas que devuelve el caso (``caso['pistas']``), nunca de una constante.

- **A**: un área con un titular, SET radiales con transformadores de dos devanados, una línea de media tensión fuera
  de las SET (no entra en el ámbito) y todos los datos.
- **B**: varios titulares, un transformador de tres devanados en cabecera, un anillo de SET (su N-1 no deja carga sin
  servir), una SET radial colgada del anillo, una línea compartida con otra área y sin asignar, una línea de enlace
  sin parámetros, una compensación capacitiva, un año sin demanda proyectada y un elemento solo de otra área.
"""
from __future__ import annotations

import random

__all__ = ['perfil_a', 'perfil_b']


def _linea(id_, desde, hasta, kv, area, titular, rng, *, areas=None, km=None):
    return {'id': id_, 'tipo': 'linea', 'desde': desde, 'hasta': hasta, 'kv': kv, 'areas': areas or [area],
            'titular': titular, 'longitud_km': km or round(rng.uniform(4, 25), 2),
            'r_ohm_per_km': round(rng.uniform(0.08, 0.2), 4), 'x_ohm_per_km': round(rng.uniform(0.35, 0.45), 4),
            'c_nf_per_km': round(rng.uniform(8, 11), 2), 'max_i_ka': round(rng.uniform(0.35, 0.6), 3)}


def _trafo2(id_, set_, hv, lv, kv_hv, kv_lv, mva, area, titular, rng):
    return {'id': id_, 'tipo': 'trafo2', 'set': set_, 'hv': hv, 'lv': lv, 'areas': [area], 'titular': titular,
            'kv': kv_hv, 'sn_mva': mva, 'vn_hv_kv': kv_hv, 'vn_lv_kv': kv_lv,
            'vk_percent': round(rng.uniform(8, 11), 2), 'vkr_percent': round(rng.uniform(0.3, 0.6), 2),
            'pfe_kw': round(rng.uniform(10, 25), 1), 'i0_percent': round(rng.uniform(0.05, 0.2), 3)}


def _barra(id_, kv, area, titular, *, set_=None, rol=''):
    return {'id': id_, 'tipo': 'barra', 'kv': kv, 'set': set_, 'rol': rol, 'areas': [area], 'titular': titular}


def _proyeccion(set_alim, anios, mva_set, rng, *, sin=()):
    """P y Q por alimentador y año; la demanda de cada SET queda entre el 30 % y el 60 % de su transformación."""
    filas = []
    for set_, alims in set_alim.items():
        base = mva_set[set_] * rng.uniform(0.3, 0.45) * 1000 / len(alims)
        crec = rng.uniform(0.02, 0.05)
        for k, anio in enumerate(anios):
            if anio in sin:
                continue
            for a in alims:
                p = base * (1 + crec) ** k
                filas.append({'alimentador': a, 'anio_calendario': anio, 'p_kw': round(p, 1),
                              'q_kvar': round(p * 0.33, 1)})
    return filas


def _comun(seed):
    rng = random.Random(seed)
    area = f'AD-{rng.randint(10, 99)}'
    otra = f'AD-{rng.randint(100, 199)}'
    kv_at = rng.choice((60.0, 66.0, 69.0))
    kv_mt = rng.choice((10.0, 13.8, 22.9))
    inicio = rng.randint(2031, 2045)
    anios = list(range(inicio, inicio + rng.randint(3, 5)))
    return rng, area, otra, kv_at, kv_mt, anios


def perfil_a(seed: int) -> dict:
    """Un titular, SET radiales con transformadores de dos devanados."""
    rng, area, otra, kv_at, kv_mt, anios = _comun(seed)
    titular = f'TIT-{rng.randint(1, 50)}'
    n_set = rng.randint(2, 4)
    sets = [f'S{rng.randint(100, 999)}{i}' for i in range(n_set)]
    fuente = f'B-{area}-fuente'
    el = [_barra(fuente, kv_at, area, titular),
          {'id': f'RE-{area}', 'tipo': 'red_externa', 'barra': fuente, 'vm_pu': 1.0, 'kv': kv_at, 'areas': [area],
           'titular': titular}]
    set_alim, mva = {}, {}
    for s in sets:
        at, mt = f'B-{s}-AT', f'B-{s}-MT'
        mva[s] = rng.choice((15.0, 25.0, 30.0))
        el += [_barra(at, kv_at, area, titular, set_=s), _barra(mt, kv_mt, area, titular, set_=s, rol='carga'),
               _linea(f'L-{s}', fuente, at, kv_at, area, titular, rng),
               _trafo2(f'T-{s}', s, at, mt, kv_at, kv_mt, mva[s], area, titular, rng),
               {'id': f'C-{s}', 'tipo': 'celda', 'set': s, 'kv': kv_mt, 'areas': [area], 'titular': titular,
                'funcion': 'alimentador'}]
        set_alim[s] = [f'{s}-A{j}' for j in range(rng.randint(1, 3))]
    # Una línea de media tensión del área fuera de las SET: no es del ámbito del PIT.
    el.append({**_linea(f'LMT-{area}', f'B-{sets[0]}-MT', f'B-{sets[0]}-MTx', kv_mt, area, titular, rng),
               'set': None})
    perfil = {'pit': {'areas': [{'codigo': area, 'titulares': [titular], 'set': sets, 'set_alimentadores': set_alim,
                                 'tension_min_kv': kv_at, 'compartidos': {}}]}}
    return {'perfil': perfil, 'elementos': el, 'proyeccion': _proyeccion(set_alim, anios, mva, rng), 'anios': anios,
            'area': area, 'pistas': {'titulares': [titular], 'sets': sets, 'fuera_por_tension': f'LMT-{area}',
                                     'radiales': [f'L-{s}' for s in sets]}}


def perfil_b(seed: int) -> dict:
    """Varios titulares, tres devanados en cabecera, anillo, compartido, línea sin parámetros y año sin demanda."""
    rng, area, otra, kv_at, kv_mt, anios = _comun(seed)
    titulares = sorted({f'TIT-{rng.randint(1, 50)}' for _ in range(5)})[:3]
    while len(titulares) < 2:
        titulares.append(f'TIT-{rng.randint(51, 99)}')
    kv_ext = rng.choice((138.0, 220.0))
    kv_ter = rng.choice((10.0, 13.8))
    n_anillo = rng.randint(3, 4)
    sets = [f'S{rng.randint(100, 999)}{i}' for i in range(n_anillo + 2)]
    cab, radial, anillo = sets[0], sets[-1], sets[1:-1]
    tit = {s: titulares[i % len(titulares)] for i, s in enumerate(sets)}
    ext, at_cab, ter = f'B-{cab}-EXT', f'B-{cab}-AT', f'B-{cab}-TER'
    el = [_barra(ext, kv_ext, area, tit[cab], set_=cab), _barra(at_cab, kv_at, area, tit[cab], set_=cab),
          _barra(ter, kv_ter, area, tit[cab], set_=cab),
          {'id': f'RE-{area}', 'tipo': 'red_externa', 'barra': ext, 'vm_pu': 1.0, 'kv': kv_ext, 'areas': [area],
           'titular': tit[cab]},
          {'id': f'T3-{cab}', 'tipo': 'trafo3', 'set': cab, 'hv': ext, 'mv': at_cab, 'lv': ter, 'areas': [area],
           'titular': tit[cab], 'kv': kv_ext, 'sn_hv_mva': 120.0, 'sn_mv_mva': 120.0, 'sn_lv_mva': 40.0,
           'vn_hv_kv': kv_ext, 'vn_mv_kv': kv_at, 'vn_lv_kv': kv_ter, 'vk_hv_percent': 10.5,
           'vk_mv_percent': 7.0, 'vk_lv_percent': 6.5, 'vkr_hv_percent': 0.3, 'vkr_mv_percent': 0.3,
           'vkr_lv_percent': 0.3, 'pfe_kw': 60.0, 'i0_percent': 0.08}]
    set_alim, mva = {}, {}
    for s in anillo + [radial]:
        at, mt = f'B-{s}-AT', f'B-{s}-MT'
        mva[s] = rng.choice((15.0, 25.0))
        el += [_barra(at, kv_at, area, tit[s], set_=s), _barra(mt, kv_mt, area, tit[s], set_=s, rol='carga'),
               _trafo2(f'T-{s}', s, at, mt, kv_at, kv_mt, mva[s], area, tit[s], rng),
               {'id': f'C-{s}', 'tipo': 'celda', 'set': s, 'kv': kv_at, 'areas': [area], 'titular': tit[s],
                'funcion': 'linea'}]
        set_alim[s] = [f'{s}-A{j}' for j in range(rng.randint(1, 3))]
    nodos = [at_cab] + [f'B-{s}-AT' for s in anillo] + [at_cab]
    lineas_anillo = []
    for i, (a, b) in enumerate(zip(nodos, nodos[1:])):
        lid = f'LA-{area}-{i}'
        lineas_anillo.append(lid)
        el.append({**_linea(lid, a, b, kv_at, area, tit[cab], rng), 'max_i_ka': 0.9})
    radial_linea = f'LR-{radial}'
    el.append(_linea(radial_linea, f'B-{anillo[0]}-AT', f'B-{radial}-AT', kv_at, area, tit[radial], rng))
    compartida = f'LX-{area}-{otra}'
    el.append({**_linea(compartida, f'B-{anillo[-1]}-AT', at_cab, kv_at, area, tit[cab], rng,
                        areas=[area, otra]), 'max_i_ka': 0.9})
    sin_param = f'LE-{area}'
    el.append({'id': sin_param, 'tipo': 'linea', 'desde': f'B-{anillo[0]}-AT', 'hasta': f'B-{anillo[1]}-AT',
               'kv': kv_at, 'areas': [area], 'titular': tit[anillo[0]], 'longitud_km': 3.0})
    el.append({'id': f'Q-{anillo[0]}', 'tipo': 'compensacion', 'set': anillo[0], 'barra': f'B-{anillo[0]}-MT',
               'q_mvar': rng.choice((2.0, 3.0)), 'kv': kv_mt, 'areas': [area], 'titular': tit[anillo[0]]})
    solo_otra = f'L-{otra}'
    el.append({**_linea(solo_otra, f'B-{otra}-1', f'B-{otra}-2', kv_at, otra, 'TIT-otra', rng)})
    sin_demanda = anios[rng.randrange(1, len(anios))]
    perfil = {'pit': {'areas': [
        {'codigo': area, 'titulares': titulares, 'set': sets, 'set_alimentadores': set_alim,
         'tension_min_kv': kv_at, 'compartidos': {}},
        {'codigo': otra, 'titulares': ['TIT-otra'], 'set': [], 'set_alimentadores': {}, 'tension_min_kv': kv_at,
         'compartidos': {}}]}}
    return {'perfil': perfil, 'elementos': el, 'proyeccion': _proyeccion(set_alim, anios, mva, rng, sin=(sin_demanda,)),
            'anios': anios, 'area': area,
            'pistas': {'titulares': titulares, 'sets': sets, 'otra_area': otra, 'compartida': compartida,
                       'sin_parametros': sin_param, 'solo_otra': solo_otra, 'anio_sin_demanda': sin_demanda,
                       'anillo': lineas_anillo, 'radial': radial_linea, 'trafo3': f'T3-{cab}',
                       'titular_de_set': tit}}
