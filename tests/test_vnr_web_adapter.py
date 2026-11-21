"""Adaptador VNR de la web. 080:RF-56, 080:RF-57: las puertas A–H corren al cargar, solo para informar.

080:RF-55 y 080:RF-53: la vía de capas lee el estado y el tipo de red del tramo, y una copia VNR-GIS
restaurada se convierte a paquete de capas con el mismo canónico.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest


def _feature(section: str, feeder: str, company: str, year: int, x: float) -> dict:
    return {
        'type': 'Feature',
        'properties': {
            'CODEMP': company,
            'ANIO': year,
            'CODTRAMOMT': section,
            'CODSALIDAMT': feeder,
            'CODNORMA': 'AA120',
            'LONGITUD': 100.0,
        },
        'geometry': {
            'type': 'LineString',
            'coordinates': [[x, -14.0], [x + 0.001, -14.0]],
        },
    }


def _vnr_zip(tmp_path: Path) -> Path:
    geojson = {
        'type': 'FeatureCollection',
        'features': [
            _feature('OLD', 'OLD101', 'EMPA', 2024, -75.10),
            _feature('S1', 'XA111', 'EMPA', 2025, -75.00),
            _feature('S2', 'XB209', 'EMPA', 2025, -74.99),
            _feature('OTHER', 'SE101', 'EMPB', 2025, -74.90),
            # Dos distribuidoras sintéticas del mismo paquete: nada depende del código de la empresa.
            _feature('A1', 'FC101', 'EMPC', 2025, -73.00),
            _feature('A2', 'FC202', 'EMPC', 2025, -72.99),
            _feature('B1', 'FD101', 'EMPD', 2025, -71.97),
        ],
    }
    archive = tmp_path / 'VNR_GIS_Empresa_A_2025.zip'
    with zipfile.ZipFile(archive, 'w') as zf:
        zf.writestr('capas/Tramo_MT.geojson', json.dumps(geojson))
    return archive


def test_safe_extract_package_rechaza_traversal_y_duplicados(tmp_path):
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import safe_extract_package
    from convertersmartgrid.adaptadores.entrada.vnr.discovery.download import ArchiveSecurityError

    traversal = tmp_path / 'traversal.zip'
    with zipfile.ZipFile(traversal, 'w') as zf:
        zf.writestr('../escape.geojson', '{}')
    with pytest.raises(ArchiveSecurityError, match='insegura'):
        safe_extract_package(traversal, tmp_path / 'out-traversal')
    assert not (tmp_path / 'escape.geojson').exists()

    duplicate = tmp_path / 'duplicate.zip'
    with pytest.warns(UserWarning, match='Duplicate name'):
        with zipfile.ZipFile(duplicate, 'w') as zf:
            zf.writestr('layer.geojson', '{}')
            zf.writestr('layer.geojson', '{}')
    with pytest.raises(ArchiveSecurityError, match='duplicada'):
        safe_extract_package(duplicate, tmp_path / 'out-duplicate')


def test_bridge_conserva_identidad_de_dos_alimentadores():
    from convertersmartgrid.dominio.model import build_feeder_model
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.models import CanonicalModel, ConductorType, Load, Node, Section, Source

    model = CanonicalModel(metadata={
        'working_crs': 'EPSG:32718', 'working_crs_is_projected': True,
    })
    model.nodes = [
        Node('A', 500000, 8450000, nominal_kv=10), Node('B', 500100, 8450000, nominal_kv=10),
        Node('C', 501000, 8450000, nominal_kv=22.9), Node('D', 501100, 8450000, nominal_kv=22.9),
    ]
    model.sections = [
        Section('S1', 'A', 'B', conductor_code='AA120', phases='ABC', nominal_kv=10,
                length_m=100, feeder_id='XA111'),
        Section('S2', 'C', 'D', conductor_code='AA120', phases='ABC', nominal_kv=22.9,
                length_m=100, feeder_id='XB209'),
    ]
    model.sources = [
        Source('SRC1', 'A', nominal_kv=10, feeder_id='XA111'),
        Source('SRC2', 'C', nominal_kv=22.9, feeder_id='XB209'),
    ]
    model.loads = [
        Load('LD1', 'B', kw=120, kvar=40, phases='ABC', feeder_id='XA111'),
        Load('LD2', 'D', kw=80, kvar=20, phases='ABC', feeder_id='XB209'),
    ]
    model.conductor_types = [ConductorType(
        'AA120', r1_ohm_km=0.25, x1_ohm_km=0.35, r0_ohm_km=0.7,
        x0_ohm_km=1.1, ampacity_a=300,
    )]

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    assert set(result.dataset.feeders) == {'XA111', 'XB209'}
    assert result.dataset.section_owner == {'S1': 'XA111', 'S2': 'XB209'}
    assert set(result.dataset.sources) == {'XA111', 'XB209'}
    assert {row['feeder']: row['status'] for row in result.readiness.values()} == {
        'XA111': 'CONVERSION_READY', 'XB209': 'CONVERSION_READY',
    }
    assert len(result.dataset.customer_loads_by_feeder['XA111']) == 1
    assert len(result.dataset.customer_loads_by_feeder['XB209']) == 1
    converted = build_feeder_model(result.dataset, 'XA111', include_geography=True)
    assert converted.loads[0].p_mw == pytest.approx(0.120)
    assert converted.loads[0].q_mvar == pytest.approx(0.040)


def test_bridge_enumera_pero_bloquea_vnr_sin_fuente_ni_cargas():
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_sections

    rows = [
        _feature('S1', 'XA111', 'EMPA', 2025, -75.00),
        _feature('S2', 'XB209', 'EMPA', 2025, -74.99),
    ]
    model = canonicalize_sections(rows).model

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))

    assert set(result.dataset.feeders) == {'XA111', 'XB209'}
    for readiness in result.readiness.values():
        assert readiness['status'] == 'INVENTORY_ONLY'
        assert {'MISSING_SOURCE', 'MISSING_CONDUCTOR_CATALOG'} <= set(readiness['blocking_codes'])
        # 023:RF-10: sin cargas se avisa y se convierte; no bloquea.
        assert 'MISSING_LOADS' not in readiness['blocking_codes']
        assert 'MISSING_LOADS' in readiness['warning_codes']


def test_vnr_adapter_respeta_empresa_y_periodo_explicitos(tmp_path):
    from convertersmartgrid.presentacion.web.source_runs import create_source_run
    from convertersmartgrid.adaptadores.sources import adapter_for
    from convertersmartgrid.presentacion.web.workspace import Workspace

    archive = _vnr_zip(tmp_path)
    ws = Workspace(id='vnr-adapter', root=tmp_path / 'workspace')
    ws.options['input_mode'] = 'vnr'
    ws.set_input('vnr_package', archive, origin='server')
    snapshot = create_source_run(ws)

    result = adapter_for('vnr', company='EMPA', period='2025').load(snapshot, aliases={})

    assert set(result.dataset.feeders) == {'XA111', 'XB209'}
    assert set(result.readiness) == {'XA111', 'XB209'}
    assert result.provenance['company'] == 'EMPA'
    assert result.provenance['period'] == '2025'
    assert result.provenance['source_run_id'] == snapshot.run_id
    assert all(row['status'] == 'INVENTORY_ONLY' for row in result.readiness.values())


#: Empresa → alimentadores que trae el paquete de prueba en 2025.
ALIMENTADORES_POR_EMPRESA = {'EMPC': {'FC101', 'FC202'}, 'EMPD': {'FD101'}}


def _ws_vnr(tmp_path, empresa: str = 'EMPC'):
    from convertersmartgrid.presentacion.web.workspace import Workspace

    ws = Workspace(id='vnr-puertas', root=tmp_path / 'workspace')
    ws.options['input_mode'] = 'vnr'
    ws.set_input('vnr_package', _vnr_zip(tmp_path), origin='server')
    # set_input borra la empresa y el periodo elegidos: se eligen después, como en la web.
    ws.options.update(source_company=empresa, source_period='2025')
    return ws


def _ctx():
    import threading
    from types import SimpleNamespace

    return SimpleNamespace(log=lambda *_: None, check_cancel=lambda: None,
                           progress=lambda *_: None, cancel=threading.Event())


def _incidencias_g_h(puertas: dict) -> dict:
    return {i['gate']: i for i in puertas['incidencias'] if i['gate'] in ('G', 'H')}


@pytest.mark.parametrize('empresa', sorted(ALIMENTADORES_POR_EMPRESA))
def test_vnr_las_puertas_corren_al_cargar_solo_para_informar(tmp_path, empresa):
    """080:RF-56 — la carga VNR corre las puertas A–H y da su veredicto e incidencias, sin bloquear.

    Para dos distribuidoras del mismo paquete: nada depende del código de la empresa.
    """
    from convertersmartgrid.presentacion.web.source_runs import create_source_run
    from convertersmartgrid.adaptadores.sources import adapter_for

    ws = _ws_vnr(tmp_path, empresa)
    result = adapter_for('vnr', company=empresa, period='2025').load(create_source_run(ws), aliases={})

    puertas = result.provenance['puertas_vnr']
    assert puertas['informativo'] is True and puertas['bloquea'] is False
    assert [r['gate'] for r in puertas['resultados']] == list('ABCDEFGH')
    gh = _incidencias_g_h(puertas)
    assert set(gh) == {'G', 'H'} and not any(i['bloquea'] for i in puertas['incidencias'])
    assert 'simulador' in gh['G']['detail']
    assert set(puertas['missing_simulator']) == {'G', 'H'}
    assert set(result.dataset.feeders) == ALIMENTADORES_POR_EMPRESA[empresa]   # la red se carga igual
    json.dumps(puertas)                                            # cabe en el inventario


def test_vnr_incidencia_g_h_llega_al_resultado_de_la_web(tmp_path):
    """080:RF-57 — la incidencia de G/H llega al resultado de la carga en la web y a su inventario."""
    from convertersmartgrid.presentacion.web import services

    ws = _ws_vnr(tmp_path)
    registro: list[str] = []
    ctx = _ctx()
    ctx.log = lambda mensaje, *_: registro.append(str(mensaje))
    resultado = services.load_dataset(ws, ctx)

    # Y en el registro del trabajo que ve el operador, sin bloquear.
    assert any(m.startswith('Puerta G') and m.endswith('(solo informa)') for m in registro)
    assert any(m.startswith('Puerta H') for m in registro)
    gh = _incidencias_g_h(resultado['puertas_vnr'])
    assert set(gh) == {'G', 'H'} and gh['H']['bloquea'] is False
    assert resultado['puertas_vnr']['bloquea'] is False
    assert _incidencias_g_h(ws.inventory['provenance']['puertas_vnr']).keys() == {'G', 'H'}
    assert ws.dataset is not None                                  # nada se bloqueó


def test_vnr_puertas_que_fallan_al_evaluar_no_tumban_la_carga(tmp_path, monkeypatch):
    """080:RF-56 — si la evaluación falla, se dice como incidencia y G/H siguen informándose."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.services import VnrApplicationService
    from convertersmartgrid.presentacion.web.source_runs import create_source_run
    from convertersmartgrid.adaptadores.sources import adapter_for

    def roto(self, *_a, **_k):
        raise RuntimeError('topología ilegible')

    monkeypatch.setattr(VnrApplicationService, 'assess', roto)
    ws = _ws_vnr(tmp_path)
    result = adapter_for('vnr', company='EMPC', period='2025').load(create_source_run(ws), aliases={})

    puertas = result.provenance['puertas_vnr']
    assert puertas['bloquea'] is False and puertas['readiness'] == 'NO_EVALUADO'
    assert set(_incidencias_g_h(puertas)) == {'G', 'H'}
    assert any('topología ilegible' in i['detail'] for i in puertas['incidencias'])
    assert set(result.dataset.feeders) == ALIMENTADORES_POR_EMPRESA['EMPC']


@pytest.mark.parametrize('empresa', sorted(ALIMENTADORES_POR_EMPRESA))
def test_vnr_resultado_de_la_carga_resume_la_revision_para_el_operador(tmp_path, empresa):
    """080:RF-57 — contrato del resultado de la carga en la web: una frase corta, sin RF ni jerga."""
    import re

    from convertersmartgrid.presentacion.web import services

    resultado = services.load_dataset(_ws_vnr(tmp_path, empresa), _ctx())

    resumen = resultado['puertas_vnr']['resumen']
    assert isinstance(resumen, str) and resumen.startswith('Revisión de la red: ')
    assert resumen.endswith('no impiden convertir.')
    n = len(resultado['puertas_vnr']['incidencias'])
    assert f'{n} aviso' in resumen and 'falta comprobarla en DIgSILENT' in resumen
    assert not re.search(r'RF-|\bgate\b|\bpuertas?\b|\b[A-H]\b|readiness|SIMULATOR', resumen, re.I)
    assert len(resumen) <= 160


def test_vnr_resumen_sin_avisos_y_por_motivo():
    """080:RF-57 — sin incidencias lo dice; cada motivo una vez, aunque lo repitan G y H."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.services import resumen_de_puertas

    assert resumen_de_puertas([]) == 'Revisión de la red: sin avisos.'
    assert resumen_de_puertas([{'gate': 'G'}, {'gate': 'H'}]) == (
        'Revisión de la red: 2 avisos (falta comprobarla en DIgSILENT); no impiden convertir.')
    assert resumen_de_puertas([{'gate': 'B'}]) == (
        'Revisión de la red: 1 aviso (datos que se completan al convertir); no impiden convertir.')


def test_vnr_capas_leen_el_estado_y_el_tipo_de_red_del_tramo():
    """080:RF-55, 080:RF-53 — en un paquete de capas, ESTADO fuera de servicio abre el tramo y CODTIPORED dice el medio."""
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_sections

    filas = [_feature('S1', 'FC101', 'EMPC', 2025, -75.00), _feature('S2', 'FC101', 'EMPC', 2025, -74.999),
             _feature('S3', 'FC101', 'EMPC', 2025, -74.998)]
    filas[0]['properties'].update(ESTADO='NA', CODTIPORED='AEREA')
    filas[1]['properties'].update(ESTADO='EN SERVICIO', CODTIPORED='SUBTERRANEA')
    filas[2]['properties'].update(CODTIPORED='X9')            # un código sin regla no se adivina

    model = canonicalize_sections(filas).model
    por_id = {t.section_id: t for t in model.sections}
    assert por_id['S1'].status == 'out_of_service' and por_id['S1'].overhead is True
    assert por_id['S2'].status == 'in_service' and por_id['S2'].overhead is False
    assert por_id['S3'].status == 'in_service' and por_id['S3'].overhead is None

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))
    abiertas = [r for r in result.dataset.switch_settings if r['SectionID'] == 'S1']
    assert {r['Location'] for r in abiertas} == {'S', 'L'} and all(r['Status'] == '0' for r in abiertas)
    assert result.dataset.line_configurations['S2']['Overhead'] == '0'
    [sin_regla] = [i for i in result.issues if i['code'] == 'NETWORK_TYPE_UNKNOWN']
    assert sin_regla['source_id'] == 'X9' and sin_regla['tramos'] == 1


def test_vnr_capas_con_los_valores_reales_de_estado_y_tipo_de_red():
    """080:RF-55, 080:RF-53 — los valores de las copias reales (consultadas en solo lectura, 2026-11-14).

    En las copias de dos distribuidoras, ``mtTramo.EstadoVNR`` solo trae E y N, con mucho más E que N;
    la leyenda ESTADO_VNR de ``cfgTablaCodigo`` dice E existente, M modificado, N nuevo,
    P proyectado y X eliminado. ``CodTipoRed`` solo trae A y S, y todo S lleva norma de cable.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_sections

    valores = [('E', 'A'), ('N', 'S'), ('M', 'A'), ('P', 'A'), ('X', 'S'), ('Z', 'Q')]
    filas = []
    for i, (estado, tipo) in enumerate(valores):
        fila = _feature(f'T{i}', 'FC101', 'EMPC', 2025, -75.0 + i * 0.001)
        fila['properties'].update(ESTADOVNR=estado, CODTIPORED=tipo)
        filas.append(fila)

    model = canonicalize_sections(filas).model
    por_id = {t.section_id: t for t in model.sections}
    assert [por_id[f'T{i}'].status for i in range(6)] == [
        'in_service', 'in_service', 'in_service', 'out_of_service', 'out_of_service', 'in_service']
    assert [por_id[f'T{i}'].overhead for i in range(6)] == [True, False, True, True, False, None]

    result = canonical_to_cymdist(model, source_path=Path('VNR.zip'))
    assert sorted(i['source_id'] for i in result.issues if i['code'] == 'SECTION_OUT_OF_SERVICE') == ['T3', 'T4']
    sin_regla = {(i['code'], i['source_id']) for i in result.issues if i['code'].endswith('_UNKNOWN')}
    assert sin_regla == {('STATUS_UNKNOWN', 'Z'), ('NETWORK_TYPE_UNKNOWN', 'Q')}


def _canonico_como_la_via_sql():
    """Un canónico sintético como el de la vía SQL: los valores de la fuente y lo que sus reglas dicen."""
    from convertersmartgrid.adaptadores.entrada.vnr.models import CanonicalModel, Node, Section
    from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import estado_o_anota, medio_o_anota

    model = CanonicalModel(metadata={'source_crs': 'EPSG:32718', 'working_crs': 'EPSG:32718',
                                     'working_crs_is_projected': True, 'company': 'EMPR'})
    fuente = [('E', 'A'), ('N', 'S'), ('X', 'A'), ('P', 'S'), ('Z', 'Q'), ('', '')]
    x0, y0 = 500000.0, 8450000.0
    for i, (estado, tipo) in enumerate(fuente):
        a, b = (x0 + 100 * i, y0), (x0 + 100 * (i + 1), y0 + 10.0)
        model.sections.append(Section(
            f'T{i}', f'N{i}', f'N{i + 1}', conductor_code='AA05003D' if tipo != 'S' else 'N207003D',
            phases='ABC', nominal_kv=10.0, length_m=round(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5, 3),
            geometry=[a, b], source_layer='mtTramo', source_id=f'T{i}', feeder_id='AL101',
            status=estado_o_anota(model.metadata, estado), overhead=medio_o_anota(model.metadata, tipo),
            source_status=estado, source_network_type=tipo))
    model.nodes = [Node(f'N{i}', x0 + 100 * i, y0 + (10.0 if i else 0.0), nominal_kv=10.0) for i in range(7)]
    return model


def test_bak_a_capas_da_el_mismo_canonico_por_la_via_de_capas(tmp_path):
    """080:RF-55 — SQL → GeoPackage → vía de capas da el mismo canónico: sin un segundo ETL.

    El conversor solo serializa el canónico, con los valores de la fuente; las reglas de estado y
    medio las aplica la vía de capas al leer ESTADOVNR y CODTIPORED.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import (
        comparar_tramos, exportar_canonico_a_capas, resumen_de_tramos)
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    origen = _canonico_como_la_via_sql()
    paquete = tmp_path / 'paquete'
    destino = exportar_canonico_a_capas(origen, paquete / 'red.gpkg')
    assert destino.is_file() and [p.name for p in paquete.iterdir()] == ['red.gpkg']   # publicación atómica

    leido, _scope = canonicalize_vnr_package(paquete)

    assert comparar_tramos(origen, leido.model) == {}
    assert resumen_de_tramos(leido.model) == resumen_de_tramos(origen)
    assert resumen_de_tramos(origen)['fuera_de_servicio'] == 2
    assert resumen_de_tramos(origen)['valores_sin_regla'] == {'estado': {'Z': 1}, 'tipo_red': {'Q': 1}}


def test_una_regla_en_el_conversor_rompe_la_equivalencia(tmp_path, monkeypatch):
    """080:RF-55 — si el conversor aplicara una regla propia (aquí, cambiar un estado), la equivalencia falla."""
    from convertersmartgrid.adaptadores.entrada.vnr.exporters import capas
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    original = capas._fila_de_tramo

    def con_regla(tramo, empresa):
        fila = original(tramo, empresa)
        if fila['ESTADOVNR'] == 'N':
            fila['ESTADOVNR'] = 'X'          # «nuevo» pasado a «eliminado»: una regla que no es del canónico
        return fila

    monkeypatch.setattr(capas, '_fila_de_tramo', con_regla)
    origen = _canonico_como_la_via_sql()
    paquete = tmp_path / 'paquete'
    capas.exportar_canonico_a_capas(origen, paquete / 'red.gpkg')
    leido, _scope = canonicalize_vnr_package(paquete)

    difs = capas.comparar_tramos(origen, leido.model)
    assert {d['campo'] for d in difs['ejemplos']} == {'status', 'source_status'}
    assert {d['tramo'] for d in difs['ejemplos']} == {'T1'}


def _canonico_completo_como_la_via_sql():
    """El canónico de la vía SQL con lo que no son tramos: SED, una maniobra, un banco y un regulador.

    Los nodos de los tramos no se tocan por la geometría (10 m de separación vertical): solo los une
    el código de nodo de la fuente, como en la copia de SQL Server.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.models import Capacitor, Load, Regulator, Switch

    model = _canonico_como_la_via_sql()
    model.loads = [
        Load('S100', 'N3', kw=40.0, kvar=8.0, phases='ABC', feeder_id='AL101', source_layer='Sed',
             etiqueta='E100', connected_kva=50.0),
        Load('S200', 'N6', kw=12.5, kvar=2.5, phases='AB', feeder_id='AL101', source_layer='Sed',
             etiqueta='E200', connected_kva=15.0),
    ]
    model.switches = [Switch('M1', 'N2', section_id='T2', on_off=0, source_layer='mtEquipo')]
    model.capacitors = [Capacitor('B1', 'N4', kvar=300.0, source_layer='mtEquipo')]
    model.regulators = [Regulator('R1', 'N5', section_id='T5', on_off=1, source_layer='mtEquipo')]
    return model


def test_via_de_capas_lee_nodos_sed_y_equipos_como_la_via_sql(tmp_path):
    """080:RF-55 — SQL → GeoPackage → vía de capas da el mismo canónico también en nodos, SED y equipos.

    Antes: la vía de capas solo modelaba los tramos MT, reconstruía los nodos por cercanía y dejaba
    Nodo_MT, Sed y Equipo_MT como ``CAPA_SIN_MODELAR``: un paquete de capas llegaba sin cargas.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import comparar_red, exportar_canonico_a_capas
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    origen = _canonico_completo_como_la_via_sql()
    paquete = tmp_path / 'paquete'
    exportar_canonico_a_capas(origen, paquete / 'red.gpkg')

    leido, _scope = canonicalize_vnr_package(paquete)
    modelo = leido.model

    assert comparar_red(origen, modelo) == {}
    assert not modelo.metadata.get('capas_sin_modelar')
    assert {c['rol'] for c in modelo.metadata['capas']} == {'tramos_mt', 'nodos', 'sed', 'equipos'}
    assert [(t.section_id, t.from_node, t.to_node) for t in modelo.sections][:2] == [('T0', 'N0', 'N1'),
                                                                                    ('T1', 'N1', 'N2')]
    assert {c.load_id: (c.connection_node, c.kw, c.kvar, c.connected_kva) for c in modelo.loads} == {
        'S100': ('N3', 40.0, 8.0, 50.0), 'S200': ('N6', 12.5, 2.5, 15.0)}
    assert [(s.switch_id, s.connection_node, s.section_id, s.on_off) for s in modelo.switches] == [
        ('M1', 'N2', 'T2', 0)]
    assert [(b.capacitor_id, b.kvar) for b in modelo.capacitors] == [('B1', 300.0)]
    assert [(r.regulator_id, r.section_id) for r in modelo.regulators] == [('R1', 'T5')]


def test_comparar_red_ve_una_carga_cambiada(tmp_path):
    """080:RF-55 — la equivalencia no es de adorno: una SED con otra potencia o en otro nodo se ve."""
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import comparar_red, exportar_canonico_a_capas
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    origen = _canonico_completo_como_la_via_sql()
    paquete = tmp_path / 'paquete'
    exportar_canonico_a_capas(origen, paquete / 'red.gpkg')
    leido, _scope = canonicalize_vnr_package(paquete)
    por_id = {c.load_id: c for c in leido.model.loads}
    por_id['S100'].kw = 41.0
    por_id['S200'].connection_node = 'N5'

    difs = comparar_red(origen, leido.model)
    assert {(d['objeto'], d['id'], d['campo']) for d in difs['ejemplos']} == {
        ('sed', 'S100', 'kw'), ('sed', 'S200', 'connection_node')}


def test_equipo_de_tipo_sin_regla_se_anota_y_no_se_pierde(tmp_path):
    """080:RF-55 — un equipo cuyo TIPO no es maniobra, banco ni regulador se anota con su recuento; nunca en silencio."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    paquete = tmp_path / 'paquete'
    paquete.mkdir()
    ruta = paquete / 'red.gpkg'
    x, y = 500000.0, 8450000.0
    gpd.GeoDataFrame([{'CODTRAMOMT': 'A1', 'CODSALIDAMT': 'AL101'}], geometry=[LineString([(x, y), (x + 50, y)])],
                     crs='EPSG:32718').to_file(ruta, layer='Tramo_MT', driver='GPKG', engine='pyogrio')
    gpd.GeoDataFrame([{'CODEQP': 'Q1', 'TIPO': 'PARARRAYOS', 'CODNODOMT': 'X'},
                      {'CODEQP': 'Q2', 'TIPO': 'MANIOBRA', 'CODNODOMT': 'X'}],
                     geometry=[Point(x, y), Point(x, y)], crs='EPSG:32718').to_file(
        ruta, layer='Equipo_MT', driver='GPKG', engine='pyogrio')

    leido, _scope = canonicalize_vnr_package(paquete)

    assert [s.switch_id for s in leido.model.switches] == ['Q2']
    assert leido.model.metadata['valores_sin_regla']['tipo_equipo'] == {'PARARRAYOS': 1}
    assert any('EQUIPO_SIN_REGLA' in w and 'PARARRAYOS' in w for w in leido.warnings)
    # El puente lo dice como tipo de equipo sin regla, no como un estado de tramo sin regla.
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist

    issues = canonical_to_cymdist(leido.model, source_path=paquete).issues
    assert [(i['code'], i['object_type'], i['source_id']) for i in issues if i.get('campo') == 'tipo_equipo'] == [
        ('EQUIPMENT_TYPE_UNKNOWN', 'equipment', 'PARARRAYOS')]


def test_aviso_dice_lo_que_si_se_modelo_cuando_hay_sed():
    """080:RF-55 — con SED y equipos modelados, el aviso ya no dice «solo los tramos de media tensión»."""
    from convertersmartgrid.adaptadores.sources.vnr import aviso_de_capas_sin_modelar

    metadata = {'capas': [{'rol': 'tramos_mt', 'registros': 3}, {'rol': 'sed', 'registros': 2},
                          {'rol': 'equipos', 'registros': 1}, {'rol': 'tramos_bt', 'registros': 4}],
                'capas_sin_modelar': [{'rol': 'tramos_bt', 'registros': 4}]}
    assert aviso_de_capas_sin_modelar(metadata) == (
        'Se modelaron los tramos de media tensión, las SED y los equipos; quedaron fuera 4 tramos de baja tensión.')


def test_bak_a_capas_no_restaura_una_base_que_no_esta_en_linea(monkeypatch):
    """080:RF-55 — SQL Server es compartido: una base que no está ONLINE no se lee ni se restaura."""
    import pytest as _pytest

    from convertersmartgrid.adaptadores.entrada.vnr.connectors import sqlserver_vnr
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import leer_base_restaurada

    class Cursor:
        def execute(self, sql, *args):
            self.sql = sql

        def fetchone(self):
            return ('RESTORING',)

    class Conexion:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(sqlserver_vnr, 'conectar', lambda *a, **k: Conexion())
    monkeypatch.setattr(sqlserver_vnr, 'restaurar', lambda *a, **k: _pytest.fail('no se restaura'))
    with _pytest.raises(ValueError, match='no está en línea'):
        leer_base_restaurada('CSG_VNR_X')


def _gpkg_multicapa(ruta):
    """Un GeoPackage corporativo sintético: tramos MT aéreos y subterráneos, tramos BT y una capa ajena."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point

    x, y = 500000.0, 8450000.0
    capas = {
        'Tramo_MT_Aereo': ([{'CODTRAMOMT': 'A1', 'CODSALIDAMT': 'AL101', 'CODNORMA': 'AA05003D'},
                            {'CODTRAMOMT': 'A2', 'CODSALIDAMT': 'AL102', 'CODNORMA': 'AA05003D'}],
                           [LineString([(x, y), (x + 100, y)]), LineString([(x, y + 500), (x + 100, y + 500)])]),
        'Tramo_MT_Subterraneo': ([{'CODTRAMOMT': 'S1', 'CODSALIDAMT': 'AL101', 'CODNORMA': 'N207003D'}],
                                 [LineString([(x + 100, y), (x + 200, y)])]),
        'Tramo_BT': ([{'CODTRAMOBT': 'B1', 'CODSED': 'SED1'}], [LineString([(x, y + 50), (x + 30, y + 50)])]),
        'Rios': ([{'NOMBRE': 'Rio Ica'}], [Point(x, y + 900)]),
    }
    for nombre, (filas, geometrias) in capas.items():
        gpd.GeoDataFrame(filas, geometry=geometrias, crs='EPSG:32718').to_file(
            ruta, layer=nombre, driver='GPKG', engine='pyogrio')
    return ruta


def test_gpkg_multicapa_lista_y_lee_cada_capa(tmp_path):
    """080:RF-55 — list_layers da TODAS las capas con campos, recuento y CRS, y read_layer lee la pedida.

    Antes (connectors/vector.py:38-63 en 51895566): una sola capa con el nombre del fichero, y
    ``read_layer`` hacía ``del layer, filters`` y volvía a leer la capa por defecto.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.connectors.vector import VectorFileAdapter

    adaptador = VectorFileAdapter(path=str(_gpkg_multicapa(tmp_path / 'red.gpkg')))
    capas = {c.name: c for c in adaptador.list_layers()}

    assert list(capas) == ['Tramo_MT_Aereo', 'Tramo_MT_Subterraneo', 'Tramo_BT', 'Rios']
    assert [capas[n].record_count for n in capas] == [2, 1, 1, 1]
    assert '32718' in capas['Tramo_BT'].crs
    assert {f['name'] for f in capas['Tramo_BT'].fields} == {'CODTRAMOBT', 'CODSED'}
    assert [r['CODTRAMOBT'] for r in adaptador.read_layer('Tramo_BT')] == ['B1']


def test_read_layer_aplica_el_filtro_por_alimentador(tmp_path):
    """080:RF-55 — los filtros no se ignoran: {"equals": …} como SQLite; un WHERE libre es un error claro."""
    import pytest as _pytest

    from convertersmartgrid.adaptadores.entrada.vnr.connectors.vector import VectorFileAdapter

    adaptador = VectorFileAdapter(path=str(_gpkg_multicapa(tmp_path / 'red.gpkg')))

    filas = adaptador.read_layer('Tramo_MT_Aereo', {'equals': {'CODSALIDAMT': 'AL101'}})
    assert [r['CODTRAMOMT'] for r in filas] == ['A1']
    with _pytest.raises(ValueError, match='WHERE'):
        adaptador.read_layer('Tramo_MT_Aereo', {'where': "CODSALIDAMT = 'AL101'"})
    with _pytest.raises(ValueError, match='no tiene el campo'):
        adaptador.read_layer('Tramo_MT_Aereo', {'equals': {'ALIMENTADOR_X': 'AL101'}})


def test_via_de_capas_une_los_tramos_mt_y_anota_las_demas_capas(tmp_path):
    """080:RF-55, 080:RF-53 — varias capas de tramos MT se unen con su capa; BT se lee y la ajena se anota.

    La capa subterránea, por su nombre, hace cable a sus tramos (deducir_medio por SOURCE_LAYER).
    """
    from convertersmartgrid.adaptadores.entrada.vnr.application.cymdist_bridge import canonical_to_cymdist
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    paquete = tmp_path / 'paquete'
    paquete.mkdir()
    _gpkg_multicapa(paquete / 'red.gpkg')

    leido, _scope = canonicalize_vnr_package(paquete)

    capa_de = {t.section_id: t.source_layer for t in leido.model.sections}
    assert capa_de == {'A1': 'red.gpkg:Tramo_MT_Aereo', 'A2': 'red.gpkg:Tramo_MT_Aereo',
                       'S1': 'red.gpkg:Tramo_MT_Subterraneo'}
    anotadas = {(o['code'], o['capa'], o['rol'], o['registros'])
                for o in leido.model.metadata['capas_sin_modelar']}
    # 080:RF-55: los tramos BT ya se modelan; solo la capa ajena queda anotada.
    assert anotadas == {('CAPA_NO_RECONOCIDA', 'red.gpkg:Rios', '', 1)}
    assert [(b.section_id, b.sed_id, b.source_layer) for b in leido.model.sections_bt] == [
        ('B1', 'SED1', 'red.gpkg:Tramo_BT')]
    bridge = canonical_to_cymdist(leido.model, source_path=paquete)
    assert bridge.dataset.line_configurations['S1']['Overhead'] == '0'
    assert bridge.dataset.line_configurations['A1']['Overhead'] == '1'


def test_capas_sin_modelar_van_delante_en_el_resumen_para_el_operador(tmp_path):
    """080:RF-55 — lo que la vía de capas no modela lo dice el resultado de la carga en su primera frase, por rol y con
    sus registros; no basta con dejarlo en metadata (auditor, 2026-11-14). Los tramos BT ya entran: la frase lo dice."""
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package
    from convertersmartgrid.adaptadores.sources.vnr import aviso_de_capas_sin_modelar

    paquete = tmp_path / 'paquete'
    paquete.mkdir()
    _gpkg_multicapa(paquete / 'red.gpkg')
    leido, _scope = canonicalize_vnr_package(paquete)

    aviso = aviso_de_capas_sin_modelar(leido.model.metadata)
    assert aviso == ('Se modelaron los tramos de media tensión y los tramos de baja tensión; quedaron fuera '
                     '1 capa sin reconocer.')
    assert 'RF-' not in aviso and 'CAPA_' not in aviso
    assert aviso_de_capas_sin_modelar({}) is None
    # En plural, con los objetos de cada rol y las capas que no se reconocen contadas como capas.
    plural = {'capas_sin_modelar': [
        {'rol': 'tramos_bt', 'registros': 7}, {'rol': 'tramos_bt', 'registros': 5}, {'rol': 'sed', 'registros': 3},
        {'rol': '', 'registros': 40}, {'rol': '', 'registros': 2}]}
    assert aviso_de_capas_sin_modelar(plural) == ('Solo se modelaron los tramos de media tensión; quedaron fuera '
                                                  '12 tramos de baja tensión, 3 SED y 2 capas sin reconocer.')


def _canonico_con_tramos_bt():
    """El canónico completo de la vía SQL con la red BT de sus SED: un tramo aéreo, uno subterráneo con un
    estado sin regla y uno proyectado (fuera de servicio), con las reglas de la vía SQL."""
    from convertersmartgrid.adaptadores.entrada.vnr.models import LowVoltageSection
    from convertersmartgrid.adaptadores.entrada.vnr.reglas_tramo import estado_o_anota, medio_o_anota

    model = _canonico_completo_como_la_via_sql()
    x0, y0 = 500000.0, 8450000.0
    fuente = [('B1', 'S100', '', 'CAAI35', 'E', 'A', [(x0 + 300, y0 + 10), (x0 + 330, y0 + 10), (x0 + 340, y0 + 10)]),
              ('B2', 'S100', 'B1', 'NYY16', 'Z', 'S', [(x0 + 340, y0 + 10), (x0 + 340, y0 + 19)]),
              ('B3', 'S200', '', 'CAAI35', 'P', 'A', [(x0 + 600, y0 + 10), (x0 + 625, y0 + 10)])]
    clave = 'valores_sin_regla_bt'
    for ident, sed, padre, norma, estado, tipo, puntos in fuente:
        largo = round(sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(puntos, puntos[1:])), 3)
        model.sections_bt.append(LowVoltageSection(
            ident, sed_id=sed, bt_feeder_id=f'SB_{sed}', feeder_id='AL101', parent_id=padre, conductor_code=norma,
            length_m=largo, geometry=puntos, status=estado_o_anota(model.metadata, estado, clave=clave),
            overhead=medio_o_anota(model.metadata, tipo, clave=clave), source_status=estado,
            source_network_type=tipo, source_layer='btTramo', source_id=ident))
    return model


def test_via_de_capas_lee_los_tramos_bt_como_la_via_sql(tmp_path):
    """080:RF-55 — SQL → GeoPackage → vía de capas da la misma red también en BT: cada tramo con su SED, su
    salida BT, su padre, su norma, su estado y su geometría, y lo sin regla anotado aparte de MT.

    Antes: el exportador no escribía BT, el canónico no tenía BT y la capa Tramo_BT quedaba como
    ``CAPA_SIN_MODELAR``.
    """
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import comparar_red, exportar_canonico_a_capas
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    origen = _canonico_con_tramos_bt()
    paquete = tmp_path / 'paquete'
    exportar_canonico_a_capas(origen, paquete / 'red.gpkg')

    leido, _scope = canonicalize_vnr_package(paquete)
    modelo = leido.model

    assert comparar_red(origen, modelo) == {}
    assert not modelo.metadata.get('capas_sin_modelar')
    assert {c['rol'] for c in modelo.metadata['capas']} == {'tramos_mt', 'nodos', 'sed', 'equipos', 'tramos_bt'}
    assert [(b.section_id, b.sed_id, b.parent_id, b.status, b.overhead) for b in modelo.sections_bt] == [
        ('B1', 'S100', '', 'in_service', True), ('B2', 'S100', 'B1', 'in_service', False),
        ('B3', 'S200', '', 'out_of_service', True)]
    assert len(modelo.sections_bt[0].geometry) == 3
    assert modelo.metadata['valores_sin_regla_bt'] == {'estado': {'Z': 1}}
    assert modelo.metadata['valores_sin_regla'] == {'estado': {'Z': 1}, 'tipo_red': {'Q': 1}}, 'MT, sin BT'


def test_comparar_red_ve_un_tramo_bt_cambiado(tmp_path):
    """080:RF-55 — la equivalencia en BT no es de adorno: otra SED, otra geometría o un tramo que falta se ven."""
    from convertersmartgrid.adaptadores.entrada.vnr.exporters.capas import comparar_red, exportar_canonico_a_capas
    from convertersmartgrid.adaptadores.entrada.vnr.pipeline import canonicalize_vnr_package

    origen = _canonico_con_tramos_bt()
    paquete = tmp_path / 'paquete'
    exportar_canonico_a_capas(origen, paquete / 'red.gpkg')
    leido, _scope = canonicalize_vnr_package(paquete)
    por_id = {b.section_id: b for b in leido.model.sections_bt}
    por_id['B1'].sed_id = 'S200'
    por_id['B2'].geometry = [(x + 1.0, y) for x, y in por_id['B2'].geometry]
    leido.model.sections_bt.remove(por_id['B3'])

    difs = comparar_red(origen, leido.model)
    assert {(d['objeto'], d['id'], d['campo']) for d in difs['ejemplos']} == {
        ('tramo_bt', 'B1', 'sed_id'), ('tramo_bt', 'B2', 'geometria')}
    assert difs['faltan']['tramo_bt'] == {'solo_en_sql': ['B3'], 'solo_en_capas': []}
