"""Production readiness sample batch."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))

from igea_dgs.batch import convert_selection
from igea_dgs.dataset import CymdistDataset
from igea_paths import resolve_igea_txt_paths


def main() -> int:
    ds = CymdistDataset.from_files(*resolve_igea_txt_paths())
    sample = ['IN111', 'NA205', 'AL108', 'LL203', 'SI213', 'PE103', 'TM104', 'AL107', 'COH101']
    out = ROOT / 'output' / 'prod_check'
    out.mkdir(parents=True, exist_ok=True)
    manifest = convert_selection(ds, sample, out, source_crs='EPSG:32718', include_geography=True)
    print(json.dumps(manifest['summary'], indent=2))
    for item in manifest['feeders']:
        name = item.get('feeder') or item.get('name') or item.get('network_id')
        print(f"{name}: status={item.get('status')} error={item.get('error') or ''}")
    ok = manifest['summary'].get('ok', 0) == len(sample) and manifest['summary'].get('failed', 0) == 0
    print('SAMPLE_BATCH_PASS' if ok else 'SAMPLE_BATCH_FAIL')
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
