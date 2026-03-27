#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass, field


SUCCESS = 'success'
FAILURE = 'failure'
RUNNING = 'running'


@dataclass
class BehaviorContext:
    controller: object
    entity: object
    entities: list
    map_manager: object = None
    rules_engine: object = None
    game_time: float = 0.0
    game_duration: float = 0.0
    data: dict = field(default_factory=dict)


class Node:
    def tick(self, context):
        raise NotImplementedError


class Selector(Node):
    def __init__(self, *children):
        self.children = children

    def tick(self, context):
        for child in self.children:
            result = child.tick(context)
            if result in {SUCCESS, RUNNING}:
                return result
        return FAILURE


class Sequence(Node):
    def __init__(self, *children):
        self.children = children

    def tick(self, context):
        for child in self.children:
            result = child.tick(context)
            if result != SUCCESS:
                return result
        return SUCCESS


class Condition(Node):
    def __init__(self, predicate):
        self.predicate = predicate

    def tick(self, context):
        return SUCCESS if self.predicate(context) else FAILURE


class Action(Node):
    def __init__(self, handler):
        self.handler = handler

    def tick(self, context):
        return self.handler(context)
