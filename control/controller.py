#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pygame
from control.manual_controller import ManualController
from control.ai_controller import AIController

class Controller:
    def __init__(self, config):
        self.config = config
        self.manual_controller = ManualController(config)
        self.ai_controller = AIController(config)
        
        # 控制模式：'manual' 或 'ai'
        self.control_mode = 'manual'
    
    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0):
        """更新控制"""
        # 获取键盘输入
        keys = pygame.key.get_pressed()

        # 更新AI控制
        self.ai_controller.update(entities, map_manager, rules_engine, game_time, game_duration)

        # 手动输入最后覆盖 AI，仅作用于正在手操的单位
        self.manual_controller.update(keys, entities)
    
    def set_control_mode(self, mode):
        """设置控制模式"""
        if mode in ['manual', 'ai']:
            self.control_mode = mode
    
    def get_control_mode(self):
        """获取当前控制模式"""
        return self.control_mode
