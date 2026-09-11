from pathlib import Path
import json

from igea_dgs.model import build_feeder_model


def test_batch_writes_geography_and_integrated_validation(ds, sample_feeder, tmp_path):
    from igea_dgs.batch import convert_selection
    from igea_dgs.dgs import diagram_line_sections

    model = build_feeder_model(ds, sample_feeder)
    nested_keys = {sed.load_key for sed in model.seds}
    free_loads = sum(
        1 for load in model.loads if (load.section_id, load.device_number) not in nested_keys
    )
    drawn_lines = len(diagram_line_sections(model))
    manifest = convert_selection(ds, [sample_feeder], tmp_path, source_crs='EPSG:32718', include_geography=True)
    assert manifest['summary'] == {'requested': 1, 'ok': 1, 'skipped': 0, 'failed': 0}
    item = manifest['feeders'][0]
    assert Path(item['geography']).exists()
    assert Path(item['geography_validation']).exists()
    report = json.loads(Path(item['validation_json']).read_text(encoding='utf-8'))
    assert report['geographic_errors'] == []
    assert report['graphic_errors'] == []
    assert report['counts']['dgs_diagrams'] == 1
    assert report['counts']['dgs_graphics'] > 0
    # Free loads keep d_load+IntGrfcon; SED loads are modules inside SecSubProd.
    # Micro service stubs stay electrical-only (no d_lin dust).
    assert report['counts']['dgs_graphic_connections'] == (
        2 * drawn_lines + free_loads + 1
    )
    assert report['counts']['dgs_pointterms'] <= len(model.nodes)
    assert report['counts']['dgs_lines'] == len(model.lines)
    assert report['counts']['dgs_seds'] == len(model.seds)
