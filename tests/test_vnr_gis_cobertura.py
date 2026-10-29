"""Módulos de VNR-GIS que ninguna prueba ejecutaba (revisión del 2026-10-08).

``gis/crs.py`` estaba al 30 %, ``gis/geometry.py`` al 45 %, ``exporters/cymdist.py`` al
37 % y ``catalogs/conductor.py`` al 0 %. Al escribir estas pruebas apareció un fallo en
el export CYMDIST: con un perfil verificado, ``export()`` pasaba la carpeta de salida en
el lugar de la especificación de columnas y fallaba con ``TypeError``. Nunca se había
ejecutado ese camino.

Spec 034: 034:RF-4.
"""

from __future__ import annotations

import pytest

from vnr_etl.catalogs.conductor import ConductorCatalog, load_conductor_catalog
from igea_dgs.util import sha256_file as sha256_of
from vnr_etl.exporters.base import ExportBlocked, TargetProfile
from vnr_etl.exporters.cymdist import CymdistExporter
from vnr_etl.gis.crs import CRSError, CRSManager
from vnr_etl.gis.geometry import (coords_from_geojson, length_pct_delta, line_endpoints,
                                  polyline_length_m)
from vnr_etl.models import CanonicalModel, ConductorType, Load, Node, Section, Source


# ------------------------------------------------------------------------------ CRS

class TestCRS:
    def test_proyectado_en_metros(self):
        info = CRSManager('EPSG:32718').inspect()
        assert info == {'source_crs': 'EPSG:32718', 'working_crs': 'EPSG:32718',
                        'projected': True}

    def test_sin_crs_en_modo_estricto_se_rechaza(self):
        with pytest.raises(CRSError, match='desconocido'):
            CRSManager(None).inspect()

    def test_sin_crs_en_modo_flexible_lo_dice(self):
        assert CRSManager(None, strict=False).inspect()['projected'] is False

    def test_en_grados_en_modo_estricto_se_rechaza(self):
        """Nunca se mide ni se hace snapping en grados."""
        with pytest.raises(CRSError, match='no es proyectado'):
            CRSManager('EPSG:4326').inspect()
        with pytest.raises(CRSError, match='proyectado'):
            CRSManager('EPSG:4326', strict=False).ensure_metre_crs()

    def test_crs_que_no_existe_nombra_el_crs(self):
        with pytest.raises(CRSError, match='EPSG:999999'):
            CRSManager('EPSG:999999').inspect()

    def test_reproyecta_a_otro_crs_de_trabajo(self):
        """UTM 18S → UTM 17S: el mismo punto, a unos 6° de longitud, cambia de huso."""
        crs = CRSManager('EPSG:32718', 'EPSG:32717')
        assert crs.ensure_metre_crs() == 'EPSG:32717'
        (x, y), = crs.transform_points([(500000.0, 8500000.0)])
        assert x > 1_000_000 and abs(y - 8500000.0) < 100_000

    def test_sin_reproyeccion_devuelve_los_mismos_puntos(self):
        puntos = [(1.0, 2.0), (3.0, 4.0)]
        assert CRSManager('EPSG:32718').transform_points(puntos) == puntos
        assert CRSManager('EPSG:32718', 'EPSG:32718').transformer_to_working() is None


# ------------------------------------------------------------------------- geometría

class TestGeometria:
    def test_coordenadas_de_cada_tipo_geojson(self):
        assert coords_from_geojson({'type': 'Point', 'coordinates': [1, 2]}) == [(1.0, 2.0)]
        assert coords_from_geojson({'type': 'LineString', 'coordinates': [[0, 0], [3, 4]]}) == [
            (0.0, 0.0), (3.0, 4.0)]
        multi = {'type': 'MultiLineString', 'coordinates': [[[0, 0], [1, 0]], [[1, 0], [1, 1]]]}
        assert coords_from_geojson(multi) == [(0.0, 0.0), (1.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        assert coords_from_geojson({'type': 'Polygon', 'coordinates': []}) == []
        assert coords_from_geojson('no es geojson') == []

    def test_extremos_de_una_linea(self):
        assert line_endpoints({'type': 'LineString', 'coordinates': [[0, 0], [1, 1], [2, 0]]}) == (
            (0.0, 0.0), (2.0, 0.0))
        assert line_endpoints(None) == (None, None)
        assert line_endpoints({'type': 'Polygon', 'coordinates': []}) == (None, None)

    def test_extremos_de_un_objeto_shapely(self):
        shapely = pytest.importorskip('shapely.geometry')
        assert line_endpoints(shapely.LineString([(0, 0), (5, 5)])) == ((0.0, 0.0), (5.0, 5.0))

    def test_longitud_de_polilinea(self):
        assert polyline_length_m([(0, 0), (3, 4), (3, 10)]) == pytest.approx(11.0)
        assert polyline_length_m([(0, 0)]) == 0.0

    def test_delta_de_longitud(self):
        assert length_pct_delta(110.0, 100.0) == pytest.approx(10.0)
        assert length_pct_delta(90.0, 100.0) == pytest.approx(10.0)
        # Sin longitud de fuente no hay delta: no se divide por cero.
        assert length_pct_delta(5.0, 0.0) is None
        assert length_pct_delta(5.0, None) is None


# ------------------------------------------------------------------ catálogo conductores

class TestCatalogoDeConductores:
    def test_carga_filas_y_no_inventa_valores(self):
        cat = load_conductor_catalog([
            {'ID': 'CU035', 'Material': 'CU', 'Section': '35', 'R1': '0.6156', 'X1': '0.44',
             'R0': '0.9', 'X0': '1.5', 'Amps': '182'},
            {'ID': 'AA050', 'R1': '0.6755', 'X1': '', 'R0': 'n/d', 'X0': None},
            {'R1': '1'},  # sin código: se ignora
        ])
        assert [c.conductor_code for c in cat.entries] == ['CU035', 'AA050']
        cu = cat.by_code()['CU035']
        assert (cu.section_mm2, cu.r1_ohm_km, cu.ampacity_a) == (35.0, 0.6156, 182.0)
        aa = cat.by_code()['AA050']
        assert aa.x1_ohm_km is None and aa.r0_ohm_km is None, (
            'un valor vacío o ilegible queda vacío: el catálogo nunca fabrica parámetros')

    def test_cobertura_solo_cuenta_los_completos(self):
        cat = load_conductor_catalog([
            {'ID': 'COMPLETO', 'R1': '0.3', 'X1': '0.4', 'R0': '0.9', 'X0': '1.2'},
            {'ID': 'INCOMPLETO', 'R1': '0.3', 'X1': '0.4'},
            {'ID': 'NEGATIVO', 'R1': '-0.1', 'X1': '0.4', 'R0': '0.9', 'X0': '1.2'},
        ])
        cov = cat.coverage(['COMPLETO', 'INCOMPLETO', 'NEGATIVO', 'AUSENTE', 'COMPLETO'])
        assert cov['total'] == 4 and cov['resolved'] == 1
        assert cov['coverage'] == pytest.approx(0.25)
        assert cov['missing'] == ['AUSENTE', 'INCOMPLETO', 'NEGATIVO']

    def test_nan_e_inf_no_son_parametros(self):
        """001:T3 — antes un X1 = «nan» contaba como dato y el conductor salía completo."""
        cat = load_conductor_catalog([
            {'ID': 'NAN', 'R1': '0.3', 'X1': 'nan', 'R0': '0.9', 'X0': '1.2'},
            {'ID': 'INF', 'R1': 'inf', 'X1': '0.4', 'R0': '0.9', 'X0': '1.2', 'Amps': '-inf'},
        ])
        nan, inf = cat.by_code()['NAN'], cat.by_code()['INF']
        assert nan.x1_ohm_km is None
        assert inf.r1_ohm_km is None and inf.ampacity_a is None
        assert cat.coverage(['NAN', 'INF'])['missing'] == ['INF', 'NAN']

    def test_cobertura_sin_codigos_es_completa(self):
        assert ConductorCatalog().coverage([])['coverage'] == 1.0


# -------------------------------------------------------------------------- CYMDIST

def _modelo() -> CanonicalModel:
    m = CanonicalModel()
    m.nodes = [Node(node_id='B'), Node(node_id='A'), Node(node_id='C')]
    m.sections = [
        Section(section_id='S2', from_node='B', to_node='C', conductor_code='CU035', length_m=40.0),
        Section(section_id='S1', from_node='A', to_node='B', conductor_code='CU035', length_m=25.5),
    ]
    m.loads = [Load(load_id='L1', connection_node='C', kw=100.0, kvar=40.0)]
    m.sources = [Source(source_id='G', node_id='A')]
    m.conductor_types = [ConductorType(conductor_code='CU035', r1_ohm_km=0.6156, x1_ohm_km=0.44)]
    return m


def _perfil(tmp_path, delimiter=';') -> TargetProfile:
    muestra = tmp_path / 'plantilla-cymdist.txt'
    muestra.write_text('plantilla conocida', encoding='utf-8')
    return TargetProfile(
        simulator='CYMDIST', sample_path=str(muestra), sample_hash=sha256_of(muestra),
        delimiter=delimiter,
        object_mapping={
            'sections': {'columns': ['section_id', 'from_node', 'to_node', 'conductor_code',
                                     'length_m']},
            'loads': {'columns': ['load_id', 'connection_node', 'kw', 'kvar']},
            'equipment': {'columns': ['conductor_code', 'r1_ohm_km', 'x1_ohm_km']},
        },
    )


class TestExportCymdist:
    def test_con_perfil_verificado_escribe_los_tres_ficheros(self, tmp_path):
        rutas = CymdistExporter(profile=_perfil(tmp_path)).export(_modelo(), tmp_path / 'out')
        assert [p.name for p in rutas] == ['CYM_SECTIONS.TXT', 'CYM_LOADS.TXT', 'CYM_EQUIPMENT.TXT']
        assert all(p.parent == tmp_path / 'out' / 'cymdist' for p in rutas)
        tramos = rutas[0].read_text(encoding='utf-8').splitlines()
        assert tramos[0] == 'section_id;from_node;to_node;conductor_code;length_m'
        # Orden determinista por identificador, no por orden de llegada.
        assert tramos[1:] == ['S1;A;B;CU035;25.5', 'S2;B;C;CU035;40.0']
        assert rutas[1].read_text(encoding='utf-8').splitlines()[1] == 'L1;C;100.0;40.0'
        assert rutas[2].read_text(encoding='utf-8').splitlines()[1] == 'CU035;0.6156;0.44'

    def test_es_determinista(self, tmp_path):
        perfil = _perfil(tmp_path)
        a = CymdistExporter(profile=perfil).export(_modelo(), tmp_path / 'a')
        b = CymdistExporter(profile=perfil).export(_modelo(), tmp_path / 'b')
        assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]

    def test_el_delimitador_dentro_de_un_valor_no_rompe_la_fila(self, tmp_path):
        m = _modelo()
        m.sections[0].conductor_code = 'CU;035'
        m.conductor_types.append(ConductorType(conductor_code='CU;035'))
        ruta = CymdistExporter(profile=_perfil(tmp_path)).export(m, tmp_path / 'out')[0]
        for fila in ruta.read_text(encoding='utf-8').splitlines():
            assert fila.count(';') == 4

    def test_referencias_rotas_bloquean_el_export(self, tmp_path):
        m = _modelo()
        m.sections.append(Section(section_id='S3', from_node='C', to_node='NO_EXISTE',
                                  conductor_code='SIN_CATALOGO'))
        m.loads.append(Load(load_id='L2', connection_node='TAMPOCO'))
        errores = CymdistExporter().validate_mapping(m)
        assert any('NO_EXISTE' in e for e in errores)
        assert any('SIN_CATALOGO' in e for e in errores)
        assert any('TAMPOCO' in e for e in errores)
        with pytest.raises(ExportBlocked, match='referencias inválidas'):
            CymdistExporter(profile=_perfil(tmp_path)).export(m, tmp_path / 'out')
        assert not (tmp_path / 'out' / 'cymdist').exists()

    def test_perfil_con_muestra_alterada_bloquea(self, tmp_path):
        perfil = _perfil(tmp_path)
        (tmp_path / 'plantilla-cymdist.txt').write_text('otra cosa', encoding='utf-8')
        with pytest.raises(ExportBlocked, match='verificado'):
            CymdistExporter(profile=perfil).export(_modelo(), tmp_path / 'out')
