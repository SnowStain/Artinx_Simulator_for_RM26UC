#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import pygame
import time
import threading
import json
import os
from map.map_manager import MapManager
from entities.entity_manager import EntityManager
from physics.physics_engine import PhysicsEngine
from rules.rules_engine import RulesEngine
from control.controller import Controller
from state_machine.sentry_state_machine import SentryStateMachine

class GameEngine:
    def __init__(self, config, config_manager=None, config_path='config.json'):
        self.config = config
        self.config_manager = config_manager
        self.config_path = config_path
        self.settings_path = config.get('_settings_path', 'settings.json')
        self.running = False
        self.fps = config.get('simulator', {}).get('fps', 50)
        self.dt = 1.0 / self.fps
        self.config['rules'] = RulesEngine.build_rule_config(self.config.get('rules', {}))
        
        # 初始化各系统
        self._create_systems()
        
        # 初始化状态机
        self.sentry_state_machine = SentryStateMachine()
        
        # 日志系统
        self.logs = []
        self.max_logs = 10
        
        # 游戏状态
        self.game_time = 0
        self.game_duration = self.config.get('rules', {}).get('game_duration', 420)
        self.score = {'red': 0, 'blue': 0}
        self.paused = True
        self.match_started = False
        self._game_over_announced = False

    def _create_systems(self):
        self.map_manager = MapManager(self.config)
        self.entity_manager = EntityManager(self.config)
        self.physics_engine = PhysicsEngine(self.config)
        self.rules_engine = RulesEngine(self.config)
        self.rules_engine.game_engine = self
        self.controller = Controller(self.config)

    def _reset_runtime_state(self):
        self.game_time = 0
        self.game_duration = self.config.get('rules', {}).get('game_duration', 420)
        self.score = {'red': 0, 'blue': 0}
        self.paused = True
        self.match_started = False
        self.logs = []
        self._game_over_announced = False
    
    def initialize(self):
        """初始化游戏引擎"""
        # 加载地图
        self.map_manager.load_map()
        
        # 创建实体
        self.entity_manager.create_entities()
        
        # 添加初始日志
        self.add_log('对局未开始，点击开始/重开进入 7 分钟对局。', 'system')

    def start_new_match(self):
        """按当前配置重开一局。"""
        self.config['rules'] = RulesEngine.build_rule_config(self.config.get('rules', {}))
        self._create_systems()
        self._reset_runtime_state()
        self.initialize()
        self.game_duration = self.config.get('rules', {}).get('game_duration', 420)
        self.match_started = True
        self.paused = False
        self.add_log('对局开始', 'system')

    def end_match(self):
        """结束当前对局，但不关闭程序。"""
        self.rules_engine.game_over = True
        self.rules_engine.stage = 'ended'
        self.paused = True
        self.match_started = False
        if not self._game_over_announced:
            self.add_log('对局已结束，可点击开始/重开重新开始。', 'system')
            self._game_over_announced = True

    def save_local_settings(self):
        """保存设施、站位和规则到本地 setting 文件。"""
        self.config['map']['facilities'] = self.map_manager.export_facilities_config()
        self.config['map']['terrain_grid'] = self.map_manager.export_terrain_grid_config()
        self.config['entities']['initial_positions'] = self.entity_manager.export_initial_positions()
        self.config['rules'] = RulesEngine.build_rule_config(self.config.get('rules', {}))
        if self.config_manager is not None:
            self.config_manager.config = self.config
            self.config_manager.save_settings(self.settings_path)
        self.add_log(f'本地设置已保存到 {self.settings_path}', 'system')
    
    def add_log(self, message, team="system"):
        """添加日志"""
        self.logs.append({'message': message, 'team': team, 'time': time.time()})
        # 限制日志数量
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
    
    def update(self):
        """更新游戏状态"""
        if self.paused or not self.match_started:
            return

        # 更新时间
        self.game_time += self.dt
        
        # 更新实体状态
        self.entity_manager.update(self.dt)
        
        # 控制处理
        self.controller.update(
            self.entity_manager.entities,
            self.map_manager,
            self.rules_engine,
            self.game_time,
            self.game_duration,
        )

        # 物理模拟
        self.physics_engine.update(self.entity_manager.entities, self.map_manager, self.rules_engine, dt=self.dt)

        # 通用自瞄：除工程外的战斗单位自动锁定最近敌人
        self._update_general_auto_aim()

        # 规则检查
        self.rules_engine.update(
            self.entity_manager.entities,
            map_manager=self.map_manager,
            dt=self.dt,
            game_time=self.game_time,
            game_duration=self.game_duration,
        )
        
        # 更新哨兵状态机
        for entity in self.entity_manager.entities:
            if entity.type == 'sentry':
                self.sentry_state_machine.update(entity)

    def entity_has_barrel(self, entity):
        if entity.type == 'sentry':
            return True
        if entity.type != 'robot':
            return False
        return entity.robot_type != '工程'

    def entity_supports_drive_modes(self, entity):
        if entity.type == 'sentry':
            return True
        if entity.type != 'robot':
            return False
        return entity.robot_type != '工程'

    def _update_general_auto_aim(self):
        max_distance = getattr(self.rules_engine, 'auto_aim_max_distance', 0.0)
        if max_distance <= 0:
            return

        track_speed = float(self.rules_engine.rules.get('shooting', {}).get('auto_aim_track_speed_deg_per_sec', 180.0))

        for entity in self.entity_manager.entities:
            if not entity.is_alive():
                continue
            if entity.type not in {'robot', 'sentry'}:
                continue
            if entity.type == 'sentry' and getattr(entity, 'front_gun_locked', False):
                entity.target = None
                entity.auto_aim_locked = False
                entity.fire_control_state = 'idle'
                continue
            if not self.entity_has_barrel(entity):
                entity.target = None
                entity.auto_aim_locked = False
                entity.fire_control_state = 'idle'
                entity.ai_decision = '工程仅保留机械臂，不参与自动射击'
                continue
            entity.auto_aim_track_speed_deg_per_sec = track_speed

            target = self._select_auto_aim_target(entity, max_distance)
            base_decision = getattr(entity, 'ai_decision', '')
            if target is None:
                entity.target = None
                entity.auto_aim_locked = False
                entity.fire_control_state = 'idle'
                entity.ai_decision = f'{base_decision} | 未发现满足地形可视条件的目标' if base_decision else '未发现满足地形可视条件的目标'
                continue

            distance = self._distance(entity, target)
            entity.target = {
                'id': target.id,
                'type': target.type,
                'x': target.position['x'],
                'y': target.position['y'],
                'distance': distance,
            }
            desired_angle = self.rules_engine._desired_turret_angle(entity, target)
            current_angle = getattr(entity, 'turret_angle', entity.angle)
            angle_diff = self.rules_engine._normalize_angle_diff(desired_angle - current_angle)
            max_step = track_speed * self.dt
            if abs(angle_diff) <= max_step:
                entity.turret_angle = desired_angle
            else:
                entity.turret_angle = (current_angle + max_step * (1 if angle_diff > 0 else -1)) % 360

            assessment = self.rules_engine.evaluate_auto_aim_target(entity, target, distance=distance, require_fov=True)
            entity.auto_aim_locked = bool(assessment.get('can_auto_aim', False))
            effective_fire_rate = self.rules_engine.get_effective_fire_rate_hz(entity)
            entity.fire_control_state = 'firing' if entity.auto_aim_locked and getattr(entity, 'ammo', 0) > 0 and effective_fire_rate > 0 else 'idle'
            if entity.auto_aim_locked:
                lock_text = f'自瞄锁定 {target.id}'
            else:
                lock_text = f'跟踪 {target.id}，角差 {assessment.get("angle_diff", 0.0):.1f}°'
            entity.ai_decision = f'{base_decision} | {lock_text}' if base_decision else lock_text

    def _select_auto_aim_target(self, shooter, max_distance):
        nearest = None
        nearest_distance = None
        for entity in self.entity_manager.entities:
            if entity.team == shooter.team or not entity.is_alive():
                continue
            distance = self._distance(shooter, entity)
            if distance > max_distance:
                continue
            if not self.rules_engine.can_track_target(shooter, entity, distance):
                continue
            if nearest_distance is None or distance < nearest_distance:
                nearest = entity
                nearest_distance = distance
        return nearest

    def _distance(self, entity_a, entity_b):
        return ((entity_a.position['x'] - entity_b.position['x']) ** 2 + (entity_a.position['y'] - entity_b.position['y']) ** 2) ** 0.5
    
    def run(self, renderer):
        """运行游戏主循环"""
        self.running = True
        self.initialize()
        
        clock = pygame.time.Clock()
        
        while self.running:
            # 处理事件
            for event in pygame.event.get():
                if hasattr(renderer, 'handle_event'):
                    if renderer.handle_event(event, self):
                        continue
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
            
            # 更新游戏状态
            self.update()
            
            # 检查游戏是否结束
            if self.rules_engine.game_over and not self._game_over_announced:
                if self.rules_engine.winner:
                    self.add_log(f"游戏结束：{self.rules_engine.winner}方获胜", 'system')
                else:
                    self.add_log('游戏结束', 'system')
                self.paused = True
                self._game_over_announced = True
            
            # 渲染画面
            renderer.render(self)
            
            # 控制帧率
            clock.tick(self.fps)
        
        # 清理资源
        pygame.quit()

    def save_match(self, save_path='saves/latest_match.json'):
        """保存对局快照。"""
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        payload = {
            'game_time': self.game_time,
            'game_duration': self.game_duration,
            'score': self.score,
            'logs': self.logs,
            'entities': self.entity_manager.export_entity_states(),
            'facilities': self.map_manager.export_facilities_config(),
        }
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.add_log(f'对局已保存: {save_path}', 'system')

    def load_match(self, save_path='saves/latest_match.json'):
        """载入对局快照。"""
        if not os.path.exists(save_path):
            self.add_log(f'存档不存在: {save_path}', 'system')
            return False

        with open(save_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)

        self.game_time = payload.get('game_time', self.game_time)
        self.game_duration = payload.get('game_duration', self.game_duration)
        self.score = payload.get('score', self.score)
        self.logs = payload.get('logs', self.logs)
        facilities = payload.get('facilities')
        if facilities:
            self.map_manager.facilities = facilities
        self.entity_manager.import_entity_states(payload.get('entities', []))
        self.match_started = True
        self.paused = False
        self.add_log(f'对局已载入: {save_path}', 'system')
        return True

    def save_editor_config(self):
        """保存开发者模式下编辑后的设施与初始站位。"""
        self.save_local_settings()

    def toggle_pause(self):
        if not self.match_started:
            self.add_log('对局尚未开始，点击开始/重开后才能暂停。', 'system')
            return
        self.paused = not self.paused
        self.add_log('已暂停' if self.paused else '已继续', 'system')
    
    def get_game_state(self):
        """获取游戏状态（用于AI接入）"""
        state = {
            'timestamp': time.time(),
            'game_time': self.game_time,
            'game_duration': self.game_duration,
            'score': self.score,
            'entities': [],
            'referee': {
                'red': self.rules_engine.get_referee_message(
                    self.entity_manager.entities,
                    self.map_manager,
                    self.game_time,
                    self.game_duration,
                    focus_team='red',
                ),
                'blue': self.rules_engine.get_referee_message(
                    self.entity_manager.entities,
                    self.map_manager,
                    self.game_time,
                    self.game_duration,
                    focus_team='blue',
                ),
            }
        }
        
        for entity in self.entity_manager.entities:
            state['entities'].append({
                'id': entity.id,
                'type': entity.type,
                'team': entity.team,
                'position': entity.position,
                'angle': entity.angle,
                'health': entity.health,
                'state': entity.state
            })
        
        return state

    def get_match_hud_data(self):
        """返回顶部比赛 HUD 所需数据。"""
        remaining = max(0.0, self.game_duration - self.game_time)
        pixels_per_meter_x = self.map_manager.map_width / max(self.map_manager.field_length_m, 1e-6)
        pixels_per_meter_y = self.map_manager.map_height / max(self.map_manager.field_width_m, 1e-6)
        avg_pixels_per_meter = (pixels_per_meter_x + pixels_per_meter_y) / 2.0
        teams = {}
        roster_order = ['robot_1', 'robot_2', 'robot_3', 'robot_4', 'robot_7']
        label_map = {
            'robot_1': '1 英雄',
            'robot_2': '2 工程',
            'robot_3': '3 步兵',
            'robot_4': '4 步兵',
            'robot_7': '7 哨兵',
        }

        for team in ['red', 'blue']:
            entities = {entity.id: entity for entity in self.entity_manager.entities if entity.team == team}
            units = []
            for key in roster_order:
                entity = entities.get(f'{team}_{key}')
                if entity is None:
                    continue
                units.append({
                    'id': key,
                    'entity_id': entity.id,
                    'label': label_map.get(key, key),
                    'robot_type': entity.robot_type or '',
                    'hp': int(entity.health),
                    'max_hp': int(entity.max_health),
                    'level': int(getattr(entity, 'level', 1)),
                    'alive': entity.is_alive(),
                    'has_barrel': self.entity_has_barrel(entity),
                })

            base = entities.get(f'{team}_base')
            outpost = entities.get(f'{team}_outpost')
            teams[team] = {
                'gold': int(self.rules_engine.team_gold.get(team, 0)),
                'base_hp': int(base.health) if base else 0,
                'base_max_hp': int(base.max_health) if base else 0,
                'outpost_hp': int(outpost.health) if outpost else 0,
                'outpost_max_hp': int(outpost.max_health) if outpost else 0,
                'units': units,
            }

        return {
            'remaining_time': remaining,
            'round_text': '未开始' if not self.match_started else ('已暂停' if self.paused else 'Round 1/5'),
            'scale_text': f'比例尺 1m≈{avg_pixels_per_meter:.2f}单位 | 8m≈{self.rules_engine.auto_aim_max_distance:.1f}',
            'red': teams['red'],
            'blue': teams['blue'],
        }

    def get_entity_detail_data(self, entity_id):
        entity = self.entity_manager.get_entity(entity_id)
        if entity is None:
            return None

        label_map = {
            'robot_1': '1 英雄',
            'robot_2': '2 工程',
            'robot_3': '3 步兵',
            'robot_4': '4 步兵',
            'robot_7': '7 哨兵',
        }
        short_id = entity.id.replace(f'{entity.team}_', '')
        physics = self.config.get('physics', {})
        power_system = physics.get('power_system', {})
        heat_system = physics.get('heat_system', {})
        type_key_map = {
            '英雄': 'hero',
            '工程': 'engineer',
            '步兵': 'infantry',
            '哨兵': 'sentry',
        }
        rule_type_key = 'sentry' if entity.type == 'sentry' else type_key_map.get(entity.robot_type, 'infantry')
        power_rule = power_system.get(rule_type_key, {})
        heat_rule = heat_system.get(rule_type_key, {})
        rule_snapshot = self.rules_engine.get_entity_rule_snapshot(entity)
        target = None
        if isinstance(getattr(entity, 'target', None), dict):
            target_id = entity.target.get('id')
            if target_id:
                target = self.entity_manager.get_entity(target_id)

        if entity.robot_type == '英雄':
            mode_labels = {
                'left_title': '底盘模式',
                'left_options': [('health_priority', '血量优先'), ('power_priority', '功率优先')],
                'right_title': '武器模式',
                'right_options': [('ranged_priority', '远程优先'), ('melee_priority', '近战优先')],
            }
        elif entity.robot_type == '步兵':
            mode_labels = {
                'left_title': '底盘模式',
                'left_options': [('health_priority', '血量优先'), ('power_priority', '功率优先')],
                'right_title': '云台模式',
                'right_options': [('cooling_priority', '冷却优先'), ('burst_priority', '爆发优先')],
            }
        else:
            mode_labels = {
                'left_title': '底盘模式',
                'left_options': [('health_priority', '血量优先'), ('power_priority', '功率优先')],
                'right_title': '云台模式',
                'right_options': [('cooling_priority', '冷却优先'), ('burst_priority', '爆发优先')],
            }

        return {
            'entity_id': entity.id,
            'team': entity.team,
            'label': label_map.get(short_id, short_id),
            'robot_type': entity.robot_type or ('哨兵' if entity.type == 'sentry' else entity.type),
            'sentry_mode': getattr(entity, 'sentry_mode', 'auto'),
            'state': entity.state,
            'alive': entity.is_alive(),
            'has_barrel': self.entity_has_barrel(entity),
            'front_gun_locked': bool(getattr(entity, 'front_gun_locked', False)),
            'out_of_combat': self.rules_engine.is_out_of_combat(entity),
            'supports_drive_modes': self.entity_supports_drive_modes(entity),
            'mode_labels': mode_labels,
            'target_id': target.id if target is not None else None,
            'health': float(entity.health),
            'max_health': float(entity.max_health),
            'ammo': int(getattr(entity, 'ammo', 0)),
            'ammo_17mm': int(getattr(entity, 'allowed_ammo_17mm', 0)),
            'ammo_42mm': int(getattr(entity, 'allowed_ammo_42mm', 0)),
            'power': float(getattr(entity, 'power', 0.0)),
            'max_power': float(getattr(entity, 'max_power', power_rule.get('max_power', 0.0))),
            'power_recovery_rate': float(getattr(entity, 'power_recovery_rate', power_rule.get('power_recovery_rate', 0.0))),
            'power_limit': float(getattr(entity, 'max_power', power_rule.get('max_power', 0.0))),
            'chassis_mode': getattr(entity, 'chassis_mode', 'health_priority'),
            'heat': float(getattr(entity, 'heat', 0.0)),
            'max_heat': float(getattr(entity, 'max_heat', heat_rule.get('max_heat', 0.0))),
            'heat_limit': float(getattr(entity, 'max_heat', heat_rule.get('max_heat', 0.0))),
            'heat_gain_per_shot': float(rule_snapshot['heat_per_shot']),
            'base_heat_dissipation_rate': float(getattr(entity, 'heat_dissipation_rate', heat_rule.get('heat_dissipation_rate', 0.0))),
            'current_cooling_rate': float(rule_snapshot['current_cooling_rate']),
            'gimbal_mode': getattr(entity, 'gimbal_mode', 'cooling_priority'),
            'shot_cooldown': float(getattr(entity, 'shot_cooldown', 0.0)),
            'overheat_lock_timer': float(getattr(entity, 'overheat_lock_timer', 0.0)),
            'posture': getattr(entity, 'posture', 'mobile'),
            'posture_cooldown': float(getattr(entity, 'posture_cooldown', 0.0)),
            'invincible_timer': float(getattr(entity, 'invincible_timer', 0.0)),
            'weak_timer': float(getattr(entity, 'weak_timer', 0.0)),
            'fort_buff_active': bool(getattr(entity, 'fort_buff_active', False)),
            'terrain_buff_timer': float(getattr(entity, 'terrain_buff_timer', 0.0)),
            'active_buff_labels': list(getattr(entity, 'active_buff_labels', [])),
            'carried_minerals': int(getattr(entity, 'carried_minerals', 0)),
            'fire_control_state': getattr(entity, 'fire_control_state', 'idle'),
            'fire_rate_hz': float(rule_snapshot['fire_rate_hz']),
            'effective_fire_rate_hz': float(rule_snapshot['effective_fire_rate_hz']),
            'ammo_per_shot': int(rule_snapshot['ammo_per_shot']),
            'power_per_shot': float(rule_snapshot['power_per_shot']),
            'armor_center_height_m': float(rule_snapshot['armor_center_height_m']),
            'camera_height_m': float(rule_snapshot['camera_height_m']),
            'overheat_lock_duration': float(rule_snapshot['overheat_lock_duration']),
            'auto_aim_max_distance_m': float(rule_snapshot['auto_aim_max_distance_m']),
            'auto_aim_max_distance_world': float(rule_snapshot['auto_aim_max_distance_world']),
            'auto_aim_fov_deg': float(rule_snapshot['auto_aim_fov_deg']),
            'chassis_profile': dict(rule_snapshot['chassis_profile']),
            'gimbal_profile': dict(rule_snapshot['gimbal_profile']),
        }
