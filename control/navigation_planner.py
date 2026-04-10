#!/usr/bin/env python3
# -*- coding: utf-8 -*-


class NavigationPlannerRuntime:
    def __init__(self, controller, worker_router):
        self._controller = controller
        self._worker_router = worker_router

    def build_search_request(self, entity, target_point, map_manager, step_limit, traversal_profile):
        controller = self._controller
        budget_scale = controller._pathfinder_distance_scale(entity, target_point, map_manager)
        total_budget_sec = controller._pathfinder_total_budget_sec * budget_scale
        grid_step = max(map_manager.terrain_grid_cell_size * 3, 24)
        resolved_target = controller._resolve_navigation_target(target_point, map_manager, entity=entity)
        if resolved_target is None:
            resolved_target = map_manager.find_nearest_passable_point(
                target_point,
                collision_radius=float(traversal_profile.get('collision_radius', 0.0)),
                search_radius=max(72, map_manager.terrain_grid_cell_size * 10),
                step=max(4, map_manager.terrain_grid_cell_size),
            )
        resolved_point = None
        if resolved_target is not None:
            resolved_point = (float(resolved_target[0]), float(resolved_target[1]))
        return {
            'start_point': (float(entity.position['x']), float(entity.position['y'])),
            'target_point': (float(target_point[0]), float(target_point[1])),
            'resolved_target_point': resolved_point,
            'step_limit': float(step_limit),
            'grid_step': int(grid_step),
            'traversal_profile': dict(traversal_profile or {}),
            'max_iterations': max(controller._pathfinder_max_iterations, int(controller._pathfinder_max_iterations * budget_scale)),
            'max_runtime_sec': controller._pathfinder_time_budget_sec * budget_scale,
            'total_budget_sec': float(total_budget_sec),
        }

    def run_search_request(self, map_manager, request):
        controller = self._controller
        resolved_target = request.get('resolved_target_point')
        if resolved_target is None:
            return controller.EMPTY_PATH_PREVIEW
        total_budget_sec = float(request.get('total_budget_sec', 0.0))
        runtime_limit = min(float(request.get('max_runtime_sec', 0.0)), total_budget_sec) if total_budget_sec > 0.0 else float(request.get('max_runtime_sec', 0.0))
        if runtime_limit <= 0.0002:
            return controller.EMPTY_PATH_PREVIEW
        path = map_manager.find_path(
            request['start_point'],
            resolved_target,
            max_height_delta_m=float(request.get('step_limit', 0.05)),
            grid_step=int(request.get('grid_step', max(map_manager.terrain_grid_cell_size * 3, 24))),
            traversal_profile=request.get('traversal_profile', {}),
            max_iterations=request.get('max_iterations'),
            max_runtime_sec=runtime_limit,
        )
        if not path:
            return controller.EMPTY_PATH_PREVIEW
        return tuple((float(point[0]), float(point[1])) for point in path)

    def finalize_search_path(self, entity, raw_path, target_point, map_manager):
        controller = self._controller
        raw_path = tuple(raw_path or controller.EMPTY_PATH_PREVIEW)
        if not raw_path:
            return controller.EMPTY_PATH_PREVIEW
        if not controller._is_path_traversable(entity, raw_path, map_manager):
            return controller.EMPTY_PATH_PREVIEW
        expanded_path = controller._expand_path_with_step_transitions(entity, raw_path, map_manager)
        return tuple(controller._segment_path_points(expanded_path, map_manager, entity=entity))

    def consume_pending_search(self, entity, target_point, map_manager, state, request_signature):
        controller = self._controller
        future = state.get('pending_path_future') if isinstance(state, dict) else None
        if future is None:
            return None, False
        if not future.done():
            return None, True
        if state.get('pending_request_signature') != request_signature:
            state.pop('pending_path_future', None)
            state.pop('pending_request_signature', None)
            state.pop('pending_target_point', None)
            return None, False
        state.pop('pending_path_future', None)
        state.pop('pending_request_signature', None)
        state.pop('pending_target_point', None)
        try:
            raw_path = tuple(future.result() or controller.EMPTY_PATH_PREVIEW)
        except Exception:
            raw_path = controller.EMPTY_PATH_PREVIEW
        return self.finalize_search_path(entity, raw_path, target_point, map_manager), False

    def submit_search(self, entity, target_point, map_manager, step_limit, traversal_profile, state, request_signature):
        pending_future = state.get('pending_path_future') if isinstance(state, dict) else None
        if pending_future is not None and not pending_future.done():
            return True
        request = self.build_search_request(entity, target_point, map_manager, step_limit, traversal_profile)
        state['pending_path_future'] = self._worker_router.submit(entity.id, self.run_search_request, map_manager, request)
        state['pending_request_signature'] = request_signature
        state['pending_target_point'] = (float(target_point[0]), float(target_point[1]))
        return True