#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame


class RendererDetailPopupMixin:
    def render_robot_detail_popup(self, game_engine):
        if not self.selected_hud_entity_id:
            self.robot_detail_rect = None
            return

        detail = game_engine.get_entity_detail_data(self.selected_hud_entity_id)
        if detail is None:
            self.selected_hud_entity_id = None
            self.robot_detail_rect = None
            return

        overlay = pygame.Surface((self.window_width, self.window_height), pygame.SRCALPHA)
        overlay.fill((10, 14, 20, 120))
        self.screen.blit(overlay, (0, 0))

        panel_width = min(540, self.window_width - 80)
        panel_height = min(520, self.window_height - 80)
        panel_rect = pygame.Rect((self.window_width - panel_width) // 2, (self.window_height - panel_height) // 2, panel_width, panel_height)
        self.robot_detail_rect = panel_rect
        pygame.draw.rect(self.screen, self.colors['hud_panel'], panel_rect, border_radius=16)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=16)

        team_color = self.colors['red'] if detail['team'] == 'red' else self.colors['blue']
        title = self.font.render(f"{detail['team'].upper()} {detail['label']} | {detail['robot_type']}", True, self.colors['white'])
        self.screen.blit(title, (panel_rect.x + 22, panel_rect.y + 18))

        close_rect = pygame.Rect(panel_rect.right - 44, panel_rect.y + 14, 28, 28)
        pygame.draw.rect(self.screen, self.colors['toolbar_button'], close_rect, border_radius=8)
        close_text = self.small_font.render('X', True, self.colors['white'])
        self.screen.blit(close_text, close_text.get_rect(center=close_rect.center))
        self.hud_actions.append((close_rect, 'close_robot_detail'))

        status_items = [
            f"状态 {detail['state']}",
            '存活' if detail['alive'] else '已击毁',
            '有枪管' if detail['has_barrel'] else '无枪管',
            '前管锁定' if detail.get('front_gun_locked') else '前管可用',
            f"火控 {detail['fire_control_state']}",
        ]
        if detail.get('sentry_mode'):
            status_items.append(f"哨兵模式 {detail['sentry_mode']}")
        if detail['target_id']:
            status_items.append(f"目标 {detail['target_id']}")
        banner_rect = pygame.Rect(panel_rect.x + 20, panel_rect.y + 58, panel_rect.width - 40, 36)
        pygame.draw.rect(self.screen, team_color, banner_rect, border_radius=10)
        banner_text = self.small_font.render(' | '.join(status_items), True, self.colors['white'])
        self.screen.blit(banner_text, banner_text.get_rect(center=banner_rect.center))

        mode_y = panel_rect.y + 102
        left_x = panel_rect.x + 24
        right_x = panel_rect.centerx + 12
        if detail.get('supports_drive_modes', False):
            mode_labels = detail.get('mode_labels', {})
            left_title = mode_labels.get('left_title', '底盘模式')
            right_title = mode_labels.get('right_title', '云台模式')
            left_options = mode_labels.get('left_options', [('health_priority', '血量优先'), ('power_priority', '功率优先')])
            right_options = mode_labels.get('right_options', [('cooling_priority', '冷却优先'), ('burst_priority', '爆发优先')])

            chassis_label = self.tiny_font.render(left_title, True, self.colors['white'])
            gimbal_label = self.tiny_font.render(right_title, True, self.colors['white'])
            self.screen.blit(chassis_label, (left_x, mode_y))
            self.screen.blit(gimbal_label, (right_x, mode_y))

            chassis_hp_rect = pygame.Rect(left_x + 64, mode_y - 4, 78, 24)
            chassis_power_rect = pygame.Rect(left_x + 148, mode_y - 4, 78, 24)
            gimbal_cool_rect = pygame.Rect(right_x + 64, mode_y - 4, 78, 24)
            gimbal_burst_rect = pygame.Rect(right_x + 148, mode_y - 4, 78, 24)
            self._draw_mode_button(chassis_hp_rect, left_options[0][1], detail.get('chassis_mode') == left_options[0][0])
            self._draw_mode_button(chassis_power_rect, left_options[1][1], detail.get('chassis_mode') == left_options[1][0])
            self._draw_mode_button(gimbal_cool_rect, right_options[0][1], detail.get('gimbal_mode') == right_options[0][0])
            self._draw_mode_button(gimbal_burst_rect, right_options[1][1], detail.get('gimbal_mode') == right_options[1][0])
            self.hud_actions.extend([
                (chassis_hp_rect, f"entity_mode:{detail['entity_id']}:chassis_mode:{left_options[0][0]}"),
                (chassis_power_rect, f"entity_mode:{detail['entity_id']}:chassis_mode:{left_options[1][0]}"),
                (gimbal_cool_rect, f"entity_mode:{detail['entity_id']}:gimbal_mode:{right_options[0][0]}"),
                (gimbal_burst_rect, f"entity_mode:{detail['entity_id']}:gimbal_mode:{right_options[1][0]}"),
            ])

        start_y = panel_rect.y + 136
        row_gap = 24
        left_lines = [
            f"当前血量: {detail['health']:.0f} / {detail['max_health']:.0f}",
            f"功率限制: {detail['power_limit']:.1f}",
            f"当前功率: {detail['power']:.1f}",
            f"功率恢复: {detail['power_recovery_rate']:.2f}/s",
            f"底盘模式: {dict(detail.get('mode_labels', {}).get('left_options', [('health_priority', '血量优先'), ('power_priority', '功率优先')])).get(detail.get('chassis_mode'), detail.get('chassis_mode'))}",
            f"热量限制: {detail['heat_limit']:.1f}",
            f"当前热量: {detail['heat']:.1f}",
            f"当前冷却速度: {detail['current_cooling_rate']:.2f}/s",
            f"基础冷却速度: {detail['base_heat_dissipation_rate']:.2f}/s",
        ]
        right_lines = [
            f"当前弹药: {detail['ammo']}",
            f"17mm 发弹量: {detail.get('ammo_17mm', 0)}",
            f"42mm 发弹量: {detail.get('ammo_42mm', 0)}",
            f"规则射速: {detail['fire_rate_hz']:.2f} 发/s",
            f"当前射速: {detail['effective_fire_rate_hz']:.2f} 发/s",
            f"单发耗弹: {detail['ammo_per_shot']}",
            f"单发功率: {detail['power_per_shot']:.1f}",
            f"单发加热: {detail['heat_gain_per_shot']:.1f}",
            f"模式二: {dict(detail.get('mode_labels', {}).get('right_options', [('cooling_priority', '冷却优先'), ('burst_priority', '爆发优先')])).get(detail.get('gimbal_mode'), detail.get('gimbal_mode'))}",
            f"枪口冷却剩余: {detail['shot_cooldown']:.2f}s",
            f"过热锁定剩余: {detail['overheat_lock_timer']:.2f}s",
            f"自瞄距离: {detail['auto_aim_max_distance_m']:.2f}m",
            f"自瞄视场: {detail['auto_aim_fov_deg']:.1f}°",
        ]
        extra_lines = [
            f"姿态模式: {detail['posture']}",
            f"脱战状态: {'是' if detail.get('out_of_combat') else '否'}",
            f"姿态切换冷却: {detail['posture_cooldown']:.2f}s",
            f"前管状态: {'锁定' if detail.get('front_gun_locked') else '解锁'}",
            f"无敌剩余: {detail['invincible_timer']:.2f}s",
            f"虚弱剩余: {detail['weak_timer']:.2f}s",
            f"堡垒增益: {'是' if detail['fort_buff_active'] else '否'}",
            f"地形增益剩余: {detail['terrain_buff_timer']:.2f}s",
            f"携带矿物: {detail.get('carried_minerals', 0)}",
            f"规则过热锁定时长: {detail['overheat_lock_duration']:.2f}s",
            f"规则距离映射: {detail['auto_aim_max_distance_world']:.1f}单位",
        ]

        for index, line in enumerate(left_lines):
            text = self.small_font.render(line, True, self.colors['white'])
            self.screen.blit(text, (left_x, start_y + index * row_gap))
        for index, line in enumerate(right_lines):
            text = self.small_font.render(line, True, self.colors['white'])
            self.screen.blit(text, (right_x, start_y + index * row_gap))

        extra_y = panel_rect.y + panel_rect.height - 108
        for index, line in enumerate(extra_lines[:4]):
            text = self.tiny_font.render(line, True, self.colors['white'])
            self.screen.blit(text, (left_x, extra_y + index * 18))
        for index, line in enumerate(extra_lines[4:]):
            text = self.tiny_font.render(line, True, self.colors['white'])
            self.screen.blit(text, (right_x, extra_y + index * 18))

        buff_labels = detail.get('active_buff_labels', [])
        if buff_labels:
            buff_text = self.tiny_font.render('当前增益: ' + ' / '.join(buff_labels[:3]), True, self.colors['yellow'])
            self.screen.blit(buff_text, (left_x, panel_rect.bottom - 22))