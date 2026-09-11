from pathlib import Path
import json

from igea_dgs.model import build_feeder_model


def test_batch_writes_geography_and_integrated_validation(ds, sample_feeder, tmp_path):
    from igea_dgs.batch import convert_selection

    model = build_feeder_model(ds, sample_feeder)
    manifest = convert_selection(ds, [sample_feeder], tmp_path, source_crs='EPSG:32718', include_geography=True)
    assert manifest['summary'] == {'requested': 1, 'ok': 1, 'failed': 0}
    item = manifest['feeders'][0]
    assert Path(item['geography']).exists()
    assert Path(item['geography_validation']).exists()
    report = json.loads(Path(item['validation_json']).read_text(encoding='utf-8'))
    assert report['geographic_errors'] == []
    assert report['graphic_errors'] == []
    assert report['counts']['dgs_diagrams'] == 1
    assert report['counts']['dgs_graphics'] > 0
    assert report['counts']['dgs_graphic_connections'] == (
        2 * len(model.lines) + len(model.loads) + 1
    )
    assert report['counts']['dgs_pointterms'] <= len(model.nodes)
    assert report['counts']['dgs_lines'] == len(model.lines)
