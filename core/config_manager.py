#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from copy import deepcopy
from datetime import datetime

class ConfigManager:
    def __init__(self):
        self.config = {}

    def _workspace_root(self, config_path=None):
        path = config_path or self.config.get('_config_path', 'config.json')
        return os.path.dirname(os.path.abspath(path))
    
    def _read_json(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _deep_merge(self, base, override):
        if not isinstance(base, dict) or not isinstance(override, dict):
            return deepcopy(override)

        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged

    def _resolve_map_preset_path(self, preset_name, config_path=None):
        if not preset_name:
            return None
        preset_ref = str(preset_name).strip()
        if not preset_ref:
            return None
        if os.path.isabs(preset_ref):
            return preset_ref
        if not preset_ref.lower().endswith('.json'):
            preset_ref = f'{preset_ref}.json'
        return os.path.join(self._workspace_root(config_path), 'map_presets', preset_ref)

    def load_map_preset(self, preset_name, config_path=None):
        preset_path = self._resolve_map_preset_path(preset_name, config_path)
        if preset_path is None or not os.path.exists(preset_path):
            return None
        payload = self._read_json(preset_path)
        if isinstance(payload, dict) and isinstance(payload.get('map'), dict):
            preset_map = payload['map']
        else:
            preset_map = payload
        if not isinstance(preset_map, dict):
            return None
        return deepcopy(preset_map)

    def _apply_map_preset(self, config, config_path=None):
        preset_name = config.get('map', {}).get('preset')
        if not preset_name:
            return config
        preset_map = self.load_map_preset(preset_name, config_path)
        if not preset_map:
            return config
        merged = deepcopy(config)
        merged['map'] = self._deep_merge(merged.get('map', {}), preset_map)
        merged['map']['preset'] = preset_name
        return merged

    def load_config(self, config_path, settings_path='settings.json'):
        """加载基础配置，并叠加本地 setting 覆盖。"""
        if not os.path.exists(config_path):
            print(f"配置文件 {config_path} 不存在")
            self.config = {}
            return self.config

        base_config = self._read_json(config_path)
        if settings_path and os.path.exists(settings_path):
            settings_config = self._read_json(settings_path)
            self.config = self._deep_merge(base_config, settings_config)
        else:
            self.config = base_config

        self.config = self._apply_map_preset(self.config, config_path)

        self.config['_config_path'] = config_path
        self.config['_settings_path'] = settings_path
        return self.config
    
    def get(self, key_path, default=None):
        """获取配置值，支持嵌套路径"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path, value):
        """设置配置值，支持嵌套路径"""
        keys = key_path.split('.')
        current = self.config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value

    def save_config(self, config_path=None):
        """保存配置文件"""
        path = config_path or self.config.get('_config_path', 'config.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def build_local_settings_payload(self, config):
        """提取需要持久化到本地 setting 的运行时配置。"""
        map_config = config.get('map', {})
        preset_name = map_config.get('preset')
        map_payload = {}
        if preset_name:
            map_payload['preset'] = preset_name
        else:
            map_payload['facilities'] = deepcopy(map_config.get('facilities', []))
            map_payload['terrain_grid'] = deepcopy(map_config.get('terrain_grid', {}))
        return {
            'simulator': {
                'show_facilities': config.get('simulator', {}).get('show_facilities', True),
                'show_aim_fov': config.get('simulator', {}).get('show_aim_fov', True),
                'enable_entity_movement': config.get('simulator', {}).get('enable_entity_movement', False),
                'show_perf_overlay': config.get('simulator', {}).get('show_perf_overlay', True),
                'enable_perf_logging': config.get('simulator', {}).get('enable_perf_logging', True),
                'enable_perf_breakdown': config.get('simulator', {}).get('enable_perf_breakdown', True),
                'enable_perf_file_logging': config.get('simulator', {}).get('enable_perf_file_logging', True),
                'perf_sample_window': config.get('simulator', {}).get('perf_sample_window', 20000),
                'perf_log_interval_sec': config.get('simulator', {}).get('perf_log_interval_sec', 5.0),
            },
            'map': map_payload,
            'entities': {
                'initial_positions': deepcopy(config.get('entities', {}).get('initial_positions', {})),
                'robot_levels': deepcopy(config.get('entities', {}).get('robot_levels', {})),
            },
            'rules': deepcopy(config.get('rules', {})),
        }

    def build_map_preset_payload(self, config, preset_name=None):
        map_config = config.get('map', {})
        payload = {
            'version': 1,
            'name': preset_name or map_config.get('preset') or 'unnamed',
            'saved_at': datetime.now().isoformat(timespec='seconds'),
            'map': {
                'image_path': map_config.get('image_path'),
                'origin_x': map_config.get('origin_x', 0),
                'origin_y': map_config.get('origin_y', 0),
                'unit': map_config.get('unit', 'px'),
                'width': map_config.get('width'),
                'height': map_config.get('height'),
                'field_length_m': map_config.get('field_length_m'),
                'field_width_m': map_config.get('field_width_m'),
                'facilities': deepcopy(map_config.get('facilities', [])),
                'terrain_grid': deepcopy(map_config.get('terrain_grid', {})),
            },
        }
        return payload

    def save_map_preset(self, preset_name, config=None, config_path=None):
        name = str(preset_name or '').strip()
        if not name:
            raise ValueError('preset_name is required')
        preset_path = self._resolve_map_preset_path(name, config_path)
        directory = os.path.dirname(preset_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = self.build_map_preset_payload(config or self.config, preset_name=name)
        with open(preset_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return preset_path

    def save_settings(self, settings_path=None, payload=None):
        """保存本地 setting 文件。"""
        path = settings_path or self.config.get('_settings_path', 'settings.json')
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        content = payload if payload is not None else self.build_local_settings_payload(self.config)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
