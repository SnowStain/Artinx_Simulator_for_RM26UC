#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame

class ManualController:
    def __init__(self, config):
        self.config = config
        self.max_speed = config.get('physics', {}).get('max_speed', 3.5)
        self.max_angular_speed = config.get('physics', {}).get('max_angular_speed', 180)
        self.enable_entity_movement = config.get('simulator', {}).get('enable_entity_movement', True)

    def _speed_to_world_units(self):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return self.max_speed * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)
    
    def update(self, keys, entities):
        """更新手动控制"""
        # 控制红方哨兵
        sentry = None
        for entity in entities:
            if entity.team == 'red' and entity.type == 'sentry' and entity.is_alive():
                sentry = entity
                break

        if sentry:
            mouse_buttons = pygame.mouse.get_pressed()
            manual_active = any([
                keys[pygame.K_w],
                keys[pygame.K_a],
                keys[pygame.K_s],
                keys[pygame.K_d],
                keys[pygame.K_q],
                keys[pygame.K_e],
                keys[pygame.K_SPACE],
                keys[pygame.K_LSHIFT],
                keys[pygame.K_RSHIFT],
                mouse_buttons[0],
            ])
            if not manual_active:
                return

            if not self.enable_entity_movement:
                sentry.set_velocity(0, 0)
                sentry.angular_velocity = 0
                sentry.fire_control_state = 'firing' if mouse_buttons[0] else 'idle'
                return

            # 移动控制
            linear_x = 0
            linear_y = 0
            
            if keys[pygame.K_w]:
                linear_x += 1
            if keys[pygame.K_s]:
                linear_x -= 1
            if keys[pygame.K_a]:
                linear_y -= 1
            if keys[pygame.K_d]:
                linear_y += 1
            
            # 旋转控制
            angular = 0
            if keys[pygame.K_q]:
                angular += 1
            if keys[pygame.K_e]:
                angular -= 1
            
            # 特殊动作
            if keys[pygame.K_SPACE]:
                # 小陀螺
                sentry.chassis_state = 'spin'
            elif keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                # 快速小陀螺
                sentry.chassis_state = 'fast_spin'
            
            # 设置速度
            speed = self._speed_to_world_units()
            sentry.set_velocity(linear_x * speed, linear_y * speed)
            sentry.angular_velocity = angular * self.max_angular_speed
            sentry.turret_angle = sentry.angle

            # 发射控制
            if mouse_buttons[0]:  # 左键发射
                sentry.fire_control_state = 'firing'
            else:
                sentry.fire_control_state = 'idle'
