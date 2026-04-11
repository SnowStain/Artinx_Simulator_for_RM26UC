#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import os

import numpy as np

from pygame_compat import pygame

from rendering.renderer_detail_popup_mixin import RendererDetailPopupMixin
from rendering.renderer_hud_mixin import RendererHudMixin
from rendering.renderer_sidebar_mixin import RendererSidebarMixin
from rendering.terrain_scene_backends import _sample_terrain_scene_data, _terrain_scene_look_at, _terrain_scene_perspective_matrix
from rendering.terrain_overview_mixin import TerrainOverviewMixin


class Renderer(TerrainOverviewMixin, RendererSidebarMixin, RendererHudMixin, RendererDetailPopupMixin):
    def __init__(self, game_engine, config):
        self.game_engine = game_engine
        self.config = config

        if bool(config.get('simulator', {}).get('gpu_preferred', True)):
            os.environ.setdefault('SDL_RENDER_BATCHING', '1')
            os.environ.setdefault('SDL_HINT_RENDER_BATCHING', '1')
            if os.name == 'nt':
                os.environ.setdefault('SDL_RENDER_DRIVER', 'direct3d11')

        pygame.init()

        desktop_sizes = []
        if hasattr(pygame.display, 'get_desktop_sizes'):
            try:
                desktop_sizes = list(pygame.display.get_desktop_sizes())
            except Exception:
                desktop_sizes = []
        desktop_width, desktop_height = desktop_sizes[0] if desktop_sizes else (1920, 1080)
        configured_width = int(config.get('simulator', {}).get('window_width', 1560))
        configured_height = int(config.get('simulator', {}).get('window_height', 920))
        self.window_width = max(1200, min(configured_width, max(1200, desktop_width - 96)))
        self.window_height = max(760, min(configured_height, max(760, desktop_height - 96)))
        display_flags = pygame.DOUBLEBUF | pygame.RESIZABLE
        if hasattr(pygame, 'HWSURFACE'):
            display_flags |= pygame.HWSURFACE
        try:
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), display_flags, vsync=1)
        except TypeError:
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), display_flags)
        pygame.display.set_caption('RM26 ARTINX-Asoul模拟器')

        self.toolbar_height = 54
        self.hud_height = 118
        self.panel_width = 270
        self.decision_panel_width = 320
        self.content_padding = 12
        self.edit_mode = 'none'
        self.facility_options = [
            {'id': 'wall', 'type': 'wall', 'team': 'neutral', 'label': '中立墙体'},
            {'id': 'dead_zone', 'type': 'dead_zone', 'team': 'neutral', 'label': '死区'},
            {'id': 'red_base', 'type': 'base', 'team': 'red', 'label': '红方基地'},
            {'id': 'red_outpost', 'type': 'outpost', 'team': 'red', 'label': '红方前哨站'},
            {'id': 'red_dog_hole', 'type': 'dog_hole', 'team': 'red', 'label': '红方狗洞'},
            {'id': 'red_undulating_road', 'type': 'undulating_road', 'team': 'red', 'label': '红方起伏路'},
            {'id': 'red_fly_slope', 'type': 'fly_slope', 'team': 'red', 'label': '红方飞坡'},
            {'id': 'red_first_step', 'type': 'first_step', 'team': 'red', 'label': '红方一级台阶'},
            {'id': 'red_second_step', 'type': 'second_step', 'team': 'red', 'label': '红方二级台阶'},
            {'id': 'red_supply', 'type': 'supply', 'team': 'red', 'label': '红方补给区'},
            {'id': 'red_fort', 'type': 'fort', 'team': 'red', 'label': '红方堡垒'},
            {'id': 'blue_base', 'type': 'base', 'team': 'blue', 'label': '蓝方基地'},
            {'id': 'blue_outpost', 'type': 'outpost', 'team': 'blue', 'label': '蓝方前哨站'},
            {'id': 'blue_dog_hole', 'type': 'dog_hole', 'team': 'blue', 'label': '蓝方狗洞'},
            {'id': 'blue_undulating_road', 'type': 'undulating_road', 'team': 'blue', 'label': '蓝方起伏路'},
            {'id': 'blue_fly_slope', 'type': 'fly_slope', 'team': 'blue', 'label': '蓝方飞坡'},
            {'id': 'blue_first_step', 'type': 'first_step', 'team': 'blue', 'label': '蓝方一级台阶'},
            {'id': 'blue_second_step', 'type': 'second_step', 'team': 'blue', 'label': '蓝方二级台阶'},
            {'id': 'blue_supply', 'type': 'supply', 'team': 'blue', 'label': '蓝方补给区'},
            {'id': 'blue_fort', 'type': 'fort', 'team': 'blue', 'label': '蓝方堡垒'},
            {'id': 'red_mining_area', 'type': 'mining_area', 'team': 'red', 'label': '红方取矿区'},
            {'id': 'blue_mining_area', 'type': 'mining_area', 'team': 'blue', 'label': '蓝方取矿区'},
            {'id': 'red_mineral_exchange', 'type': 'mineral_exchange', 'team': 'red', 'label': '红方兑矿区'},
            {'id': 'blue_mineral_exchange', 'type': 'mineral_exchange', 'team': 'blue', 'label': '蓝方兑矿区'},
            {'id': 'center_energy_mechanism', 'type': 'energy_mechanism', 'team': 'neutral', 'label': '中央能量机关'},
            {'id': 'red_rugged_road', 'type': 'rugged_road', 'team': 'red', 'label': '红方起伏路段'},
            {'id': 'blue_rugged_road', 'type': 'rugged_road', 'team': 'blue', 'label': '蓝方起伏路段'},
        ]
        self.buff_options = [
            {'id': 'buff_base_red', 'type': 'buff_base', 'team': 'red', 'label': '红方基地增益点'},
            {'id': 'buff_base_blue', 'type': 'buff_base', 'team': 'blue', 'label': '蓝方基地增益点'},
            {'id': 'buff_outpost_red', 'type': 'buff_outpost', 'team': 'red', 'label': '红方前哨站增益点'},
            {'id': 'buff_outpost_blue', 'type': 'buff_outpost', 'team': 'blue', 'label': '蓝方前哨站增益点'},
            {'id': 'buff_fort_red', 'type': 'buff_fort', 'team': 'red', 'label': '红方堡垒增益点'},
            {'id': 'buff_fort_blue', 'type': 'buff_fort', 'team': 'blue', 'label': '蓝方堡垒增益点'},
            {'id': 'buff_supply_red', 'type': 'buff_supply', 'team': 'red', 'label': '红方补给区增益点'},
            {'id': 'buff_supply_blue', 'type': 'buff_supply', 'team': 'blue', 'label': '蓝方补给区增益点'},
            {'id': 'center_exchange_red', 'type': 'mineral_exchange', 'team': 'red', 'label': '红方中心兑矿区'},
            {'id': 'center_exchange_blue', 'type': 'mineral_exchange', 'team': 'blue', 'label': '蓝方中心兑矿区'},
            {'id': 'buff_hero_deployment_red', 'type': 'buff_hero_deployment', 'team': 'red', 'label': '红方英雄部署区'},
            {'id': 'buff_hero_deployment_blue', 'type': 'buff_hero_deployment', 'team': 'blue', 'label': '蓝方英雄部署区'},
            {'id': 'buff_central_highland', 'type': 'buff_central_highland', 'team': 'neutral', 'label': '中央高地增益点'},
            {'id': 'buff_trapezoid_highland_red', 'type': 'buff_trapezoid_highland', 'team': 'red', 'label': '红方梯形高地增益点'},
            {'id': 'buff_trapezoid_highland_blue', 'type': 'buff_trapezoid_highland', 'team': 'blue', 'label': '蓝方梯形高地增益点'},
            {'id': 'buff_terrain_highland_red_start', 'type': 'buff_terrain_highland_red_start', 'team': 'red', 'label': '红方高地跨越起始段'},
            {'id': 'buff_terrain_highland_red_end', 'type': 'buff_terrain_highland_red_end', 'team': 'red', 'label': '红方高地跨越结束段'},
            {'id': 'buff_terrain_highland_blue_start', 'type': 'buff_terrain_highland_blue_start', 'team': 'blue', 'label': '蓝方高地跨越起始段'},
            {'id': 'buff_terrain_highland_blue_end', 'type': 'buff_terrain_highland_blue_end', 'team': 'blue', 'label': '蓝方高地跨越结束段'},
            {'id': 'buff_terrain_road_red_start', 'type': 'buff_terrain_road_red_start', 'team': 'red', 'label': '红方公路跨越起始段'},
            {'id': 'buff_terrain_road_red_end', 'type': 'buff_terrain_road_red_end', 'team': 'red', 'label': '红方公路跨越结束段'},
            {'id': 'buff_terrain_road_blue_start', 'type': 'buff_terrain_road_blue_start', 'team': 'blue', 'label': '蓝方公路跨越起始段'},
            {'id': 'buff_terrain_road_blue_end', 'type': 'buff_terrain_road_blue_end', 'team': 'blue', 'label': '蓝方公路跨越结束段'},
            {'id': 'buff_terrain_fly_slope_red_start', 'type': 'buff_terrain_fly_slope_red_start', 'team': 'red', 'label': '红方飞坡跨越起始段'},
            {'id': 'buff_terrain_fly_slope_red_end', 'type': 'buff_terrain_fly_slope_red_end', 'team': 'red', 'label': '红方飞坡跨越结束段'},
            {'id': 'buff_terrain_fly_slope_blue_start', 'type': 'buff_terrain_fly_slope_blue_start', 'team': 'blue', 'label': '蓝方飞坡跨越起始段'},
            {'id': 'buff_terrain_fly_slope_blue_end', 'type': 'buff_terrain_fly_slope_blue_end', 'team': 'blue', 'label': '蓝方飞坡跨越结束段'},
            {'id': 'buff_terrain_slope_red_start', 'type': 'buff_terrain_slope_red_start', 'team': 'red', 'label': '红方陡道跨越起始段'},
            {'id': 'buff_terrain_slope_red_end', 'type': 'buff_terrain_slope_red_end', 'team': 'red', 'label': '红方陡道跨越结束段'},
            {'id': 'buff_terrain_slope_blue_start', 'type': 'buff_terrain_slope_blue_start', 'team': 'blue', 'label': '蓝方陡道跨越起始段'},
            {'id': 'buff_terrain_slope_blue_end', 'type': 'buff_terrain_slope_blue_end', 'team': 'blue', 'label': '蓝方陡道跨越结束段'},
        ]
        self.terrain_brush = {
            'type': 'custom_terrain',
            'label': '统一地形刷',
            'team': 'neutral',
            'height_m': 0.0,
            'blocks_movement': False,
            'blocks_vision': False,
        }
        self.region_palette = 'facility'
        self.region_option_indices = {'facility': 0, 'buff': 0}
        self.selected_facility_type = 0
        self.entity_keys = self._build_entity_keys()
        self.selected_entity_index = 0
        self.selected_rule_index = 0
        self.facility_scroll = 0
        self.wall_scroll = 0
        self.terrain_scroll = 0
        self.rule_scroll = 0
        self.selected_wall_id = None
        self.selected_terrain_id = None
        self.terrain_preview_rect = None
        self.drag_start = None
        self.drag_current = None
        self.polygon_points = []
        self.slope_region_points = []
        self.slope_direction_start = None
        self.slope_direction_end = None
        self.terrain_painting = False
        self.terrain_erasing = False
        self.terrain_edit_batch_active = False
        self.terrain_paint_dirty = False
        self.terrain_brush_radius = 1
        self.last_terrain_paint_grid_key = None
        self.terrain_editor_tool = 'terrain'
        self.terrain_workflow_mode = 'brush'
        self.selected_terrain_cell_key = None
        self.selected_terrain_cell_keys = set()
        self.terrain_pan_active = False
        self.terrain_pan_origin = None
        self.terrain_view_offset = [0, 0]
        self.terrain_scene_zoom = 1.0
        self.terrain_scene_focus_world = None
        self.terrain_overlay_alpha = int(max(0, min(255, config.get('simulator', {}).get('terrain_overlay_alpha', 128))))
        self.terrain_smooth_strength = int(max(0, min(3, config.get('simulator', {}).get('terrain_smooth_strength', 0))))
        self.dragged_entity_id = None
        self.single_unit_decision_scroll = 0
        self.single_unit_decision_list_rect = None
        self.wall_panel_rect = None
        self.terrain_panel_rect = None
        self.overview_side_panel_rect = None
        self.overview_side_scroll = 0
        self.overview_side_scroll_max = 0
        self.active_numeric_input = None
        self.mouse_world = None
        self.viewport = None
        self.toolbar_actions = []
        self.hud_actions = []
        self.panel_actions = []
        self.facility_draw_shape = 'rect'
        self.map_cache_size = None
        self.map_cache_surface = None
        self.map_cache_key = None
        self.facility_overlay_surface = None
        self.facility_overlay_cache_key = None
        self.facility_overlay_size = None
        self.facility_overlay_world_surface = None
        self.facility_overlay_world_key = None
        self.terrain_grid_overlay_world_surface = None
        self.terrain_grid_overlay_world_key = None
        self.terrain_brush_overlay_surface = None
        self.terrain_brush_overlay_size = None
        self.aim_fov_overlay_surface = None
        self.aim_fov_overlay_size = None
        self.aim_fov_overlay_cache_key = None
        self.projectile_overlay_surface = None
        self.projectile_overlay_size = None
        self.ai_navigation_overlay_surface = None
        self.ai_navigation_overlay_size = None
        self.ai_navigation_overlay_cache_key = None
        self.terrain_3d_window = None
        self.terrain_3d_renderer = None
        self.terrain_3d_texture = None
        self.terrain_overview_window_open = False
        self.terrain_3d_window_size = (1200, 820)
        self.terrain_3d_render_key = None
        self.player_terrain_surface_cache = None
        self.player_terrain_surface_key = None
        self.terrain_3d_last_build_ms = 0
        self.terrain_scene_backend_requested = config.get('simulator', {}).get('terrain_scene_backend', 'auto')
        self.terrain_scene_backend = None
        self.terrain_3d_map_rgb_cache_key = None
        self.terrain_3d_map_rgb_cache = None
        self.terrain_scene_vertical_exaggeration = 1.0
        self.terrain_scene_ground_height_scale = 1.0
        self.terrain_scene_max_cells = int(max(12000, config.get('simulator', {}).get('terrain_scene_max_cells', 64000)))
        self.player_terrain_scene_max_cells = int(max(6000, config.get('simulator', {}).get('player_terrain_scene_max_cells', 12000)))
        self.terrain_scene_force_dark_gray = False
        self.player_control_terrain_dark_gray = bool(config.get('simulator', {}).get('player_control_terrain_dark_gray', True))
        self.player_camera_mode = str(config.get('simulator', {}).get('player_camera_mode', 'first_person') or 'first_person')
        if self.player_camera_mode not in {'first_person', 'third_person'}:
            self.player_camera_mode = 'first_person'
        self.player_third_person_distance_m = float(config.get('simulator', {}).get('player_third_person_distance_m', 1.85))
        self.player_third_person_height_m = float(config.get('simulator', {}).get('player_third_person_height_m', 0.58))
        self.player_view_ray_alpha = int(max(32, min(255, config.get('simulator', {}).get('player_view_ray_alpha', 176))))
        self.player_terrain_render_scale = float(max(0.35, min(1.0, config.get('simulator', {}).get('player_terrain_render_scale', 0.52))))
        self.player_motion_terrain_render_scale = float(max(0.35, min(self.player_terrain_render_scale, config.get('simulator', {}).get('player_motion_terrain_render_scale', 0.36))))
        self.player_camera_motion_threshold_m = float(max(0.005, config.get('simulator', {}).get('player_camera_motion_threshold_m', 0.035)))
        self._active_player_terrain_render_scale = self.player_terrain_render_scale
        self._last_player_camera_sample = None
        self.terrain_scene_prewarm_thread = None
        self.terrain_scene_prewarm_key = None
        self.terrain_scene_prewarm_ready_key = None
        self.terrain_scene_prewarm_error = None
        self.terrain_overview_ui = {'window_id': None, 'buttons': [], 'map_rect': None}
        self.terrain_overview_mouse_pos = None
        self.terrain_overview_viewport_drag_active = False
        self.terrain_3d_orbit_active = False
        self.terrain_3d_orbit_dragged = False
        self.terrain_3d_orbit_last_pos = None
        self.terrain_3d_navigation_last_ms = pygame.time.get_ticks()
        self.terrain_3d_camera_yaw = math.radians(45.0)
        self.terrain_3d_camera_pitch = 0.58
        self.terrain_3d_camera_focus_height = 0.0
        self.terrain_view_mode = '3d'
        self.terrain_shape_mode = 'circle'
        self.terrain_scene_sample_cache_key = None
        self.terrain_scene_sample_cache = None
        self.terrain_scene_color_lut = None
        self.selected_hud_entity_id = None
        self.robot_detail_page = 0
        self.robot_detail_rect = None
        self.show_facilities = config.get('simulator', {}).get('show_facilities', False)
        self.show_aim_fov = config.get('simulator', {}).get('show_aim_fov', False)
        self.show_entities = config.get('simulator', {}).get('show_entities', True)
        self.debug_panel_expanded = {
            'controller': True,
            'state_machine': False,
        }
        self.render_interval = max(1, int(config.get('simulator', {}).get('render_interval', 1)))
        self.overlay_status_refresh_ms = int(max(33, config.get('simulator', {}).get('overlay_status_refresh_ms', 120)))
        self.overlay_status_box_surface = None
        self.overlay_status_box_key = None
        self.overlay_status_log_surface = None
        self.overlay_status_log_key = None
        self.player_purchase_menu_open = False
        self.player_purchase_amount = 50
        self.player_settings_menu_open = False
        self.pre_match_config_menu_open = False
        self.player_mouse_captured = False
        self.terrain_scene_camera_override = None
        self.standalone_3d_program = bool(config.get('simulator', {}).get('standalone_3d_program', False))
        self.standalone_3d_state = 'main_menu' if self.standalone_3d_program else None
        self.standalone_3d_selected_team = 'red'
        self.standalone_3d_selected_entity_id = config.get('simulator', {}).get('standalone_3d_selected_entity_id', 'red_robot_1')
        self.standalone_3d_ricochet_enabled = bool(config.get('simulator', {}).get('player_projectile_ricochet_enabled', True))

        self.colors = {
            'bg': (231, 233, 237),
            'toolbar': (25, 30, 38),
            'toolbar_text': (245, 247, 250),
            'toolbar_button': (59, 67, 80),
            'toolbar_button_active': (208, 82, 44),
            'hud_bg': (32, 37, 45),
            'hud_panel': (48, 54, 64),
            'hud_center': (65, 76, 84),
            'hud_gold': (218, 182, 81),
            'panel': (247, 248, 250),
            'panel_border': (207, 212, 219),
            'panel_row': (234, 238, 243),
            'panel_row_active': (217, 232, 247),
            'panel_text': (34, 40, 49),
            'red': (214, 63, 63),
            'blue': (53, 112, 214),
            'green': (76, 164, 104),
            'yellow': (231, 180, 58),
            'white': (255, 255, 255),
            'black': (17, 17, 17),
            'gray': (128, 128, 128),
            'selection': (255, 255, 255),
            'overlay_bg': (18, 24, 30, 96),
            'overlay_log_bg': (18, 24, 30, 84),
        }

        self.font = self._create_font(22)
        self.small_font = self._create_font(16)
        self.tiny_font = self._create_font(13)
        self.hud_big_font = self._create_font(28)
        self.hud_mid_font = self._create_font(18)

        self.entity_radius = {
            'robot': 10,
            'uav': 8,
            'sentry': 12,
            'outpost': 20,
            'base': 30,
            'dart': 5,
            'radar': 15,
        }

    def _handle_window_resize(self, width, height):
        self.window_width = max(1200, int(width))
        self.window_height = max(760, int(height))
        display_flags = pygame.DOUBLEBUF | pygame.RESIZABLE
        if hasattr(pygame, 'HWSURFACE'):
            display_flags |= pygame.HWSURFACE
        try:
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), display_flags, vsync=1)
        except TypeError:
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), display_flags)
        self.map_cache_surface = None
        self.map_cache_size = None
        self.facility_overlay_surface = None
        self.facility_overlay_cache_key = None
        self.projectile_overlay_surface = None
        self.projectile_overlay_size = None
        self.ai_navigation_overlay_surface = None
        self.ai_navigation_overlay_size = None
        self.ai_navigation_overlay_cache_key = None
        self.aim_fov_overlay_surface = None
        self.aim_fov_overlay_size = None
        self.aim_fov_overlay_cache_key = None
        self.terrain_brush_overlay_surface = None
        self.terrain_brush_overlay_size = None
        self.terrain_3d_texture = None
        self.terrain_3d_render_key = None
        self.player_terrain_surface_cache = None
        self.player_terrain_surface_key = None

    def _create_font(self, size):
        candidates = [
            'Microsoft YaHei UI',
            'Microsoft YaHei',
            'SimHei',
            'Noto Sans CJK SC',
            'Source Han Sans SC',
            'PingFang SC',
            'WenQuanYi Zen Hei',
        ]
        for name in candidates:
            font_path = pygame.font.match_font(name)
            if font_path:
                return pygame.font.Font(font_path, size)
        return pygame.font.SysFont('arial', size)

    def _build_entity_keys(self):
        allowed = ['robot_1', 'robot_2', 'robot_3', 'robot_4', 'robot_7']
        keys = []
        for team in ['red', 'blue']:
            positions = self.config.get('entities', {}).get('initial_positions', {}).get(team, {})
            for key in allowed:
                if key in positions:
                    keys.append((team, key))
        return keys

    def _region_options(self):
        return self.facility_options if self.region_palette == 'facility' else self.buff_options

    def _selected_region_index(self):
        options = self._region_options()
        if not options:
            return 0
        current = int(self.region_option_indices.get(self.region_palette, 0))
        current = max(0, min(current, len(options) - 1))
        self.region_option_indices[self.region_palette] = current
        self.selected_facility_type = current
        return current

    def _selected_region_option(self):
        options = self._region_options()
        if not options:
            return None
        return options[self._selected_region_index()]

    def _set_selected_region_index(self, index):
        options = self._region_options()
        if not options:
            self.region_option_indices[self.region_palette] = 0
            self.selected_facility_type = 0
            return
        clamped = max(0, min(int(index), len(options) - 1))
        self.region_option_indices[self.region_palette] = clamped
        self.selected_facility_type = clamped

    def _shift_selected_region(self, delta):
        options = self._region_options()
        if not options:
            return
        self._set_selected_region_index((self._selected_region_index() + int(delta)) % len(options))

    def _set_region_palette(self, palette):
        self.region_palette = 'buff' if palette == 'buff' else 'facility'
        self._set_selected_region_index(self.region_option_indices.get(self.region_palette, 0))

    def _selected_terrain_brush_def(self):
        return self.terrain_brush

    def _refresh_editor_state(self, game_engine):
        self.entity_keys = self._build_entity_keys()
        if self.entity_keys:
            self.selected_entity_index = max(0, min(self.selected_entity_index, len(self.entity_keys) - 1))
        else:
            self.selected_entity_index = 0

        numeric_rules = self._flatten_numeric_rules(game_engine.config.get('rules', {}))
        if numeric_rules:
            self.selected_rule_index = max(0, min(self.selected_rule_index, len(numeric_rules) - 1))
            self.rule_scroll = max(0, min(self.rule_scroll, len(numeric_rules) - 1))
        else:
            self.selected_rule_index = 0
            self.rule_scroll = 0

    def render(self, game_engine):
        if self.render_interval > 1 and (game_engine._frame_index % self.render_interval) != 0:
            return
        self._refresh_editor_state(game_engine)
        self.screen.fill(self.colors['bg'])
        self.toolbar_actions = []
        self.hud_actions = []
        self.panel_actions = []

        if self.standalone_3d_program:
            if self.standalone_3d_state != 'in_match':
                self._sync_player_mouse_capture(False)
                self._render_standalone_program(game_engine)
                pygame.display.flip()
                return
            self.render_player_simulator(game_engine, top_offset=0, hud_top=0, draw_match_hud=True)
            pygame.display.flip()
            return

        self._update_viewport(game_engine.map_manager)
        self.render_toolbar(game_engine)
        if game_engine.player_control_enabled and game_engine.get_player_controlled_entity() is not None:
            self.render_player_simulator(game_engine, draw_match_hud=True)
            self.render_perf_overlay(game_engine)
            pygame.display.flip()
            return
        self._sync_player_mouse_capture(False)
        self.render_match_hud(game_engine)
        previous_clip = self.screen.get_clip()
        map_clip_rect = self._visible_map_clip_rect()
        if map_clip_rect.width > 0 and map_clip_rect.height > 0:
            self.screen.set_clip(map_clip_rect)
        self.render_map(game_engine.map_manager)
        self.render_aim_fov(game_engine)
        if self.show_entities:
            self.render_entities(game_engine.entity_manager.entities)
        if self._collision_overlay_active():
            self.render_collision_boxes(game_engine.entity_manager.entities)
        self.screen.set_clip(previous_clip)
        self.render_region_hover_hint(game_engine.map_manager)
        self.render_overlay_status(game_engine)
        self.render_sidebar(game_engine)
        self.render_robot_detail_popup(game_engine)
        self.render_perf_overlay(game_engine)
        self.render_terrain_3d_window(game_engine)
        pygame.display.flip()

    def _standalone_control_candidate_ids(self):
        return ('red_robot_1', 'red_robot_3', 'red_robot_4', 'blue_robot_1', 'blue_robot_3', 'blue_robot_4')

    def _standalone_control_candidates(self, game_engine, team=None):
        entity_map = {entity.id: entity for entity in getattr(game_engine.entity_manager, 'entities', [])}
        candidates = []
        for entity_id in self._standalone_control_candidate_ids():
            entity = entity_map.get(entity_id)
            if entity is None or not entity.is_alive():
                continue
            if team is not None and entity.team != team:
                continue
            candidates.append(entity)
        return candidates

    def _ensure_standalone_selection(self, game_engine):
        candidates = self._standalone_control_candidates(game_engine, self.standalone_3d_selected_team)
        if candidates and self.standalone_3d_selected_entity_id not in {entity.id for entity in candidates}:
            self.standalone_3d_selected_entity_id = candidates[0].id
        elif not candidates:
            all_candidates = self._standalone_control_candidates(game_engine)
            self.standalone_3d_selected_entity_id = all_candidates[0].id if all_candidates else None

    def _render_standalone_program(self, game_engine):
        self._ensure_standalone_selection(game_engine)
        background = pygame.Surface((self.window_width, self.window_height))
        background.fill((12, 16, 22))
        pygame.draw.circle(background, (26, 36, 48), (self.window_width // 2, self.window_height // 3), int(self.window_width * 0.33))
        pygame.draw.circle(background, (18, 24, 32), (self.window_width // 4, self.window_height // 2), int(self.window_width * 0.18))
        pygame.draw.circle(background, (18, 28, 38), (self.window_width * 3 // 4, self.window_height // 2), int(self.window_width * 0.22))
        self.screen.blit(background, (0, 0))
        if self.standalone_3d_state == 'main_menu':
            self._render_standalone_main_menu(game_engine)
        else:
            self._render_standalone_prematch_menu(game_engine)

    def _render_standalone_main_menu(self, game_engine):
        title = self.hud_big_font.render('3D 对局模拟器', True, self.colors['white'])
        subtitle = self.small_font.render('独立程序模式', True, (198, 204, 212))
        self.screen.blit(title, title.get_rect(center=(self.window_width // 2, 154)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.window_width // 2, 190)))

        panel_rect = pygame.Rect(0, 0, 420, 250)
        panel_rect.center = (self.window_width // 2, self.window_height // 2 + 40)
        pygame.draw.rect(self.screen, (28, 34, 42), panel_rect, border_radius=24)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=24)

        lines = [
            '开始对局后，可在赛前选择可控机器人。',
            '当前支持红/蓝 1、3、4 进入手控第一视角。',
        ]
        draw_y = panel_rect.y + 42
        for line in lines:
            rendered = self.small_font.render(line, True, (220, 225, 232))
            self.screen.blit(rendered, rendered.get_rect(center=(panel_rect.centerx, draw_y)))
            draw_y += 30

        start_rect = pygame.Rect(panel_rect.x + 60, panel_rect.bottom - 136, panel_rect.width - 120, 42)
        settings_rect = pygame.Rect(panel_rect.x + 60, panel_rect.bottom - 86, panel_rect.width - 120, 34)
        exit_rect = pygame.Rect(panel_rect.x + 60, panel_rect.bottom - 44, panel_rect.width - 120, 34)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], start_rect, border_radius=12)
        pygame.draw.rect(self.screen, (86, 96, 108), settings_rect, border_radius=10)
        pygame.draw.rect(self.screen, (64, 72, 84), exit_rect, border_radius=10)
        self.screen.blit(self.small_font.render('开始对局', True, self.colors['white']), self.small_font.render('开始对局', True, self.colors['white']).get_rect(center=start_rect.center))
        self.screen.blit(self.small_font.render('设置', True, self.colors['white']), self.small_font.render('设置', True, self.colors['white']).get_rect(center=settings_rect.center))
        self.screen.blit(self.small_font.render('退出程序', True, self.colors['white']), self.small_font.render('退出程序', True, self.colors['white']).get_rect(center=exit_rect.center))
        self.panel_actions.append((start_rect, 'standalone_open_lobby'))
        self.panel_actions.append((settings_rect, 'toggle_player_settings'))
        self.panel_actions.append((exit_rect, 'standalone_exit'))
        if self.player_settings_menu_open:
            self._render_player_settings_menu(game_engine, self.screen.get_rect())

    def _render_standalone_prematch_menu(self, game_engine):
        title = self.hud_mid_font.render('赛前选择', True, self.colors['white'])
        self.screen.blit(title, title.get_rect(center=(self.window_width // 2, 70)))

        panel_rect = pygame.Rect(0, 0, 760, 420)
        panel_rect.center = (self.window_width // 2, self.window_height // 2 + 20)
        pygame.draw.rect(self.screen, (28, 34, 42), panel_rect, border_radius=24)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=24)

        team_y = panel_rect.y + 34
        for index, team in enumerate(('red', 'blue')):
            rect = pygame.Rect(panel_rect.x + 40 + index * 124, team_y, 104, 34)
            active = self.standalone_3d_selected_team == team
            color = self.colors['red'] if team == 'red' and active else self.colors['blue'] if team == 'blue' and active else (68, 76, 88)
            pygame.draw.rect(self.screen, color, rect, border_radius=10)
            label = '红方' if team == 'red' else '蓝方'
            rendered = self.small_font.render(label, True, self.colors['white'])
            self.screen.blit(rendered, rendered.get_rect(center=rect.center))
            self.panel_actions.append((rect, f'standalone_team:{team}'))

        card_y = panel_rect.y + 94
        candidates = self._standalone_control_candidates(game_engine, self.standalone_3d_selected_team)
        for index, entity in enumerate(candidates):
            card_rect = pygame.Rect(panel_rect.x + 42 + (index % 3) * 220, card_y + (index // 3) * 108, 190, 82)
            active = entity.id == self.standalone_3d_selected_entity_id
            pygame.draw.rect(self.screen, (42, 48, 58), card_rect, border_radius=14)
            pygame.draw.rect(self.screen, self.colors['yellow'] if active else self.colors['panel_border'], card_rect, 2 if active else 1, border_radius=14)
            title = self.small_font.render(entity.display_name, True, self.colors['white'])
            subtitle = self.tiny_font.render(f'{"红方" if entity.team == "red" else "蓝方"} {getattr(entity, "robot_type", "")}', True, (198, 204, 212))
            self.screen.blit(title, (card_rect.x + 14, card_rect.y + 14))
            self.screen.blit(subtitle, (card_rect.x + 14, card_rect.y + 40))
            self.panel_actions.append((card_rect, f'standalone_pick:{entity.id}'))

        ricochet_rect = pygame.Rect(panel_rect.x + 42, panel_rect.bottom - 100, 260, 42)
        settings_rect = pygame.Rect(panel_rect.x + 42, panel_rect.bottom - 52, 136, 34)
        back_rect = pygame.Rect(panel_rect.right - 348, panel_rect.bottom - 52, 136, 34)
        confirm_rect = pygame.Rect(panel_rect.right - 194, panel_rect.bottom - 58, 152, 42)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if self.standalone_3d_ricochet_enabled else self.colors['toolbar_button'], ricochet_rect, border_radius=12)
        pygame.draw.rect(self.screen, (70, 76, 88), settings_rect, border_radius=10)
        pygame.draw.rect(self.screen, (70, 76, 88), back_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], confirm_rect, border_radius=12)
        ricochet_label = '弹丸碰障碍反弹: 开' if self.standalone_3d_ricochet_enabled else '弹丸碰障碍反弹: 关'
        self.screen.blit(self.small_font.render(ricochet_label, True, self.colors['white']), self.small_font.render(ricochet_label, True, self.colors['white']).get_rect(center=ricochet_rect.center))
        self.screen.blit(self.small_font.render('设置', True, self.colors['white']), self.small_font.render('设置', True, self.colors['white']).get_rect(center=settings_rect.center))
        self.screen.blit(self.small_font.render('返回', True, self.colors['white']), self.small_font.render('返回', True, self.colors['white']).get_rect(center=back_rect.center))
        self.screen.blit(self.small_font.render('确认开始', True, self.colors['white']), self.small_font.render('确认开始', True, self.colors['white']).get_rect(center=confirm_rect.center))
        self.panel_actions.append((ricochet_rect, 'standalone_toggle_ricochet'))
        self.panel_actions.append((settings_rect, 'toggle_player_settings'))
        self.panel_actions.append((back_rect, 'standalone_back_main'))
        self.panel_actions.append((confirm_rect, 'standalone_confirm_start'))
        if self.player_settings_menu_open:
            self._render_player_settings_menu(game_engine, self.screen.get_rect())

    def _sync_player_mouse_capture(self, active):
        desired = bool(active)
        if self.player_mouse_captured == desired:
            return
        self.player_mouse_captured = desired
        try:
            pygame.event.set_grab(desired)
        except Exception:
            pass
        try:
            pygame.mouse.set_visible(not desired)
        except Exception:
            pass

    def _player_control_candidate_id(self, game_engine):
        entities = list(game_engine.entity_manager.entities)
        if self.selected_hud_entity_id:
            for entity in entities:
                if entity.id == self.selected_hud_entity_id and entity.is_alive() and entity.type in {'robot', 'sentry'}:
                    return entity.id
        for preferred_id in ('red_robot_3',):
            for entity in entities:
                if entity.id == preferred_id and entity.is_alive() and entity.type in {'robot', 'sentry'}:
                    return entity.id
        focus_id = game_engine.get_single_unit_test_focus_entity_id()
        if focus_id:
            return focus_id
        for entity in entities:
            if entity.is_alive() and entity.team == 'red' and entity.type == 'robot':
                return entity.id
        for entity in entities:
            if entity.is_alive() and entity.type in {'robot', 'sentry'}:
                return entity.id
        return None

    def _world_to_scene_point(self, map_manager, sample_data, world_x, world_y, height_m):
        sampled_cell_size = max(float(sample_data.get('cell_size', 0.0) or 0.0), 1e-6)
        effective_height = self._meters_to_world_units(map_manager, float(height_m)) / sampled_cell_size
        return np.array([
            float(world_x) / sampled_cell_size - float(sample_data['grid_width']) * 0.5,
            effective_height,
            float(world_y) / sampled_cell_size - float(sample_data['grid_height']) * 0.5,
            1.0,
        ], dtype='f4')

    def _entity_vertical_scale(self, entity):
        return 1.0

    def _terrain_editor_display_height(self, value):
        return float(value)

    def _terrain_editor_storage_height(self, value):
        return float(value)

    def _effective_terrain_scene_max_cells(self):
        if getattr(self, 'terrain_scene_camera_override', None) is not None or bool(getattr(self, '_building_player_camera_override', False)):
            return max(6000, min(int(self.terrain_scene_max_cells), int(self.player_terrain_scene_max_cells)))
        return int(self.terrain_scene_max_cells)

    def _meters_to_world_units(self, map_manager, meters):
        if map_manager is None:
            return float(meters)
        return float(map_manager.meters_to_world_units(float(meters)))

    def _world_units_to_meters(self, map_manager, world_units):
        if map_manager is None:
            return float(world_units)
        return float(world_units) / max(float(map_manager.meters_to_world_units(1.0)), 1e-6)

    def _build_player_camera_override(self, game_engine, rect):
        entity = game_engine.get_player_controlled_entity()
        if entity is None:
            return None
        map_manager = game_engine.map_manager
        map_rgb = self._get_terrain_3d_map_rgb(map_manager)
        self._building_player_camera_override = True
        try:
            sample_data = _sample_terrain_scene_data(self, map_manager, map_rgb)
        finally:
            self._building_player_camera_override = False
        base_height_m = float(getattr(entity, 'position', {}).get('z', map_manager.get_terrain_height_m(entity.position['x'], entity.position['y'])))
        yaw_rad = math.radians(float(getattr(entity, 'turret_angle', entity.angle)))
        pitch_rad = math.radians(float(getattr(entity, 'gimbal_pitch_deg', 0.0)))
        anchor_height_m = base_height_m + float(getattr(entity, 'gimbal_height_m', 0.50)) * self._entity_vertical_scale(entity)
        direction = np.array([
            math.cos(pitch_rad) * math.cos(yaw_rad),
            math.cos(pitch_rad) * math.sin(yaw_rad),
            math.sin(pitch_rad),
        ], dtype='f4')
        world_target = np.array([
            float(entity.position['x']),
            float(entity.position['y']),
            anchor_height_m,
        ], dtype='f4') + direction * max(6.0, float(sample_data['grid_width']) * 0.12)
        if self.player_camera_mode == 'third_person':
            backward = np.array([math.cos(yaw_rad), math.sin(yaw_rad), 0.0], dtype='f4')
            world_eye = self._resolve_third_person_camera_eye(
                map_manager,
                float(entity.position['x']),
                float(entity.position['y']),
                anchor_height_m,
                backward,
            )
        else:
            world_eye = np.array([
                float(entity.position['x']),
                float(entity.position['y']),
                anchor_height_m,
            ], dtype='f4')
        eye = self._world_to_scene_point(map_manager, sample_data, world_eye[0], world_eye[1], world_eye[2])[:3]
        target = self._world_to_scene_point(map_manager, sample_data, world_target[0], world_target[1], world_target[2])[:3]
        projection = _terrain_scene_perspective_matrix(math.radians(76.0), rect.width / max(rect.height, 1), 0.05, 280.0)
        view = _terrain_scene_look_at(eye, target, np.array([0.0, 1.0, 0.0], dtype='f4'))
        return {
            'mvp': projection @ view,
            'projection': projection,
            'view': view,
            'eye': eye,
            'target': target,
            'world_eye': (float(world_eye[0]), float(world_eye[1]), float(world_eye[2])),
            'world_target': (float(world_target[0]), float(world_target[1]), float(world_target[2])),
            'world_direction': (float(direction[0]), float(direction[1]), float(direction[2])),
            'camera_mode': self.player_camera_mode,
            'sample_data': sample_data,
        }

    def _player_terrain_surface_cache_key(self, game_engine, rect):
        camera_state = getattr(self, 'terrain_scene_camera_override', None)
        if not isinstance(camera_state, dict):
            return None
        map_manager = game_engine.map_manager
        world_eye = tuple(round(float(value), 2) for value in camera_state.get('world_eye', (0.0, 0.0, 0.0)))
        world_target = tuple(round(float(value), 2) for value in camera_state.get('world_target', (0.0, 0.0, 0.0)))
        return (
            'player_view',
            getattr(self._get_terrain_scene_backend(), 'name', 'software'),
            int(getattr(map_manager, 'raster_version', 0)),
            int(rect.width),
            int(rect.height),
            round(float(getattr(self, '_active_player_terrain_render_scale', getattr(self, 'player_terrain_render_scale', 0.6))), 3),
            bool(getattr(self, 'terrain_scene_force_dark_gray', False)),
            str(camera_state.get('camera_mode', 'first_person')),
            world_eye,
            world_target,
        )

    def _collision_overlay_active(self):
        try:
            keys = pygame.key.get_pressed()
        except Exception:
            return False
        return bool(keys[pygame.K_F3])

    def _player_camera_motion_metric_m(self, map_manager, camera_state):
        if not isinstance(camera_state, dict):
            self._last_player_camera_sample = None
            return 0.0
        world_eye = camera_state.get('world_eye')
        world_target = camera_state.get('world_target')
        if world_eye is None or world_target is None:
            self._last_player_camera_sample = None
            return 0.0
        current_sample = (
            (float(world_eye[0]), float(world_eye[1]), float(world_eye[2])),
            (float(world_target[0]), float(world_target[1]), float(world_target[2])),
        )
        previous_sample = self._last_player_camera_sample
        self._last_player_camera_sample = current_sample
        if previous_sample is None:
            return 0.0
        meters_per_world_unit = 1.0 / max(float(map_manager.meters_to_world_units(1.0)), 1e-6)

        def distance_m(current_point, previous_point):
            delta_x_m = (float(current_point[0]) - float(previous_point[0])) * meters_per_world_unit
            delta_y_m = (float(current_point[1]) - float(previous_point[1])) * meters_per_world_unit
            delta_z_m = float(current_point[2]) - float(previous_point[2])
            return math.sqrt(delta_x_m * delta_x_m + delta_y_m * delta_y_m + delta_z_m * delta_z_m)

        return max(
            distance_m(current_sample[0], previous_sample[0]),
            distance_m(current_sample[1], previous_sample[1]),
        )

    def _entity_collision_polygon_world(self, entity, map_manager):
        half_length = max(0.0, float(map_manager.meters_to_world_units(float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)))
        half_width = max(0.0, float(map_manager.meters_to_world_units(float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)))
        angle_rad = math.radians(float(getattr(entity, 'angle', 0.0)))
        heading_x = math.cos(angle_rad)
        heading_y = math.sin(angle_rad)
        right_x = -heading_y
        right_y = heading_x
        center_x = float(entity.position['x'])
        center_y = float(entity.position['y'])
        return [
            (center_x + heading_x * half_length - right_x * half_width, center_y + heading_y * half_length - right_y * half_width),
            (center_x + heading_x * half_length + right_x * half_width, center_y + heading_y * half_length + right_y * half_width),
            (center_x - heading_x * half_length + right_x * half_width, center_y - heading_y * half_length + right_y * half_width),
            (center_x - heading_x * half_length - right_x * half_width, center_y - heading_y * half_length - right_y * half_width),
        ]

    def _entity_wheel_layout_world(self, entity, map_manager):
        render_width_scale = max(0.45, min(1.0, float(getattr(entity, 'body_render_width_scale', 0.82))))
        body_length_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        body_width_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5 * render_width_scale)
        wheel_radius_world = self._meters_to_world_units(map_manager, float(getattr(entity, 'wheel_radius_m', 0.08)))
        wheel_style = str(getattr(entity, 'wheel_style', 'standard'))
        wheel_offset_x = max(0.10, body_length_half * (0.72 if wheel_style == 'legged' else 0.78))
        wheel_offset_y = max(1.0, body_width_half + wheel_radius_world * 0.55)
        custom_wheel_positions_raw = getattr(entity, 'custom_wheel_positions_m', None)
        if isinstance(custom_wheel_positions_raw, (list, tuple)) and custom_wheel_positions_raw:
            wheel_positions = tuple(
                (
                    self._meters_to_world_units(map_manager, float(position[0])),
                    self._meters_to_world_units(map_manager, float(position[1]) * render_width_scale),
                )
                for position in custom_wheel_positions_raw
                if isinstance(position, (list, tuple)) and len(position) >= 2
            )
        elif int(getattr(entity, 'wheel_count', 4)) <= 2:
            wheel_positions = ((0.0, -wheel_offset_y), (0.0, wheel_offset_y))
        else:
            wheel_positions = ((-wheel_offset_x, -wheel_offset_y), (wheel_offset_x, -wheel_offset_y), (-wheel_offset_x, wheel_offset_y), (wheel_offset_x, wheel_offset_y))

        yaw_rad = math.radians(float(getattr(entity, 'angle', 0.0)))
        forward_x = math.cos(yaw_rad)
        forward_y = math.sin(yaw_rad)
        right_x = -forward_y
        right_y = forward_x
        world_positions = []
        for local_x, local_y in wheel_positions:
            world_positions.append((
                float(entity.position['x']) + forward_x * float(local_x) + right_x * float(local_y),
                float(entity.position['y']) + forward_y * float(local_x) + right_y * float(local_y),
                float(local_x),
                float(local_y),
            ))
        return tuple(world_positions)

    def _player_debug_lines(self, entity, map_manager):
        if entity is None or map_manager is None:
            return ()
        center_x_world = float(entity.position['x'])
        center_y_world = float(entity.position['y'])
        center_z_m = float(getattr(entity, 'position', {}).get('z', map_manager.get_terrain_height_m(center_x_world, center_y_world)))
        wheel_samples = []
        for world_x, world_y, local_x, local_y in self._entity_wheel_layout_world(entity, map_manager):
            if abs(local_x) <= 1e-6:
                label = '左轮' if local_y < 0.0 else '右轮'
            else:
                label = f'{"前" if local_x > 0.0 else "后"}{"左" if local_y < 0.0 else "右"}'
            wheel_samples.append((label, float(map_manager.get_terrain_height_m(world_x, world_y))))
        if wheel_samples:
            wheel_height_values = [height for _, height in wheel_samples]
            wheel_summary = f'轮底模型高度 {center_z_m:.3f}m   轮地接触 {min(wheel_height_values):.3f}-{max(wheel_height_values):.3f}m'
        else:
            wheel_summary = f'轮底模型高度 {center_z_m:.3f}m'
        lines = [
            'F3 调试',
            f'底盘中心 坐标m ({self._world_units_to_meters(map_manager, center_x_world):.2f}, {self._world_units_to_meters(map_manager, center_y_world):.2f}, {center_z_m:.3f})',
            f'底盘中心 坐标图 ({center_x_world:.1f}, {center_y_world:.1f})',
            wheel_summary,
        ]
        for index in range(0, len(wheel_samples), 2):
            chunk = wheel_samples[index:index + 2]
            lines.append('   '.join(f'{label} {height:.3f}m' for label, height in chunk))
        return tuple(lines)

    def _render_player_debug_hud(self, game_engine, rect):
        controlled_getter = getattr(game_engine, 'get_player_controlled_entity', None)
        entity = controlled_getter() if callable(controlled_getter) else None
        lines = self._player_debug_lines(entity, getattr(game_engine, 'map_manager', None))
        if not lines:
            return
        panel_height = 16 + len(lines) * 18
        panel_rect = pygame.Rect(rect.right - 494, rect.y + 18, 476, panel_height)
        pygame.draw.rect(self.screen, (18, 24, 30), panel_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=10)
        draw_y = panel_rect.y + 10
        for line_index, line in enumerate(lines):
            font = self.font if line_index == 0 else self.small_font
            text = font.render(line, True, self.colors['white'])
            self.screen.blit(text, (panel_rect.x + 12, draw_y))
            draw_y += 18

    def render_collision_boxes(self, entities):
        if self.viewport is None:
            return
        map_manager = getattr(self.game_engine, 'map_manager', None)
        if map_manager is None:
            return
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        for entity in entities:
            if not entity.is_alive() or entity.type not in {'robot', 'sentry'}:
                continue
            world_polygon = self._entity_collision_polygon_world(entity, map_manager)
            polygon = [self.world_to_screen(point[0], point[1]) for point in world_polygon]
            if any(point is None for point in polygon):
                continue
            color_rgb = (255, 104, 104) if entity.team == 'red' else (102, 182, 255)
            fill_color = (*color_rgb, 34)
            outline_color = (*color_rgb, 214)
            pygame.draw.polygon(overlay, fill_color, polygon)
            pygame.draw.polygon(overlay, outline_color, polygon, 2)
            center = self.world_to_screen(entity.position['x'], entity.position['y'])
            radius_px = max(4, int(float(getattr(entity, 'collision_radius', 0.0)) * float(self.viewport['scale'])))
            pygame.draw.circle(overlay, (*color_rgb, 156), center, radius_px, 1)
            pygame.draw.line(overlay, outline_color, polygon[0], polygon[1], 3)
        self.screen.blit(overlay, (0, 0))

    def _project_entity_collision_box_edges(self, entity, map_manager, sample_data, camera_state, rect):
        terrain_height = float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))
        base_height = float(getattr(entity, 'position', {}).get('z', terrain_height))
        vertical_scale = self._entity_vertical_scale(entity)
        body_length_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        body_width_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        body_bottom = base_height + float(getattr(entity, 'body_clearance_m', 0.10)) * vertical_scale
        body_top = body_bottom + float(getattr(entity, 'body_height_m', 0.18)) * vertical_scale
        center_scene, forward_basis, right_basis, up_basis = self._entity_scene_axes(entity, map_manager, sample_data, base_height)

        def project_corner(local_x, local_y, height_m):
            scene_xyz = center_scene + forward_basis * float(local_x) + right_basis * float(local_y) + up_basis * (float(height_m) - base_height)
            projected = self._project_scene_point(np.array([scene_xyz[0], scene_xyz[1], scene_xyz[2], 1.0], dtype='f4'), camera_state, rect)
            if projected is None:
                return None
            return (int(projected[0] - rect.x), int(projected[1] - rect.y))

        local_points = [
            (-body_length_half, -body_width_half),
            (body_length_half, -body_width_half),
            (body_length_half, body_width_half),
            (-body_length_half, body_width_half),
        ]
        corners = []
        for height in (body_bottom, body_top):
            for local_x, local_y in local_points:
                corners.append(project_corner(local_x, local_y, height))
        if any(point is None for point in corners):
            return []
        edge_indices = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
        return [(corners[start], corners[end]) for start, end in edge_indices]

    def _render_player_collision_boxes(self, game_engine, rect, camera_state):
        map_manager = game_engine.map_manager
        sample_data = camera_state.get('sample_data') or {}
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        for entity in game_engine.entity_manager.entities:
            if not entity.is_alive() or entity.type not in {'robot', 'sentry'}:
                continue
            if not self._entity_visible_from_camera(entity, map_manager, camera_state):
                continue
            edges = self._project_entity_collision_box_edges(entity, map_manager, sample_data, camera_state, rect)
            if not edges:
                continue
            color_rgb = (255, 110, 110) if entity.team == 'red' else (112, 188, 255)
            for start, end in edges:
                pygame.draw.line(overlay, (*color_rgb, 220), start, end, 2)
        self.screen.blit(overlay, rect.topleft)

    def _resolve_third_person_camera_eye(self, map_manager, anchor_x, anchor_y, anchor_height_m, backward):
        anchor_point = np.array([
            float(anchor_x),
            float(anchor_y),
            float(anchor_height_m),
        ], dtype='f4')
        desired_distance = float(map_manager.meters_to_world_units(self.player_third_person_distance_m))
        step_distance = max(2.0, float(map_manager.meters_to_world_units(0.35)))
        extra_height = float(self.player_third_person_height_m)
        direction = np.array(backward, dtype='f4')
        direction_norm = float(np.linalg.norm(direction))
        if direction_norm <= 1e-6:
            direction = np.array([1.0, 0.0, 0.0], dtype='f4')
        else:
            direction = direction / direction_norm
        distance = desired_distance
        while distance >= 0.0:
            candidate = np.array([
                anchor_point[0] - direction[0] * distance,
                anchor_point[1] - direction[1] * distance,
                anchor_point[2] + extra_height,
            ], dtype='f4')
            sample = map_manager.sample_raster_layers(float(candidate[0]), float(candidate[1]))
            if sample.get('terrain_type') != 'boundary':
                candidate[2] = max(candidate[2], float(sample.get('height_m', 0.0)) + 0.12)
                if map_manager.is_terrain_line_clear_3d(candidate, anchor_point, clearance_m=0.04):
                    return candidate
            distance -= step_distance
        fallback = np.array([
            anchor_point[0],
            anchor_point[1],
            anchor_point[2] + extra_height,
        ], dtype='f4')
        fallback[2] = max(fallback[2], float(map_manager.get_terrain_height_m(fallback[0], fallback[1])) + 0.12)
        return fallback

    def _camera_visibility_points(self, entity, map_manager):
        base_height = float(getattr(entity, 'position', {}).get('z', map_manager.get_terrain_height_m(entity.position['x'], entity.position['y'])))
        vertical_scale = self._entity_vertical_scale(entity)
        body_mid = base_height + (float(getattr(entity, 'body_clearance_m', 0.10)) + float(getattr(entity, 'body_height_m', 0.18)) * 0.55) * vertical_scale
        turret_mid = base_height + float(getattr(entity, 'gimbal_height_m', 0.50)) * vertical_scale
        half_length = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        half_width = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        yaw_rad = math.radians(float(getattr(entity, 'angle', 0.0)))
        forward_x = math.cos(yaw_rad)
        forward_y = math.sin(yaw_rad)
        right_x = -forward_y
        right_y = forward_x
        chassis_points = []
        for length_sign in (-1.0, 1.0):
            for width_sign in (-1.0, 1.0):
                chassis_points.append((
                    float(entity.position['x']) + forward_x * half_length * length_sign + right_x * half_width * width_sign,
                    float(entity.position['y']) + forward_y * half_length * length_sign + right_y * half_width * width_sign,
                    body_mid,
                ))
        chassis_points.append((float(entity.position['x']), float(entity.position['y']), body_mid))
        chassis_points.append((float(entity.position['x']), float(entity.position['y']), turret_mid))
        return tuple(chassis_points)

    def _entity_visible_from_camera(self, entity, map_manager, camera_state):
        world_eye = camera_state.get('world_eye') if isinstance(camera_state, dict) else None
        if world_eye is None:
            return True
        for point in self._camera_visibility_points(entity, map_manager):
            if map_manager.is_terrain_line_clear_3d(world_eye, point, clearance_m=0.03):
                return True
        return False

    def _resolve_player_view_aim_state(self, game_engine, camera_state):
        if not isinstance(camera_state, dict):
            return None
        world_eye = camera_state.get('world_eye')
        world_direction = camera_state.get('world_direction')
        entity = game_engine.get_player_controlled_entity()
        if world_eye is None or world_direction is None or entity is None:
            return None
        map_manager = game_engine.map_manager
        max_range = float(game_engine.rules_engine.get_range(getattr(entity, 'type', 'robot')))
        step_world = max(2.0, float(map_manager.meters_to_world_units(0.20)))
        direction = np.array(world_direction, dtype='f4')
        direction = direction / max(float(np.linalg.norm(direction)), 1e-6)
        last_point = np.array(world_eye, dtype='f4')
        path_points = [tuple(float(value) for value in last_point)]
        traveled = 0.0
        while traveled < max_range:
            travel = min(step_world, max_range - traveled)
            current = last_point + direction * travel
            sample = map_manager.sample_raster_layers(float(current[0]), float(current[1]))
            if sample.get('terrain_type') == 'boundary':
                break
            blocking_height = float(sample.get('height_m', 0.0))
            if bool(sample.get('vision_blocked', False)):
                blocking_height = max(blocking_height, float(sample.get('vision_block_height_m', 0.0)))
            if float(current[2]) <= blocking_height + 0.02:
                current[2] = blocking_height + 0.02
                path_points.append((float(current[0]), float(current[1]), float(current[2])))
                last_point = current
                break
            path_points.append((float(current[0]), float(current[1]), float(current[2])))
            last_point = current
            traveled += travel
        return {
            'x': float(last_point[0]),
            'y': float(last_point[1]),
            'z': float(last_point[2]),
            'origin_x': float(world_eye[0]),
            'origin_y': float(world_eye[1]),
            'origin_z': float(world_eye[2]),
            'path_points': tuple(path_points),
            'camera_mode': str(camera_state.get('camera_mode', 'first_person')),
        }

    def _render_player_view_ray(self, rect, camera_state, view_aim_state, map_manager, sample_data):
        if not isinstance(view_aim_state, dict):
            return
        trace_points = view_aim_state.get('path_points')
        if not isinstance(trace_points, (list, tuple)) or len(trace_points) < 2:
            return
        polyline, _ = self._project_trace_polyline(trace_points, map_manager, sample_data, camera_state, rect)
        if len(polyline) < 2:
            return
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        glow = (255, 212, 112, max(56, self.player_view_ray_alpha // 2))
        ray = (255, 244, 184, self.player_view_ray_alpha)
        pygame.draw.lines(overlay, glow, False, polyline, 4)
        pygame.draw.lines(overlay, ray, False, polyline, 2)
        pygame.draw.circle(overlay, glow, polyline[-1], 6)
        pygame.draw.circle(overlay, ray, polyline[-1], 3)
        self.screen.blit(overlay, rect.topleft)

    def _project_scene_point(self, point4, camera_state, rect):
        clip = camera_state['mvp'] @ point4
        w = float(clip[3])
        if w <= 1e-5:
            return None
        ndc = clip[:3] / w
        if ndc[2] < -1.2 or ndc[2] > 1.2:
            return None
        screen_x = rect.x + int((float(ndc[0]) * 0.5 + 0.5) * rect.width)
        screen_y = rect.y + int((1.0 - (float(ndc[1]) * 0.5 + 0.5)) * rect.height)
        return (screen_x, screen_y, float(ndc[2]))

    def _append_box_faces(self, faces, corners, color):
        face_indices = (
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (2, 3, 7, 6),
            (1, 2, 6, 5),
            (0, 3, 7, 4),
        )
        shades = (0.95, 0.55, 0.70, 0.66, 0.80, 0.62)
        for indices, shade in zip(face_indices, shades):
            pts = [corners[index] for index in indices]
            if any(point is None for point in pts):
                continue
            polygon = [(point[0], point[1]) for point in pts]
            depth = sum(point[2] for point in pts) / len(pts)
            face_color = tuple(max(0, min(255, int(channel * shade))) for channel in color)
            faces.append((depth, polygon, face_color))

    def _trace_path_points(self, trace, map_manager):
        path_points = trace.get('path_points')
        if isinstance(path_points, (list, tuple)) and len(path_points) >= 2:
            return [(float(point[0]), float(point[1]), float(point[2])) for point in path_points if point is not None and len(point) >= 3]
        start = trace.get('start')
        end = trace.get('end')
        if start is None or end is None:
            return []
        start_height_m = float(trace.get('start_height_m', float(map_manager.get_terrain_height_m(float(start[0]), float(start[1]))) + 0.50))
        end_height_m = float(trace.get('end_height_m', float(map_manager.get_terrain_height_m(float(end[0]), float(end[1]))) + 0.32))
        return [
            (float(start[0]), float(start[1]), start_height_m),
            (float(end[0]), float(end[1]), end_height_m),
        ]

    def _trace_point_at_progress(self, points, progress):
        if len(points) < 2:
            return None
        progress = max(0.0, min(1.0, float(progress)))
        game_engine = getattr(self, 'game_engine', None)
        map_manager = getattr(game_engine, 'map_manager', None)
        meters_per_world_unit = 1.0
        if map_manager is not None and hasattr(map_manager, 'meters_to_world_units'):
            meters_per_world_unit = 1.0 / max(float(map_manager.meters_to_world_units(1.0)), 1e-6)
        segment_lengths = []
        total_length = 0.0
        for start, end in zip(points, points[1:]):
            seg_len = math.sqrt(
                ((end[0] - start[0]) * meters_per_world_unit) ** 2
                + ((end[1] - start[1]) * meters_per_world_unit) ** 2
                + (end[2] - start[2]) ** 2
            )
            segment_lengths.append(seg_len)
            total_length += seg_len
        if total_length <= 1e-6:
            return points[-1]
        remaining = total_length * progress
        for index, seg_len in enumerate(segment_lengths):
            start = points[index]
            end = points[index + 1]
            if remaining <= seg_len or index == len(segment_lengths) - 1:
                ratio = 0.0 if seg_len <= 1e-6 else remaining / seg_len
                return (
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                    start[2] + (end[2] - start[2]) * ratio,
                )
            remaining -= seg_len
        return points[-1]

    def _project_trace_polyline(self, trace_points, map_manager, sample_data, camera_state, rect):
        projected_points = []
        max_depth = None
        sample_count = max(12, min(48, len(trace_points) * 2))
        previous_point = None
        for sample_index in range(sample_count + 1):
            progress = sample_index / max(sample_count, 1)
            world_point = self._trace_point_at_progress(trace_points, progress)
            if world_point is None:
                continue
            scene_point = self._world_to_scene_point(map_manager, sample_data, world_point[0], world_point[1], world_point[2])
            projected = self._project_scene_point(scene_point, camera_state, rect)
            if projected is None:
                previous_point = None
                continue
            screen_point = (int(projected[0] - rect.x), int(projected[1] - rect.y))
            if previous_point != screen_point:
                projected_points.append(screen_point)
            previous_point = screen_point
            max_depth = projected[2] if max_depth is None else max(max_depth, projected[2])
        return projected_points, max_depth

    def _entity_scene_axes(self, entity, map_manager, sample_data, base_height):
        sampled_cell_size = max(float(sample_data.get('cell_size', 0.0) or 0.0), 1e-6)
        terrain_height = float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))
        body_length_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        body_width_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        yaw_rad = math.radians(float(getattr(entity, 'angle', 0.0)))
        center_scene = self._world_to_scene_point(map_manager, sample_data, entity.position['x'], entity.position['y'], base_height)[:3]
        up_basis = self._world_to_scene_point(map_manager, sample_data, entity.position['x'], entity.position['y'], base_height + 1.0)[:3] - center_scene
        if np.linalg.norm(up_basis) <= 1e-6:
            up_basis = np.array([0.0, 0.82, 0.0], dtype='f4')

        airborne = (
            float(base_height - terrain_height) > 0.03
            or float(getattr(entity, 'jump_airborne_height_m', 0.0)) > 1e-3
            or float(getattr(entity, 'fly_slope_airborne_height_m', 0.0)) > 1e-3
        )
        if airborne:
            forward_basis = np.array([
                math.cos(yaw_rad) / sampled_cell_size,
                0.0,
                math.sin(yaw_rad) / sampled_cell_size,
            ], dtype='f4')
            right_basis = np.array([
                -math.sin(yaw_rad) / sampled_cell_size,
                0.0,
                math.cos(yaw_rad) / sampled_cell_size,
            ], dtype='f4')
            return center_scene, forward_basis, right_basis, up_basis

        forward_dx = math.cos(yaw_rad)
        forward_dy = math.sin(yaw_rad)
        right_dx = -forward_dy
        right_dy = forward_dx
        sample_forward = max(1.0, body_length_half)
        sample_right = max(1.0, body_width_half)

        front_world = (float(entity.position['x']) + forward_dx * sample_forward, float(entity.position['y']) + forward_dy * sample_forward)
        rear_world = (float(entity.position['x']) - forward_dx * sample_forward, float(entity.position['y']) - forward_dy * sample_forward)
        right_world = (float(entity.position['x']) + right_dx * sample_right, float(entity.position['y']) + right_dy * sample_right)
        left_world = (float(entity.position['x']) - right_dx * sample_right, float(entity.position['y']) - right_dy * sample_right)

        front_scene = self._world_to_scene_point(map_manager, sample_data, front_world[0], front_world[1], map_manager.get_terrain_height_m(front_world[0], front_world[1]))[:3]
        rear_scene = self._world_to_scene_point(map_manager, sample_data, rear_world[0], rear_world[1], map_manager.get_terrain_height_m(rear_world[0], rear_world[1]))[:3]
        right_scene = self._world_to_scene_point(map_manager, sample_data, right_world[0], right_world[1], map_manager.get_terrain_height_m(right_world[0], right_world[1]))[:3]
        left_scene = self._world_to_scene_point(map_manager, sample_data, left_world[0], left_world[1], map_manager.get_terrain_height_m(left_world[0], left_world[1]))[:3]

        forward_axis = (front_scene - rear_scene) / max(sample_forward * 2.0, 1e-6)
        right_axis = (right_scene - left_scene) / max(sample_right * 2.0, 1e-6)
        forward_scale = max(np.linalg.norm(forward_axis), 1e-6)
        right_scale = max(np.linalg.norm(right_axis), 1e-6)
        up_scale = max(np.linalg.norm(up_basis), 1e-6)
        forward_dir = forward_axis / forward_scale
        right_dir = right_axis / right_scale
        up_dir = np.cross(right_dir, forward_dir)
        if np.linalg.norm(up_dir) <= 1e-6:
            up_dir = up_basis / up_scale
        else:
            up_dir = up_dir / max(np.linalg.norm(up_dir), 1e-6)
        right_dir = np.cross(forward_dir, up_dir)
        if np.linalg.norm(right_dir) <= 1e-6:
            right_dir = right_axis / right_scale
        else:
            right_dir = right_dir / max(np.linalg.norm(right_dir), 1e-6)
        forward_dir = np.cross(up_dir, right_dir)
        forward_dir = forward_dir / max(np.linalg.norm(forward_dir), 1e-6)
        return center_scene, forward_dir * forward_scale, right_dir * right_scale, up_dir * up_scale

    def _climb_assist_animation_state(self, entity):
        front_drop_m = 0.04
        front_raise_m = 0.02
        rear_drop_m = 0.02
        rear_reach_m = 0.03
        state = getattr(entity, 'step_climb_state', None)
        if not isinstance(state, dict):
            return {
                'front_drop_m': front_drop_m,
                'front_raise_m': front_raise_m,
                'rear_drop_m': rear_drop_m,
                'rear_reach_m': rear_reach_m,
            }

        phase = str(state.get('phase', 'front_ascent'))
        progress = float(state.get('progress', 0.0))

        def _ratio(duration_key, fallback):
            duration = max(1e-6, float(state.get(duration_key, fallback)))
            return max(0.0, min(1.0, progress / duration))

        if phase == 'align':
            front_drop_m = 0.08
            front_raise_m = 0.05
        elif phase == 'front_ascent':
            ratio = _ratio('front_ascent_duration', 0.35)
            front_drop_m = 0.10 + 0.18 * ratio
            front_raise_m = 0.05 + 0.06 * ratio
        elif phase == 'rear_pause':
            front_drop_m = 0.18
            front_raise_m = 0.08
            rear_drop_m = 0.20
            rear_reach_m = 0.18
        elif phase == 'rear_ascent':
            ratio = _ratio('rear_ascent_duration', 0.25)
            front_drop_m = 0.18 - 0.10 * ratio
            front_raise_m = 0.08 - 0.04 * ratio
            rear_drop_m = 0.20 * (1.0 - ratio)
            rear_reach_m = 0.18 * (1.0 - ratio)

        return {
            'front_drop_m': max(0.0, front_drop_m),
            'front_raise_m': max(0.0, front_raise_m),
            'rear_drop_m': max(0.0, rear_drop_m),
            'rear_reach_m': max(0.0, rear_reach_m),
        }

    def _build_entity_model_faces(self, entity, camera_state, rect, map_manager, sample_data):
        terrain_height = float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))
        base_height = float(getattr(entity, 'position', {}).get('z', terrain_height))
        vertical_scale = self._entity_vertical_scale(entity)
        body_length_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5)
        render_width_scale = max(0.45, min(1.0, float(getattr(entity, 'body_render_width_scale', 0.82))))
        body_width_half = self._meters_to_world_units(map_manager, float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5 * render_width_scale)
        body_bottom = base_height + float(getattr(entity, 'body_clearance_m', 0.10)) * vertical_scale
        body_top = body_bottom + float(getattr(entity, 'body_height_m', 0.18)) * vertical_scale
        wheel_radius_world = self._meters_to_world_units(map_manager, float(getattr(entity, 'wheel_radius_m', 0.08)))
        wheel_radius_height = float(getattr(entity, 'wheel_radius_m', 0.08)) * vertical_scale
        yaw_rad = math.radians(float(getattr(entity, 'angle', 0.0)))
        turret_yaw_rad = math.radians(float(getattr(entity, 'turret_angle', entity.angle)))
        wheel_style = str(getattr(entity, 'wheel_style', 'standard'))
        suspension_style = str(getattr(entity, 'suspension_style', 'none'))
        arm_style = str(getattr(entity, 'arm_style', 'none'))
        front_climb_style = str(getattr(entity, 'front_climb_assist_style', 'none'))
        rear_climb_style = str(getattr(entity, 'rear_climb_assist_style', 'none'))
        has_turret = float(getattr(entity, 'gimbal_length_m', 0.0)) > 1e-6 and float(getattr(entity, 'gimbal_body_height_m', 0.0)) > 1e-6
        has_mount = has_turret and float(getattr(entity, 'gimbal_mount_height_m', 0.0)) > 1e-6
        has_barrel = has_turret and float(getattr(entity, 'barrel_length_m', 0.0)) > 1e-6 and float(getattr(entity, 'barrel_radius_m', 0.0)) > 1e-6
        faces = []

        center_scene, forward_basis, right_basis, up_basis = self._entity_scene_axes(entity, map_manager, sample_data, base_height)

        def local_to_scene(local_x, local_y, height_m, angle_rad):
            relative_angle = angle_rad - yaw_rad
            cos_a = math.cos(relative_angle)
            sin_a = math.sin(relative_angle)
            rotated_x = local_x * cos_a - local_y * sin_a
            rotated_y = local_x * sin_a + local_y * cos_a
            scene_xyz = center_scene + forward_basis * rotated_x + right_basis * rotated_y + up_basis * (float(height_m) - base_height)
            return np.array([scene_xyz[0], scene_xyz[1], scene_xyz[2], 1.0], dtype='f4')

        def box_corners(cx, cy, half_x, half_y, low_h, high_h, angle_rad):
            local_points = [(-half_x, -half_y), (half_x, -half_y), (half_x, half_y), (-half_x, half_y)]
            projected = []
            for height in (low_h, high_h):
                for local_x, local_y in local_points:
                    projected.append(self._project_scene_point(local_to_scene(local_x + cx, local_y + cy, height, angle_rad), camera_state, rect))
            return projected

        team_color = self.colors['red'] if entity.team == 'red' else self.colors['blue']
        body_base_color = tuple(getattr(entity, 'body_color_rgb', ()) or team_color)
        turret_base_color = tuple(getattr(entity, 'turret_color_rgb', ()) or (232, 232, 236))
        armor_color = tuple(getattr(entity, 'armor_color_rgb', ()) or (224, 229, 234))
        wheel_color = tuple(getattr(entity, 'wheel_color_rgb', ()) or (44, 44, 44))
        body_color = tuple(max(48, min(255, int(channel * 0.78 + 34))) for channel in body_base_color)
        self._append_box_faces(faces, box_corners(0.0, 0.0, body_length_half, body_width_half, body_bottom, body_top, yaw_rad), body_color)
        self._append_box_faces(
            faces,
            box_corners(0.0, 0.0, body_length_half * 0.82, body_width_half * 0.82, body_top - 0.02, body_top + 0.03, yaw_rad),
            tuple(max(52, min(255, int(channel * 0.58 + 56))) for channel in body_base_color),
        )

        wheel_offset_x = max(0.10, body_length_half * (0.72 if wheel_style == 'legged' else 0.78))
        wheel_offset_y = max(1.0, body_width_half + wheel_radius_world * 0.55)
        wheel_bottom = base_height
        wheel_top = wheel_bottom + wheel_radius_height * 2.0
        custom_wheel_positions_raw = getattr(entity, 'custom_wheel_positions_m', None)
        if isinstance(custom_wheel_positions_raw, (list, tuple)) and custom_wheel_positions_raw:
            wheel_positions = tuple(
                (
                    self._meters_to_world_units(map_manager, float(position[0])),
                    self._meters_to_world_units(map_manager, float(position[1]) * render_width_scale),
                )
                for position in custom_wheel_positions_raw
                if isinstance(position, (list, tuple)) and len(position) >= 2
            )
        else:
            if int(getattr(entity, 'wheel_count', 4)) <= 2:
                wheel_positions = ((0.0, -wheel_offset_y), (0.0, wheel_offset_y))
            else:
                wheel_positions = ((-wheel_offset_x, -wheel_offset_y), (wheel_offset_x, -wheel_offset_y), (-wheel_offset_x, wheel_offset_y), (wheel_offset_x, wheel_offset_y))
        wheel_half_width = max(0.8, self._meters_to_world_units(map_manager, float(getattr(entity, 'wheel_radius_m', 0.08)) * 0.32))
        for local_x, local_y in wheel_positions:
            self._append_box_faces(
                faces,
                box_corners(local_x, local_y, max(1.0, wheel_radius_world * 0.82), wheel_half_width, wheel_bottom, wheel_top, yaw_rad),
                tuple(max(26, min(180, int(channel * 0.78))) for channel in wheel_color),
            )
            if suspension_style == 'five_link':
                support_low = body_bottom + 0.02
                support_high = wheel_top - wheel_radius_height * 0.10
                link_half = self._meters_to_world_units(map_manager, 0.018)
                self._append_box_faces(faces, box_corners(local_x, local_y * 0.72, link_half, link_half, support_low, support_high, yaw_rad), (108, 112, 122))
                for offset_x in (-0.055, 0.055):
                    self._append_box_faces(
                        faces,
                        box_corners(
                            local_x + self._meters_to_world_units(map_manager, offset_x),
                            local_y * 0.88,
                            self._meters_to_world_units(map_manager, 0.012),
                            self._meters_to_world_units(map_manager, 0.060),
                            support_high - 0.08,
                            support_high - 0.01,
                            yaw_rad,
                        ),
                        (118, 122, 132),
                    )

        climb_assist = self._climb_assist_animation_state(entity)
        assist_side_offset = max(1.0, body_width_half + wheel_half_width * 0.45)
        if front_climb_style != 'none':
            plate_half_x = self._meters_to_world_units(map_manager, float(getattr(entity, 'front_climb_assist_plate_length_m', 0.05)) * 0.5)
            plate_half_y = self._meters_to_world_units(map_manager, float(getattr(entity, 'front_climb_assist_plate_width_m', 0.018)) * 0.5)
            plate_height = float(getattr(entity, 'front_climb_assist_plate_height_m', 0.18)) * vertical_scale
            plate_center_x = body_length_half + self._meters_to_world_units(map_manager, float(getattr(entity, 'front_climb_assist_forward_offset_m', 0.04))) + plate_half_x
            plate_inner_offset = self._meters_to_world_units(map_manager, float(getattr(entity, 'front_climb_assist_inner_offset_m', 0.06)) * render_width_scale)
            mount_half_x = max(self._meters_to_world_units(map_manager, 0.012), plate_half_x * 0.55)
            mount_half_y = max(self._meters_to_world_units(map_manager, 0.010), plate_half_y * 1.15)
            plate_low = max(terrain_height, body_bottom - float(climb_assist['front_drop_m']) * vertical_scale)
            plate_high = max(plate_low + 0.03, plate_low + plate_height + float(climb_assist['front_raise_m']) * vertical_scale * 0.45)
            mount_low = body_top - 0.010 * vertical_scale
            mount_high = body_top + 0.040 * vertical_scale
            for side_sign in (-1.0, 1.0):
                side_y = max(body_width_half * 0.45, assist_side_offset - plate_inner_offset) * side_sign
                self._append_box_faces(
                    faces,
                    box_corners(body_length_half * 0.78, side_y, mount_half_x, mount_half_y, mount_low, mount_high, yaw_rad),
                    (118, 122, 132),
                )
                self._append_box_faces(
                    faces,
                    box_corners(plate_center_x, side_y, plate_half_x, plate_half_y, plate_low, plate_high, yaw_rad),
                    (82, 86, 96),
                )
        if rear_climb_style != 'none':
            upper_half_x = self._meters_to_world_units(map_manager, float(getattr(entity, 'rear_climb_assist_upper_length_m', 0.09)) * 0.5)
            lower_half_x = self._meters_to_world_units(map_manager, float(getattr(entity, 'rear_climb_assist_lower_length_m', 0.08)) * 0.5)
            bar_half_y = self._meters_to_world_units(map_manager, float(getattr(entity, 'rear_climb_assist_bar_width_m', 0.016)) * 0.5)
            upper_offset = self._meters_to_world_units(map_manager, float(getattr(entity, 'rear_climb_assist_upper_offset_m', 0.055)))
            lower_offset = self._meters_to_world_units(map_manager, float(getattr(entity, 'rear_climb_assist_lower_offset_m', 0.015)))
            rear_inner_offset = self._meters_to_world_units(map_manager, float(getattr(entity, 'rear_climb_assist_inner_offset_m', 0.03)) * render_width_scale)
            upper_center_x = -body_length_half - upper_offset + upper_half_x * 0.25
            lower_center_x = -body_length_half - lower_offset + lower_half_x * 0.25 + self._meters_to_world_units(map_manager, float(climb_assist['rear_reach_m']) * 0.25)
            upper_low = body_top + 0.008 * vertical_scale
            upper_high = upper_low + max(0.012, float(getattr(entity, 'rear_climb_assist_bar_width_m', 0.016)) * vertical_scale)
            lower_low = max(terrain_height, body_bottom - float(climb_assist['rear_drop_m']) * vertical_scale)
            lower_high = lower_low + max(0.012, float(getattr(entity, 'rear_climb_assist_bar_width_m', 0.016)) * vertical_scale)
            connector_center_x = (upper_center_x + lower_center_x) * 0.5
            connector_half_x = max(self._meters_to_world_units(map_manager, 0.010), abs(upper_center_x - lower_center_x) * 0.5 + bar_half_y)
            connector_half_y = max(self._meters_to_world_units(map_manager, 0.008), bar_half_y * 0.9)
            connector_low = min(lower_high, upper_low)
            connector_high = max(lower_high, upper_low + max(0.018, float(getattr(entity, 'rear_climb_assist_bar_width_m', 0.016)) * vertical_scale * 1.2))
            for side_sign in (-1.0, 1.0):
                side_y = max(body_width_half * 0.45, assist_side_offset - rear_inner_offset) * side_sign
                self._append_box_faces(
                    faces,
                    box_corners(upper_center_x, side_y, upper_half_x, bar_half_y, upper_low, upper_high, yaw_rad),
                    (106, 110, 120),
                )
                self._append_box_faces(
                    faces,
                    box_corners(lower_center_x, side_y, lower_half_x, bar_half_y, lower_low, lower_high, yaw_rad),
                    (92, 96, 108),
                )
                self._append_box_faces(
                    faces,
                    box_corners(connector_center_x, side_y, connector_half_x, connector_half_y, connector_low, connector_high, yaw_rad),
                    (116, 120, 132),
                )

        if arm_style == 'fixed_7':
            arm_low = body_top
            arm_high = body_top + 0.50 * vertical_scale
            self._append_box_faces(
                faces,
                box_corners(0.0, 0.0, self._meters_to_world_units(map_manager, 0.05), self._meters_to_world_units(map_manager, 0.05), arm_low, arm_high, yaw_rad),
                (172, 176, 184),
            )
            self._append_box_faces(
                faces,
                box_corners(body_length_half * 0.18, 0.0, self._meters_to_world_units(map_manager, 0.22), self._meters_to_world_units(map_manager, 0.05), arm_high - 0.10 * vertical_scale, arm_high, yaw_rad),
                (188, 192, 198),
            )

        armor_plate_half_width = max(1.0, self._meters_to_world_units(map_manager, float(getattr(entity, 'armor_plate_width_m', getattr(entity, 'armor_plate_size_m', 0.12))) * 0.5))
        armor_plate_half_length = max(1.0, self._meters_to_world_units(map_manager, float(getattr(entity, 'armor_plate_length_m', getattr(entity, 'armor_plate_size_m', 0.12))) * 0.5))
        armor_plate_half_height = max(0.05, float(getattr(entity, 'armor_plate_height_m', getattr(entity, 'armor_plate_size_m', 0.12))) * 0.5 * vertical_scale)
        armor_thickness = max(0.8, self._meters_to_world_units(map_manager, float(getattr(entity, 'armor_plate_gap_m', 0.02))) + min(armor_plate_half_width, armor_plate_half_length) * 0.08)
        armor_center_h = body_bottom + (body_top - body_bottom) * 0.54
        armor_low = armor_center_h - armor_plate_half_height
        armor_high = armor_center_h + armor_plate_half_height
        armor_offset_x = body_length_half + armor_thickness * 1.35
        armor_offset_y = body_width_half + armor_thickness * 1.35
        light_half_len = max(0.4, self._meters_to_world_units(map_manager, float(getattr(entity, 'armor_light_length_m', 0.10)) * 0.5))
        light_half_width = max(0.2, self._meters_to_world_units(map_manager, float(getattr(entity, 'armor_light_width_m', 0.02)) * 0.5))
        light_half_height = max(0.01, float(getattr(entity, 'armor_light_height_m', 0.02)) * 0.5 * vertical_scale)
        light_color = tuple(max(96, min(255, int(channel * 0.95 + 22))) for channel in team_color)
        armor_specs = (
            (armor_offset_x, 0.0, armor_thickness, armor_plate_half_width),
            (-armor_offset_x, 0.0, armor_thickness, armor_plate_half_width),
            (0.0, armor_offset_y, armor_plate_half_length, armor_thickness),
            (0.0, -armor_offset_y, armor_plate_half_length, armor_thickness),
        )
        for local_x, local_y, half_x, half_y in armor_specs:
            self._append_box_faces(faces, box_corners(local_x, local_y, half_x, half_y, armor_low, armor_high, yaw_rad), armor_color)
            if abs(local_x) > abs(local_y):
                self._append_box_faces(faces, box_corners(local_x, local_y + armor_plate_half_width + light_half_width, light_half_len, light_half_width, armor_center_h - light_half_height, armor_center_h + light_half_height, yaw_rad), light_color)
                self._append_box_faces(faces, box_corners(local_x, local_y - armor_plate_half_width - light_half_width, light_half_len, light_half_width, armor_center_h - light_half_height, armor_center_h + light_half_height, yaw_rad), light_color)
            else:
                self._append_box_faces(faces, box_corners(local_x + armor_plate_half_length + light_half_width, local_y, light_half_width, light_half_len, armor_center_h - light_half_height, armor_center_h + light_half_height, yaw_rad), light_color)
                self._append_box_faces(faces, box_corners(local_x - armor_plate_half_length - light_half_width, local_y, light_half_width, light_half_len, armor_center_h - light_half_height, armor_center_h + light_half_height, yaw_rad), light_color)

        barrel_start = None
        barrel_end = None
        barrel_light_segments = []
        if has_turret:
            turret_half_x = max(1.2, self._meters_to_world_units(map_manager, float(getattr(entity, 'gimbal_length_m', 0.30)) * 0.5))
            turret_half_y = max(0.9, self._meters_to_world_units(map_manager, float(getattr(entity, 'gimbal_width_m', 0.10)) * 0.5))
            turret_half_h = max(0.04, float(getattr(entity, 'gimbal_body_height_m', 0.10)) * 0.5 * vertical_scale)
            turret_center_h = base_height + float(getattr(entity, 'gimbal_height_m', 0.50)) * vertical_scale
            turret_offset_x = self._meters_to_world_units(map_manager, float(getattr(entity, 'gimbal_offset_x_m', 0.0)))
            turret_offset_y = self._meters_to_world_units(map_manager, float(getattr(entity, 'gimbal_offset_y_m', 0.0)))
            if has_mount:
                mount_half_x = max(0.5, self._meters_to_world_units(map_manager, float(getattr(entity, 'gimbal_mount_length_m', 0.10)) * 0.5))
                mount_half_y = max(0.5, self._meters_to_world_units(map_manager, float(getattr(entity, 'gimbal_mount_width_m', 0.10)) * 0.5 * render_width_scale))
                mount_half_h = max(0.03, float(getattr(entity, 'gimbal_mount_height_m', getattr(entity, 'gimbal_mount_gap_m', 0.10))) * 0.5 * vertical_scale)
                mount_center_h = body_top + mount_half_h
                self._append_box_faces(
                    faces,
                    box_corners(turret_offset_x, turret_offset_y, mount_half_x, mount_half_y, mount_center_h - mount_half_h, mount_center_h + mount_half_h, yaw_rad),
                    (96, 100, 112),
                )
            self._append_box_faces(
                faces,
                box_corners(turret_offset_x, turret_offset_y, turret_half_x, turret_half_y, turret_center_h - turret_half_h, turret_center_h + turret_half_h, turret_yaw_rad),
                turret_base_color,
            )
            if has_barrel:
                barrel_start = self._project_scene_point(local_to_scene(turret_offset_x, turret_offset_y, turret_center_h, turret_yaw_rad), camera_state, rect)
                barrel_length_m = float(getattr(entity, 'barrel_length_m', 0.36))
                barrel_pitch_rad = math.radians(float(getattr(entity, 'gimbal_pitch_deg', 0.0)))
                barrel_horizontal = self._meters_to_world_units(map_manager, barrel_length_m * max(0.0, math.cos(barrel_pitch_rad)))
                barrel_vertical = barrel_length_m * math.sin(barrel_pitch_rad) * vertical_scale
                barrel_end = self._project_scene_point(
                    local_to_scene(
                        turret_offset_x + barrel_horizontal,
                        turret_offset_y,
                        turret_center_h + barrel_vertical,
                        turret_yaw_rad,
                    ),
                    camera_state,
                    rect,
                )
                light_width_world = self._meters_to_world_units(map_manager, float(getattr(entity, 'barrel_light_width_m', 0.02)))
                if barrel_start is not None and barrel_end is not None and light_width_world > 0.0:
                    lateral_start = self._project_scene_point(local_to_scene(turret_offset_x, turret_offset_y + light_width_world, turret_center_h, turret_yaw_rad), camera_state, rect)
                    lateral_end = self._project_scene_point(local_to_scene(turret_offset_x + barrel_horizontal, turret_offset_y + light_width_world, turret_center_h + barrel_vertical, turret_yaw_rad), camera_state, rect)
                    if lateral_start is not None and lateral_end is not None:
                        offset_start = np.array([lateral_start[0] - barrel_start[0], lateral_start[1] - barrel_start[1]], dtype='f4')
                        offset_end = np.array([lateral_end[0] - barrel_end[0], lateral_end[1] - barrel_end[1]], dtype='f4')
                        barrel_light_segments.append(((int(barrel_start[0] + offset_start[0]), int(barrel_start[1] + offset_start[1])), (int(barrel_end[0] + offset_end[0]), int(barrel_end[1] + offset_end[1])), light_color))
                        barrel_light_segments.append(((int(barrel_start[0] - offset_start[0]), int(barrel_start[1] - offset_start[1])), (int(barrel_end[0] - offset_end[0]), int(barrel_end[1] - offset_end[1])), light_color))
        return faces, barrel_start, barrel_end, wheel_positions, wheel_radius_world, wheel_radius_height, base_height, barrel_light_segments, wheel_color

    def _build_entity_wheel_overlays(self, entity, camera_state, rect, map_manager, sample_data, wheel_positions, wheel_radius_world, wheel_radius_height, base_height, game_time, wheel_color):
        if not wheel_positions:
            return []
        wheel_style = str(getattr(entity, 'wheel_style', 'standard'))
        center_scene, forward_basis, right_basis, up_basis = self._entity_scene_axes(entity, map_manager, sample_data, base_height)
        def local_to_scene(local_x, local_y, height_m):
            scene_xyz = center_scene + forward_basis * local_x + right_basis * local_y + up_basis * (float(height_m) - base_height)
            return np.array([scene_xyz[0], scene_xyz[1], scene_xyz[2], 1.0], dtype='f4')

        velocity = getattr(entity, 'velocity', {}) or {}
        speed_world = math.hypot(float(velocity.get('vx', 0.0)), float(velocity.get('vy', 0.0)))
        spin_phase = (speed_world / max(wheel_radius_world, 1e-6)) * float(game_time)
        side_offset = max(0.4, self._meters_to_world_units(map_manager, float(getattr(entity, 'wheel_radius_m', 0.08)) * 0.35))
        overlays = []
        for local_x, local_y in wheel_positions:
            wheel_center_h = base_height + wheel_radius_height
            center = self._project_scene_point(local_to_scene(local_x, local_y, wheel_center_h), camera_state, rect)
            axis_a = self._project_scene_point(local_to_scene(local_x, local_y + side_offset, wheel_center_h), camera_state, rect)
            axis_b = self._project_scene_point(local_to_scene(local_x, local_y, wheel_center_h + wheel_radius_height), camera_state, rect)
            if center is None or axis_a is None or axis_b is None:
                continue
            vec_a = np.array([axis_a[0] - center[0], axis_a[1] - center[1]], dtype='f4')
            vec_b = np.array([axis_b[0] - center[0], axis_b[1] - center[1]], dtype='f4')
            polygon = []
            for sample_index in range(16):
                angle = (math.pi * 2.0 * sample_index) / 16.0
                point = np.array([center[0], center[1]], dtype='f4') + vec_a * math.cos(angle) + vec_b * math.sin(angle)
                polygon.append((int(point[0]), int(point[1])))
            spoke_pairs = []
            for angle in (spin_phase, spin_phase + math.pi * 0.5):
                start = np.array([center[0], center[1]], dtype='f4') + vec_a * math.cos(angle) + vec_b * math.sin(angle)
                end = np.array([center[0], center[1]], dtype='f4') - vec_a * math.cos(angle) - vec_b * math.sin(angle)
                spoke_pairs.append(((int(start[0]), int(start[1])), (int(end[0]), int(end[1]))))
            overlays.append((float(center[2]), polygon, spoke_pairs, wheel_style, wheel_color))
        return overlays

    def _render_player_models(self, game_engine, rect, camera_state):
        map_manager = game_engine.map_manager
        sample_data = camera_state.get('sample_data') or {}
        faces = []
        barrel_segments = []
        barrel_light_segments = []
        controlled_getter = getattr(game_engine, 'get_player_controlled_entity', None)
        controlled = controlled_getter() if callable(controlled_getter) else None
        controlled_id = getattr(controlled, 'id', None)
        camera_mode = str(camera_state.get('camera_mode', 'first_person'))
        for entity in game_engine.entity_manager.entities:
            if not entity.is_alive() or entity.type not in {'robot', 'sentry'}:
                continue
            if controlled_id is not None and entity.id == controlled_id and camera_mode != 'third_person':
                continue
            if not self._entity_visible_from_camera(entity, map_manager, camera_state):
                continue
            entity_faces, barrel_start, barrel_end, wheel_positions, wheel_radius_world, wheel_radius_height, base_height, light_segments, wheel_color = self._build_entity_model_faces(entity, camera_state, rect, map_manager, sample_data)
            faces.extend(entity_faces)
            if barrel_start is not None and barrel_end is not None:
                barrel_segments.append((barrel_start, barrel_end))
            barrel_light_segments.extend(light_segments)

        faces.sort(key=lambda item: item[0], reverse=True)
        for _, polygon, color in faces:
            if len(polygon) < 3:
                continue
            pygame.draw.polygon(self.screen, color, polygon)
            pygame.draw.polygon(self.screen, self.colors['black'], polygon, 1)
        for start, end in barrel_segments:
            pygame.draw.line(self.screen, self.colors['black'], start[:2], end[:2], 2)
        for start, end, color in barrel_light_segments:
            pygame.draw.line(self.screen, color, start, end, 2)

    def _render_player_projectiles(self, game_engine, rect, camera_state):
        rules_engine = getattr(game_engine, 'rules_engine', None)
        traces = list(getattr(rules_engine, 'projectile_traces', ())) if rules_engine is not None else []
        if not traces:
            return
        map_manager = game_engine.map_manager
        sample_data = camera_state.get('sample_data') or {}
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        drawables = []
        eye = np.array(camera_state.get('eye', (0.0, 0.0, 0.0)), dtype='f4')
        for trace in traces:
            trace_points = self._trace_path_points(trace, map_manager)
            if len(trace_points) < 2:
                continue
            polyline, max_depth = self._project_trace_polyline(trace_points, map_manager, sample_data, camera_state, rect)
            if len(polyline) < 2:
                continue
            lifetime = max(1e-6, float(trace.get('lifetime', 0.12)))
            progress = max(0.0, min(1.0, float(trace.get('elapsed', 0.0)) / lifetime))
            tail_progress = max(0.0, progress - (0.22 if trace.get('ammo_type') == '42mm' else 0.14))

            def interpolate(progress_value):
                point = self._trace_point_at_progress(trace_points, progress_value)
                if point is None:
                    return None, None
                world_x, world_y, world_h = point
                scene_point = self._world_to_scene_point(map_manager, sample_data, world_x, world_y, world_h)
                projected = self._project_scene_point(scene_point, camera_state, rect)
                return projected, scene_point[:3]

            tip, tip_scene = interpolate(progress)
            tail, _ = interpolate(tail_progress)
            if tip is None:
                continue
            ammo_type = trace.get('ammo_type')
            is_large = ammo_type == '42mm'
            distance = max(0.75, float(np.linalg.norm(tip_scene - eye)))
            radius = int(max(3, min(20, (10.5 if is_large else 7.5) / distance * 10.0)))
            width = max(1, radius - 1)
            color = (255, 170, 74) if is_large else (255, 242, 170)
            glow = (255, 118, 54, 180) if is_large else (255, 248, 208, 150)
            team = trace.get('team')
            if team == 'blue' and not is_large:
                color = (198, 236, 255)
                glow = (120, 190, 255, 150)
            drawables.append((max_depth if max_depth is not None else tip[2], polyline, tip, tail, radius, width, color, glow))

        drawables.sort(key=lambda item: item[0], reverse=True)
        for _, polyline, tip, tail, radius, width, color, glow in drawables:
            if len(polyline) >= 2:
                pygame.draw.lines(overlay, (glow[0], glow[1], glow[2], min(176, glow[3])), False, polyline, max(2, width + 1))
                pygame.draw.lines(overlay, (*color, 180), False, polyline, max(1, width // 2))
            tip_pos = (int(tip[0] - rect.x), int(tip[1] - rect.y))
            if tail is not None:
                tail_pos = (int(tail[0] - rect.x), int(tail[1] - rect.y))
                pygame.draw.line(overlay, glow, tail_pos, tip_pos, max(1, width + 2))
                pygame.draw.line(overlay, (*color, 220), tail_pos, tip_pos, width)
            pygame.draw.circle(overlay, glow, tip_pos, radius + 2)
            pygame.draw.circle(overlay, (*color, 245), tip_pos, radius)
            pygame.draw.circle(overlay, (255, 255, 255, 220), tip_pos, max(1, radius // 2))
        self.screen.blit(overlay, rect.topleft)

    def _render_player_status_hud(self, game_engine, rect):
        hud = game_engine.get_player_hud_data()
        if hud is None:
            return
        panel_rect = pygame.Rect(rect.x + 18, rect.bottom - 138, 420, 118)
        pygame.draw.rect(self.screen, (18, 24, 30), panel_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=10)
        lines = [
            f'{hud["label"]} {hud["robot_type"]}',
            f'发弹量 {hud["ammo"]}   底盘功率 {hud["power"]:.1f}/{hud["max_power"]:.1f}',
            f'枪口热量 {hud["heat"]:.1f}/{hud["max_heat"]:.1f}   俯仰 {hud["pitch_deg"]:.1f}°',
            f'右键自瞄 {"锁定" if hud["auto_aim_locked"] else "待机"}   左键射击 {hud["fire_control_state"]}',
            f'视角 {"第三人称" if self.player_camera_mode == "third_person" else "第一人称"}   V 切换   F3 碰撞箱/坐标/轮高',
        ]
        if hud['supply_zone']:
            lines.append(f'补给区内 按 B 打开购买面板 当前数量 {self.player_purchase_amount} 发')
        draw_y = panel_rect.y + 10
        for line in lines:
            text = self.small_font.render(line, True, self.colors['white'])
            self.screen.blit(text, (panel_rect.x + 12, draw_y))
            draw_y += 18
        crosshair_center = (rect.centerx, rect.centery)
        pygame.draw.line(self.screen, self.colors['white'], (crosshair_center[0] - 12, crosshair_center[1]), (crosshair_center[0] + 12, crosshair_center[1]), 1)
        pygame.draw.line(self.screen, self.colors['white'], (crosshair_center[0], crosshair_center[1] - 12), (crosshair_center[0], crosshair_center[1] + 12), 1)

    def _render_player_purchase_menu(self, game_engine, rect):
        if not self.player_purchase_menu_open:
            return
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 96))
        self.screen.blit(overlay, rect.topleft)
        panel_rect = pygame.Rect(0, 0, 520, 238)
        panel_rect.center = rect.center
        pygame.draw.rect(self.screen, (24, 31, 38), panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=12)
        title = self.font.render('补给购买', True, self.colors['white'])
        self.screen.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.y + 28)))
        amount_rect = pygame.Rect(panel_rect.centerx - 70, panel_rect.y + 66, 140, 42)
        pygame.draw.rect(self.screen, (34, 40, 48), amount_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.colors['panel_border'], amount_rect, 1, border_radius=10)
        amount_text = self.font.render(str(int(max(1, self.player_purchase_amount))), True, self.colors['white'])
        self.screen.blit(amount_text, amount_text.get_rect(center=amount_rect.center))

        left_deltas = (-1, -10, -50, -100)
        right_deltas = (1, 10, 50, 100)
        for index, delta in enumerate(left_deltas):
            button_rect = pygame.Rect(panel_rect.x + 28, panel_rect.y + 56 + index * 36, 108, 28)
            pygame.draw.rect(self.screen, self.colors['toolbar_button'], button_rect, border_radius=8)
            label = self.small_font.render(str(delta), True, self.colors['white'])
            self.screen.blit(label, label.get_rect(center=button_rect.center))
            self.panel_actions.append((button_rect, f'player_purchase_delta:{delta}'))
        for index, delta in enumerate(right_deltas):
            button_rect = pygame.Rect(panel_rect.right - 136, panel_rect.y + 56 + index * 36, 108, 28)
            pygame.draw.rect(self.screen, self.colors['toolbar_button'], button_rect, border_radius=8)
            label = self.small_font.render(f'+{delta}', True, self.colors['white'])
            self.screen.blit(label, label.get_rect(center=button_rect.center))
            self.panel_actions.append((button_rect, f'player_purchase_delta:{delta}'))

        confirm_rect = pygame.Rect(panel_rect.x + 54, panel_rect.bottom - 54, 168, 36)
        cancel_rect = pygame.Rect(panel_rect.right - 222, panel_rect.bottom - 54, 168, 36)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], confirm_rect, border_radius=10)
        pygame.draw.rect(self.screen, (70, 76, 88), cancel_rect, border_radius=10)
        self.screen.blit(self.small_font.render('确认买弹', True, self.colors['white']), self.small_font.render('确认买弹', True, self.colors['white']).get_rect(center=confirm_rect.center))
        self.screen.blit(self.small_font.render('取消买弹', True, self.colors['white']), self.small_font.render('取消买弹', True, self.colors['white']).get_rect(center=cancel_rect.center))
        hint = self.tiny_font.render('打开面板后仍可继续驾驶，购买数量通过按钮微调', True, self.colors['white'])
        self.screen.blit(hint, hint.get_rect(center=(panel_rect.centerx, panel_rect.bottom - 82)))
        self.panel_actions.append((confirm_rect, 'player_purchase_confirm'))
        self.panel_actions.append((cancel_rect, 'player_purchase_cancel'))

    def _render_player_settings_menu(self, game_engine, rect):
        if not self.player_settings_menu_open:
            return
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, rect.topleft)
        panel_rect = pygame.Rect(0, 0, 420, 264)
        panel_rect.center = rect.center
        pygame.draw.rect(self.screen, (28, 34, 42), panel_rect, border_radius=16)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=16)
        title = self.font.render('控制设置', True, self.colors['white'])
        self.screen.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.y + 28)))
        sensitivities = game_engine.get_player_sensitivity_settings()
        rows = (
            ('水平灵敏度', 'yaw', sensitivities['yaw']),
            ('垂直灵敏度', 'pitch', sensitivities['pitch']),
        )
        for index, (label, axis, value) in enumerate(rows):
            row_y = panel_rect.y + 64 + index * 56
            self.screen.blit(self.small_font.render(label, True, self.colors['white']), (panel_rect.x + 34, row_y + 8))
            minus_rect = pygame.Rect(panel_rect.x + 168, row_y, 36, 30)
            value_rect = pygame.Rect(panel_rect.x + 214, row_y, 92, 30)
            plus_rect = pygame.Rect(panel_rect.x + 316, row_y, 36, 30)
            for draw_rect, text_value in ((minus_rect, '-'), (plus_rect, '+')):
                pygame.draw.rect(self.screen, self.colors['toolbar_button'], draw_rect, border_radius=8)
                rendered = self.small_font.render(text_value, True, self.colors['white'])
                self.screen.blit(rendered, rendered.get_rect(center=draw_rect.center))
            pygame.draw.rect(self.screen, (38, 44, 54), value_rect, border_radius=8)
            pygame.draw.rect(self.screen, self.colors['panel_border'], value_rect, 1, border_radius=8)
            value_text = self.small_font.render(f'{value:.2f}', True, self.colors['white'])
            self.screen.blit(value_text, value_text.get_rect(center=value_rect.center))
            self.panel_actions.append((minus_rect, f'player_sensitivity:{axis}:-0.01'))
            self.panel_actions.append((plus_rect, f'player_sensitivity:{axis}:0.01'))
        close_rect = pygame.Rect(panel_rect.centerx - 84, panel_rect.bottom - 48, 168, 34)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], close_rect, border_radius=10)
        self.screen.blit(self.small_font.render('关闭设置', True, self.colors['white']), self.small_font.render('关闭设置', True, self.colors['white']).get_rect(center=close_rect.center))
        self.panel_actions.append((close_rect, 'toggle_player_settings'))

    def _render_pre_match_prompt(self, game_engine, rect):
        if not getattr(game_engine, 'pre_match_setup_required', False) and float(getattr(game_engine, 'pre_match_countdown_remaining', 0.0)) <= 0.0:
            return
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 88))
        self.screen.blit(overlay, rect.topleft)
        if float(getattr(game_engine, 'pre_match_countdown_remaining', 0.0)) > 0.0:
            remaining = max(0, int(math.ceil(float(getattr(game_engine, 'pre_match_countdown_remaining', 0.0)))))
            title = self.hud_big_font.render(str(remaining), True, self.colors['white'])
            subtitle = self.hud_mid_font.render('比赛开始', True, self.colors['white'])
            self.screen.blit(title, title.get_rect(center=(rect.centerx, rect.centery - 12)))
            self.screen.blit(subtitle, subtitle.get_rect(center=(rect.centerx, rect.centery + 34)))
            return
        title = self.hud_mid_font.render('需要配置机器人参数：请按 P 设置', True, self.colors['white'])
        self.screen.blit(title, title.get_rect(center=(rect.centerx, rect.centery - 18)))
        hint = self.small_font.render('配置完成后进入 5 秒倒计时，期间所有机器人保持静止', True, (220, 225, 232))
        self.screen.blit(hint, hint.get_rect(center=(rect.centerx, rect.centery + 18)))

    def _render_pre_match_config_menu(self, game_engine, rect):
        if not self.pre_match_config_menu_open:
            return
        entity = game_engine.get_player_controlled_entity() if hasattr(game_engine, 'get_player_controlled_entity') else None
        if entity is None:
            return
        detail = game_engine.get_entity_detail_data(entity.id)
        if detail is None:
            return
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 132))
        self.screen.blit(overlay, rect.topleft)
        panel_rect = pygame.Rect(0, 0, 560, 260)
        panel_rect.center = rect.center
        pygame.draw.rect(self.screen, (28, 34, 42), panel_rect, border_radius=16)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=16)
        title = self.font.render(f'赛前参数配置 | {detail.get("label", entity.id)} {detail.get("robot_type", "")}', True, self.colors['white'])
        self.screen.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.y + 28)))

        mode_labels = detail.get('mode_labels', {})
        left_title = mode_labels.get('left_title', '底盘模式')
        right_title = mode_labels.get('right_title', '云台模式')
        left_options = mode_labels.get('left_options', [('health_priority', '血量优先'), ('power_priority', '功率优先')])
        right_options = mode_labels.get('right_options', [('cooling_priority', '冷却优先'), ('burst_priority', '爆发优先')])
        left_y = panel_rect.y + 82
        right_y = panel_rect.y + 154
        self.screen.blit(self.small_font.render(left_title, True, self.colors['white']), (panel_rect.x + 42, left_y - 24))
        self.screen.blit(self.small_font.render(right_title, True, self.colors['white']), (panel_rect.x + 42, right_y - 24))
        button_w = 188
        gap = 18
        for index, (value, label) in enumerate(left_options[:2]):
            button_rect = pygame.Rect(panel_rect.x + 42 + index * (button_w + gap), left_y, button_w, 40)
            active = detail.get('chassis_mode') == value
            pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if active else self.colors['toolbar_button'], button_rect, border_radius=10)
            rendered = self.small_font.render(label, True, self.colors['white'])
            self.screen.blit(rendered, rendered.get_rect(center=button_rect.center))
            self.panel_actions.append((button_rect, f'entity_mode:{entity.id}:chassis_mode:{value}'))
        for index, (value, label) in enumerate(right_options[:2]):
            button_rect = pygame.Rect(panel_rect.x + 42 + index * (button_w + gap), right_y, button_w, 40)
            active = detail.get('gimbal_mode') == value
            pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if active else self.colors['toolbar_button'], button_rect, border_radius=10)
            rendered = self.small_font.render(label, True, self.colors['white'])
            self.screen.blit(rendered, rendered.get_rect(center=button_rect.center))
            self.panel_actions.append((button_rect, f'entity_mode:{entity.id}:gimbal_mode:{value}'))

        confirm_rect = pygame.Rect(panel_rect.x + 72, panel_rect.bottom - 54, 170, 36)
        cancel_rect = pygame.Rect(panel_rect.right - 242, panel_rect.bottom - 54, 170, 36)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], confirm_rect, border_radius=10)
        pygame.draw.rect(self.screen, (70, 76, 88), cancel_rect, border_radius=10)
        self.screen.blit(self.small_font.render('确认并开始倒计时', True, self.colors['white']), self.small_font.render('确认并开始倒计时', True, self.colors['white']).get_rect(center=confirm_rect.center))
        self.screen.blit(self.small_font.render('取消', True, self.colors['white']), self.small_font.render('取消', True, self.colors['white']).get_rect(center=cancel_rect.center))
        self.panel_actions.append((confirm_rect, 'pre_match_confirm'))
        self.panel_actions.append((cancel_rect, 'pre_match_cancel'))

    def _render_player_pause_overlay(self, game_engine, rect):
        scene_snapshot = self.screen.subsurface(rect).copy()
        rgb = pygame.surfarray.pixels3d(scene_snapshot)
        luminance = (rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114).astype(np.uint8)
        rgb[:, :, 0] = luminance
        rgb[:, :, 1] = luminance
        rgb[:, :, 2] = luminance
        del rgb
        self.screen.blit(scene_snapshot, rect.topleft)

        veil = pygame.Surface(rect.size, pygame.SRCALPHA)
        veil.fill((18, 22, 28, 138))
        self.screen.blit(veil, rect.topleft)

        panel_rect = pygame.Rect(0, 0, 420, 214)
        panel_rect.center = (rect.centerx, rect.centery + 24)
        pygame.draw.rect(self.screen, (32, 38, 46), panel_rect, border_radius=20)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=20)

        title = self.hud_mid_font.render('比赛已暂停', True, self.colors['white'])
        self.screen.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.y + 34)))
        hint = self.small_font.render('鼠标已释放，可选择继续比赛或重新开始', True, (208, 214, 220))
        self.screen.blit(hint, hint.get_rect(center=(panel_rect.centerx, panel_rect.y + 66)))

        settings_rect = pygame.Rect(panel_rect.x + 34, panel_rect.bottom - 132, panel_rect.width - 68, 34)
        restart_rect = pygame.Rect(panel_rect.x + 34, panel_rect.bottom - 82, 156, 42)
        resume_rect = pygame.Rect(panel_rect.right - 190, panel_rect.bottom - 82, 156, 42)
        pygame.draw.rect(self.screen, (78, 86, 98), settings_rect, border_radius=10)
        pygame.draw.rect(self.screen, (83, 92, 104), restart_rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], resume_rect, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], settings_rect, 1, border_radius=10)
        pygame.draw.rect(self.screen, self.colors['panel_border'], restart_rect, 1, border_radius=12)
        pygame.draw.rect(self.screen, self.colors['panel_border'], resume_rect, 1, border_radius=12)

        settings_text = self.small_font.render('设置', True, self.colors['white'])
        restart_text = self.small_font.render('重新开始', True, self.colors['white'])
        resume_text = self.small_font.render('继续比赛', True, self.colors['white'])
        self.screen.blit(settings_text, settings_text.get_rect(center=settings_rect.center))
        self.screen.blit(restart_text, restart_text.get_rect(center=restart_rect.center))
        self.screen.blit(resume_text, resume_text.get_rect(center=resume_rect.center))

        esc_hint = self.tiny_font.render('也可以按 ESC 继续', True, (198, 204, 210))
        self.screen.blit(esc_hint, esc_hint.get_rect(center=(panel_rect.centerx, panel_rect.bottom - 20)))

        self.panel_actions.append((settings_rect, 'toggle_player_settings'))
        self.panel_actions.append((restart_rect, 'start_match'))
        self.panel_actions.append((resume_rect, 'toggle_pause'))

    def render_player_simulator(self, game_engine, top_offset=None, hud_top=None, draw_match_hud=False):
        rect_top = self.toolbar_height if top_offset is None else int(top_offset)
        hud_offset = self.toolbar_height if hud_top is None else int(hud_top)
        rect = pygame.Rect(0, rect_top, self.window_width, self.window_height - rect_top)
        pygame.draw.rect(self.screen, (10, 14, 18), rect)
        controlled_getter = getattr(game_engine, 'get_player_controlled_entity', None)
        entity = controlled_getter() if callable(controlled_getter) else None
        if entity is None:
            self._sync_player_mouse_capture(False)
            return
        menus_active = self.player_purchase_menu_open or self.player_settings_menu_open or self.pre_match_config_menu_open
        self._sync_player_mouse_capture((not game_engine.paused) and (not menus_active))
        self.terrain_scene_camera_override = self._build_player_camera_override(game_engine, rect)
        motion_metric_m = self._player_camera_motion_metric_m(game_engine.map_manager, self.terrain_scene_camera_override)
        self._active_player_terrain_render_scale = self.player_motion_terrain_render_scale if motion_metric_m > self.player_camera_motion_threshold_m else self.player_terrain_render_scale
        self.terrain_scene_force_dark_gray = False
        terrain_surface = self._render_terrain_scene_surface(game_engine, rect, self._get_terrain_3d_map_rgb(game_engine.map_manager))
        self.terrain_scene_force_dark_gray = False
        self.screen.blit(terrain_surface, rect.topleft)
        if self.terrain_scene_camera_override is not None:
            camera_mode_setter = getattr(game_engine, 'set_player_camera_mode', None)
            if callable(camera_mode_setter):
                camera_mode_setter(self.player_camera_mode)
            view_aim_state = self._resolve_player_view_aim_state(game_engine, self.terrain_scene_camera_override)
            setter = getattr(game_engine, 'set_player_view_aim_state', None)
            if callable(setter):
                setter(view_aim_state)
            self._render_player_models(game_engine, rect, self.terrain_scene_camera_override)
            self._render_player_projectiles(game_engine, rect, self.terrain_scene_camera_override)
            self._render_player_view_ray(rect, self.terrain_scene_camera_override, view_aim_state, game_engine.map_manager, self.terrain_scene_camera_override.get('sample_data') or {})
            if self._collision_overlay_active():
                self._render_player_collision_boxes(game_engine, rect, self.terrain_scene_camera_override)
        self.terrain_scene_camera_override = None
        self._active_player_terrain_render_scale = self.player_terrain_render_scale
        if draw_match_hud:
            self.render_match_hud(game_engine, top_offset=hud_offset)
        self._render_player_status_hud(game_engine, rect)
        if self._collision_overlay_active():
            self._render_player_debug_hud(game_engine, rect)
        self._render_player_purchase_menu(game_engine, rect)
        self._render_pre_match_prompt(game_engine, rect)
        self._render_pre_match_config_menu(game_engine, rect)
        if game_engine.paused and not getattr(game_engine, 'pre_match_setup_required', False) and float(getattr(game_engine, 'pre_match_countdown_remaining', 0.0)) <= 0.0:
            self._render_player_pause_overlay(game_engine, rect)
        self._render_player_settings_menu(game_engine, rect)

    def _begin_numeric_input(self, input_type, facility_id, current_value):
        self.active_numeric_input = {
            'type': input_type,
            'facility_id': facility_id,
            'text': f'{float(current_value):.2f}',
        }

    def _is_numeric_input_active(self, input_type, facility_id):
        return (
            self.active_numeric_input is not None
            and self.active_numeric_input.get('type') == input_type
            and self.active_numeric_input.get('facility_id') == facility_id
        )

    def render_perf_overlay(self, game_engine):
        if not getattr(game_engine, 'show_perf_overlay', False):
            return
        stats = game_engine.get_perf_overlay_stats()
        if not stats:
            return
        lines = [
            f'目标帧率 {int(game_engine.fps)} FPS',
            f'帧 平均 {stats["frame_avg_ms"]:.1f}ms | p95 {stats["frame_p95_ms"]:.1f}ms',
            f'事件 平均 {stats.get("event_avg_ms", 0.0):.1f}ms | p95 {stats.get("event_p95_ms", 0.0):.1f}ms',
            f'更新 平均 {stats["update_avg_ms"]:.1f}ms | p95 {stats["update_p95_ms"]:.1f}ms',
            f'渲染 平均 {stats["render_avg_ms"]:.1f}ms | p95 {stats["render_p95_ms"]:.1f}ms',
        ]
        breakdown = stats.get('breakdown') if isinstance(stats, dict) else None
        if breakdown:
            lines.append(
                '更新拆分 ent {entity_ms:.1f} | ctrl {controller_ms:.1f} | phys {physics_ms:.1f} | aim {auto_aim_ms:.1f} | rule {rules_ms:.1f}'.format(
                    entity_ms=breakdown.get('entity_ms', 0.0),
                    controller_ms=breakdown.get('controller_ms', 0.0),
                    physics_ms=breakdown.get('physics_ms', 0.0),
                    auto_aim_ms=breakdown.get('auto_aim_ms', 0.0),
                    rules_ms=breakdown.get('rules_ms', 0.0),
                )
            )
        padding = 8
        line_height = self.tiny_font.get_linesize()
        box_width = max(self.tiny_font.size(line)[0] for line in lines) + padding * 2
        box_height = line_height * len(lines) + padding * 2
        surface = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
        surface.fill((18, 24, 30, 170))
        for idx, line in enumerate(lines):
            text = self.tiny_font.render(line, True, self.colors['white'])
            surface.blit(text, (padding, padding + idx * line_height))
        dest_x = self.content_padding
        dest_y = self.toolbar_height + self.hud_height + self.content_padding
        self.screen.blit(surface, (dest_x, dest_y))

    def _cancel_numeric_input(self):
        self.active_numeric_input = None

    def _commit_numeric_input(self, game_engine, announce=False):
        if self.active_numeric_input is None:
            return False

        input_type = self.active_numeric_input.get('type')
        facility_id = self.active_numeric_input.get('facility_id')
        raw_text = self.active_numeric_input.get('text', '').strip()
        if not raw_text:
            self.active_numeric_input = None
            return False

        try:
            value = max(0.0, round(float(raw_text), 2))
        except ValueError:
            self.active_numeric_input = None
            return False

        stored_value = self._terrain_editor_storage_height(value) if input_type in {'wall', 'terrain_brush', 'terrain'} else value

        if input_type == 'wall':
            self._record_undo_snapshot(game_engine, f'墙高 {facility_id}')
            facility = game_engine.map_manager.update_wall_properties(facility_id, height_m=stored_value)
            self.selected_wall_id = facility_id
            label = '墙高'
        elif input_type == 'terrain_brush':
            self.terrain_brush['height_m'] = stored_value
            self.active_numeric_input = None
            if announce:
                game_engine.add_log(f'地形笔刷高度已设置为 {value:.2f}m', 'system')
            return True
        else:
            facility = game_engine.map_manager.update_facility_height(facility_id, stored_value)
            self.selected_terrain_id = facility_id
            label = '地形高'

        self.active_numeric_input = None
        if facility is None:
            return False

        game_engine.config.setdefault('map', {})['facilities'] = game_engine.map_manager.export_facilities_config()
        if announce:
            game_engine.add_log(f'{facility_id} {label}已设置为 {self._terrain_editor_display_height(facility.get("height_m", stored_value)):.2f}m', 'system')
        return True

    def _handle_numeric_input_keydown(self, event, game_engine):
        if self.active_numeric_input is None:
            return False

        if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER}:
            self._commit_numeric_input(game_engine, announce=True)
            return True
        if event.key == pygame.K_ESCAPE:
            self._cancel_numeric_input()
            return True
        if event.key == pygame.K_BACKSPACE:
            self.active_numeric_input['text'] = self.active_numeric_input.get('text', '')[:-1]
            return True
        if event.key == pygame.K_DELETE:
            self.active_numeric_input['text'] = ''
            return True

        character = event.unicode
        if character.isdigit():
            self.active_numeric_input['text'] = self.active_numeric_input.get('text', '') + character
            return True
        if character == '.':
            current = self.active_numeric_input.get('text', '')
            if '.' not in current:
                self.active_numeric_input['text'] = current + '.'
            return True

        return True

    def _update_viewport(self, map_manager):
        available_rect = self._terrain_available_rect()
        available_width = available_rect.width
        available_height = available_rect.height
        scale = self._terrain_effective_scale(map_manager)
        draw_width = int(map_manager.map_width * scale)
        draw_height = int(map_manager.map_height * scale)
        map_x = available_rect.x + (available_width - draw_width) // 2
        map_y = available_rect.y + (available_height - draw_height) // 2
        if self.edit_mode == 'terrain':
            map_x += int(self.terrain_view_offset[0])
            map_y += int(self.terrain_view_offset[1])
        self.viewport = {
            'map_x': map_x,
            'map_y': map_y,
            'map_width': draw_width,
            'map_height': draw_height,
            'scale': scale,
            'sidebar_x': available_rect.right,
        }

    def _terrain_available_rect(self):
        sidebar_width = self._sidebar_total_width()
        return pygame.Rect(
            self.content_padding,
            self.toolbar_height + self.hud_height + self.content_padding,
            self.window_width - sidebar_width - self.content_padding * 2,
            self.window_height - self.toolbar_height - self.hud_height - self.content_padding * 2,
        )

    def _sidebar_column_count(self):
        if self.edit_mode == 'none' and self.game_engine is not None and self.game_engine.is_single_unit_test_mode():
            return 2
        return 1

    def _sidebar_total_width(self):
        if self.edit_mode == 'none' and self.game_engine is not None and self.game_engine.is_single_unit_test_mode():
            return self.panel_width + self.decision_panel_width
        return self.panel_width

    def _terrain_fit_scale(self, map_manager):
        available_rect = self._terrain_available_rect()
        scale = min(
            available_rect.width / max(1, map_manager.map_width),
            available_rect.height / max(1, map_manager.map_height),
        )
        return max(scale, 0.1)

    def _terrain_effective_scale(self, map_manager):
        return self._terrain_fit_scale(map_manager)

    def _map_rect(self):
        if self.viewport is None:
            return pygame.Rect(0, 0, 0, 0)
        return pygame.Rect(
            self.viewport['map_x'],
            self.viewport['map_y'],
            self.viewport['map_width'],
            self.viewport['map_height'],
        )

    def _visible_map_clip_rect(self):
        map_rect = self._map_rect()
        if map_rect.width <= 0 or map_rect.height <= 0:
            return pygame.Rect(0, 0, 0, 0)
        return map_rect.clip(self.screen.get_rect())

    def _screen_point_visible(self, point, padding_px=0):
        clip_rect = self._visible_map_clip_rect()
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return False
        if padding_px:
            clip_rect = clip_rect.inflate(int(padding_px) * 2, int(padding_px) * 2)
        return clip_rect.collidepoint(int(point[0]), int(point[1]))

    def _world_point_visible(self, world_x, world_y, padding_px=0):
        return self._screen_point_visible(self.world_to_screen(world_x, world_y), padding_px=padding_px)

    def _world_rect_visible(self, x1, y1, x2, y2, padding_px=0):
        clip_rect = self._visible_map_clip_rect()
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return False
        if padding_px:
            clip_rect = clip_rect.inflate(int(padding_px) * 2, int(padding_px) * 2)
        screen_x1, screen_y1 = self.world_to_screen(x1, y1)
        screen_x2, screen_y2 = self.world_to_screen(x2, y2)
        rect = pygame.Rect(
            min(screen_x1, screen_x2),
            min(screen_y1, screen_y2),
            max(1, abs(screen_x2 - screen_x1)),
            max(1, abs(screen_y2 - screen_y1)),
        )
        return rect.colliderect(clip_rect)

    def _terrain_overlay_display_cell_size(self, map_manager, map_rect, view_width=None, view_height=None):
        if map_rect is None or map_rect.width <= 0 or map_rect.height <= 0:
            return 0.0
        if view_width is None:
            view_width = float(map_manager.map_width)
        if view_height is None:
            view_height = float(map_manager.map_height)
        cell_size = float(getattr(map_manager, 'terrain_grid_cell_size', 1.0))
        cell_width_px = map_rect.width * cell_size / max(float(view_width), 1e-6)
        cell_height_px = map_rect.height * cell_size / max(float(view_height), 1e-6)
        return min(cell_width_px, cell_height_px)

    def _terrain_overlay_draw_outlines(self, map_manager, map_rect, view_width=None, view_height=None):
        return self._terrain_overlay_display_cell_size(map_manager, map_rect, view_width=view_width, view_height=view_height) >= 6.0

    def _zoom_terrain_view(self, map_manager, zoom_steps, focus_world=None):
        if not zoom_steps:
            return False
        old_zoom = self.terrain_scene_zoom
        self.terrain_scene_zoom = max(1.0, min(6.0, self.terrain_scene_zoom * (1.15 ** zoom_steps)))
        if focus_world is not None:
            self.terrain_scene_focus_world = (
                max(0.0, min(float(map_manager.map_width - 1), float(focus_world[0]))),
                max(0.0, min(float(map_manager.map_height - 1), float(focus_world[1]))),
            )
        return abs(self.terrain_scene_zoom - old_zoom) >= 1e-6

    def render_toolbar(self, game_engine):
        pygame.draw.rect(self.screen, self.colors['toolbar'], (0, 0, self.window_width, self.toolbar_height))
        buttons = [
            ('开始/重开', 'start_match', False),
            ('暂停/继续', 'toggle_pause', game_engine.paused and not game_engine.rules_engine.game_over),
            ('设置', 'toggle_player_settings', self.player_settings_menu_open),
            ('结束对局', 'end_match', game_engine.rules_engine.game_over),
            ('保存存档', 'save_match', False),
            ('载入存档', 'load_match', False),
            ('保存设置', 'save_settings', False),
            ('主控视角', 'toggle_player_view', game_engine.player_control_enabled),
            ('设施显示', 'toggle_facilities', self.show_facilities),
            ('视场显示', 'toggle_aim_fov', self.show_aim_fov),
            ('浏览', 'mode:none', self.edit_mode == 'none'),
            ('地形编辑', 'mode:terrain', self.edit_mode == 'terrain'),
            ('站位编辑', 'mode:entity', self.edit_mode == 'entity'),
        ]

        x = 10
        for label, action, active in buttons:
            text = self.small_font.render(label, True, self.colors['toolbar_text'])
            rect = pygame.Rect(x, 10, text.get_width() + 22, self.toolbar_height - 20)
            pygame.draw.rect(
                self.screen,
                self.colors['toolbar_button_active'] if active else self.colors['toolbar_button'],
                rect,
                border_radius=6,
            )
            self.screen.blit(text, (rect.x + 11, rect.y + (rect.height - text.get_height()) // 2))
            self.toolbar_actions.append((rect, action))
            x = rect.right + 8

        if self.edit_mode == 'terrain':
            radius_label = self.small_font.render(f'半径 {self.terrain_brush_radius}', True, self.colors['toolbar_text'])
            radius_minus_rect = pygame.Rect(x, 10, 28, self.toolbar_height - 20)
            radius_value_rect = pygame.Rect(x + 34, 10, max(62, radius_label.get_width() + 18), self.toolbar_height - 20)
            radius_plus_rect = pygame.Rect(radius_value_rect.right + 6, 10, 28, self.toolbar_height - 20)
            for rect, label, active in (
                (radius_minus_rect, '-', False),
                (radius_value_rect, f'半径 {self.terrain_brush_radius}', False),
                (radius_plus_rect, '+', False),
            ):
                text = self.small_font.render(label, True, self.colors['toolbar_text'])
                pygame.draw.rect(self.screen, self.colors['toolbar_button'], rect, border_radius=6)
                self.screen.blit(text, text.get_rect(center=rect.center))
            self.toolbar_actions.extend([
                (radius_minus_rect, 'terrain_brush_radius:-1'),
                (radius_plus_rect, 'terrain_brush_radius:1'),
            ])
            x = radius_plus_rect.right + 10

            height_text_value = f'{self._terrain_editor_display_height(self.terrain_brush.get("height_m", 0.0)):.2f}m'
            height_minus_rect = pygame.Rect(x, 10, 28, self.toolbar_height - 20)
            height_value_rect = pygame.Rect(x + 34, 10, 92, self.toolbar_height - 20)
            height_plus_rect = pygame.Rect(height_value_rect.right + 6, 10, 28, self.toolbar_height - 20)
            height_active = self._is_numeric_input_active('terrain_brush', 'brush')
            height_display = self.active_numeric_input['text'] if height_active and self.active_numeric_input is not None else height_text_value
            for rect, label in (
                (height_minus_rect, '-'),
                (height_plus_rect, '+'),
            ):
                text = self.small_font.render(label, True, self.colors['toolbar_text'])
                pygame.draw.rect(self.screen, self.colors['toolbar_button'], rect, border_radius=6)
                self.screen.blit(text, text.get_rect(center=rect.center))
            pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if height_active else self.colors['toolbar_button'], height_value_rect, border_radius=6)
            height_value_text = self.small_font.render(height_display, True, self.colors['toolbar_text'])
            self.screen.blit(height_value_text, height_value_text.get_rect(center=height_value_rect.center))
            self.toolbar_actions.extend([
                (height_minus_rect, 'terrain_brush_height:-0.1'),
                (height_value_rect, 'height_input:terrain_brush:brush'),
                (height_plus_rect, 'terrain_brush_height:0.1'),
            ])
            x = height_plus_rect.right + 10

            if self.terrain_workflow_mode == 'shape' and self.terrain_shape_mode in {'smooth', 'smooth_polygon'}:
                smooth_text = self.small_font.render('Smooth', True, self.colors['toolbar_text'])
                self.screen.blit(smooth_text, (x + 4, 18))
                x += smooth_text.get_width() + 12
                for value in range(4):
                    label = str(value)
                    text = self.small_font.render(label, True, self.colors['toolbar_text'])
                    rect = pygame.Rect(x, 10, max(32, text.get_width() + 18), self.toolbar_height - 20)
                    pygame.draw.rect(
                        self.screen,
                        self.colors['toolbar_button_active'] if self.terrain_smooth_strength == value else self.colors['toolbar_button'],
                        rect,
                        border_radius=6,
                    )
                    self.screen.blit(text, text.get_rect(center=rect.center))
                    self.toolbar_actions.append((rect, f'terrain_smooth_strength:set:{value}'))
                    x = rect.right + 6
                confirm_rect = pygame.Rect(x + 4, 10, 56, self.toolbar_height - 20)
                pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], confirm_rect, border_radius=6)
                confirm_text = self.small_font.render('确定', True, self.colors['toolbar_text'])
                self.screen.blit(confirm_text, confirm_text.get_rect(center=confirm_rect.center))
                self.toolbar_actions.append((confirm_rect, 'terrain_smooth_confirm'))

        if not getattr(game_engine, 'match_started', False):
            state_label = '未开始'
        elif game_engine.rules_engine.game_over:
            state_label = '已结束'
        else:
            state_label = '已暂停' if game_engine.paused else '运行中'
        state_text = self.small_font.render(f'状态: {state_label}', True, self.colors['toolbar_text'])
        self.screen.blit(state_text, (self.window_width - state_text.get_width() - 12, 18))

    def render_map(self, map_manager):
        if self.viewport is None:
            return
        map_rect = self._map_rect()
        pygame.draw.rect(self.screen, self.colors['white'], map_rect)
        pygame.draw.rect(self.screen, self.colors['panel_border'], map_rect, 1)

        self._blit_cached_map_surface(map_manager, map_rect)

        self.render_facility_overlay(map_manager)
        if self._terrain_brush_active():
            self.render_terrain_grid_overlay(map_manager)
        self.render_drag_preview()

    def _region_display_label(self, region):
        region_id = str(region.get('id', ''))
        region_type = str(region.get('type', ''))
        region_team = str(region.get('team', 'neutral'))
        for option in self.facility_options + self.buff_options:
            if option.get('id') == region_id:
                return option.get('label', region_id)
        for option in self.facility_options + self.buff_options:
            if option.get('type') == region_type and option.get('team', 'neutral') == region_team:
                return option.get('label', region_type)
        fallback_map = {
            'wall': '墙体',
            'base': '基地',
            'outpost': '前哨站',
            'dog_hole': '狗洞',
            'undulating_road': '起伏路',
            'fly_slope': '飞坡',
            'first_step': '一级台阶',
            'second_step': '二级台阶',
            'supply': '补给区',
            'fort': '堡垒',
            'rugged_road': '起伏路段',
            'mining_area': '取矿区',
            'mineral_exchange': '兑矿区',
            'energy_mechanism': '中央能量机关',
            'buff_hero_deployment': '英雄部署区',
        }
        return fallback_map.get(region_type, region_id or region_type or '未知区域')

    def _region_function_lines(self, region):
        if region is None:
            return []
        region_type = str(region.get('type', ''))
        region_team = str(region.get('team', 'neutral'))
        team_label = '己方' if region_team in {'red', 'blue'} else '该区域'
        descriptions = {
            'wall': ['阻挡机器人通行', '可按墙高决定是否遮挡视野'],
            'base': ['主基地目标区域', '敌方前哨被破后这里会成为最终推进目标'],
            'outpost': ['前置核心目标区域', '前哨失守后会解锁后续推基地阶段'],
            'supply': [f'{team_label}补给区', '英雄和步兵缺弹时会优先来此补弹'],
            'fort': [f'{team_label}堡垒区域', '用于据守、卡位和火力覆盖'],
            'dog_hole': ['低矮穿越通道', '适合隐蔽通过，但会压缩移动路线'],
            'undulating_road': ['起伏路段', '提供掩体感路线，但机动更复杂'],
            'rugged_road': ['复杂起伏路段', '用于机动绕行和地形博弈'],
            'fly_slope': ['飞坡通道', '可快速切换上下层路线'],
            'first_step': ['一级台阶区域', '用于上台阶过渡'],
            'second_step': ['二级台阶区域', '用于进入更高台面'],
            'mining_area': [f'{team_label}取矿区', '工程机器人只会在这里采矿'],
            'mineral_exchange': [f'{team_label}兑矿区', '工程携矿后会回这里完成兑换'],
            'energy_mechanism': ['中央能量机关', '满足条件时会来此激活能量机关'],
            'buff_base': ['基地增益区', '用于基地附近的增益/机制判定'],
            'buff_outpost': ['前哨增益区', '用于前哨附近的增益/机制判定'],
            'buff_fort': ['堡垒增益区', '用于堡垒附近的增益/机制判定'],
            'buff_supply': ['补给增益区', '用于补给区相关增益判定'],
            'buff_hero_deployment': [f'{team_label}英雄部署区', '英雄只有在这里才能进入部署模式并吊射敌方前哨/基地'],
            'buff_central_highland': ['中央高地区域', '步兵/英雄会争夺这里建立高点火力'],
            'buff_trapezoid_highland': [f'{team_label}梯形高地区域', '英雄开局会优先争夺这里建立吊射位'],
            'buff_terrain_highland_red_start': ['高地跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_highland_red_end': ['高地跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_highland_blue_start': ['高地跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_highland_blue_end': ['高地跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_road_red_start': ['公路跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_road_red_end': ['公路跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_road_blue_start': ['公路跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_road_blue_end': ['公路跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_fly_slope_red_start': ['飞坡跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_fly_slope_red_end': ['飞坡跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_fly_slope_blue_start': ['飞坡跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_fly_slope_blue_end': ['飞坡跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_slope_red_start': ['陡道跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_slope_red_end': ['陡道跨越路线终点', '仅用于导航/跨越路线提示'],
            'buff_terrain_slope_blue_start': ['陡道跨越路线起点', '仅用于导航/跨越路线提示'],
            'buff_terrain_slope_blue_end': ['陡道跨越路线终点', '仅用于导航/跨越路线提示'],
        }
        return descriptions.get(region_type, ['区域机制说明未定义'])

    def _preferred_hover_region(self, regions):
        if not regions:
            return None
        for region in regions:
            if region.get('type') != 'boundary':
                return region
        return regions[0]

    def _hover_region_at_world(self, map_manager, world_pos):
        if map_manager is None or world_pos is None:
            return None
        return self._preferred_hover_region(map_manager.get_regions_at(world_pos[0], world_pos[1]))

    def _hover_grid_metrics(self, map_manager, world_pos):
        if map_manager is None or world_pos is None:
            return None
        grid_x, grid_y = map_manager._world_to_grid(world_pos[0], world_pos[1])
        max_grid_x, max_grid_y = map_manager._grid_dimensions()
        if grid_x < 0 or grid_y < 0 or grid_x >= max_grid_x or grid_y >= max_grid_y:
            return None
        x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
        cell_width_px = max(1.0, float(x2) - float(x1) + 1.0)
        cell_width_m = cell_width_px * float(map_manager.field_length_m) / max(float(map_manager.map_width), 1.0)
        height_m = map_manager._sample_grid_height(grid_x, grid_y)
        return {
            'grid_x': int(grid_x),
            'grid_y': int(grid_y),
            'height_m': float(height_m),
            'cell_width_m': float(cell_width_m),
        }

    def _draw_region_hover_card(self, surface, region, anchor_pos, clamp_rect=None, map_manager=None, world_pos=None):
        if surface is None or region is None or anchor_pos is None:
            return
        label = self._region_display_label(region)
        team_text = f"队伍: {region.get('team', 'neutral')}"
        detail = str(region.get('id', ''))
        function_lines = self._region_function_lines(region)
        text_surfaces = [
            self.small_font.render(label, True, self.colors['white']),
            self.tiny_font.render(detail, True, (214, 220, 228)) if detail else None,
            self.tiny_font.render(team_text, True, (214, 220, 228)),
        ]
        for line in function_lines:
            text_surfaces.append(self.tiny_font.render(f'功能: {line}', True, (240, 244, 248)))
        width = max(rendered.get_width() for rendered in text_surfaces if rendered is not None) + 20
        height = 12
        for rendered in text_surfaces:
            if rendered is None:
                continue
            height += rendered.get_height() + 4
        height += 4
        tooltip = pygame.Surface((width, height), pygame.SRCALPHA)
        tooltip.fill((18, 24, 30, 228))
        pygame.draw.rect(tooltip, (245, 247, 250, 180), tooltip.get_rect(), 1, border_radius=8)
        y = 8
        for rendered in text_surfaces:
            if rendered is None:
                continue
            tooltip.blit(rendered, (10, y))
            y += rendered.get_height() + 4
        if clamp_rect is None:
            clamp_rect = surface.get_rect()
        box_x = min(clamp_rect.right - width - 8, max(clamp_rect.x + 8, anchor_pos[0] + 16))
        box_y = min(clamp_rect.bottom - height - 8, max(clamp_rect.y + 8, anchor_pos[1] + 16))
        surface.blit(tooltip, (box_x, box_y))

    def _point_to_segment_distance(self, point, start, end):
        px, py = point
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) <= 1e-6 and abs(dy) <= 1e-6:
            return math.hypot(px - x1, py - y1)
        ratio = ((px - x1) * dx + (py - y1) * dy) / max(dx * dx + dy * dy, 1e-6)
        ratio = max(0.0, min(1.0, ratio))
        closest_x = x1 + ratio * dx
        closest_y = y1 + ratio * dy
        return math.hypot(px - closest_x, py - closest_y)

    def _region_outline_distance_screen(self, mouse_pos, region):
        if self.viewport is None:
            return None
        shape = region.get('shape', 'rect')
        if shape == 'line':
            start = self.world_to_screen(region['x1'], region['y1'])
            end = self.world_to_screen(region['x2'], region['y2'])
            thickness = max(2.0, float(region.get('thickness', 12)) * self.viewport['scale'])
            return max(0.0, self._point_to_segment_distance(mouse_pos, start, end) - thickness * 0.5)

        if shape == 'polygon':
            points = [self.world_to_screen(point[0], point[1]) for point in region.get('points', [])]
            if len(points) < 2:
                return None
            min_distance = None
            previous = points[-1]
            for current in points:
                distance = self._point_to_segment_distance(mouse_pos, previous, current)
                min_distance = distance if min_distance is None else min(min_distance, distance)
                previous = current
            return min_distance

        x1, y1 = self.world_to_screen(region['x1'], region['y1'])
        x2, y2 = self.world_to_screen(region['x2'], region['y2'])
        left = min(x1, x2)
        right = max(x1, x2)
        top = min(y1, y2)
        bottom = max(y1, y2)
        edges = [
            ((left, top), (right, top)),
            ((right, top), (right, bottom)),
            ((right, bottom), (left, bottom)),
            ((left, bottom), (left, top)),
        ]
        min_distance = None
        for start, end in edges:
            distance = self._point_to_segment_distance(mouse_pos, start, end)
            min_distance = distance if min_distance is None else min(min_distance, distance)
        return min_distance

    def _hovered_region(self, map_manager):
        if self.edit_mode != 'terrain' or self.viewport is None:
            return None
        mouse_pos = pygame.mouse.get_pos()
        map_rect = pygame.Rect(
            self.viewport['map_x'],
            self.viewport['map_y'],
            self.viewport['map_width'],
            self.viewport['map_height'],
        )
        if not map_rect.collidepoint(mouse_pos):
            return None

        if self.mouse_world is not None:
            hovered = self._hover_region_at_world(map_manager, self.mouse_world)
            if hovered is not None:
                return hovered

        nearest = None
        nearest_distance = None
        for region in map_manager.get_facility_regions():
            if region.get('type') == 'boundary':
                continue
            distance = self._region_outline_distance_screen(mouse_pos, region)
            if distance is None or distance > 12.0:
                continue
            if nearest_distance is None or distance < nearest_distance:
                nearest = region
                nearest_distance = distance
        return nearest

    def render_region_hover_hint(self, map_manager):
        region = self._hovered_region(map_manager)
        if region is None:
            return
        world_pos = self.mouse_world
        if world_pos is None:
            world_pos = self.screen_to_world(*pygame.mouse.get_pos())
        self._draw_region_hover_card(self.screen, region, pygame.mouse.get_pos(), clamp_rect=self.screen.get_rect(), map_manager=map_manager, world_pos=world_pos)

    def _get_scaled_map_surface(self, map_manager, size, source_rect=None):
        source = map_manager.map_image or map_manager.map_surface
        if source is None:
            return None
        normalized_source_rect = None
        if source_rect is not None:
            normalized_source_rect = (int(source_rect.x), int(source_rect.y), int(source_rect.width), int(source_rect.height))
        cache_key = (source.get_size(), tuple(size), normalized_source_rect)
        if self.map_cache_surface is None or self.map_cache_key != cache_key:
            if source_rect is not None:
                source = source.subsurface(source_rect)
            self.map_cache_surface = pygame.transform.smoothscale(source, size).convert()
            self.map_cache_size = size
            self.map_cache_key = cache_key
        return self.map_cache_surface

    def _blit_cached_map_surface(self, map_manager, map_rect):
        source = map_manager.map_image or map_manager.map_surface
        if source is None:
            return
        self._blit_world_surface(source, map_rect, map_cache=True)

    def _compute_visible_source_rect(self, map_rect, source):
        if self.viewport is None:
            return None, None
        visible_rect = map_rect.clip(self._visible_map_clip_rect())
        if visible_rect.width <= 0 or visible_rect.height <= 0:
            return None, None
        scale = max(float(self.viewport['scale']), 1e-6)
        source_rect = pygame.Rect(
            max(0, int(math.floor((visible_rect.x - map_rect.x) / scale))),
            max(0, int(math.floor((visible_rect.y - map_rect.y) / scale))),
            max(1, int(math.ceil(visible_rect.width / scale))),
            max(1, int(math.ceil(visible_rect.height / scale))),
        )
        source_rect.clamp_ip(source.get_rect())
        source_rect.width = min(source_rect.width, source.get_width() - source_rect.x)
        source_rect.height = min(source_rect.height, source.get_height() - source_rect.y)
        if source_rect.width <= 0 or source_rect.height <= 0:
            return None, None
        return visible_rect, source_rect

    def _blit_world_surface(self, source, map_rect, map_cache=False, smooth=True):
        if source is None:
            return
        visible_rect, source_rect = self._compute_visible_source_rect(map_rect, source)
        if visible_rect is None or source_rect is None:
            return
        if map_cache:
            surface = self._get_scaled_map_surface(self.game_engine.map_manager, visible_rect.size, source_rect=source_rect)
        else:
            scaler = pygame.transform.smoothscale if smooth else pygame.transform.scale
            surface = scaler(source.subsurface(source_rect), visible_rect.size)
        if surface is not None:
            self.screen.blit(surface, visible_rect.topleft)

    def _facility_color_map(self):
        return {
            'base': (255, 80, 80),
            'outpost': (80, 160, 255),
            'fly_slope': (240, 150, 60),
            'undulating_road': (120, 220, 120),
            'rugged_road': (86, 74, 62),
            'first_step': (190, 190, 255),
            'dog_hole': (255, 120, 220),
            'second_step': (255, 140, 140),
            'supply': (248, 214, 72),
            'fort': (145, 110, 80),
            'energy_mechanism': (255, 195, 64),
            'mining_area': (82, 201, 153),
            'mineral_exchange': (69, 137, 255),
            'buff_base': (255, 102, 102),
            'buff_outpost': (118, 174, 255),
            'buff_fort': (161, 129, 95),
            'buff_supply': (255, 229, 110),
            'buff_assembly': (255, 170, 66),
            'buff_hero_deployment': (255, 122, 122),
            'buff_central_highland': (176, 132, 255),
            'buff_trapezoid_highland': (214, 130, 255),
            'buff_terrain_highland_red_start': (255, 168, 168),
            'buff_terrain_highland_red_end': (214, 96, 96),
            'buff_terrain_highland_blue_start': (135, 198, 255),
            'buff_terrain_highland_blue_end': (74, 140, 214),
            'buff_terrain_road_red_start': (255, 194, 128),
            'buff_terrain_road_red_end': (224, 136, 72),
            'buff_terrain_road_blue_start': (148, 220, 255),
            'buff_terrain_road_blue_end': (70, 163, 214),
            'buff_terrain_fly_slope_red_start': (255, 152, 202),
            'buff_terrain_fly_slope_red_end': (214, 88, 150),
            'buff_terrain_fly_slope_blue_start': (170, 182, 255),
            'buff_terrain_fly_slope_blue_end': (102, 118, 214),
            'buff_terrain_slope_red_start': (255, 164, 117),
            'buff_terrain_slope_red_end': (214, 110, 66),
            'buff_terrain_slope_blue_start': (156, 255, 205),
            'buff_terrain_slope_blue_end': (86, 201, 145),
            'wall': (35, 35, 35),
            'boundary': (255, 255, 255),
        }

    def _get_world_facility_overlay_surface(self, map_manager):
        overlay_key = (
            int(map_manager.map_width),
            int(map_manager.map_height),
            int(getattr(map_manager, 'facility_version', 0)),
            bool(self.show_facilities),
        )
        if self.facility_overlay_world_surface is None or self.facility_overlay_world_key != overlay_key:
            surface = pygame.Surface((map_manager.map_width, map_manager.map_height), pygame.SRCALPHA).convert_alpha()
            color_map = self._facility_color_map()
            for region in map_manager.get_facility_regions():
                facility_type = str(region.get('type', 'boundary'))
                color = color_map.get(facility_type, self.colors['white']) or self.colors['white']
                if region.get('shape') == 'line':
                    color = self._wall_color(region) or self.colors['white']
                    pygame.draw.line(
                        surface,
                        color,
                        (int(region['x1']), int(region['y1'])),
                        (int(region['x2']), int(region['y2'])),
                        max(2, int(region.get('thickness', 12))),
                    )
                    tag = self.tiny_font.render(str(region.get('id', facility_type)), True, color)
                    surface.blit(tag, (int(region['x1']) + 4, int(region['y1']) + 4))
                    continue
                if region.get('shape') == 'polygon':
                    points = [(int(point[0]), int(point[1])) for point in region.get('points', [])]
                    if len(points) < 3:
                        continue
                    pygame.draw.polygon(surface, color, points, 1)
                    tag = self.tiny_font.render(str(region.get('id', facility_type)), True, color)
                    surface.blit(tag, (points[0][0] + 2, points[0][1] + 2))
                    continue
                if region.get('shape') != 'rect':
                    continue
                x1 = int(region['x1'])
                y1 = int(region['y1'])
                x2 = int(region['x2'])
                y2 = int(region['y2'])
                rect = pygame.Rect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
                if facility_type == 'outpost':
                    center_x = rect.x + rect.width // 2
                    center_y = rect.y + rect.height // 2
                    radius = max(10, min(rect.width, rect.height) // 2)
                    pygame.draw.circle(surface, color, (center_x, center_y), radius, 3)
                    pygame.draw.circle(surface, color, (center_x, center_y), max(6, radius - 7), 1)
                else:
                    pygame.draw.rect(surface, color, rect, 1)
                if facility_type != 'boundary':
                    tag = self.tiny_font.render(str(region.get('id', facility_type)), True, color)
                    surface.blit(tag, (rect.x + 2, rect.y + 2))
            self.facility_overlay_world_surface = surface
            self.facility_overlay_world_key = overlay_key
        return self.facility_overlay_world_surface

    def _draw_world_terrain_overlay_cell(self, surface, map_manager, cell_lookup, grid_x, grid_y, base_fill_alpha, draw_outlines=True):
        cell = cell_lookup.get(map_manager._terrain_cell_key(grid_x, grid_y))
        x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
        rect = pygame.Rect(x1, y1, max(1, x2 - x1 + 1), max(1, y2 - y1 + 1))
        surface.fill((0, 0, 0, 0), rect)
        if cell is None:
            return
        color = self._terrain_color_by_type(cell.get('type', 'flat'))
        terrain_type = str(cell.get('type', 'flat'))
        fill_alpha = base_fill_alpha if terrain_type != 'custom_terrain' else max(8, int(base_fill_alpha * 0.45))
        pygame.draw.rect(surface, (*color, fill_alpha), rect)
        if not draw_outlines:
            return
        signature = self._terrain_cell_border_signature(cell)
        outline_color = self._terrain_outline_color(cell.get('type', 'flat'))
        neighbors = {
            'top': cell_lookup.get(map_manager._terrain_cell_key(grid_x, grid_y - 1)),
            'right': cell_lookup.get(map_manager._terrain_cell_key(grid_x + 1, grid_y)),
            'bottom': cell_lookup.get(map_manager._terrain_cell_key(grid_x, grid_y + 1)),
            'left': cell_lookup.get(map_manager._terrain_cell_key(grid_x - 1, grid_y)),
        }
        if self._terrain_cell_border_signature(neighbors['top']) != signature:
            pygame.draw.line(surface, outline_color, (x1, y1), (x2, y1), 2)
        if self._terrain_cell_border_signature(neighbors['right']) != signature:
            pygame.draw.line(surface, outline_color, (x2, y1), (x2, y2), 2)
        if self._terrain_cell_border_signature(neighbors['bottom']) != signature:
            pygame.draw.line(surface, outline_color, (x1, y2), (x2, y2), 2)
        if self._terrain_cell_border_signature(neighbors['left']) != signature:
            pygame.draw.line(surface, outline_color, (x1, y1), (x1, y2), 2)

    def _get_world_terrain_grid_overlay_surface(self, map_manager, draw_outlines=True):
        overlay_key = (
            int(map_manager.map_width),
            int(map_manager.map_height),
            int(self.terrain_overlay_alpha),
            bool(draw_outlines),
        )
        dirty_state = map_manager.consume_terrain_overlay_dirty_state()
        base_fill_alpha = max(12, min(72, int(self.terrain_overlay_alpha * 0.32)))
        if self.terrain_grid_overlay_world_surface is None or self.terrain_grid_overlay_world_key != overlay_key or dirty_state.get('reset'):
            surface = pygame.Surface((map_manager.map_width, map_manager.map_height), pygame.SRCALPHA).convert_alpha()
            with map_manager._edit_state_lock:
                cell_lookup = {key: dict(cell) for key, cell in map_manager.terrain_grid_overrides.items()}
            for cell in cell_lookup.values():
                self._draw_world_terrain_overlay_cell(surface, map_manager, cell_lookup, int(cell['x']), int(cell['y']), base_fill_alpha, draw_outlines=draw_outlines)
            self.terrain_grid_overlay_world_surface = surface
            self.terrain_grid_overlay_world_key = overlay_key
        elif dirty_state.get('keys'):
            affected_keys = set()
            for key in dirty_state.get('keys', ()): 
                affected_keys.add(key)
                grid_x, grid_y = map_manager._decode_terrain_cell_key(key)
                for delta_x, delta_y in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    affected_keys.add(map_manager._terrain_cell_key(grid_x + delta_x, grid_y + delta_y))
            lookup_keys = set(affected_keys)
            for key in tuple(affected_keys):
                grid_x, grid_y = map_manager._decode_terrain_cell_key(key)
                for delta_x, delta_y in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                    lookup_keys.add(map_manager._terrain_cell_key(grid_x + delta_x, grid_y + delta_y))
            with map_manager._edit_state_lock:
                cell_lookup = {
                    key: dict(map_manager.terrain_grid_overrides[key])
                    for key in lookup_keys
                    if key in map_manager.terrain_grid_overrides
                }
            for key in affected_keys:
                grid_x, grid_y = map_manager._decode_terrain_cell_key(key)
                if grid_x < 0 or grid_y < 0:
                    continue
                max_x, max_y = map_manager._grid_dimensions()
                if grid_x >= max_x or grid_y >= max_y:
                    continue
                self._draw_world_terrain_overlay_cell(self.terrain_grid_overlay_world_surface, map_manager, cell_lookup, grid_x, grid_y, base_fill_alpha, draw_outlines=draw_outlines)
        return self.terrain_grid_overlay_world_surface

    def render_facility_overlay(self, map_manager):
        if self.viewport is None or not self.show_facilities:
            return
        self._blit_world_surface(self._get_world_facility_overlay_surface(map_manager), self._map_rect())
        if self._facility_edit_active() or self._terrain_brush_active():
            self._draw_facility_overlay(self.screen, map_manager, interactive=True)

    def _draw_facility_overlay(self, target_surface, map_manager, interactive=False):
        color_map = self._facility_color_map()
        scale = float(self.viewport['scale']) if self.viewport is not None else 1.0
        for region in map_manager.get_facility_regions():
            facility_type = str(region.get('type', 'boundary'))
            is_selected = (
                (facility_type == 'wall' and self.selected_wall_id == region.get('id'))
                or (facility_type != 'wall' and self.selected_terrain_id == region.get('id'))
            )
            if interactive and not is_selected:
                continue
            if region.get('shape') == 'line':
                color = self._wall_color(region) or self.colors['white']
                x1, y1 = self.world_to_screen(region['x1'], region['y1'])
                x2, y2 = self.world_to_screen(region['x2'], region['y2'])
                thickness = max(2, int(region.get('thickness', 12) * scale))
                pygame.draw.line(target_surface, color, (x1, y1), (x2, y2), thickness)
                if interactive and is_selected:
                    pygame.draw.line(target_surface, self.colors['yellow'], (x1, y1), (x2, y2), max(1, thickness // 3))
                    pygame.draw.circle(target_surface, self.colors['yellow'], (x1, y1), 5)
                    pygame.draw.circle(target_surface, self.colors['yellow'], (x2, y2), 5)
                continue

            if region.get('shape') == 'polygon':
                color = color_map[facility_type] if facility_type in color_map else self.colors['white']
                points = [self.world_to_screen(point[0], point[1]) for point in region.get('points', [])]
                if len(points) < 3:
                    continue
                pygame.draw.polygon(target_surface, color, points, 2 if interactive else 1)
                if interactive and is_selected:
                    pygame.draw.polygon(target_surface, self.colors['yellow'], points, 2)
                    for point in points:
                        pygame.draw.circle(target_surface, self.colors['yellow'], point, 4)
                continue

            if region.get('shape') != 'rect':
                continue
            color = color_map[facility_type] if facility_type in color_map else self.colors['white']
            x1, y1 = self.world_to_screen(region['x1'], region['y1'])
            x2, y2 = self.world_to_screen(region['x2'], region['y2'])
            rect = pygame.Rect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
            if facility_type == 'outpost':
                center_x = rect.x + rect.width // 2
                center_y = rect.y + rect.height // 2
                radius = max(10, min(rect.width, rect.height) // 2)
                pygame.draw.circle(target_surface, color, (center_x, center_y), radius, 3)
                pygame.draw.circle(target_surface, color, (center_x, center_y), max(6, radius - 7), 1)
            else:
                pygame.draw.rect(target_surface, color, rect, 2 if interactive else 1)
            if interactive and is_selected:
                pygame.draw.rect(target_surface, self.colors['yellow'], rect, 2)

    def render_drag_preview(self):
        if self.viewport is None or (not self._facility_edit_active() and not self._terrain_brush_active()):
            return
        slope_preview_points = self._slope_preview_polygon_points() if self.terrain_shape_mode == 'slope' else []
        if self._terrain_shape_tool_active() and self.terrain_shape_mode == 'slope' and slope_preview_points:
            preview_points = [self.world_to_screen(point[0], point[1]) for point in slope_preview_points]
            if not self._slope_direction_mode_active() and self.mouse_world is not None:
                preview_target = self._current_terrain_target(self.mouse_world)
                preview_points.append(self.world_to_screen(preview_target[0], preview_target[1]))
            if len(preview_points) >= 2:
                pygame.draw.lines(self.screen, self.colors['selection'], False, preview_points, 2)
            base_count = len(slope_preview_points)
            for point in preview_points[:base_count]:
                pygame.draw.circle(self.screen, self.colors['selection'], point, 4)
            if len(slope_preview_points) >= 3:
                first_point = self.world_to_screen(slope_preview_points[0][0], slope_preview_points[0][1])
                pygame.draw.circle(self.screen, self.colors['yellow'], first_point, 6, 1)
            direction_start, direction_end = self._current_slope_direction_points()
            if direction_start is not None and direction_end is not None:
                start = self.world_to_screen(direction_start[0], direction_start[1])
                end = self.world_to_screen(direction_end[0], direction_end[1])
                pygame.draw.line(self.screen, self.colors['blue'], start, end, 3)
            return
        if self._terrain_shape_tool_active() and self.terrain_shape_mode in {'polygon', 'smooth_polygon'} and self.polygon_points:
            preview_points = [self.world_to_screen(point[0], point[1]) for point in self.polygon_points]
            if self.mouse_world is not None:
                preview_target = self._current_terrain_target(self.mouse_world)
                preview_points.append(self.world_to_screen(preview_target[0], preview_target[1]))
            if len(preview_points) >= 2:
                pygame.draw.lines(self.screen, self.colors['selection'], False, preview_points, 2)
            for point in preview_points[:-1] if len(preview_points) > len(self.polygon_points) else preview_points:
                pygame.draw.circle(self.screen, self.colors['selection'], point, 4)
            if len(self.polygon_points) >= 3:
                first_point = self.world_to_screen(self.polygon_points[0][0], self.polygon_points[0][1])
                pygame.draw.circle(self.screen, self.colors['yellow'], first_point, 6, 1)
            return

        facility = self._selected_region_option()
        if facility is None:
            return
        if self._facility_edit_active() and facility['type'] != 'wall' and self.facility_draw_shape == 'polygon' and self.polygon_points:
            preview_points = [self.world_to_screen(point[0], point[1]) for point in self.polygon_points]
            if self.mouse_world is not None:
                preview_target = self._current_facility_target(self.mouse_world)
                preview_points.append(self.world_to_screen(preview_target[0], preview_target[1]))
            if len(preview_points) >= 2:
                pygame.draw.lines(self.screen, self.colors['selection'], False, preview_points, 2)
            for point in preview_points[:-1] if len(preview_points) > len(self.polygon_points) else preview_points:
                pygame.draw.circle(self.screen, self.colors['selection'], point, 4)
            if len(self.polygon_points) >= 3:
                first_point = self.world_to_screen(self.polygon_points[0][0], self.polygon_points[0][1])
                pygame.draw.circle(self.screen, self.colors['yellow'], first_point, 6, 1)
            return

        if not self.drag_start or not self.drag_current:
            return
        start_x, start_y = self.world_to_screen(self.drag_start[0], self.drag_start[1])
        current_x, current_y = self.world_to_screen(self.drag_current[0], self.drag_current[1])
        if self._terrain_select_mode_active():
            rect = pygame.Rect(
                min(start_x, current_x),
                min(start_y, current_y),
                abs(current_x - start_x),
                abs(current_y - start_y),
            )
            pygame.draw.rect(self.screen, self.colors['selection'], rect, 2)
            return
        if self._facility_edit_active() and facility['type'] == 'wall':
            pygame.draw.line(self.screen, self.colors['selection'], (start_x, start_y), (current_x, current_y), 4)
            return
        if self._terrain_shape_tool_active() and self.terrain_shape_mode == 'line':
            pygame.draw.line(self.screen, self.colors['selection'], (start_x, start_y), (current_x, current_y), max(2, self.terrain_brush_radius * 2 + 2))
            return
        if self._terrain_shape_tool_active() and self.terrain_shape_mode == 'circle':
            radius = max(1, int(math.hypot(current_x - start_x, current_y - start_y)))
            pygame.draw.circle(self.screen, self.colors['selection'], (start_x, start_y), radius, 2)
            return
        if self._facility_edit_active() and self.facility_draw_shape == 'circle':
            radius = max(1, int(math.hypot(current_x - start_x, current_y - start_y)))
            pygame.draw.circle(self.screen, self.colors['selection'], (start_x, start_y), radius, 2)
            return
        rect = pygame.Rect(
            min(start_x, current_x),
            min(start_y, current_y),
            abs(current_x - start_x),
            abs(current_y - start_y),
        )
        pygame.draw.rect(self.screen, self.colors['selection'], rect, 2)

    def render_aim_fov(self, game_engine):
        if self.viewport is None or not self.show_aim_fov:
            return

        size = (self.window_width, self.window_height)
        if self.aim_fov_overlay_surface is None or self.aim_fov_overlay_size != size:
            self.aim_fov_overlay_surface = pygame.Surface(size, pygame.SRCALPHA)
            self.aim_fov_overlay_size = size
            self.aim_fov_overlay_cache_key = None
        max_distance = game_engine.map_manager.meters_to_world_units(
            game_engine.rules_engine.rules.get('shooting', {}).get('auto_aim_max_distance_m', 8.0)
        )
        fov_deg = game_engine.rules_engine.rules.get('shooting', {}).get('auto_aim_fov_deg', 50.0)
        half_fov = fov_deg / 2.0
        relevant_entities = []

        for entity in game_engine.entity_manager.entities:
            if entity.type not in {'robot', 'sentry'} or not entity.is_alive():
                continue
            if entity.type == 'robot' and entity.robot_type == '工程':
                continue
            if not self._world_point_visible(entity.position['x'], entity.position['y'], padding_px=96):
                continue
            relevant_entities.append((
                entity.id,
                entity.team,
                round(float(entity.position['x']), 1),
                round(float(entity.position['y']), 1),
                round(float(getattr(entity, 'position', {}).get('z', 0.0)), 2),
                round(float(getattr(entity, 'turret_angle', entity.angle)), 2),
            ))

        if not relevant_entities:
            self.aim_fov_overlay_cache_key = None
            return

        overlay_key = (
            size,
            int(self.viewport['map_x']),
            int(self.viewport['map_y']),
            int(self.viewport['map_width']),
            int(self.viewport['map_height']),
            round(float(self.viewport['scale']), 4),
            getattr(game_engine.map_manager, 'raster_version', 0),
            round(float(max_distance), 2),
            round(float(fov_deg), 2),
            tuple(relevant_entities),
        )
        overlay = self.aim_fov_overlay_surface
        if self.aim_fov_overlay_cache_key != overlay_key:
            overlay.fill((0, 0, 0, 0))
            for entity in game_engine.entity_manager.entities:
                if entity.type not in {'robot', 'sentry'} or not entity.is_alive():
                    continue
                if entity.type == 'robot' and entity.robot_type == '工程':
                    continue
                if not self._world_point_visible(entity.position['x'], entity.position['y'], padding_px=96):
                    continue

                center_x, center_y = self.world_to_screen(entity.position['x'], entity.position['y'])
                turret_center = (center_x, center_y - 2)
                turret_angle = getattr(entity, 'turret_angle', entity.angle)
                origin_height_m = float(getattr(entity, 'position', {}).get('z', game_engine.map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))) + float(getattr(entity, 'gimbal_height_m', 0.50)) * self._entity_vertical_scale(entity)
                visibility = game_engine.map_manager.compute_fov_visibility(
                    (entity.position['x'], entity.position['y']),
                    turret_angle,
                    fov_deg,
                    max_distance,
                    angle_step_deg=1.25,
                    include_mask=False,
                    origin_height_m=origin_height_m,
                    terrain_height_scale=1.0,
                    max_pitch_up_deg=float(getattr(entity, 'max_pitch_up_deg', 40.0)),
                    max_pitch_down_deg=float(getattr(entity, 'max_pitch_down_deg', 35.0)),
                )
                polygon_world = visibility.get('polygon_world', ())
                polygon = [self.world_to_screen(point[0], point[1]) for point in polygon_world]
                color = self._aim_fov_colors(entity.team)[1]
                if len(polygon) >= 3:
                    pygame.draw.polygon(overlay, color, polygon)
                    pygame.draw.polygon(overlay, (*color[:3], min(220, color[3] + 60)), polygon, 1)

                self._draw_fov_edges(overlay, turret_center, turret_angle, half_fov, max_distance * self.viewport['scale'], entity.team)
            self.aim_fov_overlay_cache_key = overlay_key

        self.screen.blit(overlay, (0, 0))

    def _aim_fov_colors(self, team):
        if team == 'red':
            return [
                (214, 63, 63, 76),
                (236, 166, 66, 64),
                (255, 216, 114, 48),
            ]
        return [
            (53, 112, 214, 76),
            (84, 166, 255, 64),
            (152, 212, 255, 48),
        ]

    def _build_sector_polygon(self, center, start_angle, end_angle, inner_radius, outer_radius, steps=18):
        if outer_radius <= 0:
            return []

        cx, cy = center
        points = []
        for index in range(steps + 1):
            angle = math.radians(start_angle + (end_angle - start_angle) * index / steps)
            points.append((cx + math.cos(angle) * outer_radius, cy + math.sin(angle) * outer_radius))

        if inner_radius <= 1:
            return [center] + points

        for index in range(steps, -1, -1):
            angle = math.radians(start_angle + (end_angle - start_angle) * index / steps)
            points.append((cx + math.cos(angle) * inner_radius, cy + math.sin(angle) * inner_radius))
        return points

    def _draw_fov_edges(self, surface, center, turret_angle, half_fov, radius, team):
        edge_color = self.colors['red'] if team == 'red' else self.colors['blue']
        for angle in [turret_angle - half_fov, turret_angle, turret_angle + half_fov]:
            rad = math.radians(angle)
            end_pos = (
                center[0] + math.cos(rad) * radius,
                center[1] + math.sin(rad) * radius,
            )
            pygame.draw.line(surface, (*edge_color, 140), center, end_pos, 1)

    def render_entities(self, entities):
        for entity in entities:
            if entity.is_alive() or entity.type in {'robot', 'sentry'}:
                self.render_entity(entity)
        self.render_projectile_traces()
        self.render_ai_navigation_overlay(entities)
        self.render_hero_deployment_overlay(entities)

    def render_projectile_traces(self):
        if self.viewport is None or self.game_engine is None:
            return
        rules_engine = getattr(self.game_engine, 'rules_engine', None)
        traces = list(getattr(rules_engine, 'projectile_traces', ())) if rules_engine is not None else []
        if not traces:
            return
        size = (self.window_width, self.window_height)
        if self.projectile_overlay_surface is None or self.projectile_overlay_size != size:
            self.projectile_overlay_surface = pygame.Surface(size, pygame.SRCALPHA)
            self.projectile_overlay_size = size
        overlay = self.projectile_overlay_surface
        overlay.fill((0, 0, 0, 0))
        for trace in traces:
            trace_points = self._trace_path_points(trace, self.game_engine.map_manager)
            if len(trace_points) < 2:
                continue
            lifetime = max(1e-6, float(trace.get('lifetime', 0.12)))
            progress = max(0.0, min(1.0, float(trace.get('elapsed', 0.0)) / lifetime))
            tail_progress = max(0.0, progress - 0.16)
            tip_world = self._trace_point_at_progress(trace_points, progress)
            tail_world = self._trace_point_at_progress(trace_points, tail_progress)
            if tip_world is None:
                continue
            polyline = [self.world_to_screen(point[0], point[1]) for point in trace_points]
            tip = self.world_to_screen(tip_world[0], tip_world[1])
            tail = self.world_to_screen(tail_world[0], tail_world[1]) if tail_world is not None else tip
            is_large = trace.get('ammo_type') == '42mm'
            color_rgb = (255, 184, 90) if is_large else (255, 244, 170)
            alpha = 220 if is_large else 170
            width = 4 if is_large else 2
            radius = 4 if is_large else 2
            if len(polyline) >= 2:
                pygame.draw.lines(overlay, (*color_rgb, min(120, alpha)), False, polyline, 1 if is_large else 1)
            pygame.draw.line(overlay, (*color_rgb, alpha), tail, tip, width)
            pygame.draw.circle(overlay, (*color_rgb, min(255, alpha + 20)), tip, radius)
        self.screen.blit(overlay, (0, 0))

    def render_ai_navigation_overlay(self, entities):
        if self.viewport is None:
            return
        nav_items = []
        for entity in entities:
            if entity.type not in {'robot', 'sentry'} or not entity.is_alive():
                continue
            navigation_target = getattr(entity, 'ai_navigation_target', None)
            movement_target = getattr(entity, 'ai_movement_target', None)
            waypoint = getattr(entity, 'ai_navigation_waypoint', None)
            path_preview = getattr(entity, 'ai_path_preview', ())
            path_valid = bool(getattr(entity, 'ai_navigation_path_valid', False))
            path_state = getattr(entity, 'ai_navigation_path_state', 'passable')
            velocity = getattr(entity, 'ai_navigation_velocity', (0.0, 0.0))
            nav_radius = float(getattr(entity, 'ai_navigation_radius', 0.0))
            if navigation_target is None and movement_target is None and waypoint is None and not path_preview:
                continue
            if not path_valid and waypoint is None and len(path_preview) < 2 and navigation_target is None and movement_target is None:
                continue
            marker_target = navigation_target or movement_target or waypoint
            if not self._world_point_visible(entity.position['x'], entity.position['y'], padding_px=96):
                marker_visible = marker_target is not None and self._world_point_visible(marker_target[0], marker_target[1], padding_px=96)
                if not marker_visible:
                    continue
            nav_items.append((
                entity,
                navigation_target,
                movement_target,
                waypoint,
                path_preview,
                path_valid,
                path_state,
                velocity,
                nav_radius,
            ))

        if not nav_items:
            self.ai_navigation_overlay_cache_key = None
            return

        size = (self.window_width, self.window_height)
        if self.ai_navigation_overlay_surface is None or self.ai_navigation_overlay_size != size:
            self.ai_navigation_overlay_surface = pygame.Surface(size, pygame.SRCALPHA)
            self.ai_navigation_overlay_size = size
            self.ai_navigation_overlay_cache_key = None

        overlay_key = (
            size,
            int(self.viewport['map_x']),
            int(self.viewport['map_y']),
            int(self.viewport['map_width']),
            int(self.viewport['map_height']),
            round(float(self.viewport['scale']), 4),
            tuple(
                (
                    entity.id,
                    round(float(entity.position['x']), 1),
                    round(float(entity.position['y']), 1),
                    entity.team,
                    tuple((round(float(point[0]), 1), round(float(point[1]), 1)) for point in path_preview),
                    None if navigation_target is None else (round(float(navigation_target[0]), 1), round(float(navigation_target[1]), 1)),
                    None if movement_target is None else (round(float(movement_target[0]), 1), round(float(movement_target[1]), 1)),
                    None if waypoint is None else (round(float(waypoint[0]), 1), round(float(waypoint[1]), 1)),
                    bool(path_valid),
                    str(path_state),
                    round(float(velocity[0]), 2),
                    round(float(velocity[1]), 2),
                    round(float(nav_radius), 2),
                )
                for entity, navigation_target, movement_target, waypoint, path_preview, path_valid, path_state, velocity, nav_radius in nav_items
            ),
        )
        overlay = self.ai_navigation_overlay_surface
        if self.ai_navigation_overlay_cache_key != overlay_key:
            overlay.fill((0, 0, 0, 0))
            for entity, navigation_target, movement_target, waypoint, path_preview, path_valid, path_state, velocity, nav_radius in nav_items:
                marker_target = navigation_target or movement_target or waypoint

                team_color = self.colors['red'] if entity.team == 'red' else self.colors['blue']
                if path_state == 'blocked':
                    color_rgb = (255, 120, 120)
                elif path_state == 'step-passable':
                    color_rgb = self.colors['yellow']
                else:
                    color_rgb = team_color
                line_color = (*color_rgb, 140)
                center = self.world_to_screen(entity.position['x'], entity.position['y'])

                if len(path_preview) >= 2:
                    preview_points = [self.world_to_screen(point[0], point[1]) for point in path_preview]
                    pygame.draw.lines(overlay, line_color, False, preview_points, 2)
                    for point in preview_points[1:]:
                        pygame.draw.circle(overlay, (*color_rgb, 110), point, 3)

                if marker_target is not None:
                    marker_alpha = 90 if path_valid else 64
                    marker_outline_alpha = 178 if path_valid else 124
                    marker_pos = self.world_to_screen(marker_target[0], marker_target[1])
                    pygame.draw.circle(overlay, (*color_rgb, marker_alpha), marker_pos, 11)
                    pygame.draw.circle(overlay, (*color_rgb, marker_outline_alpha), marker_pos, 11, 2)
                    pygame.draw.line(overlay, (*color_rgb, marker_outline_alpha), (marker_pos[0] - 6, marker_pos[1]), (marker_pos[0] + 6, marker_pos[1]), 2)
                    pygame.draw.line(overlay, (*color_rgb, marker_outline_alpha), (marker_pos[0], marker_pos[1] - 6), (marker_pos[0], marker_pos[1] + 6), 2)
                    if nav_radius > 1.0:
                        radius_px = max(8, int(nav_radius * self.viewport['scale']))
                        pygame.draw.circle(overlay, (*color_rgb, 64), marker_pos, radius_px, 1)

                arrow_dx = float(velocity[0])
                arrow_dy = float(velocity[1])
                if abs(arrow_dx) <= 1e-6 and abs(arrow_dy) <= 1e-6 and marker_target is not None:
                    arrow_dx = marker_target[0] - entity.position['x']
                    arrow_dy = marker_target[1] - entity.position['y']
                arrow_len = math.hypot(arrow_dx, arrow_dy)
                if arrow_len > 1e-6:
                    arrow_alpha = 178 if path_valid else 128
                    scale = min(56.0, max(28.0, arrow_len * self.viewport['scale'] * 0.35)) / arrow_len
                    end_pos = (
                        center[0] + arrow_dx * scale,
                        center[1] + arrow_dy * scale,
                    )
                    pygame.draw.line(overlay, (*color_rgb, arrow_alpha), center, end_pos, 4)
                    heading = math.atan2(end_pos[1] - center[1], end_pos[0] - center[0])
                    head_size = 10.0
                    left = (
                        end_pos[0] - math.cos(heading - math.pi / 6.0) * head_size,
                        end_pos[1] - math.sin(heading - math.pi / 6.0) * head_size,
                    )
                    right = (
                        end_pos[0] - math.cos(heading + math.pi / 6.0) * head_size,
                        end_pos[1] - math.sin(heading + math.pi / 6.0) * head_size,
                    )
                    pygame.draw.polygon(overlay, (*color_rgb, arrow_alpha), [end_pos, left, right])
            self.ai_navigation_overlay_cache_key = overlay_key
        if overlay is not None:
            self.screen.blit(overlay, (0, 0))

    def render_hero_deployment_overlay(self, entities):
        if self.viewport is None or self.game_engine is None:
            return
        overlay = None
        labels = []
        for entity in entities:
            if not entity.is_alive() or getattr(entity, 'robot_type', '') != '英雄':
                continue
            if not bool(getattr(entity, 'hero_deployment_active', False)):
                continue
            target = self._resolve_target_entity(entity)
            if target is None or target.type not in {'outpost', 'base'} or not target.is_alive():
                continue
            if not (self._world_point_visible(entity.position['x'], entity.position['y'], padding_px=80) or self._world_point_visible(target.position['x'], target.position['y'], padding_px=80)):
                continue
            if overlay is None:
                overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
            start = self.world_to_screen(entity.position['x'], entity.position['y'])
            end = self.world_to_screen(target.position['x'], target.position['y'])
            glow_layers = [
                ((82, 255, 214, 36), 9),
                ((82, 255, 214, 72), 5),
                ((205, 255, 242, 220), 2),
            ]
            for color, width in glow_layers:
                pygame.draw.line(overlay, color, start, end, width)
            pygame.draw.circle(overlay, (82, 255, 214, 160), end, 10, 2)
            hit_probability = float(getattr(entity, 'hero_deployment_hit_probability', 0.0))
            labels.append((f'吊射 {hit_probability * 100:.0f}%', (end[0] + 10, end[1] - 16)))
        if overlay is not None:
            self.screen.blit(overlay, (0, 0))
        for text, pos in labels:
            label = self.tiny_font.render(text, True, (170, 255, 230))
            self.screen.blit(label, pos)

    def render_entity(self, entity):
        x, y = self.world_to_screen(entity.position['x'], entity.position['y'])
        if not self._screen_point_visible((x, y), padding_px=64):
            return
        if entity.is_alive():
            color = self.colors['red'] if entity.team == 'red' else self.colors['blue']
        else:
            color = self.colors['gray']

        if entity.type == 'robot':
            self.render_robot(entity, x, y, color)
        elif entity.type == 'uav':
            self.render_uav(entity, x, y, color)
        elif entity.type == 'sentry':
            self.render_sentry(entity, x, y, color)
        elif entity.type == 'outpost':
            self.render_outpost(entity, x, y, color)
        elif entity.type == 'base':
            self.render_base(entity, x, y, color)
        elif entity.type == 'dart':
            self.render_dart(entity, x, y, color)
        elif entity.type == 'radar':
            self.render_radar(entity, x, y, color)

        self.render_health_bar(entity, x, y)
        self.render_entity_status(entity, x, y)

    def render_robot(self, entity, x, y, color):
        radius = self._entity_draw_radius(entity)
        self._render_chassis_with_armor(entity, x, y, radius, color, style='robot')
        self._render_wheels(entity, x, y, radius)
        if entity.robot_type == '工程':
            self.render_engineer_arm(entity, x, y, radius)
        else:
            turret_angle = math.radians(getattr(entity, 'turret_angle', entity.angle))
            turret_radius = max(5, radius - 2)
            pygame.draw.circle(self.screen, (235, 235, 235), (x, y - 2), turret_radius)
            end_x = x + math.cos(turret_angle) * (radius * 1.6)
            end_y = y - 2 + math.sin(turret_angle) * (radius * 1.6)
            pygame.draw.line(self.screen, self.colors['black'], (x, y - 2), (end_x, end_y), 3)

        robot_num = entity.id.split('_')[-1][-1]
        num_text = self.tiny_font.render(robot_num, True, self.colors['white'])
        self.screen.blit(num_text, num_text.get_rect(center=(x, y)))

        if entity.robot_type:
            type_text = self.tiny_font.render(entity.robot_type, True, self.colors['white'])
            self.screen.blit(type_text, type_text.get_rect(center=(x, y + radius + 12)))

    def render_engineer_arm(self, entity, x, y, radius):
        arm_angle = math.radians(getattr(entity, 'turret_angle', entity.angle))
        base_center = (x, y - 2)
        pygame.draw.circle(self.screen, (215, 215, 215), base_center, max(4, radius - 3))
        elbow_x = x + math.cos(arm_angle) * (radius * 0.95)
        elbow_y = y - 2 + math.sin(arm_angle) * (radius * 0.95)
        claw_x = x + math.cos(arm_angle) * (radius * 1.7)
        claw_y = y - 2 + math.sin(arm_angle) * (radius * 1.7)
        pygame.draw.line(self.screen, self.colors['black'], base_center, (elbow_x, elbow_y), 4)
        pygame.draw.line(self.screen, self.colors['black'], (elbow_x, elbow_y), (claw_x, claw_y), 3)
        claw_spread = math.radians(24)
        claw_len = radius * 0.45
        for sign in (-1, 1):
            tip_x = claw_x + math.cos(arm_angle + claw_spread * sign) * claw_len
            tip_y = claw_y + math.sin(arm_angle + claw_spread * sign) * claw_len
            pygame.draw.line(self.screen, self.colors['black'], (claw_x, claw_y), (tip_x, tip_y), 2)

    def render_uav(self, entity, x, y, color):
        radius = self.entity_radius['uav']
        pygame.draw.circle(self.screen, color, (x, y), radius)
        pygame.draw.circle(self.screen, self.colors['white'], (x, y), radius // 2)

    def render_sentry(self, entity, x, y, color):
        radius = self._entity_draw_radius(entity)
        self._render_chassis_with_armor(entity, x, y, radius, color, style='sentry')
        self._render_wheels(entity, x, y, radius)
        turret_angle = math.radians(getattr(entity, 'turret_angle', entity.angle))
        turret_center = (x, y - 2)
        pygame.draw.circle(self.screen, self.colors['white'], turret_center, radius // 2 + 2)
        end_x = turret_center[0] + math.cos(turret_angle) * (radius * 1.8)
        end_y = turret_center[1] + math.sin(turret_angle) * (radius * 1.8)
        pygame.draw.line(self.screen, self.colors['black'], turret_center, (end_x, end_y), 3)
        pygame.draw.circle(self.screen, self.colors['black'], turret_center, 2)

    def _entity_draw_radius(self, entity):
        fallback = self.entity_radius['sentry'] if entity.type == 'sentry' else self.entity_radius['robot']
        return int(max(8.0, float(getattr(entity, 'collision_radius', fallback)) * 0.55))

    def _render_chassis_with_armor(self, entity, x, y, radius, color, style='robot'):
        body_angle = math.radians(getattr(entity, 'angle', 0.0))
        body_color = (168, 176, 184)
        body_outline = (78, 84, 92)
        armor_color = (224, 229, 234)
        team_light_color = (232, 72, 72) if entity.team == 'red' else (72, 148, 255)
        if style == 'sentry':
            body_local = [
                (-radius, radius * 0.45),
                (-radius * 0.55, -radius + 2),
                (radius * 0.55, -radius + 2),
                (radius, radius * 0.45),
                (0.0, radius),
            ]
        else:
            top = -radius + 2
            bottom = radius * 0.6
            body_local = [
                (-radius, top),
                (radius, top),
                (radius, bottom),
                (-radius, bottom),
            ]

        body = self._rotate_local_polygon(body_local, x, y, body_angle)
        pygame.draw.polygon(self.screen, body_color, body)
        pygame.draw.polygon(self.screen, body_outline, body, 1)

        plate_long = max(6.0, radius * 0.54)
        plate_short = max(3.0, radius * 0.16)
        plate_offset = radius * 1.03
        heading_x = math.cos(body_angle)
        heading_y = math.sin(body_angle)
        side_x = -heading_y
        side_y = heading_x
        plate_centers = [
            (x + heading_x * plate_offset, y + heading_y * plate_offset),
            (x - heading_x * plate_offset, y - heading_y * plate_offset),
            (x + side_x * plate_offset, y + side_y * plate_offset),
            (x - side_x * plate_offset, y - side_y * plate_offset),
        ]
        plate_angles = [body_angle + math.pi / 2.0, body_angle + math.pi / 2.0, body_angle, body_angle]
        for center, plate_angle in zip(plate_centers, plate_angles):
            plate_local = [
                (-plate_long * 0.5, -plate_short * 0.5),
                (plate_long * 0.5, -plate_short * 0.5),
                (plate_long * 0.5, plate_short * 0.5),
                (-plate_long * 0.5, plate_short * 0.5),
            ]
            plate_poly = self._rotate_local_polygon(plate_local, center[0], center[1], plate_angle)
            pygame.draw.polygon(self.screen, armor_color, plate_poly)
            pygame.draw.polygon(self.screen, body_outline, plate_poly, 1)

            light_half = max(2.0, plate_long * 0.12)
            light_thickness = max(2.0, plate_short * 0.7)
            for light_center_x in (-plate_long * 0.36, plate_long * 0.36):
                light_local = [
                    (light_center_x - light_half, -light_thickness * 0.5),
                    (light_center_x + light_half, -light_thickness * 0.5),
                    (light_center_x + light_half, light_thickness * 0.5),
                    (light_center_x - light_half, light_thickness * 0.5),
                ]
                light_poly = self._rotate_local_polygon(light_local, center[0], center[1], plate_angle)
                pygame.draw.polygon(self.screen, team_light_color, light_poly)

    def _rotate_local_polygon(self, local_points, center_x, center_y, angle_rad):
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        points = []
        for local_x, local_y in local_points:
            world_x = center_x + local_x * cos_a - local_y * sin_a
            world_y = center_y + local_x * sin_a + local_y * cos_a
            points.append((int(world_x), int(world_y)))
        return points

    def _render_wheels(self, entity, x, y, radius):
        wheel_count = int(getattr(entity, 'wheel_count', 4))
        if wheel_count <= 0:
            return
        angle = math.radians(getattr(entity, 'angle', 0.0))
        heading_x = math.cos(angle)
        heading_y = math.sin(angle)
        side_x = -heading_y
        side_y = heading_x
        wheel_radius = max(2, int(radius * 0.22))
        wheel_color = (36, 36, 36)
        if wheel_count <= 2:
            offsets = [
                (-side_x * radius * 0.95, -side_y * radius * 0.95),
                (side_x * radius * 0.95, side_y * radius * 0.95),
            ]
        else:
            front = radius * 0.65
            side = radius * 0.9
            offsets = [
                (heading_x * front - side_x * side, heading_y * front - side_y * side),
                (heading_x * front + side_x * side, heading_y * front + side_y * side),
                (-heading_x * front - side_x * side, -heading_y * front - side_y * side),
                (-heading_x * front + side_x * side, -heading_y * front + side_y * side),
            ]
        for offset_x, offset_y in offsets:
            pygame.draw.circle(self.screen, wheel_color, (int(x + offset_x), int(y + offset_y)), wheel_radius)

    def render_outpost(self, entity, x, y, color):
        radius = self.entity_radius['outpost']
        pygame.draw.circle(self.screen, color, (x, y), radius, 4)
        pygame.draw.circle(self.screen, color, (x, y), max(8, radius - 8), 1)

    def render_base(self, entity, x, y, color):
        radius = self.entity_radius['base']
        pygame.draw.circle(self.screen, color, (x, y), radius, 3)
        pygame.draw.circle(self.screen, color, (x, y), radius // 2)

    def render_dart(self, entity, x, y, color):
        pygame.draw.circle(self.screen, color, (x, y), self.entity_radius['dart'])

    def render_radar(self, entity, x, y, color):
        radius = self.entity_radius['radar']
        pygame.draw.circle(self.screen, color, (x, y), radius)
        angle_rad = math.radians(entity.angle)
        line_length = radius * 2
        end_x = x + math.cos(angle_rad) * line_length
        end_y = y + math.sin(angle_rad) * line_length
        pygame.draw.line(self.screen, color, (x, y), (end_x, end_y), 2)

    def render_health_bar(self, entity, x, y):
        if entity.type == 'base':
            bar_width = 80
            bar_height = 8
            offset_y = 52
        elif entity.type == 'outpost':
            bar_width = 60
            bar_height = 6
            offset_y = 36
        else:
            bar_width = 40
            bar_height = 5
            offset_y = 22

        if not entity.is_alive() and entity.type in {'robot', 'sentry'} and getattr(entity, 'respawn_duration', 0) > 0:
            pygame.draw.rect(self.screen, self.colors['gray'], (x - bar_width // 2, y - offset_y, bar_width, bar_height))
            progress = 1.0 - (getattr(entity, 'respawn_timer', 0.0) / max(getattr(entity, 'respawn_duration', 1.0), 1e-6))
            progress = max(0.0, min(1.0, progress))
            pygame.draw.rect(self.screen, self.colors['blue'], (x - bar_width // 2, y - offset_y, bar_width * progress, bar_height))
            text = self.tiny_font.render(f'复活 {getattr(entity, "respawn_timer", 0.0):.1f}s', True, self.colors['white'])
            self.screen.blit(text, text.get_rect(center=(x, y - offset_y - 8)))
            return

        health_percent = 0 if entity.max_health <= 0 else entity.health / entity.max_health
        pygame.draw.rect(self.screen, self.colors['gray'], (x - bar_width // 2, y - offset_y, bar_width, bar_height))
        if health_percent > 0.5:
            health_color = self.colors['green']
        elif health_percent > 0.2:
            health_color = self.colors['yellow']
        else:
            health_color = self.colors['red']
        pygame.draw.rect(self.screen, health_color, (x - bar_width // 2, y - offset_y, bar_width * health_percent, bar_height))
        hp_text = self.tiny_font.render(f'{int(entity.health)}/{int(entity.max_health)}', True, self.colors['white'])
        self.screen.blit(hp_text, hp_text.get_rect(center=(x, y - offset_y - 8)))

    def render_entity_status(self, entity, x, y):
        statuses = []
        if getattr(entity, 'invincible_timer', 0.0) > 0:
            statuses.append(('无敌', self.colors['yellow']))
        if getattr(entity, 'weak_timer', 0.0) > 0:
            statuses.append(('虚弱', self.colors['red']))
        if getattr(entity, 'fort_buff_active', False):
            statuses.append(('堡垒增益', self.colors['green']))
        if getattr(entity, 'terrain_buff_timer', 0.0) > 0:
            statuses.append(('地形增益', self.colors['blue']))
        for buff_label in getattr(entity, 'active_buff_labels', [])[:2]:
            statuses.append((buff_label, self.colors['yellow']))
        if getattr(entity, 'carried_minerals', 0) > 0:
            statuses.append((f'矿物 x{int(entity.carried_minerals)}', self.colors['green']))
        heat_lock_state = getattr(entity, 'heat_lock_state', 'normal')
        if heat_lock_state == 'cooling_unlock':
            statuses.append(('热量锁定', self.colors['yellow']))
        elif heat_lock_state == 'match_locked':
            statuses.append(('发射机构锁死', self.colors['red']))
        target = self._resolve_target_entity(entity)
        if target is not None and entity.is_alive() and self.game_engine is not None:
            if bool(getattr(entity, 'hero_deployment_active', False)) and target.type in {'outpost', 'base'}:
                motion_label = '部署吊射'
                hit_probability = float(getattr(entity, 'hero_deployment_hit_probability', 0.0))
            else:
                motion_label = self.game_engine.rules_engine.describe_target_motion(target)
                hit_probability = float(getattr(entity, 'auto_aim_hit_probability', 0.0))
            statuses.append((f'{motion_label} {hit_probability * 100:.0f}%', self.colors['white']))
        if not statuses:
            return

        y_offset = y + 28
        for label, color in statuses:
            text = self.tiny_font.render(label, True, color)
            self.screen.blit(text, text.get_rect(center=(x, y_offset)))
            y_offset += 12

    def _handle_terrain_left_press(self, game_engine, world_pos):
        self._end_terrain_edit_batch(game_engine)
        self.terrain_painting = False
        self.terrain_erasing = False
        self.last_terrain_paint_grid_key = None
        if self._terrain_select_mode_active():
            self.drag_start = world_pos
            self.drag_current = world_pos
            return
        if self._terrain_paint_mode_active():
            self._clear_terrain_selection()
            self._record_undo_snapshot(game_engine, '笔刷涂抹地形')
            self._begin_terrain_edit_batch(game_engine)
            self.drag_start = world_pos
            self.drag_current = world_pos
            self.terrain_painting = True
            self._paint_terrain_at(game_engine, world_pos)
            return
        if self._terrain_eraser_mode_active():
            self._clear_terrain_selection()
            self._record_undo_snapshot(game_engine, '橡皮擦除地形')
            self._begin_terrain_edit_batch(game_engine)
            self.drag_start = world_pos
            self.drag_current = world_pos
            self.terrain_erasing = True
            self._apply_terrain_erase(game_engine, world_pos)
            return
        self._clear_terrain_selection()
        if self.terrain_shape_mode == 'slope' and self._slope_direction_mode_active():
            slope_target = world_pos
            if self.slope_direction_start is None:
                self.slope_direction_start = slope_target
                self.slope_direction_end = slope_target
                self.drag_current = slope_target
                game_engine.add_log(f'斜坡箭头起点已设置为 ({slope_target[0]}, {slope_target[1]})，继续左键设置终点', 'system')
            else:
                self.slope_direction_end = slope_target
                self.drag_current = slope_target
                self._commit_terrain_slope_polygon(game_engine)
            return
        if self.terrain_shape_mode in {'polygon', 'slope', 'smooth_polygon'}:
            world_pos = self._current_terrain_target(world_pos)
            if self.polygon_points and len(self.polygon_points) >= 3 and math.hypot(world_pos[0] - self.polygon_points[0][0], world_pos[1] - self.polygon_points[0][1]) <= 18:
                if self.terrain_shape_mode == 'slope':
                    self._begin_terrain_slope_direction(game_engine)
                elif self.terrain_shape_mode == 'smooth_polygon':
                    self._commit_terrain_smooth_polygon(game_engine)
                else:
                    self._commit_terrain_polygon(game_engine)
            else:
                self.polygon_points.append(world_pos)
                self.drag_current = world_pos
                log_prefix = '斜坡区域' if self.terrain_shape_mode == 'slope' else ('平滑多边形' if self.terrain_shape_mode == 'smooth_polygon' else '地形多边形')
                game_engine.add_log(f'{log_prefix}已添加顶点 ({world_pos[0]}, {world_pos[1]})', 'system')
            return
        terrain_target = self._current_terrain_target(world_pos)
        self.drag_start = terrain_target
        self.drag_current = terrain_target

    def _apply_terrain_erase(self, game_engine, world_pos):
        removed = game_engine.map_manager.erase_terrain_grid(world_pos[0], world_pos[1], self.terrain_brush_radius)
        if removed:
            self.terrain_paint_dirty = True

    def _handle_terrain_right_press(self, game_engine, world_pos):
        if self.terrain_shape_mode == 'slope' and self._slope_direction_mode_active():
            self._reset_slope_state()
            self.drag_start = None
            self.drag_current = None
            game_engine.add_log('已取消当前斜坡绘制', 'system')
            return
        if self.terrain_shape_mode in {'polygon', 'slope', 'smooth_polygon'} and self.polygon_points:
            if len(self.polygon_points) >= 3:
                if self.terrain_shape_mode == 'slope':
                    self._begin_terrain_slope_direction(game_engine)
                elif self.terrain_shape_mode == 'smooth_polygon':
                    self._commit_terrain_smooth_polygon(game_engine)
                else:
                    self._commit_terrain_polygon(game_engine)
            else:
                self.polygon_points = []
                self.drag_start = None
                self.drag_current = None
                game_engine.add_log('斜坡/多边形顶点不足，已取消', 'system')
            return
        cell = game_engine.map_manager.get_terrain_grid_cell(world_pos[0], world_pos[1])
        if cell is None:
            self._clear_terrain_selection()
            return
        self._set_terrain_selection({game_engine.map_manager._terrain_cell_key(cell['x'], cell['y'])})

    def _handle_facility_left_press(self, game_engine, world_pos):
        self.selected_terrain_cell_key = None
        facility = self._selected_region_option()
        if facility is None:
            return
        if facility['type'] == 'wall':
            world_pos = self._current_facility_target(world_pos)
            if self.drag_start is None:
                self.drag_start = world_pos
                self.drag_current = world_pos
                game_engine.add_log(f'墙体起点已设置为 ({world_pos[0]}, {world_pos[1]})', 'system')
            else:
                self._commit_facility_region(game_engine, self.drag_start, world_pos)
                self.drag_start = None
                self.drag_current = None
            return

        if self.facility_draw_shape == 'polygon':
            world_pos = self._current_facility_target(world_pos)
            if self.polygon_points and len(self.polygon_points) >= 3 and math.hypot(world_pos[0] - self.polygon_points[0][0], world_pos[1] - self.polygon_points[0][1]) <= 18:
                self._commit_facility_polygon(game_engine)
            else:
                self.polygon_points.append(world_pos)
                self.drag_current = world_pos
                game_engine.add_log(f'多边形已添加顶点 ({world_pos[0]}, {world_pos[1]})', 'system')
            return

        self.drag_start = world_pos
        self.drag_current = world_pos

    def _handle_facility_right_press(self, game_engine, world_pos):
        if self.active_numeric_input is not None:
            self._commit_numeric_input(game_engine)
        selected = self._selected_region_option()
        if selected is None:
            return
        if selected['type'] != 'wall' and self.facility_draw_shape == 'polygon' and self.polygon_points:
            if len(self.polygon_points) >= 3:
                self._commit_facility_polygon(game_engine)
            else:
                self.polygon_points = []
                self.drag_current = None
                game_engine.add_log('多边形顶点不足，已取消', 'system')
            return
        if self.drag_start is not None and selected['type'] == 'wall':
            self.drag_start = None
            self.drag_current = None
            game_engine.add_log('已取消当前墙体绘制', 'system')
            return
        if world_pos is None:
            return
        facility = None
        for candidate in game_engine.map_manager.get_regions_at(world_pos[0], world_pos[1], region_types={selected.get('type')}):
            if candidate.get('type') != 'boundary':
                facility = candidate
                break
        if facility and facility.get('type') != 'boundary':
            if facility.get('type') == 'wall':
                self.selected_wall_id = facility['id']
            else:
                self.selected_terrain_id = facility['id']

    def _handle_terrain_pan_motion(self, rel):
        self.terrain_view_offset[0] += rel[0]
        self.terrain_view_offset[1] += rel[1]

    def _record_undo_snapshot(self, game_engine, label):
        if hasattr(game_engine, 'push_undo_snapshot'):
            game_engine.push_undo_snapshot(label)

    def _snap_wall_target(self, start, target):
        if start is None or target is None:
            return target
        delta_x = target[0] - start[0]
        delta_y = target[1] - start[1]
        distance = math.hypot(delta_x, delta_y)
        if distance <= 1e-6:
            return target
        angle = math.atan2(delta_y, delta_x)
        snapped_angle = round(angle / (math.pi / 4.0)) * (math.pi / 4.0)
        snapped_x = start[0] + math.cos(snapped_angle) * distance
        snapped_y = start[1] + math.sin(snapped_angle) * distance
        return int(round(snapped_x)), int(round(snapped_y))

    def _snap_orthogonal_target(self, start, target):
        if start is None or target is None:
            return target
        delta_x = target[0] - start[0]
        delta_y = target[1] - start[1]
        if abs(delta_x) >= abs(delta_y):
            return int(round(target[0])), int(round(start[1]))
        return int(round(start[0])), int(round(target[1]))

    def _current_polygon_target(self, points, target):
        if not points:
            return target
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_SHIFT:
            return self._snap_orthogonal_target(points[-1], target)
        return target

    def _current_facility_target(self, world_pos):
        if not self._facility_edit_active():
            return world_pos
        selected = self._selected_region_option()
        if selected is None:
            return world_pos
        mods = pygame.key.get_mods()
        if selected['type'] == 'wall' and self.drag_start is not None and mods & pygame.KMOD_SHIFT:
            return self._snap_wall_target(self.drag_start, world_pos)
        if self.facility_draw_shape == 'polygon' and self.polygon_points:
            return self._current_polygon_target(self.polygon_points, world_pos)
        return world_pos

    def _current_terrain_target(self, world_pos):
        if not self._terrain_shape_tool_active():
            return world_pos
        mods = pygame.key.get_mods()
        if self.terrain_shape_mode == 'line' and self.drag_start is not None and mods & pygame.KMOD_SHIFT:
            return self._snap_wall_target(self.drag_start, world_pos)
        if self.terrain_shape_mode in {'polygon', 'slope', 'smooth_polygon'} and self.polygon_points:
            return self._current_polygon_target(self.polygon_points, world_pos)
        return world_pos

    def _reset_slope_state(self):
        self.polygon_points = []
        self.slope_region_points = []
        self.slope_direction_start = None
        self.slope_direction_end = None

    def _slope_direction_mode_active(self):
        return self._terrain_shape_tool_active() and self.terrain_shape_mode == 'slope' and len(self.slope_region_points) >= 3

    def _slope_preview_polygon_points(self):
        if self._slope_direction_mode_active():
            return list(self.slope_region_points)
        return list(self.polygon_points)

    def _current_slope_direction_points(self):
        if not self._slope_direction_mode_active() or self.slope_direction_start is None:
            return None, None
        return self.slope_direction_start, self.slope_direction_end or self.slope_direction_start

    def _begin_terrain_slope_direction(self, game_engine):
        if len(self.polygon_points) < 3:
            return
        self.slope_region_points = list(self.polygon_points)
        self.polygon_points = []
        self.slope_direction_start = None
        self.slope_direction_end = None
        self.drag_start = None
        self.drag_current = None
        game_engine.add_log('斜坡区域已确认，请左键依次设置箭头起点和终点', 'system')

    def _clear_terrain_selection(self):
        self.selected_terrain_cell_key = None
        self.selected_terrain_cell_keys = set()

    def _set_terrain_selection(self, selection_keys):
        keys = sorted(selection_keys)
        self.selected_terrain_cell_keys = set(keys)
        self.selected_terrain_cell_key = keys[0] if keys else None

    def _terrain_selection_keys(self):
        if self.selected_terrain_cell_keys:
            return set(self.selected_terrain_cell_keys)
        return {self.selected_terrain_cell_key} if self.selected_terrain_cell_key else set()

    def _collect_terrain_selection_keys(self, map_manager, start, end):
        grid_x1, grid_x2, grid_y1, grid_y2 = map_manager._grid_ranges_from_world_bounds(start[0], start[1], end[0], end[1])
        selection = set()
        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                key = map_manager._terrain_cell_key(grid_x, grid_y)
                if key in map_manager.terrain_grid_overrides:
                    selection.add(key)
        return selection

    def _apply_terrain_selection(self, game_engine, selection, source_label='框选'):
        selection = set(selection or ())
        self._set_terrain_selection(selection)
        if selection:
            if len(selection) == 1:
                grid_x, grid_y = game_engine.map_manager._decode_terrain_cell_key(next(iter(selection)))
                game_engine.add_log(f'已选中格栅 ({grid_x}, {grid_y})', 'system')
            else:
                suffix = '，可点确定执行平滑' if source_label.startswith('平滑') else ''
                game_engine.add_log(f'{source_label}已选中 {len(selection)} 个地形格栅{suffix}', 'system')
        else:
            empty_message = '当前多边形区域没有可 Smooth 的已编辑地形格栅' if source_label.startswith('平滑') else '当前框选区域没有已编辑地形格栅'
            game_engine.add_log(empty_message, 'system')

    def _apply_box_terrain_selection(self, game_engine, start, end):
        if start is None or end is None:
            self._clear_terrain_selection()
            return
        map_manager = game_engine.map_manager
        selection = self._collect_terrain_selection_keys(map_manager, start, end)
        if not selection:
            cell = map_manager.get_terrain_grid_cell(end[0], end[1])
            if cell is not None:
                selection.add(map_manager._terrain_cell_key(cell['x'], cell['y']))
        self._apply_terrain_selection(game_engine, selection, source_label='框选')

    def _commit_terrain_smooth_polygon(self, game_engine):
        if len(self.polygon_points) < 3:
            return
        map_manager = game_engine.map_manager
        normalized_points = map_manager._normalize_points(self.polygon_points)
        selection = {
            map_manager._terrain_cell_key(grid_x, grid_y)
            for grid_x, grid_y in map_manager._polygon_selected_cells(normalized_points)
            if map_manager._terrain_cell_key(grid_x, grid_y) in map_manager.terrain_grid_overrides
        }
        self._apply_terrain_selection(game_engine, selection, source_label='平滑多边形')
        self.polygon_points = []
        self.drag_current = None
        self.drag_start = None

    def _delete_selected_terrain_cells(self, game_engine):
        selection = sorted(self._terrain_selection_keys())
        if not selection:
            return
        label = f'删除 {len(selection)} 个格栅' if len(selection) > 1 else f'删除格栅 {selection[0]}'
        self._record_undo_snapshot(game_engine, label)
        removed_count = 0
        for key in selection:
            grid_x, grid_y = game_engine.map_manager._decode_terrain_cell_key(key)
            if game_engine.map_manager.remove_terrain_grid_cell(grid_x, grid_y):
                removed_count += 1
        if removed_count:
            self.terrain_paint_dirty = True
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log(f'已删除 {removed_count} 个格栅地形', 'system')
        self._clear_terrain_selection()

    def _smooth_selected_terrain_cells(self, game_engine, strength=None):
        selection = sorted(self._terrain_selection_keys())
        if not selection:
            game_engine.add_log('请先框选需要平滑的地形格栅', 'system')
            return
        applied_strength = max(0, min(3, int(strength if strength is not None else getattr(self, 'terrain_smooth_strength', 0))))
        if applied_strength <= 0:
            game_engine.add_log('当前区域平滑强度为 0，请先在工具栏选择 1-3', 'system')
            return
        self.terrain_smooth_strength = applied_strength
        self._record_undo_snapshot(game_engine, f'平滑 {len(selection)} 个格栅')
        result = game_engine.map_manager.smooth_terrain_cells(selection, intensity=applied_strength)
        if result.get('changed'):
            self.terrain_paint_dirty = True
            self._sync_terrain_grid_config(game_engine)
            game_engine.config.setdefault('simulator', {})['terrain_smooth_strength'] = applied_strength
            game_engine.add_log(f'已平滑 {result.get("cell_count", 0)} 个格栅，等级 {applied_strength}', 'system')
        else:
            game_engine.add_log('选中区域未产生可见的平滑变化', 'system')

    def _commit_terrain_line(self, game_engine, start, end):
        brush = self._selected_terrain_brush_def()
        self._record_undo_snapshot(game_engine, '直线范围地形')
        changed = game_engine.map_manager.paint_terrain_line(
            start[0],
            start[1],
            end[0],
            end[1],
            brush['type'],
            height_m=brush.get('height_m', 0.0),
            brush_radius=self.terrain_brush_radius,
            team=brush.get('team', 'neutral'),
            blocks_movement=brush.get('blocks_movement'),
            blocks_vision=brush.get('blocks_vision'),
        )
        if changed:
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log('已设置直线范围地形', 'system')

    def _commit_terrain_slope_polygon(self, game_engine):
        points = self.slope_region_points if len(self.slope_region_points) >= 3 else self.polygon_points
        if len(points) < 3:
            return
        direction_start, direction_end = self._current_slope_direction_points()
        if direction_start is None or direction_end is None or math.hypot(direction_end[0] - direction_start[0], direction_end[1] - direction_start[1]) <= 1e-6:
            game_engine.add_log('请先完成斜坡箭头方向设置', 'system')
            return
        brush = self._selected_terrain_brush_def()
        self._record_undo_snapshot(game_engine, '斜坡')
        result = game_engine.map_manager.paint_terrain_slope_polygon(
            points,
            brush['type'],
            team=brush.get('team', 'neutral'),
            blocks_movement=brush.get('blocks_movement'),
            blocks_vision=brush.get('blocks_vision'),
            direction_start=direction_start,
            direction_end=direction_end,
        )
        self._reset_slope_state()
        self.drag_current = None
        self.drag_start = None
        if result.get('changed'):
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log(
                f'已按箭头方向生成斜坡，影响 {result.get("cell_count", 0)} 个格栅，高度 {result.get("min_height", 0.0):.2f}m -> {result.get("max_height", 0.0):.2f}m',
                'system',
            )

    def _set_terrain_view_center(self, map_manager, world_pos):
        sidebar_width = self.panel_width if self.edit_mode != 'none' else 0
        available_width = self.window_width - sidebar_width - self.content_padding * 2
        available_height = self.window_height - self.toolbar_height - self.hud_height - self.content_padding * 2
        scale = min(
            available_width / max(1, map_manager.map_width),
            available_height / max(1, map_manager.map_height),
        )
        scale = max(scale, 0.1)
        draw_width = int(map_manager.map_width * scale)
        draw_height = int(map_manager.map_height * scale)
        base_map_x = self.content_padding + (available_width - draw_width) // 2
        base_map_y = self.toolbar_height + self.hud_height + self.content_padding + (available_height - draw_height) // 2
        content_center_x = self.content_padding + available_width / 2
        content_center_y = self.toolbar_height + self.hud_height + self.content_padding + available_height / 2
        self.terrain_view_offset[0] = int(content_center_x - world_pos[0] * scale - base_map_x)
        self.terrain_view_offset[1] = int(content_center_y - world_pos[1] * scale - base_map_y)

    def _handle_facility_left_release(self, game_engine, world_pos):
        selected = self._selected_region_option()
        if selected is None:
            self.drag_start = None
            self.drag_current = None
            return
        if selected['type'] == 'wall' or self.facility_draw_shape == 'polygon':
            return
        if world_pos is None or self.drag_start is None:
            self.drag_start = None
            self.drag_current = None
            return
        self._commit_facility_region(game_engine, self.drag_start, world_pos)
        self.drag_start = None
        self.drag_current = None

    def _commit_terrain_rect(self, game_engine, start, end):
        brush = self._selected_terrain_brush_def()
        self._record_undo_snapshot(game_engine, '矩形范围地形')
        game_engine.map_manager.paint_terrain_rect(
            start[0],
            start[1],
            end[0],
            end[1],
            brush['type'],
            height_m=brush.get('height_m', 0.0),
            team=brush.get('team', 'neutral'),
            blocks_movement=brush.get('blocks_movement'),
            blocks_vision=brush.get('blocks_vision'),
        )
        self._sync_terrain_grid_config(game_engine)
        game_engine.add_log('已设置矩形范围地形', 'system')

    def _commit_terrain_smooth_rect(self, game_engine, start, end):
        selection = self._collect_terrain_selection_keys(game_engine.map_manager, start, end)
        if not selection:
            game_engine.add_log('当前框选区域没有可 Smooth 的已编辑地形格栅', 'system')
            return
        self._apply_terrain_selection(game_engine, selection, source_label='平滑框选')

    def _commit_terrain_circle(self, game_engine, center, edge):
        brush = self._selected_terrain_brush_def()
        radius = math.hypot(edge[0] - center[0], edge[1] - center[1])
        if radius < game_engine.map_manager.terrain_grid_cell_size * 0.5:
            radius = max(radius, self.terrain_brush_radius * game_engine.map_manager.terrain_grid_cell_size)
        self._record_undo_snapshot(game_engine, '圆形范围地形')
        game_engine.map_manager.paint_terrain_circle(
            center[0],
            center[1],
            radius,
            brush['type'],
            height_m=brush.get('height_m', 0.0),
            team=brush.get('team', 'neutral'),
            blocks_movement=brush.get('blocks_movement'),
            blocks_vision=brush.get('blocks_vision'),
        )
        self._sync_terrain_grid_config(game_engine)
        game_engine.add_log(f'已设置圆形范围地形，半径 {radius:.1f}px', 'system')

    def _commit_terrain_polygon(self, game_engine):
        if len(self.polygon_points) < 3:
            return
        brush = self._selected_terrain_brush_def()
        self._record_undo_snapshot(game_engine, '多边形范围地形')
        changed = game_engine.map_manager.paint_terrain_polygon(
            self.polygon_points,
            brush['type'],
            height_m=brush.get('height_m', 0.0),
            team=brush.get('team', 'neutral'),
            blocks_movement=brush.get('blocks_movement'),
            blocks_vision=brush.get('blocks_vision'),
        )
        self.polygon_points = []
        self.drag_current = None
        self.drag_start = None
        if changed:
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log('已设置多边形范围地形', 'system')

    def _handle_terrain_left_release(self, game_engine, world_pos):
        if self._terrain_select_mode_active():
            end_pos = self.drag_current if self.drag_current is not None else world_pos
            self._apply_box_terrain_selection(game_engine, self.drag_start, end_pos)
            self.drag_start = None
            self.drag_current = None
            return
        if self._terrain_paint_mode_active() or self._terrain_eraser_mode_active():
            self.drag_start = None
            self.drag_current = None
            self._end_terrain_edit_batch(game_engine)
            if self.terrain_paint_dirty:
                self._sync_terrain_grid_config(game_engine)
            return
        if self.terrain_shape_mode in {'polygon', 'slope', 'smooth_polygon'}:
            return
        if world_pos is None or self.drag_start is None:
            self.drag_start = None
            self.drag_current = None
            return
        end_pos = self.drag_current if self.drag_current is not None else world_pos
        if self.terrain_shape_mode == 'rect':
            self._commit_terrain_rect(game_engine, self.drag_start, end_pos)
        elif self.terrain_shape_mode == 'smooth':
            self._commit_terrain_smooth_rect(game_engine, self.drag_start, end_pos)
        elif self.terrain_shape_mode == 'line':
            self._commit_terrain_line(game_engine, self.drag_start, end_pos)
        else:
            self._commit_terrain_circle(game_engine, self.drag_start, end_pos)
        self.drag_start = None
        self.drag_current = None

    def handle_event(self, event, game_engine):
        resize_events = {
            value for value in (
                getattr(pygame, 'VIDEORESIZE', None),
                getattr(pygame, 'WINDOWRESIZED', None),
                getattr(pygame, 'WINDOWSIZECHANGED', None),
            ) if value is not None
        }
        if event.type in resize_events:
            width = getattr(event, 'w', None) or getattr(event, 'x', None) or self.window_width
            height = getattr(event, 'h', None) or getattr(event, 'y', None) or self.window_height
            self._handle_window_resize(width, height)
            return True
        if self.standalone_3d_program and self.standalone_3d_state != 'in_match':
            if self._handle_standalone_program_event(event, game_engine):
                return True
        if self._handle_player_simulator_event(event, game_engine):
            return True
        if self._handle_terrain_overview_event(event, game_engine):
            return True
        if event.type == pygame.KEYDOWN:
            if self._handle_numeric_input_keydown(event, game_engine):
                return True
            mods = pygame.key.get_mods()
            if self._terrain_brush_active() and event.key in {pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4}:
                self.terrain_workflow_mode = {
                    pygame.K_1: 'select',
                    pygame.K_2: 'brush',
                    pygame.K_3: 'erase',
                    pygame.K_4: 'shape',
                }[event.key]
                self._end_terrain_edit_batch(game_engine)
                self.drag_start = None
                self.drag_current = None
                self._reset_slope_state()
                self.terrain_painting = False
                self.terrain_erasing = False
                return True
            if event.key == pygame.K_z and mods & pygame.KMOD_CTRL and not (mods & pygame.KMOD_SHIFT) and hasattr(game_engine, 'undo_last_edit'):
                if game_engine.undo_last_edit():
                    self.map_cache_surface = None
                    self.map_cache_size = None
                    self.terrain_3d_texture = None
                    self.terrain_3d_render_key = None
                    return True
                return False
            if (((event.key == pygame.K_y) and mods & pygame.KMOD_CTRL) or ((event.key == pygame.K_z) and mods & pygame.KMOD_CTRL and mods & pygame.KMOD_SHIFT)) and hasattr(game_engine, 'redo_last_edit'):
                if game_engine.redo_last_edit():
                    self.map_cache_surface = None
                    self.map_cache_size = None
                    self.terrain_3d_texture = None
                    self.terrain_3d_render_key = None
                    return True
                return False
            if event.key == pygame.K_ESCAPE and self.selected_hud_entity_id is not None:
                self.selected_hud_entity_id = None
                self.robot_detail_page = 0
                self.robot_detail_rect = None
                return True
            if event.key == pygame.K_ESCAPE and self.edit_mode == 'terrain' and (self.polygon_points or self.slope_region_points):
                self._reset_slope_state()
                self.drag_start = None
                self.drag_current = None
                game_engine.add_log('已取消当前范围绘制', 'system')
                return True
            if event.key == pygame.K_ESCAPE:
                game_engine.toggle_pause()
                return True
            if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER} and self.edit_mode == 'terrain':
                if self._facility_edit_active() and self.facility_draw_shape == 'polygon':
                    if len(self.polygon_points) >= 3:
                        self._commit_facility_polygon(game_engine)
                    return True
                if self._terrain_brush_active() and self.terrain_shape_mode == 'polygon':
                    if len(self.polygon_points) >= 3:
                        self._commit_terrain_polygon(game_engine)
                    return True
                if self._terrain_brush_active() and self.terrain_shape_mode == 'smooth_polygon':
                    if len(self.polygon_points) >= 3:
                        self._commit_terrain_smooth_polygon(game_engine)
                    return True
                if self._terrain_brush_active() and self.terrain_shape_mode == 'slope':
                    if self._slope_direction_mode_active():
                        self._commit_terrain_slope_polygon(game_engine)
                    elif len(self.polygon_points) >= 3:
                        self._begin_terrain_slope_direction(game_engine)
                    return True
                if self._terrain_brush_active() and self.terrain_shape_mode == 'smooth':
                    self._smooth_selected_terrain_cells(game_engine)
                    return True
            if event.key == pygame.K_TAB:
                self._cycle_mode()
                return True
            if event.key == pygame.K_q:
                self._cycle_selection(game_engine, -1)
                return True
            if event.key == pygame.K_e:
                self._cycle_selection(game_engine, 1)
                return True
            if event.key == pygame.K_s and mods & pygame.KMOD_CTRL:
                self._sync_terrain_grid_config(game_engine)
                game_engine.save_local_settings()
                return True
            if event.key == pygame.K_F5:
                self._sync_terrain_grid_config(game_engine)
                game_engine.save_match()
                return True
            if event.key == pygame.K_F9:
                game_engine.load_match()
                return True
            if event.key == pygame.K_p:
                game_engine.toggle_pause()
                return True
            if event.key == pygame.K_r and self.edit_mode == 'entity':
                self._rotate_selected_entity(game_engine)
                return True
            if self._terrain_brush_active():
                if event.key == pygame.K_LEFTBRACKET:
                    self.terrain_brush_radius = max(0, self.terrain_brush_radius - 1)
                    return True
                if event.key == pygame.K_RIGHTBRACKET:
                    self.terrain_brush_radius = min(8, self.terrain_brush_radius + 1)
                    return True
            if self.edit_mode == 'rules':
                if event.key == pygame.K_UP:
                    self.selected_rule_index = max(0, self.selected_rule_index - 1)
                    self.rule_scroll = min(self.rule_scroll, self.selected_rule_index)
                    return True
                if event.key == pygame.K_DOWN:
                    max_index = max(0, len(self._flatten_numeric_rules(game_engine.config.get('rules', {}))) - 1)
                    self.selected_rule_index = min(max_index, self.selected_rule_index + 1)
                    if self.selected_rule_index > self.rule_scroll + 10:
                        self.rule_scroll += 1
                    return True
                if event.key == pygame.K_LEFT:
                    self._adjust_selected_rule(game_engine, -1)
                    return True
                if event.key == pygame.K_RIGHT:
                    self._adjust_selected_rule(game_engine, 1)
                    return True

        if event.type == pygame.MOUSEMOTION:
            if self.terrain_pan_origin is not None and self.edit_mode == 'terrain':
                rel = getattr(event, 'rel', (0, 0))
                if abs(rel[0]) + abs(rel[1]) > 0:
                    self.terrain_pan_active = True
                    self._handle_terrain_pan_motion(rel)
                    return True
            self.mouse_world = self.screen_to_world(event.pos[0], event.pos[1])
            if self.drag_start is not None:
                if self._facility_edit_active():
                    self.drag_current = self._current_facility_target(self.mouse_world)
                elif self._terrain_brush_active():
                    self.drag_current = self._current_terrain_target(self.mouse_world)
                else:
                    self.drag_current = self.mouse_world
            if self._slope_direction_mode_active() and self.slope_direction_start is not None and self.mouse_world is not None:
                self.slope_direction_end = self.mouse_world
                self.drag_current = self.mouse_world
            if self.dragged_entity_id is not None and self.mouse_world is not None:
                self._move_dragged_entity(game_engine, self.mouse_world)
            return True

        if event.type == pygame.MOUSEWHEEL and self.edit_mode == 'none' and game_engine.is_single_unit_test_mode():
            if self.single_unit_decision_list_rect is not None and self.single_unit_decision_list_rect.collidepoint(pygame.mouse.get_pos()):
                specs = list(game_engine.get_single_unit_test_decision_specs())
                visible_rows = max(1, self.single_unit_decision_list_rect.height // 30)
                max_scroll = max(0, len(specs) - visible_rows)
                self.single_unit_decision_scroll = max(0, min(max_scroll, self.single_unit_decision_scroll - event.y))
                return True

        if event.type == pygame.MOUSEWHEEL and self.edit_mode == 'rules':
            max_scroll = max(0, len(self._flatten_numeric_rules(game_engine.config.get('rules', {}))) - 1)
            self.rule_scroll = max(0, min(max_scroll, self.rule_scroll - event.y))
            return True

        if event.type == pygame.MOUSEWHEEL and self._facility_edit_active():
            if self.wall_panel_rect is not None and self.wall_panel_rect.collidepoint(pygame.mouse.get_pos()):
                wall_count = len(game_engine.map_manager.get_facility_regions('wall'))
                max_scroll = max(0, wall_count - 4)
                self.wall_scroll = max(0, min(max_scroll, self.wall_scroll - event.y))
                return True
            if self.terrain_panel_rect is not None and self.terrain_panel_rect.collidepoint(pygame.mouse.get_pos()):
                selected_facility = self._selected_region_option()
                if selected_facility is None:
                    return True
                region_count = len(game_engine.map_manager.get_facility_regions(selected_facility['type']))
                max_scroll = max(0, region_count - 4)
                self.terrain_scroll = max(0, min(max_scroll, self.terrain_scroll - event.y))
                return True
            visible_rows = max(1, (self.window_height - self.toolbar_height - self.hud_height - 200) // 34)
            max_scroll = max(0, len(self._region_options()) - visible_rows)
            self.facility_scroll = max(0, min(max_scroll, self.facility_scroll - event.y))
            return True

        if event.type == pygame.MOUSEWHEEL and self._terrain_brush_active():
            self.terrain_brush_radius = max(0, min(8, self.terrain_brush_radius - event.y))
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self._resolve_click_action(event.pos)
            if self.active_numeric_input is not None:
                if action is None or action != f"height_input:{self.active_numeric_input['type']}:{self.active_numeric_input['facility_id']}":
                    self._commit_numeric_input(game_engine)
            action = self._resolve_click_action(event.pos)
            if action:
                self._execute_action(game_engine, action)
                return True
            if self.selected_hud_entity_id is not None and self.robot_detail_rect is not None and not self.robot_detail_rect.collidepoint(event.pos):
                self.selected_hud_entity_id = None
                self.robot_detail_page = 0
                self.robot_detail_rect = None
                return True

            world_pos = self.screen_to_world(event.pos[0], event.pos[1])
            if world_pos is None:
                return True
            self.mouse_world = world_pos
            if self._facility_edit_active():
                self._handle_facility_left_press(game_engine, world_pos)
            elif self._terrain_brush_active():
                self._handle_terrain_left_press(game_engine, world_pos)
            elif self.edit_mode == 'entity':
                dragged = self._pick_editable_entity(game_engine, event.pos)
                if dragged is not None:
                    entity, team, key = dragged
                    self.dragged_entity_id = entity.id
                    self._select_entity_key(team, key)
                    self._move_dragged_entity(game_engine, world_pos, announce=False)
                else:
                    self._place_selected_entity(game_engine, world_pos)
            elif self.edit_mode == 'none' and game_engine.is_single_unit_test_mode():
                entity = self._pick_single_unit_test_entity(game_engine, event.pos)
                if entity is not None:
                    self.dragged_entity_id = entity.id
                    self._move_dragged_entity(game_engine, world_pos, announce=False)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.edit_mode == 'terrain':
            world_pos = self.screen_to_world(event.pos[0], event.pos[1])
            self.terrain_pan_active = False
            self.terrain_pan_origin = ('main', event.pos, world_pos)
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._facility_edit_active():
            world_pos = self.screen_to_world(event.pos[0], event.pos[1])
            self._handle_facility_left_release(game_engine, world_pos)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and (self.edit_mode == 'entity' or (self.edit_mode == 'none' and game_engine.is_single_unit_test_mode())):
            if self.dragged_entity_id is not None:
                entity = game_engine.entity_manager.get_entity(self.dragged_entity_id)
                self.dragged_entity_id = None
                if entity is not None:
                    game_engine.add_log(
                        f'已拖拽 {entity.id} 到 ({int(entity.position["x"])}, {int(entity.position["y"])})',
                        'system',
                    )
            return True

        if event.type == pygame.MOUSEBUTTONUP and self._terrain_brush_active():
            if event.button == 1:
                world_pos = self.screen_to_world(event.pos[0], event.pos[1])
                self.terrain_painting = False
                self.terrain_erasing = False
                self.last_terrain_paint_grid_key = None
                self._handle_terrain_left_release(game_engine, world_pos)
            elif event.button == 3:
                origin = self.terrain_pan_origin
                if not self.terrain_pan_active and origin is not None:
                    origin_world = origin[2]
                    if origin_world is not None:
                        self._handle_terrain_right_press(game_engine, origin_world)
                self.terrain_pan_active = False
                self.terrain_pan_origin = None
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 3 and self._facility_edit_active():
            origin = self.terrain_pan_origin
            if not self.terrain_pan_active and origin is not None:
                origin_world = origin[2]
                if origin_world is not None:
                    self._handle_facility_right_press(game_engine, origin_world)
            self.terrain_pan_active = False
            self.terrain_pan_origin = None
            return True
        return False

    def _resolve_click_action(self, pos):
        for rect, action in self.toolbar_actions:
            if rect.collidepoint(pos):
                return action
        for rect, action in self.hud_actions:
            if rect.collidepoint(pos):
                return action
        for rect, action in self.panel_actions:
            if rect.collidepoint(pos):
                return action
        return None

    def _handle_standalone_program_event(self, event, game_engine):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.standalone_3d_state == 'lobby':
                    self.standalone_3d_state = 'main_menu'
                else:
                    game_engine.running = False
                return True
            if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER} and self.standalone_3d_state == 'main_menu':
                self.standalone_3d_state = 'lobby'
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self._resolve_click_action(event.pos)
            if action:
                self._execute_action(game_engine, action)
            return True
        return False

    def _handle_player_simulator_event(self, event, game_engine):
        controlled_getter = getattr(game_engine, 'get_player_controlled_entity', None)
        if not callable(controlled_getter):
            return False
        entity = controlled_getter()
        if entity is None:
            if self.player_mouse_captured:
                self._sync_player_mouse_capture(False)
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.pre_match_config_menu_open:
                    self.pre_match_config_menu_open = False
                elif self.player_settings_menu_open:
                    self.player_settings_menu_open = False
                elif self.player_purchase_menu_open:
                    self.player_purchase_menu_open = False
                else:
                    game_engine.toggle_pause()
                return True
            if event.key == pygame.K_p and getattr(game_engine, 'pre_match_setup_required', False):
                self.pre_match_config_menu_open = not self.pre_match_config_menu_open
                self.player_settings_menu_open = False
                return True
            if game_engine.paused:
                if event.key == pygame.K_b and game_engine.is_player_in_supply_zone():
                    self.player_purchase_menu_open = not self.player_purchase_menu_open
                    return True
                return True
            if event.key == pygame.K_b:
                if game_engine.is_player_in_supply_zone():
                    self.player_purchase_menu_open = not self.player_purchase_menu_open
                else:
                    self.player_purchase_menu_open = False
                    game_engine.add_log('当前不在己方补给区，无法购买弹药', 'system')
                return True
            if event.key == pygame.K_v:
                self.player_camera_mode = 'third_person' if self.player_camera_mode != 'third_person' else 'first_person'
                camera_mode_setter = getattr(game_engine, 'set_player_camera_mode', None)
                if callable(camera_mode_setter):
                    camera_mode_setter(self.player_camera_mode)
                game_engine.add_log('已切换到第三人称视角' if self.player_camera_mode == 'third_person' else '已切换到第一人称视角', 'system')
                return True
        if event.type == pygame.MOUSEMOTION:
            if game_engine.paused:
                return True
            rel = getattr(event, 'rel', (0, 0))
            game_engine.accumulate_player_look_delta(rel[0], rel[1])
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            action = self._resolve_click_action(event.pos)
            if game_engine.paused:
                if event.button == 1:
                    if action:
                        self._execute_action(game_engine, action)
                    return True
                return True
            if event.button == 1 and action in {'player_purchase_confirm', 'player_purchase_cancel', 'toggle_player_settings', 'pre_match_confirm', 'pre_match_cancel'}:
                self._execute_action(game_engine, action)
                return True
            if event.button == 1 and action and action.startswith('player_purchase_delta:'):
                self._execute_action(game_engine, action)
                return True
            if event.button == 1:
                game_engine.set_player_action_state(fire_pressed=True)
                return True
            if event.button == 3:
                game_engine.set_player_action_state(autoaim_pressed=True)
                return True
        if event.type == pygame.MOUSEBUTTONUP:
            if game_engine.paused:
                return True
            if event.button == 1:
                game_engine.set_player_action_state(fire_pressed=False)
                return True
            if event.button == 3:
                game_engine.set_player_action_state(autoaim_pressed=False)
                return True
        return False

    def _execute_action(self, game_engine, action):
        if action == 'standalone_open_lobby':
            self.standalone_3d_state = 'lobby'
            return
        if action == 'standalone_exit':
            game_engine.running = False
            return
        if action == 'standalone_toggle_ricochet':
            self.standalone_3d_ricochet_enabled = not self.standalone_3d_ricochet_enabled
            game_engine.config.setdefault('simulator', {})['player_projectile_ricochet_enabled'] = self.standalone_3d_ricochet_enabled
            return
        if action == 'standalone_back_main':
            self.standalone_3d_state = 'main_menu'
            return
        if action == 'standalone_confirm_start':
            self._ensure_standalone_selection(game_engine)
            game_engine.config.setdefault('simulator', {})['player_projectile_ricochet_enabled'] = self.standalone_3d_ricochet_enabled
            game_engine.start_new_match()
            if self.standalone_3d_selected_entity_id and game_engine.set_player_controlled_entity(self.standalone_3d_selected_entity_id):
                self.selected_hud_entity_id = self.standalone_3d_selected_entity_id
                self.player_purchase_menu_open = False
                self.player_purchase_amount = 50
                game_engine.begin_pre_match_setup()
                self.standalone_3d_state = 'in_match'
            else:
                game_engine.add_log('所选机器人当前不可接管', 'system')
            return
        if action.startswith('standalone_team:'):
            self.standalone_3d_selected_team = action.split(':', 1)[1]
            self._ensure_standalone_selection(game_engine)
            return
        if action.startswith('standalone_pick:'):
            self.standalone_3d_selected_entity_id = action.split(':', 1)[1]
            if self.standalone_3d_selected_entity_id.startswith('red_'):
                self.standalone_3d_selected_team = 'red'
            elif self.standalone_3d_selected_entity_id.startswith('blue_'):
                self.standalone_3d_selected_team = 'blue'
            return
        if action == 'start_match':
            game_engine.start_new_match()
            if self.standalone_3d_program and self.standalone_3d_state == 'in_match' and self.standalone_3d_selected_entity_id:
                game_engine.set_player_controlled_entity(self.standalone_3d_selected_entity_id)
                self.selected_hud_entity_id = self.standalone_3d_selected_entity_id
            return
        if action == 'toggle_pause':
            game_engine.toggle_pause()
            return
        if action == 'toggle_player_view':
            if game_engine.player_control_enabled:
                game_engine.clear_player_controlled_entity()
                self.player_purchase_menu_open = False
                self.pre_match_config_menu_open = False
                self._sync_player_mouse_capture(False)
            else:
                candidate_id = self._player_control_candidate_id(game_engine)
                if candidate_id and game_engine.set_player_controlled_entity(candidate_id):
                    self.selected_hud_entity_id = candidate_id
                    self.player_purchase_menu_open = False
                    self.player_purchase_amount = 50
                    self._sync_player_mouse_capture(True)
                else:
                    game_engine.add_log('没有可接管的机器人', 'system')
            return
        if action == 'toggle_player_settings':
            self.player_settings_menu_open = not self.player_settings_menu_open
            return
        if action.startswith('player_sensitivity:'):
            _, axis, delta_text = action.split(':', 2)
            try:
                delta = float(delta_text)
            except ValueError:
                return
            values = game_engine.get_player_sensitivity_settings()
            if axis == 'yaw':
                game_engine.set_player_sensitivity_settings(yaw_sensitivity_deg=max(0.01, values['yaw'] + delta))
            elif axis == 'pitch':
                game_engine.set_player_sensitivity_settings(pitch_sensitivity_deg=max(0.01, values['pitch'] + delta))
            return
        if action.startswith('player_purchase_delta:'):
            try:
                delta = int(action.split(':', 1)[1])
            except ValueError:
                return
            self.player_purchase_amount = max(1, min(999, int(self.player_purchase_amount) + delta))
            return
        if action == 'player_purchase_confirm':
            result = game_engine.purchase_player_ammo(self.player_purchase_amount)
            if result.get('ok'):
                game_engine.add_log(f'已购买 {result.get("amount", 0)} 发弹药，剩余金币 {result.get("team_gold", 0.0):.1f}', 'system')
            else:
                game_engine.add_log(f'购买失败: {result.get("code", "UNKNOWN")}', 'system')
            return
        if action == 'player_purchase_cancel':
            self.player_purchase_menu_open = False
            return
        if action == 'pre_match_confirm':
            if game_engine.begin_pre_match_countdown(5.0):
                self.pre_match_config_menu_open = False
            else:
                game_engine.add_log('当前没有可配置的主控机器人', 'system')
            return
        if action == 'pre_match_cancel':
            self.pre_match_config_menu_open = False
            return
        if action == 'end_match':
            game_engine.end_match()
            return
        if action == 'save_match':
            self._sync_terrain_grid_config(game_engine)
            game_engine.save_match()
            return
        if action == 'load_match':
            game_engine.load_match()
            return
        if action == 'save_settings':
            self._sync_terrain_grid_config(game_engine)
            game_engine.save_local_settings()
            return
        if action == 'close_robot_detail':
            self.selected_hud_entity_id = None
            self.robot_detail_page = 0
            self.robot_detail_rect = None
            return
        if action.startswith('robot_detail_page:'):
            try:
                self.robot_detail_page = max(0, min(1, int(action.split(':', 1)[1])))
            except ValueError:
                self.robot_detail_page = 0
            return
        if action == 'delete_selected_terrain':
            self._delete_selected_terrain_cells(game_engine)
            return
        if action == 'terrain_smooth_selected':
            self._smooth_selected_terrain_cells(game_engine)
            return
        if action == 'terrain_smooth_confirm':
            self._smooth_selected_terrain_cells(game_engine)
            return
        if action.startswith('terrain_smooth_apply:'):
            strength = int(action.split(':', 1)[1])
            self._smooth_selected_terrain_cells(game_engine, strength=strength)
            return
        if action.startswith('delete_facility:'):
            facility_id = action.split(':', 1)[1]
            self._record_undo_snapshot(game_engine, f'删除设施 {facility_id}')
            game_engine.map_manager.remove_facility_region(facility_id)
            game_engine.config.setdefault('map', {})['facilities'] = game_engine.map_manager.export_facilities_config()
            if self.selected_wall_id == facility_id:
                self.selected_wall_id = None
            if self.selected_terrain_id == facility_id:
                self.selected_terrain_id = None
            game_engine.add_log(f'已删除设施: {facility_id}', 'system')
            return
        if action == 'toggle_facilities':
            self.show_facilities = not self.show_facilities
            game_engine.config.setdefault('simulator', {})['show_facilities'] = self.show_facilities
            game_engine.add_log('已显示设施标注' if self.show_facilities else '已隐藏设施标注', 'system')
            return
        if action == 'toggle_entities':
            self.show_entities = not self.show_entities
            game_engine.config.setdefault('simulator', {})['show_entities'] = self.show_entities
            game_engine.add_log('已显示实体渲染' if self.show_entities else '已隐藏实体渲染', 'system')
            return
        if action.startswith('hud_unit:'):
            entity_id = action.split(':', 1)[1]
            self.selected_hud_entity_id = entity_id or None
            self.robot_detail_page = 0
            return
        if action.startswith('entity_mode:'):
            _, entity_id, field_name, value = action.split(':', 3)
            entity = game_engine.entity_manager.get_entity(entity_id)
            if entity is None:
                return
            setattr(entity, field_name, value)
            game_engine.entity_manager.refresh_entity_performance_profile(entity, preserve_state=True)
            label_map = {
                'health_priority': '血量优先',
                'power_priority': '功率优先',
                'cooling_priority': '冷却优先',
                'burst_priority': '爆发优先',
                'melee_priority': '近战优先',
                'ranged_priority': '远程优先',
            }
            game_engine.add_log(f'{entity_id} 已切换{ "底盘" if field_name == "chassis_mode" else "云台" }模式为 {label_map.get(value, value)}', 'system')
            return
        if action == 'toggle_aim_fov':
            self.show_aim_fov = not self.show_aim_fov
            game_engine.config.setdefault('simulator', {})['show_aim_fov'] = self.show_aim_fov
            game_engine.add_log('已显示自瞄视场' if self.show_aim_fov else '已隐藏自瞄视场', 'system')
            return
        if action == 'toggle_perf_overlay':
            game_engine.show_perf_overlay = not bool(game_engine.show_perf_overlay)
            game_engine.config.setdefault('simulator', {})['show_perf_overlay'] = bool(game_engine.show_perf_overlay)
            game_engine.add_log('已显示性能浮层' if game_engine.show_perf_overlay else '已隐藏性能浮层', 'system')
            return
        if action.startswith('match_mode:'):
            target_mode = action.split(':', 1)[1]
            if game_engine.set_match_mode(target_mode):
                self.single_unit_decision_scroll = 0
                mode_label = '完整' if target_mode == 'full' else '单兵种测试'
                game_engine.add_log(f'对局模式已切换为 {mode_label}', 'system')
            return
        if action.startswith('test_focus_team:'):
            team = action.split(':', 1)[1]
            if game_engine.set_single_unit_test_focus(team=team):
                self.single_unit_decision_scroll = 0
                team_label = '红方' if team == 'red' else '蓝方'
                game_engine.add_log(f'单兵种测试主控方已切换为 {team_label}', 'system')
            return
        if action.startswith('test_focus_entity:'):
            entity_key = action.split(':', 1)[1]
            if game_engine.set_single_unit_test_focus(entity_key=entity_key):
                self.single_unit_decision_scroll = 0
                label_map = {
                    'robot_1': '英雄',
                    'robot_2': '工程',
                    'robot_3': '步兵1',
                    'robot_4': '步兵2',
                    'robot_7': '哨兵',
                }
                game_engine.add_log(f'单兵种测试主控兵种已切换为 {label_map.get(entity_key, entity_key)}', 'system')
            return
        if action.startswith('test_base_hp:'):
            _, team, delta = action.split(':', 2)
            if game_engine.adjust_structure_health(team, 'base', float(delta)):
                base = game_engine.entity_manager.get_entity(f'{team}_base')
                team_label = '红方' if team == 'red' else '蓝方'
                hp_value = int(getattr(base, 'health', 0.0)) if base is not None else 0
                game_engine.add_log(f'{team_label}基地血量已调整为 {hp_value}', 'system')
            return
        if action == 'test_decision_clear':
            if game_engine.set_single_unit_test_decision(''):
                game_engine.add_log('已清除主控兵种待办决策', 'system')
            return
        if action.startswith('test_decision:'):
            decision_id = action.split(':', 1)[1]
            if game_engine.set_single_unit_test_decision(decision_id):
                label = decision_id
                for spec in game_engine.get_single_unit_test_decision_specs():
                    if spec.get('id') == decision_id:
                        label = spec.get('label', decision_id)
                        break
                game_engine.add_log(f'主控兵种待办决策已设为 {label}', 'system')
            return
        if action.startswith('debug_fold:'):
            section_id = action.split(':', 1)[1]
            self.debug_panel_expanded[section_id] = not bool(self.debug_panel_expanded.get(section_id, False))
            return
        if action.startswith('debug_toggle:'):
            feature_id = action.split(':', 1)[1]
            new_value = game_engine.toggle_feature_enabled(feature_id)
            if new_value is not None:
                state_text = '启用' if new_value else '禁用'
                game_engine.add_log(f'{feature_id} 已{state_text}', 'system')
            return
        if action.startswith('mode:'):
            self._cancel_numeric_input()
            target_mode = action.split(':', 1)[1]
            if target_mode == 'facility':
                self.edit_mode = 'terrain'
                self.terrain_editor_tool = 'facility'
                self.terrain_overview_window_open = True
            else:
                self.edit_mode = target_mode
                if target_mode != 'terrain':
                    self.terrain_editor_tool = 'terrain'
                    self._close_terrain_3d_window(exit_terrain_mode=False)
                else:
                    self.terrain_overview_window_open = True
            self.terrain_painting = False
            self.terrain_erasing = False
            self._reset_slope_state()
            return
        if action == 'terrain_window_close':
            self._close_terrain_3d_window(exit_terrain_mode=False)
            return
        if action.startswith('terrain_tool:'):
            self._cancel_numeric_input()
            self.terrain_editor_tool = action.split(':', 1)[1]
            self._end_terrain_edit_batch(game_engine)
            self.overview_side_scroll = 0
            self.overview_side_scroll_max = 0
            self.terrain_overview_window_open = True
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            self.terrain_painting = False
            self.terrain_erasing = False
            self._clear_terrain_selection()
            return
        if action.startswith('terrain_workflow:'):
            self._cancel_numeric_input()
            self.terrain_workflow_mode = action.split(':', 1)[1]
            self._end_terrain_edit_batch(game_engine)
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            self.terrain_painting = False
            self.terrain_erasing = False
            return
        if action.startswith('terrain_view_mode:'):
            self.terrain_view_mode = action.split(':', 1)[1]
            self.terrain_3d_render_key = None
            self.terrain_3d_texture = None
            return
        if action.startswith('terrain_zoom:'):
            delta = int(action.split(':', 1)[1])
            self._zoom_terrain_view(game_engine.map_manager, delta)
            self.map_cache_surface = None
            self.map_cache_size = None
            self.terrain_3d_render_key = None
            self.terrain_3d_texture = None
            return
        if action.startswith('terrain_shape:'):
            self._cancel_numeric_input()
            self.terrain_workflow_mode = 'shape'
            self.terrain_shape_mode = action.split(':', 1)[1]
            self._end_terrain_edit_batch(game_engine)
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            return
        if action.startswith('facility:'):
            self._cancel_numeric_input()
            self._set_selected_region_index(int(action.split(':', 1)[1]))
            self.overview_side_scroll = 0
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            selected = self._selected_region_option()
            if selected is None:
                return
            if selected['type'] == 'wall':
                self.selected_terrain_id = None
            else:
                self.selected_wall_id = None
            return
        if action.startswith('facility_select_delta:'):
            delta = int(action.split(':', 1)[1])
            self._shift_selected_region(delta)
            self.overview_side_scroll = 0
            return
        if action.startswith('region_palette:'):
            self._set_region_palette(action.split(':', 1)[1])
            self.facility_scroll = 0
            self.overview_side_scroll = 0
            return
        if action.startswith('facility_shape:'):
            self._cancel_numeric_input()
            self.facility_draw_shape = action.split(':', 1)[1]
            self.overview_side_scroll = 0
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            return
        if action.startswith('wall_select:'):
            self._cancel_numeric_input()
            self.selected_wall_id = action.split(':', 1)[1]
            return
        if action.startswith('wall_toggle:'):
            _, wall_id, toggle_type = action.split(':', 2)
            wall = game_engine.map_manager.get_facility_by_id(wall_id)
            if wall is None:
                return
            self._record_undo_snapshot(game_engine, f'墙体属性 {wall_id}')
            if toggle_type == 'movement':
                game_engine.map_manager.update_wall_properties(wall_id, blocks_movement=not wall.get('blocks_movement', True))
            else:
                game_engine.map_manager.update_wall_properties(wall_id, blocks_vision=not wall.get('blocks_vision', True))
            game_engine.config.setdefault('map', {})['facilities'] = game_engine.map_manager.export_facilities_config()
            self.selected_wall_id = wall_id
            return
        if action.startswith('terrain_select:'):
            self._cancel_numeric_input()
            self.selected_terrain_id = action.split(':', 1)[1]
            return
        if action.startswith('height_input:'):
            _, input_type, facility_id = action.split(':', 2)
            if input_type == 'terrain_brush':
                current_value = self._terrain_editor_display_height(self._selected_terrain_brush_def().get('height_m', 0.0))
            else:
                facility = game_engine.map_manager.get_facility_by_id(facility_id)
                if facility is None:
                    return
                current_value = self._terrain_editor_display_height(facility.get('height_m', 1.0 if input_type == 'wall' else 0.0))
            self._begin_numeric_input(input_type, facility_id, current_value)
            return
        if action == 'noop':
            return
        if action.startswith('terrain_brush_radius:'):
            delta = int(action.split(':', 1)[1])
            self.terrain_brush_radius = max(0, min(8, self.terrain_brush_radius + delta))
            return
        if action.startswith('terrain_smooth_strength:set:'):
            self.terrain_smooth_strength = max(0, min(3, int(action.rsplit(':', 1)[1])))
            game_engine.config.setdefault('simulator', {})['terrain_smooth_strength'] = self.terrain_smooth_strength
            return
        if action.startswith('terrain_smooth_strength:'):
            delta = int(action.split(':', 1)[1])
            self.terrain_smooth_strength = max(0, min(3, self.terrain_smooth_strength + delta))
            game_engine.config.setdefault('simulator', {})['terrain_smooth_strength'] = self.terrain_smooth_strength
            return
        if action.startswith('terrain_brush_height:'):
            delta = float(action.split(':', 1)[1])
            display_value = self._terrain_editor_display_height(self.terrain_brush.get('height_m', 0.0))
            self.terrain_brush['height_m'] = round(max(0.0, min(5.0, self._terrain_editor_storage_height(display_value + delta))), 2)
            return
        if action.startswith('entity:'):
            self.selected_entity_index = int(action.split(':', 1)[1])
            return
        if action.startswith('rule_select:'):
            self.selected_rule_index = int(action.split(':', 1)[1])
            return
        if action.startswith('rule_adjust:'):
            _, path, delta = action.split(':', 2)
            self._adjust_rule_setting(game_engine, path, int(delta))

    def _cycle_mode(self):
        order = ['none', 'terrain', 'entity']
        current_index = order.index(self.edit_mode)
        self.edit_mode = order[(current_index + 1) % len(order)]
        self._reset_slope_state()
        if self.edit_mode != 'terrain':
            self.terrain_editor_tool = 'terrain'
            self._close_terrain_3d_window(exit_terrain_mode=False)
        else:
            self.terrain_overview_window_open = True

    def _cycle_selection(self, game_engine, delta):
        if self.edit_mode == 'terrain':
            if self.terrain_editor_tool == 'facility':
                self._shift_selected_region(delta)
        elif self.edit_mode == 'entity' and self.entity_keys:
            self.selected_entity_index = (self.selected_entity_index + delta) % len(self.entity_keys)
        elif self.edit_mode == 'rules':
            numeric_rules = self._flatten_numeric_rules(game_engine.config.get('rules', {}))
            if numeric_rules:
                self.selected_rule_index = (self.selected_rule_index + delta) % len(numeric_rules)

    def _commit_facility_region(self, game_engine, start, end):
        facility = self._selected_region_option()
        if facility is None:
            return
        self._record_undo_snapshot(game_engine, f'设施 {facility["label"]}')
        if facility['type'] == 'wall':
            region = game_engine.map_manager.add_wall_line(start[0], start[1], end[0], end[1])
            self.selected_wall_id = region['id']
        elif self.facility_draw_shape == 'circle':
            radius = math.hypot(end[0] - start[0], end[1] - start[1])
            points = []
            for index in range(20):
                angle = math.tau * index / 20.0
                points.append((int(start[0] + math.cos(angle) * radius), int(start[1] + math.sin(angle) * radius)))
            region = game_engine.map_manager.add_polygon_region(
                facility['type'],
                points,
                team=facility['team'],
                base_id=facility['id'],
            )
            self.selected_terrain_id = region['id'] if region is not None else None
        else:
            region = game_engine.map_manager.upsert_facility_region(
                facility['id'],
                facility['type'],
                start[0],
                start[1],
                end[0],
                end[1],
                team=facility['team'],
            )
            self.selected_terrain_id = region['id']
        game_engine.config.setdefault('map', {})['facilities'] = game_engine.map_manager.export_facilities_config()
        game_engine.add_log(f"已更新设施: {region['id']}", 'system')

    def _commit_facility_polygon(self, game_engine):
        if len(self.polygon_points) < 3:
            return
        facility = self._selected_region_option()
        if facility is None:
            return
        self._record_undo_snapshot(game_engine, f'多边形设施 {facility["label"]}')
        region = game_engine.map_manager.add_polygon_region(
            facility['type'],
            self.polygon_points,
            team=facility['team'],
            base_id=facility['id'],
        )
        self.polygon_points = []
        self.drag_current = None
        if region is None:
            return
        self.selected_terrain_id = region['id']
        game_engine.config.setdefault('map', {})['facilities'] = game_engine.map_manager.export_facilities_config()
        game_engine.add_log(f"已新增多边形设施: {region['id']}", 'system')

    def _paint_terrain_at(self, game_engine, world_pos):
        grid_x, grid_y = game_engine.map_manager._world_to_grid(world_pos[0], world_pos[1])
        paint_key = game_engine.map_manager._terrain_cell_key(grid_x, grid_y)
        if paint_key == self.last_terrain_paint_grid_key:
            return
        brush = self._selected_terrain_brush_def()
        game_engine.map_manager.paint_terrain_grid(
            world_pos[0],
            world_pos[1],
            brush['type'],
            height_m=brush.get('height_m', 0.0),
            brush_radius=self.terrain_brush_radius,
            team=brush.get('team', 'neutral'),
            blocks_movement=brush.get('blocks_movement'),
            blocks_vision=brush.get('blocks_vision'),
        )
        self.last_terrain_paint_grid_key = paint_key
        self.terrain_paint_dirty = True

    def _sync_terrain_grid_config(self, game_engine):
        if not self.terrain_paint_dirty:
            return
        game_engine.config.setdefault('map', {})['terrain_grid'] = game_engine.map_manager.export_terrain_grid_config()
        self.terrain_paint_dirty = False

    def _begin_terrain_edit_batch(self, game_engine):
        if self.terrain_edit_batch_active:
            return
        game_engine.map_manager.begin_raster_batch()
        self.terrain_edit_batch_active = True

    def _end_terrain_edit_batch(self, game_engine):
        if not self.terrain_edit_batch_active:
            return
        game_engine.map_manager.end_raster_batch()
        self.terrain_edit_batch_active = False

    def _wall_color(self, region):
        blocks_movement = bool(region.get('blocks_movement', True))
        blocks_vision = bool(region.get('blocks_vision', True))
        if blocks_movement and blocks_vision:
            return (35, 35, 35)
        if blocks_movement:
            return (120, 78, 54)
        if blocks_vision:
            return (56, 96, 132)
        return (150, 150, 150)

    def _place_selected_entity(self, game_engine, world_pos):
        if not self.entity_keys:
            return
        team, key = self.entity_keys[self.selected_entity_index]
        entity = game_engine.entity_manager.get_entity(f'{team}_{key}')
        if entity is None:
            return
        entity.position['x'] = world_pos[0]
        entity.position['y'] = world_pos[1]
        entity.spawn_position = {'x': world_pos[0], 'y': world_pos[1], 'z': entity.position.get('z', 0)}
        game_engine.config.setdefault('entities', {}).setdefault('initial_positions', {}).setdefault(team, {}).setdefault(key, {})
        game_engine.config['entities']['initial_positions'][team][key]['x'] = world_pos[0]
        game_engine.config['entities']['initial_positions'][team][key]['y'] = world_pos[1]
        entity.set_velocity(0, 0)
        entity.angular_velocity = 0
        game_engine.add_log(f'已放置 {team}_{key} 到 ({world_pos[0]}, {world_pos[1]})', 'system')

    def _rotate_selected_entity(self, game_engine):
        if not self.entity_keys:
            return
        team, key = self.entity_keys[self.selected_entity_index]
        entity = game_engine.entity_manager.get_entity(f'{team}_{key}')
        if entity is None:
            return
        entity.angle = (entity.angle + 45) % 360
        entity.spawn_angle = entity.angle
        game_engine.config['entities']['initial_positions'][team][key]['angle'] = entity.angle
        game_engine.add_log(f'已旋转 {entity.id} 到 {int(entity.angle)} 度', 'system')

    def _adjust_selected_rule(self, game_engine, direction):
        numeric_rules = self._flatten_numeric_rules(game_engine.config.get('rules', {}))
        if not numeric_rules:
            return
        self._adjust_rule_setting(game_engine, numeric_rules[self.selected_rule_index]['path'], direction)

    def _adjust_rule_setting(self, game_engine, path, direction):
        value = self._get_nested_rule_value(game_engine.config['rules'], path)
        if value is None:
            return
        step = self._rule_step(value)
        new_value = value + step * direction
        if isinstance(value, int):
            new_value = max(0, int(round(new_value)))
        else:
            new_value = round(max(0.0, new_value), 2)
        self._set_nested_rule_value(game_engine.config['rules'], path, new_value)
        game_engine.game_duration = game_engine.config['rules'].get('game_duration', game_engine.game_duration)
        game_engine.add_log(f'规则已调整: {path} = {new_value}', 'system')

    def _get_nested_rule_value(self, root, path):
        current = root
        for key in path.split('.'):
            current = current.get(key)
            if current is None:
                return None
        return current

    def _set_nested_rule_value(self, root, path, value):
        current = root
        keys = path.split('.')
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = value

    def _rule_step(self, value):
        if isinstance(value, int):
            if value >= 500:
                return 50
            if value >= 100:
                return 10
            if value >= 20:
                return 5
            return 1
        if value >= 10:
            return 1.0
        if value >= 1:
            return 0.5
        return 0.1

    def _pick_editable_entity(self, game_engine, screen_pos):
        for team, key in reversed(self.entity_keys):
            entity = game_engine.entity_manager.get_entity(f'{team}_{key}')
            if entity is None:
                continue
            center_x, center_y = self.world_to_screen(entity.position['x'], entity.position['y'])
            radius = self._entity_draw_radius(entity)
            radius += 8
            if math.hypot(screen_pos[0] - center_x, screen_pos[1] - center_y) <= radius:
                return entity, team, key
        return None

    def _pick_single_unit_test_entity(self, game_engine, screen_pos):
        candidates = []
        for entity in getattr(game_engine.entity_manager, 'entities', ()):
            if getattr(entity, 'type', None) not in {'robot', 'sentry'}:
                continue
            candidates.append(entity)
        for entity in reversed(candidates):
            center_x, center_y = self.world_to_screen(entity.position['x'], entity.position['y'])
            radius = self._entity_draw_radius(entity) + 8
            if math.hypot(screen_pos[0] - center_x, screen_pos[1] - center_y) <= radius:
                return entity
        return None

    def _select_entity_key(self, team, key):
        for index, candidate in enumerate(self.entity_keys):
            if candidate == (team, key):
                self.selected_entity_index = index
                return

    def _move_dragged_entity(self, game_engine, world_pos, announce=False):
        entity = game_engine.entity_manager.get_entity(self.dragged_entity_id)
        if entity is None:
            return
        team = entity.team
        key = entity.id.replace(f'{team}_', '')
        entity.position['x'] = world_pos[0]
        entity.position['y'] = world_pos[1]
        entity.spawn_position = {'x': world_pos[0], 'y': world_pos[1], 'z': entity.position.get('z', 0)}
        entity.set_velocity(0, 0)
        entity.angular_velocity = 0
        game_engine.config.setdefault('entities', {}).setdefault('initial_positions', {}).setdefault(team, {}).setdefault(key, {})
        game_engine.config['entities']['initial_positions'][team][key]['x'] = world_pos[0]
        game_engine.config['entities']['initial_positions'][team][key]['y'] = world_pos[1]
        if announce:
            game_engine.add_log(f'已拖拽 {entity.id} 到 ({world_pos[0]}, {world_pos[1]})', 'system')

    def _resolve_target_entity(self, entity):
        target = getattr(entity, 'target', None)
        if self.game_engine is None or not isinstance(target, dict):
            return None
        target_id = target.get('id')
        if not target_id:
            return None
        for candidate in self.game_engine.entity_manager.entities:
            if candidate.id == target_id and candidate.is_alive():
                return candidate
        return None

    def world_to_screen(self, world_x, world_y):
        if self.viewport is None:
            return 0, 0
        return (
            int(self.viewport['map_x'] + world_x * self.viewport['scale']),
            int(self.viewport['map_y'] + world_y * self.viewport['scale']),
        )

    def screen_to_world(self, screen_x, screen_y):
        if self.viewport is None:
            return None
        map_rect = pygame.Rect(
            self.viewport['map_x'],
            self.viewport['map_y'],
            self.viewport['map_width'],
            self.viewport['map_height'],
        )
        if not map_rect.collidepoint((screen_x, screen_y)):
            return None
        return (
            int((screen_x - self.viewport['map_x']) / self.viewport['scale']),
            int((screen_y - self.viewport['map_y']) / self.viewport['scale']),
        )