#!/usr/bin/env python3
# -*- coding: utf-8 -*-

class Entity:
    def __init__(self, entity_id, entity_type, team, position, angle=0, robot_type=None):
        self.id = entity_id
        self.type = entity_type
        self.team = team
        self.robot_type = robot_type  # 机器人类型：英雄、工程、步兵、哨兵
        self.level = 1
        self.display_name = entity_id
        self.position = position  # {'x': x, 'y': y, 'z': z}
        self.spawn_position = dict(position)
        self.respawn_position = dict(position)
        self.previous_position = dict(position)
        self.last_valid_position = dict(position)
        self.angle = angle  # 角度（度）
        self.spawn_angle = angle
        self.turret_angle = angle
        self.velocity = {'vx': 0, 'vy': 0, 'vz': 0}
        self.angular_velocity = 0
        self.health = 100
        self.max_health = 100
        self.state = "idle"
        self.target = None
        self.movable = True
        self.collidable = True
        self.collision_radius = 16.0
        self.wheel_count = 4
        self.collision_recovery_timer = 0.0
        self.collision_recovery_vector = (0.0, 0.0)
        self.active_buff_labels = []
        
        # 底盘功率系统
        self.power = 100
        self.max_power = 100
        self.power_recovery_rate = 1.0
        self.chassis_mode = 'health_priority'
        
        # 枪管热量系统
        self.heat = 0
        self.max_heat = 100
        self.heat_gain_per_shot = 10
        self.heat_dissipation_rate = 5
        self.heat_managed_by_rules = True
        self.heat_lock_state = 'normal'
        self.heat_lock_reason = ''
        self.heat_ui_disabled = False
        self.heat_cooling_accumulator = 0.0
        self.gimbal_mode = 'cooling_priority'
        self.hero_weapon_mode = 'ranged_priority'
        
        # 火控状态
        self.fire_control_state = 'idle'
        self.front_gun_locked = False
        self.auto_aim_locked = False

        # 裁判系统相关状态（哨兵重点使用）
        self.ammo = 0
        self.allowed_ammo_17mm = 0
        self.allowed_ammo_42mm = 0
        self.ammo_type = '17mm'
        self.gold = 0.0
        self.posture = 'mobile'
        self.sentry_mode = 'auto'
        self.posture_cooldown = 0.0
        self.posture_active_time = 0.0
        self.ai_decision = ''
        self.ai_behavior_node = ''
        self.ai_navigation_target = None
        self.ai_movement_target = None
        self.ai_navigation_waypoint = None
        self.ai_path_preview = ()
        self.ai_navigation_subgoals = ()
        self.ai_navigation_path_valid = False
        self.ai_navigation_radius = 0.0
        self.ai_navigation_velocity = (0.0, 0.0)
        self.ai_decision_weights = ()
        self.ai_decision_top3 = ()
        self.ai_decision_selected = ''
        self.search_angular_speed = 36.0
        self.fire_rate_hz = 8.0
        self.ammo_per_shot = 1
        self.power_per_shot = 6.0
        self.autoaim_locked_target_id = None
        self.autoaim_lock_timer = 0.0
        self.auto_aim_hit_probability = 0.0
        self.auto_aim_hit_probability_target_id = None
        self.auto_aim_hit_probability_updated_at = -1e9
        self.shot_cooldown = 0.0
        self.overheat_lock_timer = 0.0
        self.evasive_spin_timer = 0.0
        self.evasive_spin_direction = 1.0
        self.evasive_spin_rate_deg = 420.0
        self.last_damage_source_id = None
        self.respawn_timer = 0.0
        self.respawn_duration = 0.0
        self.respawn_recovery_timer = 0.0
        self.invincible_timer = 0.0
        self.weak_timer = 0.0
        self.respawn_invalid_timer = 0.0
        self.respawn_invalid_elapsed = 0.0
        self.respawn_invalid_pending_release = False
        self.respawn_weak_active = False
        self.respawn_mode = 'normal'
        self.instant_respawn_count = 0
        self.death_handled = False
        self.permanent_eliminated = False
        self.elimination_reason = ''
        self.fort_buff_active = False
        self.trapezoid_highground_active = False
        self.terrain_buff_timer = 0.0
        self.fly_slope_airborne_timer = 0.0
        self.supply_cooldown = 0.0
        self.supply_ammo_claimed = 0
        self.exchange_cooldown = 0.0
        self.last_combat_time = -1e9
        self.pending_rule_events = []
        self.traversal_state = None
        self.max_terrain_step_height_m = 0.35
        self.can_climb_steps = True
        self.step_climb_duration_sec = 2.0
        self.step_climb_state = None
        self.dynamic_damage_taken_mult = 1.0
        self.dynamic_damage_dealt_mult = 1.0
        self.dynamic_cooling_mult = 1.0
        self.dynamic_power_recovery_mult = 1.0
        self.dynamic_power_capacity_mult = 1.0
        self.dynamic_invincible = False
        self.timed_buffs = {}
        self.buff_cooldowns = {}
        self.buff_path_progress = {}
        self.energy_small_buff_timer = 0.0
        self.energy_large_buff_timer = 0.0
        self.energy_large_damage_dealt_mult = 1.0
        self.energy_large_damage_taken_mult = 1.0
        self.energy_large_cooling_mult = 1.0
        self.assembly_buff_time_used = 0.0
        self.hero_deployment_charge = 0.0
        self.hero_deployment_active = False
        self.hero_deployment_zone_active = False
        self.hero_deployment_state = 'inactive'
        self.hero_deployment_target_id = None
        self.hero_deployment_hit_probability = 0.0
        self.hero_deployment_hit_probability_target_id = None
        self.hero_deployment_hit_probability_updated_at = -1e9
        self.carried_minerals = 0
        self.carried_mineral_type = None
        self.mined_minerals_total = 0
        self.exchanged_minerals_total = 0
        self.exchanged_gold_total = 0.0
        self.mining_timer = 0.0
        self.mining_target_duration = 0.0
        self.exchange_timer = 0.0
        self.exchange_target_duration = 0.0
        self.mining_zone_id = None
        self.exchange_zone_id = None
        self.role_purchase_cooldown = 0.0
        self.recent_attackers = []
    
    def update(self, dt):
        """更新实体状态"""
        if getattr(self, 'robot_type', '') == '英雄' and bool(getattr(self, 'hero_deployment_active', False)):
            self.velocity = {'vx': 0.0, 'vy': 0.0, 'vz': 0.0}
            self.angular_velocity = 0.0

        # 更新位置
        if self.movable:
            self.previous_position = dict(self.position)
            self.position['x'] += self.velocity['vx'] * dt
            self.position['y'] += self.velocity['vy'] * dt
            self.position['z'] += self.velocity['vz'] * dt
        
        # 更新角度
        self.angle += self.angular_velocity * dt
        self.angle %= 360

        self.collision_recovery_timer = max(0.0, float(getattr(self, 'collision_recovery_timer', 0.0)) - dt)
        if self.collision_recovery_timer <= 0.0:
            self.collision_recovery_vector = (0.0, 0.0)

        self.autoaim_lock_timer = max(0.0, float(getattr(self, 'autoaim_lock_timer', 0.0)) - dt)
        if self.autoaim_lock_timer <= 0.0:
            self.autoaim_locked_target_id = None

        self.evasive_spin_timer = max(0.0, float(getattr(self, 'evasive_spin_timer', 0.0)) - dt)
        
        # 更新底盘功率（恢复）
        power_recovery_mult = max(0.0, float(getattr(self, 'dynamic_power_recovery_mult', 1.0)))
        self.power += self.power_recovery_rate * power_recovery_mult * dt
        power_capacity = float(getattr(self, 'max_power', 0.0)) * max(0.0, float(getattr(self, 'dynamic_power_capacity_mult', 1.0)))
        if self.power > power_capacity:
            self.power = power_capacity
        
        # 热量由规则引擎按 10Hz 规则统一处理，避免与实体逐帧冷却叠加。
        if not bool(getattr(self, 'heat_managed_by_rules', True)):
            cooling_mult = max(0.0, float(getattr(self, 'dynamic_cooling_mult', 1.0)))
            self.heat -= self.heat_dissipation_rate * cooling_mult * dt
            if self.heat < 0:
                self.heat = 0
    
    def set_position(self, x, y, z=0):
        """设置位置"""
        self.position = {'x': x, 'y': y, 'z': z}
        self.previous_position = dict(self.position)
        self.last_valid_position = dict(self.position)
    
    def set_velocity(self, vx, vy, vz=0):
        """设置速度"""
        if not self.movable:
            self.velocity = {'vx': 0, 'vy': 0, 'vz': 0}
            return
        if getattr(self, 'robot_type', '') == '英雄' and bool(getattr(self, 'hero_deployment_active', False)):
            self.velocity = {'vx': 0.0, 'vy': 0.0, 'vz': 0.0}
            return
        self.velocity = {'vx': vx, 'vy': vy, 'vz': vz}
    
    def take_damage(self, damage):
        """受到伤害"""
        self.health -= damage
        if self.health< 0:
            self.health = 0
            self.state = "destroyed"
    
    def heal(self, amount):
        """恢复生命值"""
        self.health += amount
        if self.health >self.max_health:
            self.health = self.max_health
    
    def is_alive(self):
        """检查是否存活"""
        return self.health > 0
