#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import os
import sys
from copy import deepcopy
from datetime import datetime

from pygame_compat import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from control.ai_controller import AIController
from core.config_manager import ConfigManager
from entities.entity import Entity
from map.map_manager import MapManager


class BehaviorEditorEngine:
    ROLE_ORDER = ('sentry', 'infantry', 'hero', 'engineer')
    ROLE_PREVIEW_ENTITY_IDS = {
        'hero': 'robot_1',
        'engineer': 'robot_2',
        'infantry': 'robot_3',
        'sentry': 'robot_7',
    }
    REGION_MODE_LABELS = {
        'enter_then_execute': '先进入区域再执行',
        'strict_inside': '仅在区域内触发',
    }

    def __init__(self, config_path='config.json', settings_path='settings.json'):
        self.config_path = config_path
        self.settings_path = settings_path
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load_config(config_path, settings_path)
        self.config['_config_path'] = config_path
        self.config['_settings_path'] = settings_path
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
        if isinstance(payload, dict):
            payload.setdefault('version', 1)
            payload.setdefault('name', str(preset_name))
            payload.setdefault('roles', {})
            return payload
        return self._empty_payload(preset_name)

    def role_keys(self):
        return tuple(role_key for role_key in self.ROLE_ORDER if self.ai_controller.get_available_decision_plugins(role_key))

    def role_label(self, role_key):
        return {'sentry': '哨兵', 'infantry': '步兵', 'hero': '英雄', 'engineer': '工程'}.get(role_key, role_key)

    def selected_role_key(self):
        role_keys = self.role_keys()
        if not role_keys:
            return 'hero'
        self.selected_role_index = max(0, min(self.selected_role_index, len(role_keys) - 1))
        return role_keys[self.selected_role_index]

    def role_specs(self, role_key=None):
        role = role_key or self.selected_role_key()
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
        if spec['id'] not in decisions and create:
            decisions[spec['id']] = {}
        return decisions.get(spec['id'])

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
        if not isinstance(point_targets, dict):
            return {}
        normalized = {}
        for key, value in point_targets.items():
            if not isinstance(key, str) or not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            try:
                normalized[key] = [round(float(value[0]), 1), round(float(value[1]), 1)]
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

    def _override_is_default(self, normalized):
        return (
            not normalized.get('label')
            and 'enabled' not in normalized
            and not normalized.get('condition_expr')
            and not normalized.get('time_window')
            and not normalized.get('task_regions')
            and not normalized.get('destination_regions')
            and not normalized.get('task_regions_by_team')
            and not normalized.get('destination_regions_by_team')
            and not normalized.get('point_targets')
            and not normalized.get('point_targets_by_team')
            and normalized.get('region_mode', 'enter_then_execute') == 'enter_then_execute'
        )

    def _normalize_override(self, override):
        override = deepcopy(override or {})
        if 'time_window' in override and not isinstance(override['time_window'], dict):
            override.pop('time_window', None)
        task_regions = self._normalize_region_list(override.get('task_regions', []))
        if task_regions:
            override['task_regions'] = task_regions
        else:
            override.pop('task_regions', None)
        destination_regions = self._normalize_region_list(override.get('destination_regions', []))
        if destination_regions:
            override['destination_regions'] = destination_regions
        else:
            override.pop('destination_regions', None)
        task_regions_by_team = self._normalize_team_region_map(override.get('task_regions_by_team', {}))
        if task_regions_by_team:
            override['task_regions_by_team'] = task_regions_by_team
        else:
            override.pop('task_regions_by_team', None)
        destination_regions_by_team = self._normalize_team_region_map(override.get('destination_regions_by_team', {}))
        if destination_regions_by_team:
            override['destination_regions_by_team'] = destination_regions_by_team
        else:
            override.pop('destination_regions_by_team', None)
        point_targets = self._normalize_point_target_map(override.get('point_targets', {}))
        if point_targets:
            override['point_targets'] = point_targets
        else:
            override.pop('point_targets', None)
        point_targets_by_team = self._normalize_team_point_target_map(override.get('point_targets_by_team', {}))
        if point_targets_by_team:
            override['point_targets_by_team'] = point_targets_by_team
        else:
            override.pop('point_targets_by_team', None)
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
            if decision is None:
                decision = {
                    'summary': '当前预演态势下未生成动作，回退到默认目的地预览' if action_error is None else '预演执行异常，已回退到默认目的地预览',
                    'navigation_target': fallback_target,
                    'movement_target': fallback_target,
                    'velocity': (0.0, 0.0),
                    'chassis_state': 'normal',
                    'turret_state': 'searching',
                }
            navigation_target = decision.get('navigation_target') or decision.get('movement_target') or fallback_target
            if navigation_target is None:
                navigation_target = (float(actor.position['x']), float(actor.position['y']))
            region_candidates = []
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
            plan['teams'][team] = {
                'entity_id': actor.id,
                'start': (float(actor.position['x']), float(actor.position['y'])),
                'target': (float(navigation_target[0]), float(navigation_target[1])),
                'regions': region_candidates,
                'summary': str(decision.get('summary', '')),
                'result': str(result),
                'chassis_state': str(decision.get('chassis_state', 'normal')),
                'turret_state': str(decision.get('turret_state', 'searching')),
            }
            if action_error is None:
                feedback_lines.append(f"{team.upper()}: {plan['teams'][team]['summary']}")
            else:
                feedback_lines.append(f"{team.upper()}: {action_error}")
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
        filtered = [str(decision_id) for decision_id in override_order if str(decision_id) in default_ids]
        return filtered

    def is_decision_active_for_role(self, decision_id, role_key=None):
        return str(decision_id) in set(self.role_active_decision_ids(role_key))

    def toggle_role_decision(self, decision_id, role_key=None):
        role = role_key or self.selected_role_key()
        decision_id = str(decision_id)
        role_entry = self._role_entry(role, create=True)
        active_ids = self.role_active_decision_ids(role)
        if decision_id in active_ids:
            active_ids = [item for item in active_ids if item != decision_id]
            role_entry.get('decisions', {}).pop(decision_id, None)
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
        if field_name in {'label', 'condition_expr'}:
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
        role_entry.get('decisions', {}).pop(spec['id'], None)
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
        override = self.current_override(create=False) or {}
        return [deepcopy(region) for region in self.ai_controller._behavior_override_regions(override, team=team)]

    def current_destination_override_regions(self, team=None):
        override = self.current_override(create=False) or {}
        return [deepcopy(region) for region in self.ai_controller._behavior_override_destination_regions(override, team=team)]

    def current_destination_regions(self, team=None):
        override_regions = self.current_destination_override_regions(team=team)
        if override_regions:
            return override_regions
        spec = self.selected_spec()
        if spec is None:
            return []
        return self.ai_controller.get_decision_destination_preview_regions(self.selected_role_key(), spec['id'], self.map_manager, team=team)

    def current_point_targets(self, team=None):
        spec = self.selected_spec()
        if spec is None:
            return {}
        return dict(self.ai_controller.get_decision_point_targets(self.selected_role_key(), spec['id'], self.map_manager, team=team))

    def editable_point_targets(self):
        spec = self.selected_spec() or {}
        editable = spec.get('editable_targets', ())
        return [dict(item) for item in editable if isinstance(item, dict) and str(item.get('id', '')).strip()]

    def current_regions_for_kind(self, region_kind='destination', team=None):
        return self.current_destination_regions(team=team) if region_kind == 'destination' else self.current_task_regions(team=team)

    def _editable_regions(self, region_kind='destination', create=False, team=None):
        override = self.current_override(create=create)
        if override is None:
            return None
        field_name = 'destination_regions' if region_kind == 'destination' else 'task_regions'
        if team in {'red', 'blue'}:
            by_team_field = f'{field_name}_by_team'
            by_team = override.get(by_team_field)
            if not isinstance(by_team, dict):
                by_team = {}
                if create:
                    override[by_team_field] = by_team
            regions = by_team.get(team)
            if not isinstance(regions, list) and create:
                regions = [deepcopy(region) for region in self.current_regions_for_kind(region_kind, team=team)]
                by_team[team] = regions
            return by_team.get(team) if isinstance(by_team.get(team), list) else []
        regions = override.get(field_name)
        if not isinstance(regions, list) and create:
            regions = [deepcopy(region) for region in self.current_regions_for_kind(region_kind)] if region_kind == 'destination' else []
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
        field_name = 'destination_regions' if region_kind == 'destination' else 'task_regions'
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
        task_regions = self._editable_regions('task', create=True, team=team)
        if task_regions is None:
            return
        task_regions.append(deepcopy(region))
        self._persist_live_changes('已更新任务区域')

    def add_destination_region(self, region, team=None):
        destination_regions = self._editable_regions('destination', create=True, team=team)
        if destination_regions is None:
            return
        destination_regions.append(deepcopy(region))
        self._persist_live_changes('已更新目的地区域')

    def remove_region_at_point(self, point, region_kind='task', team=None):
        region_index, _ = self.region_at_point(point, region_kind=region_kind, team=team)
        if region_index is None:
            return False
        return self.remove_region_at_index(region_index, region_kind=region_kind, log_message='已删除区域覆盖', team=team)

    def set_point_target(self, target_key, point, team=None):
        override = self.current_override(create=True)
        if override is None or point is None:
            return False
        if team in {'red', 'blue'}:
            by_team = override.setdefault('point_targets_by_team', {})
            targets = by_team.get(team)
            if not isinstance(targets, dict):
                targets = {key: [round(value[0], 1), round(value[1], 1)] for key, value in self.current_point_targets(team=team).items()}
                by_team[team] = targets
        else:
            targets = override.setdefault('point_targets', {})
            if not isinstance(targets, dict):
                targets = {}
                override['point_targets'] = targets
        targets[str(target_key)] = [round(float(point[0]), 1), round(float(point[1]), 1)]
        self.prune_current_override_if_default()
        self._persist_live_changes('已更新目标点')
        return True

    def clear_point_target(self, target_key, team=None):
        override = self.current_override(create=False)
        if override is None:
            return False
        removed = False
        if team in {'red', 'blue'}:
            by_team = override.get('point_targets_by_team', {})
            targets = by_team.get(team) if isinstance(by_team, dict) else None
            if isinstance(targets, dict) and str(target_key) in targets:
                targets.pop(str(target_key), None)
                removed = True
                if not targets:
                    by_team.pop(team, None)
                if not by_team:
                    override.pop('point_targets_by_team', None)
        else:
            targets = override.get('point_targets')
            if isinstance(targets, dict) and str(target_key) in targets:
                targets.pop(str(target_key), None)
                removed = True
                if not targets:
                    override.pop('point_targets', None)
        if removed:
            self.prune_current_override_if_default()
            self._persist_live_changes('已清除目标点')
        return removed

    def clear_current_override(self):
        spec = self.selected_spec()
        role_key = self.selected_role_key()
        if spec is None:
            return False
        role_entry = self._role_entry(role_key, create=False)
        if role_entry is None:
            return False
        removed = role_entry.get('decisions', {}).pop(spec['id'], None)
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
                filtered_order = [str(decision_id) for decision_id in decision_order if str(decision_id) in default_ids]
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
        self.ai_controller._refresh_behavior_runtime_overrides(force=True)
        self._reset_preview_world()
        self.add_log(f'已重载行为预设: {name}')


class BehaviorEditorApp:
    def __init__(self, engine):
        self.engine = engine
        pygame.init()
        self.window_width = int(engine.config.get('simulator', {}).get('window_width', 1400))
        self.window_height = int(engine.config.get('simulator', {}).get('window_height', 900))
        self.screen = pygame.display.set_mode((self.window_width, self.window_height))
        pygame.display.set_caption('RoboMaster 行为编辑器')
        self.clock = pygame.time.Clock()
        self.running = False
        self.toolbar_height = 56
        self.panel_width = 760
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
            ('region', '区域'),
        )
        self.detail_page = 'overview'
        self.panel_scroll_y = 0
        self.panel_scroll_max = 0
        self.panel_scroll_step = 48
        self.list_scroll_step = 32
        self.panel_viewport_rect = None
        self.region_edit_target = 'destination'
        self.region_edit_team = 'red'
        self.map_cache = None
        self.map_cache_size = None
        map_width = max(1.0, float(getattr(self.engine.map_manager, 'map_width', 1.0) or 1.0))
        map_height = max(1.0, float(getattr(self.engine.map_manager, 'map_height', 1.0) or 1.0))
        self.map_zoom = 1.0
        self.map_zoom_min = 1.0
        self.map_zoom_max = 4.0
        self.map_view_center = (map_width * 0.5, map_height * 0.5)
        self.mouse_world = None
        self.shape_mode = 'rect'
        self.drag_start = None
        self.drag_current = None
        self.polygon_points = []
        self.selected_region_kind = None
        self.selected_region_index = None
        self.selected_region_team = None
        self.region_drag_state = None
        self.point_edit_target = None
        self.active_text_input = None
        self.click_actions = []
        self.preview_run_duration_ms = 1400
        self.preview_pause_duration_ms = 2000
        self.preview_loop_active = False
        self.preview_cycle_started_ms = 0
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
        return {'sentry': '哨兵', 'infantry': '步兵', 'hero': '英雄', 'engineer': '工程'}.get(role_key, role_key)

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
                    cycle_duration = self.preview_run_duration_ms + self.preview_pause_duration_ms
                    if elapsed >= cycle_duration:
                        self._restart_preview_cycle(current_ms)
                        team_plan = self.engine.preview_plan.get('teams', {}).get(entity.team)
                        elapsed = current_ms - self.preview_cycle_started_ms
                    ratio = min(1.0, max(0.0, elapsed / max(self.preview_run_duration_ms, 1)))
                    start = team_plan.get('start', (entity.position['x'], entity.position['y']))
                    target = team_plan.get('target', start)
                    interp = (
                        float(start[0]) + (float(target[0]) - float(start[0])) * ratio,
                        float(start[1]) + (float(target[1]) - float(start[1])) * ratio,
                    )
                    preview_point = self.world_to_screen(interp)
                    if preview_point is not None:
                        draw_point = preview_point
                    target_point = self.world_to_screen(target)
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
        feedback_lines = self.engine.preview_feedback or ['点击上方按钮预演当前选中决策', '红蓝双方会沿决策输出的导航目标循环播放']
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
            return ['未设置任务区域，保持默认地点逻辑。']
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
            point = targets.get(point_id)
            row_rect = pygame.Rect(rect.x + 8, row_y, rect.width - 16, 30)
            active = self.point_edit_target == point_id
            pygame.draw.rect(self.screen, self.colors['panel_row_active'] if active else self.colors['panel_row'], row_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.colors['panel_border'], row_rect, 1, border_radius=6)
            label = str(item.get('label', point_id))
            value_text = f'({int(point[0])}, {int(point[1])})' if point is not None else '未设置'
            label_surface = self.tiny_font.render(f'{label}: {value_text}', True, self.colors['panel_text'])
            self.screen.blit(label_surface, (row_rect.x + 8, row_rect.y + 8))
            edit_rect = pygame.Rect(row_rect.right - 56, row_rect.y + 5, 22, 20)
            clear_rect = pygame.Rect(row_rect.right - 28, row_rect.y + 5, 22, 20)
            pygame.draw.rect(self.screen, self.colors['green'] if active else self.colors['blue'], edit_rect, border_radius=5)
            pygame.draw.rect(self.screen, self.colors['gray'] if point is None else self.colors['orange'], clear_rect, border_radius=5)
            edit_text = self.tiny_font.render('设', True, self.colors['white'])
            clear_text = self.tiny_font.render('清', True, self.colors['white'])
            self.screen.blit(edit_text, (edit_rect.x + (edit_rect.width - edit_text.get_width()) // 2, edit_rect.y + 3))
            self.screen.blit(clear_text, (clear_rect.x + (clear_rect.width - clear_text.get_width()) // 2, clear_rect.y + 3))
            self._append_click_action(row_rect, f'edit_point_target:{point_id}', clip_rect=self.panel_viewport_rect)
            self._append_click_action(edit_rect, f'edit_point_target:{point_id}', clip_rect=self.panel_viewport_rect)
            if point is not None:
                self._append_click_action(clear_rect, f'clear_point_target:{point_id}', clip_rect=self.panel_viewport_rect)
            row_y += 36

    def render_toolbar(self):
        pygame.draw.rect(self.screen, self.colors['toolbar'], (0, 0, self.window_width, self.toolbar_height))
        x = 10
        for label, action, active in (
            ('保存预设', 'save', False),
            ('应用到主程序', 'apply', False),
            ('重载预设', 'reload', False),
            ('编辑目的地', 'edit_layer:destination', self.region_edit_target == 'destination'),
            ('编辑任务区域', 'edit_layer:task', self.region_edit_target == 'task'),
            ('编辑红方', 'edit_team:red', self.region_edit_team == 'red'),
            ('编辑蓝方', 'edit_team:blue', self.region_edit_team == 'blue'),
            ('矩形', 'shape:rect', self.shape_mode == 'rect'),
            ('圆形', 'shape:circle', self.shape_mode == 'circle'),
            ('多边形', 'shape:polygon', self.shape_mode == 'polygon'),
            ('清空当前覆盖', 'clear_override', False),
            ('删除命中区域', 'delete_region_at_cursor', False),
        ):
            x = self._toolbar_button(x, label, action, active=active)

        preset_rect = pygame.Rect(x + 6, 10, 180, self.toolbar_height - 20)
        pygame.draw.rect(self.screen, self.colors['white'], preset_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.colors['toolbar_button_active'] if self.active_text_input and self.active_text_input.get('field') == 'preset_name' else self.colors['panel_border'], preset_rect, 2, border_radius=6)
        preset_text = self.active_text_input['text'] if self.active_text_input and self.active_text_input.get('field') == 'preset_name' else self.engine.preset_name
        rendered = self.base_font.render(preset_text or 'latest_behavior', True, self.colors['panel_text'])
        self.screen.blit(rendered, (preset_rect.x + 10, preset_rect.y + 8))
        self.click_actions.append((preset_rect, 'edit:preset_name'))

        hint_text = '绿色=目的地 | 黄色=任务区域 | 红蓝按钮切换队伍 | 点回起点或 Enter 完成多边形 | 目标点点设后左键落点'
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
        self._render_destination_regions()
        self._render_task_regions()
        self._render_selected_region_overlay()
        self._render_point_targets_overlay()
        self._render_preview_target_regions()
        self._render_preview_units()
        self._render_drawing_preview()
        if self.mouse_world is not None:
            point_hint = ''
            if self.point_edit_target is not None:
                point_hint = f' | 正在设置目标点: {self.point_edit_target}'
            coord_text = self.tiny_font.render(f'世界坐标: ({int(self.mouse_world[0])}, {int(self.mouse_world[1])}) | 缩放 {self.map_zoom:.2f}x{point_hint}', True, self.colors['panel_text'])
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

    def _task_region_color(self, index):
        palette = (self.colors['yellow'], self.colors['orange'], self.colors['red'], self.colors['blue'])
        return palette[index % len(palette)]

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
                    rect = pygame.Rect(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]), abs(end[1] - start[1]))
                    pygame.draw.rect(self.screen, color, rect, width)

    def _render_destination_regions(self):
        self._render_region_collection(self.engine.current_destination_regions(team=self.region_edit_team), self.colors['green'], width=3)

    def _render_task_regions(self):
        for index, region in enumerate(self.engine.current_task_regions(team=self.region_edit_team)):
            self._render_region_collection([region], self._task_region_color(index), width=3)

    def _render_point_targets_overlay(self):
        target_defs = self.engine.editable_point_targets()
        if not target_defs:
            return
        targets = self.engine.current_point_targets(team=self.region_edit_team)
        if not targets:
            return
        color = self.colors['red'] if self.region_edit_team == 'red' else self.colors['blue']
        ordered_points = []
        for index, item in enumerate(target_defs, start=1):
            point = targets.get(str(item.get('id', '')))
            if point is None:
                continue
            ordered_points.append(point)
            screen_point = self.world_to_screen(point)
            if screen_point is None:
                continue
            active = self.point_edit_target == str(item.get('id', ''))
            pygame.draw.circle(self.screen, self.colors['white'], screen_point, 10)
            pygame.draw.circle(self.screen, self.colors['orange'] if active else color, screen_point, 10, 3)
            label_surface = self.tiny_font.render(str(index), True, self.colors['panel_text'])
            self.screen.blit(label_surface, (screen_point[0] - label_surface.get_width() // 2, screen_point[1] - label_surface.get_height() // 2))
        if len(ordered_points) >= 2:
            for start, end in zip(ordered_points[:-1], ordered_points[1:]):
                start_point = self.world_to_screen(start)
                end_point = self.world_to_screen(end)
                if start_point is not None and end_point is not None:
                    pygame.draw.line(self.screen, color, start_point, end_point, 2)

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
            preview_color = self.colors['green'] if self.region_edit_target == 'destination' else self.colors['yellow']
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
        preview_color = self.colors['green'] if self.region_edit_target == 'destination' else self.colors['yellow']
        if self.shape_mode == 'circle':
            radius = max(2, int(math.hypot(end[0] - start[0], end[1] - start[1])))
            pygame.draw.circle(self.screen, preview_color, start, radius, 2)
        else:
            rect = pygame.Rect(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]), abs(end[1] - start[1]))
            pygame.draw.rect(self.screen, preview_color, rect, 2)

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
            hint_text = self.tiny_font.render('滚轮可上下滚动全部决策', True, self.colors['gray'])
            self.screen.blit(hint_text, (header_rect.right - hint_text.get_width(), header_rect.y + 6))
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

        edit_values = {
            'label': self.active_text_input['text'] if self.active_text_input and self.active_text_input.get('field') == 'label' else str(override.get('label', '')),
            'condition_expr': self.active_text_input['text'] if self.active_text_input and self.active_text_input.get('field') == 'condition_expr' else str(override.get('condition_expr', '')),
            'start_sec': self.active_text_input['text'] if self.active_text_input and self.active_text_input.get('field') == 'start_sec' else str((override.get('time_window') or {}).get('start_sec', '')),
            'end_sec': self.active_text_input['text'] if self.active_text_input and self.active_text_input.get('field') == 'end_sec' else str((override.get('time_window') or {}).get('end_sec', '')),
        }

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
            half_width = (viewport_rect.width - 28) // 2
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, half_width, card_h_small), '启用状态', [self.engine.current_enabled_label()], action='toggle:enabled', active=True)
            self._panel_card(pygame.Rect(viewport_rect.x + 18 + half_width, card_y, half_width, card_h_small), '区域模式', [self.engine.current_region_mode_label()], action='toggle:region_mode')
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 92), '覆盖说明', [
                '未修改的字段保持默认行为树逻辑。',
                '已覆盖的标签、时间、条件和区域会在运行时叠加到默认决策上。',
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
        elif self.detail_page == 'region':
            destination_regions = self.engine.current_destination_regions(team=self.region_edit_team)
            task_regions = self.engine.current_task_regions(team=self.region_edit_team)
            editable_targets = self.engine.editable_point_targets()
            point_targets = self.engine.current_point_targets(team=self.region_edit_team)
            edit_layer_label = '目的地区域' if self.region_edit_target == 'destination' else '任务区域'
            edit_team_label = '红方' if self.region_edit_team == 'red' else '蓝方'
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '当前编辑层', [edit_layer_label], action=f'edit_layer:{self.region_edit_target}', active=True)
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '当前编辑队伍', [edit_team_label], action=f'edit_team:{self.region_edit_team}', active=True)
            card_y += card_h_small + 8
            if editable_targets:
                point_rect = pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, self._point_target_section_height(len(editable_targets)))
                self._render_point_target_section(point_rect, f'地形目标点列表（{edit_team_label}）', editable_targets, point_targets)
                card_y += point_rect.height + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '目的地区域数量', [f'{len(destination_regions)} 个区域'])
            card_y += card_h_small + 8
            destination_rect = pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, self._region_list_section_height(len(destination_regions)))
            self._render_region_list_section(destination_rect, f'目的地列表（{edit_team_label}）', destination_regions, 'destination')
            card_y += destination_rect.height + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '区域模式', [self.engine.current_region_mode_label()], action='toggle:region_mode', active=True)
            card_y += card_h_small + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, card_h_small), '任务区域数量', [f'{len(task_regions)} 个区域'])
            card_y += card_h_small + 8
            task_rect = pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, self._region_list_section_height(len(task_regions)))
            self._render_region_list_section(task_rect, f'任务区域列表（{edit_team_label}）', task_regions, 'task')
            card_y += task_rect.height + 8
            self._panel_card(pygame.Rect(viewport_rect.x + 10, card_y, viewport_rect.width - 20, 122), '绘制说明', [
                '绿色区域表示行为目的地，黄色区域表示触发/任务区域。',
                '工具栏可切换当前编辑层和红蓝双方。',
                '矩形/圆形：左键拖拽完成；多边形：左键逐点添加，点回起点或 Enter 收尾。',
                '点击已有区域可选中并拖拽编辑，右侧列表也可直接选中或删除。',
            ])
            card_y += 130

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
        if self.active_text_input is None:
            return False
        field = self.active_text_input.get('field')
        text = str(self.active_text_input.get('text', ''))
        if field == 'preset_name':
            self.engine.preset_name = text.strip() or 'latest_behavior'
            self.engine._persist_live_changes(f'主程序已切换行为预设: {self.engine.preset_name}')
        elif field in {'label', 'condition_expr'}:
            self.engine.set_override_field(field, text)
        elif field in {'start_sec', 'end_sec'}:
            value = text.strip()
            if not value:
                self.engine.set_override_field(field, None)
            else:
                try:
                    self.engine.set_override_field(field, float(value))
                except ValueError:
                    self.engine.add_log(f'{field} 不是有效数字，已保留原值')
        self.active_text_input = None
        return True

    def handle_text_input_key(self, event):
        if self.active_text_input is None:
            return False
        if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER}:
            self.commit_text_input()
            return True
        if event.key == pygame.K_ESCAPE:
            self.active_text_input = None
            return True
        if event.key == pygame.K_BACKSPACE:
            self.active_text_input['text'] = self.active_text_input.get('text', '')[:-1]
            return True
        if event.key == pygame.K_DELETE:
            self.active_text_input['text'] = ''
            return True
        if event.unicode and event.unicode.isprintable():
            self.active_text_input['text'] = self.active_text_input.get('text', '') + event.unicode
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
        if action.startswith('edit_layer:'):
            self.region_edit_target = action.split(':', 1)[1]
            self._clear_region_selection()
            return
        if action.startswith('edit_team:'):
            self.region_edit_team = action.split(':', 1)[1]
            self.point_edit_target = None
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
            self._clear_region_selection()
            return
        if action.startswith('role:'):
            self.engine.selected_role_index = int(action.split(':', 1)[1])
            self.panel_scroll_y = 0
            self.decision_list_scroll_y = 0
            self.sidebar_list_scroll_y = 0
            self.preview_loop_active = False
            self._clear_region_selection()
            return
        if action.startswith('decision:'):
            self.engine.selected_decision_index[self.engine.selected_role_key()] = int(action.split(':', 1)[1])
            self.detail_page = 'overview'
            self.panel_scroll_y = 0
            self.preview_loop_active = False
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
        if action.startswith('select_region:'):
            _, region_kind, raw_index = action.split(':', 2)
            self.region_edit_target = region_kind
            self.point_edit_target = None
            self._set_selected_region(region_kind, int(raw_index), region_team=self.region_edit_team)
            return
        if action.startswith('delete_region:'):
            _, region_kind, raw_index = action.split(':', 2)
            if self.engine.remove_region_at_index(int(raw_index), region_kind=region_kind, log_message='已删除区域覆盖', team=self.region_edit_team):
                if self.selected_region_kind == region_kind and self.selected_region_team == self.region_edit_team and self.selected_region_index == int(raw_index):
                    self._clear_region_selection()
            return
        if action.startswith('edit_point_target:'):
            self.point_edit_target = action.split(':', 1)[1]
            self._clear_region_selection()
            return
        if action.startswith('clear_point_target:'):
            self.engine.clear_point_target(action.split(':', 1)[1], team=self.region_edit_team)
            if self.point_edit_target == action.split(':', 1)[1]:
                self.point_edit_target = None
            return
        if action.startswith('edit:'):
            field = action.split(':', 1)[1]
            override = self.engine.current_override(create=False) or {}
            if field in {'label', 'condition_expr'}:
                text = str(override.get(field, ''))
            elif field in {'start_sec', 'end_sec'}:
                text = str((override.get('time_window') or {}).get(field, ''))
            else:
                text = self.engine.preset_name
            self.active_text_input = {'field': field, 'text': text}
            return
        if action == 'toggle:enabled':
            self.engine.cycle_enabled_state()
            return
        if action == 'toggle:region_mode':
            self.engine.cycle_region_mode()
            return
        if action == 'clear_override':
            self.engine.clear_current_override()
            self.point_edit_target = None
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
        add_region = self.engine.add_destination_region if self.region_edit_target == 'destination' else self.engine.add_task_region
        region_label = '目的地区域' if self.region_edit_target == 'destination' else '任务区域'
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
                    for rect, action in list(self.click_actions):
                        if rect.collidepoint(event.pos):
                            self._handle_action(action)
                            handled = True
                            break
                    if handled:
                        continue
                    world_point = self.screen_to_world(event.pos)
                    self.mouse_world = world_point
                    if world_point is None:
                        if self.active_text_input is not None:
                            self.commit_text_input()
                        continue
                    if self.point_edit_target is not None:
                        self.engine.set_point_target(self.point_edit_target, world_point, team=self.region_edit_team)
                        self.engine.add_log(f'已设置 {self.point_edit_target} 目标点')
                        self.point_edit_target = None
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