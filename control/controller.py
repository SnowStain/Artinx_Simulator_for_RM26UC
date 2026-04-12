#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
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
        self._controller_dispatch_interval = max(
            0.04,
            min(
                float(ai_config.get('controller_dispatch_interval_sec', max(0.04, float(ai_config.get('update_interval_sec', 0.16)) * 0.5))),
                max(0.04, float(ai_config.get('update_interval_sec', 0.16))),
            ),
        )
        self._player_control_dispatch_interval = max(
            self._controller_dispatch_interval,
            float(ai_config.get('player_control_dispatch_interval_sec', max(0.20, self._controller_dispatch_interval * 1.5))),
        )
        self._standalone_player_control_dispatch_interval = max(
            self._player_control_dispatch_interval,
            float(ai_config.get('standalone_player_control_dispatch_interval_sec', max(0.32, self._player_control_dispatch_interval * 1.6))),
        )
        self._controller_time_budget_sec = max(0.0, float(ai_config.get('controller_time_budget_ms', 12.0)) / 1000.0)
        self._controller_dispatch_backoff_max = max(1.0, float(ai_config.get('controller_dispatch_backoff_max', 2.5)))
        self._last_ai_dispatch_duration_sec = 0.0
        self._last_ai_dispatch_time = -1e9
        
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

    def _collect_ai_shard_entities(self, entities, controlled_ids=None, excluded_ids=None):
        controlled_ids = None if controlled_ids is None else set(controlled_ids)
        excluded_ids = set(excluded_ids or ())
        shard_entities = [[] for _ in range(self._ai_worker_threads)]
        for entity in entities:
            if entity.id in excluded_ids:
                continue
            if controlled_ids is not None and entity.id not in controlled_ids:
                continue
            if not self._is_ai_controllable_entity(entity):
                continue
            role_key = self._entity_role_key(entity)
            shard_index = self._role_shard_map.get(role_key)
            if shard_index is None:
                shard_index = self._assign_entity_to_shard(entity.id)
            shard_entities[shard_index].append(entity)
        return shard_entities

    def _update_ai_parallel(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0, controlled_entity_ids=None, excluded_entity_ids=None, player_focus_entity_id=None):
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        excluded_ids = set(excluded_entity_ids or ())
        map_center_x = None
        if map_manager is not None:
            map_center_x = float(getattr(map_manager, 'map_width', 0.0)) * 0.5
        shared_frame = AIFrameContext.from_entities(entities, map_center_x=map_center_x, player_entity_id=player_focus_entity_id)
        shard_entities = self._collect_ai_shard_entities(entities, controlled_ids=controlled_ids, excluded_ids=excluded_ids)

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

    def _maintain_ai_motion_only(self, entities, controlled_entity_ids=None, excluded_entity_ids=None):
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        excluded_ids = set(excluded_entity_ids or ())
        shard_entities = self._collect_ai_shard_entities(entities, controlled_ids=controlled_ids, excluded_ids=excluded_ids)
        for shard_index, members in enumerate(shard_entities):
            if not members:
                continue
            self._ai_controllers[shard_index].maintain_entities_motion(members)

    def _should_dispatch_ai(self, game_time, player_control_active=False, standalone_player_mode=False):
        if standalone_player_mode:
            dispatch_interval = self._standalone_player_control_dispatch_interval
        else:
            dispatch_interval = self._player_control_dispatch_interval if player_control_active else self._controller_dispatch_interval
        if self._controller_time_budget_sec > 1e-6 and self._last_ai_dispatch_duration_sec > self._controller_time_budget_sec:
            overload_ratio = self._last_ai_dispatch_duration_sec / self._controller_time_budget_sec
            dispatch_interval *= min(self._controller_dispatch_backoff_max, max(1.0, overload_ratio))
        if self._last_ai_dispatch_time <= -1e8:
            self._last_ai_dispatch_time = float(game_time)
            return True
        if float(game_time) - self._last_ai_dispatch_time + 1e-9 < dispatch_interval:
            return False
        self._last_ai_dispatch_time = float(game_time)
        return True
    
    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0, controlled_entity_ids=None, ai_excluded_entity_ids=None, manual_entity_ids=None, manual_state=None):
        """更新控制"""
        # 获取键盘输入
        keys = pygame.key.get_pressed()
        controlled_ids = None if controlled_entity_ids is None else set(controlled_entity_ids)
        manual_ids = set(manual_entity_ids or ())
        target_entities = [entity for entity in entities if entity.id in manual_ids]
        standalone_player_mode = bool(self.config.get('simulator', {}).get('standalone_3d_program', False)) and bool(manual_ids)
        player_focus_entity_id = next(iter(manual_ids), None)

        # 更新 AI 控制（并行分片）；异常时回退到单线程，避免中断对局。
        dispatch_ai = self._should_dispatch_ai(
            game_time,
            player_control_active=bool(manual_ids),
            standalone_player_mode=standalone_player_mode,
        )
        dispatch_started_at = time.perf_counter() if dispatch_ai else None
        try:
            if dispatch_ai:
                self._update_ai_parallel(
                    entities,
                    map_manager,
                    rules_engine,
                    game_time,
                    game_duration,
                    controlled_entity_ids=controlled_ids,
                    excluded_entity_ids=ai_excluded_entity_ids,
                    player_focus_entity_id=player_focus_entity_id,
                )
                if dispatch_started_at is not None:
                    self._last_ai_dispatch_duration_sec = max(0.0, time.perf_counter() - dispatch_started_at)
            else:
                self._maintain_ai_motion_only(entities, controlled_entity_ids=controlled_ids, excluded_entity_ids=ai_excluded_entity_ids)
        except Exception:
            ai_entities = [entity for entity in entities if entity.id not in set(ai_excluded_entity_ids or ())]
            if dispatch_ai:
                self._ai_controllers[0].update(ai_entities, map_manager, rules_engine, game_time, game_duration, controlled_entity_ids=controlled_ids, controlled_entities=tuple(ai_entities))
                if dispatch_started_at is not None:
                    self._last_ai_dispatch_duration_sec = max(0.0, time.perf_counter() - dispatch_started_at)
            else:
                self._ai_controllers[0].maintain_entities_motion(ai_entities)

        # 手动输入最后覆盖 AI，仅作用于正在手操的单位
        self.manual_controller.update(keys, target_entities, all_entities=entities, rules_engine=rules_engine, manual_state=manual_state)

    def set_player_look_sensitivity(self, yaw_sensitivity_deg=None, pitch_sensitivity_deg=None):
        if hasattr(self.manual_controller, 'set_look_sensitivity'):
            self.manual_controller.set_look_sensitivity(yaw_sensitivity_deg, pitch_sensitivity_deg)
    
    def set_control_mode(self, mode):
        """设置控制模式"""
        if mode in ['manual', 'ai']:
            self.control_mode = mode
    
    def get_control_mode(self):
        """获取当前控制模式"""
        return self.control_mode
