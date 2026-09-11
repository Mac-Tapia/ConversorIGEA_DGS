from pathlib import Path
import json

from igea_dgs.dataset import CymdistDataset

RED = Path('/mnt/data/RED_030826(1).txt')
LOAD = Path('/mnt/data/CARGA_030826(1).txt')
EQUIP = Path('/mnt/data/BD_Equipo_V261124 (1)(1).txt')


def test_batch_writes_geography_and_integrated_validation(tmp_path):
    from igea_dgs.batch import convert_selection

    ds = CymdistDataset.from_files(RED, LOAD, EQUIP)
    manifest = convert_selection(ds, ['IN111'], tmp_path, source_crs='EPSG:32718', include_geography=True)
    assert manifest['summary'] == {'requested': 1, 'ok': 1, 'failed': 0}
    item = manifest['feeders'][0]
    assert Path(item['geography']).exists()
    assert Path(item['geography_validation']).exists()
    report = json.loads(Path(item['validation_json']).read_text(encoding='utf-8'))
    assert report['geographic_errors'] == []
    assert report['graphic_errors'] == []
    assert report['counts']['dgs_diagrams'] == 1
    assert report['counts']['dgs_graphics'] == 1936 + 1934 + 383 + 1
    assert report['counts']['dgs_graphic_connections'] == 2 * 1934 + 383 + 1
