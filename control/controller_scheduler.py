#!/usr/bin/env python3
# -*- coding: utf-8 -*-


class ControllerShardScheduler:
    def __init__(self, shard_count, shard_budget_per_frame):
        self._shard_count = max(1, int(shard_count))
        self._shard_budget_per_frame = max(1, min(self._shard_count, int(shard_budget_per_frame)))
        self._cursor = 0

    def select_active_shards(self, available_shards):
        ordered_available = sorted({int(index) for index in available_shards if 0 <= int(index) < self._shard_count})
        if not ordered_available:
            return ()
        if len(ordered_available) <= self._shard_budget_per_frame:
            self._cursor = (ordered_available[-1] + 1) % self._shard_count
            return tuple(ordered_available)

        available_set = set(ordered_available)
        selected = []
        for offset in range(self._shard_count):
            shard_index = (self._cursor + offset) % self._shard_count
            if shard_index not in available_set:
                continue
            selected.append(shard_index)
            if len(selected) >= self._shard_budget_per_frame:
                break

        if len(selected) < self._shard_budget_per_frame:
            for shard_index in ordered_available:
                if shard_index in selected:
                    continue
                selected.append(shard_index)
                if len(selected) >= self._shard_budget_per_frame:
                    break

        self._cursor = (selected[-1] + 1) % self._shard_count
        return tuple(selected)