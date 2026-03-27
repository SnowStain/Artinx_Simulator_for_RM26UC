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
        self.default_max_terrain_step_height_m = float(config.get('physics', {}).get('normal_max_terrain_step_height_m', 0.05))
        self.default_step_climb_duration_sec = float(config.get('physics', {}).get('default_step_climb_duration_sec', 2.0))
        self.infantry_step_climb_duration_sec = float(config.get('physics', {}).get('infantry_step_climb_duration_sec', 0.5))

    def _max_speed_world_units(self):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return self.max_speed * ((pixels_per_meter_x + pixels_per_meter_y) / 2.0)
    
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
        if not map_manager.is_position_valid(entity.position['x'], entity.position['y']):
            # 碰撞处理
            last_valid = dict(getattr(entity, 'last_valid_position', entity.position))
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
        
        radius1 = radius_map.get(entity1.type, 10)
        radius2 = radius_map.get(entity2.type, 10)
        
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
        
        # 分离实体
        if entity1_movable and entity2_movable:
            entity1.position['x'] -= nx * overlap * 0.5
            entity1.position['y'] -= ny * overlap * 0.5
            entity2.position['x'] += nx * overlap * 0.5
            entity2.position['y'] += ny * overlap * 0.5
        elif entity1_movable:
            entity1.position['x'] -= nx * overlap
            entity1.position['y'] -= ny * overlap
        elif entity2_movable:
            entity2.position['x'] += nx * overlap
            entity2.position['y'] += ny * overlap
        
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
        path_result = map_manager.evaluate_movement_path(
            previous['x'],
            previous['y'],
            current['x'],
            current['y'],
            max_height_delta_m=step_limit,
        )

        if path_result.get('ok'):
            entity.position['z'] = float(path_result.get('end_height_m', current.get('z', 0.0)))
            entity.last_valid_position = dict(entity.position)
            return

        if path_result.get('reason') == 'height_delta':
            transition = map_manager.get_step_transition(previous['x'], previous['y'], current['x'], current['y'])
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

    def _begin_step_climb(self, entity, transition, map_manager, dt):
        state = getattr(entity, 'step_climb_state', None)
        if state is None or state.get('facility_id') != transition.get('facility_id'):
            start_point = (float(entity.previous_position['x']), float(entity.previous_position['y']))
            end_point = (float(transition.get('top_point')[0]), float(transition.get('top_point')[1]))
            entity.step_climb_state = {
                'facility_id': transition.get('facility_id'),
                'facility_type': transition.get('facility_type'),
                'progress': 0.0,
                'duration': self._resolved_step_climb_duration(entity),
                'start_point': start_point,
                'approach_point': transition.get('approach_point'),
                'top_point': transition.get('top_point'),
                'end_point': end_point,
                'start_height': map_manager.get_terrain_height_m(start_point[0], start_point[1]),
                'end_height': map_manager.get_terrain_height_m(end_point[0], end_point[1]),
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
        state['progress'] = float(state.get('progress', 0.0)) + float(dt)
        duration = max(float(state.get('duration', self.default_step_climb_duration_sec)), 1e-6)
        ratio = max(0.0, min(1.0, state['progress'] / duration))
        smooth_ratio = ratio * ratio * (3.0 - 2.0 * ratio)
        entity.position['x'] = start_point[0] + (end_point[0] - start_point[0]) * smooth_ratio
        entity.position['y'] = start_point[1] + (end_point[1] - start_point[1]) * smooth_ratio
        entity.position['z'] = float(state.get('start_height', 0.0)) + (float(state.get('end_height', 0.0)) - float(state.get('start_height', 0.0))) * smooth_ratio
        entity.last_valid_position = dict(entity.position)
        if ratio < 1.0:
            return True

        entity.position['x'] = end_point[0]
        entity.position['y'] = end_point[1]
        entity.position['z'] = float(state.get('end_height', map_manager.get_terrain_height_m(end_point[0], end_point[1])))
        entity.previous_position = dict(entity.position)
        entity.last_valid_position = dict(entity.position)
        entity.step_climb_state = None
        return True
