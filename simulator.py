#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame
import json
import sys
import os
from datetime import datetime

# 添加项目根目录及核心目录到路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(PROJECT_ROOT, "core")

def _add_to_sys_path(path):
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

def _add_package_parent(package_name):
    for dirpath, dirnames, _ in os.walk(PROJECT_ROOT):
        if package_name in dirnames:
            _add_to_sys_path(dirpath)
            return

_add_to_sys_path(PROJECT_ROOT)
_add_to_sys_path(CORE_DIR)
_add_package_parent("state_machine")

from core.game_engine import GameEngine
from core.config_manager import ConfigManager
from rendering.renderer import Renderer

def main():
    # 初始化配置管理器
    config_manager = ConfigManager()
    config = config_manager.load_config("config.json", "settings.json")
    config['_config_path'] = 'config.json'
    config['_settings_path'] = 'settings.json'
    
    # 初始化游戏引擎
    game_engine = GameEngine(config, config_manager=config_manager, config_path='config.json')
    
    # 初始化渲染器
    renderer = Renderer(game_engine, config)
    
    # 启动游戏循环
    game_engine.run(renderer)

if __name__ == "__main__":
    main()
