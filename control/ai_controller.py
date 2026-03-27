#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from control.behavior_tree import Action, BehaviorContext, Condition, Selector, Sequence, SUCCESS, FAILURE


class AIController:
    def __init__(self, config):
        self.config = config
        self.ai_strategy = config.get('ai', {}).get('strategy', {})
        self._patrol_index = {}
        self.enable_entity_movement = config.get('simulator', {}).get('enable_entity_movement', True)
        self._path_cache = {}
        self._ai_update_interval = float(config.get('ai', {}).get('update_interval_sec', 0.12))
        self._path_replan_interval = float(config.get('ai', {}).get('path_replan_interval_sec', 0.35))
        self._last_ai_update_time = {}
        self._entity_path_state = {}
        self.role_trees = self._build_role_trees()

    def _build_role_trees(self):
        sentry_tree = Selector(
            Sequence(Condition(lambda ctx: getattr(ctx.entity, 'front_gun_locked', False)), Action(self._action_return_to_supply_unlock)),
            Sequence(Condition(lambda ctx: self._is_opening_phase(ctx) and self._can_sentry_exchange(ctx)), Action(self._action_sentry_opening_exchange)),
            Sequence(Condition(self._should_recover_after_respawn), Action(self._action_recover_after_respawn)),
            Sequence(Condition(self._is_critical_state), Action(self._action_emergency_retreat)),
            Sequence(Condition(self._should_protect_hero), Action(self._action_protect_hero)),
            Sequence(Condition(self._should_intercept_enemy_engineer), Action(self._action_intercept_enemy_engineer)),
            Sequence(Condition(self._should_support_infantry_push), Action(self._action_support_infantry_push)),
            Sequence(Condition(self._has_teamfight_window), Action(self._action_teamfight_cover)),
            Sequence(Condition(self._has_target), Action(self._action_sentry_engage)),
            Sequence(Condition(self._should_cross_terrain), Action(self._action_cross_terrain)),
            Sequence(Condition(self._should_push_outpost), Action(self._action_push_outpost)),
            Sequence(Condition(self._should_push_base), Action(self._action_push_base)),
            Action(self._action_patrol_key_facilities),
        )

        infantry_tree = Selector(
            Sequence(Condition(lambda ctx: self._is_opening_phase(ctx) and self._needs_supply(ctx)), Action(self._action_opening_supply)),
            Sequence(Condition(self._should_recover_after_respawn), Action(self._action_recover_after_respawn)),
            Sequence(Condition(self._is_critical_state), Action(self._action_emergency_retreat)),
            Sequence(Condition(self._should_defend_outpost_from_hero), Action(self._action_defend_outpost_from_hero)),
            Sequence(Condition(self._should_intercept_enemy_engineer), Action(self._action_intercept_enemy_engineer)),
            Sequence(Condition(self._should_activate_energy), Action(self._action_activate_energy)),
            Sequence(Condition(self._should_cross_terrain), Action(self._action_cross_terrain)),
            Sequence(Condition(self._should_push_outpost), Action(self._action_push_outpost)),
            Sequence(Condition(self._has_teamfight_window), Action(self._action_teamfight_push)),
            Sequence(Condition(self._has_target), Action(self._action_pursue_enemy)),
            Sequence(Condition(self._should_push_base), Action(self._action_push_base)),
            Action(self._action_patrol_key_facilities),
        )

        hero_tree = Selector(
            Sequence(Condition(lambda ctx: self._is_opening_phase(ctx) and self._needs_supply(ctx)), Action(self._action_opening_supply)),
            Sequence(Condition(self._should_recover_after_respawn), Action(self._action_recover_after_respawn)),
            Sequence(Condition(self._should_hero_seek_cover), Action(self._action_hero_seek_cover)),
            Sequence(Condition(self._should_hero_lob_outpost), Action(self._action_hero_lob_outpost)),
            Sequence(Condition(self._should_hero_lob_base), Action(self._action_hero_lob_base)),
            Sequence(Condition(self._should_cross_terrain), Action(self._action_cross_terrain)),
            Sequence(Condition(self._has_target), Action(self._action_pursue_enemy)),
            Sequence(Condition(self._should_push_base), Action(self._action_push_base)),
            Action(self._action_patrol_key_facilities),
        )

        engineer_tree = Selector(
            Sequence(Condition(self._should_recover_after_respawn), Action(self._action_recover_after_respawn)),
            Sequence(Condition(self._is_critical_state), Action(self._action_emergency_retreat)),
            Sequence(Condition(self._needs_mining_cycle), Action(self._action_engineer_mining_cycle)),
            Sequence(Condition(self._should_activate_energy), Action(self._action_activate_energy)),
            Sequence(Condition(self._should_cross_terrain), Action(self._action_cross_terrain)),
            Sequence(Condition(self._needs_structure_support), Action(self._action_support_structures)),
            Sequence(Condition(self._has_teamfight_window), Action(self._action_teamfight_cover)),
            Action(self._action_support_sentry_screen),
        )

        return {
            'sentry': sentry_tree,
            'infantry': infantry_tree,
            'hero': hero_tree,
            'engineer': engineer_tree,
        }

    def _meters_to_world_units(self, meters, map_manager=None):
        if map_manager is not None and hasattr(map_manager, 'meters_to_world_units'):
            return map_manager.meters_to_world_units(meters)
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return meters * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)

    def update(self, entities, map_manager=None, rules_engine=None, game_time=0.0, game_duration=0.0):
        for entity in entities:
            if not self._should_control_entity(entity):
                continue
            last_update = self._last_ai_update_time.get(entity.id, -1e9)
            if game_time - last_update < self._ai_update_interval:
                self._maintain_continuous_motion(entity)
                continue
            self._last_ai_update_time[entity.id] = game_time
            context = self._build_context(entity, entities, map_manager, rules_engine, game_time, game_duration)
            tree = self.role_trees.get(context.data['role_key'])
            if tree is None:
                self._apply_idle_decision(entity, '未定义角色行为树')
                continue
            result = tree.tick(context)
            decision = context.data.get('decision')
            if result == FAILURE or decision is None:
                decision = self._idle_decision(entity, '行为树未命中有效分支，原地待命')
            self._apply_decision(entity, decision, rules_engine)

    def _should_control_entity(self, entity):
        if not entity.is_alive():
            return False
        if entity.type not in {'robot', 'sentry'}:
            return False
        return True

    def _build_context(self, entity, entities, map_manager, rules_engine, game_time, game_duration):
        role_key = self._role_key(entity)
        strategy = self.ai_strategy.get(role_key, self.ai_strategy.get('infantry', {}))
        enemies = [other for other in entities if other.team != entity.team and other.is_alive()]
        allies = [other for other in entities if other.team == entity.team and other.id != entity.id and other.is_alive()]
        target = self.select_priority_target(entity, enemies, strategy, rules_engine)
        nearby_allies = [other for other in allies if self._distance(entity, other) <= self._meters_to_world_units(5.0, map_manager)]
        nearby_enemies = [other for other in enemies if self._distance(entity, other) <= self._meters_to_world_units(6.0, map_manager)]
        own_outpost = self._find_entity(entities, entity.team, 'outpost')
        own_base = self._find_entity(entities, entity.team, 'base')
        enemy_team = 'blue' if entity.team == 'red' else 'red'
        enemy_outpost = self._find_entity(entities, enemy_team, 'outpost')
        enemy_base = self._find_entity(entities, enemy_team, 'base')
        allied_sentry = self._find_entity(entities, entity.team, 'sentry')
        allied_hero = self._find_entity_by_role(entities, entity.team, 'hero')
        allied_infantry = self._find_entity_by_role(entities, entity.team, 'infantry', exclude_id=entity.id)
        enemy_hero = self._find_entity_by_role(entities, enemy_team, 'hero')
        enemy_engineer = self._find_entity_by_role(entities, enemy_team, 'engineer')
        energy_anchor = self.get_energy_anchor(map_manager)
        mining_anchor = self.get_mining_anchor(entity, map_manager)
        exchange_anchor = self.get_exchange_anchor(entity, map_manager)
        map_center = self.get_map_center(map_manager)
        health_ratio = 0.0 if entity.max_health <= 0 else entity.health / entity.max_health
        heat_ratio = 0.0 if entity.max_heat <= 0 else entity.heat / entity.max_heat
        low_ammo_threshold = int(strategy.get('low_ammo_threshold', 40 if entity.type == 'sentry' else 25))
        supply_claimable = self._supply_claimable_ammo(entity, rules_engine, game_time)
        supply_eta = self._next_supply_eta(rules_engine, game_time)
        supply_candidate = self._select_supply_runner(entity, allies + [entity], rules_engine, game_time)
        data = {
            'role_key': role_key,
            'strategy': strategy,
            'target': target,
            'nearby_allies': nearby_allies,
            'nearby_enemies': nearby_enemies,
            'own_outpost': own_outpost,
            'own_base': own_base,
            'enemy_outpost': enemy_outpost,
            'enemy_base': enemy_base,
            'allied_sentry': allied_sentry,
            'allied_hero': allied_hero,
            'allied_infantry': allied_infantry,
            'enemy_hero': enemy_hero,
            'enemy_engineer': enemy_engineer,
            'energy_anchor': energy_anchor,
            'mining_anchor': mining_anchor,
            'exchange_anchor': exchange_anchor,
            'map_center': map_center,
            'health_ratio': health_ratio,
            'heat_ratio': heat_ratio,
            'ammo_low': getattr(entity, 'ammo', 0) <= low_ammo_threshold,
            'low_ammo_threshold': low_ammo_threshold,
            'supply_claimable': supply_claimable,
            'supply_eta': supply_eta,
            'supply_candidate_id': supply_candidate.id if supply_candidate is not None else None,
            'opening_phase': game_time <= min(45.0, max(30.0, game_duration * 0.12 if game_duration > 0 else 45.0)),
            'late_phase': game_duration > 0 and (game_duration - game_time) <= 120.0,
            'outnumbered': len(nearby_enemies) > len(nearby_allies) + 1,
            'teamfight_ready': len(nearby_allies) >= 1 and len(nearby_enemies) >= 1,
            'transit_anchor': None,
            'carried_minerals': int(getattr(entity, 'carried_minerals', 0)),
            'energy_buff_active': any(float(getattr(other, 'timed_buffs', {}).get('energy_mechanism_boost', 0.0)) > 0.0 for other in [entity] + allies),
        }
        return BehaviorContext(self, entity, entities, map_manager, rules_engine, game_time, game_duration, data)

    def _role_key(self, entity):
        if entity.type == 'sentry':
            return 'sentry'
        type_map = {
            '英雄': 'hero',
            '工程': 'engineer',
            '步兵': 'infantry',
        }
        return type_map.get(getattr(entity, 'robot_type', ''), 'infantry')

    def _idle_decision(self, entity, summary):
        return {
            'summary': summary,
            'target': None,
            'aim_point': None,
            'navigation_target': None,
            'movement_target': None,
            'velocity': (0.0, 0.0),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'searching',
            'angular_velocity': 0.0,
        }

    def _apply_idle_decision(self, entity, summary):
        self._apply_decision(entity, self._idle_decision(entity, summary), None)

    def _apply_decision(self, entity, decision, rules_engine):
        entity.ai_decision = decision.get('summary', '')
        entity.target = decision.get('target')
        entity.ai_navigation_target = decision.get('navigation_target')
        entity.ai_movement_target = decision.get('movement_target')
        entity.fire_control_state = decision.get('fire_control_state', 'idle')
        entity.chassis_state = decision.get('chassis_state', 'normal')
        entity.turret_state = decision.get('turret_state', 'searching')
        move_x, move_y = decision.get('velocity', (0.0, 0.0))
        entity.ai_navigation_velocity = (move_x, move_y)
        entity.set_velocity(move_x, move_y)
        entity.angular_velocity = decision.get('angular_velocity', 0.0)
        aim_point = decision.get('aim_point')
        if aim_point is not None:
            dx = aim_point[0] - entity.position['x']
            dy = aim_point[1] - entity.position['y']
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                entity.turret_angle = math.degrees(math.atan2(dy, dx))
        desired_posture = decision.get('posture')
        if desired_posture and desired_posture != getattr(entity, 'posture', 'mobile') and rules_engine is not None:
            rules_engine.request_posture_change(entity, desired_posture)

    def _maintain_continuous_motion(self, entity):
        move_x, move_y = getattr(entity, 'ai_navigation_velocity', (0.0, 0.0))
        if abs(move_x) <= 1e-6 and abs(move_y) <= 1e-6:
            return
        entity.set_velocity(move_x, move_y)

    def _is_opening_phase(self, context):
        return bool(context.data.get('opening_phase'))

    def _needs_supply(self, context):
        entity = context.entity
        if self._is_opening_phase(context):
            opening_target = self._opening_ammo_target(context)
            if opening_target > 0 and getattr(entity, 'ammo', 0) < opening_target:
                return True
        if getattr(entity, 'ammo', 0) > context.data.get('low_ammo_threshold', 20):
            return False
        if context.data.get('supply_candidate_id') != entity.id:
            return False
        claimable = context.data.get('supply_claimable', 0)
        eta = context.data.get('supply_eta', 999.0)
        return claimable > 0 or eta <= 10.0

    def _opening_ammo_target(self, context):
        entity = context.entity
        purchase_rules = context.rules_engine.rules.get('ammo_purchase', {}) if context.rules_engine is not None else {}
        opening_targets = purchase_rules.get('opening_targets', {})
        if getattr(entity, 'ammo_type', None) == '42mm':
            return int(opening_targets.get('hero_42mm', 4))
        if getattr(entity, 'ammo_type', None) == '17mm' and entity.type == 'robot':
            return int(opening_targets.get('infantry_17mm', 40))
        return 0

    def _is_critical_state(self, context):
        return (
            context.data.get('health_ratio', 1.0) <= 0.35
            or context.data.get('heat_ratio', 0.0) >= 0.82
            or (context.data.get('ammo_low') and context.data.get('outnumbered'))
        )

    def _has_target(self, context):
        return context.data.get('target') is not None

    def _has_teamfight_window(self, context):
        return bool(context.data.get('teamfight_ready'))

    def _should_claim_buff(self, context):
        return context.data.get('role_key') in {'hero', 'infantry'} and getattr(context.entity, 'terrain_buff_timer', 0.0) <= 0.25

    def _should_activate_energy(self, context):
        role_key = context.data.get('role_key')
        if role_key not in {'engineer', 'infantry'}:
            return False
        if context.data.get('energy_anchor') is None or context.data.get('energy_buff_active'):
            return False
        if role_key == 'engineer' and context.data.get('carried_minerals', 0) > 0:
            return False
        if role_key == 'infantry' and context.data.get('outnumbered', False):
            return False
        return 30.0 <= context.game_time <= max(45.0, context.game_duration - 75.0)

    def _should_cross_terrain(self, context):
        return getattr(context.entity, 'terrain_buff_timer', 0.0) <= 0.25

    def _should_recover_after_respawn(self, context):
        entity = context.entity
        if getattr(entity, 'front_gun_locked', False):
            return True
        return getattr(entity, 'respawn_recovery_timer', 0.0) > 0.0

    def _should_defend_outpost_from_hero(self, context):
        if context.data.get('role_key') != 'infantry':
            return False
        own_outpost = context.data.get('own_outpost')
        enemy_hero = context.data.get('enemy_hero')
        if own_outpost is None or enemy_hero is None or not own_outpost.is_alive() or not enemy_hero.is_alive():
            return False
        return self._distance(own_outpost, enemy_hero) <= self._meters_to_world_units(8.0, context.map_manager)

    def _should_intercept_enemy_engineer(self, context):
        if context.data.get('role_key') not in {'infantry', 'sentry'}:
            return False
        enemy_engineer = context.data.get('enemy_engineer')
        if enemy_engineer is None or not enemy_engineer.is_alive():
            return False
        if getattr(enemy_engineer, 'carried_minerals', 0) > 0:
            return True
        enemy_base = context.data.get('enemy_base')
        if enemy_base is not None and self._distance(enemy_engineer, enemy_base) <= self._meters_to_world_units(7.5, context.map_manager):
            return True
        return False

    def _should_protect_hero(self, context):
        if context.data.get('role_key') != 'sentry':
            return False
        allied_hero = context.data.get('allied_hero')
        if allied_hero is None or not allied_hero.is_alive():
            return False
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (allied_hero.position['x'], allied_hero.position['y']), {'infantry', 'sentry'})
        return threat is not None and threat['distance'] <= self._meters_to_world_units(6.0, context.map_manager)

    def _should_support_infantry_push(self, context):
        if context.data.get('role_key') != 'sentry':
            return False
        allied_infantry = context.data.get('allied_infantry')
        enemy_outpost = context.data.get('enemy_outpost')
        if allied_infantry is None or enemy_outpost is None:
            return False
        return allied_infantry.is_alive() and enemy_outpost.is_alive()

    def _should_hero_seek_cover(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (context.entity.position['x'], context.entity.position['y']), {'infantry', 'sentry'})
        return threat is not None and threat['distance'] <= self._meters_to_world_units(6.0, context.map_manager)

    def _should_hero_lob_outpost(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        return enemy_outpost is not None and enemy_outpost.is_alive()

    def _should_hero_lob_base(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        enemy_base = context.data.get('enemy_base')
        return enemy_base is not None and enemy_base.is_alive() and (enemy_outpost is None or not enemy_outpost.is_alive())

    def _needs_structure_support(self, context):
        outpost = context.data.get('own_outpost')
        base = context.data.get('own_base')
        return (
            (outpost is not None and outpost.health < outpost.max_health * 0.65)
            or (base is not None and base.health < base.max_health * 0.85)
        )

    def _needs_mining_cycle(self, context):
        if context.data.get('role_key') != 'engineer':
            return False
        if context.data.get('carried_minerals', 0) > 0:
            return context.data.get('exchange_anchor') is not None
        return context.data.get('mining_anchor') is not None

    def _should_push_outpost(self, context):
        enemy_outpost = context.data.get('enemy_outpost')
        if enemy_outpost is None or not enemy_outpost.is_alive():
            return False
        return context.game_time >= 40.0 and not context.data.get('outnumbered', False)

    def _should_push_base(self, context):
        enemy_base = context.data.get('enemy_base')
        if enemy_base is None or not enemy_base.is_alive():
            return False
        enemy_outpost = context.data.get('enemy_outpost')
        return context.data.get('late_phase') or enemy_outpost is None or not enemy_outpost.is_alive()

    def _can_hero_lob_shot(self, context):
        if context.data.get('role_key') != 'hero':
            return False
        target = context.data.get('target')
        if target is None:
            return False
        highground = self._find_nearest_facility_center(context.map_manager, context.entity, ['second_step', 'fly_slope'])
        if highground is None:
            return False
        distance = target['distance']
        return distance >= self._meters_to_world_units(7.0, context.map_manager)

    def _can_sentry_exchange(self, context):
        entity = context.entity
        if entity.type != 'sentry' or context.rules_engine is None:
            return False
        if getattr(entity, 'exchange_cooldown', 0.0) > 0:
            return False
        gold = float(getattr(entity, 'gold', 0.0))
        ammo_cost = float(context.rules_engine.rules.get('sentry', {}).get('exchange', {}).get('ammo_cost', 0.0))
        opening_ammo_target = int(context.data.get('strategy', {}).get('opening_ammo_target', 340))
        return gold >= ammo_cost > 0 and getattr(entity, 'ammo', 0) < opening_ammo_target

    def _set_decision(self, context, summary, target=None, target_point=None, speed=None, posture=None, preferred_route=None, fire_control='idle', chassis_state='normal', turret_state='searching', angular_velocity=0.0, orbit=False):
        entity = context.entity
        move_target = target_point
        if preferred_route is not None:
            transit_destination = preferred_route.get('target') if isinstance(preferred_route, dict) else preferred_route
            transit_anchor = self.choose_transit_anchor(entity, transit_destination, context.map_manager, context.rules_engine)
            if transit_anchor is not None:
                move_target = transit_anchor
        velocity = (0.0, 0.0)
        if move_target is not None and speed is not None:
            if orbit and target is not None:
                velocity = self.maintain_distance(entity, target, preferred_route.get('distance', 0.0), speed)
            else:
                velocity = self.navigate_towards(entity, move_target, speed, context.map_manager)
        velocity = self._apply_local_avoidance(entity, velocity, context.entities, move_target)
        decision_target = target
        aim_point = target_point if target is None else (target['x'], target['y'])
        context.data['decision'] = {
            'summary': summary,
            'target': decision_target,
            'aim_point': aim_point,
            'navigation_target': target_point,
            'movement_target': move_target,
            'velocity': velocity,
            'fire_control_state': fire_control,
            'chassis_state': chassis_state,
            'turret_state': turret_state,
            'angular_velocity': angular_velocity,
            'posture': posture,
        }
        return SUCCESS

    def _action_return_to_supply_unlock(self, context):
        retreat_point = self.get_supply_slot(context.entity, context.map_manager)
        speed = self._meters_to_world_units(1.8, context.map_manager)
        return self._set_decision(context, '前管锁定，返回补给区解锁', target_point=retreat_point, speed=speed, posture='mobile')

    def _action_sentry_opening_exchange(self, context):
        result = context.rules_engine.request_exchange(context.entity, 'ammo', amount=1)
        summary = '开局分批兑换弹药并准备压前哨站' if result.get('ok') else '当前不满足兑换条件，改为直接压前哨站'
        target = context.data.get('enemy_outpost')
        if target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.6, context.map_manager)
        return self._set_decision(context, summary, target=self.entity_to_target(target, context.entity), target_point=(target.position['x'], target.position['y']), speed=speed, posture='mobile', turret_state='aiming')

    def _action_opening_supply(self, context):
        supply = self.get_supply_slot(context.entity, context.map_manager)
        if supply is None:
            return FAILURE
        speed = self._meters_to_world_units(1.7, context.map_manager)
        claimable = context.data.get('supply_claimable', 0)
        eta = context.data.get('supply_eta', 0.0)
        opening_target = self._opening_ammo_target(context)
        if self._is_opening_phase(context) and opening_target > 0 and getattr(context.entity, 'ammo', 0) < opening_target:
            summary = f'开局前往补给区建立弹药储备，目标弹量 {opening_target}'
        else:
            summary = '进入补给预约位，等待弹药窗口' if claimable <= 0 else '进入补给区领取弹药'
            if claimable <= 0 and eta > 10.0:
                return FAILURE
        return self._set_decision(context, summary, target_point=supply, speed=speed)

    def _action_emergency_retreat(self, context):
        retreat_point = self.choose_retreat_anchor(context.entity, context.map_manager, prefer_supply=context.data.get('ammo_low', False))
        speed = self._meters_to_world_units(2.0, context.map_manager)
        posture = 'defense' if context.entity.type == 'sentry' else None
        return self._set_decision(context, '血量/热量/弹药不利，执行规避撤退', target=context.data.get('target'), target_point=retreat_point, speed=speed, posture=posture, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_recover_after_respawn(self, context):
        supply = self.get_supply_slot(context.entity, context.map_manager)
        if supply is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        posture = 'defense' if context.entity.type == 'sentry' else None
        return self._set_decision(context, '原地复活后撤回补给区，解锁枪管并恢复状态', target=context.data.get('target'), target_point=supply, speed=speed, preferred_route={'target': supply}, posture=posture, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_claim_buff(self, context):
        facility = self._find_best_buff_anchor(context)
        if facility is None:
            return FAILURE
        speed = self._meters_to_world_units(1.8, context.map_manager)
        center = self.facility_center(facility)
        return self._set_decision(context, f'前往 {facility.get("type")} 抢占地形增益', target=context.data.get('target'), target_point=center, speed=speed, preferred_route={'target': center})

    def _action_activate_energy(self, context):
        anchor = context.data.get('energy_anchor')
        if anchor is None:
            return FAILURE
        speed = self._meters_to_world_units(1.6, context.map_manager)
        return self._set_decision(context, '转入中央能量机关正面激活位，争取团队增益', target=context.data.get('target'), target_point=anchor, speed=speed, turret_state='aiming' if context.data.get('target') else 'searching')

    def _action_cross_terrain(self, context):
        facility = self._find_best_buff_anchor(context, terrain_only=True)
        if facility is None:
            return FAILURE
        speed = self._meters_to_world_units(1.8, context.map_manager)
        center = self.facility_center(facility)
        return self._set_decision(context, f'主动翻越 {facility.get("type")} 建立侧翼路线', target_point=center, speed=speed)

    def _action_support_structures(self, context):
        support_target = context.data.get('own_outpost')
        if support_target is None or support_target.health >= support_target.max_health * 0.65:
            support_target = context.data.get('own_base')
        if support_target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.6, context.map_manager)
        point = (support_target.position['x'], support_target.position['y'])
        return self._set_decision(context, f'工程位回防 {support_target.id}，保持修复/掩护链', target_point=point, speed=speed, preferred_route={'target': point})

    def _action_defend_outpost_from_hero(self, context):
        enemy_hero = context.data.get('enemy_hero')
        own_outpost = context.data.get('own_outpost')
        if enemy_hero is None or own_outpost is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        point = (own_outpost.position['x'], own_outpost.position['y'])
        return self._set_decision(context, '步兵回防前哨站，阻止敌方英雄吊射', target=self.entity_to_target(enemy_hero, context.entity), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming')

    def _action_intercept_enemy_engineer(self, context):
        enemy_engineer = context.data.get('enemy_engineer')
        if enemy_engineer is None:
            return FAILURE
        point = (enemy_engineer.position['x'], enemy_engineer.position['y'])
        speed = self._meters_to_world_units(2.0 if context.data.get('role_key') == 'infantry' else 1.7, context.map_manager)
        return self._set_decision(context, '拦截敌方工程回家路线，切断其经济与能量节奏', target=self.entity_to_target(enemy_engineer, context.entity), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming')

    def _action_protect_hero(self, context):
        allied_hero = context.data.get('allied_hero')
        if allied_hero is None:
            return FAILURE
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (allied_hero.position['x'], allied_hero.position['y']), {'infantry', 'sentry'})
        target = threat['entity'] if threat is not None else None
        point = self._escort_anchor(allied_hero, target, context.map_manager)
        speed = self._meters_to_world_units(1.6, context.map_manager)
        decision_target = self.entity_to_target(target, context.entity) if target is not None else context.data.get('target')
        return self._set_decision(context, '哨兵贴近英雄提供火力保护，阻断敌方近身威胁', target=decision_target, target_point=point, speed=speed, preferred_route={'target': point}, posture='attack', turret_state='aiming' if decision_target else 'searching')

    def _action_support_infantry_push(self, context):
        allied_infantry = context.data.get('allied_infantry')
        enemy_outpost = context.data.get('enemy_outpost')
        if allied_infantry is None:
            return FAILURE
        anchor_target = enemy_outpost if enemy_outpost is not None and enemy_outpost.is_alive() else allied_infantry
        point = self._escort_anchor(allied_infantry, anchor_target, context.map_manager)
        speed = self._meters_to_world_units(1.6, context.map_manager)
        decision_target = self.entity_to_target(anchor_target, context.entity) if anchor_target is not None and anchor_target is not allied_infantry else context.data.get('target')
        return self._set_decision(context, '哨兵与步兵协同压前哨站，顺带封堵对方回防线', target=decision_target, target_point=point, speed=speed, preferred_route={'target': point}, posture='attack', turret_state='aiming' if decision_target else 'searching')

    def _action_engineer_mining_cycle(self, context):
        carried = context.data.get('carried_minerals', 0)
        target_point = context.data.get('exchange_anchor') if carried > 0 else context.data.get('mining_anchor')
        if target_point is None:
            return FAILURE
        speed = self._meters_to_world_units(1.85, context.map_manager)
        if carried > 0:
            summary = f'工程携带 {carried} 单位矿物，前往兑矿区变现为队伍金币'
        else:
            summary = '工程前往取矿区执行经济闭环，为队友购买弹药提供金币'
        return self._set_decision(context, summary, target_point=target_point, speed=speed, preferred_route={'target': target_point})

    def _action_support_sentry_screen(self, context):
        allied_sentry = context.data.get('allied_sentry')
        if allied_sentry is None:
            return FAILURE
        offset = self._screen_offset(context.entity.team)
        point = (allied_sentry.position['x'] + offset[0], allied_sentry.position['y'] + offset[1])
        speed = self._meters_to_world_units(1.4, context.map_manager)
        return self._set_decision(context, '工程位围绕己方哨兵展开护送与补位', target=context.data.get('target'), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='searching')

    def _action_teamfight_push(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        desired_distance = self._meters_to_world_units(4.6 if context.data.get('role_key') == 'hero' else 3.8, context.map_manager)
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)
        velocity = self.engage_from_anchor(context.entity, target, guard_anchor, desired_distance=desired_distance, speed=speed, map_manager=context.map_manager)
        context.data['decision'] = {
            'summary': '与友军形成团战面，压制敌方主火力',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': guard_anchor,
            'movement_target': guard_anchor,
            'velocity': velocity,
            'fire_control_state': 'idle',
            'chassis_state': 'follow_turret',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': 'attack' if context.entity.type == 'sentry' else None,
        }
        return SUCCESS

    def _action_teamfight_cover(self, context):
        target = context.data.get('target')
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)
        speed = self._meters_to_world_units(1.6, context.map_manager)
        summary = '围绕据点维持交叉火力，准备接团'
        return self._set_decision(context, summary, target=target, target_point=guard_anchor, speed=speed, preferred_route={'target': guard_anchor}, posture='attack' if context.entity.type == 'sentry' else None, turret_state='aiming' if target else 'searching')

    def _action_pursue_enemy(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        speed = self._meters_to_world_units(2.0 if context.data.get('role_key') == 'hero' else 1.8, context.map_manager)
        return self._set_decision(context, f'追击 {target["id"]}，维持压力', target=target, target_point=(target['x'], target['y']), speed=speed, preferred_route={'target': (target['x'], target['y'])}, turret_state='aiming')

    def _action_sentry_engage(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        strategy = context.data.get('strategy', {})
        ideal_distance = self._meters_to_world_units(float(strategy.get('ideal_distance_m', 5.5)), context.map_manager)
        engage_speed = self._meters_to_world_units(float(strategy.get('engage_speed_mps', 1.8)), context.map_manager)
        firing_distance = self._meters_to_world_units(float(strategy.get('firing_distance_m', 9.0)), context.map_manager)
        guard_anchor = self.choose_guard_anchor(context.entity, target, context.map_manager)
        context.data['decision'] = {
            'summary': f'锁定 {target["id"]}，围绕防守锚点输出',
            'posture': 'attack' if target['distance'] <= firing_distance and context.data.get('heat_ratio', 0.0) < 0.7 else 'mobile',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': guard_anchor,
            'movement_target': guard_anchor,
            'velocity': self.engage_from_anchor(context.entity, target, guard_anchor, desired_distance=ideal_distance, speed=engage_speed, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'follow_turret' if target['distance'] <= self._meters_to_world_units(5.5, context.map_manager) else 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
        }
        return SUCCESS

    def _action_hero_lob_shot(self, context):
        target = context.data.get('target')
        if target is None:
            return FAILURE
        highground = self._find_nearest_facility_center(context.map_manager, context.entity, ['second_step', 'fly_slope'])
        if highground is None:
            return FAILURE
        speed = self._meters_to_world_units(1.9, context.map_manager)
        distance = self._distance_to_point(context.entity, highground)
        if distance > 65:
            return self._set_decision(context, '英雄转入高台吊射位，准备远距离压制', target=target, target_point=highground, speed=speed, turret_state='aiming')
        context.data['decision'] = {
            'summary': '英雄占据高台吊射位，远距离压制目标',
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': highground,
            'movement_target': highground,
            'velocity': self.maintain_distance(context.entity, target, self._meters_to_world_units(7.5, context.map_manager), speed * 0.55, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': None,
        }
        return SUCCESS

    def _action_hero_seek_cover(self, context):
        threat = self._nearest_enemy_by_roles(context.entities, context.entity.team, (context.entity.position['x'], context.entity.position['y']), {'infantry', 'sentry'})
        if threat is None:
            return FAILURE
        cover_anchor = self.choose_retreat_anchor(context.entity, context.map_manager, prefer_supply=False)
        allied_sentry = context.data.get('allied_sentry')
        if allied_sentry is not None and allied_sentry.is_alive():
            cover_anchor = self._escort_anchor(allied_sentry, threat['entity'], context.map_manager)
        speed = self._meters_to_world_units(2.1, context.map_manager)
        return self._set_decision(context, '英雄遭遇敌方步兵/哨兵压迫，回撤到己方掩护区域', target=self.entity_to_target(threat['entity'], context.entity), target_point=cover_anchor, speed=speed, preferred_route={'target': cover_anchor}, turret_state='aiming')

    def _action_hero_lob_outpost(self, context):
        enemy_outpost = context.data.get('enemy_outpost')
        if enemy_outpost is None:
            return FAILURE
        return self._action_hero_lob_structure(context, enemy_outpost, '英雄转入 6-8m 吊射位，优先压制敌方前哨站')

    def _action_hero_lob_base(self, context):
        enemy_base = context.data.get('enemy_base')
        if enemy_base is None:
            return FAILURE
        return self._action_hero_lob_structure(context, enemy_base, '敌方前哨站已倒，英雄转火基地并保持远距离吊射')

    def _action_hero_lob_structure(self, context, target_entity, summary):
        preferred_distance = self._meters_to_world_units(7.0, context.map_manager)
        anchor = self._structure_lob_anchor(context.entity, target_entity, context.data.get('own_base'), preferred_distance)
        speed = self._meters_to_world_units(1.9, context.map_manager)
        target = self.entity_to_target(target_entity, context.entity)
        if self._distance_to_point(context.entity, anchor) > self._meters_to_world_units(0.8, context.map_manager):
            return self._set_decision(context, summary, target=target, target_point=anchor, speed=speed, preferred_route={'target': anchor}, turret_state='aiming')
        context.data['decision'] = {
            'summary': summary,
            'target': target,
            'aim_point': (target['x'], target['y']),
            'navigation_target': anchor,
            'movement_target': anchor,
            'velocity': self.maintain_distance(context.entity, target, preferred_distance, speed * 0.45, map_manager=context.map_manager),
            'fire_control_state': 'idle',
            'chassis_state': 'normal',
            'turret_state': 'aiming',
            'angular_velocity': 0.0,
            'posture': None,
        }
        return SUCCESS

    def _action_push_outpost(self, context):
        target_entity = context.data.get('enemy_outpost')
        if target_entity is None:
            return FAILURE
        point = (target_entity.position['x'], target_entity.position['y'])
        speed = self._meters_to_world_units(1.9, context.map_manager)
        summary = '推进敌方前哨站，压缩防守纵深'
        return self._set_decision(context, summary, target=self.entity_to_target(target_entity, context.entity), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming')

    def _action_push_base(self, context):
        target_entity = context.data.get('enemy_base')
        if target_entity is None:
            return FAILURE
        point = (target_entity.position['x'], target_entity.position['y'])
        speed = self._meters_to_world_units(2.0, context.map_manager)
        summary = '转入基地推进阶段，集中火力终结比赛'
        return self._set_decision(context, summary, target=self.entity_to_target(target_entity, context.entity), target_point=point, speed=speed, preferred_route={'target': point}, turret_state='aiming')

    def _action_patrol_key_facilities(self, context):
        patrol_points = self.get_patrol_points(context.entity.team, context.map_manager)
        patrol_target = self.next_patrol_point(context.entity, patrol_points)
        speed = self._meters_to_world_units(1.4, context.map_manager)
        return self._set_decision(context, '沿关键设施轮巡，保持阵型与视野', target=context.data.get('target'), target_point=patrol_target, speed=speed, turret_state='aiming' if context.data.get('target') else 'searching', angular_velocity=12.0)

    def select_priority_target(self, entity, enemies, strategy, rules_engine=None, max_distance=None):
        priority_targets = strategy.get('priority_targets', ['sentry', 'robot', 'outpost', 'base'])
        priority_map = {target_type: len(priority_targets) - index for index, target_type in enumerate(priority_targets)}
        best_target = None
        best_score = None
        for other in enemies:
            distance = self._distance(entity, other)
            if max_distance is not None and distance > max_distance:
                continue
            hp_ratio = 0 if other.max_health <= 0 else other.health / other.max_health
            los_bonus = 0.0
            if rules_engine is not None and entity.type in {'robot', 'sentry'} and getattr(entity, 'robot_type', '') != '工程':
                assessment = rules_engine.evaluate_auto_aim_target(entity, other, distance=distance, require_fov=False)
                if assessment.get('can_track', False):
                    los_bonus = 240.0
                elif not assessment.get('line_of_sight', True):
                    los_bonus = -180.0
            score = priority_map.get(other.type, 0) * 1000 - distance + (1.0 - hp_ratio) * 220 + los_bonus
            if other.type in {'outpost', 'base'}:
                score += 50.0 if self._distance(entity, other) <= self._meters_to_world_units(8.5) else 0.0
            if best_score is None or score > best_score:
                best_score = score
                best_target = self.entity_to_target(other, entity)
        return best_target

    def entity_to_target(self, target_entity, source_entity):
        distance = self._distance(source_entity, target_entity)
        return {
            'id': target_entity.id,
            'type': target_entity.type,
            'x': target_entity.position['x'],
            'y': target_entity.position['y'],
            'distance': distance,
            'hp': target_entity.health,
            'max_hp': target_entity.max_health,
        }

    def _find_entity(self, entities, team, entity_type):
        for entity in entities:
            if entity.team == team and entity.type == entity_type:
                return entity
        return None

    def _distance(self, source, target):
        return math.hypot(target.position['x'] - source.position['x'], target.position['y'] - source.position['y'])

    def _distance_to_point(self, entity, point):
        return math.hypot(point[0] - entity.position['x'], point[1] - entity.position['y'])

    def get_team_anchor(self, team, anchor_type, map_manager):
        if map_manager is None:
            return None
        for facility in map_manager.get_facility_regions(anchor_type):
            if facility.get('team') == team:
                return self.facility_center(facility)
        return None

    def get_energy_anchor(self, map_manager):
        if map_manager is None:
            return None
        facilities = map_manager.get_facility_regions('energy_mechanism')
        if facilities:
            return self._energy_activation_anchor(facilities[0], map_manager)
        return self.get_map_center(map_manager)

    def get_mining_anchor(self, entity, map_manager):
        return self._nearest_region_center(entity, map_manager, ['mining_area'])

    def get_exchange_anchor(self, entity, map_manager):
        return self._nearest_region_center(entity, map_manager, ['mineral_exchange'])

    def get_map_center(self, map_manager):
        width = getattr(map_manager, 'map_width', None) or self.config.get('map', {}).get('width', 1576)
        height = getattr(map_manager, 'map_height', None) or self.config.get('map', {}).get('height', 873)
        return int(width / 2), int(height / 2)

    def get_patrol_points(self, team, map_manager):
        if map_manager is None:
            return []
        facility_ids = [
            f'{team}_fort',
            f'{team}_outpost',
            f'{team}_supply',
            f'{team}_undulating_road',
            f'{team}_fly_slope',
            f'{team}_base',
        ]
        facility_map = {facility.get('id'): facility for facility in map_manager.get_facility_regions()}
        return [self.facility_center(facility_map[facility_id]) for facility_id in facility_ids if facility_id in facility_map]

    def choose_retreat_anchor(self, entity, map_manager, prefer_supply=False):
        if map_manager is None:
            return entity.position['x'], entity.position['y']
        facility_order = ['supply', 'fort', 'outpost', 'base'] if prefer_supply else ['fort', 'outpost', 'base', 'supply']
        for facility_type in facility_order:
            anchor = self.get_team_anchor(entity.team, facility_type, map_manager)
            if anchor is not None:
                return anchor
        return entity.position['x'], entity.position['y']

    def choose_guard_anchor(self, entity, target, map_manager):
        if map_manager is None:
            return entity.position['x'], entity.position['y']
        candidates = []
        for facility_type, weight in [('fort', 1.5), ('outpost', 1.25), ('supply', 0.9), ('base', 0.8)]:
            anchor = self.get_team_anchor(entity.team, facility_type, map_manager)
            if anchor is None:
                continue
            target_distance = math.hypot(target['x'] - anchor[0], target['y'] - anchor[1]) if target is not None else 0.0
            entity_distance = math.hypot(entity.position['x'] - anchor[0], entity.position['y'] - anchor[1])
            score = weight * 1000.0 - target_distance * 0.75 - entity_distance * 0.20
            candidates.append((score, anchor))
        if not candidates:
            return entity.position['x'], entity.position['y']
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def choose_transit_anchor(self, entity, destination, map_manager, rules_engine=None):
        if map_manager is None or destination is None:
            return None
        candidate_types = ['fly_slope', 'undulating_road', 'first_step', 'second_step']
        best = None
        best_score = None
        for facility_type in candidate_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {entity.team, 'neutral'}:
                    continue
                if not self._terrain_access_allowed(entity, facility, rules_engine):
                    continue
                center = self.facility_center(facility)
                to_facility = self._distance_to_point(entity, center)
                to_goal = math.hypot(destination[0] - center[0], destination[1] - center[1])
                score = to_facility * 0.65 + to_goal * 0.35
                if best_score is None or score < best_score:
                    best_score = score
                    best = center
        if best is None:
            return None
        direct = self._distance_to_point(entity, destination)
        via = self._distance_to_point(entity, best) + math.hypot(destination[0] - best[0], destination[1] - best[1])
        return best if via <= direct * 1.15 else None

    def _find_best_buff_anchor(self, context, terrain_only=False):
        if context.map_manager is None:
            return None
        entity = context.entity
        target = context.data.get('target')
        target_point = (target['x'], target['y']) if target is not None else context.data.get('energy_anchor') or context.data.get('map_center')
        buff_rules_map = context.rules_engine.rules.get('buff_zones', {}) if context.rules_engine is not None else {}
        candidates = []
        for facility in context.map_manager.get_facility_regions():
            facility_type = facility.get('type', '')
            if not facility_type.startswith('buff_'):
                continue
            if terrain_only and not facility_type.startswith('buff_terrain_'):
                continue
            if facility.get('team') not in {entity.team, 'neutral'}:
                continue

            buff_rules = buff_rules_map.get(facility_type, {})
            if not buff_rules:
                continue
            if hasattr(context.rules_engine, '_buff_access_allowed') and not context.rules_engine._buff_access_allowed(entity, facility, buff_rules):
                continue
            if buff_rules.get('engineer_only') and getattr(entity, 'robot_type', '') != '工程':
                continue

            center = self.facility_center(facility)
            distance_to_entity = self._distance_to_point(entity, center)
            distance_to_target = math.hypot(target_point[0] - center[0], target_point[1] - center[1])
            bonus = 0.0
            if facility_type.startswith('buff_terrain_'):
                bonus += 140.0
            elif facility_type in {'buff_central_highland', 'buff_trapezoid_highland', 'buff_fort'}:
                bonus += 90.0
            elif facility_type in {'buff_supply', 'buff_base', 'buff_outpost'}:
                bonus += 60.0
            score = distance_to_target * 0.75 + distance_to_entity * 0.35 - bonus
            candidates.append((score, facility))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _find_nearest_facility_center(self, map_manager, entity, facility_types):
        if map_manager is None:
            return None
        best = None
        best_score = None
        for facility_type in facility_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {entity.team, 'neutral'}:
                    continue
                center = self.facility_center(facility)
                score = self._distance_to_point(entity, center)
                if best_score is None or score < best_score:
                    best_score = score
                    best = center
        return best

    def _nearest_region_center(self, entity, map_manager, facility_types):
        if map_manager is None:
            return None
        best_center = None
        best_distance = None
        for facility_type in facility_types:
            for facility in map_manager.get_facility_regions(facility_type):
                if facility.get('team') not in {'neutral', entity.team}:
                    continue
                center = self.facility_center(facility)
                distance = self._distance_to_point(entity, center)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_center = center
        return best_center

    def _screen_offset(self, team):
        return (48, 42) if team == 'red' else (-48, -42)

    def _find_entity_by_role(self, entities, team, role_key, exclude_id=None):
        for entity in entities:
            if entity.id == exclude_id or entity.team != team or not entity.is_alive():
                continue
            if self._role_key(entity) == role_key:
                return entity
        return None

    def _nearest_enemy_by_roles(self, entities, team, point, role_keys):
        best = None
        best_distance = None
        for entity in entities:
            if entity.team == team or not entity.is_alive():
                continue
            if self._role_key(entity) not in role_keys:
                continue
            distance = math.hypot(entity.position['x'] - point[0], entity.position['y'] - point[1])
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best = entity
        if best is None:
            return None
        return {'entity': best, 'distance': best_distance}

    def _escort_anchor(self, ally, threat, map_manager):
        if ally is None:
            return None
        offset_distance = self._meters_to_world_units(1.8, map_manager)
        if threat is None:
            return ally.position['x'], ally.position['y']
        dx = ally.position['x'] - threat.position['x']
        dy = ally.position['y'] - threat.position['y']
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return ally.position['x'], ally.position['y']
        return (
            ally.position['x'] + dx / length * offset_distance,
            ally.position['y'] + dy / length * offset_distance,
        )

    def _structure_lob_anchor(self, entity, structure, fallback_anchor, preferred_distance):
        if fallback_anchor is not None:
            reference_x = fallback_anchor.position['x']
            reference_y = fallback_anchor.position['y']
        else:
            reference_x = entity.position['x']
            reference_y = entity.position['y']
        dx = reference_x - structure.position['x']
        dy = reference_y - structure.position['y']
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx, dy, length = 0.0, -1.0, 1.0
        return (
            structure.position['x'] + dx / length * preferred_distance,
            structure.position['y'] + dy / length * preferred_distance,
        )

    def _energy_activation_anchor(self, facility, map_manager):
        center_x, center_y = self.facility_center(facility)
        points = list(facility.get('points', []))
        if len(points) >= 2:
            edge_mid_x = (float(points[0][0]) + float(points[-1][0])) / 2.0
            edge_mid_y = (float(points[0][1]) + float(points[-1][1])) / 2.0
            normal_x = edge_mid_x - center_x
            normal_y = edge_mid_y - center_y
        else:
            normal_x = 0.0
            normal_y = -1.0
        normal_len = math.hypot(normal_x, normal_y)
        if normal_len <= 1e-6:
            normal_x, normal_y = 0.0, -1.0
        else:
            normal_x /= normal_len
            normal_y /= normal_len
        anchor_distance = self._meters_to_world_units(5.5, map_manager)
        return center_x + normal_x * anchor_distance, center_y + normal_y * anchor_distance

    def _terrain_access_allowed(self, entity, facility, rules_engine=None):
        if rules_engine is not None and hasattr(rules_engine, '_terrain_access_allowed'):
            return rules_engine._terrain_access_allowed(entity, facility)
        if facility.get('type') == 'undulating_road':
            return False
        return True

    def _blend_velocity(self, velocity_a, velocity_b, ratio_a=0.6, ratio_b=0.4):
        return (
            velocity_a[0] * ratio_a + velocity_b[0] * ratio_b,
            velocity_a[1] * ratio_a + velocity_b[1] * ratio_b,
        )

    def engage_from_anchor(self, entity, target, anchor_point, desired_distance, speed=2.8, map_manager=None):
        target_velocity = self.maintain_distance(entity, target, desired_distance, speed, map_manager=map_manager)
        if anchor_point is None:
            return target_velocity
        anchor_velocity = self.navigate_towards(entity, anchor_point, speed * 0.7, map_manager)
        anchor_distance = math.hypot(anchor_point[0] - entity.position['x'], anchor_point[1] - entity.position['y'])
        if anchor_distance <= 90:
            return target_velocity
        if target['distance'] > desired_distance + 140:
            return self._blend_velocity(target_velocity, anchor_velocity, 0.72, 0.28)
        if target['distance'] < desired_distance - 120:
            return self._blend_velocity(target_velocity, anchor_velocity, 0.82, 0.18)
        return self._blend_velocity(target_velocity, anchor_velocity, 0.58, 0.42)

    def next_patrol_point(self, entity, patrol_points):
        if not patrol_points:
            return entity.position['x'], entity.position['y']
        patrol_index = self._patrol_index.get(entity.id, 0)
        target = patrol_points[patrol_index % len(patrol_points)]
        distance = math.hypot(target[0] - entity.position['x'], target[1] - entity.position['y'])
        if distance < 60:
            patrol_index = (patrol_index + 1) % len(patrol_points)
            self._patrol_index[entity.id] = patrol_index
            target = patrol_points[patrol_index]
        else:
            self._patrol_index[entity.id] = patrol_index
        return target

    def move_towards(self, entity, target_point, speed=2.0):
        if not self.enable_entity_movement or target_point is None:
            return 0.0, 0.0
        dx = target_point[0] - entity.position['x']
        dy = target_point[1] - entity.position['y']
        distance = math.hypot(dx, dy)
        if distance < 5:
            return 0.0, 0.0
        return (dx / distance) * speed, (dy / distance) * speed

    def navigate_towards(self, entity, target_point, speed, map_manager):
        if not self.enable_entity_movement or target_point is None:
            entity.ai_navigation_waypoint = None
            entity.ai_path_preview = []
            return 0.0, 0.0
        if map_manager is None:
            entity.ai_navigation_waypoint = target_point
            entity.ai_path_preview = [target_point]
            return self.move_towards(entity, target_point, speed)
        next_point = self._next_path_waypoint(entity, target_point, map_manager)
        return self.move_towards(entity, next_point, speed)

    def _next_path_waypoint(self, entity, target_point, map_manager):
        raster_version = getattr(map_manager, 'raster_version', 0)
        step_limit = float(getattr(entity, 'max_terrain_step_height_m', 0.05))
        traversal_profile = self._traversal_profile(entity)
        start_cell = self._path_cell(entity.position, map_manager)
        goal_cell = self._path_cell({'x': target_point[0], 'y': target_point[1]}, map_manager)
        state = self._entity_path_state.get(entity.id)
        current_time = self._last_ai_update_time.get(entity.id, 0.0)
        need_replan = state is None
        if not need_replan:
            need_replan = (
                state.get('goal_cell') != goal_cell
                or state.get('raster_version') != raster_version
                or state.get('step_limit') != round(step_limit, 3)
                or state.get('step_duration') != traversal_profile['step_climb_duration_sec']
                or not state.get('path')
            )

        if need_replan:
            cache_key = (start_cell, goal_cell, raster_version, round(step_limit, 3), traversal_profile['step_climb_duration_sec'])
            path = self._path_cache.get(cache_key)
            if path is None:
                path = map_manager.find_path(
                    (entity.position['x'], entity.position['y']),
                    target_point,
                    max_height_delta_m=step_limit,
                    grid_step=max(map_manager.terrain_grid_cell_size * 3, 16),
                    traversal_profile=traversal_profile,
                )
                if len(self._path_cache) > 64:
                    self._path_cache.clear()
                self._path_cache[cache_key] = path
            state = {
                'start_cell': start_cell,
                'goal_cell': goal_cell,
                'raster_version': raster_version,
                'step_limit': round(step_limit, 3),
                'step_duration': traversal_profile['step_climb_duration_sec'],
                'path': list(path or []),
                'index': 1,
                'planned_at': current_time,
            }
            self._entity_path_state[entity.id] = state

        path = state.get('path', [])
        if not path:
            entity.ai_navigation_waypoint = None
            entity.ai_path_preview = []
            return entity.position['x'], entity.position['y']
        index = max(1, min(int(state.get('index', 1)), max(len(path) - 1, 1)))
        advance_distance = max(10.0, map_manager.terrain_grid_cell_size * 1.5)
        while index < len(path) - 1 and self._distance_to_point(entity, path[index]) <= advance_distance:
            index += 1
        state['index'] = index
        preview = [
            (float(entity.position['x']), float(entity.position['y']))
        ]
        preview.extend(path[index:min(len(path), index + 6)])
        entity.ai_navigation_waypoint = path[index]
        entity.ai_path_preview = preview
        return path[index]

    def _path_cell(self, position, map_manager):
        step = max(map_manager.terrain_grid_cell_size * 2, 12)
        return int(position['x']) // step, int(position['y']) // step

    def _traversal_profile(self, entity):
        return {
            'can_climb_steps': bool(getattr(entity, 'can_climb_steps', False)),
            'step_climb_duration_sec': float(getattr(entity, 'step_climb_duration_sec', 2.0)),
        }

    def _supply_claimable_ammo(self, entity, rules_engine, game_time):
        if rules_engine is None:
            return 0
        interval = float(rules_engine.rules.get('supply', {}).get('ammo_interval', 60.0))
        ammo_gain = int(rules_engine.rules.get('supply', {}).get('ammo_gain', 100))
        if interval <= 0 or ammo_gain <= 0:
            return 0
        generated = int(game_time // interval) * ammo_gain
        claimed = int(getattr(entity, 'supply_ammo_claimed', 0))
        return max(0, generated - claimed)

    def _next_supply_eta(self, rules_engine, game_time):
        if rules_engine is None:
            return 999.0
        interval = float(rules_engine.rules.get('supply', {}).get('ammo_interval', 60.0))
        if interval <= 0:
            return 999.0
        remainder = game_time % interval
        if remainder <= 1e-6:
            return 0.0
        return interval - remainder

    def _select_supply_runner(self, entity, allies, rules_engine, game_time):
        if rules_engine is None:
            return entity
        candidates = [member for member in allies if member.is_alive() and getattr(member, 'ammo_type', 'none') != 'none']
        if not candidates:
            return entity
        def urgency(member):
            ammo = getattr(member, 'ammo', 0)
            claimable = self._supply_claimable_ammo(member, rules_engine, game_time)
            heat_ratio = 0.0 if member.max_heat <= 0 else member.heat / max(member.max_heat, 1e-6)
            return (claimable > 0, ammo <= 0, ammo < 20, heat_ratio < 0.8, -ammo)
        candidates.sort(key=urgency, reverse=True)
        return candidates[0]

    def get_supply_slot(self, entity, map_manager):
        if map_manager is None:
            return None
        facility = None
        for region in map_manager.get_facility_regions('supply'):
            if region.get('team') == entity.team:
                facility = region
                break
        if facility is None:
            return None
        slots = self._facility_slots(facility)
        if not slots:
            return self.facility_center(facility)
        slot_index = self._stable_slot_index(entity.id, len(slots))
        return slots[slot_index]

    def _facility_slots(self, facility):
        center_x, center_y = self.facility_center(facility)
        width = max(20, int(abs(facility['x2'] - facility['x1'])))
        height = max(20, int(abs(facility['y2'] - facility['y1'])))
        offset_x = max(18, width // 4)
        offset_y = max(18, height // 4)
        return [
            (center_x - offset_x, center_y - offset_y),
            (center_x + offset_x, center_y - offset_y),
            (center_x - offset_x, center_y + offset_y),
            (center_x + offset_x, center_y + offset_y),
            (center_x, center_y - offset_y),
            (center_x, center_y + offset_y),
        ]

    def _stable_slot_index(self, key, size):
        if size <= 0:
            return 0
        return sum(ord(char) for char in str(key)) % size

    def _apply_local_avoidance(self, entity, desired_velocity, entities, target_point=None):
        if not self.enable_entity_movement:
            return desired_velocity

        desired_x, desired_y = desired_velocity
        base_speed = math.hypot(desired_x, desired_y)
        if base_speed <= 1e-6:
            return desired_velocity

        repulsion_x = 0.0
        repulsion_y = 0.0
        lateral_x = 0.0
        lateral_y = 0.0
        target_dx = 0.0
        target_dy = 0.0
        if target_point is not None:
            target_dx = target_point[0] - entity.position['x']
            target_dy = target_point[1] - entity.position['y']

        for other in entities:
            if other.id == entity.id or not other.is_alive() or not getattr(other, 'movable', True):
                continue
            if other.team != entity.team:
                continue

            dx = entity.position['x'] - other.position['x']
            dy = entity.position['y'] - other.position['y']
            distance = math.hypot(dx, dy)
            if distance <= 1e-6 or distance > 64.0:
                continue

            influence = (64.0 - distance) / 64.0
            repulsion_x += (dx / distance) * influence
            repulsion_y += (dy / distance) * influence

            if target_point is not None:
                other_target_dx = target_point[0] - other.position['x']
                other_target_dy = target_point[1] - other.position['y']
                heading_dot = desired_x * getattr(other, 'velocity', {}).get('vx', 0.0) + desired_y * getattr(other, 'velocity', {}).get('vy', 0.0)
                shared_goal = math.hypot(other_target_dx - target_dx, other_target_dy - target_dy) <= 48.0
                if shared_goal or heading_dot < 0.0:
                    side = 1.0 if entity.id < other.id else -1.0
                    lateral_x += (-dy / distance) * influence * side
                    lateral_y += (dx / distance) * influence * side

        adjusted_x = desired_x + repulsion_x * base_speed * 0.85 + lateral_x * base_speed * 0.45
        adjusted_y = desired_y + repulsion_y * base_speed * 0.85 + lateral_y * base_speed * 0.45
        adjusted_speed = math.hypot(adjusted_x, adjusted_y)
        if adjusted_speed <= 1e-6:
            return 0.0, 0.0
        scale = base_speed / adjusted_speed
        return adjusted_x * scale, adjusted_y * scale

    def maintain_distance(self, entity, target, desired_distance, speed=2.8, map_manager=None):
        dx = target['x'] - entity.position['x']
        dy = target['y'] - entity.position['y']
        distance = max(target['distance'], 1.0)
        if distance > desired_distance + 120:
            if map_manager is not None:
                return self.navigate_towards(entity, (target['x'], target['y']), speed, map_manager)
            return (dx / distance) * speed, (dy / distance) * speed
        if distance < desired_distance - 120:
            return (-dx / distance) * speed, (-dy / distance) * speed
        return (-dy / distance) * (speed * 0.6), (dx / distance) * (speed * 0.6)

    def facility_center(self, facility):
        return int((facility['x1'] + facility['x2']) / 2), int((facility['y1'] + facility['y2']) / 2)