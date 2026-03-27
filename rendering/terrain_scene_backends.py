#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

import numpy as np

from pygame_compat import pygame

try:
    import moderngl
    MODERNGL_IMPORT_ERROR = None
except Exception as exc:
    moderngl = None
    MODERNGL_IMPORT_ERROR = str(exc)


def create_terrain_scene_backend(name):
    selected = str(name or 'auto').strip().lower()
    if selected in {'auto', 'moderngl'} and moderngl is not None:
        try:
            return ModernGLTerrainSceneBackend()
        except Exception as exc:
            if selected == 'moderngl':
                raise
            reason = f'moderngl init failed: {exc}'
            return SoftwareTerrainSceneBackend(reason=reason, requested=selected)
    if selected in {'auto', 'moderngl'}:
        reason = f'moderngl unavailable: {MODERNGL_IMPORT_ERROR or "import failed"}'
        return SoftwareTerrainSceneBackend(reason=reason, requested=selected)
    return SoftwareTerrainSceneBackend(requested=selected)


def _sample_terrain_scene_data(renderer, map_manager, map_rgb):
    layers = map_manager.get_raster_layers()
    height_map = layers['height_map']
    terrain_type_map = layers['terrain_type_map']
    grid_width, grid_height = map_manager._grid_dimensions()
    cell_size = max(map_manager.terrain_grid_cell_size, 1)
    center_xs = np.minimum(map_manager.map_width - 1, np.arange(grid_width, dtype=np.int32) * cell_size + cell_size // 2)
    center_ys = np.minimum(map_manager.map_height - 1, np.arange(grid_height, dtype=np.int32) * cell_size + cell_size // 2)
    sampled_heights = height_map[np.ix_(center_ys, center_xs)]
    sampled_codes = terrain_type_map[np.ix_(center_ys, center_xs)]
    if map_rgb is not None:
        sampled_base_colors = map_rgb[np.ix_(center_ys, center_xs)]
    else:
        sampled_base_colors = np.full((grid_height, grid_width, 3), 214, dtype=np.uint8)

    if getattr(renderer, 'terrain_editor_tool', 'terrain') == 'facility':
        sampled_heights = np.zeros_like(sampled_heights)
        sampled_codes = np.zeros_like(sampled_codes)

    blended_colors = np.empty((grid_height, grid_width, 3), dtype=np.uint8)
    for grid_y in range(grid_height):
        for grid_x in range(grid_width):
            terrain_code = int(sampled_codes[grid_y, grid_x])
            base_color = sampled_base_colors[grid_y, grid_x]
            overlay_color = renderer._terrain_color_by_code(terrain_code)
            if terrain_code == 0:
                blended_colors[grid_y, grid_x] = base_color
            else:
                blended_colors[grid_y, grid_x] = [
                    min(255, int(base_color[index] * 0.38 + overlay_color[index] * 0.62))
                    for index in range(3)
                ]

    return {
        'grid_width': grid_width,
        'grid_height': grid_height,
        'cell_size': cell_size,
        'sampled_heights': sampled_heights,
        'sampled_codes': sampled_codes,
        'sampled_base_colors': sampled_base_colors,
        'blended_colors': blended_colors,
    }


def _terrain_scene_focus_grid(renderer, map_manager, grid_width, grid_height):
    focus_world = getattr(renderer, 'terrain_scene_focus_world', None)
    if focus_world is None:
        return (grid_width - 1) / 2.0, (grid_height - 1) / 2.0
    focus_grid_x, focus_grid_y = map_manager._world_to_grid(focus_world[0], focus_world[1])
    focus_grid_x = max(0, min(grid_width - 1, focus_grid_x))
    focus_grid_y = max(0, min(grid_height - 1, focus_grid_y))
    return float(focus_grid_x), float(focus_grid_y)


class SoftwareTerrainSceneBackend:
    name = 'software'

    def __init__(self, reason=None, requested=None):
        self.reason = reason
        self.requested = requested or 'software'
        if reason:
            self.status_label = f'software fallback | {reason}'
        else:
            self.status_label = 'software'

    def render_scene(self, renderer, game_engine, size, map_rgb=None):
        width, height = int(size[0]), int(size[1])
        surface = pygame.Surface((width, height))
        surface.fill((236, 240, 245))

        map_manager = game_engine.map_manager
        data = _sample_terrain_scene_data(renderer, map_manager, map_rgb)
        grid_width = data['grid_width']
        grid_height = data['grid_height']
        sampled_heights = data['sampled_heights']
        blended_colors = data['blended_colors']

        padding = 20
        yaw_cos = math.cos(renderer.terrain_3d_camera_yaw)
        yaw_sin = math.sin(renderer.terrain_3d_camera_yaw)
        pitch = max(0.18, min(1.15, renderer.terrain_3d_camera_pitch))
        scene_zoom = max(1.0, float(getattr(renderer, 'terrain_scene_zoom', 1.0)))
        center_offset_x, center_offset_y = _terrain_scene_focus_grid(renderer, map_manager, grid_width, grid_height)

        def build_entries(tile_width):
            depth_scale = max(3.0, tile_width * 0.95)
            height_scale = max(10.0, tile_width * 4.4)
            half_w = max(2.0, tile_width * 0.50)
            half_d = max(2.0, tile_width * 0.28 * pitch)
            entries = []
            min_x = float('inf')
            max_x = float('-inf')
            min_y = float('inf')
            max_y = float('-inf')

            for grid_y in range(grid_height):
                for grid_x in range(grid_width):
                    height_m = float(sampled_heights[grid_y, grid_x])
                    top_color = tuple(int(channel) for channel in blended_colors[grid_y, grid_x])
                    local_x = grid_x - center_offset_x
                    local_y = grid_y - center_offset_y
                    rotated_x = local_x * yaw_cos - local_y * yaw_sin
                    depth = local_x * yaw_sin + local_y * yaw_cos
                    screen_x = rotated_x * tile_width
                    screen_y = depth * depth_scale * pitch
                    height_px = height_m * height_scale
                    min_x = min(min_x, screen_x - half_w)
                    max_x = max(max_x, screen_x + half_w)
                    min_y = min(min_y, screen_y - half_d - height_px)
                    max_y = max(max_y, screen_y + half_d)
                    entries.append((depth, screen_x, screen_y, height_px, top_color, half_w, half_d))

            return entries, (min_x, max_x, min_y, max_y)

        initial_fit = min((width - padding * 2) / max(grid_width + grid_height, 1), (height - padding * 2) / max((grid_width + grid_height) * 0.58, 1))
        tile_w = max(3.0, min(48.0, initial_fit * scene_zoom))
        cell_entries, bounds = build_entries(tile_w)
        span_x = max(1.0, bounds[1] - bounds[0])
        span_y = max(1.0, bounds[3] - bounds[2])
        max_ratio = max((width - padding * 2) / span_x, (height - padding * 2) / span_y)
        min_ratio = min((width - padding * 2) / span_x, (height - padding * 2) / span_y, 1.0)
        fit_ratio = min_ratio if scene_zoom <= 1.0 else min(1.0, max_ratio)
        if fit_ratio < 0.999 or fit_ratio > 1.001:
            tile_w = max(2.0, tile_w * fit_ratio)
            cell_entries, bounds = build_entries(tile_w)
        offset_x = (width - (bounds[1] - bounds[0])) / 2.0 - bounds[0]
        offset_y = (height - (bounds[3] - bounds[2])) / 2.0 - bounds[2]

        cell_entries.sort(key=lambda item: item[0])
        for _, screen_x, screen_y, height_px, top_color, half_w, half_d in cell_entries:
            screen_x += offset_x
            screen_y += offset_y
            top = [
                (round(screen_x), round(screen_y - half_d - height_px)),
                (round(screen_x + half_w), round(screen_y - height_px)),
                (round(screen_x), round(screen_y + half_d - height_px)),
                (round(screen_x - half_w), round(screen_y - height_px)),
            ]
            left = [
                (round(screen_x - half_w), round(screen_y - height_px)),
                (round(screen_x), round(screen_y + half_d - height_px)),
                (round(screen_x), round(screen_y + half_d)),
                (round(screen_x - half_w), round(screen_y)),
            ]
            right = [
                (round(screen_x + half_w), round(screen_y - height_px)),
                (round(screen_x), round(screen_y + half_d - height_px)),
                (round(screen_x), round(screen_y + half_d)),
                (round(screen_x + half_w), round(screen_y)),
            ]
            left_color = tuple(max(0, int(channel * 0.70)) for channel in top_color)
            right_color = tuple(max(0, int(channel * 0.86)) for channel in top_color)
            pygame.draw.polygon(surface, left_color, left)
            pygame.draw.polygon(surface, right_color, right)
            pygame.draw.polygon(surface, top_color, top)
            pygame.draw.polygon(surface, renderer.colors['panel_border'], top, 1)

        return surface


class ModernGLTerrainSceneBackend:
    name = 'moderngl'

    def __init__(self):
        if moderngl is None:
            raise RuntimeError('ModernGL is not available')
        self.ctx = moderngl.create_standalone_context()
        self.program = self.ctx.program(
            vertex_shader='''
                #version 330
                in vec3 in_position;
                in vec3 in_color;
                uniform mat4 u_mvp;
                uniform vec3 u_light_dir;
                out vec3 v_color;
                void main() {
                    gl_Position = u_mvp * vec4(in_position, 1.0);
                    float light = 0.42 + max(dot(vec3(0.0, 1.0, 0.0), normalize(u_light_dir)), 0.0) * 0.58;
                    v_color = in_color * light;
                }
            ''',
            fragment_shader='''
                #version 330
                in vec3 v_color;
                out vec4 fragColor;
                void main() {
                    fragColor = vec4(v_color, 1.0);
                }
            ''',
        )
        self.framebuffer = None
        self.framebuffer_size = None
        self.vbo = None
        self.vao = None
        self.geometry_key = None
        self.scene_bounds = (1.0, 1.0, 1.0)
        self.status_label = 'moderngl'

    def render_scene(self, renderer, game_engine, size, map_rgb=None):
        width, height = int(size[0]), int(size[1])
        if width <= 0 or height <= 0:
            return pygame.Surface((1, 1))

        self._ensure_framebuffer((width, height))
        self._ensure_geometry(renderer, game_engine.map_manager, map_rgb)

        aspect = width / max(height, 1)
        grid_width, grid_height, max_height = self.scene_bounds
        scene_zoom = max(1.0, float(getattr(renderer, 'terrain_scene_zoom', 1.0)))
        distance = (max(grid_width, grid_height) * 1.28 + max_height * 2.4 + 6.0) / scene_zoom
        yaw = renderer.terrain_3d_camera_yaw
        pitch = max(0.20, min(1.15, renderer.terrain_3d_camera_pitch))
        focus_grid_x, focus_grid_y = _terrain_scene_focus_grid(renderer, game_engine.map_manager, int(grid_width), int(grid_height))
        target = np.array([
            focus_grid_x - grid_width / 2.0 + 0.5,
            max_height * 0.18,
            focus_grid_y - grid_height / 2.0 + 0.5,
        ], dtype='f4')
        camera = np.array([
            math.sin(yaw) * math.cos(pitch) * distance,
            math.sin(pitch) * distance + max_height * 0.55 + 2.0,
            math.cos(yaw) * math.cos(pitch) * distance,
        ], dtype='f4')
        camera += target

        projection = self._perspective_matrix(math.radians(52.0), aspect, 0.1, max(distance * 4.0, 200.0))
        view = self._look_at(camera, target, np.array([0.0, 1.0, 0.0], dtype='f4'))
        mvp = projection @ view

        self.framebuffer.use()
        self.framebuffer.clear(0.87, 0.90, 0.94, 1.0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.enable(moderngl.CULL_FACE)
        self.program['u_mvp'].write(mvp.astype('f4').tobytes())
        self.program['u_light_dir'].value = (0.35, 0.92, 0.28)
        self.vao.render(moderngl.TRIANGLES)

        raw = self.framebuffer.read(components=3, alignment=1)
        surface = pygame.image.fromstring(raw, (width, height), 'RGB')
        return pygame.transform.flip(surface, False, True)

    def _ensure_framebuffer(self, size):
        if self.framebuffer is not None and self.framebuffer_size == size:
            return
        if self.framebuffer is not None:
            self.framebuffer.release()
        self.framebuffer = self.ctx.simple_framebuffer(size)
        self.framebuffer_size = size

    def _ensure_geometry(self, renderer, map_manager, map_rgb):
        geometry_key = (map_manager.raster_version, map_manager.terrain_grid_cell_size)
        if self.geometry_key == geometry_key and self.vao is not None:
            return

        data = _sample_terrain_scene_data(renderer, map_manager, map_rgb)
        grid_width = data['grid_width']
        grid_height = data['grid_height']
        sampled_heights = data['sampled_heights']
        blended_colors = data['blended_colors']
        center_offset_x = grid_width / 2.0
        center_offset_y = grid_height / 2.0
        vertical_scale = 0.82
        vertices = []

        for grid_y in range(grid_height):
            for grid_x in range(grid_width):
                top_color = [channel / 255.0 for channel in blended_colors[grid_y, grid_x]]
                height_value = float(sampled_heights[grid_y, grid_x]) * vertical_scale
                x0 = grid_x - center_offset_x
                x1 = x0 + 1.0
                z0 = grid_y - center_offset_y
                z1 = z0 + 1.0
                p0 = (x0, height_value, z0)
                p1 = (x1, height_value, z0)
                p2 = (x1, height_value, z1)
                p3 = (x0, height_value, z1)
                vertices.extend((*p0, *top_color, *p1, *top_color, *p2, *top_color))
                vertices.extend((*p0, *top_color, *p2, *top_color, *p3, *top_color))

        vertex_array = np.array(vertices, dtype='f4')
        if self.vao is not None:
            self.vao.release()
        if self.vbo is not None:
            self.vbo.release()
        self.vbo = self.ctx.buffer(vertex_array.tobytes())
        self.vao = self.ctx.vertex_array(
            self.program,
            [(self.vbo, '3f 3f', 'in_position', 'in_color')],
        )
        self.scene_bounds = (
            max(1.0, float(grid_width)),
            max(1.0, float(grid_height)),
            max(1.0, float(np.max(sampled_heights) * vertical_scale)),
        )
        self.geometry_key = geometry_key

    def _perspective_matrix(self, fov_y, aspect, near, far):
        f = 1.0 / math.tan(fov_y / 2.0)
        matrix = np.zeros((4, 4), dtype='f4')
        matrix[0, 0] = f / max(aspect, 1e-6)
        matrix[1, 1] = f
        matrix[2, 2] = (far + near) / (near - far)
        matrix[2, 3] = (2.0 * far * near) / (near - far)
        matrix[3, 2] = -1.0
        return matrix

    def _look_at(self, eye, target, up):
        forward = target - eye
        forward /= max(np.linalg.norm(forward), 1e-6)
        right = np.cross(forward, up)
        right /= max(np.linalg.norm(right), 1e-6)
        true_up = np.cross(right, forward)

        matrix = np.identity(4, dtype='f4')
        matrix[0, :3] = right
        matrix[1, :3] = true_up
        matrix[2, :3] = -forward
        matrix[0, 3] = -np.dot(right, eye)
        matrix[1, 3] = -np.dot(true_up, eye)
        matrix[2, 3] = np.dot(forward, eye)
        return matrix