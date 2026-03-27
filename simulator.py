#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pygame_compat import pygame
import json
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
