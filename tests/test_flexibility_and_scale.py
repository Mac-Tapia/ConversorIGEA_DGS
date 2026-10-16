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

import os
import random
import time

import pytest

from igea_dgs.batch import convert_selection
from igea_dgs.reglas import SIN_REGLAS
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
        # Fidelidad literal al TXT: sin las reglas que funden puentes o quitan trafomix.
        ds, manifest = _convert(spec, tmp_path, reglas=SIN_REGLAS)
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

    def test_many_feeders_do_not_degrade_per_section_cost(self, tmp_path):
        """Multiplicar los alimentadores no debe encarecer cada tramo.

        Nada de 10, 50 o 200 fijos: el número de alimentadores y el tamaño de cada uno
        se sortean, porque una entrega real puede traer cualquier cantidad y de
        tamaños muy desiguales. La semilla va en el mensaje de fallo; con
        ``IGEA_SCALE_SEED=<semilla>`` se reproduce el mismo sorteo.

        El motor recorría CUSTOMER LOADS, las maniobras y los INTERMEDIATE NODES
        enteros por cada alimentador (O(F·N)). Con 50 alimentadores medianos cada uno
        costaba 38 ms; con 200, 142 ms. La prueba anterior toleraba hasta ×4 y lo
        dejaba pasar.
        """
        seed = _scale_seed()
        rng = random.Random(seed)
        few_n = rng.randint(4, 10)
        many_n = few_n * rng.randint(6, 12)
        typical = dict(
            sections_per_feeder=rng.randint(40, 120),
            loads_per_feeder=rng.randint(10, 40),
            switches_per_feeder=rng.randint(1, 6),
            intermediate_per_section=rng.randint(1, 2),
        )
        few = ExportSpec(feeders=few_n, seed=rng.randrange(2**31), **typical)
        many = ExportSpec(feeders=many_n, seed=rng.randrange(2**31), **typical)

        # El mejor de tres. El ruido (otro proceso, el antivirus revisando cada fichero
        # nuevo) solo suma tiempo, nunca lo resta, así que el mínimo es la medida
        # fiable. Con una sola medida, esta prueba falló una vez al ejecutarse justo
        # detrás de las pruebas pesadas con datos reales, y pasaba sola.
        def best_of_three(spec, name):
            times = []
            for attempt in range(3):
                start = time.perf_counter()
                _convert(spec, tmp_path / f'{name}{attempt}')
                times.append(time.perf_counter() - start)
            return min(times)

        t_few = best_of_three(few, 'few')
        t_many = best_of_three(many, 'many')

        if t_few < 0.05:
            pytest.skip(f'medición no fiable: {t_few * 1000:.0f} ms (semilla {seed})')
        per_section_few = t_few / few.total_sections
        per_section_many = t_many / many.total_sections
        # Lineal ≈ ×1. El O(F·N) de antes daba ≈ ×(many_n / few_n), es decir ×6 a ×12.
        assert per_section_many < per_section_few * 2.0, (
            f'semilla {seed}: coste por tramo {per_section_few * 1e3:.3f} ms con '
            f'{few_n} alimentadores ({few.total_sections} tramos) vs '
            f'{per_section_many * 1e3:.3f} ms con {many_n} ({many.total_sections} tramos)'
        )


def _scale_seed() -> int:
    fixed = os.environ.get('IGEA_SCALE_SEED')
    return int(fixed) if fixed else random.SystemRandom().randrange(2**31)


class TestRandomExports:
    """Exports de forma sorteada: cuántos alimentadores, y de qué tamaño cada uno."""

    @pytest.mark.parametrize('draw', range(3))
    def test_every_feeder_converts_and_matches_its_txt(self, draw, tmp_path):
        seed = _scale_seed() + draw
        rng = random.Random(seed)
        spec = ExportSpec(
            feeders=rng.randint(1, 60),
            sections_per_feeder=rng.randint(1, 30),
            loads_per_feeder=rng.randint(0, 10),
            switches_per_feeder=rng.randint(0, 3),
            intermediate_per_section=rng.randint(0, 2),
            header_only_feeders=rng.randint(0, 3),
            layout=rng.choice(['reducido', 'completo']),
            seed=seed,
        )
        ds, manifest = _convert(spec, tmp_path)
        errors = [f"{it['feeder']}: {it.get('error')}" for it in manifest['feeders'] if it['status'] != 'ok']
        assert not errors, f'semilla {seed}, {spec}: {errors}'
        assert manifest['summary']['ok'] == spec.total_feeders, f'semilla {seed}'

        total_loads = 0
        for item in manifest['feeders']:
            if item['topology'] == 'source_only':
                continue
            tables = parse_dgs(item['dgs'])
            network_id = item['network_id']
            txt_loads = sum(1 for key in ds.customer_loads if ds.section_owner.get(key[0]) == network_id)
            assert len(tables['ElmLod']['rows']) == txt_loads, f'semilla {seed}: {item["feeder"]}'
            total_loads += txt_loads
        assert total_loads == spec.total_loads, f'semilla {seed}'


class _NoFullScan:
    """Tabla que admite ``len`` y ``get`` pero revienta si alguien la recorre entera."""

    def __init__(self, name: str, original):
        self._name = name
        self._original = original

    def __len__(self):
        return len(self._original)

    def __bool__(self):
        return bool(self._original)

    def get(self, *args):
        return self._original.get(*args)

    def _scan(self, *_args):
        raise AssertionError(
            f'recorrido completo de {self._name} al convertir un alimentador: O(F·N). '
            'Use los índices por alimentador de CymdistDataset.'
        )

    __iter__ = items = values = keys = _scan


class TestNoFullTableScanPerFeeder:
    """Guarda determinista contra O(alimentadores × filas).

    Medir tiempos no la detecta con datos pequeños: el término cuadrático queda tapado
    por el coste lineal de escribir. Aquí, una vez construidos los índices, las tablas
    completas se sustituyen por otras que fallan si se recorren. Convertir un
    alimentador tiene que funcionar igual.
    """

    def test_feeder_conversion_uses_only_the_indices(self, tmp_path):
        from igea_dgs.geography import build_geography
        from igea_dgs.model import build_feeder_model

        seed = _scale_seed()
        spec = ExportSpec(feeders=6, sections_per_feeder=8, loads_per_feeder=4,
                          switches_per_feeder=2, intermediate_per_section=2, seed=seed)
        ds = load_export(spec, tmp_path / 'src')
        # Construye los índices mientras las tablas aún se pueden recorrer.
        ds.customer_loads_by_feeder, ds.switching_by_feeder, ds.intermediate_by_section
        for name in ('customer_loads', 'switch_settings', 'sectionalizer_settings', 'intermediate_nodes'):
            object.__setattr__(ds, name, _NoFullScan(name, getattr(ds, name)))

        for network_id in ds.feeder_ids():
            model = build_feeder_model(ds, network_id, include_geography=True)
            build_geography(ds, model, source_crs='EPSG:32718', target_crs='EPSG:4326')


class TestParallelWorkers:
    """Varios procesos a la vez: mismo resultado byte a byte que en serie."""

    def test_parallel_output_is_identical_to_serial(self, tmp_path):
        import hashlib
        import json

        seed = _scale_seed()
        rng = random.Random(seed)
        spec = ExportSpec(
            feeders=rng.randint(5, 25), sections_per_feeder=rng.randint(3, 20),
            loads_per_feeder=rng.randint(1, 8), switches_per_feeder=rng.randint(0, 3),
            header_only_feeders=rng.randint(0, 2),
            layout=rng.choice(['reducido', 'completo']), seed=seed,
        )
        ds = load_export(spec, tmp_path / 'src')

        def run(out, workers):
            manifest = convert_selection(ds, None, out, all_feeders=True,
                                         source_crs='EPSG:32718', workers=workers)
            files = {f.relative_to(out).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
                     for f in sorted(out.rglob('*')) if f.is_file() and f.name != 'batch_manifest.json'}
            return manifest, files

        serial, serial_files = run(tmp_path / 'serial', 1)
        parallel, parallel_files = run(tmp_path / 'parallel', 3)

        assert parallel['workers'] == 3
        assert parallel_files == serial_files, f'semilla {seed}'

        def portable(manifest, root):
            text = json.dumps(manifest['feeders'], sort_keys=True)
            return text.replace(json.dumps(str(root))[1:-1], '<out>')

        assert portable(parallel, tmp_path / 'parallel') == portable(serial, tmp_path / 'serial'), \
            f'semilla {seed}: el manifiesto en paralelo debe seguir el orden de la selección'
        assert not list((tmp_path / 'parallel').glob('.igea-stage-*'))

    def test_cancel_stops_launching_and_leaves_nothing_half_written(self, tmp_path):
        import threading

        spec = ExportSpec(feeders=30, sections_per_feeder=15, loads_per_feeder=3, seed=_scale_seed())
        ds = load_export(spec, tmp_path / 'src')
        cancel = threading.Event()

        def on_progress(_network_id, done, _total):
            if done >= 2:
                cancel.set()

        out = tmp_path / 'dgs'
        manifest = convert_selection(ds, None, out, all_feeders=True, source_crs='EPSG:32718',
                                     workers=2, cancel=cancel, on_progress=on_progress)
        summary = manifest['summary']
        assert summary['status'] == 'cancelled'
        assert 2 <= summary['requested'] < spec.feeders
        assert summary['requested'] + summary['not_processed'] == spec.feeders
        # Lo que el manifiesto da por convertido existe entero; nada más quedó en disco.
        published = {p.stem for p in out.glob('*.dgs')}
        assert published == {it['feeder'] for it in manifest['feeders'] if it['status'] == 'ok'}
        assert not list(out.glob('.igea-stage-*'))

    @pytest.mark.parametrize(('workers', 'total', 'expected'), [
        (None, 50, 1), (1, 50, 1), (4, 50, 4), (8, 3, 3), (4, 0, 1),
    ])
    def test_resolve_workers(self, workers, total, expected):
        from igea_dgs.batch import resolve_workers

        assert resolve_workers(workers, total) == expected

    def test_zero_workers_is_automatic_and_capped(self):
        from igea_dgs.batch import AUTO_WORKERS_MAX, resolve_workers

        assert resolve_workers(0, 10_000) == min(AUTO_WORKERS_MAX, os.cpu_count() or 1)
        assert resolve_workers(0, 1) == 1


def test_cancelar_en_serie_termina_el_alimentador_en_marcha(tmp_path):
    """Cancelar no corta un alimentador: el que ya empezó termina y se publica entero.

    La interfaz decía que «se descarta entero», y no era verdad: la cancelación se
    comprueba entre alimentadores. Esta prueba fija el comportamiento real.
    """
    import threading

    spec = ExportSpec(feeders=6, sections_per_feeder=5, loads_per_feeder=2)
    ds = load_export(spec, tmp_path / 'src')
    cancel = threading.Event()
    empezados: list[str] = []

    def on_progress(network_id, index, _total):
        empezados.append(network_id)
        if index == 2:
            cancel.set()   # se pide mientras el segundo está a punto de convertirse

    out = tmp_path / 'dgs'
    manifest = convert_selection(ds, None, out, all_feeders=True, source_crs='EPSG:32718',
                                 cancel=cancel, on_progress=on_progress)
    assert manifest['summary']['status'] == 'cancelled'
    assert [it['network_id'] for it in manifest['feeders']] == empezados == list(ds.feeder_ids())[:2]
    assert all(it['status'] == 'ok' for it in manifest['feeders'])
    assert len(list(out.glob('*.dgs'))) == 2
    assert not list(out.glob('.igea-stage-*'))
