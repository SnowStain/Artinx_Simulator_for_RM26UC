import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import build_robot_venue_map_asset as builder


def load_source_map(source_path: Path):
    with source_path.open('r', encoding='utf-8-sig') as handle:
        return json.load(handle)


def move_first_rect_facility(payload, delta_px=12.0):
    updated = deepcopy(payload)
    facilities = updated.get('map', {}).get('facilities', [])
    for facility in facilities:
        if facility.get('shape') == 'rect' and 'x1' in facility and 'x2' in facility:
            facility['x1'] = float(facility['x1']) + delta_px
            facility['x2'] = float(facility['x2']) + delta_px
            return updated, facility.get('id')
    raise RuntimeError('未找到可演示增量修改的 rect 设施')


def main():
    workspace = WORKSPACE_ROOT
    source_path = workspace / 'maps' / 'basicMap' / 'map.json'
    payload = load_source_map(source_path)
    updated_payload, facility_id = move_first_rect_facility(payload)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_input = Path(temp_dir) / 'incremental_map.json'
        temp_output = Path(temp_dir) / 'incremental_asset'
        with temp_input.open('w', encoding='utf-8') as handle:
            json.dump(updated_payload, handle, ensure_ascii=False, indent=2)
        result = builder.build_asset_package(temp_input, temp_output, zip_enabled=False)
        print(f'incremental rebuild facility: {facility_id}')
        print(f'output dir: {result["output_dir"]}')
        print(f'status: {result["status"]}')


if __name__ == '__main__':
    main()