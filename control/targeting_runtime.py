#!/usr/bin/env python3
# -*- coding: utf-8 -*-


class TargetingRuntime:
    def __init__(self, controller):
        self._controller = controller

    def target_assessment(self, entity, other, distance, rules_engine, require_fov=False):
        controller = self._controller
        if rules_engine is None:
            return {}
        cache_key = (entity.id, other.id, round(float(distance), 1), bool(require_fov))
        cached = controller._frame_target_assessment_cache.get(cache_key)
        if cached is not None:
            return cached
        assessment = rules_engine.evaluate_auto_aim_target(entity, other, distance=distance, require_fov=require_fov)
        controller._frame_target_assessment_cache[cache_key] = assessment
        return assessment

    def priority_target_threat_score(self, source_entity, target_entity):
        controller = self._controller
        role_key = controller._role_key(target_entity)
        threat_score = {
            'hero': 320.0,
            'sentry': 300.0,
            'infantry': 240.0,
            'engineer': 100.0,
        }.get(role_key, 160.0)
        if target_entity.type == 'outpost':
            threat_score = 150.0
        elif target_entity.type == 'base':
            threat_score = 110.0
        if getattr(source_entity, 'last_damage_source_id', None) == target_entity.id:
            threat_score += 120.0
        target_state = getattr(target_entity, 'target', None)
        if isinstance(target_state, dict) and target_state.get('id') == source_entity.id:
            threat_score += 100.0
        if getattr(target_entity, 'fire_control_state', 'idle') == 'firing':
            threat_score += 70.0
        return threat_score

    def priority_target_score(self, entity, other, priority_map, rules_engine=None, max_distance=None, require_fov=False):
        controller = self._controller
        distance = controller._distance(entity, other)
        if max_distance is not None and distance > max_distance:
            return None
        hp_ratio = 1.0
        if float(getattr(other, 'max_health', 0.0)) > 0.0:
            hp_ratio = max(0.0, min(1.0, float(getattr(other, 'health', 0.0)) / float(other.max_health)))
        reference_distance = max_distance if max_distance is not None else controller._meters_to_world_units(9.0)
        distance_score = max(0.0, 1.0 - distance / max(reference_distance, 1e-6)) * 180.0
        finish_score = (1.0 - hp_ratio) * 140.0
        if float(getattr(other, 'health', 0.0)) <= max(1.0, float(getattr(other, 'max_health', 0.0)) * 0.28):
            finish_score += 75.0
        visibility_score = 0.0
        if rules_engine is not None and entity.type in {'robot', 'sentry'} and getattr(entity, 'robot_type', '') != '工程':
            assessment = self.target_assessment(entity, other, distance, rules_engine, require_fov=require_fov)
            visibility_key = 'can_auto_aim' if require_fov else 'can_track'
            if assessment.get(visibility_key, False):
                visibility_score += 220.0
                if assessment.get('can_auto_aim', False):
                    visibility_score += 60.0
            elif require_fov:
                visibility_score -= 260.0
            elif not assessment.get('line_of_sight', True):
                visibility_score -= 180.0
        score = priority_map.get(other.type, 0) * 220.0
        score += self.priority_target_threat_score(entity, other)
        score += distance_score
        score += finish_score
        score += visibility_score
        if other.type in {'outpost', 'base'} and distance <= controller._meters_to_world_units(8.5):
            score += 50.0
        return score

    def select_priority_target_entity(self, entity, enemies, strategy, rules_engine=None, max_distance=None, require_fov=False):
        enemy_base = None
        enemy_outpost_alive = False
        for other in enemies:
            if other.type == 'base':
                enemy_base = other
            elif other.type == 'outpost' and other.is_alive():
                enemy_outpost_alive = True
        base_unlocked = False
        if enemy_base is not None and enemy_base.is_alive() and not enemy_outpost_alive:
            if rules_engine is not None and hasattr(rules_engine, 'is_base_shielded'):
                base_unlocked = not bool(rules_engine.is_base_shielded(enemy_base))
            else:
                base_unlocked = True
        if base_unlocked and not require_fov:
            return enemy_base
        priority_targets = strategy.get('priority_targets', ['sentry', 'robot', 'outpost', 'base'])
        priority_map = {target_type: len(priority_targets) - index for index, target_type in enumerate(priority_targets)}
        visible_combat_target_exists = False
        if rules_engine is not None and entity.type in {'robot', 'sentry'}:
            for other in enemies:
                if other.type not in {'robot', 'sentry'}:
                    continue
                distance = self._controller._distance(entity, other)
                if max_distance is not None and distance > max_distance:
                    continue
                assessment = self.target_assessment(entity, other, distance, rules_engine, require_fov=require_fov)
                if assessment.get('can_auto_aim' if require_fov else 'can_track', False):
                    visible_combat_target_exists = True
                    break
        best_target = None
        best_score = None
        for other in enemies:
            if other.type == 'base' and rules_engine is not None and hasattr(rules_engine, 'is_base_shielded') and rules_engine.is_base_shielded(other):
                continue
            if visible_combat_target_exists and other.type in {'outpost', 'base'}:
                continue
            score = self.priority_target_score(entity, other, priority_map, rules_engine=rules_engine, max_distance=max_distance, require_fov=require_fov)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_score = score
                best_target = other
        return best_target

    def select_priority_target(self, entity, enemies, strategy, rules_engine=None, max_distance=None, require_fov=False):
        best_target = self.select_priority_target_entity(entity, enemies, strategy, rules_engine=rules_engine, max_distance=max_distance, require_fov=require_fov)
        if best_target is None:
            return None
        return self._controller.entity_to_target(best_target, entity)