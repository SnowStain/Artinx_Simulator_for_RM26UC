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


class AIController:
    EMPTY_PATH_PREVIEW = ()
    ROLE_BEHAVIOR_TREE_FILES = {
        'sentry': ('sentry_btcpp.xml', 'SentryBehaviorTree'),
        'infantry': ('infantry_btcpp.xml', 'InfantryBehaviorTree'),
        'hero': ('hero_btcpp.xml', 'HeroBehaviorTree'),
        'engineer': ('engineer_btcpp.xml', 'EngineerBehaviorTree'),
    }

    def __init__(self, config):
        self.config = config
        self.ai_strategy = config.get('ai', {}).get('strategy', {})
        self._ai_config = config.get('ai', {})
        self._patrol_index = {}
        self._post_supply_goal_state = {}
        self.enable_entity_movement = config.get('simulator', {}).get('enable_entity_movement', True)
        self._path_cache = {}
        self._stuck_state = {}
        self._ai_update_interval = float(self._ai_config.get('update_interval_sec', 0.12))
        self._path_replan_interval = float(self._ai_config.get('path_replan_interval_sec', 0.5))
        self._path_replans_per_update = max(1, int(self._ai_config.get('path_replans_per_update', 1)))
        self._pathfinder_max_iterations = max(80, int(self._ai_config.get('pathfinder_max_iterations', 700)))
        self._pathfinder_time_budget_sec = max(0.0005, float(self._ai_config.get('pathfinder_time_budget_ms', 3.5)) / 1000.0)
        self._pathfinder_total_budget_sec = max(self._pathfinder_time_budget_sec, float(self._ai_config.get('pathfinder_total_budget_ms', 12.0)) / 1000.0)
        self._pathfinder_max_attempts = max(1, int(self._ai_config.get('pathfinder_max_attempts', 6)))
        self._pathfinder_use_dual_resolution = bool(self._ai_config.get('pathfinder_use_dual_resolution', False))
        self._pathfinder_try_resolved_target = bool(self._ai_config.get('pathfinder_try_resolved_target', False))
        self._path_replans_remaining = self._path_replans_per_update
        self._last_ai_update_time = {}
        self._entity_path_state = {}
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
        self._refresh_behavior_runtime_overrides(force=True)

    def _entity_update_phase_offset(self, entity_id):
        # 打散同帧集中重算，避免 update_interval 对齐造成周期性卡顿峰值。
        if self._ai_update_interval <= 1e-6:
            return 0.0
        phase = abs(hash(str(entity_id))) % 4096
        return (phase / 4096.0) * self._ai_update_interval

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
                self._decision_spec('emergency_retreat', '紧急撤退', self._is_critical_state, self._action_emergency_retreat),
                self._decision_spec('sentry_opening_highground', '开局一级台阶飞坡', self._should_sentry_opening_highground, self._action_sentry_opening_highground),
                self._decision_spec('sentry_fly_slope', '飞坡突入', self._should_sentry_fly_slope, self._action_sentry_fly_slope),
                self._decision_spec('force_push_base', '推进基地', self._should_force_push_base, self._action_push_base),
                self._decision_spec('swarm_attack', '发现即集火', self._has_target, self._action_swarm_attack),
                self._decision_spec('protect_hero', '保护英雄', self._should_protect_hero, self._action_protect_hero),
                self._decision_spec('highground_assault', '高地压制', self._should_take_enemy_highground, self._action_highground_assault),
                self._decision_spec('support_infantry_push', '配合步兵推进', self._should_support_infantry_push, self._action_support_infantry_push),
                self._decision_spec('support_engineer', '护送工程', self._should_support_engineer, self._action_support_engineer),
                self._decision_spec('intercept_enemy_engineer', '拦截敌工', self._should_intercept_enemy_engineer, self._action_intercept_enemy_engineer),
                self._decision_spec('push_outpost', '推进前哨站', self._should_push_outpost, self._action_push_outpost),
                self._decision_spec('teamfight_cover', '团战掩护', self._has_teamfight_window, self._action_teamfight_cover),
                self._decision_spec('push_base', '推进基地', self._should_push_base, self._action_push_base),
                self._decision_spec('terrain_fly_slope', '飞坡', self._should_terrain_fly_slope, self._action_terrain_fly_slope, default_destination_types=('fly_slope',), terrain_mode='fly_slope'),
                self._decision_spec('terrain_first_step', '翻越一级台阶', self._should_terrain_first_step, self._action_terrain_first_step, default_destination_types=('first_step',), terrain_mode='first_step'),
                self._decision_spec('terrain_second_step', '翻越二级台阶', self._should_terrain_second_step, self._action_terrain_second_step, default_destination_types=('second_step',), terrain_mode='second_step'),
                self._decision_spec('patrol_key_facilities', '巡关键设施', None, self._action_patrol_key_facilities, fallback=True),
            ],
            'infantry': [
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('must_restock', '强制补给', self._must_restock_before_combat, self._action_opening_supply),
                self._decision_spec('force_push_base', '推进基地', self._should_force_push_base, self._action_push_base),
                self._decision_spec('emergency_retreat', '紧急撤退', self._is_critical_state, self._action_emergency_retreat),
                self._decision_spec('opening_supply', '常规补给', self._needs_supply, self._action_opening_supply),
                self._decision_spec('infantry_opening_highground', '开局抢高地增益', self._should_infantry_opening_highground, self._action_infantry_opening_highground),
                self._decision_spec('swarm_attack', '发现即集火', self._has_target, self._action_swarm_attack),
                self._decision_spec('activate_energy', '激活能量机关', self._should_activate_energy, self._action_activate_energy),
                self._decision_spec('intercept_enemy_engineer', '拦截敌工', self._should_intercept_enemy_engineer, self._action_intercept_enemy_engineer),
                self._decision_spec('highground_assault', '高地压制前哨', self._should_take_enemy_highground, self._action_highground_assault),
                self._decision_spec('push_outpost', '推进前哨站', self._should_push_outpost, self._action_push_outpost),
                self._decision_spec('teamfight_push', '团战推进', self._has_teamfight_window, self._action_teamfight_push),
                self._decision_spec('push_base', '推进基地', self._should_push_base, self._action_push_base),
                self._decision_spec('terrain_fly_slope', '飞坡', self._should_terrain_fly_slope, self._action_terrain_fly_slope, default_destination_types=('fly_slope',), terrain_mode='fly_slope'),
                self._decision_spec('terrain_first_step', '翻越一级台阶', self._should_terrain_first_step, self._action_terrain_first_step, default_destination_types=('first_step',), terrain_mode='first_step'),
                self._decision_spec('terrain_second_step', '翻越二级台阶', self._should_terrain_second_step, self._action_terrain_second_step, default_destination_types=('second_step',), terrain_mode='second_step'),
                self._decision_spec('patrol_key_facilities', '巡关键设施', None, self._action_patrol_key_facilities, fallback=True),
            ],
            'hero': [
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('must_restock', '强制补给', self._must_restock_before_combat, self._action_opening_supply),
                self._decision_spec('force_push_base', '推进基地', self._should_force_push_base, self._action_push_base),
                self._decision_spec('opening_supply', '常规补给', self._needs_supply, self._action_opening_supply),
                self._decision_spec('hero_seek_cover', '英雄找掩护', self._should_hero_seek_cover, self._action_hero_seek_cover),
                self._decision_spec('hero_opening_highground', '开局高地部署', self._should_hero_opening_highground, self._action_hero_opening_highground),
                self._decision_spec('highground_assault', '近战高地压制', self._should_hero_melee_highground_assault, self._action_highground_assault),
                self._decision_spec('swarm_attack', '发现即集火', self._has_target, self._action_swarm_attack),
                self._decision_spec('activate_energy', '激活能量机关', self._should_activate_energy, self._action_activate_energy),
                self._decision_spec('hero_lob_outpost', '吊射前哨站', self._should_hero_lob_outpost, self._action_hero_lob_outpost),
                self._decision_spec('hero_lob_base', '吊射基地', self._should_hero_lob_base, self._action_hero_lob_base),
                self._decision_spec('terrain_fly_slope', '飞坡', self._should_terrain_fly_slope, self._action_terrain_fly_slope, default_destination_types=('fly_slope',), terrain_mode='fly_slope'),
                self._decision_spec('terrain_first_step', '翻越一级台阶', self._should_terrain_first_step, self._action_terrain_first_step, default_destination_types=('first_step',), terrain_mode='first_step'),
                self._decision_spec('terrain_second_step', '翻越二级台阶', self._should_terrain_second_step, self._action_terrain_second_step, default_destination_types=('second_step',), terrain_mode='second_step'),
                self._decision_spec('push_base', '推进基地', self._should_push_base, self._action_push_base),
                self._decision_spec('patrol_key_facilities', '巡关键设施', None, self._action_patrol_key_facilities, fallback=True),
            ],
            'engineer': [
                self._decision_spec('recover_after_respawn', '复活回补', self._should_recover_after_respawn, self._action_recover_after_respawn),
                self._decision_spec('emergency_retreat', '紧急撤退', self._is_critical_state, self._action_emergency_retreat),
                self._decision_spec('engineer_exchange', '回家兑矿', self._needs_engineer_exchange, self._action_engineer_exchange),
                self._decision_spec('engineer_mine', '前往采矿', self._needs_engineer_mining, self._action_engineer_mine),
                self._decision_spec('terrain_fly_slope', '飞坡', self._should_terrain_fly_slope, self._action_terrain_fly_slope, default_destination_types=('fly_slope',), terrain_mode='fly_slope'),
                self._decision_spec('terrain_first_step', '翻越一级台阶', self._should_terrain_first_step, self._action_terrain_first_step, default_destination_types=('first_step',), terrain_mode='first_step'),
                self._decision_spec('terrain_second_step', '翻越二级台阶', self._should_terrain_second_step, self._action_terrain_second_step, default_destination_types=('second_step',), terrain_mode='second_step'),
                self._decision_spec('engineer_cycle', '取矿兑矿循环', None, self._action_engineer_cycle, fallback=True),
            ],
        }

    def _available_plugin_bindings_for_role(self, role_key):
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

    def _normalize_behavior_point_targets(self, targets):
        if not isinstance(targets, dict):
            return {}
        normalized = {}
        for key, value in targets.items():
            if not isinstance(key, str):
                continue
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            try:
                normalized[key] = (float(value[0]), float(value[1]))
            except (TypeError, ValueError):
                continue
        return normalized

    def get_available_decision_plugins(self, role_key):
        return [dict(binding) for binding in self._available_plugin_bindings_for_role(role_key)]

    def _role_decision_order_override(self, role_key, available_ids):
        role_entry = self._behavior_override_roles().get(role_key, {})
        order = role_entry.get('decision_order') if isinstance(role_entry, dict) else None
        if order is None:
            return list(available_ids)
        if not isinstance(order, list):
            return list(available_ids)
        return [str(decision_id) for decision_id in order if str(decision_id) in available_ids]

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
        self.role_decision_specs = self._build_role_decision_specs()
        self.role_trees = self._build_role_trees()
        return True

    def _behavior_condition_registry(self):
        return {
            'front_gun_locked': lambda ctx: getattr(ctx.entity, 'front_gun_locked', False),
            'recover_after_respawn': self._should_recover_after_respawn,
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
        override = decisions.get(decision_id, {}) if isinstance(decisions, dict) else {}
        return override if isinstance(override, dict) else {}

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
            'front_gun_locked': bool(getattr(entity, 'front_gun_locked', False)),
            'hero_ranged': bool(self._hero_prefers_ranged(entity)),
            'hero_melee': bool(self._hero_prefers_melee(entity)),
            'enemy_outpost_alive': bool(enemy_outpost is not None and enemy_outpost.is_alive()),
            'enemy_base_alive': bool(enemy_base is not None and enemy_base.is_alive()),
            'carried_minerals': float(context.data.get('carried_minerals', 0)),
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
        regions = []
        shared_regions = override.get(field_name, [])
        if isinstance(shared_regions, list):
            regions.extend(region for region in shared_regions if isinstance(region, dict))
        if team is not None:
            by_team = override.get(f'{field_name}_by_team', {})
            team_regions = by_team.get(team, []) if isinstance(by_team, dict) else []
            if isinstance(team_regions, list):
                explicit = [region for region in team_regions if isinstance(region, dict)]
                if explicit:
                    return explicit
        return regions

    def _behavior_override_regions(self, override, team=None):
        return self._behavior_override_team_regions(override, 'task_regions', team=team)

    def _behavior_override_destination_regions(self, override, team=None):
        return self._behavior_override_team_regions(override, 'destination_regions', team=team)

    def _behavior_override_point_targets(self, override, team=None):
        if not isinstance(override, dict):
            return {}
        merged = self._normalize_behavior_point_targets(override.get('point_targets', {}))
        if team is None:
            return merged
        by_team = override.get('point_targets_by_team', {})
        team_targets = by_team.get(team, {}) if isinstance(by_team, dict) else {}
        merged.update(self._normalize_behavior_point_targets(team_targets))
        return merged

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
        for region in self._behavior_override_destination_regions(override, team=context.entity.team):
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
        radii = [self._behavior_region_navigation_radius(region, entity=entity) for region in self._behavior_override_destination_regions(override, team=team)]
        return max(radii, default=0.0)

    def _behavior_override_inside_destination(self, context, override):
        point = (float(context.entity.position['x']), float(context.entity.position['y']))
        return any(self._point_in_behavior_region(point, region) for region in self._behavior_override_destination_regions(override, team=context.entity.team))

    def _navigate_to_behavior_override_region(self, context, spec_label, override):
        region_target = self._nearest_behavior_override_center(context, override)
        if region_target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.8, context.map_manager)
        summary = f'{spec_label}：先进入任务区域'
        return self._set_decision(context, summary, target=context.data.get('target'), target_point=region_target, speed=speed, preferred_route={'target': region_target}, turret_state='aiming' if context.data.get('target') else 'searching')

    def _apply_behavior_destination_override(self, context, spec_label, override):
        if not self._behavior_override_destination_regions(override, team=context.entity.team):
            return None
        destination_target = self._behavior_override_destination_center(context, override)
        if destination_target is None:
            return FAILURE
        decision = context.data.get('decision')
        target = decision.get('target') if isinstance(decision, dict) else context.data.get('target')
        turret_state = decision.get('turret_state', 'aiming' if target else 'searching') if isinstance(decision, dict) else ('aiming' if target else 'searching')
        if decision is None or not self._behavior_override_inside_destination(context, override):
            summary = f'{spec_label}：前往编辑目的地区域'
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

        def wrapped_condition(context):
            if enabled_state is False:
                return False
            if not self._behavior_override_time_ok(context.game_time, override):
                return False
            if not self._behavior_override_expression_ok(context, override):
                return False
            if not fallback and original_condition is not None and not bool(original_condition(context)):
                return False
            if str(override.get('region_mode', 'enter_then_execute')) == 'strict_inside' and self._behavior_override_regions(override):
                return self._behavior_override_inside_entity(context, override)
            return True

        def wrapped_action(context):
            if enabled_state is False:
                return FAILURE
            if not self._behavior_override_time_ok(context.game_time, override):
                return FAILURE
            if not self._behavior_override_expression_ok(context, override):
                return FAILURE
            if self._behavior_override_regions(override) and not self._behavior_override_inside_entity(context, override):
                return self._navigate_to_behavior_override_region(context, override.get('label', spec.get('label', '任务')), override)
            result = original_action(context)
            destination_result = self._apply_behavior_destination_override(context, override.get('label', spec.get('label', '任务')), override)
            if destination_result is not None:
                return destination_result
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

    def get_decision_destination_preview_regions(self, role_key, decision_id, map_manager, team=None):
        if map_manager is None:
            return []
        binding = self._available_plugin_binding(role_key, decision_id)
        if binding is None:
            return []
        preview_regions = binding.get('preview_regions') if callable(binding.get('preview_regions')) else None
        override = self._behavior_override_for_decision(role_key, decision_id)
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

    def _arrival_tolerance_world_units(self, map_manager=None):
        tolerance_m = float(self.config.get('ai', {}).get('target_arrival_tolerance_m', 0.6))
        return max(8.0, self._meters_to_world_units(tolerance_m, map_manager))

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

    def _is_target_reached(self, entity, target_point, map_manager=None):
        if target_point is None:
            return True
        region = self._target_region(target_point, map_manager)
        entity_point = (float(entity.position['x']), float(entity.position['y']))
        if region is not None:
            return self._is_point_inside_region(entity_point, region, map_manager) and self._distance_to_point(entity, target_point) <= self._arrival_tolerance_world_units(map_manager)
        return self._distance_to_point(entity, target_point) <= self._arrival_tolerance_world_units(map_manager)

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

    def _clear_navigation_overlay_state(self, entity):
        self._set_navigation_overlay_state(entity, waypoint=None, preview=self.EMPTY_PATH_PREVIEW, path_valid=False, region_radius=0.0, traversal_state='idle')

    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0, controlled_entity_ids=None):
        if self._last_behavior_reload_check_time < 0.0 or game_time - self._last_behavior_reload_check_time >= self._behavior_reload_check_interval:
            self._last_behavior_reload_check_time = game_time
            self._refresh_behavior_runtime_overrides()
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        self._path_replans_remaining = self._path_replans_per_update
        for entity in entities:
            if controlled_ids is not None and entity.id not in controlled_ids:
                continue
            if not self._should_control_entity(entity):
                continue
            last_update = self._last_ai_update_time.get(entity.id)
            if last_update is None:
                last_update = game_time - self._entity_update_phase_offset(entity.id)
                self._last_ai_update_time[entity.id] = last_update
            if game_time - last_update < self._ai_update_interval:
                self._maintain_continuous_motion(entity)
                continue
            self._last_ai_update_time[entity.id] = game_time
            context = self._build_context(entity, entities, map_manager, rules_engine, game_time, game_duration)
            tree = self.role_trees.get(context.data['role_key'])
            if tree is None:
                self._apply_idle_decision(entity, '未定义角色行为树')
                continue
            result = tree.tick(context)
            decision = context.data.get('decision')
            if result == FAILURE or decision is None:
                decision = self._idle_navigation_decision(context, '行为树未命中有效分支，保持缓行巡航')
            bt_node = str(context.data.get('bt_action_node', ''))
            decision['bt_node'] = bt_node
            self._store_decision_diagnostics(entity, context, bt_node)
            self._apply_decision(entity, decision, rules_engine)

    def _should_control_entity(self, entity):
        if not entity.is_alive():
            return False
        if entity.type not in {'robot', 'sentry'}:
            return False
        return True

    def _build_context(self, entity, entities, map_manager, rules_engine, game_time, game_duration):
        role_key = self._role_key(entity)
        strategy = self.ai_strategy.get(role_key, self.ai_strategy.get('infantry', {}))
        opening_phase = game_time <= min(45.0, max(30.0, game_duration * 0.12 if game_duration > 0 else 45.0))
        enemies = [other for other in entities if other.team != entity.team and other.is_alive()]
        allies = [other for other in entities if other.team == entity.team and other.id != entity.id and other.is_alive()]
        target = self.select_priority_target(entity, enemies, strategy, rules_engine)
        nearby_allies = [other for other in allies if self._distance(entity, other) <= self._meters_to_world_units(5.0, map_manager)]
        nearby_enemies = [other for other in enemies if self._distance(entity, other) <= self._meters_to_world_units(6.0, map_manager)]
        own_outpost = self._find_entity(entities, entity.team, 'outpost')
        own_base = self._find_entity(entities, entity.team, 'base')
        enemy_team = 'blue' if entity.team == 'red' else 'red'
        enemy_outpost = self._find_entity(entities, enemy_team, 'outpost')
        enemy_base = self._find_entity(entities, enemy_team, 'base')
        allied_sentry = self._find_entity(entities, entity.team, 'sentry')
        allied_hero = self._find_entity_by_role(entities, entity.team, 'hero')
        allied_infantry = self._find_entity_by_role(entities, entity.team, 'infantry', exclude_id=entity.id)
        allied_engineer = self._find_entity_by_role(entities, entity.team, 'engineer')
        enemy_hero = self._find_entity_by_role(entities, enemy_team, 'hero')
        enemy_engineer = self._find_entity_by_role(entities, enemy_team, 'engineer')
        energy_anchor = self.get_energy_anchor(entity.team, map_manager)
        energy_snapshot = rules_engine.get_energy_mechanism_snapshot(entity.team) if rules_engine is not None and hasattr(rules_engine, 'get_energy_mechanism_snapshot') else {'can_activate': False, 'state': 'inactive'}
        mining_anchor = self.get_mining_anchor(entity, map_manager)
        exchange_anchor = self.get_exchange_anchor(entity, map_manager)
        map_center = self.get_map_center(map_manager)
        health_ratio = 0.0 if entity.max_health <= 0 else entity.health / entity.max_health
        heat_ratio = 0.0 if entity.max_heat <= 0 else entity.heat / entity.max_heat
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
        if self._must_restock_before_combat(context):
            return True
        opening_need = False
        if self._is_opening_phase(context):
            opening_target = self._opening_ammo_target(context)
            if opening_target > 0 and getattr(entity, 'ammo', 0) < opening_target:
                opening_need = True
                if getattr(entity, 'ammo', 0) <= 0:
                    return True
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
        return (
            context.data.get('health_ratio', 1.0) <= 0.35
            or context.data.get('heat_ratio', 0.0) >= 0.82
            or (context.data.get('ammo_low') and context.data.get('outnumbered'))
        )

    def _has_target(self, context):
        return context.data.get('target') is not None

    def _has_teamfight_window(self, context):
        return len(context.data.get('nearby_enemies', [])) >= 1

    def _should_execute_post_supply_plan(self, context):
        return False

    def _should_force_push_base(self, context):
        return bool(context.data.get('base_assault_unlocked'))

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
            state = {'committed': random.random() <= 0.9, 'completed': False}
            self._sentry_fly_slope_state[context.entity.id] = state
        if not state.get('committed', False) or state.get('completed', False):
            return False
        return True

    def _should_take_enemy_highground(self, context):
        return self._outpost_pressure_highground_anchor(context) is not None

    def _should_claim_buff(self, context):
        return context.data.get('role_key') in {'hero', 'infantry'} and getattr(context.entity, 'terrain_buff_timer', 0.0) <= 0.25

    def _should_activate_energy(self, context):
        role_key = context.data.get('role_key')
        if role_key not in {'hero', 'infantry'}:
            return False
        if context.data.get('energy_anchor') is None or context.data.get('energy_buff_active'):
            return False
        if not context.data.get('energy_can_activate', False):
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
        return (
            context.data.get('role_key') == 'engineer'
            and context.data.get('carried_minerals', 0) <= 0
            and context.data.get('mining_anchor') is not None
        )

    def _needs_engineer_exchange(self, context):
        return (
            context.data.get('role_key') == 'engineer'
            and context.data.get('carried_minerals', 0) > 0
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
        enemy_base = context.data.get('enemy_base')
        if enemy_base is None or not enemy_base.is_alive():
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        if enemy_outpost is not None and enemy_outpost.is_alive():
            return False
        return bool(context.data.get('base_assault_unlocked'))

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

    def _set_decision(self, context, summary, target=None, target_point=None, speed=None, posture=None, preferred_route=None, fire_control='idle', chassis_state='normal', turret_state='searching', angular_velocity=0.0, orbit=False):
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
            'navigation_radius': self._target_region_radius(entity, strategic_target, context.map_manager),
            'velocity': velocity,
            'fire_control_state': fire_control,
            'chassis_state': chassis_state,
            'turret_state': turret_state,
            'angular_velocity': angular_velocity,
            'posture': posture,
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
        if not self._can_directly_traverse(entity, waypoint, map_manager):
            return None
        return waypoint

    def _navigation_subgoal_spacing(self, map_manager=None):
        spacing_m = float(self._ai_config.get('navigation_subgoal_spacing_m', 1.35))
        base_step = 18.0
        if map_manager is not None:
            base_step = max(base_step, float(map_manager.terrain_grid_cell_size) * 2.0)
        return max(base_step, self._meters_to_world_units(spacing_m, map_manager))

    def _segment_path_points(self, path_points, map_manager=None):
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
        focus_target = self._priority_enemy_unit_target(context) or context.data.get('target')
        speed = self._meters_to_world_units(2.2, context.map_manager)
        if self._distance_to_point(context.entity, slope_anchor) > self._meters_to_world_units(0.8, context.map_manager):
            result = self._set_decision(
                context,
                '哨兵先进入飞坡起始位，准备对正坡道冲坡',
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
                    'summary': '哨兵从飞坡起始增益点满功率冲坡，越过死区后落入敌侧区域',
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

    def _movement_segment_status(self, entity, from_point, to_point, map_manager, step_limit=None):
        if map_manager is None or from_point is None or to_point is None:
            return {'passable': False, 'requires_step': False, 'transition': None, 'reason': 'no_map'}
        result = map_manager.evaluate_movement_path(
            float(from_point[0]),
            float(from_point[1]),
            float(to_point[0]),
            float(to_point[1]),
            max_height_delta_m=float(step_limit if step_limit is not None else getattr(entity, 'max_terrain_step_height_m', 0.05)),
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
        )
        if result.get('ok'):
            return {'passable': True, 'requires_step': False, 'transition': None, 'reason': 'ok'}
        transition = None
        if result.get('reason') == 'height_delta' and getattr(entity, 'can_climb_steps', False):
            transition = map_manager.get_step_transition(
                float(from_point[0]),
                float(from_point[1]),
                float(to_point[0]),
                float(to_point[1]),
                max_height_delta_m=float(step_limit if step_limit is not None else getattr(entity, 'max_terrain_step_height_m', 0.05)),
            )
        if transition is not None:
            return {'passable': True, 'requires_step': True, 'transition': transition, 'reason': 'step'}
        return {'passable': False, 'requires_step': False, 'transition': None, 'reason': result.get('reason', 'blocked')}

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
            '占领我方高地增益区，从高地火力压制敌方前哨站',
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
            return self._action_hero_lob_structure(context, enemy_base, '敌方前哨站已倒，英雄转火基地并保持远距离吊射')
        speed = self._meters_to_world_units(1.9, context.map_manager)
        target = self.entity_to_target(enemy_base, context.entity)
        if self._distance_to_point(context.entity, anchor) > self._meters_to_world_units(0.8, context.map_manager):
            return self._set_decision(context, '敌方前哨站已倒，远程英雄转入己方高地增益区吊射敌方基地', target=target, target_point=anchor, speed=speed, preferred_route={'target': anchor}, turret_state='aiming')
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
        }
        return SUCCESS

    def _action_hero_lob_structure(self, context, target_entity, summary):
        preferred_distance = self._meters_to_world_units(7.0, context.map_manager)
        anchor = self._hero_ranged_highground_anchor(context) or self._structure_lob_anchor(context.entity, target_entity, context.data.get('own_base'), preferred_distance)
        speed = self._meters_to_world_units(1.9, context.map_manager)
        target = self.entity_to_target(target_entity, context.entity)
        if self._distance_to_point(context.entity, anchor) > self._meters_to_world_units(0.8, context.map_manager):
            return self._set_decision(context, summary, target=target, target_point=anchor, speed=speed, preferred_route={'target': anchor}, turret_state='aiming')
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
        role_key = self._role_key(target_entity)
        threat_score = {
            'hero': 320.0,
            'sentry': 300.0,
            'infantry': 240.0,
            'engineer': 100.0,
        }.get(role_key, 160.0)
        if target_entity.type == 'outpost':
            threat_score = 150.0
        elif target_entity.type == 'base':
            threat_score = 110.0
        if getattr(source_entity, 'last_damage_source_id', None) == target_entity.id:
            threat_score += 120.0
        target_state = getattr(target_entity, 'target', None)
        if isinstance(target_state, dict) and target_state.get('id') == source_entity.id:
            threat_score += 100.0
        if getattr(target_entity, 'fire_control_state', 'idle') == 'firing':
            threat_score += 70.0
        return threat_score

    def _priority_target_score(self, entity, other, priority_map, rules_engine=None, max_distance=None):
        distance = self._distance(entity, other)
        if max_distance is not None and distance > max_distance:
            return None

        hp_ratio = 1.0
        if float(getattr(other, 'max_health', 0.0)) > 0.0:
            hp_ratio = max(0.0, min(1.0, float(getattr(other, 'health', 0.0)) / float(other.max_health)))
        reference_distance = max_distance if max_distance is not None else self._meters_to_world_units(9.0)
        distance_score = max(0.0, 1.0 - distance / max(reference_distance, 1e-6)) * 180.0
        finish_score = (1.0 - hp_ratio) * 140.0
        if float(getattr(other, 'health', 0.0)) <= max(1.0, float(getattr(other, 'max_health', 0.0)) * 0.28):
            finish_score += 75.0

        visibility_score = 0.0
        if rules_engine is not None and entity.type in {'robot', 'sentry'} and getattr(entity, 'robot_type', '') != '工程':
            assessment = rules_engine.evaluate_auto_aim_target(entity, other, distance=distance, require_fov=False)
            if assessment.get('can_track', False):
                visibility_score += 220.0
                if assessment.get('can_auto_aim', False):
                    visibility_score += 60.0
            elif not assessment.get('line_of_sight', True):
                visibility_score -= 180.0

        score = priority_map.get(other.type, 0) * 220.0
        score += self._priority_target_threat_score(entity, other)
        score += distance_score
        score += finish_score
        score += visibility_score
        if other.type in {'outpost', 'base'} and distance <= self._meters_to_world_units(8.5):
            score += 50.0
        return score

    def _select_priority_target_entity(self, entity, enemies, strategy, rules_engine=None, max_distance=None):
        enemy_base = None
        enemy_outpost_alive = False
        for other in enemies:
            if other.type == 'base':
                enemy_base = other
            elif other.type == 'outpost' and other.is_alive():
                enemy_outpost_alive = True
        base_unlocked = False
        if enemy_base is not None and enemy_base.is_alive() and not enemy_outpost_alive:
            if rules_engine is not None and hasattr(rules_engine, 'is_base_shielded'):
                base_unlocked = not bool(rules_engine.is_base_shielded(enemy_base))
            else:
                base_unlocked = True
        if base_unlocked:
            return enemy_base

        priority_targets = strategy.get('priority_targets', ['sentry', 'robot', 'outpost', 'base'])
        priority_map = {target_type: len(priority_targets) - index for index, target_type in enumerate(priority_targets)}
        visible_combat_target_exists = False
        if rules_engine is not None and entity.type in {'robot', 'sentry'}:
            for other in enemies:
                if other.type not in {'robot', 'sentry'}:
                    continue
                distance = self._distance(entity, other)
                if max_distance is not None and distance > max_distance:
                    continue
                assessment = rules_engine.evaluate_auto_aim_target(entity, other, distance=distance, require_fov=False)
                if assessment.get('can_track', False):
                    visible_combat_target_exists = True
                    break
        best_target = None
        best_score = None
        for other in enemies:
            if other.type == 'base' and rules_engine is not None and hasattr(rules_engine, 'is_base_shielded') and rules_engine.is_base_shielded(other):
                continue
            if visible_combat_target_exists and other.type in {'outpost', 'base'}:
                continue
            score = self._priority_target_score(entity, other, priority_map, rules_engine=rules_engine, max_distance=max_distance)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
                best_target = other
        return best_target

    def select_priority_target(self, entity, enemies, strategy, rules_engine=None, max_distance=None):
        best_target = self._select_priority_target_entity(entity, enemies, strategy, rules_engine=rules_engine, max_distance=max_distance)
        if best_target is None:
            return None
        return self.entity_to_target(best_target, entity)

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
                terrain_bias = {'fly_slope': -42.0, 'first_step': -28.0, 'second_step': -20.0}[facility_type]
                role_bias = 0.0
                role_key = context.data.get('role_key')
                if role_key == 'sentry' and facility_type == 'fly_slope':
                    role_bias -= 18.0
                if role_key == 'infantry' and facility_type in {'first_step', 'second_step'}:
                    role_bias -= 12.0
                if role_key == 'engineer' and facility_type == 'fly_slope':
                    role_bias += 18.0
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
        for radius_mult in (1.0, 1.45, 1.9):
            radius = base_radius * radius_mult
            for offset_deg in (90, -90, 135, -135, 180, 45, -45):
                candidate_heading = heading + math.radians(offset_deg)
                candidate = (
                    float(entity.position['x']) + math.cos(candidate_heading) * radius,
                    float(entity.position['y']) + math.sin(candidate_heading) * radius,
                )
                if not map_manager.is_position_valid_for_radius(candidate[0], candidate[1], collision_radius=float(getattr(entity, 'collision_radius', 0.0))):
                    continue
                if not map_manager.is_segment_valid_for_radius(
                    entity.position['x'],
                    entity.position['y'],
                    candidate[0],
                    candidate[1],
                    collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
                ):
                    return candidate
        return None

    def navigate_towards(self, entity, target_point, speed, map_manager):
        if not self.enable_entity_movement or target_point is None:
            self._clear_navigation_overlay_state(entity)
            return 0.0, 0.0
        target_point = self._resolve_navigation_target(target_point, map_manager, entity=entity)
        region_radius = self._target_region_radius(entity, target_point, map_manager)
        if self._is_target_reached(entity, target_point, map_manager):
            self._clear_navigation_overlay_state(entity)
            entity.ai_navigation_target = target_point
            state = self._entity_path_state.get(entity.id)
            if state is not None:
                state['path'] = self.EMPTY_PATH_PREVIEW
            return 0.0, 0.0
        if map_manager is None:
            self._set_navigation_overlay_state(entity, waypoint=target_point, preview=(target_point,), path_valid=True, region_radius=region_radius, traversal_state='passable')
            return self.move_towards(entity, target_point, self._resolved_navigation_speed(entity, speed, target_point, map_manager))
        next_point = self._next_path_waypoint(entity, target_point, map_manager)
        desired_velocity = self.move_towards(entity, next_point, self._resolved_navigation_speed(entity, speed, next_point, map_manager))
        return self._avoid_static_obstacles(entity, desired_velocity, map_manager)

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
        direct_status = self._movement_segment_status(entity, (entity.position['x'], entity.position['y']), target_point, map_manager)
        if direct_traverse_distance <= direct_traverse_limit and direct_status['passable']:
            raw_path = [
                (float(entity.position['x']), float(entity.position['y'])),
                (float(target_point[0]), float(target_point[1])),
            ]
            traversal_state = 'passable'
            if direct_status['requires_step'] and direct_status['transition'] is not None:
                transition = direct_status['transition']
                approach_point = transition.get('approach_point') or target_point
                climb_points = tuple(transition.get('climb_points', ())) or (transition.get('top_point') or target_point,)
                raw_path = [
                    (float(entity.position['x']), float(entity.position['y'])),
                    (float(approach_point[0]), float(approach_point[1])),
                ]
                for climb_point in climb_points:
                    raw_path.append((float(climb_point[0]), float(climb_point[1])))
                raw_path.extend([
                    (float(target_point[0]), float(target_point[1])),
                ])
                traversal_state = 'step-passable'
            segmented_path = self._segment_path_points(raw_path, map_manager)
            direct_index = 1 if len(segmented_path) > 1 else 0
            direct_waypoint = segmented_path[direct_index] if segmented_path else (float(target_point[0]), float(target_point[1]))
            self._entity_path_state[entity.id] = {
                'path': segmented_path,
                'index': direct_index,
                'last_waypoint': direct_waypoint,
                'planned_at': self._last_ai_update_time.get(entity.id, 0.0),
                'last_speed': math.hypot(float(getattr(entity, 'velocity', {}).get('vx', 0.0)), float(getattr(entity, 'velocity', {}).get('vy', 0.0))),
                'last_wp_distance': self._distance_to_point(entity, direct_waypoint),
            }
            preview = self._build_path_preview(entity, segmented_path, direct_index)
            self._set_navigation_overlay_state(entity, waypoint=direct_waypoint, preview=preview, path_valid=True, region_radius=self._target_region_radius(entity, target_point, map_manager), traversal_state=traversal_state)
            return direct_waypoint

        raster_version = getattr(map_manager, 'raster_version', 0)
        step_limit = float(getattr(entity, 'max_terrain_step_height_m', 0.05))
        traversal_profile = self._traversal_profile(entity)
        start_cell = self._path_cell(entity.position, map_manager)
        goal_cell = self._path_cell({'x': target_point[0], 'y': target_point[1]}, map_manager)
        state = self._entity_path_state.get(entity.id)
        state_view = state or {}
        current_time = self._last_ai_update_time.get(entity.id, 0.0)
        current_speed = math.hypot(float(getattr(entity, 'velocity', {}).get('vx', 0.0)), float(getattr(entity, 'velocity', {}).get('vy', 0.0)))
        force_fresh_replan = False
        need_replan = state is None
        if not need_replan:
            need_replan = (
                state_view.get('goal_cell') != goal_cell
                or state_view.get('raster_version') != raster_version
                or state_view.get('step_limit') != round(step_limit, 3)
                or state_view.get('can_climb_steps') != bool(traversal_profile.get('can_climb_steps', False))
                or state_view.get('collision_radius') != round(float(traversal_profile.get('collision_radius', 0.0)), 2)
                or not state_view.get('path')
            )
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
            if current_time - planned_at >= max(0.18, self._path_replan_interval * 1.5):
                active_path = state_view.get('path', ())
                active_index = self._path_waypoint_index(active_path, state_view.get('index', 1)) if active_path else 0
                path_deviation = self._path_deviation_distance(entity, state_view.get('path', ()), active_index)
                if path_deviation > max(24.0, map_manager.terrain_grid_cell_size * 2.8):
                    need_replan = True
                    force_fresh_replan = True
        if not need_replan:
            last_speed = float(state_view.get('last_speed', current_speed))
            speed_delta = abs(current_speed - last_speed)
            if speed_delta >= max(24.0, map_manager.terrain_grid_cell_size * 1.8):
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
        if not need_replan:
            active_path = state.get('path', []) if state else []
            active_index = self._path_waypoint_index(active_path, state.get('index', 1)) if active_path else 0
            if active_path:
                probe_distance = self._distance_to_point(entity, active_path[active_index])
                if probe_distance < float(stuck.get('best_distance', float('inf'))) - max(4.0, map_manager.terrain_grid_cell_size * 0.45):
                    stuck['best_distance'] = probe_distance
                    stuck['last_progress_time'] = current_time
                elif current_time - float(stuck.get('last_progress_time', current_time)) >= 0.8:
                    need_replan = True
                    force_fresh_replan = True
                    stuck['best_distance'] = probe_distance
                    stuck['last_progress_time'] = current_time
            stuck['last_check_time'] = current_time

        if need_replan:
            cache_key = (start_cell, goal_cell, raster_version, round(step_limit, 3), traversal_profile['step_climb_duration_sec'], round(traversal_profile.get('collision_radius', 0.0), 2))
            path = None if force_fresh_replan else self._path_cache.get(cache_key)
            if path is None:
                if self._can_replan_path():
                    path = self._search_navigation_path(entity, target_point, map_manager, step_limit, traversal_profile)
                    if len(self._path_cache) > 64:
                        self._path_cache.clear()
                    self._path_cache[cache_key] = path
                else:
                    path = state_view.get('path', self.EMPTY_PATH_PREVIEW)
            state = {
                'start_cell': start_cell,
                'goal_cell': goal_cell,
                'raster_version': raster_version,
                'step_limit': round(step_limit, 3),
                'can_climb_steps': bool(traversal_profile.get('can_climb_steps', False)),
                'collision_radius': round(float(traversal_profile.get('collision_radius', 0.0)), 2),
                'path': tuple(path or self.EMPTY_PATH_PREVIEW),
                'index': self._path_waypoint_index(tuple(path or self.EMPTY_PATH_PREVIEW), 1),
                'planned_at': current_time,
                'last_speed': current_speed,
                'last_wp_distance': 0.0,
            }
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
            if not self._can_replan_path():
                preview = ((float(entity.position['x']), float(entity.position['y'])), (float(path[index][0]), float(path[index][1])), (float(target_point[0]), float(target_point[1])))
                self._set_navigation_overlay_state(entity, waypoint=path[index], preview=preview, path_valid=False, traversal_state='blocked')
                return path[index]
            refreshed_path = self._search_navigation_path(entity, target_point, map_manager, step_limit, traversal_profile)
            state['path'] = tuple(refreshed_path or self.EMPTY_PATH_PREVIEW)
            state['index'] = self._path_waypoint_index(state['path'], 1)
            state['planned_at'] = current_time
            if not state['path']:
                self._clear_navigation_overlay_state(entity)
                return float(entity.position['x']), float(entity.position['y'])
            path = state['path']
            index = self._path_waypoint_index(path, state.get('index', 1))
            state['last_waypoint'] = path[index]
            state['last_wp_distance'] = self._distance_to_point(entity, path[index])
        stuck = self._stuck_state.get(entity.id, {})
        if current_time - float(stuck.get('last_progress_time', current_time)) >= 0.8:
            escape_waypoint = self._build_escape_waypoint(entity, path[index], map_manager)
            if escape_waypoint is not None:
                state['escape_waypoint'] = escape_waypoint
                state['escape_until'] = current_time + 0.55
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

    def _search_navigation_path(self, entity, target_point, map_manager, step_limit, traversal_profile):
        start_time = time.perf_counter()
        budget_scale = self._pathfinder_distance_scale(entity, target_point, map_manager)
        total_budget_sec = self._pathfinder_total_budget_sec * budget_scale
        deadline = start_time + total_budget_sec if total_budget_sec > 0 else None
        base_steps = [max(map_manager.terrain_grid_cell_size * 4, 18)]
        if self._pathfinder_use_dual_resolution:
            base_steps.append(max(map_manager.terrain_grid_cell_size * 2, 12))
        candidate_points = self._target_region_candidate_points(entity, target_point, map_manager)
        if self._pathfinder_try_resolved_target:
            resolved_target = map_manager.find_nearest_passable_point(
                target_point,
                collision_radius=float(traversal_profile.get('collision_radius', 0.0)),
                search_radius=max(72, map_manager.terrain_grid_cell_size * 10),
                step=max(4, map_manager.terrain_grid_cell_size),
            )
            if resolved_target is not None and resolved_target != target_point:
                candidate_points.append(resolved_target)
        search_plans = [
            {
                'steps': tuple(base_steps),
                'max_iterations': max(self._pathfinder_max_iterations, int(self._pathfinder_max_iterations * budget_scale)),
                'max_runtime_sec': self._pathfinder_time_budget_sec * budget_scale,
            },
            {
                'steps': tuple(sorted({max(map_manager.terrain_grid_cell_size, 8), max(map_manager.terrain_grid_cell_size * 2, 12), *base_steps})),
                'max_iterations': max(1200, int(self._pathfinder_max_iterations * 2 * budget_scale)),
                'max_runtime_sec': max(0.006, self._pathfinder_time_budget_sec * 1.6 * budget_scale),
            },
        ]
        resolved_candidates = []
        seen_candidates = set()
        for candidate in candidate_points:
            resolved_candidate = self._resolve_navigation_target(candidate, map_manager, entity=entity)
            if resolved_candidate is None:
                continue
            key = (round(float(resolved_candidate[0]), 2), round(float(resolved_candidate[1]), 2))
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            resolved_candidates.append((float(resolved_candidate[0]), float(resolved_candidate[1])))
        resolved_candidates.sort(key=lambda point: math.hypot(point[0] - float(entity.position['x']), point[1] - float(entity.position['y'])))
        max_candidates = max(2, int(self._ai_config.get('pathfinder_max_candidates', 4)))
        resolved_candidates = resolved_candidates[:max_candidates]
        attempts = 0
        for search_plan in search_plans:
            if deadline is not None and time.perf_counter() >= deadline:
                break
            for candidate in resolved_candidates:
                for grid_step in search_plan['steps']:
                    if attempts >= self._pathfinder_max_attempts:
                        return self.EMPTY_PATH_PREVIEW
                    if deadline is not None:
                        remaining_budget = deadline - time.perf_counter()
                        if remaining_budget <= 0:
                            return self.EMPTY_PATH_PREVIEW
                        runtime_limit = min(float(search_plan['max_runtime_sec']), remaining_budget)
                    else:
                        runtime_limit = float(search_plan['max_runtime_sec'])
                    if runtime_limit <= 0.0002:
                        return self.EMPTY_PATH_PREVIEW
                    attempts += 1
                    path = map_manager.find_path(
                        (entity.position['x'], entity.position['y']),
                        candidate,
                        max_height_delta_m=step_limit,
                        grid_step=grid_step,
                        traversal_profile=traversal_profile,
                        max_iterations=search_plan['max_iterations'],
                        max_runtime_sec=runtime_limit,
                    )
                    if self._is_path_traversable(entity, path, map_manager):
                        expanded_path = self._expand_path_with_step_transitions(entity, path, map_manager)
                        return tuple(self._segment_path_points(expanded_path, map_manager))
        return self.EMPTY_PATH_PREVIEW

    def _expand_path_with_step_transitions(self, entity, path, map_manager):
        if not path:
            return self.EMPTY_PATH_PREVIEW
        expanded = [tuple(path[0])]
        previous_point = (float(path[0][0]), float(path[0][1]))
        for point in path[1:]:
            current_point = (float(point[0]), float(point[1]))
            status = self._movement_segment_status(entity, previous_point, current_point, map_manager)
            if status['requires_step'] and status['transition'] is not None:
                transition = status['transition']
                approach_point = transition.get('approach_point')
                climb_points = tuple(transition.get('climb_points', ())) or (transition.get('top_point'),)
                for extra_point in (approach_point, *climb_points):
                    if extra_point is None:
                        continue
                    normalized = (float(extra_point[0]), float(extra_point[1]))
                    if expanded[-1] != normalized:
                        expanded.append(normalized)
            if expanded[-1] != current_point:
                expanded.append(current_point)
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
        return bool(status['passable'])

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
            sum_x = 0.0
            sum_y = 0.0
            valid_count = 0
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                sum_x += float(point[0])
                sum_y += float(point[1])
                valid_count += 1
            if valid_count > 0:
                return int(round(sum_x / valid_count)), int(round(sum_y / valid_count))
        return int((facility['x1'] + facility['x2']) / 2), int((facility['y1'] + facility['y2']) / 2)