#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from pygame_compat import pygame


class RendererSidebarMixin:
    def render_sidebar(self, game_engine):
        if self.viewport is None or self.edit_mode == 'none':
            return

        panel_rect = pygame.Rect(
            self.viewport['sidebar_x'],
            self.toolbar_height + self.hud_height,
            self.panel_width,
            self.window_height - self.toolbar_height - self.hud_height,
        )
        pygame.draw.rect(self.screen, self.colors['panel'], panel_rect)
        pygame.draw.line(self.screen, self.colors['panel_border'], panel_rect.topleft, panel_rect.bottomleft, 1)
        title = self.font.render(self._mode_label(self.edit_mode), True, self.colors['panel_text'])
        self.screen.blit(title, (panel_rect.x + 16, panel_rect.y + 16))

        if self.edit_mode == 'terrain':
            self.render_terrain_editor_panel(game_engine, panel_rect)
        elif self.edit_mode == 'entity':
            self.render_entity_panel(game_engine, panel_rect)
        elif self.edit_mode == 'rules':
            self.render_rules_panel(game_engine, panel_rect)

    def render_facility_panel(self, game_engine, panel_rect):
        y = panel_rect.y + 56
        self.wall_panel_rect = None
        self.terrain_panel_rect = None
        options = self._region_options()
        selected_facility = self._selected_region_option()
        if selected_facility is None:
            return

        facility_rect = pygame.Rect(panel_rect.x + 16, y, 92, 26)
        buff_rect = pygame.Rect(panel_rect.x + 116, y, 92, 26)
        self._draw_mode_button(facility_rect, '设施设置', self.region_palette == 'facility')
        self._draw_mode_button(buff_rect, '增益设置', self.region_palette == 'buff')
        self.panel_actions.append((facility_rect, 'region_palette:facility'))
        self.panel_actions.append((buff_rect, 'region_palette:buff'))
        y += 36

        wall_mode = selected_facility['type'] == 'wall'
        if wall_mode:
            lines = [
                '墙体点一下起点，再点一下终点',
                '右键取消当前墙体或删除墙',
                'Q / E 切换设施项',
                '点击保存设置写入本地 setting 文件',
            ]
        elif self.facility_draw_shape == 'polygon':
            lines = [
                '多边形左键逐点连接',
                '点回第一个点 / 回车 / 右键 可闭合',
                'Esc 取消当前多边形',
                'Q / E 切换设施项',
            ]
        else:
            lines = [
                '矩形设施左键拖拽绘制',
                '右键删除当前光标下设施',
                'Q / E 切换设施项',
                '点击保存设置写入本地 setting 文件',
            ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        info_lines = []
        if self.mouse_world is not None:
            regions = game_engine.map_manager.get_regions_at(self.mouse_world[0], self.mouse_world[1])
            facility = regions[0] if regions else None
            if facility:
                info_lines = [
                    '当前命中设施',
                    f"ID: {facility.get('id', '-')}",
                    f"类型: {facility.get('type', '-')}",
                    f"队伍: {facility.get('team', '-')}",
                ]
                if facility.get('type') != 'boundary':
                    info_lines.append(f"高度: {facility.get('height_m', 0.0):.2f}m")
                if len(regions) > 1:
                    info_lines.append(f"叠加区域: {len(regions)}")

        y += 8
        if not wall_mode:
            rect_mode_rect = pygame.Rect(panel_rect.x + 16, y, 72, 26)
            polygon_mode_rect = pygame.Rect(panel_rect.x + 96, y, 88, 26)
            self._draw_mode_button(rect_mode_rect, '矩形', self.facility_draw_shape == 'rect')
            self._draw_mode_button(polygon_mode_rect, '多边形', self.facility_draw_shape == 'polygon')
            self.panel_actions.append((rect_mode_rect, 'facility_shape:rect'))
            self.panel_actions.append((polygon_mode_rect, 'facility_shape:polygon'))
            y += 38

        row_height = 34
        info_height = len(info_lines) * 18 + 18 if info_lines else 0
        available_bottom = panel_rect.bottom - y - 16
        min_visible_rows = 4
        editor_height = 0
        if wall_mode:
            editor_height = min(292, max(236, available_bottom - min_visible_rows * row_height))
        else:
            editor_height = min(280, max(220, available_bottom - min_visible_rows * row_height))
        reserved_bottom = max(info_height, max(0, editor_height))
        visible_height = panel_rect.bottom - y - reserved_bottom - 24
        max_visible = max(1, visible_height // row_height)
        max_scroll = max(0, len(options) - max_visible)
        self.facility_scroll = max(0, min(self.facility_scroll, max_scroll))
        end_index = min(len(options), self.facility_scroll + max_visible)

        for index in range(self.facility_scroll, end_index):
            facility = options[index]
            rect = pygame.Rect(panel_rect.x + 16, y, panel_rect.width - 32, 28)
            active = index == self._selected_region_index()
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], rect, border_radius=5)
            text = self.small_font.render(facility['label'], True, self.colors['panel_text'])
            self.screen.blit(text, (rect.x + 10, rect.y + 5))
            self.panel_actions.append((rect, f'facility:{index}'))
            y += row_height

        if len(options) > max_visible:
            self._render_panel_scrollbar(panel_rect, panel_rect.bottom - visible_height - 16, visible_height, max_visible, len(options), self.facility_scroll)

        if wall_mode:
            wall_panel_rect = pygame.Rect(panel_rect.x + 16, panel_rect.bottom - editor_height - 8, panel_rect.width - 32, editor_height)
            self.wall_panel_rect = wall_panel_rect
            self.render_wall_panel(game_engine, wall_panel_rect)
        elif selected_facility['type'] != 'boundary':
            terrain_panel_rect = pygame.Rect(panel_rect.x + 16, panel_rect.bottom - editor_height - 8, panel_rect.width - 32, editor_height)
            self.terrain_panel_rect = terrain_panel_rect
            self.render_terrain_panel(game_engine, terrain_panel_rect, selected_facility)
        elif info_lines:
            info_y = panel_rect.bottom - info_height - 8
            for line in info_lines:
                text = self.tiny_font.render(line, True, self.colors['panel_text'])
                self.screen.blit(text, (panel_rect.x + 16, info_y))
                info_y += 18

    def render_terrain_editor_panel(self, game_engine, panel_rect):
        toggle_y = panel_rect.y + 56
        terrain_rect = pygame.Rect(panel_rect.x + 16, toggle_y, 92, 28)
        facility_rect = pygame.Rect(panel_rect.x + 116, toggle_y, 92, 28)
        self._draw_mode_button(terrain_rect, '地形笔刷', self.terrain_editor_tool == 'terrain')
        self._draw_mode_button(facility_rect, '设施放置', self.terrain_editor_tool == 'facility')
        self.panel_actions.append((terrain_rect, 'terrain_tool:terrain'))
        self.panel_actions.append((facility_rect, 'terrain_tool:facility'))

        content_rect = pygame.Rect(panel_rect.x, toggle_y + 36, panel_rect.width, panel_rect.height - 36)
        if self.terrain_editor_tool == 'facility':
            self.render_facility_panel(game_engine, content_rect)
            return

        self.render_terrain_brush_panel(game_engine, content_rect)

    def render_terrain_brush_panel(self, game_engine, panel_rect):
        self.terrain_panel_rect = panel_rect
        self.terrain_preview_rect = None
        y = panel_rect.y + 56
        lines = [
            '左键拖拽涂抹格栅地形',
            '上半区右键拖动旋转3D，下半区右键短按选中',
            '设施编辑已合并到本模式顶部的“设施放置”',
            '总览终端下半区也可直接刷地形和放设施',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        brush = self._selected_terrain_brush_def()
        height_rect = pygame.Rect(panel_rect.right - 138, y + 2, 124, 22)
        height_active = self._is_numeric_input_active('terrain_brush', 'brush')
        height_text = f"{brush.get('height_m', 0.0):.2f}"
        if height_active and self.active_numeric_input is not None:
            height_text = self.active_numeric_input['text']
        label = self.tiny_font.render(f"笔刷高度: {brush.get('height_m', 0.0):.2f}m", True, self.colors['panel_text'])
        self.screen.blit(label, (panel_rect.x + 16, y + 5))
        self._draw_input_box(height_rect, height_text, height_active)
        self.panel_actions.append((height_rect, 'height_input:terrain_brush:brush'))
        y += 34

        radius_text = self.tiny_font.render(f'笔刷半径: {self.terrain_brush_radius}', True, self.colors['panel_text'])
        self.screen.blit(radius_text, (panel_rect.x + 16, y + 5))
        minus_rect = pygame.Rect(panel_rect.x + 110, y + 1, 24, 22)
        plus_rect = pygame.Rect(panel_rect.x + 140, y + 1, 24, 22)
        pygame.draw.rect(self.screen, self.colors['toolbar_button'], minus_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.colors['toolbar_button'], plus_rect, border_radius=4)
        self.screen.blit(self.tiny_font.render('-', True, self.colors['white']), (minus_rect.x + 8, minus_rect.y + 3))
        self.screen.blit(self.tiny_font.render('+', True, self.colors['white']), (plus_rect.x + 7, plus_rect.y + 3))
        self.panel_actions.append((minus_rect, 'terrain_brush_radius:-1'))
        self.panel_actions.append((plus_rect, 'terrain_brush_radius:1'))
        y += 34

        layer_toggle_rect = pygame.Rect(panel_rect.x + 16, y, 104, 26)
        alpha_minus_rect = pygame.Rect(panel_rect.x + 132, y + 1, 24, 24)
        alpha_plus_rect = pygame.Rect(panel_rect.x + 194, y + 1, 24, 24)
        alpha_value_rect = pygame.Rect(panel_rect.x + 162, y, 28, 26)
        self._draw_mode_button(layer_toggle_rect, '高度图层', self.height_layer_enabled)
        pygame.draw.rect(self.screen, self.colors['toolbar_button'], alpha_minus_rect, border_radius=4)
        pygame.draw.rect(self.screen, self.colors['toolbar_button'], alpha_plus_rect, border_radius=4)
        self.screen.blit(self.tiny_font.render('-', True, self.colors['white']), (alpha_minus_rect.x + 8, alpha_minus_rect.y + 3))
        self.screen.blit(self.tiny_font.render('+', True, self.colors['white']), (alpha_plus_rect.x + 7, alpha_plus_rect.y + 3))
        alpha_percent = int(round(self.height_layer_alpha / 255.0 * 100))
        alpha_text = self.tiny_font.render(str(alpha_percent), True, self.colors['panel_text'])
        self.screen.blit(alpha_text, alpha_text.get_rect(center=alpha_value_rect.center))
        self.panel_actions.append((layer_toggle_rect, 'height_layer_toggle'))
        self.panel_actions.append((alpha_minus_rect, 'height_layer_alpha:-16'))
        self.panel_actions.append((alpha_plus_rect, 'height_layer_alpha:16'))
        y += 34

        step_text = self.tiny_font.render(f'分层步进: {self.height_layer_step_m:.2f}m', True, self.colors['panel_text'])
        self.screen.blit(step_text, (panel_rect.x + 16, y + 4))
        y += 28

        if self.terrain_workflow_mode == 'shape':
            smooth_text = self.tiny_font.render(f'Smooth 强度: {self.terrain_smooth_strength}', True, self.colors['panel_text'])
            self.screen.blit(smooth_text, (panel_rect.x + 16, y + 5))
            smooth_minus_rect = pygame.Rect(panel_rect.x + 116, y + 1, 24, 22)
            smooth_plus_rect = pygame.Rect(panel_rect.x + 146, y + 1, 24, 22)
            smooth_apply_rect = pygame.Rect(panel_rect.x + 178, y, 88, 24)
            pygame.draw.rect(self.screen, self.colors['toolbar_button'], smooth_minus_rect, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['toolbar_button'], smooth_plus_rect, border_radius=4)
            self._draw_mode_button(smooth_apply_rect, 'Smooth', False)
            self.screen.blit(self.tiny_font.render('-', True, self.colors['white']), (smooth_minus_rect.x + 8, smooth_minus_rect.y + 3))
            self.screen.blit(self.tiny_font.render('+', True, self.colors['white']), (smooth_plus_rect.x + 7, smooth_plus_rect.y + 3))
            self.panel_actions.append((smooth_minus_rect, 'terrain_smooth_strength:-1'))
            self.panel_actions.append((smooth_plus_rect, 'terrain_smooth_strength:1'))
            self.panel_actions.append((smooth_apply_rect, 'terrain_smooth_selected'))
            y += 32

        preview_height = 196
        preview_rect = pygame.Rect(panel_rect.x + 16, panel_rect.bottom - preview_height - 12, panel_rect.width - 32, preview_height)
        self.terrain_preview_rect = preview_rect
        info_block = [
            '地形刷不再区分类型，只控制高度与半径。',
            '墙体、补给区、堡垒等特殊语义继续用上方“设施”工具编辑。',
            '刷出的统一地形默认可通行，用于快速塑形。',
            '高级栏里的 Smooth 可拖框平滑已编辑格栅。',
        ]
        for line in info_block:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        cell = None
        if self.mouse_world is not None:
            cell = game_engine.map_manager.get_terrain_grid_cell(self.mouse_world[0], self.mouse_world[1])
        info_lines = [
            f'当前笔刷: {brush["label"]}',
            '左键涂抹，右键选中/拖动画面',
        ]
        if cell is not None:
            info_lines.append(f'当前格: {cell["type"]} / {cell.get("height_m", 0.0):.2f}m')
        info_y = preview_rect.y - 42
        for line in info_lines[-2:]:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, info_y))
            info_y += 18

        if self.selected_terrain_cell_key:
            grid_x, grid_y = game_engine.map_manager._decode_terrain_cell_key(self.selected_terrain_cell_key)
            selected_cell = game_engine.map_manager.terrain_grid_overrides.get(self.selected_terrain_cell_key)
            if selected_cell is not None:
                selected_text = self.tiny_font.render(
                    f'已选中格栅 ({grid_x}, {grid_y})  {selected_cell.get("type", "flat")}  {selected_cell.get("height_m", 0.0):.2f}m',
                    True,
                    self.colors['panel_text'],
                )
                self.screen.blit(selected_text, (panel_rect.x + 16, preview_rect.y - 64))
                delete_rect = pygame.Rect(panel_rect.right - 110, preview_rect.y - 68, 94, 24)
                pygame.draw.rect(self.screen, self.colors['red'], delete_rect, border_radius=5)
                delete_text = self.tiny_font.render('删除选中地形', True, self.colors['white'])
                self.screen.blit(delete_text, delete_text.get_rect(center=delete_rect.center))
                self.panel_actions.append((delete_rect, 'delete_selected_terrain'))

        self.render_terrain_preview(game_engine, preview_rect)

    def render_terrain_preview(self, game_engine, rect):
        pygame.draw.rect(self.screen, self.colors['panel_row'], rect, border_radius=6)
        title = self.small_font.render('格栅 3D 预览', True, self.colors['panel_text'])
        self.screen.blit(title, (rect.x + 8, rect.y + 8))

        if self.mouse_world is not None:
            center_grid_x, center_grid_y = game_engine.map_manager._world_to_grid(self.mouse_world[0], self.mouse_world[1])
        else:
            grid_width, grid_height = game_engine.map_manager._grid_dimensions()
            center_grid_x = grid_width // 2
            center_grid_y = grid_height // 2

        tile_w = 18
        tile_h = 9
        height_scale = 16
        preview_origin_x = rect.x + rect.width // 2
        preview_origin_y = rect.y + rect.height - 26
        radius = 4
        grid_width, grid_height = game_engine.map_manager._grid_dimensions()

        cells = []
        for grid_y in range(max(0, center_grid_y - radius), min(grid_height, center_grid_y + radius + 1)):
            for grid_x in range(max(0, center_grid_x - radius), min(grid_width, center_grid_x + radius + 1)):
                x1, y1, x2, y2 = game_engine.map_manager._grid_cell_bounds(grid_x, grid_y)
                sample = game_engine.map_manager.sample_raster_layers((x1 + x2) / 2, (y1 + y2) / 2)
                cells.append((grid_x, grid_y, sample))

        cells.sort(key=lambda item: item[0] + item[1])
        for grid_x, grid_y, sample in cells:
            iso_x = preview_origin_x + (grid_x - center_grid_x - (grid_y - center_grid_y)) * tile_w / 2
            iso_y = preview_origin_y + (grid_x - center_grid_x + grid_y - center_grid_y) * tile_h / 2
            height_px = sample['height_m'] * height_scale
            top = [
                (iso_x, iso_y - tile_h - height_px),
                (iso_x + tile_w / 2, iso_y - height_px),
                (iso_x, iso_y + tile_h - height_px),
                (iso_x - tile_w / 2, iso_y - height_px),
            ]
            left = [
                (iso_x - tile_w / 2, iso_y - height_px),
                (iso_x, iso_y + tile_h - height_px),
                (iso_x, iso_y + tile_h),
                (iso_x - tile_w / 2, iso_y),
            ]
            right = [
                (iso_x + tile_w / 2, iso_y - height_px),
                (iso_x, iso_y + tile_h - height_px),
                (iso_x, iso_y + tile_h),
                (iso_x + tile_w / 2, iso_y),
            ]
            top_color = self._terrain_color_by_code(sample['terrain_code'])
            left_color = tuple(max(0, int(channel * 0.72)) for channel in top_color)
            right_color = tuple(max(0, int(channel * 0.86)) for channel in top_color)
            pygame.draw.polygon(self.screen, left_color, left)
            pygame.draw.polygon(self.screen, right_color, right)
            pygame.draw.polygon(self.screen, top_color, top)
            pygame.draw.polygon(self.screen, self.colors['panel_border'], top, 1)

    def render_wall_panel(self, game_engine, rect):
        pygame.draw.rect(self.screen, self.colors['panel_row'], rect, border_radius=6)
        title = self.small_font.render('已画墙', True, self.colors['panel_text'])
        self.screen.blit(title, (rect.x + 8, rect.y + 8))

        walls = game_engine.map_manager.get_facility_regions('wall')
        if not walls:
            text = self.tiny_font.render('当前还没有墙，先在场地上点击两点绘制。', True, self.colors['panel_text'])
            self.screen.blit(text, (rect.x + 8, rect.y + 38))
            self.selected_wall_id = None
            return

        wall_ids = [wall['id'] for wall in walls]
        if self.selected_wall_id not in wall_ids:
            self.selected_wall_id = wall_ids[0]

        list_top = rect.y + 34
        row_height = 26
        list_height = min(104, max(52, rect.height - 154))
        max_visible = max(1, list_height // row_height)
        max_scroll = max(0, len(walls) - max_visible)
        self.wall_scroll = max(0, min(self.wall_scroll, max_scroll))
        end_index = min(len(walls), self.wall_scroll + max_visible)

        for index in range(self.wall_scroll, end_index):
            wall = walls[index]
            row_rect = pygame.Rect(rect.x + 8, list_top, rect.width - 24, 22)
            active = wall['id'] == self.selected_wall_id
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel'], row_rect, border_radius=4)
            label = self.tiny_font.render(f"{wall['id']}  高 {wall.get('height_m', 1.0):.2f}m", True, self.colors['panel_text'])
            self.screen.blit(label, (row_rect.x + 8, row_rect.y + 4))
            self.panel_actions.append((row_rect, f"wall_select:{wall['id']}"))
            list_top += row_height

        if len(walls) > max_visible:
            self._render_panel_scrollbar(rect, rect.y + 34, list_height, max_visible, len(walls), self.wall_scroll)

        wall = game_engine.map_manager.get_facility_by_id(self.selected_wall_id)
        if wall is None:
            return

        details_y = rect.y + 42 + list_height
        movement_rect = pygame.Rect(rect.x + 8, details_y, rect.width - 16, 26)
        vision_rect = pygame.Rect(rect.x + 8, details_y + 32, rect.width - 16, 26)
        self._draw_toggle_row(movement_rect, f"运动阻拦: {'开' if wall.get('blocks_movement', True) else '关'}", wall.get('blocks_movement', True))
        self._draw_toggle_row(vision_rect, f"视野阻拦: {'开' if wall.get('blocks_vision', True) else '关'}", wall.get('blocks_vision', True))
        self.panel_actions.append((movement_rect, f"wall_toggle:{wall['id']}:movement"))
        self.panel_actions.append((vision_rect, f"wall_toggle:{wall['id']}:vision"))

        height_label = self.tiny_font.render(f"墙高: {wall.get('height_m', 1.0):.2f}m", True, self.colors['panel_text'])
        self.screen.blit(height_label, (rect.x + 8, details_y + 72))
        input_rect = pygame.Rect(rect.right - 138, details_y + 68, 124, 22)
        active = self._is_numeric_input_active('wall', wall['id'])
        input_text = f"{wall.get('height_m', 1.0):.2f}"
        if active and self.active_numeric_input is not None:
            input_text = self.active_numeric_input['text']
        self._draw_input_box(input_rect, input_text, active)
        self.panel_actions.append((input_rect, f"height_input:wall:{wall['id']}"))
        hint = self.tiny_font.render('点击输入，回车确认', True, self.colors['panel_text'])
        self.screen.blit(hint, (rect.x + 8, details_y + 94))

        delete_rect = pygame.Rect(rect.right - 108, details_y + 90, 96, 24)
        pygame.draw.rect(self.screen, self.colors['red'], delete_rect, border_radius=5)
        delete_text = self.tiny_font.render('删除该墙', True, self.colors['white'])
        self.screen.blit(delete_text, delete_text.get_rect(center=delete_rect.center))
        self.panel_actions.append((delete_rect, f'delete_facility:{wall["id"]}'))

        summary_lines = [
            f"长度: {math.hypot(wall['x2'] - wall['x1'], wall['y2'] - wall['y1']):.1f}",
            f"端点: ({wall['x1']}, {wall['y1']}) -> ({wall['x2']}, {wall['y2']})",
        ]
        detail_line_y = details_y + 122
        for line in summary_lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (rect.x + 8, detail_line_y))
            detail_line_y += 18

    def render_terrain_panel(self, game_engine, rect, selected_facility):
        pygame.draw.rect(self.screen, self.colors['panel_row'], rect, border_radius=6)
        height_editable_types = {'base', 'outpost', 'fly_slope', 'undulating_road', 'rugged_road', 'first_step', 'second_step', 'dog_hole', 'supply', 'fort'}
        show_height_editor = selected_facility.get('type') in height_editable_types
        title = self.small_font.render('区域详情' if not show_height_editor else '地形高度', True, self.colors['panel_text'])
        self.screen.blit(title, (rect.x + 8, rect.y + 8))

        regions = [
            region for region in game_engine.map_manager.get_facility_regions(selected_facility['type'])
            if region.get('type') == selected_facility['type']
        ]
        if not regions:
            text = self.tiny_font.render('当前类型还没有区域。矩形拖拽或多边形闭合后会出现在这里。', True, self.colors['panel_text'])
            self.screen.blit(text, (rect.x + 8, rect.y + 38))
            self.selected_terrain_id = None
            return

        region_ids = [region['id'] for region in regions]
        if self.selected_terrain_id not in region_ids:
            self.selected_terrain_id = region_ids[-1]

        list_top = rect.y + 34
        row_height = 26
        list_height = min(104, max(52, rect.height - 136))
        max_visible = max(1, list_height // row_height)
        max_scroll = max(0, len(regions) - max_visible)
        self.terrain_scroll = max(0, min(self.terrain_scroll, max_scroll))
        end_index = min(len(regions), self.terrain_scroll + max_visible)

        for index in range(self.terrain_scroll, end_index):
            region = regions[index]
            row_rect = pygame.Rect(rect.x + 8, list_top, rect.width - 24, 22)
            active = region['id'] == self.selected_terrain_id
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel'], row_rect, border_radius=4)
            shape_label = '多边形' if region.get('shape') == 'polygon' else '矩形'
            label_text = f"{region['id']}  {shape_label}"
            if show_height_editor:
                label_text += f"  高 {region.get('height_m', 0.0):.2f}m"
            label = self.tiny_font.render(label_text, True, self.colors['panel_text'])
            self.screen.blit(label, (row_rect.x + 8, row_rect.y + 4))
            self.panel_actions.append((row_rect, f"terrain_select:{region['id']}"))
            list_top += row_height

        if len(regions) > max_visible:
            self._render_panel_scrollbar(rect, rect.y + 34, list_height, max_visible, len(regions), self.terrain_scroll)

        region = game_engine.map_manager.get_facility_by_id(self.selected_terrain_id)
        if region is None:
            return

        details_y = rect.y + 42 + list_height
        shape_text = self.tiny_font.render(f"形状: {'多边形' if region.get('shape') == 'polygon' else '矩形'}", True, self.colors['panel_text'])
        self.screen.blit(shape_text, (rect.x + 8, details_y))
        delete_y = details_y + 20
        if show_height_editor:
            height_label = self.tiny_font.render(f"地形高: {region.get('height_m', 0.0):.2f}m", True, self.colors['panel_text'])
            self.screen.blit(height_label, (rect.x + 8, details_y + 22))

            input_rect = pygame.Rect(rect.right - 138, details_y + 18, 124, 22)
            active = self._is_numeric_input_active('terrain', region['id'])
            input_text = f"{region.get('height_m', 0.0):.2f}"
            if active and self.active_numeric_input is not None:
                input_text = self.active_numeric_input['text']
            self._draw_input_box(input_rect, input_text, active)
            self.panel_actions.append((input_rect, f"height_input:terrain:{region['id']}"))
            hint = self.tiny_font.render('点击输入，回车确认', True, self.colors['panel_text'])
            self.screen.blit(hint, (rect.x + 8, details_y + 48))
            delete_y = details_y + 44
        else:
            team_text = self.tiny_font.render(f"队伍: {region.get('team', 'neutral')}", True, self.colors['panel_text'])
            self.screen.blit(team_text, (rect.x + 8, details_y + 22))

        delete_rect = pygame.Rect(rect.right - 116, delete_y, 104, 24)
        pygame.draw.rect(self.screen, self.colors['red'], delete_rect, border_radius=5)
        delete_text = self.tiny_font.render('删除该区域', True, self.colors['white'])
        self.screen.blit(delete_text, delete_text.get_rect(center=delete_rect.center))
        self.panel_actions.append((delete_rect, f'delete_facility:{region["id"]}'))

        if region.get('shape') == 'polygon':
            summary = f"顶点数: {len(region.get('points', []))}"
        else:
            summary = f"范围: ({region['x1']}, {region['y1']}) -> ({region['x2']}, {region['y2']})"
        summary_text = self.tiny_font.render(summary, True, self.colors['panel_text'])
        self.screen.blit(summary_text, (rect.x + 8, delete_rect.bottom + 8))

        if self.facility_draw_shape == 'polygon' and self.polygon_points:
            pending_text = self.tiny_font.render(f'当前多边形已记录 {len(self.polygon_points)} 个点', True, self.colors['panel_text'])
            self.screen.blit(pending_text, (rect.x + 8, details_y + 94))

    def _draw_toggle_row(self, rect, label, enabled):
        pygame.draw.rect(self.screen, self.colors['panel_row_active'] if enabled else self.colors['panel'], rect, border_radius=4)
        text = self.tiny_font.render(label, True, self.colors['panel_text'])
        self.screen.blit(text, (rect.x + 8, rect.y + 5))

    def _draw_mode_button(self, rect, label, active):
        pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], rect, border_radius=4)
        text = self.tiny_font.render(label, True, self.colors['panel_text'])
        self.screen.blit(text, (rect.x + 10, rect.y + 5))

    def _draw_input_box(self, rect, text, active):
        pygame.draw.rect(self.screen, self.colors['white'], rect, border_radius=4)
        border_color = self.colors['toolbar_button_active'] if active else self.colors['panel_border']
        pygame.draw.rect(self.screen, border_color, rect, 2 if active else 1, border_radius=4)
        rendered = self.tiny_font.render(text or '0.00', True, self.colors['panel_text'])
        self.screen.blit(rendered, (rect.x + 8, rect.y + 4))

    def _terrain_color_by_type(self, terrain_type):
        color_map = {
            'flat': (214, 214, 214),
            'custom_terrain': (214, 156, 92),
            'wall': (50, 50, 50),
            'fly_slope': (240, 150, 60),
            'undulating_road': (120, 220, 120),
            'rugged_road': (86, 74, 62),
            'first_step': (190, 190, 255),
            'second_step': (255, 140, 140),
            'dog_hole': (255, 120, 220),
            'boundary': (255, 255, 255),
            'supply': (248, 214, 72),
            'fort': (145, 110, 80),
            'outpost': (80, 160, 255),
            'base': (255, 80, 80),
            'energy_mechanism': (255, 195, 64),
            'mining_area': (82, 201, 153),
            'mineral_exchange': (69, 137, 255),
            'buff_base': (255, 102, 102),
            'buff_outpost': (118, 174, 255),
            'buff_fort': (161, 129, 95),
            'buff_supply': (255, 229, 110),
            'buff_assembly': (255, 170, 66),
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
        }
        return color_map.get(terrain_type, (255, 255, 255))

    def _terrain_color_by_code(self, terrain_code):
        terrain_type = self.game_engine.map_manager.terrain_label_by_code.get(terrain_code, '平地')
        type_lookup = {
            '平地': 'flat',
            '自定义地形': 'custom_terrain',
            '边界': 'boundary',
            '墙': 'wall',
            '狗洞': 'dog_hole',
            '二级台阶': 'second_step',
            '一级台阶': 'first_step',
            '飞坡': 'fly_slope',
            '起伏路段': 'rugged_road',
            '补给区': 'supply',
            '堡垒': 'fort',
            '前哨站': 'outpost',
            '基地': 'base',
        }
        return self._terrain_color_by_type(type_lookup.get(terrain_type, 'flat'))

    def render_terrain_grid_overlay(self, map_manager):
        if self.viewport is None:
            return

        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        grid_width, grid_height = map_manager._grid_dimensions()

        if self.height_layer_enabled:
            for grid_y in range(grid_height):
                for grid_x in range(grid_width):
                    x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
                    sx1, sy1 = self.world_to_screen(x1, y1)
                    sx2, sy2 = self.world_to_screen(x2 + 1, y2 + 1)
                    rect = pygame.Rect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))
                    if rect.right < self.viewport['map_x'] or rect.left > self.viewport['map_x'] + self.viewport['map_width']:
                        continue
                    if rect.bottom < self.viewport['map_y'] or rect.top > self.viewport['map_y'] + self.viewport['map_height']:
                        continue
                    height_m = map_manager._sample_grid_height(grid_x, grid_y)
                    color = self._height_layer_color(height_m)
                    outline = self._height_layer_outline_color(height_m)
                    pygame.draw.rect(overlay, (*color, self.height_layer_alpha), rect)
                    pygame.draw.rect(overlay, (*outline, min(255, self.height_layer_alpha + 36)), rect, 1)

        if self.mouse_world is not None:
            brush = self._selected_terrain_brush_def()
            center_grid_x, center_grid_y = map_manager._world_to_grid(self.mouse_world[0], self.mouse_world[1])
            color = self._terrain_color_by_type(brush['type'])
            for grid_y in range(max(0, center_grid_y - self.terrain_brush_radius), min(grid_height, center_grid_y + self.terrain_brush_radius + 1)):
                for grid_x in range(max(0, center_grid_x - self.terrain_brush_radius), min(grid_width, center_grid_x + self.terrain_brush_radius + 1)):
                    if math.hypot(grid_x - center_grid_x, grid_y - center_grid_y) > self.terrain_brush_radius + 0.25:
                        continue
                    x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
                    sx1, sy1 = self.world_to_screen(x1, y1)
                    sx2, sy2 = self.world_to_screen(x2 + 1, y2 + 1)
                    rect = pygame.Rect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))
                    pygame.draw.rect(overlay, (*color, 72), rect)
                    pygame.draw.rect(overlay, (*self.colors['white'], 160), rect, 1)
        if self.selected_terrain_cell_key:
            grid_x, grid_y = map_manager._decode_terrain_cell_key(self.selected_terrain_cell_key)
            x1, y1, x2, y2 = map_manager._grid_cell_bounds(grid_x, grid_y)
            sx1, sy1 = self.world_to_screen(x1, y1)
            sx2, sy2 = self.world_to_screen(x2 + 1, y2 + 1)
            rect = pygame.Rect(sx1, sy1, max(1, sx2 - sx1), max(1, sy2 - sy1))
            pygame.draw.rect(overlay, (*self.colors['yellow'], 90), rect)
            pygame.draw.rect(overlay, self.colors['yellow'], rect, 2)
        self.screen.blit(overlay, (0, 0))

    def render_entity_panel(self, game_engine, panel_rect):
        y = panel_rect.y + 56
        lines = [
            '长按实体可直接拖拽站位',
            '左键空白处可放置当前实体',
            'R 旋转当前实体朝向',
            'Q / E 切换实体',
            '点击保存设置写入本地 setting 文件',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        y += 8
        for index, (team, key) in enumerate(self.entity_keys):
            rect = pygame.Rect(panel_rect.x + 16, y, panel_rect.width - 32, 28)
            active = index == self.selected_entity_index
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], rect, border_radius=5)
            labels = {
                'robot_1': '1英雄',
                'robot_2': '2工程',
                'robot_3': '3步兵',
                'robot_4': '4步兵',
                'robot_7': '7哨兵',
            }
            team_label = '红方' if team == 'red' else '蓝方'
            text = self.small_font.render(f'{team_label}{labels.get(key, key)}', True, self.colors['panel_text'])
            self.screen.blit(text, (rect.x + 10, rect.y + 5))
            self.panel_actions.append((rect, f'entity:{index}'))
            y += 34

    def render_rules_panel(self, game_engine, panel_rect):
        y = panel_rect.y + 56
        lines = [
            '点击 +/- 调整数值',
            '方向键上下切换，左右调整',
            '保存设置后，下次运行自动按 setting 加载',
            '开始/重开可完整应用新规则',
        ]
        for line in lines:
            text = self.tiny_font.render(line, True, self.colors['panel_text'])
            self.screen.blit(text, (panel_rect.x + 16, y))
            y += 18

        y += 10
        row_height = 32
        numeric_rules = self._flatten_numeric_rules(game_engine.config.get('rules', {}))
        visible_height = panel_rect.bottom - y - 16
        max_visible = max(1, visible_height // row_height)
        start = min(self.rule_scroll, max(0, len(numeric_rules) - max_visible))
        end = min(len(numeric_rules), start + max_visible)

        for visible_index, item in enumerate(numeric_rules[start:end]):
            rule_index = start + visible_index
            rect = pygame.Rect(panel_rect.x + 16, y, panel_rect.width - 32, 28)
            active = rule_index == self.selected_rule_index
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], rect, border_radius=5)
            label = self.tiny_font.render(self._format_rule_label(item['path']), True, self.colors['panel_text'])
            value = self.tiny_font.render(str(item['value']), True, self.colors['panel_text'])
            minus_rect = pygame.Rect(rect.right - 68, rect.y + 4, 24, 20)
            plus_rect = pygame.Rect(rect.right - 34, rect.y + 4, 24, 20)
            pygame.draw.rect(self.screen, self.colors['toolbar_button'], minus_rect, border_radius=4)
            pygame.draw.rect(self.screen, self.colors['toolbar_button'], plus_rect, border_radius=4)
            self.screen.blit(label, (rect.x + 8, rect.y + 7))
            self.screen.blit(value, (rect.right - 118, rect.y + 7))
            self.screen.blit(self.tiny_font.render('-', True, self.colors['white']), (minus_rect.x + 8, minus_rect.y + 2))
            self.screen.blit(self.tiny_font.render('+', True, self.colors['white']), (plus_rect.x + 7, plus_rect.y + 2))
            self.panel_actions.append((rect, f'rule_select:{rule_index}'))
            self.panel_actions.append((minus_rect, f'rule_adjust:{item["path"]}:-1'))
            self.panel_actions.append((plus_rect, f'rule_adjust:{item["path"]}:1'))
            y += row_height

    def _flatten_numeric_rules(self, data, prefix=''):
        items = []
        for key, value in data.items():
            path = f'{prefix}.{key}' if prefix else key
            if isinstance(value, dict):
                items.extend(self._flatten_numeric_rules(value, path))
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                items.append({'path': path, 'value': value})
        return items

    def _format_rule_label(self, path):
        return path.replace('.', ' / ')

    def _terrain_brush_active(self):
        return self.edit_mode == 'terrain' and self.terrain_editor_tool == 'terrain'

    def _terrain_select_mode_active(self):
        return self._terrain_brush_active() and getattr(self, 'terrain_workflow_mode', 'brush') == 'select'

    def _terrain_paint_mode_active(self):
        return self._terrain_brush_active() and getattr(self, 'terrain_workflow_mode', 'brush') == 'brush'

    def _terrain_eraser_mode_active(self):
        return self._terrain_brush_active() and getattr(self, 'terrain_workflow_mode', 'brush') == 'erase'

    def _terrain_shape_tool_active(self):
        return self._terrain_brush_active() and getattr(self, 'terrain_workflow_mode', 'brush') == 'shape'

    def _facility_edit_active(self):
        return self.edit_mode == 'terrain' and self.terrain_editor_tool == 'facility'

    def _mode_label(self, mode):
        labels = {
            'none': '浏览模式',
            'terrain': '地形编辑',
            'entity': '站位编辑',
            'rules': '规则编辑',
        }
        if mode == 'terrain':
            return '统一编辑(设施)' if self.terrain_editor_tool == 'facility' else '统一编辑(地形)'
        return labels.get(mode, mode)

    def _render_panel_scrollbar(self, panel_rect, top_y, height, visible_count, total_count, scroll_value):
        track_rect = pygame.Rect(panel_rect.right - 14, top_y, 6, height)
        pygame.draw.rect(self.screen, self.colors['panel_border'], track_rect, border_radius=3)

        thumb_height = max(28, int(height * (visible_count / max(total_count, 1))))
        max_scroll = max(1, total_count - visible_count)
        travel = max(0, height - thumb_height)
        thumb_y = top_y if total_count <= visible_count else top_y + int((scroll_value / max_scroll) * travel)
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], thumb_rect, border_radius=3)