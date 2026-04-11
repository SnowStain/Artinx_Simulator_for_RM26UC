import argparse
import json
import math
import os
import shutil
import sys
import time
import tracemalloc
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import numpy as np
import trimesh
from trimesh.transformations import rotation_matrix, translation_matrix

from core.config_manager import ConfigManager


ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / 'robot_venue_map_asset'
DEFAULT_CONFIG_PATH = ROOT_DIR / 'config.json'
DEFAULT_SETTINGS_PATH = ROOT_DIR / 'CommonSetting.json'
DEFAULT_INPUT_CANDIDATES = (
    ROOT_DIR / 'map.json',
    ROOT_DIR / 'maps' / 'basicMap' / 'map.json',
    ROOT_DIR / 'map_presets' / 'basicMap.json',
)

SOURCE_TYPE_DEFAULTS = {
    'boundary': {'normalized_type': 'wall', 'height': 0.5, 'block_movement': True, 'block_vision': True, 'tag': 'boundary'},
    'wall': {'normalized_type': 'wall', 'height': 0.5, 'block_movement': True, 'block_vision': True, 'tag': 'wall'},
    'base': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'base'},
    'outpost': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'outpost'},
    'supply': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'supply'},
    'mineral_exchange': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'mineral_exchange'},
    'mining_area': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'mining_area'},
    'energy_mechanism': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'energy_mechanism'},
    'buff_supply': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_supply'},
    'buff_outpost': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_outpost'},
    'buff_base': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_base'},
    'buff_fort': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_fort'},
    'buff_trapezoid_highland': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_trapezoid_highland'},
    'buff_hero_deployment': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_hero_deployment'},
    'buff_central_highland': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'buff_central_highland'},
    'buff_terrain_highland_red_start': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_highland_red_start'},
    'buff_terrain_highland_red_end': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_highland_red_end'},
    'buff_terrain_highland_blue_start': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_highland_blue_start'},
    'buff_terrain_highland_blue_end': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_highland_blue_end'},
    'buff_terrain_road_red_start': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_road_red_start'},
    'buff_terrain_road_red_end': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_road_red_end'},
    'buff_terrain_road_blue_start': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_road_blue_start'},
    'buff_terrain_road_blue_end': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'terrain_road_blue_end'},
    'first_step': {'normalized_type': 'ramp', 'height': 0.18, 'block_movement': True, 'block_vision': False, 'tag': 'first_step', 'rotation_x_deg': 30.0},
    'second_step': {'normalized_type': 'ramp', 'height': 0.28, 'block_movement': True, 'block_vision': False, 'tag': 'second_step', 'rotation_x_deg': 30.0},
    'fly_slope': {'normalized_type': 'ramp', 'height': 0.18, 'block_movement': True, 'block_vision': False, 'tag': 'fly_slope', 'rotation_x_deg': 30.0},
    'rugged_road': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'rugged_road'},
    'dog_hole': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'dog_hole'},
    'dead_zone': {'normalized_type': 'ground_mark', 'height': 0.01, 'block_movement': False, 'block_vision': False, 'tag': 'dead_zone'},
}


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def ensure_clean_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def resolve_active_map_payload(config_path, settings_path):
    if not config_path.exists():
        return None, None
    config_manager = ConfigManager()
    config = config_manager.load_config(str(config_path), str(settings_path))
    map_config = deepcopy(config.get('map', {}))
    preset_name = map_config.get('preset')
    if preset_name:
        preset_path = config_manager._resolve_map_preset_path(preset_name, str(config_path))
        if preset_path and os.path.exists(preset_path):
            return Path(preset_path).resolve(), None
    if map_config.get('facilities') is not None:
        payload = {
            'version': 1,
            'name': map_config.get('preset') or 'active_map',
            'saved_at': now_iso(),
            'map': map_config,
        }
        return None, payload
    return None, None


def resolve_input_source(args):
    if args.input:
        return Path(args.input).resolve(), None
    root_map = DEFAULT_INPUT_CANDIDATES[0]
    if root_map.exists():
        return root_map.resolve(), None
    active_path, active_payload = resolve_active_map_payload(Path(args.config).resolve(), Path(args.settings).resolve())
    if active_path is not None or active_payload is not None:
        return active_path, active_payload
    for candidate in DEFAULT_INPUT_CANDIDATES[1:]:
        if candidate.exists():
            return candidate.resolve(), None
    raise FileNotFoundError('未找到可用输入文件；请传入 --input，或保证根目录 map.json / 当前激活地图可用。')


def load_json(path: Path):
    with path.open('r', encoding='utf-8-sig') as handle:
        return json.load(handle)


def save_json(path: Path, payload):
    with path.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def signed_area(points):
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return total * 0.5


def point_in_triangle(point, a, b, c):
    px, py = point
    ax, ay = a
    bx, by = b
    cx, cy = c
    v0 = (cx - ax, cy - ay)
    v1 = (bx - ax, by - ay)
    v2 = (px - ax, py - ay)
    dot00 = v0[0] * v0[0] + v0[1] * v0[1]
    dot01 = v0[0] * v1[0] + v0[1] * v1[1]
    dot02 = v0[0] * v2[0] + v0[1] * v2[1]
    dot11 = v1[0] * v1[0] + v1[1] * v1[1]
    dot12 = v1[0] * v2[0] + v1[1] * v2[1]
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) < 1e-9:
        return False
    inv_denom = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv_denom
    v = (dot00 * dot12 - dot01 * dot02) * inv_denom
    return u >= 0.0 and v >= 0.0 and (u + v) <= 1.0


def is_convex(prev_pt, cur_pt, next_pt):
    return ((cur_pt[0] - prev_pt[0]) * (next_pt[1] - cur_pt[1]) - (cur_pt[1] - prev_pt[1]) * (next_pt[0] - cur_pt[0])) > 1e-9


def triangulate_polygon(points):
    points_2d = [(float(point[0]), float(point[1])) for point in points]
    if len(points_2d) < 3:
        raise ValueError('polygon requires at least three points')
    if signed_area(points_2d) < 0:
        points_2d = list(reversed(points_2d))
    indices = list(range(len(points_2d)))
    triangles = []
    guard = 0
    while len(indices) > 3 and guard < len(points_2d) * len(points_2d):
        ear_found = False
        for offset, current_index in enumerate(indices):
            prev_index = indices[offset - 1]
            next_index = indices[(offset + 1) % len(indices)]
            prev_pt = points_2d[prev_index]
            cur_pt = points_2d[current_index]
            next_pt = points_2d[next_index]
            if not is_convex(prev_pt, cur_pt, next_pt):
                continue
            triangle = (prev_pt, cur_pt, next_pt)
            blocked = False
            for test_index in indices:
                if test_index in (prev_index, current_index, next_index):
                    continue
                if point_in_triangle(points_2d[test_index], *triangle):
                    blocked = True
                    break
            if blocked:
                continue
            triangles.append((prev_index, current_index, next_index))
            indices.pop(offset)
            ear_found = True
            break
        if not ear_found:
            break
        guard += 1
    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))
    if not triangles:
        raise ValueError('polygon triangulation failed')
    return points_2d, triangles


def extrude_polygon(points, height):
    points_2d, triangles = triangulate_polygon(points)
    height = float(height)
    bottom_vertices = np.array([[x, 0.0, z] for x, z in points_2d], dtype=np.float64)
    top_vertices = np.array([[x, height, z] for x, z in points_2d], dtype=np.float64)
    vertices = np.vstack([bottom_vertices, top_vertices])
    vertex_count = len(points_2d)
    faces = []
    for a, b, c in triangles:
        faces.append([c, b, a])
        faces.append([a + vertex_count, b + vertex_count, c + vertex_count])
    for index in range(vertex_count):
        next_index = (index + 1) % vertex_count
        faces.append([index, next_index, next_index + vertex_count])
        faces.append([index, next_index + vertex_count, index + vertex_count])
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces, dtype=np.int64), process=False)
    mesh.remove_unreferenced_vertices()
    mesh.merge_vertices()
    return mesh


def polygon_centroid(points):
    points_2d = np.array(points, dtype=np.float64)
    return np.mean(points_2d, axis=0)


def convert_px_to_meters(x_px, y_px, width_px, height_px, venue_width_m, venue_depth_m):
    x_m = float(x_px) / float(width_px) * float(venue_width_m)
    z_m = float(venue_depth_m) - (float(y_px) / float(height_px) * float(venue_depth_m))
    return x_m, z_m


def copy_input_file(input_path: Path | None, input_payload, output_dir: Path):
    copied = output_dir / 'input_map_copy.json'
    if input_path is not None:
        shutil.copy2(input_path, copied)
        return copied
    if input_payload is None:
        raise ValueError('input payload is required when input_path is None')
    save_json(copied, input_payload)
    return copied


def make_warning(message, severity='warning', facility_id=None):
    payload = {'severity': severity, 'message': message}
    if facility_id is not None:
        payload['facility_id'] = facility_id
    return payload


def normalize_standard_schema(payload, input_path):
    warnings = []
    venue_size = payload.get('venue_size', [28.0, 15.0])
    facilities = payload.get('facilities')
    if facilities is None:
        raise ValueError('标准 schema 缺少 facilities 字段')
    standard_facilities = []
    seen_ids = set()
    for raw in facilities:
        facility_id = str(raw.get('id'))
        if facility_id in seen_ids:
            raise ValueError(f'存在重复设施 ID: {facility_id}')
        seen_ids.add(facility_id)
        position = raw.get('position')
        size = raw.get('size')
        if not position or len(position) != 3:
            raise ValueError(f'设施 {facility_id} 缺少合法 position')
        if not size or len(size) != 3:
            raise ValueError(f'设施 {facility_id} 缺少合法 size')
        standard_facilities.append({
            'id': facility_id,
            'type': str(raw.get('type', 'obstacle')),
            'position': [float(position[0]), float(position[1]), float(position[2])],
            'size': [float(size[0]), float(size[1]), float(size[2])],
            'rotation': float(raw.get('rotation', 0.0)),
            'block_movement': bool(raw.get('block_movement', True)),
            'block_vision': bool(raw.get('block_vision', True)),
            'tag': str(raw.get('tag', 'default')),
            'source_shape': 'box',
            'source_path': str(input_path.name),
        })
    return {
        'source_schema': 'task_standard',
        'input_file': str(input_path),
        'venue_size': [float(venue_size[0]), float(venue_size[1])],
        'facilities': standard_facilities,
        'terrain_grid': deepcopy(payload.get('terrain_grid') or {}),
        'function_grid': deepcopy(payload.get('function_grid') or {}),
        'runtime_meta': deepcopy(payload.get('runtime_meta') or {}),
        'warnings': warnings,
    }


def infer_defaults_for_source_type(source_type):
    return deepcopy(SOURCE_TYPE_DEFAULTS.get(source_type, {
        'normalized_type': 'obstacle',
        'height': 0.2,
        'block_movement': True,
        'block_vision': True,
        'tag': source_type or 'default',
    }))


def normalize_project_schema(payload, input_path):
    warnings = [make_warning('输入不是任务书标准 schema，已按项目地图格式自动适配。', severity='info')]
    map_payload = payload.get('map') or {}
    facilities = map_payload.get('facilities')
    if facilities is None:
        raise ValueError('项目地图格式缺少 map.facilities 字段')
    width_px = float(map_payload.get('width') or map_payload.get('source_width') or 1576.0)
    height_px = float(map_payload.get('height') or map_payload.get('source_height') or 873.0)
    venue_width_m = float(map_payload.get('field_length_m', 28.0))
    venue_depth_m = float(map_payload.get('field_width_m', 15.0))
    seen_ids = set()
    standard_facilities = []
    for raw in facilities:
        facility_id = str(raw.get('id'))
        if facility_id in seen_ids:
            raise ValueError(f'存在重复设施 ID: {facility_id}')
        seen_ids.add(facility_id)
        source_type = str(raw.get('type', 'obstacle'))
        defaults = infer_defaults_for_source_type(source_type)
        source_shape = str(raw.get('shape', 'rect'))
        rotation_deg = float(raw.get('rotation', 0.0))
        if source_shape == 'rect':
            x1 = float(raw.get('x1', 0.0))
            x2 = float(raw.get('x2', x1))
            y1 = float(raw.get('y1', 0.0))
            y2 = float(raw.get('y2', y1))
            center_x_px = (x1 + x2) * 0.5
            center_y_px = (y1 + y2) * 0.5
            center_x_m, center_z_m = convert_px_to_meters(center_x_px, center_y_px, width_px, height_px, venue_width_m, venue_depth_m)
            size_x_m = abs(x2 - x1) / width_px * venue_width_m
            size_z_m = abs(y2 - y1) / height_px * venue_depth_m
            size_y_m = float(raw.get('height_m', 0.0)) or float(defaults['height'])
            standard_facilities.append({
                'id': facility_id,
                'type': defaults['normalized_type'],
                'position': [center_x_m, size_y_m * 0.5 if defaults['normalized_type'] != 'ground_mark' else 0.005, center_z_m],
                'size': [max(size_x_m, 0.01), max(size_y_m if defaults['normalized_type'] != 'ground_mark' else 0.01, 0.01), max(size_z_m, 0.01)],
                'rotation': rotation_deg,
                'rotation_x_deg': float(defaults.get('rotation_x_deg', 0.0)),
                'block_movement': bool(raw.get('block_movement', defaults['block_movement'])),
                'block_vision': bool(raw.get('block_vision', defaults['block_vision'])),
                'tag': str(raw.get('tag', defaults['tag'])),
                'source_type': source_type,
                'source_shape': source_shape,
                'source_bounds_px': [x1, y1, x2, y2],
            })
        elif source_shape == 'polygon':
            raw_points = raw.get('points') or []
            if len(raw_points) < 3:
                warnings.append(make_warning('polygon 点数不足，已跳过该设施', severity='error', facility_id=facility_id))
                continue
            points_m = [convert_px_to_meters(point[0], point[1], width_px, height_px, venue_width_m, venue_depth_m) for point in raw_points]
            centroid_x, centroid_z = polygon_centroid(points_m)
            size_y_m = float(raw.get('height_m', 0.0)) or float(defaults['height'])
            standard_facilities.append({
                'id': facility_id,
                'type': defaults['normalized_type'],
                'position': [float(centroid_x), size_y_m * 0.5 if defaults['normalized_type'] != 'ground_mark' else 0.005, float(centroid_z)],
                'size': [0.0, max(size_y_m if defaults['normalized_type'] != 'ground_mark' else 0.01, 0.01), 0.0],
                'rotation': rotation_deg,
                'rotation_x_deg': float(defaults.get('rotation_x_deg', 0.0)),
                'block_movement': bool(raw.get('block_movement', defaults['block_movement'])),
                'block_vision': bool(raw.get('block_vision', defaults['block_vision'])),
                'tag': str(raw.get('tag', defaults['tag'])),
                'source_type': source_type,
                'source_shape': source_shape,
                'source_points': [[float(point[0]), float(point[1])] for point in points_m],
            })
        else:
            warnings.append(make_warning(f'不支持的 source shape {source_shape}，已按矩形兜底', facility_id=facility_id))
            x1 = float(raw.get('x1', 0.0))
            x2 = float(raw.get('x2', x1))
            y1 = float(raw.get('y1', 0.0))
            y2 = float(raw.get('y2', y1))
            center_x_px = (x1 + x2) * 0.5
            center_y_px = (y1 + y2) * 0.5
            center_x_m, center_z_m = convert_px_to_meters(center_x_px, center_y_px, width_px, height_px, venue_width_m, venue_depth_m)
            standard_facilities.append({
                'id': facility_id,
                'type': 'obstacle',
                'position': [center_x_m, 0.1, center_z_m],
                'size': [max(abs(x2 - x1) / width_px * venue_width_m, 0.01), 0.2, max(abs(y2 - y1) / height_px * venue_depth_m, 0.01)],
                'rotation': 0.0,
                'rotation_x_deg': 0.0,
                'block_movement': True,
                'block_vision': True,
                'tag': source_type,
                'source_type': source_type,
                'source_shape': 'rect',
                'source_bounds_px': [x1, y1, x2, y2],
            })
        pos_x, _, pos_z = standard_facilities[-1]['position']
        if pos_x < 0.0 or pos_x > venue_width_m or pos_z < 0.0 or pos_z > venue_depth_m:
            warnings.append(make_warning('设施中心超出场地范围，已保留生成并记录警告。', facility_id=facility_id))
    return {
        'source_schema': 'project_map_schema',
        'input_file': str(input_path),
        'venue_size': [venue_width_m, venue_depth_m],
        'facilities': standard_facilities,
        'terrain_grid': deepcopy(map_payload.get('terrain_grid') or {}),
        'function_grid': deepcopy(map_payload.get('function_grid') or {}),
        'runtime_meta': deepcopy(map_payload.get('runtime_grid') or {}),
        'warnings': warnings,
    }


def normalize_input(payload, input_path):
    if 'venue_size' in payload and 'facilities' in payload:
        return normalize_standard_schema(payload, input_path)
    if 'map' in payload and isinstance(payload.get('map'), dict):
        return normalize_project_schema(payload, input_path)
    raise ValueError('输入文件既不是任务书标准 schema，也不是当前项目地图 schema。')


def create_box(extents, center, name=None):
    mesh = trimesh.creation.box(extents=extents)
    mesh.apply_translation(center)
    if name is not None:
        mesh.metadata['name'] = name
    return mesh


def build_base_meshes(standard_config):
    venue_width, venue_depth = standard_config['venue_size']
    base_items = []
    ground = create_box((venue_width, 0.1, venue_depth), (venue_width * 0.5, -0.05, venue_depth * 0.5), name='venue_ground')
    ground.metadata.update({'id': 'venue_ground', 'tag': 'venue_base', 'block_movement': False, 'block_vision': False})
    base_items.append({'mesh': ground, 'metadata': deepcopy(ground.metadata), 'category': 'base'})
    wall_specs = [
        ('boundary_south', (venue_width, 0.5, 0.1), (venue_width * 0.5, 0.25, 0.05)),
        ('boundary_north', (venue_width, 0.5, 0.1), (venue_width * 0.5, 0.25, venue_depth - 0.05)),
        ('boundary_west', (0.1, 0.5, venue_depth), (0.05, 0.25, venue_depth * 0.5)),
        ('boundary_east', (0.1, 0.5, venue_depth), (venue_width - 0.05, 0.25, venue_depth * 0.5)),
    ]
    for wall_id, extents, center in wall_specs:
        wall = create_box(extents, center, name=wall_id)
        wall.metadata.update({'id': wall_id, 'tag': 'venue_base', 'block_movement': True, 'block_vision': True})
        base_items.append({'mesh': wall, 'metadata': deepcopy(wall.metadata), 'category': 'base'})
    return base_items


def mesh_from_standard_facility(facility):
    primitive_type = facility['type']
    facility_id = facility['id']
    source_shape = facility.get('source_shape', 'box')
    if source_shape == 'polygon' and facility.get('source_points'):
        extrusion_height = facility['size'][1] if primitive_type != 'ground_mark' else 0.01
        mesh = extrude_polygon(facility['source_points'], extrusion_height)
        if primitive_type == 'ground_mark':
            mesh.apply_translation((0.0, 0.0, 0.0))
    elif primitive_type == 'cylinder_pillar':
        radius = max(float(facility['size'][0]) * 0.5, 0.01)
        height = max(float(facility['size'][1]), 0.01)
        mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=16)
    else:
        extents = facility['size']
        mesh = trimesh.creation.box(extents=extents)
    if source_shape != 'polygon' or primitive_type == 'cylinder_pillar':
        rot_x_deg = float(facility.get('rotation_x_deg', 0.0))
        rot_y_deg = float(facility.get('rotation', 0.0))
        if abs(rot_x_deg) > 1e-6:
            mesh.apply_transform(rotation_matrix(math.radians(rot_x_deg), [1, 0, 0]))
        if abs(rot_y_deg) > 1e-6:
            mesh.apply_transform(rotation_matrix(math.radians(rot_y_deg), [0, 1, 0]))
        mesh.apply_transform(translation_matrix(facility['position']))
    else:
        rot_y_deg = float(facility.get('rotation', 0.0))
        if abs(rot_y_deg) > 1e-6:
            centroid = np.array(facility['position'], dtype=np.float64)
            mesh.apply_translation(-centroid)
            mesh.apply_transform(rotation_matrix(math.radians(rot_y_deg), [0, 1, 0]))
            mesh.apply_translation(centroid)
    mesh.metadata.update({
        'id': facility_id,
        'type': primitive_type,
        'tag': facility['tag'],
        'block_movement': facility['block_movement'],
        'block_vision': facility['block_vision'],
        'source_type': facility.get('source_type', primitive_type),
        'source_shape': source_shape,
    })
    return mesh


def build_facility_meshes(standard_config, warnings):
    items = []
    for facility in standard_config['facilities']:
        facility_id = facility['id']
        if facility.get('source_type') == 'boundary':
            warnings.append(make_warning('boundary 设施由基础边界墙体统一表示，单独设施网格跳过。', severity='info', facility_id=facility_id))
            continue
        try:
            mesh = mesh_from_standard_facility(facility)
            items.append({'mesh': mesh, 'metadata': deepcopy(facility), 'category': 'facility'})
        except Exception as exc:
            warnings.append(make_warning(f'设施网格生成失败: {exc}', severity='error', facility_id=facility_id))
    return items


def optimize_mesh(mesh):
    mesh = mesh.copy()
    mesh.merge_vertices()
    try:
        mesh.update_faces(mesh.unique_faces())
    except Exception:
        pass
    try:
        mesh.update_faces(mesh.nondegenerate_faces())
    except Exception:
        pass
    mesh.remove_unreferenced_vertices()
    return mesh


def build_combined_mesh(items):
    meshes = [entry['mesh'] for entry in items if entry.get('mesh') is not None]
    if not meshes:
        raise ValueError('没有可合并的网格')
    combined = trimesh.util.concatenate(meshes)
    return optimize_mesh(combined)


def build_collision_mesh(items):
    collision_items = []
    for entry in items:
        metadata = entry.get('metadata', {})
        if entry.get('category') == 'base':
            collision_items.append(entry['mesh'])
            continue
        if metadata.get('block_movement', False):
            collision_items.append(entry['mesh'])
    if not collision_items:
        return trimesh.creation.box(extents=(0.01, 0.01, 0.01))
    return optimize_mesh(trimesh.util.concatenate(collision_items))


def build_scene(items, metadata_payload):
    scene = trimesh.Scene()
    scene.metadata = metadata_payload
    for entry in items:
        geom_name = entry['metadata'].get('id', f'geom_{len(scene.geometry)}')
        mesh = entry['mesh'].copy()
        mesh.metadata.update(entry['metadata'])
        scene.add_geometry(mesh, node_name=geom_name, geom_name=geom_name)
    return scene


def export_glb(scene, path: Path):
    path.write_bytes(scene.export(file_type='glb'))


def export_obj(mesh, obj_path: Path):
    obj_text = mesh.export(file_type='obj', include_texture=False, return_texture=False)
    if isinstance(obj_text, bytes):
        obj_text = obj_text.decode('utf-8')
    mtl_name = obj_path.with_suffix('.mtl').name
    obj_text = f'mtllib {mtl_name}\n' + obj_text
    obj_path.write_text(obj_text, encoding='utf-8')
    obj_path.with_suffix('.mtl').write_text('newmtl default\nKd 0.75 0.75 0.75\nKa 0.2 0.2 0.2\nKs 0.0 0.0 0.0\n', encoding='utf-8')


def compute_vertex_normals(mesh):
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    normals = np.zeros_like(vertices, dtype=np.float64)
    if len(vertices) == 0 or len(faces) == 0:
        return normals.astype(np.float32)
    triangles = vertices[faces]
    face_normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    lengths = np.linalg.norm(normals, axis=1)
    non_zero = lengths > 1e-9
    normals[non_zero] /= lengths[non_zero][:, None]
    return normals.astype(np.float32)


def build_moderngl_payload(mesh, output_path: Path):
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    indices = np.asarray(mesh.faces.reshape(-1), dtype=np.uint32)
    normals = compute_vertex_normals(mesh)
    if normals.shape != vertices.shape:
        normals = np.zeros_like(vertices, dtype=np.float32)
    min_x = float(vertices[:, 0].min()) if len(vertices) else 0.0
    max_x = float(vertices[:, 0].max()) if len(vertices) else 1.0
    min_z = float(vertices[:, 2].min()) if len(vertices) else 0.0
    max_z = float(vertices[:, 2].max()) if len(vertices) else 1.0
    uv = np.zeros((len(vertices), 2), dtype=np.float32)
    if len(vertices):
        span_x = max(max_x - min_x, 1e-6)
        span_z = max(max_z - min_z, 1e-6)
        uv[:, 0] = (vertices[:, 0] - min_x) / span_x
        uv[:, 1] = (vertices[:, 2] - min_z) / span_z
    material = np.array([0.58, 0.62, 0.67, 1.0], dtype=np.float32)
    np.savez_compressed(output_path, vertices=vertices, indices=indices, normals=normals, uv=uv, material_rgba=material)


def make_metadata(standard_config, items, warnings):
    exported_facility_ids = [entry['metadata'].get('id') for entry in items if entry.get('category') == 'facility']
    return {
        'generated_at': now_iso(),
        'source_schema': standard_config['source_schema'],
        'input_file': standard_config['input_file'],
        'venue_size': standard_config['venue_size'],
        'facility_count': len(standard_config['facilities']),
        'exported_facility_ids': exported_facility_ids,
        'facilities': deepcopy(standard_config['facilities']),
        'terrain_grid': deepcopy(standard_config.get('terrain_grid') or {}),
        'function_grid': deepcopy(standard_config.get('function_grid') or {}),
        'runtime_meta': deepcopy(standard_config.get('runtime_meta') or {}),
        'warnings': deepcopy(warnings),
    }


def validate_outputs(output_dir: Path, standard_config, metadata_payload, warnings):
    validation = {
        'generated_at': now_iso(),
        'status': 'passed',
        'checks': [],
        'metrics': {},
        'warnings': deepcopy(warnings),
        'errors': [],
    }
    glb_path = output_dir / 'venue_map.glb'
    ursina_path = output_dir / 'venue_map_ursina.glb'
    obj_path = output_dir / 'venue_map_pybullet.obj'
    npz_path = output_dir / 'venue_map_moderngl_data.npz'
    metadata_path = output_dir / 'venue_map_metadata.json'
    report_path = output_dir / 'build_execution_report.md'
    validation_path = output_dir / 'build_validation_report.json'
    required_files = [glb_path, ursina_path, obj_path, obj_path.with_suffix('.mtl'), npz_path, metadata_path, report_path, validation_path]
    for required in required_files:
        ok = required.exists()
        validation['checks'].append({'name': f'exists:{required.name}', 'passed': ok})
        if not ok:
            validation['errors'].append(f'缺少输出文件: {required.name}')
    load_start = time.perf_counter()
    loaded_glb = trimesh.load(glb_path, force='scene')
    load_elapsed_ms = (time.perf_counter() - load_start) * 1000.0
    validation['checks'].append({'name': 'trimesh_load_glb', 'passed': loaded_glb is not None})
    validation['metrics']['glb_load_ms'] = round(load_elapsed_ms, 3)
    try:
        loaded_ursina = trimesh.load(ursina_path, force='scene')
        validation['checks'].append({'name': 'trimesh_load_ursina_glb', 'passed': loaded_ursina is not None})
    except Exception as exc:
        validation['checks'].append({'name': 'trimesh_load_ursina_glb', 'passed': False, 'details': str(exc)})
        validation['errors'].append(f'Ursina GLB 读取失败: {exc}')
    try:
        loaded_obj = trimesh.load(obj_path, force='mesh')
        validation['checks'].append({'name': 'trimesh_load_obj', 'passed': loaded_obj is not None})
    except Exception as exc:
        validation['checks'].append({'name': 'trimesh_load_obj', 'passed': False, 'details': str(exc)})
        validation['errors'].append(f'OBJ 读取失败: {exc}')
    try:
        moderngl_data = np.load(npz_path)
        validation['checks'].append({'name': 'numpy_load_npz', 'passed': 'vertices' in moderngl_data and 'indices' in moderngl_data})
        validation['metrics']['moderngl_vertex_count'] = int(moderngl_data['vertices'].shape[0])
    except Exception as exc:
        validation['checks'].append({'name': 'numpy_load_npz', 'passed': False, 'details': str(exc)})
        validation['errors'].append(f'NPZ 读取失败: {exc}')
    try:
        metadata_loaded = load_json(metadata_path)
        validation['checks'].append({'name': 'json_load_metadata', 'passed': len(metadata_loaded.get('facilities', [])) == len(metadata_payload.get('facilities', []))})
    except Exception as exc:
        validation['checks'].append({'name': 'json_load_metadata', 'passed': False, 'details': str(exc)})
        validation['errors'].append(f'元数据读取失败: {exc}')
    bounds = loaded_glb.bounds if hasattr(loaded_glb, 'bounds') else None
    venue_width, venue_depth = standard_config['venue_size']
    if bounds is not None:
        size = bounds[1] - bounds[0]
        validation['metrics']['scene_size_xyz_m'] = [round(float(size[0]), 4), round(float(size[1]), 4), round(float(size[2]), 4)]
        validation['checks'].append({'name': 'scene_width_match', 'passed': abs(float(size[0]) - venue_width) <= 0.25})
        validation['checks'].append({'name': 'scene_depth_match', 'passed': abs(float(size[2]) - venue_depth) <= 0.25})
    exported_files = {
        'venue_map.glb': glb_path.stat().st_size,
        'venue_map_ursina.glb': ursina_path.stat().st_size,
        'venue_map_pybullet.obj': obj_path.stat().st_size,
        'venue_map_moderngl_data.npz': npz_path.stat().st_size,
    }
    validation['metrics']['file_sizes_bytes'] = exported_files
    validation['checks'].append({'name': 'main_glb_size_le_5mb', 'passed': exported_files['venue_map.glb'] <= 5 * 1024 * 1024})
    validation['checks'].append({'name': 'glb_load_ms_le_10', 'passed': load_elapsed_ms <= 10.0})
    if hasattr(loaded_glb, 'geometry'):
        face_count = int(sum(len(geometry.faces) for geometry in loaded_glb.geometry.values()))
    else:
        face_count = int(len(loaded_glb.faces))
    validation['metrics']['face_count'] = face_count
    validation['checks'].append({'name': 'face_count_le_10000', 'passed': face_count <= 10000})
    validation['checks'].append({'name': 'facility_count_preserved', 'passed': len(metadata_payload.get('facilities', [])) == len(standard_config.get('facilities', []))})
    failed_checks = [check for check in validation['checks'] if not check.get('passed')]
    if failed_checks:
        validation['status'] = 'failed'
    return validation


def write_execution_report(output_dir: Path, input_path: Path, standard_config, metadata_payload, validation_payload, warnings, metrics_summary):
    lines = [
        '# Robot Venue Map Asset Build Report',
        '',
        f'- 执行时间: {now_iso()}',
        f'- 输入文件: {input_path}',
        f'- 输入 schema: {standard_config["source_schema"]}',
        f'- 场地尺寸: {standard_config["venue_size"][0]}m x {standard_config["venue_size"][1]}m',
        f'- 设施数量: {len(standard_config["facilities"])}',
        '',
        '## 执行步骤',
        '',
        '1. 读取输入文件副本并完成 schema 识别与标准化适配。',
        '2. 生成地面与四周边界基础网格。',
        '3. 按设施逐个构建 box / polygon prism / cylinder / ramp 网格。',
        '4. 合并网格、清理重复顶点与退化面，生成视觉网格与碰撞网格。',
        '5. 导出 GLB / OBJ / NPZ / JSON 资产，并回读校验。',
        '',
        '## 校验摘要',
        '',
        f'- 最终状态: {validation_payload["status"]}',
        f'- 主模型面数: {validation_payload["metrics"].get("face_count", 0)}',
        f'- 主模型大小: {validation_payload["metrics"].get("file_sizes_bytes", {}).get("venue_map.glb", 0)} bytes',
        f'- GLB 加载耗时: {validation_payload["metrics"].get("glb_load_ms", 0.0)} ms',
        f'- 构建峰值内存: {metrics_summary.get("peak_memory_mb", 0.0)} MB',
        '',
        '## 异常与告警',
        '',
    ]
    if warnings:
        for warning in warnings:
            facility_text = f' [{warning.get("facility_id")}]' if warning.get('facility_id') else ''
            lines.append(f'- {warning.get("severity", "warning")}{facility_text}: {warning["message"]}')
    else:
        lines.append('- 无')
    lines.extend([
        '',
        '## 使用示例',
        '',
        '### Ursina',
        '',
        '```python',
        'from ursina import Ursina, Entity',
        'app = Ursina()',
        "Entity(model='robot_venue_map_asset/venue_map_ursina.glb', collider='mesh')",
        'app.run()',
        '```',
        '',
        '### PyBullet',
        '',
        '```python',
        'import pybullet as p',
        'p.connect(p.GUI)',
        "p.createCollisionShape(p.GEOM_MESH, fileName='robot_venue_map_asset/venue_map_pybullet.obj')",
        '```',
        '',
        '### ModernGL',
        '',
        '```python',
        'import numpy as np',
        "payload = np.load('robot_venue_map_asset/venue_map_moderngl_data.npz')",
        "vertices = payload['vertices']",
        "indices = payload['indices']",
        '```',
        '',
        '### 障碍物查询接口示例',
        '',
        '```python',
        'import json',
        "metadata = json.load(open('robot_venue_map_asset/venue_map_metadata.json', encoding='utf-8'))",
        "blocking = [item for item in metadata['facilities'] if item.get('block_movement')]",
        '```',
        '',
        '### 增量修改示例',
        '',
        '```python',
        '# 修改某个 facility 后重新运行构建脚本即可；流程按设施线性处理，不需要全量栅格重建。',
        '```',
    ])
    (output_dir / 'build_execution_report.md').write_text('\n'.join(lines), encoding='utf-8')


def zip_output(output_dir: Path):
    zip_path = output_dir.with_suffix('.zip')
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(output_dir.rglob('*')):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(output_dir.parent))
    return zip_path


def build_asset_package(input_path: Path | None, output_dir: Path, zip_enabled=True, input_payload=None):
    start_time = time.perf_counter()
    tracemalloc.start()
    ensure_clean_dir(output_dir)
    input_copy_path = copy_input_file(input_path, input_payload, output_dir)
    raw_payload = load_json(input_copy_path)
    source_label = input_path if input_path is not None else output_dir / 'input_map_copy.json'
    standard_config = normalize_input(raw_payload, source_label)
    warnings = list(standard_config.get('warnings', []))
    save_json(output_dir / 'standard_config.json', standard_config)
    base_items = build_base_meshes(standard_config)
    facility_items = build_facility_meshes(standard_config, warnings)
    all_items = base_items + facility_items
    full_map_mesh = build_combined_mesh(all_items)
    collision_mesh = build_collision_mesh(all_items)
    metadata_payload = make_metadata(standard_config, all_items, warnings)
    scene_metadata = {
        'generated_at': metadata_payload['generated_at'],
        'venue_size': metadata_payload['venue_size'],
        'facility_ids': [facility['id'] for facility in metadata_payload['facilities']],
    }
    full_scene = build_scene(all_items, scene_metadata)
    collision_scene = build_scene([entry for entry in all_items if entry['category'] == 'base' or entry['metadata'].get('block_movement', False)], scene_metadata)
    export_glb(full_scene, output_dir / 'venue_map.glb')
    export_glb(collision_scene, output_dir / 'venue_map_ursina.glb')
    export_obj(collision_mesh, output_dir / 'venue_map_pybullet.obj')
    build_moderngl_payload(full_map_mesh, output_dir / 'venue_map_moderngl_data.npz')
    save_json(output_dir / 'venue_map_metadata.json', metadata_payload)
    current_memory, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    metrics_summary = {
        'elapsed_sec': round(time.perf_counter() - start_time, 3),
        'peak_memory_mb': round(peak_memory / (1024 * 1024), 3),
        'current_memory_mb': round(current_memory / (1024 * 1024), 3),
    }
    provisional_validation = {
        'generated_at': now_iso(),
        'status': 'pending',
        'checks': [],
        'metrics': metrics_summary,
        'warnings': warnings,
        'errors': [],
    }
    save_json(output_dir / 'build_validation_report.json', provisional_validation)
    write_execution_report(output_dir, source_label, standard_config, metadata_payload, provisional_validation, warnings, metrics_summary)
    validation_payload = validate_outputs(output_dir, standard_config, metadata_payload, warnings)
    validation_payload['metrics'].update(metrics_summary)
    save_json(output_dir / 'build_validation_report.json', validation_payload)
    write_execution_report(output_dir, source_label, standard_config, metadata_payload, validation_payload, warnings, metrics_summary)
    zip_path = zip_output(output_dir) if zip_enabled else None
    return {
        'status': validation_payload['status'],
        'output_dir': str(output_dir),
        'zip_path': str(zip_path) if zip_path is not None else '',
        'validation_report': validation_payload,
    }


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description='构建机器人竞赛场地标准化 3D 地图资产包。默认优先读取根目录 map.json；若不存在，则回退到当前激活地图配置。',
    )
    parser.add_argument('legacy_input', nargs='?', help='兼容旧调用方式的输入文件路径')
    parser.add_argument('--input', help='输入 map.json 路径；可为任务书标准 schema 或当前项目地图 schema')
    parser.add_argument('--output', default=str(OUTPUT_DIR), help='输出目录，默认 robot_venue_map_asset')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_PATH), help='默认输入回退时使用的 config.json 路径')
    parser.add_argument('--settings', default=str(DEFAULT_SETTINGS_PATH), help='默认输入回退时使用的 CommonSetting.json 路径')
    parser.add_argument('--no-zip', action='store_true', help='不生成 zip 归档')
    return parser


def main(argv=None):
    argv = argv or sys.argv
    parser = build_arg_parser()
    args = parser.parse_args(argv[1:])
    if args.input is None and args.legacy_input:
        args.input = args.legacy_input
    try:
        input_path, input_payload = resolve_input_source(args)
        result = build_asset_package(
            input_path=input_path,
            output_dir=Path(args.output).resolve(),
            zip_enabled=not args.no_zip,
            input_payload=input_payload,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] == 'passed' else 1
    except Exception as exc:
        failure_report = {
            'status': 'failed',
            'error': str(exc),
            'generated_at': now_iso(),
        }
        failure_dir = Path(getattr(args, 'output', OUTPUT_DIR)).resolve()
        failure_dir.mkdir(parents=True, exist_ok=True)
        save_json(failure_dir / 'build_validation_report.json', failure_report)
        print(json.dumps(failure_report, ensure_ascii=False, indent=2))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())