from copy import deepcopy

from control.behavior_tree import FAILURE
from control.decision_plugins.catalog import PLUGINS


TARGET_DEFS = (
	{'id': 'primary', 'label': '第一目标点'},
	{'id': 'secondary', 'label': '第二目标点'},
)


def _team_direction(team):
	return 1.0 if team == 'red' else -1.0


def _pick_step_targets(controller, map_manager, team, facility_type, near_offset_m, far_offset_m):
	if map_manager is None:
		return {}
	base_anchor = controller.get_team_anchor(team, 'base', map_manager)
	best_facility = None
	best_distance = None
	for facility in map_manager.get_facility_regions(facility_type):
		if facility.get('team') not in {team, 'neutral'}:
			continue
		center = controller.facility_center(facility)
		distance = 0.0 if base_anchor is None else ((float(center[0]) - float(base_anchor[0])) ** 2 + (float(center[1]) - float(base_anchor[1])) ** 2) ** 0.5
		if best_distance is None or distance < best_distance:
			best_distance = distance
			best_facility = facility
	if best_facility is None:
		return {}
	direction = _team_direction(team)
	min_x = min(float(best_facility.get('x1', 0.0)), float(best_facility.get('x2', 0.0)))
	max_x = max(float(best_facility.get('x1', 0.0)), float(best_facility.get('x2', 0.0)))
	center_y = (float(best_facility.get('y1', 0.0)) + float(best_facility.get('y2', 0.0))) * 0.5
	near_edge = min_x if direction > 0 else max_x
	far_edge = max_x if direction > 0 else min_x
	primary = controller._resolve_navigation_target(
		(near_edge - direction * controller._meters_to_world_units(0.55, map_manager), center_y),
		map_manager,
	)
	secondary = controller._resolve_navigation_target(
		(far_edge + direction * controller._meters_to_world_units(1.05, map_manager), center_y),
		map_manager,
	)
	targets = {}
	if primary is not None:
		targets['primary'] = (float(primary[0]), float(primary[1]))
	if secondary is not None:
		targets['secondary'] = (float(secondary[0]), float(secondary[1]))
	return targets


def _effective_targets(controller, role_key, decision_id, map_manager, team):
	return controller.get_decision_point_targets(role_key, decision_id, map_manager, team=team) or _pick_step_targets(controller, map_manager, team, 'second_step', 0.55, 1.05)


def terrain_condition(controller, context, role_key, binding):
	return bool(controller._best_terrain_traversal_plan(context, required_type='second_step'))


def terrain_action(controller, context, role_key, binding):
	targets = _effective_targets(controller, role_key, binding.get('id'), context.map_manager, context.entity.team)
	primary = targets.get('primary')
	secondary = targets.get('secondary') or primary
	if primary is None and secondary is None:
		return FAILURE
	focus_target = context.data.get('target')
	speed = controller._meters_to_world_units(1.95, context.map_manager)
	if primary is not None and not controller._is_target_reached(context.entity, primary, context.map_manager):
		return controller._set_decision(
			context,
			'翻越二级台阶先进入第一目标点，完成接近与预对正',
			target=focus_target,
			target_point=primary,
			speed=speed,
			preferred_route={'target': primary},
			turret_state='aiming' if focus_target is not None else 'searching',
		)
	return controller._set_decision(
		context,
		'翻越二级台阶转入第二目标点，完成高差跨越路线',
		target=focus_target,
		target_point=secondary,
		speed=speed,
		preferred_route={'target': secondary},
		turret_state='aiming' if focus_target is not None else 'searching',
	)


def terrain_preview_points(controller, role_key, map_manager, team=None, override=None, binding=None):
	return _pick_step_targets(controller, map_manager, team or 'red', 'second_step', 0.55, 1.05)


def terrain_preview_regions(controller, role_key, map_manager, team=None, override=None, binding=None):
	decision_id = binding.get('id') if isinstance(binding, dict) else 'terrain_second_step'
	targets = _effective_targets(controller, role_key, decision_id, map_manager, team or 'red')
	radius = controller._meters_to_world_units(0.52, map_manager) if map_manager is not None else 24.0
	return [{'shape': 'circle', 'cx': float(point[0]), 'cy': float(point[1]), 'radius': float(radius)} for point in targets.values()]


PLUGIN = deepcopy(PLUGINS['terrain_second_step'])
for role_config in PLUGIN.get('roles', {}).values():
	role_config['condition'] = terrain_condition
	role_config['action'] = terrain_action
	role_config['preview_points'] = terrain_preview_points
	role_config['preview_regions'] = terrain_preview_regions
	role_config['editable_targets'] = TARGET_DEFS
