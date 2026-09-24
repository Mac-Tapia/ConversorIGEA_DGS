"""El conversor no está afinado a un export concreto: flexibilidad y escala.

El export de referencia tiene 96 alimentadores, 38.657 tramos y una convención de
nombres concreta. Otro cliente traerá más o menos alimentadores, otros códigos y otro
CRS. Estas pruebas lo ejercitan con exports sintéticos de forma variable, sin depender
de datos de ninguna distribuidora.

Cubre tres propiedades:

- **Flexibilidad**: cualquier número de alimentadores, cualquier convención de nombre,
  cualquier CRS métrico, y tablas opcionales ausentes.
- **Fidelidad**: lo que sale en el DGS es exactamente lo que entra en el TXT, sea cual
  sea el tamaño.
- **Escalabilidad**: el coste crece de forma lineal con el número de tramos, no
  cuadrática (regresión histórica C-02).
"""

from __future__ import annotations

import time

import pytest

from igea_dgs.batch import convert_selection
from igea_dgs.naming import feeder_short_name
from igea_dgs.validate import parse_dgs
from synthetic_export import ExportSpec, load_export


def _convert(spec: ExportSpec, tmp_path, **kwargs):
    ds = load_export(spec, tmp_path / 'src')
    manifest = convert_selection(
        ds, None, tmp_path / 'dgs', all_feeders=True, strict=True,
        **{'include_geography': True, 'source_crs': 'EPSG:32718', **kwargs},
    )
    return ds, manifest


def _assert_all_ok(manifest, expected: int):
    errors = [f"{it['feeder']}: {it.get('error')}" for it in manifest['feeders'] if it['status'] != 'ok']
    assert not errors, errors
    assert manifest['summary']['ok'] == expected
    assert manifest['summary']['failed'] == 0


class TestFeederCountIsNotFixed:
    """Ni 96 ni ningún otro número está grabado en el motor."""

    @pytest.mark.parametrize('feeders', [1, 2, 7, 25])
    def test_any_number_of_feeders_converts(self, feeders, tmp_path):
        spec = ExportSpec(feeders=feeders, sections_per_feeder=3)
        _ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, feeders)
        assert len(list((tmp_path / 'dgs').glob('*.dgs'))) == feeders

    def test_a_single_feeder_export_works(self, tmp_path):
        _ds, manifest = _convert(ExportSpec(feeders=1, sections_per_feeder=1, loads_per_feeder=1), tmp_path)
        _assert_all_ok(manifest, 1)

    def test_mixed_full_and_header_only_feeders(self, tmp_path):
        spec = ExportSpec(feeders=4, header_only_feeders=2, sections_per_feeder=3)
        _ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, 6)
        topologies = sorted(it['topology'] for it in manifest['feeders'])
        assert topologies == ['full'] * 4 + ['source_only'] * 2


class TestNamingConventionIsNotFixed:
    """El nombre corto se deduce del NetworkID, no de una lista de códigos."""

    @pytest.mark.parametrize('naming', ['net', 'dash', 'dotted', 'plain'])
    def test_any_network_id_convention(self, naming, tmp_path):
        spec = ExportSpec(feeders=3, sections_per_feeder=2, naming=naming)
        ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, 3)
        expected = {spec.short_name(i) for i in range(1, spec.feeders + 1)}
        assert {it['short_name'] for it in manifest['feeders']} == expected
        # Y el selector por nombre corto resuelve al NetworkID correcto.
        for index in range(1, spec.feeders + 1):
            assert ds.resolve_feeder(spec.short_name(index)) == spec.network_id(index)


class TestOptionalTablesMayBeAbsent:
    """Un export sin maniobras o sin vértices intermedios sigue siendo convertible."""

    def test_without_switch_table(self, tmp_path):
        spec = ExportSpec(feeders=2, sections_per_feeder=3, with_switch_table=False)
        _ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, 2)
        for item in manifest['feeders']:
            assert len(parse_dgs(item['dgs'])['StaSwitch']['rows']) == 0

    def test_without_intermediate_nodes(self, tmp_path):
        spec = ExportSpec(feeders=2, sections_per_feeder=3, with_intermediate_table=False)
        _ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, 2)

    def test_without_cable_catalog(self, tmp_path):
        """Sin catálogo de cable subterráneo, las secciones UG usan el DEFAULT aéreo."""
        spec = ExportSpec(feeders=2, sections_per_feeder=3, with_cable_catalog=False)
        _ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, 2)

    def test_without_loads(self, tmp_path):
        spec = ExportSpec(feeders=2, sections_per_feeder=3, loads_per_feeder=0)
        _ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, 2)
        for item in manifest['feeders']:
            tables = parse_dgs(item['dgs'])
            assert len(tables['ElmLod']['rows']) == 0
            assert len(tables.get('ElmSubstat', {'rows': []})['rows']) == 0


class TestAnyMetreCrs:
    @pytest.mark.parametrize('crs', ['EPSG:32718', 'EPSG:32618', 'EPSG:31983', 'EPSG:5343'])
    def test_conversion_is_independent_of_the_metre_crs(self, crs, tmp_path):
        pytest.importorskip('pyproj')
        spec = ExportSpec(feeders=2, sections_per_feeder=3)
        _ds, manifest = _convert(spec, tmp_path, source_crs=crs)
        _assert_all_ok(manifest, 2)
        assert manifest['source_crs'] == crs


class TestOutputMatchesInputWhateverTheSize:
    @pytest.mark.parametrize(
        ('feeders', 'sections', 'loads'),
        [(1, 1, 1), (3, 5, 2), (10, 12, 4)],
    )
    def test_element_counts_equal_the_txt(self, feeders, sections, loads, tmp_path):
        spec = ExportSpec(
            feeders=feeders, sections_per_feeder=sections, loads_per_feeder=loads,
            switches_per_feeder=1, intermediate_per_section=2,
        )
        ds, manifest = _convert(spec, tmp_path)
        _assert_all_ok(manifest, feeders)

        total_lines = total_loads = 0
        for item in manifest['feeders']:
            tables = parse_dgs(item['dgs'])
            network_id = item['network_id']
            txt_sections = len(ds.feeders[network_id])
            txt_loads = sum(1 for key in ds.customer_loads if ds.section_owner.get(key[0]) == network_id)
            assert len(tables['ElmLne']['rows']) == txt_sections, item['feeder']
            assert len(tables['ElmLod']['rows']) == txt_loads, item['feeder']
            total_lines += txt_sections
            total_loads += txt_loads

        assert total_lines == spec.total_sections
        assert total_loads == feeders * min(loads, sections)

    def test_phases_present_in_the_txt_survive_into_the_model(self, tmp_path):
        """El generador alterna ABC/AB/A; el modelo debe conservar lo leído."""
        from igea_dgs.model import build_feeder_model

        spec = ExportSpec(feeders=1, sections_per_feeder=6)
        ds = load_export(spec, tmp_path / 'src')
        model = build_feeder_model(ds, feeder_short_name(ds.feeder_ids()[0]))
        assert {line.phase for line in model.lines} == {'ABC', 'AB', 'A'}


class TestScalability:
    """El coste debe crecer linealmente con los tramos (regresión C-02)."""

    def test_cost_is_linear_in_sections(self, tmp_path):
        small = ExportSpec(feeders=4, sections_per_feeder=50, loads_per_feeder=10)
        large = ExportSpec(feeders=4, sections_per_feeder=200, loads_per_feeder=40)

        start = time.perf_counter()
        _convert(small, tmp_path / 'small')
        t_small = time.perf_counter() - start

        start = time.perf_counter()
        _convert(large, tmp_path / 'large')
        t_large = time.perf_counter() - start

        if t_small < 0.05:
            pytest.skip(f'medición no fiable: {t_small * 1000:.0f} ms')
        ratio = t_large / t_small
        # 4× los tramos: lineal ≈ 4×, cuadrático ≈ 16×.
        assert ratio < 8.0, f'coste ×{ratio:.1f} al cuadruplicar los tramos (lineal ≈ 4)'

    def test_many_feeders_do_not_degrade_per_feeder_cost(self, tmp_path):
        """Pasar de 5 a 40 alimentadores no debe encarecer cada alimentador.

        El motor recorría todo CUSTOMER LOADS / INTERMEDIATE NODES por alimentador
        (O(F·N)); con pocos datos apenas se nota, pero debe seguir siendo proporcional.
        """
        few = ExportSpec(feeders=5, sections_per_feeder=20, loads_per_feeder=5)
        many = ExportSpec(feeders=40, sections_per_feeder=20, loads_per_feeder=5)

        start = time.perf_counter()
        _convert(few, tmp_path / 'few')
        t_few = time.perf_counter() - start

        start = time.perf_counter()
        _convert(many, tmp_path / 'many')
        t_many = time.perf_counter() - start

        if t_few < 0.05:
            pytest.skip(f'medición no fiable: {t_few * 1000:.0f} ms')
        per_feeder_few = t_few / few.feeders
        per_feeder_many = t_many / many.feeders
        assert per_feeder_many < per_feeder_few * 4.0, (
            f'coste por alimentador: {per_feeder_few * 1000:.1f} ms con {few.feeders} '
            f'vs {per_feeder_many * 1000:.1f} ms con {many.feeders}'
        )
