#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import os
import sys
import json
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

from pygame_compat import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from control.ai_controller import AIController
from core.config_manager import ConfigManager
from entities.entity import Entity
from map.map_manager import MapManager


class BehaviorEditorEngine:
    ROLE_ORDER = ('sentry', 'infantry', 'hero', 'engineer', 'common')
    MAX_STRATEGY_STAGES = 4
    ROLE_PREVIEW_ENTITY_IDS = {
        'hero': 'robot_1',
        'engineer': 'robot_2',
        'infantry': 'robot_3',
        'sentry': 'robot_7',
        'common': 'robot_3',
    }
    COLLISION_PROFILE_DEFAULTS = {
        'hero': {'collision_radius': 20.0, 'body_length_m': 0.65, 'body_width_m': 0.55, 'body_height_m': 0.20, 'body_clearance_m': 0.10, 'wheel_radius_m': 0.08, 'wheel_style': 'mecanum'},
        'engineer': {'collision_radius': 21.0, 'body_length_m': 0.55, 'body_width_m': 0.50, 'body_height_m': 0.20, 'body_clearance_m': 0.10, 'wheel_radius_m': 0.08, 'wheel_style': 'mecanum'},
        'infantry': {'collision_radius': 18.0, 'body_length_m': 0.50, 'body_width_m': 0.45, 'body_height_m': 0.20, 'body_clearance_m': 0.20, 'wheel_radius_m': 0.06, 'wheel_style': 'legged'},
        'sentry': {'collision_radius': 24.0, 'body_length_m': 0.55, 'body_width_m': 0.50, 'body_height_m': 0.20, 'body_clearance_m': 0.10, 'wheel_radius_m': 0.08, 'wheel_style': 'mecanum'},
    }
    COLLISION_FIELD_SPECS = (
        {'key': 'collision_radius', 'label': '碰撞半径（世界单位）', 'min': 8.0, 'max': 48.0},
        {'key': 'body_length_m', 'label': '碰撞箱长度（米）', 'min': 0.20, 'max': 1.40},
        {'key': 'body_width_m', 'label': '碰撞箱宽度（米）', 'min': 0.20, 'max': 1.20},
        {'key': 'body_height_m', 'label': '碰撞箱高度（米）', 'min': 0.05, 'max': 0.80},
        {'key': 'body_clearance_m', 'label': '离地间隙（米）', 'min': 0.0, 'max': 0.40},
        {'key': 'wheel_radius_m', 'label': '轮半径（米）', 'min': 0.02, 'max': 0.25},
    )
    REGION_MODE_LABELS = {
        'enter_then_execute': '先进入区域再执行',
        'strict_inside': '仅在区域内触发',
    }
    STRATEGY_TASK_TYPE_ORDER = ('default', 'terrain_traversal', 'assault', 'field_interaction', 'defense', 'area_patrol')
    STRATEGY_TASK_TYPE_LABELS = {
        'default': '默认行为树',
        'terrain_traversal': '地形跨越类',
        'assault': '进攻类',
        'field_interaction': '场地交互类',
        'defense': '防守类',
        'area_patrol': '区域巡航类',
    }
    DESTINATION_MODE_ORDER = ('region', 'none')
    DESTINATION_MODE_LABELS = {
        'region': '到达选定区域',
        'none': '不设置目标地点',
    }
    DESTINATION_REFERENCE_ORDER = (
        'enemy_any_unit', 'enemy_hero', 'enemy_infantry', 'enemy_engineer', 'enemy_sentry',
        'enemy_any_facility', 'enemy_outpost', 'enemy_base',
        'ally_hero', 'ally_infantry', 'ally_engineer', 'ally_sentry',
        'own_supply', 'own_base', 'own_outpost',
        'enemy_outpost_anchor', 'enemy_base_anchor', 'map_center',
    )
    ASSAULT_REFERENCE_ORDER = (
        'enemy_any_unit', 'enemy_hero', 'enemy_infantry', 'enemy_engineer', 'enemy_sentry',
        'enemy_any_facility', 'enemy_outpost', 'enemy_base',
    )
    ASSAULT_FOLLOW_PRIORITY_ORDER = ('target_first', 'destination_first')
    ASSAULT_FOLLOW_PRIORITY_LABELS = {
        'target_first': '目标优先',
        'destination_first': '引用地点优先',
    }
    FIELD_INTERACTION_ORDER = ('own_supply', 'mining_area', 'energy_mechanism')
    FIELD_INTERACTION_LABELS = {
        'own_supply': '补给',
        'mining_area': '取矿',
        'energy_mechanism': '激活能量机关',
    }
    DEFENSE_REFERENCE_ORDER = ('high_threat_enemy', 'defend_base')
    DEFENSE_REFERENCE_LABELS = {
        'high_threat_enemy': '打击高威胁敌人',
        'defend_base': '回防基地',
    }
    STRATEGY_REFERENCE_LABELS = {
        'enemy_any_unit': '敌方任意单位',
        'enemy_hero': '敌方英雄',
        'enemy_infantry': '敌方步兵',
        'enemy_engineer': '敌方工程',
        'enemy_sentry': '敌方哨兵',
        'enemy_any_facility': '敌方任意设施',
        'enemy_outpost': '敌方前哨站',
        'enemy_base': '敌方基地',
        'ally_hero': '己方英雄',
        'ally_infantry': '己方步兵',
        'ally_engineer': '己方工程',
        'ally_sentry': '己方哨兵',
        'own_supply': '己方补给区',
        'own_base': '己方基地',
        'own_outpost': '己方前哨站',
        'enemy_outpost_anchor': '敌前哨锚点',
        'enemy_base_anchor': '敌基地锚点',
        'map_center': '地图中心',
    }
    STRATEGY_TERRAIN_TARGET_DEFS = tuple(
        {'id': f'node_{index}', 'label': f'跨越节点 {index}'} for index in range(1, MAX_STRATEGY_STAGES + 1)
    )

    def __init__(self, config_path='config.json', settings_path=None):
        self.config_path = config_path
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config(config_path, settings_path)
        self.config['_config_path'] = config_path
        self.settings_path = self.config.get('_settings_path', self.config_manager.default_settings_path(config_path))
        self.config['_settings_path'] = self.settings_path
        self.map_manager = MapManager(self.config)
        self.map_manager.load_map()
        self.ai_controller = AIController(self.config)
        self.logs = []
        self.max_logs = 8
        self.selected_role_index = 0
        self.selected_decision_index = {role_key: 0 for role_key in self.ROLE_ORDER}
        default_preset = str(self.config.get('ai', {}).get('behavior_preset', '') or '').strip() or 'latest_behavior'
        self.preset_name = default_preset[:-5] if default_preset.lower().endswith('.json') else default_preset
        self.behavior_payload = self._load_behavior_payload(self.preset_name)
        self.appearance_preset_path = self._resolve_appearance_preset_path()
        self.appearance_payload = self._load_appearance_payload()
        self.preview_world = []
        self.preview_plan = None
        self.preview_feedback = []
        self._reset_preview_world()

    def add_log(self, message):
        self.logs.append(str(message))
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def _empty_payload(self, preset_name):
        return {
            'version': 1,
            'name': str(preset_name or 'latest_behavior'),
            'saved_at': datetime.now().isoformat(timespec='seconds'),
            'roles': {},
        }

    def _load_behavior_payload(self, preset_name):
        payload = self.config_manager.load_behavior_preset(preset_name, self.config_path)
        if isinstance(payload, dict) and 'roles' in payload:
            payload.setdefault('version', 1)
            payload.setdefault('name', str(preset_name))
            payload.setdefault('roles', {})
            roles = payload.get('roles', {})
            if isinstance(roles, dict):
                for role_entry in roles.values():
                    if not isinstance(role_entry, dict):
                        continue
                    decisions = role_entry.get('decisions', {})
                    if not isinstance(decisions, dict):
                        continue
                    for decision_id, override in list(decisions.items()):
                        decisions[decision_id] = self._normalize_override(override)
            return payload
        return self._empty_payload(preset_name)

    def _resolve_appearance_preset_path(self):
        configured_path = str(self.config.get('entities', {}).get('appearance_preset_path', os.path.join('appearance_presets', 'latest_appearance.json')))
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.join(os.path.dirname(os.path.abspath(self.config_path)), configured_path)

    def _load_appearance_payload(self):
        if not os.path.exists(self.appearance_preset_path):
            return {'profiles': {}}
        try:
            with open(self.appearance_preset_path, 'r', encoding='utf-8') as file:
                payload = json.load(file)
        except Exception:
            return {'profiles': {}}
        if not isinstance(payload, dict):
            return {'profiles': {}}
        if not isinstance(payload.get('profiles'), dict):
            payload['profiles'] = {}
        return payload

    def _save_appearance_payload(self):
        directory = os.path.dirname(self.appearance_preset_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.appearance_preset_path, 'w', encoding='utf-8') as file:
            json.dump(self.appearance_payload, file, ensure_ascii=False, indent=2)

    def _collision_role_key(self, role_key=None):
        role = str(role_key or self.selected_role_key() or 'hero')
        return role if role in self.COLLISION_PROFILE_DEFAULTS else None

    def current_collision_profile(self, role_key=None):
        role = self._collision_role_key(role_key)
        if role is None:
            return None
        merged = dict(self.COLLISION_PROFILE_DEFAULTS.get(role, {}))
        profiles = self.appearance_payload.get('profiles', {}) if isinstance(self.appearance_payload, dict) else {}
        override = profiles.get(role, {}) if isinstance(profiles, dict) else {}
        if isinstance(override, dict):
            merged.update(override)
        return merged

    def _sync_collision_profile_fields(self, role_key, profile):
        wheel_style = str(profile.get('wheel_style', self.COLLISION_PROFILE_DEFAULTS.get(role_key, {}).get('wheel_style', 'mecanum')) or 'mecanum')
        body_length_m = float(profile.get('body_length_m', self.COLLISION_PROFILE_DEFAULTS[role_key]['body_length_m']))
        body_width_m = float(profile.get('body_width_m', self.COLLISION_PROFILE_DEFAULTS[role_key]['body_width_m']))
        wheel_radius_m = float(profile.get('wheel_radius_m', self.COLLISION_PROFILE_DEFAULTS[role_key]['wheel_radius_m']))
        if wheel_style == 'legged':
            wheel_y = round(body_width_m * 0.5 + wheel_radius_m * 0.55, 3)
            profile['custom_wheel_positions_m'] = [[0.0, -wheel_y], [0.0, wheel_y]]
        else:
            wheel_x = round(body_length_m * 0.39, 3)
            wheel_y = round(body_width_m * 0.5 + wheel_radius_m * 0.55, 3)
            profile['custom_wheel_positions_m'] = [[-wheel_x, -wheel_y], [wheel_x, -wheel_y], [-wheel_x, wheel_y], [wheel_x, wheel_y]]
        profile.pop('gimbal_height_m', None)

    def set_collision_field(self, field_name, value, role_key=None):
        role = self._collision_role_key(role_key)
        if role is None:
            return False
        profiles = self.appearance_payload.setdefault('profiles', {})
        profile = profiles.get(role)
        if not isinstance(profile, dict):
            profile = dict(self.COLLISION_PROFILE_DEFAULTS.get(role, {}))
            profiles[role] = profile
        spec = next((item for item in self.COLLISION_FIELD_SPECS if item['key'] == field_name), None)
        if spec is None:
            return False
        profile[field_name] = max(float(spec['min']), min(float(spec['max']), float(value)))
        self._sync_collision_profile_fields(role, profile)
        self._save_appearance_payload()
        self._reset_preview_world()
        self.add_log(f'已更新{self.role_label(role)}碰撞箱参数: {spec["label"]}')
        return True

    def role_keys(self):
        return tuple(role_key for role_key in self.ROLE_ORDER if self.ai_controller.get_available_decision_plugins(role_key))

    def role_label(self, role_key):
        return {'sentry': '哨兵', 'infantry': '步兵', 'hero': '英雄', 'engineer': '工程', 'common': '通用'}.get(role_key, role_key)

    def selected_role_key(self):
        role_keys = self.role_keys()
        if not role_keys:
            return 'hero'
        self.selected_role_index = max(0, min(self.selected_role_index, len(role_keys) - 1))
        return role_keys[self.selected_role_index]

    def role_specs(self, role_key=None):
        role = role_key or self.selected_role_key()
        if role == self.ai_controller.COMMON_ROLE_KEY:
            specs = []
            for binding in self.role_available_plugins(role):
                action = binding.get('action') if callable(binding.get('action')) else None
                if action is None:
                    continue
                specs.append({
                    'id': str(binding.get('id', '')),
                    'label': str(binding.get('label', binding.get('id', ''))),
                    'action': (lambda ctx, plugin_action=action, plugin_binding=dict(binding), plugin_role=role:
                        plugin_action(self.ai_controller, ctx, plugin_role, plugin_binding)),
                    'fallback': bool(binding.get('fallback', True)),
                    'description': str(binding.get('description', '')),
                    'editable_targets': tuple(binding.get('editable_targets', ())),
                    'default_destination_types': tuple(binding.get('default_destination_types', ())),
                })
            return specs
        return list(self.ai_controller.role_decision_specs.get(role, ()))

    def selected_spec(self):
        role_key = self.selected_role_key()
        specs = self.role_specs(role_key)
        if not specs:
            return None
        selected_index = self.selected_decision_index.get(role_key, 0)
        selected_index = max(0, min(selected_index, len(specs) - 1))
        self.selected_decision_index[role_key] = selected_index
        return specs[selected_index]

    def _role_entry(self, role_key, create=False):
        roles = self.behavior_payload.setdefault('roles', {})
        if role_key not in roles and create:
            roles[role_key] = {'decisions': {}, 'decision_order': None}
        return roles.get(role_key)

    def current_override(self, create=False):
        spec = self.selected_spec()
        if spec is None:
            return None
        role_entry = self._role_entry(self.selected_role_key(), create=create)
        if role_entry is None:
            return None
        decisions = role_entry.setdefault('decisions', {})
        canonical_id = self.ai_controller._canonical_decision_id(spec['id'])
        if canonical_id not in decisions:
            for alias_id in self.ai_controller._decision_alias_ids(canonical_id):
                if alias_id in decisions:
                    return decisions.get(alias_id)
        if canonical_id not in decisions and create:
            decisions[canonical_id] = {}
        return decisions.get(canonical_id)

    def _normalize_region_list(self, regions):
        if not isinstance(regions, list):
            return []
        return [deepcopy(region) for region in regions if isinstance(region, dict)]

    def _normalize_team_region_map(self, team_regions):
        if not isinstance(team_regions, dict):
            return {}
        normalized = {}
        for team in ('red', 'blue'):
            regions = self._normalize_region_list(team_regions.get(team, []))
            if regions:
                normalized[team] = regions
        return normalized

    def _normalize_point_target_map(self, point_targets):
        specs = self._normalize_point_target_specs(point_targets)
        return {
            key: [float(spec['x']), float(spec['y'])]
            for key, spec in specs.items()
        }

    def _normalize_point_target_specs(self, point_targets):
        if not isinstance(point_targets, dict):
            return {}
        normalized = {}
        aliases = {'primary': 'node_1', 'secondary': 'node_2', 'first': 'node_1', 'second': 'node_2'}
        for key, value in point_targets.items():
            if not isinstance(key, str):
                continue
            try:
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
                point_x_value = float(str(point_x))
                point_y_value = float(str(point_y))
                spec = {
                    'x': round(point_x_value, 1),
                    'y': round(point_y_value, 1),
                }
                if radius not in {None, ''}:
                    radius_value = float(str(radius))
                    spec['radius'] = round(max(6.0, radius_value), 1)
                normalized[aliases.get(key, key)] = spec
            except (TypeError, ValueError):
                continue
        return normalized

    def _normalize_team_point_target_map(self, team_targets):
        if not isinstance(team_targets, dict):
            return {}
        normalized = {}
        for team in ('red', 'blue'):
            targets = self._normalize_point_target_map(team_targets.get(team, {}))
            if targets:
                normalized[team] = targets
        return normalized

    def _normalize_team_point_target_specs(self, team_targets):
        if not isinstance(team_targets, dict):
            return {}
        normalized = {}
        for team in ('red', 'blue'):
            targets = self._normalize_point_target_specs(team_targets.get(team, {}))
            if targets:
                normalized[team] = targets
        return normalized

    def _normalize_strategy_stage(self, strategy):
        if not isinstance(strategy, dict):
            return {}
        normalized = {}
        task_type = str(strategy.get('task_type', 'default') or 'default').strip()
        if task_type not in self.STRATEGY_TASK_TYPE_ORDER:
            task_type = 'default'
        if task_type != 'default':
            normalized['task_type'] = task_type
        destination_mode = str(strategy.get('destination_mode', 'region') or 'region').strip()
        if destination_mode not in self.DESTINATION_MODE_ORDER:
            destination_mode = 'region'
        if destination_mode != 'region':
            normalized['destination_mode'] = destination_mode
        assault_ref = str(strategy.get('assault_ref', 'enemy_any_unit') or 'enemy_any_unit').strip()
        if assault_ref and assault_ref != 'enemy_any_unit':
            normalized['assault_ref'] = assault_ref
        assault_follow_priority = str(strategy.get('assault_follow_priority', 'target_first') or 'target_first').strip()
        if assault_follow_priority in self.ASSAULT_FOLLOW_PRIORITY_ORDER and assault_follow_priority != 'target_first':
            normalized['assault_follow_priority'] = assault_follow_priority
        interaction_ref = str(strategy.get('interaction_ref', 'own_supply') or 'own_supply').strip()
        if interaction_ref in self.FIELD_INTERACTION_ORDER and interaction_ref != 'own_supply':
            normalized['interaction_ref'] = interaction_ref
        defense_ref = str(strategy.get('defense_ref', 'high_threat_enemy') or 'high_threat_enemy').strip()
        if defense_ref in self.DEFENSE_REFERENCE_ORDER and defense_ref != 'high_threat_enemy':
            normalized['defense_ref'] = defense_ref
        engage_distance = strategy.get('engage_distance_m', None)
        if engage_distance not in {None, ''}:
            try:
                engage_value = max(0.5, float(str(engage_distance)))
            except (TypeError, ValueError):
                engage_value = None
            if engage_value is not None and abs(engage_value - 8.0) > 1e-6:
                normalized['engage_distance_m'] = round(engage_value, 2)
        return normalized

    def _normalize_strategy(self, strategy):
        if not isinstance(strategy, dict):
            return {}
        stages = []
        raw_stages = strategy.get('stages', None)
        if isinstance(raw_stages, list):
            for stage in raw_stages:
                normalized_stage = self._normalize_strategy_stage(stage)
                if normalized_stage:
                    stages.append(normalized_stage)
        else:
            normalized_stage = self._normalize_strategy_stage(strategy)
            if normalized_stage:
                stages.append(normalized_stage)
        return {'stages': stages} if stages else {}

    def _override_is_default(self, normalized):
        return (
            not normalized.get('label')
            and not normalized.get('brief')
            and not normalized.get('trigger_note')
            and not normalized.get('logic_note')
            and not normalized.get('function_note')
            and 'enabled' not in normalized
            and not normalized.get('condition_expr')
            and not normalized.get('time_window')
            and not normalized.get('behavior_regions')
            and not normalized.get('behavior_regions_by_team')
            and not normalized.get('strategy')
            and normalized.get('region_mode', 'enter_then_execute') == 'enter_then_execute'
        )

    def _normalize_override(self, override):
        override = deepcopy(override or {})
        for field_name in ('brief', 'trigger_note', 'logic_note', 'function_note'):
            text = str(override.get(field_name, '') or '').strip()
            if text:
                override[field_name] = text
            else:
                if field_name in override:
                    override.pop(field_name)
        if 'time_window' in override and not isinstance(override['time_window'], dict):
            override.pop('time_window', None)
        behavior_regions = self._normalize_region_list(override.get('behavior_regions', []))
        if not behavior_regions:
            legacy_behavior_regions = []
            for region in self._normalize_region_list(override.get('task_regions', [])) + self._normalize_region_list(override.get('destination_regions', [])):
                if region not in legacy_behavior_regions:
                    legacy_behavior_regions.append(region)
            behavior_regions = legacy_behavior_regions
        if behavior_regions:
            override['behavior_regions'] = behavior_regions
        else:
            override.pop('behavior_regions', None)
        behavior_regions_by_team = self._normalize_team_region_map(override.get('behavior_regions_by_team', {}))
        if not behavior_regions_by_team:
            merged_by_team = {}
            for team in ('red', 'blue'):
                team_regions = []
                for region in self._normalize_region_list((override.get('task_regions_by_team', {}) or {}).get(team, [])) + self._normalize_region_list((override.get('destination_regions_by_team', {}) or {}).get(team, [])):
                    if region not in team_regions:
                        team_regions.append(region)
                if team_regions:
                    merged_by_team[team] = team_regions
            behavior_regions_by_team = merged_by_team
        if behavior_regions_by_team:
            override['behavior_regions_by_team'] = behavior_regions_by_team
        else:
            override.pop('behavior_regions_by_team', None)
        override.pop('task_regions', None)
        override.pop('destination_regions', None)
        override.pop('task_regions_by_team', None)
        override.pop('destination_regions_by_team', None)
        override.pop('point_targets', None)
        override.pop('point_targets_by_team', None)
        strategy = self._normalize_strategy(override.get('strategy', {}))
        if strategy:
            override['strategy'] = strategy
        else:
            override.pop('strategy', None)
        override.setdefault('region_mode', 'enter_then_execute')
        return override

    def _persist_live_changes(self, log_message=None):
        payload = self._pruned_payload()
        payload['name'] = self.preset_name
        self.behavior_payload = payload
        self.config_manager.save_behavior_preset(self.preset_name, payload, self.config_path)
        self.config.setdefault('ai', {})['behavior_preset'] = self.preset_name
        self.config_manager.config = self.config
        self.config_manager.save_settings(self.settings_path)
        self.ai_controller.config = self.config
        self.ai_controller._refresh_behavior_runtime_overrides(force=True)
        self._reset_preview_world()
        if log_message:
            self.add_log(log_message)

    def _reset_preview_world(self):
        self.preview_world = self._build_preview_world()
        self.preview_plan = None
        self.preview_feedback = []

    def _preview_robot_id_for_role(self, role_key):
        return self.ROLE_PREVIEW_ENTITY_IDS.get(role_key, 'robot_3')

    def _build_preview_world(self):
        entities = []
        initial_positions = deepcopy(self.config.get('entities', {}).get('initial_positions', {}))
        robot_types = deepcopy(self.config.get('entities', {}).get('robot_types', {}))
        for team in ('red', 'blue'):
            for robot_id, pose in (initial_positions.get(team, {}) or {}).items():
                robot_type = robot_types.get(robot_id, '步兵')
                entity_type = 'sentry' if robot_id == 'robot_7' else 'robot'
                entity = Entity(
                    f'preview_{team}_{robot_id}',
                    entity_type,
                    team,
                    {'x': float(pose.get('x', 0.0)), 'y': float(pose.get('y', 0.0)), 'z': 0.0},
                    angle=int(float(pose.get('angle', 0.0))),
                    robot_type=robot_type,
                )
                entity.display_name = f'{team}_{robot_id}'
                entity.max_health = 400 if robot_type == '英雄' else (250 if robot_type == '工程' else 300)
                entity.health = entity.max_health
                entity.max_heat = 260 if entity_type == 'sentry' else 120
                entity.heat = 0.0
                entity.ammo = 200
                entity.ammo_type = '17mm'
                entity.front_gun_locked = False
                entity.hero_weapon_mode = 'ranged_priority' if robot_type == '英雄' else getattr(entity, 'hero_weapon_mode', 'ranged_priority')
                entities.append(entity)
        for facility_type in ('base', 'outpost'):
            for facility in self.map_manager.get_facility_regions(facility_type):
                center = self.ai_controller.facility_center(facility)
                entity = Entity(
                    f'preview_{facility.get("id")}',
                    facility_type,
                    facility.get('team', 'neutral'),
                    {'x': float(center[0]), 'y': float(center[1]), 'z': 0.0},
                    angle=0,
                    robot_type=None,
                )
                entity.max_health = 1500 if facility_type == 'base' else 600
                entity.health = entity.max_health
                entity.movable = False
                entity.collidable = False
                entities.append(entity)
        return entities

    def preview_world_entities(self):
        return list(self.preview_world)

    def _preview_actor(self, team, role_key, entities):
        target_robot_id = self._preview_robot_id_for_role(role_key)
        target_id = f'preview_{team}_{target_robot_id}'
        for entity in entities:
            if entity.id == target_id:
                return entity
        return None

    def _fallback_preview_target(self, team, role_key, decision_id, actor):
        regions = self.ai_controller.get_decision_destination_preview_regions(role_key, decision_id, self.map_manager, team=team)
        best_point = None
        best_distance = None
        for region in regions:
            region_team = region.get('team')
            if region_team not in {None, 'neutral', team}:
                continue
            center = self.ai_controller._behavior_region_center(region)
            if center is None:
                continue
            distance = math.hypot(float(center[0]) - float(actor.position['x']), float(center[1]) - float(actor.position['y']))
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_point = (float(center[0]), float(center[1]))
        return best_point

    def build_decision_preview(self):
        spec = self.selected_spec()
        role_key = self.selected_role_key()
        if spec is None:
            return None
        override_brief = str((self.current_override(create=False) or {}).get('brief', '') or '').strip()
        self.preview_world = self._build_preview_world()
        plan = {
            'role_key': role_key,
            'decision_id': spec['id'],
            'label': spec['label'],
            'teams': {},
        }
        feedback_lines = []
        for team in ('red', 'blue'):
            actor = self._preview_actor(team, role_key, self.preview_world)
            if actor is None:
                continue
            context = self.ai_controller._build_context(actor, self.preview_world, self.map_manager, None, 35.0, 420.0)
            action_error = None
            try:
                result = spec['action'](context)
                decision = context.data.get('decision')
            except Exception as exc:
                result = 'preview_error'
                decision = None
                action_error = f'{type(exc).__name__}: {exc}'
            fallback_target = self._fallback_preview_target(team, role_key, spec['id'], actor)
            preview_script = self.ai_controller.build_override_preview_script(context, role_key, spec['id'], spec['label'])
            if decision is None:
                decision = {
                    'summary': '当前预演态势下未生成动作，回退到默认目的地预览' if action_error is None else '预演执行异常，已回退到默认目的地预览',
                    'navigation_target': fallback_target,
                    'movement_target': fallback_target,
                    'velocity': (0.0, 0.0),
                    'chassis_state': 'normal',
                    'turret_state': 'searching',
                }
            segments = []
            if preview_script is not None:
                current_start = (float(actor.position['x']), float(actor.position['y']))
                for segment in preview_script.get('segments', []):
                    point = segment.get('point')
                    if point is None:
                        continue
                    target_point = (float(point[0]), float(point[1]))
                    segments.append({
                        'label': str(segment.get('label', spec['label'])),
                        'start': current_start,
                        'target': target_point,
                        'duration_ms': max(250, int(segment.get('duration_ms', 900))),
                        'target_entity_id': segment.get('target_entity_id'),
                    })
                    current_start = target_point
            navigation_target = decision.get('navigation_target') or decision.get('movement_target') or fallback_target
            if segments:
                navigation_target = segments[-1]['target']
            if navigation_target is None:
                navigation_target = (float(actor.position['x']), float(actor.position['y']))
            region_candidates = []
            if preview_script is not None:
                for region in preview_script.get('regions', []):
                    region_team = region.get('team')
                    if region_team not in {None, 'neutral', team}:
                        continue
                    region_candidates.append(deepcopy(region))
            else:
                for region in self.ai_controller.get_decision_destination_preview_regions(role_key, spec['id'], self.map_manager, team=team):
                    region_team = region.get('team')
                    if region_team not in {None, 'neutral', team}:
                        continue
                    region_candidates.append(deepcopy(region))
            if not region_candidates and navigation_target is not None:
                region_candidates.append({
                    'shape': 'circle',
                    'cx': float(navigation_target[0]),
                    'cy': float(navigation_target[1]),
                    'radius': 28.0,
                })
            if not segments:
                decision_target = decision.get('target') if isinstance(decision.get('target'), dict) else None
                segments = [{
                    'label': str(decision.get('summary', spec['label'])),
                    'start': (float(actor.position['x']), float(actor.position['y'])),
                    'target': (float(navigation_target[0]), float(navigation_target[1])),
                    'duration_ms': 1200,
                    'target_entity_id': decision_target.get('id') if decision_target is not None else None,
                }]
            duration_ms = sum(int(segment.get('duration_ms', 0)) for segment in segments)
            plan['teams'][team] = {
                'entity_id': actor.id,
                'start': (float(actor.position['x']), float(actor.position['y'])),
                'target': (float(navigation_target[0]), float(navigation_target[1])),
                'segments': segments,
                'duration_ms': duration_ms,
                'regions': region_candidates,
                'summary': str(override_brief or (preview_script or {}).get('summary', decision.get('summary', ''))),
                'result': str(result),
                'chassis_state': str(decision.get('chassis_state', 'normal')),
                'turret_state': str(decision.get('turret_state', 'searching')),
            }
            if action_error is None:
                feedback_lines.append(f"{team.upper()}: {plan['teams'][team]['summary']}")
            else:
                feedback_lines.append(f"{team.upper()}: {action_error}")
        if plan['teams']:
            plan['duration_ms'] = max(int(team_plan.get('duration_ms', 0)) for team_plan in plan['teams'].values())
        self.preview_plan = plan if plan['teams'] else None
        self.preview_feedback = feedback_lines
        if self.preview_plan is not None:
            self.add_log(f"开始预演决策: {spec['label']}")
        return self.preview_plan

    def role_available_plugins(self, role_key=None):
        return self.ai_controller.get_available_decision_plugins(role_key or self.selected_role_key())

    def role_default_decision_ids(self, role_key=None):
        plugins = self.role_available_plugins(role_key or self.selected_role_key())
        return [str(plugin.get('id')) for plugin in plugins]

    def role_active_decision_ids(self, role_key=None):
        role = role_key or self.selected_role_key()
        role_entry = self._role_entry(role, create=False) or {}
        override_order = role_entry.get('decision_order') if isinstance(role_entry, dict) else None
        default_ids = self.role_default_decision_ids(role)
        if override_order is None:
            return list(default_ids)
        if not isinstance(override_order, list):
            return list(default_ids)
        filtered = []
        seen = set()
        for decision_id in override_order:
            canonical_id = self.ai_controller._canonical_decision_id(decision_id)
            if canonical_id not in default_ids or canonical_id in seen:
                continue
            filtered.append(canonical_id)
            seen.add(canonical_id)
        return filtered

    def move_role_decision(self, decision_id, direction, role_key=None):
        role = role_key or self.selected_role_key()
        active_ids = self.role_active_decision_ids(role)
        decision_id = str(decision_id)
        if decision_id not in active_ids:
            return False
        current_index = active_ids.index(decision_id)
        target_index = current_index + int(direction)
        if target_index < 0 or target_index >= len(active_ids):
            return False
        active_ids[current_index], active_ids[target_index] = active_ids[target_index], active_ids[current_index]
        role_entry = self._role_entry(role, create=True)
        if active_ids == self.role_default_decision_ids(role):
            role_entry.pop('decision_order', None)
        else:
            role_entry['decision_order'] = list(active_ids)
        self.selected_decision_index[role] = target_index
        self._persist_live_changes(f'已调整 {self.role_label(role)} 决策顺序')
        return True

    def is_decision_active_for_role(self, decision_id, role_key=None):
        return str(decision_id) in set(self.role_active_decision_ids(role_key))

    def toggle_role_decision(self, decision_id, role_key=None):
        role = role_key or self.selected_role_key()
        decision_id = str(decision_id)
        role_entry = self._role_entry(role, create=True)
        active_ids = self.role_active_decision_ids(role)
        if decision_id in active_ids:
            active_ids = [item for item in active_ids if item != decision_id]
            decisions = role_entry.get('decisions', {})
            if isinstance(decisions, dict):
                for alias_id in self.ai_controller._decision_alias_ids(decision_id):
                    decisions.pop(alias_id, None)
            self.add_log(f'已从 {self.role_label(role)} 移除决策: {decision_id}')
        else:
            default_ids = self.role_default_decision_ids(role)
            target_index = default_ids.index(decision_id) if decision_id in default_ids else len(active_ids)
            inserted = False
            for index, current_id in enumerate(active_ids):
                current_default_index = default_ids.index(current_id) if current_id in default_ids else len(default_ids)
                if target_index < current_default_index:
                    active_ids.insert(index, decision_id)
                    inserted = True
                    break
            if not inserted:
                active_ids.append(decision_id)
            self.add_log(f'已为 {self.role_label(role)} 添加决策: {decision_id}')
        if active_ids == self.role_default_decision_ids(role):
            role_entry.pop('decision_order', None)
        else:
            role_entry['decision_order'] = list(active_ids)
        if 'decision_order' not in role_entry and not role_entry.get('decisions'):
            self.behavior_payload.get('roles', {}).pop(role, None)
        self._persist_live_changes()
        specs = self.role_specs(role)
        if specs:
            current_index = self.selected_decision_index.get(role, 0)
            self.selected_decision_index[role] = max(0, min(current_index, len(specs) - 1))

    def set_override_field(self, field_name, value):
        override = self.current_override(create=True)
        if override is None:
            return
        if field_name in {'label', 'condition_expr', 'brief', 'trigger_note', 'logic_note', 'function_note'}:
            text = str(value or '').strip()
            if text:
                override[field_name] = text
            else:
                override.pop(field_name, None)
        elif field_name == 'enabled':
            if value in {'default', None}:
                override.pop('enabled', None)
            else:
                override['enabled'] = bool(value)
        elif field_name in {'start_sec', 'end_sec'}:
            window = override.setdefault('time_window', {})
            if value in {None, ''}:
                window.pop('start_sec' if field_name == 'start_sec' else 'end_sec', None)
            else:
                window['start_sec' if field_name == 'start_sec' else 'end_sec'] = float(value)
            if not window:
                override.pop('time_window', None)
        elif field_name == 'region_mode':
            mode = str(value or 'enter_then_execute')
            if mode == 'enter_then_execute':
                override.pop('region_mode', None)
            else:
                override['region_mode'] = mode
        self.prune_current_override_if_default()
        self._persist_live_changes()

    def prune_current_override_if_default(self):
        spec = self.selected_spec()
        override = self.current_override(create=False)
        if spec is None or override is None:
            return
        normalized = self._normalize_override(override)
        is_default = self._override_is_default(normalized)
        if not is_default:
            return
        role_entry = self._role_entry(self.selected_role_key(), create=False)
        if role_entry is None:
            return
        decisions = role_entry.get('decisions', {})
        if isinstance(decisions, dict):
            for alias_id in self.ai_controller._decision_alias_ids(spec['id']):
                decisions.pop(alias_id, None)
        if not role_entry.get('decisions') and 'decision_order' not in role_entry:
            self.behavior_payload.get('roles', {}).pop(self.selected_role_key(), None)

    def cycle_enabled_state(self):
        override = self.current_override(create=True)
        current = override.get('enabled', 'default') if override is not None else 'default'
        next_state = { 'default': True, True: False, False: 'default' }[current]
        self.set_override_field('enabled', next_state)

    def cycle_region_mode(self):
        override = self.current_override(create=True)
        current = str(override.get('region_mode', 'enter_then_execute')) if override is not None else 'enter_then_execute'
        next_state = 'strict_inside' if current == 'enter_then_execute' else 'enter_then_execute'
        self.set_override_field('region_mode', next_state)

    def current_task_regions(self, team=None):
        return self.current_behavior_regions(team=team)

    def current_behavior_override_regions(self, team=None):
        override = self.current_override(create=False) or {}
        return [deepcopy(region) for region in self.ai_controller._behavior_override_regions(override, team=team)]

    def current_behavior_regions(self, team=None):
        override_regions = self.current_behavior_override_regions(team=team)
        if override_regions:
            return override_regions
        spec = self.selected_spec()
        if spec is None:
            return []
        return self.ai_controller.get_decision_destination_preview_regions(self.selected_role_key(), spec['id'], self.map_manager, team=team)

    def current_destination_override_regions(self, team=None):
        return self.current_behavior_override_regions(team=team)

    def current_destination_regions(self, team=None):
        return self.current_behavior_regions(team=team)

    def current_point_targets(self, team=None):
        return {}

    def current_point_target_specs(self, team=None):
        return {}

    def editable_point_targets(self):
        return []

    def strategy_stages(self):
        override = self.current_override(create=False) or {}
        strategy = self._normalize_strategy(override.get('strategy', {}))
        return [dict(stage) for stage in strategy.get('stages', [])]

    def current_strategy_stage(self, stage_index=0):
        stages = self.strategy_stages()
        if 0 <= stage_index < len(stages):
            return dict(stages[stage_index])
        return {}

    def current_strategy(self):
        return self.current_strategy_stage(0)

    def set_strategy_field(self, field_name, value, stage_index=0):
        override = self.current_override(create=True)
        if override is None:
            return
        strategy = self._normalize_strategy(override.get('strategy', {}))
        stages = [dict(stage) for stage in strategy.get('stages', [])]
        if stage_index < 0 or stage_index >= self.MAX_STRATEGY_STAGES:
            return
        while len(stages) <= stage_index:
            stages.append({})
        stage = dict(stages[stage_index])
        if field_name in {'task_type', 'destination_mode', 'assault_ref', 'assault_follow_priority', 'interaction_ref', 'defense_ref'}:
            text = str(value or '').strip()
            if field_name == 'task_type' and (not text or text == 'default'):
                stage.pop('task_type', None)
            elif field_name == 'destination_mode' and (not text or text == 'region'):
                stage.pop('destination_mode', None)
            elif field_name == 'assault_ref' and (not text or text == 'enemy_any_unit'):
                stage.pop('assault_ref', None)
            elif field_name == 'assault_follow_priority' and (not text or text == 'target_first'):
                stage.pop('assault_follow_priority', None)
            elif field_name == 'interaction_ref' and (not text or text == 'own_supply'):
                stage.pop('interaction_ref', None)
            elif field_name == 'defense_ref' and (not text or text == 'high_threat_enemy'):
                stage.pop('defense_ref', None)
            elif text:
                stage[field_name] = text
            else:
                stage.pop(field_name, None)
        elif field_name == 'engage_distance_m':
            if value in {None, ''}:
                stage.pop('engage_distance_m', None)
            else:
                stage['engage_distance_m'] = float(value)
        stages[stage_index] = self._normalize_strategy_stage(stage)
        stages = [dict(item) for item in stages if item][:self.MAX_STRATEGY_STAGES]
        normalized = {'stages': stages} if stages else {}
        if normalized:
            override['strategy'] = normalized
        else:
            override.pop('strategy', None)
        self.prune_current_override_if_default()
        self._persist_live_changes('已更新策略编辑')

    def clear_strategy_stage(self, stage_index=0):
        override = self.current_override(create=True)
        if override is None:
            return
        stages = self.strategy_stages()
        if stage_index < 0 or stage_index >= len(stages):
            return
        del stages[stage_index]
        if stages:
            override['strategy'] = {'stages': stages[:self.MAX_STRATEGY_STAGES]}
        else:
            override.pop('strategy', None)
        self.prune_current_override_if_default()
        self._persist_live_changes('已清除阶段策略')

    def cycle_strategy_field(self, field_name, stage_index=0):
        strategy = self.current_strategy_stage(stage_index)
        if field_name == 'task_type':
            order = self.STRATEGY_TASK_TYPE_ORDER
            current = str(strategy.get('task_type', 'default'))
        elif field_name == 'destination_mode':
            order = self.DESTINATION_MODE_ORDER
            current = str(strategy.get('destination_mode', 'region'))
        elif field_name == 'assault_ref':
            order = self.ASSAULT_REFERENCE_ORDER
            current = str(strategy.get('assault_ref', order[0]))
        elif field_name == 'assault_follow_priority':
            order = self.ASSAULT_FOLLOW_PRIORITY_ORDER
            current = str(strategy.get('assault_follow_priority', order[0]))
        elif field_name == 'interaction_ref':
            order = self.FIELD_INTERACTION_ORDER
            current = str(strategy.get('interaction_ref', order[0]))
        elif field_name == 'defense_ref':
            order = self.DEFENSE_REFERENCE_ORDER
            current = str(strategy.get('defense_ref', order[0]))
        else:
            return
        if current not in order:
            current = order[0]
        next_value = order[(order.index(current) + 1) % len(order)]
        self.set_strategy_field(field_name, next_value, stage_index=stage_index)

    def current_strategy_task_type_label(self, stage_index=0):
        task_type = str(self.current_strategy_stage(stage_index).get('task_type', 'default'))
        return self.STRATEGY_TASK_TYPE_LABELS.get(task_type, task_type)

    def current_destination_mode_label(self, stage_index=0):
        mode = str(self.current_strategy_stage(stage_index).get('destination_mode', 'region'))
        return self.DESTINATION_MODE_LABELS.get(mode, mode)

    def current_destination_ref_label(self, stage_index=0):
        return '已停用'

    def current_assault_ref_label(self, stage_index=0):
        reference = str(self.current_strategy_stage(stage_index).get('assault_ref', self.ASSAULT_REFERENCE_ORDER[0]))
        return self.STRATEGY_REFERENCE_LABELS.get(reference, reference)

    def current_assault_follow_priority_label(self, stage_index=0):
        priority = str(self.current_strategy_stage(stage_index).get('assault_follow_priority', self.ASSAULT_FOLLOW_PRIORITY_ORDER[0]))
        return self.ASSAULT_FOLLOW_PRIORITY_LABELS.get(priority, priority)

    def current_interaction_ref_label(self, stage_index=0):
        reference = str(self.current_strategy_stage(stage_index).get('interaction_ref', self.FIELD_INTERACTION_ORDER[0]))
        return self.FIELD_INTERACTION_LABELS.get(reference, reference)

    def current_defense_ref_label(self, stage_index=0):
        reference = str(self.current_strategy_stage(stage_index).get('defense_ref', self.DEFENSE_REFERENCE_ORDER[0]))
        return self.DEFENSE_REFERENCE_LABELS.get(reference, reference)

    def current_engage_distance_text(self, stage_index=0):
        return str(self.current_strategy_stage(stage_index).get('engage_distance_m', 8.0))

    def _callable_source_label(self, func):
        if func is None:
            return '未绑定'
        raw = getattr(func, '__func__', func)
        name = str(getattr(raw, '__name__', type(raw).__name__))
        code = getattr(raw, '__code__', None)
        if code is None:
            return name
        workspace_root = os.path.dirname(os.path.abspath(__file__))
        try:
            file_label = os.path.relpath(str(code.co_filename), workspace_root).replace('\\', '/')
        except ValueError:
            file_label = os.path.basename(str(code.co_filename))
        return f'{name} -> {file_label}:{int(code.co_firstlineno)}'

    def current_decision_implementation_details(self):
        spec = self.selected_spec()
        if spec is None:
            return {
                'description': '',
                'trigger_lines': [],
                'logic_lines': [],
                'function_lines': [],
                'interface_lines': [],
                'override': {},
            }
        role_key = self.selected_role_key()
        decision_id = str(spec.get('id', ''))
        binding = self.ai_controller._available_plugin_binding(role_key, decision_id) or {}
        condition_registry = self.ai_controller._behavior_condition_registry()
        action_registry = self.ai_controller._behavior_action_registry()
        condition_ref = str(binding.get('condition_ref', '') or '').strip()
        action_ref = str(binding.get('action_ref', decision_id) or decision_id).strip()
        condition_callable = binding.get('condition') if callable(binding.get('condition')) else condition_registry.get(condition_ref)
        action_callable = binding.get('action') if callable(binding.get('action')) else action_registry.get(action_ref)
        preview_points_callable = binding.get('preview_points') if callable(binding.get('preview_points')) else None
        preview_regions_callable = binding.get('preview_regions') if callable(binding.get('preview_regions')) else None
        override = self.current_override(create=False) or {}
        description = str(binding.get('description', spec.get('description', '')) or '').strip() or '当前决策没有提供额外插件描述。'
        trigger_lines = [description]
        if bool(binding.get('fallback', spec.get('fallback', False))):
            trigger_lines.append('该决策是兜底行为：当前面更高优先级决策都不触发时，才会运行这个决策。')
        elif condition_ref:
            trigger_lines.append(f'触发条件引用: {condition_ref}')
        else:
            trigger_lines.append('当前决策没有显式 condition_ref，通常由上层逻辑直接调度。')
        trigger_lines.append(f'触发函数入口: {self._callable_source_label(condition_callable or spec.get("condition"))}')

        logic_lines = [f'执行动作引用: {action_ref}']
        logic_lines.append(f'执行函数入口: {self._callable_source_label(action_callable or spec.get("action"))}')
        stages = self.strategy_stages()
        if stages:
            logic_lines.append(f'当前已配置 {len(stages)} 个顺序阶段，运行时会按阶段 1 到阶段 {len(stages)} 依次执行。')
        else:
            logic_lines.append('当前未配置自定义阶段，运行时会保持默认决策逻辑。')
        if binding.get('default_destination_types'):
            logic_lines.append(f'默认设施目标类型: {", ".join(str(item) for item in binding.get("default_destination_types", ()))}')
        if binding.get('terrain_mode'):
            logic_lines.append(f'地形模式: {binding.get("terrain_mode")}')
        function_lines = [
            f'condition: {self._callable_source_label(condition_callable or spec.get("condition"))}',
            f'action: {self._callable_source_label(action_callable or spec.get("action"))}',
            f'preview_points: {self._callable_source_label(preview_points_callable)}',
            f'preview_regions: {self._callable_source_label(preview_regions_callable)}',
        ]
        interface_lines = [
            'label: 决策显示名称',
            'brief: 决策简述与预演摘要',
            'trigger_note: 你自己写的触发说明',
            'logic_note: 你自己写的运行逻辑说明',
            'function_note: 你自己写的函数说明/备注',
            'condition_expr: 额外触发条件表达式',
            'region_mode: 先进入行为区域 or 严格在区域内',
            'behavior_regions: 统一行为区域',
            'strategy.stages[n].task_type: 阶段行为类型',
            'strategy.stages[n].destination_mode: 阶段目标模式',
            'strategy.stages[n].assault_ref: 阶段进攻对象',
            'strategy.stages[n].assault_follow_priority: 引用地点/目标优先级',
            'strategy.stages[n].interaction_ref: 场地交互目标',
            'strategy.stages[n].defense_ref: 防守目标',
            'strategy.stages[n].engage_distance_m: 巡航触敌距离',
        ]
        return {
            'description': description,
            'trigger_lines': trigger_lines,
            'logic_lines': logic_lines,
            'function_lines': function_lines,
            'interface_lines': interface_lines,
            'override': dict(override),
        }

    def _opposite_team(self, team):
        return 'blue' if team == 'red' else 'red'

    def _mirror_point_across_map_center(self, point):
        if point is None:
            return None
        map_width = float(getattr(self.map_manager, 'map_width', 0.0) or 0.0)
        map_height = float(getattr(self.map_manager, 'map_height', 0.0) or 0.0)
        return (round(map_width - float(point[0]), 1), round(map_height - float(point[1]), 1))

    def _mirror_region_across_map_center(self, region, target_team):
        mirrored = deepcopy(region)
        shape = str(mirrored.get('shape', 'rect'))
        mirrored.pop('id', None)
        if 'team' in mirrored:
            mirrored['team'] = target_team
        if shape == 'circle':
            mirrored_point = self._mirror_point_across_map_center((mirrored.get('cx', mirrored.get('x', 0.0)), mirrored.get('cy', mirrored.get('y', 0.0))))
            if mirrored_point is not None:
                mirrored['cx'] = mirrored_point[0]
                mirrored['cy'] = mirrored_point[1]
            return mirrored
        if shape == 'polygon':
            mirrored['points'] = [self._mirror_point_across_map_center(point) for point in mirrored.get('points', [])]
            return mirrored
        x1 = float(mirrored.get('x1', 0.0))
        y1 = float(mirrored.get('y1', 0.0))
        x2 = float(mirrored.get('x2', 0.0))
        y2 = float(mirrored.get('y2', 0.0))
        first = self._mirror_point_across_map_center((x1, y1))
        second = self._mirror_point_across_map_center((x2, y2))
        if first is not None and second is not None:
            mirrored['x1'] = min(first[0], second[0])
            mirrored['y1'] = min(first[1], second[1])
            mirrored['x2'] = max(first[0], second[0])
            mirrored['y2'] = max(first[1], second[1])
        return mirrored

    def _replace_team_regions(self, region_kind, team, regions):
        target_regions = self._editable_regions(region_kind, create=True, team=team)
        if target_regions is None:
            return False
        target_regions[:] = [deepcopy(region) for region in regions]
        return True

    def _replace_team_point_targets(self, team, targets):
        return False

    def mirror_current_team_to_opponent(self, source_team):
        source_team = str(source_team or 'red')
        target_team = self._opposite_team(source_team)
        behavior_regions = [
            self._mirror_region_across_map_center(region, target_team)
            for region in self.current_behavior_regions(team=source_team)
        ]
        updated = False
        updated = self._replace_team_regions('behavior', target_team, behavior_regions) or updated
        if not updated:
            return False
        self.prune_current_override_if_default()
        self._persist_live_changes(f'已将{self.role_label(self.selected_role_key())} {source_team} 侧绘制中心对称到 {target_team}')
        return True

    def current_regions_for_kind(self, region_kind='destination', team=None):
        return self.current_behavior_regions(team=team)

    def _editable_regions(self, region_kind='destination', create=False, team=None):
        override = self.current_override(create=create)
        if override is None:
            return None
        field_name = 'behavior_regions'
        if team in {'red', 'blue'}:
            by_team_field = f'{field_name}_by_team'
            by_team = override.get(by_team_field)
            if not isinstance(by_team, dict):
                by_team = {}
                if create:
                    override[by_team_field] = by_team
            regions = by_team.get(team)
            if not isinstance(regions, list) and create:
                regions = [deepcopy(region) for region in self.current_behavior_regions(team=team)]
                by_team[team] = regions
            return by_team.get(team) if isinstance(by_team.get(team), list) else []
        regions = override.get(field_name)
        if not isinstance(regions, list) and create:
            regions = [deepcopy(region) for region in self.current_behavior_regions()]
            override[field_name] = regions
        return override.get(field_name) if isinstance(override.get(field_name), list) else []

    def region_at_point(self, point, region_kind='destination', team=None):
        regions = self.current_regions_for_kind(region_kind, team=team)
        for index in range(len(regions) - 1, -1, -1):
            if self.ai_controller._point_in_behavior_region(point, regions[index]):
                return index, deepcopy(regions[index])
        return None, None

    def update_region(self, region_index, region, region_kind='destination', log_message=None, team=None):
        regions = self._editable_regions(region_kind, create=True, team=team)
        if regions is None or region_index < 0 or region_index >= len(regions):
            return False
        regions[region_index] = deepcopy(region)
        self._persist_live_changes(log_message or '已更新逻辑区域')
        return True

    def remove_region_at_index(self, region_index, region_kind='destination', log_message=None, team=None):
        regions = self._editable_regions(region_kind, create=True, team=team)
        if regions is None or region_index < 0 or region_index >= len(regions):
            return False
        regions.pop(region_index)
        field_name = 'behavior_regions'
        override = self.current_override(create=False)
        if override is not None and not regions:
            if team in {'red', 'blue'}:
                by_team = override.get(f'{field_name}_by_team', {})
                if isinstance(by_team, dict):
                    by_team.pop(team, None)
                    if not by_team:
                        override.pop(f'{field_name}_by_team', None)
            else:
                override.pop(field_name, None)
        self.prune_current_override_if_default()
        self._persist_live_changes(log_message or '已删除逻辑区域')
        return True

    def add_task_region(self, region, team=None):
        self.add_behavior_region(region, team=team)

    def add_behavior_region(self, region, team=None):
        behavior_regions = self._editable_regions('behavior', create=True, team=team)
        if behavior_regions is None:
            return
        behavior_regions.append(deepcopy(region))
        self._persist_live_changes('已更新行为区域')

    def add_destination_region(self, region, team=None):
        self.add_behavior_region(region, team=team)

    def remove_region_at_point(self, point, region_kind='destination', team=None, log_message=None):
        regions = self._editable_regions(region_kind, create=True, team=team)
        if regions is None:
            return False
        removed = False
        for index in range(len(regions) - 1, -1, -1):
            if self.ai_controller._point_in_behavior_region(point, regions[index]):
                del regions[index]
                removed = True
                break
        if not removed:
            return False
        field_name = 'behavior_regions'
        override = self.current_override(create=False)
        if override is not None and not regions:
            if team in {'red', 'blue'}:
                by_team = override.get(f'{field_name}_by_team', {})
                if isinstance(by_team, dict):
                    by_team.pop(team, None)
                    if not by_team:
                        override.pop(f'{field_name}_by_team', None)
            else:
                override.pop(field_name, None)
        self.prune_current_override_if_default()
        self._persist_live_changes(log_message or '已删除逻辑区域')
        return True

    def set_point_target(self, target_id, point, team=None):
        return

    def set_point_target_radius(self, target_id, radius, team=None):
        return False

    def clear_point_target(self, target_id, team=None):
        return False

    def clear_current_override(self):
        spec = self.selected_spec()
        role_key = self.selected_role_key()
        if spec is None:
            return False
        role_entry = self._role_entry(role_key, create=False)
        if role_entry is None:
            return False
        removed = None
        decisions = role_entry.get('decisions', {})
        if isinstance(decisions, dict):
            for alias_id in self.ai_controller._decision_alias_ids(spec['id']):
                popped = decisions.pop(alias_id, None)
                if popped is not None:
                    removed = popped
        if not role_entry.get('decisions') and 'decision_order' not in role_entry:
            self.behavior_payload.get('roles', {}).pop(role_key, None)
        if removed is not None:
            self._persist_live_changes('已清空当前决策覆盖，恢复默认行为')
        return removed is not None

    def current_enabled_label(self):
        override = self.current_override(create=False) or {}
        enabled = override.get('enabled', 'default')
        return { 'default': '默认', True: '启用', False: '禁用' }[enabled]

    def current_region_mode_label(self):
        override = self.current_override(create=False) or {}
        mode = str(override.get('region_mode', 'enter_then_execute'))
        return self.REGION_MODE_LABELS.get(mode, mode)

    def _pruned_payload(self):
        payload = self._empty_payload(self.preset_name)
        for role_key, role_entry in (self.behavior_payload.get('roles', {}) or {}).items():
            decisions = {}
            decision_order = role_entry.get('decision_order') if isinstance(role_entry, dict) else None
            for decision_id, override in (role_entry.get('decisions', {}) or {}).items():
                normalized = self._normalize_override(override)
                if self._override_is_default(normalized):
                    continue
                if normalized.get('region_mode', 'enter_then_execute') == 'enter_then_execute':
                    normalized.pop('region_mode', None)
                decisions[decision_id] = normalized
            default_ids = self.role_default_decision_ids(role_key)
            if decision_order is None:
                persist_order = None
            elif not isinstance(decision_order, list):
                persist_order = None
            else:
                filtered_order = []
                seen = set()
                for decision_id in decision_order:
                    canonical_id = self.ai_controller._canonical_decision_id(decision_id)
                    if canonical_id not in default_ids or canonical_id in seen:
                        continue
                    filtered_order.append(canonical_id)
                    seen.add(canonical_id)
                persist_order = None if filtered_order == list(default_ids) else filtered_order
            if decisions or persist_order is not None:
                payload['roles'][role_key] = {'decisions': decisions}
                if persist_order is not None:
                    payload['roles'][role_key]['decision_order'] = persist_order
        payload['saved_at'] = datetime.now().isoformat(timespec='seconds')
        return payload

    def save_preset(self, preset_name=None):
        name = str(preset_name or self.preset_name or 'latest_behavior').strip() or 'latest_behavior'
        self.preset_name = name
        payload = self._pruned_payload()
        payload['name'] = name
        path = self.config_manager.save_behavior_preset(name, payload, self.config_path)
        self.behavior_payload = payload
        saved_name = os.path.basename(path) if path else f'{name}.json'
        self.add_log(f'行为预设已保存: {saved_name}')
        return path

    def apply_preset(self, preset_name=None):
        self.save_preset(preset_name)
        self.config.setdefault('ai', {})['behavior_preset'] = self.preset_name
        self.config_manager.config = self.config
        self.config_manager.save_settings(self.settings_path)
        self.add_log(f'主程序已切换行为预设: {self.preset_name}')

    def reload_preset(self, preset_name=None):
        name = str(preset_name or self.preset_name or 'latest_behavior').strip() or 'latest_behavior'
        self.preset_name = name
        self.behavior_payload = self._load_behavior_payload(name)
        self.appearance_payload = self._load_appearance_payload()
        self.ai_controller._refresh_behavior_runtime_overrides(force=True)
        self._reset_preview_world()
        self.add_log(f'已重载行为预设: {name}')


class BehaviorEditorApp:
    def __init__(self, engine):
        self.engine = engine
        pygame.init()
        self.window_width = max(1680, int(engine.config.get('simulator', {}).get('window_width', 1400)))
        self.window_height = max(980, int(engine.config.get('simulator', {}).get('window_height', 900)))
        self.screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption('RoboMaster 行为编辑器')
        self.clock = pygame.time.Clock()
        self.running = False
        self.toolbar_height = 56
        self.panel_width = 960
        self.padding = 12
        self.decision_rows_per_page = 6
        self.decision_page_index = {role_key: 0 for role_key in self.engine.ROLE_ORDER}
        self.decision_list_scroll_y = 0
        self.decision_list_scroll_max = 0
        self.decision_list_viewport_rect = None
        self.sidebar_list_scroll_y = 0
        self.sidebar_list_scroll_max = 0
        self.sidebar_list_viewport_rect = None
        self.detail_pages = (
            ('overview', '概览'),
            ('condition', '条件'),
            ('strategy', '策略'),
            ('region', '区域'),
            ('collision', '碰撞箱'),
            ('implementation', '实现说明'),
        )
        self.detail_page = 'overview'
        self.panel_scroll_y = 0
        self.panel_scroll_max = 0
        self.panel_scroll_step = 48
        self.list_scroll_step = 32
        self.panel_viewport_rect = None
        self.region_edit_target = 'behavior'
        self.region_edit_team = 'red'
        self.selected_strategy_stage_index = 0
        self.map_texture = self.engine.map_manager.map_image
        self.map_cache = None
        self.map_cache_size = None
        map_width = max(1.0, float(getattr(self.engine.map_manager, 'map_width', 1.0) or 1.0))
        map_height = max(1.0, float(getattr(self.engine.map_manager, 'map_height', 1.0) or 1.0))
        self.map_zoom = 1.0
        self.map_zoom_min = 1.0
        self.map_zoom_max = 4.0
        self.map_view_center = (self.map_texture.get_width() // 2, self.map_texture.get_height() // 2)
        self.map_dragging = False
        self.map_drag_last_pos = None
        self.active_text = SimpleNamespace(input=None)
        self.shape_mode = 'rect'
        self.drag_start = None
        self.drag_current = None
        self.polygon_points = []
        self.region_drag_state = None
        self.selected_region_kind = None
        self.selected_region_index = None
        self.selected_region_team = None
        self.mouse_world = None
        self.point_edit_target = None

        self.preview_loop_active = False
        self.preview_cycle_started_ms = 0
        self.preview_run_duration_ms = 1800
        self.preview_pause_duration_ms = 600

        self.colors = {
            'bg': (233, 236, 241),
            'toolbar': (26, 31, 38),
            'toolbar_text': (247, 248, 250),
            'toolbar_button': (67, 77, 92),
            'toolbar_button_active': (210, 92, 47),
            'panel': (248, 249, 252),
            'panel_border': (205, 211, 220),
            'panel_text': (31, 39, 47),
            'panel_row': (236, 240, 245),
            'panel_row_active': (218, 231, 245),
            'map_bg': (255, 255, 255),
            'red': (214, 63, 63),
            'blue': (53, 112, 214),
            'yellow': (233, 181, 55),
            'green': (66, 156, 105),
            'orange': (225, 140, 72),
            'white': (255, 255, 255),
            'gray': (132, 139, 149),
            'black': (18, 18, 18),
        }
        self.title_font = pygame.font.SysFont('Microsoft YaHei UI', 18, bold=True)
        self.base_font = pygame.font.SysFont('Microsoft YaHei UI', 16)
        self.small_font = pygame.font.SysFont('Microsoft YaHei UI', 14)
        self.tiny_font = pygame.font.SysFont('Microsoft YaHei UI', 12)

    def map_rect(self):
        return pygame.Rect(
            self.padding,
            self.toolbar_height + self.padding,
            self.window_width - self.panel_width - self.padding * 3,
            self.window_height - self.toolbar_height - self.padding * 2,
        )

    def map_draw_rect(self):
        area_rect = self.map_rect()
        map_manager = self.engine.map_manager
        map_width = max(1.0, float(getattr(map_manager, 'map_width', 1) or 1))
        map_height = max(1.0, float(getattr(map_manager, 'map_height', 1) or 1))
        scale = min(area_rect.width / map_width, area_rect.height / map_height)
        draw_width = max(1, int(map_width * scale))
        draw_height = max(1, int(map_height * scale))
        return pygame.Rect(
            area_rect.x + (area_rect.width - draw_width) // 2,
            area_rect.y + (area_rect.height - draw_height) // 2,
            draw_width,
            draw_height,
        )

    def panel_rect(self):
        return pygame.Rect(
            self.window_width - self.panel_width - self.padding,
            self.toolbar_height + self.padding,
            self.panel_width,
            self.window_height - self.toolbar_height - self.padding * 2,
        )

    def _map_surface(self, target_size):
        map_image = getattr(self.engine.map_manager, 'map_image', None)
        if map_image is None:
            return None
        bounds = self._map_visible_world_bounds()
        cache_key = (target_size, tuple(round(value, 2) for value in bounds))
        if self.map_cache is None or self.map_cache_size != cache_key:
            map_manager = self.engine.map_manager
            image_width, image_height = map_image.get_size()
            source_x = int(max(0, min(image_width - 1, bounds[0] / max(float(map_manager.map_width), 1.0) * image_width)))
            source_y = int(max(0, min(image_height - 1, bounds[1] / max(float(map_manager.map_height), 1.0) * image_height)))
            source_w = max(1, int(bounds[2] / max(float(map_manager.map_width), 1.0) * image_width))
            source_h = max(1, int(bounds[3] / max(float(map_manager.map_height), 1.0) * image_height))
            source_w = min(source_w, image_width - source_x)
            source_h = min(source_h, image_height - source_y)
            source_rect = pygame.Rect(source_x, source_y, source_w, source_h)
            cropped = map_image.subsurface(source_rect).copy()
            self.map_cache = pygame.transform.smoothscale(cropped, target_size)
            self.map_cache_size = cache_key
        return self.map_cache

    def _map_visible_world_bounds(self):
        map_manager = self.engine.map_manager
        map_width = max(1.0, float(getattr(map_manager, 'map_width', 1.0) or 1.0))
        map_height = max(1.0, float(getattr(map_manager, 'map_height', 1.0) or 1.0))
        zoom = max(self.map_zoom_min, min(self.map_zoom, self.map_zoom_max))
        visible_width = map_width / zoom
        visible_height = map_height / zoom
        center_x, center_y = self.map_view_center
        left = max(0.0, min(float(center_x) - visible_width * 0.5, map_width - visible_width))
        top = max(0.0, min(float(center_y) - visible_height * 0.5, map_height - visible_height))
        return (left, top, visible_width, visible_height)

    def _clamp_map_view_center(self):
        map_manager = self.engine.map_manager
        map_width = max(1.0, float(getattr(map_manager, 'map_width', 1.0) or 1.0))
        map_height = max(1.0, float(getattr(map_manager, 'map_height', 1.0) or 1.0))
        left, top, visible_width, visible_height = self._map_visible_world_bounds()
        self.map_view_center = (
            max(visible_width * 0.5, min(map_width - visible_width * 0.5, left + visible_width * 0.5)),
            max(visible_height * 0.5, min(map_height - visible_height * 0.5, top + visible_height * 0.5)),
        )

    def _zoom_map_around(self, screen_pos, wheel_delta):
        world_before = self.screen_to_world(screen_pos)
        if world_before is None:
            return
        factor = 1.12 if int(wheel_delta) > 0 else (1.0 / 1.12)
        new_zoom = max(self.map_zoom_min, min(self.map_zoom * factor, self.map_zoom_max))
        if abs(new_zoom - self.map_zoom) <= 1e-6:
            return
        self.map_zoom = new_zoom
        world_after = self.screen_to_world(screen_pos)
        if world_after is not None:
            self.map_view_center = (
                float(self.map_view_center[0]) + float(world_before[0]) - float(world_after[0]),
                float(self.map_view_center[1]) + float(world_before[1]) - float(world_after[1]),
            )
        self._clamp_map_view_center()
        self.map_cache = None
        self.map_cache_size = None

    def world_to_screen(self, point):
        map_rect = self.map_draw_rect()
        map_manager = self.engine.map_manager
        if point is None or map_manager.map_width <= 0 or map_manager.map_height <= 0:
            return None
        left, top, visible_width, visible_height = self._map_visible_world_bounds()
        scale_x = map_rect.width / max(visible_width, 1.0)
        scale_y = map_rect.height / max(visible_height, 1.0)
        return (
            map_rect.x + int((float(point[0]) - left) * scale_x),
            map_rect.y + int((float(point[1]) - top) * scale_y),
        )

    def screen_to_world(self, screen_pos):
        map_rect = self.map_draw_rect()
        if not map_rect.collidepoint(screen_pos):
            return None
        map_manager = self.engine.map_manager
        left, top, visible_width, visible_height = self._map_visible_world_bounds()
        local_x = (screen_pos[0] - map_rect.x) / max(map_rect.width, 1)
        local_y = (screen_pos[1] - map_rect.y) / max(map_rect.height, 1)
        return (
            max(0.0, min(float(map_manager.map_width), left + local_x * visible_width)),
            max(0.0, min(float(map_manager.map_height), top + local_y * visible_height)),
        )

    def _toolbar_button(self, x, label, action, active=False):
        text = self.base_font.render(label, True, self.colors['toolbar_text'])
        rect = pygame.Rect(x, 10, text.get_width() + 22, self.toolbar_height - 20)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if active else self.colors['toolbar_button'], rect, border_radius=6)
        self.screen.blit(text, (rect.x + 11, rect.y + (rect.height - text.get_height()) // 2))
        self.click_actions.append((rect, action))
        return rect.right + 8

    def _role_label(self, role_key):
        return {'sentry': '哨兵', 'infantry': '步兵', 'hero': '英雄', 'engineer': '工程', 'common': '通用'}.get(role_key, role_key)

    def _clear_region_selection(self):
        self.selected_region_kind = None
        self.selected_region_index = None
        self.selected_region_team = None
        self.region_drag_state = None

    def _selected_region(self):
        if self.selected_region_kind != self.region_edit_target or self.selected_region_team != self.region_edit_team or self.selected_region_index is None:
            return None
        regions = self.engine.current_regions_for_kind(self.selected_region_kind, team=self.selected_region_team)
        if self.selected_region_index < 0 or self.selected_region_index >= len(regions):
            self._clear_region_selection()
            return None
        return deepcopy(regions[self.selected_region_index])

    def _set_selected_region(self, region_kind, region_index, region_team=None):
        self.selected_region_kind = region_kind
        self.selected_region_index = region_index
        self.selected_region_team = region_team or self.region_edit_team

    def _world_distance(self, first, second):
        if first is None or second is None:
            return float('inf')
        return math.hypot(float(first[0]) - float(second[0]), float(first[1]) - float(second[1]))

    def _snap_orthogonal_target(self, start, target):
        if start is None or target is None:
            return target
        delta_x = float(target[0]) - float(start[0])
        delta_y = float(target[1]) - float(start[1])
        if abs(delta_x) >= abs(delta_y):
            return (float(target[0]), float(start[1]))
        return (float(start[0]), float(target[1]))

    def _current_polygon_target(self, points, target):
        if not points:
            return target
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_SHIFT:
            return self._snap_orthogonal_target(points[-1], target)
        return target

    def _current_draw_target(self, world_pos):
        if world_pos is None:
            return None
        mods = pygame.key.get_mods()
        if self.shape_mode == 'polygon' and self.polygon_points:
            return self._current_polygon_target(self.polygon_points, world_pos)
        if self.shape_mode in {'rect', 'circle'} and self.drag_start is not None and mods & pygame.KMOD_SHIFT:
            return self._snap_orthogonal_target(self.drag_start, world_pos)
        return world_pos

    def _translate_region(self, region, delta_x, delta_y):
        moved = deepcopy(region)
        shape = str(moved.get('shape', 'rect'))
        if shape == 'circle':
            moved['cx'] = round(float(moved.get('cx', moved.get('x', 0.0))) + delta_x, 1)
            moved['cy'] = round(float(moved.get('cy', moved.get('y', 0.0))) + delta_y, 1)
            return moved
        if shape == 'polygon':
            moved['points'] = [
                (round(float(point[0]) + delta_x, 1), round(float(point[1]) + delta_y, 1))
                for point in moved.get('points', [])
            ]
            return moved
        moved['x1'] = round(float(moved.get('x1', 0.0)) + delta_x, 1)
        moved['y1'] = round(float(moved.get('y1', 0.0)) + delta_y, 1)
        moved['x2'] = round(float(moved.get('x2', 0.0)) + delta_x, 1)
        moved['y2'] = round(float(moved.get('y2', 0.0)) + delta_y, 1)
        return moved

    def _region_handles(self, region):
        shape = str(region.get('shape', 'rect'))
        if shape == 'circle':
            center = (float(region.get('cx', region.get('x', 0.0))), float(region.get('cy', region.get('y', 0.0))))
            radius = float(region.get('radius', 0.0))
            return {'center': center, 'radius': (center[0] + radius, center[1])}
        if shape == 'polygon':
            return {f'vertex:{index}': (float(point[0]), float(point[1])) for index, point in enumerate(region.get('points', []))}
        return {
            'x1y1': (float(region.get('x1', 0.0)), float(region.get('y1', 0.0))),
            'x2y1': (float(region.get('x2', 0.0)), float(region.get('y1', 0.0))),
            'x1y2': (float(region.get('x1', 0.0)), float(region.get('y2', 0.0))),
            'x2y2': (float(region.get('x2', 0.0)), float(region.get('y2', 0.0))),
        }

    def _begin_region_drag(self, world_point):
        region_kind = self.region_edit_target
        region_team = self.region_edit_team
        regions = self.engine.current_regions_for_kind(region_kind, team=region_team)
        handle_tolerance = 14.0
        for index in range(len(regions) - 1, -1, -1):
            region = deepcopy(regions[index])
            shape = str(region.get('shape', 'rect'))
            handles = self._region_handles(region)
            if shape == 'polygon':
                for handle_key, handle_point in handles.items():
                    if self._world_distance(world_point, handle_point) <= handle_tolerance:
                        self._set_selected_region(region_kind, index, region_team=region_team)
                        self.region_drag_state = {
                            'kind': region_kind,
                            'team': region_team,
                            'index': index,
                            'mode': 'polygon_vertex',
                            'handle': handle_key,
                            'start': world_point,
                            'original': region,
                            'preview': deepcopy(region),
                        }
                        return True
            elif shape == 'circle':
                if self._world_distance(world_point, handles['radius']) <= handle_tolerance:
                    self._set_selected_region(region_kind, index, region_team=region_team)
                    self.region_drag_state = {
                        'kind': region_kind,
                        'team': region_team,
                        'index': index,
                        'mode': 'circle_radius',
                        'start': world_point,
                        'original': region,
                        'preview': deepcopy(region),
                    }
                    return True
            else:
                for handle_key, handle_point in handles.items():
                    if self._world_distance(world_point, handle_point) <= handle_tolerance:
                        self._set_selected_region(region_kind, index, region_team=region_team)
                        self.region_drag_state = {
                            'kind': region_kind,
                            'team': region_team,
                            'index': index,
                            'mode': 'rect_corner',
                            'handle': handle_key,
                            'start': world_point,
                            'original': region,
                            'preview': deepcopy(region),
                        }
                        return True
            if self.engine.ai_controller._point_in_behavior_region(world_point, region):
                self._set_selected_region(region_kind, index, region_team=region_team)
                self.region_drag_state = {
                    'kind': region_kind,
                    'team': region_team,
                    'index': index,
                    'mode': 'move',
                    'start': world_point,
                    'original': region,
                    'preview': deepcopy(region),
                }
                return True
        return False

    def _update_region_drag_preview(self, world_point):
        if self.region_drag_state is None or world_point is None:
            return
        state = self.region_drag_state
        original = state['original']
        preview = deepcopy(original)
        mode = state['mode']
        if mode == 'move':
            delta_x = float(world_point[0]) - float(state['start'][0])
            delta_y = float(world_point[1]) - float(state['start'][1])
            preview = self._translate_region(original, delta_x, delta_y)
        elif mode == 'rect_corner':
            target = self._current_draw_target(world_point)
            if target is None:
                return
            handle = state['handle']
            if 'x1' in handle:
                preview['x1'] = round(float(target[0]), 1)
            if 'x2' in handle:
                preview['x2'] = round(float(target[0]), 1)
            if 'y1' in handle:
                preview['y1'] = round(float(target[1]), 1)
            if 'y2' in handle:
                preview['y2'] = round(float(target[1]), 1)
        elif mode == 'circle_radius':
            center = (float(original.get('cx', original.get('x', 0.0))), float(original.get('cy', original.get('y', 0.0))))
            preview['radius'] = round(max(4.0, self._world_distance(center, world_point)), 1)
        elif mode == 'polygon_vertex':
            vertex_index = int(str(state['handle']).split(':', 1)[1])
            points = list(preview.get('points', []))
            if 0 <= vertex_index < len(points):
                points[vertex_index] = (round(float(world_point[0]), 1), round(float(world_point[1]), 1))
                preview['points'] = points
        state['preview'] = preview

    def _commit_region_drag(self):
        if self.region_drag_state is None:
            return False
        state = self.region_drag_state
        self.region_drag_state = None
        preview = state['preview']
        if preview == state['original']:
            return False
        updated = self.engine.update_region(
            state['index'],
            preview,
            region_kind=state['kind'],
            log_message='已更新逻辑区域',
            team=state.get('team'),
        )
        if updated:
            self._set_selected_region(state['kind'], state['index'], region_team=state.get('team'))
        return updated

    def _append_polygon_point(self, world_point):
        if world_point is None:
            return
        self._clear_region_selection()
        self.polygon_points.append(world_point)
        self.drag_current = world_point
        self.engine.add_log(f'多边形已添加顶点 ({int(world_point[0])}, {int(world_point[1])})')

    def _wrap_text(self, text, font, max_width, max_lines=None):
        raw_text = str(text or '')
        if not raw_text:
            return []
        lines = []
        for paragraph in raw_text.splitlines() or ['']:
            current = ''
            for char in paragraph:
                candidate = f'{current}{char}'
                if current and font.size(candidate)[0] > max_width:
                    lines.append(current)
                    current = char
                    if max_lines is not None and len(lines) >= max_lines:
                        return lines[:-1] + [f'{lines[-1][:-1]}…' if len(lines[-1]) > 1 else '…']
                else:
                    current = candidate
            lines.append(current or ' ')
            if max_lines is not None and len(lines) >= max_lines:
                return lines[:max_lines]
        return lines

    def _draw_text_lines(self, lines, font, color, x, y, line_gap=4, max_height=None):
        current_y = y
        for line in lines:
            surface = font.render(line, True, color)
            if max_height is not None and current_y + surface.get_height() > max_height:
                break
            self.screen.blit(surface, (x, current_y))
            current_y += surface.get_height() + line_gap
        return current_y

    def _panel_card(self, rect, title, body_lines=None, action=None, active=False, title_font=None, body_font=None):
        pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['white'], rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=8)
        if action is not None:
            click_rect = rect
            if self.panel_viewport_rect is not None:
                click_rect = rect.clip(self.panel_viewport_rect)
            if click_rect.width > 0 and click_rect.height > 0:
                self.click_actions.append((click_rect, action))
        title_font = title_font or self.small_font
        body_font = body_font or self.tiny_font
        title_surface = title_font.render(str(title), True, self.colors['panel_text'])
        self.screen.blit(title_surface, (rect.x + 10, rect.y + 8))
        if body_lines:
            max_body_width = max(24, rect.width - 20)
            wrapped_lines = []
            for line in body_lines:
                wrapped_lines.extend(self._wrap_text(line, body_font, max_body_width, max_lines=6))
            self._draw_text_lines(wrapped_lines, body_font, self.colors['gray'], rect.x + 10, rect.y + 10 + title_surface.get_height(), line_gap=3, max_height=rect.bottom - 8)

    def _decision_row(self, rect, label, decision_id, action=None, active=False, clip_rect=None):
        pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], rect, border_radius=6)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=6)
        label_surface = self.small_font.render(str(label), True, self.colors['panel_text'])
        decision_surface = self.tiny_font.render(str(decision_id), True, self.colors['gray'])
        self.screen.blit(label_surface, (rect.x + 10, rect.y + 6))
        self.screen.blit(decision_surface, (rect.x + 10, rect.y + 10 + label_surface.get_height()))
        if action is not None:
            click_rect = rect.clip(clip_rect) if clip_rect is not None else rect
            if click_rect.width > 0 and click_rect.height > 0:
                self.click_actions.append((click_rect, action))

    def _render_preview_units(self):
        preview_world = self.engine.preview_world_entities()
        if not preview_world:
            return
        current_ms = pygame.time.get_ticks()
        active_plan = self.engine.preview_plan or {}
        plan_duration = int(active_plan.get('duration_ms', self.preview_run_duration_ms) or self.preview_run_duration_ms)
        if self.preview_loop_active and active_plan:
            cycle_duration = plan_duration + self.preview_pause_duration_ms
            if current_ms - self.preview_cycle_started_ms >= cycle_duration:
                self._restart_preview_cycle(current_ms)
        for entity in preview_world:
            if entity.type not in {'robot', 'sentry'}:
                continue
            point = self.world_to_screen((entity.position['x'], entity.position['y']))
            if point is None:
                continue
            draw_point = point
            if self.preview_loop_active and self.engine.preview_plan is not None:
                team_plan = self.engine.preview_plan.get('teams', {}).get(entity.team)
                if team_plan is not None and team_plan.get('entity_id') == entity.id:
                    elapsed = current_ms - self.preview_cycle_started_ms
                    interp, active_segment = self._preview_team_position(team_plan, elapsed)
                    preview_point = self.world_to_screen(interp) if interp is not None else None
                    if preview_point is not None:
                        draw_point = preview_point
                    target = active_segment.get('target') if active_segment is not None else team_plan.get('target')
                    target_point = self.world_to_screen(target) if target is not None else None
                    if target_point is not None:
                        pygame.draw.line(self.screen, self.colors['green'], draw_point, target_point, 2)
                        pygame.draw.circle(self.screen, self.colors['green'], target_point, 5, 2)
            color = self.colors['red'] if entity.team == 'red' else self.colors['blue']
            radius = 8 if entity.type == 'sentry' else 6
            pygame.draw.circle(self.screen, color, draw_point, radius)
            pygame.draw.circle(self.screen, self.colors['white'], draw_point, radius, 1)
            role_text = entity.robot_type[0] if getattr(entity, 'robot_type', '') else 'B'
            label_surface = self.tiny_font.render(role_text, True, self.colors['white'])
            self.screen.blit(label_surface, (draw_point[0] - label_surface.get_width() // 2, draw_point[1] - label_surface.get_height() // 2))

    def _preview_team_position(self, team_plan, elapsed_ms):
        segments = list(team_plan.get('segments', ()))
        if not segments:
            return team_plan.get('start'), None
        remaining = max(0, int(elapsed_ms))
        for segment in segments:
            duration_ms = max(1, int(segment.get('duration_ms', 900)))
            start = segment.get('start', team_plan.get('start'))
            target = segment.get('target', start)
            if remaining <= duration_ms:
                ratio = min(1.0, max(0.0, remaining / duration_ms))
                interp = (
                    float(start[0]) + (float(target[0]) - float(start[0])) * ratio,
                    float(start[1]) + (float(target[1]) - float(start[1])) * ratio,
                )
                return interp, segment
            remaining -= duration_ms
        last_segment = segments[-1]
        return last_segment.get('target', team_plan.get('target')), last_segment

    def _restart_preview_cycle(self, current_ms=None):
        plan = self.engine.build_decision_preview()
        if plan is None:
            self.preview_loop_active = False
            return
        self.preview_loop_active = True
        self.preview_cycle_started_ms = current_ms if current_ms is not None else pygame.time.get_ticks()

    def _render_available_decision_sidebar(self, sidebar_rect):
        pygame.draw.rect(self.screen, self.colors['white'], sidebar_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], sidebar_rect, 1, border_radius=8)
        title = self.small_font.render('可选决策 / 预演', True, self.colors['panel_text'])
        self.screen.blit(title, (sidebar_rect.x + 10, sidebar_rect.y + 10))

        preview_label = '停止预演' if self.preview_loop_active else '预演当前决策'
        preview_rect = pygame.Rect(sidebar_rect.x + 10, sidebar_rect.y + 36, sidebar_rect.width - 20, 32)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'], preview_rect, border_radius=6)
        preview_surface = self.small_font.render(preview_label, True, self.colors['white'])
        self.screen.blit(preview_surface, (preview_rect.x + (preview_rect.width - preview_surface.get_width()) // 2, preview_rect.y + 7))
        self.click_actions.append((preview_rect, 'preview:toggle'))

        feedback_rect = pygame.Rect(sidebar_rect.x + 10, preview_rect.bottom + 8, sidebar_rect.width - 20, 92)
        pygame.draw.rect(self.screen, self.colors['panel_row'], feedback_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.colors['panel_border'], feedback_rect, 1, border_radius=6)
        feedback_title = self.tiny_font.render('预演反馈', True, self.colors['panel_text'])
        self.screen.blit(feedback_title, (feedback_rect.x + 8, feedback_rect.y + 8))
        feedback_lines = self.engine.preview_feedback or ['点击上方按钮预演当前选中决策', '预演会按完整策略阶段播放移动与追击结果']
        self._draw_text_lines(feedback_lines[:4], self.tiny_font, self.colors['gray'], feedback_rect.x + 8, feedback_rect.y + 26, line_gap=2, max_height=feedback_rect.bottom - 8)

        list_y = feedback_rect.bottom + 10
        list_title = self.tiny_font.render('当前角色全部可选决策', True, self.colors['panel_text'])
        self.screen.blit(list_title, (sidebar_rect.x + 10, list_y))
        list_y += list_title.get_height() + 8
        list_viewport = pygame.Rect(sidebar_rect.x + 10, list_y, sidebar_rect.width - 20, max(40, sidebar_rect.bottom - list_y - 10))
        pygame.draw.rect(self.screen, self.colors['panel_row'], list_viewport, border_radius=6)
        pygame.draw.rect(self.screen, self.colors['panel_border'], list_viewport, 1, border_radius=6)
        plugins = self.engine.role_available_plugins()
        row_height = 32
        total_height = len(plugins) * row_height + 4
        self.sidebar_list_scroll_max = max(0, total_height - list_viewport.height)
        self.sidebar_list_scroll_y = max(0, min(self.sidebar_list_scroll_y, self.sidebar_list_scroll_max))
        self.sidebar_list_viewport_rect = list_viewport
        clip_backup = self.screen.get_clip()
        self.screen.set_clip(list_viewport)
        row_y = list_viewport.y + 2 - self.sidebar_list_scroll_y
        for plugin in plugins:
            decision_id = str(plugin.get('id', ''))
            active = self.engine.is_decision_active_for_role(decision_id)
            row_rect = pygame.Rect(list_viewport.x + 2, row_y, list_viewport.width - 4, 30)
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], row_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['panel_border'], row_rect, 1, border_radius=6)
            marker_rect = pygame.Rect(row_rect.right - 26, row_rect.y + 7, 16, 16)
            pygame.draw.rect(self.screen, self.colors['green'] if active else self.colors['gray'], marker_rect, border_radius=4)
            marker_text = self.tiny_font.render('开' if active else '关', True, self.colors['white'])
            self.screen.blit(marker_text, (marker_rect.x + (marker_rect.width - marker_text.get_width()) // 2, marker_rect.y + 3))
            label_surface = self.tiny_font.render(str(plugin.get('label', decision_id)), True, self.colors['panel_text'])
            self.screen.blit(label_surface, (row_rect.x + 8, row_rect.y + 5))
            id_surface = self.tiny_font.render(decision_id, True, self.colors['gray'])
            self.screen.blit(id_surface, (row_rect.x + 8, row_rect.y + 15))
            click_rect = row_rect.clip(list_viewport)
            if click_rect.width > 0 and click_rect.height > 0:
                self.click_actions.append((click_rect, f'toggle_decision:{decision_id}'))
            row_y += row_height
        self.screen.set_clip(clip_backup)
        self._draw_generic_scrollbar(list_viewport, self.sidebar_list_scroll_y, self.sidebar_list_scroll_max)

    def _draw_scroll_hint(self, rect):
        if self.panel_scroll_max <= 0:
            return
        hint_surface = self.tiny_font.render('滚轮可上下查看详情', True, self.colors['gray'])
        self.screen.blit(hint_surface, (rect.right - hint_surface.get_width() - 10, rect.y + 8))

    def _draw_scrollbar(self, rect):
        if self.panel_scroll_max <= 0:
            return
        track_rect = pygame.Rect(rect.right - 8, rect.y + 8, 4, max(24, rect.height - 16))
        pygame.draw.rect(self.screen, self.colors['panel_border'], track_rect, border_radius=4)
        thumb_height = max(28, int(track_rect.height * (rect.height / max(rect.height + self.panel_scroll_max, 1))))
        scroll_ratio = self.panel_scroll_y / max(self.panel_scroll_max, 1)
        thumb_y = track_rect.y + int((track_rect.height - thumb_height) * scroll_ratio)
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
        pygame.draw.rect(self.screen, self.colors['gray'], thumb_rect, border_radius=4)

    def _draw_generic_scrollbar(self, rect, scroll_y, scroll_max):
        if scroll_max <= 0:
            return
        track_rect = pygame.Rect(rect.right - 8, rect.y + 8, 4, max(24, rect.height - 16))
        pygame.draw.rect(self.screen, self.colors['panel_border'], track_rect, border_radius=4)
        thumb_height = max(28, int(track_rect.height * (rect.height / max(rect.height + scroll_max, 1))))
        scroll_ratio = scroll_y / max(scroll_max, 1)
        thumb_y = track_rect.y + int((track_rect.height - thumb_height) * scroll_ratio)
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_height)
        pygame.draw.rect(self.screen, self.colors['gray'], thumb_rect, border_radius=4)

    def _clamp_panel_scroll(self):
        self.panel_scroll_y = max(0, min(self.panel_scroll_y, self.panel_scroll_max))

    def _decision_page_state(self, role_key, specs):
        total_pages = max(1, int(math.ceil(len(specs) / max(1, self.decision_rows_per_page))))
        page_index = max(0, min(self.decision_page_index.get(role_key, 0), total_pages - 1))
        self.decision_page_index[role_key] = page_index
        start = page_index * self.decision_rows_per_page
        end = start + self.decision_rows_per_page
        return page_index, total_pages, specs[start:end]

    def _region_summary_lines(self, regions):
        if not regions:
            return ['未设置行为区域，保持默认地点逻辑。']
        lines = []
        for index, region in enumerate(regions[:4], start=1):
            lines.append(self._region_display_label(region, index=index))
        if len(regions) > 4:
            lines.append(f'其余 {len(regions) - 4} 个区域已省略显示')
        return lines

    def _region_display_label(self, region, index=None):
        prefix = f'{index}. ' if index is not None else ''
        shape = str(region.get('shape', 'rect'))
        if shape == 'circle':
            return f'{prefix}圆形 中心({int(region.get("cx", 0))},{int(region.get("cy", 0))}) 半径 {int(region.get("radius", 0))}'
        if shape == 'polygon':
            return f'{prefix}多边形 顶点 {len(region.get("points", []))} 个'
        return f'{prefix}矩形 ({int(region.get("x1", 0))},{int(region.get("y1", 0))}) - ({int(region.get("x2", 0))},{int(region.get("y2", 0))})'

    def _region_list_section_height(self, count):
        return 44 + max(1, count) * 34

    def _point_target_section_height(self, count):
        return 44 + max(1, count) * 36

    def _append_click_action(self, rect, action, clip_rect=None):
        click_rect = rect.clip(clip_rect) if clip_rect is not None else rect
        if click_rect.width > 0 and click_rect.height > 0:
            self.click_actions.append((click_rect, action))

    def _render_region_list_section(self, rect, title, regions, region_kind):
        pygame.draw.rect(self.screen, self.colors['white'], rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=8)
        title_surface = self.small_font.render(title, True, self.colors['panel_text'])
        self.screen.blit(title_surface, (rect.x + 10, rect.y + 8))
        if not regions:
            empty_surface = self.tiny_font.render('当前没有区域，地图或下方按钮可新增。', True, self.colors['gray'])
            self.screen.blit(empty_surface, (rect.x + 10, rect.y + 24 + title_surface.get_height()))
            return
        row_y = rect.y + 12 + title_surface.get_height()
        for index, region in enumerate(regions):
            row_rect = pygame.Rect(rect.x + 8, row_y, rect.width - 16, 28)
            is_selected = self.selected_region_kind == region_kind and self.selected_region_team == self.region_edit_team and self.selected_region_index == index
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if is_selected else self.colors['panel_row'], row_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['panel_border'], row_rect, 1, border_radius=6)
            label_surface = self.tiny_font.render(self._region_display_label(region, index=index + 1), True, self.colors['panel_text'])
            self.screen.blit(label_surface, (row_rect.x + 8, row_rect.y + 7))
            delete_rect = pygame.Rect(row_rect.right - 30, row_rect.y + 4, 22, 20)
            pygame.draw.rect(self.screen, self.colors['red'], delete_rect, border_radius=5)
            delete_text = self.tiny_font.render('删', True, self.colors['white'])
            self.screen.blit(delete_text, (delete_rect.x + (delete_rect.width - delete_text.get_width()) // 2, delete_rect.y + 3))
            self._append_click_action(row_rect, f'select_region:{region_kind}:{index}', clip_rect=self.panel_viewport_rect)
            self._append_click_action(delete_rect, f'delete_region:{region_kind}:{index}', clip_rect=self.panel_viewport_rect)
            row_y += 34

    def _render_point_target_section(self, rect, title, target_defs, targets):
        pygame.draw.rect(self.screen, self.colors['white'], rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=8)
        title_surface = self.small_font.render(title, True, self.colors['panel_text'])
        self.screen.blit(title_surface, (rect.x + 10, rect.y + 8))
        if not target_defs:
            empty_surface = self.tiny_font.render('当前决策没有可编辑目标点。', True, self.colors['gray'])
            self.screen.blit(empty_surface, (rect.x + 10, rect.y + 24 + title_surface.get_height()))
            return
        row_y = rect.y + 12 + title_surface.get_height()
        for item in target_defs:
            point_id = str(item.get('id', ''))
            point_spec = targets.get(point_id)
            row_rect = pygame.Rect(rect.x + 8, row_y, rect.width - 16, 30)
            active = self.point_edit_target == point_id
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], row_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['panel_border'], row_rect, 1, border_radius=6)
            label = str(item.get('label', point_id))
            if point_spec is None:
                value_text = '未设置'
            else:
                radius_text = f' / 范围 {int(point_spec.get("radius", 0) or 0)}' if point_spec.get('radius', None) not in {None, ''} else ''
                value_text = f'({int(point_spec.get("x", 0))}, {int(point_spec.get("y", 0))}){radius_text}'
            label_surface = self.tiny_font.render(f'{label}: {value_text}', True, self.colors['panel_text'])
            self.screen.blit(label_surface, (row_rect.x + 8, row_rect.y + 8))
            edit_rect = pygame.Rect(row_rect.right - 56, row_rect.y + 5, 22, 20)
            clear_rect = pygame.Rect(row_rect.right - 28, row_rect.y + 5, 22, 20)
            pygame.draw.rect(self.screen, self.colors['green'] if active else self.colors['blue'], edit_rect, border_radius=5)
            pygame.draw.rect(self.screen, self.colors['gray'] if point_spec is None else self.colors['orange'], clear_rect, border_radius=5)
            edit_text = self.tiny_font.render('设', True, self.colors['white'])
            clear_text = self.tiny_font.render('清', True, self.colors['white'])
            self.screen.blit(edit_text, (edit_rect.x + (edit_rect.width - edit_text.get_width()) // 2, edit_rect.y + 3))
            self.screen.blit(clear_text, (clear_rect.x + (clear_rect.width - clear_text.get_width()) // 2, clear_rect.y + 3))
            self._append_click_action(row_rect, f'edit_point_target:{point_id}', clip_rect=self.panel_viewport_rect)
            self._append_click_action(edit_rect, f'edit_point_target:{point_id}', clip_rect=self.panel_viewport_rect)
            if point_spec is not None:
                self._append_click_action(clear_rect, f'clear_point_target:{point_id}', clip_rect=self.panel_viewport_rect)
            row_y += 36

    def render_toolbar(self):
        pygame.draw.rect(self.screen, self.colors['toolbar'], (0, 0, self.window_width, self.toolbar_height))
        x = 10
        for label, action, active in (
            ('保存预设', 'save', False),
            ('应用到主程序', 'apply', False),
            ('重载预设', 'reload', False),
            ('编辑红方', 'edit_team:red', self.region_edit_team == 'red'),
            ('编辑蓝方', 'edit_team:blue', self.region_edit_team == 'blue'),
            ('中心对称到对方', 'mirror:to_opponent', False),
            ('矩形', 'shape:rect', self.shape_mode == 'rect'),
            ('圆形', 'shape:circle', self.shape_mode == 'circle'),
            ('多边形', 'shape:polygon', self.shape_mode == 'polygon'),
            ('清空当前覆盖', 'clear_override', False),
            ('删除命中区域', 'delete_region_at_cursor', False),
        ):
            x = self._toolbar_button(x, label, action, active=active)

        preset_rect = pygame.Rect(x + 6, 10, 180, self.toolbar_height - 20)
        active_input = self.active_text.input or {}
        pygame.draw.rect(self.screen, self.colors['white'], preset_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if active_input.get('field') == 'preset_name' else self.colors['panel_border'], preset_rect, 2, border_radius=6)
        preset_text = active_input.get('text', '') if active_input.get('field') == 'preset_name' else self.engine.preset_name
        rendered = self.base_font.render(preset_text or 'latest_behavior', True, self.colors['panel_text'])
        self.screen.blit(rendered, (preset_rect.x + 10, preset_rect.y + 8))
        self.click_actions.append((preset_rect, 'edit:preset_name'))

        hint_text = '绿色=行为区域 | 策略页可编辑 4 个顺序阶段'
        hint = self.tiny_font.render(hint_text, True, self.colors['toolbar_text'])
        hint_x = preset_rect.right + 14
        if hint_x + hint.get_width() <= self.window_width - 12:
            self.screen.blit(hint, (hint_x, 20))

    def render_map(self):
        map_area_rect = self.map_rect()
        map_rect = self.map_draw_rect()
        pygame.draw.rect(self.screen, self.colors['map_bg'], map_area_rect)
        pygame.draw.rect(self.screen, self.colors['panel_border'], map_area_rect, 1)
        surface = self._map_surface(map_rect.size)
        if surface is not None:
            self.screen.blit(surface, map_rect.topleft)
        pygame.draw.rect(self.screen, self.colors['panel_border'], map_rect, 1)
        self._render_facility_overlay()
        self._render_behavior_regions()
        self._render_selected_region_overlay()
        self._render_preview_target_regions()
        self._render_preview_units()
        self._render_drawing_preview()
        if self.mouse_world is not None:
            coord_text = self.tiny_font.render(f'世界坐标: ({int(self.mouse_world[0])}, {int(self.mouse_world[1])}) | 缩放 {self.map_zoom:.2f}x', True, self.colors['panel_text'])
            self.screen.blit(coord_text, (map_area_rect.x + 10, map_area_rect.bottom - coord_text.get_height() - 8))

    def _render_facility_overlay(self):
        for region in self.engine.map_manager.facilities:
            shape = region.get('shape', 'rect')
            color = self.colors['red'] if region.get('team') == 'red' else (self.colors['blue'] if region.get('team') == 'blue' else self.colors['gray'])
            if shape == 'polygon':
                points = [self.world_to_screen(point) for point in region.get('points', [])]
                points = [point for point in points if point is not None]
                if len(points) >= 3:
                    pygame.draw.polygon(self.screen, color, points, 1)
            elif shape == 'line':
                start = self.world_to_screen((region.get('x1', 0), region.get('y1', 0)))
                end = self.world_to_screen((region.get('x2', 0), region.get('y2', 0)))
                if start and end:
                    pygame.draw.line(self.screen, color, start, end, max(1, int(region.get('thickness', 8) * 0.08)))
            else:
                top_left = self.world_to_screen((region.get('x1', 0), region.get('y1', 0)))
                bottom_right = self.world_to_screen((region.get('x2', 0), region.get('y2', 0)))
                if top_left and bottom_right:
                    rect = pygame.Rect(top_left[0], top_left[1], max(1, bottom_right[0] - top_left[0]), max(1, bottom_right[1] - top_left[1]))
                    pygame.draw.rect(self.screen, color, rect, 1)

    def _render_region_collection(self, regions, color, width=3):
        for region in regions:
            shape = region.get('shape', 'rect')
            if shape == 'circle':
                center = self.world_to_screen((region.get('cx', region.get('x', 0)), region.get('cy', region.get('y', 0))))
                edge = self.world_to_screen((region.get('cx', 0) + region.get('radius', 0), region.get('cy', 0)))
                if center and edge:
                    radius = max(2, int(math.hypot(edge[0] - center[0], edge[1] - center[1])))
                    pygame.draw.circle(self.screen, color, center, radius, width)
            elif shape == 'polygon':
                points = [self.world_to_screen(point) for point in region.get('points', [])]
                points = [point for point in points if point is not None]
                if len(points) >= 3:
                    pygame.draw.polygon(self.screen, color, points, width)
            else:
                start = self.world_to_screen((region.get('x1', 0), region.get('y1', 0)))
                end = self.world_to_screen((region.get('x2', 0), region.get('y2', 0)))
                if start and end:
                    rect = pygame.Rect(
                        min(start[0], end[0]),
                        min(start[1], end[1]),
                        abs(end[0] - start[0]),
                        abs(end[1] - start[1]),
                    )
                    pygame.draw.rect(self.screen, color, rect, width)

    def _render_behavior_regions(self):
        if str(self.engine.current_strategy_stage(self.selected_strategy_stage_index).get('task_type', 'default') or 'default') == 'terrain_traversal':
            return
        self._render_region_collection(self.engine.current_behavior_regions(team=self.region_edit_team), self.colors['green'], width=3)

    def _render_point_targets_overlay(self):
        return

    def _render_selected_region_overlay(self):
        region = deepcopy(self.region_drag_state['preview']) if self.region_drag_state is not None else self._selected_region()
        if region is None:
            return
        self._render_region_collection([region], self.colors['orange'], width=4)
        for handle_point in self._region_handles(region).values():
            point = self.world_to_screen(handle_point)
            if point is None:
                continue
            pygame.draw.circle(self.screen, self.colors['white'], point, 6)
            pygame.draw.circle(self.screen, self.colors['orange'], point, 6, 2)

    def _render_preview_target_regions(self):
        plan = self.engine.preview_plan
        if plan is None:
            return
        map_rect = self.map_draw_rect()
        overlay = pygame.Surface(map_rect.size, pygame.SRCALPHA)
        for team, color_key in (('red', 'red'), ('blue', 'blue')):
            color = self.colors[color_key]
            fill_color = (*color, 42)
            outline_color = (*color, 160)
            for region in plan.get('teams', {}).get(team, {}).get('regions', []):
                shape = str(region.get('shape', 'rect'))
                if shape == 'circle':
                    center = self.world_to_screen((region.get('cx', region.get('x', 0)), region.get('cy', region.get('y', 0))))
                    edge = self.world_to_screen((region.get('cx', 0) + region.get('radius', 0), region.get('cy', 0)))
                    if center and edge:
                        local_center = (center[0] - map_rect.x, center[1] - map_rect.y)
                        radius = max(2, int(math.hypot(edge[0] - center[0], edge[1] - center[1])))
                        pygame.draw.circle(overlay, fill_color, local_center, radius)
                        pygame.draw.circle(overlay, outline_color, local_center, radius, 2)
                elif shape == 'polygon':
                    points = [self.world_to_screen(point) for point in region.get('points', [])]
                    points = [(point[0] - map_rect.x, point[1] - map_rect.y) for point in points if point is not None]
                    if len(points) >= 3:
                        pygame.draw.polygon(overlay, fill_color, points)
                        pygame.draw.polygon(overlay, outline_color, points, 2)
                else:
                    start = self.world_to_screen((region.get('x1', 0), region.get('y1', 0)))
                    end = self.world_to_screen((region.get('x2', 0), region.get('y2', 0)))
                    if start and end:
                        rect = pygame.Rect(
                            min(start[0], end[0]) - map_rect.x,
                            min(start[1], end[1]) - map_rect.y,
                            abs(end[0] - start[0]),
                            abs(end[1] - start[1]),
                        )
                        pygame.draw.rect(overlay, fill_color, rect)
                        pygame.draw.rect(overlay, outline_color, rect, 2)
        self.screen.blit(overlay, map_rect.topleft)

    def _render_drawing_preview(self):
        if self.shape_mode == 'polygon' and self.polygon_points:
            points = [self.world_to_screen(point) for point in self.polygon_points]
            points = [point for point in points if point is not None]
            preview_color = self.colors['green']
            if self.mouse_world is not None:
                preview_target = self._current_draw_target(self.mouse_world)
                target_point = self.world_to_screen(preview_target)
                if target_point is not None:
                    points.append(target_point)
            if len(points) >= 2:
                pygame.draw.lines(self.screen, preview_color, False, points, 2)
            for point in points[:-1] if len(points) > len(self.polygon_points) else points:
                pygame.draw.circle(self.screen, preview_color, point, 4)
            if len(self.polygon_points) >= 3:
                first_point = self.world_to_screen(self.polygon_points[0])
                if first_point is not None:
                    pygame.draw.circle(self.screen, self.colors['orange'], first_point, 6, 1)
            return
        if self.drag_start is None or self.drag_current is None:
            return
        start = self.world_to_screen(self.drag_start)
        end = self.world_to_screen(self.drag_current)
        if start is None or end is None:
            return
        preview_color = self.colors['green']
        if self.shape_mode == 'circle':
            radius = max(2, int(math.hypot(end[0] - start[0], end[1] - start[1])))
            pygame.draw.circle(self.screen, preview_color, start, radius, 2)
        else:
            rect = pygame.Rect(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]), abs(end[1] - start[1]))
            pygame.draw.rect(self.screen, preview_color, rect, 2)

    def _strategy_stage_summary(self, stage_index):
        stage = self.engine.current_strategy_stage(stage_index)
        if not stage:
            return f'阶段 {stage_index + 1}: 未启用'
        task_type = self.engine.current_strategy_task_type_label(stage_index)
        parts = [task_type]
        destination_mode = str(stage.get('destination_mode', 'region') or 'region')
        if destination_mode == 'none':
            parts.append('无目标地点')
        task_key = str(stage.get('task_type', 'default') or 'default')
        if task_key == 'assault':
            parts.append(self.engine.current_assault_ref_label(stage_index))
        if task_key == 'field_interaction':
            parts.append(self.engine.current_interaction_ref_label(stage_index))
        if task_key == 'defense':
            parts.append(self.engine.current_defense_ref_label(stage_index))
        if task_key == 'area_patrol':
            parts.append(f'{self.engine.current_engage_distance_text(stage_index)}m')
        return f'阶段 {stage_index + 1}: ' + ' / '.join(parts)

    def render_panel(self):
        panel_rect = self.panel_rect()
        pygame.draw.rect(self.screen, self.colors['panel'], panel_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.colors['panel_border'], panel_rect, 1, border_radius=10)
        inner_full = panel_rect.inflate(-16, -16)
        sidebar_width = 236
        inner = pygame.Rect(inner_full.x, inner_full.y, inner_full.width - sidebar_width - 12, inner_full.height)
        sidebar_rect = pygame.Rect(inner.right + 12, inner_full.y, sidebar_width, inner_full.height)
        y = inner.y
        title = self.title_font.render('行为决策编辑器', True, self.colors['panel_text'])
        self.screen.blit(title, (inner.x, y))
        y += title.get_height() + 10

        x = inner.x
        role_keys = self.engine.role_keys()
        for index, role_key in enumerate(role_keys):
            label = self._role_label(role_key)
            text = self.small_font.render(label, True, self.colors['panel_text'])
            rect = pygame.Rect(x, y, text.get_width() + 24, 28)
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if index == self.engine.selected_role_index else self.colors['panel_row'], rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['panel_border'], rect, 1, border_radius=6)
            self.screen.blit(text, (rect.x + 12, rect.y + 5))
            self.click_actions.append((rect, f'role:{index}'))
            x = rect.right + 8
        y += 40

        specs = self.engine.role_specs()
        role_key = self.engine.selected_role_key()
        header_rect = pygame.Rect(inner.x, y, inner.width, 28)
        header_text = self.small_font.render(f'决策列表 共 {len(specs)} 项', True, self.colors['panel_text'])
        self.screen.blit(header_text, (header_rect.x, header_rect.y + 4))
        if specs:
            move_up_rect = pygame.Rect(header_rect.right - 118, header_rect.y + 2, 50, 24)
            move_down_rect = pygame.Rect(header_rect.right - 60, header_rect.y + 2, 50, 24)
            pygame.draw.rect(self.screen, self.colors['panel_row'], move_up_rect, border_radius=5)
            pygame.draw.rect(self.screen, self.colors['panel_border'], move_up_rect, 1, border_radius=5)
            pygame.draw.rect(self.screen, self.colors['panel_row'], move_down_rect, border_radius=5)
            pygame.draw.rect(self.screen, self.colors['panel_border'], move_down_rect, 1, border_radius=5)
            up_text = self.tiny_font.render('上移', True, self.colors['panel_text'])
            down_text = self.tiny_font.render('下移', True, self.colors['panel_text'])
            self.screen.blit(up_text, (move_up_rect.x + (move_up_rect.width - up_text.get_width()) // 2, move_up_rect.y + 5))
            self.screen.blit(down_text, (move_down_rect.x + (move_down_rect.width - down_text.get_width()) // 2, move_down_rect.y + 5))
            self.click_actions.append((move_up_rect, 'decision_move:up'))
            self.click_actions.append((move_down_rect, 'decision_move:down'))
            hint_text = self.tiny_font.render('滚轮可上下滚动全部决策', True, self.colors['gray'])
            self.screen.blit(hint_text, (header_rect.right - hint_text.get_width() - 126, header_rect.y + 6))
        y += 30

        decision_row_height = 44
        decision_list_height = min(max(170, inner.height // 4), 280)
        list_rect = pygame.Rect(inner.x, y, inner.width, decision_list_height)
        pygame.draw.rect(self.screen, self.colors['white'], list_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], list_rect, 1, border_radius=8)
        list_viewport = list_rect.inflate(-6, -6)
        self.decision_list_viewport_rect = list_viewport
        total_height = len(specs) * (decision_row_height + 4)
        self.decision_list_scroll_max = max(0, total_height - list_viewport.height)
        self.decision_list_scroll_y = max(0, min(self.decision_list_scroll_y, self.decision_list_scroll_max))
        row_y = list_viewport.y - self.decision_list_scroll_y
        selected_index = self.engine.selected_decision_index.get(role_key, 0)
        clip_backup = self.screen.get_clip()
        self.screen.set_clip(list_viewport)
        for index, spec in enumerate(specs):
            row_rect = pygame.Rect(list_viewport.x, row_y, list_viewport.width, decision_row_height)
            self._decision_row(row_rect, spec['label'], spec['id'], action=f'decision:{index}', active=index == selected_index, clip_rect=list_viewport)
            row_y += decision_row_height + 4
        self.screen.set_clip(clip_backup)
        self._draw_generic_scrollbar(list_rect, self.decision_list_scroll_y, self.decision_list_scroll_max)
        y = list_rect.bottom + 12

        spec = self.engine.selected_spec()
        if spec is None:
            empty_rect = pygame.Rect(inner.x, y, inner.width, max(120, inner.bottom - y))
            pygame.draw.rect(self.screen, self.colors['white'], empty_rect, border_radius=8)
            pygame.draw.rect(self.screen, self.colors['panel_border'], empty_rect, 1, border_radius=8)
            empty_title = self.small_font.render('当前角色没有激活决策', True, self.colors['panel_text'])
            self.screen.blit(empty_title, (empty_rect.x + 12, empty_rect.y + 12))
            empty_hint = self.tiny_font.render('请在最右侧可选决策栏中开启一个或多个决策。', True, self.colors['gray'])
            self.screen.blit(empty_hint, (empty_rect.x + 12, empty_rect.y + 36))
            self._render_available_decision_sidebar(sidebar_rect)
            return
        override = self.engine.current_override(create=False) or {}

        tabs_y = y
        tab_x = inner.x
        for page_id, label in self.detail_pages:
            text = self.small_font.render(label, True, self.colors['panel_text'])
            tab_rect = pygame.Rect(tab_x, tabs_y, text.get_width() + 24, 28)
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if self.detail_page == page_id else self.colors['panel_row'], tab_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['panel_border'], tab_rect, 1, border_radius=6)
            self.screen.blit(text, (tab_rect.x + 12, tab_rect.y + 5))
            self.click_actions.append((tab_rect, f'panel_page:{page_id}'))
            tab_x = tab_rect.right + 8
        y += 40

        viewport_rect = pygame.Rect(inner.x, y, inner.width, max(120, inner.bottom - y))
        pygame.draw.rect(self.screen, self.colors['white'], viewport_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], viewport_rect, 1, border_radius=8)
        self._draw_scroll_hint(viewport_rect)

        active_input = self.active_text.input or {}
        selected_stage_index = max(0, min(self.selected_strategy_stage_index, self.engine.MAX_STRATEGY_STAGES - 1))
        self.selected_strategy_stage_index = selected_stage_index
        implementation_details = self.engine.current_decision_implementation_details()
        collision_profile = self.engine.current_collision_profile()
        edit_values = {
            'label': active_input.get('text', '') if active_input.get('field') == 'label' else str(override.get('label', '')),
            'brief': active_input.get('text', '') if active_input.get('field') == 'brief' else str(override.get('brief', '')),
            'trigger_note': active_input.get('text', '') if active_input.get('field') == 'trigger_note' else str(override.get('trigger_note', '')),
            'logic_note': active_input.get('text', '') if active_input.get('field') == 'logic_note' else str(override.get('logic_note', '')),
            'function_note': active_input.get('text', '') if active_input.get('field') == 'function_note' else str(override.get('function_note', '')),
            'condition_expr': active_input.get('text', '') if active_input.get('field') == 'condition_expr' else str(override.get('condition_expr', '')),
            'start_sec': active_input.get('text', '') if active_input.get('field') == 'start_sec' else str((override.get('time_window') or {}).get('start_sec', '')),
            'end_sec': active_input.get('text', '') if active_input.get('field') == 'end_sec' else str((override.get('time_window') or {}).get('end_sec', '')),
            'engage_distance_m': active_input.get('text', '') if active_input.get('field') == f'engage_distance_m:{selected_stage_index}' else self.engine.current_engage_distance_text(selected_stage_index),
        }
        for collision_spec in self.engine.COLLISION_FIELD_SPECS:
            collision_field = f'collision:{collision_spec["key"]}'
            if active_input.get('field') == collision_field:
                edit_values[collision_field] = active_input.get('text', '')
            elif collision_profile is not None:
                edit_values[collision_field] = str(collision_profile.get(collision_spec['key'], ''))
            else:
                edit_values[collision_field] = '当前角色无实体碰撞配置'

        self._clamp_panel_scroll()
        self.panel_viewport_rect = viewport_rect
        clip_backup = self.screen.get_clip()
        self.screen.set_clip(viewport_rect)

        footer_height = 72
        base_content_y = viewport_rect.y + 10 - self.panel_scroll_y
        card_y = base_content_y
        card_h_small = 66
        card_h_medium = 84
        card_h_large = 126
        current_label = override.get('label', spec['label'])
        if self.detail_page == 'overview':
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '决策 ID', [spec['id']])
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_medium), '当前标签', [current_label])
            card_y += card_h_medium + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_medium), '决策简述', [edit_values['brief'] or '未填写'], action='edit:brief', active=True)
            card_y += card_h_medium + 8
            half_width = (viewport_rect.width - 28) // 2
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, half_width, card_h_small), '启用状态', [self.engine.current_enabled_label()], action='toggle:enabled', active=True)
            self._panel_card(pygame.Rect(viewport_rect.x + 18 + half_width, card_y, half_width, card_h_small), '区域模式', [self.engine.current_region_mode_label()], action='toggle:region_mode')
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 92), '覆盖说明', [
                '未修改的字段保持默认行为树逻辑。',
                '已覆盖的标签、简述、时间、条件、策略和行为区域会在运行时叠加到默认决策上。',
            ])
            card_y += 100
        elif self.detail_page == 'condition':
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '启用状态', [self.engine.current_enabled_label()], action='toggle:enabled', active=True)
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '自定义标签', [edit_values['label'] or '默认'], action='edit:label', active=True)
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_large), '条件表达式', [edit_values['condition_expr'] or '默认'], action='edit:condition_expr', active=True)
            card_y += card_h_large + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 102), '可用变量示例', [
                'game_time >= 30 and has_target',
                'hero_ranged and enemy_outpost_alive',
                'health_ratio < 0.45 or outnumbered',
            ])
            card_y += 110
        elif self.detail_page == 'strategy':
            strategy = self.engine.current_strategy_stage(selected_stage_index)
            task_type = str(strategy.get('task_type', 'default'))
            destination_mode = str(strategy.get('destination_mode', 'region'))
            stage_card_width = (viewport_rect.width - 28) // 2
            stage_card_height = 62
            for stage_slot_index in range(self.engine.MAX_STRATEGY_STAGES):
                stage_rect = pygame.Rect(
                    viewport_rect.x + 10 + (stage_slot_index % 2) * (stage_card_width + 8),
                    card_y + (stage_slot_index // 2) * (stage_card_height + 8),
                    stage_card_width,
                    stage_card_height,
                )
                self._panel_card(
                    stage_rect,
                    f'阶段 {stage_slot_index + 1}',
                    [self._strategy_stage_summary(stage_slot_index)],
                    action=f'strategy_stage:select:{stage_slot_index}',
                    active=selected_stage_index == stage_slot_index,
                )
            card_y += stage_card_height * 2 + 24
            half_width = (viewport_rect.width - 28) // 2
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, half_width, card_h_small), '当前编辑阶段', [f'阶段 {selected_stage_index + 1}'], active=True)
            self._panel_card(pygame.Rect(viewport_rect.x + 18 + half_width, card_y, half_width, card_h_small), '清空当前阶段', ['移除该阶段并压缩后续顺序'], action=f'strategy_stage:clear:{selected_stage_index}')
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '任务目标类型', [self.engine.current_strategy_task_type_label(selected_stage_index)], action=f'cycle:strategy_task_type:{selected_stage_index}', active=True)
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '目标地点类型', [self.engine.current_destination_mode_label(selected_stage_index)], action=f'cycle:destination_mode:{selected_stage_index}', active=True)
            card_y += card_h_small + 8
            if task_type == 'assault':
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_medium), '进攻对象', [self.engine.current_assault_ref_label(selected_stage_index)], action=f'cycle:assault_ref:{selected_stage_index}', active=True)
                card_y += card_h_medium + 8
            if task_type == 'field_interaction':
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_medium), '交互目标', [self.engine.current_interaction_ref_label(selected_stage_index)], action=f'cycle:interaction_ref:{selected_stage_index}', active=True)
                card_y += card_h_medium + 8
            if task_type == 'defense':
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_medium), '防守目标', [self.engine.current_defense_ref_label(selected_stage_index)], action=f'cycle:defense_ref:{selected_stage_index}', active=True)
                card_y += card_h_medium + 8
            if task_type == 'area_patrol':
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '触敌距离（米）', [edit_values['engage_distance_m']], action=f'edit:engage_distance_m:{selected_stage_index}', active=True)
                card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 144), '策略说明', [
                '一个决策最多可配置 4 个顺序阶段，会按阶段 1 到 4 依次执行。',
                '地形跨越类：使用跨越节点 1 到 4，节点自带生效范围，不再额外叠目标区域。',
                '进攻类：可设置进攻对象。',
                '场地交互类：支持补给、取矿、激活能量机关。',
                '防守类：需要先配置行为区域，再选择高威胁敌人或回防基地。',
                '区域巡航类：在行为区域内随机巡航，触敌距离可单独配置。',
                '目标地点可设置为行为区域，也可以明确关闭。',
            ])
            card_y += 152
        elif self.detail_page == 'region':
            behavior_regions = self.engine.current_behavior_regions(team=self.region_edit_team)
            edit_team_label = '红方' if self.region_edit_team == 'red' else '蓝方'
            terrain_stage_active = str(self.engine.current_strategy_stage(selected_stage_index).get('task_type', 'default') or 'default') == 'terrain_traversal'
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '当前编辑队伍', [edit_team_label], action=f'edit_team:{self.region_edit_team}', active=True)
            card_y += card_h_small + 8
            if not terrain_stage_active:
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '行为区域数量', [f'{len(behavior_regions)} 个区域'])
                card_y += card_h_small + 8
                behavior_rect = pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, self._region_list_section_height(len(behavior_regions)))
                self._render_region_list_section(behavior_rect, f'行为区域列表（{edit_team_label}）', behavior_regions, 'behavior')
                card_y += behavior_rect.height + 8
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '区域模式', [self.engine.current_region_mode_label()], action='toggle:region_mode', active=True)
                card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 122), '绘制说明', [
                '绿色区域表示统一的行为区域。',
                '地形跨越类当前不再使用旧目标点/节点预设。',
                '工具栏可切换当前红蓝双方。',
                '矩形/圆形：左键拖拽完成；多边形：左键逐点添加，点回起点或 Enter 收尾。',
                '点击已有区域可选中并拖拽编辑，右侧列表也可直接选中或删除。',
            ])
            card_y += 130
        elif self.detail_page == 'collision':
            role_key = self.engine.selected_role_key()
            if collision_profile is None:
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 96), '当前角色', [
                    f'{self._role_label(role_key)} 不对应具体机器人实体。',
                    '通用角色没有独立碰撞箱配置。',
                ])
                card_y += 104
            else:
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 92), '碰撞箱说明', [
                    '这里编辑的是机器人运行时底盘碰撞参数，会写入 appearance preset。',
                    '修改后主程序按住 F3 可直接查看碰撞箱。',
                    '长度、宽度、离地间隙和轮半径也会影响底盘模型与越障表现。',
                ])
                card_y += 100
                half_width = (viewport_rect.width - 28) // 2
                for field_index, collision_spec in enumerate(self.engine.COLLISION_FIELD_SPECS):
                    row_index = field_index // 2
                    col_index = field_index % 2
                    field_rect = pygame.Rect(
                        viewport_rect.x + 10 + col_index * (half_width + 8),
                        card_y + row_index * (card_h_small + 8),
                        half_width,
                        card_h_small,
                    )
                    collision_field = f'collision:{collision_spec["key"]}'
                    self._panel_card(field_rect, collision_spec['label'], [edit_values[collision_field]], action=f'edit:{collision_field}', active=True)
                card_y += ((len(self.engine.COLLISION_FIELD_SPECS) + 1) // 2) * (card_h_small + 8)
                self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 88), '当前角色碰撞摘要', [
                    f'角色: {self._role_label(role_key)}',
                    f"长 {float(collision_profile.get('body_length_m', 0.0)):.2f}m / 宽 {float(collision_profile.get('body_width_m', 0.0)):.2f}m / 高 {float(collision_profile.get('body_height_m', 0.0)):.2f}m",
                    f"碰撞半径 {float(collision_profile.get('collision_radius', 0.0)):.1f}   轮半径 {float(collision_profile.get('wheel_radius_m', 0.0)):.2f}m",
                    f'保存位置: {self.engine.appearance_preset_path}',
                ])
                card_y += 96
        elif self.detail_page == 'implementation':
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 108), '系统触发说明', implementation_details.get('trigger_lines', []))
            card_y += 116
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 132), '系统运行逻辑', implementation_details.get('logic_lines', []))
            card_y += 140
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 128), '调用函数与代码入口', implementation_details.get('function_lines', []))
            card_y += 136
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 180), '可修改接口', implementation_details.get('interface_lines', []))
            card_y += 188
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_medium), '你写的触发说明', [edit_values['trigger_note'] or '点击这里填写你自己的触发说明'], action='edit:trigger_note', active=True)
            card_y += card_h_medium + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_large), '你写的运行逻辑说明', [edit_values['logic_note'] or '点击这里填写你自己的运行逻辑说明'], action='edit:logic_note', active=True)
            card_y += card_h_large + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_large), '你写的函数说明 / 修改备注', [edit_values['function_note'] or '点击这里填写函数说明、改造思路或代码修改备注'], action='edit:function_note', active=True)
            card_y += card_h_large + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 102), '说明', [
                '上半部分是系统自动解析的插件说明、触发入口、动作入口和代码位置。',
                '下半部分是你可以直接修改并保存到行为预设里的说明字段。',
                '如果你要改真正的实现代码，请按上面的文件与函数入口到对应源码里修改。',
            ])
            card_y += 110

        log_rect = pygame.Rect(viewport_rect.x, card_y + 8, viewport_rect.width, footer_height)
        pygame.draw.rect(self.screen, self.colors['panel_row'], log_rect, border_radius=8)
        pygame.draw.rect(self.screen, self.colors['panel_border'], log_rect, 1, border_radius=8)
        log_title = self.small_font.render('最近操作', True, self.colors['panel_text'])
        self.screen.blit(log_title, (log_rect.x + 10, log_rect.y + 8))
        log_y = log_rect.y + 10 + log_title.get_height()
        for log in self.engine.logs[-3:]:
            log_lines = self._wrap_text(log, self.tiny_font, log_rect.width - 20, max_lines=2)
            log_y = self._draw_text_lines(log_lines, self.tiny_font, self.colors['gray'], log_rect.x + 10, log_y, line_gap=2, max_height=log_rect.bottom - 6) + 2

        self.screen.set_clip(clip_backup)
        self.panel_scroll_max = max(0, log_rect.bottom + 10 - viewport_rect.y - viewport_rect.height)
        self._clamp_panel_scroll()
        self._draw_scrollbar(viewport_rect)
        self.panel_viewport_rect = None
        self._render_available_decision_sidebar(sidebar_rect)

    def commit_text_input(self):
        if self.active_text.input is None:
            return False
        field = self.active_text.input.get('field')
        text = str(self.active_text.input.get('text', ''))
        if field == 'preset_name':
            self.engine.preset_name = text.strip() or 'latest_behavior'
            self.engine._persist_live_changes(f'主程序已切换行为预设: {self.engine.preset_name}')
        elif field in {'label', 'condition_expr', 'brief', 'trigger_note', 'logic_note', 'function_note'}:
            self.engine.set_override_field(field, text)
        elif str(field).startswith('engage_distance_m:'):
            try:
                stage_index = int(str(field).split(':', 1)[1])
            except ValueError:
                stage_index = self.selected_strategy_stage_index
            value = text.strip()
            if not value:
                self.engine.set_strategy_field('engage_distance_m', None, stage_index=stage_index)
            else:
                try:
                    self.engine.set_strategy_field('engage_distance_m', float(value), stage_index=stage_index)
                except ValueError:
                    self.engine.add_log('触敌距离不是有效数字，已保留原值')
        elif field in {'start_sec', 'end_sec'}:
            value = text.strip()
            if not value:
                self.engine.set_override_field(field, None)
            else:
                try:
                    self.engine.set_override_field(field, float(value))
                except ValueError:
                    self.engine.add_log(f'{field} 不是有效数字，已保留原值')
        elif str(field).startswith('collision:'):
            collision_field = str(field).split(':', 1)[1]
            try:
                self.engine.set_collision_field(collision_field, float(text.strip()))
            except ValueError:
                self.engine.add_log(f'{collision_field} 不是有效数字，已保留原值')
        self.active_text.input = None
        return True

    def handle_text_input_key(self, event):
        if self.active_text.input is None:
            return False
        if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER}:
            self.commit_text_input()
            return True
        if event.key == pygame.K_ESCAPE:
            self.active_text.input = None
            return True
        if event.key == pygame.K_BACKSPACE:
            self.active_text.input['text'] = self.active_text.input.get('text', '')[:-1]
            return True
        if event.key == pygame.K_DELETE:
            self.active_text.input['text'] = ''
            return True
        if event.unicode and event.unicode.isprintable():
            self.active_text.input['text'] = self.active_text.input.get('text', '') + event.unicode
            return True
        return True

    def _handle_action(self, action):
        if action == 'save':
            self.commit_text_input()
            self.engine.save_preset(self.engine.preset_name)
            return
        if action == 'apply':
            self.commit_text_input()
            self.engine.apply_preset(self.engine.preset_name)
            return
        if action == 'reload':
            self.commit_text_input()
            self.engine.reload_preset(self.engine.preset_name)
            return
        if action.startswith('shape:'):
            self.shape_mode = action.split(':', 1)[1]
            self.drag_start = None
            self.drag_current = None
            if self.shape_mode != 'polygon':
                self.polygon_points = []
            self.region_drag_state = None
            return
        if action.startswith('edit_team:'):
            self.region_edit_team = action.split(':', 1)[1]
            self.point_edit_target = None
            self._clear_region_selection()
            return
        if action == 'mirror:to_opponent':
            self.engine.mirror_current_team_to_opponent(self.region_edit_team)
            self._clear_region_selection()
            return
        if action == 'preview:toggle':
            if self.preview_loop_active:
                self.preview_loop_active = False
                self.engine.preview_feedback = ['已停止预演']
            else:
                self._restart_preview_cycle()
            return
        if action.startswith('toggle_decision:'):
            self.engine.toggle_role_decision(action.split(':', 1)[1])
            self.preview_loop_active = False
            self.sidebar_list_scroll_y = max(0, min(self.sidebar_list_scroll_y, self.sidebar_list_scroll_max))
            self.decision_list_scroll_y = max(0, min(self.decision_list_scroll_y, self.decision_list_scroll_max))
            self.selected_strategy_stage_index = 0
            self._clear_region_selection()
            return
        if action.startswith('decision_move:'):
            spec = self.engine.selected_spec()
            if spec is None:
                return
            direction = -1 if action.endswith('up') else 1
            self.engine.move_role_decision(spec['id'], direction)
            return
        if action.startswith('role:'):
            self.engine.selected_role_index = int(action.split(':', 1)[1])
            self.panel_scroll_y = 0
            self.decision_list_scroll_y = 0
            self.sidebar_list_scroll_y = 0
            self.preview_loop_active = False
            self.selected_strategy_stage_index = 0
            self._clear_region_selection()
            return
        if action.startswith('decision:'):
            self.engine.selected_decision_index[self.engine.selected_role_key()] = int(action.split(':', 1)[1])
            self.detail_page = 'overview'
            self.panel_scroll_y = 0
            self.preview_loop_active = False
            self.selected_strategy_stage_index = 0
            self._clear_region_selection()
            return
        if action.startswith('decision_page:'):
            role_key = self.engine.selected_role_key()
            specs = self.engine.role_specs(role_key)
            page_index, total_pages, _ = self._decision_page_state(role_key, specs)
            direction = -1 if action.endswith('prev') else 1
            self.decision_page_index[role_key] = max(0, min(total_pages - 1, page_index + direction))
            return
        if action.startswith('panel_page:'):
            self.detail_page = action.split(':', 1)[1]
            self.panel_scroll_y = 0
            return
        if action.startswith('strategy_stage:select:'):
            self.selected_strategy_stage_index = max(0, min(self.engine.MAX_STRATEGY_STAGES - 1, int(action.rsplit(':', 1)[1])))
            return
        if action.startswith('strategy_stage:clear:'):
            self.engine.clear_strategy_stage(int(action.rsplit(':', 1)[1]))
            self.selected_strategy_stage_index = max(0, min(self.selected_strategy_stage_index, self.engine.MAX_STRATEGY_STAGES - 1))
            return
        if action.startswith('select_region:'):
            _, region_kind, raw_index = action.split(':', 2)
            self.region_edit_target = 'behavior'
            self.point_edit_target = None
            self._set_selected_region(region_kind, int(raw_index), region_team=self.region_edit_team)
            return
        if action.startswith('delete_region:'):
            _, region_kind, raw_index = action.split(':', 2)
            if self.engine.remove_region_at_index(int(raw_index), region_kind=region_kind, log_message='已删除区域覆盖', team=self.region_edit_team):
                if self.selected_region_kind == region_kind and self.selected_region_team == self.region_edit_team and self.selected_region_index == int(raw_index):
                    self._clear_region_selection()
            return
        if action.startswith('edit:'):
            parts = action.split(':')
            field = ':'.join(parts[1:])
            override = self.engine.current_override(create=False) or {}
            if field in {'label', 'condition_expr', 'brief', 'trigger_note', 'logic_note', 'function_note'}:
                text = str(override.get(field, ''))
            elif field.startswith('collision:'):
                collision_profile = self.engine.current_collision_profile() or {}
                text = str(collision_profile.get(field.split(':', 1)[1], ''))
            elif field.startswith('engage_distance_m:'):
                try:
                    stage_index = int(field.split(':', 1)[1])
                except ValueError:
                    stage_index = self.selected_strategy_stage_index
                text = self.engine.current_engage_distance_text(stage_index)
            elif field in {'start_sec', 'end_sec'}:
                text = str((override.get('time_window') or {}).get(field, ''))
            else:
                text = self.engine.preset_name
            self.active_text.input = {'field': field, 'text': text}
            return
        if action == 'toggle:enabled':
            self.engine.cycle_enabled_state()
            return
        if action == 'toggle:region_mode':
            self.engine.cycle_region_mode()
            return
        if action.startswith('cycle:strategy_task_type:'):
            self.engine.cycle_strategy_field('task_type', stage_index=int(action.rsplit(':', 1)[1]))
            return
        if action.startswith('cycle:destination_mode:'):
            self.engine.cycle_strategy_field('destination_mode', stage_index=int(action.rsplit(':', 1)[1]))
            return
        if action.startswith('cycle:assault_ref:'):
            self.engine.cycle_strategy_field('assault_ref', stage_index=int(action.rsplit(':', 1)[1]))
            return
        if action.startswith('cycle:assault_follow_priority:'):
            self.engine.cycle_strategy_field('assault_follow_priority', stage_index=int(action.rsplit(':', 1)[1]))
            return
        if action.startswith('cycle:interaction_ref:'):
            self.engine.cycle_strategy_field('interaction_ref', stage_index=int(action.rsplit(':', 1)[1]))
            return
        if action.startswith('cycle:defense_ref:'):
            self.engine.cycle_strategy_field('defense_ref', stage_index=int(action.rsplit(':', 1)[1]))
            return
        if action == 'clear_override':
            self.engine.clear_current_override()
            self.point_edit_target = None
            self.selected_strategy_stage_index = 0
            self._clear_region_selection()
            return
        if action == 'delete_region_at_cursor' and self.mouse_world is not None:
            if self.selected_region_kind == self.region_edit_target and self.selected_region_team == self.region_edit_team and self.selected_region_index is not None:
                if self.engine.remove_region_at_index(self.selected_region_index, region_kind=self.region_edit_target, log_message='已删除区域覆盖', team=self.region_edit_team):
                    self._clear_region_selection()
                    self.engine.add_log('已删除选中区域')
            elif self.engine.remove_region_at_point(self.mouse_world, region_kind=self.region_edit_target, team=self.region_edit_team):
                self.engine.add_log('已删除命中的区域')
            return

    def finalize_drawn_region(self):
        add_region = self.engine.add_behavior_region
        region_label = '行为区域'
        if self.shape_mode == 'polygon':
            if len(self.polygon_points) >= 3:
                add_region({'shape': 'polygon', 'points': [(round(point[0], 1), round(point[1], 1)) for point in self.polygon_points]}, team=self.region_edit_team)
                self.engine.add_log(f'已添加多边形{region_label}')
            self.polygon_points = []
            self._clear_region_selection()
            return
        if self.drag_start is None or self.drag_current is None:
            return
        start = self.drag_start
        end = self.drag_current
        if self.shape_mode == 'circle':
            radius = math.hypot(end[0] - start[0], end[1] - start[1])
            if radius >= 4.0:
                add_region({'shape': 'circle', 'cx': round(start[0], 1), 'cy': round(start[1], 1), 'radius': round(radius, 1)}, team=self.region_edit_team)
                self.engine.add_log(f'已添加圆形{region_label}')
        else:
            if abs(end[0] - start[0]) >= 2.0 and abs(end[1] - start[1]) >= 2.0:
                add_region({
                    'shape': 'rect',
                    'x1': round(min(start[0], end[0]), 1),
                    'y1': round(min(start[1], end[1]), 1),
                    'x2': round(max(start[0], end[0]), 1),
                    'y2': round(max(start[1], end[1]), 1),
                }, team=self.region_edit_team)
                self.engine.add_log(f'已添加矩形{region_label}')
        self.drag_start = None
        self.drag_current = None
        self._clear_region_selection()

    def run(self):
        self.running = True
        self.engine.add_log('行为编辑器已启动')
        self.render()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    continue
                if event.type == pygame.KEYDOWN:
                    if self.handle_text_input_key(event):
                        continue
                    if event.key == pygame.K_ESCAPE:
                        if self.shape_mode == 'polygon' and self.polygon_points:
                            self.polygon_points = []
                        else:
                            self.running = False
                        continue
                    if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER} and self.shape_mode == 'polygon' and len(self.polygon_points) >= 3:
                        self.finalize_drawn_region()
                        continue
                    if event.key == pygame.K_BACKSPACE and self.shape_mode == 'polygon' and self.polygon_points:
                        self.polygon_points.pop()
                        continue
                if event.type == pygame.MOUSEMOTION:
                    self.mouse_world = self.screen_to_world(event.pos)
                    if self.region_drag_state is not None and self.mouse_world is not None:
                        self._update_region_drag_preview(self.mouse_world)
                    if self.drag_start is not None and self.shape_mode in {'rect', 'circle'}:
                        self.drag_current = self._current_draw_target(self.mouse_world)
                if event.type == pygame.MOUSEWHEEL:
                    mouse_pos = pygame.mouse.get_pos()
                    if self.map_draw_rect().collidepoint(mouse_pos):
                        self._zoom_map_around(mouse_pos, event.y)
                        self.mouse_world = self.screen_to_world(mouse_pos)
                        continue
                    if self.sidebar_list_viewport_rect is not None and self.sidebar_list_viewport_rect.collidepoint(mouse_pos):
                        self.sidebar_list_scroll_y -= int(event.y) * self.list_scroll_step
                        self.sidebar_list_scroll_y = max(0, min(self.sidebar_list_scroll_y, self.sidebar_list_scroll_max))
                        continue
                    if self.decision_list_viewport_rect is not None and self.decision_list_viewport_rect.collidepoint(mouse_pos):
                        self.decision_list_scroll_y -= int(event.y) * self.list_scroll_step
                        self.decision_list_scroll_y = max(0, min(self.decision_list_scroll_y, self.decision_list_scroll_max))
                        continue
                    if self.panel_rect().collidepoint(mouse_pos):
                        self.panel_scroll_y -= int(event.y) * self.panel_scroll_step
                        self._clamp_panel_scroll()
                        continue
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    handled = False
                    for rect, action in reversed(self.click_actions):
                        if rect.collidepoint(event.pos):
                            self._handle_action(action)
                            handled = True
                            break
                    if handled:
                        continue
                    world_point = self.screen_to_world(event.pos)
                    self.mouse_world = world_point
                    if world_point is None:
                        if self.active_text.input is not None:
                            self.commit_text_input()
                        continue
                    if self.shape_mode == 'polygon' and self.polygon_points:
                        world_point = self._current_draw_target(world_point)
                        if self.polygon_points and len(self.polygon_points) >= 3 and self._world_distance(world_point, self.polygon_points[0]) <= 18.0:
                            self.finalize_drawn_region()
                        else:
                            self._append_polygon_point(world_point)
                    elif self._begin_region_drag(world_point):
                        self.drag_start = None
                        self.drag_current = None
                    elif self.shape_mode == 'polygon':
                        world_point = self._current_draw_target(world_point)
                        self._append_polygon_point(world_point)
                    else:
                        self._clear_region_selection()
                        self.drag_start = world_point
                        self.drag_current = world_point
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.region_drag_state is not None:
                    self._commit_region_drag()
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.shape_mode in {'rect', 'circle'}:
                    self.drag_current = self._current_draw_target(self.screen_to_world(event.pos))
                    self.finalize_drawn_region()
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if self.point_edit_target is not None:
                        self.point_edit_target = None
                        continue
                    if self.shape_mode == 'polygon' and self.polygon_points:
                        if len(self.polygon_points) >= 3:
                            self.finalize_drawn_region()
                        else:
                            self.polygon_points = []
                            self.drag_current = None
                            self.engine.add_log('多边形顶点不足，已取消')
                        continue
                    world_point = self.screen_to_world(event.pos)
                    self.mouse_world = world_point
                    if world_point is not None and self.engine.remove_region_at_point(world_point, region_kind=self.region_edit_target, team=self.region_edit_team):
                        self._clear_region_selection()
                        self.engine.add_log('已删除命中的区域')

            self.render()
            self.clock.tick(60)

        pygame.quit()

    def render(self):
        self.click_actions = []
        self.screen.fill(self.colors['bg'])
        self.render_toolbar()
        self.render_map()
        self.render_panel()
        pygame.display.flip()


def main():
    engine = BehaviorEditorEngine()
    app = BehaviorEditorApp(engine)
    app.run()


if __name__ == '__main__':
    main()