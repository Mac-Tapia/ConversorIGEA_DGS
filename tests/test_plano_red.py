"""Spec 111: el plano de la red. Identidad de cada elemento por su código de la fuente, cruce con el nombre en DIgSILENT,
revisión de la red y vista del plano con todos los vértices de la fuente (111:RF-1, RF-2, RF-3, RF-11).

Exports sintéticos sorteados (``ExportSpec(seed=…)``), con las dos disposiciones y dos CRS de origen distintos.
"""
from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import json
import random

import pytest

from convertersmartgrid import dgs
from convertersmartgrid.geography import build_geography, geography_to_dict
from convertersmartgrid.model import Node, build_feeder_model
from synthetic_export import CRS_SINTETICO, ExportSpec, load_export

LAYOUTS = ('reducido', 'completo')
#: Dos perfiles sintéticos con CRS de origen distintos (P13): ningún CRS de una empresa.
CRS_PERFILES = (CRS_SINTETICO, 'EPSG:32718')


def _plano_red():
    assert importlib.util.find_spec('convertersmartgrid.plano_red') is not None, 'falta convertersmartgrid.plano_red'
    return importlib.import_module('convertersmartgrid.plano_red')


def _semilla() -> int:
    return random.SystemRandom().randrange(1, 2 ** 31)


def _red(tmp_path, layout='reducido', crs=CRS_SINTETICO, seed=None, **kw):
    """[(modelo, geografía en dict)] de un export sintético sorteado."""
    seed = _semilla() if seed is None else seed
    n = random.Random(seed).randint(2, 5)
    spec = ExportSpec(feeders=n, seed=seed, layout=layout, **kw)
    ds = load_export(spec, tmp_path / f'{layout}_{seed}')
    salida = []
    for net in ds.feeder_ids():
        modelo = build_feeder_model(ds, net, strict=True, include_geography=True)
        geo = build_geography(ds, modelo, source_crs=crs)
        salida.append((modelo, geography_to_dict(geo, modelo)))
    assert salida, f'semilla={seed}'
    print(f'semilla={seed}')        # lección B6: sale en el informe de cualquier fallo de la prueba que la use
    return salida


def _uno(elementos, que: str):
    """Lección B6: el elemento buscado, o un fallo que dice cuál falta (la semilla va impresa por ``_red``)."""
    x = next(elementos, None)
    assert x is not None, f'{que}: no está en la red sorteada (la semilla va en la salida de la prueba)'
    return x


# ----------------------------------------------------------------------------------------- identidad (T3)

def test_111_rf2_nombre_en_pf_es_el_mismo_nombre_que_el_dgs():
    """111:RF-2 — ``dgs.nombre_en_pf`` es el nombre público del ``loc_name`` del DGS, igual sobre identificadores
    sorteados con tildes, espacios y por encima del límite de 40 caracteres."""
    assert hasattr(dgs, 'nombre_en_pf'), 'falta dgs.nombre_en_pf'
    azar = random.Random(_semilla())
    letras = 'abcñáéíóúüABCÑÁÉ _-./0123456789'
    for _ in range(300):
        valor = ''.join(azar.choice(letras) for _ in range(azar.randint(1, 70)))
        assert dgs.nombre_en_pf(valor) == dgs._loc_name(valor), valor
    assert len(dgs.nombre_en_pf('x' * 90)) == 40


def test_111_rf2_nombre_en_pf_no_cambia_ningun_dgs(tmp_path, monkeypatch):
    """111:RF-2 — el DGS no pasa por el alias: con ``nombre_en_pf`` roto, el DGS sintético sale idéntico byte a byte, y
    cada barra y tramo del DGS lleva el nombre que da ``nombre_en_pf`` a su código."""
    assert hasattr(dgs, 'nombre_en_pf'), 'falta dgs.nombre_en_pf'
    modelo, _geo = _red(tmp_path)[0]
    antes = tmp_path / 'antes.dgs'
    dgs.write_dgs(modelo, antes)

    def _roto(_valor):
        raise AssertionError('el DGS no puede llamar al alias')

    monkeypatch.setattr(dgs, 'nombre_en_pf', _roto)
    despues = tmp_path / 'despues.dgs'
    dgs.write_dgs(modelo, despues)
    monkeypatch.undo()
    assert antes.read_bytes() == despues.read_bytes()
    texto = antes.read_text(encoding='utf-8', errors='replace')
    for codigo in list(modelo.nodes)[:5] + [ln.section_id for ln in modelo.lines[:5]]:
        assert dgs.nombre_en_pf(codigo) in texto, codigo


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf2_identidad_un_codigo_de_la_fuente_por_elemento(tmp_path, layout):
    """111:RF-2 — cada barra, tramo, SED y maniobra sale una vez, con su código de la fuente y su nombre en DIgSILENT."""
    plano_red = _plano_red()
    assert hasattr(plano_red, 'identidad'), 'falta plano_red.identidad'
    for modelo, _geo in _red(tmp_path, layout):
        ident = plano_red.identidad(modelo)
        por_tipo = {}
        for e in ident['elementos']:
            por_tipo.setdefault(e['tipo'], []).append(e)
        assert sorted(e['codigo'] for e in por_tipo['barra']) == sorted(modelo.nodes)
        assert sorted(e['codigo'] for e in por_tipo['tramo']) == sorted(ln.section_id for ln in modelo.lines)
        assert len(por_tipo.get('sed', [])) == len(modelo.seds)
        assert len(por_tipo.get('maniobra', [])) == len(modelo.devices)
        for e in por_tipo['barra'] + por_tipo['tramo']:
            assert e['nombre_pf'] == dgs.nombre_en_pf(e['codigo'])
        assert ident['colisiones'] == []
        for e in por_tipo['tramo']:
            assert plano_red.codigo_de_nombre(ident, 'tramo', e['nombre_pf']) == e['codigo']


def test_111_rf2_dos_codigos_con_el_mismo_nombre_se_avisan_y_no_se_cruzan(tmp_path):
    """111:RF-2 — dos códigos que dan el mismo nombre en DIgSILENT (recortado a 40) se avisan, y ese nombre no se
    traduce a ninguno de los dos: un resultado nunca se pinta en otro elemento."""
    plano_red = _plano_red()
    assert hasattr(plano_red, 'identidad'), 'falta plano_red.identidad'
    modelo, _geo = _red(tmp_path)[0]
    base = 'N' * 40
    nodos = {**modelo.nodes, f'{base}_A': Node(f'{base}_A', 0.0, 0.0), f'{base}_B': Node(f'{base}_B', 0.0, 0.0)}
    ident = plano_red.identidad(dataclasses.replace(modelo, nodes=nodos))
    colision = [c for c in ident['colisiones'] if c['tipo'] == 'barra']
    assert colision == [{'tipo': 'barra', 'nombre_pf': dgs.nombre_en_pf(f'{base}_A'),
                         'codigos': [f'{base}_A', f'{base}_B']}]
    assert plano_red.codigo_de_nombre(ident, 'barra', dgs.nombre_en_pf(f'{base}_A')) is None


# ------------------------------------------------------------------------------------------ revisión (T3)

def test_111_rf11_revision_de_la_red_por_ejecucion_y_geografia(tmp_path):
    """111:RF-11 — la revisión es la huella del ``run_id`` y de los manifiestos de geografía elegidos: igual con los
    mismos, sin depender del orden; distinta si cambia la ejecución o un solo byte de un manifiesto."""
    plano_red = _plano_red()
    assert hasattr(plano_red, 'revision_red'), 'falta plano_red.revision_red'
    rutas = {}
    for modelo, geo in _red(tmp_path):
        ruta = tmp_path / f'{modelo.name}_geography.json'
        ruta.write_text(json.dumps(geo), encoding='utf-8')
        rutas[modelo.name] = ruta
    r1 = plano_red.revision_red('run-1', rutas)
    assert r1 == plano_red.revision_red('run-1', dict(reversed(list(rutas.items()))))
    assert len(r1) == 64 and int(r1, 16) >= 0
    assert r1 != plano_red.revision_red('run-2', rutas)
    primero = next(iter(rutas.values()))
    primero.write_bytes(primero.read_bytes() + b' ')
    assert r1 != plano_red.revision_red('run-1', rutas)


# ----------------------------------------------------------------------------------------- vista (T4)

def _vista_disponible():
    plano_red = _plano_red()
    assert hasattr(plano_red, 'vista'), 'falta plano_red.vista'
    return plano_red


@pytest.mark.parametrize('crs', CRS_PERFILES)
@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf1_la_vista_lleva_todos_los_vertices_de_la_fuente(tmp_path, layout, crs):
    """111:RF-1 — cada tramo sale con la secuencia entera de vértices de su manifiesto de geografía, sin simplificar,
    con las dos disposiciones y dos CRS de origen."""
    plano_red = _vista_disponible()
    for modelo, geo in _red(tmp_path, layout, crs):
        v = plano_red.vista(modelo, geo)
        assert v['alimentador'] == modelo.name and v['source_crs'] == crs and not v['sin_coordenadas']
        por_codigo = {t['codigo']: t for t in v['tramos']}
        assert sorted(por_codigo) == sorted(geo['lines'])
        for sid, linea in geo['lines'].items():
            assert por_codigo[sid]['vertices'] == [[p['lat'], p['lon']] for p in linea['path']], sid
        assert sum(len(t['vertices']) for t in v['tramos']) == sum(len(x['path']) for x in geo['lines'].values())


@pytest.mark.parametrize('layout', LAYOUTS)
def test_111_rf2_la_vista_usa_el_mismo_codigo_que_la_identidad(tmp_path, layout):
    """111:RF-2 — tramos, barras, SED y maniobras de la vista llevan el código y el nombre de la identidad."""
    plano_red = _vista_disponible()
    for modelo, geo in _red(tmp_path, layout):
        v = plano_red.vista(modelo, geo)
        ident = {(e['tipo'], e['codigo']): e['nombre_pf'] for e in plano_red.identidad(modelo)['elementos']}
        for tipo, clave in (('tramo', 'tramos'), ('barra', 'barras'), ('sed', 'sed'), ('maniobra', 'maniobras')):
            for e in v[clave]:
                assert ident[(tipo, e['codigo'])] == e['nombre_pf'], (tipo, e['codigo'])
        assert len(v['maniobras']) == len(modelo.devices)
        assert {m['estado'] for m in v['maniobras']} <= {'abierto', 'cerrado'}


def test_111_rf3_cada_elemento_dice_su_dato_original_lo_deducido_y_su_calidad(tmp_path):
    """111:RF-3 — el dato original de la fuente, lo deducido con su regla y su motivo, y el estado de calidad."""
    plano_red = _vista_disponible()
    modelo, geo = _red(tmp_path)[0]
    tramo = modelo.lines[0]
    nodo = sorted(modelo.nodes)[-1]
    nodos = {**modelo.nodes, nodo: dataclasses.replace(modelo.nodes[nodo], coord_inferida=True)}
    modelo = dataclasses.replace(modelo, nodes=nodos)
    decision = {'entity_type': 'section', 'entity_id': tramo.section_id, 'field': 'phase', 'original_value': '',
                'applied_value': 'ABC', 'level': 'inferred', 'rule': 'fase_del_vecino',
                'reason': 'la fuente no trae la fase; se toma la del tramo anterior', 'confidence': 0.8}
    validacion = {'errors': [], 'warnings': [f'{tramo.section_id}: trazado con un vértice repetido']}
    v = plano_red.vista(modelo, geo, validacion=validacion, decisiones=[decision])
    t = _uno((x for x in v['tramos'] if x['codigo'] == tramo.section_id), f'el tramo {tramo.section_id}')
    assert t['original']['tipo'] == tramo.source_type_code
    assert t['original']['longitud_m'] == (tramo.txt_length_m if tramo.txt_length_m is not None else tramo.length_m)
    deducida = _uno((d for d in t['deducido'] if d['campo'] == 'phase'), 'la fase deducida')
    assert deducida['regla'] == 'fase_del_vecino' and deducida['motivo'] and deducida['valor'] == 'ABC'
    assert t['calidad'] == 'aviso' and t['avisos'] == ['trazado con un vértice repetido']
    b = _uno((x for x in v['barras'] if x['codigo'] == nodo), f'la barra {nodo}')
    assert any(d['campo'] == 'coordenadas' and d['motivo'] for d in b['deducido'])
    assert all(x['calidad'] == 'ok' for x in v['tramos'] if x['codigo'] != tramo.section_id)


def test_111_rf2_una_doble_terna_son_dos_elementos_en_el_mismo_trazo(tmp_path):
    """111:RF-2 — dos tramos entre los mismos nodos salen como dos elementos, cada uno con su código, y cada uno dice
    con cuál comparte el trazo."""
    plano_red = _vista_disponible()
    modelo, geo = _red(tmp_path)[0]
    tramo = modelo.lines[0]
    gemelo = dataclasses.replace(tramo, section_id=f'{tramo.section_id}_T2')
    modelo = dataclasses.replace(modelo, lines=[*modelo.lines, gemelo])
    geo = {**geo, 'lines': {**geo['lines'], gemelo.section_id: geo['lines'][tramo.section_id]}}
    v = plano_red.vista(modelo, geo)
    t1 = _uno((x for x in v['tramos'] if x['codigo'] == tramo.section_id), f'el tramo {tramo.section_id}')
    t2 = _uno((x for x in v['tramos'] if x['codigo'] == gemelo.section_id), f'el tramo {gemelo.section_id}')
    assert t1['vertices'] == t2['vertices']
    assert t1['paralelo_con'] == [gemelo.section_id] and t2['paralelo_con'] == [tramo.section_id]


def test_111_rf1_un_alimentador_sin_coordenadas_se_lista_y_no_se_pinta(tmp_path):
    """111:RF-1 — sin geografía, el alimentador sale en la lista, sin vértices que pintar, y el plano lo dice."""
    plano_red = _vista_disponible()
    (m1, g1), (m2, _g2) = _red(tmp_path)[:2]
    v1, v2 = plano_red.vista(m1, g1), plano_red.vista(m2, None)
    assert v2['sin_coordenadas'] and all(t['vertices'] == [] and t['calidad'] == 'sin_coordenadas' for t in v2['tramos'])
    assert len(v2['tramos']) == len(m2.lines)
    plano = plano_red.resumen_plano([v1, v2])
    assert plano['alimentadores'] == [m1.name, m2.name] and plano['sin_coordenadas'] == [m2.name]
