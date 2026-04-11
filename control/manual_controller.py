#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from pygame_compat import pygame

class ManualController:
    def __init__(self, config):
        self.config = config
        self.max_speed = config.get('physics', {}).get('max_speed', 3.5)
        self.max_angular_speed = config.get('physics', {}).get('max_angular_speed', 180)
        self.enable_entity_movement = config.get('simulator', {}).get('enable_entity_movement', True)
        simulator_config = config.get('simulator', {})
        self.look_sensitivity_deg = float(simulator_config.get('player_look_sensitivity_deg', 0.18))
        self.pitch_sensitivity_deg = float(simulator_config.get('player_pitch_sensitivity_deg', 0.12))
        self.player_turn_follow_rate_deg = float(simulator_config.get('player_turn_follow_rate_deg', 240.0))
        self.player_small_gyro_speed_deg = float(simulator_config.get('player_small_gyro_speed_deg', 420.0))

    def set_look_sensitivity(self, yaw_sensitivity_deg=None, pitch_sensitivity_deg=None):
        if yaw_sensitivity_deg is not None:
            self.look_sensitivity_deg = max(0.01, float(yaw_sensitivity_deg))
        if pitch_sensitivity_deg is not None:
            self.pitch_sensitivity_deg = max(0.01, float(pitch_sensitivity_deg))

    def _speed_to_world_units(self):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return self.max_speed * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)
    
    def _normalize_angle_diff(self, angle_deg):
        return ((float(angle_deg) + 180.0) % 360.0) - 180.0

    def _clamp_pitch(self, entity, pitch_deg):
        max_up = float(getattr(entity, 'max_pitch_up_deg', 25.0))
        max_down = float(getattr(entity, 'max_pitch_down_deg', 25.0))
        return max(-max_down, min(max_up, float(pitch_deg)))

    def _pressed(self, keys, key_code):
        if hasattr(keys, 'get'):
            return float(keys.get(key_code, 0))
        try:
            return float(keys[key_code])
        except Exception:
            return 0.0

    def _select_manual_autoaim_target(self, entity, all_entities, rules_engine):
        if rules_engine is None:
            return None, None, None, None
        max_distance = float(getattr(rules_engine, 'auto_aim_max_distance', 0.0))
        if max_distance <= 0.0:
            return None, None, None, None
        best_target = None
        best_plate = None
        best_yaw = None
        best_pitch = None
        best_error = None
        current_yaw = float(getattr(entity, 'turret_angle', entity.angle))
        current_pitch = float(getattr(entity, 'gimbal_pitch_deg', 0.0))
        for other in all_entities or ():
            if other.id == entity.id or other.team == entity.team or not other.is_alive():
                continue
            for plate in rules_engine.get_entity_armor_plate_targets(other):
                distance = ((plate['x'] - entity.position['x']) ** 2 + (plate['y'] - entity.position['y']) ** 2) ** 0.5
                if distance > max_distance:
                    continue
                if not rules_engine.has_line_of_sight_to_point(entity, plate['x'], plate['y'], plate['z']):
                    continue
                desired_yaw, desired_pitch = rules_engine.get_aim_angles_to_point(entity, plate['x'], plate['y'], plate['z'])
                yaw_diff = abs(self._normalize_angle_diff(desired_yaw - current_yaw))
                pitch_diff = abs(float(desired_pitch) - current_pitch)
                angular_error = yaw_diff * yaw_diff + pitch_diff * pitch_diff
                if best_error is None or angular_error < best_error:
                    best_error = angular_error
                    best_target = other
                    best_plate = plate
                    best_yaw = desired_yaw
                    best_pitch = desired_pitch
        return best_target, best_plate, best_yaw, best_pitch

    def update(self, keys, entities, all_entities=None, rules_engine=None, manual_state=None):
        """更新手动控制"""
        state = manual_state or {}
        yaw_delta = float(state.get('look_dx', 0.0))
        pitch_delta = float(state.get('look_dy', 0.0))
        fire_pressed = bool(state.get('fire_pressed', False))
        autoaim_pressed = bool(state.get('autoaim_pressed', False))
        view_aim_state = state.get('view_aim_state') if isinstance(state.get('view_aim_state'), dict) else None
        camera_mode = str(state.get('camera_mode', 'first_person') or 'first_person')
        small_gyro_pressed = bool(self._pressed(keys, pygame.K_LSHIFT) or self._pressed(keys, pygame.K_RSHIFT))
        jump_pressed = bool(self._pressed(keys, pygame.K_SPACE))

        for entity in tuple(entities or ()):
            if not entity.is_alive():
                continue

            entity.player_controlled = True
            entity.chassis_state = 'player_controlled'
            entity.small_gyro_active = bool(small_gyro_pressed)
            entity.player_camera_mode = camera_mode

            if getattr(entity, 'robot_type', '') == '步兵':
                if jump_pressed and not bool(getattr(entity, 'player_jump_key_down', False)):
                    entity.jump_requested = True
                entity.player_jump_key_down = jump_pressed
            else:
                entity.player_jump_key_down = jump_pressed

            if autoaim_pressed:
                target, plate, target_yaw, target_pitch = self._select_manual_autoaim_target(entity, all_entities or (), rules_engine)
                if target is not None and plate is not None and target_yaw is not None and target_pitch is not None:
                    entity.target = {
                        'id': target.id,
                        'type': target.type,
                        'x': target.position['x'],
                        'y': target.position['y'],
                        'distance': ((target.position['x'] - entity.position['x']) ** 2 + (target.position['y'] - entity.position['y']) ** 2) ** 0.5,
                        'plate_id': plate.get('id'),
                    }
                    entity.manual_aim_point = {
                        'x': float(plate['x']),
                        'y': float(plate['y']),
                        'z': float(plate['z']),
                        'plate_id': plate.get('id'),
                        'target_id': target.id,
                    }
                    entity.auto_aim_locked = True
                    entity.turret_angle = float(target_yaw)
                    entity.gimbal_pitch_deg = self._clamp_pitch(entity, float(target_pitch))
                else:
                    entity.auto_aim_locked = False
                    entity.manual_aim_point = None
            else:
                entity.auto_aim_locked = False
                current_turret_angle = getattr(entity, 'turret_angle', None)
                if current_turret_angle is None:
                    current_turret_angle = entity.angle
                entity.turret_angle = (float(current_turret_angle) + yaw_delta * self.look_sensitivity_deg) % 360.0
                entity.target = None
                if view_aim_state is not None:
                    entity.manual_aim_point = {
                        'x': float(view_aim_state.get('x', entity.position['x'])),
                        'y': float(view_aim_state.get('y', entity.position['y'])),
                        'z': float(view_aim_state.get('z', getattr(entity, 'position', {}).get('z', 0.0))),
                        'origin_x': float(view_aim_state.get('origin_x', entity.position['x'])),
                        'origin_y': float(view_aim_state.get('origin_y', entity.position['y'])),
                        'origin_z': float(view_aim_state.get('origin_z', getattr(entity, 'position', {}).get('z', 0.0))),
                    }
                else:
                    entity.manual_aim_point = None

            current_pitch = float(getattr(entity, 'gimbal_pitch_deg', 0.0))
            entity.gimbal_pitch_deg = self._clamp_pitch(entity, current_pitch + pitch_delta * self.pitch_sensitivity_deg)

            if not self.enable_entity_movement:
                entity.set_velocity(0.0, 0.0, 0.0)
                entity.angular_velocity = 0.0
                entity.fire_control_state = 'firing' if fire_pressed else 'idle'
                continue

            move_forward = self._pressed(keys, pygame.K_w) - self._pressed(keys, pygame.K_s)
            move_right = self._pressed(keys, pygame.K_d) - self._pressed(keys, pygame.K_a)
            speed = self._speed_to_world_units()
            turret_angle = getattr(entity, 'turret_angle', None)
            if turret_angle is None:
                turret_angle = entity.angle
            movement_angle_deg = float(turret_angle)
            movement_intensity = 0.0
            velocity_x = 0.0
            velocity_y = 0.0
            if getattr(entity, 'robot_type', '') == '步兵':
                move_left = self._pressed(keys, pygame.K_a)
                move_right_key = self._pressed(keys, pygame.K_d)
                if move_forward > 1e-6:
                    movement_angle_deg = float(turret_angle)
                    movement_intensity = min(1.0, float(move_forward))
                elif move_forward < -1e-6:
                    movement_angle_deg = float(turret_angle) + 180.0
                    movement_intensity = min(1.0, float(-move_forward))
                elif move_left > move_right_key + 1e-6:
                    movement_angle_deg = float(turret_angle) - 90.0
                    movement_intensity = min(1.0, float(move_left))
                elif move_right_key > move_left + 1e-6:
                    movement_angle_deg = float(turret_angle) + 90.0
                    movement_intensity = min(1.0, float(move_right_key))
            else:
                diagonal = (move_forward ** 2 + move_right ** 2) ** 0.5
                if diagonal > 1e-6:
                    move_forward /= diagonal
                    move_right /= diagonal
                    movement_intensity = 1.0
                yaw_rad = math.radians(float(turret_angle))
                forward_x = math.cos(yaw_rad)
                forward_y = math.sin(yaw_rad)
                right_x = math.cos(yaw_rad + math.pi * 0.5)
                right_y = math.sin(yaw_rad + math.pi * 0.5)
                velocity_x = (forward_x * move_forward + right_x * move_right) * speed
                velocity_y = (forward_y * move_forward + right_y * move_right) * speed
                entity.set_velocity(velocity_x, velocity_y, 0.0)

            if entity.small_gyro_active:
                if getattr(entity, 'robot_type', '') == '步兵':
                    entity.set_velocity(0.0, 0.0, 0.0)
                entity.angular_velocity = float(getattr(entity, 'small_gyro_direction', 1.0)) * self.player_small_gyro_speed_deg
            else:
                if getattr(entity, 'robot_type', '') == '步兵':
                    yaw_rad = math.radians(movement_angle_deg)
                    velocity_x = math.cos(yaw_rad) * speed * movement_intensity
                    velocity_y = math.sin(yaw_rad) * speed * movement_intensity
                    entity.set_velocity(velocity_x, velocity_y, 0.0)
                    if movement_intensity > 1e-6:
                        target_chassis_angle = float(movement_angle_deg)
                    else:
                        target_chassis_angle = float(getattr(entity, 'turret_angle', entity.angle))
                else:
                    target_chassis_angle = getattr(entity, 'turret_angle', None)
                    if target_chassis_angle is None:
                        target_chassis_angle = entity.angle
                    target_chassis_angle = float(target_chassis_angle)
                angle_diff = self._normalize_angle_diff(target_chassis_angle - float(getattr(entity, 'angle', 0.0)))
                max_step = self.player_turn_follow_rate_deg * (1.0 / max(float(self.config.get('simulator', {}).get('fps', 50)), 1.0))
                if abs(angle_diff) <= max_step:
                    entity.angle = target_chassis_angle % 360.0
                    entity.angular_velocity = 0.0
                else:
                    entity.angular_velocity = max(-self.player_turn_follow_rate_deg, min(self.player_turn_follow_rate_deg, angle_diff * 6.0))

            entity.fire_control_state = 'firing' if fire_pressed else 'idle'
