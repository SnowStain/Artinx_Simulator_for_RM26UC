#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame
import math
import numpy as np
import os
from heapq import heappop, heappush

class MapManager:
    def __init__(self, config):
        self.config = config
        self.map_image = None
        self.map_surface = None
        self.terrain_data = {}
        self.scale = config.get('simulator', {}).get('scale', 1.0)
        self.origin_x = config.get('map', {}).get('origin_x', 0)
        self.origin_y = config.get('map', {}).get('origin_y', 0)
        self.map_width = config.get('map', {}).get('width', 1576)
        self.map_height = config.get('map', {}).get('height', 873)
        self.field_length_m = config.get('map', {}).get('field_length_m', 28.0)
        self.field_width_m = config.get('map', {}).get('field_width_m', 15.0)
        self.terrain_grid_cell_size = int(config.get('map', {}).get('terrain_grid', {}).get('cell_size', 8))
        self.facilities = []
        self.terrain_grid_overrides = {}
        self.terrain_code_by_type = {
            'flat': 0,
            'boundary': 1,
            'wall': 2,
            'dog_hole': 3,
            'second_step': 4,
            'first_step': 5,
            'fly_slope': 6,
            'undulating_road': 7,
            'supply': 8,
            'fort': 9,
            'outpost': 10,
            'base': 11,
            'custom_terrain': 12,
            'rugged_road': 13,
        }
        self.terrain_label_by_code = {
            0: '平地',
            1: '边界',
            2: '墙',
            3: '狗洞',
            4: '二级台阶',
            5: '一级台阶',
            6: '飞坡',
            7: '起伏路段',
            8: '补给区',
            9: '堡垒',
            10: '前哨站',
            11: '基地',
            12: '自定义地形',
            13: '起伏路段',
        }
        self.height_map = None
        self.terrain_type_map = None
        self.move_block_map = None
        self.vision_block_height_map = None
        self.priority_map = None
        self.raster_dirty = True
        self.raster_version = 0
        self.terrain_priority = [
            'boundary',
            'wall',
            'rugged_road',
            'dog_hole',
            'second_step',
            'first_step',
            'fly_slope',
            'undulating_road',
            'supply',
            'fort',
            'outpost',
            'base',
        ]
        self.priority_rank = {terrain_type: index for index, terrain_type in enumerate(self.terrain_priority)}
        self._load_facilities_from_config()
        self._load_terrain_grid_from_config()

    def _mark_raster_dirty(self):
        self.raster_dirty = True
        self.raster_version += 1

    def _terrain_cell_key(self, grid_x, grid_y):
        return f'{int(grid_x)},{int(grid_y)}'

    def _decode_terrain_cell_key(self, key):
        grid_x, grid_y = key.split(',', 1)
        return int(grid_x), int(grid_y)

    def _grid_dimensions(self):
        return (
            math.ceil(self.map_width / max(self.terrain_grid_cell_size, 1)),
            math.ceil(self.map_height / max(self.terrain_grid_cell_size, 1)),
        )

    def _world_to_grid(self, world_x, world_y):
        cell_size = max(self.terrain_grid_cell_size, 1)
        return int(world_x) // cell_size, int(world_y) // cell_size

    def _grid_cell_bounds(self, grid_x, grid_y):
        cell_size = max(self.terrain_grid_cell_size, 1)
        x1 = grid_x * cell_size
        y1 = grid_y * cell_size
        x2 = min(self.map_width - 1, x1 + cell_size - 1)
        y2 = min(self.map_height - 1, y1 + cell_size - 1)
        return x1, y1, x2, y2

    def _terrain_override_payload(self, grid_x, grid_y, terrain_type, height_m, team='neutral', blocks_movement=None, blocks_vision=None):
        return {
            'x': int(grid_x),
            'y': int(grid_y),
            'type': terrain_type,
            'team': team,
            'height_m': round(float(height_m), 2),
            'blocks_movement': bool(blocks_movement) if blocks_movement is not None else terrain_type in {'wall', 'boundary', 'dog_hole'},
            'blocks_vision': bool(blocks_vision) if blocks_vision is not None else terrain_type == 'wall',
        }

    def _set_terrain_override_cell(self, grid_x, grid_y, terrain_type, height_m, team='neutral', blocks_movement=None, blocks_vision=None):
        self.terrain_grid_overrides[self._terrain_cell_key(grid_x, grid_y)] = self._terrain_override_payload(
            grid_x,
            grid_y,
            terrain_type,
            height_m,
            team=team,
            blocks_movement=blocks_movement,
            blocks_vision=blocks_vision,
        )

    def _grid_ranges_from_world_bounds(self, x1, y1, x2, y2):
        cell_size = max(self.terrain_grid_cell_size, 1)
        min_x = max(0, min(int(x1), int(x2)))
        max_x = min(self.map_width - 1, max(int(x1), int(x2)))
        min_y = max(0, min(int(y1), int(y2)))
        max_y = min(self.map_height - 1, max(int(y1), int(y2)))
        grid_x1 = max(0, min_x // cell_size)
        grid_x2 = min(self._grid_dimensions()[0] - 1, max_x // cell_size)
        grid_y1 = max(0, min_y // cell_size)
        grid_y2 = min(self._grid_dimensions()[1] - 1, max_y // cell_size)
        return grid_x1, grid_x2, grid_y1, grid_y2

    def _point_in_polygon_simple(self, x, y, points):
        if len(points) < 3:
            return False
        inside = False
        previous_x, previous_y = points[-1]
        for current_x, current_y in points:
            intersects = ((current_y > y) != (previous_y > y)) and (
                x < current_x + (previous_x - current_x) * (y - current_y) / (previous_y - current_y)
            )
            if intersects:
                inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    def _point_on_polygon_edge(self, x, y, points):
        if len(points) < 2:
            return False
        previous_x, previous_y = points[-1]
        for current_x, current_y in points:
            if self._orientation(previous_x, previous_y, current_x, current_y, x, y) == 0 and self._point_on_segment(previous_x, previous_y, current_x, current_y, x, y):
                return True
            previous_x, previous_y = current_x, current_y
        return False

    def _point_in_polygon(self, x, y, points):
        if len(points) < 3:
            return False
        if self._point_on_polygon_edge(x, y, points):
            return True
        return self._point_in_polygon_simple(x, y, points)

    def _point_in_rect_bounds(self, x, y, x1, y1, x2, y2):
        return x1 <= x <= x2 and y1 <= y <= y2

    def _orientation(self, ax, ay, bx, by, cx, cy):
        value = (by - ay) * (cx - bx) - (bx - ax) * (cy - by)
        if abs(value) <= 1e-6:
            return 0
        return 1 if value > 0 else 2

    def _point_on_segment(self, ax, ay, bx, by, px, py):
        return (
            min(ax, bx) - 1e-6 <= px <= max(ax, bx) + 1e-6
            and min(ay, by) - 1e-6 <= py <= max(ay, by) + 1e-6
        )

    def _segments_intersect(self, p1, p2, q1, q2):
        ax, ay = p1
        bx, by = p2
        cx, cy = q1
        dx, dy = q2
        o1 = self._orientation(ax, ay, bx, by, cx, cy)
        o2 = self._orientation(ax, ay, bx, by, dx, dy)
        o3 = self._orientation(cx, cy, dx, dy, ax, ay)
        o4 = self._orientation(cx, cy, dx, dy, bx, by)

        if o1 != o2 and o3 != o4:
            return True
        if o1 == 0 and self._point_on_segment(ax, ay, bx, by, cx, cy):
            return True
        if o2 == 0 and self._point_on_segment(ax, ay, bx, by, dx, dy):
            return True
        if o3 == 0 and self._point_on_segment(cx, cy, dx, dy, ax, ay):
            return True
        if o4 == 0 and self._point_on_segment(cx, cy, dx, dy, bx, by):
            return True
        return False

    def _polygon_intersects_rect(self, points, x1, y1, x2, y2):
        if len(points) < 3:
            return False

        rect_corners = [
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2),
        ]
        rect_edges = [
            (rect_corners[0], rect_corners[1]),
            (rect_corners[1], rect_corners[2]),
            (rect_corners[2], rect_corners[3]),
            (rect_corners[3], rect_corners[0]),
        ]

        for corner_x, corner_y in rect_corners:
            if self._point_in_polygon_simple(corner_x, corner_y, points):
                return True

        for point_x, point_y in points:
            if self._point_in_rect_bounds(point_x, point_y, x1, y1, x2, y2):
                return True

        previous_point = points[-1]
        for current_point in points:
            for edge_start, edge_end in rect_edges:
                if self._segments_intersect(previous_point, current_point, edge_start, edge_end):
                    return True
            previous_point = current_point

        return False

    def _polygon_selected_cells(self, normalized_points):
        if len(normalized_points) < 3:
            return []
        x1, y1, x2, y2 = self._polygon_bounds(normalized_points)
        grid_x1, grid_x2, grid_y1, grid_y2 = self._grid_ranges_from_world_bounds(x1, y1, x2, y2)
        selected_cells = []
        cell_size = max(self.terrain_grid_cell_size, 1)
        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                sample_x = min(self.map_width - 1, grid_x * cell_size + cell_size / 2.0)
                sample_y = min(self.map_height - 1, grid_y * cell_size + cell_size / 2.0)
                if self._point_in_polygon(sample_x, sample_y, normalized_points):
                    selected_cells.append((grid_x, grid_y))
        return selected_cells

    def _distance_to_segment_points(self, x, y, start, end):
        x1 = float(start[0])
        y1 = float(start[1])
        x2 = float(end[0])
        y2 = float(end[1])
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(x - x1, y - y1)
        t = ((x - x1) * dx + (y - y1) * dy) / max(dx * dx + dy * dy, 1e-6)
        t = max(0.0, min(1.0, t))
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return math.hypot(x - closest_x, y - closest_y)

    def _sample_line_average_height(self, start, end, samples=16):
        sample_count = max(2, int(samples))
        total_height = 0.0
        for index in range(sample_count):
            factor = index / max(sample_count - 1, 1)
            sample_x = start[0] + (end[0] - start[0]) * factor
            sample_y = start[1] + (end[1] - start[1]) * factor
            total_height += self.get_terrain_height_m(sample_x, sample_y)
        return round(total_height / sample_count, 2)

    def _sample_grid_height(self, grid_x, grid_y):
        x1, y1, x2, y2 = self._grid_cell_bounds(grid_x, grid_y)
        return round(self.get_terrain_height_m((x1 + x2) / 2.0, (y1 + y2) / 2.0), 2)

    def _load_terrain_grid_from_config(self):
        terrain_grid = self.config.get('map', {}).get('terrain_grid', {})
        self.terrain_grid_cell_size = int(terrain_grid.get('cell_size', self.terrain_grid_cell_size))
        self.terrain_grid_overrides = {}
        for cell in terrain_grid.get('cells', []):
            grid_x = int(cell.get('x', 0))
            grid_y = int(cell.get('y', 0))
            normalized = {
                'x': grid_x,
                'y': grid_y,
                'type': cell.get('type', 'flat'),
                'team': cell.get('team', 'neutral'),
                'height_m': round(float(cell.get('height_m', 0.0)), 2),
                'blocks_movement': bool(cell.get('blocks_movement', False)),
                'blocks_vision': bool(cell.get('blocks_vision', False)),
            }
            self.terrain_grid_overrides[self._terrain_cell_key(grid_x, grid_y)] = normalized
        self._mark_raster_dirty()

    def export_terrain_grid_config(self):
        cells = []
        for key in sorted(self.terrain_grid_overrides.keys(), key=lambda item: tuple(map(int, item.split(',')))):
            cell = dict(self.terrain_grid_overrides[key])
            cells.append(cell)
        return {
            'cell_size': int(self.terrain_grid_cell_size),
            'cells': cells,
        }

    def paint_terrain_grid(self, world_x, world_y, terrain_type, height_m=0.0, brush_radius=0, team='neutral', blocks_movement=None, blocks_vision=None):
        center_grid_x, center_grid_y = self._world_to_grid(world_x, world_y)
        max_x, max_y = self._grid_dimensions()
        for grid_y in range(max(0, center_grid_y - brush_radius), min(max_y, center_grid_y + brush_radius + 1)):
            for grid_x in range(max(0, center_grid_x - brush_radius), min(max_x, center_grid_x + brush_radius + 1)):
                if math.hypot(grid_x - center_grid_x, grid_y - center_grid_y) > brush_radius + 0.25:
                    continue
                self._set_terrain_override_cell(grid_x, grid_y, terrain_type, height_m, team=team, blocks_movement=blocks_movement, blocks_vision=blocks_vision)
        self._mark_raster_dirty()

    def paint_terrain_rect(self, x1, y1, x2, y2, terrain_type, height_m=0.0, team='neutral', blocks_movement=None, blocks_vision=None):
        grid_x1, grid_x2, grid_y1, grid_y2 = self._grid_ranges_from_world_bounds(x1, y1, x2, y2)
        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                self._set_terrain_override_cell(grid_x, grid_y, terrain_type, height_m, team=team, blocks_movement=blocks_movement, blocks_vision=blocks_vision)
        self._mark_raster_dirty()

    def paint_terrain_circle(self, center_x, center_y, radius_world, terrain_type, height_m=0.0, team='neutral', blocks_movement=None, blocks_vision=None):
        radius_world = max(0.0, float(radius_world))
        grid_x1, grid_x2, grid_y1, grid_y2 = self._grid_ranges_from_world_bounds(center_x - radius_world, center_y - radius_world, center_x + radius_world, center_y + radius_world)
        cell_size = max(self.terrain_grid_cell_size, 1)
        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                sample_x = min(self.map_width - 1, grid_x * cell_size + cell_size / 2.0)
                sample_y = min(self.map_height - 1, grid_y * cell_size + cell_size / 2.0)
                if math.hypot(sample_x - center_x, sample_y - center_y) <= radius_world + cell_size * 0.35:
                    self._set_terrain_override_cell(grid_x, grid_y, terrain_type, height_m, team=team, blocks_movement=blocks_movement, blocks_vision=blocks_vision)
        self._mark_raster_dirty()

    def paint_terrain_polygon(self, points, terrain_type, height_m=0.0, team='neutral', blocks_movement=None, blocks_vision=None):
        normalized_points = self._normalize_points(points)
        if len(normalized_points) < 3:
            return False
        changed = False
        for grid_x, grid_y in self._polygon_selected_cells(normalized_points):
            self._set_terrain_override_cell(grid_x, grid_y, terrain_type, height_m, team=team, blocks_movement=blocks_movement, blocks_vision=blocks_vision)
            changed = True
        if changed:
            self._mark_raster_dirty()
        return changed

    def paint_terrain_line(self, start_x, start_y, end_x, end_y, terrain_type, height_m=0.0, brush_radius=0, team='neutral', blocks_movement=None, blocks_vision=None):
        line_start = (int(start_x), int(start_y))
        line_end = (int(end_x), int(end_y))
        cell_size = max(self.terrain_grid_cell_size, 1)
        line_width = max(cell_size * 0.45, (float(brush_radius) + 0.5) * cell_size)
        grid_x1, grid_x2, grid_y1, grid_y2 = self._grid_ranges_from_world_bounds(
            min(line_start[0], line_end[0]) - line_width,
            min(line_start[1], line_end[1]) - line_width,
            max(line_start[0], line_end[0]) + line_width,
            max(line_start[1], line_end[1]) + line_width,
        )
        changed = False
        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                x1, y1, x2, y2 = self._grid_cell_bounds(grid_x, grid_y)
                sample_x = (x1 + x2) / 2.0
                sample_y = (y1 + y2) / 2.0
                if self._distance_to_segment_points(sample_x, sample_y, line_start, line_end) <= line_width:
                    self._set_terrain_override_cell(grid_x, grid_y, terrain_type, height_m, team=team, blocks_movement=blocks_movement, blocks_vision=blocks_vision)
                    changed = True
        if changed:
            self._mark_raster_dirty()
        return changed

    def paint_terrain_slope(self, line1_start, line1_end, line2_start, line2_end, terrain_type, team='neutral', blocks_movement=None, blocks_vision=None):
        first_start = (int(line1_start[0]), int(line1_start[1]))
        first_end = (int(line1_end[0]), int(line1_end[1]))
        second_start = (int(line2_start[0]), int(line2_start[1]))
        second_end = (int(line2_end[0]), int(line2_end[1]))

        same_direction_cost = math.hypot(first_start[0] - second_start[0], first_start[1] - second_start[1]) + math.hypot(first_end[0] - second_end[0], first_end[1] - second_end[1])
        swapped_direction_cost = math.hypot(first_start[0] - second_end[0], first_start[1] - second_end[1]) + math.hypot(first_end[0] - second_start[0], first_end[1] - second_start[1])
        if swapped_direction_cost < same_direction_cost:
            second_start, second_end = second_end, second_start

        polygon = [first_start, first_end, second_end, second_start]
        if len(polygon) < 4:
            return {'changed': False, 'start_height': 0.0, 'end_height': 0.0}

        start_height = self._sample_line_average_height(first_start, first_end)
        end_height = self._sample_line_average_height(second_start, second_end)
        x1, y1, x2, y2 = self._polygon_bounds(polygon)
        grid_x1, grid_x2, grid_y1, grid_y2 = self._grid_ranges_from_world_bounds(x1, y1, x2, y2)
        cell_size = max(self.terrain_grid_cell_size, 1)
        edge_bias = cell_size * 0.35
        changed = False

        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                sample_x = min(self.map_width - 1, grid_x * cell_size + cell_size / 2.0)
                sample_y = min(self.map_height - 1, grid_y * cell_size + cell_size / 2.0)
                if not self._point_in_polygon_simple(sample_x, sample_y, polygon):
                    continue
                distance_to_first = max(0.0, self._distance_to_segment_points(sample_x, sample_y, first_start, first_end) - edge_bias)
                distance_to_second = max(0.0, self._distance_to_segment_points(sample_x, sample_y, second_start, second_end) - edge_bias)
                blend_total = distance_to_first + distance_to_second
                blend = 0.5 if blend_total <= 1e-6 else distance_to_first / blend_total
                height_value = round(start_height + (end_height - start_height) * blend, 2)
                self._set_terrain_override_cell(grid_x, grid_y, terrain_type, height_value, team=team, blocks_movement=blocks_movement, blocks_vision=blocks_vision)
                changed = True

        if changed:
            self._mark_raster_dirty()
        return {
            'changed': changed,
            'start_height': start_height,
            'end_height': end_height,
        }

    def paint_terrain_slope_polygon(self, points, terrain_type, team='neutral', blocks_movement=None, blocks_vision=None, filter_iterations=12, direction_start=None, direction_end=None):
        normalized_points = self._normalize_points(points)
        if len(normalized_points) < 3:
            return {'changed': False, 'cell_count': 0, 'min_height': 0.0, 'max_height': 0.0}

        slope_info = self.analyze_terrain_slope_polygon(normalized_points, direction_start=direction_start, direction_end=direction_end)
        if not slope_info.get('changed'):
            return {'changed': False, 'cell_count': 0, 'min_height': 0.0, 'max_height': 0.0}

        selected_cells = slope_info['selected_cells']
        min_height = slope_info['min_height']
        max_height = slope_info['max_height']
        low_center_x, low_center_y = slope_info['low_point']
        high_center_x, high_center_y = slope_info['high_point']
        axis_x = high_center_x - low_center_x
        axis_y = high_center_y - low_center_y
        axis_length_sq = axis_x * axis_x + axis_y * axis_y

        for grid_x, grid_y in selected_cells:
            x1, y1, x2, y2 = self._grid_cell_bounds(grid_x, grid_y)
            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0
            if axis_length_sq <= 1e-6:
                blend = 0.0
            else:
                blend = ((center_x - low_center_x) * axis_x + (center_y - low_center_y) * axis_y) / axis_length_sq
                blend = max(0.0, min(1.0, blend))
            height_value = round(min_height + (max_height - min_height) * blend, 2)
            self._set_terrain_override_cell(
                grid_x,
                grid_y,
                terrain_type,
                height_value,
                team=team,
                blocks_movement=blocks_movement,
                blocks_vision=blocks_vision,
            )

        self._mark_raster_dirty()
        return {
            'changed': True,
            'cell_count': len(selected_cells),
            'min_height': round(min_height, 2),
            'max_height': round(max_height, 2),
        }

    def analyze_terrain_slope_polygon(self, points, direction_start=None, direction_end=None):
        normalized_points = self._normalize_points(points)
        if len(normalized_points) < 3:
            return {'changed': False, 'cell_count': 0, 'min_height': 0.0, 'max_height': 0.0}

        selected_cells = self._polygon_selected_cells(normalized_points)
        if not selected_cells:
            return {'changed': False, 'cell_count': 0, 'min_height': 0.0, 'max_height': 0.0}

        original_heights = {cell: self._sample_grid_height(cell[0], cell[1]) for cell in selected_cells}
        low_cell = min(selected_cells, key=lambda cell: (original_heights[cell], cell[1], cell[0]))
        high_cell = max(selected_cells, key=lambda cell: (original_heights[cell], cell[1], cell[0]))
        min_height = original_heights[low_cell]
        max_height = original_heights[high_cell]

        low_x1, low_y1, low_x2, low_y2 = self._grid_cell_bounds(low_cell[0], low_cell[1])
        high_x1, high_y1, high_x2, high_y2 = self._grid_cell_bounds(high_cell[0], high_cell[1])
        low_point = ((low_x1 + low_x2) / 2.0, (low_y1 + low_y2) / 2.0)
        high_point = ((high_x1 + high_x2) / 2.0, (high_y1 + high_y2) / 2.0)
        direction_points = self._normalize_points([direction_start, direction_end]) if direction_start is not None and direction_end is not None else []
        if len(direction_points) == 2:
            start_point, end_point = direction_points
            if math.hypot(end_point[0] - start_point[0], end_point[1] - start_point[1]) > 1e-6:
                low_point = (float(start_point[0]), float(start_point[1]))
                high_point = (float(end_point[0]), float(end_point[1]))
        return {
            'changed': True,
            'selected_cells': selected_cells,
            'cell_count': len(selected_cells),
            'min_height': round(min_height, 2),
            'max_height': round(max_height, 2),
            'low_point': low_point,
            'high_point': high_point,
            'low_cell': low_cell,
            'high_cell': high_cell,
        }

    def erase_terrain_grid(self, world_x, world_y, brush_radius=0):
        center_grid_x, center_grid_y = self._world_to_grid(world_x, world_y)
        max_x, max_y = self._grid_dimensions()
        removed = False
        for grid_y in range(max(0, center_grid_y - brush_radius), min(max_y, center_grid_y + brush_radius + 1)):
            for grid_x in range(max(0, center_grid_x - brush_radius), min(max_x, center_grid_x + brush_radius + 1)):
                if math.hypot(grid_x - center_grid_x, grid_y - center_grid_y) > brush_radius + 0.25:
                    continue
                removed = self.terrain_grid_overrides.pop(self._terrain_cell_key(grid_x, grid_y), None) is not None or removed
        if removed:
            self._mark_raster_dirty()
        return removed

    def remove_terrain_grid_cell(self, grid_x, grid_y):
        removed = self.terrain_grid_overrides.pop(self._terrain_cell_key(grid_x, grid_y), None)
        if removed is not None:
            self._mark_raster_dirty()
            return True
        return False

    def smooth_terrain_cells(self, cell_keys, intensity=1):
        strength = max(1, min(3, int(intensity)))
        normalized_cells = []
        for item in cell_keys or []:
            if isinstance(item, str):
                grid_x, grid_y = self._decode_terrain_cell_key(item)
            else:
                grid_x, grid_y = int(item[0]), int(item[1])
            key = self._terrain_cell_key(grid_x, grid_y)
            if key in self.terrain_grid_overrides:
                normalized_cells.append((grid_x, grid_y))
        if not normalized_cells:
            return {'changed': False, 'cell_count': 0}

        changed = False
        for _ in range(strength):
            source_heights = {}
            for grid_x, grid_y in normalized_cells:
                for sample_y in range(grid_y - 1, grid_y + 2):
                    for sample_x in range(grid_x - 1, grid_x + 2):
                        if (sample_x, sample_y) in source_heights:
                            continue
                        if sample_x < 0 or sample_y < 0:
                            continue
                        max_x, max_y = self._grid_dimensions()
                        if sample_x >= max_x or sample_y >= max_y:
                            continue
                        source_heights[(sample_x, sample_y)] = self._sample_grid_height(sample_x, sample_y)

            updated_heights = {}
            for grid_x, grid_y in normalized_cells:
                neighbors = []
                for sample_y in range(grid_y - 1, grid_y + 2):
                    for sample_x in range(grid_x - 1, grid_x + 2):
                        if (sample_x, sample_y) in source_heights:
                            neighbors.append(source_heights[(sample_x, sample_y)])
                if not neighbors:
                    continue
                current_height = source_heights.get((grid_x, grid_y), 0.0)
                average_height = sum(neighbors) / len(neighbors)
                updated_heights[(grid_x, grid_y)] = round(current_height * 0.35 + average_height * 0.65, 2)

            for (grid_x, grid_y), new_height in updated_heights.items():
                cell = self.terrain_grid_overrides.get(self._terrain_cell_key(grid_x, grid_y))
                if cell is None:
                    continue
                if abs(float(cell.get('height_m', 0.0)) - new_height) <= 1e-6:
                    continue
                self._set_terrain_override_cell(
                    grid_x,
                    grid_y,
                    cell.get('type', 'custom_terrain'),
                    new_height,
                    team=cell.get('team', 'neutral'),
                    blocks_movement=cell.get('blocks_movement'),
                    blocks_vision=cell.get('blocks_vision'),
                )
                changed = True

        if changed:
            self._mark_raster_dirty()
        return {'changed': changed, 'cell_count': len(normalized_cells), 'strength': strength}

    def get_terrain_grid_cell(self, world_x, world_y):
        grid_x, grid_y = self._world_to_grid(world_x, world_y)
        return self.terrain_grid_overrides.get(self._terrain_cell_key(grid_x, grid_y))

    def _create_raster_layers(self):
        shape = (self.map_height, self.map_width)
        self.height_map = np.zeros(shape, dtype=np.float32)
        self.terrain_type_map = np.zeros(shape, dtype=np.uint8)
        self.move_block_map = np.zeros(shape, dtype=np.bool_)
        self.vision_block_height_map = np.zeros(shape, dtype=np.float32)
        self.priority_map = np.full(shape, fill_value=255, dtype=np.uint8)

    def _ensure_raster_layers(self):
        if self.height_map is None or self.height_map.shape != (self.map_height, self.map_width):
            self._create_raster_layers()
            self.raster_dirty = True
        if self.raster_dirty:
            self._rebuild_raster_layers()

    def _clamp_bounds(self, x1, y1, x2, y2):
        return (
            max(0, int(x1)),
            max(0, int(y1)),
            min(self.map_width - 1, int(x2)),
            min(self.map_height - 1, int(y2)),
        )

    def _region_bounds(self, region):
        if region.get('shape') == 'line':
            thickness = int(region.get('thickness', 12)) + 1
            return self._clamp_bounds(
                min(region['x1'], region['x2']) - thickness,
                min(region['y1'], region['y2']) - thickness,
                max(region['x1'], region['x2']) + thickness,
                max(region['y1'], region['y2']) + thickness,
            )
        return self._clamp_bounds(region.get('x1', 0), region.get('y1', 0), region.get('x2', 0), region.get('y2', 0))

    def _region_mask(self, region, x1, y1, x2, y2):
        width = x2 - x1 + 1
        height = y2 - y1 + 1
        if width <= 0 or height <= 0:
            return None

        shape = region.get('shape')
        xs = np.arange(x1, x2 + 1)
        ys = np.arange(y1, y2 + 1)

        if shape == 'rect':
            if region.get('type') == 'boundary':
                thickness = int(region.get('thickness', 10))
                return (
                    (xs[np.newaxis, :] <= region['x1'] + thickness)
                    | (xs[np.newaxis, :] >= region['x2'] - thickness)
                    | (ys[:, np.newaxis] <= region['y1'] + thickness)
                    | (ys[:, np.newaxis] >= region['y2'] - thickness)
                )
            return np.ones((height, width), dtype=np.bool_)

        if shape == 'line':
            x_grid, y_grid = np.meshgrid(xs, ys)
            x1_line = float(region.get('x1', 0))
            y1_line = float(region.get('y1', 0))
            x2_line = float(region.get('x2', 0))
            y2_line = float(region.get('y2', 0))
            dx = x2_line - x1_line
            dy = y2_line - y1_line
            if dx == 0 and dy == 0:
                distances = np.hypot(x_grid - x1_line, y_grid - y1_line)
            else:
                denominator = max(dx * dx + dy * dy, 1e-6)
                t = ((x_grid - x1_line) * dx + (y_grid - y1_line) * dy) / denominator
                t = np.clip(t, 0.0, 1.0)
                closest_x = x1_line + t * dx
                closest_y = y1_line + t * dy
                distances = np.hypot(x_grid - closest_x, y_grid - closest_y)
            return distances <= float(region.get('thickness', 12))

        if shape == 'polygon':
            points = region.get('points', [])
            if len(points) < 3:
                return None
            x_grid, y_grid = np.meshgrid(xs, ys)
            mask = np.zeros((height, width), dtype=np.bool_)
            previous_x, previous_y = points[-1]
            for current_x, current_y in points:
                denominator = float(previous_y - current_y)
                intersects = np.zeros((height, width), dtype=np.bool_)
                if abs(denominator) > 1e-6:
                    crosses_scanline = (current_y > y_grid) != (previous_y > y_grid)
                    x_intersect = current_x + (previous_x - current_x) * (y_grid - current_y) / denominator
                    intersects = crosses_scanline & (x_grid < x_intersect)
                mask ^= intersects
                previous_x, previous_y = current_x, current_y
            return mask

        return None

    def _apply_region_to_raster(self, region):
        x1, y1, x2, y2 = self._region_bounds(region)
        if x2 < x1 or y2 < y1:
            return

        mask = self._region_mask(region, x1, y1, x2, y2)
        if mask is None or not mask.any():
            return

        rows = slice(y1, y2 + 1)
        cols = slice(x1, x2 + 1)
        priority = self.priority_rank.get(region.get('type', 'flat'), 254)
        priority_view = self.priority_map[rows, cols]
        replace_mask = mask & (priority <= priority_view)
        if replace_mask.any():
            self.priority_map[rows, cols][replace_mask] = priority
            self.terrain_type_map[rows, cols][replace_mask] = self.terrain_code_by_type.get(region.get('type', 'flat'), 0)
            self.height_map[rows, cols][replace_mask] = float(region.get('height_m', 0.0))

            move_block = False
            if region.get('type') == 'wall':
                move_block = bool(region.get('blocks_movement', True))
            elif region.get('type') in {'boundary', 'dog_hole', 'rugged_road'}:
                move_block = True
            self.move_block_map[rows, cols][replace_mask] = move_block

        vision_height = 0.0
        if region.get('type') == 'wall' and bool(region.get('blocks_vision', True)):
            vision_height = float(region.get('height_m', 0.0))
        if vision_height > 0.0:
            self.vision_block_height_map[rows, cols] = np.maximum(
                self.vision_block_height_map[rows, cols],
                np.where(mask, vision_height, 0.0),
            )

    def _apply_terrain_override_to_raster(self, cell):
        grid_x = int(cell.get('x', 0))
        grid_y = int(cell.get('y', 0))
        x1, y1, x2, y2 = self._grid_cell_bounds(grid_x, grid_y)
        rows = slice(y1, y2 + 1)
        cols = slice(x1, x2 + 1)
        terrain_type = cell.get('type', 'flat')
        self.priority_map[rows, cols] = 0
        self.terrain_type_map[rows, cols] = self.terrain_code_by_type.get(terrain_type, 0)
        self.height_map[rows, cols] = round(float(cell.get('height_m', 0.0)), 2)
        self.move_block_map[rows, cols] = bool(cell.get('blocks_movement', False))
        if bool(cell.get('blocks_vision', False)):
            self.vision_block_height_map[rows, cols] = np.maximum(
                self.vision_block_height_map[rows, cols],
                round(float(cell.get('height_m', 0.0)), 2),
            )
        else:
            self.vision_block_height_map[rows, cols] = 0.0

    def _rebuild_raster_layers(self):
        self._create_raster_layers()
        for facility_type in reversed(self.terrain_priority):
            for region in self.facilities:
                if region.get('type') == facility_type:
                    self._apply_region_to_raster(region)
        for cell in self.terrain_grid_overrides.values():
            self._apply_terrain_override_to_raster(cell)
        self.raster_dirty = False

    def get_raster_layers(self):
        self._ensure_raster_layers()
        return {
            'shape': (self.map_height, self.map_width),
            'height_map': self.height_map,
            'terrain_type_map': self.terrain_type_map,
            'move_block_map': self.move_block_map,
            'vision_block_height_map': self.vision_block_height_map,
            'terrain_code_by_type': dict(self.terrain_code_by_type),
            'terrain_label_by_code': dict(self.terrain_label_by_code),
        }

    def sample_raster_layers(self, x, y):
        map_x = int(x)
        map_y = int(y)
        if not (0 <= map_x < self.map_width and 0 <= map_y < self.map_height):
            return {
                'terrain_code': self.terrain_code_by_type['boundary'],
                'terrain_label': '边界',
                'height_m': 0.0,
                'move_blocked': True,
                'vision_block_height_m': 0.0,
            }

        self._ensure_raster_layers()
        terrain_code = int(self.terrain_type_map[map_y, map_x])
        return {
            'terrain_code': terrain_code,
            'terrain_label': self.terrain_label_by_code.get(terrain_code, '平地'),
            'height_m': round(float(self.height_map[map_y, map_x]), 2),
            'move_blocked': bool(self.move_block_map[map_y, map_x]),
            'vision_block_height_m': round(float(self.vision_block_height_map[map_y, map_x]), 2),
        }

    def _normalize_points(self, points):
        normalized = []
        for point in points or []:
            if isinstance(point, dict):
                px = point.get('x', 0)
                py = point.get('y', 0)
            else:
                px, py = point[0], point[1]
            normalized.append((int(px), int(py)))
        return normalized

    def _polygon_bounds(self, points):
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)

    def _default_height_for_region(self, region):
        if region.get('type') == 'wall':
            return 1.0
        return 0.0

    def _normalize_region(self, region):
        normalized = dict(region)
        shape = normalized.get('shape', 'rect')
        normalized['shape'] = shape

        if shape == 'polygon':
            normalized['points'] = self._normalize_points(normalized.get('points', []))
            if len(normalized['points']) >= 3:
                x1, y1, x2, y2 = self._polygon_bounds(normalized['points'])
                normalized['x1'] = x1
                normalized['y1'] = y1
                normalized['x2'] = x2
                normalized['y2'] = y2

        if normalized.get('type') == 'wall' or normalized.get('shape') == 'line':
            normalized['type'] = 'wall'
            normalized['shape'] = 'line'
            normalized['blocks_movement'] = bool(normalized.get('blocks_movement', True))
            normalized['blocks_vision'] = bool(normalized.get('blocks_vision', True))
            normalized['height_m'] = float(normalized.get('height_m', 1.0))
            normalized['thickness'] = int(normalized.get('thickness', 12))
        elif normalized.get('type') != 'boundary':
            normalized['height_m'] = round(float(normalized.get('height_m', self._default_height_for_region(normalized))), 2)
        return normalized
    
    def load_map(self):
        """加载地图图像"""
        map_path = self.config.get('map', {}).get('image_path', '场地-俯视图.png')
        resolved_path = map_path
        if not os.path.isabs(resolved_path):
            config_path = self.config.get('_config_path')
            base_dir = os.path.dirname(os.path.abspath(config_path)) if config_path else os.getcwd()
            candidate = os.path.join(base_dir, resolved_path)
            if os.path.exists(candidate):
                resolved_path = candidate
        
        if os.path.exists(resolved_path):
            try:
                self.map_image = pygame.image.load(resolved_path)
                # 调整地图大小
                width = int(self.map_image.get_width() * self.scale)
                height = int(self.map_image.get_height() * self.scale)
                self.map_surface = pygame.transform.scale(self.map_image, (width, height))
                self.map_width = self.map_image.get_width()
                self.map_height = self.map_image.get_height()
                self._mark_raster_dirty()
                print(f"地图加载成功: {resolved_path}")
            except pygame.error as e:
                print(f"地图加载失败: {e}")
        else:
            print(f"地图文件不存在: {resolved_path}")

    def _load_facilities_from_config(self):
        """加载设施区域定义（优先使用配置，缺省使用内置俯视图标定）。"""
        configured = self.config.get('map', {}).get('facilities', [])
        if configured:
            self.facilities = [self._normalize_region(region) for region in configured]
            self._mark_raster_dirty()
            return

        # 坐标依据 1576x873 俯视图进行标定；用于裁判系统与地形判定。
        self.facilities = [
            {'id': 'red_base', 'type': 'base', 'team': 'red', 'shape': 'rect', 'x1': 95, 'y1': 360, 'x2': 230, 'y2': 500},
            {'id': 'red_outpost', 'type': 'outpost', 'team': 'red', 'shape': 'rect', 'x1': 380, 'y1': 360, 'x2': 505, 'y2': 500},
            {'id': 'center_energy_mechanism', 'type': 'energy_mechanism', 'team': 'neutral', 'shape': 'rect', 'x1': 738, 'y1': 398, 'x2': 838, 'y2': 478},
            {'id': 'red_fly_slope', 'type': 'fly_slope', 'team': 'red', 'shape': 'rect', 'x1': 560, 'y1': 600, 'x2': 1020, 'y2': 790},
            {'id': 'red_second_step', 'type': 'second_step', 'team': 'red', 'shape': 'rect', 'x1': 435, 'y1': 650, 'x2': 515, 'y2': 725},
            {'id': 'red_first_step', 'type': 'first_step', 'team': 'red', 'shape': 'rect', 'x1': 345, 'y1': 635, 'x2': 555, 'y2': 760},
            {'id': 'red_supply', 'type': 'supply', 'team': 'red', 'shape': 'rect', 'x1': 130, 'y1': 620, 'x2': 300, 'y2': 815},
            {'id': 'red_mineral_exchange', 'type': 'mineral_exchange', 'team': 'red', 'shape': 'rect', 'x1': 145, 'y1': 540, 'x2': 265, 'y2': 605},
            {'id': 'red_mining_area', 'type': 'mining_area', 'team': 'red', 'shape': 'rect', 'x1': 420, 'y1': 545, 'x2': 540, 'y2': 625},
            {'id': 'red_undulating_road', 'type': 'undulating_road', 'team': 'red', 'shape': 'rect', 'x1': 230, 'y1': 245, 'x2': 740, 'y2': 635},
            {'id': 'red_dog_hole', 'type': 'dog_hole', 'team': 'red', 'shape': 'rect', 'x1': 640, 'y1': 610, 'x2': 930, 'y2': 665},
            {'id': 'red_fort', 'type': 'fort', 'team': 'red', 'shape': 'rect', 'x1': 245, 'y1': 320, 'x2': 360, 'y2': 520},
            {'id': 'blue_base', 'type': 'base', 'team': 'blue', 'shape': 'rect', 'x1': 1330, 'y1': 360, 'x2': 1470, 'y2': 500},
            {'id': 'blue_outpost', 'type': 'outpost', 'team': 'blue', 'shape': 'rect', 'x1': 1070, 'y1': 360, 'x2': 1195, 'y2': 500},
            {'id': 'blue_fly_slope', 'type': 'fly_slope', 'team': 'blue', 'shape': 'rect', 'x1': 560, 'y1': 95, 'x2': 1020, 'y2': 275},
            {'id': 'blue_second_step', 'type': 'second_step', 'team': 'blue', 'shape': 'rect', 'x1': 1075, 'y1': 115, 'x2': 1155, 'y2': 185},
            {'id': 'blue_first_step', 'type': 'first_step', 'team': 'blue', 'shape': 'rect', 'x1': 1020, 'y1': 105, 'x2': 1230, 'y2': 235},
            {'id': 'blue_supply', 'type': 'supply', 'team': 'blue', 'shape': 'rect', 'x1': 1276, 'y1': 58, 'x2': 1446, 'y2': 253},
            {'id': 'blue_mineral_exchange', 'type': 'mineral_exchange', 'team': 'blue', 'shape': 'rect', 'x1': 1311, 'y1': 268, 'x2': 1431, 'y2': 333},
            {'id': 'blue_mining_area', 'type': 'mining_area', 'team': 'blue', 'shape': 'rect', 'x1': 1036, 'y1': 248, 'x2': 1156, 'y2': 328},
            {'id': 'blue_undulating_road', 'type': 'undulating_road', 'team': 'blue', 'shape': 'rect', 'x1': 840, 'y1': 245, 'x2': 1345, 'y2': 635},
            {'id': 'blue_dog_hole', 'type': 'dog_hole', 'team': 'blue', 'shape': 'rect', 'x1': 640, 'y1': 215, 'x2': 930, 'y2': 265},
            {'id': 'blue_fort', 'type': 'fort', 'team': 'blue', 'shape': 'rect', 'x1': 1215, 'y1': 320, 'x2': 1330, 'y2': 520},
            {'id': 'boundary_outer', 'type': 'boundary', 'team': 'neutral', 'shape': 'rect', 'x1': 0, 'y1': 0, 'x2': 1575, 'y2': 872, 'thickness': 14},
        ]
        self._mark_raster_dirty()

    def _in_rect(self, x, y, region):
        return region['x1'] <= x <= region['x2'] and region['y1'] <= y <= region['y2']

    def _in_boundary_band(self, x, y, region):
        thickness = region.get('thickness', 10)
        if not self._in_rect(x, y, region):
            return False
        return (
            x <= region['x1'] + thickness
            or x >= region['x2'] - thickness
            or y <= region['y1'] + thickness
            or y >= region['y2'] - thickness
        )

    def _distance_to_segment(self, x, y, region):
        x1 = float(region.get('x1', 0))
        y1 = float(region.get('y1', 0))
        x2 = float(region.get('x2', 0))
        y2 = float(region.get('y2', 0))
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(x - x1, y - y1)
        t = ((x - x1) * dx + (y - y1) * dy) / max(dx * dx + dy * dy, 1e-6)
        t = max(0.0, min(1.0, t))
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return math.hypot(x - closest_x, y - closest_y)

    def _on_line(self, x, y, region):
        return self._distance_to_segment(x, y, region) <= float(region.get('thickness', 12))

    def _in_polygon(self, x, y, region):
        points = region.get('points', [])
        if len(points) < 3:
            return False

        inside = False
        previous_x, previous_y = points[-1]
        for current_x, current_y in points:
            denominator = previous_y - current_y
            intersects = False
            if ((current_y > y) != (previous_y > y)) and abs(denominator) > 1e-6:
                x_intersect = current_x + (previous_x - current_x) * (y - current_y) / denominator
                intersects = x < x_intersect
            if intersects:
                inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    def _region_contains_point(self, x, y, region):
        shape = region.get('shape')
        facility_type = region.get('type')
        if shape == 'rect':
            if facility_type == 'boundary':
                return self._in_boundary_band(x, y, region)
            return self._in_rect(x, y, region)
        if shape == 'polygon':
            return self._in_polygon(x, y, region)
        if shape == 'line':
            return self._on_line(x, y, region)
        return False

    def _next_variant_id(self, base_id, suffix):
        existing_ids = {region.get('id') for region in self.facilities}
        index = 1
        candidate = f'{base_id}_{suffix}_{index}'
        while candidate in existing_ids:
            index += 1
            candidate = f'{base_id}_{suffix}_{index}'
        return candidate

    def get_facility_at(self, x, y):
        """返回指定位置命中的设施定义；未命中返回None。"""
        regions = self.get_regions_at(x, y)
        if regions:
            return regions[0]
        return None

    def get_regions_at(self, x, y, region_types=None):
        requested_types = set(region_types) if region_types else None
        type_rank = {facility_type: index for index, facility_type in enumerate(self.terrain_priority)}
        default_rank = len(self.terrain_priority) + 32
        hits = []
        for region in self.facilities:
            facility_type = region.get('type')
            if requested_types is not None and facility_type not in requested_types:
                continue
            if self._region_contains_point(x, y, region):
                hits.append(region)
        hits.sort(key=lambda region: (type_rank.get(region.get('type'), default_rank), str(region.get('id', ''))))
        return hits

    def get_facility_regions(self, facility_type=None):
        """获取设施区域列表，可按类型过滤。"""
        if facility_type is None:
            return list(self.facilities)
        return [f for f in self.facilities if f.get('type') == facility_type]

    def get_facility_by_id(self, facility_id):
        for facility in self.facilities:
            if facility.get('id') == facility_id:
                return facility
        return None

    def facility_center(self, facility):
        return int((facility['x1'] + facility['x2']) / 2), int((facility['y1'] + facility['y2']) / 2)

    def upsert_facility_region(self, facility_id, facility_type, x1, y1, x2, y2, team='neutral'):
        """新增或更新矩形设施区域。"""
        existing = self.get_facility_by_id(facility_id)
        normalized = {
            'id': facility_id,
            'type': facility_type,
            'team': team,
            'shape': 'rect',
            'x1': int(min(x1, x2)),
            'y1': int(min(y1, y2)),
            'x2': int(max(x1, x2)),
            'y2': int(max(y1, y2)),
            'height_m': float(existing.get('height_m', 0.0)) if existing else 0.0,
        }

        for index, region in enumerate(self.facilities):
            if region.get('id') == facility_id:
                self.facilities[index] = normalized
                self._mark_raster_dirty()
                return normalized

        self.facilities.append(normalized)
        self._mark_raster_dirty()
        return normalized

    def add_polygon_region(self, facility_type, points, team='neutral', base_id=None):
        normalized_points = self._normalize_points(points)
        if len(normalized_points) < 3:
            return None

        x1, y1, x2, y2 = self._polygon_bounds(normalized_points)
        base = base_id or facility_type
        region = {
            'id': self._next_variant_id(base, 'poly'),
            'type': facility_type,
            'team': team,
            'shape': 'polygon',
            'points': normalized_points,
            'x1': x1,
            'y1': y1,
            'x2': x2,
            'y2': y2,
            'height_m': 0.0,
        }
        normalized = self._normalize_region(region)
        self.facilities.append(normalized)
        self._mark_raster_dirty()
        return normalized

    def add_wall_line(self, x1, y1, x2, y2, thickness=12):
        existing_ids = {
            region.get('id')
            for region in self.facilities
            if str(region.get('id', '')).startswith('wall_')
        }
        index = 1
        while f'wall_{index}' in existing_ids:
            index += 1
        region = {
            'id': f'wall_{index}',
            'type': 'wall',
            'team': 'neutral',
            'shape': 'line',
            'x1': int(x1),
            'y1': int(y1),
            'x2': int(x2),
            'y2': int(y2),
            'thickness': int(thickness),
            'blocks_movement': True,
            'blocks_vision': True,
            'height_m': 1.0,
        }
        normalized = self._normalize_region(region)
        self.facilities.append(normalized)
        self._mark_raster_dirty()
        return normalized

    def update_wall_properties(self, wall_id, blocks_movement=None, blocks_vision=None, height_m=None):
        facility = self.get_facility_by_id(wall_id)
        if facility is None or facility.get('type') != 'wall':
            return None
        if blocks_movement is not None:
            facility['blocks_movement'] = bool(blocks_movement)
        if blocks_vision is not None:
            facility['blocks_vision'] = bool(blocks_vision)
        if height_m is not None:
            facility['height_m'] = max(0.0, round(float(height_m), 2))
        self._mark_raster_dirty()
        return facility

    def update_facility_height(self, facility_id, height_m):
        facility = self.get_facility_by_id(facility_id)
        if facility is None or facility.get('type') == 'boundary':
            return None
        facility['height_m'] = max(0.0, round(float(height_m), 2))
        self._mark_raster_dirty()
        return facility

    def remove_facility_region(self, facility_id):
        """删除设施区域。"""
        self.facilities = [region for region in self.facilities if region.get('id') != facility_id]
        self._mark_raster_dirty()

    def export_facilities_config(self):
        """导出设施配置。"""
        return [dict(region) for region in self.facilities]

    def get_facility_summary(self):
        """返回按设施类型分组的区域概要，供裁判系统使用。"""
        summary = {}
        for region in self.facilities:
            facility_type = region.get('type', 'unknown')
            summary.setdefault(facility_type, []).append(region.get('id'))
        return summary
    
    def get_terrain_type(self, x, y):
        """获取指定位置的地形类型"""
        map_x = int(x)
        map_y = int(y)

        if not (0 <= map_x < self.map_width and 0 <= map_y < self.map_height):
            return "边界"

        return self.sample_raster_layers(map_x, map_y)['terrain_label']

    def get_terrain_height_m(self, x, y):
        return self.sample_raster_layers(x, y)['height_m']

    def find_path(self, start_point, end_point, max_height_delta_m=0.05, grid_step=None, traversal_profile=None):
        self._ensure_raster_layers()
        if start_point is None or end_point is None:
            return []

        traversal_profile = traversal_profile or {}

        step = max(4, int(grid_step or max(self.terrain_grid_cell_size * 2, 12)))
        start = self._point_to_nav_cell(start_point, step)
        goal = self._point_to_nav_cell(end_point, step)
        start_world = self._nav_cell_center(start, step)
        goal_world = self._nav_cell_center(goal, step)

        if not self._is_nav_cell_passable(start, step):
            start = self._find_nearest_passable_nav_cell(start, step, search_radius=4)
            if start is None:
                return []
            start_world = self._nav_cell_center(start, step)
        if not self._is_nav_cell_passable(goal, step):
            goal = self._find_nearest_passable_nav_cell(goal, step, search_radius=4)
            if goal is None:
                return []
            goal_world = self._nav_cell_center(goal, step)

        open_heap = []
        heappush(open_heap, (0.0, start))
        came_from = {}
        g_score = {start: 0.0}
        closed = set()
        iteration_count = 0
        max_iterations = 2500

        while open_heap:
            iteration_count += 1
            if iteration_count > max_iterations:
                break
            _, current = heappop(open_heap)
            if current in closed:
                continue
            if current == goal:
                return self._reconstruct_nav_path(came_from, current, step, start_world, goal_world)
            closed.add(current)

            current_world = self._nav_cell_center(current, step)
            current_height = self.get_terrain_height_m(current_world[0], current_world[1])
            for neighbor in self._iter_nav_neighbors(current):
                if neighbor in closed:
                    continue
                if not self._is_nav_cell_passable(neighbor, step):
                    continue
                neighbor_world = self._nav_cell_center(neighbor, step)
                neighbor_height = self.get_terrain_height_m(neighbor_world[0], neighbor_world[1])
                transition = None
                if abs(float(neighbor_height) - float(current_height)) > float(max_height_delta_m) + 1e-6:
                    transition = self.get_step_transition(current_world[0], current_world[1], neighbor_world[0], neighbor_world[1])
                    if transition is None or not traversal_profile.get('can_climb_steps', False):
                        continue

                step_cost = math.hypot(neighbor_world[0] - current_world[0], neighbor_world[1] - current_world[1])
                if transition is not None:
                    step_cost += float(traversal_profile.get('step_climb_duration_sec', 2.0)) * step * 3.0
                tentative_g = g_score[current] + step_cost
                if tentative_g >= g_score.get(neighbor, float('inf')):
                    continue
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                heuristic = math.hypot(goal_world[0] - neighbor_world[0], goal_world[1] - neighbor_world[1])
                heappush(open_heap, (tentative_g + heuristic, neighbor))

        return []

    def _point_to_nav_cell(self, point, step):
        x = max(0, min(self.map_width - 1, int(point[0])))
        y = max(0, min(self.map_height - 1, int(point[1])))
        return x // step, y // step

    def _nav_cell_center(self, cell, step):
        max_x = max(0, self.map_width - 1)
        max_y = max(0, self.map_height - 1)
        center_x = min(max_x, cell[0] * step + step // 2)
        center_y = min(max_y, cell[1] * step + step // 2)
        return center_x, center_y

    def _iter_nav_neighbors(self, cell):
        for offset_y in (-1, 0, 1):
            for offset_x in (-1, 0, 1):
                if offset_x == 0 and offset_y == 0:
                    continue
                yield cell[0] + offset_x, cell[1] + offset_y

    def _is_nav_cell_passable(self, cell, step):
        max_cell_x = math.ceil(self.map_width / step)
        max_cell_y = math.ceil(self.map_height / step)
        if not (0 <= cell[0] < max_cell_x and 0 <= cell[1] < max_cell_y):
            return False
        center = self._nav_cell_center(cell, step)
        sample = self.sample_raster_layers(center[0], center[1])
        if sample['move_blocked']:
            return False
        return True

    def _find_nearest_passable_nav_cell(self, cell, step, search_radius=4):
        if self._is_nav_cell_passable(cell, step):
            return cell
        for radius in range(1, search_radius + 1):
            for offset_y in range(-radius, radius + 1):
                for offset_x in range(-radius, radius + 1):
                    candidate = cell[0] + offset_x, cell[1] + offset_y
                    if self._is_nav_cell_passable(candidate, step):
                        return candidate
        return None

    def _reconstruct_nav_path(self, came_from, current, step, start_point, end_point):
        cells = [current]
        while current in came_from:
            current = came_from[current]
            cells.append(current)
        cells.reverse()
        points = [start_point]
        points.extend(self._nav_cell_center(cell, step) for cell in cells[1:-1])
        points.append(end_point)
        return points

    def _step_ascent_direction(self, facility):
        team = facility.get('team')
        if team == 'red':
            return -1
        if team == 'blue':
            return 1
        center_y = (facility['y1'] + facility['y2']) / 2.0
        return -1 if center_y >= self.map_height / 2.0 else 1

    def _step_transition_for_facility(self, facility, from_x, from_y, to_x, to_y):
        if facility.get('type') not in {'first_step', 'second_step'}:
            return None
        direction = self._step_ascent_direction(facility)
        center_x, center_y = self.facility_center(facility)
        width = max(1.0, abs(facility['x2'] - facility['x1']))
        margin = max(float(self.terrain_grid_cell_size) * 1.5, 12.0)
        align_margin = max(width * 0.45, margin)
        if abs(float(from_x) - center_x) > align_margin and abs(float(to_x) - center_x) > align_margin:
            return None

        if direction < 0:
            entry_y = float(facility['y2'])
            moving_ok = float(to_y) < float(from_y)
            crossing_ok = float(from_y) >= entry_y - margin and float(to_y) <= entry_y + margin
            approach_point = (int(center_x), int(min(self.map_height - 1, facility['y2'] + margin)))
            top_point = (int(center_x), int(max(facility['y1'], facility['y1'] + margin)))
        else:
            entry_y = float(facility['y1'])
            moving_ok = float(to_y) > float(from_y)
            crossing_ok = float(from_y) <= entry_y + margin and float(to_y) >= entry_y - margin
            approach_point = (int(center_x), int(max(0, facility['y1'] - margin)))
            top_point = (int(center_x), int(min(facility['y2'], facility['y2'] - margin)))

        if not moving_ok or not crossing_ok:
            return None
        if not self._in_rect(to_x, to_y, facility):
            return None
        return {
            'facility_id': facility.get('id'),
            'facility_type': facility.get('type'),
            'approach_point': approach_point,
            'top_point': top_point,
            'direction': direction,
        }

    def get_step_transition(self, from_x, from_y, to_x, to_y):
        for facility_type in ('first_step', 'second_step'):
            for facility in self.get_facility_regions(facility_type):
                transition = self._step_transition_for_facility(facility, from_x, from_y, to_x, to_y)
                if transition is not None:
                    return transition
        return None

    def evaluate_movement_path(self, from_x, from_y, to_x, to_y, max_height_delta_m=0.05):
        start_sample = self.sample_raster_layers(from_x, from_y)
        end_sample = self.sample_raster_layers(to_x, to_y)
        if end_sample['move_blocked']:
            return {
                'ok': False,
                'reason': 'blocked',
                'start_height_m': start_sample['height_m'],
                'end_height_m': end_sample['height_m'],
            }

        distance = math.hypot(float(to_x) - float(from_x), float(to_y) - float(from_y))
        sample_stride = max(1.0, self.terrain_grid_cell_size * 0.5)
        sample_count = max(1, int(math.ceil(distance / sample_stride)))
        previous_height = float(start_sample['height_m'])

        for step_index in range(1, sample_count + 1):
            ratio = step_index / sample_count
            sample_x = float(from_x) + (float(to_x) - float(from_x)) * ratio
            sample_y = float(from_y) + (float(to_y) - float(from_y)) * ratio
            sample = self.sample_raster_layers(sample_x, sample_y)
            if sample['move_blocked']:
                return {
                    'ok': False,
                    'reason': 'blocked',
                    'start_height_m': start_sample['height_m'],
                    'end_height_m': sample['height_m'],
                }
            height_delta = abs(float(sample['height_m']) - previous_height)
            if height_delta > float(max_height_delta_m) + 1e-6:
                return {
                    'ok': False,
                    'reason': 'height_delta',
                    'start_height_m': start_sample['height_m'],
                    'end_height_m': sample['height_m'],
                    'height_delta_m': round(height_delta, 3),
                }
            previous_height = float(sample['height_m'])

        return {
            'ok': True,
            'reason': 'ok',
            'start_height_m': start_sample['height_m'],
            'end_height_m': end_sample['height_m'],
            'height_delta_m': round(abs(float(end_sample['height_m']) - float(start_sample['height_m'])), 3),
        }
    
    def is_position_valid(self, x, y):
        """检查位置是否有效（不在障碍物上）"""
        sample = self.sample_raster_layers(x, y)
        return not sample['move_blocked']
    
    def convert_world_to_screen(self, world_x, world_y):
        """将世界坐标转换为屏幕坐标"""
        screen_x = int((world_x - self.origin_x) * self.scale)
        screen_y = int((world_y - self.origin_y) * self.scale)
        return screen_x, screen_y
    
    def convert_screen_to_world(self, screen_x, screen_y):
        """将屏幕坐标转换为世界坐标"""
        world_x = (screen_x / self.scale) + self.origin_x
        world_y = (screen_y / self.scale) + self.origin_y
        return world_x, world_y

    def pixels_per_meter_x(self):
        return self.map_width / max(self.field_length_m, 1e-6)

    def pixels_per_meter_y(self):
        return self.map_height / max(self.field_width_m, 1e-6)

    def meters_to_world_units(self, meters):
        avg_pixels_per_meter = (self.pixels_per_meter_x() + self.pixels_per_meter_y()) / 2.0
        return meters * avg_pixels_per_meter
