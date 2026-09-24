"""Guards against the O(lines²) diagram/validation regression.

Historical defect (see docs/DIAGNOSTICO_BACKEND_FRONTEND_2026-09-22.md, C-02):
``diagram_anchor_node`` rebuilt the full node-adjacency index on every lookup and
``validate_dgs`` scanned ``model.lines`` linearly inside a loop over DGS rows.
Converting the largest reference feeder (2,024 sections) cost ~17 s, of which 95 %
was those two patterns; cost grew as ~4.8e-6 · sections².

The call-count test below is the real guard and needs no utility TXT: it fails the
moment someone puts an index rebuild back inside a loop, regardless of machine speed.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from igea_dgs import dgs as dgs_module
from igea_dgs.dgs import write_dgs
from igea_dgs.geography import GeoLine, GeoPoint, GeographyManifest
from igea_dgs.model import FeederModel, Line, LineType, Load, Node, Sed
from igea_dgs.validate import validate_dgs

# Wall-clock ceiling for the largest reference feeder. Measured after the fix:
# ~0.3 s. Before it: ~17 s. The wide margin keeps slow CI runners green while
# still catching a return to quadratic behaviour.
MAX_SECONDS_LARGEST_FEEDER = 3.0

# write_dgs and validate_dgs each build the adjacency index once. Anything that
# scales with the number of lines means the index moved back inside a loop.
MAX_NEIGHBOR_BUILDS = 6


def _chain_model(sections: int, *, stub_every: int = 3) -> FeederModel:
    """Radial chain SRC→N1→…→Nn plus ≤1 m service stubs carrying loads/SEDs.

    The micro stubs are essential: ``is_micro_service_stub_line`` returns early for
    any span longer than ``max_stub_m``, so a chain of ordinary sections never
    reaches ``diagram_anchor_node`` and would not exercise the regression at all.
    Real CYMDIST exports hang each SED off a ~0.3 m stub, which is what made the
    quadratic path dominate.
    """
    node_ids = ['SRC'] + [f'N{i}' for i in range(1, sections + 1)]
    nodes = {nid: Node(nid, float(i) * 10.0, 0.0) for i, nid in enumerate(node_ids)}
    line_type = LineType('LINE:T', 'T', 'LINE', 0.1, 0.1, 0.1, 0.1, 0.0, 0.0, 100.0)
    lines = [
        Line(f'S{i}', node_ids[i], node_ids[i + 1], 'ABC', 'LINE:T', 'T', 10.0, True)
        for i in range(sections)
    ]

    loads: list[Load] = []
    seds: list[Sed] = []
    for index in range(stub_every, sections, stub_every):
        primary = node_ids[index]
        tip = f'{primary}_T'
        nodes[tip] = Node(tip, float(index) * 10.0 + 0.3, 0.0)
        stub_id = f'ST{index}'
        # 0.3 m tip section: exactly the CYMDIST service-stub pattern.
        lines.append(Line(stub_id, primary, tip, 'ABC', 'LINE:T', 'T', 0.3, True))
        code = f'SE{index:04d}'
        device = f'DEV{index}'
        loads.append(Load(
            stub_id, device, f'CUST_{index}_{code}', '1', tip,
            0.01, 0.0, 0.97, 50.0, 0.0, 'ABC',
            sed_code=code, display_name=code,
        ))
        seds.append(Sed(
            code=code, loc_name=code, node_id=tip, design_kva=50.0,
            section_id=stub_id, device_number=device, load_key=(stub_id, device),
        ))

    return FeederModel(
        name='CHAIN',
        network_id='NET_CHAIN',
        nominal_kv=13.8,
        source_node='SRC',
        nodes=nodes,
        lines=lines,
        loads=loads,
        devices=[],
        line_types={'LINE:T': line_type},
        seds=seds,
    )


def _chain_geography(model: FeederModel) -> GeographyManifest:
    node_ids = sorted(model.nodes)
    points = {
        nid: GeoPoint(lat=-14.0 + i * 0.0001, lon=-75.0 + i * 0.0001, x=float(i) * 10.0, y=0.0)
        for i, nid in enumerate(node_ids)
    }
    lines = {
        line.section_id: GeoLine(
            section_id=line.section_id,
            from_node=line.from_node,
            to_node=line.to_node,
            path=(points[line.from_node], points[line.to_node]),
        )
        for line in model.lines
    }
    lats = [p.lat for p in points.values()]
    lons = [p.lon for p in points.values()]
    return GeographyManifest(
        feeder=model.name,
        network_id=model.network_id,
        source_node=model.source_node,
        source_crs='EPSG:32718',
        target_crs='EPSG:4326',
        nodes=points,
        lines=lines,
        source_xy_bounds=(0.0, 0.0, float(len(node_ids)) * 10.0, 0.0),
        target_bounds=(min(lats), min(lons), max(lats), max(lons)),
        intermediate_point_count=0,
        intermediate_section_count=0,
    )


def _convert(model: FeederModel, path: Path) -> dict:
    geography = _chain_geography(model)
    write_dgs(model, path, geography=geography)
    return validate_dgs(model, path, geography=geography)


def test_adjacency_index_is_not_rebuilt_per_line(tmp_path, monkeypatch):
    """The guard: index builds must stay constant, not grow with section count."""
    calls = {'n': 0}
    original = dgs_module._line_neighbors

    def counting(model):
        calls['n'] += 1
        return original(model)

    monkeypatch.setattr(dgs_module, '_line_neighbors', counting)

    model = _chain_model(300)
    report = _convert(model, tmp_path / 'chain.dgs')

    assert report['errors_total'] == 0, report
    assert calls['n'] <= MAX_NEIGHBOR_BUILDS, (
        f'_line_neighbors se construyó {calls["n"]} veces para 300 tramos; '
        'volvió a quedar dentro de un bucle (regresión O(lines²))'
    )


def test_conversion_cost_grows_linearly_with_sections(tmp_path):
    """Quadrupling the sections must not multiply the cost by ~16."""
    small = _chain_model(200)
    large = _chain_model(800)

    start = time.perf_counter()
    _convert(small, tmp_path / 'small.dgs')
    t_small = time.perf_counter() - start

    start = time.perf_counter()
    _convert(large, tmp_path / 'large.dgs')
    t_large = time.perf_counter() - start

    if t_small < 0.02:  # too fast to time reliably on this machine
        pytest.skip(f'medición no fiable: {t_small * 1000:.1f} ms para 200 tramos')

    ratio = t_large / t_small
    # Linear ≈ 4×, quadratic ≈ 16×. 8× leaves room for constant overhead and jitter.
    assert ratio < 8.0, f'coste ×{ratio:.1f} al cuadruplicar los tramos (esperado ≈4, cuadrático ≈16)'


def test_largest_reference_feeder_within_time_budget(ds, tmp_path):
    """End-to-end budget on real data; skipped when the TXT set is absent."""
    from igea_dgs.geography import build_geography
    from igea_dgs.model import build_feeder_model

    network_id = max(
        (nid for nid in ds.feeder_ids() if ds.feeders[nid]),
        key=lambda nid: len(ds.feeders[nid]),
    )
    sections = len(ds.feeders[network_id])

    start = time.perf_counter()
    model = build_feeder_model(ds, network_id, strict=True)
    geography = build_geography(ds, model, source_crs='EPSG:32718')
    out = tmp_path / 'largest.dgs'
    write_dgs(model, out, geography=geography)
    report = validate_dgs(model, out, geography=geography)
    elapsed = time.perf_counter() - start

    assert report['errors_total'] == 0
    assert elapsed < MAX_SECONDS_LARGEST_FEEDER, (
        f'{model.name} ({sections} tramos) tardó {elapsed:.1f} s, '
        f'presupuesto {MAX_SECONDS_LARGEST_FEEDER} s'
    )
