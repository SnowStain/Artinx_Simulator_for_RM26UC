#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ast
import json
import math
import os
import random
import time
import xml.etree.ElementTree as ET
from copy import deepcopy

from control.behavior_tree import Action, BehaviorContext, Condition, Selector, Sequence, SUCCESS, FAILURE
from control.decision_plugins import load_decision_plugins
from control.frame_context import AIFrameContext
from control.navigation_planner import NavigationPlannerRuntime
from control.pathfinding_worker_router import EntityPathfinderRouter
from control.targeting_runtime import TargetingRuntime


class AIController:
    EMPTY_PATH_PREVIEW = ()
    TODO_DECISION_ID = 'todo_rebuild_decision_system'
    MAX_STRATEGY_STAGES = 4
    DEFAULT_ENGAGE_DISTANCE_M = 8.0
    COMMON_ROLE_KEY = 'common'
    STRATEGY_TASK_TYPES = {
        'default',
        'terrain_traversal',
        'assault',
        'area_patrol',
        'field_interaction',
        'defense',
    }
    POINT_TARGET_ALIASES = {
        'primary': 'node_1',
        'secondary': 'node_2',
        'first': 'node_1',
        'second': 'node_2',
    }
    MERGED_DECISION_ALIASES = {
        'force_push_base': 'push_base',
        'must_restock': 'opening_supply',
        'terrain_fly_slope': 'cross_terrain',
        'terrain_first_step': 'cross_terrain',
        'terrain_second_step': 'cross_terrain',
    }
    ROLE_BEHAVIOR_TREE_FILES = {
        'sentry': ('sentry_btcpp.xml', 'SentryBehaviorTree'),
        'infantry': ('infantry_btcpp.xml', 'InfantryBehaviorTree'),
        'hero': ('hero_btcpp.xml', 'HeroBehaviorTree'),
        'engineer': ('engineer_btcpp.xml', 'EngineerBehaviorTree'),
    }
    COMMON_TERRAIN_POLICY_TARGET_DEFS = (
        {'id': 'node_1', 'label': '跨越节点 1'},
        {'id': 'node_2', 'label': '跨越节点 2'},
        {'id': 'node_3', 'label': '跨越节点 3'},
        {'id': 'node_4', 'label': '跨越节点 4'},
    )
    COMMON_TERRAIN_POLICY_DEFS = (
        {
            'id': 'common_first_step_up',
            'label': '上一级台阶',
            'description': '所有移动在经过一级台阶上行时统一调用的跨越策略。',
            'terrain_type': 'first_step',
            'direction': 'up',
            'default_destination_types': ('first_step',),
        },
        {
            'id': 'common_first_step_down',
            'label': '下一级台阶',
            'description': '所有移动在经过一级台阶下行时统一调用的跨越策略。',
            'terrain_type': 'first_step',
            'direction': 'down',
            'default_destination_types': ('first_step',),
        },
        {
            'id': 'common_second_step_up',
            'label': '上二级台阶',
            'description': '所有移动在经过二级台阶上行时统一调用的跨越策略。',
            'terrain_type': 'second_step',
            'direction': 'up',
            'default_destination_types': ('second_step',),
        },
        {
            'id': 'common_second_step_down',
            'label': '下二级台阶',
            'description': '所有移动在经过二级台阶下行时统一调用的跨越策略。',
            'terrain_type': 'second_step',
            'direction': 'down',
            'default_destination_types': ('second_step',),
        },
        {
            'id': 'common_fly_slope',
            'label': '飞坡通道',
            'description': '所有移动在经过飞坡时统一调用的跨越策略。',
            'terrain_type': 'fly_slope',
            'direction': 'forward',
            'default_destination_types': ('fly_slope',),
        },
    )
    TODO_ROLE_LABELS = {
        'sentry': '哨兵决策 TODO',
        'infantry': '步兵决策 TODO',
        'hero': '英雄决策 TODO',
        'engineer': '工程决策 TODO',
    }

    def __init__(self, config):
        self.config = config
        self.ai_strategy = config.get('ai', {}).get('strategy', {})
        self._ai_config = config.get('ai', {})
        self._patrol_index = {}
        self._strategy_patrol_state = {}
        self._post_supply_goal_state = {}
        self.enable_entity_movement = config.get('simulator', {}).get('enable_entity_movement', True)
        self._path_cache = {}
        self._stuck_state = {}
        self._forced_supply_escape_state = {}
        self._ai_update_interval = float(self._ai_config.get('update_interval_sec', 0.16))
        self._path_replan_interval = float(self._ai_config.get('path_replan_interval_sec', 0.9))
        self._path_replans_per_update = max(1, int(self._ai_config.get('path_replans_per_update', 1)))
        self._pathfinder_max_iterations = max(80, int(self._ai_config.get('pathfinder_max_iterations', 320)))
        self._pathfinder_time_budget_sec = max(0.0005, float(self._ai_config.get('pathfinder_time_budget_ms', 1.8)) / 1000.0)
        self._pathfinder_total_budget_sec = max(self._pathfinder_time_budget_sec, float(self._ai_config.get('pathfinder_total_budget_ms', 5.0)) / 1000.0)
        self._pathfinder_max_attempts = max(1, int(self._ai_config.get('pathfinder_max_attempts', 3)))
        self._pathfinder_use_dual_resolution = bool(self._ai_config.get('pathfinder_use_dual_resolution', False))
        self._pathfinder_try_resolved_target = bool(self._ai_config.get('pathfinder_try_resolved_target', False))
        self._path_stale_recheck_interval = max(self._path_replan_interval, float(self._ai_config.get('path_stale_recheck_interval_sec', self._path_replan_interval)))
        self._path_failure_retry_sec = max(self._ai_update_interval, float(self._ai_config.get('path_failure_retry_sec', max(0.45, self._ai_update_interval * 2.5))))
        self._path_failure_retry_max_sec = max(self._path_failure_retry_sec, float(self._ai_config.get('path_failure_retry_max_sec', 1.6)))
        self._path_goal_hysteresis_world = max(24.0, float(self._ai_config.get('path_goal_hysteresis_world', 56.0)))
        self._direct_segment_check_interval = max(self._ai_update_interval, float(self._ai_config.get('direct_segment_check_interval_sec', max(0.28, self._ai_update_interval * 1.5))))
        self._pathfinder_worker_threads = max(1, int(self._ai_config.get('pathfinder_worker_threads', 1)))
        self._path_replans_remaining = self._path_replans_per_update
        self._last_ai_update_time = {}
        self._entity_path_state = {}
        self._route_progress_state = {}
        self._movement_status_cache = {}
        self._sentry_fly_slope_state = {}
        self._behavior_tree_dir = os.path.join(os.path.dirname(__file__), 'behavior_trees')
        self._decision_plugin_catalog = load_decision_plugins()
        self._behavior_override_payload = {}
        self._behavior_override_path = None
        self._behavior_override_mtime = None
        self._settings_mtime = None
        self._behavior_reload_check_interval = max(0.1, float(self._ai_config.get('behavior_reload_check_interval_sec', 0.25)))
        self._last_behavior_reload_check_time = -1.0
        self.role_decision_specs = {}
        self.role_trees = {}
        self._pathfinder_router = EntityPathfinderRouter()
        self._navigation_planner = NavigationPlannerRuntime(self, self._pathfinder_router)
        self._targeting_runtime = TargetingRuntime(self)
        self._frame_target_assessment_cache = {}
        self._refresh_behavior_runtime_overrides(force=True)

    def shutdown(self):
        router = getattr(self, '_pathfinder_router', None)
        if router is not None:
            router.shutdown()
            self._pathfinder_router = None

    def __del__(self):
        self.shutdown()

    def _entity_update_phase_offset(self, entity_id):
        # 打散同帧集中重算，避免 update_interval 对齐造成周期性卡顿峰值。
        if self._ai_update_interval <= 1e-6:
            return 0.0
        phase = abs(hash(str(entity_id))) % 4096
        return (phase / 4096.0) * self._ai_update_interval

    def _debug_feature_toggles(self):
        simulator_config = self.config.get('simulator', {}) if isinstance(self.config, dict) else {}
        toggles = simulator_config.get('debug_feature_toggles', {})
        return toggles if isinstance(toggles, dict) else {}

    def _debug_toggle_enabled(self, feature_id, default=True):
        toggles = self._debug_feature_toggles()
        if feature_id not in toggles:
            return bool(default)
        return bool(toggles.get(feature_id))

    def _role_debug_key(self, entity):
        role_key = self._role_key(entity)
        if role_key not in {'hero', 'infantry', 'sentry', 'engineer'}:
            return 'infantry'
        return role_key

    def _role_state_machine_enabled(self, entity):
        return self._debug_toggle_enabled(f'state_machine.{self._role_debug_key(entity)}', True)

    def _role_controller_feature_enabled(self, entity, feature_name):
        return self._debug_toggle_enabled(f'controller.{self._role_debug_key(entity)}.{feature_name}', True)

    def _can_replan_path(self):
        if self._path_replans_remaining <= 0:
            return False
        self._path_replans_remaining -= 1
        return True

    def _decision_spec(self, decision_id, label, condition, action, fallback=False, **metadata):
        spec = {
            'id': str(decision_id),
            'label': str(label),
            'condition': condition,
            'action': action,
            'fallback': bool(fallback),
        }
        for key, value in metadata.items():
            if value is not None:
                spec[key] = value
        return spec

    def _legacy_default_role_decision_specs(self):
        return {
            'sentry': [
                self._decision_spec('return_to_supply_unlock', '回补解锁', lambda ctx: getattr(ctx.entity, 'front_gun_locked', False), self._action_return_to_supply_unlock),
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('push_base', '进攻基地', self._should_push_base, self._action_push_base),
                self._decision_spec('emergency_defend_base', '紧急回防基地', self._should_emergency_defend_base, self._action_emergency_defend_base),
                self._decision_spec('opening_supply', '补给区补给', self._needs_supply, self._action_opening_supply),
                self._decision_spec('emergency_retreat', '紧急撤退', self._is_critical_state, self._action_emergency_retreat),
                self._decision_spec('sentry_opening_highground', '开局一级台阶飞坡', self._should_sentry_opening_highground, self._action_sentry_opening_highground),
                self._decision_spec('activate_energy', '开符', self._should_activate_energy, self._action_activate_energy),
                self._decision_spec('sentry_fly_slope', '前压打击后排', self._should_sentry_fly_slope, self._action_sentry_fly_slope),
                self._decision_spec('highground_assault', '占领高地进攻前哨', self._should_take_enemy_highground, self._action_highground_assault),
                self._decision_spec('support_infantry_push', '配合步兵推进', self._should_support_infantry_push, self._action_support_infantry_push),
                self._decision_spec('protect_hero', '保护英雄', self._should_protect_hero, self._action_protect_hero),
                self._decision_spec('support_engineer', '护送工程', self._should_support_engineer, self._action_support_engineer),
                self._decision_spec('intercept_enemy_engineer', '拦截敌工', self._should_intercept_enemy_engineer, self._action_intercept_enemy_engineer),
                self._decision_spec('push_outpost', '推进前哨站', self._should_push_outpost, self._action_push_outpost),
                self._decision_spec('teamfight_cover', '团战掩护', self._has_teamfight_window, self._action_teamfight_cover),
                self._decision_spec('swarm_attack', '发现即集火', self._has_target, self._action_swarm_attack),
                self._decision_spec('cross_terrain', '地形跨越', self._should_cross_terrain, self._action_cross_terrain, default_destination_types=('fly_slope', 'first_step', 'second_step')),
                self._decision_spec('patrol_key_facilities', '巡关键设施', None, self._action_patrol_key_facilities, fallback=True),
            ],
            'infantry': [
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('push_base', '进攻基地', self._should_push_base, self._action_push_base),
                self._decision_spec('emergency_defend_base', '紧急回防基地', self._should_emergency_defend_base, self._action_emergency_defend_base),
                self._decision_spec('opening_supply', '补给区补给', self._needs_supply, self._action_opening_supply),
                self._decision_spec('emergency_retreat', '紧急撤退', self._is_critical_state, self._action_emergency_retreat),
                self._decision_spec('infantry_opening_highground', '开局抢高地增益', self._should_infantry_opening_highground, self._action_infantry_opening_highground),
                self._decision_spec('activate_energy', '开符', self._should_activate_energy, self._action_activate_energy),
                self._decision_spec('highground_assault', '占领高地进攻前哨', self._should_take_enemy_highground, self._action_highground_assault),
                self._decision_spec('push_outpost', '推进前哨站', self._should_push_outpost, self._action_push_outpost),
                self._decision_spec('intercept_enemy_engineer', '拦截敌工', self._should_intercept_enemy_engineer, self._action_intercept_enemy_engineer),
                self._decision_spec('swarm_attack', '发现即集火', self._has_target, self._action_swarm_attack),
                self._decision_spec('teamfight_push', '团战推进', self._has_teamfight_window, self._action_teamfight_push),
                self._decision_spec('cross_terrain', '地形跨越', self._should_cross_terrain, self._action_cross_terrain, default_destination_types=('fly_slope', 'first_step', 'second_step')),
                self._decision_spec('patrol_key_facilities', '巡关键设施', None, self._action_patrol_key_facilities, fallback=True),
            ],
            'hero': [
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('push_base', '进攻基地', self._should_push_base, self._action_push_base),
                self._decision_spec('emergency_defend_base', '紧急回防基地', self._should_emergency_defend_base, self._action_emergency_defend_base),
                self._decision_spec('opening_supply', '补给区补给', self._needs_supply, self._action_opening_supply),
                self._decision_spec('hero_seek_cover', '英雄找掩护', self._should_hero_seek_cover, self._action_hero_seek_cover),
                self._decision_spec('hero_opening_highground', '开局高地部署', self._should_hero_opening_highground, self._action_hero_opening_highground),
                self._decision_spec('highground_assault', '占领高地进攻前哨', self._should_hero_melee_highground_assault, self._action_highground_assault),
                self._decision_spec('hero_lob_outpost', '吊射前哨站', self._should_hero_lob_outpost, self._action_hero_lob_outpost),
                self._decision_spec('hero_lob_base', '吊射基地', self._should_hero_lob_base, self._action_hero_lob_base),
                self._decision_spec('swarm_attack', '发现即集火', self._has_target, self._action_swarm_attack),
                self._decision_spec('cross_terrain', '地形跨越', self._should_cross_terrain, self._action_cross_terrain, default_destination_types=('fly_slope', 'first_step', 'second_step')),
                self._decision_spec('patrol_key_facilities', '巡关键设施', None, self._action_patrol_key_facilities, fallback=True),
            ],
            'engineer': [
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('opening_supply', '补给区补给', self._needs_supply, self._action_opening_supply),
                self._decision_spec('emergency_retreat', '紧急撤退', self._is_critical_state, self._action_emergency_retreat),
                self._decision_spec('engineer_exchange', '回家兑矿', self._needs_engineer_exchange, self._action_engineer_exchange),
                self._decision_spec('engineer_mine', '前往采矿', self._needs_engineer_mining, self._action_engineer_mine),
                self._decision_spec('cross_terrain', '地形跨越', self._should_cross_terrain, self._action_cross_terrain, default_destination_types=('fly_slope', 'first_step', 'second_step')),
                self._decision_spec('engineer_cycle', '取矿兑矿循环', None, self._action_engineer_cycle, fallback=True),
            ],
        }

    def _available_plugin_bindings_for_role(self, role_key):
        if self._decision_system_disabled():
            return []
        if role_key == self.COMMON_ROLE_KEY:
            return [dict(binding) for binding in self._common_terrain_policy_bindings()]
        bindings = []
        for plugin_id, plugin in self._decision_plugin_catalog.items():
            role_config = plugin.get('roles', {}).get(role_key)
            if not isinstance(role_config, dict):
                continue
            bindings.append({
                'id': plugin_id,
                'description': str(plugin.get('description', '')),
                **role_config,
            })
        bindings.sort(key=lambda item: (int(item.get('order', 10_000)), str(item.get('id', ''))))
        return bindings

    def _available_plugin_binding(self, role_key, decision_id):
        decision_id = str(decision_id)
        for binding in self._available_plugin_bindings_for_role(role_key):
            if str(binding.get('id', '')) == decision_id:
                return binding
        return None

    def _common_terrain_policy_def(self, decision_id):
        decision_id = str(decision_id or '').strip()
        for policy in self.COMMON_TERRAIN_POLICY_DEFS:
            if str(policy.get('id', '')) == decision_id:
                return dict(policy)
        return None

    def _common_terrain_policy_bindings(self):
        bindings = []
        for policy in self.COMMON_TERRAIN_POLICY_DEFS:
            policy_id = str(policy['id'])
            bindings.append({
                'id': policy_id,
                'label': str(policy['label']),
                'description': str(policy.get('description', '')),
                'fallback': True,
                'default_destination_types': tuple(policy.get('default_destination_types', ())),
                'terrain_type': str(policy.get('terrain_type', '')),
                'direction': str(policy.get('direction', 'forward')),
                'editable_targets': tuple(dict(item) for item in self.COMMON_TERRAIN_POLICY_TARGET_DEFS),
                'preview_points': (lambda controller, role_key, map_manager, team=None, override=None, binding=None, bound_id=policy_id:
                    controller._common_terrain_policy_preview_points(bound_id, map_manager, team=team or 'red')),
                'preview_regions': (lambda controller, role_key, map_manager, team=None, override=None, binding=None, bound_id=policy_id:
                    controller._common_terrain_policy_preview_regions(bound_id, map_manager, team=team or 'red')),
                'action': (lambda controller, ctx, plugin_role, plugin_binding, bound_id=policy_id:
                    controller._preview_common_terrain_policy_action(ctx, bound_id)),
            })
        return bindings

    def _preview_common_terrain_policy_action(self, context, decision_id):
        route_specs = self._common_terrain_policy_route_specs(
            decision_id,
            context.entity.team,
            context.map_manager,
            entity=context.entity,
        )
        if not route_specs:
            return FAILURE
        target_point = route_specs[0]['point']
        policy = self._common_terrain_policy_def(decision_id) or {}
        focus_target = context.data.get('target')
        return self._set_decision(
            context,
            f"通用跨越策略：{str(policy.get('label', decision_id))}",
            target=focus_target,
            target_point=target_point,
            speed=self._meters_to_world_units(1.9, context.map_manager),
            preferred_route={'target': target_point},
            turret_state='aiming' if focus_target is not None else 'searching',
        )

    def _nearest_team_facility(self, map_manager, team, facility_type):
        if map_manager is None:
            return None
        base_anchor = self.get_team_anchor(team, 'base', map_manager)
        best_facility = None
        best_distance = None
        for facility in map_manager.get_facility_regions(facility_type):
            if facility.get('team') not in {team, 'neutral'}:
                continue
            center = self.facility_center(facility)
            if base_anchor is None:
                return facility
            distance = math.hypot(float(center[0]) - float(base_anchor[0]), float(center[1]) - float(base_anchor[1]))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_facility = facility
        return best_facility

    def _common_terrain_policy_team_direction(self, team):
        return 1.0 if str(team) == 'red' else -1.0

    def _common_step_policy_default_points(self, facility_type, direction, team, map_manager, entity=None):
        facility = self._nearest_team_facility(map_manager, team, facility_type)
        if facility is None:
            return {}
        travel_sign = self._common_terrain_policy_team_direction(team)
        if direction == 'down':
            travel_sign *= -1.0
        min_x = min(float(facility.get('x1', 0.0)), float(facility.get('x2', 0.0)))
        max_x = max(float(facility.get('x1', 0.0)), float(facility.get('x2', 0.0)))
        center_y = (float(facility.get('y1', 0.0)) + float(facility.get('y2', 0.0))) * 0.5
        near_edge = min_x if travel_sign > 0 else max_x
        far_edge = max_x if travel_sign > 0 else min_x
        if facility_type == 'first_step':
            near_offset_m = 0.45
            far_offset_m = 0.78
        else:
            near_offset_m = 0.55
            far_offset_m = 1.05
        primary = self._resolve_navigation_target(
            (near_edge - travel_sign * self._meters_to_world_units(near_offset_m, map_manager), center_y),
            map_manager,
            entity=entity,
        )
        secondary = self._resolve_navigation_target(
            (far_edge + travel_sign * self._meters_to_world_units(far_offset_m, map_manager), center_y),
            map_manager,
            entity=entity,
        )
        targets = {}
        if primary is not None:
            targets['node_1'] = {'x': float(primary[0]), 'y': float(primary[1])}
        if secondary is not None:
            targets['node_2'] = {'x': float(secondary[0]), 'y': float(secondary[1])}
        return targets

    def _common_fly_slope_policy_default_points(self, team, map_manager, entity=None):
        if map_manager is None:
            return {}
        facility_type = 'buff_terrain_fly_slope_red_start' if team == 'red' else 'buff_terrain_fly_slope_blue_start'
        primary = None
        for facility in map_manager.get_facility_regions(facility_type):
            if facility.get('team') in {'neutral', team}:
                primary = self._resolve_navigation_target(self.facility_center(facility), map_manager, entity=entity)
                break
        slope = self._nearest_team_facility(map_manager, team, 'fly_slope')
        if slope is None:
            return {'node_1': {'x': float(primary[0]), 'y': float(primary[1])}} if primary is not None else {}
        direction = self._common_terrain_policy_team_direction(team)
        peak_x = float(slope.get('x2', 0.0)) if direction > 0 else float(slope.get('x1', 0.0))
        center_y = (float(slope.get('y1', 0.0)) + float(slope.get('y2', 0.0))) * 0.5
        if primary is None:
            primary = self._resolve_navigation_target(self.facility_center(slope), map_manager, entity=entity)
        landing = self._resolve_navigation_target(
            (peak_x + direction * self._meters_to_world_units(0.85, map_manager), center_y),
            map_manager,
            entity=entity,
        )
        targets = {}
        if primary is not None:
            targets['node_1'] = {'x': float(primary[0]), 'y': float(primary[1])}
        if landing is not None:
            targets['node_2'] = {'x': float(landing[0]), 'y': float(landing[1])}
        return targets

    def _default_common_terrain_policy_target_specs(self, decision_id, team, map_manager, entity=None):
        policy = self._common_terrain_policy_def(decision_id) or {}
        terrain_type = str(policy.get('terrain_type', ''))
        if terrain_type == 'fly_slope':
            return self._common_fly_slope_policy_default_points(team, map_manager, entity=entity)
        if terrain_type in {'first_step', 'second_step'}:
            return self._common_step_policy_default_points(
                terrain_type,
                str(policy.get('direction', 'up')),
                team,
                map_manager,
                entity=entity,
            )
        return {}

    def _ordered_common_target_specs(self, target_specs, map_manager, entity=None):
        ordered = []
        for target_id, point_spec in (target_specs or {}).items():
            if not str(target_id).startswith('node_'):
                continue
            suffix = str(target_id).split('_', 1)[1]
            try:
                sort_key = int(suffix)
            except ValueError:
                continue
            point = (float(point_spec['x']), float(point_spec['y']))
            resolved = self._resolve_navigation_target(point, map_manager, entity=entity) if map_manager is not None else point
            if resolved is None:
                continue
            ordered.append((
                sort_key,
                {
                    'id': str(target_id),
                    'index': sort_key,
                    'point': (float(resolved[0]), float(resolved[1])),
                    'radius': float(point_spec.get('radius', 0.0) or 0.0),
                },
            ))
        ordered.sort(key=lambda item: item[0])
        return [item[1] for item in ordered[:self.MAX_STRATEGY_STAGES]]

    def _common_terrain_policy_route_specs(self, decision_id, team, map_manager, entity=None):
        override = self._behavior_override_for_decision(self.COMMON_ROLE_KEY, decision_id)
        target_specs = self._behavior_override_point_target_specs(override, team=team)
        if not target_specs:
            target_specs = self._default_common_terrain_policy_target_specs(decision_id, team, map_manager, entity=entity)
        return self._ordered_common_target_specs(target_specs, map_manager, entity=entity)

    def _common_terrain_policy_preview_points(self, decision_id, map_manager, team='red'):
        route_specs = self._common_terrain_policy_route_specs(decision_id, team, map_manager)
        return {
            str(spec['id']): (float(spec['point'][0]), float(spec['point'][1]))
            for spec in route_specs
        }

    def _common_terrain_policy_preview_regions(self, decision_id, map_manager, team='red'):
        route_specs = self._common_terrain_policy_route_specs(decision_id, team, map_manager)
        radius = self._meters_to_world_units(0.5, map_manager) if map_manager is not None else 22.0
        return [
            {
                'shape': 'circle',
                'cx': float(spec['point'][0]),
                'cy': float(spec['point'][1]),
                'radius': float(spec['radius'] or radius),
            }
            for spec in route_specs
        ]

    def _terrain_policy_decision_id_for_traversal(self, traversal):
        if not isinstance(traversal, dict):
            return None
        terrain_type = str(traversal.get('facility_type', '') or '')
        direction = str(traversal.get('direction', '') or '')
        if terrain_type == 'first_step':
            return 'common_first_step_up' if direction == 'up' else 'common_first_step_down'
        if terrain_type == 'second_step':
            return 'common_second_step_up' if direction == 'up' else 'common_second_step_down'
        if terrain_type == 'fly_slope':
            return 'common_fly_slope'
        return None

    def _default_traversal_path_points(self, traversal):
        if not isinstance(traversal, dict):
            return self.EMPTY_PATH_PREVIEW
        points = []
        for key in ('entry_point', 'approach_point'):
            point = traversal.get(key)
            if point is None:
                continue
            normalized = (float(point[0]), float(point[1]))
            if not points or points[-1] != normalized:
                points.append(normalized)
            break
        for point in tuple(traversal.get('climb_points', ())) or self.EMPTY_PATH_PREVIEW:
            if point is None:
                continue
            normalized = (float(point[0]), float(point[1]))
            if not points or points[-1] != normalized:
                points.append(normalized)
        for key in ('top_point', 'exit_point', 'landing_point'):
            point = traversal.get(key)
            if point is None:
                continue
            normalized = (float(point[0]), float(point[1]))
            if not points or points[-1] != normalized:
                points.append(normalized)
        return tuple(points)

    def _terrain_policy_path_points(self, entity, traversal, map_manager):
        decision_id = self._terrain_policy_decision_id_for_traversal(traversal)
        if decision_id is None:
            return self._default_traversal_path_points(traversal)
        route_specs = self._common_terrain_policy_route_specs(
            decision_id,
            getattr(entity, 'team', 'red'),
            map_manager,
            entity=entity,
        )
        if route_specs:
            return tuple((float(spec['point'][0]), float(spec['point'][1])) for spec in route_specs)
        return self._default_traversal_path_points(traversal)

    def _normalize_behavior_point_targets(self, targets):
        specs = self._normalize_behavior_point_target_specs(targets)
        return {
            key: (float(spec['x']), float(spec['y']))
            for key, spec in specs.items()
        }

    def _normalize_behavior_point_target_specs(self, targets):
        if not isinstance(targets, dict):
            return {}
        normalized = {}
        for key, value in targets.items():
            if not isinstance(key, str):
                continue
            try:
                mapped_key = self.POINT_TARGET_ALIASES.get(key, key)
                radius = None
                if isinstance(value, dict):
                    point_x = value.get('x', value.get('cx'))
                    point_y = value.get('y', value.get('cy'))
                    radius = value.get('radius')
                elif isinstance(value, (list, tuple)) and len(value) >= 2:
                    point_x = value[0]
                    point_y = value[1]
                    radius = value[2] if len(value) >= 3 else None
                else:
                    continue
                if point_x in {None, ''} or point_y in {None, ''}:
                    continue
                spec = {
                    'x': round(float(point_x), 1),
                    'y': round(float(point_y), 1),
                }
                if radius not in {None, ''}:
                    spec['radius'] = round(max(6.0, float(radius)), 1)
                normalized[mapped_key] = spec
            except (TypeError, ValueError):
                continue
        return normalized

    def _normalize_behavior_stage(self, stage):
        if not isinstance(stage, dict):
            return {}
        normalized = {}
        task_type = str(stage.get('task_type', 'default') or 'default').strip()
        if task_type not in self.STRATEGY_TASK_TYPES:
            task_type = 'default'
        if task_type != 'default':
            normalized['task_type'] = task_type

        destination_mode = str(stage.get('destination_mode', 'region') or 'region').strip()
        if destination_mode not in {'region', 'reference', 'none'}:
            destination_mode = 'region'
        if destination_mode != 'region':
            normalized['destination_mode'] = destination_mode

        destination_ref = str(stage.get('destination_ref', '') or '').strip()
        if destination_ref:
            normalized['destination_ref'] = destination_ref

        assault_ref = str(stage.get('assault_ref', 'enemy_any_unit') or 'enemy_any_unit').strip()
        if assault_ref and assault_ref != 'enemy_any_unit':
            normalized['assault_ref'] = assault_ref

        assault_follow_priority = str(stage.get('assault_follow_priority', 'target_first') or 'target_first').strip()
        if assault_follow_priority in {'target_first', 'destination_first'} and assault_follow_priority != 'target_first':
            normalized['assault_follow_priority'] = assault_follow_priority

        interaction_ref = str(stage.get('interaction_ref', 'own_supply') or 'own_supply').strip()
        if interaction_ref in {'own_supply', 'mining_area', 'energy_mechanism'} and interaction_ref != 'own_supply':
            normalized['interaction_ref'] = interaction_ref

        defense_ref = str(stage.get('defense_ref', 'high_threat_enemy') or 'high_threat_enemy').strip()
        if defense_ref in {'high_threat_enemy', 'defend_base'} and defense_ref != 'high_threat_enemy':
            normalized['defense_ref'] = defense_ref

        engage_distance_m = stage.get('engage_distance_m', None)
        if engage_distance_m not in {None, ''}:
            try:
                engage_value = max(0.5, float(engage_distance_m))
            except (TypeError, ValueError):
                engage_value = None
            if engage_value is not None and abs(engage_value - self.DEFAULT_ENGAGE_DISTANCE_M) > 1e-6:
                normalized['engage_distance_m'] = round(engage_value, 2)
        return normalized

    def _normalize_behavior_strategy(self, strategy):
        if not isinstance(strategy, dict):
            return {}
        normalized = {}
        stages = []
        raw_stages = strategy.get('stages', None)
        if isinstance(raw_stages, list):
            for stage in raw_stages[:self.MAX_STRATEGY_STAGES]:
                normalized_stage = self._normalize_behavior_stage(stage)
                if normalized_stage:
                    stages.append(normalized_stage)
        else:
            normalized_stage = self._normalize_behavior_stage(strategy)
            if normalized_stage:
                stages.append(normalized_stage)
        if stages:
            normalized['stages'] = stages
        return normalized

    def _behavior_override_stages(self, override):
        if not isinstance(override, dict):
            return []
        strategy = self._normalize_behavior_strategy(override.get('strategy', {}))
        return [dict(stage) for stage in strategy.get('stages', []) if isinstance(stage, dict)]

    def _behavior_override_strategy(self, override):
        stages = self._behavior_override_stages(override)
        return dict(stages[0]) if stages else {}

    def get_available_decision_plugins(self, role_key):
        if self._decision_system_disabled():
            if role_key == self.COMMON_ROLE_KEY:
                return []
            return [{
                'id': self.TODO_DECISION_ID,
                'label': self.TODO_ROLE_LABELS.get(role_key, '决策系统 TODO'),
                'description': '当前旧决策系统已移除，后续将在此接口上重建设计。',
                'fallback': True,
                'order': 0,
            }]
        return [dict(binding) for binding in self._available_plugin_bindings_for_role(role_key)]

    def _canonical_decision_id(self, decision_id):
        decision_id = str(decision_id or '').strip()
        return self.MERGED_DECISION_ALIASES.get(decision_id, decision_id)

    def _decision_alias_ids(self, decision_id):
        canonical_id = self._canonical_decision_id(decision_id)
        aliases = [canonical_id]
        aliases.extend(alias for alias, target in self.MERGED_DECISION_ALIASES.items() if target == canonical_id)
        return tuple(dict.fromkeys(aliases))

    def _role_decision_order_override(self, role_key, available_ids):
        role_entry = self._behavior_override_roles().get(role_key, {})
        order = role_entry.get('decision_order') if isinstance(role_entry, dict) else None
        if order is None:
            return list(available_ids)
        if not isinstance(order, list):
            return list(available_ids)
        filtered = []
        seen = set()
        available = set(available_ids)
        for decision_id in order:
            canonical_id = self._canonical_decision_id(decision_id)
            if canonical_id not in available or canonical_id in seen:
                continue
            filtered.append(canonical_id)
            seen.add(canonical_id)
        return filtered

    def _default_role_decision_specs(self):
        condition_registry = self._behavior_condition_registry()
        action_registry = self._behavior_action_registry()
        specs_by_role = {}
        for role_key in ('sentry', 'infantry', 'hero', 'engineer'):
            bindings = self._available_plugin_bindings_for_role(role_key)
            if not bindings:
                continue
            binding_by_id = {binding['id']: binding for binding in bindings}
            active_ids = self._role_decision_order_override(role_key, binding_by_id)
            role_specs = []
            for decision_id in active_ids:
                binding = binding_by_id.get(decision_id)
                if binding is None:
                    continue
                action = binding.get('action') if callable(binding.get('action')) else None
                if action is not None:
                    action = (lambda ctx, plugin_action=action, plugin_binding=dict(binding), plugin_role=role_key: plugin_action(self, ctx, plugin_role, plugin_binding))
                else:
                    action_ref = str(binding.get('action_ref', decision_id)).strip()
                    action = action_registry.get(action_ref)
                if action is None:
                    continue
                condition_ref = str(binding.get('condition_ref', '')).strip()
                fallback = bool(binding.get('fallback', False) or not condition_ref)
                condition = binding.get('condition') if callable(binding.get('condition')) else None
                if condition is not None:
                    condition = (lambda ctx, plugin_condition=condition, plugin_binding=dict(binding), plugin_role=role_key: plugin_condition(self, ctx, plugin_role, plugin_binding))
                elif not fallback:
                    condition = condition_registry.get(condition_ref)
                if not fallback and condition is None:
                    continue
                role_specs.append(self._decision_spec(
                    decision_id,
                    str(binding.get('label', decision_id)),
                    condition,
                    action,
                    fallback=fallback,
                    default_destination_types=tuple(binding.get('default_destination_types', ())),
                    terrain_mode=binding.get('terrain_mode'),
                    description=binding.get('description', ''),
                    editable_targets=tuple(binding.get('editable_targets', ())),
                ))
            if role_specs:
                specs_by_role[role_key] = role_specs
        return specs_by_role or self._legacy_default_role_decision_specs()

    def _parse_xml_bool(self, raw_value):
        return str(raw_value or '').strip().lower() in {'1', 'true', 'yes', 'on'}

    def _resolve_behavior_override_path(self):
        behavior_preset = str(self.config.get('ai', {}).get('behavior_preset', '') or '').strip()
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if behavior_preset:
            if os.path.isabs(behavior_preset):
                return behavior_preset
            preset_ref = behavior_preset if behavior_preset.lower().endswith('.json') else f'{behavior_preset}.json'
            return os.path.join(workspace_root, 'behavior_presets', preset_ref)
        fallback_path = os.path.join(workspace_root, 'behavior_presets', 'latest_behavior.json')
        return fallback_path if os.path.exists(fallback_path) else None

    def _load_behavior_override_payload(self):
        override_path = self._resolve_behavior_override_path()
        if override_path is None or not os.path.exists(override_path):
            return {}
        try:
            with open(override_path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _safe_file_mtime(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return None
        try:
            return os.path.getmtime(file_path)
        except OSError:
            return None

    def _reload_behavior_settings_if_needed(self):
        settings_path = self.config.get('_settings_path')
        settings_mtime = self._safe_file_mtime(settings_path)
        if settings_mtime is None or settings_mtime == self._settings_mtime:
            return False
        self._settings_mtime = settings_mtime
        try:
            with open(settings_path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            return False
        ai_payload = payload.get('ai', {}) if isinstance(payload, dict) else {}
        if not isinstance(ai_payload, dict):
            return False
        current_preset = str(self.config.get('ai', {}).get('behavior_preset', '') or '').strip()
        next_preset = str(ai_payload.get('behavior_preset', '') or '').strip()
        if next_preset == current_preset:
            return False
        self.config.setdefault('ai', {})['behavior_preset'] = next_preset
        return True

    def _refresh_behavior_runtime_overrides(self, force=False):
        settings_changed = self._reload_behavior_settings_if_needed()
        override_path = self._resolve_behavior_override_path()
        override_mtime = self._safe_file_mtime(override_path)
        changed = bool(
            force
            or settings_changed
            or override_path != self._behavior_override_path
            or override_mtime != self._behavior_override_mtime
        )
        if not changed:
            return False
        self._behavior_override_path = override_path
        self._behavior_override_mtime = override_mtime
        self._behavior_override_payload = self._load_behavior_override_payload()
        self.role_decision_specs = self._build_todo_role_decision_specs()
        self.role_trees = {}
        return True

    def _decision_system_disabled(self):
        return True

    def _todo_decision_action(self, context):
        return self._idle_navigation_decision(context, 'TODO: 决策系统待重构，当前仅保留占位接口')

    def _build_todo_role_decision_specs(self):
        specs = {}
        for role_key in ('sentry', 'infantry', 'hero', 'engineer'):
            specs[role_key] = [
                self._decision_spec(
                    self.TODO_DECISION_ID,
                    self.TODO_ROLE_LABELS.get(role_key, '决策系统 TODO'),
                    None,
                    self._todo_decision_action,
                    fallback=True,
                    description='当前旧决策系统已移除，后续将在此接口上重建设计。',
                )
            ]
        return specs

    def _behavior_condition_registry(self):
        return {
            'front_gun_locked': lambda ctx: getattr(ctx.entity, 'front_gun_locked', False),
            'recover_after_respawn': self._should_recover_after_respawn,
            'emergency_defend_base': self._should_emergency_defend_base,
            'critical_state': self._is_critical_state,
            'sentry_opening_highground': self._should_sentry_opening_highground,
            'sentry_fly_slope': self._should_sentry_fly_slope,
            'force_push_base': self._should_force_push_base,
            'has_target': self._has_target,
            'protect_hero': self._should_protect_hero,
            'take_enemy_highground': self._should_take_enemy_highground,
            'support_infantry_push': self._should_support_infantry_push,
            'support_engineer': self._should_support_engineer,
            'intercept_enemy_engineer': self._should_intercept_enemy_engineer,
            'push_outpost': self._should_push_outpost,
            'teamfight_window': self._has_teamfight_window,
            'push_base': self._should_push_base,
            'cross_terrain': self._should_cross_terrain,
            'terrain_fly_slope': self._should_terrain_fly_slope,
            'terrain_first_step': self._should_terrain_first_step,
            'terrain_second_step': self._should_terrain_second_step,
            'must_restock': self._must_restock_before_combat,
            'needs_supply': self._needs_supply,
            'infantry_opening_highground': self._should_infantry_opening_highground,
            'activate_energy': self._should_activate_energy,
            'hero_seek_cover': self._should_hero_seek_cover,
            'hero_opening_highground': self._should_hero_opening_highground,
            'hero_melee_highground_assault': self._should_hero_melee_highground_assault,
            'hero_lob_outpost': self._should_hero_lob_outpost,
            'hero_lob_base': self._should_hero_lob_base,
            'engineer_exchange': self._needs_engineer_exchange,
            'engineer_mine': self._needs_engineer_mining,
        }

    def _behavior_action_registry(self):
        return {
            'return_to_supply_unlock': self._action_return_to_supply_unlock,
            'recover_after_respawn': self._action_recover_after_respawn,
            'emergency_defend_base': self._action_emergency_defend_base,
            'emergency_retreat': self._action_emergency_retreat,
            'sentry_opening_highground': self._action_sentry_opening_highground,
            'sentry_fly_slope': self._action_sentry_fly_slope,
            'push_base': self._action_push_base,
            'swarm_attack': self._action_swarm_attack,
            'protect_hero': self._action_protect_hero,
            'highground_assault': self._action_highground_assault,
            'support_infantry_push': self._action_support_infantry_push,
            'support_engineer': self._action_support_engineer,
            'intercept_enemy_engineer': self._action_intercept_enemy_engineer,
            'push_outpost': self._action_push_outpost,
            'teamfight_cover': self._action_teamfight_cover,
            'teamfight_push': self._action_teamfight_push,
            'cross_terrain': self._action_cross_terrain,
            'terrain_fly_slope': self._action_terrain_fly_slope,
            'terrain_first_step': self._action_terrain_first_step,
            'terrain_second_step': self._action_terrain_second_step,
            'patrol_key_facilities': self._action_patrol_key_facilities,
            'opening_supply': self._action_opening_supply,
            'infantry_opening_highground': self._action_infantry_opening_highground,
            'activate_energy': self._action_activate_energy,
            'hero_seek_cover': self._action_hero_seek_cover,
            'hero_opening_highground': self._action_hero_opening_highground,
            'hero_lob_outpost': self._action_hero_lob_outpost,
            'hero_lob_base': self._action_hero_lob_base,
            'engineer_exchange': self._action_engineer_exchange,
            'engineer_mine': self._action_engineer_mine,
            'engineer_cycle': self._action_engineer_cycle,
        }

    def _behavior_override_roles(self):
        roles = self._behavior_override_payload.get('roles', {})
        return roles if isinstance(roles, dict) else {}

    def _behavior_override_for_decision(self, role_key, decision_id):
        role_entry = self._behavior_override_roles().get(role_key, {})
        decisions = role_entry.get('decisions', {}) if isinstance(role_entry, dict) else {}
        if not isinstance(decisions, dict):
            return {}
        merged = {}
        for candidate_id in self._decision_alias_ids(decision_id):
            override = decisions.get(candidate_id, {})
            if isinstance(override, dict):
                merged.update(deepcopy(override))
        return merged

    def _behavior_override_time_ok(self, game_time, override):
        window = override.get('time_window', {}) if isinstance(override, dict) else {}
        if not isinstance(window, dict):
            return True
        start_sec = window.get('start_sec')
        end_sec = window.get('end_sec')
        try:
            if start_sec is not None and str(start_sec) != '' and float(game_time) < float(start_sec):
                return False
            if end_sec is not None and str(end_sec) != '' and float(game_time) > float(end_sec):
                return False
        except (TypeError, ValueError):
            return True
        return True

    def _behavior_override_expression_vars(self, context):
        entity = context.entity
        enemy_outpost = context.data.get('enemy_outpost')
        enemy_base = context.data.get('enemy_base')
        return {
            'game_time': float(context.game_time),
            'ammo': float(getattr(entity, 'ammo', 0)),
            'health_ratio': float(context.data.get('health_ratio', 1.0)),
            'heat_ratio': float(context.data.get('heat_ratio', 0.0)),
            'has_target': bool(context.data.get('target') is not None),
            'outnumbered': bool(context.data.get('outnumbered', False)),
            'opening_phase': bool(context.data.get('opening_phase', False)),
            'base_assault_unlocked': bool(context.data.get('base_assault_unlocked', False)),
            'emergency_base_defense': bool(context.data.get('emergency_base_defense', False)),
            'front_gun_locked': bool(getattr(entity, 'front_gun_locked', False)),
            'hero_ranged': bool(self._hero_prefers_ranged(entity)),
            'hero_melee': bool(self._hero_prefers_melee(entity)),
            'enemy_outpost_alive': bool(enemy_outpost is not None and enemy_outpost.is_alive()),
            'enemy_base_alive': bool(enemy_base is not None and enemy_base.is_alive()),
            'carried_minerals': float(context.data.get('carried_minerals', 0)),
            'team_health_ratio': float(context.data.get('team_health_ratio', 0.0)),
            'needs_heal_supply': bool(context.data.get('needs_heal_supply', False)),
            'in_supply_zone': bool(self._is_in_facility_zone(entity, context.map_manager, 'supply')),
            'in_deployment_zone': bool(getattr(entity, 'hero_deployment_zone_active', False)),
        }

    def _eval_behavior_expr_node(self, node, variables):
        if isinstance(node, ast.Expression):
            return self._eval_behavior_expr_node(node.body, variables)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return variables.get(node.id, False)
        if isinstance(node, ast.BoolOp):
            values = [bool(self._eval_behavior_expr_node(value, variables)) for value in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_behavior_expr_node(node.operand, variables)
            if isinstance(node.op, ast.Not):
                return not bool(operand)
            if isinstance(node.op, ast.USub):
                return -float(operand)
            if isinstance(node.op, ast.UAdd):
                return float(operand)
        if isinstance(node, ast.BinOp):
            left = self._eval_behavior_expr_node(node.left, variables)
            right = self._eval_behavior_expr_node(node.right, variables)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
        if isinstance(node, ast.Compare):
            left = self._eval_behavior_expr_node(node.left, variables)
            for operator_node, comparator in zip(node.ops, node.comparators):
                right = self._eval_behavior_expr_node(comparator, variables)
                if isinstance(operator_node, ast.Eq):
                    ok = left == right
                elif isinstance(operator_node, ast.NotEq):
                    ok = left != right
                elif isinstance(operator_node, ast.Gt):
                    ok = left > right
                elif isinstance(operator_node, ast.GtE):
                    ok = left >= right
                elif isinstance(operator_node, ast.Lt):
                    ok = left < right
                elif isinstance(operator_node, ast.LtE):
                    ok = left <= right
                elif isinstance(operator_node, ast.In):
                    ok = left in right
                elif isinstance(operator_node, ast.NotIn):
                    ok = left not in right
                else:
                    return False
                if not ok:
                    return False
                left = right
            return True
        raise ValueError('unsupported expression node')

    def _behavior_override_expression_ok(self, context, override):
        expression = str(override.get('condition_expr', '') or '').strip()
        if not expression:
            return True
        try:
            tree = ast.parse(expression, mode='eval')
            return bool(self._eval_behavior_expr_node(tree, self._behavior_override_expression_vars(context)))
        except Exception:
            return False

    def _behavior_override_team_regions(self, override, field_name, team=None):
        if not isinstance(override, dict):
            return []
        def collect_regions(base_field_name):
            regions = []
            shared_regions = override.get(base_field_name, [])
            if isinstance(shared_regions, list):
                regions.extend(region for region in shared_regions if isinstance(region, dict))
            if team is not None:
                by_team = override.get(f'{base_field_name}_by_team', {})
                team_regions = by_team.get(team, []) if isinstance(by_team, dict) else []
                if isinstance(team_regions, list):
                    explicit = [region for region in team_regions if isinstance(region, dict)]
                    if explicit:
                        return explicit
            return regions

        if field_name == 'behavior_regions':
            regions = collect_regions('behavior_regions')
            if regions:
                return regions
            legacy_regions = []
            for region in collect_regions('task_regions') + collect_regions('destination_regions'):
                if region not in legacy_regions:
                    legacy_regions.append(region)
            return legacy_regions
        return collect_regions(field_name)

    def _behavior_override_regions(self, override, team=None):
        return self._behavior_override_team_regions(override, 'behavior_regions', team=team)

    def _behavior_override_destination_regions(self, override, team=None):
        return self._behavior_override_team_regions(override, 'behavior_regions', team=team)

    def _behavior_override_point_targets(self, override, team=None):
        specs = self._behavior_override_point_target_specs(override, team=team)
        return {
            key: (float(spec['x']), float(spec['y']))
            for key, spec in specs.items()
        }

    def _behavior_override_point_target_specs(self, override, team=None):
        if not isinstance(override, dict):
            return {}
        merged = self._normalize_behavior_point_target_specs(override.get('point_targets', {}))
        if team is None:
            return merged
        by_team = override.get('point_targets_by_team', {})
        team_targets = by_team.get(team, {}) if isinstance(by_team, dict) else {}
        merged.update(self._normalize_behavior_point_target_specs(team_targets))
        return merged

    def _strategy_reference_entity(self, context, ref_id):
        ref_id = str(ref_id or '').strip()
        if not ref_id:
            return None
        if ref_id == 'enemy_any_unit':
            nearest = self._nearest_enemy_by_roles(
                context.entities,
                context.entity.team,
                (context.entity.position['x'], context.entity.position['y']),
                ('hero', 'infantry', 'engineer', 'sentry'),
            )
            return nearest.get('entity') if isinstance(nearest, dict) else None
        if ref_id == 'enemy_any_facility':
            candidates = [context.data.get('enemy_outpost'), context.data.get('enemy_base')]
            best_entity = None
            best_distance = None
            for entity in candidates:
                if entity is None or not entity.is_alive():
                    continue
                distance = self._distance(context.entity, entity)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_entity = entity
            return best_entity
        if ref_id == 'enemy_outpost':
            entity = context.data.get('enemy_outpost')
            return entity if entity is not None and entity.is_alive() else None
        if ref_id == 'enemy_base':
            entity = context.data.get('enemy_base')
            return entity if entity is not None and entity.is_alive() else None
        if ref_id == 'ally_hero':
            return context.data.get('allied_hero')
        if ref_id == 'ally_infantry':
            return context.data.get('allied_infantry')
        if ref_id == 'ally_engineer':
            return context.data.get('allied_engineer')
        if ref_id == 'ally_sentry':
            return context.data.get('allied_sentry')
        if ref_id == 'enemy_hero':
            return context.data.get('enemy_hero')
        if ref_id == 'enemy_engineer':
            return context.data.get('enemy_engineer')
        if ref_id == 'enemy_infantry':
            nearest = self._nearest_enemy_by_roles(
                context.entities,
                context.entity.team,
                (context.entity.position['x'], context.entity.position['y']),
                ('infantry',),
            )
            return nearest.get('entity') if isinstance(nearest, dict) else None
        if ref_id == 'enemy_sentry':
            nearest = self._nearest_enemy_by_roles(
                context.entities,
                context.entity.team,
                (context.entity.position['x'], context.entity.position['y']),
                ('sentry',),
            )
            return nearest.get('entity') if isinstance(nearest, dict) else None
        return None

    def _strategy_reference_point(self, context, ref_id):
        ref_id = str(ref_id or '').strip()
        if not ref_id:
            return None
        entity = self._strategy_reference_entity(context, ref_id)
        if entity is not None:
            return (float(entity.position['x']), float(entity.position['y']))
        if ref_id == 'own_supply':
            return self.get_team_anchor(context.entity.team, 'supply', context.map_manager, entity=context.entity)
        if ref_id == 'own_base':
            return self.get_team_anchor(context.entity.team, 'base', context.map_manager, entity=context.entity)
        if ref_id == 'own_outpost':
            entity = context.data.get('own_outpost')
            if entity is not None:
                return (float(entity.position['x']), float(entity.position['y']))
        if ref_id == 'enemy_outpost_anchor':
            entity = context.data.get('enemy_outpost')
            if entity is not None and entity.is_alive():
                return (float(entity.position['x']), float(entity.position['y']))
        if ref_id == 'enemy_base_anchor':
            entity = context.data.get('enemy_base')
            if entity is not None and entity.is_alive():
                return (float(entity.position['x']), float(entity.position['y']))
        if ref_id == 'map_center':
            return context.data.get('map_center')
        return None

    def _resolve_strategy_reference(self, context, ref_id):
        ref_id = str(ref_id or '').strip()
        if not ref_id:
            return None
        entity = self._strategy_reference_entity(context, ref_id)
        if entity is not None:
            return {
                'kind': 'entity',
                'reference': ref_id,
                'entity': entity,
                'target': self.entity_to_target(entity, context.entity),
                'point': (float(entity.position['x']), float(entity.position['y'])),
            }
        point = self._strategy_reference_point(context, ref_id)
        if point is None:
            return None
        resolved = self._resolve_navigation_target(point, context.map_manager, entity=context.entity) if context.map_manager is not None else point
        if resolved is None:
            return None
        return {
            'kind': 'point',
            'reference': ref_id,
            'entity': None,
            'target': None,
            'point': (float(resolved[0]), float(resolved[1])),
        }

    def _strategy_destination_target(self, context, override, strategy):
        destination_mode = str(strategy.get('destination_mode', 'region') or 'region')
        if destination_mode == 'none':
            return None
        if destination_mode == 'reference':
            return self._resolve_strategy_reference(context, strategy.get('destination_ref', ''))
        destination_point = self._behavior_override_destination_center(context, override)
        if destination_point is None:
            return None
        return {
            'kind': 'point',
            'reference': 'region',
            'entity': None,
            'target': None,
            'point': (float(destination_point[0]), float(destination_point[1])),
        }

    def _strategy_ordered_node_targets(self, override, team=None):
        return [node['point'] for node in self._strategy_ordered_node_specs(override, team=team)]

    def _resolve_ordered_route_specs(self, entity, override, map_manager):
        resolved_specs = []
        seen = set()
        for node_spec in self._strategy_ordered_node_specs(override, team=getattr(entity, 'team', None))[:self.MAX_STRATEGY_STAGES]:
            point = node_spec.get('point')
            if point is None:
                continue
            resolved = self._resolve_navigation_target(point, map_manager, entity=entity) if map_manager is not None else point
            if resolved is None:
                continue
            normalized = (float(resolved[0]), float(resolved[1]))
            key = (round(normalized[0], 1), round(normalized[1], 1))
            if key in seen:
                continue
            seen.add(key)
            resolved_specs.append({
                'id': str(node_spec.get('id', f'node_{len(resolved_specs) + 1}')),
                'index': int(node_spec.get('index', len(resolved_specs) + 1) or len(resolved_specs) + 1),
                'point': normalized,
                'radius': self._strategy_node_radius(node_spec, map_manager),
            })
        return resolved_specs

    def _decision_navigation_speed(self, decision, map_manager=None):
        speed = math.hypot(*tuple(decision.get('velocity', (0.0, 0.0))))
        if speed > 1e-6:
            return speed
        return self._meters_to_world_units(1.5, map_manager)

    def _apply_override_route_points(self, context, override):
        decision = context.data.get('decision')
        if not isinstance(decision, dict):
            return
        final_target = decision.get('navigation_target')
        if final_target is None:
            self._clear_route_progress(context.entity, 'override_route_points')
            return
        route_specs = self._resolve_ordered_route_specs(context.entity, override, context.map_manager)
        if not route_specs:
            self._clear_route_progress(context.entity, 'override_route_points')
            return

        active_target = (float(final_target[0]), float(final_target[1]))
        active_radius = float(decision.get('navigation_radius', 0.0) or 0.0)
        active_spec, active_index = self._advance_route_progress(context.entity, 'override_route_points', route_specs, context.map_manager)
        if active_spec is not None:
            active_target = active_spec['point']
            active_radius = float(active_spec['radius'])
            remaining_route_specs = route_specs[active_index:]
        else:
            remaining_route_specs = []

        staged_target = getattr(context.entity, 'ai_navigation_waypoint', None) or active_target
        speed = self._decision_navigation_speed(decision, context.map_manager)
        velocity = self.navigate_towards(context.entity, active_target, speed, context.map_manager)
        velocity = self._apply_local_avoidance(context.entity, velocity, context.entities, staged_target)
        decision['movement_target'] = staged_target
        decision['velocity'] = velocity
        decision['navigation_radius'] = active_radius
        decision['route_points'] = tuple((spec['point'][0], spec['point'][1], spec['radius']) for spec in remaining_route_specs)
        if active_spec is not None:
            decision['active_route_index'] = 0
        else:
            decision.pop('active_route_index', None)

    def _strategy_node_default_radius(self, map_manager=None):
        return max(18.0, self._meters_to_world_units(0.55, map_manager))

    def _strategy_ordered_node_specs(self, override, team=None):
        target_specs = self._behavior_override_point_target_specs(override, team=team)
        ordered = []
        for target_id, point_spec in target_specs.items():
            if not str(target_id).startswith('node_'):
                continue
            suffix = str(target_id).split('_', 1)[1]
            try:
                sort_key = int(suffix)
            except ValueError:
                continue
            ordered.append((
                sort_key,
                {
                    'id': str(target_id),
                    'index': sort_key,
                    'point': (float(point_spec['x']), float(point_spec['y'])),
                    'radius': float(point_spec.get('radius', 0.0) or 0.0),
                },
            ))
        ordered.sort(key=lambda item: item[0])
        return [spec for _, spec in ordered]

    def _random_point_in_behavior_region(self, region, rng):
        if region is None:
            return None
        shape = str(region.get('shape', 'rect'))
        if shape == 'circle':
            radius = max(1.0, float(region.get('radius', 0.0)))
            angle = rng.uniform(0.0, math.tau)
            distance = radius * math.sqrt(rng.random())
            center = self._behavior_region_center(region)
            if center is None:
                return None
            return (
                float(center[0]) + math.cos(angle) * distance,
                float(center[1]) + math.sin(angle) * distance,
            )
        if shape == 'polygon':
            points = [tuple(point) for point in region.get('points', []) if isinstance(point, (list, tuple)) and len(point) >= 2]
            if not points:
                return None
            min_x = min(float(point[0]) for point in points)
            max_x = max(float(point[0]) for point in points)
            min_y = min(float(point[1]) for point in points)
            max_y = max(float(point[1]) for point in points)
            for _ in range(18):
                candidate = (rng.uniform(min_x, max_x), rng.uniform(min_y, max_y))
                if self._point_in_behavior_region(candidate, region):
                    return candidate
            return self._behavior_region_center(region)
        x1 = min(float(region.get('x1', 0.0)), float(region.get('x2', 0.0)))
        x2 = max(float(region.get('x1', 0.0)), float(region.get('x2', 0.0)))
        y1 = min(float(region.get('y1', 0.0)), float(region.get('y2', 0.0)))
        y2 = max(float(region.get('y1', 0.0)), float(region.get('y2', 0.0)))
        return (rng.uniform(x1, x2), rng.uniform(y1, y2))

    def _behavior_region_preview_points(self, region):
        shape = str(region.get('shape', 'rect'))
        center = self._behavior_region_center(region)
        if center is None:
            return []
        candidates = [(float(center[0]), float(center[1]))]
        if shape == 'circle':
            radius = max(6.0, float(region.get('radius', 0.0)) * 0.45)
            cx, cy = center
            candidates.extend([
                (cx + radius, cy),
                (cx - radius, cy),
                (cx, cy + radius),
                (cx, cy - radius),
            ])
        elif shape == 'polygon':
            points = list(region.get('points', []))
            for point in points[:4]:
                candidates.append((float(point[0]), float(point[1])))
        else:
            x1 = min(float(region.get('x1', center[0])), float(region.get('x2', center[0])))
            x2 = max(float(region.get('x1', center[0])), float(region.get('x2', center[0])))
            y1 = min(float(region.get('y1', center[1])), float(region.get('y2', center[1])))
            y2 = max(float(region.get('y1', center[1])), float(region.get('y2', center[1])))
            candidates.extend([
                (x1 + (x2 - x1) * 0.25, y1 + (y2 - y1) * 0.25),
                (x1 + (x2 - x1) * 0.75, y1 + (y2 - y1) * 0.25),
                (x1 + (x2 - x1) * 0.25, y1 + (y2 - y1) * 0.75),
                (x1 + (x2 - x1) * 0.75, y1 + (y2 - y1) * 0.75),
            ])
        return candidates

    def _strategy_pick_patrol_point(self, context, regions, state_key):
        if not regions:
            return None
        state = self._strategy_patrol_state.get(state_key, {'index': 0, 'point': None})
        current_point = state.get('point')
        if current_point is not None and not self._is_target_reached(context.entity, current_point, context.map_manager):
            return current_point
        region_index = int(state.get('index', 0)) % len(regions)
        region = regions[region_index]
        rng = random.Random(f'{state_key}:{int(state.get("index", 0))}')
        candidates = []
        for _ in range(12):
            candidate = self._random_point_in_behavior_region(region, rng)
            if candidate is not None:
                candidates.append(candidate)
        candidates.extend(self._behavior_region_preview_points(region))
        for candidate in candidates:
            resolved = self._resolve_navigation_target(candidate, context.map_manager, entity=context.entity) if context.map_manager is not None else candidate
            if resolved is None:
                continue
            if self._point_in_behavior_region(resolved, region):
                point = (float(resolved[0]), float(resolved[1]))
                self._strategy_patrol_state[state_key] = {'index': int(state.get('index', 0)) + 1, 'point': point}
                return point
        center = self._behavior_region_center(region)
        if center is None:
            return None
        resolved = self._resolve_navigation_target(center, context.map_manager, entity=context.entity) if context.map_manager is not None else center
        if resolved is None:
            return None
        point = (float(resolved[0]), float(resolved[1]))
        self._strategy_patrol_state[state_key] = {'index': int(state.get('index', 0)) + 1, 'point': point}
        return point

    def _strategy_trackable_reference(self, context, resolved, max_distance=None):
        if not isinstance(resolved, dict):
            return None
        entity = resolved.get('entity')
        if entity is None:
            return resolved
        if not entity.is_alive():
            return None
        distance = self._distance(context.entity, entity)
        if max_distance is not None and distance > max_distance:
            return None
        rules_engine = context.rules_engine
        if rules_engine is not None and context.entity.type in {'robot', 'sentry'}:
            if not rules_engine.can_track_target(context.entity, entity, distance=distance):
                return None
        return {
            'kind': 'entity',
            'reference': resolved.get('reference'),
            'entity': entity,
            'target': self.entity_to_target(entity, context.entity),
            'point': (float(entity.position['x']), float(entity.position['y'])),
        }

    def _strategy_patrol_decision(self, context, spec_label, override, strategy, summary):
        patrol_regions = self._behavior_override_regions(override, team=context.entity.team)
        patrol_key = (context.entity.id, spec_label, context.entity.team, 'patrol')
        patrol_point = self._strategy_pick_patrol_point(context, patrol_regions, patrol_key)
        if patrol_point is None:
            patrol_destination = self._strategy_destination_target(context, override, strategy)
            patrol_point = patrol_destination.get('point') if patrol_destination is not None else None
        if patrol_point is None:
            return FAILURE
        return self._set_decision(
            context,
            summary,
            target=None,
            target_point=patrol_point,
            speed=self._meters_to_world_units(1.45, context.map_manager),
            preferred_route={'target': patrol_point},
            turret_state='searching',
            angular_velocity=18.0,
        )

    def _stage_summary_prefix(self, spec_label, stage_index, stage_total):
        return f'{spec_label} 阶段{stage_index + 1}/{stage_total}' if stage_total > 1 else str(spec_label)

    def _stage_destination_completed(self, context, override, stage):
        destination_mode = str(stage.get('destination_mode', 'region') or 'region')
        if destination_mode == 'none':
            return True
        if str(stage.get('task_type', 'default') or 'default') == 'terrain_traversal' and destination_mode == 'region':
            return True
        if destination_mode == 'region':
            return self._behavior_override_inside_destination(context, override)
        destination = self._strategy_destination_target(context, override, stage)
        if destination is None or destination.get('point') is None:
            return False
        return self._is_target_reached(context.entity, destination['point'], context.map_manager)

    def _strategy_node_radius(self, node_spec, map_manager=None):
        return max(self._strategy_node_default_radius(map_manager), float((node_spec or {}).get('radius', 0.0) or 0.0))

    def _strategy_interaction_point(self, context, interaction_ref):
        interaction_ref = str(interaction_ref or 'own_supply')
        if interaction_ref == 'own_supply':
            return self._supply_navigation_anchor(context.entity, context.map_manager)
        if interaction_ref == 'mining_area':
            return context.data.get('mining_anchor') or self.get_mining_anchor(context.entity, context.map_manager)
        if interaction_ref == 'energy_mechanism':
            return context.data.get('energy_anchor') or self.get_energy_anchor(context.entity.team, context.map_manager)
        return None

    def _strategy_high_threat_enemy(self, context, override):
        defend_regions = self._behavior_override_regions(override, team=context.entity.team)
        if not defend_regions:
            return None
        best_enemy = None
        best_score = None
        for enemy in context.entities:
            if enemy.team == context.entity.team or not enemy.is_alive() or enemy.type not in {'robot', 'sentry'}:
                continue
            point = (float(enemy.position['x']), float(enemy.position['y']))
            closest_distance = min((self._distance_to_region(point, region) for region in defend_regions), default=float('inf'))
            if closest_distance > self._meters_to_world_units(2.0, context.map_manager):
                continue
            score = self._priority_target_threat_score(context.entity, enemy)
            score += max(0.0, 240.0 - closest_distance * 0.8)
            if getattr(enemy, 'last_damage_source_id', None) in {getattr(context.data.get('own_base'), 'id', None), getattr(context.data.get('own_outpost'), 'id', None)}:
                score += 120.0
            if best_score is None or score > best_score:
                best_score = score
                best_enemy = enemy
        if best_enemy is None:
            return None
        return {
            'entity': best_enemy,
            'target': self.entity_to_target(best_enemy, context.entity),
            'point': (float(best_enemy.position['x']), float(best_enemy.position['y'])),
        }

    def _strategy_defense_decision(self, context, stage_prefix, override, stage):
        defend_regions = self._behavior_override_regions(override, team=context.entity.team)
        if not defend_regions:
            return FAILURE
        defense_ref = str(stage.get('defense_ref', 'high_threat_enemy') or 'high_threat_enemy')
        defend_anchor = self._behavior_override_destination_center(context, override)
        if defend_anchor is None:
            defend_anchor = self.get_team_anchor(context.entity.team, 'base', context.map_manager, entity=context.entity)
        threat = self._strategy_high_threat_enemy(context, override)
        if threat is not None:
            target = threat.get('target')
            hold_point = threat.get('point') if defense_ref == 'high_threat_enemy' else defend_anchor
            return self._set_decision(
                context,
                f'{stage_prefix}：发现高威胁敌人，转入区域防守打击',
                target=target,
                target_point=hold_point,
                speed=self._meters_to_world_units(1.9, context.map_manager),
                preferred_route={'target': hold_point},
                turret_state='aiming' if target is not None else 'searching',
                navigation_radius=self._behavior_destination_navigation_radius(override, entity=context.entity),
            )
        if defense_ref == 'defend_base':
            base_anchor = self.get_team_anchor(context.entity.team, 'base', context.map_manager, entity=context.entity) or defend_anchor
            return self._set_decision(
                context,
                f'{stage_prefix}：回防基地并保持区域警戒',
                target=context.data.get('target'),
                target_point=base_anchor,
                speed=self._meters_to_world_units(1.7, context.map_manager),
                preferred_route={'target': base_anchor},
                turret_state='aiming' if context.data.get('target') is not None else 'searching',
                navigation_radius=self._behavior_destination_navigation_radius(override, entity=context.entity),
            )
        return self._strategy_patrol_decision(context, stage_prefix, override, stage, f'{stage_prefix}：在防守区域内巡逻搜索')

    def _apply_behavior_stage(self, context, spec_label, override, stage, stage_index, stage_total):
        stage_prefix = self._stage_summary_prefix(spec_label, stage_index, stage_total)
        task_type = str(stage.get('task_type', 'default') or 'default')

        if task_type == 'terrain_traversal':
            nodes = self._strategy_ordered_node_specs(override, team=context.entity.team)
            focus_target = context.data.get('target')
            speed = self._meters_to_world_units(1.9, context.map_manager)
            active_nodes = nodes[:self.MAX_STRATEGY_STAGES]
            progress_key = f'terrain_traversal:{int(stage_index)}'
            active_node, active_node_index = self._advance_route_progress(context.entity, progress_key, active_nodes, context.map_manager)
            if active_node is not None:
                point = active_node.get('point')
                node_radius = self._strategy_node_radius(active_node, context.map_manager)
                return self._set_decision(
                    context,
                    f'{stage_prefix}：前往跨越节点 {int(active_node.get("index", (active_node_index or 0) + 1))}/{max(1, len(active_nodes))}',
                    target=focus_target,
                    target_point=point,
                    speed=speed,
                    preferred_route={'target': point},
                    turret_state='aiming' if focus_target is not None else 'searching',
                    navigation_radius=node_radius,
                )
            self._clear_route_progress(context.entity, progress_key)
            destination = None
            if str(stage.get('destination_mode', 'region') or 'region') == 'reference':
                destination = self._strategy_destination_target(context, override, stage)
            if destination is not None and destination.get('point') is not None and not self._stage_destination_completed(context, override, stage):
                destination_target = destination.get('target') or focus_target
                destination_point = destination.get('point')
                return self._set_decision(
                    context,
                    f'{stage_prefix}：跨越完成后转入阶段目标',
                    target=destination_target,
                    target_point=destination_point,
                    speed=speed,
                    preferred_route={'target': destination_point},
                    turret_state='aiming' if destination_target is not None else 'searching',
                )
            return SUCCESS

        if task_type == 'assault':
            assault_ref = stage.get('assault_ref', 'enemy_any_unit') or 'enemy_any_unit'
            follow_priority = str(stage.get('assault_follow_priority', 'target_first') or 'target_first')
            resolved = self._resolve_strategy_reference(context, assault_ref)
            destination = self._strategy_destination_target(context, override, stage)
            tracked = self._strategy_trackable_reference(context, resolved) if resolved is not None else None
            if follow_priority == 'destination_first' and str(stage.get('destination_mode', 'region') or 'region') == 'reference' and destination is not None and destination.get('point') is not None:
                destination_point = destination.get('point')
                destination_radius = self._target_region_radius(context.entity, destination_point, context.map_manager)
                if not self._is_target_reached(context.entity, destination_point, context.map_manager, navigation_radius=destination_radius):
                    return self._set_decision(
                        context,
                        f'{stage_prefix}：优先跟随引用地点进入攻击区域',
                        target=tracked.get('target') if tracked is not None else context.data.get('target'),
                        target_point=destination_point,
                        speed=self._meters_to_world_units(1.95, context.map_manager),
                        preferred_route={'target': destination_point},
                        turret_state='aiming' if tracked is not None or context.data.get('target') is not None else 'searching',
                        navigation_radius=destination_radius,
                    )
                if tracked is not None and tracked.get('target') is not None:
                    return self._set_decision(
                        context,
                        f'{stage_prefix}：占据引用地点后执行搜索打击',
                        target=tracked.get('target'),
                        target_point=destination_point,
                        speed=self._meters_to_world_units(1.7, context.map_manager),
                        preferred_route={'target': destination_point},
                        turret_state='aiming',
                        navigation_radius=destination_radius,
                    )
                return self._strategy_patrol_decision(context, stage_prefix, override, stage, f'{stage_prefix}：占据引用地点后进行区域搜索')
            resolved = tracked or destination
            if resolved is None:
                return FAILURE
            target = resolved.get('target') or context.data.get('target')
            point = resolved.get('point')
            if point is None:
                return self._strategy_patrol_decision(context, stage_prefix, override, stage, f'{stage_prefix}：目标点不可达，转入区域搜索')
            return self._set_decision(
                context,
                f'{stage_prefix}：锁定进攻目标并持续追击',
                target=target,
                target_point=point,
                speed=self._meters_to_world_units(2.1, context.map_manager),
                preferred_route={'target': point},
                turret_state='aiming' if target is not None else 'searching',
            )

        if task_type == 'field_interaction':
            interaction_ref = str(stage.get('interaction_ref', 'own_supply') or 'own_supply')
            if interaction_ref == 'own_supply':
                return self._action_opening_supply(context)
            if interaction_ref == 'energy_mechanism' and context.data.get('energy_anchor') is not None:
                return self._action_activate_energy(context)
            if interaction_ref == 'mining_area' and context.data.get('role_key') == 'engineer':
                return self._action_engineer_mine(context)
            interaction_point = self._strategy_interaction_point(context, interaction_ref)
            if interaction_point is None:
                return FAILURE
            return self._set_decision(
                context,
                f'{stage_prefix}：前往场地交互目标',
                target=context.data.get('target'),
                target_point=interaction_point,
                speed=self._meters_to_world_units(1.7, context.map_manager),
                preferred_route={'target': interaction_point},
                turret_state='aiming' if context.data.get('target') is not None else 'searching',
            )

        if task_type == 'defense':
            return self._strategy_defense_decision(context, stage_prefix, override, stage)

        if task_type == 'area_patrol':
            engage_distance_m = float(stage.get('engage_distance_m', self.DEFAULT_ENGAGE_DISTANCE_M) or self.DEFAULT_ENGAGE_DISTANCE_M)
            engage_distance_world = self._meters_to_world_units(engage_distance_m, context.map_manager)
            contact = self._strategy_area_patrol_target(context, engage_distance_world)
            if contact is not None:
                point = contact.get('point')
                target = contact.get('target')
                return self._set_decision(
                    context,
                    f'{stage_prefix}：发现近距离目标，转入直接攻击',
                    target=target,
                    target_point=point,
                    speed=self._meters_to_world_units(2.0, context.map_manager),
                    preferred_route={'target': point},
                    turret_state='aiming',
                )
            return self._strategy_patrol_decision(context, stage_prefix, override, stage, f'{stage_prefix}：在行为区域内巡航搜索')

        destination = self._strategy_destination_target(context, override, stage)
        if destination is None or destination.get('point') is None:
            return SUCCESS
        if self._stage_destination_completed(context, override, stage):
            return SUCCESS
        target = destination.get('target') or context.data.get('target')
        target_point = destination['point']
        return self._set_decision(
            context,
            f'{stage_prefix}：前往阶段目标',
            target=target,
            target_point=target_point,
            speed=self._meters_to_world_units(1.8, context.map_manager),
            preferred_route={'target': target_point},
            turret_state='aiming' if target is not None else 'searching',
        )

    def _strategy_area_patrol_target(self, context, engage_distance_world):
        enemies = [
            other
            for other in context.entities
            if other.team != context.entity.team and other.is_alive() and other.type in {'robot', 'sentry'}
        ]
        strategy = dict(context.data.get('strategy', {}))
        entity = self._select_priority_target_entity(
            context.entity,
            enemies,
            strategy,
            rules_engine=context.rules_engine,
            max_distance=engage_distance_world,
        )
        if entity is None:
            return None
        rules_engine = context.rules_engine
        if rules_engine is not None and not rules_engine.can_track_target(context.entity, entity, distance=self._distance(context.entity, entity)):
            return None
        target = self.entity_to_target(entity, context.entity)
        return {
            'kind': 'entity',
            'reference': 'enemy_within_range',
            'entity': entity,
            'target': target,
            'point': (float(target['x']), float(target['y'])),
        }

    def _apply_behavior_strategy(self, context, spec_label, override, strategy):
        stages = self._behavior_override_stages(override)
        if not stages:
            return None
        for index, stage in enumerate(stages):
            result = self._apply_behavior_stage(context, spec_label, override, stage, index, len(stages))
            if result == SUCCESS:
                continue
            return result
        return None

    def build_override_preview_script(self, context, role_key, decision_id, spec_label):
        override = self._behavior_override_for_decision(role_key, decision_id)
        stages = self._behavior_override_stages(override)
        if not stages:
            return None

        includes_terrain_stage = any(str(stage.get('task_type', 'default') or 'default') == 'terrain_traversal' for stage in stages)
        regions = [] if includes_terrain_stage else [deepcopy(region) for region in self._behavior_override_regions(override, team=context.entity.team)]
        segments = []

        for stage_index, stage in enumerate(stages):
            stage_label = self._stage_summary_prefix(spec_label, stage_index, len(stages))
            task_type = str(stage.get('task_type', 'default') or 'default')
            if task_type == 'terrain_traversal':
                for node_spec in self._strategy_ordered_node_specs(override, team=context.entity.team)[:self.MAX_STRATEGY_STAGES]:
                    point = node_spec.get('point')
                    if point is None:
                        continue
                    node_radius = self._strategy_node_radius(node_spec, context.map_manager)
                    segments.append({
                        'label': f'{stage_label} 跨越节点 {int(node_spec.get("index", 1))}',
                        'point': (float(point[0]), float(point[1])),
                        'duration_ms': 900,
                    })
                    regions.append({
                        'shape': 'circle',
                        'cx': float(point[0]),
                        'cy': float(point[1]),
                        'radius': float(node_radius),
                    })
                destination = None
                if str(stage.get('destination_mode', 'region') or 'region') == 'reference':
                    destination = self._strategy_destination_target(context, override, stage)
                if destination is not None and destination.get('point') is not None:
                    segments.append({
                        'label': f'{stage_label} 阶段目标',
                        'point': destination['point'],
                        'duration_ms': 1050,
                        'target_entity_id': destination['entity'].id if destination.get('entity') is not None else None,
                    })
                continue
            if task_type == 'assault':
                destination = self._strategy_destination_target(context, override, stage)
                resolved = self._resolve_strategy_reference(context, stage.get('assault_ref', 'enemy_any_unit') or 'enemy_any_unit')
                if str(stage.get('assault_follow_priority', 'target_first') or 'target_first') == 'destination_first' and str(stage.get('destination_mode', 'region') or 'region') == 'reference' and destination is not None and destination.get('point') is not None:
                    segments.append({
                        'label': f'{stage_label} 先进入引用地点',
                        'point': destination['point'],
                        'duration_ms': 960,
                        'target_entity_id': destination['entity'].id if destination.get('entity') is not None else None,
                    })
                    if resolved is not None and resolved.get('point') is not None:
                        segments.append({
                            'label': f'{stage_label} 地点内搜索打击',
                            'point': destination['point'],
                            'duration_ms': 980,
                            'target_entity_id': resolved['entity'].id if resolved.get('entity') is not None else None,
                        })
                    continue
                if resolved is None:
                    resolved = destination
                if resolved is not None and resolved.get('point') is not None:
                    target_point = resolved['point']
                    target_entity = resolved.get('entity')
                    if target_entity is not None:
                        dx = float(target_point[0]) - float(context.entity.position['x'])
                        dy = float(target_point[1]) - float(context.entity.position['y'])
                        length = math.hypot(dx, dy)
                        preferred_distance = self._meters_to_world_units(1.6, context.map_manager)
                        if length > 1e-6:
                            approach = (
                                float(target_point[0]) - dx / length * preferred_distance,
                                float(target_point[1]) - dy / length * preferred_distance,
                            )
                            segments.append({'label': f'{stage_label} 接近目标', 'point': approach, 'duration_ms': 950})
                    segments.append({
                        'label': f'{stage_label} 追击压制',
                        'point': (float(target_point[0]), float(target_point[1])),
                        'duration_ms': 1100,
                        'target_entity_id': target_entity.id if target_entity is not None else None,
                    })
                continue
            if task_type == 'field_interaction':
                interaction_point = self._strategy_interaction_point(context, stage.get('interaction_ref', 'own_supply') or 'own_supply')
                if interaction_point is not None:
                    segments.append({
                        'label': f'{stage_label} 场地交互',
                        'point': (float(interaction_point[0]), float(interaction_point[1])),
                        'duration_ms': 980,
                    })
                continue
            if task_type == 'defense':
                defend_regions = [deepcopy(region) for region in self._behavior_override_regions(override, team=context.entity.team)]
                regions.extend(defend_regions)
                preview_context = context
                state_key = (context.entity.id, stage_label, context.entity.team, 'defense-preview')
                self._strategy_patrol_state.pop(state_key, None)
                for _ in range(2):
                    point = self._strategy_pick_patrol_point(preview_context, defend_regions, state_key)
                    if point is None:
                        break
                    segments.append({'label': f'{stage_label} 防守巡逻', 'point': point, 'duration_ms': 760})
                threat = self._strategy_high_threat_enemy(context, override)
                if threat is not None and threat.get('point') is not None:
                    segments.append({
                        'label': f'{stage_label} 防守打击',
                        'point': threat['point'],
                        'duration_ms': 900,
                        'target_entity_id': threat['entity'].id if threat.get('entity') is not None else None,
                    })
                continue
            if task_type == 'area_patrol':
                preview_context = context
                state_key = (context.entity.id, stage_label, context.entity.team, 'preview')
                patrol_regions = [deepcopy(region) for region in self._behavior_override_regions(override, team=context.entity.team)]
                regions.extend(patrol_regions)
                self._strategy_patrol_state.pop(state_key, None)
                for _ in range(3):
                    point = self._strategy_pick_patrol_point(preview_context, patrol_regions, state_key)
                    if point is None:
                        break
                    segments.append({'label': f'{stage_label} 区域巡航', 'point': point, 'duration_ms': 760})
                contact = self._strategy_area_patrol_target(context, self._meters_to_world_units(float(stage.get('engage_distance_m', self.DEFAULT_ENGAGE_DISTANCE_M) or self.DEFAULT_ENGAGE_DISTANCE_M), context.map_manager))
                if contact is not None and contact.get('point') is not None:
                    segments.append({
                        'label': f'{stage_label} 进入攻击',
                        'point': contact['point'],
                        'duration_ms': 900,
                    })
                continue
            destination = self._strategy_destination_target(context, override, stage)
            if destination is not None and destination.get('point') is not None:
                segments.append({
                    'label': f'{stage_label} 目标导向',
                    'point': destination['point'],
                    'duration_ms': 1050,
                    'target_entity_id': destination['entity'].id if destination.get('entity') is not None else None,
                })

        if not segments:
            return None

        brief = str(override.get('brief', '') or '').strip()
        return {
            'summary': brief or f'{spec_label}：按策略脚本完整预演',
            'segments': segments,
            'regions': regions,
            'task_type': str(stages[0].get('task_type', 'default') or 'default'),
        }

    def _point_in_behavior_region(self, point, region):
        if point is None or region is None:
            return False
        shape = str(region.get('shape', 'rect'))
        px = float(point[0])
        py = float(point[1])
        if shape == 'circle':
            radius = max(0.0, float(region.get('radius', 0.0)))
            cx = float(region.get('cx', region.get('x', 0.0)))
            cy = float(region.get('cy', region.get('y', 0.0)))
            return math.hypot(px - cx, py - cy) <= radius
        if shape == 'polygon':
            points = region.get('points', [])
            if len(points) < 3:
                return False
            inside = False
            previous = points[-1]
            for current in points:
                x1 = float(previous[0])
                y1 = float(previous[1])
                x2 = float(current[0])
                y2 = float(current[1])
                intersects = ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / max((y2 - y1), 1e-6) + x1)
                if intersects:
                    inside = not inside
                previous = current
            return inside
        x1 = float(region.get('x1', 0.0))
        y1 = float(region.get('y1', 0.0))
        x2 = float(region.get('x2', 0.0))
        y2 = float(region.get('y2', 0.0))
        return min(x1, x2) <= px <= max(x1, x2) and min(y1, y2) <= py <= max(y1, y2)

    def _clear_route_progress(self, entity, progress_key=None):
        state = self._route_progress_state.get(entity.id)
        if not isinstance(state, dict):
            return
        if progress_key is None:
            self._route_progress_state.pop(entity.id, None)
            return
        state.pop(progress_key, None)
        if not state:
            self._route_progress_state.pop(entity.id, None)

    def _route_progress_signature(self, route_specs):
        return tuple(
            (
                str(route_spec.get('id', '')),
                round(float(route_spec['point'][0]), 1),
                round(float(route_spec['point'][1]), 1),
                round(float(route_spec.get('radius', 0.0) or 0.0), 1),
            )
            for route_spec in route_specs
        )

    def _advance_route_progress(self, entity, progress_key, route_specs, map_manager=None):
        if not route_specs:
            self._clear_route_progress(entity, progress_key)
            return None, None

        entity_state = self._route_progress_state.setdefault(entity.id, {})
        signature = self._route_progress_signature(route_specs)
        progress_state = entity_state.get(progress_key)
        if not isinstance(progress_state, dict) or progress_state.get('signature') != signature:
            progress_state = {
                'signature': signature,
                'index': 0,
                'best_distance': None,
            }
            entity_state[progress_key] = progress_state

        tolerance = self._arrival_tolerance_world_units(map_manager)
        index = max(0, min(int(progress_state.get('index', 0)), len(route_specs)))
        best_distance = progress_state.get('best_distance')

        while index < len(route_specs):
            route_spec = route_specs[index]
            point = route_spec['point']
            radius = max(0.0, float(route_spec.get('radius', 0.0) or 0.0))
            distance = self._distance_to_point(entity, point)
            if best_distance is None or distance < best_distance:
                best_distance = distance
            completion_window = max(radius, tolerance * 0.65)
            overshoot_margin = max(10.0, tolerance * 0.4)
            reached = self._is_target_reached(entity, point, map_manager, navigation_radius=radius)
            overshot = best_distance <= completion_window and distance > best_distance + overshoot_margin
            if not reached and not overshot:
                break
            index += 1
            best_distance = None

        progress_state['index'] = index
        progress_state['best_distance'] = best_distance
        entity_state[progress_key] = progress_state

        if index >= len(route_specs):
            return None, None
        return route_specs[index], index

    def _facility_step_side(self, point, facility, map_manager):
        if point is None or facility is None or map_manager is None:
            return 0
        center = map_manager.facility_center(facility)
        if center is None:
            return 0
        team = facility.get('team')
        if team == 'red':
            direction = -1.0
        elif team == 'blue':
            direction = 1.0
        else:
            direction = -1.0 if float(center[1]) >= float(getattr(map_manager, 'map_height', 0.0)) * 0.5 else 1.0
        delta_y = float(point[1]) - float(center[1])
        if abs(delta_y) <= max(6.0, float(getattr(map_manager, 'terrain_grid_cell_size', 0.0)) * 0.6):
            return 0
        return 1 if delta_y * direction >= 0.0 else -1

    def _engineer_second_step_yield_penalty(self, context, facility_type, facility, resolved_point):
        if facility_type != 'second_step' or context.data.get('role_key') != 'engineer':
            return 0.0
        ally_infantry = context.data.get('allied_infantry')
        if ally_infantry is None or not ally_infantry.is_alive():
            return 0.0
        map_manager = context.map_manager
        if map_manager is None:
            return 0.0
        center = map_manager.facility_center(facility)
        if center is None:
            return 0.0
        entity_point = (float(context.entity.position['x']), float(context.entity.position['y']))
        infantry_point = (float(ally_infantry.position['x']), float(ally_infantry.position['y']))
        extent = max(abs(float(facility['x2']) - float(facility['x1'])), abs(float(facility['y2']) - float(facility['y1'])))
        near_limit = max(extent * 1.7, self._meters_to_world_units(2.4, map_manager))
        if math.hypot(entity_point[0] - center[0], entity_point[1] - center[1]) > near_limit:
            return 0.0
        if math.hypot(infantry_point[0] - center[0], infantry_point[1] - center[1]) > near_limit:
            return 0.0
        entity_side = self._facility_step_side(entity_point, facility, map_manager)
        infantry_side = self._facility_step_side(infantry_point, facility, map_manager)
        target_side = self._facility_step_side(resolved_point, facility, map_manager)
        if entity_side == 0 or infantry_side == 0:
            return 0.0
        if entity_side == infantry_side:
            return 0.0
        if target_side != 0 and target_side == infantry_side:
            return 340.0
        return 220.0

    def _behavior_region_center(self, region):
        shape = str(region.get('shape', 'rect'))
        if shape == 'circle':
            return (float(region.get('cx', region.get('x', 0.0))), float(region.get('cy', region.get('y', 0.0))))
        if shape == 'polygon':
            points = region.get('points', [])
            if not points:
                return None
            sum_x = sum(float(point[0]) for point in points)
            sum_y = sum(float(point[1]) for point in points)
            return (sum_x / len(points), sum_y / len(points))
        return (
            (float(region.get('x1', 0.0)) + float(region.get('x2', 0.0))) * 0.5,
            (float(region.get('y1', 0.0)) + float(region.get('y2', 0.0))) * 0.5,
        )

    def _behavior_override_inside_entity(self, context, override):
        point = (float(context.entity.position['x']), float(context.entity.position['y']))
        regions = self._behavior_override_regions(override, team=context.entity.team)
        return any(self._point_in_behavior_region(point, region) for region in regions)

    def _nearest_behavior_override_center(self, context, override):
        best_point = None
        best_distance = None
        for region in self._behavior_override_regions(override, team=context.entity.team):
            center = self._behavior_region_center(region)
            if center is None:
                continue
            resolved = self._resolve_navigation_target(center, context.map_manager, entity=context.entity) if context.map_manager is not None else center
            if resolved is None:
                continue
            distance = self._distance_to_point(context.entity, resolved)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_point = (float(resolved[0]), float(resolved[1]))
        return best_point

    def _behavior_override_destination_center(self, context, override):
        best_point = None
        best_distance = None
        for region in self._behavior_override_regions(override, team=context.entity.team):
            center = self._behavior_region_center(region)
            if center is None:
                continue
            resolved = self._resolve_navigation_target(center, context.map_manager, entity=context.entity) if context.map_manager is not None else center
            if resolved is None:
                continue
            distance = self._distance_to_point(context.entity, resolved)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_point = (float(resolved[0]), float(resolved[1]))
        return best_point

    def _behavior_region_navigation_radius(self, region, entity=None):
        if region is None:
            return 0.0
        shape = str(region.get('shape', 'rect'))
        if shape == 'circle':
            radius = max(0.0, float(region.get('radius', 0.0)))
        elif shape == 'polygon':
            center = self._behavior_region_center(region)
            if center is None:
                radius = 0.0
            else:
                radius = max(
                    (math.hypot(float(point[0]) - center[0], float(point[1]) - center[1]) for point in region.get('points', [])),
                    default=0.0,
                )
        else:
            width = abs(float(region.get('x2', 0.0)) - float(region.get('x1', 0.0)))
            height = abs(float(region.get('y2', 0.0)) - float(region.get('y1', 0.0)))
            radius = max(width, height) * 0.35
        collision_radius = float(getattr(entity, 'collision_radius', 16.0)) if entity is not None else 0.0
        return max(radius, collision_radius * 0.6)

    def _behavior_destination_navigation_radius(self, override, entity=None):
        team = getattr(entity, 'team', None) if entity is not None else None
        radii = [self._behavior_region_navigation_radius(region, entity=entity) for region in self._behavior_override_regions(override, team=team)]
        return max(radii, default=0.0)

    def _behavior_override_inside_destination(self, context, override):
        point = (float(context.entity.position['x']), float(context.entity.position['y']))
        return any(self._point_in_behavior_region(point, region) for region in self._behavior_override_regions(override, team=context.entity.team))

    def _navigate_to_behavior_override_region(self, context, spec_label, override):
        region_target = self._nearest_behavior_override_center(context, override)
        if region_target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.8, context.map_manager)
        summary = f'{spec_label}：先进入行为区域'
        return self._set_decision(context, summary, target=context.data.get('target'), target_point=region_target, speed=speed, preferred_route={'target': region_target}, turret_state='aiming' if context.data.get('target') else 'searching')

    def _apply_behavior_destination_override(self, context, spec_label, override):
        strategy = self._behavior_override_strategy(override)
        destination_mode = str(strategy.get('destination_mode', 'region') or 'region')
        if destination_mode == 'none':
            return None
        if destination_mode == 'reference':
            resolved = self._strategy_destination_target(context, override, strategy)
            if resolved is None or resolved.get('point') is None:
                return FAILURE
            decision = context.data.get('decision')
            target = resolved.get('target') or (decision.get('target') if isinstance(decision, dict) else context.data.get('target'))
            point = resolved['point']
            if decision is None:
                speed = self._meters_to_world_units(1.8, context.map_manager)
                return self._set_decision(
                    context,
                    f'{spec_label}：前往引用目标',
                    target=target,
                    target_point=point,
                    speed=speed,
                    preferred_route={'target': point},
                    turret_state='aiming' if target is not None else 'searching',
                )
            speed = math.hypot(*decision.get('velocity', (0.0, 0.0)))
            if speed <= 1e-6:
                speed = self._meters_to_world_units(1.5, context.map_manager)
            staged_target = getattr(context.entity, 'ai_navigation_waypoint', None) or point
            velocity = self.navigate_towards(context.entity, point, speed, context.map_manager)
            velocity = self._apply_local_avoidance(context.entity, velocity, context.entities, staged_target)
            decision['summary'] = f"{decision.get('summary', spec_label)}（引用目标）"
            decision['target'] = target
            decision['navigation_target'] = point
            decision['movement_target'] = staged_target
            decision['navigation_radius'] = self._target_region_radius(context.entity, point, context.map_manager)
            decision['velocity'] = velocity
            decision['turret_state'] = 'aiming' if target is not None else decision.get('turret_state', 'searching')
            return SUCCESS

        if not self._behavior_override_regions(override, team=context.entity.team):
            return None
        destination_target = self._behavior_override_destination_center(context, override)
        if destination_target is None:
            return FAILURE
        decision = context.data.get('decision')
        target = decision.get('target') if isinstance(decision, dict) else context.data.get('target')
        turret_state = decision.get('turret_state', 'aiming' if target else 'searching') if isinstance(decision, dict) else ('aiming' if target else 'searching')
        if decision is None or not self._behavior_override_inside_destination(context, override):
            summary = f'{spec_label}：前往编辑行为区域'
            speed = self._meters_to_world_units(1.8, context.map_manager)
            return self._set_decision(context, summary, target=target, target_point=destination_target, speed=speed, preferred_route={'target': destination_target}, turret_state=turret_state)
        speed = math.hypot(*decision.get('velocity', (0.0, 0.0)))
        if speed <= 1e-6:
            speed = self._meters_to_world_units(1.45, context.map_manager)
        staged_target = getattr(context.entity, 'ai_navigation_waypoint', None) or destination_target
        velocity = self.navigate_towards(context.entity, destination_target, speed, context.map_manager)
        velocity = self._apply_local_avoidance(context.entity, velocity, context.entities, staged_target)
        decision['summary'] = f"{decision.get('summary', spec_label)}（编辑目的地）"
        decision['navigation_target'] = destination_target
        decision['movement_target'] = staged_target
        decision['navigation_radius'] = self._behavior_destination_navigation_radius(override, entity=context.entity)
        decision['velocity'] = velocity
        return SUCCESS

    def _wrap_behavior_override(self, role_key, spec, override):
        if not override:
            return spec
        fallback = bool(spec.get('fallback', False))
        original_condition = spec.get('condition')
        original_action = spec.get('action')
        enabled_state = override.get('enabled', 'default')
        strategy = self._behavior_override_strategy(override)
        terrain_strategy_active = any(
            str(stage.get('task_type', 'default') or 'default') == 'terrain_traversal'
            for stage in self._behavior_override_stages(override)
        )

        def wrapped_condition(context):
            if enabled_state is False:
                return False
            if not self._behavior_override_time_ok(context.game_time, override):
                return False
            if not self._behavior_override_expression_ok(context, override):
                return False
            if not fallback and original_condition is not None and not bool(original_condition(context)):
                return False
            if not terrain_strategy_active and str(override.get('region_mode', 'enter_then_execute')) == 'strict_inside' and self._behavior_override_regions(override):
                return self._behavior_override_inside_entity(context, override)
            return True

        def wrapped_action(context):
            if enabled_state is False:
                return FAILURE
            if not self._behavior_override_time_ok(context.game_time, override):
                return FAILURE
            if not self._behavior_override_expression_ok(context, override):
                return FAILURE
            if not terrain_strategy_active and self._behavior_override_regions(override) and not self._behavior_override_inside_entity(context, override):
                return self._navigate_to_behavior_override_region(context, override.get('label', spec.get('label', '任务')), override)
            strategy_result = self._apply_behavior_strategy(context, override.get('label', spec.get('label', '任务')), override, strategy)
            if strategy_result is not None:
                return strategy_result
            result = original_action(context)
            destination_result = self._apply_behavior_destination_override(context, override.get('label', spec.get('label', '任务')), override)
            if destination_result is not None:
                result = destination_result
            self._apply_override_route_points(context, override)
            return result

        wrapped_spec = dict(spec)
        wrapped_spec['label'] = str(override.get('label', spec.get('label', spec['id'])))
        wrapped_spec['condition'] = None if fallback else wrapped_condition
        wrapped_spec['action'] = wrapped_action
        wrapped_spec['fallback'] = fallback
        return wrapped_spec

    def _apply_behavior_overrides_to_specs(self, specs_by_role):
        wrapped_specs = {}
        for role_key, specs in specs_by_role.items():
            role_specs = []
            for spec in specs:
                override = self._behavior_override_for_decision(role_key, spec['id'])
                role_specs.append(self._wrap_behavior_override(role_key, spec, override) if override else spec)
            wrapped_specs[role_key] = role_specs
        return wrapped_specs

    def _load_role_decision_specs_from_xml(self, role_key, condition_registry, action_registry):
        file_info = self.ROLE_BEHAVIOR_TREE_FILES.get(role_key)
        if file_info is None:
            return None
        file_name, tree_id = file_info
        file_path = os.path.join(self._behavior_tree_dir, file_name)
        if not os.path.exists(file_path):
            return None
        root = ET.parse(file_path).getroot()
        behavior_tree = root.find(f".//BehaviorTree[@ID='{tree_id}']")
        if behavior_tree is None:
            return None
        branch_root = None
        for child in list(behavior_tree):
            if child.tag in {'ReactiveFallback', 'Fallback', 'Selector'}:
                branch_root = child
                break
        if branch_root is None:
            return None

        specs = []
        for child in list(branch_root):
            decision_id = str(child.attrib.get('decision_id', '')).strip()
            if not decision_id:
                continue
            label = str(child.attrib.get('decision_label', decision_id)).strip()
            action_ref = str(child.attrib.get('action_ref', decision_id)).strip()
            condition_ref = str(child.attrib.get('condition_ref', '')).strip()
            fallback = self._parse_xml_bool(child.attrib.get('fallback')) or not condition_ref
            action = action_registry.get(action_ref)
            if action is None:
                continue
            condition = None if fallback else condition_registry.get(condition_ref)
            if not fallback and condition is None:
                continue
            specs.append(self._decision_spec(decision_id, label, condition, action, fallback=fallback))
        return specs or None

    def _build_role_decision_specs(self):
        default_specs = self._default_role_decision_specs()
        if self._decision_plugin_catalog:
            return self._apply_behavior_overrides_to_specs(default_specs)
        condition_registry = self._behavior_condition_registry()
        action_registry = self._behavior_action_registry()
        loaded_specs = {}
        for role_key, fallback_specs in default_specs.items():
            xml_specs = self._load_role_decision_specs_from_xml(role_key, condition_registry, action_registry)
            loaded_specs[role_key] = xml_specs or fallback_specs
        return self._apply_behavior_overrides_to_specs(loaded_specs)

    def _build_role_trees(self):
        role_trees = {}
        for role_key, specs in self.role_decision_specs.items():
            children = []
            for spec in specs:
                action_node = Action(spec['action'])
                if spec.get('fallback', False) or spec.get('condition') is None:
                    children.append(action_node)
                else:
                    children.append(Sequence(Condition(spec['condition']), action_node))
            role_trees[role_key] = Selector(*children)
        return role_trees

    def _action_id_from_node_name(self, node_name):
        raw = str(node_name or '').strip()
        if raw.startswith('_action_'):
            raw = raw[len('_action_'):]
        return raw

    def _evaluate_decision_candidates(self, context, selected_id=''):
        specs = self.role_decision_specs.get(context.data.get('role_key'), ())
        if not specs:
            return ()
        total = max(1, len(specs) - 1)
        ranked = []
        for index, spec in enumerate(specs):
            condition = spec.get('condition')
            fallback = bool(spec.get('fallback', False))
            try:
                matched = True if fallback or condition is None else bool(condition(context))
            except Exception:
                matched = False
            priority_ratio = 1.0 - (index / total)
            if matched:
                weight = 0.58 + priority_ratio * 0.30
            elif fallback:
                weight = 0.18 + priority_ratio * 0.08
            else:
                weight = 0.04 + priority_ratio * 0.14
            if selected_id and spec['id'] == selected_id:
                weight = 1.0
                matched = True
            ranked.append({
                'id': spec['id'],
                'label': spec['label'],
                'weight': max(0.0, min(1.0, weight)),
                'matched': matched,
                'priority_index': index,
            })
        ranked.sort(key=lambda item: (-item['weight'], item['priority_index']))
        return tuple(ranked)

    def _store_decision_diagnostics(self, entity, context, bt_node):
        selected_id = self._action_id_from_node_name(bt_node)
        ranked = self._evaluate_decision_candidates(context, selected_id=selected_id)
        entity.ai_decision_selected = selected_id
        entity.ai_decision_weights = ranked
        entity.ai_decision_top3 = ranked[:3]

    def _decision_spec_by_id(self, role_key, decision_id):
        for spec in self.role_decision_specs.get(role_key, ()):
            if spec.get('id') == decision_id:
                return spec
        return None

    def _execute_forced_test_decision(self, context, decision_id):
        if not decision_id:
            return None, ''
        spec = self._decision_spec_by_id(context.data.get('role_key'), decision_id)
        if spec is None:
            return None, ''
        action = spec.get('action')
        if action is None:
            return None, ''
        try:
            decision = action(context)
        except Exception:
            return None, ''
        if decision is None:
            return None, ''
        resolved = dict(decision)
        resolved.setdefault('summary', f'测试模式强制执行 {spec.get("label", decision_id)}')
        return resolved, f'_action_{spec.get("id", decision_id)}'

    def get_decision_destination_preview_regions(self, role_key, decision_id, map_manager, team=None):
        if map_manager is None:
            return []
        binding = self._available_plugin_binding(role_key, decision_id)
        preview_regions = binding.get('preview_regions') if callable(binding.get('preview_regions')) else None
        override = self._behavior_override_for_decision(role_key, decision_id)
        override_regions = self._behavior_override_regions(override, team=team)
        if override_regions:
            return [deepcopy(region) for region in override_regions]
        if binding is None:
            return []
        if preview_regions is not None:
            result = preview_regions(self, role_key, map_manager, team=team, override=override, binding=dict(binding))
            if isinstance(result, list):
                return [deepcopy(region) for region in result if isinstance(region, dict)]
        facility_types = tuple(binding.get('default_destination_types', ()))
        regions = []
        for facility_type in facility_types:
            regions.extend(deepcopy(map_manager.get_facility_regions(facility_type)))
        return regions

    def get_decision_point_targets(self, role_key, decision_id, map_manager, team=None):
        binding = self._available_plugin_binding(role_key, decision_id)
        override = self._behavior_override_for_decision(role_key, decision_id)
        targets = {}
        if binding is not None:
            preview_points = binding.get('preview_points') if callable(binding.get('preview_points')) else None
            if preview_points is not None:
                targets.update(self._normalize_behavior_point_targets(
                    preview_points(self, role_key, map_manager, team=team, override=override, binding=dict(binding))
                ))
        targets.update(self._behavior_override_point_targets(override, team=team))
        return targets

    def get_decision_point_target_specs(self, role_key, decision_id, map_manager, team=None):
        binding = self._available_plugin_binding(role_key, decision_id)
        override = self._behavior_override_for_decision(role_key, decision_id)
        specs = {}
        if binding is not None:
            preview_points = binding.get('preview_points') if callable(binding.get('preview_points')) else None
            if preview_points is not None:
                specs.update(self._normalize_behavior_point_target_specs(
                    preview_points(self, role_key, map_manager, team=team, override=override, binding=dict(binding))
                ))
        for target_id, override_spec in self._behavior_override_point_target_specs(override, team=team).items():
            merged = dict(specs.get(target_id, {}))
            merged.update(dict(override_spec))
            specs[target_id] = merged
        return specs

    def _has_combat_ammo(self, entity, rules_engine=None):
        if entity is None:
            return False
        if rules_engine is not None and hasattr(rules_engine, '_available_ammo'):
            return int(rules_engine._available_ammo(entity)) > 0
        ammo_per_shot = max(1, int(getattr(entity, 'ammo_per_shot', 1) or 1))
        return int(getattr(entity, 'ammo', 0)) >= ammo_per_shot

    def _hero_has_ranged_ammo(self, context):
        return context.data.get('role_key') == 'hero' and self._has_combat_ammo(context.entity, context.rules_engine)

    def _meters_to_world_units(self, meters, map_manager=None):
        if map_manager is not None and hasattr(map_manager, 'meters_to_world_units'):
            return map_manager.meters_to_world_units(meters)
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return meters * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)

    def _world_units_to_meters(self, world_units, map_manager=None):
        return float(world_units) / max(self._meters_to_world_units(1.0, map_manager), 1e-6)

    def _arrival_tolerance_world_units(self, map_manager=None):
        tolerance_m = float(self.config.get('ai', {}).get('target_arrival_tolerance_m', 0.6))
        return max(8.0, self._meters_to_world_units(tolerance_m, map_manager))

    def _is_enemy_half_position(self, team, x_coord, map_center_x):
        if team == 'red':
            return float(x_coord) >= float(map_center_x)
        return float(x_coord) <= float(map_center_x)

    def _team_health_snapshot(self, entities, team):
        current_health = 0.0
        max_health = 0.0
        for other in entities:
            if other.team != team or other.type not in {'robot', 'sentry'}:
                continue
            max_value = max(0.0, float(getattr(other, 'max_health', 0.0)))
            max_health += max_value
            if other.is_alive():
                current_health += max(0.0, float(getattr(other, 'health', 0.0)))
        ratio = current_health / max_health if max_health > 1e-6 else 0.0
        return current_health, max_health, ratio

    def _combat_half_pressure_counts(self, entities, team, map_center_x):
        ally_enemy_half_count = 0
        enemy_own_half_count = 0
        ally_enemy_half_roles = set()
        for other in entities:
            if other.type not in {'robot', 'sentry'} or not other.is_alive():
                continue
            role_key = self._role_key(other)
            if role_key not in {'sentry', 'infantry', 'hero'}:
                continue
            if other.team == team:
                if self._is_enemy_half_position(team, other.position['x'], map_center_x):
                    ally_enemy_half_count += 1
                    ally_enemy_half_roles.add(role_key)
            elif self._is_enemy_half_position(other.team, other.position['x'], map_center_x):
                enemy_own_half_count += 1
        return {
            'ally_enemy_half_count': ally_enemy_half_count,
            'enemy_own_half_count': enemy_own_half_count,
            'ally_enemy_half_roles': ally_enemy_half_roles,
        }

    def _frontline_health_near_enemy_base(self, entities, team, enemy_base, map_manager):
        if enemy_base is None or not enemy_base.is_alive():
            return 0.0
        radius = self._meters_to_world_units(10.0, map_manager)
        total = 0.0
        for other in entities:
            if other.team != team or other.type not in {'robot', 'sentry'} or not other.is_alive():
                continue
            if self._distance(other, enemy_base) <= radius:
                total += max(0.0, float(getattr(other, 'health', 0.0)))
        return total

    def _supply_health_threshold_ratio(self, entity, map_manager):
        supply_anchor = self.get_supply_slot(entity, map_manager) or self.get_team_anchor(entity.team, 'supply', map_manager, entity=entity)
        if supply_anchor is None:
            return 0.20
        distance_m = max(0.0, min(40.0, self._world_units_to_meters(self._distance_to_point(entity, supply_anchor), map_manager)))
        return max(0.20, min(0.40, 0.20 + (1.0 - distance_m / 40.0) * 0.20))

    def _base_defense_anchor(self, context):
        return self.get_team_anchor(context.entity.team, 'fort', context.map_manager, entity=context.entity) or self.get_team_anchor(context.entity.team, 'base', context.map_manager, entity=context.entity)

    def _highest_threat_enemy_in_own_half(self, context):
        map_center = context.data.get('map_center') or self.get_map_center(context.map_manager)
        if map_center is None:
            return None
        own_base = context.data.get('own_base')
        defense_anchor = self._base_defense_anchor(context)
        if own_base is None and defense_anchor is None:
            return None
        base_radius = self._meters_to_world_units(10.0, context.map_manager)
        best_enemy = None
        best_score = None
        for enemy in context.entities:
            if enemy.team == context.entity.team or not enemy.is_alive() or enemy.type not in {'robot', 'sentry'}:
                continue
            role_key = self._role_key(enemy)
            if role_key not in {'sentry', 'infantry', 'hero'}:
                continue
            in_own_half = self._is_enemy_half_position(enemy.team, enemy.position['x'], map_center[0])
            near_base = own_base is not None and self._distance(enemy, own_base) <= base_radius
            if not in_own_half and not near_base:
                continue
            score = self._priority_target_threat_score(context.entity, enemy)
            if own_base is not None:
                score += max(0.0, 260.0 - self._distance(enemy, own_base) * 0.45)
            if defense_anchor is not None:
                score += max(0.0, 180.0 - self._distance_to_point(enemy, defense_anchor) * 0.35)
            if getattr(enemy, 'last_damage_source_id', None) in {getattr(own_base, 'id', None), getattr(context.data.get('own_outpost'), 'id', None)}:
                score += 160.0
            if best_score is None or score > best_score:
                best_score = score
                best_enemy = enemy
        return best_enemy

    def _target_region(self, target_point, map_manager=None):
        if target_point is None or map_manager is None:
            return None
        regions = map_manager.get_regions_at(target_point[0], target_point[1])
        if not regions:
            return None
        for region in regions:
            if region.get('type') not in {'boundary', 'wall'}:
                return region
        return regions[0]

    def _is_point_inside_region(self, point, region, map_manager=None):
        if point is None or region is None or map_manager is None:
            return False
        region_id = region.get('id')
        if region_id is None:
            return False
        regions = map_manager.get_regions_at(point[0], point[1])
        return any(candidate.get('id') == region_id for candidate in regions)

    def _distance_point_to_segment(self, point, start, end):
        px, py = float(point[0]), float(point[1])
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        dx = ex - sx
        dy = ey - sy
        segment_length_sq = dx * dx + dy * dy
        if segment_length_sq <= 1e-6:
            return math.hypot(px - sx, py - sy)
        t = ((px - sx) * dx + (py - sy) * dy) / segment_length_sq
        t = max(0.0, min(1.0, t))
        closest_x = sx + t * dx
        closest_y = sy + t * dy
        return math.hypot(px - closest_x, py - closest_y)

    def _distance_to_region(self, point, region):
        if point is None or region is None:
            return float('inf')
        shape = region.get('shape', 'rect')
        px = float(point[0])
        py = float(point[1])
        if shape == 'line':
            distance = self._distance_point_to_segment(
                (px, py),
                (float(region.get('x1', px)), float(region.get('y1', py))),
                (float(region.get('x2', px)), float(region.get('y2', py))),
            )
            return max(0.0, distance - float(region.get('thickness', 0.0)))
        if shape == 'polygon':
            points = region.get('points', [])
            if len(points) >= 2:
                best = float('inf')
                previous = points[-1]
                for current in points:
                    best = min(best, self._distance_point_to_segment((px, py), previous, current))
                    previous = current
                return best
        x1 = min(float(region.get('x1', px)), float(region.get('x2', px)))
        x2 = max(float(region.get('x1', px)), float(region.get('x2', px)))
        y1 = min(float(region.get('y1', py)), float(region.get('y2', py)))
        y2 = max(float(region.get('y1', py)), float(region.get('y2', py)))
        dx = max(x1 - px, 0.0, px - x2)
        dy = max(y1 - py, 0.0, py - y2)
        return math.hypot(dx, dy)

    def _target_region_entry_buffer(self, entity, map_manager=None):
        collision_radius = float(getattr(entity, 'collision_radius', 16.0))
        return max(6.0, collision_radius * 0.3, self._arrival_tolerance_world_units(map_manager) * 0.35)

    def _is_target_reached(self, entity, target_point, map_manager=None, navigation_radius=None):
        if target_point is None:
            return True
        region = self._target_region(target_point, map_manager)
        entity_point = (float(entity.position['x']), float(entity.position['y']))
        tolerance = max(self._arrival_tolerance_world_units(map_manager), float(navigation_radius or 0.0))
        if region is not None:
            return self._is_point_inside_region(entity_point, region, map_manager) and self._distance_to_point(entity, target_point) <= tolerance
        return self._distance_to_point(entity, target_point) <= tolerance

    def _resolve_navigation_target(self, target_point, map_manager, entity=None):
        if target_point is None or map_manager is None:
            return target_point
        resolved = (float(target_point[0]), float(target_point[1]))
        collision_radius = float(getattr(entity, 'collision_radius', 16.0)) if entity is not None else 16.0
        region = self._target_region(resolved, map_manager)
        if region is not None:
            region_resolved = self._resolve_navigation_target_in_region(resolved, region, map_manager, entity=entity)
            if region_resolved is not None:
                return region_resolved
        if map_manager.is_position_valid_for_radius(resolved[0], resolved[1], collision_radius=collision_radius):
            return resolved
        return map_manager.find_nearest_passable_point(
            resolved,
            collision_radius=collision_radius,
            search_radius=max(int(self._arrival_tolerance_world_units(map_manager) * 6.0), 72),
            step=max(4, map_manager.terrain_grid_cell_size),
        )

    def _resolve_navigation_target_in_region(self, target_point, region, map_manager, entity=None):
        if region is None or map_manager is None:
            return None
        region_id = region.get('id')
        if region_id is None:
            return None
        collision_radius = float(getattr(entity, 'collision_radius', 16.0)) if entity is not None else 16.0
        search_radius = max(int(self._arrival_tolerance_world_units(map_manager) * 6.0), 72)
        step = max(4, map_manager.terrain_grid_cell_size)
        best_point = None
        best_distance = None
        for candidate in self._target_region_candidate_points(entity, target_point, map_manager):
            direct_candidate = (float(candidate[0]), float(candidate[1]))
            if map_manager.is_position_valid_for_radius(direct_candidate[0], direct_candidate[1], collision_radius=collision_radius):
                resolved_candidate = direct_candidate
            else:
                resolved_candidate = map_manager.find_nearest_passable_point(
                    direct_candidate,
                    collision_radius=collision_radius,
                    search_radius=search_radius,
                    step=step,
                )
            if resolved_candidate is None:
                continue
            if not self._is_point_inside_region(resolved_candidate, region, map_manager):
                continue
            distance = math.hypot(resolved_candidate[0] - float(target_point[0]), resolved_candidate[1] - float(target_point[1]))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_point = (float(resolved_candidate[0]), float(resolved_candidate[1]))
        return best_point

    def _target_region_radius(self, entity, target_point, map_manager=None):
        region = self._target_region(target_point, map_manager)
        if region is None:
            return 0.0
        width = abs(float(region.get('x2', target_point[0])) - float(region.get('x1', target_point[0])))
        height = abs(float(region.get('y2', target_point[1])) - float(region.get('y1', target_point[1])))
        radius = max(width, height) * 0.35
        return max(radius, float(getattr(entity, 'collision_radius', 16.0)) * 0.6)

    def _target_region_candidate_points(self, entity, target_point, map_manager=None):
        if target_point is None:
            return []
        candidates = []
        seen = set()

        def add_candidate(point):
            if point is None:
                return
            normalized = (float(point[0]), float(point[1]))
            key = (round(normalized[0], 2), round(normalized[1], 2))
            if key in seen:
                return
            seen.add(key)
            candidates.append(normalized)

        add_candidate(target_point)
        region = self._target_region(target_point, map_manager)
        if region is None:
            target_radius = max(12.0, self._arrival_tolerance_world_units(map_manager) * 0.8)
            for dx, dy in ((target_radius, 0.0), (-target_radius, 0.0), (0.0, target_radius), (0.0, -target_radius)):
                add_candidate((target_point[0] + dx, target_point[1] + dy))
            return candidates

        add_candidate(self.facility_center(region))
        if region.get('shape') != 'rect':
            return candidates

        x1 = min(float(region.get('x1', target_point[0])), float(region.get('x2', target_point[0])))
        x2 = max(float(region.get('x1', target_point[0])), float(region.get('x2', target_point[0])))
        y1 = min(float(region.get('y1', target_point[1])), float(region.get('y2', target_point[1])))
        y2 = max(float(region.get('y1', target_point[1])), float(region.get('y2', target_point[1])))
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        collision_radius = float(getattr(entity, 'collision_radius', 16.0))
        inset = min(max(8.0, collision_radius * 0.75, self._arrival_tolerance_world_units(map_manager) * 0.4), width * 0.3, height * 0.3)
        if inset <= 0.0:
            inset = 0.0
        left = x1 + inset
        right = x2 - inset
        top = y1 + inset
        bottom = y2 - inset
        if left > right:
            left = right = (x1 + x2) * 0.5
        if top > bottom:
            top = bottom = (y1 + y2) * 0.5
        entity_x = float(entity.position['x']) if entity is not None else float(target_point[0])
        entity_y = float(entity.position['y']) if entity is not None else float(target_point[1])

        for point in (
            (left, top),
            (right, top),
            (left, bottom),
            (right, bottom),
            ((left + right) * 0.5, top),
            ((left + right) * 0.5, bottom),
            (left, (top + bottom) * 0.5),
            (right, (top + bottom) * 0.5),
            (
                min(max(entity_x, left), right),
                min(max(entity_y, top), bottom),
            ),
        ):
            add_candidate(point)
        return candidates

    def _set_navigation_overlay_state(self, entity, waypoint=None, preview=None, path_valid=None, region_radius=0.0, traversal_state='passable'):
        entity.ai_navigation_waypoint = waypoint
        entity.ai_navigation_radius = float(region_radius or 0.0)
        entity.ai_navigation_path_state = traversal_state
        if preview:
            entity.ai_path_preview = tuple(preview)
        else:
            entity.ai_path_preview = self.EMPTY_PATH_PREVIEW
        entity.ai_navigation_subgoals = entity.ai_path_preview[1:] if len(entity.ai_path_preview) > 1 else self.EMPTY_PATH_PREVIEW
        if path_valid is None:
            path_valid = waypoint is not None or bool(entity.ai_path_preview)
        entity.ai_navigation_path_valid = bool(path_valid)

    def _build_navigation_search_request(self, entity, target_point, map_manager, step_limit, traversal_profile):
        return self._navigation_planner.build_search_request(entity, target_point, map_manager, step_limit, traversal_profile)

    def _run_navigation_search_request(self, map_manager, request):
        return self._navigation_planner.run_search_request(map_manager, request)

    def _finalize_navigation_search_path(self, entity, raw_path, target_point, map_manager):
        return self._navigation_planner.finalize_search_path(entity, raw_path, target_point, map_manager)

    def _consume_pending_navigation_search(self, entity, target_point, map_manager, state, request_signature):
        return self._navigation_planner.consume_pending_search(entity, target_point, map_manager, state, request_signature)

    def _submit_navigation_search(self, entity, target_point, map_manager, step_limit, traversal_profile, state, request_signature):
        return self._navigation_planner.submit_search(entity, target_point, map_manager, step_limit, traversal_profile, state, request_signature)

    def _clear_navigation_overlay_state(self, entity):
        self._set_navigation_overlay_state(entity, waypoint=None, preview=self.EMPTY_PATH_PREVIEW, path_valid=False, region_radius=0.0, traversal_state='idle')

    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0, controlled_entity_ids=None, controlled_entities=None, shared_frame=None):
        if self._last_behavior_reload_check_time < 0.0 or game_time - self._last_behavior_reload_check_time >= self._behavior_reload_check_interval:
            self._last_behavior_reload_check_time = game_time
            self._refresh_behavior_runtime_overrides()
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        if controlled_entities is not None and controlled_ids is None:
            controlled_ids = {entity.id for entity in controlled_entities}
        update_entities = tuple(controlled_entities) if controlled_entities is not None else tuple(entities)
        frame_view = shared_frame if isinstance(shared_frame, AIFrameContext) else None
        self._cleanup_runtime_state(entities, controlled_ids)
        self._movement_status_cache.clear()
        self._frame_target_assessment_cache.clear()
        self._path_replans_remaining = self._path_replans_per_update
        for entity in update_entities:
            if controlled_ids is not None and entity.id not in controlled_ids:
                continue
            if not self._should_control_entity(entity):
                continue
            if not self._role_state_machine_enabled(entity):
                self._maintain_continuous_motion(entity)
                continue
            last_update = self._last_ai_update_time.get(entity.id)
            if last_update is None:
                last_update = game_time - self._entity_update_phase_offset(entity.id)
                self._last_ai_update_time[entity.id] = last_update
            if game_time - last_update < self._ai_update_interval:
                self._maintain_continuous_motion(entity)
                continue
            self._last_ai_update_time[entity.id] = game_time
            context = self._build_context(entity, entities, map_manager, rules_engine, game_time, game_duration, shared_frame=frame_view)
            if self._decision_system_disabled():
                decision = self._todo_decision_action(context)
                bt_node = f'_action_{self.TODO_DECISION_ID}'
                decision['bt_node'] = bt_node
                self._store_decision_diagnostics(entity, context, bt_node)
                self._apply_decision(entity, decision, rules_engine)
                continue
            tree = self.role_trees.get(context.data['role_key'])
            if tree is None:
                self._apply_idle_decision(entity, '未定义角色行为树')
                continue
            forced_test_decision_id = str(getattr(entity, 'test_forced_decision_id', '') or '').strip()
            if forced_test_decision_id:
                forced_decision, forced_bt_node = self._execute_forced_test_decision(context, forced_test_decision_id)
                if forced_decision is not None:
                    forced_decision['bt_node'] = forced_bt_node
                    self._store_decision_diagnostics(entity, context, forced_bt_node)
                    self._apply_decision(entity, forced_decision, rules_engine)
                    continue
            result = tree.tick(context)
            decision = context.data.get('decision')
            if result == FAILURE or decision is None:
                decision = self._idle_navigation_decision(context, '行为树未命中有效分支，保持缓行巡航')
            bt_node = str(context.data.get('bt_action_node', ''))
            decision['bt_node'] = bt_node
            self._store_decision_diagnostics(entity, context, bt_node)
            self._apply_decision(entity, decision, rules_engine)

    def maintain_entities_motion(self, entities):
        for entity in tuple(entities or ()):
            if not self._should_control_entity(entity):
                continue
            self._maintain_continuous_motion(entity)

    def _cleanup_runtime_state(self, entities, controlled_ids=None):
        active_ids = {
            entity.id
            for entity in entities
            if (controlled_ids is None or entity.id in controlled_ids)
        }
        runtime_maps = (
            self._last_ai_update_time,
            self._entity_path_state,
            self._route_progress_state,
            self._stuck_state,
            self._forced_supply_escape_state,
            self._post_supply_goal_state,
            self._sentry_fly_slope_state,
            self._strategy_patrol_state,
            self._patrol_index,
        )
        for runtime_map in runtime_maps:
            stale_ids = [entity_id for entity_id in runtime_map.keys() if entity_id not in active_ids]
            for entity_id in stale_ids:
                runtime_map.pop(entity_id, None)
        router = getattr(self, '_pathfinder_router', None)
        if router is not None:
            router.prune(active_ids)

    def _should_control_entity(self, entity):
        if not entity.is_alive():
            return False
        if entity.type not in {'robot', 'sentry'}:
            return False
        return True

    def _build_context(self, entity, entities, map_manager, rules_engine, game_time, game_duration, shared_frame=None):
        role_key = self._role_key(entity)
        strategy = self.ai_strategy.get(role_key, self.ai_strategy.get('infantry', {}))
        opening_phase = game_time <= min(45.0, max(30.0, game_duration * 0.12 if game_duration > 0 else 45.0))
        frame_view = shared_frame if isinstance(shared_frame, AIFrameContext) else None
        enemy_team = 'blue' if entity.team == 'red' else 'red'
        if frame_view is not None:
            enemies = list(frame_view.enemies_for(entity.team))
            allies = list(frame_view.allies_for(entity.team, exclude_id=entity.id))
            own_outpost = frame_view.structure(entity.team, 'outpost')
            own_base = frame_view.structure(entity.team, 'base')
            enemy_outpost = frame_view.structure(enemy_team, 'outpost')
            enemy_base = frame_view.structure(enemy_team, 'base')
            allied_sentry = frame_view.first_role(entity.team, 'sentry')
            allied_hero = frame_view.first_role(entity.team, 'hero')
            allied_infantry = frame_view.first_role(entity.team, 'infantry', exclude_id=entity.id)
            allied_engineer = frame_view.first_role(entity.team, 'engineer')
            enemy_hero = frame_view.first_role(enemy_team, 'hero')
            enemy_engineer = frame_view.first_role(enemy_team, 'engineer')
            team_health_current, team_health_max, team_health_ratio = frame_view.health_snapshot(entity.team)
        else:
            enemies = [other for other in entities if other.team != entity.team and other.is_alive()]
            allies = [other for other in entities if other.team == entity.team and other.id != entity.id and other.is_alive()]
            own_outpost = self._find_entity(entities, entity.team, 'outpost')
            own_base = self._find_entity(entities, entity.team, 'base')
            enemy_outpost = self._find_entity(entities, enemy_team, 'outpost')
            enemy_base = self._find_entity(entities, enemy_team, 'base')
            allied_sentry = self._find_entity(entities, entity.team, 'sentry')
            allied_hero = self._find_entity_by_role(entities, entity.team, 'hero')
            allied_infantry = self._find_entity_by_role(entities, entity.team, 'infantry', exclude_id=entity.id)
            allied_engineer = self._find_entity_by_role(entities, entity.team, 'engineer')
            enemy_hero = self._find_entity_by_role(entities, enemy_team, 'hero')
            enemy_engineer = self._find_entity_by_role(entities, enemy_team, 'engineer')
            team_health_current, team_health_max, team_health_ratio = self._team_health_snapshot(entities, entity.team)
        target = self.select_priority_target(entity, enemies, strategy, rules_engine)
        nearby_allies = [other for other in allies if self._distance(entity, other) <= self._meters_to_world_units(5.0, map_manager)]
        nearby_enemies = [other for other in enemies if self._distance(entity, other) <= self._meters_to_world_units(6.0, map_manager)]
        energy_anchor = self.get_energy_anchor(entity.team, map_manager)
        energy_snapshot = rules_engine.get_energy_mechanism_snapshot(entity.team) if rules_engine is not None and hasattr(rules_engine, 'get_energy_mechanism_snapshot') else {'can_activate': False, 'state': 'inactive'}
        mining_anchor = self.get_mining_anchor(entity, map_manager)
        exchange_anchor = self.get_exchange_anchor(entity, map_manager)
        map_center = self.get_map_center(map_manager)
        health_ratio = 0.0 if entity.max_health <= 0 else entity.health / entity.max_health
        heat_ratio = 0.0 if entity.max_heat <= 0 else entity.heat / entity.max_heat
        frontline_enemy_base_health = self._frontline_health_near_enemy_base(entities, entity.team, enemy_base, map_manager)
        frontline_pressure_override = team_health_max > 1e-6 and frontline_enemy_base_health >= team_health_max * 0.30
        if frame_view is not None:
            half_pressure = frame_view.pressure_snapshot(entity.team)
        else:
            half_pressure = self._combat_half_pressure_counts(entities, entity.team, map_center[0] if map_center is not None else 0.0)
        supply_health_threshold = self._supply_health_threshold_ratio(entity, map_manager)
        needs_heal_supply = health_ratio <= supply_health_threshold and not frontline_pressure_override
        low_ammo_threshold = int(strategy.get('low_ammo_threshold', 40 if entity.type == 'sentry' else 25))
        opening_target = self._opening_ammo_target_for_entity(entity, rules_engine)
        supply_claimable = self._supply_claimable_ammo(entity, rules_engine, game_time)
        supply_eta = self._next_supply_eta(rules_engine, game_time)
        supply_candidate = self._select_supply_runner(entity, allies + [entity], rules_engine, game_time)
        in_supply_zone = self._is_inside_team_facility(entity, map_manager, 'supply')
        base_assault_unlocked = False
        if enemy_base is not None and enemy_base.is_alive() and (enemy_outpost is None or not enemy_outpost.is_alive()):
            if rules_engine is not None and hasattr(rules_engine, 'is_base_shielded'):
                base_assault_unlocked = not bool(rules_engine.is_base_shielded(enemy_base))
            else:
                base_assault_unlocked = True
        emergency_base_defense = False
        if own_base is not None and enemy_base is not None and own_base.is_alive() and enemy_base.is_alive():
            emergency_base_defense = (
                float(own_base.health) + 300.0 <= float(enemy_base.health)
                and int(half_pressure['enemy_own_half_count']) >= int(half_pressure['ally_enemy_half_count']) + 1
            )
        data = {
            'role_key': role_key,
            'strategy': strategy,
            'target': target,
            'nearby_allies': nearby_allies,
            'nearby_enemies': nearby_enemies,
            'own_outpost': own_outpost,
            'own_base': own_base,
            'enemy_outpost': enemy_outpost,
            'enemy_base': enemy_base,
            'base_assault_unlocked': base_assault_unlocked,
            'emergency_base_defense': emergency_base_defense,
            'allied_sentry': allied_sentry,
            'allied_hero': allied_hero,
            'allied_infantry': allied_infantry,
            'allied_engineer': allied_engineer,
            'enemy_hero': enemy_hero,
            'enemy_engineer': enemy_engineer,
            'energy_anchor': energy_anchor,
            'energy_can_activate': bool(energy_snapshot.get('can_activate', False)),
            'energy_state': energy_snapshot.get('state', 'inactive'),
            'mining_anchor': mining_anchor,
            'exchange_anchor': exchange_anchor,
            'map_center': map_center,
            'health_ratio': health_ratio,
            'heat_ratio': heat_ratio,
            'team_health_current': team_health_current,
            'team_health_max': team_health_max,
            'team_health_ratio': team_health_ratio,
            'frontline_enemy_base_health': frontline_enemy_base_health,
            'frontline_pressure_override': frontline_pressure_override,
            'ally_offense_in_enemy_half_count': int(half_pressure['ally_enemy_half_count']),
            'enemy_offense_in_own_half_count': int(half_pressure['enemy_own_half_count']),
            'ally_sentry_in_enemy_half': 'sentry' in half_pressure['ally_enemy_half_roles'],
            'ally_infantry_in_enemy_half': 'infantry' in half_pressure['ally_enemy_half_roles'],
            'supply_health_threshold': supply_health_threshold,
            'needs_heal_supply': needs_heal_supply,
            'ammo_low': getattr(entity, 'ammo', 0) <= low_ammo_threshold,
            'low_ammo_threshold': low_ammo_threshold,
            'supply_claimable': supply_claimable,
            'supply_eta': supply_eta,
            'supply_candidate_id': supply_candidate.id if supply_candidate is not None else None,
            'opening_phase': opening_phase,
            'opening_ammo_target': opening_target,
            'in_supply_zone': in_supply_zone,
            'has_combat_ammo': self._has_combat_ammo(entity, rules_engine),
            'must_restock': role_key in {'hero', 'infantry'} and getattr(entity, 'ammo_type', 'none') != 'none' and getattr(entity, 'ammo', 0) <= 0,
            'late_phase': game_duration > 0 and (game_duration - game_time) <= 120.0,
            'outnumbered': len(nearby_enemies) > len(nearby_allies) + 1,
            'teamfight_ready': len(nearby_enemies) >= 1,
            'transit_anchor': None,
            'carried_minerals': int(getattr(entity, 'carried_minerals', 0)),
            'energy_buff_active': any(
                float(getattr(other, 'timed_buffs', {}).get('energy_mechanism_boost', 0.0)) > 0.0
                or float(getattr(other, 'energy_small_buff_timer', 0.0)) > 0.0
                or float(getattr(other, 'energy_large_buff_timer', 0.0)) > 0.0
                for other in [entity] + allies
            ),
        }
        return BehaviorContext(self, entity, entities, map_manager, rules_engine, game_time, game_duration, data)

    def _fallback_objective(self, context):
        # Ensure we keep a navigable waypoint even when no BT action fires.
        map_manager = context.map_manager
        if map_manager is None:
            return None
        enemy_team = 'blue' if context.entity.team == 'red' else 'red'
        # Prefer unlocked enemy base, then enemy outpost, otherwise own supply/base center.
        enemy_base = context.data.get('enemy_base')
        enemy_outpost = context.data.get('enemy_outpost')
        if context.data.get('base_assault_unlocked') and enemy_base is not None and enemy_base.is_alive():
            return (enemy_base.position['x'], enemy_base.position['y'])
        if enemy_outpost is not None and enemy_outpost.is_alive():
            return (enemy_outpost.position['x'], enemy_outpost.position['y'])
        supply_anchor = self.get_team_anchor(context.entity.team, 'supply', map_manager, entity=context.entity)
        if supply_anchor is not None:
            return supply_anchor
        base_anchor = self.get_team_anchor(context.entity.team, 'base', map_manager, entity=context.entity)
        if base_anchor is not None:
            return base_anchor
        return self.get_map_center(map_manager)

    def _role_key(self, entity):
        if entity.type == 'sentry':
            return 'sentry'
        type_map = {
            '英雄': 'hero',
            '工程': 'engineer',
            '步兵': 'infantry',
        }
        return type_map.get(getattr(entity, 'robot_type', ''), 'infantry')

    def _idle_decision(self, entity, summary):
        return {
            'summary': summary,
            'target': None,
            'aim_point': None,
            'navigation_target': None,
            'movement_target': None,
            'velocity': (0.0, 0.0),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'searching',
            'angular_velocity': 0.0,
        }

    def _idle_navigation_decision(self, context, summary):
        fallback = self._fallback_objective(context)
        if fallback is None:
            return self._idle_decision(context.entity, summary)
        speed = self._meters_to_world_units(1.35, context.map_manager)
        velocity = self.navigate_towards(context.entity, fallback, speed, context.map_manager)
        staged = getattr(context.entity, 'ai_navigation_waypoint', None) or fallback
        return {
            'summary': summary,
            'target': None,
            'aim_point': None,
            'navigation_target': fallback,
            'movement_target': staged,
            'velocity': velocity,
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'searching',
            'angular_velocity': 0.0,
        }

    def _apply_idle_decision(self, entity, summary):
        self._apply_decision(entity, self._idle_decision(entity, summary), None)

    def _apply_decision(self, entity, decision, rules_engine):
        entity.ai_decision = decision.get('summary', '')
        entity.ai_behavior_node = decision.get('bt_node', '')
        entity.target = decision.get('target')
        structure_lob_target_type = str(decision.get('structure_lob_target_type', '') or '').strip()
        entity.hero_structure_lob_active = bool(structure_lob_target_type)
        entity.hero_structure_lob_target_type = structure_lob_target_type or None
        entity.hero_deployment_forced_off = bool(decision.get('disengage_deployment', False))
        if entity.hero_deployment_forced_off:
            entity.hero_deployment_active = False
            entity.hero_deployment_state = 'inactive'
        entity.ai_navigation_target = decision.get('navigation_target')
        entity.ai_movement_target = decision.get('movement_target')
        entity.ai_navigation_radius = float(decision.get('navigation_radius', 0.0) or 0.0)
        if entity.ai_navigation_target is None and entity.ai_movement_target is None:
            self._clear_navigation_overlay_state(entity)
        entity.fire_control_state = decision.get('fire_control_state', 'idle')
        entity.chassis_state = decision.get('chassis_state', 'normal')
        entity.turret_state = decision.get('turret_state', 'searching')
        move_x, move_y = decision.get('velocity', (0.0, 0.0))
        if getattr(entity, 'robot_type', '') == '英雄' and bool(getattr(entity, 'hero_deployment_active', False)):
            move_x, move_y = 0.0, 0.0
            entity.chassis_state = 'power_off'
        entity.ai_navigation_velocity = (move_x, move_y)
        entity.set_velocity(move_x, move_y)
        entity.angular_velocity = decision.get('angular_velocity', 0.0)
        if getattr(entity, 'robot_type', '') == '英雄' and bool(getattr(entity, 'hero_deployment_active', False)):
            entity.angular_velocity = 0.0
        if float(getattr(entity, 'evasive_spin_timer', 0.0)) > 0.0:
            entity.chassis_state = 'fast_spin'
            spin_direction = float(getattr(entity, 'evasive_spin_direction', 1.0)) or 1.0
            spin_rate = float(getattr(entity, 'evasive_spin_rate_deg', 420.0))
            entity.angular_velocity = spin_direction * spin_rate
        if getattr(entity, 'step_climb_state', None) or getattr(entity, 'ai_navigation_path_state', 'passable') == 'step-passable':
            entity.chassis_state = 'normal'
            entity.angular_velocity = 0.0
        aim_point = decision.get('aim_point')
        if aim_point is not None:
            dx = aim_point[0] - entity.position['x']
            dy = aim_point[1] - entity.position['y']
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                entity.turret_angle = math.degrees(math.atan2(dy, dx))
        desired_posture = decision.get('posture')
        if desired_posture and desired_posture != getattr(entity, 'posture', 'mobile') and rules_engine is not None:
            rules_engine.request_posture_change(entity, desired_posture)

    def _maintain_continuous_motion(self, entity):
        move_x, move_y = getattr(entity, 'ai_navigation_velocity', (0.0, 0.0))
        if abs(move_x) <= 1e-6 and abs(move_y) <= 1e-6:
            return
        entity.set_velocity(move_x, move_y)

    def _is_opening_phase(self, context):
        return bool(context.data.get('opening_phase'))

    def _hero_prefers_melee(self, entity):
        return getattr(entity, 'hero_weapon_mode', getattr(entity, 'gimbal_mode', 'ranged_priority')) == 'melee_priority'

    def _hero_prefers_ranged(self, entity):
        return not self._hero_prefers_melee(entity)

    def _is_in_facility_zone(self, entity, map_manager, facility_type):
        if entity is None or map_manager is None:
            return False
        return any(
            region.get('team') in {'neutral', entity.team}
            for region in map_manager.get_regions_at(entity.position['x'], entity.position['y'], region_types={facility_type})
        )

    def _role_key_from_hint(self, entity_type, robot_type):
        if entity_type == 'sentry':
            return 'sentry'
        return {
            '英雄': 'hero',
            '工程': 'engineer',
            '步兵': 'infantry',
        }.get(robot_type, entity_type)

    def _recent_enemy_pressure(self, context):
        pressure = []
        for attacker in list(getattr(context.entity, 'recent_attackers', [])):
            if float(attacker.get('time_left', 0.0)) <= 0.0:
                continue
            if attacker.get('team') == context.entity.team:
                continue
            pressure.append({
                'id': attacker.get('id'),
                'role_key': self._role_key_from_hint(attacker.get('type'), attacker.get('robot_type')),
                'damage': float(attacker.get('damage', 0.0)),
                'time_left': float(attacker.get('time_left', 0.0)),
            })
        return pressure

    def _must_restock_before_combat(self, context):
        return bool(context.data.get('must_restock'))

    def _needs_supply(self, context):
        entity = context.entity
        if context.data.get('needs_heal_supply', False):
            return True
        if self._must_restock_before_combat(context):
            return True
        opening_need = False
        if self._is_opening_phase(context):
            opening_target = self._opening_ammo_target(context)
            if opening_target > 0 and getattr(entity, 'ammo', 0) < opening_target:
                opening_need = True
                if getattr(entity, 'ammo', 0) <= 0:
                    return True
        if getattr(entity, 'ammo_type', 'none') == 'none':
            return False
        if not opening_need and getattr(entity, 'ammo', 0) > context.data.get('low_ammo_threshold', 20):
            return False
        if context.data.get('supply_candidate_id') != entity.id:
            return False
        if opening_need:
            return True
        claimable = context.data.get('supply_claimable', 0)
        eta = context.data.get('supply_eta', 999.0)
        return claimable > 0 or eta <= 10.0

    def _opening_ammo_target(self, context):
        return self._opening_ammo_target_for_entity(context.entity, context.rules_engine)

    def _opening_ammo_target_for_entity(self, entity, rules_engine):
        purchase_rules = rules_engine.rules.get('ammo_purchase', {}) if rules_engine is not None else {}
        opening_targets = purchase_rules.get('opening_targets', {})
        if getattr(entity, 'ammo_type', None) == '42mm':
            return max(10, int(opening_targets.get('hero_42mm', 10)))
        if getattr(entity, 'ammo_type', None) == '17mm' and entity.type == 'robot':
            return max(100, int(opening_targets.get('infantry_17mm', 100)))
        return 0

    def _is_inside_team_facility(self, entity, map_manager, facility_type):
        if map_manager is None:
            return False
        for region in map_manager.get_regions_at(entity.position['x'], entity.position['y'], region_types={facility_type}):
            if region.get('team') == entity.team:
                return True
        return False

    def _update_post_supply_goal_state(self, entity, role_key, opening_phase, in_supply_zone, opening_ammo_ready, game_time, map_manager, stage_anchor):
        state = self._post_supply_goal_state.get(entity.id)
        if state is not None and float(state.get('expires_at', 0.0)) <= float(game_time):
            self._post_supply_goal_state.pop(entity.id, None)
            state = None
        if role_key not in {'hero', 'infantry'}:
            self._post_supply_goal_state.pop(entity.id, None)
            return None
        has_ammo = getattr(entity, 'ammo_type', 'none') != 'none' and getattr(entity, 'ammo', 0) > 0
        if in_supply_zone and has_ammo:
            expires_at = max(float(state.get('expires_at', 0.0)) if state is not None else 0.0, float(game_time) + 24.0)
            state = {'goal': 'home_stage', 'expires_at': expires_at}
            self._post_supply_goal_state[entity.id] = state
            return state['goal']
        if state is not None and state.get('goal') == 'home_stage' and stage_anchor is not None:
            if self._distance_to_point(entity, stage_anchor) <= self._meters_to_world_units(0.9, map_manager):
                if role_key == 'hero':
                    next_goal = 'hero_trapezoid' if self._hero_prefers_ranged(entity) else 'hero_highground'
                else:
                    next_goal = 'infantry_push'
                state = {
                    'goal': next_goal,
                    'expires_at': max(float(state.get('expires_at', 0.0)), float(game_time) + (18.0 if opening_phase else 12.0)),
                }
                self._post_supply_goal_state[entity.id] = state
        return state.get('goal') if state is not None else None

    def _is_critical_state(self, context):
        health_ratio = float(context.data.get('health_ratio', 1.0))
        return (
            health_ratio <= 0.14
            or context.data.get('heat_ratio', 0.0) >= 0.88
            or (health_ratio <= 0.24 and context.data.get('outnumbered', False))
            or (context.data.get('ammo_low') and context.data.get('outnumbered') and health_ratio <= 0.45)
        )

    def _has_target(self, context):
        return context.data.get('target') is not None

    def _has_teamfight_window(self, context):
        return len(context.data.get('nearby_enemies', [])) >= 1

    def _should_execute_post_supply_plan(self, context):
        return False

    def _should_force_push_base(self, context):
        return self._should_push_base(context)

    def _should_emergency_defend_base(self, context):
        if context.data.get('role_key') not in {'sentry', 'infantry', 'hero'}:
            return False
        return bool(context.data.get('emergency_base_defense', False))

    def _should_sentry_fly_slope(self, context):
        if context.data.get('role_key') != 'sentry':
            return False
        map_manager = context.map_manager
        if map_manager is None:
            return False
        slope_anchor = self._team_fly_slope_anchor(context)
        if slope_anchor is None:
            return False
        state = self._sentry_fly_slope_state.get(context.entity.id)
        if state is None:
            state = {'committed': self._is_opening_phase(context), 'completed': False}
            self._sentry_fly_slope_state[context.entity.id] = state
        if self._is_opening_phase(context):
            return not state.get('completed', False)
        if context.data.get('needs_heal_supply', False) or context.data.get('outnumbered', False):
            return False
        if float(context.data.get('health_ratio', 1.0)) < 0.55:
            return False
        map_center = context.data.get('map_center') or self.get_map_center(map_manager)
        if map_center is None or self._is_enemy_half_position(context.entity.team, context.entity.position['x'], map_center[0]):
            return False
        enemy_hero = context.data.get('enemy_hero')
        return enemy_hero is not None and enemy_hero.is_alive()

    def _should_take_enemy_highground(self, context):
        return self._outpost_pressure_highground_anchor(context) is not None

    def _should_claim_buff(self, context):
        return context.data.get('role_key') in {'hero', 'infantry'} and getattr(context.entity, 'terrain_buff_timer', 0.0) <= 0.25

    def _should_activate_energy(self, context):
        role_key = context.data.get('role_key')
        if role_key not in {'sentry', 'infantry'}:
            return False
        if context.data.get('energy_anchor') is None or context.data.get('energy_buff_active'):
            return False
        if not context.data.get('energy_can_activate', False):
            return False
        if context.data.get('needs_heal_supply', False):
            return False
        if role_key == 'infantry' and context.data.get('outnumbered', False):
            return False
        return True

    def _should_cross_terrain(self, context):
        return self._best_terrain_traversal_plan(context) is not None

    def _should_terrain_fly_slope(self, context):
        plan = self._best_terrain_traversal_plan(context)
        return bool(plan and plan.get('type') == 'fly_slope')

    def _should_terrain_first_step(self, context):
        plan = self._best_terrain_traversal_plan(context)
        return bool(plan and plan.get('type') == 'first_step')

    def _should_terrain_second_step(self, context):
        plan = self._best_terrain_traversal_plan(context)
        return bool(plan and plan.get('type') == 'second_step')

    def _should_recover_after_respawn(self, context):
        entity = context.entity
        if getattr(entity, 'front_gun_locked', False):
            return True
        if getattr(entity, 'respawn_weak_active', False):
            return True
        return getattr(entity, 'respawn_invalid_timer', 0.0) > 0.0 or getattr(entity, 'respawn_recovery_timer', 0.0) > 0.0

    def _should_defend_own_outpost(self, context):
        # 防守己方前哨站的分支已按需求关闭，始终返回 False。
        return False

    def _is_designated_outpost_defender(self, context):
        own_outpost = context.data.get('own_outpost')
        if own_outpost is None:
            return False
        candidates = []
        for other in context.entities:
            if other.team != context.entity.team or not other.is_alive():
                continue
            role_key = self._role_key(other)
            if role_key not in {'hero', 'infantry', 'sentry'}:
                continue
            distance = math.hypot(
                float(other.position['x']) - float(own_outpost.position['x']),
                float(other.position['y']) - float(own_outpost.position['y']),
            )
            role_priority = 2 if role_key == 'sentry' else (1 if role_key == 'hero' else 0)
            stable_id = sum(ord(char) for char in str(getattr(other, 'id', '')))
            candidates.append((distance, -role_priority, stable_id, other.id))
        if not candidates:
            return False
        candidates.sort()
        return candidates[0][3] == context.entity.id

    def _should_intercept_enemy_engineer(self, context):
        if context.data.get('role_key') not in {'infantry', 'sentry'}:
            return False
        enemy_engineer = context.data.get('enemy_engineer')
        if enemy_engineer is None or not enemy_engineer.is_alive():
            return False
        if getattr(enemy_engineer, 'carried_minerals', 0) > 0:
            return True
        enemy_base = context.data.get('enemy_base')
        if enemy_base is not None and self._distance(enemy_engineer, enemy_base) <= self._meters_to_world_units(7.5, context.map_manager):
            return True
        return False

    def _should_protect_hero(self, context):
        if context.data.get('role_key') != 'sentry':
            return False
        allied_hero = context.data.get('allied_hero')
        if allied_hero is None or not allied_hero.is_alive():
            return False
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (allied_hero.position['x'], allied_hero.position['y']), {'infantry', 'sentry'})
        return threat is not None and threat['distance'] <= self._meters_to_world_units(6.0, context.map_manager)

    def _should_support_infantry_push(self, context):
        if context.data.get('role_key') != 'sentry':
            return False
        allied_infantry = context.data.get('allied_infantry')
        enemy_outpost = context.data.get('enemy_outpost')
        if allied_infantry is None or enemy_outpost is None:
            return False
        return allied_infantry.is_alive() and enemy_outpost.is_alive()

    def _should_support_engineer(self, context):
        if context.data.get('role_key') != 'sentry':
            return False
        allied_engineer = context.data.get('allied_engineer')
        if allied_engineer is None or not allied_engineer.is_alive():
            return False
        if getattr(allied_engineer, 'carried_minerals', 0) > 0:
            return True
        mining_anchor = context.data.get('mining_anchor')
        if mining_anchor is None:
            return False
        return self._distance_to_point(allied_engineer, mining_anchor) <= self._meters_to_world_units(5.0, context.map_manager)

    def _should_hero_seek_cover(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        if self._hero_prefers_melee(context.entity):
            return False
        recent_pressure = self._recent_enemy_pressure(context)
        if any(entry['role_key'] == 'infantry' for entry in recent_pressure):
            return True
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (context.entity.position['x'], context.entity.position['y']), {'infantry'})
        return threat is not None and threat['distance'] <= self._meters_to_world_units(5.6, context.map_manager)

    def _should_hero_opening_highground(self, context):
        return context.data.get('role_key') == 'hero' and self._is_opening_phase(context)

    def _should_sentry_opening_highground(self, context):
        if context.data.get('role_key') != 'sentry' or not self._is_opening_phase(context):
            return False
        if self._sentry_opening_step_anchor(context) is None:
            return False
        state = self._sentry_fly_slope_state.get(context.entity.id)
        return not bool(state and state.get('completed', False))

    def _should_infantry_opening_highground(self, context):
        if context.data.get('role_key') != 'infantry' or not self._is_opening_phase(context):
            return False
        if not self._has_combat_ammo(context.entity, context.rules_engine):
            return False
        if self._needs_supply(context):
            return False
        return self._infantry_opening_highground_anchor(context) is not None

    def _should_hero_melee_highground_assault(self, context):
        if context.data.get('role_key') != 'hero' or not self._hero_prefers_melee(context.entity):
            return False
        return self._should_take_enemy_highground(context)

    def _should_hero_lob_outpost(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        if not self._hero_prefers_ranged(context.entity):
            return False
        if not self._hero_has_ranged_ammo(context):
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        return enemy_outpost is not None and enemy_outpost.is_alive()

    def _should_hero_lob_base(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        if not self._hero_prefers_ranged(context.entity):
            return False
        if not self._hero_has_ranged_ammo(context):
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        enemy_base = context.data.get('enemy_base')
        return enemy_base is not None and enemy_base.is_alive() and (enemy_outpost is None or not enemy_outpost.is_alive())

    def _needs_structure_support(self, context):
        outpost = context.data.get('own_outpost')
        base = context.data.get('own_base')
        return (
            (outpost is not None and outpost.health < outpost.max_health * 0.65)
            or (base is not None and base.health < base.max_health * 0.85)
        )

    def _needs_engineer_mining(self, context):
        capacity = self._minerals_per_trip(context.rules_engine)
        return (
            context.data.get('role_key') == 'engineer'
            and context.data.get('carried_minerals', 0) < capacity
            and context.data.get('mining_anchor') is not None
        )

    def _needs_engineer_exchange(self, context):
        capacity = self._minerals_per_trip(context.rules_engine)
        return (
            context.data.get('role_key') == 'engineer'
            and context.data.get('carried_minerals', 0) >= capacity
            and context.data.get('exchange_anchor') is not None
        )

    def _should_push_outpost(self, context):
        enemy_outpost = context.data.get('enemy_outpost')
        if enemy_outpost is None or not enemy_outpost.is_alive():
            return False
        if context.data.get('target') is not None:
            return False
        if context.data.get('role_key') in {'infantry', 'sentry'}:
            return not context.data.get('outnumbered', False)
        return context.game_time >= 30.0 and not context.data.get('outnumbered', False)

    def _should_push_base(self, context):
        if context.data.get('role_key') not in {'sentry', 'infantry', 'hero'}:
            return False
        if context.data.get('role_key') == 'hero' and self._hero_prefers_ranged(context.entity):
            return False
        enemy_base = context.data.get('enemy_base')
        if enemy_base is None or not enemy_base.is_alive():
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        if enemy_outpost is not None and enemy_outpost.is_alive():
            return False
        if not bool(context.data.get('base_assault_unlocked')):
            return False
        if float(context.data.get('team_health_ratio', 0.0)) <= 0.30:
            return False
        if not context.data.get('ally_sentry_in_enemy_half', False):
            return False
        if not context.data.get('ally_infantry_in_enemy_half', False):
            return False
        return True

    def _can_hero_lob_shot(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        if not self._hero_has_ranged_ammo(context):
            return False
        target = context.data.get('target')
        if target is None:
            return False
        highground = self._find_nearest_facility_center(context.map_manager, context.entity, ['second_step', 'fly_slope'])
        if highground is None:
            return False
        distance = target['distance']
        return distance >= self._meters_to_world_units(7.0, context.map_manager)

    def _can_sentry_exchange(self, context):
        entity = context.entity
        if entity.type != 'sentry' or context.rules_engine is None:
            return False
        if getattr(entity, 'exchange_cooldown', 0.0) > 0:
            return False
        gold = float(getattr(entity, 'gold', 0.0))
        ammo_cost = float(context.rules_engine.rules.get('sentry', {}).get('exchange', {}).get('ammo_cost', 0.0))
        opening_ammo_target = int(context.data.get('strategy', {}).get('opening_ammo_target', 340))
        return gold >= ammo_cost > 0 and getattr(entity, 'ammo', 0) < opening_ammo_target

    def _set_decision(self, context, summary, target=None, target_point=None, speed=None, posture=None, preferred_route=None, fire_control='idle', chassis_state='normal', turret_state='searching', angular_velocity=0.0, orbit=False, navigation_radius=None, structure_lob_target_type=None, disengage_deployment=False):
        entity = context.entity
        if target is not None and chassis_state == 'normal':
            chassis_state = 'spin'
            if abs(float(angular_velocity)) <= 1e-6:
                angular_velocity = 120.0
        move_target = target_point
        strategic_target = target_point
        if preferred_route is not None:
            transit_destination = preferred_route.get('target') if isinstance(preferred_route, dict) else preferred_route
            transit_anchor = self.choose_transit_anchor(entity, transit_destination, context.map_manager, context.rules_engine)
            if transit_anchor is not None:
                move_target = transit_anchor
                strategic_target = transit_destination
        velocity = (0.0, 0.0)
        if move_target is not None and speed is not None:
            if orbit and target is not None:
                orbit_distance = preferred_route.get('distance', 0.0) if isinstance(preferred_route, dict) else 0.0
                velocity = self.maintain_distance(entity, target, orbit_distance, speed)
            else:
                velocity = self.navigate_towards(entity, move_target, speed, context.map_manager)
        if getattr(entity, 'step_climb_state', None) or getattr(entity, 'ai_navigation_path_state', 'passable') == 'step-passable':
            chassis_state = 'normal'
            angular_velocity = 0.0
        staged_target = getattr(entity, 'ai_navigation_waypoint', None) or move_target
        velocity = self._apply_local_avoidance(entity, velocity, context.entities, staged_target)
        decision_target = target
        aim_point = target_point if target is None else (target['x'], target['y'])
        context.data['decision'] = {
            'summary': summary,
            'target': decision_target,
            'aim_point': aim_point,
            'navigation_target': strategic_target,
            'movement_target': staged_target,
            'navigation_radius': float(navigation_radius if navigation_radius is not None else self._target_region_radius(entity, strategic_target, context.map_manager)),
            'velocity': velocity,
            'fire_control_state': fire_control,
            'chassis_state': chassis_state,
            'turret_state': turret_state,
            'angular_velocity': angular_velocity,
            'posture': posture,
            'structure_lob_target_type': structure_lob_target_type,
            'disengage_deployment': bool(disengage_deployment),
        }
        return SUCCESS

    def _stage_short_term_goal(self, entity, target_point, map_manager):
        return target_point

    def _temporary_midpoint_waypoint(self, entity, target_point, map_manager):
        if map_manager is None or target_point is None:
            return None
        if self._role_key(entity) not in {'hero', 'infantry'}:
            return None
        if self._can_directly_traverse(entity, target_point, map_manager):
            return None
        midpoint = (
            (float(entity.position['x']) + float(target_point[0])) * 0.5,
            (float(entity.position['y']) + float(target_point[1])) * 0.5,
        )
        resolved = self._resolve_navigation_target(midpoint, map_manager, entity=entity)
        if resolved is None:
            return None
        waypoint = (float(resolved[0]), float(resolved[1]))
        if self._distance_to_point(entity, waypoint) <= self._arrival_tolerance_world_units(map_manager):
            return None
        midpoint_status = self._movement_segment_status(entity, (entity.position['x'], entity.position['y']), waypoint, map_manager)
        if not midpoint_status['passable']:
            return None
        return waypoint

    def _navigation_subgoal_spacing(self, map_manager=None):
        spacing_m = float(self._ai_config.get('navigation_subgoal_spacing_m', 1.75))
        base_step = 18.0
        if map_manager is not None:
            base_step = max(base_step, float(map_manager.terrain_grid_cell_size) * 2.0)
        return max(base_step, self._meters_to_world_units(spacing_m, map_manager))

    def _segment_path_points(self, path_points, map_manager=None, entity=None):
        if not path_points:
            return self.EMPTY_PATH_PREVIEW

        segmented = []
        seen = set()

        def add_point(point):
            normalized = (float(point[0]), float(point[1]))
            key = (round(normalized[0], 2), round(normalized[1], 2))
            if key in seen:
                return
            seen.add(key)
            segmented.append(normalized)

        add_point(path_points[0])
        max_segment = self._navigation_subgoal_spacing(map_manager)
        role_key = self._role_key(entity) if entity is not None else None
        if role_key in {'engineer', 'infantry'}:
            max_segment *= 1.18
        elif role_key in {'hero', 'sentry'}:
            max_segment *= 1.08
        for point in path_points[1:]:
            start = segmented[-1]
            end = (float(point[0]), float(point[1]))
            distance = math.hypot(end[0] - start[0], end[1] - start[1])
            subdivisions = max(1, int(math.ceil(distance / max(max_segment, 1e-6))))
            for index in range(1, subdivisions):
                progress = index / subdivisions
                add_point((
                    start[0] + (end[0] - start[0]) * progress,
                    start[1] + (end[1] - start[1]) * progress,
                ))
            add_point(end)
        return tuple(segmented)

    def _build_path_preview(self, entity, path, index):
        remaining_path = path[index:]
        return ((float(entity.position['x']), float(entity.position['y'])),) + tuple(remaining_path)

    def _path_waypoint_index(self, path, preferred_index=1):
        if not path:
            return 0
        minimum_index = 0 if len(path) == 1 else 1
        return max(minimum_index, min(int(preferred_index), len(path) - 1))

    def _pathfinder_distance_scale(self, entity, target_point, map_manager):
        if map_manager is None or target_point is None:
            return 1.0
        map_diagonal = math.hypot(float(getattr(map_manager, 'map_width', 0.0)), float(getattr(map_manager, 'map_height', 0.0)))
        if map_diagonal <= 1e-6:
            return 1.0
        target_distance = self._distance_to_point(entity, target_point)
        normalized = max(0.0, min(1.0, target_distance / map_diagonal))
        return 1.0 + normalized * 4.0

    def _action_return_to_supply_unlock(self, context):
        retreat_point = self.get_supply_slot(context.entity, context.map_manager)
        speed = self._meters_to_world_units(1.8, context.map_manager)
        return self._set_decision(context, '前管锁定，返回补给区解锁', target_point=retreat_point, speed=speed, posture='mobile')

    def _action_sentry_opening_exchange(self, context):
        result = context.rules_engine.request_exchange(context.entity, 'ammo', amount=1)
        summary = '开局分批兑换弹药并准备压前哨站' if result.get('ok') else '当前不满足兑换条件，改为直接压前哨站'
        target = context.data.get('enemy_outpost')
        if target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.6, context.map_manager)
        return self._set_decision(context, summary, target=self.entity_to_target(target, context.entity), target_point=(target.position['x'], target.position['y']), speed=speed, posture='mobile', turret_state='aiming')

    def _action_opening_supply(self, context):
        supply = self._supply_navigation_anchor(context.entity, context.map_manager)
        if supply is None:
            return FAILURE
        speed = self._meters_to_world_units(1.7, context.map_manager)
        if self._must_restock_before_combat(context):
            return self._set_decision(context, '弹药已空，立即前往补给区补弹', target_point=supply, speed=speed, preferred_route={'target': supply})
        if context.data.get('needs_heal_supply', False):
            if getattr(context.entity, 'ammo_type', 'none') != 'none':
                summary = '团队血线低于动态补给阈值，返回补给区回血并补弹'
            else:
                summary = '团队血线低于动态补给阈值，立即返回补给区回血'
            return self._set_decision(context, summary, target=context.data.get('target'), target_point=supply, speed=speed, preferred_route={'target': supply}, turret_state='aiming' if context.data.get('target') else 'searching')
        claimable = context.data.get('supply_claimable', 0)
        eta = context.data.get('supply_eta', 0.0)
        opening_target = self._opening_ammo_target(context)
        if self._is_opening_phase(context) and opening_target > 0 and getattr(context.entity, 'ammo', 0) < opening_target:
            summary = f'开局前往补给区建立弹药储备，目标弹量 {opening_target}'
        else:
            summary = '进入补给预约位，等待弹药窗口' if claimable <= 0 else '进入补给区领取弹药'
            if claimable <= 0 and eta > 10.0:
                return FAILURE
        return self._set_decision(context, summary, target_point=supply, speed=speed)

    def _action_execute_post_supply_plan(self, context):
        goal = context.data.get('post_supply_goal')
        if goal == 'home_stage':
            return self._action_move_to_post_supply_stage(context)
        if goal == 'hero_trapezoid':
            return self._action_hero_ranged_highground(context)
        if goal == 'hero_lob':
            return self._action_hero_ranged_highground(context)
        if goal == 'hero_highground':
            return self._action_hero_melee_highground(context)
        if goal == 'infantry_push':
            return self._action_infantry_post_supply_plan(context)
        return FAILURE

    def _action_move_to_post_supply_stage(self, context):
        stage_anchor = context.data.get('post_supply_stage_anchor')
        if stage_anchor is None:
            return FAILURE
        speed = self._meters_to_world_units(1.85, context.map_manager)
        target = context.data.get('target')
        summary = '补给完成，先转入堡垒与基地之间的集结区域'
        return self._set_decision(
            context,
            summary,
            target=target,
            target_point=stage_anchor,
            speed=speed,
            preferred_route={'target': stage_anchor},
            turret_state='aiming' if target is not None else 'searching',
        )

    def _action_hero_trapezoid_highground(self, context):
        return self._action_hero_ranged_highground(context)

    def _action_infantry_post_supply_plan(self, context):
        enemy_outpost = context.data.get('enemy_outpost')
        target = self.entity_to_target(enemy_outpost, context.entity) if enemy_outpost is not None and enemy_outpost.is_alive() else context.data.get('target')
        speed = self._meters_to_world_units(1.9, context.map_manager)
        highground = self._infantry_opening_highground_anchor(context)
        if highground is not None:
            return self._set_decision(
                context,
                '补给完成后前压高地区域，准备从高地推进敌方前哨站',
                target=target,
                target_point=highground,
                speed=speed,
                preferred_route={'target': highground},
                turret_state='aiming' if target is not None else 'searching',
            )
        if enemy_outpost is not None and enemy_outpost.is_alive():
            return self._action_push_outpost(context)
        return FAILURE

    def _action_hero_opening_highground(self, context):
        if self._hero_prefers_melee(context.entity):
            return self._action_hero_melee_highground(context)
        return self._action_hero_ranged_highground(context)

    def _action_hero_ranged_highground(self, context):
        hero_anchor = self._hero_ranged_highground_anchor(context)
        if hero_anchor is None:
            return FAILURE
        target_entity = context.data.get('enemy_outpost') or context.data.get('target')
        target = self.entity_to_target(target_entity, context.entity) if getattr(target_entity, 'position', None) is not None else context.data.get('target')
        speed = self._meters_to_world_units(2.0, context.map_manager)
        if self._distance_to_point(context.entity, hero_anchor) > self._meters_to_world_units(0.9, context.map_manager):
            return self._set_decision(
                context,
                '远程英雄优先进入己方梯形高地增益区，再开始吊射',
                target=target,
                target_point=hero_anchor,
                speed=speed,
                preferred_route={'target': hero_anchor},
                turret_state='aiming' if target is not None else 'searching',
            )
        if target is None:
            return self._set_decision(context, '远程英雄先吃到己方梯形高地增益，等待吊射目标暴露', target_point=hero_anchor, speed=speed * 0.5)
        context.data['decision'] = {
            'summary': '远程英雄占据己方梯形高地增益区执行吊射',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': hero_anchor,
            'movement_target': hero_anchor,
            'velocity': self.maintain_distance(context.entity, target, self._meters_to_world_units(7.2, context.map_manager), speed * 0.45, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': None,
        }
        return SUCCESS

    def _action_hero_melee_highground(self, context):
        hero_anchor = self._outpost_pressure_highground_anchor(context)
        if hero_anchor is None:
            return FAILURE
        target_entity = context.data.get('enemy_outpost') or context.data.get('target')
        target = self.entity_to_target(target_entity, context.entity) if getattr(target_entity, 'position', None) is not None else context.data.get('target')
        speed = self._meters_to_world_units(2.0, context.map_manager)
        if self._distance_to_point(context.entity, hero_anchor) > self._meters_to_world_units(1.0, context.map_manager):
            return self._set_decision(
                context,
                '英雄近战优先，先上我方高地增益区压制敌方前哨站',
                target=target,
                target_point=hero_anchor,
                speed=speed,
                preferred_route={'target': hero_anchor},
                turret_state='aiming' if target is not None else 'searching',
            )
        patrol_anchor = self._base_side_patrol_anchor(context.entity, context.map_manager, hero_anchor, context.data.get('enemy_base'))
        focus_target = self._priority_enemy_unit_target(context) or target
        if focus_target is None:
            return self._set_decision(
                context,
                '英雄已占领高地，沿靠近敌方基地一侧巡逻并持续索敌',
                target_point=patrol_anchor,
                speed=speed * 0.72,
                preferred_route={'target': patrol_anchor},
                turret_state='searching',
            )
        return self._safe_pressure_decision(context, focus_target, '英雄在高地基地侧巡逻并发现目标后立即打击', speed, preferred_distance_m=3.6)

    def _action_sentry_opening_highground(self, context):
        opening_anchor = self._sentry_opening_step_anchor(context)
        if opening_anchor is None:
            return self._action_sentry_fly_slope(context)
        target_entity = context.data.get('enemy_outpost')
        target = self.entity_to_target(target_entity, context.entity) if target_entity is not None else context.data.get('target')
        speed = self._meters_to_world_units(1.85, context.map_manager)
        if self._distance_to_point(context.entity, opening_anchor) > self._meters_to_world_units(0.9, context.map_manager):
            return self._set_decision(
                context,
                '哨兵开局先上一节一级台阶，再转入飞坡突入路线',
                target=target,
                target_point=opening_anchor,
                speed=speed,
                preferred_route={'target': opening_anchor},
                posture='attack',
                turret_state='aiming' if target is not None else 'searching',
            )
        return self._action_sentry_fly_slope(context)

    def _action_infantry_opening_highground(self, context):
        opening_anchor = self._infantry_opening_highground_anchor(context)
        if opening_anchor is None:
            return FAILURE
        enemy_outpost = context.data.get('enemy_outpost')
        target = self.entity_to_target(enemy_outpost, context.entity) if enemy_outpost is not None and enemy_outpost.is_alive() else (self._priority_enemy_unit_target(context) or context.data.get('target'))
        speed = self._meters_to_world_units(1.95, context.map_manager)
        return self._set_decision(
            context,
            '步兵开局直抢高地增益区，并准备压制敌方前哨站',
            target=target,
            target_point=opening_anchor,
            speed=speed,
            preferred_route={'target': opening_anchor},
            turret_state='aiming' if target is not None else 'searching',
        )

    def _action_sentry_fly_slope(self, context):
        state = self._sentry_fly_slope_state.get(context.entity.id)
        if state is None:
            state = {'committed': True, 'completed': False}
            self._sentry_fly_slope_state[context.entity.id] = state
        slope_anchor = self._team_fly_slope_start_anchor(context) or self._team_fly_slope_anchor(context)
        if slope_anchor is None:
            state['completed'] = True
            return FAILURE
        enemy_hero = context.data.get('enemy_hero')
        focus_target = self.entity_to_target(enemy_hero, context.entity) if enemy_hero is not None and enemy_hero.is_alive() else (self._priority_enemy_unit_target(context) or context.data.get('target'))
        speed = self._meters_to_world_units(2.2, context.map_manager)
        if self._distance_to_point(context.entity, slope_anchor) > self._meters_to_world_units(0.8, context.map_manager):
            result = self._set_decision(
                context,
                '哨兵前压前先进入飞坡起始位，准备对正坡道冲击敌方后排',
                target=focus_target,
                target_point=slope_anchor,
                speed=speed,
                preferred_route={'target': slope_anchor},
                posture='attack',
                turret_state='aiming' if focus_target else 'searching',
            )
        else:
            landing_point = self._fly_slope_landing_point(context, slope_anchor)
            desired_heading = 0.0 if context.entity.team == 'red' else 180.0
            angle_diff = ((desired_heading - float(getattr(context.entity, 'angle', 0.0)) + 180.0) % 360.0) - 180.0
            if abs(angle_diff) > 8.0:
                context.data['decision'] = {
                    'summary': '哨兵在飞坡起始增益点对正坡道，准备满功率冲坡',
                    'target': focus_target,
                    'aim_point': (focus_target['x'], focus_target['y']) if focus_target is not None else landing_point,
                    'navigation_target': slope_anchor,
                    'movement_target': slope_anchor,
                    'velocity': (0.0, 0.0),
                    'fire_control_state': 'idle',
                    'chassis_state': 'normal',
                    'turret_state': 'aiming' if focus_target else 'searching',
                    'angular_velocity': max(-240.0, min(240.0, angle_diff * 3.2)),
                    'posture': 'attack',
                }
                result = SUCCESS
            else:
                full_speed = self._max_speed_world_units() * 0.98
                context.data['decision'] = {
                    'summary': '哨兵从飞坡起始位满功率冲坡，直插敌方后排区域并就近开火',
                    'target': focus_target,
                    'aim_point': (focus_target['x'], focus_target['y']) if focus_target is not None else landing_point,
                    'navigation_target': landing_point,
                    'movement_target': landing_point,
                    'velocity': self.move_towards(context.entity, landing_point, full_speed),
                    'fire_control_state': 'idle',
                    'chassis_state': 'normal',
                    'turret_state': 'aiming' if focus_target else 'searching',
                    'angular_velocity': 0.0,
                    'posture': 'attack',
                }
                result = SUCCESS
        if context.map_manager is not None:
            map_center_x = self.get_map_center(context.map_manager)[0]
            if (context.entity.team == 'red' and context.entity.position['x'] >= map_center_x) or (context.entity.team == 'blue' and context.entity.position['x'] <= map_center_x):
                state['completed'] = True
        return result

    def _action_emergency_defend_base(self, context):
        defense_anchor = self._base_defense_anchor(context)
        if defense_anchor is None:
            return FAILURE
        threat_entity = self._highest_threat_enemy_in_own_half(context)
        speed = self._meters_to_world_units(2.0 if context.data.get('role_key') == 'hero' else 1.8, context.map_manager)
        summary = '己方基地血量劣势且本方半场受压，立即回防堡垒区域保护基地'
        if threat_entity is None:
            return self._set_decision(context, summary, target=context.data.get('target'), target_point=defense_anchor, speed=speed, preferred_route={'target': defense_anchor}, posture='attack' if context.entity.type == 'sentry' else None, turret_state='aiming' if context.data.get('target') else 'searching')
        threat_target = self.entity_to_target(threat_entity, context.entity)
        hold_point = defense_anchor if self._distance_to_point(threat_entity, defense_anchor) <= self._meters_to_world_units(6.0, context.map_manager) else (float(threat_entity.position['x']), float(threat_entity.position['y']))
        return self._set_decision(context, summary, target=threat_target, target_point=hold_point, speed=speed, preferred_route={'target': hold_point}, posture='attack' if context.entity.type == 'sentry' else None, turret_state='aiming')

    def _action_emergency_retreat(self, context):
        retreat_point = self.choose_retreat_anchor(context.entity, context.map_manager, prefer_supply=context.data.get('ammo_low', False))
        speed = self._meters_to_world_units(2.0, context.map_manager)
        posture = 'defense' if context.entity.type == 'sentry' else None
        return self._set_decision(context, '血量/热量/弹药不利，执行规避撤退', target=context.data.get('target'), target_point=retreat_point, speed=speed, posture=posture, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_recover_after_respawn(self, context):
        supply = self.get_supply_slot(context.entity, context.map_manager)
        if supply is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        posture = 'defense' if context.entity.type == 'sentry' else None
        return self._set_decision(context, '原地复活后撤回补给区，解锁枪管并恢复状态', target=context.data.get('target'), target_point=supply, speed=speed, preferred_route={'target': supply}, posture=posture, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_claim_buff(self, context):
        facility = self._find_best_buff_anchor(context)
        if facility is None:
            return FAILURE
        speed = self._meters_to_world_units(1.8, context.map_manager)
        center = self.facility_center(facility)
        return self._set_decision(context, f'前往 {facility.get("type")} 抢占地形增益', target=context.data.get('target'), target_point=center, speed=speed, preferred_route={'target': center})

    def _action_activate_energy(self, context):
        anchor = context.data.get('energy_anchor')
        if anchor is None:
            return FAILURE
        speed = self._meters_to_world_units(1.6, context.map_manager)
        return self._set_decision(context, '转入中央能量机关队伍激活位，保持激活窗口直至完成小/大能量机关', target=context.data.get('target'), target_point=anchor, speed=speed, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_cross_terrain(self, context):
        plan = self._best_terrain_traversal_plan(context)
        if plan is None:
            return FAILURE
        return self._action_terrain_traversal(context, plan.get('type'))

    def _action_terrain_fly_slope(self, context):
        return self._action_terrain_traversal(context, 'fly_slope')

    def _action_terrain_first_step(self, context):
        return self._action_terrain_traversal(context, 'first_step')

    def _action_terrain_second_step(self, context):
        return self._action_terrain_traversal(context, 'second_step')

    def _action_support_structures(self, context):
        support_target = context.data.get('own_outpost')
        if support_target is None or support_target.health >= support_target.max_health * 0.65:
            support_target = context.data.get('own_base')
        if support_target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.6, context.map_manager)
        if support_target.type == 'base':
            point = self.get_team_anchor(context.entity.team, 'base', context.map_manager, entity=context.entity)
        else:
            point = (support_target.position['x'], support_target.position['y'])
        return self._set_decision(context, f'工程位回防 {support_target.id}，保持修复/掩护链', target_point=point, speed=speed, preferred_route={'target': point})

    def _action_defend_own_outpost(self, context):
        own_outpost = context.data.get('own_outpost')
        own_base = context.data.get('own_base')
        facility = own_outpost if own_outpost is not None and own_outpost.is_alive() else own_base
        if facility is None:
            return FAILURE
        threat_anchor = (facility.position['x'], facility.position['y'])
        threat = self._nearest_enemy_by_roles(
            context.entities,
            context.entity.team,
            threat_anchor,
            {'hero', 'infantry', 'engineer', 'sentry'},
        )
        speed = self._meters_to_world_units(1.9, context.map_manager)
        if threat is not None:
            attacker = threat['entity']
            point = self._escort_anchor(facility, attacker, context.map_manager)
            summary = '己方据点受压，优先击退逼近的敌方单位'
            return self._set_decision(context, summary, target=self.entity_to_target(attacker, context.entity), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming')
        point = threat_anchor
        return self._set_decision(context, '己方据点受击，回防并建立掩护阵位', target=context.data.get('target'), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_intercept_enemy_engineer(self, context):
        enemy_engineer = context.data.get('enemy_engineer')
        if enemy_engineer is None:
            return FAILURE
        point = (enemy_engineer.position['x'], enemy_engineer.position['y'])
        speed = self._meters_to_world_units(2.0 if context.data.get('role_key') == 'infantry' else 1.7, context.map_manager)
        return self._set_decision(context, '拦截敌方工程回家路线，切断其经济与能量节奏', target=self.entity_to_target(enemy_engineer, context.entity), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming')

    def _action_protect_hero(self, context):
        allied_hero = context.data.get('allied_hero')
        if allied_hero is None:
            return FAILURE
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (allied_hero.position['x'], allied_hero.position['y']), {'infantry', 'sentry'})
        target = threat['entity'] if threat is not None else None
        point = self._escort_anchor(allied_hero, target, context.map_manager)
        speed = self._meters_to_world_units(1.6, context.map_manager)
        decision_target = self.entity_to_target(target, context.entity) if target is not None else context.data.get('target')
        return self._set_decision(context, '哨兵贴近英雄提供火力保护，阻断敌方近身威胁', target=decision_target, target_point=point, speed=speed, preferred_route={'target': point}, posture='attack', turret_state='aiming' if decision_target else 'searching')

    def _action_support_infantry_push(self, context):
        allied_infantry = context.data.get('allied_infantry')
        enemy_outpost = context.data.get('enemy_outpost')
        if allied_infantry is None:
            return FAILURE
        anchor_target = enemy_outpost if enemy_outpost is not None and enemy_outpost.is_alive() else allied_infantry
        point = self._escort_anchor(allied_infantry, anchor_target, context.map_manager)
        speed = self._meters_to_world_units(1.6, context.map_manager)
        decision_target = self.entity_to_target(anchor_target, context.entity) if anchor_target is not None and anchor_target is not allied_infantry else context.data.get('target')
        return self._set_decision(context, '哨兵与步兵协同压前哨站，顺带封堵对方回防线', target=decision_target, target_point=point, speed=speed, preferred_route={'target': point}, posture='attack', turret_state='aiming' if decision_target else 'searching')

    def _action_support_engineer(self, context):
        allied_engineer = context.data.get('allied_engineer')
        if allied_engineer is None:
            return FAILURE
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (allied_engineer.position['x'], allied_engineer.position['y']), {'infantry', 'hero', 'sentry'})
        threat_entity = threat['entity'] if threat is not None else None
        point = self._escort_anchor(allied_engineer, threat_entity, context.map_manager)
        speed = self._meters_to_world_units(1.55, context.map_manager)
        decision_target = self.entity_to_target(threat_entity, context.entity) if threat_entity is not None else context.data.get('target')
        return self._set_decision(context, '哨兵贴近工程巡航掩护，保障采矿与兑矿路线安全', target=decision_target, target_point=point, speed=speed, preferred_route={'target': point}, posture='attack', turret_state='aiming' if decision_target else 'searching')

    def _minerals_per_trip(self, rules_engine):
        raw = 2
        if rules_engine is not None:
            raw = rules_engine.rules.get('mining', {}).get('minerals_per_trip', 2)
        try:
            amount = int(raw)
        except (TypeError, ValueError):
            amount = 2
        return min(3, max(1, amount))

    def _action_engineer_mine(self, context):
        anchor = context.data.get('mining_anchor')
        if anchor is None:
            return FAILURE
        speed = self._meters_to_world_units(2.0, context.map_manager)
        capacity = self._minerals_per_trip(context.rules_engine)
        summary = f'工程前往取矿点，单次采集上限 {capacity} 单位'
        return self._set_decision(context, summary, target_point=anchor, speed=speed, preferred_route={'target': anchor})

    def _action_engineer_exchange(self, context):
        anchor = context.data.get('exchange_anchor')
        if anchor is None:
            return FAILURE
        carried = context.data.get('carried_minerals', 0)
        speed = self._meters_to_world_units(2.15, context.map_manager)
        summary = f'工程携带 {carried} 单位矿物，快速兑矿并优先保命'
        return self._set_decision(context, summary, target_point=anchor, speed=speed, preferred_route={'target': anchor})

    def _action_engineer_cycle(self, context):
        if context.data.get('carried_minerals', 0) > 0:
            result = self._action_engineer_exchange(context)
            if result == SUCCESS:
                return result
        return self._action_engineer_mine(context)

    def _supply_navigation_anchor(self, entity, map_manager):
        if map_manager is None:
            return None
        # 对步兵/英雄，补给点必须落在实际补给区内部，避免在外围大半径即判定到达。
        return self.get_supply_slot(entity, map_manager)

    def _post_supply_stage_anchor(self, entity, map_manager):
        if map_manager is None:
            return None
        fort_region = self._find_team_facility(map_manager, entity.team, 'fort')
        base_region = self._find_team_facility(map_manager, entity.team, 'base')
        fort_anchor = self.facility_center(fort_region) if fort_region is not None else None
        base_anchor = self.facility_center(base_region) if base_region is not None else None
        if fort_anchor is not None:
            if base_anchor is not None:
                dx = float(base_anchor[0]) - float(fort_anchor[0])
                dy = float(base_anchor[1]) - float(fort_anchor[1])
                offset = self._meters_to_world_units(0.8, map_manager)
                length = math.hypot(dx, dy)
                if length > 1e-6:
                    staged = (float(fort_anchor[0]) + dx / length * offset, float(fort_anchor[1]) + dy / length * offset)
                else:
                    staged = fort_anchor
                return self._resolve_navigation_target(staged, map_manager, entity=entity)
            return self._resolve_navigation_target(fort_anchor, map_manager, entity=entity)
        if base_anchor is not None:
            return self._resolve_navigation_target(base_anchor, map_manager, entity=entity)
        return self._supply_navigation_anchor(entity, map_manager)

    def _basic_movement_segment_status(self, entity, from_point, to_point, map_manager, step_limit=None):
        if map_manager is None or from_point is None or to_point is None:
            return {'passable': False, 'requires_step': False, 'transition': None, 'traversal': None, 'reason': 'no_map', 'detour_points': self.EMPTY_PATH_PREVIEW}
        resolved_step_limit = float(step_limit if step_limit is not None else getattr(entity, 'max_terrain_step_height_m', 0.05))
        cache_key = (
            'basic',
            getattr(entity, 'id', None),
            int(getattr(map_manager, 'raster_version', 0)),
            round(float(getattr(entity, 'collision_radius', 0.0)), 2),
            bool(getattr(entity, 'can_climb_steps', False)),
            round(resolved_step_limit, 3),
            round(float(from_point[0]), 2),
            round(float(from_point[1]), 2),
            round(float(to_point[0]), 2),
            round(float(to_point[1]), 2),
        )
        cached_status = self._movement_status_cache.get(cache_key)
        if cached_status is not None:
            return cached_status
        result = map_manager.evaluate_movement_path(
            float(from_point[0]),
            float(from_point[1]),
            float(to_point[0]),
            float(to_point[1]),
            max_height_delta_m=resolved_step_limit,
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
        )
        traversal = map_manager.describe_segment_traversal(
            float(from_point[0]),
            float(from_point[1]),
            float(to_point[0]),
            float(to_point[1]),
            max_height_delta_m=resolved_step_limit,
        )
        if result.get('ok'):
            traversal_type = str(traversal.get('facility_type', '')) if isinstance(traversal, dict) else ''
            requires_step = bool(result.get('requires_step_alignment')) or traversal_type in {'first_step', 'second_step', 'terrain_step'}
            status = {
                'passable': True,
                'requires_step': requires_step,
                'transition': traversal if requires_step else None,
                'traversal': traversal,
                'reason': 'ok',
                'detour_points': self.EMPTY_PATH_PREVIEW,
            }
            self._movement_status_cache[cache_key] = status
            return status
        transition = None
        if result.get('reason') == 'height_delta' and getattr(entity, 'can_climb_steps', False):
            transition = map_manager.get_step_transition(
                float(from_point[0]),
                float(from_point[1]),
                float(to_point[0]),
                float(to_point[1]),
                max_height_delta_m=resolved_step_limit,
            )
        if transition is not None:
            traversal = traversal or transition
            status = {
                'passable': True,
                'requires_step': True,
                'transition': transition,
                'traversal': traversal,
                'reason': 'step',
                'detour_points': self.EMPTY_PATH_PREVIEW,
            }
            self._movement_status_cache[cache_key] = status
            return status
        status = {
            'passable': False,
            'requires_step': False,
            'transition': None,
            'traversal': traversal,
            'reason': result.get('reason', 'blocked'),
            'detour_points': self.EMPTY_PATH_PREVIEW,
        }
        self._movement_status_cache[cache_key] = status
        return status

    def _front_obstacle_probe_distance(self, map_manager):
        if map_manager is None:
            return 0.0
        return max(float(getattr(map_manager, 'terrain_grid_cell_size', 8)) * 4.0, self._meters_to_world_units(1.5, map_manager))

    def _front_obstacle_clear(self, entity, from_point, to_point, map_manager, step_limit=None):
        if map_manager is None or from_point is None or to_point is None:
            return False
        distance = math.hypot(float(to_point[0]) - float(from_point[0]), float(to_point[1]) - float(from_point[1]))
        if distance <= 1e-6:
            return True
        resolved_step_limit = float(step_limit if step_limit is not None else getattr(entity, 'max_terrain_step_height_m', 0.05))
        trace_distance = min(distance, self._front_obstacle_probe_distance(map_manager))
        obstacle = map_manager.trace_movement_obstacle(
            float(from_point[0]),
            float(from_point[1]),
            float(to_point[0]),
            float(to_point[1]),
            max_height_delta_m=resolved_step_limit,
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
            max_distance=trace_distance,
        )
        return obstacle is None

    def _probe_segment_detour(self, entity, from_point, to_point, map_manager, step_limit=None):
        if map_manager is None or from_point is None or to_point is None:
            return self.EMPTY_PATH_PREVIEW
        start_x = float(from_point[0])
        start_y = float(from_point[1])
        end_x = float(to_point[0])
        end_y = float(to_point[1])
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        distance = math.hypot(delta_x, delta_y)
        collision_radius = float(getattr(entity, 'collision_radius', 0.0))
        if distance <= max(20.0, collision_radius * 1.2):
            return self.EMPTY_PATH_PREVIEW

        resolved_step_limit = float(step_limit if step_limit is not None else getattr(entity, 'max_terrain_step_height_m', 0.05))
        front_probe_distance = min(distance, self._front_obstacle_probe_distance(map_manager))
        obstacle = map_manager.trace_movement_obstacle(
            start_x,
            start_y,
            end_x,
            end_y,
            max_height_delta_m=resolved_step_limit,
            collision_radius=collision_radius,
            max_distance=front_probe_distance,
        )
        if obstacle is None:
            return self.EMPTY_PATH_PREVIEW

        direction_x = delta_x / max(distance, 1e-6)
        direction_y = delta_y / max(distance, 1e-6)
        extension = map_manager.estimate_obstacle_extension_direction(
            obstacle.get('point'),
            approach_point=obstacle.get('previous_point'),
            sample_radius=max(float(map_manager.terrain_grid_cell_size) * 3.0, collision_radius * 2.5, 20.0),
            sample_step=max(2, int(round(float(map_manager.terrain_grid_cell_size) * 0.5))),
        )
        outward_x = float(obstacle.get('previous_point', (start_x, start_y))[0]) - float(obstacle.get('point', (start_x, start_y))[0])
        outward_y = float(obstacle.get('previous_point', (start_x, start_y))[1]) - float(obstacle.get('point', (start_x, start_y))[1])
        outward_length = math.hypot(outward_x, outward_y)
        if outward_length <= 1e-6:
            outward_x = -direction_x
            outward_y = -direction_y
            outward_length = math.hypot(outward_x, outward_y)
        outward_x /= max(outward_length, 1e-6)
        outward_y /= max(outward_length, 1e-6)

        if extension is not None:
            tangent_x, tangent_y = extension.get('tangent', (0.0, 0.0))
            normal_x, normal_y = extension.get('normal', (outward_x, outward_y))
        else:
            tangent_x, tangent_y = -direction_y, direction_x
            normal_x, normal_y = outward_x, outward_y

        tangent_length = math.hypot(tangent_x, tangent_y)
        if tangent_length <= 1e-6:
            return self.EMPTY_PATH_PREVIEW
        tangent_x /= tangent_length
        tangent_y /= tangent_length
        normal_length = math.hypot(normal_x, normal_y)
        if normal_length <= 1e-6:
            normal_x, normal_y = outward_x, outward_y
            normal_length = math.hypot(normal_x, normal_y)
        normal_x /= max(normal_length, 1e-6)
        normal_y /= max(normal_length, 1e-6)

        slide_step = max(float(map_manager.terrain_grid_cell_size) * 1.25, collision_radius * 1.1, 10.0)
        clearance = max(float(map_manager.terrain_grid_cell_size) * 0.9, collision_radius + 4.0, 8.0)
        search_radius = int(max(slide_step * 2.5, clearance * 2.0, 20.0))
        search_step = max(4, int(map_manager.terrain_grid_cell_size))
        max_slide_distance = max(self._meters_to_world_units(6.0, map_manager), front_probe_distance * 2.5)
        max_slide_steps = max(4, int(math.ceil(max_slide_distance / max(slide_step, 1.0))))
        best_partial_path = self.EMPTY_PATH_PREVIEW
        best_partial_remaining = float('inf')

        for tangent_sign in (1.0, -1.0):
            slide_dir_x = tangent_x * tangent_sign
            slide_dir_y = tangent_y * tangent_sign
            current_point = (start_x, start_y)
            path_points = []
            visited = set()
            for _ in range(max_slide_steps):
                raw_point = (
                    current_point[0] + slide_dir_x * slide_step + normal_x * clearance,
                    current_point[1] + slide_dir_y * slide_step + normal_y * clearance,
                )
                resolved = map_manager.find_nearest_passable_point(
                    raw_point,
                    collision_radius=collision_radius,
                    search_radius=search_radius,
                    step=search_step,
                )
                if resolved is None:
                    break
                candidate = (float(resolved[0]), float(resolved[1]))
                candidate_key = (round(candidate[0], 2), round(candidate[1], 2))
                if candidate_key in visited:
                    break
                visited.add(candidate_key)
                if math.hypot(candidate[0] - current_point[0], candidate[1] - current_point[1]) <= max(4.0, collision_radius * 0.35):
                    continue
                segment_status = self._basic_movement_segment_status(entity, current_point, candidate, map_manager, step_limit=step_limit)
                if not segment_status['passable']:
                    break
                if not path_points or path_points[-1] != candidate:
                    path_points.append(candidate)
                current_point = candidate
                remaining_distance = math.hypot(end_x - current_point[0], end_y - current_point[1])
                if remaining_distance < best_partial_remaining:
                    best_partial_remaining = remaining_distance
                    best_partial_path = tuple(path_points)
                if self._front_obstacle_clear(entity, current_point, (end_x, end_y), map_manager, step_limit=step_limit):
                    return tuple(path_points)
        return tuple(best_partial_path)

    def _movement_segment_status(self, entity, from_point, to_point, map_manager, step_limit=None):
        resolved_step_limit = float(step_limit if step_limit is not None else getattr(entity, 'max_terrain_step_height_m', 0.05))
        cache_key = (
            'full',
            getattr(entity, 'id', None),
            int(getattr(map_manager, 'raster_version', 0)) if map_manager is not None else 0,
            round(float(getattr(entity, 'collision_radius', 0.0)), 2),
            bool(getattr(entity, 'can_climb_steps', False)),
            round(resolved_step_limit, 3),
            round(float(from_point[0]), 2) if from_point is not None else 0.0,
            round(float(from_point[1]), 2) if from_point is not None else 0.0,
            round(float(to_point[0]), 2) if to_point is not None else 0.0,
            round(float(to_point[1]), 2) if to_point is not None else 0.0,
        )
        cached_status = self._movement_status_cache.get(cache_key)
        if cached_status is not None:
            return cached_status
        status = self._basic_movement_segment_status(entity, from_point, to_point, map_manager, step_limit=step_limit)
        if status['passable']:
            self._movement_status_cache[cache_key] = status
            return status
        if status.get('reason') not in {'blocked', 'height_delta'}:
            self._movement_status_cache[cache_key] = status
            return status
        detour_points = self._probe_segment_detour(entity, from_point, to_point, map_manager, step_limit=step_limit)
        if detour_points:
            status = {
                'passable': True,
                'requires_step': False,
                'transition': None,
                'traversal': None,
                'reason': 'probe_detour',
                'detour_points': detour_points,
            }
            self._movement_status_cache[cache_key] = status
            return status
        self._movement_status_cache[cache_key] = status
        return status

    def _action_support_sentry_screen(self, context):
        allied_sentry = context.data.get('allied_sentry')
        if allied_sentry is None:
            return FAILURE
        offset = self._screen_offset(context.entity.team)
        point = (allied_sentry.position['x'] + offset[0], allied_sentry.position['y'] + offset[1])
        speed = self._meters_to_world_units(1.4, context.map_manager)
        return self._set_decision(context, '工程位围绕己方哨兵展开护送与补位', target=context.data.get('target'), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='searching')

    def _action_highground_assault(self, context):
        anchor = self._outpost_pressure_highground_anchor(context)
        if anchor is None:
            return FAILURE
        enemy_outpost = context.data.get('enemy_outpost')
        primary_target = enemy_outpost if enemy_outpost is not None and enemy_outpost.is_alive() else None
        target = self._priority_enemy_unit_target(context) or (self.entity_to_target(primary_target, context.entity) if primary_target is not None else context.data.get('target'))
        speed = self._meters_to_world_units(2.0 if context.data.get('role_key') == 'hero' else 1.85, context.map_manager)
        strategic_target = (primary_target.position['x'], primary_target.position['y']) if primary_target is not None else anchor
        return self._set_decision(
            context,
            '占领高地增益区，从高地火力压制敌方前哨站',
            target=target,
            target_point=anchor,
            speed=speed,
            preferred_route={'target': anchor, 'strategic_target': strategic_target},
            turret_state='aiming' if target else 'searching',
        )

    def _action_teamfight_push(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        desired_distance = self._meters_to_world_units(4.6 if context.data.get('role_key') == 'hero' else 3.8, context.map_manager)
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)
        velocity = self.engage_from_anchor(context.entity, target, guard_anchor, desired_distance=desired_distance, speed=speed, map_manager=context.map_manager)
        context.data['decision'] = {
            'summary': '与友军形成团战面，压制敌方主火力',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': guard_anchor,
            'movement_target': guard_anchor,
            'velocity': velocity,
            'fire_control_state': 'idle',
            'chassis_state': 'follow_turret',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': 'attack' if context.entity.type == 'sentry' else None,
        }
        return SUCCESS

    def _action_teamfight_cover(self, context):
        target = context.data.get('target')
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)
        speed = self._meters_to_world_units(1.6, context.map_manager)
        summary = '围绕据点维持交叉火力，准备接团'
        return self._set_decision(context, summary, target=target, target_point=guard_anchor, speed=speed, preferred_route={'target': guard_anchor}, posture='attack' if context.entity.type == 'sentry' else None, turret_state='aiming' if target else 'searching')

    def _unit_support_weight(self, role_key):
        return {
            'hero': 1.35,
            'sentry': 1.30,
            'infantry': 1.00,
            'engineer': 0.55,
        }.get(role_key, 1.0)

    def _desired_safe_autoaim_distance_m(self, context, target=None):
        role_key = context.data.get('role_key')
        distance_m = {
            'hero': 4.8,
            'sentry': 4.2,
            'infantry': 3.4,
            'engineer': 2.6,
        }.get(role_key, 3.5)
        if target is not None and target.get('type') == 'outpost':
            distance_m = max(distance_m, 3.8)
        elif target is not None and target.get('type') == 'base':
            distance_m = max(distance_m, 4.4)
        if context.data.get('outnumbered', False):
            distance_m += 0.6
        if context.data.get('health_ratio', 1.0) < 0.55:
            distance_m += 0.5
        if context.data.get('heat_ratio', 0.0) > 0.65:
            distance_m += 0.3
        return min(5.0, max(2.0, distance_m))

    def _assess_target_protection(self, context, target):
        if target is None:
            return 0.0, 0.0, False
        support_radius = self._meters_to_world_units(5.5, context.map_manager)
        target_point = (target['x'], target['y'])
        target_id = target.get('id')
        enemy_support = 0.0
        ally_support = self._unit_support_weight(context.data.get('role_key'))
        for other in context.entities:
            if not other.is_alive():
                continue
            distance = math.hypot(other.position['x'] - target_point[0], other.position['y'] - target_point[1])
            if distance > support_radius:
                continue
            weight = self._unit_support_weight(self._role_key(other))
            if other.team != context.entity.team:
                if str(getattr(other, 'id', '')) == str(target_id):
                    continue
                enemy_support += weight
            elif other.id != context.entity.id:
                ally_support += weight * 0.9

        for structure, bonus in ((context.data.get('enemy_outpost'), 0.9), (context.data.get('enemy_base'), 1.2)):
            if structure is None or not structure.is_alive():
                continue
            distance = math.hypot(structure.position['x'] - target_point[0], structure.position['y'] - target_point[1])
            if distance <= self._meters_to_world_units(4.5, context.map_manager):
                enemy_support += bonus

        threshold = 0.75
        if context.data.get('health_ratio', 1.0) < 0.5 or context.data.get('outnumbered', False):
            threshold = 0.25
        return enemy_support, ally_support, enemy_support > ally_support + threshold

    def _standoff_anchor(self, entity, target, map_manager, desired_distance):
        dx = float(entity.position['x']) - float(target['x'])
        dy = float(entity.position['y']) - float(target['y'])
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx, dy, length = 0.0, -1.0, 1.0
        anchor = (
            float(target['x']) + dx / length * desired_distance,
            float(target['y']) + dy / length * desired_distance,
        )
        return self._resolve_navigation_target(anchor, map_manager, entity=entity)

    def _safe_pressure_decision(self, context, target, summary, speed, preferred_distance_m=None):
        if target is None:
            return FAILURE
        safe_distance_m = self._desired_safe_autoaim_distance_m(context, target)
        if preferred_distance_m is not None:
            safe_distance_m = min(5.0, max(2.0, max(safe_distance_m, float(preferred_distance_m))))
        desired_distance = self._meters_to_world_units(safe_distance_m, context.map_manager)
        enemy_support, ally_support, overprotected = self._assess_target_protection(context, target)
        standoff_anchor = self._standoff_anchor(context.entity, target, context.map_manager, desired_distance)
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)

        if context.data.get('health_ratio', 1.0) < 0.38:
            nav_target = self.choose_retreat_anchor(context.entity, context.map_manager, prefer_supply=context.data.get('ammo_low', False))
            velocity = self.navigate_towards(context.entity, nav_target, speed, context.map_manager)
            detail = '，当前状态偏危险，先回撤保命'
        elif overprotected:
            fallback_highground = self._fallback_highground_anchor(context)
            nav_target = fallback_highground or guard_anchor or standoff_anchor
            hold_distance = self._meters_to_world_units(min(5.0, safe_distance_m + 0.6), context.map_manager)
            velocity = self.engage_from_anchor(context.entity, target, nav_target, desired_distance=hold_distance, speed=speed * 0.78, map_manager=context.map_manager)
            detail = f'，目标受保护过多({enemy_support:.1f}>{ally_support:.1f})，转为安全压制'
        else:
            nav_target = standoff_anchor or guard_anchor or (context.entity.position["x"], context.entity.position["y"])
            velocity = self.engage_from_anchor(context.entity, target, nav_target, desired_distance=desired_distance, speed=speed, map_manager=context.map_manager)
            detail = f'，保持 {safe_distance_m:.1f}m 安全自瞄距离'

        context.data['decision'] = {
            'summary': f'{summary}{detail}',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': nav_target,
            'movement_target': nav_target,
            'velocity': velocity,
            'fire_control_state': 'idle',
            'chassis_state': 'follow_turret' if target.get('type') not in {'base', 'outpost'} else 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': 'attack' if context.entity.type == 'sentry' and not overprotected else None,
        }
        return SUCCESS

    def _priority_enemy_unit_target(self, context):
        enemies = [
            enemy for enemy in context.entities
            if enemy.team != context.entity.team and enemy.is_alive() and enemy.type in {'robot', 'sentry'}
        ]
        best = self._select_priority_target_entity(
            context.entity,
            enemies,
            context.data.get('strategy', {}),
            rules_engine=context.rules_engine,
        )
        if best is None:
            return None
        return self.entity_to_target(best, context.entity)

    def _action_swarm_attack(self, context):
        target = self._priority_enemy_unit_target(context) or context.data.get('target')
        if target is None:
            return FAILURE
        role_key = context.data.get('role_key')
        speed = self._meters_to_world_units(2.1 if role_key == 'hero' else 1.95, context.map_manager)
        preferred_distance_m = 2.6 if target.get('type') in {'robot', 'sentry'} else 3.0
        return self._safe_pressure_decision(context, target, '发现敌人就近集火推进', speed, preferred_distance_m=preferred_distance_m)

    def _action_pursue_enemy(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        role_key = context.data.get('role_key')
        speed = self._meters_to_world_units(2.0 if role_key == 'hero' else 1.8, context.map_manager)

        pursuit_target = target
        pursuit_point = (target['x'], target['y'])
        summary = f'追击敌方单位 {target["id"]}，维持压力'

        enemy_outpost = context.data.get('enemy_outpost')
        enemy_base = context.data.get('enemy_base')
        if role_key == 'infantry':
            if enemy_outpost is not None and enemy_outpost.is_alive():
                pursuit_target = self.entity_to_target(enemy_outpost, context.entity)
                pursuit_point = self._assault_anchor(context.entity, enemy_outpost, context.map_manager, preferred_distance_m=2.8)
                summary = '追击目标：敌方前哨站（优先压制前哨）'
            elif bool(context.data.get('base_assault_unlocked')) and enemy_base is not None and enemy_base.is_alive():
                pursuit_target = self.entity_to_target(enemy_base, context.entity)
                pursuit_point = self._assault_anchor(context.entity, enemy_base, context.map_manager, preferred_distance_m=3.5)
                summary = '追击目标：敌方基地（前哨已破，转入推基地）'
        elif target.get('type') == 'outpost' and enemy_outpost is not None and enemy_outpost.is_alive():
            pursuit_target = self.entity_to_target(enemy_outpost, context.entity)
            pursuit_point = self._assault_anchor(context.entity, enemy_outpost, context.map_manager, preferred_distance_m=2.8)
            summary = '追击目标：敌方前哨站'
        elif target.get('type') == 'base' and enemy_base is not None and enemy_base.is_alive():
            pursuit_target = self.entity_to_target(enemy_base, context.entity)
            summary = '追击目标：敌方基地'
        preferred_distance_m = None
        if pursuit_target.get('type') == 'outpost':
            preferred_distance_m = 2.8
        elif pursuit_target.get('type') == 'base':
            preferred_distance_m = 3.5
        return self._safe_pressure_decision(context, pursuit_target, summary, speed, preferred_distance_m=preferred_distance_m)

    def _action_sentry_engage(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        strategy = context.data.get('strategy', {})
        ideal_distance = self._meters_to_world_units(float(strategy.get('ideal_distance_m', 5.5)), context.map_manager)
        engage_speed = self._meters_to_world_units(float(strategy.get('engage_speed_mps', 1.8)), context.map_manager)
        firing_distance = self._meters_to_world_units(float(strategy.get('firing_distance_m', 9.0)), context.map_manager)
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)
        context.data['decision'] = {
            'summary': f'锁定 {target["id"]}，围绕防守锚点输出',
            'posture': 'attack' if target['distance'] <= firing_distance and context.data.get('heat_ratio', 0.0) < 0.7 else 'mobile',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': guard_anchor,
            'movement_target': guard_anchor,
            'velocity': self.engage_from_anchor(context.entity, target, guard_anchor, desired_distance=ideal_distance, speed=engage_speed, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'follow_turret' if target['distance'] <= self._meters_to_world_units(5.5, context.map_manager) else 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
        }
        return SUCCESS

    def _action_hero_lob_shot(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        highground = self._find_nearest_facility_center(context.map_manager, context.entity, ['second_step', 'fly_slope'])
        if highground is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        distance = self._distance_to_point(context.entity, highground)
        if distance > 65:
            return self._set_decision(context, '英雄转入高台吊射位，准备远距离压制', target=target, target_point=highground, speed=speed, turret_state='aiming')
        context.data['decision'] = {
            'summary': '英雄占据高台吊射位，远距离压制目标',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': highground,
            'movement_target': highground,
            'velocity': self.maintain_distance(context.entity, target, self._meters_to_world_units(7.5, context.map_manager), speed * 0.55, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': None,
        }
        return SUCCESS

    def _action_hero_seek_cover(self, context):
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (context.entity.position['x'], context.entity.position['y']), {'infantry', 'sentry'})
        if threat is None:
            return FAILURE
        cover_anchor = self.get_supply_slot(context.entity, context.map_manager) or self.choose_retreat_anchor(context.entity, context.map_manager, prefer_supply=True)
        speed = self._meters_to_world_units(2.1, context.map_manager)
        return self._set_decision(context, '远程英雄遭遇敌方压迫，快速撤回己方补给区重新部署', target=self.entity_to_target(threat['entity'], context.entity), target_point=cover_anchor, speed=speed, preferred_route={'target': cover_anchor}, turret_state='aiming')

    def _action_hero_lob_outpost(self, context):
        enemy_outpost = context.data.get('enemy_outpost')
        if enemy_outpost is None:
            return FAILURE
        return self._action_hero_lob_structure(context, enemy_outpost, '英雄转入 6-8m 吊射位，优先压制敌方前哨站')

    def _action_hero_lob_base(self, context):
        enemy_base = context.data.get('enemy_base')
        if enemy_base is None:
            return FAILURE
        anchor = self._outpost_pressure_highground_anchor(context)
        if anchor is None:
            return self._action_hero_lob_structure(context, enemy_base, '敌方前哨站已倒，英雄转火基地并保持远距离吊射', structure_lob_target_type='base', disengage_deployment=True)
        speed = self._meters_to_world_units(1.9, context.map_manager)
        target = self.entity_to_target(enemy_base, context.entity)
        if self._distance_to_point(context.entity, anchor) > self._meters_to_world_units(0.8, context.map_manager):
            return self._set_decision(context, '敌方前哨站已倒，远程英雄转入己方高地增益区吊射敌方基地', target=target, target_point=anchor, speed=speed, preferred_route={'target': anchor}, turret_state='aiming', structure_lob_target_type='base', disengage_deployment=True)
        context.data['decision'] = {
            'summary': '远程英雄占据己方高地增益区，对敌方基地实施吊射',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': anchor,
            'movement_target': anchor,
            'velocity': self.maintain_distance(context.entity, target, self._meters_to_world_units(7.2, context.map_manager), speed * 0.4, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': None,
            'structure_lob_target_type': 'base',
            'disengage_deployment': True,
        }
        return SUCCESS

    def _action_hero_lob_structure(self, context, target_entity, summary, structure_lob_target_type=None, disengage_deployment=False):
        preferred_distance = self._meters_to_world_units(7.0, context.map_manager)
        anchor = self._hero_ranged_highground_anchor(context) or self._structure_lob_anchor(context.entity, target_entity, context.data.get('own_base'), preferred_distance)
        speed = self._meters_to_world_units(1.9, context.map_manager)
        target = self.entity_to_target(target_entity, context.entity)
        if self._distance_to_point(context.entity, anchor) > self._meters_to_world_units(0.8, context.map_manager):
            return self._set_decision(context, summary, target=target, target_point=anchor, speed=speed, preferred_route={'target': anchor}, turret_state='aiming', structure_lob_target_type=structure_lob_target_type, disengage_deployment=disengage_deployment)
        context.data['decision'] = {
            'summary': summary,
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': anchor,
            'movement_target': anchor,
            'velocity': self.maintain_distance(context.entity, target, preferred_distance, speed * 0.45, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': None,
            'structure_lob_target_type': structure_lob_target_type,
            'disengage_deployment': bool(disengage_deployment),
        }
        return SUCCESS

    def _action_push_outpost(self, context):
        target_entity = context.data.get('enemy_outpost')
        if target_entity is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        summary = '推进敌方前哨站，压缩防守纵深'
        return self._safe_pressure_decision(context, self.entity_to_target(target_entity, context.entity), summary, speed, preferred_distance_m=2.8)

    def _action_push_base(self, context):
        target_entity = context.data.get('enemy_base')
        if target_entity is None:
            return FAILURE
        speed = self._meters_to_world_units(2.0, context.map_manager)
        summary = '转入基地推进阶段，集中火力终结比赛'
        return self._safe_pressure_decision(context, self.entity_to_target(target_entity, context.entity), summary, speed, preferred_distance_m=3.5)

    def _action_patrol_key_facilities(self, context):
        patrol_points = self.get_patrol_points(context.entity, context.map_manager)
        patrol_target = self.next_patrol_point(context.entity, patrol_points)
        speed = self._meters_to_world_units(1.4, context.map_manager)
        return self._set_decision(context, '沿关键设施轮巡，保持阵型与视野', target=context.data.get('target'), target_point=patrol_target, speed=speed, turret_state='aiming' if context.data.get('target') else 'searching', angular_velocity=12.0)

    def _priority_target_threat_score(self, source_entity, target_entity):
        return self._targeting_runtime.priority_target_threat_score(source_entity, target_entity)

    def _target_assessment(self, entity, other, distance, rules_engine):
        return self._targeting_runtime.target_assessment(entity, other, distance, rules_engine)

    def _priority_target_score(self, entity, other, priority_map, rules_engine=None, max_distance=None):
        return self._targeting_runtime.priority_target_score(entity, other, priority_map, rules_engine=rules_engine, max_distance=max_distance)

    def _select_priority_target_entity(self, entity, enemies, strategy, rules_engine=None, max_distance=None):
        return self._targeting_runtime.select_priority_target_entity(entity, enemies, strategy, rules_engine=rules_engine, max_distance=max_distance)

    def select_priority_target(self, entity, enemies, strategy, rules_engine=None, max_distance=None):
        return self._targeting_runtime.select_priority_target(entity, enemies, strategy, rules_engine=rules_engine, max_distance=max_distance)

    def entity_to_target(self, target_entity, source_entity):
        distance = self._distance(source_entity, target_entity)
        return {
            'id': target_entity.id,
            'type': target_entity.type,
            'x': target_entity.position['x'],
            'y': target_entity.position['y'],
            'distance': distance,
            'hp': target_entity.health,
            'max_hp': target_entity.max_health,
        }

    def _find_entity(self, entities, team, entity_type):
        for entity in entities:
            if entity.team == team and entity.type == entity_type:
                return entity
        return None

    def _distance(self, source, target):
        return math.hypot(target.position['x'] - source.position['x'], target.position['y'] - source.position['y'])

    def _distance_to_point(self, entity, point):
        return math.hypot(point[0] - entity.position['x'], point[1] - entity.position['y'])

    def _distance_to_segment(self, point, segment_start, segment_end):
        start_x = float(segment_start[0])
        start_y = float(segment_start[1])
        end_x = float(segment_end[0])
        end_y = float(segment_end[1])
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        if abs(delta_x) <= 1e-6 and abs(delta_y) <= 1e-6:
            return math.hypot(float(point[0]) - start_x, float(point[1]) - start_y)
        projection = ((float(point[0]) - start_x) * delta_x + (float(point[1]) - start_y) * delta_y) / max(delta_x * delta_x + delta_y * delta_y, 1e-6)
        projection = max(0.0, min(1.0, projection))
        closest_x = start_x + delta_x * projection
        closest_y = start_y + delta_y * projection
        return math.hypot(float(point[0]) - closest_x, float(point[1]) - closest_y)

    def _path_deviation_distance(self, entity, path, start_index=1):
        if not path:
            return float('inf')
        probe = (float(entity.position['x']), float(entity.position['y']))
        begin = max(0, int(start_index) - 1)
        end = max(begin + 1, len(path))
        best_distance = math.hypot(probe[0] - float(path[begin][0]), probe[1] - float(path[begin][1]))
        for index in range(begin, end - 1):
            candidate = self._distance_to_segment(probe, path[index], path[index + 1])
            if candidate < best_distance:
                best_distance = candidate
        return best_distance

    def get_team_anchor(self, team, anchor_type, map_manager, entity=None):
        if map_manager is None:
            return None
        facility = self._find_team_facility(map_manager, team, anchor_type)
        if facility is None:
            return None
        return self._facility_anchor_point(facility, map_manager, entity=entity)

    def get_energy_anchor(self, team, map_manager):
        if map_manager is None:
            return None
        facilities = map_manager.get_facility_regions('energy_mechanism')
        if facilities:
            return self._energy_activation_anchor(team, facilities[0], map_manager)
        return self.get_map_center(map_manager)

    def get_mining_anchor(self, entity, map_manager):
        return self._nearest_region_center(entity, map_manager, ['mining_area'])

    def get_exchange_anchor(self, entity, map_manager):
        if map_manager is None:
            return None
        # 优先返回己方兑矿区，再退化到中立兑矿区，避免跑去敌方或无队伍标记的兑矿点。
        best_ally = None
        best_neutral = None
        best_ally_dist = None
        best_neutral_dist = None
        for facility in map_manager.get_facility_regions('mineral_exchange'):
            team = facility.get('team')
            center = self.facility_center(facility)
            distance = self._distance_to_point(entity, center)
            if team == entity.team:
                if best_ally is None or best_ally_dist is None or distance < best_ally_dist:
                    best_ally = center
                    best_ally_dist = distance
            elif team in {None, 'neutral'}:
                if best_neutral is None or best_neutral_dist is None or distance < best_neutral_dist:
                    best_neutral = center
                    best_neutral_dist = distance
        return best_ally or best_neutral

    def get_map_center(self, map_manager):
        width = getattr(map_manager, 'map_width', None) or self.config.get('map', {}).get('width', 1576)
        height = getattr(map_manager, 'map_height', None) or self.config.get('map', {}).get('height', 873)
        return int(width / 2), int(height / 2)

    def get_patrol_points(self, entity, map_manager):
        if map_manager is None:
            return []
        team = entity.team
        enemy_team = 'blue' if team == 'red' else 'red'
        role_key = self._role_key(entity)
        if role_key in {'hero', 'infantry', 'sentry'}:
            points = []
            for target_team, facility_type in ((enemy_team, 'outpost'), (team, 'fort'), (enemy_team, 'fort'), (enemy_team, 'base')):
                facility = self._find_team_facility(map_manager, target_team, facility_type)
                if facility is not None:
                    points.append(self._facility_anchor_point(facility, map_manager, entity=entity))
            central_highland = self._nearest_region_center(entity, map_manager, ['buff_central_highland'])
            if central_highland is not None:
                points.insert(1, central_highland)
            return points
        points = []
        mining_anchor = self.get_mining_anchor(entity, map_manager)
        exchange_anchor = self.get_exchange_anchor(entity, map_manager)
        supply_anchor = self.get_team_anchor(team, 'supply', map_manager, entity=entity)
        base_anchor = self.get_team_anchor(team, 'base', map_manager, entity=entity)
        for anchor in (mining_anchor, exchange_anchor, supply_anchor, base_anchor):
            if anchor is not None:
                points.append(anchor)
        return points

    def choose_retreat_anchor(self, entity, map_manager, prefer_supply=False):
        if map_manager is None:
            return entity.position['x'], entity.position['y']
        facility_order = ['supply', 'fort', 'outpost', 'base'] if prefer_supply else ['fort', 'outpost', 'base', 'supply']
        for facility_type in facility_order:
            anchor = self.get_team_anchor(entity.team, facility_type, map_manager, entity=entity)
            if anchor is not None:
                return anchor
        return entity.position['x'], entity.position['y']

    def choose_guard_anchor(self, entity, target, map_manager):
        if map_manager is None:
            return entity.position['x'], entity.position['y']
        candidates = []
        for facility_type, weight in [('fort', 1.5), ('outpost', 1.25), ('supply', 0.9), ('base', 0.8)]:
            anchor = self.get_team_anchor(entity.team, facility_type, map_manager, entity=entity)
            if anchor is None:
                continue
            target_distance = math.hypot(target['x'] - anchor[0], target['y'] - anchor[1]) if target is not None else 0.0
            entity_distance = math.hypot(entity.position['x'] - anchor[0], entity.position['y'] - anchor[1])
            score = weight * 1000.0 - target_distance * 0.75 - entity_distance * 0.20
            candidates.append((score, anchor))
        if not candidates:
            return entity.position['x'], entity.position['y']
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def choose_transit_anchor(self, entity, destination, map_manager, rules_engine=None):
        if map_manager is None or destination is None:
            return None
        candidate_types = ['fly_slope', 'undulating_road', 'first_step', 'second_step']
        best = None
        best_score = None
        for facility_type in candidate_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {entity.team, 'neutral'}:
                    continue
                if not self._terrain_access_allowed(entity, facility, rules_engine):
                    continue
                center = self.facility_center(facility)
                to_facility = self._distance_to_point(entity, center)
                to_goal = math.hypot(destination[0] - center[0], destination[1] - center[1])
                score = to_facility * 0.65 + to_goal * 0.35
                if best_score is None or score < best_score:
                    best_score = score
                    best = center
        if best is None:
            return None
        direct = self._distance_to_point(entity, destination)
        via = self._distance_to_point(entity, best) + math.hypot(destination[0] - best[0], destination[1] - best[1])
        return best if via <= direct * 1.15 else None

    def _best_terrain_traversal_plan(self, context, required_type=None):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        entity = context.entity
        if float(getattr(entity, 'terrain_buff_timer', 0.0)) > 0.25:
            return None
        target = context.data.get('target')
        target_point = (target['x'], target['y']) if target is not None else context.data.get('energy_anchor') or context.data.get('map_center') or self.get_map_center(map_manager)
        candidates = []
        for facility_type in ('fly_slope', 'first_step', 'second_step'):
            if required_type is not None and facility_type != required_type:
                continue
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {entity.team, 'neutral'}:
                    continue
                if not self._terrain_access_allowed(entity, facility, context.rules_engine):
                    continue
                center = self.facility_center(facility)
                resolved = self._resolve_navigation_target(center, map_manager, entity=entity)
                if resolved is None:
                    continue
                distance_to_entity = self._distance_to_point(entity, resolved)
                distance_to_target = math.hypot(float(target_point[0]) - float(resolved[0]), float(target_point[1]) - float(resolved[1]))
                terrain_bias = {'first_step': -52.0, 'second_step': -40.0, 'fly_slope': -16.0}[facility_type]
                role_bias = 0.0
                role_key = context.data.get('role_key')
                if role_key == 'sentry':
                    if facility_type == 'fly_slope':
                        if context.data.get('enemy_hero') is not None and float(context.data.get('health_ratio', 1.0)) >= 0.60:
                            role_bias -= 10.0
                        else:
                            role_bias += 16.0
                    elif facility_type == 'first_step':
                        role_bias -= 8.0
                if role_key == 'infantry' and facility_type in {'first_step', 'second_step'}:
                    role_bias -= 12.0
                if role_key == 'engineer' and facility_type == 'fly_slope':
                    role_bias += 24.0
                role_bias += self._engineer_second_step_yield_penalty(context, facility_type, facility, resolved)
                score = distance_to_entity * 0.58 + distance_to_target * 0.42 + terrain_bias + role_bias
                candidates.append((score, facility_type, facility, resolved))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        _, facility_type, facility, resolved = candidates[0]
        return {
            'type': facility_type,
            'facility': facility,
            'target': (float(resolved[0]), float(resolved[1])),
        }

    def _action_terrain_traversal(self, context, facility_type):
        plan = self._best_terrain_traversal_plan(context, required_type=facility_type)
        if plan is None:
            return FAILURE
        summary_map = {
            'fly_slope': '主动利用飞坡快速换侧并建立侧翼路线',
            'first_step': '主动翻越一级台阶切入有利地形',
            'second_step': '主动翻越二级台阶抢占高差路线',
        }
        target_point = plan.get('target')
        if target_point is not None and context.map_manager is not None:
            traversal = context.map_manager.describe_segment_traversal(
                float(context.entity.position['x']),
                float(context.entity.position['y']),
                float(target_point[0]),
                float(target_point[1]),
                max_height_delta_m=float(getattr(context.entity, 'max_terrain_step_height_m', 0.35)),
            )
            if isinstance(traversal, dict) and str(traversal.get('facility_type', '')) == facility_type:
                policy_points = self._terrain_policy_path_points(context.entity, traversal, context.map_manager)
                if policy_points:
                    target_point = policy_points[0]
        speed = self._meters_to_world_units(1.8, context.map_manager)
        target = context.data.get('target')
        return self._set_decision(
            context,
            summary_map.get(facility_type, '主动翻越地形建立侧翼路线'),
            target=target,
            target_point=target_point,
            speed=speed,
            preferred_route={'target': target_point},
            turret_state='aiming' if target is not None else 'searching',
        )

    def _find_best_buff_anchor(self, context, terrain_only=False):
        if context.map_manager is None:
            return None
        entity = context.entity
        target = context.data.get('target')
        target_point = (target['x'], target['y']) if target is not None else context.data.get('energy_anchor') or context.data.get('map_center')
        buff_rules_map = context.rules_engine.rules.get('buff_zones', {}) if context.rules_engine is not None else {}
        candidates = []
        for facility in context.map_manager.get_facility_regions():
            facility_type = facility.get('type', '')
            if not facility_type.startswith('buff_'):
                continue
            if terrain_only and not facility_type.startswith('buff_terrain_'):
                continue
            if facility.get('team') not in {entity.team, 'neutral'}:
                continue

            buff_rules = buff_rules_map.get(facility_type, {})
            if not buff_rules:
                continue
            if hasattr(context.rules_engine, '_buff_access_allowed') and not context.rules_engine._buff_access_allowed(entity, facility, buff_rules):
                continue
            if buff_rules.get('engineer_only') and getattr(entity, 'robot_type', '') != '工程':
                continue

            center = self.facility_center(facility)
            distance_to_entity = self._distance_to_point(entity, center)
            distance_to_target = math.hypot(target_point[0] - center[0], target_point[1] - center[1])
            bonus = 0.0
            if facility_type.startswith('buff_terrain_'):
                bonus += 140.0
            elif facility_type in {'buff_central_highland', 'buff_trapezoid_highland', 'buff_fort'}:
                bonus += 90.0
            elif facility_type in {'buff_supply', 'buff_base', 'buff_outpost'}:
                bonus += 60.0
            score = distance_to_target * 0.75 + distance_to_entity * 0.35 - bonus
            candidates.append((score, facility))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _find_nearest_facility_center(self, map_manager, entity, facility_types):
        if map_manager is None:
            return None
        best = None
        best_score = None
        for facility_type in facility_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {entity.team, 'neutral'}:
                    continue
                center = self.facility_center(facility)
                score = self._distance_to_point(entity, center)
                if best_score is None or score < best_score:
                    best_score = score
                    best = center
        return best

    def _nearest_region_center(self, entity, map_manager, facility_types):
        if map_manager is None:
            return None
        best_center = None
        best_distance = None
        for facility_type in facility_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {'neutral', entity.team}:
                    continue
                center = self.facility_center(facility)
                distance = self._distance_to_point(entity, center)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_center = center
        return best_center

    def _enemy_highground_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        enemy_team = 'blue' if context.entity.team == 'red' else 'red'
        target_entity = context.data.get('enemy_outpost') or context.data.get('enemy_base')
        target_point = (target_entity.position['x'], target_entity.position['y']) if target_entity is not None else self.get_map_center(map_manager)
        candidates = []
        for facility_type in ('buff_trapezoid_highland', 'second_step', 'fly_slope', 'buff_central_highland'):
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {enemy_team, 'neutral'}:
                    continue
                center = self.facility_center(facility)
                distance_target = math.hypot(center[0] - target_point[0], center[1] - target_point[1])
                distance_entity = self._distance_to_point(context.entity, center)
                score = distance_target * 0.75 + distance_entity * 0.25
                candidates.append((score, center))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return self._resolve_navigation_target(candidates[0][1], map_manager, entity=context.entity)

    def _sentry_opening_step_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        return self._find_nearest_facility_center(map_manager, context.entity, ['first_step', 'fly_slope'])

    def _infantry_opening_highground_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        return self._find_nearest_facility_center(
            map_manager,
            context.entity,
            ['buff_central_highland', 'second_step', 'first_step', 'fly_slope'],
        )

    def _fallback_highground_anchor(self, context):
        role_key = context.data.get('role_key')
        if role_key == 'infantry':
            return self._infantry_opening_highground_anchor(context)
        if role_key == 'hero':
            if self._hero_prefers_ranged(context.entity):
                return self._hero_ranged_highground_anchor(context)
            return self._outpost_pressure_highground_anchor(context)
        return self._find_nearest_facility_center(
            context.map_manager,
            context.entity,
            ['buff_central_highland', 'buff_trapezoid_highland', 'second_step', 'first_step', 'fly_slope'],
        )

    def _outpost_pressure_highground_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        target_entity = context.data.get('enemy_outpost') or context.data.get('enemy_base')
        target_point = (target_entity.position['x'], target_entity.position['y']) if target_entity is not None else self.get_map_center(map_manager)
        candidates = []
        role_key = context.data.get('role_key')
        if role_key == 'infantry':
            facility_types = ('buff_central_highland',)
        else:
            facility_types = ('buff_trapezoid_highland', 'buff_central_highland')
        for facility_type in facility_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {'neutral', context.entity.team}:
                    continue
                center = self.facility_center(facility)
                distance_target = math.hypot(center[0] - target_point[0], center[1] - target_point[1])
                distance_entity = self._distance_to_point(context.entity, center)
                score = distance_target * 0.75 + distance_entity * 0.25
                candidates.append((score, center))
        if not candidates:
            fallback_types = ['buff_central_highland', 'second_step', 'first_step', 'fly_slope'] if role_key == 'infantry' else ['buff_trapezoid_highland', 'buff_central_highland', 'second_step', 'first_step', 'fly_slope']
            return self._find_nearest_facility_center(map_manager, context.entity, fallback_types)
        candidates.sort(key=lambda item: item[0])
        return self._resolve_navigation_target(candidates[0][1], map_manager, entity=context.entity)

    def _hero_ranged_highground_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        trapezoid_anchor = self._find_nearest_facility_center(map_manager, context.entity, ['buff_trapezoid_highland'])
        if trapezoid_anchor is not None:
            return trapezoid_anchor
        return self._hero_deployment_anchor(context)

    def _base_side_patrol_anchor(self, entity, map_manager, origin_anchor, enemy_base):
        if origin_anchor is None or enemy_base is None:
            return origin_anchor
        direction_x = float(enemy_base.position['x']) - float(origin_anchor[0])
        direction_y = float(enemy_base.position['y']) - float(origin_anchor[1])
        length = math.hypot(direction_x, direction_y)
        if length <= 1e-6:
            return origin_anchor
        offset = self._meters_to_world_units(1.4, map_manager)
        anchor = (
            float(origin_anchor[0]) + direction_x / length * offset,
            float(origin_anchor[1]) + direction_y / length * offset,
        )
        return self._resolve_navigation_target(anchor, map_manager, entity=entity)

    def _team_fly_slope_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        for facility in map_manager.get_facility_regions('fly_slope'):
            if facility.get('team') == context.entity.team:
                return self._resolve_navigation_target(self.facility_center(facility), map_manager, entity=context.entity)
        return None

    def _team_fly_slope_start_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        facility_type = 'buff_terrain_fly_slope_red_start' if context.entity.team == 'red' else 'buff_terrain_fly_slope_blue_start'
        for facility in map_manager.get_facility_regions(facility_type):
            if facility.get('team') in {'neutral', context.entity.team}:
                return self._resolve_navigation_target(self.facility_center(facility), map_manager, entity=context.entity)
        return None

    def _hero_deployment_anchor(self, context):
        map_manager = context.map_manager
        if map_manager is None:
            return None
        for facility in map_manager.get_facility_regions('buff_hero_deployment'):
            if facility.get('team') == context.entity.team:
                return self._resolve_navigation_target(self.facility_center(facility), map_manager, entity=context.entity)
        return None

    def _fly_slope_landing_point(self, context, slope_anchor):
        map_manager = context.map_manager
        if map_manager is None or slope_anchor is None:
            return slope_anchor
        direction = 1.0 if context.entity.team == 'red' else -1.0
        landing = None
        for facility in map_manager.get_facility_regions('fly_slope'):
            if facility.get('team') != context.entity.team:
                continue
            peak_x = float(facility.get('x2', 0.0)) if direction > 0 else float(facility.get('x1', 0.0))
            center_y = float((facility.get('y1', 0.0) + facility.get('y2', 0.0)) * 0.5)
            landing = (
                peak_x + direction * self._meters_to_world_units(0.85, map_manager),
                center_y,
            )
            break
        if landing is None:
            landing = (
                float(slope_anchor[0]) + direction * self._meters_to_world_units(0.85, map_manager),
                float(slope_anchor[1]),
            )
        return self._resolve_navigation_target(landing, map_manager, entity=context.entity)

    def _screen_offset(self, team):
        return (48, 42) if team == 'red' else (-48, -42)

    def _find_entity_by_role(self, entities, team, role_key, exclude_id=None):
        for entity in entities:
            if entity.id == exclude_id or entity.team != team or not entity.is_alive():
                continue
            if self._role_key(entity) == role_key:
                return entity
        return None

    def _nearest_enemy_by_roles(self, entities, team, point, role_keys):
        best = None
        best_distance = None
        for entity in entities:
            if entity.team == team or not entity.is_alive():
                continue
            if self._role_key(entity) not in role_keys:
                continue
            distance = math.hypot(entity.position['x'] - point[0], entity.position['y'] - point[1])
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = entity
        if best is None:
            return None
        return {'entity': best, 'distance': best_distance}

    def _escort_anchor(self, ally, threat, map_manager):
        if ally is None:
            return None
        offset_distance = self._meters_to_world_units(1.8, map_manager)
        if threat is None:
            return ally.position['x'], ally.position['y']
        dx = ally.position['x'] - threat.position['x']
        dy = ally.position['y'] - threat.position['y']
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return ally.position['x'], ally.position['y']
        return (
            ally.position['x'] + dx / length * offset_distance,
            ally.position['y'] + dy / length * offset_distance,
        )

    def _structure_lob_anchor(self, entity, structure, fallback_anchor, preferred_distance):
        if fallback_anchor is not None:
            reference_x = fallback_anchor.position['x']
            reference_y = fallback_anchor.position['y']
        else:
            reference_x = entity.position['x']
            reference_y = entity.position['y']
        dx = reference_x - structure.position['x']
        dy = reference_y - structure.position['y']
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx, dy, length = 0.0, -1.0, 1.0
        return (
            structure.position['x'] + dx / length * preferred_distance,
            structure.position['y'] + dy / length * preferred_distance,
        )

    def _energy_activation_anchor(self, team, facility, map_manager):
        if facility.get('type') == 'energy_mechanism' and facility.get('shape', 'rect') == 'rect':
            if team == 'blue':
                return 970.0, 770.0
            return 579.0, 204.0
        center_x, center_y = self.facility_center(facility)
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
        anchor_distance = self._meters_to_world_units(5.5, map_manager)
        return center_x + normal_x * anchor_distance, center_y + normal_y * anchor_distance

    def _terrain_access_allowed(self, entity, facility, rules_engine=None):
        if rules_engine is not None and hasattr(rules_engine, '_terrain_access_allowed'):
            return rules_engine._terrain_access_allowed(entity, facility)
        if facility.get('type') == 'undulating_road':
            return False
        return True

    def _blend_velocity(self, velocity_a, velocity_b, ratio_a=0.6, ratio_b=0.4):
        return (
            velocity_a[0] * ratio_a + velocity_b[0] * ratio_b,
            velocity_a[1] * ratio_a + velocity_b[1] * ratio_b,
        )

    def engage_from_anchor(self, entity, target, anchor_point, desired_distance, speed=2.8, map_manager=None):
        target_velocity = self.maintain_distance(entity, target, desired_distance, speed, map_manager=map_manager)
        if anchor_point is None:
            return target_velocity
        anchor_velocity = self.navigate_towards(entity, anchor_point, speed * 0.7, map_manager)
        anchor_distance = math.hypot(anchor_point[0] - entity.position['x'], anchor_point[1] - entity.position['y'])
        if anchor_distance <= 90:
            return target_velocity
        if target['distance'] > desired_distance + 140:
            return self._blend_velocity(target_velocity, anchor_velocity, 0.72, 0.28)
        if target['distance'] < desired_distance - 120:
            return self._blend_velocity(target_velocity, anchor_velocity, 0.82, 0.18)
        return self._blend_velocity(target_velocity, anchor_velocity, 0.58, 0.42)

    def next_patrol_point(self, entity, patrol_points):
        if not patrol_points:
            return entity.position['x'], entity.position['y']
        patrol_index = self._patrol_index.get(entity.id, 0)
        target = patrol_points[patrol_index % len(patrol_points)]
        distance = math.hypot(target[0] - entity.position['x'], target[1] - entity.position['y'])
        if distance < 60:
            patrol_index = (patrol_index + 1) % len(patrol_points)
            self._patrol_index[entity.id] = patrol_index
            target = patrol_points[patrol_index]
        else:
            self._patrol_index[entity.id] = patrol_index
        return target

    def move_towards(self, entity, target_point, speed=2.0):
        if not self.enable_entity_movement or target_point is None:
            return 0.0, 0.0
        dx = target_point[0] - entity.position['x']
        dy = target_point[1] - entity.position['y']
        distance = math.hypot(dx, dy)
        if distance < 5:
            return 0.0, 0.0
        return (dx / distance) * speed, (dy / distance) * speed

    def _max_speed_world_units(self):
        physics = self.config.get('physics', {})
        map_config = self.config.get('map', {})
        field_length_m = float(map_config.get('field_length_m', 28.0))
        field_width_m = float(map_config.get('field_width_m', 15.0))
        map_width = float(map_config.get('width', 1576.0))
        map_height = float(map_config.get('height', 873.0))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return float(physics.get('max_speed', 3.5)) * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)

    def _resolved_navigation_speed(self, entity, requested_speed, target_point, map_manager):
        if target_point is None:
            return requested_speed
        max_speed = self._max_speed_world_units() * 0.96
        friction = float(self.config.get('physics', {}).get('friction', 0.1))
        corrected_speed = requested_speed / max(0.45, 1.0 - friction)
        distance = math.hypot(float(target_point[0]) - float(entity.position['x']), float(target_point[1]) - float(entity.position['y']))
        if map_manager is not None and distance >= max(80.0, map_manager.terrain_grid_cell_size * 4.0):
            start_height = float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))
            end_height = float(map_manager.get_terrain_height_m(target_point[0], target_point[1]))
            if abs(end_height - start_height) <= 0.03:
                corrected_speed = max(corrected_speed, max_speed * 0.82)
        effective_capacity = max(1e-6, float(getattr(entity, 'max_power', 0.0)) * float(getattr(entity, 'dynamic_power_capacity_mult', 1.0)))
        power_ratio = float(getattr(entity, 'power', 0.0)) / effective_capacity
        if power_ratio < 0.2:
            corrected_speed *= 0.72
        elif power_ratio < 0.4:
            corrected_speed *= 0.86
        return min(max_speed, corrected_speed)

    def _build_escape_waypoint(self, entity, preferred_point, map_manager):
        if map_manager is None:
            return None
        base_dx = float(preferred_point[0]) - float(entity.position['x']) if preferred_point is not None else 0.0
        base_dy = float(preferred_point[1]) - float(entity.position['y']) if preferred_point is not None else 0.0
        if abs(base_dx) <= 1e-6 and abs(base_dy) <= 1e-6:
            heading = math.radians(float(getattr(entity, 'angle', 0.0)))
        else:
            heading = math.atan2(base_dy, base_dx)
        base_radius = max(map_manager.terrain_grid_cell_size * 2.0, float(getattr(entity, 'collision_radius', 16.0)) * 2.4, 36.0)
        for radius_mult in (1.0, 1.45, 1.9, 2.35):
            radius = base_radius * radius_mult
            for offset_deg in (90, -90, 60, -60, 135, -135, 180, 35, -35):
                candidate_heading = heading + math.radians(offset_deg)
                candidate = (
                    float(entity.position['x']) + math.cos(candidate_heading) * radius,
                    float(entity.position['y']) + math.sin(candidate_heading) * radius,
                )
                if not map_manager.is_position_valid_for_radius(candidate[0], candidate[1], collision_radius=float(getattr(entity, 'collision_radius', 0.0))):
                    continue
                if map_manager.is_segment_valid_for_radius(
                    entity.position['x'],
                    entity.position['y'],
                    candidate[0],
                    candidate[1],
                    collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
                ):
                    return candidate
        return None

    def _clear_forced_supply_escape(self, entity_id):
        self._forced_supply_escape_state.pop(entity_id, None)

    def _activate_infantry_supply_escape(self, entity, target_point, map_manager, current_time):
        if map_manager is None or getattr(entity, 'robot_type', '') != '步兵':
            return None
        if getattr(entity, 'ammo_type', 'none') == 'none' or int(getattr(entity, 'ammo', 0)) <= 0:
            return None
        in_supply_zone = self._is_inside_team_facility(entity, map_manager, 'supply')
        if not in_supply_zone:
            supply_anchor = self.get_team_anchor(entity.team, 'supply', map_manager, entity=entity)
            if supply_anchor is None or self._distance_to_point(entity, supply_anchor) > self._meters_to_world_units(1.8, map_manager):
                return None
        fort_anchor = self.get_team_anchor(entity.team, 'fort', map_manager, entity=entity) or self.get_team_anchor(entity.team, 'base', map_manager, entity=entity)
        if fort_anchor is None:
            return None
        resolved_anchor = self._resolve_navigation_target(fort_anchor, map_manager, entity=entity)
        if resolved_anchor is None:
            return None
        anchor = (float(resolved_anchor[0]), float(resolved_anchor[1]))
        self._forced_supply_escape_state[entity.id] = {
            'anchor': anchor,
            'resume_target': (float(target_point[0]), float(target_point[1])) if target_point is not None else None,
            'expires_at': float(current_time) + 8.0,
        }
        self._entity_path_state.pop(entity.id, None)
        self._stuck_state[entity.id] = {
            'best_distance': float('inf'),
            'last_progress_time': float(current_time),
            'last_check_time': float(current_time),
        }
        return anchor

    def _active_infantry_supply_escape_anchor(self, entity, map_manager, current_time):
        state = self._forced_supply_escape_state.get(entity.id)
        if not state:
            return None
        anchor = state.get('anchor')
        if anchor is None or map_manager is None or float(state.get('expires_at', 0.0)) <= float(current_time):
            self._clear_forced_supply_escape(entity.id)
            return None
        if self._distance_to_point(entity, anchor) <= self._meters_to_world_units(0.9, map_manager):
            self._clear_forced_supply_escape(entity.id)
            return None
        return (float(anchor[0]), float(anchor[1]))

    def navigate_towards(self, entity, target_point, speed, map_manager):
        if not self.enable_entity_movement or target_point is None:
            self._clear_navigation_overlay_state(entity)
            return 0.0, 0.0
        target_point = self._resolve_navigation_target(target_point, map_manager, entity=entity)
        planning_enabled = self._role_controller_feature_enabled(entity, 'path_planning')
        avoidance_enabled = self._role_controller_feature_enabled(entity, 'avoidance')
        current_time = float(self._last_ai_update_time.get(entity.id, 0.0))
        forced_escape_anchor = self._active_infantry_supply_escape_anchor(entity, map_manager, current_time)
        if forced_escape_anchor is not None:
            preview = (
                (float(entity.position['x']), float(entity.position['y'])),
                forced_escape_anchor,
                (float(target_point[0]), float(target_point[1])),
            )
            self._set_navigation_overlay_state(entity, waypoint=forced_escape_anchor, preview=preview, path_valid=False, region_radius=0.0, traversal_state='passable')
            desired_velocity = self.move_towards(entity, forced_escape_anchor, self._resolved_navigation_speed(entity, speed, forced_escape_anchor, map_manager))
            return self._avoid_static_obstacles(entity, desired_velocity, map_manager) if avoidance_enabled else desired_velocity
        region_radius = self._target_region_radius(entity, target_point, map_manager)
        if self._is_target_reached(entity, target_point, map_manager):
            self._clear_navigation_overlay_state(entity)
            self._clear_forced_supply_escape(entity.id)
            entity.ai_navigation_target = target_point
            state = self._entity_path_state.get(entity.id)
            if state is not None:
                state['path'] = self.EMPTY_PATH_PREVIEW
            return 0.0, 0.0
        if map_manager is None:
            self._set_navigation_overlay_state(entity, waypoint=target_point, preview=(target_point,), path_valid=True, region_radius=region_radius, traversal_state='passable')
            return self.move_towards(entity, target_point, self._resolved_navigation_speed(entity, speed, target_point, map_manager))
        if not planning_enabled:
            preview = (
                (float(entity.position['x']), float(entity.position['y'])),
                (float(target_point[0]), float(target_point[1])),
            )
            self._set_navigation_overlay_state(entity, waypoint=target_point, preview=preview, path_valid=False, region_radius=region_radius, traversal_state='direct')
            desired_velocity = self.move_towards(entity, target_point, self._resolved_navigation_speed(entity, speed, target_point, map_manager))
            return self._avoid_static_obstacles(entity, desired_velocity, map_manager) if avoidance_enabled else desired_velocity
        next_point = self._next_path_waypoint(entity, target_point, map_manager)
        desired_velocity = self.move_towards(entity, next_point, self._resolved_navigation_speed(entity, speed, next_point, map_manager))
        return self._avoid_static_obstacles(entity, desired_velocity, map_manager) if avoidance_enabled else desired_velocity

    def _avoid_static_obstacles(self, entity, desired_velocity, map_manager):
        vx, vy = desired_velocity
        speed = math.hypot(vx, vy)
        if speed <= 1e-6 or map_manager is None:
            return desired_velocity
        collision_radius = float(getattr(entity, 'collision_radius', 0.0))
        lookahead = max(map_manager.terrain_grid_cell_size * 2.0, speed * 0.25, 16.0)
        nx, ny = vx / speed, vy / speed
        probe_x = entity.position['x'] + nx * lookahead
        probe_y = entity.position['y'] + ny * lookahead
        if map_manager.is_segment_valid_for_radius(
            entity.position['x'],
            entity.position['y'],
            probe_x,
            probe_y,
            collision_radius=collision_radius,
        ):
            return desired_velocity
        best_velocity = (0.0, 0.0)
        best_score = float('-inf')
        angles = (20, -20, 35, -35, 55, -55, 80, -80, 110, -110, 145, -145)
        heading = math.atan2(vy, vx)
        for offset in angles:
            candidate_heading = heading + math.radians(offset)
            cand_vx = math.cos(candidate_heading) * speed
            cand_vy = math.sin(candidate_heading) * speed
            cand_probe_x = entity.position['x'] + math.cos(candidate_heading) * lookahead
            cand_probe_y = entity.position['y'] + math.sin(candidate_heading) * lookahead
            if not map_manager.is_segment_valid_for_radius(
                entity.position['x'],
                entity.position['y'],
                cand_probe_x,
                cand_probe_y,
                collision_radius=collision_radius,
            ):
                continue
            direction_score = (cand_vx * vx + cand_vy * vy) / max(speed * speed, 1e-6)
            turn_penalty = abs(offset) / 180.0
            score = direction_score - turn_penalty * 0.35
            if score > best_score:
                best_score = score
                best_velocity = (cand_vx, cand_vy)
        return best_velocity

    def _next_path_waypoint(self, entity, target_point, map_manager):
        if self._is_target_reached(entity, target_point, map_manager):
            self._clear_navigation_overlay_state(entity)
            self._entity_path_state[entity.id] = {
                'path': self.EMPTY_PATH_PREVIEW,
                'index': 0,
                'last_waypoint': None,
            }
            return float(entity.position['x']), float(entity.position['y'])

        step_climb_state = getattr(entity, 'step_climb_state', None)
        if step_climb_state:
            forced = step_climb_state.get('top_point') or step_climb_state.get('end_point')
            if forced is not None:
                remaining_points = []
                segment_points = tuple(step_climb_state.get('segment_points', ()))
                segment_index = max(0, int(step_climb_state.get('segment_index', 0)))
                for point in segment_points[segment_index:]:
                    normalized = (float(point[0]), float(point[1]))
                    if not remaining_points or remaining_points[-1] != normalized:
                        remaining_points.append(normalized)
                forced_point = (float(forced[0]), float(forced[1]))
                if not remaining_points or remaining_points[-1] != forced_point:
                    remaining_points.append(forced_point)
                preview = [(float(entity.position['x']), float(entity.position['y']))]
                preview.extend(remaining_points)
                final_target = (float(target_point[0]), float(target_point[1]))
                if preview[-1] != final_target:
                    preview.append(final_target)
                point = (float(forced[0]), float(forced[1]))
                self._set_navigation_overlay_state(entity, waypoint=point, preview=tuple(preview), path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='step-passable')
                return point

        direct_traverse_distance = self._distance_to_point(entity, target_point)
        direct_traverse_limit = math.hypot(float(map_manager.map_width), float(map_manager.map_height))
        current_time = self._last_ai_update_time.get(entity.id, 0.0)
        pathfinding_enabled = self._role_controller_feature_enabled(entity, 'pathfinding')
        state = self._entity_path_state.get(entity.id)
        direct_target_signature = (round(float(target_point[0]), 1), round(float(target_point[1]), 1))
        direct_status = None
        if state is not None and state.get('direct_target') == direct_target_signature and current_time < float(state.get('direct_status_until', 0.0)):
            direct_status = state.get('direct_status')
        if direct_status is None:
            direct_status = self._movement_segment_status(entity, (entity.position['x'], entity.position['y']), target_point, map_manager)
            if state is None:
                state = {}
                self._entity_path_state[entity.id] = state
            direct_interval = self._direct_segment_check_interval
            state['direct_target'] = direct_target_signature
            state['direct_status'] = direct_status
            state['direct_status_until'] = current_time + direct_interval
        if direct_traverse_distance <= direct_traverse_limit and direct_status['passable']:
            raw_path = [(float(entity.position['x']), float(entity.position['y']))]
            for detour_point in tuple(direct_status.get('detour_points', ())) or self.EMPTY_PATH_PREVIEW:
                normalized = (float(detour_point[0]), float(detour_point[1]))
                if raw_path[-1] != normalized:
                    raw_path.append(normalized)
            final_target = (float(target_point[0]), float(target_point[1]))
            if raw_path[-1] != final_target:
                raw_path.append(final_target)
            expanded_path = self._expand_path_with_step_transitions(entity, raw_path, map_manager)
            segmented_path = tuple(self._segment_path_points(expanded_path, map_manager, entity=entity))
            traversal_state = 'step-passable' if any(self._movement_segment_status(entity, segmented_path[idx], segmented_path[idx + 1], map_manager)['requires_step'] for idx in range(len(segmented_path) - 1)) else 'passable'
            direct_index = 1 if len(segmented_path) > 1 else 0
            direct_waypoint = segmented_path[direct_index] if segmented_path else (float(target_point[0]), float(target_point[1]))
            self._entity_path_state[entity.id] = {
                'path': segmented_path,
                'index': direct_index,
                'last_waypoint': direct_waypoint,
                'planned_at': self._last_ai_update_time.get(entity.id, 0.0),
                'last_speed': math.hypot(float(getattr(entity, 'velocity', {}).get('vx', 0.0)), float(getattr(entity, 'velocity', {}).get('vy', 0.0))),
                'last_wp_distance': self._distance_to_point(entity, direct_waypoint),
                'direct_target': direct_target_signature,
                'direct_status': direct_status,
                'direct_status_until': current_time + self._direct_segment_check_interval,
            }
            preview = self._build_path_preview(entity, segmented_path, direct_index)
            self._set_navigation_overlay_state(entity, waypoint=direct_waypoint, preview=preview, path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state=traversal_state)
            return direct_waypoint

        if not pathfinding_enabled:
            midpoint = self._temporary_midpoint_waypoint(entity, target_point, map_manager)
            fallback_point = midpoint or (float(target_point[0]), float(target_point[1]))
            preview = (
                (float(entity.position['x']), float(entity.position['y'])),
                fallback_point,
                (float(target_point[0]), float(target_point[1])),
            )
            self._set_navigation_overlay_state(entity, waypoint=fallback_point, preview=preview, path_valid=False, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='blocked')
            return fallback_point

        raster_version = getattr(map_manager, 'raster_version', 0)
        step_limit = float(getattr(entity, 'max_terrain_step_height_m', 0.05))
        traversal_profile = self._traversal_profile(entity)
        start_cell = self._path_cell(entity.position, map_manager)
        goal_cell = self._path_cell({'x': target_point[0], 'y': target_point[1]}, map_manager)
        state = self._entity_path_state.get(entity.id)
        state_view = state or {}
        current_speed = math.hypot(float(getattr(entity, 'velocity', {}).get('vx', 0.0)), float(getattr(entity, 'velocity', {}).get('vy', 0.0)))
        force_fresh_replan = False
        path_signature_changed = False
        need_replan = state is None
        previous_goal_point = state_view.get('goal_point')
        target_shift_distance = None
        if previous_goal_point is not None:
            target_shift_distance = math.hypot(
                float(previous_goal_point[0]) - float(target_point[0]),
                float(previous_goal_point[1]) - float(target_point[1]),
            )
        goal_shift_threshold = max(
            self._path_goal_hysteresis_world,
            map_manager.terrain_grid_cell_size * 6.0,
            float(getattr(entity, 'collision_radius', 0.0)) * 2.5,
        )
        if not need_replan:
            goal_changed = state_view.get('goal_cell') != goal_cell
            if goal_changed and target_shift_distance is not None and target_shift_distance <= goal_shift_threshold:
                goal_changed = False
            path_signature_changed = (
                goal_changed
                or state_view.get('raster_version') != raster_version
                or state_view.get('step_limit') != round(step_limit, 3)
                or state_view.get('can_climb_steps') != bool(traversal_profile.get('can_climb_steps', False))
                or state_view.get('collision_radius') != round(float(traversal_profile.get('collision_radius', 0.0)), 2)
            )
            need_replan = path_signature_changed or not state_view.get('path')
        next_replan_at = float(state_view.get('next_replan_at', 0.0))
        failure_cooldown_active = (
            state is not None
            and not path_signature_changed
            and not state_view.get('path')
            and current_time < next_replan_at
        )
        if failure_cooldown_active:
            need_replan = False
        if not need_replan:
            active_path = state_view.get('path', ())
            active_index = self._path_waypoint_index(active_path, state_view.get('index', 1)) if active_path else 0
            deviation_limit = max(
                18.0,
                map_manager.terrain_grid_cell_size * 2.2,
                float(getattr(entity, 'collision_radius', 0.0)) * 1.3,
            )
            path_deviation = self._path_deviation_distance(entity, active_path, active_index)
            if path_deviation > deviation_limit:
                need_replan = True
                force_fresh_replan = True
        if not need_replan:
            planned_at = float(state_view.get('planned_at', current_time))
            if current_time - planned_at >= self._path_stale_recheck_interval:
                active_path = state_view.get('path', ())
                active_index = self._path_waypoint_index(active_path, state_view.get('index', 1)) if active_path else 0
                path_deviation = self._path_deviation_distance(entity, state_view.get('path', ()), active_index)
                if path_deviation > max(32.0, map_manager.terrain_grid_cell_size * 3.5):
                    need_replan = True
                    force_fresh_replan = True
        if not need_replan:
            last_speed = float(state_view.get('last_speed', current_speed))
            speed_delta = abs(current_speed - last_speed)
            if current_time - float(state_view.get('planned_at', current_time)) >= self._path_stale_recheck_interval and speed_delta >= max(48.0, map_manager.terrain_grid_cell_size * 4.0):
                need_replan = True
                force_fresh_replan = True
        if not need_replan:
            waypoint = state_view.get('last_waypoint')
            last_wp_distance = float(state_view.get('last_wp_distance', 0.0))
            if waypoint is not None:
                current_wp_distance = self._distance_to_point(entity, waypoint)
                # 距离上个路点明显变大时，说明局部动态/避障已改变，需要重新规划路径。
                if current_wp_distance > last_wp_distance + max(16.0, map_manager.terrain_grid_cell_size * 1.5):
                    need_replan = True
                    force_fresh_replan = True
                if state is not None:
                    state['last_wp_distance'] = current_wp_distance

        stuck = self._stuck_state.get(entity.id)
        if stuck is None:
            stuck = {
                'best_distance': float('inf'),
                'last_progress_time': current_time,
                'last_check_time': current_time,
            }
            self._stuck_state[entity.id] = stuck
        stall_timeout = 0.8 if getattr(entity, 'step_climb_state', None) or getattr(entity, 'ai_navigation_path_state', 'passable') == 'step-passable' else 1.15
        if not need_replan:
            active_path = state.get('path', []) if state else []
            active_index = self._path_waypoint_index(active_path, state.get('index', 1)) if active_path else 0
            if active_path:
                probe_distance = self._distance_to_point(entity, active_path[active_index])
                if probe_distance < float(stuck.get('best_distance', float('inf'))) - max(4.0, map_manager.terrain_grid_cell_size * 0.45):
                    stuck['best_distance'] = probe_distance
                    stuck['last_progress_time'] = current_time
                elif current_time - float(stuck.get('last_progress_time', current_time)) >= stall_timeout:
                    need_replan = True
                    force_fresh_replan = True
                    stuck['best_distance'] = probe_distance
                    stuck['last_progress_time'] = current_time
            stuck['last_check_time'] = current_time

        if need_replan:
            cache_key = (start_cell, goal_cell, raster_version, round(step_limit, 3), traversal_profile['step_climb_duration_sec'], round(traversal_profile.get('collision_radius', 0.0), 2))
            path = None
            path_pending = False
            fail_count = int(state_view.get('fail_count', 0))
            next_replan_at = float(state_view.get('next_replan_at', 0.0))
            pending_future = state_view.get('pending_path_future') if isinstance(state_view, dict) else None
            pending_signature = state_view.get('pending_request_signature') if isinstance(state_view, dict) else None
            pending_target_point = state_view.get('pending_target_point') if isinstance(state_view, dict) else None
            pending_path, path_pending = self._consume_pending_navigation_search(entity, target_point, map_manager, state_view, cache_key)
            if pending_path:
                path = tuple(pending_path)
                fail_count = 0
                next_replan_at = 0.0
            if not force_fresh_replan:
                if path is None:
                    cache_entry = self._path_cache.get(cache_key)
                    if isinstance(cache_entry, dict):
                        cached_path = tuple(cache_entry.get('path', self.EMPTY_PATH_PREVIEW))
                        cached_retry_at = float(cache_entry.get('next_replan_at', 0.0))
                        if cached_path or cached_retry_at > current_time:
                            path = cached_path
                            fail_count = int(cache_entry.get('fail_count', fail_count))
                            next_replan_at = cached_retry_at
                    elif cache_entry is not None:
                        path = tuple(cache_entry)
            if path is None and not path_pending:
                if self._can_replan_path():
                    submit_state = dict(state_view) if isinstance(state_view, dict) else {}
                    if self._submit_navigation_search(entity, target_point, map_manager, step_limit, traversal_profile, submit_state, cache_key):
                        path_pending = True
                    else:
                        path = self._finalize_navigation_search_path(
                            entity,
                            self._run_navigation_search_request(
                                map_manager,
                                self._build_navigation_search_request(entity, target_point, map_manager, step_limit, traversal_profile),
                            ),
                            target_point,
                            map_manager,
                        )
                    pending_future = submit_state.get('pending_path_future')
                    pending_signature = submit_state.get('pending_request_signature')
                    pending_target_point = submit_state.get('pending_target_point')
                    if path:
                        fail_count = 0
                        next_replan_at = 0.0
                    elif not path_pending:
                        fail_count = min(8, fail_count + 1)
                        retry_delay = min(self._path_failure_retry_max_sec, self._path_failure_retry_sec * (2 ** max(0, fail_count - 1)))
                        next_replan_at = current_time + retry_delay
                    if not path_pending:
                        if len(self._path_cache) > 64:
                            self._path_cache.clear()
                        self._path_cache[cache_key] = {
                            'path': tuple(path or self.EMPTY_PATH_PREVIEW),
                            'fail_count': fail_count,
                            'next_replan_at': next_replan_at,
                        }
                else:
                    path = tuple(state_view.get('path', self.EMPTY_PATH_PREVIEW))
            elif path:
                fail_count = 0
                next_replan_at = 0.0
            if path_pending and not path:
                path = tuple(state_view.get('path', self.EMPTY_PATH_PREVIEW))
            if not path_pending:
                pending_future = None
                pending_signature = None
                pending_target_point = None
            state = {
                'start_cell': start_cell,
                'goal_cell': goal_cell,
                'goal_point': (float(target_point[0]), float(target_point[1])),
                'raster_version': raster_version,
                'step_limit': round(step_limit, 3),
                'can_climb_steps': bool(traversal_profile.get('can_climb_steps', False)),
                'collision_radius': round(float(traversal_profile.get('collision_radius', 0.0)), 2),
                'path': tuple(path or self.EMPTY_PATH_PREVIEW),
                'index': self._path_waypoint_index(tuple(path or self.EMPTY_PATH_PREVIEW), 1),
                'planned_at': current_time,
                'next_replan_at': 0.0 if path else next_replan_at,
                'fail_count': 0 if path else fail_count,
                'last_speed': current_speed,
                'last_wp_distance': 0.0,
            }
            if pending_future is not None and pending_signature == cache_key:
                state['pending_path_future'] = pending_future
                state['pending_request_signature'] = pending_signature
                state['pending_target_point'] = pending_target_point
            self._entity_path_state[entity.id] = state
            self._stuck_state[entity.id] = {
                'best_distance': float('inf'),
                'last_progress_time': current_time,
                'last_check_time': current_time,
            }

        if state is None:
            midpoint = self._temporary_midpoint_waypoint(entity, target_point, map_manager)
            if midpoint is not None:
                self._set_navigation_overlay_state(entity, waypoint=midpoint, preview=((float(entity.position['x']), float(entity.position['y'])), midpoint, (float(target_point[0]), float(target_point[1]))), path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='passable')
                return midpoint
            forced_anchor = self._activate_infantry_supply_escape(entity, target_point, map_manager, current_time)
            if forced_anchor is not None:
                self._set_navigation_overlay_state(entity, waypoint=forced_anchor, preview=((float(entity.position['x']), float(entity.position['y'])), forced_anchor, (float(target_point[0]), float(target_point[1]))), path_valid=False, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='passable')
                return forced_anchor
            self._clear_navigation_overlay_state(entity)
            return float(entity.position['x']), float(entity.position['y'])

        escape_waypoint = state.get('escape_waypoint') if state else None
        escape_until = float(state.get('escape_until', 0.0)) if state else 0.0
        if escape_waypoint is not None and current_time < escape_until:
            self._set_navigation_overlay_state(entity, waypoint=escape_waypoint, preview=(
                (float(entity.position['x']), float(entity.position['y'])),
                (float(escape_waypoint[0]), float(escape_waypoint[1])),
                (float(target_point[0]), float(target_point[1])),
                ), path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager))
            return escape_waypoint

        path = state.get('path', [])
        if not path:
            midpoint = self._temporary_midpoint_waypoint(entity, target_point, map_manager)
            if midpoint is not None:
                self._set_navigation_overlay_state(entity, waypoint=midpoint, preview=((float(entity.position['x']), float(entity.position['y'])), midpoint, (float(target_point[0]), float(target_point[1]))), path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='passable')
                return midpoint
            forced_anchor = self._activate_infantry_supply_escape(entity, target_point, map_manager, current_time)
            if forced_anchor is not None:
                self._set_navigation_overlay_state(entity, waypoint=forced_anchor, preview=((float(entity.position['x']), float(entity.position['y'])), forced_anchor, (float(target_point[0]), float(target_point[1]))), path_valid=False, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='passable')
                return forced_anchor
            self._clear_navigation_overlay_state(entity)
            self._stuck_state[entity.id] = {
                'best_distance': float('inf'),
                'last_progress_time': current_time,
                'last_check_time': current_time,
            }
            return entity.position['x'], entity.position['y']
        index = self._path_waypoint_index(path, state.get('index', 1))
        speed_lookahead = current_speed * max(0.08, self._ai_update_interval)
        advance_distance = max(self._arrival_tolerance_world_units(map_manager), map_manager.terrain_grid_cell_size * 1.5 + speed_lookahead)
        while index < len(path) - 1 and self._distance_to_point(entity, path[index]) <= advance_distance:
            index += 1
        direct_index = self._furthest_direct_path_index(entity, path, index, map_manager)
        if direct_index > index:
            index = direct_index
        last_waypoint = state.get('last_waypoint')
        if last_waypoint is not None and index < len(path):
            if self._distance_to_point(entity, last_waypoint) > advance_distance * 0.65:
                candidate_distance = math.hypot(path[index][0] - target_point[0], path[index][1] - target_point[1])
                locked_distance = math.hypot(last_waypoint[0] - target_point[0], last_waypoint[1] - target_point[1])
                if locked_distance <= candidate_distance + max(12.0, map_manager.terrain_grid_cell_size * 0.8):
                    state['index'] = max(1, index - 1)
                    index = state['index']
        state['index'] = index
        state['last_waypoint'] = path[index]
        state['last_speed'] = current_speed
        state['last_wp_distance'] = self._distance_to_point(entity, path[index])
        if not self._can_directly_traverse(entity, path[index], map_manager):
            waypoint_status = self._movement_segment_status(entity, (entity.position['x'], entity.position['y']), path[index], map_manager)
            detour_points = tuple(waypoint_status.get('detour_points', ())) or self.EMPTY_PATH_PREVIEW
            if waypoint_status['passable'] and detour_points:
                local_path = [(float(entity.position['x']), float(entity.position['y']))]
                for detour_point in detour_points:
                    normalized = (float(detour_point[0]), float(detour_point[1]))
                    if local_path[-1] != normalized:
                        local_path.append(normalized)
                waypoint_target = (float(path[index][0]), float(path[index][1]))
                if local_path[-1] != waypoint_target:
                    local_path.append(waypoint_target)
                local_expanded_path = self._expand_path_with_step_transitions(entity, local_path, map_manager)
                segmented_local_path = tuple(self._segment_path_points(local_expanded_path, map_manager, entity=entity))
                detour_index = 1 if len(segmented_local_path) > 1 else 0
                detour_waypoint = segmented_local_path[detour_index] if segmented_local_path else waypoint_target
                preview_path = list(segmented_local_path)
                for tail_point in path[index + 1:]:
                    normalized_tail = (float(tail_point[0]), float(tail_point[1]))
                    if not preview_path or preview_path[-1] != normalized_tail:
                        preview_path.append(normalized_tail)
                preview = self._build_path_preview(entity, tuple(preview_path), detour_index)
                traversal_state = 'step-passable' if any(self._movement_segment_status(entity, preview[idx], preview[idx + 1], map_manager)['requires_step'] for idx in range(len(preview) - 1)) else 'passable'
                state['last_waypoint'] = detour_waypoint
                state['last_wp_distance'] = self._distance_to_point(entity, detour_waypoint)
                self._set_navigation_overlay_state(entity, waypoint=detour_waypoint, preview=preview, path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state=traversal_state)
                return detour_waypoint
            immediate_escape = self._build_escape_waypoint(entity, path[index], map_manager)
            if immediate_escape is not None:
                state['escape_waypoint'] = immediate_escape
                state['escape_until'] = current_time + 0.35
                preview = (
                    (float(entity.position['x']), float(entity.position['y'])),
                    (float(immediate_escape[0]), float(immediate_escape[1])),
                    (float(path[index][0]), float(path[index][1])),
                    (float(target_point[0]), float(target_point[1])),
                )
                self._set_navigation_overlay_state(entity, waypoint=immediate_escape, preview=preview, path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='passable')
                return immediate_escape
            if not self._can_replan_path():
                preview = ((float(entity.position['x']), float(entity.position['y'])), (float(path[index][0]), float(path[index][1])), (float(target_point[0]), float(target_point[1])))
                self._set_navigation_overlay_state(entity, waypoint=path[index], preview=preview, path_valid=False, traversal_state='blocked')
                return path[index]
            refresh_signature = (
                start_cell,
                goal_cell,
                raster_version,
                round(step_limit, 3),
                traversal_profile['step_climb_duration_sec'],
                round(traversal_profile.get('collision_radius', 0.0), 2),
            )
            refreshed_path, refresh_pending = self._consume_pending_navigation_search(entity, target_point, map_manager, state, refresh_signature)
            if refreshed_path:
                state['path'] = tuple(refreshed_path or self.EMPTY_PATH_PREVIEW)
                state['index'] = self._path_waypoint_index(state['path'], 1)
                state['planned_at'] = current_time
            elif not refresh_pending:
                self._submit_navigation_search(entity, target_point, map_manager, step_limit, traversal_profile, state, refresh_signature)
            if not state['path']:
                forced_anchor = self._activate_infantry_supply_escape(entity, target_point, map_manager, current_time)
                if forced_anchor is not None:
                    self._set_navigation_overlay_state(entity, waypoint=forced_anchor, preview=((float(entity.position['x']), float(entity.position['y'])), forced_anchor, (float(target_point[0]), float(target_point[1]))), path_valid=False, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state='passable')
                    return forced_anchor
                self._clear_navigation_overlay_state(entity)
                return float(entity.position['x']), float(entity.position['y'])
            path = state['path']
            index = self._path_waypoint_index(path, state.get('index', 1))
            state['last_waypoint'] = path[index]
            state['last_wp_distance'] = self._distance_to_point(entity, path[index])
        stuck = self._stuck_state.get(entity.id, {})
        if current_time - float(stuck.get('last_progress_time', current_time)) >= stall_timeout:
            escape_waypoint = self._build_escape_waypoint(entity, path[index], map_manager)
            if escape_waypoint is not None:
                state['escape_waypoint'] = escape_waypoint
                state['escape_until'] = current_time + (0.75 if getattr(entity, 'ai_navigation_path_state', 'passable') == 'step-passable' else 0.55)
                self._set_navigation_overlay_state(entity, waypoint=escape_waypoint, preview=(
                    (float(entity.position['x']), float(entity.position['y'])),
                    (float(escape_waypoint[0]), float(escape_waypoint[1])),
                    path[index],
                ), path_valid=True, traversal_state='step-passable' if getattr(entity, 'step_climb_state', None) else 'passable')
                return escape_waypoint
        preview = self._build_path_preview(entity, path, index)
        path_state = 'step-passable' if any(self._movement_segment_status(entity, preview[idx], preview[idx + 1], map_manager)['requires_step'] for idx in range(len(preview) - 1)) else 'passable'
        self._set_navigation_overlay_state(entity, waypoint=path[index], preview=preview, path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state=path_state)
        return path[index]

    def _expand_path_with_step_transitions(self, entity, path, map_manager):
        if not path:
            return self.EMPTY_PATH_PREVIEW
        expanded = [tuple(path[0])]
        previous_point = (float(path[0][0]), float(path[0][1]))
        for point in path[1:]:
            current_point = (float(point[0]), float(point[1]))
            status = self._movement_segment_status(entity, previous_point, current_point, map_manager)
            segment_targets = tuple(status.get('detour_points', ())) + (current_point,)
            segment_start = previous_point
            for segment_target in segment_targets:
                normalized_target = (float(segment_target[0]), float(segment_target[1]))
                segment_status = self._basic_movement_segment_status(entity, segment_start, normalized_target, map_manager)
                traversal = segment_status.get('traversal') or segment_status.get('transition')
                extra_points = self._terrain_policy_path_points(entity, traversal, map_manager) if traversal is not None else self.EMPTY_PATH_PREVIEW
                if not extra_points and segment_status['requires_step'] and segment_status['transition'] is not None:
                    transition = segment_status['transition']
                    approach_point = transition.get('approach_point')
                    climb_points = tuple(transition.get('climb_points', ())) or (transition.get('top_point'),)
                    extra_points = tuple(
                        (float(extra_point[0]), float(extra_point[1]))
                        for extra_point in (approach_point, *climb_points)
                        if extra_point is not None
                    )
                for extra_point in extra_points:
                    normalized = (float(extra_point[0]), float(extra_point[1]))
                    if expanded[-1] != normalized:
                        expanded.append(normalized)
                if expanded[-1] != normalized_target:
                    expanded.append(normalized_target)
                segment_start = normalized_target
            previous_point = current_point
        return tuple(expanded)

    def _is_path_traversable(self, entity, path, map_manager):
        if not path:
            return False
        previous_point = (float(entity.position['x']), float(entity.position['y']))
        for point in path[1:]:
            status = self._movement_segment_status(entity, previous_point, point, map_manager)
            if not status['passable']:
                return False
            previous_point = (float(point[0]), float(point[1]))
        return True

    def _path_cell(self, position, map_manager):
        step = max(map_manager.terrain_grid_cell_size * 2, 12)
        return int(position['x']) // step, int(position['y']) // step

    def _traversal_profile(self, entity):
        role_key = self._role_key(entity)
        can_climb = bool(getattr(entity, 'can_climb_steps', True if role_key in {'hero', 'infantry', 'engineer'} else False))
        duration = float(getattr(entity, 'step_climb_duration_sec', 2.0))
        # 1~4 号机器人上台阶耗时固定 1s。
        try:
            if isinstance(entity.id, str) and entity.id.startswith('robot_'):
                num = int(entity.id.split('_')[-1])
                if 1 <= num <= 4:
                    duration = 1.0
        except Exception:
            pass
        # 将属性回写给实体，供物理层直接使用。
        entity.can_climb_steps = can_climb
        entity.step_climb_duration_sec = duration
        return {
            'can_climb_steps': can_climb,
            'step_climb_duration_sec': duration,
            'collision_radius': float(getattr(entity, 'collision_radius', 0.0)),
        }

    def _supply_claimable_ammo(self, entity, rules_engine, game_time):
        if rules_engine is None:
            return 0
        interval = float(rules_engine.rules.get('supply', {}).get('ammo_interval', 60.0))
        ammo_gain = int(rules_engine._supply_ammo_gain(entity)) if hasattr(rules_engine, '_supply_ammo_gain') else int(rules_engine.rules.get('supply', {}).get('ammo_gain', 100))
        if interval <= 0 or ammo_gain <= 0:
            return 0
        generated = int(game_time // interval) * ammo_gain
        claimed = int(getattr(entity, 'supply_ammo_claimed', 0))
        return max(0, generated - claimed)

    def _next_supply_eta(self, rules_engine, game_time):
        if rules_engine is None:
            return 999.0
        interval = float(rules_engine.rules.get('supply', {}).get('ammo_interval', 60.0))
        if interval <= 0:
            return 999.0
        remainder = game_time % interval
        if remainder <= 1e-6:
            return 0.0
        return interval - remainder

    def _select_supply_runner(self, entity, allies, rules_engine, game_time):
        if rules_engine is None:
            return entity
        candidates = [member for member in allies if member.is_alive() and getattr(member, 'ammo_type', 'none') != 'none']
        if not candidates:
            return entity
        def urgency(member):
            ammo = getattr(member, 'ammo', 0)
            claimable = self._supply_claimable_ammo(member, rules_engine, game_time)
            heat_ratio = 0.0 if member.max_heat <= 0 else member.heat / max(member.max_heat, 1e-6)
            ammo_kind_priority = 1 if getattr(member, 'ammo_type', '17mm') == '17mm' else 0
            stable_id_priority = -sum(ord(char) for char in str(getattr(member, 'id', '')))
            return (claimable > 0, ammo <= 0, ammo < 20, heat_ratio < 0.8, -ammo, ammo_kind_priority, stable_id_priority)
        return max(candidates, key=urgency)

    def get_supply_slot(self, entity, map_manager):
        if map_manager is None:
            return None
        facility = None
        for region in map_manager.get_facility_regions('supply'):
            if region.get('team') == entity.team:
                facility = region
                break
        if facility is None:
            return None
        slots = self._facility_slots(facility)
        if not slots:
            return self._facility_anchor_point(facility, map_manager, entity=entity)
        slot_index = self._stable_slot_index(entity.id, len(slots))
        return map_manager.find_nearest_passable_point(
            slots[slot_index],
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
            search_radius=max(40, int(getattr(entity, 'collision_radius', 16.0) * 3.0)),
            step=max(4, map_manager.terrain_grid_cell_size),
        )

    def _facility_slots(self, facility):
        center_x, center_y = self.facility_center(facility)
        width = max(20, int(abs(facility['x2'] - facility['x1'])))
        height = max(20, int(abs(facility['y2'] - facility['y1'])))
        offset_x = max(18, width // 4)
        offset_y = max(18, height // 4)
        return [
            (center_x - offset_x, center_y - offset_y),
            (center_x + offset_x, center_y - offset_y),
            (center_x - offset_x, center_y + offset_y),
            (center_x + offset_x, center_y + offset_y),
            (center_x, center_y - offset_y),
            (center_x, center_y + offset_y),
        ]

    def _stable_slot_index(self, key, size):
        if size <= 0:
            return 0
        return sum(ord(char) for char in str(key)) % size

    def _apply_local_avoidance(self, entity, desired_velocity, entities, target_point=None):
        if not self.enable_entity_movement:
            return desired_velocity

        desired_x, desired_y = desired_velocity
        base_speed = math.hypot(desired_x, desired_y)
        if base_speed <= 1e-6:
            return desired_velocity

        repulsion_x = 0.0
        repulsion_y = 0.0
        lateral_x = 0.0
        lateral_y = 0.0
        target_dx = 0.0
        target_dy = 0.0
        if target_point is not None:
            target_dx = target_point[0] - entity.position['x']
            target_dy = target_point[1] - entity.position['y']

        for other in entities:
            if other.id == entity.id or not other.is_alive() or not getattr(other, 'movable', True):
                continue

            dx = entity.position['x'] - other.position['x']
            dy = entity.position['y'] - other.position['y']
            distance = math.hypot(dx, dy)
            if distance <= 1e-6 or distance > 64.0:
                continue

            influence = (64.0 - distance) / 64.0
            repulsion_x += (dx / distance) * influence
            repulsion_y += (dy / distance) * influence

            if target_point is not None:
                other_target_dx = target_point[0] - other.position['x']
                other_target_dy = target_point[1] - other.position['y']
                heading_dot = desired_x * getattr(other, 'velocity', {}).get('vx', 0.0) + desired_y * getattr(other, 'velocity', {}).get('vy', 0.0)
                shared_goal = math.hypot(other_target_dx - target_dx, other_target_dy - target_dy) <= 48.0
                if shared_goal or heading_dot < 0.0:
                    side = 1.0 if entity.id < other.id else -1.0
                    lateral_x += (-dy / distance) * influence * side
                    lateral_y += (dx / distance) * influence * side

        recovery_timer = float(getattr(entity, 'collision_recovery_timer', 0.0))
        if recovery_timer > 0.0:
            rec_x, rec_y = getattr(entity, 'collision_recovery_vector', (0.0, 0.0))
            recovery_gain = min(1.0, recovery_timer / 0.5)
            repulsion_x += rec_x * (0.9 + 0.6 * recovery_gain)
            repulsion_y += rec_y * (0.9 + 0.6 * recovery_gain)

        adjusted_x = desired_x + repulsion_x * base_speed * 0.85 + lateral_x * base_speed * 0.45
        adjusted_y = desired_y + repulsion_y * base_speed * 0.85 + lateral_y * base_speed * 0.45
        adjusted_speed = math.hypot(adjusted_x, adjusted_y)
        if adjusted_speed <= 1e-6:
            return 0.0, 0.0
        scale = base_speed / adjusted_speed
        return adjusted_x * scale, adjusted_y * scale

    def maintain_distance(self, entity, target, desired_distance, speed=2.8, map_manager=None):
        dx = target['x'] - entity.position['x']
        dy = target['y'] - entity.position['y']
        distance = max(target['distance'], 1.0)
        if distance > desired_distance + 120:
            if map_manager is not None:
                return self.navigate_towards(entity, (target['x'], target['y']), speed, map_manager)
            return (dx / distance) * speed, (dy / distance) * speed
        if distance < desired_distance - 120:
            return (-dx / distance) * speed, (-dy / distance) * speed
        return (-dy / distance) * (speed * 0.6), (dx / distance) * (speed * 0.6)

    def _assault_anchor(self, entity, structure, map_manager, preferred_distance_m=3.0):
        preferred_distance = self._meters_to_world_units(preferred_distance_m, map_manager)
        dx = float(entity.position['x']) - float(structure.position['x'])
        dy = float(entity.position['y']) - float(structure.position['y'])
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx, dy, length = 0.0, -1.0, 1.0
        return (
            float(structure.position['x']) + dx / length * preferred_distance,
            float(structure.position['y']) + dy / length * preferred_distance,
        )

    def _furthest_direct_path_index(self, entity, path, current_index, map_manager):
        if current_index >= len(path) - 1:
            return current_index
        furthest = current_index
        for candidate_index in range(len(path) - 1, current_index, -1):
            if self._can_directly_traverse(entity, path[candidate_index], map_manager):
                furthest = candidate_index
                break
        return furthest

    def _can_directly_traverse(self, entity, point, map_manager):
        if map_manager is None or point is None:
            return False
        status = self._movement_segment_status(entity, (entity.position['x'], entity.position['y']), point, map_manager)
        return bool(status['passable']) and not bool(status.get('detour_points'))

    def _find_team_facility(self, map_manager, team, facility_type):
        if map_manager is None:
            return None
        for facility in map_manager.get_facility_regions(facility_type):
            if facility.get('team') == team:
                return facility
        return None

    def _facility_anchor_point(self, facility, map_manager, entity=None):
        anchor = self.facility_center(facility)
        if map_manager is None or anchor is None:
            return anchor
        collision_radius = float(getattr(entity, 'collision_radius', 0.0)) if entity is not None else 16.0

        if facility.get('type') == 'base':
            half_w = abs(facility.get('x2', anchor[0]) - facility.get('x1', anchor[0])) / 2.0
            half_h = abs(facility.get('y2', anchor[1]) - facility.get('y1', anchor[1])) / 2.0
            margin = max(32.0, collision_radius * 1.6)
            reference_x = float(entity.position['x']) if entity is not None else float(anchor[0])
            reference_y = float(entity.position['y']) if entity is not None else float(anchor[1])
            candidates = [
                (anchor[0] + half_w + margin, anchor[1]),
                (anchor[0] - half_w - margin, anchor[1]),
                (anchor[0], anchor[1] + half_h + margin),
                (anchor[0], anchor[1] - half_h - margin),
            ]
            best = None
            best_dist = None
            for candidate in candidates:
                if map_manager.is_position_valid_for_radius(candidate[0], candidate[1], collision_radius=collision_radius):
                    dist = math.hypot(candidate[0] - reference_x, candidate[1] - reference_y)
                    if best_dist is None or dist < best_dist:
                        best = candidate
                        best_dist = dist
            anchor = best or anchor

        return map_manager.find_nearest_passable_point(
            anchor,
            collision_radius=collision_radius,
            search_radius=max(72, int(collision_radius * 5.0)),
            step=max(4, map_manager.terrain_grid_cell_size),
        )

    def facility_center(self, facility):
        points = facility.get('points', []) if isinstance(facility, dict) else []
        if points:
            valid_points = []
            sum_x = 0.0
            sum_y = 0.0
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                normalized = (float(point[0]), float(point[1]))
                valid_points.append(normalized)
                sum_x += normalized[0]
                sum_y += normalized[1]
            if valid_points:
                average_point = (sum_x / len(valid_points), sum_y / len(valid_points))
                candidate_points = [
                    average_point,
                    (
                        (float(facility.get('x1', average_point[0])) + float(facility.get('x2', average_point[0]))) * 0.5,
                        (float(facility.get('y1', average_point[1])) + float(facility.get('y2', average_point[1]))) * 0.5,
                    ),
                ]
                signed_area = 0.0
                centroid_x = 0.0
                centroid_y = 0.0
                previous_x, previous_y = valid_points[-1]
                for current_x, current_y in valid_points:
                    cross = previous_x * current_y - current_x * previous_y
                    signed_area += cross
                    centroid_x += (previous_x + current_x) * cross
                    centroid_y += (previous_y + current_y) * cross
                    previous_x, previous_y = current_x, current_y
                if abs(signed_area) > 1e-6:
                    candidate_points.insert(0, (centroid_x / (3.0 * signed_area), centroid_y / (3.0 * signed_area)))
                for candidate in candidate_points:
                    if self._point_in_behavior_region(candidate, facility):
                        return int(round(candidate[0])), int(round(candidate[1]))

                x1 = float(facility.get('x1', average_point[0]))
                x2 = float(facility.get('x2', average_point[0]))
                y1 = float(facility.get('y1', average_point[1]))
                y2 = float(facility.get('y2', average_point[1]))
                best_inside = None
                best_distance = None
                for ratio_y in (0.5, 0.35, 0.65, 0.2, 0.8):
                    sample_y = y1 + (y2 - y1) * ratio_y
                    for ratio_x in (0.5, 0.35, 0.65, 0.2, 0.8):
                        sample_x = x1 + (x2 - x1) * ratio_x
                        candidate = (sample_x, sample_y)
                        if not self._point_in_behavior_region(candidate, facility):
                            continue
                        distance = math.hypot(candidate[0] - average_point[0], candidate[1] - average_point[1])
                        if best_distance is None or distance < best_distance:
                            best_distance = distance
                            best_inside = candidate
                if best_inside is not None:
                    return int(round(best_inside[0])), int(round(best_inside[1]))
                return int(round(average_point[0])), int(round(average_point[1]))
        return int((facility['x1'] + facility['x2']) / 2), int((facility['y1'] + facility['y2']) / 2)