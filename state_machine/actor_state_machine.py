#!/usr/bin/env python3
# -*- coding: utf-8 -*-


class ActorStateMachine:
    def __init__(self):
        self._state_groups = {}
        self._default_states = {}

    def register_state_group(self, group_name, handlers, default_state):
        normalized_group = str(group_name or '').strip()
        if not normalized_group:
            return
        self._state_groups[normalized_group] = dict(handlers or {})
        self._default_states[normalized_group] = str(default_state or '')

    def ensure_state(self, actor, group_name):
        attr_name = f'{group_name}_state'
        current_state = getattr(actor, attr_name, '')
        if current_state in self._state_groups.get(group_name, {}):
            return current_state
        default_state = self._default_states.get(group_name, '')
        if default_state:
            setattr(actor, attr_name, default_state)
        return default_state

    def set_state(self, actor, group_name, state_name):
        normalized_state = str(state_name or '')
        if normalized_state not in self._state_groups.get(group_name, {}):
            return False
        setattr(actor, f'{group_name}_state', normalized_state)
        return True

    def update_group(self, actor, group_name):
        current_state = self.ensure_state(actor, group_name)
        handler = self._state_groups.get(group_name, {}).get(current_state)
        if handler is None:
            return False
        handler(actor)
        return True