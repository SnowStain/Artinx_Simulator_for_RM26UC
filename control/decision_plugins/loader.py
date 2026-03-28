#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib
import os


def load_decision_plugins():
    definitions_dir = os.path.join(os.path.dirname(__file__), 'definitions')
    plugins = {}
    for file_name in sorted(os.listdir(definitions_dir)):
        if not file_name.endswith('.py') or file_name == '__init__.py':
            continue
        module_name = file_name[:-3]
        module = importlib.import_module(f'control.decision_plugins.definitions.{module_name}')
        plugin = getattr(module, 'PLUGIN', None)
        if not isinstance(plugin, dict):
            continue
        plugin_id = str(plugin.get('id', '')).strip()
        roles = plugin.get('roles', {})
        if not plugin_id or not isinstance(roles, dict):
            continue
        plugins[plugin_id] = plugin
    return plugins
