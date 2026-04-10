#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from concurrent.futures import ThreadPoolExecutor

import pygame
from control.manual_controller import ManualController
from control.ai_controller import AIController
from control.controller_scheduler import ControllerShardScheduler
from control.frame_context import AIFrameContext


class Controller:
    _ROLE_SHARD_ORDER = ('sentry', 'hero', 'engineer', 'infantry')

    def __init__(self, config):
        self.config = config
        self.manual_controller = ManualController(config)
        ai_config = config.get('ai', {})
        configured_workers = int(ai_config.get('controller_worker_threads', len(self._ROLE_SHARD_ORDER)))
        cpu_count = os.cpu_count() or 2
        role_worker_target = len(self._ROLE_SHARD_ORDER)
        self._ai_worker_threads = max(1, min(max(configured_workers, role_worker_target), cpu_count))

        # 每个兵种角色使用独立 AIController，避免不同兵种争抢同一分片的缓存与运行时状态。
        self._role_shard_map = {
            role_key: min(index, self._ai_worker_threads - 1)
            for index, role_key in enumerate(self._ROLE_SHARD_ORDER)
        }
        default_shards_per_frame = max(1, min(self._ai_worker_threads, (len(self._ROLE_SHARD_ORDER) + 1) // 2))
        configured_shards_per_frame = int(ai_config.get('controller_shards_per_frame', default_shards_per_frame))
        self._shard_scheduler = ControllerShardScheduler(self._ai_worker_threads, configured_shards_per_frame)
        self._ai_controllers = [AIController(config) for _ in range(self._ai_worker_threads)]
        self._ai_executor = ThreadPoolExecutor(max_workers=self._ai_worker_threads) if self._ai_worker_threads > 1 else None
        
        # 控制模式：'manual' 或 'ai'
        self.control_mode = 'manual'

    def shutdown(self):
        for ai_controller in getattr(self, '_ai_controllers', ()):
            if hasattr(ai_controller, 'shutdown'):
                ai_controller.shutdown()
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

    def _entity_role_key(self, entity):
        if entity.type == 'sentry':
            return 'sentry'
        robot_type = str(getattr(entity, 'robot_type', '') or '').strip()
        return {
            '英雄': 'hero',
            '工程': 'engineer',
            '步兵': 'infantry',
        }.get(robot_type, 'infantry')

    def _update_ai_parallel(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0, controlled_entity_ids=None):
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        map_center_x = None
        if map_manager is not None:
            map_center_x = float(getattr(map_manager, 'map_width', 0.0)) * 0.5
        shared_frame = AIFrameContext.from_entities(entities, map_center_x=map_center_x)
        shard_entities = [[] for _ in range(self._ai_worker_threads)]
        for entity in entities:
            if controlled_ids is not None and entity.id not in controlled_ids:
                continue
            if not self._is_ai_controllable_entity(entity):
                continue
            role_key = self._entity_role_key(entity)
            shard_index = self._role_shard_map.get(role_key)
            if shard_index is None:
                shard_index = self._assign_entity_to_shard(entity.id)
            shard_entities[shard_index].append(entity)

        active_shards = [index for index, members in enumerate(shard_entities) if members]
        if not active_shards:
            return
        scheduled_shards = set(self._shard_scheduler.select_active_shards(active_shards))

        if self._ai_worker_threads <= 1 or self._ai_executor is None:
            scheduled_index = next(iter(scheduled_shards)) if scheduled_shards else active_shards[0]
            self._ai_controllers[scheduled_index].update(
                entities,
                map_manager,
                rules_engine,
                game_time,
                game_duration,
                controlled_entity_ids={entity.id for entity in shard_entities[scheduled_index]},
                controlled_entities=tuple(shard_entities[scheduled_index]),
                shared_frame=shared_frame,
            )
            for shard_index, members in enumerate(shard_entities):
                if not members or shard_index == scheduled_index:
                    continue
                self._ai_controllers[shard_index].maintain_entities_motion(members)
            return

        futures = []
        for shard_index in active_shards:
            members = shard_entities[shard_index]
            if shard_index not in scheduled_shards:
                self._ai_controllers[shard_index].maintain_entities_motion(members)
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
                    {entity.id for entity in members},
                    tuple(members),
                    shared_frame,
                )
            )

        for future in futures:
            future.result()
    
    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0, controlled_entity_ids=None):
        """更新控制"""
        # 获取键盘输入
        keys = pygame.key.get_pressed()
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        target_entities = [entity for entity in entities if controlled_ids is None or entity.id in controlled_ids]

        # 更新 AI 控制（并行分片）；异常时回退到单线程，避免中断对局。
        try:
            self._update_ai_parallel(entities, map_manager, rules_engine, game_time, game_duration, controlled_entity_ids=controlled_ids)
        except Exception:
            self._ai_controllers[0].update(target_entities, map_manager, rules_engine, game_time, game_duration, controlled_entity_ids=controlled_ids, controlled_entities=tuple(target_entities))

        # 手动输入最后覆盖 AI，仅作用于正在手操的单位
        self.manual_controller.update(keys, target_entities)
    
    def set_control_mode(self, mode):
        """设置控制模式"""
        if mode in ['manual', 'ai']:
            self.control_mode = mode
    
    def get_control_mode(self):
        """获取当前控制模式"""
        return self.control_mode
