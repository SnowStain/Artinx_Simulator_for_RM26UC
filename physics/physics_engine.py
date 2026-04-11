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
        self.default_direct_terrain_step_height_m = float(config.get('physics', {}).get('direct_terrain_step_height_m', 0.06))
        self.default_max_terrain_step_height_m = float(config.get('physics', {}).get('normal_max_terrain_step_height_m', 0.35))
        self.default_step_climb_duration_sec = float(config.get('physics', {}).get('default_step_climb_duration_sec', 1.0))
        self.infantry_step_climb_duration_sec = float(config.get('physics', {}).get('infantry_step_climb_duration_sec', 1.0))
        self.infantry_jump_height_m = float(config.get('physics', {}).get('infantry_jump_height_m', 0.40))
        self.jump_gravity_mps2 = float(config.get('physics', {}).get('jump_gravity_mps2', 9.8))
        self.fly_slope_dead_zone_clearance_m = float(config.get('physics', {}).get('fly_slope_dead_zone_clearance_m', 0.20))
        self.fly_slope_launch_boost_mps = float(config.get('physics', {}).get('fly_slope_launch_boost_mps', 3.1))
        self.fly_slope_lateral_preserve = float(config.get('physics', {}).get('fly_slope_lateral_preserve', 0.25))
        self.jump_landing_grace_sec = float(config.get('physics', {}).get('jump_landing_grace_sec', 0.18))
        self.max_collision_separation_m = float(config.get('physics', {}).get('max_collision_separation_m', 0.10))
        self.collision_slop_m = float(config.get('physics', {}).get('collision_slop_m', 0.02))
        self.infantry_jump_launch_velocity_mps = math.sqrt(max(0.0, 2.0 * self.jump_gravity_mps2 * self.infantry_jump_height_m))

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

    def _world_units_to_meters(self, world_units):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        pixels_per_meter = max((pixels_per_meter_x + pixels_per_meter_y) * 0.5, 1e-6)
        return float(world_units) / pixels_per_meter

    def _resolved_direct_step_height(self, entity):
        return max(
            0.0,
            float(
                getattr(
                    entity,
                    'direct_terrain_step_height_m',
                    getattr(entity, 'max_terrain_step_height_m', self.default_direct_terrain_step_height_m),
                )
            ),
        )

    def _resolved_step_climb_height(self, entity):
        return max(
            self._resolved_direct_step_height(entity),
            float(
                getattr(
                    entity,
                    'max_step_climb_height_m',
                    getattr(entity, 'max_terrain_step_height_m', self.default_max_terrain_step_height_m),
                )
            ),
        )

    def _fly_slope_ballistic_height_m(self, entity, traversal):
        if not isinstance(traversal, dict) or traversal.get('facility_type') != 'fly_slope' or traversal.get('direction') != 'forward':
            return 0.0
        launch_point = traversal.get('entry_point') or traversal.get('approach_point')
        landing_point = traversal.get('landing_point') or traversal.get('exit_point')
        if launch_point is None or landing_point is None:
            return 0.0
        launch_x = float(launch_point[0])
        launch_y = float(launch_point[1])
        landing_x = float(landing_point[0])
        landing_y = float(landing_point[1])
        delta_x = landing_x - launch_x
        delta_y = landing_y - launch_y
        total_distance_world = math.hypot(delta_x, delta_y)
        if total_distance_world <= 1e-6:
            return 0.0
        current_x = float(entity.position['x'])
        current_y = float(entity.position['y'])
        progress = ((current_x - launch_x) * delta_x + (current_y - launch_y) * delta_y) / max(total_distance_world * total_distance_world, 1e-6)
        progress = max(0.0, min(1.0, progress))
        total_distance_m = self._world_units_to_meters(total_distance_world)
        speed_world = math.hypot(float(entity.velocity.get('vx', 0.0)), float(entity.velocity.get('vy', 0.0)))
        speed_mps = self._world_units_to_meters(speed_world)
        apex_ratio = 0.35 if total_distance_m >= 1.6 else 0.5
        apex_height_m = max(
            self.fly_slope_dead_zone_clearance_m,
            min(1.5, 0.20 + total_distance_m * 0.08 + speed_mps * 0.10),
        )
        if progress <= apex_ratio:
            local_progress = progress / max(apex_ratio, 1e-6)
            return apex_height_m * (1.0 - (1.0 - local_progress) ** 2)
        local_progress = (1.0 - progress) / max(1.0 - apex_ratio, 1e-6)
        return apex_height_m * (1.0 - (1.0 - local_progress) ** 2)

    def _apply_fly_slope_launch_boost(self, entity, traversal):
        if not isinstance(traversal, dict) or traversal.get('facility_type') != 'fly_slope' or traversal.get('direction') != 'forward':
            entity.fly_slope_immunity_armed = False
            return False
        launch_point = traversal.get('entry_point') or traversal.get('approach_point')
        landing_point = traversal.get('landing_point') or traversal.get('exit_point')
        if launch_point is None or landing_point is None:
            entity.fly_slope_immunity_armed = False
            return False
        direction_x = float(landing_point[0]) - float(launch_point[0])
        direction_y = float(landing_point[1]) - float(launch_point[1])
        direction_length = math.hypot(direction_x, direction_y)
        if direction_length <= 1e-6:
            entity.fly_slope_immunity_armed = False
            return False
        direction_x /= direction_length
        direction_y /= direction_length
        current_vx = float(entity.velocity.get('vx', 0.0))
        current_vy = float(entity.velocity.get('vy', 0.0))
        parallel_speed = current_vx * direction_x + current_vy * direction_y
        perpendicular_vx = current_vx - direction_x * parallel_speed
        perpendicular_vy = current_vy - direction_y * parallel_speed
        boost_world = self._meters_to_world_units(self.fly_slope_launch_boost_mps)
        enforced_parallel_speed = max(parallel_speed, boost_world)
        preserved_lateral = max(0.0, min(1.0, self.fly_slope_lateral_preserve))
        entity.velocity['vx'] = direction_x * enforced_parallel_speed + perpendicular_vx * preserved_lateral
        entity.velocity['vy'] = direction_y * enforced_parallel_speed + perpendicular_vy * preserved_lateral
        if not bool(getattr(entity, 'fly_slope_immunity_armed', False)):
            entity.fly_slope_airborne_timer = max(float(getattr(entity, 'fly_slope_airborne_timer', 0.0)), 2.0)
            entity.fly_slope_immunity_armed = True
        return True

    def _current_jump_airborne_height_m(self, entity):
        return max(0.0, float(getattr(entity, 'jump_airborne_height_m', 0.0)))

    def _current_jump_clearance_m(self, entity):
        airborne_height = self._current_jump_airborne_height_m(entity)
        vertical_velocity = float(getattr(entity, 'jump_vertical_velocity_mps', 0.0))
        if vertical_velocity <= 1e-6:
            return airborne_height
        remaining_rise = (vertical_velocity * vertical_velocity) / max(2.0 * self.jump_gravity_mps2, 1e-6)
        return min(self.infantry_jump_height_m, airborne_height + remaining_rise)

    def _current_airborne_body_clearance_m(self, entity):
        return self._current_jump_airborne_height_m(entity) + max(0.0, float(getattr(entity, 'fly_slope_airborne_height_m', 0.0)))

    def _can_entity_jump(self, entity):
        return (
            getattr(entity, 'type', None) == 'robot'
            and getattr(entity, 'robot_type', '') == '步兵'
            and not getattr(entity, 'step_climb_state', None)
            and float(getattr(entity, 'fly_slope_airborne_height_m', 0.0)) <= 1e-6
            and self._current_jump_airborne_height_m(entity) <= 1e-6
            and float(getattr(entity, 'jump_vertical_velocity_mps', 0.0)) <= 1e-6
        )

    def _update_jump_state(self, entity, dt):
        landing_grace_timer = max(0.0, float(getattr(entity, 'jump_landing_grace_timer', 0.0)) - float(dt))
        entity.jump_landing_grace_timer = landing_grace_timer
        if bool(getattr(entity, 'jump_requested', False)):
            entity.jump_requested = False
            if self._can_entity_jump(entity):
                entity.jump_vertical_velocity_mps = self.infantry_jump_launch_velocity_mps

        airborne_height = self._current_jump_airborne_height_m(entity)
        vertical_velocity = float(getattr(entity, 'jump_vertical_velocity_mps', 0.0))
        was_airborne = airborne_height > 1e-6 or vertical_velocity > 1e-6
        if airborne_height <= 1e-6 and vertical_velocity <= 1e-6:
            entity.jump_airborne_height_m = 0.0
            entity.jump_vertical_velocity_mps = 0.0
            entity.velocity['vz'] = 0.0
            return

        airborne_height = airborne_height + vertical_velocity * float(dt) - 0.5 * self.jump_gravity_mps2 * float(dt) * float(dt)
        vertical_velocity -= self.jump_gravity_mps2 * float(dt)
        airborne_height = max(0.0, airborne_height)
        if airborne_height <= 1e-6 and vertical_velocity <= 0.0:
            airborne_height = 0.0
            vertical_velocity = 0.0
        if was_airborne and airborne_height <= 1e-6 and vertical_velocity <= 1e-6:
            entity.jump_landing_grace_timer = self.jump_landing_grace_sec
        entity.jump_airborne_height_m = airborne_height
        entity.jump_vertical_velocity_mps = vertical_velocity
        entity.velocity['vz'] = vertical_velocity

    def _try_accept_jump_landing_pose(self, entity, map_manager, previous, current, step_limit, effective_step_limit):
        if float(getattr(entity, 'jump_landing_grace_timer', 0.0)) <= 1e-6:
            return False
        if map_manager is None:
            return False
        if not self._is_entity_chassis_pose_valid(map_manager, entity, current['x'], current['y']):
            return False
        previous_height = map_manager.get_terrain_height_m(previous['x'], previous['y'])
        current_height = map_manager.get_terrain_height_m(current['x'], current['y'])
        height_gain = current_height - previous_height
        if height_gain <= step_limit + 1e-6 or height_gain > effective_step_limit + 1e-6:
            return False
        move_distance = math.hypot(float(current['x']) - float(previous['x']), float(current['y']) - float(previous['y']))
        max_snap_distance = max(self._meters_to_world_units(0.9), self._entity_chassis_collision_radius(entity) * 1.6)
        if move_distance > max_snap_distance:
            return False
        entity.position['x'] = float(current['x'])
        entity.position['y'] = float(current['y'])
        entity.position['z'] = current_height
        entity.jump_airborne_height_m = 0.0
        entity.jump_vertical_velocity_mps = 0.0
        entity.jump_landing_grace_timer = 0.0
        entity.fly_slope_airborne_height_m = 0.0
        entity.fly_slope_immunity_armed = False
        entity.velocity['vz'] = 0.0
        entity.last_valid_position = dict(entity.position)
        return True

    def _entity_chassis_collision_radius(self, entity):
        body_length_m = float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.0)))
        body_width_m = float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.0)))
        if body_length_m <= 1e-6 or body_width_m <= 1e-6:
            return float(getattr(entity, 'collision_radius', 0.0))
        half_length = self._meters_to_world_units(body_length_m * 0.5)
        half_width = self._meters_to_world_units(body_width_m * 0.5)
        return max(float(getattr(entity, 'collision_radius', 0.0)), math.hypot(half_length, half_width))

    def _is_entity_chassis_pose_valid(self, map_manager, entity, x, y):
        if map_manager is None:
            return True
        if getattr(entity, 'type', None) not in {'robot', 'sentry'}:
            return map_manager.is_position_valid_for_radius(x, y, collision_radius=float(getattr(entity, 'collision_radius', 0.0)))
        return map_manager.is_position_valid_for_chassis(
            x,
            y,
            float(getattr(entity, 'angle', 0.0)),
            float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.0))),
            float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.0))),
            body_clearance_m=float(getattr(entity, 'body_clearance_m', 0.0)) + self._current_airborne_body_clearance_m(entity),
        )
    
    def update(self, entities, map_manager, rules_engine=None, dt=None):
        """更新物理状态"""
        sim_dt = float(dt if dt is not None else 1.0 / max(float(self.config.get('simulator', {}).get('fps', 50)), 1.0))
        for entity in entities:
            if not entity.is_alive() or not getattr(entity, 'collidable', True):
                continue
            
            # 应用摩擦力
            self.apply_friction(entity)
            self._update_jump_state(entity, sim_dt)

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
        step_climb_active = bool(getattr(entity, 'step_climb_state', None))
        # 检查与地图的碰撞
        if not step_climb_active and not self._is_entity_chassis_pose_valid(map_manager, entity, entity.position['x'], entity.position['y']):
            # 碰撞处理
            last_valid = dict(getattr(entity, 'last_valid_position', entity.position))
            if not self._is_entity_chassis_pose_valid(map_manager, entity, last_valid['x'], last_valid['y']):
                recovered = map_manager.find_nearest_passable_point(
                    (entity.position['x'], entity.position['y']),
                    collision_radius=self._entity_chassis_collision_radius(entity),
                    search_radius=max(96, int(self._entity_chassis_collision_radius(entity) * 8.0)),
                    step=max(4, map_manager.terrain_grid_cell_size),
                )
                if recovered is not None:
                    last_valid = {
                        'x': float(recovered[0]),
                        'y': float(recovered[1]),
                        'z': map_manager.get_terrain_height_m(recovered[0], recovered[1]) + self._current_jump_airborne_height_m(entity),
                    }
                    entity.last_valid_position = dict(last_valid)
            entity.position['x'] = last_valid['x']
            entity.position['y'] = last_valid['y']
            entity.position['z'] = map_manager.get_terrain_height_m(last_valid['x'], last_valid['y']) + self._current_jump_airborne_height_m(entity)
            entity.velocity['vx'] = 0.0
            entity.velocity['vy'] = 0.0
            entity.velocity['vz'] = float(getattr(entity, 'jump_vertical_velocity_mps', 0.0))
        
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

        if getattr(entity, 'step_climb_state', None):
            entity.fly_slope_airborne_height_m = 0.0
            if self._update_step_climb(entity, map_manager, dt):
                return
            entity.step_climb_state = None

        previous = dict(getattr(entity, 'previous_position', entity.position))
        current = entity.position
        direct_step_limit = self._resolved_direct_step_height(entity)
        climb_step_limit = self._resolved_step_climb_height(entity)
        jump_airborne_height = self._current_jump_airborne_height_m(entity)
        jump_traversal_clearance = self._current_jump_clearance_m(entity)
        effective_step_limit = direct_step_limit + jump_traversal_clearance
        effective_body_clearance = float(getattr(entity, 'body_clearance_m', 0.0)) + jump_airborne_height

        path_result = map_manager.evaluate_movement_path(
            previous['x'],
            previous['y'],
            current['x'],
            current['y'],
            max_height_delta_m=effective_step_limit,
            collision_radius=self._entity_chassis_collision_radius(entity),
            angle_deg=float(getattr(entity, 'angle', 0.0)),
            body_length_m=float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.0))),
            body_width_m=float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.0))),
            body_clearance_m=effective_body_clearance,
        )

        if path_result.get('ok'):
            traversal = map_manager.describe_segment_traversal(
                previous['x'],
                previous['y'],
                current['x'],
                current['y'],
                max_height_delta_m=climb_step_limit,
            )
            traversal_type = str(traversal.get('facility_type', '')) if isinstance(traversal, dict) else ''
            traversal_step_height = float(traversal.get('step_height_m', 0.0)) if isinstance(traversal, dict) else 0.0
            requires_step_motion = bool(getattr(entity, 'can_climb_steps', False)) and traversal_type in {'first_step', 'second_step', 'terrain_step'} and traversal_step_height > direct_step_limit + 1e-6
            if path_result.get('requires_step_alignment', False) or requires_step_motion:
                desired_heading_value = path_result.get('step_heading_deg')
                if desired_heading_value is None:
                    desired_heading_value = getattr(entity, 'angle', 0.0)
                desired_heading = float(desired_heading_value)
                if requires_step_motion and isinstance(traversal, dict):
                    approach_point = traversal.get('approach_point')
                    top_point = traversal.get('top_point')
                    desired_heading = self._step_heading_deg(approach_point, top_point, desired_heading)
                angle_diff = self._normalize_angle_diff(desired_heading - float(getattr(entity, 'angle', 0.0)))
                if abs(angle_diff) > 10.0:
                    turn_speed = 360.0 * float(dt)
                    turn_step = max(-turn_speed, min(turn_speed, angle_diff))
                    entity.angle = (float(getattr(entity, 'angle', 0.0)) + turn_step) % 360.0
                    entity.turret_angle = entity.angle
                    entity.position['x'] = previous['x']
                    entity.position['y'] = previous['y']
                    entity.position['z'] = float(path_result.get('start_height_m', previous.get('z', 0.0))) + jump_airborne_height
                    entity.velocity['vx'] = 0.0
                    entity.velocity['vy'] = 0.0
                    entity.velocity['vz'] = float(getattr(entity, 'jump_vertical_velocity_mps', 0.0))
                    entity.last_valid_position = dict(entity.position)
                    return
                if requires_step_motion:
                    transition = map_manager.get_step_transition(
                        previous['x'],
                        previous['y'],
                        current['x'],
                        current['y'],
                        max_height_delta_m=climb_step_limit,
                    )
                    if transition is not None:
                        entity.fly_slope_airborne_height_m = 0.0
                        self._begin_step_climb(entity, transition, map_manager, dt)
                        return
            self._apply_fly_slope_launch_boost(entity, traversal)
            airborne_height_m = 0.0
            if getattr(entity, 'type', None) == 'sentry':
                airborne_height_m = self._fly_slope_ballistic_height_m(entity, traversal)
            entity.fly_slope_airborne_height_m = airborne_height_m
            entity.position['z'] = float(path_result.get('end_height_m', current.get('z', 0.0))) + airborne_height_m + jump_airborne_height
            entity.last_valid_position = dict(entity.position)
            return

        transition = None
        if getattr(entity, 'can_climb_steps', False):
            transition = map_manager.get_step_transition(
                previous['x'],
                previous['y'],
                current['x'],
                current['y'],
                max_height_delta_m=climb_step_limit,
            )
        if transition is not None:
            entity.fly_slope_airborne_height_m = 0.0
            self._begin_step_climb(entity, transition, map_manager, dt)
            return

        if self._try_accept_jump_landing_pose(entity, map_manager, previous, current, direct_step_limit, effective_step_limit):
            return

        fallback = dict(getattr(entity, 'last_valid_position', previous))
        entity.position['x'] = fallback['x']
        entity.position['y'] = fallback['y']
        entity.position['z'] = map_manager.get_terrain_height_m(fallback['x'], fallback['y']) + jump_airborne_height
        entity.fly_slope_airborne_height_m = 0.0
        entity.fly_slope_immunity_armed = False
        entity.velocity['vx'] = 0.0
        entity.velocity['vy'] = 0.0
        entity.velocity['vz'] = float(getattr(entity, 'jump_vertical_velocity_mps', 0.0))

    def _resolved_step_climb_duration(self, entity):
        return float(getattr(entity, 'step_climb_duration_sec', self.infantry_step_climb_duration_sec))

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

    def _step_rear_contact_ratio(self, entity, start_point, end_point):
        if start_point is None or end_point is None:
            return 0.62
        distance = math.hypot(float(end_point[0]) - float(start_point[0]), float(end_point[1]) - float(start_point[1]))
        if distance <= 1e-6:
            return 0.62
        collision_radius = float(getattr(entity, 'collision_radius', 16.0))
        ratio = 0.45 + min(0.22, collision_radius / distance)
        return max(0.52, min(0.68, ratio))

    def _lerp_point(self, start_point, end_point, ratio):
        return (
            float(start_point[0]) + (float(end_point[0]) - float(start_point[0])) * float(ratio),
            float(start_point[1]) + (float(end_point[1]) - float(start_point[1])) * float(ratio),
        )

    def _configure_step_segment(self, entity, state, map_manager):
        segment_start = state.get('start_point') or state.get('approach_point')
        end_point = state.get('end_point') or state.get('top_point')
        if segment_start is None or end_point is None:
            return
        segment_start = (float(segment_start[0]), float(segment_start[1]))
        end_point = (float(end_point[0]), float(end_point[1]))
        rear_contact_ratio = self._step_rear_contact_ratio(entity, segment_start, end_point)
        rear_contact_point = self._lerp_point(segment_start, end_point, rear_contact_ratio)
        total_duration = max(float(state.get('total_duration', self._resolved_step_climb_duration(entity))), 0.8)
        state['segment_start_point'] = segment_start
        state['segment_start_height'] = map_manager.get_terrain_height_m(segment_start[0], segment_start[1])
        state['rear_contact_ratio'] = rear_contact_ratio
        state['rear_contact_point'] = rear_contact_point
        state['rear_contact_height'] = map_manager.get_terrain_height_m(rear_contact_point[0], rear_contact_point[1])
        state['front_ascent_duration'] = max(0.2, total_duration * 0.42)
        state['rear_pause_duration'] = 0.5
        state['rear_ascent_duration'] = max(0.18, total_duration * 0.28)

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
        self._configure_step_segment(entity, state, map_manager)
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
                self._configure_step_segment(entity, state, map_manager)
                state['align_probe_index'] = 0
                state['align_stuck_time'] = 0.0
                state['align_last_abs_diff'] = None
                return True
        return False

    def _begin_step_climb(self, entity, transition, map_manager, dt):
        state = getattr(entity, 'step_climb_state', None)
        if state is None or state.get('facility_id') != transition.get('facility_id'):
            approach_point = transition.get('approach_point')
            if approach_point is None:
                start_point = (float(entity.previous_position['x']), float(entity.previous_position['y']))
            else:
                start_point = (float(approach_point[0]), float(approach_point[1]))
            segment_points = tuple(
                (float(point[0]), float(point[1])) for point in transition.get('climb_points', ())
            ) or ((float(transition.get('top_point')[0]), float(transition.get('top_point')[1])),)
            end_point = segment_points[0]
            desired_heading_deg = self._step_heading_deg(start_point, end_point, getattr(entity, 'angle', 0.0))
            total_duration = float(getattr(entity, 'step_climb_duration_sec', self._resolved_step_climb_duration(entity)))
            entity.step_climb_state = {
                'facility_id': transition.get('facility_id'),
                'facility_type': transition.get('facility_type'),
                'progress': 0.0,
                'total_duration': total_duration,
                'step_limit_m': self._resolved_step_climb_height(entity),
                'phase': 'align',
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
            self._configure_step_segment(entity, entity.step_climb_state, map_manager)
        self._update_step_climb(entity, map_manager, dt)

    def _update_step_climb(self, entity, map_manager, dt):
        state = getattr(entity, 'step_climb_state', None)
        if not state:
            return False
        start_point = state.get('segment_start_point') or state.get('start_point') or state.get('approach_point')
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
                entity.position['z'] = float(state.get('segment_start_height', state.get('start_height', map_manager.get_terrain_height_m(start_point[0], start_point[1]))))
                entity.last_valid_position = dict(entity.position)
                entity.previous_position = dict(entity.position)
                return True
            state['phase'] = 'front_ascent'
            state['progress'] = 0.0
            state['start_point'] = (float(entity.position['x']), float(entity.position['y']))
            state['start_height'] = map_manager.get_terrain_height_m(entity.position['x'], entity.position['y'])
            self._configure_step_segment(entity, state, map_manager)
            state['align_stuck_time'] = 0.0
            state['align_last_abs_diff'] = None
            state['align_probe_index'] = 0

        phase = state.get('phase', 'front_ascent')
        desired_heading = float(state.get('desired_heading_deg', getattr(entity, 'angle', 0.0)))
        if phase == 'rear_pause':
            hold_point = state.get('rear_contact_point') or end_point or start_point
            hold_height = float(state.get('rear_contact_height', map_manager.get_terrain_height_m(hold_point[0], hold_point[1])))
            entity.position['x'] = hold_point[0]
            entity.position['y'] = hold_point[1]
            entity.position['z'] = hold_height
            entity.angle = desired_heading % 360.0
            entity.turret_angle = entity.angle
            entity.last_valid_position = dict(entity.position)
            entity.previous_position = dict(entity.position)
            state['progress'] = float(state.get('progress', 0.0)) + float(dt)
            if state['progress'] < float(state.get('rear_pause_duration', 0.5)):
                return True
            state['phase'] = 'rear_ascent'
            state['progress'] = 0.0
            state['climb_last_progress'] = 0.0
            state['climb_stuck_time'] = 0.0
            return True

        motion_start = state.get('segment_start_point', start_point)
        motion_end = end_point
        motion_start_height = float(state.get('segment_start_height', state.get('start_height', map_manager.get_terrain_height_m(motion_start[0], motion_start[1]))))
        motion_end_height = float(state.get('end_height', map_manager.get_terrain_height_m(motion_end[0], motion_end[1]))) if motion_end is not None else motion_start_height
        duration = float(state.get('front_ascent_duration', self.default_step_climb_duration_sec))
        if phase == 'front_ascent':
            motion_end = state.get('rear_contact_point') or end_point
            motion_end_height = float(state.get('rear_contact_height', motion_end_height))
            duration = float(state.get('front_ascent_duration', self.default_step_climb_duration_sec))
        elif phase == 'rear_ascent':
            motion_start = state.get('rear_contact_point') or motion_start
            motion_start_height = float(state.get('rear_contact_height', motion_start_height))
            duration = float(state.get('rear_ascent_duration', self.default_step_climb_duration_sec))

        state['progress'] = float(state.get('progress', 0.0)) + float(dt)
        duration = max(duration, 1e-6)
        ratio = max(0.0, min(1.0, state['progress'] / duration))
        motion_ratio = ratio * ratio if phase == 'front_ascent' else (ratio * ratio * (3.0 - 2.0 * ratio))
        next_x = motion_start[0] + (motion_end[0] - motion_start[0]) * motion_ratio
        next_y = motion_start[1] + (motion_end[1] - motion_start[1]) * motion_ratio
        if not map_manager.is_position_valid_for_radius(next_x, next_y, collision_radius=float(getattr(entity, 'collision_radius', 0.0))):
            state['climb_stuck_time'] = float(state.get('climb_stuck_time', 0.0)) + float(dt)
            if state['climb_stuck_time'] >= 0.25 and self._reseek_step_entry(entity, state, map_manager):
                state['phase'] = 'front_ascent'
                state['progress'] = 0.0
                state['start_point'] = (float(entity.position['x']), float(entity.position['y']))
                state['start_height'] = map_manager.get_terrain_height_m(entity.position['x'], entity.position['y'])
                state['end_height'] = map_manager.get_terrain_height_m(state['end_point'][0], state['end_point'][1])
                self._configure_step_segment(entity, state, map_manager)
                state['climb_stuck_time'] = 0.0
                state['climb_last_progress'] = 0.0
                return True
            entity.position['x'] = start_point[0]
            entity.position['y'] = start_point[1]
            entity.position['z'] = float(state.get('segment_start_height', state.get('start_height', map_manager.get_terrain_height_m(start_point[0], start_point[1]))))
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
        entity.position['z'] = motion_start_height + (motion_end_height - motion_start_height) * motion_ratio
        entity.angle = desired_heading % 360.0
        entity.turret_angle = entity.angle
        entity.last_valid_position = dict(entity.position)
        if ratio < 1.0:
            return True

        if phase == 'front_ascent':
            contact_point = state.get('rear_contact_point') or motion_end
            entity.position['x'] = contact_point[0]
            entity.position['y'] = contact_point[1]
            entity.position['z'] = float(state.get('rear_contact_height', motion_end_height))
            entity.previous_position = dict(entity.position)
            entity.last_valid_position = dict(entity.position)
            state['phase'] = 'rear_pause'
            state['progress'] = 0.0
            state['climb_last_progress'] = 0.0
            state['climb_stuck_time'] = 0.0
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
            self._configure_step_segment(entity, state, map_manager)
            state['phase'] = 'front_ascent'
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
