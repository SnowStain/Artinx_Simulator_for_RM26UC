#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import os
import sys

from pygame_compat import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config_manager import ConfigManager
from core.game_engine import GameEngine
from rendering.renderer import Renderer


class FunctionalEditorEngine(GameEngine):
    DUMMY_ROLE_TO_ROBOT_TYPE = {
        'infantry': '步兵',
        'hero': '英雄',
        'engineer': '工程',
        'sentry': '哨兵',
    }

    def __init__(self, config, config_manager=None, config_path='config.json'):
        super().__init__(config, config_manager=config_manager, config_path=config_path)
        self.function_path_active = False
        self.function_path_goal = None
        self.function_path_speed_scale = 0.88
        self.function_dummy_entity_ids = []
        self.function_dummy_counter = 0
        self.set_match_mode('single_unit_test')
        self.set_single_unit_test_focus(team='red', entity_key='robot_3')

    def initialize(self):
        super().initialize()
        self.set_match_mode('single_unit_test')
        self.set_single_unit_test_focus(team='red', entity_key='robot_3')
        self.match_started = True
        self.paused = False
        self.add_log('自定义功能编辑器已启动', 'system')

    def sync_function_grid_config(self):
        self.config.setdefault('map', {})['function_grid'] = self.map_manager.export_function_grid_config()

    def update(self):
        controller_enabled = bool(self.debug_feature_toggles.get('controller', True))
        if self.function_path_active:
            self.debug_feature_toggles['controller'] = False
        try:
            super().update()
        finally:
            self.debug_feature_toggles['controller'] = controller_enabled
        if self.function_path_active:
            self._update_function_path_runtime()

    def _update_function_path_runtime(self):
        entity = self.get_single_unit_test_focus_entity()
        if entity is None or not entity.is_alive() or self.function_path_goal is None:
            return
        ai_controllers = getattr(self.controller, '_ai_controllers', ())
        if not ai_controllers:
            return
        ai_controller = ai_controllers[0]
        entity.step_climb_state = None
        entity.can_climb_steps = False
        ai_controller._last_ai_update_time[entity.id] = float(self.game_time)
        requested_speed = ai_controller._max_speed_world_units() * self.function_path_speed_scale
        velocity = ai_controller.navigate_towards(entity, self.function_path_goal, requested_speed, self.map_manager)
        entity.set_velocity(velocity[0], velocity[1])

    def set_function_path_goal(self, world_pos):
        if world_pos is None:
            self.function_path_goal = None
            return False
        self.function_path_goal = (float(world_pos[0]), float(world_pos[1]))
        return True

    def clear_function_path_goal(self):
        self.function_path_goal = None

    def set_function_path_active(self, active):
        self.function_path_active = bool(active and self.function_path_goal is not None)
        focus_entity = self.get_single_unit_test_focus_entity()
        if not self.function_path_active and focus_entity is not None:
            focus_entity.set_velocity(0.0, 0.0)
            ai_controllers = getattr(self.controller, '_ai_controllers', ())
            if ai_controllers:
                ai_controllers[0]._clear_navigation_overlay_state(focus_entity)
        return self.function_path_active

    def teleport_focus_entity(self, world_pos):
        entity = self.get_single_unit_test_focus_entity()
        if entity is None or world_pos is None:
            return False
        terrain_height = self.map_manager.get_terrain_height_m(world_pos[0], world_pos[1])
        entity.set_position(float(world_pos[0]), float(world_pos[1]), terrain_height)
        entity.spawn_position = {'x': float(world_pos[0]), 'y': float(world_pos[1]), 'z': terrain_height}
        entity.respawn_position = dict(entity.spawn_position)
        entity.set_velocity(0.0, 0.0)
        entity.angular_velocity = 0.0
        return True

    def add_dummy_entity(self, team='blue', role_key='infantry', position=None):
        normalized_team = 'red' if str(team or 'blue') == 'red' else 'blue'
        normalized_role = str(role_key or 'infantry')
        robot_type = self.DUMMY_ROLE_TO_ROBOT_TYPE.get(normalized_role, '步兵')
        entity_type = 'sentry' if normalized_role == 'sentry' else 'robot'
        if position is None:
            position = (self.map_manager.map_width * 0.5, self.map_manager.map_height * 0.5)
        for _ in range(1, 1000):
            self.function_dummy_counter += 1
            key = f'dummy_{self.function_dummy_counter}'
            entity_id = f'{normalized_team}_{key}'
            if self.entity_manager.get_entity(entity_id) is None:
                break
        else:
            return None
        terrain_height = self.map_manager.get_terrain_height_m(position[0], position[1])
        entity = self.entity_manager.create_entity(
            entity_id,
            entity_type,
            normalized_team,
            {'x': float(position[0]), 'y': float(position[1]), 'z': terrain_height},
            angle=0,
            robot_type=robot_type,
        )
        entity.display_name = entity_id
        entity.spawn_position = {'x': float(position[0]), 'y': float(position[1]), 'z': terrain_height}
        entity.respawn_position = dict(entity.spawn_position)
        entity.set_velocity(0.0, 0.0)
        entity.angular_velocity = 0.0
        self.function_dummy_entity_ids.append(entity.id)
        team_positions = self.config.setdefault('entities', {}).setdefault('initial_positions', {}).setdefault(normalized_team, {})
        team_positions[key] = {'x': float(position[0]), 'y': float(position[1]), 'height': terrain_height, 'angle': 0}
        self.config.setdefault('entities', {}).setdefault('robot_types', {})[key] = robot_type
        return entity

    def remove_dummy_entity(self, entity_id):
        entity = self.entity_manager.get_entity(entity_id)
        if entity is None or entity_id not in self.function_dummy_entity_ids:
            return False
        self.entity_manager.entities = [item for item in self.entity_manager.entities if item.id != entity_id]
        self.entity_manager.entity_map.pop(entity_id, None)
        self.function_dummy_entity_ids = [item for item in self.function_dummy_entity_ids if item != entity_id]
        team = entity.team
        key = entity.id.replace(f'{team}_', '')
        self.config.setdefault('entities', {}).setdefault('initial_positions', {}).setdefault(team, {}).pop(key, None)
        self.config.setdefault('entities', {}).setdefault('robot_types', {}).pop(key, None)
        return True

    def list_dummy_entities(self):
        items = []
        for entity_id in self.function_dummy_entity_ids:
            entity = self.entity_manager.get_entity(entity_id)
            if entity is None:
                continue
            items.append(entity)
        return items


class FunctionalEditorRenderer(Renderer):
    FUNCTION_TABS = (
        ('passability', '通行编辑'),
        ('measure', '地图测距'),
        ('path', '路径测试'),
        ('dummy', '虚拟单位'),
    )
    FUNCTION_PASS_MODE_LABELS = {
        'passable': '可通过',
        'conditional': '条件通过',
        'blocked': '不可通过',
    }

    def __init__(self, game_engine, config):
        super().__init__(game_engine, config)
        pygame.display.set_caption('RoboMaster 自定义功能编辑器')
        self.function_tab = 'passability'
        self.function_pick_mode = ''
        self.function_paint_dirty = False
        self.function_brush = {
            'pass_mode': 'passable',
            'label': '可通过',
            'heading_deg': 0.0,
        }
        self.measure_points: dict[str, tuple[float, float] | None] = {'a': None, 'b': None}
        self.edit_mode = 'function'

    def _terrain_brush_active(self):
        if self.edit_mode == 'function':
            return self.function_tab == 'passability'
        return self.edit_mode == 'terrain' and self.terrain_editor_tool == 'terrain'

    def _facility_edit_active(self):
        return self.edit_mode == 'terrain' and self.terrain_editor_tool == 'facility'

    def _mode_label(self, mode):
        if mode == 'function':
            return '自定义功能编辑'
        return super()._mode_label(mode)

    def _selected_terrain_brush_def(self):
        if self.edit_mode == 'function':
            return self.function_brush
        return super()._selected_terrain_brush_def()

    def _function_fill_rgba(self, pass_mode):
        if pass_mode == 'blocked':
            return (220, 60, 60, 77)
        if pass_mode == 'conditional':
            return (234, 140, 32, 51)
        return (64, 122, 224, 51)

    def _function_outline_rgb(self, pass_mode):
        if pass_mode == 'blocked':
            return (220, 60, 60)
        if pass_mode == 'conditional':
            return (234, 140, 32)
        return (64, 122, 224)

    def _pixels_per_meter(self, map_manager):
        pixels_per_meter_x = float(map_manager.map_width) / max(float(map_manager.field_length_m), 1e-6)
        pixels_per_meter_y = float(map_manager.map_height) / max(float(map_manager.field_width_m), 1e-6)
        return (pixels_per_meter_x + pixels_per_meter_y) * 0.5

    def _world_distance_m(self, map_manager, point_a, point_b):
        if point_a is None or point_b is None:
            return 0.0
        distance_world = math.hypot(float(point_b[0]) - float(point_a[0]), float(point_b[1]) - float(point_a[1]))
        return distance_world / max(self._pixels_per_meter(map_manager), 1e-6)

    def _sidebar_total_width(self):
        if self.edit_mode == 'function':
            return self.panel_width + self.decision_panel_width
        return super()._sidebar_total_width()

    def _cycle_mode(self):
        order = ['none', 'function', 'terrain']
        current_index = order.index(self.edit_mode) if self.edit_mode in order else 0
        self.edit_mode = order[(current_index + 1) % len(order)]
        self.drag_start = None
        self.drag_current = None
        self.function_pick_mode = ''
        self._reset_slope_state()
        self.terrain_painting = False
        self.terrain_erasing = False
        if self.edit_mode != 'terrain':
            self.terrain_editor_tool = 'terrain'
            self._close_terrain_3d_window(exit_terrain_mode=False)
        else:
            self.terrain_overview_window_open = True

    def _layout_panel_buttons(self, panel_rect, y, button_specs, active_value=None, x_padding=16, gap_x=8, gap_y=8, min_width=58, button_height=26):
        x = panel_rect.x + x_padding
        max_x = panel_rect.right - x_padding
        for label, action, is_active in button_specs:
            width = max(min_width, self.tiny_font.size(label)[0] + 22)
            if x + width > max_x and x > panel_rect.x + x_padding:
                x = panel_rect.x + x_padding
                y += button_height + gap_y
            rect = pygame.Rect(x, y, min(width, max_x - x), button_height)
            self._draw_mode_button(rect, label, bool(is_active))
            self.panel_actions.append((rect, action))
            x = rect.right + gap_x
        return y + button_height

    def _draw_heading_arrow(self, surface, rect, heading_deg, color, alpha=220, scale=0.35):
        heading = math.radians(float(heading_deg or 0.0))
        center = rect.center
        radius = max(6.0, min(rect.width, rect.height) * scale)
        end_pos = (
            center[0] + math.cos(heading) * radius,
            center[1] + math.sin(heading) * radius,
        )
        pygame.draw.line(surface, (*color, alpha), center, end_pos, 2)
        head_size = max(4.0, radius * 0.32)
        left = (
            end_pos[0] - math.cos(heading - math.pi / 6.0) * head_size,
            end_pos[1] - math.sin(heading - math.pi / 6.0) * head_size,
        )
        right = (
            end_pos[0] - math.cos(heading + math.pi / 6.0) * head_size,
            end_pos[1] - math.sin(heading + math.pi / 6.0) * head_size,
        )
        pygame.draw.polygon(surface, (*color, alpha), [end_pos, left, right])

    def _render_function_decision_panel(self, game_engine, panel_rect):
        pygame.draw.rect(self.screen, self.colors['panel'], panel_rect)
        pygame.draw.line(self.screen, self.colors['panel_border'], panel_rect.topleft, panel_rect.bottomleft, 1)
        decision_title = self.font.render('决策预览', True, self.colors['panel_text'])
        self.screen.blit(decision_title, (panel_rect.x + 16, panel_rect.y + 16))
        hint = self.tiny_font.render('基于当前地形、功能层与路径状态实时更新', True, self.colors['panel_text'])
        self.screen.blit(hint, (panel_rect.x + 16, panel_rect.y + 44))
        self.render_single_unit_decision_panel(game_engine, panel_rect)

    def _handle_function_pick_click(self, game_engine, world_pos):
        if self.function_pick_mode == 'measure_a':
            self.measure_points['a'] = (float(world_pos[0]), float(world_pos[1]))
            game_engine.add_log(f'已设置测距 A 点: ({int(world_pos[0])}, {int(world_pos[1])})', 'system')
        elif self.function_pick_mode == 'measure_b':
            self.measure_points['b'] = (float(world_pos[0]), float(world_pos[1]))
            distance_m = self._world_distance_m(game_engine.map_manager, self.measure_points['a'], self.measure_points['b'])
            game_engine.add_log(f'已设置测距 B 点，距离 {distance_m:.2f}m', 'system')
        elif self.function_pick_mode == 'path_start':
            if game_engine.teleport_focus_entity(world_pos):
                game_engine.add_log(f'已设置路径起点: ({int(world_pos[0])}, {int(world_pos[1])})', 'system')
        elif self.function_pick_mode == 'path_goal':
            if game_engine.set_function_path_goal(world_pos):
                game_engine.add_log(f'已设置路径终点: ({int(world_pos[0])}, {int(world_pos[1])})', 'system')
        self.function_pick_mode = ''

    def _begin_function_entity_drag(self, game_engine, world_pos, screen_pos):
        entity = self._pick_single_unit_test_entity(game_engine, screen_pos)
        if entity is None:
            return False
        self.dragged_entity_id = entity.id
        entity_key = entity.id.split('_', 1)[1] if '_' in entity.id else entity.id
        if entity_key in {'robot_1', 'robot_2', 'robot_3', 'robot_4', 'robot_7'}:
            game_engine.set_single_unit_test_focus(team=entity.team, entity_key=entity_key)
        self._move_dragged_entity(game_engine, world_pos, announce=False)
        return True

    def render_toolbar(self, game_engine):
        pygame.draw.rect(self.screen, self.colors['toolbar'], (0, 0, self.window_width, self.toolbar_height))
        buttons = [
            ('开始/重开', 'start_match', False),
            ('暂停/继续', 'toggle_pause', game_engine.paused and not game_engine.rules_engine.game_over),
            ('保存存档', 'save_match', False),
            ('保存设置', 'save_settings', False),
            ('浏览', 'mode:none', self.edit_mode == 'none'),
            ('功能编辑', 'mode:function', self.edit_mode == 'function'),
            ('地形编辑', 'mode:terrain', self.edit_mode == 'terrain'),
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

        state_label = '已暂停' if game_engine.paused else '运行中'
        state_text = self.small_font.render(f'状态: {state_label}', True, self.colors['toolbar_text'])
        self.screen.blit(state_text, (self.window_width - state_text.get_width() - 12, 18))

    def render_sidebar(self, game_engine):
        if self.viewport is None:
            return

        panel_rect = pygame.Rect(
            self.viewport['sidebar_x'],
            self.toolbar_height + self.hud_height,
            self.panel_width,
            self.window_height - self.toolbar_height - self.hud_height,
        )
        pygame.draw.rect(self.screen, self.colors['panel'], panel_rect)
        pygame.draw.line(self.screen, self.colors['panel_border'], panel_rect.topleft, panel_rect.bottomleft, 1)
        title = self.font.render('对局控制' if self.edit_mode == 'none' else self._mode_label(self.edit_mode), True, self.colors['panel_text'])
        self.screen.blit(title, (panel_rect.x + 16, panel_rect.y + 16))

        if self.edit_mode == 'function':
            self.render_function_panel(game_engine, panel_rect)
            decision_rect = pygame.Rect(
                panel_rect.right,
                panel_rect.y,
                self.decision_panel_width,
                panel_rect.height,
            )
            self._render_function_decision_panel(game_engine, decision_rect)
        elif self.edit_mode == 'none':
            self.render_match_control_panel(game_engine, panel_rect)
        elif self.edit_mode == 'terrain':
            self.render_terrain_editor_panel(game_engine, panel_rect)
        elif self.edit_mode == 'entity':
            self.render_entity_panel(game_engine, panel_rect)
        elif self.edit_mode == 'rules':
            self.render_rules_panel(game_engine, panel_rect)

        if self.edit_mode == 'none' and game_engine.is_single_unit_test_mode():
            decision_rect = pygame.Rect(
                panel_rect.right,
                panel_rect.y,
                self.decision_panel_width,
                panel_rect.height,
            )
            pygame.draw.rect(self.screen, self.colors['panel'], decision_rect)
            pygame.draw.line(self.screen, self.colors['panel_border'], decision_rect.topleft, decision_rect.bottomleft, 1)
            decision_title = self.font.render('决策可视化', True, self.colors['panel_text'])
            self.screen.blit(decision_title, (decision_rect.x + 16, decision_rect.y + 16))
            self.render_single_unit_decision_panel(game_engine, decision_rect)

    def render_function_panel(self, game_engine, panel_rect):
        y = panel_rect.y + 56
        tab_specs = [(label, f'function_tab:{tab_id}', self.function_tab == tab_id) for tab_id, label in self.FUNCTION_TABS]
        y = self._layout_panel_buttons(panel_rect, y, tab_specs, min_width=64, button_height=26) + 14

        if self.function_tab == 'passability':
            self.render_function_passability_panel(game_engine, panel_rect, y)
        elif self.function_tab == 'measure':
            self.render_function_measure_panel(game_engine, panel_rect, y)
        elif self.function_tab == 'path':
            self.render_function_path_panel(game_engine, panel_rect, y)
        else:
            self.render_function_dummy_panel(game_engine, panel_rect, y)

    def render_function_passability_panel(self, game_engine, panel_rect, y):
        lines = [
            '复用地图编辑交互: 刷子/圆/矩形/多边形/直线。',
            '按住 Shift 可水平/垂直吸附；右键拖动画面。',
            '条件通过默认按当前方向角限制通行；Slope 形状可像斜坡一样直接画箭头。',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        y += 8
        pass_specs = [
            (self.FUNCTION_PASS_MODE_LABELS[pass_mode], f'function_pass_mode:{pass_mode}', self.function_brush['pass_mode'] == pass_mode)
            for pass_mode in ('passable', 'conditional', 'blocked')
        ]
        y = self._layout_panel_buttons(panel_rect, y, pass_specs, min_width=82, button_height=28) + 12

        workflow_specs = (
            ('select', '框选'),
            ('brush', '刷子'),
            ('erase', '擦除'),
            ('shape', '形状'),
        )
        workflow_buttons = [(label, f'terrain_workflow:{workflow_id}', self.terrain_workflow_mode == workflow_id) for workflow_id, label in workflow_specs]
        y = self._layout_panel_buttons(panel_rect, y, workflow_buttons, min_width=60, button_height=26) + 10

        if self.function_brush['pass_mode'] == 'conditional':
            label = self.small_font.render(f'通过方向: {self.function_brush["heading_deg"]:.0f}°', True, self.colors['panel_text'])
            self.screen.blit(label, (panel_rect.x + 16, y + 2))
            minus_rect = pygame.Rect(panel_rect.x + 156, y, 28, 24)
            plus_rect = pygame.Rect(panel_rect.x + 190, y, 28, 24)
            snap_rect = pygame.Rect(panel_rect.x + 224, y, 44, 24)
            self._draw_mode_button(minus_rect, '-', False)
            self._draw_mode_button(plus_rect, '+', False)
            self._draw_mode_button(snap_rect, '45°', False)
            self.panel_actions.append((minus_rect, 'function_heading:-15'))
            self.panel_actions.append((plus_rect, 'function_heading:15'))
            self.panel_actions.append((snap_rect, 'function_heading_snap'))
            y += 34

        if self.terrain_workflow_mode == 'shape':
            shape_specs = (
                ('circle', '圆'),
                ('rect', '矩形'),
                ('polygon', '多边形'),
                ('line', '直线'),
                ('slope', '箭头区'),
            )
            shape_buttons = [(label, f'terrain_shape:{shape_id}', self.terrain_shape_mode == shape_id) for shape_id, label in shape_specs]
            y = self._layout_panel_buttons(panel_rect, y, shape_buttons, min_width=56, gap_x=6, button_height=24) + 8

        y += 6
        radius_text = self.tiny_font.render(f'笔刷半径: {self.terrain_brush_radius}', True, self.colors['panel_text'])
        self.screen.blit(radius_text, (panel_rect.x + 16, y + 4))
        minus_rect = pygame.Rect(panel_rect.x + 98, y + 1, 24, 22)
        plus_rect = pygame.Rect(panel_rect.x + 128, y + 1, 24, 22)
        self._draw_mode_button(minus_rect, '-', False)
        self._draw_mode_button(plus_rect, '+', False)
        self.panel_actions.append((minus_rect, 'terrain_brush_radius:-1'))
        self.panel_actions.append((plus_rect, 'terrain_brush_radius:1'))
        y += 32

        cell = game_engine.map_manager.get_function_grid_cell(self.mouse_world[0], self.mouse_world[1]) if self.mouse_world is not None else None
        info_lines = [
            f'当前模式: {self.FUNCTION_PASS_MODE_LABELS[self.function_brush["pass_mode"]]}',
            '可通过: 20% 透明蓝色',
            '条件通过: 20% 透明橙色 + 箭头',
            '不可通过: 30% 透明红色',
        ]
        if cell is not None:
            heading_text = ''
            if cell.get('heading_deg') is not None:
                heading_text = f' / {float(cell.get("heading_deg", 0.0)):.0f}°'
            info_lines.append(f'鼠标格: {self.FUNCTION_PASS_MODE_LABELS.get(cell.get("pass_mode", "passable"), "可通过")}{heading_text}')
        for line in info_lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

    def render_function_measure_panel(self, game_engine, panel_rect, y):
        lines = [
            '点击“设置 A/B 点”后，在地图上点击一次即可落点。',
            '距离会自动按场地真实尺寸换算为米。',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18
        y += 10
        actions = [
            ('设置 A 点', 'function_pick:measure_a', self.function_pick_mode == 'measure_a'),
            ('设置 B 点', 'function_pick:measure_b', self.function_pick_mode == 'measure_b'),
            ('清除', 'function_measure_clear', False),
        ]
        y = self._layout_panel_buttons(panel_rect, y, actions, min_width=76, button_height=28) + 14
        point_a = self.measure_points.get('a')
        point_b = self.measure_points.get('b')
        distance_m = self._world_distance_m(game_engine.map_manager, point_a, point_b)
        details = [
            f'A 点: {point_a if point_a is not None else "未设置"}',
            f'B 点: {point_b if point_b is not None else "未设置"}',
            f'现实距离: {distance_m:.2f} m',
        ]
        for line in details:
            text = self.small_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 24

    def render_function_path_panel(self, game_engine, panel_rect, y):
        lines = [
            '路径测试使用当前单兵种测试主控单位。',
            '路径运行时会禁用主 AI，仅保留规划、局部避障和自动重规划。',
            '右侧决策预览会基于当前地形、功能层和路径状态实时刷新。',
            '主控单位在功能编辑里禁用跨越，仅用于纯决策与寻路测试。',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18
        y += 8

        team_title = self.small_font.render('主控方', True, self.colors['panel_text'])
        self.screen.blit(team_title, (panel_rect.x + 16, y))
        y += 28
        focus_team = getattr(game_engine, 'single_unit_test_team', 'red')
        team_buttons = [
            ('红方', 'test_focus_team:red', focus_team == 'red'),
            ('蓝方', 'test_focus_team:blue', focus_team == 'blue'),
        ]
        y = self._layout_panel_buttons(panel_rect, y, team_buttons, min_width=72, button_height=26) + 10

        focus_key = getattr(game_engine, 'single_unit_test_entity_key', 'robot_3')
        unit_specs = (
            ('robot_1', '英雄'),
            ('robot_2', '工程'),
            ('robot_3', '步兵1'),
            ('robot_4', '步兵2'),
            ('robot_7', '哨兵'),
        )
        unit_buttons = [(label, f'test_focus_entity:{entity_key}', focus_key == entity_key) for entity_key, label in unit_specs]
        y = self._layout_panel_buttons(panel_rect, y, unit_buttons, min_width=76, gap_x=6, button_height=24) + 16

        focus_entity = game_engine.get_single_unit_test_focus_entity()
        goal = getattr(game_engine, 'function_path_goal', None)
        active = bool(getattr(game_engine, 'function_path_active', False))
        controls = [
            ('设起点', 'function_pick:path_start', self.function_pick_mode == 'path_start'),
            ('设终点', 'function_pick:path_goal', self.function_pick_mode == 'path_goal'),
            ('清除终点', 'function_path_clear_goal', False),
            ('停止路径' if active else '开始路径', 'function_path_toggle', active),
            ('取消取点', 'function_pick:', bool(self.function_pick_mode)),
        ]
        y = self._layout_panel_buttons(panel_rect, y, controls, min_width=84, button_height=28) + 14

        info_lines = [
            f'当前单位: {focus_entity.id if focus_entity is not None else "无"}',
            f'当前终点: {goal if goal is not None else "未设置"}',
            f'路径状态: {"运行中" if active else "待机"}',
        ]
        for line in info_lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        y += 8
        structure_specs = (
            ('red', 'base', '红基地'),
            ('blue', 'base', '蓝基地'),
            ('red', 'outpost', '红前哨'),
            ('blue', 'outpost', '蓝前哨'),
        )
        for team, structure_type, label in structure_specs:
            entity = game_engine.entity_manager.get_entity(f'{team}_{structure_type}')
            hp_text = f'{int(getattr(entity, "health", 0.0))}/{int(getattr(entity, "max_health", 0.0))}' if entity is not None else '0/0'
            text = self.tiny_font.render(f'{label}: {hp_text}', True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y + 5))
            minus_rect = pygame.Rect(panel_rect.x + 150, y + 1, 26, 22)
            plus_rect = pygame.Rect(panel_rect.x + 182, y + 1, 26, 22)
            self._draw_mode_button(minus_rect, '-', False)
            self._draw_mode_button(plus_rect, '+', False)
            self.panel_actions.append((minus_rect, f'function_structure_hp:{team}:{structure_type}:-100'))
            self.panel_actions.append((plus_rect, f'function_structure_hp:{team}:{structure_type}:100'))
            y += 26

    def render_function_dummy_panel(self, game_engine, panel_rect, y):
        lines = [
            '添加的虚拟单位不会主动行动，但会保留实体属性，可被主控兵种感知与锁定。',
            '功能编辑模式下所有机器人和哨兵都可直接拖拽移动。',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18
        y += 8

        button_specs = [
            ('红步兵', 'function_dummy_add:red:infantry', False),
            ('蓝步兵', 'function_dummy_add:blue:infantry', False),
            ('红哨兵', 'function_dummy_add:red:sentry', False),
            ('蓝哨兵', 'function_dummy_add:blue:sentry', False),
        ]
        y = self._layout_panel_buttons(panel_rect, y, button_specs, min_width=90, button_height=24) + 18

        title = self.small_font.render('当前虚拟单位', True, self.colors['panel_text'])
        self.screen.blit(title, (panel_rect.x + 16, y))
        y += 26
        dummy_entities = game_engine.list_dummy_entities() if hasattr(game_engine, 'list_dummy_entities') else ()
        if not dummy_entities:
            text = self.tiny_font.render('当前没有额外虚拟单位', True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            return
        for entity in dummy_entities[:10]:
            label = f'{entity.id} ({entity.robot_type or entity.type})'
            text = self.tiny_font.render(label, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y + 4))
            delete_rect = pygame.Rect(panel_rect.right - 76, y, 60, 22)
            self._draw_mode_button(delete_rect, '删除', False)
            self.panel_actions.append((delete_rect, f'function_dummy_remove:{entity.id}'))
            y += 26

    def render_map(self, map_manager):
        super().render_map(map_manager)
        self.render_function_grid_overlay(map_manager)
        self.render_measure_overlay(map_manager)
        self.render_function_path_overlay(map_manager)

    def render_terrain_grid_overlay(self, map_manager):
        if self.edit_mode != 'function':
            return super().render_terrain_grid_overlay(map_manager)

        if self.viewport is None or self.mouse_world is None or self.function_tab != 'passability':
            return

        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        center_grid_x, center_grid_y = map_manager._world_to_grid(self.mouse_world[0], self.mouse_world[1])
        grid_width, grid_height = map_manager._grid_dimensions()
        outline = self._function_outline_rgb(self.function_brush['pass_mode'])
        fill = self._function_fill_rgba(self.function_brush['pass_mode'])
        for grid_y in range(max(0, center_grid_y - self.terrain_brush_radius), min(grid_height, center_grid_y + self.terrain_brush_radius + 1)):
            for grid_x in range(max(0, center_grid_x - self.terrain_brush_radius), min(grid_width, center_grid_x + self.terrain_brush_radius + 1)):
                if math.hypot(grid_x - center_grid_x, grid_y - center_grid_y) > self.terrain_brush_radius + 0.25:
                    continue
                x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
                sx1, sy1 = self.world_to_screen(x1, y1)
                sx2, sy2 = self.world_to_screen(x2 + 1, y2 + 1)
                rect = pygame.Rect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))
                pygame.draw.rect(overlay, fill, rect)
                pygame.draw.rect(overlay, (*outline, 190), rect, 1)
                if self.function_brush['pass_mode'] == 'conditional':
                    self._draw_heading_arrow(overlay, rect, self.function_brush.get('heading_deg', 0.0), outline, alpha=200, scale=0.32)
        self.screen.blit(overlay, (0, 0))

    def render_function_grid_overlay(self, map_manager):
        if self.viewport is None:
            return
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        for cell in map_manager.function_grid_overrides.values():
            grid_x = int(cell.get('x', 0))
            grid_y = int(cell.get('y', 0))
            x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
            sx1, sy1 = self.world_to_screen(x1, y1)
            sx2, sy2 = self.world_to_screen(x2 + 1, y2 + 1)
            rect = pygame.Rect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))
            pass_mode = str(cell.get('pass_mode', 'passable'))
            fill_color = self._function_fill_rgba(pass_mode)
            outline = self._function_outline_rgb(pass_mode)
            pygame.draw.rect(overlay, fill_color, rect)
            pygame.draw.rect(overlay, (*outline, 170), rect, 1)
            if pass_mode == 'conditional':
                self._draw_heading_arrow(overlay, rect, cell.get('heading_deg', 0.0), outline)

        if self.edit_mode == 'function' and self.selected_terrain_cell_key:
            grid_x, grid_y = map_manager._decode_function_cell_key(self.selected_terrain_cell_key)
            x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
            sx1, sy1 = self.world_to_screen(x1, y1)
            sx2, sy2 = self.world_to_screen(x2 + 1, y2 + 1)
            rect = pygame.Rect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))
            pygame.draw.rect(overlay, (*self.colors['yellow'], 88), rect)
            pygame.draw.rect(overlay, self.colors['yellow'], rect, 2)
            selected_cell = map_manager.function_grid_overrides.get(self.selected_terrain_cell_key)
            if selected_cell is not None and selected_cell.get('pass_mode') == 'conditional':
                self._draw_heading_arrow(overlay, rect, selected_cell.get('heading_deg', 0.0), self.colors['yellow'])
        self.screen.blit(overlay, (0, 0))

    def render_measure_overlay(self, map_manager):
        point_a = self.measure_points.get('a')
        point_b = self.measure_points.get('b')
        if point_a is None and point_b is None:
            return
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        if point_a is not None:
            pygame.draw.circle(overlay, (72, 210, 120, 220), self.world_to_screen(point_a[0], point_a[1]), 7)
        if point_b is not None:
            pygame.draw.circle(overlay, (245, 199, 69, 220), self.world_to_screen(point_b[0], point_b[1]), 7)
        if point_a is not None and point_b is not None:
            start = self.world_to_screen(point_a[0], point_a[1])
            end = self.world_to_screen(point_b[0], point_b[1])
            pygame.draw.line(overlay, (250, 250, 250, 220), start, end, 2)
            distance_m = self._world_distance_m(map_manager, point_a, point_b)
            label = self.small_font.render(f'{distance_m:.2f} m', True, self.colors['white'])
            midpoint = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)
            overlay.blit(label, label.get_rect(center=(midpoint[0], midpoint[1] - 14)))
        self.screen.blit(overlay, (0, 0))

    def render_function_path_overlay(self, map_manager):
        goal = getattr(self.game_engine, 'function_path_goal', None)
        if goal is None:
            return
        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        pos = self.world_to_screen(goal[0], goal[1])
        pygame.draw.circle(overlay, (255, 255, 255, 72), pos, 14)
        pygame.draw.circle(overlay, (255, 255, 255, 210), pos, 14, 2)
        pygame.draw.line(overlay, (255, 255, 255, 210), (pos[0] - 7, pos[1]), (pos[0] + 7, pos[1]), 2)
        pygame.draw.line(overlay, (255, 255, 255, 210), (pos[0], pos[1] - 7), (pos[0], pos[1] + 7), 2)
        label = self.tiny_font.render('路径终点', True, self.colors['white'])
        overlay.blit(label, (pos[0] + 10, pos[1] - 20))
        self.screen.blit(overlay, (0, 0))

    def _paint_terrain_at(self, game_engine, world_pos):
        if self.edit_mode != 'function':
            return super()._paint_terrain_at(game_engine, world_pos)
        grid_x, grid_y = game_engine.map_manager._world_to_grid(world_pos[0], world_pos[1])
        paint_key = game_engine.map_manager._function_cell_key(grid_x, grid_y)
        if paint_key == self.last_terrain_paint_grid_key:
            return
        game_engine.map_manager.paint_function_grid(
            world_pos[0],
            world_pos[1],
            pass_mode=self.function_brush['pass_mode'],
            brush_radius=self.terrain_brush_radius,
            heading_deg=self.function_brush.get('heading_deg', 0.0),
        )
        self.last_terrain_paint_grid_key = paint_key
        self.function_paint_dirty = True

    def _apply_terrain_erase(self, game_engine, world_pos):
        if self.edit_mode != 'function':
            return super()._apply_terrain_erase(game_engine, world_pos)
        removed = game_engine.map_manager.erase_function_grid(world_pos[0], world_pos[1], self.terrain_brush_radius)
        if removed:
            self.function_paint_dirty = True

    def _sync_terrain_grid_config(self, game_engine):
        if self.edit_mode == 'function' or self.function_paint_dirty:
            if self.function_paint_dirty:
                game_engine.sync_function_grid_config()
                self.function_paint_dirty = False
        return super()._sync_terrain_grid_config(game_engine)

    def _commit_terrain_line(self, game_engine, start, end):
        if self.edit_mode != 'function':
            return super()._commit_terrain_line(game_engine, start, end)
        self._record_undo_snapshot(game_engine, '功能通行直线')
        if game_engine.map_manager.paint_function_line(
            start[0],
            start[1],
            end[0],
            end[1],
            pass_mode=self.function_brush['pass_mode'],
            brush_radius=self.terrain_brush_radius,
            heading_deg=self.function_brush.get('heading_deg', 0.0),
        ):
            self.function_paint_dirty = True
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log('已设置直线通行功能区', 'system')

    def _commit_terrain_rect(self, game_engine, start, end):
        if self.edit_mode != 'function':
            return super()._commit_terrain_rect(game_engine, start, end)
        self._record_undo_snapshot(game_engine, '功能通行矩形')
        game_engine.map_manager.paint_function_rect(
            start[0],
            start[1],
            end[0],
            end[1],
            pass_mode=self.function_brush['pass_mode'],
            heading_deg=self.function_brush.get('heading_deg', 0.0),
        )
        self.function_paint_dirty = True
        self._sync_terrain_grid_config(game_engine)
        game_engine.add_log('已设置矩形通行功能区', 'system')

    def _commit_terrain_circle(self, game_engine, center, edge):
        if self.edit_mode != 'function':
            return super()._commit_terrain_circle(game_engine, center, edge)
        radius = math.hypot(edge[0] - center[0], edge[1] - center[1])
        if radius < game_engine.map_manager.terrain_grid_cell_size * 0.5:
            radius = max(radius, self.terrain_brush_radius * game_engine.map_manager.terrain_grid_cell_size)
        self._record_undo_snapshot(game_engine, '功能通行圆形')
        game_engine.map_manager.paint_function_circle(
            center[0],
            center[1],
            radius,
            pass_mode=self.function_brush['pass_mode'],
            heading_deg=self.function_brush.get('heading_deg', 0.0),
        )
        self.function_paint_dirty = True
        self._sync_terrain_grid_config(game_engine)
        game_engine.add_log(f'已设置圆形通行功能区，半径 {radius:.1f}px', 'system')

    def _commit_terrain_polygon(self, game_engine):
        if self.edit_mode != 'function':
            return super()._commit_terrain_polygon(game_engine)
        if len(self.polygon_points) < 3:
            return
        self._record_undo_snapshot(game_engine, '功能通行多边形')
        changed = game_engine.map_manager.paint_function_polygon(
            self.polygon_points,
            pass_mode=self.function_brush['pass_mode'],
            heading_deg=self.function_brush.get('heading_deg', 0.0),
        )
        self.polygon_points = []
        self.drag_current = None
        self.drag_start = None
        if changed:
            self.function_paint_dirty = True
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log('已设置多边形通行功能区', 'system')

    def _commit_terrain_slope_polygon(self, game_engine):
        if self.edit_mode != 'function':
            return super()._commit_terrain_slope_polygon(game_engine)
        points = self.slope_region_points if len(self.slope_region_points) >= 3 else self.polygon_points
        if len(points) < 3:
            return
        direction_start, direction_end = self._current_slope_direction_points()
        if direction_start is None or direction_end is None or math.hypot(direction_end[0] - direction_start[0], direction_end[1] - direction_start[1]) <= 1e-6:
            game_engine.add_log('请先完成条件通过箭头方向设置', 'system')
            return
        self._record_undo_snapshot(game_engine, '条件通过箭头区')
        result = game_engine.map_manager.paint_function_slope_polygon(
            points,
            pass_mode='conditional',
            direction_start=direction_start,
            direction_end=direction_end,
        )
        self._reset_slope_state()
        self.drag_current = None
        self.drag_start = None
        if result.get('changed'):
            self.function_paint_dirty = True
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log(
                f'已设置条件通过箭头区，影响 {result.get("cell_count", 0)} 个格栅，方向 {result.get("heading_deg", 0.0):.0f}°',
                'system',
            )

    def _collect_terrain_selection_keys(self, map_manager, start, end):
        if self.edit_mode != 'function':
            return super()._collect_terrain_selection_keys(map_manager, start, end)
        grid_x1, grid_x2, grid_y1, grid_y2 = map_manager._grid_ranges_from_world_bounds(start[0], start[1], end[0], end[1])
        selection = set()
        for grid_y in range(grid_y1, grid_y2 + 1):
            for grid_x in range(grid_x1, grid_x2 + 1):
                key = map_manager._function_cell_key(grid_x, grid_y)
                if key in map_manager.function_grid_overrides:
                    selection.add(key)
        return selection

    def _apply_box_terrain_selection(self, game_engine, start, end):
        if self.edit_mode != 'function':
            return super()._apply_box_terrain_selection(game_engine, start, end)
        if start is None or end is None:
            self._clear_terrain_selection()
            return
        map_manager = game_engine.map_manager
        selection = self._collect_terrain_selection_keys(map_manager, start, end)
        if not selection:
            cell = map_manager.get_function_grid_cell(end[0], end[1])
            if cell is not None:
                selection.add(map_manager._function_cell_key(cell['x'], cell['y']))
        self._set_terrain_selection(selection)
        if selection:
            game_engine.add_log(f'已框选 {len(selection)} 个功能格栅', 'system')
        else:
            game_engine.add_log('当前框选区域没有已编辑功能格栅', 'system')

    def _delete_selected_terrain_cells(self, game_engine):
        if self.edit_mode != 'function':
            return super()._delete_selected_terrain_cells(game_engine)
        selection = sorted(self._terrain_selection_keys())
        if not selection:
            return
        self._record_undo_snapshot(game_engine, f'删除 {len(selection)} 个功能格栅')
        removed_count = 0
        for key in selection:
            grid_x, grid_y = game_engine.map_manager._decode_function_cell_key(key)
            if game_engine.map_manager.remove_function_grid_cell(grid_x, grid_y):
                removed_count += 1
        if removed_count:
            self.function_paint_dirty = True
            self._sync_terrain_grid_config(game_engine)
            game_engine.add_log(f'已删除 {removed_count} 个功能格栅', 'system')
        self._clear_terrain_selection()

    def _execute_action(self, game_engine, action):
        if action in {'save_settings', 'save_match', 'start_match', 'load_match'}:
            self._sync_terrain_grid_config(game_engine)
        if action == 'mode:none':
            self.edit_mode = 'none'
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            self.terrain_painting = False
            self.terrain_erasing = False
            self.function_pick_mode = ''
            return
        if action == 'mode:function':
            self.edit_mode = 'function'
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            self.terrain_painting = False
            self.terrain_erasing = False
            self.function_pick_mode = ''
            return
        if action.startswith('function_tab:'):
            self.function_tab = action.split(':', 1)[1]
            self.function_pick_mode = ''
            self.drag_start = None
            self.drag_current = None
            self._reset_slope_state()
            return
        if action.startswith('function_pass_mode:'):
            pass_mode = action.split(':', 1)[1]
            self.function_brush['pass_mode'] = pass_mode
            self.function_brush['label'] = self.FUNCTION_PASS_MODE_LABELS.get(pass_mode, pass_mode)
            if pass_mode != 'conditional' and self.terrain_shape_mode == 'slope':
                self.terrain_shape_mode = 'rect'
            return
        if action.startswith('function_heading:'):
            delta = float(action.split(':', 1)[1])
            self.function_brush['heading_deg'] = (float(self.function_brush.get('heading_deg', 0.0)) + delta) % 360.0
            return
        if action == 'function_heading_snap':
            self.function_brush['heading_deg'] = round(float(self.function_brush.get('heading_deg', 0.0)) / 45.0) * 45.0 % 360.0
            return
        if action.startswith('function_pick:'):
            self.function_pick_mode = action.split(':', 1)[1]
            return
        if action == 'function_measure_clear':
            self.measure_points = {'a': None, 'b': None}
            self.function_pick_mode = ''
            return
        if action == 'function_path_clear_goal':
            game_engine.clear_function_path_goal()
            game_engine.set_function_path_active(False)
            return
        if action == 'function_path_toggle':
            active = game_engine.set_function_path_active(not getattr(game_engine, 'function_path_active', False))
            game_engine.add_log('路径测试已启动' if active else '路径测试已停止', 'system')
            return
        if action.startswith('function_structure_hp:'):
            _, team, structure_type, delta = action.split(':', 3)
            if game_engine.adjust_structure_health(team, structure_type, float(delta)):
                entity = game_engine.entity_manager.get_entity(f'{team}_{structure_type}')
                label = f'{"红" if team == "red" else "蓝"}{"基地" if structure_type == "base" else "前哨"}'
                game_engine.add_log(f'{label}血量已调整为 {int(getattr(entity, "health", 0.0))}', 'system')
            return
        if action.startswith('function_dummy_add:'):
            _, team, role_key = action.split(':', 2)
            position = self.mouse_world or (game_engine.map_manager.map_width * 0.5, game_engine.map_manager.map_height * 0.5)
            entity = game_engine.add_dummy_entity(team=team, role_key=role_key, position=position)
            if entity is not None:
                game_engine.add_log(f'已添加虚拟单位: {entity.id}', 'system')
            return
        if action.startswith('function_dummy_remove:'):
            entity_id = action.split(':', 1)[1]
            if game_engine.remove_dummy_entity(entity_id):
                game_engine.add_log(f'已删除虚拟单位: {entity_id}', 'system')
            return
        return super()._execute_action(game_engine, action)

    def handle_event(self, event, game_engine):
        if self.edit_mode == 'function' and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self.function_pick_mode:
            self.function_pick_mode = ''
            return True

        if self.edit_mode == 'function' and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            action = self._resolve_click_action(event.pos)
            if action is None:
                world_pos = self.screen_to_world(event.pos[0], event.pos[1])
                if world_pos is not None and self.function_pick_mode:
                    self._handle_function_pick_click(game_engine, world_pos)
                    return True
                if world_pos is not None and self._begin_function_entity_drag(game_engine, world_pos, event.pos):
                    return True

        if super().handle_event(event, game_engine):
            return True
        if self.edit_mode != 'function':
            return False

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragged_entity_id is not None:
            entity = game_engine.entity_manager.get_entity(self.dragged_entity_id)
            self.dragged_entity_id = None
            if entity is not None:
                game_engine.add_log(
                    f'已拖拽 {entity.id} 到 ({int(entity.position["x"])}, {int(entity.position["y"])})',
                    'system',
                )
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            world_pos = self.screen_to_world(event.pos[0], event.pos[1])
            if world_pos is None or not self.function_pick_mode:
                return False
            self._handle_function_pick_click(game_engine, world_pos)
            return True
        return False


def main():
    config_manager = ConfigManager()
    config = config_manager.load_config('config.json', 'settings.json')
    config['_config_path'] = 'config.json'
    config['_settings_path'] = 'settings.json'

    game_engine = FunctionalEditorEngine(config, config_manager=config_manager, config_path='config.json')
    renderer = FunctionalEditorRenderer(game_engine, config)
    game_engine.run(renderer)


if __name__ == '__main__':
    main()