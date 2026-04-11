#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dataclasses import dataclass


def _role_key(entity):
    if getattr(entity, 'type', None) == 'sentry':
        return 'sentry'
    return {
        '英雄': 'hero',
        '工程': 'engineer',
        '步兵': 'infantry',
    }.get(getattr(entity, 'robot_type', ''), 'infantry')


@dataclass(frozen=True)
class AIFrameContext:
    entities: tuple
    alive_by_team: dict
    structures: dict
    role_members: dict
    team_health: dict
    half_pressure: dict
    player_entity_id: str | None
    player_team: str | None
    player_position: tuple | None

    @classmethod
    def from_entities(cls, entities, map_center_x=None, player_entity_id=None):
        all_entities = tuple(entities or ())
        alive_by_team = {'red': [], 'blue': []}
        structures = {}
        role_members = {}
        player_team = None
        player_position = None
        team_health = {
            'red': [0.0, 0.0],
            'blue': [0.0, 0.0],
        }
        half_pressure = {
            'red': {
                'ally_enemy_half_count': 0,
                'enemy_own_half_count': 0,
                'ally_enemy_half_roles': set(),
            },
            'blue': {
                'ally_enemy_half_count': 0,
                'enemy_own_half_count': 0,
                'ally_enemy_half_roles': set(),
            },
        }

        for entity in all_entities:
            team = getattr(entity, 'team', None)
            if team not in alive_by_team:
                continue
            if player_entity_id is not None and getattr(entity, 'id', None) == player_entity_id and getattr(entity, 'type', None) in {'robot', 'sentry'} and entity.is_alive():
                player_team = team
                player_position = (float(entity.position['x']), float(entity.position['y']))
            if getattr(entity, 'type', None) in {'base', 'outpost'} and structures.get((team, entity.type)) is None:
                structures[(team, entity.type)] = entity
            if getattr(entity, 'type', None) not in {'robot', 'sentry'}:
                continue
            max_health = max(0.0, float(getattr(entity, 'max_health', 0.0)))
            team_health[team][1] += max_health
            if not entity.is_alive():
                continue
            alive_by_team[team].append(entity)
            team_health[team][0] += max(0.0, float(getattr(entity, 'health', 0.0)))
            role_key = _role_key(entity)
            role_members.setdefault((team, role_key), []).append(entity)

            if role_key not in {'sentry', 'infantry', 'hero'}:
                continue
            if map_center_x is None:
                continue
            x_coord = float(entity.position['x'])
            if team == 'red':
                in_enemy_half = x_coord >= float(map_center_x)
                if in_enemy_half:
                    half_pressure['red']['ally_enemy_half_count'] += 1
                    half_pressure['red']['ally_enemy_half_roles'].add(role_key)
                    half_pressure['blue']['enemy_own_half_count'] += 1
            else:
                in_enemy_half = x_coord <= float(map_center_x)
                if in_enemy_half:
                    half_pressure['blue']['ally_enemy_half_count'] += 1
                    half_pressure['blue']['ally_enemy_half_roles'].add(role_key)
                    half_pressure['red']['enemy_own_half_count'] += 1

        frozen_alive = {
            team: tuple(members)
            for team, members in alive_by_team.items()
        }
        frozen_roles = {
            key: tuple(members)
            for key, members in role_members.items()
        }
        frozen_team_health = {
            team: (
                values[0],
                values[1],
                values[0] / values[1] if values[1] > 1e-6 else 0.0,
            )
            for team, values in team_health.items()
        }
        frozen_half_pressure = {
            team: {
                'ally_enemy_half_count': int(summary['ally_enemy_half_count']),
                'enemy_own_half_count': int(summary['enemy_own_half_count']),
                'ally_enemy_half_roles': frozenset(summary['ally_enemy_half_roles']),
            }
            for team, summary in half_pressure.items()
        }
        return cls(
            entities=all_entities,
            alive_by_team=frozen_alive,
            structures=structures,
            role_members=frozen_roles,
            team_health=frozen_team_health,
            half_pressure=frozen_half_pressure,
            player_entity_id=str(player_entity_id) if player_entity_id is not None else None,
            player_team=player_team,
            player_position=player_position,
        )

    def allies_for(self, team, exclude_id=None):
        members = self.alive_by_team.get(team, ())
        if exclude_id is None:
            return members
        return tuple(entity for entity in members if entity.id != exclude_id)

    def enemies_for(self, team):
        enemy_team = 'blue' if team == 'red' else 'red'
        return self.alive_by_team.get(enemy_team, ())

    def structure(self, team, entity_type):
        return self.structures.get((team, entity_type))

    def first_role(self, team, role_key, exclude_id=None):
        members = self.role_members.get((team, role_key), ())
        for entity in members:
            if exclude_id is not None and entity.id == exclude_id:
                continue
            return entity
        return None

    def health_snapshot(self, team):
        return self.team_health.get(team, (0.0, 0.0, 0.0))

    def pressure_snapshot(self, team):
        return self.half_pressure.get(team, {
            'ally_enemy_half_count': 0,
            'enemy_own_half_count': 0,
            'ally_enemy_half_roles': frozenset(),
        })