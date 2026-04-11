#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import math
import os
import sys
from copy import deepcopy

import numpy as np
from pygame_compat import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_manager import ConfigManager

try:
    import moderngl
    from rendering.terrain_scene_backends import _terrain_scene_look_at, _terrain_scene_perspective_matrix
    MODERNGL_PREVIEW_ERROR = None
except Exception as exc:
    moderngl = None
    MODERNGL_PREVIEW_ERROR = str(exc)


ROLE_ORDER = (
    ('hero', '英雄'),
    ('engineer', '工程'),
    ('infantry', '步兵'),
    ('sentry', '哨兵'),
)

PART_LABELS = {
    'body': '底盘',
    'wheel': '车轮',
    'turret': '云台',
    'barrel': '枪管',
    'mount': '连接件',
    'armor': '装甲板',
    'armor_light': '装甲灯条',
    'barrel_light': '枪管灯条',
}


def _normalize_profile_constraints(role_key, profile):
    normalized = deepcopy(profile)
    if 'barrel_length_m' not in normalized:
        normalized['barrel_length_m'] = 0.48 if role_key == 'hero' else (0.0 if role_key == 'engineer' else 0.36)
    if 'barrel_radius_m' not in normalized:
        normalized['barrel_radius_m'] = 0.020 if role_key == 'hero' else (0.0 if role_key == 'engineer' else 0.015)
    if role_key == 'engineer':
        normalized['gimbal_length_m'] = 0.0
        normalized['gimbal_width_m'] = 0.0
        normalized['gimbal_body_height_m'] = 0.0
        normalized['gimbal_mount_gap_m'] = 0.0
        normalized['gimbal_mount_length_m'] = 0.0
        normalized['gimbal_mount_width_m'] = 0.0
        normalized['gimbal_mount_height_m'] = 0.0
        normalized['barrel_length_m'] = 0.0
        normalized['barrel_radius_m'] = 0.0
    return normalized


def _default_profile(role_key):
    base_profiles = {
        'hero': {
            'body_length_m': 0.65,
            'body_width_m': 0.55,
            'body_height_m': 0.20,
            'body_clearance_m': 0.10,
            'wheel_radius_m': 0.08,
            'gimbal_length_m': 0.35,
            'gimbal_width_m': 0.15,
            'gimbal_body_height_m': 0.15,
            'gimbal_mount_gap_m': 0.10,
            'gimbal_mount_length_m': 0.12,
            'gimbal_mount_width_m': 0.12,
            'gimbal_mount_height_m': 0.10,
            'barrel_length_m': 0.48,
            'barrel_radius_m': 0.020,
            'gimbal_height_m': 0.475,
            'gimbal_offset_x_m': 0.0,
            'gimbal_offset_y_m': 0.0,
            'armor_plate_width_m': 0.24,
            'armor_plate_length_m': 0.24,
            'armor_plate_height_m': 0.24,
            'armor_plate_gap_m': 0.02,
            'armor_light_length_m': 0.12,
            'armor_light_width_m': 0.025,
            'armor_light_height_m': 0.025,
            'barrel_light_length_m': 0.12,
            'barrel_light_width_m': 0.02,
            'barrel_light_height_m': 0.02,
            'body_render_width_scale': 0.82,
            'wheel_style': 'mecanum',
            'suspension_style': 'none',
            'arm_style': 'none',
        },
        'engineer': {
            'body_length_m': 0.55,
            'body_width_m': 0.50,
            'body_height_m': 0.20,
            'body_clearance_m': 0.10,
            'wheel_radius_m': 0.08,
            'gimbal_length_m': 0.0,
            'gimbal_width_m': 0.0,
            'gimbal_body_height_m': 0.0,
            'gimbal_mount_gap_m': 0.0,
            'gimbal_mount_length_m': 0.0,
            'gimbal_mount_width_m': 0.0,
            'gimbal_mount_height_m': 0.0,
            'barrel_length_m': 0.0,
            'barrel_radius_m': 0.0,
            'gimbal_height_m': 0.42,
            'gimbal_offset_x_m': 0.0,
            'gimbal_offset_y_m': 0.0,
            'armor_plate_width_m': 0.16,
            'armor_plate_length_m': 0.16,
            'armor_plate_height_m': 0.16,
            'armor_plate_gap_m': 0.02,
            'armor_light_length_m': 0.10,
            'armor_light_width_m': 0.02,
            'armor_light_height_m': 0.02,
            'barrel_light_length_m': 0.10,
            'barrel_light_width_m': 0.02,
            'barrel_light_height_m': 0.02,
            'body_render_width_scale': 0.82,
            'wheel_style': 'mecanum',
            'suspension_style': 'none',
            'arm_style': 'fixed_7',
        },
        'infantry': {
            'body_length_m': 0.50,
            'body_width_m': 0.45,
            'body_height_m': 0.20,
            'body_clearance_m': 0.20,
            'wheel_radius_m': 0.06,
            'gimbal_length_m': 0.30,
            'gimbal_width_m': 0.10,
            'gimbal_body_height_m': 0.10,
            'gimbal_mount_gap_m': 0.10,
            'gimbal_mount_length_m': 0.10,
            'gimbal_mount_width_m': 0.10,
            'gimbal_mount_height_m': 0.10,
            'barrel_length_m': 0.36,
            'barrel_radius_m': 0.015,
            'gimbal_height_m': 0.55,
            'gimbal_offset_x_m': 0.0,
            'gimbal_offset_y_m': 0.0,
            'armor_plate_width_m': 0.16,
            'armor_plate_length_m': 0.16,
            'armor_plate_height_m': 0.16,
            'armor_plate_gap_m': 0.02,
            'armor_light_length_m': 0.10,
            'armor_light_width_m': 0.02,
            'armor_light_height_m': 0.02,
            'barrel_light_length_m': 0.10,
            'barrel_light_width_m': 0.02,
            'barrel_light_height_m': 0.02,
            'body_render_width_scale': 0.78,
            'wheel_style': 'legged',
            'suspension_style': 'five_link',
            'arm_style': 'none',
        },
        'sentry': {
            'body_length_m': 0.55,
            'body_width_m': 0.50,
            'body_height_m': 0.20,
            'body_clearance_m': 0.10,
            'wheel_radius_m': 0.08,
            'gimbal_length_m': 0.30,
            'gimbal_width_m': 0.10,
            'gimbal_body_height_m': 0.10,
            'gimbal_mount_gap_m': 0.10,
            'gimbal_mount_length_m': 0.10,
            'gimbal_mount_width_m': 0.10,
            'gimbal_mount_height_m': 0.10,
            'barrel_length_m': 0.36,
            'barrel_radius_m': 0.015,
            'gimbal_height_m': 0.45,
            'gimbal_offset_x_m': 0.0,
            'gimbal_offset_y_m': 0.0,
            'armor_plate_width_m': 0.16,
            'armor_plate_length_m': 0.16,
            'armor_plate_height_m': 0.16,
            'armor_plate_gap_m': 0.02,
            'armor_light_length_m': 0.10,
            'armor_light_width_m': 0.02,
            'armor_light_height_m': 0.02,
            'barrel_light_length_m': 0.10,
            'barrel_light_width_m': 0.02,
            'barrel_light_height_m': 0.02,
            'body_render_width_scale': 0.82,
            'wheel_style': 'mecanum',
            'suspension_style': 'none',
            'arm_style': 'none',
        },
    }
    profile = deepcopy(base_profiles[role_key])
    if profile['wheel_style'] == 'legged':
        wheel_y = profile['body_width_m'] * 0.5 + profile['wheel_radius_m'] * 0.55
        profile['custom_wheel_positions_m'] = [
            [0.0, -wheel_y],
            [0.0, wheel_y],
        ]
    else:
        wheel_x = profile['body_length_m'] * 0.39
        wheel_y = profile['body_width_m'] * 0.5 + profile['wheel_radius_m'] * 0.55
        profile['custom_wheel_positions_m'] = [
            [-wheel_x, -wheel_y],
            [wheel_x, -wheel_y],
            [-wheel_x, wheel_y],
            [wheel_x, wheel_y],
        ]
    profile['body_color_rgb'] = [166, 174, 186]
    profile['turret_color_rgb'] = [232, 232, 236]
    profile['armor_color_rgb'] = [224, 229, 234]
    profile['wheel_color_rgb'] = [44, 44, 44]
    return _normalize_profile_constraints(role_key, profile)


def _append_preview_face(vertices, p0, p1, p2, p3, color, normal):
    vertices.extend((*p0, *color, *normal, *p1, *color, *normal, *p2, *color, *normal))
    vertices.extend((*p0, *color, *normal, *p2, *color, *normal, *p3, *color, *normal))


def _append_preview_box(vertices, center, half_extents, color_rgb, yaw_rad=0.0):
    cx, cy, cz = center
    half_x, half_y, half_z = half_extents
    color = tuple(float(channel) / 255.0 for channel in color_rgb)
    cos_yaw = math.cos(yaw_rad)
    sin_yaw = math.sin(yaw_rad)

    def rotate_point(point):
        point_x, point_y, point_z = point
        return (
            cx + point_x * cos_yaw - point_z * sin_yaw,
            cy + point_y,
            cz + point_x * sin_yaw + point_z * cos_yaw,
        )

    def rotate_normal(normal):
        normal_x, normal_y, normal_z = normal
        return (
            normal_x * cos_yaw - normal_z * sin_yaw,
            normal_y,
            normal_x * sin_yaw + normal_z * cos_yaw,
        )

    corners = {
        'lbn': rotate_point((-half_x, -half_y, -half_z)),
        'rbn': rotate_point((half_x, -half_y, -half_z)),
        'rbs': rotate_point((half_x, -half_y, half_z)),
        'lbs': rotate_point((-half_x, -half_y, half_z)),
        'ltn': rotate_point((-half_x, half_y, -half_z)),
        'rtn': rotate_point((half_x, half_y, -half_z)),
        'rts': rotate_point((half_x, half_y, half_z)),
        'lts': rotate_point((-half_x, half_y, half_z)),
    }
    face_specs = (
        (('ltn', 'rtn', 'rts', 'lts'), (0.0, 1.0, 0.0), 1.0),
        (('lbs', 'rbs', 'rbn', 'lbn'), (0.0, -1.0, 0.0), 0.42),
        (('lbn', 'rbn', 'rtn', 'ltn'), (0.0, 0.0, -1.0), 0.68),
        (('rbs', 'lbs', 'lts', 'rts'), (0.0, 0.0, 1.0), 0.82),
        (('rbn', 'rbs', 'rts', 'rtn'), (1.0, 0.0, 0.0), 0.76),
        (('lbs', 'lbn', 'ltn', 'lts'), (-1.0, 0.0, 0.0), 0.60),
    )
    for corner_keys, normal, shade in face_specs:
        shaded_color = tuple(max(0.0, min(1.0, channel * shade)) for channel in color)
        rotated_normal = rotate_normal(normal)
        _append_preview_face(
            vertices,
            corners[corner_keys[0]],
            corners[corner_keys[1]],
            corners[corner_keys[2]],
            corners[corner_keys[3]],
            shaded_color,
            rotated_normal,
        )


def _append_preview_cylinder(vertices, center, radius, half_width, color_rgb, segments=12):
    cx, cy, cz = center
    color = tuple(float(channel) / 255.0 for channel in color_rgb)
    front_ring = []
    back_ring = []
    for index in range(segments):
        angle = (math.pi * 2.0 * index) / max(segments, 3)
        ring_x = math.cos(angle) * radius
        ring_y = math.sin(angle) * radius
        front_ring.append((cx + ring_x, cy + ring_y, cz - half_width))
        back_ring.append((cx + ring_x, cy + ring_y, cz + half_width))
    front_center = (cx, cy, cz - half_width)
    back_center = (cx, cy, cz + half_width)
    for index in range(segments):
        next_index = (index + 1) % segments
        normal_a = np.array(front_ring[index]) - np.array(front_center)
        normal_b = np.array(front_ring[next_index]) - np.array(front_center)
        average = normal_a + normal_b
        norm = np.linalg.norm(average)
        side_normal = tuple((average / norm).tolist()) if norm > 1e-6 else (1.0, 0.0, 0.0)
        _append_preview_face(vertices, front_ring[index], front_ring[next_index], back_ring[next_index], back_ring[index], color, side_normal)
        _append_preview_face(vertices, front_center, front_ring[next_index], front_ring[index], front_center, tuple(max(0.0, channel * 0.84) for channel in color), (0.0, 0.0, -1.0))
        _append_preview_face(vertices, back_center, back_ring[index], back_ring[next_index], back_center, tuple(max(0.0, channel * 0.94) for channel in color), (0.0, 0.0, 1.0))


class ModernGLAppearancePreview:
    def __init__(self):
        self.ctx = None
        self.program = None
        self.framebuffer = None
        self.framebuffer_size = None
        self.vbo = None
        self.vao = None
        self.geometry_key = None
        self.bounds_radius = 1.0
        self.error = MODERNGL_PREVIEW_ERROR
        if moderngl is None:
            return
        try:
            self.ctx = moderngl.create_standalone_context()
            self.program = self.ctx.program(
                vertex_shader='''
                    #version 330
                    in vec3 in_position;
                    in vec3 in_color;
                    in vec3 in_normal;
                    uniform mat4 u_mvp;
                    uniform vec3 u_light_dir;
                    out vec3 v_color;
                    void main() {
                        vec3 normal = normalize(in_normal);
                        float light = 0.38 + max(dot(normal, normalize(u_light_dir)), 0.0) * 0.62;
                        v_color = in_color * light;
                        gl_Position = u_mvp * vec4(in_position, 1.0);
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
            self.error = None
        except Exception as exc:
            self.error = str(exc)
            self.ctx = None
            self.program = None

    def _ensure_framebuffer(self, size):
        if self.ctx is None:
            return False
        if self.framebuffer is not None and self.framebuffer_size == size:
            return True
        if self.framebuffer is not None:
            self.framebuffer.release()
        self.framebuffer = self.ctx.simple_framebuffer(size)
        self.framebuffer_size = size
        return True

    def _profile_geometry_key(self, profile):
        return json.dumps(profile, sort_keys=True, ensure_ascii=True)

    def _build_geometry(self, profile):
        vertices = []
        render_width_scale = float(profile.get('body_render_width_scale', 0.82))
        has_turret = float(profile.get('gimbal_length_m', 0.0)) > 1e-6 and float(profile.get('gimbal_body_height_m', 0.0)) > 1e-6
        has_barrel = has_turret and float(profile.get('barrel_length_m', 0.0)) > 1e-6 and float(profile.get('barrel_radius_m', 0.0)) > 1e-6
        body_y = float(profile['body_clearance_m']) + float(profile['body_height_m']) * 0.5
        _append_preview_box(
            vertices,
            (0.0, body_y, 0.0),
            (float(profile['body_length_m']) * 0.5, float(profile['body_height_m']) * 0.5, float(profile['body_width_m']) * 0.5 * render_width_scale),
            profile['body_color_rgb'],
        )
        _append_preview_box(
            vertices,
            (0.0, body_y + float(profile['body_height_m']) * 0.36, 0.0),
            (float(profile['body_length_m']) * 0.40, max(0.015, float(profile['body_height_m']) * 0.12), float(profile['body_width_m']) * 0.40 * render_width_scale),
            [max(0, min(255, int(channel * 0.82 + 20))) for channel in profile['body_color_rgb']],
        )

        wheel_radius = max(0.018, float(profile['wheel_radius_m']))
        wheel_half_z = max(0.018, float(profile['wheel_radius_m']) * 0.32)
        for wheel_x, wheel_y in profile['custom_wheel_positions_m']:
            _append_preview_cylinder(
                vertices,
                (float(wheel_x), wheel_radius, float(wheel_y) * render_width_scale),
                wheel_radius,
                wheel_half_z,
                profile['wheel_color_rgb'],
            )

        armor_gap = float(profile['armor_plate_gap_m'])
        body_half_x = float(profile['body_length_m']) * 0.5
        body_half_z = float(profile['body_width_m']) * 0.5 * render_width_scale
        armor_half_h = float(profile['armor_plate_height_m']) * 0.5
        armor_center_y = float(profile['body_clearance_m']) + float(profile['body_height_m']) * 0.55
        armor_thickness = max(0.012, armor_gap * 0.75)
        armor_color = profile['armor_color_rgb']
        _append_preview_box(vertices, (body_half_x + armor_gap + armor_thickness * 0.5, armor_center_y, 0.0), (armor_thickness * 0.5, armor_half_h, float(profile['armor_plate_width_m']) * 0.5), armor_color)
        _append_preview_box(vertices, (-(body_half_x + armor_gap + armor_thickness * 0.5), armor_center_y, 0.0), (armor_thickness * 0.5, armor_half_h, float(profile['armor_plate_width_m']) * 0.5), armor_color)
        _append_preview_box(vertices, (0.0, armor_center_y, body_half_z + armor_gap + armor_thickness * 0.5), (float(profile['armor_plate_length_m']) * 0.5, armor_half_h, armor_thickness * 0.5), armor_color)
        _append_preview_box(vertices, (0.0, armor_center_y, -(body_half_z + armor_gap + armor_thickness * 0.5)), (float(profile['armor_plate_length_m']) * 0.5, armor_half_h, armor_thickness * 0.5), armor_color)
        armor_light_color = [110, 168, 255]
        armor_light_half_x = float(profile.get('armor_light_length_m', 0.10)) * 0.5
        armor_light_half_y = max(0.005, float(profile.get('armor_light_height_m', 0.02)) * 0.5)
        armor_light_half_z = max(0.005, float(profile.get('armor_light_width_m', 0.02)) * 0.5)
        _append_preview_box(vertices, (body_half_x + armor_gap + armor_thickness, armor_center_y, float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z), (armor_light_half_z, armor_light_half_y, armor_light_half_x), armor_light_color)
        _append_preview_box(vertices, (body_half_x + armor_gap + armor_thickness, armor_center_y, -(float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z)), (armor_light_half_z, armor_light_half_y, armor_light_half_x), armor_light_color)
        _append_preview_box(vertices, (-(body_half_x + armor_gap + armor_thickness), armor_center_y, float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z), (armor_light_half_z, armor_light_half_y, armor_light_half_x), armor_light_color)
        _append_preview_box(vertices, (-(body_half_x + armor_gap + armor_thickness), armor_center_y, -(float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z)), (armor_light_half_z, armor_light_half_y, armor_light_half_x), armor_light_color)
        _append_preview_box(vertices, (float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z, armor_center_y, body_half_z + armor_gap + armor_thickness), (armor_light_half_x, armor_light_half_y, armor_light_half_z), armor_light_color)
        _append_preview_box(vertices, (-(float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z), armor_center_y, body_half_z + armor_gap + armor_thickness), (armor_light_half_x, armor_light_half_y, armor_light_half_z), armor_light_color)
        _append_preview_box(vertices, (float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z, armor_center_y, -(body_half_z + armor_gap + armor_thickness)), (armor_light_half_x, armor_light_half_y, armor_light_half_z), armor_light_color)
        _append_preview_box(vertices, (-(float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z), armor_center_y, -(body_half_z + armor_gap + armor_thickness)), (armor_light_half_x, armor_light_half_y, armor_light_half_z), armor_light_color)

        if has_turret:
            turret_offset_x = float(profile['gimbal_offset_x_m'])
            turret_offset_z = float(profile['gimbal_offset_y_m'])
            if float(profile.get('gimbal_mount_height_m', 0.0)) > 1e-6:
                _append_preview_box(
                    vertices,
                    (turret_offset_x, body_y + float(profile['body_height_m']) * 0.5 + float(profile['gimbal_mount_height_m']) * 0.5, turret_offset_z),
                    (max(0.02, float(profile['gimbal_mount_length_m']) * 0.5), max(0.02, float(profile['gimbal_mount_height_m']) * 0.5), max(0.02, float(profile['gimbal_mount_width_m']) * 0.5 * render_width_scale)),
                    [96, 100, 112],
                )
            turret_center_y = float(profile['gimbal_height_m'])
            _append_preview_box(
                vertices,
                (turret_offset_x, turret_center_y, turret_offset_z),
                (float(profile['gimbal_length_m']) * 0.5, float(profile['gimbal_body_height_m']) * 0.5, float(profile['gimbal_width_m']) * 0.5 * render_width_scale),
                profile['turret_color_rgb'],
            )
            if has_barrel:
                barrel_length = float(profile['barrel_length_m'])
                barrel_radius = max(0.005, float(profile['barrel_radius_m']))
                _append_preview_box(
                    vertices,
                    (turret_offset_x + float(profile['gimbal_length_m']) * 0.5 + barrel_length * 0.5, turret_center_y, turret_offset_z),
                    (barrel_length * 0.5, barrel_radius, barrel_radius),
                    profile['turret_color_rgb'],
                )
                barrel_light_half_x = float(profile.get('barrel_light_length_m', 0.10)) * 0.5
                barrel_light_half_y = max(0.005, float(profile.get('barrel_light_height_m', 0.02)) * 0.5)
                barrel_light_half_z = max(0.005, float(profile.get('barrel_light_width_m', 0.02)) * 0.5)
                barrel_light_center_x = turret_offset_x + float(profile['gimbal_length_m']) * 0.5 + barrel_length * 0.45
                _append_preview_box(vertices, (barrel_light_center_x, turret_center_y, turret_offset_z + barrel_light_half_z * 3.0), (barrel_light_half_x, barrel_light_half_y, barrel_light_half_z), armor_light_color)
                _append_preview_box(vertices, (barrel_light_center_x, turret_center_y, turret_offset_z - barrel_light_half_z * 3.0), (barrel_light_half_x, barrel_light_half_y, barrel_light_half_z), armor_light_color)

        if str(profile.get('arm_style', 'none')) == 'fixed_7':
            _append_preview_box(vertices, (0.0, body_y + float(profile['body_height_m']) * 0.95, 0.0), (0.03, 0.22, 0.03), [172, 176, 184])
            _append_preview_box(vertices, (float(profile['body_length_m']) * 0.16, body_y + float(profile['body_height_m']) + 0.18, 0.0), (0.18, 0.03, 0.03), [188, 192, 198])

        vertex_array = np.array(vertices, dtype='f4')
        self.bounds_radius = max(
            0.6,
            float(profile['body_length_m']) * 0.9,
            float(profile['body_width_m']) * 0.9,
            float(profile.get('gimbal_length_m', 0.0)) + float(profile.get('barrel_length_m', 0.0)) * 0.8,
            float(profile['gimbal_height_m']) + 0.25,
        )
        if self.vao is not None:
            self.vao.release()
        if self.vbo is not None:
            self.vbo.release()
        self.vbo = self.ctx.buffer(vertex_array.tobytes())
        self.vao = self.ctx.vertex_array(self.program, [(self.vbo, '3f 3f 3f', 'in_position', 'in_color', 'in_normal')])

    def render_scene(self, profile, size, yaw=0.72, pitch=0.42):
        width, height = int(size[0]), int(size[1])
        if width <= 1 or height <= 1:
            return None
        if self.ctx is None or self.program is None or not self._ensure_framebuffer((width, height)):
            return None
        geometry_key = self._profile_geometry_key(profile)
        if geometry_key != self.geometry_key:
            self._build_geometry(profile)
            self.geometry_key = geometry_key

        target = np.array([0.0, float(profile['body_clearance_m']) + float(profile['body_height_m']) * 0.45, 0.0], dtype='f4')
        distance = max(1.4, self.bounds_radius * 2.9)
        eye = np.array([
            math.sin(yaw) * math.cos(pitch) * distance,
            math.sin(pitch) * distance + self.bounds_radius * 0.25,
            math.cos(yaw) * math.cos(pitch) * distance,
        ], dtype='f4') + target
        projection = _terrain_scene_perspective_matrix(math.radians(42.0), width / max(height, 1), 0.05, max(8.0, distance * 6.0))
        view = _terrain_scene_look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype='f4'))
        mvp = projection @ view

        self.framebuffer.use()
        self.framebuffer.clear(0.08, 0.10, 0.13, 1.0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        self.program['u_mvp'].write(mvp.T.astype('f4').tobytes())
        self.program['u_light_dir'].value = (0.35, 0.92, 0.28)
        self.vao.render(moderngl.TRIANGLES)

        raw = self.framebuffer.read(components=3, alignment=1)
        return pygame.transform.flip(pygame.image.fromstring(raw, (width, height), 'RGB'), False, True)


class AppearanceEditorApp:
    def __init__(self, config_path='config.json', settings_path='settings.json'):
        self.config_path = config_path
        self.settings_path = settings_path
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config(config_path, settings_path)
        self.config['_config_path'] = config_path
        self.config['_settings_path'] = settings_path
        self.preset_path = self._resolve_preset_path()
        self.profiles = self._load_profiles()
        self.current_role = ROLE_ORDER[0][0]
        self.selected_part = None
        self.selected_field_index = 0
        self.status_text = '右侧预览点击部件后编辑，左右方向键调整，Shift 加速，Ctrl+S 保存，Tab 切换车型，R 重置当前车型'
        self.running = True
        self.preview_mode = 'split'
        self.preview_3d_yaw = 0.72
        self.preview_3d_pitch = 0.42
        self.field_scroll = 0
        self.field_scroll_drag_active = False
        self.preview_drag_active = False
        self.preview_mode_tabs = []
        self.preview_part_hitboxes = []
        self.field_scrollbar_thumb_rect = None
        self.field_scrollbar_track_rect = None
        self.field_panel_rect = None
        self.preview_panel_rect = None
        self.preview_content_rect = None

        pygame.init()
        pygame.display.set_caption('车辆外貌编辑器')
        self.window_width = 1460
        self.window_height = 900
        self.screen = pygame.display.set_mode((self.window_width, self.window_height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.SysFont('microsoftyaheiui', 28)
        self.font = pygame.font.SysFont('microsoftyaheiui', 20)
        self.small_font = pygame.font.SysFont('microsoftyaheiui', 16)
        self.tiny_font = pygame.font.SysFont('microsoftyaheiui', 13)
        self.colors = {
            'bg': (17, 21, 27),
            'panel': (26, 31, 38),
            'panel_alt': (32, 38, 46),
            'panel_border': (82, 92, 106),
            'text': (232, 237, 242),
            'muted': (166, 174, 184),
            'accent': (255, 166, 72),
            'accent_dim': (96, 68, 38),
            'success': (88, 176, 118),
            'danger': (196, 92, 92),
            'preview_bg': (13, 16, 21),
            'grid': (55, 61, 69),
        }
        self.field_specs = self._build_field_specs()
        self.preview_renderer_3d = ModernGLAppearancePreview()

    def _resolve_preset_path(self):
        configured_path = str(self.config.get('entities', {}).get('appearance_preset_path', os.path.join('appearance_presets', 'latest_appearance.json')))
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.join(os.path.dirname(os.path.abspath(self.config_path)), configured_path)

    def _load_profiles(self):
        profiles = {role_key: _default_profile(role_key) for role_key, _ in ROLE_ORDER}
        if os.path.exists(self.preset_path):
            try:
                with open(self.preset_path, 'r', encoding='utf-8') as file:
                    payload = json.load(file)
            except Exception:
                payload = {}
            stored_profiles = payload.get('profiles', {}) if isinstance(payload, dict) else {}
            if isinstance(stored_profiles, dict):
                for role_key in profiles:
                    override = stored_profiles.get(role_key, {})
                    if isinstance(override, dict):
                        profiles[role_key].update(deepcopy(override))
                    profiles[role_key] = _normalize_profile_constraints(role_key, profiles[role_key])
        return profiles

    def _save_profiles(self):
        for role_key in list(self.profiles.keys()):
            self.profiles[role_key] = _normalize_profile_constraints(role_key, self.profiles[role_key])
        os.makedirs(os.path.dirname(self.preset_path), exist_ok=True)
        with open(self.preset_path, 'w', encoding='utf-8') as file:
            json.dump({'profiles': self.profiles}, file, ensure_ascii=False, indent=2)
        self.status_text = f'已保存到 {self.preset_path}'

    def _build_field_specs(self):
        fields = [
            {'part': 'body', 'label': '底盘长度', 'kind': 'number', 'key': 'body_length_m', 'min': 0.30, 'max': 1.20, 'step': 0.01},
            {'part': 'body', 'label': '底盘宽度', 'kind': 'number', 'key': 'body_width_m', 'min': 0.20, 'max': 1.00, 'step': 0.01},
            {'part': 'body', 'label': '视觉宽度系数', 'kind': 'number', 'key': 'body_render_width_scale', 'min': 0.45, 'max': 1.00, 'step': 0.01},
            {'part': 'body', 'label': '底盘高度', 'kind': 'number', 'key': 'body_height_m', 'min': 0.10, 'max': 0.60, 'step': 0.01},
            {'part': 'body', 'label': '离地间隙', 'kind': 'number', 'key': 'body_clearance_m', 'min': 0.02, 'max': 0.40, 'step': 0.01},
            {'part': 'turret', 'label': '云台长度', 'kind': 'number', 'key': 'gimbal_length_m', 'min': 0.10, 'max': 0.80, 'step': 0.01},
            {'part': 'turret', 'label': '云台宽度', 'kind': 'number', 'key': 'gimbal_width_m', 'min': 0.05, 'max': 0.40, 'step': 0.01},
            {'part': 'turret', 'label': '云台厚度', 'kind': 'number', 'key': 'gimbal_body_height_m', 'min': 0.05, 'max': 0.30, 'step': 0.01},
            {'part': 'turret', 'label': '云台高度', 'kind': 'number', 'key': 'gimbal_height_m', 'min': 0.10, 'max': 1.20, 'step': 0.01},
            {'part': 'turret', 'label': '云台偏移X', 'kind': 'number', 'key': 'gimbal_offset_x_m', 'min': -0.30, 'max': 0.30, 'step': 0.01},
            {'part': 'turret', 'label': '云台偏移Y', 'kind': 'number', 'key': 'gimbal_offset_y_m', 'min': -0.30, 'max': 0.30, 'step': 0.01},
            {'part': 'mount', 'label': '连接件长度', 'kind': 'number', 'key': 'gimbal_mount_length_m', 'min': 0.04, 'max': 0.40, 'step': 0.01},
            {'part': 'mount', 'label': '连接件宽度', 'kind': 'number', 'key': 'gimbal_mount_width_m', 'min': 0.04, 'max': 0.40, 'step': 0.01},
            {'part': 'mount', 'label': '连接件高度', 'kind': 'number', 'key': 'gimbal_mount_height_m', 'min': 0.04, 'max': 0.40, 'step': 0.01},
            {'part': 'barrel', 'label': '枪管长度', 'kind': 'number', 'key': 'barrel_length_m', 'min': 0.08, 'max': 0.80, 'step': 0.01},
            {'part': 'barrel', 'label': '枪管半径', 'kind': 'number', 'key': 'barrel_radius_m', 'min': 0.005, 'max': 0.06, 'step': 0.001},
            {'part': 'armor', 'label': '装甲宽度', 'kind': 'number', 'key': 'armor_plate_width_m', 'min': 0.08, 'max': 0.40, 'step': 0.01},
            {'part': 'armor', 'label': '装甲长度', 'kind': 'number', 'key': 'armor_plate_length_m', 'min': 0.08, 'max': 0.40, 'step': 0.01},
            {'part': 'armor', 'label': '装甲高度', 'kind': 'number', 'key': 'armor_plate_height_m', 'min': 0.08, 'max': 0.40, 'step': 0.01},
            {'part': 'armor', 'label': '装甲间距', 'kind': 'number', 'key': 'armor_plate_gap_m', 'min': 0.005, 'max': 0.08, 'step': 0.005},
            {'part': 'armor_light', 'label': '灯条长度', 'kind': 'number', 'key': 'armor_light_length_m', 'min': 0.04, 'max': 0.30, 'step': 0.005},
            {'part': 'armor_light', 'label': '灯条宽度', 'kind': 'number', 'key': 'armor_light_width_m', 'min': 0.005, 'max': 0.08, 'step': 0.005},
            {'part': 'armor_light', 'label': '灯条高度', 'kind': 'number', 'key': 'armor_light_height_m', 'min': 0.005, 'max': 0.08, 'step': 0.005},
            {'part': 'barrel_light', 'label': '灯条长度', 'kind': 'number', 'key': 'barrel_light_length_m', 'min': 0.04, 'max': 0.30, 'step': 0.005},
            {'part': 'barrel_light', 'label': '灯条宽度', 'kind': 'number', 'key': 'barrel_light_width_m', 'min': 0.005, 'max': 0.08, 'step': 0.005},
            {'part': 'barrel_light', 'label': '灯条高度', 'kind': 'number', 'key': 'barrel_light_height_m', 'min': 0.005, 'max': 0.08, 'step': 0.005},
            {'part': 'wheel', 'label': '轮半径', 'kind': 'number', 'key': 'wheel_radius_m', 'min': 0.03, 'max': 0.20, 'step': 0.005},
        ]
        for color_key, part, label in (
            ('body_color_rgb', 'body', '底盘'),
            ('turret_color_rgb', 'turret', '云台'),
            ('armor_color_rgb', 'armor', '装甲'),
            ('wheel_color_rgb', 'wheel', '车轮'),
        ):
            for channel_index, channel_label in enumerate(('R', 'G', 'B')):
                fields.append({'part': part, 'label': f'{label} {channel_label}', 'kind': 'color', 'color_key': color_key, 'channel': channel_index, 'min': 0, 'max': 255, 'step': 1})
        return fields

    def _profile_has_turret(self, profile):
        return float(profile.get('gimbal_length_m', 0.0)) > 1e-6 and float(profile.get('gimbal_body_height_m', 0.0)) > 1e-6

    def _profile_has_mount(self, profile):
        return self._profile_has_turret(profile) and float(profile.get('gimbal_mount_height_m', 0.0)) > 1e-6

    def _profile_has_barrel(self, profile):
        return self._profile_has_turret(profile) and float(profile.get('barrel_length_m', 0.0)) > 1e-6 and float(profile.get('barrel_radius_m', 0.0)) > 1e-6

    def _visible_field_specs(self):
        if self.selected_part is None:
            return []
        profile = self._current_profile()
        if self.selected_part == 'turret' and not self._profile_has_turret(profile):
            return []
        if self.selected_part == 'mount' and not self._profile_has_mount(profile):
            return []
        if self.selected_part in {'barrel', 'barrel_light'} and not self._profile_has_barrel(profile):
            return []
        fields = [spec for spec in self.field_specs if spec.get('part') == self.selected_part]
        if self.selected_part == 'wheel':
            for index, _ in enumerate(profile.get('custom_wheel_positions_m', [])):
                fields.append({'part': 'wheel', 'label': f'轮 {index + 1} X', 'kind': 'wheel', 'wheel_index': index, 'axis': 0, 'min': -0.80, 'max': 0.80, 'step': 0.01})
                fields.append({'part': 'wheel', 'label': f'轮 {index + 1} Y', 'kind': 'wheel', 'wheel_index': index, 'axis': 1, 'min': -0.80, 'max': 0.80, 'step': 0.01})
        return fields

    def _current_profile(self):
        return self.profiles[self.current_role]

    def _field_value(self, spec):
        profile = self._current_profile()
        if spec['kind'] == 'number':
            return float(profile.get(spec['key'], 0.0))
        if spec['kind'] == 'wheel':
            return float(profile['custom_wheel_positions_m'][spec['wheel_index']][spec['axis']])
        return int(profile[spec['color_key']][spec['channel']])

    def _set_field_value(self, spec, value):
        clamped = max(spec['min'], min(spec['max'], value))
        profile = self._current_profile()
        if spec['kind'] == 'number':
            profile[spec['key']] = round(float(clamped), 3)
            if spec['key'] in {'body_length_m', 'body_width_m', 'wheel_radius_m'}:
                self._rebuild_default_wheel_layout_if_needed(profile)
            self.profiles[self.current_role] = _normalize_profile_constraints(self.current_role, profile)
            return
        if spec['kind'] == 'wheel':
            profile['custom_wheel_positions_m'][spec['wheel_index']][spec['axis']] = round(float(clamped), 3)
            return
        profile[spec['color_key']][spec['channel']] = int(round(clamped))

    def _rebuild_default_wheel_layout_if_needed(self, profile):
        current = profile.get('custom_wheel_positions_m', [])
        wheel_count = 2 if str(profile.get('wheel_style', 'standard')) == 'legged' else 4
        if not isinstance(current, list) or len(current) != wheel_count:
            current = []
        wheel_y = round(float(profile['body_width_m']) * 0.5 + float(profile['wheel_radius_m']) * 0.55, 3)
        if wheel_count == 2:
            defaults = [
                [0.0, -wheel_y],
                [0.0, wheel_y],
            ]
        else:
            wheel_x = round(float(profile['body_length_m']) * 0.39, 3)
            defaults = [
                [-wheel_x, -wheel_y],
                [wheel_x, -wheel_y],
                [-wheel_x, wheel_y],
                [wheel_x, wheel_y],
            ]
        if not current or all(len(position) < 2 for position in current):
            profile['custom_wheel_positions_m'] = defaults

    def _adjust_selected(self, direction, fast=False):
        visible_fields = self._visible_field_specs()
        if not visible_fields:
            return
        self.selected_field_index = max(0, min(self.selected_field_index, len(visible_fields) - 1))
        spec = visible_fields[self.selected_field_index]
        step = spec['step'] * (5 if fast else 1)
        self._set_field_value(spec, self._field_value(spec) + direction * step)

    def _role_tabs(self):
        tabs = []
        start_x = 28
        for role_key, label in ROLE_ORDER:
            tabs.append((role_key, label, pygame.Rect(start_x, 72, 110, 40)))
            start_x += 122
        return tabs

    def _layout_panels(self):
        field_width = max(430, min(620, int(self.window_width * 0.36)))
        preview_x = 24 + field_width + 22
        preview_width = max(420, self.window_width - preview_x - 24)
        panel_height = self.window_height - 188
        self.field_panel_rect = pygame.Rect(24, 126, field_width, panel_height)
        self.preview_panel_rect = pygame.Rect(preview_x, 126, preview_width, panel_height)
        return self.field_panel_rect, self.preview_panel_rect

    def _field_rows(self, rect, scroll_offset=0):
        rows = []
        row_height = 28
        y = 52 - int(scroll_offset)
        row_width = rect.width - 30
        visible_fields = self._visible_field_specs()
        for index, spec in enumerate(visible_fields):
            rows.append(('field', spec, pygame.Rect(rect.x + 10, rect.y + y, row_width, row_height), index))
            y += row_height + 4
        content_height = max(0, y + 12)
        return rows, content_height

    def _max_field_scroll(self, rect):
        _, content_height = self._field_rows(rect, scroll_offset=0)
        visible_height = max(1, rect.height - 64)
        return max(0, content_height - visible_height)

    def _set_field_scroll(self, rect, value):
        self.field_scroll = max(0, min(self._max_field_scroll(rect), int(round(value))))

    def _ensure_selected_field_visible(self, rect):
        rows, _ = self._field_rows(rect, scroll_offset=self.field_scroll)
        target_rect = next((row_rect for row_type, _, row_rect, field_index in rows if row_type == 'field' and field_index == self.selected_field_index), None)
        content_top = rect.y + 44
        content_bottom = rect.bottom - 12
        if target_rect is None:
            return
        if target_rect.top < content_top:
            self._set_field_scroll(rect, self.field_scroll - (content_top - target_rect.top))
        elif target_rect.bottom > content_bottom:
            self._set_field_scroll(rect, self.field_scroll + (target_rect.bottom - content_bottom))

    def _preview_mode_rects(self, rect):
        tabs = []
        labels = (('split', '双视图'), ('top', '俯视'), ('side', '侧视'), ('3d', '3D'))
        x = rect.x + 12
        for mode_key, label in labels:
            tab_rect = pygame.Rect(x, rect.y + 10, 86, 30)
            tabs.append((mode_key, label, tab_rect))
            x += 94
        return tabs

    def _draw_text(self, text, font, color, pos):
        surface = font.render(text, True, color)
        self.screen.blit(surface, pos)

    def _iter_3d_preview_primitives(self, profile):
        render_width_scale = float(profile.get('body_render_width_scale', 0.82))
        has_turret = self._profile_has_turret(profile)
        has_mount = self._profile_has_mount(profile)
        has_barrel = self._profile_has_barrel(profile)
        body_y = float(profile['body_clearance_m']) + float(profile['body_height_m']) * 0.5
        yield ('body', (0.0, body_y, 0.0), (float(profile['body_length_m']) * 0.5, float(profile['body_height_m']) * 0.5, float(profile['body_width_m']) * 0.5 * render_width_scale))

        wheel_radius = max(0.018, float(profile['wheel_radius_m']))
        wheel_half_z = max(0.018, float(profile['wheel_radius_m']) * 0.32)
        for wheel_x, wheel_y in profile['custom_wheel_positions_m']:
            yield ('wheel', (float(wheel_x), wheel_radius, float(wheel_y) * render_width_scale), (wheel_radius, wheel_radius, wheel_half_z))

        armor_gap = float(profile['armor_plate_gap_m'])
        body_half_x = float(profile['body_length_m']) * 0.5
        body_half_z = float(profile['body_width_m']) * 0.5 * render_width_scale
        armor_half_h = float(profile['armor_plate_height_m']) * 0.5
        armor_center_y = float(profile['body_clearance_m']) + float(profile['body_height_m']) * 0.55
        armor_thickness = max(0.012, armor_gap * 0.75)
        armor_half_width = float(profile['armor_plate_width_m']) * 0.5
        armor_half_length = float(profile['armor_plate_length_m']) * 0.5
        for center, extents in (
            ((body_half_x + armor_gap + armor_thickness * 0.5, armor_center_y, 0.0), (armor_thickness * 0.5, armor_half_h, armor_half_width)),
            ((-(body_half_x + armor_gap + armor_thickness * 0.5), armor_center_y, 0.0), (armor_thickness * 0.5, armor_half_h, armor_half_width)),
            ((0.0, armor_center_y, body_half_z + armor_gap + armor_thickness * 0.5), (armor_half_length, armor_half_h, armor_thickness * 0.5)),
            ((0.0, armor_center_y, -(body_half_z + armor_gap + armor_thickness * 0.5)), (armor_half_length, armor_half_h, armor_thickness * 0.5)),
        ):
            yield ('armor', center, extents)

        armor_light_half_x = float(profile.get('armor_light_length_m', 0.10)) * 0.5
        armor_light_half_y = max(0.005, float(profile.get('armor_light_height_m', 0.02)) * 0.5)
        armor_light_half_z = max(0.005, float(profile.get('armor_light_width_m', 0.02)) * 0.5)
        armor_light_centers = (
            (body_half_x + armor_gap + armor_thickness, armor_center_y, float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z),
            (body_half_x + armor_gap + armor_thickness, armor_center_y, -(float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z)),
            (-(body_half_x + armor_gap + armor_thickness), armor_center_y, float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z),
            (-(body_half_x + armor_gap + armor_thickness), armor_center_y, -(float(profile['armor_plate_width_m']) * 0.5 + armor_light_half_z)),
            (float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z, armor_center_y, body_half_z + armor_gap + armor_thickness),
            (-(float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z), armor_center_y, body_half_z + armor_gap + armor_thickness),
            (float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z, armor_center_y, -(body_half_z + armor_gap + armor_thickness)),
            (-(float(profile['armor_plate_length_m']) * 0.5 + armor_light_half_z), armor_center_y, -(body_half_z + armor_gap + armor_thickness)),
        )
        for center in armor_light_centers:
            yield ('armor_light', center, (armor_light_half_x, armor_light_half_y, armor_light_half_z))

        if has_mount or has_turret:
            turret_offset_x = float(profile['gimbal_offset_x_m'])
            turret_offset_z = float(profile['gimbal_offset_y_m'])
            if has_mount:
                yield (
                    'mount',
                    (turret_offset_x, body_y + float(profile['body_height_m']) * 0.5 + float(profile['gimbal_mount_height_m']) * 0.5, turret_offset_z),
                    (max(0.02, float(profile['gimbal_mount_length_m']) * 0.5), max(0.02, float(profile['gimbal_mount_height_m']) * 0.5), max(0.02, float(profile['gimbal_mount_width_m']) * 0.5 * render_width_scale)),
                )
            if has_turret:
                turret_center_y = float(profile['gimbal_height_m'])
                yield (
                    'turret',
                    (turret_offset_x, turret_center_y, turret_offset_z),
                    (float(profile['gimbal_length_m']) * 0.5, float(profile['gimbal_body_height_m']) * 0.5, float(profile['gimbal_width_m']) * 0.5 * render_width_scale),
                )
                if has_barrel:
                    barrel_length = float(profile['barrel_length_m'])
                    barrel_radius = max(0.005, float(profile['barrel_radius_m']))
                    yield (
                        'barrel',
                        (turret_offset_x + float(profile['gimbal_length_m']) * 0.5 + barrel_length * 0.5, turret_center_y, turret_offset_z),
                        (barrel_length * 0.5, barrel_radius, barrel_radius),
                    )
                    barrel_light_half_x = float(profile.get('barrel_light_length_m', 0.10)) * 0.5
                    barrel_light_half_y = max(0.005, float(profile.get('barrel_light_height_m', 0.02)) * 0.5)
                    barrel_light_half_z = max(0.005, float(profile.get('barrel_light_width_m', 0.02)) * 0.5)
                    barrel_light_center_x = turret_offset_x + float(profile['gimbal_length_m']) * 0.5 + barrel_length * 0.45
                    yield ('barrel_light', (barrel_light_center_x, turret_center_y, turret_offset_z + barrel_light_half_z * 3.0), (barrel_light_half_x, barrel_light_half_y, barrel_light_half_z))
                    yield ('barrel_light', (barrel_light_center_x, turret_center_y, turret_offset_z - barrel_light_half_z * 3.0), (barrel_light_half_x, barrel_light_half_y, barrel_light_half_z))

    def _project_3d_preview_point(self, point, mvp, size):
        clip = mvp @ np.array([float(point[0]), float(point[1]), float(point[2]), 1.0], dtype='f4')
        if abs(float(clip[3])) <= 1e-6:
            return None
        ndc = clip[:3] / float(clip[3])
        if float(ndc[2]) < -1.2 or float(ndc[2]) > 1.2:
            return None
        width, height = size
        screen_x = (float(ndc[0]) * 0.5 + 0.5) * width
        screen_y = (1.0 - (float(ndc[1]) * 0.5 + 0.5)) * height
        return (screen_x, screen_y)

    def _build_3d_preview_hitboxes(self, rect, profile):
        if '_terrain_scene_look_at' not in globals() or '_terrain_scene_perspective_matrix' not in globals():
            return
        width, height = rect.size
        if width <= 1 or height <= 1:
            return
        target = np.array([0.0, float(profile['body_clearance_m']) + float(profile['body_height_m']) * 0.45, 0.0], dtype='f4')
        bounds_radius = max(
            0.6,
            float(profile['body_length_m']) * 0.9,
            float(profile['body_width_m']) * 0.9,
            float(profile.get('gimbal_length_m', 0.0)) + float(profile.get('barrel_length_m', 0.0)) * 0.8,
            float(profile.get('gimbal_height_m', 0.0)) + 0.25,
        )
        distance = max(1.4, bounds_radius * 2.9)
        eye = np.array([
            math.sin(self.preview_3d_yaw) * math.cos(self.preview_3d_pitch) * distance,
            math.sin(self.preview_3d_pitch) * distance + bounds_radius * 0.25,
            math.cos(self.preview_3d_yaw) * math.cos(self.preview_3d_pitch) * distance,
        ], dtype='f4') + target
        projection = _terrain_scene_perspective_matrix(math.radians(42.0), width / max(height, 1), 0.05, max(8.0, distance * 6.0))
        view = _terrain_scene_look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype='f4'))
        mvp = projection @ view
        hitboxes = []
        for part, center, half_extents in self._iter_3d_preview_primitives(profile):
            cx, cy, cz = center
            hx, hy, hz = half_extents
            projected = []
            for offset_x in (-hx, hx):
                for offset_y in (-hy, hy):
                    for offset_z in (-hz, hz):
                        point = self._project_3d_preview_point((cx + offset_x, cy + offset_y, cz + offset_z), mvp, (width, height))
                        if point is not None:
                            projected.append(point)
            if not projected:
                continue
            xs = [point[0] for point in projected]
            ys = [point[1] for point in projected]
            box = pygame.Rect(int(min(xs)), int(min(ys)), max(6, int(max(xs) - min(xs))), max(6, int(max(ys) - min(ys))))
            box.move_ip(rect.x, rect.y)
            distance_to_eye = float(np.linalg.norm(np.array(center, dtype='f4') - eye))
            hitboxes.append((distance_to_eye, part, box.inflate(8, 8)))
        for _, part, box in sorted(hitboxes, key=lambda item: item[0], reverse=True):
            self.preview_part_hitboxes.append((part, box))

    def _draw_top_preview(self, rect, profile):
        pygame.draw.rect(self.screen, self.colors['preview_bg'], rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=12)
        self._draw_text('俯视预览', self.font, self.colors['text'], (rect.x + 14, rect.y + 12))
        center = (rect.centerx, rect.centery + 16)
        render_width_scale = float(profile.get('body_render_width_scale', 0.82))
        has_mount = self._profile_has_mount(profile)
        has_turret = self._profile_has_turret(profile)
        has_barrel = self._profile_has_barrel(profile)
        max_extent = max(profile['body_length_m'] * 0.75, profile['body_width_m'] * render_width_scale * 0.85, float(profile.get('gimbal_length_m', 0.0)) + float(profile.get('barrel_length_m', 0.0)), 0.45)
        scale = min((rect.width - 80) / max(max_extent * 2.0, 0.6), (rect.height - 100) / max(max_extent * 2.0, 0.6))

        def world_to_screen(point_x, point_y):
            return (int(center[0] + point_x * scale), int(center[1] + point_y * scale))

        def highlight_rect(target_rect, radius=8):
            pygame.draw.rect(self.screen, (244, 214, 72), target_rect.inflate(6, 6), 3, border_radius=radius)

        def register_hitbox(part, area_rect):
            self.preview_part_hitboxes.append((part, area_rect.inflate(8, 8)))

        body_color = tuple(profile['body_color_rgb'])
        turret_color = tuple(profile['turret_color_rgb'])
        armor_color = tuple(profile['armor_color_rgb'])
        wheel_color = tuple(profile['wheel_color_rgb'])
        team_light_color = (110, 168, 255)

        body_rect = pygame.Rect(0, 0, int(profile['body_length_m'] * scale), int(profile['body_width_m'] * render_width_scale * scale))
        body_rect.center = center
        pygame.draw.rect(self.screen, body_color, body_rect, border_radius=10)
        pygame.draw.rect(self.screen, (18, 20, 24), body_rect, 2, border_radius=10)
        register_hitbox('body', body_rect)
        if self.selected_part == 'body':
            highlight_rect(body_rect, radius=10)

        for wheel_x, wheel_y in profile['custom_wheel_positions_m']:
            wheel_pos = world_to_screen(wheel_x, wheel_y * render_width_scale)
            wheel_radius = max(6, int(profile['wheel_radius_m'] * scale * 0.55))
            pygame.draw.circle(self.screen, wheel_color, wheel_pos, wheel_radius)
            pygame.draw.circle(self.screen, self.colors['panel_border'], wheel_pos, wheel_radius, 1)
            pygame.draw.line(self.screen, self.colors['panel_border'], (wheel_pos[0] - wheel_radius // 2, wheel_pos[1] - wheel_radius // 2), (wheel_pos[0] + wheel_radius // 2, wheel_pos[1] + wheel_radius // 2), 1)
            pygame.draw.line(self.screen, self.colors['panel_border'], (wheel_pos[0] - wheel_radius // 2, wheel_pos[1] + wheel_radius // 2), (wheel_pos[0] + wheel_radius // 2, wheel_pos[1] - wheel_radius // 2), 1)
            register_hitbox('wheel', pygame.Rect(wheel_pos[0] - wheel_radius, wheel_pos[1] - wheel_radius, wheel_radius * 2, wheel_radius * 2))
            if self.selected_part == 'wheel':
                pygame.draw.circle(self.screen, (244, 214, 72), wheel_pos, wheel_radius + 4, 2)

        if has_mount:
            mount_rect = pygame.Rect(0, 0, max(10, int(profile['gimbal_mount_length_m'] * scale)), max(10, int(profile['gimbal_mount_width_m'] * render_width_scale * scale)))
            mount_rect.center = world_to_screen(profile['gimbal_offset_x_m'], profile['gimbal_offset_y_m'])
            pygame.draw.rect(self.screen, (96, 100, 112), mount_rect, border_radius=6)
            pygame.draw.rect(self.screen, (18, 20, 24), mount_rect, 1, border_radius=6)
            register_hitbox('mount', mount_rect)
            if self.selected_part == 'mount':
                highlight_rect(mount_rect, radius=6)

        if has_turret:
            turret_rect = pygame.Rect(0, 0, max(12, int(profile['gimbal_length_m'] * scale)), max(12, int(profile['gimbal_width_m'] * render_width_scale * scale)))
            turret_rect.center = world_to_screen(profile['gimbal_offset_x_m'], profile['gimbal_offset_y_m'])
            pygame.draw.rect(self.screen, turret_color, turret_rect, border_radius=8)
            pygame.draw.rect(self.screen, (18, 20, 24), turret_rect, 2, border_radius=8)
            register_hitbox('turret', turret_rect)
            if self.selected_part == 'turret':
                highlight_rect(turret_rect, radius=8)
            if has_barrel:
                barrel_end = world_to_screen(profile['gimbal_offset_x_m'] + profile['gimbal_length_m'] * 0.5 + profile['barrel_length_m'], profile['gimbal_offset_y_m'])
                pygame.draw.line(self.screen, turret_color, turret_rect.center, barrel_end, max(4, int(profile['barrel_radius_m'] * scale * 6.0)))
                pygame.draw.line(self.screen, (18, 20, 24), turret_rect.center, barrel_end, 2)
                barrel_rect = pygame.Rect(min(turret_rect.centerx, barrel_end[0]), min(turret_rect.centery, barrel_end[1]) - 4, abs(barrel_end[0] - turret_rect.centerx), max(8, abs(barrel_end[1] - turret_rect.centery) + 8))
                register_hitbox('barrel', barrel_rect)
                if self.selected_part == 'barrel':
                    highlight_rect(barrel_rect, radius=6)
                barrel_light_width = max(3, int(profile['barrel_light_width_m'] * scale * 1.5))
                barrel_light_length = max(10, int(profile['barrel_light_length_m'] * scale))
                barrel_light_offset = max(5, int(profile['barrel_light_width_m'] * scale * 4.0))
                for direction in (-1, 1):
                    light_rect = pygame.Rect(0, 0, barrel_light_length, barrel_light_width)
                    light_rect.center = (int((turret_rect.centerx + barrel_end[0]) * 0.5), int((turret_rect.centery + barrel_end[1]) * 0.5 + direction * barrel_light_offset))
                    pygame.draw.rect(self.screen, team_light_color, light_rect, border_radius=4)
                    register_hitbox('barrel_light', light_rect)
                    if self.selected_part == 'barrel_light':
                        highlight_rect(light_rect, radius=4)

        armor_half_length = profile['body_length_m'] * 0.5 + profile['armor_plate_gap_m']
        armor_half_width = profile['body_width_m'] * render_width_scale * 0.5 + profile['armor_plate_gap_m']
        armor_w = max(8, int(profile['armor_plate_width_m'] * scale * 0.55))
        armor_l = max(8, int(profile['armor_plate_length_m'] * scale * 0.55))
        armor_specs = (
            (armor_half_length, 0.0, 8, armor_w),
            (-armor_half_length, 0.0, 8, armor_w),
            (0.0, armor_half_width, armor_l, 8),
            (0.0, -armor_half_width, armor_l, 8),
        )
        for offset_x, offset_y, width_px, height_px in armor_specs:
            armor_rect = pygame.Rect(0, 0, width_px, height_px)
            armor_rect.center = world_to_screen(offset_x, offset_y)
            pygame.draw.rect(self.screen, armor_color, armor_rect, border_radius=4)
            pygame.draw.rect(self.screen, (18, 20, 24), armor_rect, 1, border_radius=4)
            register_hitbox('armor', armor_rect)
            if self.selected_part == 'armor':
                highlight_rect(armor_rect, radius=4)
            light_length = max(8, int(profile['armor_light_length_m'] * scale))
            light_width = max(4, int(profile['armor_light_width_m'] * scale * 2.0))
            if width_px < height_px:
                light_a = pygame.Rect(armor_rect.centerx - light_width // 2, armor_rect.top - light_length, light_width, light_length)
                light_b = pygame.Rect(armor_rect.centerx - light_width // 2, armor_rect.bottom, light_width, light_length)
            else:
                light_a = pygame.Rect(armor_rect.left - light_length, armor_rect.centery - light_width // 2, light_length, light_width)
                light_b = pygame.Rect(armor_rect.right, armor_rect.centery - light_width // 2, light_length, light_width)
            for light_rect in (light_a, light_b):
                pygame.draw.rect(self.screen, team_light_color, light_rect, border_radius=4)
                register_hitbox('armor_light', light_rect)
                if self.selected_part == 'armor_light':
                    highlight_rect(light_rect, radius=4)

    def _draw_side_preview(self, rect, profile):
        pygame.draw.rect(self.screen, self.colors['preview_bg'], rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=12)
        self._draw_text('侧视预览', self.font, self.colors['text'], (rect.x + 14, rect.y + 12))
        ground_y = rect.bottom - 42
        pygame.draw.line(self.screen, self.colors['grid'], (rect.x + 20, ground_y), (rect.right - 20, ground_y), 2)
        scale = min((rect.width - 80) / max(profile['body_length_m'] + float(profile.get('barrel_length_m', 0.0)) + 0.35, 0.5), (rect.height - 100) / max(profile['gimbal_height_m'] + 0.4, 0.5))
        center_x = rect.centerx
        has_mount = self._profile_has_mount(profile)
        has_turret = self._profile_has_turret(profile)
        has_barrel = self._profile_has_barrel(profile)

        def register_hitbox(part, area_rect):
            self.preview_part_hitboxes.append((part, area_rect.inflate(8, 8)))

        wheel_radius = max(6, int(profile['wheel_radius_m'] * scale))
        body_width_px = max(40, int(profile['body_length_m'] * scale))
        body_height_px = max(20, int(profile['body_height_m'] * scale))
        clearance_px = max(4, int(profile['body_clearance_m'] * scale))
        wheel_positions = profile.get('custom_wheel_positions_m', [])
        wheel_centers = tuple((center_x + int(float(wheel_x) * scale), ground_y - wheel_radius) for wheel_x, _ in wheel_positions) or ((center_x, ground_y - wheel_radius),)
        for wheel_center in wheel_centers:
            pygame.draw.circle(self.screen, tuple(profile['wheel_color_rgb']), wheel_center, wheel_radius)
            pygame.draw.circle(self.screen, self.colors['panel_border'], wheel_center, wheel_radius, 1)
            pygame.draw.line(self.screen, self.colors['panel_border'], (wheel_center[0] - wheel_radius // 2, wheel_center[1] - wheel_radius // 2), (wheel_center[0] + wheel_radius // 2, wheel_center[1] + wheel_radius // 2), 1)
            pygame.draw.line(self.screen, self.colors['panel_border'], (wheel_center[0] - wheel_radius // 2, wheel_center[1] + wheel_radius // 2), (wheel_center[0] + wheel_radius // 2, wheel_center[1] - wheel_radius // 2), 1)
            register_hitbox('wheel', pygame.Rect(wheel_center[0] - wheel_radius, wheel_center[1] - wheel_radius, wheel_radius * 2, wheel_radius * 2))
            if self.selected_part == 'wheel':
                pygame.draw.circle(self.screen, (244, 214, 72), wheel_center, wheel_radius + 4, 2)
        body_rect = pygame.Rect(0, 0, body_width_px, body_height_px)
        body_rect.center = (center_x, ground_y - wheel_radius * 2 - clearance_px - body_height_px // 2 + 10)
        pygame.draw.rect(self.screen, tuple(profile['body_color_rgb']), body_rect, border_radius=10)
        pygame.draw.rect(self.screen, (18, 20, 24), body_rect, 2, border_radius=10)
        register_hitbox('body', body_rect)
        if self.selected_part == 'body':
            pygame.draw.rect(self.screen, (244, 214, 72), body_rect.inflate(6, 6), 3, border_radius=10)
        if has_mount:
            mount_rect = pygame.Rect(0, 0, max(12, int(profile['gimbal_mount_length_m'] * scale)), max(10, int(profile['gimbal_mount_height_m'] * scale)))
            mount_rect.center = (center_x + int(profile['gimbal_offset_x_m'] * scale), body_rect.top - mount_rect.height // 2 + 6)
            pygame.draw.rect(self.screen, (96, 100, 112), mount_rect, border_radius=5)
            pygame.draw.rect(self.screen, (18, 20, 24), mount_rect, 1, border_radius=5)
            register_hitbox('mount', mount_rect)
            if self.selected_part == 'mount':
                pygame.draw.rect(self.screen, (244, 214, 72), mount_rect.inflate(6, 6), 3, border_radius=6)
        if has_turret:
            turret_rect = pygame.Rect(0, 0, max(28, int(profile['gimbal_length_m'] * scale)), max(16, int(profile['gimbal_body_height_m'] * scale)))
            turret_center_y = ground_y - int(profile['gimbal_height_m'] * scale)
            turret_rect.center = (center_x + int(profile['gimbal_offset_x_m'] * scale), turret_center_y)
            pygame.draw.rect(self.screen, tuple(profile['turret_color_rgb']), turret_rect, border_radius=8)
            pygame.draw.rect(self.screen, (18, 20, 24), turret_rect, 2, border_radius=8)
            register_hitbox('turret', turret_rect)
            if self.selected_part == 'turret':
                pygame.draw.rect(self.screen, (244, 214, 72), turret_rect.inflate(6, 6), 3, border_radius=8)
            if has_barrel:
                barrel_end = (turret_rect.right + max(18, int(profile['barrel_length_m'] * scale)), turret_rect.centery)
                pygame.draw.line(self.screen, tuple(profile['turret_color_rgb']), turret_rect.center, barrel_end, max(3, int(profile['barrel_radius_m'] * scale * 2.8)))
                pygame.draw.line(self.screen, (18, 20, 24), turret_rect.center, barrel_end, 2)
                barrel_rect = pygame.Rect(min(turret_rect.centerx, barrel_end[0]), min(turret_rect.centery, barrel_end[1]) - 4, abs(barrel_end[0] - turret_rect.centerx), 8)
                register_hitbox('barrel', barrel_rect)
                if self.selected_part == 'barrel':
                    pygame.draw.rect(self.screen, (244, 214, 72), barrel_rect.inflate(6, 6), 3, border_radius=6)

    def _draw_preview_panel(self, rect):
        profile = self._current_profile()
        self.preview_part_hitboxes = []
        pygame.draw.rect(self.screen, self.colors['panel'], rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=12)
        self.preview_mode_tabs = self._preview_mode_rects(rect)
        for mode_key, label, tab_rect in self.preview_mode_tabs:
            active = mode_key == self.preview_mode
            pygame.draw.rect(self.screen, self.colors['accent'] if active else self.colors['panel_alt'], tab_rect, border_radius=8)
            pygame.draw.rect(self.screen, self.colors['panel_border'], tab_rect, 1, border_radius=8)
            text_color = (20, 22, 24) if active else self.colors['text']
            text_surface = self.small_font.render(label, True, text_color)
            self.screen.blit(text_surface, text_surface.get_rect(center=tab_rect.center))
        content_rect = pygame.Rect(rect.x + 12, rect.y + 52, rect.width - 24, rect.height - 64)
        self.preview_content_rect = content_rect
        if self.preview_mode == 'split':
            top_rect = pygame.Rect(content_rect.x, content_rect.y, content_rect.width, int(content_rect.height * 0.56))
            side_rect = pygame.Rect(content_rect.x, top_rect.bottom + 12, content_rect.width, content_rect.bottom - top_rect.bottom - 12)
            self._draw_top_preview(top_rect, profile)
            self._draw_side_preview(side_rect, profile)
            return
        if self.preview_mode == 'top':
            self._draw_top_preview(content_rect, profile)
            return
        if self.preview_mode == 'side':
            self._draw_side_preview(content_rect, profile)
            return
        preview_surface = self.preview_renderer_3d.render_scene(profile, content_rect.size, yaw=self.preview_3d_yaw, pitch=self.preview_3d_pitch) if self.preview_renderer_3d is not None else None
        pygame.draw.rect(self.screen, self.colors['preview_bg'], content_rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], content_rect, 1, border_radius=12)
        if preview_surface is not None:
            self.screen.blit(preview_surface, content_rect.topleft)
            self._build_3d_preview_hitboxes(content_rect, profile)
        else:
            title = '3D 预览不可用'
            detail = self.preview_renderer_3d.error if self.preview_renderer_3d is not None else MODERNGL_PREVIEW_ERROR
            self._draw_text(title, self.font, self.colors['text'], (content_rect.x + 18, content_rect.y + 18))
            if detail:
                self._draw_text(detail, self.small_font, self.colors['muted'], (content_rect.x + 18, content_rect.y + 52))
        hint = self.tiny_font.render('拖动鼠标可旋转 3D 预览', True, self.colors['muted'])
        self.screen.blit(hint, (content_rect.x + 14, content_rect.bottom - 24))

    def _draw_fields_panel(self, rect):
        pygame.draw.rect(self.screen, self.colors['panel'], rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=12)
        title = f'{PART_LABELS.get(self.selected_part, "可调参数")}参数' if self.selected_part is not None else '选择部件'
        self._draw_text(title, self.font, self.colors['text'], (rect.x + 14, rect.y + 12))
        content_rect = pygame.Rect(rect.x + 8, rect.y + 42, rect.width - 20, rect.height - 54)
        pygame.draw.rect(self.screen, self.colors['panel_alt'], content_rect, border_radius=8)
        if self.selected_part is None:
            hint_lines = [
                '右侧预览中点击部件后，这里才会出现对应的长宽高与颜色参数。',
                '当前可选：底盘、车轮、云台、枪管、连接件、装甲板、装甲灯条、枪管灯条。',
            ]
            for index, line in enumerate(hint_lines):
                self._draw_text(line, self.small_font, self.colors['muted'], (content_rect.x + 16, content_rect.y + 18 + index * 26))
            self.field_scrollbar_track_rect = None
            self.field_scrollbar_thumb_rect = None
            return
        old_clip = self.screen.get_clip()
        self.screen.set_clip(content_rect)
        rows, content_height = self._field_rows(rect, scroll_offset=self.field_scroll)
        self.field_scrollbar_track_rect = None
        self.field_scrollbar_thumb_rect = None
        for row_type, payload, row_rect, field_index in rows:
            if row_rect.bottom < content_rect.top or row_rect.top > content_rect.bottom:
                continue
            spec = payload
            active = field_index == self.selected_field_index
            pygame.draw.rect(self.screen, self.colors['panel_alt'] if active else (31, 36, 42), row_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['accent'] if active else self.colors['panel_border'], row_rect, 1, border_radius=6)
            value = self._field_value(spec)
            value_text = f'{value:.3f}' if spec['kind'] != 'color' else f'{int(value)}'
            self._draw_text(spec['label'], self.small_font, self.colors['text'], (row_rect.x + 10, row_rect.y + 5))
            value_surface = self.small_font.render(value_text, True, self.colors['muted'])
            self.screen.blit(value_surface, value_surface.get_rect(right=row_rect.right - 10, centery=row_rect.centery))
        self.screen.set_clip(old_clip)

        max_scroll = max(0, content_height - content_rect.height)
        if max_scroll > 0:
            track_rect = pygame.Rect(rect.right - 12, content_rect.y + 4, 6, content_rect.height - 8)
            thumb_height = max(34, int(track_rect.height * content_rect.height / max(content_height, 1)))
            thumb_y = track_rect.y + int((track_rect.height - thumb_height) * (self.field_scroll / max(max_scroll, 1)))
            thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
            pygame.draw.rect(self.screen, (58, 64, 74), track_rect, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['accent'], thumb_rect, border_radius=4)
            self.field_scrollbar_track_rect = track_rect
            self.field_scrollbar_thumb_rect = thumb_rect

    def _draw_header(self):
        self._draw_text('车辆外貌编辑器', self.title_font, self.colors['text'], (28, 22))
        self._draw_text('保存后的预设会在后续创建单位时自动应用', self.small_font, self.colors['muted'], (30, 52))
        for role_key, label, rect in self._role_tabs():
            active = role_key == self.current_role
            pygame.draw.rect(self.screen, self.colors['accent'] if active else self.colors['panel_alt'], rect, border_radius=8)
            pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=8)
            text_surface = self.font.render(label, True, (20, 22, 24) if active else self.colors['text'])
            self.screen.blit(text_surface, text_surface.get_rect(center=rect.center))

    def _draw_footer(self):
        footer_rect = pygame.Rect(24, self.window_height - 44, self.window_width - 48, 24)
        self._draw_text(self.status_text, self.small_font, self.colors['muted'], footer_rect.topleft)

    def _handle_click(self, pos):
        for mode_key, _, rect in self.preview_mode_tabs:
            if rect.collidepoint(pos):
                self.preview_mode = mode_key
                return
        for role_key, _, rect in self._role_tabs():
            if rect.collidepoint(pos):
                self.current_role = role_key
                return
        field_panel, _ = self._layout_panels()
        if self.field_scrollbar_thumb_rect is not None and self.field_scrollbar_thumb_rect.collidepoint(pos):
            self.field_scroll_drag_active = True
            return
        if self.field_scrollbar_track_rect is not None and self.field_scrollbar_track_rect.collidepoint(pos):
            thumb_height = self.field_scrollbar_thumb_rect.height if self.field_scrollbar_thumb_rect is not None else 0
            relative = pos[1] - self.field_scrollbar_track_rect.y - thumb_height * 0.5
            ratio = relative / max(1, self.field_scrollbar_track_rect.height - thumb_height)
            self._set_field_scroll(field_panel, ratio * self._max_field_scroll(field_panel))
            return
        for part, hitbox in reversed(self.preview_part_hitboxes):
            if hitbox.collidepoint(pos):
                self.selected_part = part
                self.selected_field_index = 0
                self.field_scroll = 0
                return
        if self.preview_content_rect is not None and self.preview_content_rect.collidepoint(pos) and self.preview_mode != '3d':
            self.selected_part = None
            return
        rows, _ = self._field_rows(field_panel, scroll_offset=self.field_scroll)
        for row_type, _, row_rect, field_index in rows:
            if row_type == 'field' and row_rect.collidepoint(pos):
                self.selected_field_index = field_index
                self._ensure_selected_field_visible(field_panel)
                return
    def _reset_current_role(self):
        self.profiles[self.current_role] = _default_profile(self.current_role)
        self.selected_part = None
        self.status_text = f'已重置 {dict(ROLE_ORDER)[self.current_role]} 默认外观'

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.VIDEORESIZE:
            self.window_width = max(1200, int(event.w))
            self.window_height = max(760, int(event.h))
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), pygame.RESIZABLE)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            if self.preview_mode == '3d' and self.preview_content_rect is not None and self.preview_content_rect.collidepoint(event.pos):
                self.preview_drag_active = True
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button in {1, 3}:
            self.field_scroll_drag_active = False
            self.preview_drag_active = False
            return
        if event.type == pygame.MOUSEMOTION:
            if self.field_scroll_drag_active and self.field_panel_rect is not None and self.field_scrollbar_track_rect is not None and self.field_scrollbar_thumb_rect is not None:
                thumb_height = self.field_scrollbar_thumb_rect.height
                relative = event.pos[1] - self.field_scrollbar_track_rect.y - thumb_height * 0.5
                ratio = relative / max(1, self.field_scrollbar_track_rect.height - thumb_height)
                self._set_field_scroll(self.field_panel_rect, ratio * self._max_field_scroll(self.field_panel_rect))
                return
            if self.preview_drag_active and self.preview_mode == '3d':
                rel_x, rel_y = getattr(event, 'rel', (0, 0))
                self.preview_3d_yaw += rel_x * 0.012
                self.preview_3d_pitch = max(0.12, min(1.12, self.preview_3d_pitch - rel_y * 0.010))
                return
        if event.type == pygame.MOUSEWHEEL:
            if self.field_panel_rect is not None and self.field_panel_rect.collidepoint(pygame.mouse.get_pos()):
                self._set_field_scroll(self.field_panel_rect, self.field_scroll - event.y * 36)
                return
            if self.preview_mode == '3d' and self.preview_content_rect is not None and self.preview_content_rect.collidepoint(pygame.mouse.get_pos()):
                self.preview_3d_pitch = max(0.12, min(1.12, self.preview_3d_pitch + event.y * 0.04))
                return
            self._adjust_selected(event.y, fast=bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
            return
        if event.type != pygame.KEYDOWN:
            return
        modifiers = pygame.key.get_mods()
        if event.key == pygame.K_ESCAPE:
            self.running = False
            return
        if event.key == pygame.K_TAB:
            role_keys = [role_key for role_key, _ in ROLE_ORDER]
            current_index = role_keys.index(self.current_role)
            self.current_role = role_keys[(current_index + 1) % len(role_keys)]
            self.selected_part = None
            self.selected_field_index = 0
            return
        if event.key == pygame.K_r:
            self._reset_current_role()
            return
        if event.key == pygame.K_s and modifiers & pygame.KMOD_CTRL:
            self._save_profiles()
            return
        if event.key == pygame.K_UP:
            visible_fields = self._visible_field_specs()
            if not visible_fields:
                return
            self.selected_field_index = max(0, self.selected_field_index - 1)
            if self.field_panel_rect is not None:
                self._ensure_selected_field_visible(self.field_panel_rect)
            return
        if event.key == pygame.K_DOWN:
            visible_fields = self._visible_field_specs()
            if not visible_fields:
                return
            self.selected_field_index = min(len(visible_fields) - 1, self.selected_field_index + 1)
            if self.field_panel_rect is not None:
                self._ensure_selected_field_visible(self.field_panel_rect)
            return
        if event.key in {pygame.K_LEFT, pygame.K_MINUS, pygame.K_KP_MINUS}:
            self._adjust_selected(-1, fast=bool(modifiers & pygame.KMOD_SHIFT))
            return
        if event.key in {pygame.K_RIGHT, pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS}:
            self._adjust_selected(1, fast=bool(modifiers & pygame.KMOD_SHIFT))
            return
        if event.key in {pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4}:
            role_index = int(event.unicode) - 1 if event.unicode in {'1', '2', '3', '4'} else None
            if role_index is not None and 0 <= role_index < len(ROLE_ORDER):
                self.current_role = ROLE_ORDER[role_index][0]

    def render(self):
        self.screen.fill(self.colors['bg'])
        self._draw_header()
        field_panel, preview_panel = self._layout_panels()
        self._draw_fields_panel(field_panel)
        self._draw_preview_panel(preview_panel)
        self._draw_footer()
        pygame.display.flip()

    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
            self.render()
            self.clock.tick(60)
        pygame.quit()


def main():
    app = AppearanceEditorApp()
    app.run()


if __name__ == '__main__':
    main()