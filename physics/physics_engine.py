#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

class PhysicsEngine:
    def __init__(self, config):
        self.config = config
        self.max_speed = config.get('physics', {}).get('max_speed', 3.5)
        self.max_acceleration = config.get('physics', {}).get('max_acceleration', 2.0)
        self.max_angular_speed = config.get('physics', {}).get('max_angular_speed', 180)
        self.friction = config.get('physics', {}).get('friction', 0.1)
        self.collision_damping = config.get('physics', {}).get('collision_damping', 0.8)
        self.step_height = config.get('physics', {}).get('step_height', 15)
        self.slope_limit = config.get('physics', {}).get('slope_limit', 30)
        self.default_max_terrain_step_height_m = float(config.get('physics', {}).get('normal_max_terrain_step_height_m', 0.35))
        self.default_step_climb_duration_sec = float(config.get('physics', {}).get('default_step_climb_duration_sec', 1.0))
        self.infantry_step_climb_duration_sec = float(config.get('physics', {}).get('infantry_step_climb_duration_sec', 1.0))
        self.max_collision_separation_m = float(config.get('physics', {}).get('max_collision_separation_m', 0.10))
        self.collision_slop_m = float(config.get('physics', {}).get('collision_slop_m', 0.02))

    def _max_speed_world_units(self):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return self.max_speed * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)

    def _meters_to_world_units(self, meters):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return float(meters) * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)
    
    def update(self, entities, map_manager, rules_engine=None, dt=None):
        """更新物理状态"""
        sim_dt = float(dt if dt is not None else 1.0 / max(float(self.config.get('simulator', {}).get('fps', 50)), 1.0))
        for entity in entities:
            if not entity.is_alive() or not getattr(entity, 'collidable', True):
                continue
            
            # 应用摩擦力
            self.apply_friction(entity)

            # 按地形高度差限制位移
            self.enforce_terrain_movement(entity, map_manager, sim_dt)
            
            # 检查碰撞
            self.check_collisions(entity, entities, map_manager, rules_engine)
            
            # 限制速度
            self.limit_velocity(entity)
    
    def apply_friction(self, entity):
        """应用摩擦力"""
        if not getattr(entity, 'movable', True):
            entity.velocity['vx'] = 0
            entity.velocity['vy'] = 0
            entity.velocity['vz'] = 0
            entity.angular_velocity = 0
            return
        friction_factor = 1.0 - self.friction
        
        entity.velocity['vx'] *= friction_factor
        entity.velocity['vy'] *= friction_factor
        entity.velocity['vz'] *= friction_factor
        
        entity.angular_velocity *= friction_factor
    
    def check_collisions(self, entity, entities, map_manager, rules_engine=None):
        """检查碰撞"""
        if not getattr(entity, 'collidable', True):
            return
        # 检查与地图的碰撞
        if not map_manager.is_position_valid_for_radius(
            entity.position['x'],
            entity.position['y'],
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
        ):
            # 碰撞处理
            last_valid = dict(getattr(entity, 'last_valid_position', entity.position))
            if not map_manager.is_position_valid_for_radius(
                last_valid['x'],
                last_valid['y'],
                collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
            ):
                recovered = map_manager.find_nearest_passable_point(
                    (entity.position['x'], entity.position['y']),
                    collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
                    search_radius=max(96, int(float(getattr(entity, 'collision_radius', 16.0)) * 8.0)),
                    step=max(4, map_manager.terrain_grid_cell_size),
                )
                if recovered is not None:
                    last_valid = {
                        'x': float(recovered[0]),
                        'y': float(recovered[1]),
                        'z': map_manager.get_terrain_height_m(recovered[0], recovered[1]),
                    }
                    entity.last_valid_position = dict(last_valid)
            entity.position['x'] = last_valid['x']
            entity.position['y'] = last_valid['y']
            entity.position['z'] = map_manager.get_terrain_height_m(last_valid['x'], last_valid['y'])
            entity.velocity['vx'] = 0.0
            entity.velocity['vy'] = 0.0
            entity.velocity['vz'] = 0.0
        
        # 检查与其他实体的碰撞
        for other_entity in entities:
            if entity.id != other_entity.id and other_entity.is_alive() and getattr(other_entity, 'collidable', True):
                distance = self.calculate_distance(entity.position, other_entity.position)
                min_distance = self.get_min_distance(entity, other_entity)
                
                if distance< min_distance:
                    # 碰撞响应
                    impact_speed = self.resolve_collision(entity, other_entity, distance, min_distance)
                    if rules_engine is not None and entity.id < other_entity.id and impact_speed > 0:
                        rules_engine.handle_collision_damage(entity, other_entity, impact_speed)
    
    def calculate_distance(self, pos1, pos2):
        """计算两点之间的距离"""
        return math.hypot(pos1['x'] - pos2['x'], pos1['y'] - pos2['y'])
    
    def get_min_distance(self, entity1, entity2):
        """获取两个实体之间的最小距离"""
        # 根据实体类型返回不同的碰撞半径
        radius_map = {
            'robot': 20,
            'uav': 10,
            'sentry': 25,
            'outpost': 50,
            'base': 100,
            'dart': 5,
            'radar': 15
        }

        radius1 = float(getattr(entity1, 'collision_radius', radius_map.get(entity1.type, 10)))
        radius2 = float(getattr(entity2, 'collision_radius', radius_map.get(entity2.type, 10)))
        
        return radius1 + radius2
    
    def resolve_collision(self, entity1, entity2, distance, min_distance):
        """解决碰撞"""
        entity1_movable = getattr(entity1, 'movable', True)
        entity2_movable = getattr(entity2, 'movable', True)
        if not entity1_movable and not entity2_movable:
            return 0.0

        # 计算碰撞方向
        dx = entity2.position['x'] - entity1.position['x']
        dy = entity2.position['y'] - entity1.position['y']
        
        if distance >0:
            nx = dx / distance
            ny = dy / distance
        else:
            nx = 1.0
            ny = 0.0
        
        # 计算重叠量
        overlap = min_distance - distance
        separation_slop = self._meters_to_world_units(self.collision_slop_m)
        max_separation = self._meters_to_world_units(self.max_collision_separation_m)
        correction = min(max(0.0, overlap - separation_slop), max_separation)
        if correction <= 1e-6:
            correction = min(overlap, max_separation * 0.35)
        
        # 分离实体
        if entity1_movable and entity2_movable:
            entity1.position['x'] -= nx * correction * 0.5
            entity1.position['y'] -= ny * correction * 0.5
            entity2.position['x'] += nx * correction * 0.5
            entity2.position['y'] += ny * correction * 0.5
        elif entity1_movable:
            entity1.position['x'] -= nx * correction
            entity1.position['y'] -= ny * correction
        elif entity2_movable:
            entity2.position['x'] += nx * correction
            entity2.position['y'] += ny * correction

        recover_scale = min(max(correction, 0.0) / max(min_distance, 1e-6), 0.18)
        recover_timer = 0.22 + recover_scale * 0.28
        if entity1_movable:
            entity1.collision_recovery_timer = max(float(getattr(entity1, 'collision_recovery_timer', 0.0)), recover_timer)
            entity1.collision_recovery_vector = (-nx * recover_scale, -ny * recover_scale)
        if entity2_movable:
            entity2.collision_recovery_timer = max(float(getattr(entity2, 'collision_recovery_timer', 0.0)), recover_timer)
            entity2.collision_recovery_vector = (nx * recover_scale, ny * recover_scale)
        
        # 应用碰撞冲量
        vx1 = entity1.velocity['vx']
        vy1 = entity1.velocity['vy']
        vx2 = entity2.velocity['vx']
        vy2 = entity2.velocity['vy']
        
        # 相对速度
        v_rel_x = vx2 - vx1
        v_rel_y = vy2 - vy1
        
        # 法向相对速度
        v_rel_n = v_rel_x * nx + v_rel_y * ny
        
        # 如果物体正在分离，不处理碰撞
        if v_rel_n > 0:
            return 0.0
        
        # 计算冲量
        restitution = self.collision_damping
        j = -(1 + restitution) * v_rel_n
        j /= 1.0 + 1.0  # 假设质量相等
        max_push_speed = self._meters_to_world_units(0.12)
        j = min(j, max_push_speed)
        
        # 应用冲量
        if entity1_movable:
            entity1.velocity['vx'] += j * nx
            entity1.velocity['vy'] += j * ny

        if entity2_movable:
            entity2.velocity['vx'] -= j * nx
            entity2.velocity['vy'] -= j * ny

        return abs(v_rel_n)
    
    def limit_velocity(self, entity):
        """限制速度"""
        if not getattr(entity, 'movable', True):
            entity.velocity['vx'] = 0
            entity.velocity['vy'] = 0
            entity.velocity['vz'] = 0
            entity.angular_velocity = 0
            return
        # 限制线速度
        speed = math.hypot(entity.velocity['vx'], entity.velocity['vy'])
        max_speed_world = self._max_speed_world_units()
        if speed > max_speed_world:
            ratio = max_speed_world / speed
            entity.velocity['vx'] *= ratio
            entity.velocity['vy'] *= ratio
        
        # 限制角速度
        entity.angular_velocity = max(-self.max_angular_speed, 
                                     min(self.max_angular_speed, 
                                         entity.angular_velocity))
    
    def apply_force(self, entity, force_x, force_y):
        """应用力（简化版，假设质量为1）"""
        entity.velocity['vx'] += force_x * self.max_acceleration
        entity.velocity['vy'] += force_y * self.max_acceleration

    def enforce_terrain_movement(self, entity, map_manager, dt):
        if not getattr(entity, 'movable', True):
            return

        if self._update_step_climb(entity, map_manager, dt):
            return

        previous = dict(getattr(entity, 'previous_position', entity.position))
        current = entity.position
        step_limit = float(getattr(entity, 'max_terrain_step_height_m', self.default_max_terrain_step_height_m))
        transition = None
        if getattr(entity, 'can_climb_steps', False):
            transition = map_manager.get_step_transition(
                previous['x'],
                previous['y'],
                current['x'],
                current['y'],
                max_height_delta_m=step_limit,
            )
            if transition is not None:
                self._begin_step_climb(entity, transition, map_manager, dt)
                return

        path_result = map_manager.evaluate_movement_path(
            previous['x'],
            previous['y'],
            current['x'],
            current['y'],
            max_height_delta_m=step_limit,
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
        )

        if path_result.get('ok'):
            entity.position['z'] = float(path_result.get('end_height_m', current.get('z', 0.0)))
            entity.last_valid_position = dict(entity.position)
            return

        if path_result.get('reason') in {'height_delta', 'blocked'}:
            transition = transition or map_manager.get_step_transition(
                previous['x'],
                previous['y'],
                current['x'],
                current['y'],
                max_height_delta_m=step_limit,
            )
            if transition is not None and getattr(entity, 'can_climb_steps', False):
                self._begin_step_climb(entity, transition, map_manager, dt)
                return

        fallback = dict(getattr(entity, 'last_valid_position', previous))
        entity.position['x'] = fallback['x']
        entity.position['y'] = fallback['y']
        entity.position['z'] = map_manager.get_terrain_height_m(fallback['x'], fallback['y'])
        entity.velocity['vx'] = 0.0
        entity.velocity['vy'] = 0.0
        entity.velocity['vz'] = 0.0

    def _resolved_step_climb_duration(self, entity):
        if getattr(entity, 'robot_type', '') == '步兵':
            return float(getattr(entity, 'step_climb_duration_sec', self.infantry_step_climb_duration_sec))
        return float(getattr(entity, 'step_climb_duration_sec', self.default_step_climb_duration_sec))

    def _normalize_angle_diff(self, angle_diff):
        while angle_diff > 180.0:
            angle_diff -= 360.0
        while angle_diff < -180.0:
            angle_diff += 360.0
        return angle_diff

    def _step_heading_deg(self, start_point, end_point, fallback_angle):
        if start_point is None or end_point is None:
            return float(fallback_angle)
        heading_dx = float(end_point[0]) - float(start_point[0])
        heading_dy = float(end_point[1]) - float(start_point[1])
        if abs(heading_dx) <= 1e-6 and abs(heading_dy) <= 1e-6:
            return float(fallback_angle)
        return math.degrees(math.atan2(heading_dy, heading_dx))

    def _try_lateral_step_probe(self, entity, state, map_manager, candidate_x, candidate_y):
        if not map_manager.is_position_valid_for_radius(
            candidate_x,
            candidate_y,
            collision_radius=float(getattr(entity, 'collision_radius', 0.0)),
        ):
            return False

        top_point = state.get('top_point') or state.get('end_point')
        transition = None
        if top_point is not None:
            transition = map_manager.get_step_transition(
                candidate_x,
                candidate_y,
                top_point[0],
                top_point[1],
                max_height_delta_m=float(state.get('step_limit_m', self.default_max_terrain_step_height_m)),
            )

        if transition is not None and transition.get('facility_id') == state.get('facility_id'):
            state['approach_point'] = transition.get('approach_point')
            state['top_point'] = transition.get('top_point')
            climb_points = tuple(
                (float(point[0]), float(point[1])) for point in transition.get('climb_points', ())
            ) or ((float(transition.get('top_point')[0]), float(transition.get('top_point')[1])),)
            state['segment_points'] = climb_points
            state['segment_index'] = 0
            state['end_point'] = climb_points[0]

        state['start_point'] = (float(candidate_x), float(candidate_y))
        state['start_height'] = map_manager.get_terrain_height_m(candidate_x, candidate_y)
        end_point = state.get('end_point') or top_point
        if end_point is not None:
            state['end_height'] = map_manager.get_terrain_height_m(end_point[0], end_point[1])
            state['desired_heading_deg'] = self._step_heading_deg(
                state['start_point'],
                end_point,
                state.get('desired_heading_deg', getattr(entity, 'angle', 0.0)),
            )
        state['align_last_abs_diff'] = None
        state['align_stuck_time'] = 0.0
        state['align_probe_index'] = 0
        return True

    def _reseek_step_entry(self, entity, state, map_manager):
        target = state.get('top_point') or state.get('end_point')
        if target is None:
            return False

        collision_radius = float(getattr(entity, 'collision_radius', 0.0))
        base_radius = max(map_manager.terrain_grid_cell_size * 1.5, collision_radius * 0.8, 12.0)
        radii = (base_radius, base_radius * 1.6, base_radius * 2.2)
        angles_deg = (0, 45, 90, 135, 180, 225, 270, 315)
        step_limit = float(state.get('step_limit_m', self.default_max_terrain_step_height_m))
        for radius in radii:
            for angle_deg in angles_deg:
                heading = math.radians(angle_deg)
                candidate_x = float(target[0]) + math.cos(heading) * radius
                candidate_y = float(target[1]) + math.sin(heading) * radius
                if not map_manager.is_position_valid_for_radius(candidate_x, candidate_y, collision_radius=collision_radius):
                    continue
                transition = map_manager.get_step_transition(
                    candidate_x,
                    candidate_y,
                    target[0],
                    target[1],
                    max_height_delta_m=step_limit,
                )
                if transition is None or transition.get('facility_id') != state.get('facility_id'):
                    continue
                state['start_point'] = (float(candidate_x), float(candidate_y))
                state['start_height'] = map_manager.get_terrain_height_m(candidate_x, candidate_y)
                state['approach_point'] = transition.get('approach_point')
                state['top_point'] = transition.get('top_point')
                climb_points = tuple(
                    (float(point[0]), float(point[1])) for point in transition.get('climb_points', ())
                ) or ((float(transition.get('top_point')[0]), float(transition.get('top_point')[1])),)
                state['segment_points'] = climb_points
                state['segment_index'] = 0
                state['end_point'] = climb_points[0]
                state['desired_heading_deg'] = self._step_heading_deg(state['start_point'], state['end_point'], getattr(entity, 'angle', 0.0))
                state['align_probe_index'] = 0
                state['align_stuck_time'] = 0.0
                state['align_last_abs_diff'] = None
                return True
        return False

    def _begin_step_climb(self, entity, transition, map_manager, dt):
        state = getattr(entity, 'step_climb_state', None)
        if state is None or state.get('facility_id') != transition.get('facility_id'):
            start_point = (float(entity.previous_position['x']), float(entity.previous_position['y']))
            segment_points = tuple(
                (float(point[0]), float(point[1])) for point in transition.get('climb_points', ())
            ) or ((float(transition.get('top_point')[0]), float(transition.get('top_point')[1])),)
            end_point = segment_points[0]
            desired_heading_deg = self._step_heading_deg(start_point, end_point, getattr(entity, 'angle', 0.0))
            requires_alignment = getattr(entity, 'robot_type', '') != '步兵'
            total_duration = float(getattr(entity, 'step_climb_duration_sec', self._resolved_step_climb_duration(entity)))
            segment_duration = max(0.18, total_duration / max(1, len(segment_points)))
            entity.step_climb_state = {
                'facility_id': transition.get('facility_id'),
                'facility_type': transition.get('facility_type'),
                'progress': 0.0,
                'duration': segment_duration,
                'total_duration': total_duration,
                'step_limit_m': float(getattr(entity, 'max_terrain_step_height_m', self.default_max_terrain_step_height_m)),
                'phase': 'align' if requires_alignment else 'climb',
                'start_point': start_point,
                'approach_point': transition.get('approach_point'),
                'top_point': transition.get('top_point'),
                'segment_points': segment_points,
                'segment_index': 0,
                'end_point': end_point,
                'start_height': map_manager.get_terrain_height_m(start_point[0], start_point[1]),
                'end_height': map_manager.get_terrain_height_m(end_point[0], end_point[1]),
                'desired_heading_deg': desired_heading_deg,
                'align_tolerance_deg': 8.0,
                'align_speed_deg_per_sec': 360.0,
                'align_last_abs_diff': None,
                'align_stuck_time': 0.0,
                'align_probe_index': 0,
                'climb_stuck_time': 0.0,
                'climb_last_progress': 0.0,
            }
        self._update_step_climb(entity, map_manager, dt)

    def _update_step_climb(self, entity, map_manager, dt):
        state = getattr(entity, 'step_climb_state', None)
        if not state:
            return False
        start_point = state.get('start_point') or state.get('approach_point')
        end_point = state.get('end_point') or state.get('top_point')
        entity.velocity['vx'] = 0.0
        entity.velocity['vy'] = 0.0
        entity.velocity['vz'] = 0.0
        entity.angular_velocity = 0.0

        phase = state.get('phase', 'climb')
        desired_heading = float(state.get('desired_heading_deg', getattr(entity, 'angle', 0.0)))
        if phase == 'align':
            angle_diff = self._normalize_angle_diff(desired_heading - float(getattr(entity, 'angle', 0.0)))
            tolerance = float(state.get('align_tolerance_deg', 8.0))
            probe_step = self._meters_to_world_units(0.18)
            probe_offsets = (probe_step, -probe_step, probe_step * 2.0, -probe_step * 2.0)
            if abs(angle_diff) > tolerance:
                last_abs_diff = state.get('align_last_abs_diff')
                current_abs_diff = abs(angle_diff)
                if last_abs_diff is not None and abs(current_abs_diff - float(last_abs_diff)) <= 0.35:
                    state['align_stuck_time'] = float(state.get('align_stuck_time', 0.0)) + float(dt)
                else:
                    state['align_stuck_time'] = 0.0
                state['align_last_abs_diff'] = current_abs_diff

                if float(state.get('align_stuck_time', 0.0)) >= 0.45:
                    probe_index = int(state.get('align_probe_index', 0))
                    lateral = probe_offsets[probe_index % len(probe_offsets)]
                    state['align_probe_index'] = probe_index + 1

                    heading_rad = math.radians(desired_heading)
                    side_x = -math.sin(heading_rad)
                    side_y = math.cos(heading_rad)
                    candidate_x = float(start_point[0]) + side_x * lateral
                    candidate_y = float(start_point[1]) + side_y * lateral
                    if self._try_lateral_step_probe(
                        entity,
                        state,
                        map_manager,
                        candidate_x,
                        candidate_y,
                    ):
                        start_point = state.get('start_point', start_point)
                        desired_heading = float(state.get('desired_heading_deg', desired_heading))

                if int(state.get('align_probe_index', 0)) >= len(probe_offsets):
                    if self._reseek_step_entry(entity, state, map_manager):
                        start_point = state.get('start_point', start_point)
                        desired_heading = float(state.get('desired_heading_deg', desired_heading))
                    else:
                        state['align_stuck_time'] = 0.0

                turn_speed = float(state.get('align_speed_deg_per_sec', 360.0)) * float(dt)
                turn_step = max(-turn_speed, min(turn_speed, angle_diff))
                entity.angle = (float(getattr(entity, 'angle', 0.0)) + turn_step) % 360.0
                entity.turret_angle = entity.angle
                entity.position['x'] = start_point[0]
                entity.position['y'] = start_point[1]
                entity.position['z'] = float(state.get('start_height', map_manager.get_terrain_height_m(start_point[0], start_point[1])))
                entity.last_valid_position = dict(entity.position)
                entity.previous_position = dict(entity.position)
                return True
            state['phase'] = 'climb'
            state['progress'] = 0.0
            state['start_point'] = (float(entity.position['x']), float(entity.position['y']))
            state['start_height'] = map_manager.get_terrain_height_m(entity.position['x'], entity.position['y'])
            state['align_stuck_time'] = 0.0
            state['align_last_abs_diff'] = None
            state['align_probe_index'] = 0

        state['progress'] = float(state.get('progress', 0.0)) + float(dt)
        duration = max(float(state.get('duration', self.default_step_climb_duration_sec)), 1e-6)
        ratio = max(0.0, min(1.0, state['progress'] / duration))
        smooth_ratio = ratio * ratio * (3.0 - 2.0 * ratio)
        next_x = start_point[0] + (end_point[0] - start_point[0]) * smooth_ratio
        next_y = start_point[1] + (end_point[1] - start_point[1]) * smooth_ratio
        if not map_manager.is_position_valid_for_radius(next_x, next_y, collision_radius=float(getattr(entity, 'collision_radius', 0.0))):
            state['climb_stuck_time'] = float(state.get('climb_stuck_time', 0.0)) + float(dt)
            if state['climb_stuck_time'] >= 0.25 and self._reseek_step_entry(entity, state, map_manager):
                state['phase'] = 'align' if getattr(entity, 'robot_type', '') != '步兵' else 'climb'
                state['progress'] = 0.0
                state['start_point'] = (float(entity.position['x']), float(entity.position['y']))
                state['start_height'] = map_manager.get_terrain_height_m(entity.position['x'], entity.position['y'])
                state['end_height'] = map_manager.get_terrain_height_m(state['end_point'][0], state['end_point'][1])
                state['climb_stuck_time'] = 0.0
                state['climb_last_progress'] = 0.0
                return True
            entity.position['x'] = start_point[0]
            entity.position['y'] = start_point[1]
            entity.position['z'] = float(state.get('start_height', map_manager.get_terrain_height_m(start_point[0], start_point[1])))
            entity.last_valid_position = dict(entity.position)
            entity.previous_position = dict(entity.position)
            return True
        last_progress = float(state.get('climb_last_progress', 0.0))
        if ratio <= last_progress + 1e-4:
            state['climb_stuck_time'] = float(state.get('climb_stuck_time', 0.0)) + float(dt)
        else:
            state['climb_stuck_time'] = 0.0
        state['climb_last_progress'] = ratio
        entity.position['x'] = next_x
        entity.position['y'] = next_y
        entity.position['z'] = float(state.get('start_height', 0.0)) + (float(state.get('end_height', 0.0)) - float(state.get('start_height', 0.0))) * smooth_ratio
        entity.angle = desired_heading % 360.0
        entity.turret_angle = entity.angle
        entity.last_valid_position = dict(entity.position)
        if ratio < 1.0:
            return True

        segment_points = tuple(state.get('segment_points', ()))
        segment_index = int(state.get('segment_index', 0))
        if segment_index < len(segment_points) - 1:
            next_index = segment_index + 1
            next_end = segment_points[next_index]
            state['segment_index'] = next_index
            state['progress'] = 0.0
            state['start_point'] = (end_point[0], end_point[1])
            state['start_height'] = float(state.get('end_height', map_manager.get_terrain_height_m(end_point[0], end_point[1])))
            state['end_point'] = next_end
            state['end_height'] = map_manager.get_terrain_height_m(next_end[0], next_end[1])
            state['desired_heading_deg'] = self._step_heading_deg(state['start_point'], next_end, desired_heading)
            state['climb_last_progress'] = 0.0
            state['climb_stuck_time'] = 0.0
            entity.position['x'] = end_point[0]
            entity.position['y'] = end_point[1]
            entity.position['z'] = float(state.get('start_height', map_manager.get_terrain_height_m(end_point[0], end_point[1])))
            entity.previous_position = dict(entity.position)
            entity.last_valid_position = dict(entity.position)
            return True

        entity.position['x'] = end_point[0]
        entity.position['y'] = end_point[1]
        entity.position['z'] = float(state.get('end_height', map_manager.get_terrain_height_m(end_point[0], end_point[1])))
        entity.previous_position = dict(entity.position)
        entity.last_valid_position = dict(entity.position)
        entity.step_climb_state = None
        return True
