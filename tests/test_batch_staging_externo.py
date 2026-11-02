"""065:RF-10 / 065:RF-11: también el lote prepara DGS fuera de su salida durable."""
from pathlib import Path

import pytest
from synthetic_export import ExportSpec, load_export


@pytest.mark.parametrize('grupo', [False, True])
@pytest.mark.parametrize('layout', ['reducido', 'completo'])
def test_dgs_se_prepara_fuera_y_limpia_al_terminar(tmp_path, monkeypatch, grupo, layout):
    """065:RF-10 / 065:RF-11 / 065:RF-12 — ambas vías conservan sus artefactos completos."""
    from convertersmartgrid import batch
    from convertersmartgrid.runtime_paths import rutas_runtime
    monkeypatch.setenv('CSG_RUNTIME_HOME', str(tmp_path / 'runtime'))
    monkeypatch.setenv('CSG_CACHE_HOME', str(tmp_path / 'cache'))
    dataset = load_export(ExportSpec(feeders=2, sections_per_feeder=3,
                                   loads_per_feeder=1, switches_per_feeder=0,
                                   seed=173, layout=layout), tmp_path / 'entrada')
    out = tmp_path / 'salida'
    original = batch.write_dgs
    observed = []
    def write(model, path, **kwargs):
        assert not Path(path).resolve().is_relative_to(out.resolve())
        assert Path(path).anchor == out.anchor
        observed.append(Path(path))
        return original(model, path, **kwargs)
    monkeypatch.setattr(batch, 'write_dgs', write)
    selected = list(dataset.feeder_ids())
    if grupo:
        result = batch.convert_group(dataset, selected, out, name='grupo', include_geography=False)
        assert result['status'] == 'ok', result
    else:
        result = batch.convert_selection(dataset, selected, out, workers=1, include_geography=False)
        assert result['summary']['ok'] == len(selected), result
    assert observed
    assert not list(out.glob(batch.STAGE_PREFIX + '*'))
    assert not list(rutas_runtime().staging_para(out).rglob('owner.json'))
    assert list(out.glob('*.dgs'))
