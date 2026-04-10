#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import time
from concurrent.futures import ThreadPoolExecutor


class EntityPathfinderRouter:
    def __init__(self):
        self._lock = threading.Lock()
        self._executors = {}

    def _executor_for(self, entity_id):
        now = time.perf_counter()
        with self._lock:
            entry = self._executors.get(entity_id)
            if entry is None:
                executor = ThreadPoolExecutor(max_workers=1)
                entry = {
                    'executor': executor,
                    'last_used': now,
                }
                self._executors[entity_id] = entry
            else:
                entry['last_used'] = now
            return entry['executor']

    def submit(self, entity_id, fn, *args, **kwargs):
        executor = self._executor_for(entity_id)
        return executor.submit(fn, *args, **kwargs)

    def prune(self, active_entity_ids):
        active_ids = set(active_entity_ids or ())
        stale_entries = []
        with self._lock:
            for entity_id in list(self._executors.keys()):
                if entity_id in active_ids:
                    continue
                stale_entries.append(self._executors.pop(entity_id))
        for entry in stale_entries:
            entry['executor'].shutdown(wait=False)

    def shutdown(self):
        with self._lock:
            entries = list(self._executors.values())
            self._executors.clear()
        for entry in entries:
            entry['executor'].shutdown(wait=False)