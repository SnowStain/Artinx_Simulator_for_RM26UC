#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame
import math

from rendering.renderer_detail_popup_mixin import RendererDetailPopupMixin
from rendering.renderer_hud_mixin import RendererHudMixin
from rendering.renderer_sidebar_mixin import RendererSidebarMixin
from rendering.terrain_overview_mixin import TerrainOverviewMixin


class Renderer(TerrainOverviewMixin, RendererSidebarMixin, RendererHudMixin, RendererDetailPopupMixin):
    def __init__(self, game_engine, config):
        self.game_engine = game_engine
        self.config = config

        pygame.init()

        self.window_width = config.get('simulator', {}).get('window_width', 1200)
        self.window_height = config.get('simulator', {}).get('window_height', 800)
        display_flags = pygame.DOUBLEBUF
        if hasattr(pygame, 'HWSURFACE'):
            display_flags |= pygame.HWSURFACE
        try:
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), display_flags, vsync=1)
        except TypeError:
            self.screen = pygame.display.set_mode((self.window_width, self.window_height), display_flags)
        pygame.display.set_caption('RM26 Artinx-Asoul模拟器')

        self.toolbar_height = 54
        self.hud_height = 118
        self.panel_width = 320
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
        self.terrain_smooth_strength = int(max(1, min(3, config.get('simulator', {}).get('terrain_smooth_strength', 1))))
        self.height_layer_enabled = config.get('simulator', {}).get('height_layer_enabled', True)
        self.height_layer_alpha = int(max(0, min(255, config.get('simulator', {}).get('height_layer_alpha', 96))))
        self.height_layer_step_m = 0.02
        self.dragged_entity_id = None
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
        self.facility_overlay_surface = None
        self.facility_overlay_cache_key = None
        self.facility_overlay_size = None
        self.projectile_overlay_surface = None
        self.projectile_overlay_size = None
        self.ai_navigation_overlay_surface = None
        self.ai_navigation_overlay_size = None
        self.terrain_3d_window = None
        self.terrain_3d_renderer = None
        self.terrain_3d_texture = None
        self.terrain_overview_window_open = False
        self.terrain_3d_window_size = (1200, 820)
        self.terrain_3d_render_key = None
        self.terrain_3d_last_build_ms = 0
        self.terrain_scene_backend_requested = config.get('simulator', {}).get('terrain_scene_backend', 'auto')
        self.terrain_scene_backend = None
        self.terrain_3d_map_rgb_cache_key = None
        self.terrain_3d_map_rgb_cache = None
        self.terrain_overview_ui = {'window_id': None, 'buttons': [], 'map_rect': None}
        self.terrain_overview_mouse_pos = None
        self.terrain_overview_viewport_drag_active = False
        self.terrain_3d_orbit_active = False
        self.terrain_3d_orbit_dragged = False
        self.terrain_3d_orbit_last_pos = None
        self.terrain_3d_camera_yaw = math.radians(45.0)
        self.terrain_3d_camera_pitch = 0.58
        self.terrain_view_mode = '3d'
        self.terrain_shape_mode = 'circle'
        self.selected_hud_entity_id = None
        self.robot_detail_page = 0
        self.robot_detail_rect = None
        self.show_facilities = config.get('simulator', {}).get('show_facilities', False)
        self.show_aim_fov = config.get('simulator', {}).get('show_aim_fov', False)
        self.render_interval = max(1, int(config.get('simulator', {}).get('render_interval', 1)))
        self.overlay_status_refresh_ms = int(max(33, config.get('simulator', {}).get('overlay_status_refresh_ms', 120)))
        self.overlay_status_box_surface = None
        self.overlay_status_box_key = None
        self.overlay_status_log_surface = None
        self.overlay_status_log_key = None

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

        self._update_viewport(game_engine.map_manager)
        self.render_toolbar(game_engine)
        self.render_match_hud(game_engine)
        self.render_map(game_engine.map_manager)
        self.render_aim_fov(game_engine)
        self.render_entities(game_engine.entity_manager.entities)
        self.render_region_hover_hint(game_engine.map_manager)
        self.render_overlay_status(game_engine)
        self.render_sidebar(game_engine)
        self.render_robot_detail_popup(game_engine)
        self.render_perf_overlay(game_engine)
        self.render_terrain_3d_window(game_engine)
        pygame.display.flip()

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

        if input_type == 'wall':
            self._record_undo_snapshot(game_engine, f'墙高 {facility_id}')
            facility = game_engine.map_manager.update_wall_properties(facility_id, height_m=value)
            self.selected_wall_id = facility_id
            label = '墙高'
        elif input_type == 'terrain_brush':
            self.terrain_brush['height_m'] = value
            self.active_numeric_input = None
            if announce:
                game_engine.add_log(f'地形笔刷高度已设置为 {value:.2f}m', 'system')
            return True
        else:
            facility = game_engine.map_manager.update_facility_height(facility_id, value)
            self.selected_terrain_id = facility_id
            label = '地形高'

        self.active_numeric_input = None
        if facility is None:
            return False

        game_engine.config.setdefault('map', {})['facilities'] = game_engine.map_manager.export_facilities_config()
        if announce:
            game_engine.add_log(f'{facility_id} {label}已设置为 {facility.get("height_m", value):.2f}m', 'system')
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
        sidebar_width = self.panel_width if self.edit_mode != 'none' else 0
        return pygame.Rect(
            self.content_padding,
            self.toolbar_height + self.hud_height + self.content_padding,
            self.window_width - sidebar_width - self.content_padding * 2,
            self.window_height - self.toolbar_height - self.hud_height - self.content_padding * 2,
        )

    def _terrain_fit_scale(self, map_manager):
        available_rect = self._terrain_available_rect()
        scale = min(
            available_rect.width / max(1, map_manager.map_width),
            available_rect.height / max(1, map_manager.map_height),
        )
        return max(scale, 0.1)

    def _terrain_effective_scale(self, map_manager):
        return self._terrain_fit_scale(map_manager)

    def _height_layer_band_index(self, height_m):
        step = max(0.001, float(getattr(self, 'height_layer_step_m', 0.02)))
        return int(round(float(height_m) / step))

    def _height_layer_color(self, height_m):
        band_index = self._height_layer_band_index(height_m)
        hue = (band_index * 37) % 360
        saturation = 58 + (band_index % 4) * 6
        value = 88 - (band_index % 3) * 4
        color = pygame.Color(0, 0, 0)
        color.hsva = (hue, max(20, min(100, saturation)), max(35, min(100, value)), 100)
        return color.r, color.g, color.b

    def _height_layer_outline_color(self, height_m):
        base = self._height_layer_color(height_m)
        return tuple(max(0, min(255, int(channel * 0.62))) for channel in base)

    def _zoom_terrain_view(self, map_manager, zoom_steps, focus_world=None):
        if not zoom_steps:
            return False
        old_zoom = self.terrain_scene_zoom
        self.terrain_scene_zoom = max(1.0, min(6.0, self.terrain_scene_zoom * (1.15 ** zoom_steps)))
        if focus_world is not None:
            self.terrain_scene_focus_world = (
                max(0, min(map_manager.map_width - 1, int(focus_world[0]))),
                max(0, min(map_manager.map_height - 1, int(focus_world[1]))),
            )
        return abs(self.terrain_scene_zoom - old_zoom) >= 1e-6

    def render_toolbar(self, game_engine):
        pygame.draw.rect(self.screen, self.colors['toolbar'], (0, 0, self.window_width, self.toolbar_height))
        buttons = [
            ('开始/重开', 'start_match', False),
            ('暂停/继续', 'toggle_pause', game_engine.paused and not game_engine.rules_engine.game_over),
            ('结束对局', 'end_match', game_engine.rules_engine.game_over),
            ('保存存档', 'save_match', False),
            ('载入存档', 'load_match', False),
            ('保存设置', 'save_settings', False),
            ('设施显示', 'toggle_facilities', self.show_facilities),
            ('视场显示', 'toggle_aim_fov', self.show_aim_fov),
            ('浏览', 'mode:none', self.edit_mode == 'none'),
            ('地形编辑', 'mode:terrain', self.edit_mode == 'terrain'),
            ('站位编辑', 'mode:entity', self.edit_mode == 'entity'),
            ('规则编辑', 'mode:rules', self.edit_mode == 'rules'),
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
        map_rect = pygame.Rect(
            self.viewport['map_x'],
            self.viewport['map_y'],
            self.viewport['map_width'],
            self.viewport['map_height'],
        )
        pygame.draw.rect(self.screen, self.colors['white'], map_rect)
        pygame.draw.rect(self.screen, self.colors['panel_border'], map_rect, 1)

        surface = self._get_scaled_map_surface(map_manager, map_rect.size)
        if surface is not None:
            self.screen.blit(surface, map_rect.topleft)

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

    def _draw_region_hover_card(self, surface, region, anchor_pos, clamp_rect=None):
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
        self._draw_region_hover_card(self.screen, region, pygame.mouse.get_pos(), clamp_rect=self.screen.get_rect())

    def _get_scaled_map_surface(self, map_manager, size):
        source = map_manager.map_image or map_manager.map_surface
        if source is None:
            return None
        if self.map_cache_surface is None or self.map_cache_size != size:
            self.map_cache_surface = pygame.transform.smoothscale(source, size).convert()
            self.map_cache_size = size
        return self.map_cache_surface

    def render_facility_overlay(self, map_manager):
        if self.viewport is None or not self.show_facilities:
            return
        interactive = self._facility_edit_active() or self._terrain_brush_active()
        if not interactive:
            viewport_key = (
                int(self.viewport['map_x']),
                int(self.viewport['map_y']),
                int(self.viewport['map_width']),
                int(self.viewport['map_height']),
                round(float(self.viewport['scale']), 4),
                getattr(map_manager, 'raster_version', 0),
            )
            size = (self.window_width, self.window_height)
            if self.facility_overlay_surface is None or self.facility_overlay_size != size:
                self.facility_overlay_surface = pygame.Surface(size, pygame.SRCALPHA).convert_alpha()
                self.facility_overlay_size = size
                self.facility_overlay_cache_key = None
            if self.facility_overlay_cache_key != viewport_key:
                self.facility_overlay_surface.fill((0, 0, 0, 0))
                self._draw_facility_overlay(self.facility_overlay_surface, map_manager, interactive=False)
                self.facility_overlay_cache_key = viewport_key
            self.screen.blit(self.facility_overlay_surface, (0, 0))
            return
        self._draw_facility_overlay(self.screen, map_manager, interactive=True)

    def _draw_facility_overlay(self, target_surface, map_manager, interactive=False):
        color_map = {
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
        for region in map_manager.get_facility_regions():
            facility_type = str(region.get('type', 'boundary'))
            if region.get('shape') == 'line':
                color = self._wall_color(region)
                x1, y1 = self.world_to_screen(region['x1'], region['y1'])
                x2, y2 = self.world_to_screen(region['x2'], region['y2'])
                thickness = max(2, int(region.get('thickness', 12) * self.viewport['scale']))
                pygame.draw.line(target_surface, color, (x1, y1), (x2, y2), thickness)
                if interactive and self.selected_wall_id == region.get('id'):
                    pygame.draw.line(target_surface, self.colors['yellow'], (x1, y1), (x2, y2), max(1, thickness // 3))
                    pygame.draw.circle(target_surface, self.colors['yellow'], (x1, y1), 5)
                    pygame.draw.circle(target_surface, self.colors['yellow'], (x2, y2), 5)
                tag = self.tiny_font.render(str(region.get('id', facility_type)), True, color)
                target_surface.blit(tag, (x1 + 4, y1 + 4))
                continue

            if region.get('shape') == 'polygon':
                color = color_map[facility_type] if facility_type in color_map else self.colors['white']
                points = [self.world_to_screen(point[0], point[1]) for point in region.get('points', [])]
                if len(points) < 3:
                    continue
                pygame.draw.polygon(target_surface, color, points, 2 if interactive else 1)
                if interactive and self.selected_terrain_id == region.get('id'):
                    pygame.draw.polygon(target_surface, self.colors['yellow'], points, 2)
                    for point in points:
                        pygame.draw.circle(target_surface, self.colors['yellow'], point, 4)
                tag = self.tiny_font.render(str(region.get('id', facility_type)), True, color)
                target_surface.blit(tag, (points[0][0] + 2, points[0][1] + 2))
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
            if interactive and self.selected_terrain_id == region.get('id'):
                pygame.draw.rect(target_surface, self.colors['yellow'], rect, 2)
            if facility_type != 'boundary':
                tag = self.tiny_font.render(str(region.get('id', facility_type)), True, color)
                target_surface.blit(tag, (rect.x + 2, rect.y + 2))

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
        if self._terrain_shape_tool_active() and self.terrain_shape_mode == 'polygon' and self.polygon_points:
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

        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        band_distances = [
            game_engine.map_manager.meters_to_world_units(1.0),
            game_engine.map_manager.meters_to_world_units(5.0),
            game_engine.map_manager.meters_to_world_units(8.0),
        ]
        fov_deg = game_engine.rules_engine.rules.get('shooting', {}).get('auto_aim_fov_deg', 50.0)
        half_fov = fov_deg / 2.0

        for entity in game_engine.entity_manager.entities:
            if entity.type not in {'robot', 'sentry'} or not entity.is_alive():
                continue
            if entity.type == 'robot' and entity.robot_type == '工程':
                continue

            center_x, center_y = self.world_to_screen(entity.position['x'], entity.position['y'])
            turret_center = (center_x, center_y - 2)
            turret_angle = getattr(entity, 'turret_angle', entity.angle)
            start_angle = turret_angle - half_fov
            end_angle = turret_angle + half_fov
            band_colors = self._aim_fov_colors(entity.team)
            inner_distance = 0.0

            for outer_distance, color in zip(band_distances, band_colors):
                polygon = self._build_sector_polygon(
                    turret_center,
                    start_angle,
                    end_angle,
                    inner_distance * self.viewport['scale'],
                    outer_distance * self.viewport['scale'],
                )
                if len(polygon) >= 3:
                    pygame.draw.polygon(overlay, color, polygon)
                    pygame.draw.polygon(overlay, (*color[:3], min(220, color[3] + 50)), polygon, 1)
                inner_distance = outer_distance

            self._draw_fov_edges(overlay, turret_center, turret_angle, half_fov, band_distances[-1] * self.viewport['scale'], entity.team)

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
            start = trace.get('start')
            end = trace.get('end')
            if start is None or end is None:
                continue
            lifetime = max(1e-6, float(trace.get('lifetime', 0.12)))
            progress = max(0.0, min(1.0, float(trace.get('elapsed', 0.0)) / lifetime))
            tail_progress = max(0.0, progress - 0.16)
            tip_world = (
                float(start[0]) + (float(end[0]) - float(start[0])) * progress,
                float(start[1]) + (float(end[1]) - float(start[1])) * progress,
            )
            tail_world = (
                float(start[0]) + (float(end[0]) - float(start[0])) * tail_progress,
                float(start[1]) + (float(end[1]) - float(start[1])) * tail_progress,
            )
            tip = self.world_to_screen(tip_world[0], tip_world[1])
            tail = self.world_to_screen(tail_world[0], tail_world[1])
            is_large = trace.get('ammo_type') == '42mm'
            color_rgb = (255, 184, 90) if is_large else (255, 244, 170)
            alpha = 220 if is_large else 170
            width = 4 if is_large else 2
            radius = 4 if is_large else 2
            pygame.draw.line(overlay, (*color_rgb, alpha), tail, tip, width)
            pygame.draw.circle(overlay, (*color_rgb, min(255, alpha + 20)), tip, radius)
        self.screen.blit(overlay, (0, 0))

    def render_ai_navigation_overlay(self, entities):
        if self.viewport is None:
            return
        overlay = None
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

            if overlay is None:
                size = (self.window_width, self.window_height)
                if self.ai_navigation_overlay_surface is None or self.ai_navigation_overlay_size != size:
                    self.ai_navigation_overlay_surface = pygame.Surface(size, pygame.SRCALPHA)
                    self.ai_navigation_overlay_size = size
                overlay = self.ai_navigation_overlay_surface
                overlay.fill((0, 0, 0, 0))

            team_color = self.colors['red'] if entity.team == 'red' else self.colors['blue']
            if path_state == 'blocked':
                color_rgb = (255, 120, 120)
            elif path_state == 'step-passable':
                color_rgb = self.colors['yellow']
            else:
                color_rgb = team_color
            arrow_color = (*color_rgb, 178)
            line_color = (*color_rgb, 140)
            center = self.world_to_screen(entity.position['x'], entity.position['y'])

            if len(path_preview) >= 2:
                preview_points = [self.world_to_screen(point[0], point[1]) for point in path_preview]
                pygame.draw.lines(overlay, line_color, False, preview_points, 2)
                for point in preview_points[1:]:
                    pygame.draw.circle(overlay, (*color_rgb, 110), point, 3)

            marker_target = navigation_target or movement_target or waypoint
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
            distance = math.hypot(target.position['x'] - entity.position['x'], target.position['y'] - entity.position['y'])
            hit_probability = self.game_engine.rules_engine.calculate_hit_probability(entity, target, distance)
            if bool(getattr(entity, 'hero_deployment_active', False)) and target.type in {'outpost', 'base'}:
                motion_label = '部署吊射'
            else:
                motion_label = self.game_engine.rules_engine.describe_target_motion(target)
            statuses.append((f'{motion_label} {hit_probability * 100:.0f}%', self.colors['white']))
        if not statuses:
            return

        y_offset = y + 28
        for label, color in statuses:
            text = self.tiny_font.render(label, True, color)
            self.screen.blit(text, text.get_rect(center=(x, y_offset)))
            y_offset += 12

    def _handle_terrain_left_press(self, game_engine, world_pos):
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
            self.drag_start = world_pos
            self.drag_current = world_pos
            self.terrain_painting = True
            self._paint_terrain_at(game_engine, world_pos)
            return
        if self._terrain_eraser_mode_active():
            self._clear_terrain_selection()
            self._record_undo_snapshot(game_engine, '橡皮擦除地形')
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
        if self.terrain_shape_mode in {'polygon', 'slope'}:
            world_pos = self._current_terrain_target(world_pos)
            if self.polygon_points and len(self.polygon_points) >= 3 and math.hypot(world_pos[0] - self.polygon_points[0][0], world_pos[1] - self.polygon_points[0][1]) <= 18:
                if self.terrain_shape_mode == 'slope':
                    self._begin_terrain_slope_direction(game_engine)
                else:
                    self._commit_terrain_polygon(game_engine)
            else:
                self.polygon_points.append(world_pos)
                self.drag_current = world_pos
                log_prefix = '斜坡区域' if self.terrain_shape_mode == 'slope' else '地形多边形'
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
        if self.terrain_shape_mode in {'polygon', 'slope'} and self.polygon_points:
            if len(self.polygon_points) >= 3:
                if self.terrain_shape_mode == 'slope':
                    self._begin_terrain_slope_direction(game_engine)
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
        if self.terrain_shape_mode in {'polygon', 'slope'} and self.polygon_points:
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
        self._set_terrain_selection(selection)
        if selection:
            if len(selection) == 1:
                grid_x, grid_y = map_manager._decode_terrain_cell_key(next(iter(selection)))
                game_engine.add_log(f'已选中格栅 ({grid_x}, {grid_y})', 'system')
            else:
                game_engine.add_log(f'已框选 {len(selection)} 个地形格栅', 'system')
        else:
            game_engine.add_log('当前框选区域没有已编辑地形格栅', 'system')

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
        applied_strength = max(1, min(3, int(strength if strength is not None else getattr(self, 'terrain_smooth_strength', 1))))
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
        self._set_terrain_selection(selection)
        self._smooth_selected_terrain_cells(game_engine)

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
            if self.terrain_paint_dirty:
                self._sync_terrain_grid_config(game_engine)
            return
        if self.terrain_shape_mode in {'polygon', 'slope'}:
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
                self.drag_start = None
                self.drag_current = None
                self._reset_slope_state()
                self.terrain_painting = False
                self.terrain_erasing = False
                return True
            if event.key == pygame.K_z and mods & pygame.KMOD_CTRL and hasattr(game_engine, 'undo_last_edit'):
                if game_engine.undo_last_edit():
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
            if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER} and self.edit_mode == 'terrain':
                if self._facility_edit_active() and self.facility_draw_shape == 'polygon':
                    if len(self.polygon_points) >= 3:
                        self._commit_facility_polygon(game_engine)
                    return True
                if self._terrain_brush_active() and self.terrain_shape_mode == 'polygon':
                    if len(self.polygon_points) >= 3:
                        self._commit_terrain_polygon(game_engine)
                    return True
                if self._terrain_brush_active() and self.terrain_shape_mode == 'slope':
                    if self._slope_direction_mode_active():
                        self._commit_terrain_slope_polygon(game_engine)
                    elif len(self.polygon_points) >= 3:
                        self._begin_terrain_slope_direction(game_engine)
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
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and self.edit_mode == 'terrain':
            world_pos = self.screen_to_world(event.pos[0], event.pos[1])
            self.terrain_pan_active = False
            self.terrain_pan_origin = ('main', event.pos, world_pos)
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._facility_edit_active():
            world_pos = self.screen_to_world(event.pos[0], event.pos[1])
            self._handle_facility_left_release(game_engine, world_pos)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.edit_mode == 'entity':
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

    def _execute_action(self, game_engine, action):
        if action == 'start_match':
            game_engine.start_new_match()
            return
        if action == 'toggle_pause':
            game_engine.toggle_pause()
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
        if action == 'height_layer_toggle':
            self.height_layer_enabled = not self.height_layer_enabled
            game_engine.config.setdefault('simulator', {})['height_layer_enabled'] = self.height_layer_enabled
            self.terrain_3d_render_key = None
            self.terrain_3d_texture = None
            return
        if action.startswith('height_layer_alpha:'):
            delta = int(action.split(':', 1)[1])
            self.height_layer_alpha = max(0, min(255, self.height_layer_alpha + delta))
            game_engine.config.setdefault('simulator', {})['height_layer_alpha'] = self.height_layer_alpha
            self.terrain_3d_render_key = None
            self.terrain_3d_texture = None
            return
        if action.startswith('terrain_shape:'):
            self._cancel_numeric_input()
            self.terrain_workflow_mode = 'shape'
            self.terrain_shape_mode = action.split(':', 1)[1]
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
                current_value = self._selected_terrain_brush_def().get('height_m', 0.0)
            else:
                facility = game_engine.map_manager.get_facility_by_id(facility_id)
                if facility is None:
                    return
                current_value = facility.get('height_m', 1.0 if input_type == 'wall' else 0.0)
            self._begin_numeric_input(input_type, facility_id, current_value)
            return
        if action == 'noop':
            return
        if action.startswith('terrain_brush_radius:'):
            delta = int(action.split(':', 1)[1])
            self.terrain_brush_radius = max(0, min(8, self.terrain_brush_radius + delta))
            return
        if action.startswith('terrain_smooth_strength:'):
            delta = int(action.split(':', 1)[1])
            self.terrain_smooth_strength = max(1, min(3, self.terrain_smooth_strength + delta))
            game_engine.config.setdefault('simulator', {})['terrain_smooth_strength'] = self.terrain_smooth_strength
            return
        if action.startswith('terrain_brush_height:'):
            delta = float(action.split(':', 1)[1])
            self.terrain_brush['height_m'] = round(max(0.0, min(5.0, self.terrain_brush.get('height_m', 0.0) + delta)), 2)
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
        order = ['none', 'terrain', 'entity', 'rules']
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
        if self.game_engine is None or not isinstance(getattr(entity, 'target', None), dict):
            return None
        target_id = entity.target.get('id')
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