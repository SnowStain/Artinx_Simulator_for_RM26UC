#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import random
from copy import deepcopy
from typing import Any, Dict, List


class RulesEngine:
    @staticmethod
    def build_rule_config(raw_rules=None):
        defaults = {
            'game_duration': 420,
            'economy': {
                'initial_gold': 400.0,
            },
            'combat': {
                'disengage_duration': 6.0,
            },
            'collision': {
                'damage_cooldown': 0.5,
                'min_impact_speed': 1.0,
            },
            'robot_profiles': {
                'hero': {
                    'max_health': 150,
                    'initial_health': 150,
                    'max_power': 100,
                    'power_recovery_rate': 1.0,
                    'max_heat': 100,
                    'heat_gain_per_shot': 10,
                    'heat_dissipation_rate': 5,
                    'ammo_type': '42mm',
                    'initial_allowed_ammo_17mm': 0,
                    'initial_allowed_ammo_42mm': 0,
                },
                'engineer': {
                    'max_health': 250,
                    'initial_health': 250,
                    'max_power': 120,
                    'power_recovery_rate': 1.2,
                    'max_heat': 0,
                    'heat_gain_per_shot': 0,
                    'heat_dissipation_rate': 0,
                    'fire_rate_hz': 0.0,
                    'ammo_per_shot': 0,
                    'ammo_type': 'none',
                    'initial_allowed_ammo_17mm': 0,
                    'initial_allowed_ammo_42mm': 0,
                },
                'infantry': {
                    'max_health': 100,
                    'initial_health': 100,
                    'max_power': 60,
                    'power_recovery_rate': 1.5,
                    'max_heat': 60,
                    'heat_gain_per_shot': 6,
                    'heat_dissipation_rate': 3,
                    'ammo_type': '17mm',
                    'initial_allowed_ammo_17mm': 0,
                    'initial_allowed_ammo_42mm': 0,
                },
            },
            'sentry': {
                'default_mode': 'auto',
                'posture_cooldown': 5.0,
                'posture_decay_time': 180.0,
                'modes': {
                    'auto': {
                        'max_health': 400,
                        'initial_health': 400,
                        'max_power': 100,
                        'power_recovery_rate': 2.0,
                        'max_heat': 260,
                        'heat_gain_per_shot': 12,
                        'heat_dissipation_rate': 30,
                        'ammo_type': '17mm',
                        'initial_allowed_ammo_17mm': 300,
                        'initial_allowed_ammo_42mm': 0,
                    },
                    'semi_auto': {
                        'max_health': 200,
                        'initial_health': 200,
                        'max_power': 60,
                        'power_recovery_rate': 1.6,
                        'max_heat': 100,
                        'heat_gain_per_shot': 12,
                        'heat_dissipation_rate': 10,
                        'ammo_type': '17mm',
                        'initial_allowed_ammo_17mm': 200,
                        'initial_allowed_ammo_42mm': 0,
                    },
                },
                'exchange': {
                    'ammo_cost': 10,
                    'interval_sec': 2.0,
                    'remote_ammo_cost': 20,
                    'hp_cost': 20,
                    'remote_hp_cost': 30,
                    'revive_now_cost': 80,
                    'local_17mm_unit': 10,
                    'local_42mm_unit': 1,
                    'remote_17mm_unit': 100,
                    'remote_42mm_unit': 10,
                    'remote_delay': 6.0,
                    'remote_hp_gain_ratio': 0.6,
                    'hp_gain_ratio': 0.6,
                },
            },
            'base': {
                'max_health': 2000,
            },
            'outpost': {
                'max_health': 1500,
            },
            'radar': {
                'range': 260,
                'mark_gain_per_sec': 1.0,
                'mark_decay_per_sec': 0.5,
                'vulnerability_mult': 1.25,
            },
            'shooting': {
                'fire_rate_hz': 8.0,
                'ammo_per_shot': 1,
                'power_per_shot': 6.0,
                'heat_per_shot': 12.0,
                'overheat_lock_duration': 5.0,
                'armor_center_height_m': 0.15,
                'turret_axis_height_m': 0.45,
                'camera_height_m': 0.45,
                'los_sample_step_m': 0.25,
                'los_clearance_m': 0.02,
                'auto_aim_max_distance_m': 8.0,
                'auto_aim_fov_deg': 50.0,
                'auto_aim_track_speed_deg_per_sec': 180.0,
                'motion_thresholds': {
                    'spinning_angular_velocity_deg': 45.0,
                    'translating_target_speed_mps': 0.45,
                },
                'auto_aim_accuracy': {
                    'near_all': 0.30,
                    'mid_fixed': 1.00,
                    'mid_spin': 0.80,
                    'mid_translating_spin': 0.60,
                    'far_fixed': 0.90,
                    'far_spin': 0.40,
                    'far_translating_spin': 0.10,
                },
                'base_hit_probability': 0.88,
                'min_hit_probability': 0.1,
                'range_falloff': 0.65,
                'movement_penalty_factor': 0.04,
                'aim_angle_penalty_deg': 90.0,
            },
            'control_modes': {
                'chassis': {
                    'health_priority': {
                        'min_power_ratio': 0.22,
                        'base_fire_rate_mult': 0.92,
                        'low_hp_ratio': 0.35,
                        'low_hp_fire_rate_mult': 0.78,
                        'power_cost_mult': 0.9,
                    },
                    'power_priority': {
                        'min_power_ratio': 0.08,
                        'base_fire_rate_mult': 1.0,
                        'low_hp_ratio': 0.2,
                        'low_hp_fire_rate_mult': 0.92,
                        'power_cost_mult': 1.05,
                    },
                },
                'gimbal': {
                    'cooling_priority': {
                        'base_fire_rate_mult': 0.9,
                        'soft_heat_ratio': 0.72,
                        'min_fire_rate_ratio': 0.28,
                    },
                    'burst_priority': {
                        'base_fire_rate_mult': 1.15,
                        'soft_heat_ratio': 0.88,
                        'min_fire_rate_ratio': 0.45,
                    },
                },
            },
            'performance_profiles': {
                'hero': {
                    'weapon_modes': {
                        'melee_priority': {
                            '1': {'max_health': 200, 'initial_health': 200, 'max_power': 70, 'max_heat': 140, 'heat_dissipation_rate': 12, 'ammo_type': '42mm'},
                            '2': {'max_health': 225, 'initial_health': 225, 'max_power': 75, 'max_heat': 150, 'heat_dissipation_rate': 14, 'ammo_type': '42mm'},
                            '3': {'max_health': 250, 'initial_health': 250, 'max_power': 80, 'max_heat': 160, 'heat_dissipation_rate': 16, 'ammo_type': '42mm'},
                            '4': {'max_health': 275, 'initial_health': 275, 'max_power': 85, 'max_heat': 170, 'heat_dissipation_rate': 18, 'ammo_type': '42mm'},
                            '5': {'max_health': 300, 'initial_health': 300, 'max_power': 90, 'max_heat': 180, 'heat_dissipation_rate': 20, 'ammo_type': '42mm'},
                            '6': {'max_health': 325, 'initial_health': 325, 'max_power': 95, 'max_heat': 190, 'heat_dissipation_rate': 22, 'ammo_type': '42mm'},
                            '7': {'max_health': 350, 'initial_health': 350, 'max_power': 100, 'max_heat': 200, 'heat_dissipation_rate': 24, 'ammo_type': '42mm'},
                            '8': {'max_health': 375, 'initial_health': 375, 'max_power': 105, 'max_heat': 210, 'heat_dissipation_rate': 26, 'ammo_type': '42mm'},
                            '9': {'max_health': 400, 'initial_health': 400, 'max_power': 110, 'max_heat': 220, 'heat_dissipation_rate': 28, 'ammo_type': '42mm'},
                            '10': {'max_health': 450, 'initial_health': 450, 'max_power': 120, 'max_heat': 240, 'heat_dissipation_rate': 30, 'ammo_type': '42mm'},
                        },
                        'ranged_priority': {
                            '1': {'max_health': 150, 'initial_health': 150, 'max_power': 50, 'max_heat': 100, 'heat_dissipation_rate': 20, 'ammo_type': '42mm'},
                            '2': {'max_health': 165, 'initial_health': 165, 'max_power': 55, 'max_heat': 102, 'heat_dissipation_rate': 23, 'ammo_type': '42mm'},
                            '3': {'max_health': 180, 'initial_health': 180, 'max_power': 60, 'max_heat': 104, 'heat_dissipation_rate': 26, 'ammo_type': '42mm'},
                            '4': {'max_health': 195, 'initial_health': 195, 'max_power': 65, 'max_heat': 106, 'heat_dissipation_rate': 29, 'ammo_type': '42mm'},
                            '5': {'max_health': 210, 'initial_health': 210, 'max_power': 70, 'max_heat': 108, 'heat_dissipation_rate': 32, 'ammo_type': '42mm'},
                            '6': {'max_health': 225, 'initial_health': 225, 'max_power': 75, 'max_heat': 110, 'heat_dissipation_rate': 35, 'ammo_type': '42mm'},
                            '7': {'max_health': 240, 'initial_health': 240, 'max_power': 80, 'max_heat': 115, 'heat_dissipation_rate': 38, 'ammo_type': '42mm'},
                            '8': {'max_health': 255, 'initial_health': 255, 'max_power': 85, 'max_heat': 120, 'heat_dissipation_rate': 41, 'ammo_type': '42mm'},
                            '9': {'max_health': 270, 'initial_health': 270, 'max_power': 90, 'max_heat': 125, 'heat_dissipation_rate': 44, 'ammo_type': '42mm'},
                            '10': {'max_health': 300, 'initial_health': 300, 'max_power': 100, 'max_heat': 130, 'heat_dissipation_rate': 50, 'ammo_type': '42mm'},
                        },
                    },
                },
                'infantry': {
                    'chassis_modes': {
                        'power_priority': {
                            '1': {'max_health': 150, 'initial_health': 150, 'max_power': 60},
                            '2': {'max_health': 175, 'initial_health': 175, 'max_power': 65},
                            '3': {'max_health': 200, 'initial_health': 200, 'max_power': 70},
                            '4': {'max_health': 225, 'initial_health': 225, 'max_power': 75},
                            '5': {'max_health': 250, 'initial_health': 250, 'max_power': 80},
                            '6': {'max_health': 275, 'initial_health': 275, 'max_power': 85},
                            '7': {'max_health': 300, 'initial_health': 300, 'max_power': 90},
                            '8': {'max_health': 325, 'initial_health': 325, 'max_power': 95},
                            '9': {'max_health': 350, 'initial_health': 350, 'max_power': 100},
                            '10': {'max_health': 400, 'initial_health': 400, 'max_power': 100},
                        },
                        'health_priority': {
                            '1': {'max_health': 200, 'initial_health': 200, 'max_power': 45},
                            '2': {'max_health': 225, 'initial_health': 225, 'max_power': 50},
                            '3': {'max_health': 250, 'initial_health': 250, 'max_power': 55},
                            '4': {'max_health': 275, 'initial_health': 275, 'max_power': 60},
                            '5': {'max_health': 300, 'initial_health': 300, 'max_power': 65},
                            '6': {'max_health': 325, 'initial_health': 325, 'max_power': 70},
                            '7': {'max_health': 350, 'initial_health': 350, 'max_power': 75},
                            '8': {'max_health': 375, 'initial_health': 375, 'max_power': 80},
                            '9': {'max_health': 400, 'initial_health': 400, 'max_power': 90},
                            '10': {'max_health': 400, 'initial_health': 400, 'max_power': 100},
                        },
                    },
                    'gimbal_modes': {
                        'burst_priority': {
                            '1': {'max_heat': 170, 'heat_dissipation_rate': 5, 'ammo_type': '17mm'},
                            '2': {'max_heat': 180, 'heat_dissipation_rate': 7, 'ammo_type': '17mm'},
                            '3': {'max_heat': 190, 'heat_dissipation_rate': 9, 'ammo_type': '17mm'},
                            '4': {'max_heat': 200, 'heat_dissipation_rate': 11, 'ammo_type': '17mm'},
                            '5': {'max_heat': 210, 'heat_dissipation_rate': 12, 'ammo_type': '17mm'},
                            '6': {'max_heat': 220, 'heat_dissipation_rate': 13, 'ammo_type': '17mm'},
                            '7': {'max_heat': 230, 'heat_dissipation_rate': 14, 'ammo_type': '17mm'},
                            '8': {'max_heat': 240, 'heat_dissipation_rate': 16, 'ammo_type': '17mm'},
                            '9': {'max_heat': 250, 'heat_dissipation_rate': 18, 'ammo_type': '17mm'},
                            '10': {'max_heat': 260, 'heat_dissipation_rate': 20, 'ammo_type': '17mm'},
                        },
                        'cooling_priority': {
                            '1': {'max_heat': 40, 'heat_dissipation_rate': 12, 'ammo_type': '17mm'},
                            '2': {'max_heat': 48, 'heat_dissipation_rate': 14, 'ammo_type': '17mm'},
                            '3': {'max_heat': 56, 'heat_dissipation_rate': 16, 'ammo_type': '17mm'},
                            '4': {'max_heat': 64, 'heat_dissipation_rate': 18, 'ammo_type': '17mm'},
                            '5': {'max_heat': 72, 'heat_dissipation_rate': 20, 'ammo_type': '17mm'},
                            '6': {'max_heat': 80, 'heat_dissipation_rate': 22, 'ammo_type': '17mm'},
                            '7': {'max_heat': 88, 'heat_dissipation_rate': 24, 'ammo_type': '17mm'},
                            '8': {'max_heat': 96, 'heat_dissipation_rate': 26, 'ammo_type': '17mm'},
                            '9': {'max_heat': 114, 'heat_dissipation_rate': 28, 'ammo_type': '17mm'},
                            '10': {'max_heat': 120, 'heat_dissipation_rate': 30, 'ammo_type': '17mm'},
                        },
                    },
                },
            },
            'mining': {
                'mine_duration_min_sec': 10.0,
                'mine_duration_max_sec': 15.0,
                'exchange_duration_min_sec': 10.0,
                'exchange_duration_max_sec': 15.0,
                'minerals_per_trip': 1,
                'gold_per_mineral': 120.0,
            },
            'energy_mechanism': {
                'activation_distance_min_m': 4.0,
                'activation_distance_max_m': 7.0,
                'activation_hold_sec': 10.0,
                'front_angle_deg': 55.0,
                'buff_duration_sec': 45.0,
                'damage_dealt_mult': 1.15,
                'cooling_mult': 1.2,
                'power_recovery_mult': 1.15,
                'allowed_role_keys': ['engineer', 'infantry'],
            },
            'ammo_purchase': {
                'purchase_interval_sec': 2.0,
                '17mm_batch': 20,
                '42mm_batch': 1,
                '17mm_cost': 12.0,
                '42mm_cost': 20.0,
                'opening_targets': {
                    'hero_42mm': 4,
                    'infantry_17mm': 40,
                },
            },
            'supply': {
                    'ammo_gain': 100,
                    'ammo_interval': 60.0,
                    'heal_ratio_per_sec': 0.10,
                    'late_heal_ratio_per_sec': 0.25,
                'late_heal_start_time': 240.0,
            },
                'buff_zones': {
                    'buff_base': {'damage_taken_mult': 0.5, 'clear_weak': True, 'team_locked': True, 'allowed_entity_types': ['robot']},
                    'buff_central_highland': {'damage_taken_mult': 0.75, 'allowed_role_keys': ['hero', 'infantry', 'sentry'], 'exclusive_control': True},
                    'buff_trapezoid_highland': {'damage_taken_mult': 0.5, 'team_locked': True, 'allowed_entity_types': ['robot']},
                    'buff_outpost': {
                        'damage_taken_mult': 0.75,
                        'clear_weak': True,
                        'team_locked': True,
                        'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'],
                        'require_owner_outpost_alive': True,
                        'allow_enemy_capture_after_outpost_destroyed_sec': 300.0,
                        'enemy_allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'],
                    },
                    'buff_assembly': {'invincible': True, 'engineer_only': True, 'max_duration_sec': 180.0},
                    'buff_terrain_highland_red_start': {'pair_role': 'start', 'pair_key': 'terrain_highland_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 5.0},
                    'buff_terrain_highland_red_end': {'pair_role': 'end', 'pair_key': 'terrain_highland_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 5.0, 'timed_effects': {'terrain_highland_defense': 30.0}},
                    'buff_terrain_highland_blue_start': {'pair_role': 'start', 'pair_key': 'terrain_highland_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 5.0},
                    'buff_terrain_highland_blue_end': {'pair_role': 'end', 'pair_key': 'terrain_highland_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 5.0, 'timed_effects': {'terrain_highland_defense': 30.0}},
                    'buff_terrain_road_red_start': {'pair_role': 'start', 'pair_key': 'terrain_road_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0},
                    'buff_terrain_road_red_end': {'pair_role': 'end', 'pair_key': 'terrain_road_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0, 'timed_effects': {'terrain_road_cooling': 5.0}, 'cooldown_key': 'terrain_road_lockout', 'cooldown_duration_sec': 15.0},
                    'buff_terrain_road_blue_start': {'pair_role': 'start', 'pair_key': 'terrain_road_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0},
                    'buff_terrain_road_blue_end': {'pair_role': 'end', 'pair_key': 'terrain_road_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0, 'timed_effects': {'terrain_road_cooling': 5.0}, 'cooldown_key': 'terrain_road_lockout', 'cooldown_duration_sec': 15.0},
                    'buff_terrain_fly_slope_red_start': {'pair_role': 'start', 'pair_key': 'terrain_fly_slope_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0},
                    'buff_terrain_fly_slope_red_end': {'pair_role': 'end', 'pair_key': 'terrain_fly_slope_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0, 'timed_effects': {'terrain_fly_slope_defense': 30.0}},
                    'buff_terrain_fly_slope_blue_start': {'pair_role': 'start', 'pair_key': 'terrain_fly_slope_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0},
                    'buff_terrain_fly_slope_blue_end': {'pair_role': 'end', 'pair_key': 'terrain_fly_slope_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 3.0, 'timed_effects': {'terrain_fly_slope_defense': 30.0}},
                    'buff_terrain_slope_red_start': {'pair_role': 'start', 'pair_key': 'terrain_slope_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 10.0},
                    'buff_terrain_slope_red_end': {'pair_role': 'end', 'pair_key': 'terrain_slope_red', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 10.0, 'timed_effects': {'terrain_slope_defense': 10.0, 'terrain_slope_cooling': 120.0}},
                    'buff_terrain_slope_blue_start': {'pair_role': 'start', 'pair_key': 'terrain_slope_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 10.0},
                    'buff_terrain_slope_blue_end': {'pair_role': 'end', 'pair_key': 'terrain_slope_blue', 'team_locked': True, 'allowed_role_keys': ['hero', 'engineer', 'infantry', 'sentry'], 'sequence_timeout_sec': 10.0, 'timed_effects': {'terrain_slope_defense': 10.0, 'terrain_slope_cooling': 120.0}},
                    'buff_supply': {'acts_as_supply': True, 'team_locked': True, 'allowed_entity_types': ['robot'], 'engineer_invincible': True},
                    'buff_fort': {
                        'acts_as_fort': True,
                        'team_locked': True,
                        'allowed_role_keys': ['infantry', 'sentry'],
                        'require_owner_outpost_destroyed': True,
                        'allow_enemy_capture_after_outpost_destroyed_sec': 180.0,
                        'enemy_allowed_role_keys': ['infantry', 'sentry'],
                    },
                },
            'fort': {
                'damage_taken_mult': 0.85,
                'hit_probability_mult': 1.1,
                'cooling_mult': 1.2,
            },
            'terrain_cross': {
                'duration': 15.0,
                'min_hold_time': 1.0,
                'completion_ratio': 0.55,
                'damage_taken_mult': 0.9,
                'damage_dealt_mult': 1.1,
                'hit_probability_mult': 1.08,
                'cooling_mult': 1.15,
            },
            'terrain_access': {
                'undulating_road': {'allowed_role_keys': []},
            },
            'respawn': {
                'robot_delay': 10.0,
                'sentry_delay': 15.0,
                'invincible_duration': 3.0,
                'weaken_duration': 6.0,
                'weaken_damage_taken_mult': 1.15,
                'weaken_damage_dealt_mult': 0.7,
            },
            'health': {
                'robot': {'max_health': 100, 'initial_health': 100},
                'sentry': {'max_health': 400, 'initial_health': 400},
                'uav': {'max_health': 50, 'initial_health': 50},
                'outpost': {'max_health': 1500, 'initial_health': 1500},
                'base': {'max_health': 2000, 'initial_health': 2000},
                'dart': {'max_health': 10, 'initial_health': 10},
                'radar': {'max_health': 80, 'initial_health': 80},
            },
            'damage': {
                'robot': {'bullet_17mm': 20, 'bullet_42mm': 200, 'dart': 200, 'collision': 2},
                'sentry': {'bullet_17mm': 20, 'bullet_42mm': 200, 'dart': 200, 'collision': 2},
                'uav': {'bullet_17mm': 20, 'bullet_42mm': 200, 'dart': 200, 'collision': 2},
                'outpost': {'bullet_17mm': 20, 'bullet_42mm': 200, 'dart': 750, 'collision': 0},
                'base': {
                    'bullet_17mm': 20,
                    'bullet_17mm_front_upper': 5,
                    'bullet_42mm': 200,
                    'dart': 625,
                    'dart_fixed_target': 200,
                    'dart_random_fixed_target': 300,
                    'dart_terminal_moving_target': 1000,
                    'collision': 0,
                },
                'dart': {'bullet_17mm': 0, 'bullet_42mm': 0, 'dart': 0, 'collision': 0},
                'radar': {'bullet_17mm': 20, 'bullet_42mm': 200, 'dart': 200, 'collision': 2},
            },
        }

        def merge_dict(base, override):
            merged = deepcopy(base)
            if not isinstance(override, dict):
                return merged
            for key, value in override.items():
                if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key] = merge_dict(merged[key], value)
                else:
                    merged[key] = deepcopy(value)
            return merged

        return merge_dict(defaults, raw_rules or {})

    def __init__(self, config):
        self.config = config
        self.rules = self.build_rule_config(config.get('rules', {}))
        self.config['rules'] = self.rules
        self.damage_system = self.load_damage_system()
        self.health_system = self.load_health_system()
        self.game_over = False
        self.winner = None
        self.game_engine: Any = None
        self.stage = 'running'
        self.initial_gold = float(self.rules['economy'].get('initial_gold', 400.0))
        self.team_gold = {'red': self.initial_gold, 'blue': self.initial_gold}
        self.team_minerals = {'red': 0, 'blue': 0}
        self.posture_effects = {
            'mobile': {
                'power_mult': 1.5,
                'cool_mult': 1.0 / 3.0,
                'damage_mult': 1.25,
                'decay': {'power_mult': 1.2},
            },
            'attack': {
                'power_mult': 0.5,
                'cool_mult': 3.0,
                'damage_mult': 1.25,
                'decay': {'cool_mult': 2.0},
            },
            'defense': {
                'power_mult': 0.5,
                'cool_mult': 1.0 / 3.0,
                'damage_mult': 0.5,
                'decay': {'damage_mult': 0.75},
            },
        }
        self.radar_marks: Dict[str, float] = {}
        self.energy_activation_progress = {}
        self.occupied_facilities = {
            'red': {'base': [], 'outpost': [], 'fly_slope': [], 'undulating_road': [], 'rugged_road': [], 'first_step': [], 'dog_hole': [], 'second_step': [], 'supply': [], 'fort': [], 'energy_mechanism': [], 'mining_area': [], 'mineral_exchange': []},
            'blue': {'base': [], 'outpost': [], 'fly_slope': [], 'undulating_road': [], 'rugged_road': [], 'first_step': [], 'dog_hole': [], 'second_step': [], 'supply': [], 'fort': [], 'energy_mechanism': [], 'mining_area': [], 'mineral_exchange': []},
        }
        self.terrain_cross_types = {'fly_slope', 'undulating_road', 'first_step', 'second_step', 'dog_hole'}
        self.auto_aim_max_distance = self._meters_to_world_units(self.rules['shooting']['auto_aim_max_distance_m'])
        self.collision_damage_cooldowns = {}
        self.game_time = 0.0

    def load_damage_system(self):
        return deepcopy(self.rules['damage'])

    def load_health_system(self):
        return deepcopy(self.rules['health'])

    def get_current_cooling_rate(self, entity):
        base_rate = float(getattr(entity, 'heat_dissipation_rate', 0.0))
        base_rate *= float(getattr(entity, 'dynamic_cooling_mult', 1.0))
        if entity.type != 'sentry':
            return base_rate

        posture_effect = self._resolve_posture_effect(entity)
        cooling_mult = posture_effect['cool_mult']
        if getattr(entity, 'fort_buff_active', False):
            cooling_mult *= self.rules['fort']['cooling_mult']
        if getattr(entity, 'terrain_buff_timer', 0.0) > 0:
            cooling_mult *= self.rules['terrain_cross']['cooling_mult']
        return base_rate * cooling_mult

    def get_entity_rule_snapshot(self, entity):
        shooting = self.rules['shooting']
        control_modes = self.rules['control_modes']
        chassis_mode = getattr(entity, 'chassis_mode', 'health_priority')
        gimbal_mode = getattr(entity, 'gimbal_mode', 'cooling_priority')
        return {
            'fire_rate_hz': float(getattr(entity, 'fire_rate_hz', shooting['fire_rate_hz'])),
            'effective_fire_rate_hz': float(self.get_effective_fire_rate_hz(entity)),
            'ammo_per_shot': int(getattr(entity, 'ammo_per_shot', shooting['ammo_per_shot'])),
            'power_per_shot': float(self.get_effective_power_per_shot(entity)),
            'heat_per_shot': float(getattr(entity, 'heat_gain_per_shot', shooting['heat_per_shot'])),
            'overheat_lock_duration': float(shooting['overheat_lock_duration']),
            'armor_center_height_m': float(shooting['armor_center_height_m']),
            'turret_axis_height_m': float(shooting.get('turret_axis_height_m', shooting.get('camera_height_m', 0.45))),
            'camera_height_m': float(shooting['camera_height_m']),
            'auto_aim_max_distance_m': float(shooting['auto_aim_max_distance_m']),
            'auto_aim_max_distance_world': float(self.auto_aim_max_distance),
            'auto_aim_fov_deg': float(shooting['auto_aim_fov_deg']),
            'auto_aim_track_speed_deg_per_sec': float(shooting.get('auto_aim_track_speed_deg_per_sec', 180.0)),
            'current_cooling_rate': float(self.get_current_cooling_rate(entity)),
            'chassis_mode': chassis_mode,
            'gimbal_mode': gimbal_mode,
            'chassis_profile': dict(control_modes['chassis'].get(chassis_mode, {})),
            'gimbal_profile': dict(control_modes['gimbal'].get(gimbal_mode, {})),
        }

    def _chassis_mode_profile(self, entity):
        mode = getattr(entity, 'chassis_mode', 'health_priority')
        profiles = self.rules['control_modes']['chassis']
        return profiles.get(mode, profiles['health_priority'])

    def _gimbal_mode_profile(self, entity):
        mode = getattr(entity, 'gimbal_mode', 'cooling_priority')
        profiles = self.rules['control_modes']['gimbal']
        return profiles.get(mode, profiles['cooling_priority'])

    def get_effective_power_per_shot(self, entity):
        base_cost = float(getattr(entity, 'power_per_shot', self.rules['shooting'].get('power_per_shot', 0.0)))
        chassis_profile = self._chassis_mode_profile(entity)
        return base_cost * float(chassis_profile.get('power_cost_mult', 1.0))

    def get_effective_fire_rate_hz(self, entity):
        base_rate = float(getattr(entity, 'fire_rate_hz', self.rules['shooting']['fire_rate_hz']))
        chassis_profile = self._chassis_mode_profile(entity)
        gimbal_profile = self._gimbal_mode_profile(entity)
        fire_rate = base_rate
        fire_rate *= float(chassis_profile.get('base_fire_rate_mult', 1.0))
        fire_rate *= float(gimbal_profile.get('base_fire_rate_mult', 1.0))

        max_power = max(float(getattr(entity, 'max_power', 0.0)), 1e-6)
        power_ratio = float(getattr(entity, 'power', 0.0)) / max_power
        if power_ratio < float(chassis_profile.get('min_power_ratio', 0.0)):
            return 0.0

        max_health = max(float(getattr(entity, 'max_health', 0.0)), 1e-6)
        health_ratio = float(getattr(entity, 'health', 0.0)) / max_health
        if health_ratio < float(chassis_profile.get('low_hp_ratio', 0.0)):
            fire_rate *= float(chassis_profile.get('low_hp_fire_rate_mult', 1.0))

        max_heat = max(float(getattr(entity, 'max_heat', 0.0)), 1e-6)
        heat_ratio = float(getattr(entity, 'heat', 0.0)) / max_heat
        soft_heat_ratio = float(gimbal_profile.get('soft_heat_ratio', 1.0))
        if heat_ratio >= soft_heat_ratio:
            progress = min(1.0, max(0.0, (heat_ratio - soft_heat_ratio) / max(1.0 - soft_heat_ratio, 1e-6)))
            min_fire_rate_ratio = float(gimbal_profile.get('min_fire_rate_ratio', 0.25))
            fire_rate *= max(min_fire_rate_ratio, 1.0 - progress * (1.0 - min_fire_rate_ratio))

        return max(0.0, fire_rate)

    def _map_manager(self):
        if self.game_engine is None:
            return None
        return getattr(self.game_engine, 'map_manager', None)

    def _entity_ground_height_m(self, entity):
        map_manager = self._map_manager()
        if map_manager is None:
            return 0.0
        return float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))

    def _shooter_view_height_m(self, shooter):
        shooting = self.rules['shooting']
        view_offset = float(shooting.get('turret_axis_height_m', shooting.get('camera_height_m', 0.45)))
        return self._entity_ground_height_m(shooter) + view_offset

    def _target_armor_height_m(self, target):
        return self._entity_ground_height_m(target) + float(self.rules['shooting'].get('armor_center_height_m', 0.15))

    def _normalize_angle_diff(self, angle_diff):
        while angle_diff > 180:
            angle_diff -= 360
        while angle_diff < -180:
            angle_diff += 360
        return angle_diff

    def _desired_turret_angle(self, shooter, target):
        dx = target.position['x'] - shooter.position['x']
        dy = target.position['y'] - shooter.position['y']
        return math.degrees(math.atan2(dy, dx))

    def has_line_of_sight(self, shooter, target):
        map_manager = self._map_manager()
        if map_manager is None:
            return True

        start_x = float(shooter.position['x'])
        start_y = float(shooter.position['y'])
        end_x = float(target.position['x'])
        end_y = float(target.position['y'])
        distance = math.hypot(end_x - start_x, end_y - start_y)
        if distance <= 1e-6:
            return True

        shooter_height = self._shooter_view_height_m(shooter)
        target_height = self._target_armor_height_m(target)
        step = max(map_manager.meters_to_world_units(self.rules['shooting'].get('los_sample_step_m', 0.25)), 1.0)
        steps = max(2, int(distance / step) + 1)
        clearance = float(self.rules['shooting'].get('los_clearance_m', 0.02))
        endpoint_guard = min(0.12, 0.5 / max(steps, 1))

        for index in range(1, steps):
            progress = index / steps
            if progress <= endpoint_guard or progress >= 1.0 - endpoint_guard:
                continue
            sample_x = start_x + (end_x - start_x) * progress
            sample_y = start_y + (end_y - start_y) * progress
            sample = map_manager.sample_raster_layers(sample_x, sample_y)
            obstacle_height = max(float(sample.get('height_m', 0.0)), float(sample.get('vision_block_height_m', 0.0)))
            sight_height = shooter_height + (target_height - shooter_height) * progress
            if obstacle_height >= sight_height - clearance:
                return False
        return True

    def evaluate_auto_aim_target(self, shooter, target, distance=None, require_fov=True):
        if target is None or not target.is_alive() or target.team == shooter.team:
            return {
                'valid': False,
                'distance': float('inf'),
                'in_range': False,
                'line_of_sight': False,
                'angle_diff': 180.0,
                'within_fov': False,
                'can_track': False,
                'can_auto_aim': False,
            }

        if distance is None:
            distance = math.hypot(target.position['x'] - shooter.position['x'], target.position['y'] - shooter.position['y'])
        max_distance = self.get_range(shooter.type)
        in_range = distance <= max_distance
        line_of_sight = in_range and self.has_line_of_sight(shooter, target)
        desired_angle = self._desired_turret_angle(shooter, target)
        current_angle = getattr(shooter, 'turret_angle', shooter.angle)
        angle_diff = self._normalize_angle_diff(desired_angle - current_angle)
        half_fov = float(self.rules['shooting'].get('auto_aim_fov_deg', 50.0)) / 2.0
        within_fov = abs(angle_diff) <= half_fov
        can_track = in_range and line_of_sight
        can_auto_aim = can_track and (within_fov if require_fov else True)
        return {
            'valid': True,
            'distance': distance,
            'in_range': in_range,
            'line_of_sight': line_of_sight,
            'desired_angle': desired_angle,
            'angle_diff': angle_diff,
            'within_fov': within_fov,
            'can_track': can_track,
            'can_auto_aim': can_auto_aim,
        }

    def can_auto_aim_target(self, shooter, target, distance=None):
        return self.evaluate_auto_aim_target(shooter, target, distance=distance, require_fov=True).get('can_auto_aim', False)

    def can_track_target(self, shooter, target, distance=None):
        return self.evaluate_auto_aim_target(shooter, target, distance=distance, require_fov=False).get('can_track', False)

    def update(self, entities, map_manager=None, dt=0.02, game_time=0.0, game_duration=None):
        self.dt = dt
        self.game_time = game_time
        self._latest_entities = list(entities)
        for entity in entities:
            if entity.type in {'robot', 'sentry'}:
                entity.auto_aim_limit = self.auto_aim_max_distance
        self._update_entity_timers(entities, dt)
        self._update_gold(entities, dt)
        self._update_sentry_posture_and_heat(entities, dt)

        if map_manager is not None:
            self._update_occupied_facilities(entities, map_manager)
            self._update_facility_effects(entities, map_manager, dt)
            self._update_energy_mechanism_control(entities, map_manager, dt)
            self._update_radar_marks(entities, map_manager)

        self.check_damage(entities)
        self.check_health(entities)

        if game_duration and game_time >= game_duration:
            self.stage = 'ended'
            self.game_over = True
            self.winner = self._winner_by_base_health(entities)

    def _meters_to_world_units(self, meters):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 0.0) or 0.0)
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 0.0) or 0.0)
        map_width = float(self.config.get('map', {}).get('width', 0.0) or 0.0)
        map_height = float(self.config.get('map', {}).get('height', 0.0) or 0.0)
        if field_length_m > 0 and field_width_m > 0 and map_width > 0 and map_height > 0:
            pixels_per_meter_x = map_width / field_length_m
            pixels_per_meter_y = map_height / field_width_m
            return meters * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)

        unit = str(self.config.get('map', {}).get('unit', 'cm')).lower()
        if unit in {'px', 'pixel', 'pixels'}:
            return meters
        if unit == 'mm':
            return meters * 1000.0
        if unit == 'm':
            return meters
        return meters * 100.0

    def _winner_by_base_health(self, entities):
        red_base = self._find_entity(entities, 'red', 'base')
        blue_base = self._find_entity(entities, 'blue', 'base')
        red_hp = red_base.health if red_base else 0
        blue_hp = blue_base.health if blue_base else 0
        if red_hp > blue_hp:
            return 'red'
        if blue_hp > red_hp:
            return 'blue'
        return 'draw'

    def _find_entity(self, entities, team, entity_type):
        for entity in entities:
            if entity.team == team and entity.type == entity_type:
                return entity
        return None

    def _update_entity_timers(self, entities, dt):
        for entity in entities:
            self._expire_buff_path_progress(entity)
            entity.shot_cooldown = max(0.0, getattr(entity, 'shot_cooldown', 0.0) - dt)
            entity.overheat_lock_timer = max(0.0, getattr(entity, 'overheat_lock_timer', 0.0) - dt)
            entity.invincible_timer = max(0.0, getattr(entity, 'invincible_timer', 0.0) - dt)
            entity.weak_timer = max(0.0, getattr(entity, 'weak_timer', 0.0) - dt)
            entity.terrain_buff_timer = max(0.0, getattr(entity, 'terrain_buff_timer', 0.0) - dt)
            entity.supply_cooldown = max(0.0, getattr(entity, 'supply_cooldown', 0.0) - dt)
            entity.exchange_cooldown = max(0.0, getattr(entity, 'exchange_cooldown', 0.0) - dt)
            entity.respawn_recovery_timer = max(0.0, getattr(entity, 'respawn_recovery_timer', 0.0) - dt)
            entity.role_purchase_cooldown = max(0.0, getattr(entity, 'role_purchase_cooldown', 0.0) - dt)
            entity.timed_buffs = {
                key: max(0.0, float(value) - dt)
                for key, value in dict(getattr(entity, 'timed_buffs', {})).items()
                if max(0.0, float(value) - dt) > 0.0
            }
            entity.buff_cooldowns = {
                key: max(0.0, float(value) - dt)
                for key, value in dict(getattr(entity, 'buff_cooldowns', {})).items()
                if max(0.0, float(value) - dt) > 0.0
            }

            self._process_pending_rule_events(entity)

            if entity.state in {'respawning', 'destroyed'} and getattr(entity, 'respawn_timer', 0.0) > 0:
                entity.respawn_timer = max(0.0, entity.respawn_timer - dt)
                if entity.respawn_timer <= 0:
                    self._respawn_entity(entity)

            if entity.state not in {'respawning', 'destroyed'}:
                if entity.invincible_timer > 0:
                    entity.state = 'invincible'
                elif entity.weak_timer > 0:
                    entity.state = 'weak'
                elif entity.state in {'invincible', 'weak'}:
                    entity.state = 'idle'

    def _update_gold(self, entities, dt):
        for entity in entities:
            if entity.type in {'robot', 'sentry'}:
                entity.gold = self.team_gold[entity.team]

    def _primary_ammo_key(self, entity):
        ammo_type = getattr(entity, 'ammo_type', None)
        if ammo_type == '42mm':
            return 'allowed_ammo_42mm'
        if ammo_type == '17mm':
            return 'allowed_ammo_17mm'
        return None

    def _sync_legacy_ammo(self, entity):
        ammo_key = self._primary_ammo_key(entity)
        entity.ammo = int(getattr(entity, ammo_key, 0)) if ammo_key else 0

    def _available_ammo(self, entity):
        ammo_key = self._primary_ammo_key(entity)
        if ammo_key is None:
            return 0
        return int(getattr(entity, ammo_key, 0))

    def _add_allowed_ammo(self, entity, amount, ammo_type=None):
        ammo_kind = ammo_type or getattr(entity, 'ammo_type', None)
        if ammo_kind == '42mm':
            entity.allowed_ammo_42mm = max(0, int(getattr(entity, 'allowed_ammo_42mm', 0) + amount))
        elif ammo_kind == '17mm':
            entity.allowed_ammo_17mm = max(0, int(getattr(entity, 'allowed_ammo_17mm', 0) + amount))
        self._sync_legacy_ammo(entity)

    def _consume_allowed_ammo(self, entity, amount):
        ammo_key = self._primary_ammo_key(entity)
        if ammo_key is None:
            return 0
        current = int(getattr(entity, ammo_key, 0))
        consumed = min(current, int(amount))
        setattr(entity, ammo_key, current - consumed)
        self._sync_legacy_ammo(entity)
        return consumed

    def is_out_of_combat(self, entity):
        disengage_duration = float(self.rules.get('combat', {}).get('disengage_duration', 6.0))
        return (self.game_time - float(getattr(entity, 'last_combat_time', -1e9))) >= disengage_duration

    def _mark_in_combat(self, entity):
        entity.last_combat_time = self.game_time

    def _queue_pending_rule_event(self, entity, event_type, delay, payload):
        entity.pending_rule_events.append({
            'type': event_type,
            'time_left': float(delay),
            'payload': deepcopy(payload),
        })

    def _process_pending_rule_events(self, entity):
        events = []
        for event in list(getattr(entity, 'pending_rule_events', [])):
            event['time_left'] = max(0.0, float(event.get('time_left', 0.0)) - self.dt)
            if event['time_left'] > 0.0:
                events.append(event)
                continue
            payload = event.get('payload', {})
            if event.get('type') == 'remote_ammo':
                self._add_allowed_ammo(entity, int(payload.get('amount', 0)), payload.get('ammo_type'))
            elif event.get('type') == 'remote_hp':
                entity.heal(float(payload.get('amount', 0.0)))
        entity.pending_rule_events = events

    def _supply_claimable_ammo(self, entity):
        if self._primary_ammo_key(entity) is None:
            return 0
        interval = float(self.rules['supply'].get('ammo_interval', 60.0))
        ammo_gain = int(self.rules['supply'].get('ammo_gain', 100))
        if interval <= 0:
            return 0
        generated = int(self.game_time // interval) * ammo_gain
        claimed = int(getattr(entity, 'supply_ammo_claimed', 0))
        return max(0, generated - claimed)

    def _claim_supply_ammo(self, entity):
        claimable = self._supply_claimable_ammo(entity)
        if claimable <= 0:
            return 0
        self._add_allowed_ammo(entity, claimable)
        entity.supply_ammo_claimed = int(getattr(entity, 'supply_ammo_claimed', 0)) + claimable
        return claimable

    def _mining_duration(self, exchange=False):
        mining_rules = self.rules.get('mining', {})
        if exchange:
            return random.uniform(
                float(mining_rules.get('exchange_duration_min_sec', 10.0)),
                float(mining_rules.get('exchange_duration_max_sec', 15.0)),
            )
        return random.uniform(
            float(mining_rules.get('mine_duration_min_sec', 10.0)),
            float(mining_rules.get('mine_duration_max_sec', 15.0)),
        )

    def _reset_dynamic_effects(self, entity):
        entity.dynamic_damage_taken_mult = 1.0
        entity.dynamic_damage_dealt_mult = 1.0
        entity.dynamic_cooling_mult = 1.0
        entity.dynamic_power_recovery_mult = 1.0
        entity.dynamic_invincible = False
        entity.active_buff_labels = []
        self._expire_buff_path_progress(entity)

        pending_label_map = {
            'terrain_highland_red': '红方高地跨越起点已触发',
            'terrain_highland_blue': '蓝方高地跨越起点已触发',
            'terrain_road_red': '红方公路跨越起点已触发',
            'terrain_road_blue': '蓝方公路跨越起点已触发',
            'terrain_fly_slope_red': '红方飞坡跨越起点已触发',
            'terrain_fly_slope_blue': '蓝方飞坡跨越起点已触发',
            'terrain_slope_red': '红方陡道跨越起点已触发',
            'terrain_slope_blue': '蓝方陡道跨越起点已触发',
        }
        for pair_key in dict(getattr(entity, 'buff_path_progress', {})).keys():
            pending_label = pending_label_map.get(pair_key)
            if pending_label and pending_label not in entity.active_buff_labels:
                entity.active_buff_labels.append(pending_label)

        timed_buffs = getattr(entity, 'timed_buffs', {})
        if timed_buffs.get('terrain_highland_defense', 0.0) > 0:
            entity.dynamic_damage_taken_mult *= 0.75
            entity.active_buff_labels.append('高地地形增益')
        if timed_buffs.get('terrain_road_cooling', 0.0) > 0:
            entity.dynamic_cooling_mult *= 1.25
            entity.active_buff_labels.append('公路冷却增益')
        if timed_buffs.get('terrain_fly_slope_defense', 0.0) > 0:
            entity.dynamic_damage_taken_mult *= 0.75
            entity.active_buff_labels.append('飞坡防御增益')
        if timed_buffs.get('terrain_slope_defense', 0.0) > 0:
            entity.dynamic_damage_taken_mult *= 0.5
            entity.active_buff_labels.append('陡道防御增益')
        if timed_buffs.get('terrain_slope_cooling', 0.0) > 0:
            entity.dynamic_cooling_mult *= 2.0
            entity.active_buff_labels.append('陡道冷却增益')
        if timed_buffs.get('energy_mechanism_boost', 0.0) > 0:
            energy_rules = self.rules.get('energy_mechanism', {})
            entity.dynamic_damage_dealt_mult *= float(energy_rules.get('damage_dealt_mult', 1.15))
            entity.dynamic_cooling_mult *= float(energy_rules.get('cooling_mult', 1.2))
            entity.dynamic_power_recovery_mult *= float(energy_rules.get('power_recovery_mult', 1.15))
            entity.active_buff_labels.append('中央能量机关增益')

    def _clear_negative_states(self, entity):
        entity.weak_timer = 0.0
        if entity.state == 'weak':
            entity.state = 'idle'

    def _entity_role_key(self, entity):
        if entity.type == 'sentry':
            return 'sentry'
        role_map = {
            '英雄': 'hero',
            '工程': 'engineer',
            '步兵': 'infantry',
        }
        return role_map.get(getattr(entity, 'robot_type', ''), entity.type)

    def _paired_buff_timeout_by_key(self, pair_key):
        for buff_rules in self.rules.get('buff_zones', {}).values():
            if buff_rules.get('pair_role') == 'start' and buff_rules.get('pair_key') == pair_key:
                return float(buff_rules.get('sequence_timeout_sec', 0.0))
        return 0.0

    def _expire_buff_path_progress(self, entity):
        progress = dict(getattr(entity, 'buff_path_progress', {}))
        changed = False
        for pair_key, state in list(progress.items()):
            timeout = self._paired_buff_timeout_by_key(pair_key)
            if timeout > 0.0 and self.game_time - float(state.get('time', 0.0)) > timeout:
                progress.pop(pair_key, None)
                changed = True
        if changed:
            entity.buff_path_progress = progress

    def _terrain_access_allowed(self, entity, facility):
        facility_type = facility.get('type') if isinstance(facility, dict) else str(facility)
        access_rules = dict(self.rules.get('terrain_access', {}).get(facility_type, {}))
        role_key = self._entity_role_key(entity)
        if 'allowed_entity_types' in access_rules:
            allowed_entity_types = set(access_rules.get('allowed_entity_types', []))
            if entity.type not in allowed_entity_types:
                return False
        if 'allowed_role_keys' in access_rules:
            allowed_role_keys = set(access_rules.get('allowed_role_keys', []))
            return role_key in allowed_role_keys
        return True

    def _energy_front_descriptor(self, facility):
        center_x = (float(facility.get('x1', 0)) + float(facility.get('x2', 0))) / 2.0
        center_y = (float(facility.get('y1', 0)) + float(facility.get('y2', 0))) / 2.0
        points = list(facility.get('points', []))
        if len(points) >= 2:
            edge_mid_x = (float(points[0][0]) + float(points[-1][0])) / 2.0
            edge_mid_y = (float(points[0][1]) + float(points[-1][1])) / 2.0
            normal_x = edge_mid_x - center_x
            normal_y = edge_mid_y - center_y
        else:
            normal_x = 0.0
            normal_y = -1.0
        normal_len = math.hypot(normal_x, normal_y)
        if normal_len <= 1e-6:
            normal_x, normal_y = 0.0, -1.0
        else:
            normal_x /= normal_len
            normal_y /= normal_len
        return center_x, center_y, normal_x, normal_y

    def _energy_activation_anchor(self, facility):
        center_x, center_y, normal_x, normal_y = self._energy_front_descriptor(facility)
        energy_rules = self.rules.get('energy_mechanism', {})
        anchor_distance_m = (
            float(energy_rules.get('activation_distance_min_m', 4.0))
            + float(energy_rules.get('activation_distance_max_m', 7.0))
        ) * 0.5
        anchor_distance = self._meters_to_world_units(anchor_distance_m)
        return center_x + normal_x * anchor_distance, center_y + normal_y * anchor_distance

    def _is_valid_energy_activator(self, entity, facility):
        if entity.type not in {'robot', 'sentry'} or not entity.is_alive():
            return False
        energy_rules = self.rules.get('energy_mechanism', {})
        allowed_role_keys = set(energy_rules.get('allowed_role_keys', []))
        role_key = self._entity_role_key(entity)
        if allowed_role_keys and role_key not in allowed_role_keys:
            return False
        center_x, center_y, normal_x, normal_y = self._energy_front_descriptor(facility)
        offset_x = float(entity.position['x']) - center_x
        offset_y = float(entity.position['y']) - center_y
        distance = math.hypot(offset_x, offset_y)
        min_distance = self._meters_to_world_units(float(energy_rules.get('activation_distance_min_m', 4.0)))
        max_distance = self._meters_to_world_units(float(energy_rules.get('activation_distance_max_m', 7.0)))
        if distance < min_distance or distance > max_distance:
            return False
        offset_len = max(distance, 1e-6)
        dot = (offset_x / offset_len) * normal_x + (offset_y / offset_len) * normal_y
        min_dot = math.cos(math.radians(float(energy_rules.get('front_angle_deg', 55.0))))
        return dot >= min_dot

    def _grant_team_energy_buff(self, entities, team):
        duration = float(self.rules.get('energy_mechanism', {}).get('buff_duration_sec', 45.0))
        for entity in entities:
            if entity.team != team or entity.type not in {'robot', 'sentry'} or not entity.is_alive():
                continue
            entity.timed_buffs['energy_mechanism_boost'] = max(float(entity.timed_buffs.get('energy_mechanism_boost', 0.0)), duration)

    def _update_energy_mechanism_control(self, entities, map_manager, dt):
        facilities = map_manager.get_facility_regions('energy_mechanism')
        if not facilities:
            return
        hold_sec = float(self.rules.get('energy_mechanism', {}).get('activation_hold_sec', 10.0))
        for facility in facilities:
            facility_id = str(facility.get('id', 'energy_mechanism'))
            progress = self.energy_activation_progress.setdefault(facility_id, {'red': 0.0, 'blue': 0.0})
            active_teams = []
            for team in ['red', 'blue']:
                if any(self._is_valid_energy_activator(entity, facility) for entity in entities if entity.team == team):
                    active_teams.append(team)
            if len(active_teams) != 1:
                progress['red'] = 0.0
                progress['blue'] = 0.0
                continue
            active_team = active_teams[0]
            other_team = 'blue' if active_team == 'red' else 'red'
            progress[other_team] = 0.0
            progress[active_team] = float(progress.get(active_team, 0.0)) + dt
            if progress[active_team] >= hold_sec:
                self._grant_team_energy_buff(entities, active_team)
                self._log(f'{active_team} 方完成中央能量机关激活，获得团队增益', active_team)
                progress[active_team] = 0.0

    def _structure_alive(self, team, entity_type):
        for entity in getattr(self, '_latest_entities', []):
            if entity.team == team and entity.type == entity_type and entity.is_alive():
                return True
        return False

    def _region_has_enemy_occupant(self, region, entity):
        for other in getattr(self, '_latest_entities', []):
            if other.id == entity.id or not other.is_alive() or other.team == entity.team:
                continue
            if other.type not in {'robot', 'sentry'}:
                continue
            if self._region_contains_point(region, other.position['x'], other.position['y']):
                return True
        return False

    def _region_contains_point(self, region, x, y):
        shape = region.get('shape', 'rect')
        if shape == 'rect':
            return region.get('x1', 0) <= x <= region.get('x2', 0) and region.get('y1', 0) <= y <= region.get('y2', 0)
        if shape == 'line':
            x1 = float(region.get('x1', 0))
            y1 = float(region.get('y1', 0))
            x2 = float(region.get('x2', 0))
            y2 = float(region.get('y2', 0))
            dx = x2 - x1
            dy = y2 - y1
            if dx == 0 and dy == 0:
                return math.hypot(x - x1, y - y1) <= float(region.get('thickness', 12))
            t = ((x - x1) * dx + (y - y1) * dy) / max(dx * dx + dy * dy, 1e-6)
            t = max(0.0, min(1.0, t))
            closest_x = x1 + t * dx
            closest_y = y1 + t * dy
            return math.hypot(x - closest_x, y - closest_y) <= float(region.get('thickness', 12))
        points = region.get('points', [])
        if len(points) < 3:
            return False
        inside = False
        previous_x, previous_y = points[-1]
        for current_x, current_y in points:
            denominator = previous_y - current_y
            intersects = False
            if ((current_y > y) != (previous_y > y)) and abs(denominator) > 1e-6:
                x_intersect = current_x + (previous_x - current_x) * (y - current_y) / denominator
                intersects = x < x_intersect
            if intersects:
                inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    def _buff_access_allowed(self, entity, region, buff_rules):
        allowed_entity_types = set(buff_rules.get('allowed_entity_types', []))
        if allowed_entity_types and entity.type not in allowed_entity_types:
            return False

        allowed_role_keys = set(buff_rules.get('allowed_role_keys', []))
        role_key = self._entity_role_key(entity)
        if allowed_role_keys and role_key not in allowed_role_keys:
            return False

        owner_team = region.get('team', 'neutral')
        if buff_rules.get('require_owner_outpost_alive') and owner_team not in {'neutral', None}:
            if owner_team == entity.team and not self._structure_alive(owner_team, 'outpost'):
                return False

        if buff_rules.get('require_owner_outpost_destroyed') and owner_team not in {'neutral', None}:
            if owner_team == entity.team and self._structure_alive(owner_team, 'outpost'):
                return False

        if buff_rules.get('team_locked') and owner_team not in {entity.team, 'neutral'}:
            unlock_time = float(buff_rules.get('allow_enemy_capture_after_outpost_destroyed_sec', 0.0))
            enemy_allowed_roles = set(buff_rules.get('enemy_allowed_role_keys', []))
            if unlock_time <= 0.0 or self.game_time < unlock_time:
                return False
            if self._structure_alive(owner_team, 'outpost'):
                return False
            if enemy_allowed_roles and role_key not in enemy_allowed_roles:
                return False

        if buff_rules.get('exclusive_control') and self._region_has_enemy_occupant(region, entity):
            return False

        return True

    def _handle_paired_buff_region(self, entity, region, buff_rules):
        pair_role = buff_rules.get('pair_role')
        pair_key = buff_rules.get('pair_key')
        if not pair_role or not pair_key:
            return False

        progress = dict(getattr(entity, 'buff_path_progress', {}))
        region_id = region.get('id')
        timeout = float(buff_rules.get('sequence_timeout_sec', 0.0))
        if pair_role == 'start':
            progress = {key: value for key, value in progress.items() if not str(key).startswith('terrain_') or key == pair_key}
            progress[pair_key] = {
                'region_id': region_id,
                'time': float(self.game_time),
            }
            entity.buff_path_progress = progress
            return False

        start_state = progress.get(pair_key)
        if not start_state:
            return False
        if start_state.get('region_id') == region_id:
            return False
        if timeout > 0.0 and float(self.game_time) - float(start_state.get('time', 0.0)) > timeout:
            progress.pop(pair_key, None)
            entity.buff_path_progress = progress
            return False

        progress.pop(pair_key, None)
        entity.buff_path_progress = progress
        return True

    def _handle_mining_zone(self, entity, region, dt):
        if getattr(entity, 'robot_type', '') != '工程' or entity.type != 'robot':
            return
        if getattr(entity, 'carried_minerals', 0) > 0:
            entity.mining_timer = 0.0
            entity.mining_zone_id = None
            entity.mining_target_duration = 0.0
            return
        if entity.mining_zone_id != region.get('id'):
            entity.mining_zone_id = region.get('id')
            entity.mining_timer = 0.0
            entity.mining_target_duration = self._mining_duration(exchange=False)
        entity.mining_timer += dt
        if entity.mining_timer < max(0.1, entity.mining_target_duration):
            return
        entity.carried_minerals += int(self.rules.get('mining', {}).get('minerals_per_trip', 1))
        entity.mining_timer = 0.0
        entity.mining_target_duration = self._mining_duration(exchange=False)
        self.team_minerals[entity.team] = self.team_minerals.get(entity.team, 0) + int(self.rules.get('mining', {}).get('minerals_per_trip', 1))
        self._log(f'{entity.id} 在取矿区完成采矿，当前携带 {entity.carried_minerals} 单位矿物', entity.team)

    def _handle_exchange_zone(self, entity, region, dt):
        if getattr(entity, 'robot_type', '') != '工程' or entity.type != 'robot':
            return
        if getattr(entity, 'carried_minerals', 0) <= 0:
            entity.exchange_timer = 0.0
            entity.exchange_zone_id = None
            entity.exchange_target_duration = 0.0
            return
        if entity.exchange_zone_id != region.get('id'):
            entity.exchange_zone_id = region.get('id')
            entity.exchange_timer = 0.0
            entity.exchange_target_duration = self._mining_duration(exchange=True)
        entity.exchange_timer += dt
        if entity.exchange_timer < max(0.1, entity.exchange_target_duration):
            return
        carried = int(getattr(entity, 'carried_minerals', 0))
        gold_gain = carried * float(self.rules.get('mining', {}).get('gold_per_mineral', 120.0))
        self.team_gold[entity.team] += gold_gain
        entity.gold = self.team_gold[entity.team]
        self.team_minerals[entity.team] = max(0, self.team_minerals.get(entity.team, 0) - carried)
        entity.carried_minerals = 0
        entity.exchange_timer = 0.0
        entity.exchange_target_duration = self._mining_duration(exchange=True)
        self._log(f'{entity.id} 在兑矿区完成兑矿，队伍获得 {gold_gain:.0f} 金币', entity.team)

    def _try_purchase_role_ammo(self, entity):
        if entity.type != 'robot' or getattr(entity, 'robot_type', '') not in {'英雄', '步兵'}:
            return 0
        if getattr(entity, 'role_purchase_cooldown', 0.0) > 0:
            return 0
        purchase_rules = self.rules.get('ammo_purchase', {})
        ammo_type = getattr(entity, 'ammo_type', '17mm')
        if ammo_type == '42mm':
            batch = int(purchase_rules.get('42mm_batch', 1))
            cost = float(purchase_rules.get('42mm_cost', 20.0))
        else:
            batch = int(purchase_rules.get('17mm_batch', 20))
            cost = float(purchase_rules.get('17mm_cost', 12.0))
        if batch <= 0 or self.team_gold.get(entity.team, 0.0) < cost:
            return 0
        self.team_gold[entity.team] -= cost
        entity.gold = self.team_gold[entity.team]
        self._add_allowed_ammo(entity, batch, ammo_type)
        entity.role_purchase_cooldown = float(purchase_rules.get('purchase_interval_sec', 2.0))
        return batch

    def _apply_buff_region(self, entity, region, dt, active_regions=None):
        buff_rules = self.rules.get('buff_zones', {}).get(region.get('type'), {})
        if not buff_rules:
            return
        label_map = {
            'buff_base': '基地增益',
            'buff_outpost': '前哨增益',
            'buff_fort': '堡垒增益点',
            'buff_supply': '补给增益点',
            'buff_assembly': '装配增益点',
            'buff_central_highland': '中央高地',
            'buff_trapezoid_highland': '梯形高地',
            'buff_terrain_highland_red_start': '红方高地跨越起点',
            'buff_terrain_highland_red_end': '红方高地跨越终点',
            'buff_terrain_highland_blue_start': '蓝方高地跨越起点',
            'buff_terrain_highland_blue_end': '蓝方高地跨越终点',
            'buff_terrain_road_red_start': '红方公路跨越起点',
            'buff_terrain_road_red_end': '红方公路跨越终点',
            'buff_terrain_road_blue_start': '蓝方公路跨越起点',
            'buff_terrain_road_blue_end': '蓝方公路跨越终点',
            'buff_terrain_fly_slope_red_start': '红方飞坡跨越起点',
            'buff_terrain_fly_slope_red_end': '红方飞坡跨越终点',
            'buff_terrain_fly_slope_blue_start': '蓝方飞坡跨越起点',
            'buff_terrain_fly_slope_blue_end': '蓝方飞坡跨越终点',
            'buff_terrain_slope_red_start': '红方陡道跨越起点',
            'buff_terrain_slope_red_end': '红方陡道跨越终点',
            'buff_terrain_slope_blue_start': '蓝方陡道跨越起点',
            'buff_terrain_slope_blue_end': '蓝方陡道跨越终点',
        }
        if not self._buff_access_allowed(entity, region, buff_rules):
            return
        if buff_rules.get('pair_role') == 'start':
            blocked_types = set(buff_rules.get('blocked_if_inside_facilities', ['base', 'outpost', 'supply', 'fort']))
            for other_region in active_regions or []:
                if other_region.get('id') == region.get('id'):
                    continue
                if other_region.get('type') in blocked_types and other_region.get('team') in {entity.team, 'neutral'}:
                    return
        if buff_rules.get('engineer_only') and getattr(entity, 'robot_type', '') != '工程':
            return

        label = label_map.get(region.get('type'))
        if label and label not in entity.active_buff_labels:
            entity.active_buff_labels.append(label)

        if buff_rules.get('pair_role'):
            if not self._handle_paired_buff_region(entity, region, buff_rules):
                return

        damage_taken_mult = float(buff_rules.get('damage_taken_mult', 1.0))
        entity.dynamic_damage_taken_mult *= damage_taken_mult

        if buff_rules.get('clear_weak'):
            self._clear_negative_states(entity)

        if buff_rules.get('acts_as_fort'):
            entity.fort_buff_active = True

        if buff_rules.get('acts_as_supply'):
            entity.heal(entity.max_health * float(self.rules['supply'].get('heal_ratio_per_sec', 0.10)) * dt)
            purchased = self._try_purchase_role_ammo(entity)
            if buff_rules.get('engineer_invincible') and getattr(entity, 'robot_type', '') == '工程':
                entity.dynamic_invincible = True
            if purchased > 0:
                self._log(f'{entity.id} 在增益补给点购买 {purchased} 发允许发弹量', entity.team)

        if buff_rules.get('invincible'):
            max_duration = float(buff_rules.get('max_duration_sec', 0.0))
            if max_duration <= 0.0 or getattr(entity, 'assembly_buff_time_used', 0.0) < max_duration:
                entity.dynamic_invincible = True
                entity.assembly_buff_time_used = min(max_duration, getattr(entity, 'assembly_buff_time_used', 0.0) + dt) if max_duration > 0.0 else getattr(entity, 'assembly_buff_time_used', 0.0)

        timed_effects = dict(buff_rules.get('timed_effects', {}))
        cooldown_key = buff_rules.get('cooldown_key')
        if timed_effects:
            if cooldown_key and getattr(entity, 'buff_cooldowns', {}).get(cooldown_key, 0.0) > 0:
                return
            for effect_key, duration in timed_effects.items():
                entity.timed_buffs[effect_key] = max(float(entity.timed_buffs.get(effect_key, 0.0)), float(duration))
            if cooldown_key:
                entity.buff_cooldowns[cooldown_key] = float(buff_rules.get('cooldown_duration_sec', 0.0))

    def _resolve_posture_effect(self, sentry):
        posture = getattr(sentry, 'posture', 'mobile')
        effect = deepcopy(self.posture_effects.get(posture, self.posture_effects['mobile']))
        decay_time = self.rules['sentry'].get('posture_decay_time', 180.0)
        if getattr(sentry, 'posture_active_time', 0.0) >= decay_time:
            for key, value in effect.get('decay', {}).items():
                effect[key] = value
        return effect

    def _update_sentry_posture_and_heat(self, entities, dt):
        for entity in entities:
            if entity.type != 'sentry':
                continue

            entity.posture_cooldown = max(0.0, getattr(entity, 'posture_cooldown', 0.0) - dt)
            entity.posture_active_time = getattr(entity, 'posture_active_time', 0.0) + dt

            posture_effect = self._resolve_posture_effect(entity)
            total_cooling_mult = posture_effect['cool_mult']
            if getattr(entity, 'fort_buff_active', False):
                total_cooling_mult *= self.rules['fort']['cooling_mult']
            if getattr(entity, 'terrain_buff_timer', 0.0) > 0:
                total_cooling_mult *= self.rules['terrain_cross']['cooling_mult']

            base_cooling = entity.heat_dissipation_rate * dt
            desired_cooling = entity.heat_dissipation_rate * total_cooling_mult * dt
            entity.heat = max(0.0, entity.heat - (desired_cooling - base_cooling))

    def _update_occupied_facilities(self, entities, map_manager):
        for team in ['red', 'blue']:
            for facility_type in self.occupied_facilities[team]:
                self.occupied_facilities[team][facility_type] = []

        controllable_types = {'base', 'outpost', 'fly_slope', 'undulating_road', 'rugged_road', 'first_step', 'dog_hole', 'second_step', 'supply', 'fort', 'energy_mechanism', 'mining_area', 'mineral_exchange'}
        for entity in entities:
            if entity.type not in {'robot', 'sentry', 'engineer'} or not entity.is_alive():
                continue

            regions = map_manager.get_regions_at(entity.position['x'], entity.position['y'])
            if not regions:
                continue
            for facility in regions:
                facility_type = facility.get('type')
                facility_id = facility.get('id')
                if facility_type in controllable_types and facility_id not in self.occupied_facilities[entity.team].setdefault(facility_type, []):
                    self.occupied_facilities[entity.team][facility_type].append(facility_id)

    def _update_facility_effects(self, entities, map_manager, dt):
        for entity in entities:
            if entity.type not in {'robot', 'sentry'}:
                continue
            if not entity.is_alive():
                entity.fort_buff_active = False
                entity.traversal_state = None
                continue

            self._reset_dynamic_effects(entity)
            entity.fort_buff_active = False

            regions = map_manager.get_regions_at(entity.position['x'], entity.position['y'])
            facility = regions[0] if regions else None
            if not any(region.get('type') == 'mining_area' for region in regions):
                entity.mining_timer = 0.0
                entity.mining_zone_id = None
            if not any(region.get('type') == 'mineral_exchange' for region in regions):
                entity.exchange_timer = 0.0
                entity.exchange_zone_id = None

            for region in regions:
                region_type = region.get('type')
                if region_type == 'fort' and region.get('team') == entity.team:
                    entity.fort_buff_active = True
                if region_type == 'supply' and region.get('team') == entity.team:
                    if entity.type == 'sentry' and getattr(entity, 'front_gun_locked', False):
                        entity.front_gun_locked = False
                        self._log(f'{entity.id} 返回己方补给区，前管重新解锁', entity.team)
                    heal_ratio = float(self.rules['supply'].get('heal_ratio_per_sec', 0.10))
                    if self.game_time >= float(self.rules['supply'].get('late_heal_start_time', 240.0)) and self.is_out_of_combat(entity):
                        heal_ratio = float(self.rules['supply'].get('late_heal_ratio_per_sec', 0.25))
                    entity.heal(entity.max_health * heal_ratio * dt)
                    claimable = self._claim_supply_ammo(entity)
                    purchased = self._try_purchase_role_ammo(entity)
                    if claimable > 0:
                        self._log(f'{entity.id} 在补给区获得 {claimable} 发允许发弹量', entity.team)
                    if purchased > 0:
                        self._log(f'{entity.id} 使用队伍金币购买 {purchased} 发允许发弹量', entity.team)
                elif region_type == 'mining_area':
                    self._handle_mining_zone(entity, region, dt)
                elif region_type == 'mineral_exchange':
                    self._handle_exchange_zone(entity, region, dt)
                elif region_type.startswith('buff_'):
                    self._apply_buff_region(entity, region, dt, regions)

            if facility and facility.get('type') in self.terrain_cross_types and self._terrain_access_allowed(entity, facility):
                self._update_traversal_progress(entity, facility, dt)
            else:
                self._finish_traversal_if_needed(entity)
                entity.traversal_state = None

    def _update_traversal_progress(self, entity, facility, dt):
        state = getattr(entity, 'traversal_state', None)
        if state is None or state.get('facility_id') != facility.get('id'):
            entity.traversal_state = {
                'facility_id': facility.get('id'),
                'facility_type': facility.get('type'),
                'time': 0.0,
                'entry_x': entity.position['x'],
                'entry_y': entity.position['y'],
                'last_x': entity.position['x'],
                'last_y': entity.position['y'],
                'width': abs(facility['x2'] - facility['x1']),
                'height': abs(facility['y2'] - facility['y1']),
            }
            return

        state['time'] += dt
        state['last_x'] = entity.position['x']
        state['last_y'] = entity.position['y']

    def _finish_traversal_if_needed(self, entity):
        state = getattr(entity, 'traversal_state', None)
        if not state:
            return

        min_hold_time = self.rules['terrain_cross']['min_hold_time']
        completion_ratio = self.rules['terrain_cross']['completion_ratio']
        travel_distance = math.hypot(state['last_x'] - state['entry_x'], state['last_y'] - state['entry_y'])
        facility_span = max(1.0, max(state['width'], state['height']))
        if state['time'] >= min_hold_time and travel_distance >= facility_span * completion_ratio:
            entity.terrain_buff_timer = self.rules['terrain_cross']['duration']
            self._log(f'{entity.id} 完整通过 {state["facility_type"]}，获得地形增益', entity.team)

    def _update_radar_marks(self, entities, map_manager):
        for entity_id in list(self.radar_marks.keys()):
            decay = self.rules['radar']['mark_decay_per_sec'] * self.dt
            self.radar_marks[entity_id] = max(0.0, self.radar_marks.get(entity_id, 0.0) - decay)

        for entity in entities:
            if entity.type != 'radar' or not entity.is_alive():
                continue

            radar_team = entity.team
            for target in entities:
                if target.team == radar_team or not target.is_alive():
                    continue

                distance = math.hypot(target.position['x'] - entity.position['x'], target.position['y'] - entity.position['y'])
                if distance < self.rules['radar']['range']:
                    gain = self.rules['radar']['mark_gain_per_sec'] * self.dt
                    self.radar_marks[target.id] = min(1.0, self.radar_marks.get(target.id, 0.0) + gain)

    def check_damage(self, entities):
        for shooter in entities:
            if shooter.type not in {'robot', 'sentry'} or not shooter.is_alive():
                continue
            if shooter.type == 'sentry' and getattr(shooter, 'front_gun_locked', False):
                continue
            if getattr(shooter, 'fire_control_state', 'idle') != 'firing':
                continue
            if getattr(shooter, 'respawn_timer', 0.0) > 0 or getattr(shooter, 'shot_cooldown', 0.0) > 0:
                continue
            if getattr(shooter, 'overheat_lock_timer', 0.0) > 0 or self._available_ammo(shooter) <= 0:
                continue
            if self.get_effective_fire_rate_hz(shooter) <= 0.0:
                continue

            target = self._resolve_autoaim_target(shooter, entities)
            if target is None:
                continue

            self._consume_shot(shooter)
            distance = math.hypot(target.position['x'] - shooter.position['x'], target.position['y'] - shooter.position['y'])
            hit_probability = self.calculate_hit_probability(shooter, target, distance)
            if random.random() <= hit_probability:
                damage = self.calculate_damage(shooter, target)
                if damage > 0:
                    self._mark_in_combat(shooter)
                    self._mark_in_combat(target)
                    target.take_damage(damage)

    def _resolve_autoaim_target(self, shooter, entities):
        max_distance = self.get_range(shooter.type)
        target_id = None
        if isinstance(getattr(shooter, 'target', None), dict):
            target_id = shooter.target.get('id')

        if target_id is not None:
            for entity in entities:
                if entity.id == target_id and entity.team != shooter.team and entity.is_alive():
                    distance = math.hypot(entity.position['x'] - shooter.position['x'], entity.position['y'] - shooter.position['y'])
                    if distance <= max_distance and self.can_track_target(shooter, entity, distance):
                        return entity

        nearest = None
        nearest_distance = None
        for entity in entities:
            if entity.team == shooter.team or not entity.is_alive():
                continue
            distance = math.hypot(entity.position['x'] - shooter.position['x'], entity.position['y'] - shooter.position['y'])
            if distance > max_distance:
                continue
            if not self.can_track_target(shooter, entity, distance):
                continue
            if nearest_distance is None or distance < nearest_distance:
                nearest = entity
                nearest_distance = distance
        return nearest

    def _consume_shot(self, shooter):
        self._consume_allowed_ammo(shooter, getattr(shooter, 'ammo_per_shot', self.rules['shooting']['ammo_per_shot']))
        effective_fire_rate = self.get_effective_fire_rate_hz(shooter)
        shooter.shot_cooldown = 1.0 / max(effective_fire_rate, 1e-6)
        shooter.power = max(0.0, float(getattr(shooter, 'power', 0.0)) - self.get_effective_power_per_shot(shooter))
        shooter.heat += float(getattr(shooter, 'heat_gain_per_shot', self.rules['shooting']['heat_per_shot']))
        self._mark_in_combat(shooter)
        if shooter.heat >= shooter.max_heat:
            shooter.heat = shooter.max_heat
            was_locked = getattr(shooter, 'overheat_lock_timer', 0.0) > 0.0
            shooter.overheat_lock_timer = max(
                float(getattr(shooter, 'overheat_lock_timer', 0.0)),
                float(self.rules['shooting']['overheat_lock_duration']),
            )
            shooter.fire_control_state = 'idle'
            if not was_locked:
                self._log(
                    f'{shooter.id} 枪口过热，发射机构锁定 {self.rules["shooting"]["overheat_lock_duration"]:.1f} 秒',
                    shooter.team,
                )

    def get_range(self, entity_type):
        if entity_type in {'robot', 'sentry'}:
            return self.auto_aim_max_distance
        return self.auto_aim_max_distance

    def calculate_hit_probability(self, shooter, target, distance=None):
        if getattr(target, 'invincible_timer', 0.0) > 0 or getattr(target, 'dynamic_invincible', False):
            return 0.0

        if distance is None:
            distance = math.hypot(
                target.position['x'] - shooter.position['x'],
                target.position['y'] - shooter.position['y'],
            )
        max_distance = self.get_range(shooter.type)
        if distance > max_distance:
            return 0.0
        assessment = self.evaluate_auto_aim_target(shooter, target, distance=distance, require_fov=True)
        if not assessment.get('can_auto_aim'):
            return 0.0

        probability = self._get_auto_aim_accuracy(distance, target)
        probability *= self._hit_probability_multiplier(shooter)
        return max(0.0, min(1.0, probability))

    def _get_turret_angle_diff(self, shooter, target):
        desired_angle = self._desired_turret_angle(shooter, target)
        turret_angle = getattr(shooter, 'turret_angle', shooter.angle)
        return self._normalize_angle_diff(desired_angle - turret_angle)

    def _get_auto_aim_accuracy(self, distance, target):
        profile = self.rules['shooting'].get('auto_aim_accuracy', {})
        motion_type = self.classify_target_motion(target)
        near_limit = self._meters_to_world_units(1.0)
        mid_limit = self._meters_to_world_units(5.0)

        if distance <= near_limit:
            return profile.get('near_all', 0.30)

        if distance <= mid_limit:
            key = {
                'fixed': 'mid_fixed',
                'spin': 'mid_spin',
                'translating_spin': 'mid_translating_spin',
            }[motion_type]
            return profile.get(key, 0.60)

        key = {
            'fixed': 'far_fixed',
            'spin': 'far_spin',
            'translating_spin': 'far_translating_spin',
        }[motion_type]
        return profile.get(key, 0.10)

    def classify_target_motion(self, target):
        thresholds = self.rules['shooting'].get('motion_thresholds', {})
        translating_speed = self._meters_to_world_units(thresholds.get('translating_target_speed_mps', 0.45))
        spinning_angular_velocity = thresholds.get('spinning_angular_velocity_deg', 45.0)

        linear_speed = math.hypot(target.velocity['vx'], target.velocity['vy'])
        angular_speed = abs(getattr(target, 'angular_velocity', 0.0))
        chassis_state = getattr(target, 'chassis_state', 'normal')
        is_spinning = angular_speed >= spinning_angular_velocity or chassis_state in {'spin', 'fast_spin'}
        is_translating = linear_speed >= translating_speed

        if is_spinning and is_translating:
            return 'translating_spin'
        if is_spinning:
            return 'spin'
        if is_translating:
            return 'translating_spin'
        return 'fixed'

    def describe_target_motion(self, target):
        labels = {
            'fixed': '固定靶',
            'spin': '小陀螺',
            'translating_spin': '平动靶',
        }
        return labels.get(self.classify_target_motion(target), '固定靶')

    def _hit_probability_multiplier(self, shooter):
        multiplier = 1.0
        if getattr(shooter, 'fort_buff_active', False):
            multiplier *= self.rules['fort']['hit_probability_mult']
        if getattr(shooter, 'terrain_buff_timer', 0.0) > 0:
            multiplier *= self.rules['terrain_cross']['hit_probability_mult']
        if getattr(shooter, 'weak_timer', 0.0) > 0:
            multiplier *= 0.75
        return multiplier

    def calculate_damage(self, shooter, target):
        if getattr(target, 'invincible_timer', 0.0) > 0 or getattr(target, 'dynamic_invincible', False):
            return 0.0

        target_damage_table = self.damage_system.get(target.type, {})
        projectile_key = self._resolve_projectile_damage_key(shooter)
        damage = float(target_damage_table.get(projectile_key, 0))
        damage *= self._damage_dealt_multiplier(shooter)
        damage *= self._damage_taken_multiplier(target)
        return max(0.0, round(damage, 2))

    def _resolve_projectile_damage_key(self, shooter):
        if getattr(shooter, 'ammo_type', '17mm') == '42mm':
            return 'bullet_42mm'
        if shooter.type == 'sentry':
            return 'bullet_17mm'

        robot_type = getattr(shooter, 'robot_type', '') or ''
        if robot_type == '英雄':
            return 'bullet_42mm'
        return 'bullet_17mm'

    def handle_collision_damage(self, entity1, entity2, impact_speed):
        min_impact_speed = float(self.rules.get('collision', {}).get('min_impact_speed', 1.0))
        if impact_speed < min_impact_speed:
            return

        pair_key = tuple(sorted((entity1.id, entity2.id)))
        cooldown = float(self.rules.get('collision', {}).get('damage_cooldown', 0.5))
        last_time = self.collision_damage_cooldowns.get(pair_key, -1e9)
        if self.game_time - last_time < cooldown:
            return
        self.collision_damage_cooldowns[pair_key] = self.game_time

        for source, target in ((entity1, entity2), (entity2, entity1)):
            damage = float(self.damage_system.get(target.type, {}).get('collision', 0))
            if damage > 0 and target.is_alive():
                self._mark_in_combat(source)
                self._mark_in_combat(target)
                target.take_damage(damage)

    def _damage_dealt_multiplier(self, shooter):
        multiplier = float(getattr(shooter, 'dynamic_damage_dealt_mult', 1.0))
        if getattr(shooter, 'terrain_buff_timer', 0.0) > 0:
            multiplier *= self.rules['terrain_cross']['damage_dealt_mult']
        if getattr(shooter, 'weak_timer', 0.0) > 0:
            multiplier *= self.rules['respawn']['weaken_damage_dealt_mult']
        return multiplier

    def _damage_taken_multiplier(self, target):
        multiplier = float(getattr(target, 'dynamic_damage_taken_mult', 1.0))
        if target.type == 'sentry':
            multiplier *= self._resolve_posture_effect(target)['damage_mult']
        if getattr(target, 'robot_type', '') == '工程' and self.game_time >= 180.0:
            multiplier *= 0.5
        if getattr(target, 'fort_buff_active', False):
            multiplier *= self.rules['fort']['damage_taken_mult']
        if getattr(target, 'terrain_buff_timer', 0.0) > 0:
            multiplier *= self.rules['terrain_cross']['damage_taken_mult']
        if getattr(target, 'weak_timer', 0.0) > 0:
            multiplier *= self.rules['respawn']['weaken_damage_taken_mult']
        if self.radar_marks.get(target.id, 0.0) >= 1.0:
            multiplier *= self.rules['radar']['vulnerability_mult']
        return multiplier

    def check_health(self, entities):
        for entity in entities:
            if entity.health > 0:
                continue
            entity.health = 0
            self.handle_destroy(entity)

    def handle_destroy(self, entity):
        if getattr(entity, 'death_handled', False):
            return

        entity.state = 'destroyed'
        entity.death_handled = True
        entity.target = None
        entity.fire_control_state = 'idle'
        entity.set_velocity(0, 0)
        entity.angular_velocity = 0
        entity.respawn_position = dict(getattr(entity, 'last_valid_position', entity.position))
        entity.invincible_timer = 0.0
        entity.weak_timer = 0.0
        entity.fort_buff_active = False
        entity.terrain_buff_timer = 0.0
        entity.traversal_state = None
        entity.dynamic_invincible = False
        entity.active_buff_labels = []
        entity.timed_buffs = {}
        entity.buff_cooldowns = {}
        entity.buff_path_progress = {}
        entity.carried_minerals = 0
        entity.mining_timer = 0.0
        entity.exchange_timer = 0.0

        if entity.type == 'base':
            self.game_over = True
            self.winner = 'red' if entity.team == 'blue' else 'blue'
            self.stage = 'ended'
            self._log(f'{entity.team}基地被摧毁！游戏结束！{self.winner}方获胜！', self.winner)
            return

        if entity.type in {'robot', 'sentry'}:
            delay_key = 'sentry_delay' if entity.type == 'sentry' else 'robot_delay'
            entity.respawn_duration = self.rules['respawn'][delay_key]
            entity.respawn_timer = entity.respawn_duration
            entity.state = 'respawning'
            if entity.type == 'sentry':
                entity.front_gun_locked = True
            self._log(f'{entity.id} 被击毁，进入复活读条', entity.team)
            return

        if entity.type == 'outpost':
            self._log(f'{entity.team}前哨站被摧毁！', entity.team)

    def _respawn_entity(self, entity):
        respawn_position = dict(getattr(entity, 'respawn_position', entity.position))
        entity.position = respawn_position
        entity.previous_position = dict(respawn_position)
        entity.last_valid_position = dict(respawn_position)
        entity.angle = entity.spawn_angle
        entity.turret_angle = entity.spawn_angle
        entity.health = entity.max_health
        entity.heat = 0.0
        entity.posture_active_time = 0.0
        entity.target = None
        entity.fire_control_state = 'idle'
        entity.velocity = {'vx': 0, 'vy': 0, 'vz': 0}
        entity.angular_velocity = 0
        entity.respawn_timer = 0.0
        entity.respawn_duration = 0.0
        entity.respawn_recovery_timer = float(self.rules['respawn']['weaken_duration'])
        entity.invincible_timer = self.rules['respawn']['invincible_duration']
        entity.weak_timer = self.rules['respawn']['weaken_duration']
        entity.death_handled = False
        entity.dynamic_invincible = False
        entity.active_buff_labels = []
        entity.timed_buffs = {}
        entity.buff_cooldowns = {}
        entity.buff_path_progress = {}
        entity.carried_minerals = 0
        entity.mining_timer = 0.0
        entity.exchange_timer = 0.0
        entity.state = 'invincible' if entity.invincible_timer > 0 else ('weak' if entity.weak_timer > 0 else 'idle')
        if entity.type == 'sentry':
            entity.front_gun_locked = True
        self._log(f'{entity.id} 已在原地复活，开始回补给区恢复状态', entity.team)

    def get_initial_health(self, entity_type):
        if entity_type in self.health_system:
            return self.health_system[entity_type]['initial_health']
        return 100

    def get_max_health(self, entity_type):
        if entity_type in self.health_system:
            return self.health_system[entity_type]['max_health']
        return 100

    def request_posture_change(self, sentry, posture):
        if sentry.type != 'sentry':
            return {'ok': False, 'code': 'NOT_SENTRY'}
        if posture not in self.posture_effects:
            return {'ok': False, 'code': 'INVALID_POSTURE'}
        if getattr(sentry, 'posture_cooldown', 0.0) > 0:
            return {'ok': False, 'code': 'POSTURE_COOLDOWN'}

        sentry.posture = posture
        sentry.posture_cooldown = self.rules['sentry']['posture_cooldown']
        sentry.posture_active_time = 0.0
        return {'ok': True, 'code': 'POSTURE_SWITCHED', 'posture': posture}

    def request_exchange(self, sentry, exchange_type, amount=1, target_entity=None):
        if sentry.type != 'sentry':
            return {'ok': False, 'code': 'NOT_SENTRY'}
        if getattr(sentry, 'exchange_cooldown', 0.0) > 0:
            return {'ok': False, 'code': 'EXCHANGE_COOLDOWN', 'time_left': getattr(sentry, 'exchange_cooldown', 0.0)}

        exchange = self.rules['sentry']['exchange']
        costs = {
            'ammo': exchange['ammo_cost'],
            'remote_ammo': exchange['remote_ammo_cost'],
            'hp': exchange['hp_cost'],
            'remote_hp': exchange['remote_hp_cost'],
            'revive_now': exchange['revive_now_cost'],
        }
        if exchange_type not in costs:
            return {'ok': False, 'code': 'INVALID_EXCHANGE_TYPE'}

        if exchange_type == 'revive_now' and sentry.is_alive():
            return {'ok': False, 'code': 'ALREADY_ALIVE'}

        if exchange_type in {'remote_ammo', 'remote_hp'}:
            if target_entity is None:
                return {'ok': False, 'code': 'TARGET_REQUIRED'}
            if target_entity.team != sentry.team:
                return {'ok': False, 'code': 'INVALID_TARGET_TEAM'}
            if not target_entity.is_alive():
                return {'ok': False, 'code': 'TARGET_NOT_ALIVE'}

        total_cost = costs[exchange_type] * amount
        if sentry.gold < total_cost:
            return {'ok': False, 'code': 'INSUFFICIENT_GOLD', 'need': total_cost, 'have': sentry.gold}

        sentry.gold -= total_cost
        self.team_gold[sentry.team] = sentry.gold
        sentry.exchange_cooldown = float(exchange.get('interval_sec', 2.0))

        if exchange_type in {'ammo', 'remote_ammo'}:
            ammo_receiver = target_entity if exchange_type == 'remote_ammo' else sentry
            ammo_type = getattr(ammo_receiver, 'ammo_type', '17mm')
            if ammo_type == '42mm':
                gain = exchange['remote_42mm_unit'] if exchange_type == 'remote_ammo' else exchange['local_42mm_unit']
            else:
                gain = exchange['remote_17mm_unit'] if exchange_type == 'remote_ammo' else exchange['local_17mm_unit']
            if exchange_type == 'remote_ammo':
                self._queue_pending_rule_event(
                    ammo_receiver,
                    'remote_ammo',
                    exchange['remote_delay'],
                    {'amount': int(gain * amount), 'ammo_type': ammo_type},
                )
            else:
                self._add_allowed_ammo(sentry, int(gain * amount), ammo_type)
        elif exchange_type in {'hp', 'remote_hp'}:
            hp_receiver = target_entity if exchange_type == 'remote_hp' else sentry
            heal_amount = hp_receiver.max_health * float(exchange['remote_hp_gain_ratio' if exchange_type == 'remote_hp' else 'hp_gain_ratio']) * amount
            if exchange_type == 'remote_hp':
                self._queue_pending_rule_event(
                    hp_receiver,
                    'remote_hp',
                    exchange['remote_delay'],
                    {'amount': float(heal_amount)},
                )
            else:
                sentry.heal(heal_amount)
        elif exchange_type == 'revive_now':
            self._respawn_entity(sentry)

        return {
            'ok': True,
            'code': 'EXCHANGE_SUCCESS',
            'exchange_type': exchange_type,
            'cost': total_cost,
            'target_id': getattr(target_entity, 'id', sentry.id),
        }

    def confirm_respawn(self, sentry):
        if sentry.type != 'sentry':
            return {'ok': False, 'code': 'NOT_SENTRY'}
        if sentry.is_alive():
            return {'ok': False, 'code': 'ALREADY_ALIVE'}
        if getattr(sentry, 'respawn_timer', 0.0) > 0:
            return {'ok': False, 'code': 'RESPAWN_NOT_READY', 'time_left': sentry.respawn_timer}

        self._respawn_entity(sentry)
        return {'ok': True, 'code': 'RESPAWN_CONFIRMED'}

    def get_referee_message(self, entities, map_manager, game_time, game_duration, focus_team='red'):
        sentry = self._find_entity(entities, focus_team, 'sentry')
        if sentry is None:
            return {}

        enemy_team = 'blue' if focus_team == 'red' else 'red'
        base = self._find_entity(entities, focus_team, 'base')
        outpost = self._find_entity(entities, focus_team, 'outpost')
        marked_enemy_ids: List[str] = []
        max_mark_progress = 0.0
        for entity in entities:
            if entity.team == enemy_team:
                progress = self.radar_marks.get(entity.id, 0.0)
                if progress > 0:
                    marked_enemy_ids.append(entity.id)
                max_mark_progress = max(max_mark_progress, progress)

        effect = self._resolve_posture_effect(sentry)
        gains = {
            'occupied_facilities': self.occupied_facilities.get(focus_team, {}),
            'fort_active': getattr(sentry, 'fort_buff_active', False),
            'terrain_cross_active': getattr(sentry, 'terrain_buff_timer', 0.0) > 0,
            'terrain_cross_time_left': round(getattr(sentry, 'terrain_buff_timer', 0.0), 2),
            'supply_cooldown': round(getattr(sentry, 'supply_cooldown', 0.0), 2),
        }

        team_info = {}
        for entity in entities:
            if entity.team != focus_team:
                continue
            team_info[entity.id] = {
                'type': entity.type,
                'hp': entity.health,
                'max_hp': entity.max_health,
                'pos': (entity.position['x'], entity.position['y'], entity.position.get('z', 0)),
                'alive': entity.is_alive(),
                'state': entity.state,
                'respawn_timer': round(getattr(entity, 'respawn_timer', 0.0), 2),
                'invincible_timer': round(getattr(entity, 'invincible_timer', 0.0), 2),
                'weak_timer': round(getattr(entity, 'weak_timer', 0.0), 2),
            }

        return {
            'game_status': {
                'stage': self.stage,
                'time_left': max(0.0, game_duration - game_time),
                'match_time': game_duration,
            },
            'robot_status': {
                'hp': sentry.health,
                'heat': sentry.heat,
                'ammo': getattr(sentry, 'ammo', 0),
                'gold': round(sentry.gold, 2),
                'team_minerals': int(self.team_minerals.get(focus_team, 0)),
                'posture': getattr(sentry, 'posture', 'mobile'),
                'posture_cooldown': round(getattr(sentry, 'posture_cooldown', 0.0), 2),
                'height': sentry.position.get('z', 0),
                'respawn_timer': round(getattr(sentry, 'respawn_timer', 0.0), 2),
                'invincible_timer': round(getattr(sentry, 'invincible_timer', 0.0), 2),
                'weak_timer': round(getattr(sentry, 'weak_timer', 0.0), 2),
                'auto_aim_limit': round(self.auto_aim_max_distance, 2),
            },
            'power_heat_data': {
                'power_mult': effect['power_mult'],
                'cool_mult': effect['cool_mult'],
                'damage_mult': effect['damage_mult'],
            },
            'event_data': {
                'base_hp': base.health if base else 0,
                'outpost_hp': outpost.health if outpost else 0,
                'gains': gains,
                'team_gold': round(self.team_gold.get(focus_team, 0.0), 2),
                'team_minerals': int(self.team_minerals.get(focus_team, 0)),
                'facility_summary': map_manager.get_facility_summary() if map_manager else {},
                'radar_marked_enemies': marked_enemy_ids,
            },
            'radar_data': {
                'marked_progress_P': round(max_mark_progress, 3),
                'vulnerability': self.rules['radar']['vulnerability_mult'] if max_mark_progress >= 1.0 else 1.0,
            },
            'team_info': team_info,
        }

    def _log(self, message, team='system'):
        if self.game_engine is not None:
            self.game_engine.add_log(message, team)
