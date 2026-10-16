"""The source CRS must be projected in metres, or conversion is refused.

Historical defect (docs/DIAGNOSTICO_BACKEND_FRONTEND_2026-09-22.md, C-01):
``apply_georeferenced_lengths`` measures euclidean distance over raw CoordX/CoordY
and writes the result as metres, without consulting the CRS units. With coordinates
in degrees the total length of one reference feeder dropped from 127 m to 0.001145 m
(factor 110,575) and the converter still reported ``ok`` with ``errors_total = 0``:
the validator compares the DGS against the same model that produced it, so it is
structurally unable to notice.
"""

from __future__ import annotations

import pytest

from igea_dgs.geography import assert_metre_source_crs

pytest.importorskip('pyproj', reason='la verificación de unidades del CRS requiere pyproj')


@pytest.mark.parametrize('crs', ['EPSG:32718', 'EPSG:32717', 'EPSG:31983', 'EPSG:5343'])
def test_projected_metre_crs_is_accepted(crs):
    assert_metre_source_crs(crs)


@pytest.mark.parametrize(
    ('crs', 'unit'),
    [
        ('EPSG:4326', 'degree'),        # WGS84 lon/lat — el caso del defecto
        ('EPSG:4258', 'degree'),        # ETRS89 geográfico
        ('EPSG:2230', 'US survey foot'),  # proyectado, pero en pies
    ],
)
def test_non_metre_crs_is_refused_with_actionable_message(crs, unit):
    with pytest.raises(ValueError) as excinfo:
        assert_metre_source_crs(crs)
    message = str(excinfo.value)
    assert crs in message
    assert unit in message
    assert 'metros' in message


def test_unknown_crs_is_refused():
    with pytest.raises(ValueError, match='no reconocido'):
        assert_metre_source_crs('EPSG:no-existe')


def test_batch_refuses_degree_crs_before_writing_anything(ds, sample_feeder, tmp_path):
    """El lote debe fallar antes de escribir, no producir un DGS 'válido'."""
    from igea_dgs.batch import convert_selection

    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='no metros'):
        convert_selection(
            ds, [sample_feeder], out,
            include_geography=True, source_crs='EPSG:4326', strict=True,
        )
    assert not list(out.glob('*.dgs'))


def test_no_geography_does_not_require_a_metre_crs(ds, sample_feeder, tmp_path):
    """Sin georreferenciación el CRS es irrelevante y no debe bloquear."""
    from igea_dgs.batch import convert_selection

    manifest = convert_selection(
        ds, [sample_feeder], tmp_path / 'out',
        include_geography=False, source_crs='EPSG:4326', strict=True,
    )
    assert manifest['summary']['failed'] == 0
