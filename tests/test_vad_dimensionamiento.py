"""Spec 108 T6 — dimensionamiento de la empresa modelo con el motor físico sobre la traza real (108:RF-7).

Dos empresas sintéticas sorteadas por semilla, con nombres neutros: alimentadores de MT a 10 o 22,9 kV con SED
sobredimensionadas, un catálogo de conductores sintético con sus rangos de corriente económica (el «sustento de la
empresa» del Anexo 6) y una tabla de potencias por sector típico y tipo de SED sintética, con su huella. Nada de datos
reales ni códigos de una empresa. El flujo es el de ``oraculo``, con pandapower.
"""
from __future__ import annotations

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
    ConductorType,
    Feeder,
    Section,
    Source,
    System,
    Transformer,
)
from convertersmartgrid.adaptadores.informes import (
    HORAS_ANIO,
    coeficientes_factor_de_perdidas,
    factor_de_perdidas,
)
from convertersmartgrid.dominio.registro_normativo import RegistroNormativo, cargar_registro
from convertersmartgrid.aplicacion.vad import VadError
from convertersmartgrid.adaptadores.vad.dimensionamiento import (
    DemandaSed,
    RangoEconomico,
    TablaTransformadores,
    dimensionar,
)
from convertersmartgrid.adaptadores.vad.modelo_rural import armar_modelo_rural, comprobar_trazas

pytest.importorskip('pandapower')

RAIZ = Path(__file__).resolve().parents[1]
VAD = RAIZ / 'config' / 'vad'
SEMILLAS = (7, 2026, 644573672)
EMPRESAS = ('EMPRESA_A', 'EMPRESA_B')
CRS = 'EPSG:32719'
#: Las reglas en que se apoya el dimensionamiento, escritas aquí y no importadas: la prueba fija el contrato.
REGLAS = ('vad.anexo6.sed', 'vad.anexo6.mt.calibre_economico', 'vad.anexo6.mt.fases_y_material',
          'vad.anexo6.mt.caida_tension_max', 'vad.anexo6.mt.tensiones_y_secciones', 'vad.anexo6.bt',
          'vad.anexo6.terceros')
#: «Para puntos trifásicos con potencias menores a 5 kVA» (Anexo 6-10, línea 6796): el umbral es el dato
#: trifasico_umbral_kVA de la regla (T7), no el nombre de la clave.
UMBRAL_TRIFASICO = 5.0
KVA_REALES = (100.0, 160.0, 250.0)
SECTORES = ('ST_SINT_A', 'ST_SINT_B')
TIPOS = ('TIPO_SINT_1', 'TIPO_SINT_2')
POTENCIAS = (5.0, 10.0, 15.0, 25.0, 37.0, 50.0, 75.0, 100.0, 160.0, 250.0, 300.0, 400.0)
NO_NORMALIZADAS = frozenset({37.0})
HUELLA_TABLA = 'f' * 64
SUSTENTO = 'hoja sintética de corriente económica'

#: (código, material, sección mm², R1, X1, ampacidad A). El de 16 mm² de Al queda bajo la sección mínima del Anexo, y
#: el de 95 mm² no trae X1: ninguno de los dos se puede elegir.
CONDUCTORES = (
    ('CND_AL_16', 'Al', 16.0, 1.91, 0.45, 90.0),
    ('CND_AL_25', 'Al', 25.0, 1.20, 0.44, 120.0),
    ('CND_AL_35', 'Al', 35.0, 0.87, 0.43, 150.0),
    ('CND_AL_50', 'Al', 50.0, 0.64, 0.42, 180.0),
    ('CND_AL_70', 'Al', 70.0, 0.44, 0.41, 230.0),
    ('CND_AL_95', 'Al', 95.0, 0.32, None, 280.0),
    ('CND_AL_120', 'Al', 120.0, 0.25, 0.39, 330.0),
    ('CND_CU_16', 'Cu', 16.0, 1.15, 0.44, 130.0),
    ('CND_CU_35', 'Cu', 35.0, 0.52, 0.42, 200.0),
)
#: Rangos estrechos a propósito: las corrientes de la red sintética (de décimas a unas decenas de A) caen en varios.
RANGOS = (
    ('CND_AL_16', 0.0, 0.5), ('CND_AL_25', 0.0, 0.5), ('CND_AL_35', 0.5, 1.5), ('CND_AL_50', 1.5, 3.0),
    ('CND_AL_70', 3.0, 6.0), ('CND_AL_95', 6.0, 12.0), ('CND_AL_120', 6.0, 400.0),
    ('CND_CU_16', 0.0, 1.5), ('CND_CU_35', 1.5, 400.0),
)
REALES = ('CND_AL_25', 'CND_AL_35', 'CND_AL_50', 'CND_AL_70')


@pytest.fixture(scope='module')
def registro():
    return cargar_registro(VAD)


def _punto(rng, cerca=None, paso=400.0):
    if cerca is None:
        return rng.uniform(250_000.0, 750_000.0), rng.uniform(8_000_000.0, 8_300_000.0)
    return cerca[0] + rng.uniform(-paso, paso), cerca[1] + rng.uniform(-paso, paso)


def _vnr(semilla: int, empresa: str) -> CanonicalModel:
    """VNR sintético: 2 a 4 alimentadores, 2 o 3 SED cada uno, con kVA reales muy por encima de su demanda."""
    rng = random.Random(f'dim|{empresa}|{semilla}')
    m = CanonicalModel(metadata={'crs': CRS})
    m.systems.append(System(f'{empresa}_S1', company_id=empresa))
    for c in CONDUCTORES:
        m.conductor_types.append(ConductorType(c[0], material=c[1], section_mm2=c[2], r1_ohm_km=c[3],
                                               x1_ohm_km=c[4], ampacity_a=c[5]))
    for i in range(rng.randint(2, 4)):
        alim = f'{empresa}_AL{i + 1}'
        m.feeders.append(Feeder(alim, company_id=empresa, system_id=f'{empresa}_S1'))
        kv = rng.choice((10.0, 22.9))
        cabecera = f'{alim}_N0'
        m.sources.append(Source(f'{alim}_FU', cabecera, kv, feeder_id=alim))
        coords = {cabecera: _punto(rng)}
        nodos = [cabecera]
        for k in range(rng.randint(5, 10)):
            padre = rng.choice(nodos)
            nuevo = f'{alim}_N{k + 1}'
            coords[nuevo] = _punto(rng, coords[padre])
            pts = [coords[padre]] + [_punto(rng, coords[padre], 150.0) for _ in range(rng.randint(0, 3))]
            geom = {'type': 'LineString', 'coordinates': [list(p) for p in pts + [coords[nuevo]]]}
            m.sections.append(Section(f'{alim}_MT{k + 1}', padre, nuevo, conductor_code=rng.choice(REALES),
                                      phases=rng.choice(('ABC', 'ABC', 'A', 'AB')), nominal_kv=kv,
                                      length_m=polyline_length_m(coords_from_geojson(geom)), geometry=geom,
                                      feeder_id=alim))
            nodos.append(nuevo)
        for j, nodo in enumerate(sorted(rng.sample(nodos[1:], k=rng.randint(2, 3)))):
            m.transformers.append(Transformer(f'{alim}_SED{j + 1}', nodo, kv, 0.38, rng.choice(KVA_REALES)))
    return m


def _entradas(vnr: CanonicalModel, semilla: int) -> dict:
    """Lo que el dimensionamiento recibe además del modelo: demanda, tabla, rangos, sector y tipo, factor de carga."""
    rng = random.Random(f'entradas|{semilla}')
    fases_de_nodo = {s.to_node: s.phases for s in vnr.sections}
    demanda = {}
    for t in vnr.transformers:
        kw = rng.uniform(3.0, 50.0)
        fp = rng.uniform(0.85, 0.98)
        demanda[t.transformer_id] = DemandaSed(kw, kw * math.tan(math.acos(fp)), fases_de_nodo[t.connection_node],
                                               'caracterización sintética (T4)')
    return {
        'cabeceras': {s.feeder_id: s.node_id for s in vnr.sources},
        'conductor_de': {s.section_id: s.conductor_code for s in vnr.sections},
        'conductores': list(vnr.conductor_types),
        'rangos': [RangoEconomico(c, a, b, SUSTENTO) for c, a, b in RANGOS],
        'demanda': demanda,
        'tabla': TablaTransformadores({(s, t): POTENCIAS for s in SECTORES for t in TIPOS}, HUELLA_TABLA,
                                      NO_NORMALIZADAS),
        'sector_de': {f.feeder_id: SECTORES[i % 2] for i, f in enumerate(vnr.feeders)},
        'tipo_de_sed': {t.transformer_id: rng.choice(TIPOS) for t in vnr.transformers},
        'factor_carga': {f.feeder_id: rng.uniform(0.3, 0.8) for f in vnr.feeders},
    }


def _esperada(d: DemandaSed, lista, valor) -> float:
    """La potencia que pide la regla vad.anexo6.sed, calculada aquí sin el módulo."""
    if d.kva > valor['demanda_mayor_kVA']:
        return math.ceil(d.kva / valor['modulo_kVA']) * valor['modulo_kVA']
    objetivo = d.kva
    if d.fases == 'ABC' and d.kva < UMBRAL_TRIFASICO:
        objetivo = valor['trifasico_menor_5kVA_asigna_kVA']
    return min(p for p in lista if p >= objetivo)


def _armar(registro, semilla, empresa, **cambios):
    vnr = _vnr(semilla, empresa)
    modelo = armar_modelo_rural(vnr, registro=registro)
    entradas = {**_entradas(vnr, semilla), **cambios}
    return vnr, modelo, entradas


@pytest.mark.parametrize('empresa', EMPRESAS)
@pytest.mark.parametrize('semilla', SEMILLAS)
def test_sed_sobredimensionadas_cambian_su_potencia_y_no_la_traza(registro, semilla, empresa):
    """108:RF-7 — en una red sorteada con SED sobredimensionadas, su potencia cambia y la huella de vértices no."""
    vnr, modelo, entradas = _armar(registro, semilla, empresa)
    antes = {t.tramo: (t.vertices, t.huella) for t in modelo.tramos}
    dim = dimensionar(modelo, registro=registro, **entradas)
    assert dim.modelo is modelo
    assert {t.tramo: (t.vertices, t.huella) for t in dim.modelo.tramos} == antes
    assert dim.hash_vertices() == {k: v[1] for k, v in antes.items()}
    comprobar_trazas(dim.modelo, vnr)
    assert {t.tramo: t.huella for t in dim.tramos} == {s.section_id: antes[s.section_id][1] for s in vnr.sections}

    valor = registro.regla('vad.anexo6.sed').regla.valor
    assert {s.sed for s in dim.sed} == {t.transformer_id for t in vnr.transformers}
    for s in dim.sed:
        assert s.kva_real in KVA_REALES
        assert s.kva_modelo == _esperada(entradas['demanda'][s.sed], POTENCIAS, valor), s.sed
        assert s.cambia and s.kva_modelo < s.kva_real, s.sed
        assert (s.kva_modelo in NO_NORMALIZADAS) == ('no normalizada' in s.nota), s.sed
    assert set(dim.redes) == {f.feeder_id for f in vnr.feeders}
    asignada = {s.sed: s.kva_modelo for s in dim.sed}
    for red in dim.redes.values():
        assert red.seds and all(x.design_kva == asignada[x.code] for x in red.seds)
    for clave in REGLAS:
        assert set(dim.criterios) >= {clave}
        assert dim.criterios[clave]['huella'] == registro.regla(clave).huella()
        assert 'líneas' in dim.criterios[clave]['cita']
    assert dim.huella and len(dim.huella) == 64


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_conductor_por_corriente_economica_y_seccion_minima(registro, semilla):
    """108:RF-7 — cada tramo de MT toma el conductor cuyo rango económico contiene su corriente del flujo, nunca uno
    bajo la sección mínima del Anexo 6 ni uno sin impedancia."""
    vnr, modelo, entradas = _armar(registro, semilla, EMPRESAS[0])
    dim = dimensionar(modelo, registro=registro, **entradas)
    catalogo = {c.conductor_code: c for c in vnr.conductor_types}
    rango = {c: (a, b) for c, a, b in RANGOS}
    minimos = registro.regla('vad.anexo6.mt.tensiones_y_secciones').regla.valor['seccion_min_mm2']
    mt = [t for t in dim.tramos if t.nivel == 'MT']
    assert len(mt) == sum(1 for s in vnr.sections if s.nominal_kv >= 1)
    adaptados = [t for t in mt if t.conductor_modelo is not None]
    assert len({t.conductor_modelo for t in adaptados}) >= 2, 'el sorteo tiene que cruzar más de un rango'
    for t in adaptados:
        assert t.conductor_modelo not in ('CND_AL_16', 'CND_AL_95'), t.tramo
        c = catalogo[t.conductor_modelo]
        assert c.section_mm2 >= minimos[c.material]
        desde, hasta = rango[t.conductor_modelo]
        propios = [rango[k] for k, x in catalogo.items() if x.material == c.material and k not in ('CND_AL_16',
                                                                                                   'CND_AL_95')]
        assert desde <= t.corriente_a <= hasta or t.corriente_a < min(a for a, _ in propios), t.tramo
        red = dim.redes[t.alimentador]
        linea = next(x for x in red.lines if x.section_id == t.tramo)
        assert linea.type_key == t.conductor_modelo
    for red in dim.redes.values():
        for tipo in red.line_types.values():
            assert tipo.r1_ohm_km > 0 and tipo.x1_ohm_km > 0, tipo.code
    assert any('CND_AL_95' in h and 'no entra con 0 Ω' in h for h in dim.huecos)


@pytest.mark.parametrize('semilla', SEMILLAS)
def test_perdidas_del_oraculo_y_factor_empirico(registro, semilla):
    """108:RF-7 — las pérdidas de potencia son las de oraculo.validar sobre la red dimensionada y las de energía usan
    informes.factor_de_perdidas con los coeficientes del registro."""
    from convertersmartgrid.adaptadores.oraculo import validar

    vnr, modelo, entradas = _armar(registro, semilla, EMPRESAS[1])
    dim = dimensionar(modelo, registro=registro, **entradas)
    caida_max = registro.regla('vad.anexo6.mt.caida_tension_max').regla.valor
    lineal, cuadratico, _cita = coeficientes_factor_de_perdidas(registro)
    assert {p.alimentador for p in dim.perdidas} == {f.feeder_id for f in vnr.feeders}
    for p in dim.perdidas:
        assert p.calculado, p.motivo
        informe = validar(dim.redes[p.alimentador], comparar=False)
        assert informe.convergio
        assert math.isclose(p.perdidas_kw, informe.perdidas_mw * 1000.0, rel_tol=1e-9, abs_tol=1e-9)
        assert p.flujo == informe.flujo
        fc = entradas['factor_carga'][p.alimentador]
        assert p.factor_carga == fc
        assert math.isclose(p.factor_perdidas, factor_de_perdidas(fc, registro), rel_tol=1e-12)
        assert math.isclose(p.factor_perdidas, lineal * fc + cuadratico * fc * fc, rel_tol=1e-12)
        assert math.isclose(p.perdidas_kwh_anio, p.perdidas_kw * HORAS_ANIO * p.factor_perdidas, rel_tol=1e-12)
        assert p.caida_max_pct == caida_max and p.caida_mt_pct is not None and p.caida_mt_pct >= 0
    assert set(dim.criterios) >= {'vad.anexo4.factor_perdidas_empirico'}


@pytest.mark.parametrize('falta', ('sin_xline', 'sin_rline', 'cero'))
def test_conductor_sin_impedancia_es_hueco_nombrado(registro, falta):
    """108:RF-7 — un conductor sin rline o xline (o con los dos en 0) es un hueco nombrado: su alimentador no se calcula
    con 0 Ω y los demás sí."""
    vnr, modelo, entradas = _armar(registro, SEMILLAS[0], EMPRESAS[0])
    r1, x1 = {'sin_xline': (0.5, None), 'sin_rline': (None, 0.4), 'cero': (0.0, 0.0)}[falta]
    roto = ConductorType('CND_SINT_ROTO', material='Al', section_mm2=50.0, r1_ohm_km=r1, x1_ohm_km=x1,
                         ampacity_a=180.0)
    rng = random.Random(falta)
    victima = rng.choice([s for s in vnr.sections if s.nominal_kv >= 1])
    conductor_de = {**entradas['conductor_de'], victima.section_id: 'CND_SINT_ROTO'}
    dim = dimensionar(modelo, registro=registro, **{**entradas, 'conductor_de': conductor_de,
                                                     'conductores': entradas['conductores'] + [roto]})
    alimentador = victima.feeder_id
    assert any(victima.section_id in h and 'CND_SINT_ROTO' in h and 'no entra con 0 Ω' in h for h in dim.huecos)
    perdidas = {p.alimentador: p for p in dim.perdidas}
    assert set(perdidas) == {f.feeder_id for f in vnr.feeders}
    assert not perdidas[alimentador].calculado and victima.section_id in perdidas[alimentador].motivo
    assert perdidas[alimentador].perdidas_kw is None
    assert alimentador not in dim.redes
    assert all(t.conductor_modelo is None for t in dim.tramos if t.alimentador == alimentador)
    otros = {f.feeder_id for f in vnr.feeders} - {alimentador}
    assert otros and set(dim.redes) == otros and all(perdidas[a].calculado for a in otros)
    for red in dim.redes.values():
        assert all(tipo.code != 'CND_SINT_ROTO' and tipo.r1_ohm_km > 0 and tipo.x1_ohm_km > 0
                   for tipo in red.line_types.values())
    assert all(s.kva_modelo is not None for s in dim.sed)
    assert not dim.completo


def test_reglas_de_asignacion_del_anexo6(registro):
    """108:RF-7 — módulos de 300 kVA sobre 350, potencia ajustada del punto trifásico pequeño, nota de la potencia no
    normalizada y hueco nombrado cuando ninguna potencia con costo cubre la demanda."""
    vnr, modelo, entradas = _armar(registro, SEMILLAS[0], EMPRESAS[0])
    seds = sorted(t.transformer_id for t in vnr.transformers)
    assert len(seds) >= 5
    grande, pequena_3f, pequena_1f, no_norm, sin_cubrir = seds[:5]
    origen = 'caracterización sintética (T4)'
    demanda = {**entradas['demanda'], grande: DemandaSed(500.0, 150.0, 'ABC', origen),
               pequena_3f: DemandaSed(3.0, 0.5, 'ABC', origen), pequena_1f: DemandaSed(3.0, 0.5, 'A', origen),
               no_norm: DemandaSed(30.0, 6.0, 'ABC', origen), sin_cubrir: DemandaSed(150.0, 20.0, 'ABC', origen)}
    corta = (5.0, 10.0, 25.0, 50.0, 100.0)
    tipo_de_sed = {**entradas['tipo_de_sed'], sin_cubrir: 'TIPO_SINT_CORTA'}
    potencias = {**entradas['tabla'].potencias,
                 **{(s, 'TIPO_SINT_CORTA'): corta for s in SECTORES}}
    tabla = TablaTransformadores(potencias, HUELLA_TABLA, NO_NORMALIZADAS)
    dim = dimensionar(modelo, registro=registro, **{**entradas, 'demanda': demanda, 'tipo_de_sed': tipo_de_sed,
                                                     'tabla': tabla})
    assert {s.sed for s in dim.sed} == set(seds)
    por_sed = {s.sed: s for s in dim.sed}
    assert por_sed[grande].kva_modelo == 600.0 and por_sed[grande].modulos == 2
    assert por_sed[pequena_3f].kva_modelo == 10.0 and 'potencia ajustada' in por_sed[pequena_3f].nota
    assert por_sed[pequena_1f].kva_modelo == 5.0
    assert por_sed[no_norm].kva_modelo == 37.0 and 'no normalizada' in por_sed[no_norm].nota
    assert por_sed[sin_cubrir].kva_modelo is None
    assert any(sin_cubrir in h and 'mayor potencia con costo' in h for h in dim.huecos)
    alimentador = por_sed[sin_cubrir].alimentador
    assert alimentador not in dim.redes
    assert any(f'alimentador {alimentador}' in h and f'SED {sin_cubrir} sin dimensionar' in h for h in dim.huecos)


def test_sin_rangos_economicos_no_se_adapta_y_se_nombra(registro):
    """108:RF-7 — sin los rangos de corriente económica que sustenta la empresa, ningún conductor se adapta: se nombra,
    y el flujo usa el conductor real."""
    vnr, modelo, entradas = _armar(registro, SEMILLAS[2], EMPRESAS[0])
    dim = dimensionar(modelo, registro=registro, **{**entradas, 'rangos': []})
    mt = [t for t in dim.tramos if t.nivel == 'MT']
    assert mt and all(t.conductor_modelo is None for t in mt)
    assert any('sin rango de corriente económica' in h for h in dim.huecos)
    assert set(dim.redes) == {f.feeder_id for f in vnr.feeders}
    for t in mt:
        linea = next(x for x in dim.redes[t.alimentador].lines if x.section_id == t.tramo)
        assert linea.type_key == t.conductor_real == entradas['conductor_de'][t.tramo]


def test_zona_corrosiva_cambia_a_cobre(registro):
    """108:RF-7 — un tramo en zona corrosiva toma un conductor de Cu en lugar de Al, como dice la regla del Anexo 6."""
    vnr, modelo, entradas = _armar(registro, SEMILLAS[0], EMPRESAS[1])
    corrosivos = {s.section_id for s in vnr.sections if s.feeder_id == vnr.feeders[0].feeder_id}
    dim = dimensionar(modelo, registro=registro, corrosivos=corrosivos, **entradas)
    catalogo = {c.conductor_code: c for c in vnr.conductor_types}
    elegidos = {t.tramo: t.conductor_modelo for t in dim.tramos if t.tramo in corrosivos}
    assert set(elegidos) == corrosivos
    assert all(c is not None and catalogo[c].material == 'Cu' for c in elegidos.values()), elegidos
    otros = [t for t in dim.tramos if t.tramo not in corrosivos and t.conductor_modelo is not None]
    assert otros and all(catalogo[t.conductor_modelo].material == 'Al' for t in otros)


def _sin(registro: RegistroNormativo, clave: str) -> RegistroNormativo:
    return RegistroNormativo({a: dataclasses.replace(n, reglas=tuple(r for r in n.reglas if r.clave != clave))
                              for a, n in registro.normas.items()})


@pytest.mark.parametrize('clave', REGLAS)
def test_sin_una_regla_del_anexo6_no_se_dimensiona(registro, clave):
    """108:RF-7 — cada criterio sale de su regla del registro, con su cita: sin ella, no se dimensiona."""
    _, modelo, entradas = _armar(registro, SEMILLAS[0], EMPRESAS[0])
    with pytest.raises(VadError, match=clave.replace('.', r'\.')):
        dimensionar(modelo, registro=_sin(registro, clave), **entradas)


def test_entradas_sin_origen_se_rechazan():
    """108:RF-7 — una demanda sin origen, una tabla sin la huella de su SICODI o un rango sin sustento no entran."""
    with pytest.raises(VadError, match='origen'):
        DemandaSed(10.0, 2.0, 'ABC', '')
    with pytest.raises(VadError, match='huella'):
        TablaTransformadores({(SECTORES[0], TIPOS[0]): POTENCIAS}, '', NO_NORMALIZADAS)
    with pytest.raises(VadError, match='sustento'):
        RangoEconomico('CND_AL_25', 0.0, 3.0, '')


#: Aleaciones de aluminio sintéticas: la de 16 mm² queda bajo la sección mínima del Al (25 mm²).
ALEACIONES = (('CND_AAAC_16', 'AAAC', 16.0, 1.95, 0.45, 90.0), ('CND_AAAC_50', 'AAAC', 50.0, 0.66, 0.42, 180.0),
              ('CND_ACSR_70', 'ACSR', 70.0, 0.46, 0.41, 230.0))


def test_aleaciones_de_aluminio_cuentan_como_al(registro):
    """108:RF-7 — AAAC y ACSR cuentan como Al para la sección mínima del Anexo 6 (interpretación de f4: su conductor es
    aluminio): se eligen por su rango económico, un tramo real de AAAC se adapta y una aleación bajo 25 mm² no se elige."""
    vnr, modelo, entradas = _armar(registro, SEMILLAS[0], EMPRESAS[0])
    aleaciones = [ConductorType(c, material=m, section_mm2=s, r1_ohm_km=r, x1_ohm_km=x, ampacity_a=a)
                  for c, m, s, r, x, a in ALEACIONES]
    rangos = [RangoEconomico(c, a, b, SUSTENTO) for c, a, b in RANGOS if c not in ('CND_AL_50', 'CND_AL_70')]
    rangos += [RangoEconomico('CND_AAAC_16', 0.0, 0.5, SUSTENTO), RangoEconomico('CND_AAAC_50', 1.5, 3.0, SUSTENTO),
               RangoEconomico('CND_ACSR_70', 3.0, 6.0, SUSTENTO)]
    primero = vnr.feeders[0].feeder_id
    de_aaac = {s.section_id for s in vnr.sections if s.feeder_id == primero}
    conductor_de = {**entradas['conductor_de'], **dict.fromkeys(de_aaac, 'CND_AAAC_50')}
    dim = dimensionar(modelo, registro=registro, **{**entradas, 'conductores': entradas['conductores'] + aleaciones,
                                                     'rangos': rangos, 'conductor_de': conductor_de})
    assert not any('sin sección mínima' in h for h in dim.huecos), dim.huecos
    propios = [t for t in dim.tramos if t.tramo in de_aaac]
    assert propios and all(t.conductor_modelo is not None for t in propios), [(t.tramo, t.nota) for t in propios]
    adaptados = [t for t in dim.tramos if t.conductor_modelo is not None]
    assert all(t.conductor_modelo != 'CND_AAAC_16' for t in adaptados)
    en_aleacion = [t for t in adaptados if 1.5 <= t.corriente_a <= 6.0]
    assert en_aleacion and all(t.conductor_modelo in ('CND_AAAC_50', 'CND_ACSR_70') for t in en_aleacion)
    for material in ('AAAC', 'ACSR'):
        assert any(f'material {material}: cuenta como Al' in n for n in dim.notas), material


def _con_valor(registro: RegistroNormativo, clave: str, valor) -> RegistroNormativo:
    return RegistroNormativo({a: dataclasses.replace(n, reglas=tuple(dataclasses.replace(r, valor=valor)
                                                                    if r.clave == clave else r for r in n.reglas))
                              for a, n in registro.normas.items()})


def test_umbral_del_punto_trifasico_sale_del_registro(registro):
    """108:RF-7 — el umbral del punto trifásico pequeño es el dato trifasico_umbral_kVA de vad.anexo6.sed (5 kVA, línea
    6796), no el nombre de una clave: otro umbral en el registro cambia la asignación, y sin él no se dimensiona."""
    valor = registro.regla('vad.anexo6.sed').regla.valor
    assert valor.get('trifasico_umbral_kVA') == UMBRAL_TRIFASICO
    _, modelo, entradas = _armar(registro, SEMILLAS[0], EMPRESAS[0])
    sed = min(entradas['demanda'])
    demanda = {**entradas['demanda'], sed: DemandaSed(3.0, 0.5, 'ABC', 'caracterización sintética (T4)')}
    con = {s.sed: s for s in dimensionar(modelo, registro=registro, **{**entradas, 'demanda': demanda}).sed}
    assert con[sed].kva_modelo == valor['trifasico_menor_5kVA_asigna_kVA'] and 'potencia ajustada' in con[sed].nota
    otro = _con_valor(registro, 'vad.anexo6.sed', {**valor, 'trifasico_umbral_kVA': 2.0})
    bajo = {s.sed: s for s in dimensionar(modelo, registro=otro, **{**entradas, 'demanda': demanda}).sed}
    assert bajo[sed].kva_modelo == 5.0 and 'potencia ajustada' not in bajo[sed].nota
    sin = _con_valor(registro, 'vad.anexo6.sed', {k: v for k, v in valor.items() if k != 'trifasico_umbral_kVA'})
    with pytest.raises(VadError, match='trifasico_umbral_kVA'):
        dimensionar(modelo, registro=sin, **{**entradas, 'demanda': demanda})


def test_el_flujo_es_el_del_oraculo():
    """108:RF-7 — el dimensionamiento corre el flujo público del oráculo (oraculo.ejecutar), sin repetir sus llamadas a
    pandapower."""
    import inspect

    from convertersmartgrid.adaptadores import oraculo
    from convertersmartgrid.adaptadores.vad import dimensionamiento

    fuente = inspect.getsource(dimensionamiento)
    assert 'runpp' not in fuente
    assert 'ejecutar(pp, net)' in fuente and 'def ejecutar(pp, net)' in inspect.getsource(oraculo)
