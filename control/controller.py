#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from concurrent.futures import ThreadPoolExecutor

import pygame
from control.manual_controller import ManualController
from control.ai_controller import AIController


class Controller:
    def __init__(self, config):
        self.config = config
        self.manual_controller = ManualController(config)
        ai_config = config.get('ai', {})
        configured_workers = int(ai_config.get('controller_worker_threads', 1))
        cpu_count = os.cpu_count() or 2
        self._ai_worker_threads = max(1, min(configured_workers, cpu_count))

        # 每个分片使用独立 AIController，避免共享缓存字典导致线程冲突。
        self._ai_controllers = [AIController(config) for _ in range(self._ai_worker_threads)]
        self._ai_executor = ThreadPoolExecutor(max_workers=self._ai_worker_threads) if self._ai_worker_threads > 1 else None
        
        # 控制模式：'manual' 或 'ai'
        self.control_mode = 'manual'

    def shutdown(self):
        if self._ai_executor is not None:
            self._ai_executor.shutdown(wait=False)
            self._ai_executor = None

    def __del__(self):
        self.shutdown()

    def _is_ai_controllable_entity(self, entity):
        return entity.is_alive() and entity.type in {'robot', 'sentry'}

    def _assign_entity_to_shard(self, entity_id):
        # 使用稳定分片保证实体始终走同一个 AIController，保留路径/卡住检测等历史状态。
        return abs(hash(entity_id)) % self._ai_worker_threads

    def _update_ai_parallel(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0):
        if self._ai_worker_threads <= 1 or self._ai_executor is None:
            self._ai_controllers[0].update(entities, map_manager, rules_engine, game_time, game_duration)
            return

        shard_entity_ids = [set() for _ in range(self._ai_worker_threads)]
        for entity in entities:
            if not self._is_ai_controllable_entity(entity):
                continue
            shard_index = self._assign_entity_to_shard(entity.id)
            shard_entity_ids[shard_index].add(entity.id)

        futures = []
        for shard_index, entity_ids in enumerate(shard_entity_ids):
            if not entity_ids:
                continue
            ai_controller = self._ai_controllers[shard_index]
            futures.append(
                self._ai_executor.submit(
                    ai_controller.update,
                    entities,
                    map_manager,
                    rules_engine,
                    game_time,
                    game_duration,
                    entity_ids,
                )
            )

        for future in futures:
            future.result()
    
    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0):
        """更新控制"""
        # 获取键盘输入
        keys = pygame.key.get_pressed()

        # 更新 AI 控制（并行分片）；异常时回退到单线程，避免中断对局。
        try:
            self._update_ai_parallel(entities, map_manager, rules_engine, game_time, game_duration)
        except Exception:
            self._ai_controllers[0].update(entities, map_manager, rules_engine, game_time, game_duration)

        # 手动输入最后覆盖 AI，仅作用于正在手操的单位
        self.manual_controller.update(keys, entities)
    
    def set_control_mode(self, mode):
        """设置控制模式"""
        if mode in ['manual', 'ai']:
            self.control_mode = mode
    
    def get_control_mode(self):
        """获取当前控制模式"""
        return self.control_mode
