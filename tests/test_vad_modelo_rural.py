"""Spec 108 T5 — modelo georreferenciado rural del Anexo 6: la red real, sin mover un vértice (108:RF-5).

Dos empresas sintéticas sorteadas por semilla, con nombres neutros: alimentadores con MT de 10 o 22,9 kV, SED con su
potencia y redes de BT que cuelgan de ellas, en un UTM cualquiera. La vía TXT usa el export sintético en sus dos
disposiciones. Nada de datos reales ni códigos de una empresa.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import random
from pathlib import Path

import pytest

from convertersmartgrid.adaptadores.entrada.vnr.gis.geometry import (
    coords_from_geojson,
    polyline_length_m,
)
from convertersmartgrid.adaptadores.entrada.vnr.models.canonical import (
    CanonicalModel,
    Feeder,
    Section,
    Source,
    System,
    Transformer,
)
from convertersmartgrid.registro_normativo import RegistroNormativo, cargar_registro
from convertersmartgrid.vad import VadError
from convertersmartgrid.vad.modelo_rural import (
    SIN_MODELAR_URBANO,
    armar_modelo_rural,
    comprobar_trazas,
    hash_vertices,
)

RAIZ = Path(__file__).resolve().parents[1]
VAD = RAIZ / 'config' / 'vad'
SEMILLAS = (7, 2026, 644573672)
EMPRESAS = ('EMPRESA_A', 'EMPRESA_B')
LAYOUTS = ('reducido', 'completo')
CRS = 'EPSG:32719'
DESPLAZAMIENTO = 1e-9
ACTO = 'tdr-vad-2026-anexo-r033'


@pytest.fixture(scope='module')
def registro():
    return cargar_registro(VAD)


def _punto(rng: random.Random, cerca: tuple[float, float] | None = None, paso: float = 400.0) -> tuple[float, float]:
    """Un punto del UTM sintético; con la norte por debajo de 2**23 un desplazamiento de 1e-9 siempre se ve."""
    if cerca is None:
        return rng.uniform(250_000.0, 750_000.0), rng.uniform(8_000_000.0, 8_300_000.0)
    return cerca[0] + rng.uniform(-paso, paso), cerca[1] + rng.uniform(-paso, paso)


def _linea(rng, a, b, intermedios):
    pts = [a] + [_punto(rng, a, 150.0) for _ in range(intermedios)] + [b]
    return {'type': 'LineString', 'coordinates': [list(p) for p in pts]}


def _vnr(semilla: int, empresa: str) -> CanonicalModel:
    """VNR canónico sintético de una empresa: 2 a 4 alimentadores en dos sistemas, con MT, SED y BT sorteadas."""
    rng = random.Random(f'{empresa}|{semilla}')
    m = CanonicalModel(metadata={'crs': CRS})
    alimentadores = rng.randint(2, 4)
    for s in ('S1', 'S2'):
        m.systems.append(System(f'{empresa}_{s}', company_id=empresa))
    bt_sin_traza = rng.randrange(alimentadores)
    for i in range(alimentadores):
        alim = f'{empresa}_AL{i + 1}'
        sistema = f'{empresa}_S{1 if i < max(2, alimentadores - 1) else 2}'
        m.feeders.append(Feeder(alim, company_id=empresa, system_id=sistema))
        kv = rng.choice((10.0, 22.9))
        cabecera = f'{alim}_N0'
        m.sources.append(Source(f'{alim}_FU', cabecera, kv, feeder_id=alim))
        coords = {cabecera: _punto(rng)}
        nodos = [cabecera]
        for k in range(rng.randint(4, 12)):
            padre = rng.choice(nodos)
            nuevo = f'{alim}_N{k + 1}'
            coords[nuevo] = _punto(rng, coords[padre])
            geom = _linea(rng, coords[padre], coords[nuevo], rng.randint(0, 3))
            largo = polyline_length_m(coords_from_geojson(geom))
            m.sections.append(Section(f'{alim}_MT{k + 1}', padre, nuevo, phases=rng.choice(('ABC', 'A', 'AB')),
                                      nominal_kv=kv, length_m=largo, geometry=geom, feeder_id=alim))
            nodos.append(nuevo)
        seds = rng.sample(nodos[1:], k=min(len(nodos) - 1, rng.randint(1, 3)))
        for j, nodo in enumerate(sorted(seds)):
            m.transformers.append(Transformer(f'{alim}_SED{j + 1}', nodo, kv, 0.38,
                                              rng.choice((10.0, 25.0, 37.5, 50.0, 75.0, 160.0))))
            bt_nodos = [nodo]
            for b in range(rng.randint(1, 4)):
                padre = rng.choice(bt_nodos)
                nuevo = f'{alim}_SED{j + 1}_B{b + 1}'
                coords[nuevo] = _punto(rng, coords[padre], 60.0)
                geom = _linea(rng, coords[padre], coords[nuevo], rng.randint(0, 2))
                largo = polyline_length_m(coords_from_geojson(geom))
                sin_traza = i == bt_sin_traza and j == 0 and b == 0
                m.sections.append(Section(f'{alim}_SED{j + 1}_BT{b + 1}', padre, nuevo, phases='ABC',
                                          nominal_kv=0.38, length_m=largo, geometry=None if sin_traza else geom,
                                          feeder_id=alim))
                bt_nodos.append(nuevo)
    return m


def _distancias(tramos, cabecera):
    """Distancia a cada nodo por el árbol, recorrida en la prueba sin ``troncal``."""
    vecinos = {}
    for t in tramos:
        vecinos.setdefault(t.desde, []).append((t.hasta, t.longitud_m))
        vecinos.setdefault(t.hasta, []).append((t.desde, t.longitud_m))
    dist, pila = {cabecera: 0.0}, [cabecera]
    while pila:
        u = pila.pop()
        for v, largo in vecinos.get(u, ()):
            if v not in dist:
                dist[v] = dist[u] + largo
                pila.append(v)
    return dist


def _mover(vertices, i):
    x, y = vertices[i]
    movido = x + DESPLAZAMIENTO
    assert movido != x, 'el sorteo dejó una x en la que 1e-9 no cambia el float'
    return vertices[:i] + ((movido, y),) + vertices[i + 1:]


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_la_huella_de_cada_tramo_es_la_del_vnr(registro, semilla, empresa):
    """108:RF-5 — cada tramo del modelo lleva, bit a bit, los vértices, la longitud y la huella del VNR, y las SED reales."""
    vnr = _vnr(semilla, empresa)
    modelo = armar_modelo_rural(vnr, registro=registro)
    assert modelo.fuente == 'vnr' and modelo.crs_origen == CRS
    assert modelo.fundamento == registro.regla('vad.anexo6.traza_real').huella()
    assert len(modelo.tramos) == len(vnr.sections)
    for s in vnr.sections:
        t = modelo.tramo(s.section_id)
        esperados = tuple(coords_from_geojson(s.geometry)) if s.geometry else ()
        assert t.vertices == esperados
        assert t.huella == (hash_vertices(esperados) if esperados else '')
        assert t.longitud_m == s.length_m and t.longitud_origen == 'fuente'
        assert t.nivel == ('BT' if s.nominal_kv < 1 else 'MT')
    assert {(x.sed, x.kva) for x in modelo.sed} == {(x.transformer_id, x.sn_kva) for x in vnr.transformers}
    comprobar_trazas(modelo, vnr)


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_troncal_y_derivaciones_por_alimentador(registro, semilla, empresa):
    """108:RF-5 — la troncal es el camino más largo desde la cabecera, y el resto de la MT son derivaciones."""
    vnr = _vnr(semilla, empresa)
    modelo = armar_modelo_rural(vnr, registro=registro)
    for fu in vnr.sources:
        mt = [t for t in modelo.tramos if t.alimentador == fu.feeder_id and t.nivel == 'MT']
        assert {t.clase for t in mt} <= {'troncal', 'derivacion'}
        dist = _distancias(mt, fu.node_id)
        troncal = [t for t in mt if t.clase == 'troncal']
        assert troncal, fu.feeder_id
        assert math.isclose(sum(t.longitud_m for t in troncal), max(dist.values()), rel_tol=1e-12)
        km = modelo.km()
        assert math.isclose(km[(fu.feeder_id, 'MT', 'troncal')] * 1000.0, sum(t.longitud_m for t in troncal))
    for t in modelo.tramos:
        if t.nivel == 'BT':
            assert t.clase in {'troncal', 'derivacion'}, t.tramo


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_un_vertice_movido_1e9_cambia_la_huella_y_se_rechaza(registro, semilla, empresa):
    """108:RF-5 — mover un vértice 1e-9 cambia la huella; el modelo no lo acepta ni contra el VNR ni dentro de un tramo."""
    vnr = _vnr(semilla, empresa)
    modelo = armar_modelo_rural(vnr, registro=registro)
    rng = random.Random(semilla)
    con_traza = [s for s in vnr.sections if s.geometry]
    elegido = rng.choice(con_traza)
    tramo = modelo.tramo(elegido.section_id)
    assert tramo.vertices == tuple(coords_from_geojson(elegido.geometry))
    i = rng.randrange(len(tramo.vertices))
    movidos = _mover(tramo.vertices, i)
    assert hash_vertices(movidos) != tramo.huella

    with pytest.raises(VadError, match=elegido.section_id):
        dataclasses.replace(tramo, vertices=movidos)

    alterado = copy.deepcopy(vnr)
    seccion = next(s for s in alterado.sections if s.section_id == elegido.section_id)
    seccion.geometry = {'type': 'LineString', 'coordinates': [list(p) for p in movidos]}
    modelo_alterado = armar_modelo_rural(alterado, registro=registro)
    assert modelo_alterado.tramo(elegido.section_id).huella == hash_vertices(movidos)
    with pytest.raises(VadError, match=elegido.section_id):
        comprobar_trazas(modelo_alterado, vnr)
    with pytest.raises(VadError, match=elegido.section_id):
        comprobar_trazas(modelo, alterado)


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_bt_sin_geometria_se_nombra_sin_vertices_inventados(registro, semilla, empresa):
    """108:RF-5 — un tramo de BT sin geometría se nombra, no recibe vértices y el modelo no queda completo."""
    vnr = _vnr(semilla, empresa)
    sin_traza = sorted(s.section_id for s in vnr.sections if s.geometry is None)
    assert sin_traza, 'el sorteo tiene que traer un tramo de BT sin traza'
    modelo = armar_modelo_rural(vnr, registro=registro)
    assert modelo.sin_geometria == tuple(sin_traza)
    for nombre in sin_traza:
        t = modelo.tramo(nombre)
        assert t.nivel == 'BT' and t.vertices == () and t.huella == ''
        assert t.longitud_origen == 'fuente'
    assert not modelo.completo
    t = modelo.tramo(sin_traza[0])
    with pytest.raises(VadError, match=sin_traza[0]):
        dataclasses.replace(t, huella=hash_vertices(((0.0, 0.0), (1.0, 1.0))))


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_sistema_mixto_deja_la_parte_urbana_sin_modelar(registro, semilla, empresa):
    """108:RF-5 — en un sistema mixto, la parte urbana queda «sin modelar (anexo 5 pendiente)» y no entra en el modelo."""
    vnr = _vnr(semilla, empresa)
    rng = random.Random(f'mixto|{semilla}')
    s1 = [f.feeder_id for f in vnr.feeders if f.system_id == f'{empresa}_S1']
    assert len(s1) >= 2
    urbano = rng.choice(s1)
    ambito = {f.feeder_id: 'urbano' if f.feeder_id == urbano else 'rural' for f in vnr.feeders}
    modelo = armar_modelo_rural(vnr, registro=registro, ambito=ambito)
    assert dict(modelo.sin_modelar) == {urbano: SIN_MODELAR_URBANO}
    assert modelo.sistemas_mixtos == (f'{empresa}_S1',)
    assert all(t.alimentador != urbano for t in modelo.tramos)
    assert all(s.alimentador != urbano for s in modelo.sed)
    rurales = {s.section_id for s in vnr.sections if s.feeder_id != urbano}
    assert {t.tramo for t in modelo.tramos} == rurales
    assert not modelo.completo

    del ambito[urbano]
    with pytest.raises(VadError, match=urbano):
        armar_modelo_rural(vnr, registro=registro, ambito=ambito)


def test_sin_la_regla_del_anexo6_no_se_arma():
    """108:RF-5 — el modelo se apoya en la regla vad.anexo6.traza_real: sin ella en el registro, no se arma."""
    with pytest.raises(VadError, match='vad.anexo6.traza_real'):
        armar_modelo_rural(_vnr(SEMILLAS[0], EMPRESAS[0]), registro=RegistroNormativo())


def test_las_reglas_del_anexo6_amplian_el_tdr_con_su_cita(registro):
    """108:RF-5 — las 16 reglas del Anexo 6 amplían el TdR registrado, sin repetir vad.anexo6.trazas, y todas citan."""
    norma = registro.norma(ACTO)
    anexo6 = [r for r in norma.reglas if r.clave.startswith('vad.anexo6.')]
    assert len(anexo6) == 17
    assert sum(r.clave == 'vad.anexo6.trazas' for r in anexo6) == 1
    for r in anexo6:
        assert r.citada, r.clave
        if r.clave != 'vad.anexo6.trazas':
            primeras = [int(p.split('-')[0]) for p in r.lineas.replace(' ', '').split(';')]
            assert all(6317 <= n <= 6868 for n in primeras), r.clave
    sed = registro.regla('vad.anexo6.sed').regla
    assert sed.valor['trifasico_menor_5kVA_asigna_kVA'] == 10 and sed.valor['modulo_kVA'] == 300
    assert 'SICODI' in sed.interpretacion and 'no normalizadas' in sed.interpretacion


def _via_txt(tmp_path: Path, layout: str, semilla: int):
    from synthetic_export import CRS_SINTETICO, ExportSpec, load_export

    from convertersmartgrid.geography import build_geography
    from convertersmartgrid.model import build_feeder_model

    spec = ExportSpec(feeders=3, sections_per_feeder=6, loads_per_feeder=2, intermediate_per_section=3,
                      layout=layout, seed=semilla)
    ds = load_export(spec, tmp_path / f'export_{layout}_{semilla}')
    pares = []
    for nid in ds.feeder_ids():
        if not ds.feeders.get(nid):
            continue
        modelo = build_feeder_model(ds, nid, strict=True)
        pares.append((modelo, build_geography(ds, modelo, source_crs=CRS_SINTETICO)))
    return pares


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_via_txt_en_las_dos_disposiciones(registro, tmp_path, semilla):
    """108:RF-5 — por la vía TXT, la huella de cada tramo es la de su geografía, la misma en las dos disposiciones."""
    pytest.importorskip('pyproj')
    huellas = {}
    for layout in LAYOUTS:
        pares = _via_txt(tmp_path, layout, semilla)
        modelo = armar_modelo_rural(pares, registro=registro)
        assert modelo.fuente == 'txt'
        esperadas = {sid: hash_vertices([(p.x, p.y) for p in g.path]) for _, geo in pares
                     for sid, g in geo.lines.items()}
        assert {t.tramo: t.huella for t in modelo.tramos} == esperadas
        assert any(len(t.vertices) > 2 for t in modelo.tramos), 'sin puntos intermedios no se prueba la traza'
        for fm, _ in pares:
            mt = [t for t in modelo.tramos if t.alimentador == fm.name]
            assert {t.clase for t in mt} <= {'troncal', 'derivacion'} and any(t.clase == 'troncal' for t in mt)
        comprobar_trazas(modelo, pares)
        huellas[layout] = esperadas

        fm, geo = pares[0]
        sid = min(geo.lines)
        linea = geo.lines[sid]
        i = len(linea.path) // 2
        movido = dataclasses.replace(linea.path[i], x=linea.path[i].x + DESPLAZAMIENTO)
        assert movido.x != linea.path[i].x
        lineas = dict(geo.lines)
        lineas[sid] = dataclasses.replace(linea, path=linea.path[:i] + (movido,) + linea.path[i + 1:])
        alterados = [(fm, dataclasses.replace(geo, lines=lineas))] + pares[1:]
        with pytest.raises(VadError, match=sid):
            comprobar_trazas(modelo, alterados)

        sin = dict(geo.lines)
        del sin[sid]
        sin_traza = armar_modelo_rural([(fm, dataclasses.replace(geo, lines=sin))] + pares[1:], registro=registro)
        assert sin_traza.sin_geometria == (sid,)
        assert sin_traza.tramo(sid).vertices == () and not sin_traza.completo
    # La disposición completa trae además los tramos de las SED; los comunes tienen la misma traza.
    reducido, completo = huellas['reducido'], huellas['completo']
    assert reducido and set(reducido) <= set(completo)
    assert {sid: completo[sid] for sid in reducido} == reducido
