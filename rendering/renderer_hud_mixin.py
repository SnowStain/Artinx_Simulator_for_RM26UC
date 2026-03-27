#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame


class RendererHudMixin:
    def render_match_hud(self, game_engine):
        hud_rect = pygame.Rect(0, self.toolbar_height, self.window_width, self.hud_height)
        pygame.draw.rect(self.screen, self.colors['hud_bg'], hud_rect)

        hud_data = game_engine.get_match_hud_data()
        center_x = self.window_width // 2
        center_panel = pygame.Rect(center_x - 96, self.toolbar_height + 10, 192, 86)
        pygame.draw.rect(self.screen, self.colors['hud_center'], center_panel, border_radius=14)

        round_text = self.tiny_font.render(hud_data['round_text'], True, self.colors['white'])
        self.screen.blit(round_text, round_text.get_rect(center=(center_x, self.toolbar_height + 18)))

        scale_text = self.tiny_font.render(hud_data['scale_text'], True, self.colors['white'])
        self.screen.blit(scale_text, scale_text.get_rect(center=(center_x, self.toolbar_height + 96)))

        remaining = max(0, int(hud_data['remaining_time']))
        minutes = remaining // 60
        seconds = remaining % 60
        timer_text = self.hud_big_font.render(f'{minutes}:{seconds:02d}', True, self.colors['white'])
        self.screen.blit(timer_text, timer_text.get_rect(center=(center_x, self.toolbar_height + 50)))

        gold_rect = pygame.Rect(center_x - 78, self.toolbar_height + 64, 156, 26)
        pygame.draw.rect(self.screen, self.colors['hud_panel'], gold_rect, border_radius=12)
        gold_text = self.small_font.render(
            f'金币 红 {hud_data["red"]["gold"]} | 蓝 {hud_data["blue"]["gold"]}',
            True,
            self.colors['hud_gold'],
        )
        self.screen.blit(gold_text, gold_text.get_rect(center=gold_rect.center))

        self._render_team_hud('red', '红方', pygame.Rect(10, self.toolbar_height + 8, center_x - 120, 96), hud_data['red'])
        self._render_team_hud('blue', '蓝方', pygame.Rect(center_x + 110, self.toolbar_height + 8, self.window_width - center_x - 120, 96), hud_data['blue'])

    def _render_team_hud(self, team_key, team_label, rect, team_data):
        team_color = self.colors['red'] if team_key == 'red' else self.colors['blue']
        pygame.draw.rect(self.screen, self.colors['hud_panel'], rect, border_radius=12)

        banner_rect = pygame.Rect(rect.x + 8, rect.y + 8, rect.width - 16, 24)
        pygame.draw.rect(self.screen, team_color, banner_rect, border_radius=10)
        banner_text = self.hud_mid_font.render(f'{team_label}  金币 {team_data["gold"]}', True, self.colors['white'])
        self.screen.blit(banner_text, banner_text.get_rect(center=banner_rect.center))

        structure_text = self.tiny_font.render(
            f'基地 {team_data["base_hp"]}/{team_data["base_max_hp"]}   前哨站 {team_data["outpost_hp"]}/{team_data["outpost_max_hp"]}',
            True,
            self.colors['white'],
        )
        self.screen.blit(structure_text, (rect.x + 12, rect.y + 40))

        unit_area_y = rect.y + 62
        unit_card_width = max(56, (rect.width - 20) // max(1, len(team_data['units'])))
        for index, unit in enumerate(team_data['units']):
            card_rect = pygame.Rect(rect.x + 8 + index * unit_card_width, unit_area_y, unit_card_width - 6, 28)
            border_color = team_color if unit['alive'] else self.colors['gray']
            is_selected = self.selected_hud_entity_id == unit.get('entity_id')
            pygame.draw.rect(self.screen, (28, 33, 41), card_rect, border_radius=8)
            pygame.draw.rect(self.screen, self.colors['yellow'] if is_selected else border_color, card_rect, 2 if is_selected else 1, border_radius=8)
            name_text = self.tiny_font.render(unit['label'], True, self.colors['white'])
            hp_text = self.tiny_font.render(f'{unit["hp"]}', True, self.colors['hud_gold'] if unit['alive'] else self.colors['gray'])
            lv_text = self.tiny_font.render(f'Lv{unit["level"]}', True, self.colors['white'])
            self.screen.blit(name_text, (card_rect.x + 6, card_rect.y + 2))
            self.screen.blit(hp_text, (card_rect.x + 6, card_rect.y + 14))
            self.screen.blit(lv_text, (card_rect.right - lv_text.get_width() - 6, card_rect.y + 14))
            if unit.get('has_barrel'):
                pygame.draw.circle(self.screen, self.colors['green'], (card_rect.right - 12, card_rect.y + 9), 3)
            self.hud_actions.append((card_rect, f'hud_unit:{unit.get("entity_id", "")}'))

    def render_overlay_status(self, game_engine):
        if self.viewport is None:
            return
        lines = [
            f'时间: {int(game_engine.game_time)}s / {int(game_engine.game_duration)}s',
            f'比分: 红方 {game_engine.score["red"]} | 蓝方 {game_engine.score["blue"]}',
            f'模式: {self._mode_label(self.edit_mode)}',
            f'视场: {"显示" if self.show_aim_fov else "隐藏"}',
            f'比例尺: 1m≈{((game_engine.map_manager.pixels_per_meter_x() + game_engine.map_manager.pixels_per_meter_y()) / 2.0):.2f}单位',
            f'8m距离: ≈{game_engine.rules_engine.auto_aim_max_distance:.1f}单位',
        ]
        if self.mouse_world is not None:
            lines.append(f'坐标: ({self.mouse_world[0]}, {self.mouse_world[1]})')

        box = pygame.Surface((280, 24 + len(lines) * 18), pygame.SRCALPHA)
        box.fill(self.colors['overlay_bg'])
        for index, line in enumerate(lines):
            text = self.tiny_font.render(line, True, self.colors['white'])
            box.blit(text, (10, 8 + index * 18))
        left_bottom_pos = (self.viewport['map_x'] + 8, self.viewport['map_y'] + self.viewport['map_height'] - box.get_height() - 8)
        self.screen.blit(box, left_bottom_pos)

        logs = game_engine.logs[-6:]
        if not logs:
            return
        log_surface = pygame.Surface((460, 20 + len(logs) * 18), pygame.SRCALPHA)
        log_surface.fill(self.colors['overlay_log_bg'])
        for index, log in enumerate(logs):
            color = self.colors['white']
            if log['team'] == 'red':
                color = self.colors['red']
            elif log['team'] == 'blue':
                color = self.colors['blue']
            text = self.tiny_font.render(log['message'], True, color)
            log_surface.blit(text, (10, 6 + index * 18))
        self.screen.blit(log_surface, (self.viewport['map_x'] + self.viewport['map_width'] - log_surface.get_width() - 8, self.viewport['map_y'] + self.viewport['map_height'] - log_surface.get_height() - 8))