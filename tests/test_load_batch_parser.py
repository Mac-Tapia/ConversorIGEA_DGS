"""Focused multi-feeder parser edge cases kept independent of PF tooling."""

from __future__ import annotations

from types import SimpleNamespace


def test_new_sed_coordinate_tie_is_reported_as_ambiguous():
    from igea_dgs.loads_create import NewSedLoad, split_create_by_feeder

    node = SimpleNamespace(node_id='N1', x=10.0, y=20.0)
    models = {
        'F-A': SimpleNamespace(nodes={'N1': node}),
        'F-B': SimpleNamespace(nodes={'N1': node}),
    }
    row = NewSedLoad(
        sed_code='SED-TIE', installed_kva=100.0, kw=20.0,
        coord_x=10.0, coord_y=20.0,
    )

    routed, errors = split_create_by_feeder({'GENERAL': ([row], [])}, models)

    assert routed['F-A'][0] == [] and routed['F-B'][0] == []
    assert len(errors) == 1
    assert 'ambigua' in errors[0].lower()
    assert 'F-A' in errors[0] and 'F-B' in errors[0]
