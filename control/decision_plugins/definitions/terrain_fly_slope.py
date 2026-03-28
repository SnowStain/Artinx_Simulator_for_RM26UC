from copy import deepcopy

from control.behavior_tree import FAILURE
from control.decision_plugins.catalog import PLUGINS


TARGET_DEFS = (
	{'id': 'node_1', 'label': '跨越节点 1'},
	{'id': 'node_2', 'label': '跨越节点 2'},
	{'id': 'node_3', 'label': '跨越节点 3'},
	{'id': 'node_4', 'label': '跨越节点 4'},
)


def _team_direction(team):
	return 1.0 if team == 'red' else -1.0


def _default_targets(controller, map_manager, team):
	if map_manager is None:
		return {}
	facility_type = 'buff_terrain_fly_slope_red_start' if team == 'red' else 'buff_terrain_fly_slope_blue_start'
	primary = None
	for facility in map_manager.get_facility_regions(facility_type):
		if facility.get('team') in {'neutral', team}:
			primary = controller._resolve_navigation_target(controller.facility_center(facility), map_manager)
			break
	slope = None
	base_anchor = controller.get_team_anchor(team, 'base', map_manager)
	best_distance = None
	for facility in map_manager.get_facility_regions('fly_slope'):
		if facility.get('team') not in {team, 'neutral'}:
			continue
		center = controller.facility_center(facility)
		if base_anchor is None:
			slope = facility
			break
		distance = ((float(center[0]) - float(base_anchor[0])) ** 2 + (float(center[1]) - float(base_anchor[1])) ** 2) ** 0.5
		if best_distance is None or distance < best_distance:
			best_distance = distance
			slope = facility
	if slope is None:
		return {'node_1': primary} if primary is not None else {}
	direction = _team_direction(team)
	peak_x = float(slope.get('x2', 0.0)) if direction > 0 else float(slope.get('x1', 0.0))
	center_y = (float(slope.get('y1', 0.0)) + float(slope.get('y2', 0.0))) * 0.5
	if primary is None:
		primary = controller._resolve_navigation_target(controller.facility_center(slope), map_manager)
	landing = controller._resolve_navigation_target(
		(peak_x + direction * controller._meters_to_world_units(0.85, map_manager), center_y),
		map_manager,
	)
	targets = {}
	if primary is not None:
		targets['node_1'] = (float(primary[0]), float(primary[1]))
	if landing is not None:
		targets['node_2'] = (float(landing[0]), float(landing[1]))
	return targets


def _effective_targets(controller, role_key, decision_id, map_manager, team):
	return controller.get_decision_point_targets(role_key, decision_id, map_manager, team=team) or _default_targets(controller, map_manager, team)


def terrain_condition(controller, context, role_key, binding):
	plan = controller._best_terrain_traversal_plan(context, required_type='fly_slope')
	return bool(plan)


def terrain_action(controller, context, role_key, binding):
	targets = _effective_targets(controller, role_key, binding.get('id'), context.map_manager, context.entity.team)
	primary = targets.get('node_1')
	secondary = targets.get('node_2') or primary
	if primary is None and secondary is None:
		return FAILURE
	focus_target = context.data.get('target')
	speed = controller._meters_to_world_units(2.0, context.map_manager)
	if primary is not None and not controller._is_target_reached(context.entity, primary, context.map_manager):
		return controller._set_decision(
			context,
			'飞坡行为先进入跨越节点 1，对正坡道并准备切入',
			target=focus_target,
			target_point=primary,
			speed=speed,
			preferred_route={'target': primary},
			turret_state='aiming' if focus_target is not None else 'searching',
		)
	return controller._set_decision(
		context,
		'飞坡行为转入跨越节点 2，完成飞坡落点切换',
		target=focus_target,
		target_point=secondary,
		speed=speed * 1.05,
		preferred_route={'target': secondary},
		turret_state='aiming' if focus_target is not None else 'searching',
	)


def terrain_preview_points(controller, role_key, map_manager, team=None, override=None, binding=None):
	return _default_targets(controller, map_manager, team or 'red')


def terrain_preview_regions(controller, role_key, map_manager, team=None, override=None, binding=None):
	decision_id = binding.get('id') if isinstance(binding, dict) else 'terrain_fly_slope'
	targets = _effective_targets(controller, role_key, decision_id, map_manager, team or 'red')
	radius = controller._meters_to_world_units(0.55, map_manager) if map_manager is not None else 24.0
	return [
		{'shape': 'circle', 'cx': float(point[0]), 'cy': float(point[1]), 'radius': float(radius)}
		for point in targets.values()
	]


PLUGIN = deepcopy(PLUGINS['terrain_fly_slope'])
for role_config in PLUGIN.get('roles', {}).values():
	role_config['condition'] = terrain_condition
	role_config['action'] = terrain_action
	role_config['preview_points'] = terrain_preview_points
	role_config['preview_regions'] = terrain_preview_regions
	role_config['editable_targets'] = TARGET_DEFS
