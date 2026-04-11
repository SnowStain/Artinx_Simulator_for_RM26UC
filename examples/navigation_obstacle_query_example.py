import json
from pathlib import Path


def load_metadata(metadata_path: Path):
    with metadata_path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def find_blocking_facilities(metadata, tag=None):
    facilities = metadata.get('facilities', [])
    blocking = [item for item in facilities if item.get('block_movement')]
    if tag:
        blocking = [item for item in blocking if item.get('tag') == tag]
    return blocking


def main():
    metadata_path = Path(__file__).resolve().parents[1] / 'robot_venue_map_asset' / 'venue_map_metadata.json'
    metadata = load_metadata(metadata_path)
    blocking = find_blocking_facilities(metadata)
    print(f'blocking facility count: {len(blocking)}')
    for facility in blocking[:10]:
        print(f'- {facility.get("id")} type={facility.get("type")} tag={facility.get("tag")} pos={facility.get("position")}')


if __name__ == '__main__':
    main()