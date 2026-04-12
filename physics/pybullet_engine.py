#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math
import os

try:
    import pybullet as p
except ImportError:  # pragma: no cover - runtime dependency
    p = None


class PyBulletPhysicsEngine:
    def __init__(self, config):
        if p is None:
            raise ImportError('PyBulletPhysicsEngine requires the pybullet package. Install pybullet first.')
        self.config = config
        physics_cfg = config.get('physics', {})
        self.max_speed = float(physics_cfg.get('max_speed', 3.5))
        self.max_acceleration = float(physics_cfg.get('max_acceleration', 2.0))
        self.max_angular_speed = float(physics_cfg.get('max_angular_speed', 180.0))
        self.default_direct_terrain_step_height_m = float(physics_cfg.get('direct_terrain_step_height_m', 0.06))
        self.default_max_terrain_step_height_m = float(physics_cfg.get('normal_max_terrain_step_height_m', 0.35))
        self.infantry_jump_height_m = float(physics_cfg.get('infantry_jump_height_m', 0.40))
        self.infantry_jump_forward_speed_mps = float(physics_cfg.get('infantry_jump_forward_speed_mps', 2.8))
        self.jump_gravity_mps2 = float(physics_cfg.get('jump_gravity_mps2', 9.8))
        self.linear_drag = float(physics_cfg.get('linear_drag', 0.16))
        self.angular_drag = float(physics_cfg.get('angular_drag', 0.24))
        self.lateral_friction = float(physics_cfg.get('lateral_friction', 1.15))
        self.restitution = float(physics_cfg.get('restitution', 0.02))
        self.contact_damage_speed_threshold_mps = float(physics_cfg.get('contact_damage_speed_threshold_mps', 0.45))
        self.jump_landing_grace_sec = float(physics_cfg.get('jump_landing_grace_sec', 0.18))
        self.airborne_ground_tolerance_m = float(physics_cfg.get('airborne_ground_tolerance_m', 0.035))
        self.fixed_time_step = float(physics_cfg.get('pybullet_fixed_time_step_sec', 1.0 / 120.0))
        self.max_substeps = int(max(1, physics_cfg.get('pybullet_max_substeps', 4)))
        self.infantry_jump_launch_velocity_mps = math.sqrt(max(0.0, 2.0 * self.jump_gravity_mps2 * self.infantry_jump_height_m))

        self.client = p.connect(p.DIRECT)
        p.setGravity(0.0, 0.0, -self.jump_gravity_mps2, physicsClientId=self.client)
        p.setPhysicsEngineParameter(
            fixedTimeStep=self.fixed_time_step,
            numSubSteps=self.max_substeps,
            physicsClientId=self.client,
        )
        self._plane_shape = p.createCollisionShape(p.GEOM_PLANE, physicsClientId=self.client)
        self._plane_body = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=self._plane_shape,
            basePosition=[0.0, 0.0, 0.0],
            physicsClientId=self.client,
        )
        self._terrain_body = None
        self._terrain_key = None
        self._entity_body_ids = {}
        self._body_entity_ids = {}
        self._entity_joint_pairs = {}
        self._entity_commanded_planar_velocity_mps = {}

    def shutdown(self):
        if getattr(self, 'client', None) is not None:
            try:
                p.disconnect(physicsClientId=self.client)
            except Exception:
                pass
            self.client = None

    def _max_speed_world_units(self):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return self.max_speed * ((pixels_per_meter_x + pixels_per_meter_y) * 0.5)

    def _meters_to_world_units(self, meters):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        return float(meters) * ((pixels_per_meter_x + pixels_per_meter_y) * 0.5)

    def _world_units_to_meters(self, world_units):
        field_length_m = float(self.config.get('map', {}).get('field_length_m', 28.0))
        field_width_m = float(self.config.get('map', {}).get('field_width_m', 15.0))
        map_width = float(self.config.get('map', {}).get('width', 1576))
        map_height = float(self.config.get('map', {}).get('height', 873))
        pixels_per_meter_x = map_width / max(field_length_m, 1e-6)
        pixels_per_meter_y = map_height / max(field_width_m, 1e-6)
        pixels_per_meter = max((pixels_per_meter_x + pixels_per_meter_y) * 0.5, 1e-6)
        return float(world_units) / pixels_per_meter

    def _entity_uses_level_body_pose(self, entity):
        return getattr(entity, 'type', None) == 'robot' and getattr(entity, 'robot_type', '') == '步兵'

    def _resolved_direct_step_height(self, entity):
        return max(0.0, float(getattr(entity, 'direct_terrain_step_height_m', self.default_direct_terrain_step_height_m)))

    def _resolved_step_climb_height(self, entity):
        return max(
            self._resolved_direct_step_height(entity),
            float(getattr(entity, 'max_step_climb_height_m', self.default_max_terrain_step_height_m)),
        )

    def _current_jump_airborne_height_m(self, entity):
        return max(0.0, float(getattr(entity, 'jump_airborne_height_m', 0.0)))

    def _current_jump_pose_height_m(self, entity):
        return max(
            self._current_jump_airborne_height_m(entity),
            max(0.0, float(getattr(entity, 'jump_clearance_target_m', 0.0))),
            max(0.0, float(getattr(entity, 'fly_slope_airborne_height_m', 0.0))),
        )

    def _current_jump_clearance_m(self, entity):
        airborne_height = self._current_jump_pose_height_m(entity)
        vertical_velocity = float(getattr(entity, 'jump_vertical_velocity_mps', 0.0))
        if vertical_velocity <= 1e-6:
            return airborne_height
        remaining_rise = (vertical_velocity * vertical_velocity) / max(2.0 * self.jump_gravity_mps2, 1e-6)
        return min(self.infantry_jump_height_m, airborne_height + remaining_rise)

    def _entity_collision_radius_world(self, entity):
        body_length_m = float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.0)))
        body_width_m = float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.0)))
        if body_length_m > 1e-6 and body_width_m > 1e-6 and not self._entity_uses_level_body_pose(entity):
            return max(float(getattr(entity, 'collision_radius', 0.0)), self._meters_to_world_units(math.hypot(body_length_m * 0.5, body_width_m * 0.5)))
        return float(getattr(entity, 'collision_radius', 0.0))

    def _is_entity_pose_valid(self, map_manager, entity, x_world, y_world, angle_deg=None):
        if map_manager is None:
            return True
        if getattr(entity, 'type', None) not in {'robot', 'sentry'} or self._entity_uses_level_body_pose(entity):
            return map_manager.is_position_valid_for_radius(x_world, y_world, collision_radius=self._entity_collision_radius_world(entity))
        return map_manager.is_position_valid_for_chassis(
            x_world,
            y_world,
            float(getattr(entity, 'angle', 0.0) if angle_deg is None else angle_deg),
            float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.0))),
            float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.0))),
            body_clearance_m=float(getattr(entity, 'body_clearance_m', 0.0)) + self._current_jump_pose_height_m(entity),
        )

    def _body_half_extents_m(self, entity):
        return (
            max(0.04, float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5),
            max(0.04, float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.5),
            max(0.03, float(getattr(entity, 'body_height_m', 0.18)) * 0.5),
        )

    def _entity_mass_kg(self, entity):
        if not getattr(entity, 'movable', True) or getattr(entity, 'type', None) in {'outpost', 'base', 'radar'}:
            return 0.0
        if getattr(entity, 'type', None) == 'sentry':
            return 55.0
        if getattr(entity, 'type', None) == 'uav':
            return 9.0
        if getattr(entity, 'robot_type', '') == '步兵':
            return 18.0
        if getattr(entity, 'robot_type', '') == '英雄':
            return 42.0
        return 32.0

    def _entity_center_z_m(self, entity, ground_height_m):
        _, _, half_height = self._body_half_extents_m(entity)
        return float(ground_height_m) + float(getattr(entity, 'body_clearance_m', 0.0)) + half_height + self._current_jump_pose_height_m(entity)

    def _build_joint_arrays(self, entity):
        side_offsets = (-1.0, 1.0)
        joint_pairs = []
        link_masses = []
        link_collision_shapes = []
        link_visual_shapes = []
        link_positions = []
        link_orientations = []
        link_inertial_positions = []
        link_inertial_orientations = []
        link_parent_indices = []
        link_joint_types = []
        link_joint_axes = []

        if getattr(entity, 'rear_climb_assist_style', 'none') != 'none':
            mount_x = -float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.5 + float(getattr(entity, 'rear_climb_assist_mount_offset_x_m', 0.03))
            mount_z = float(getattr(entity, 'rear_climb_assist_mount_height_m', 0.20)) - float(getattr(entity, 'body_clearance_m', 0.0)) - float(getattr(entity, 'body_height_m', 0.18)) * 0.5
            for side_index, side_sign in enumerate(side_offsets):
                side_y = float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.26 * side_sign
                upper_joint_index = len(link_masses)
                link_masses.append(0.05)
                link_collision_shapes.append(-1)
                link_visual_shapes.append(-1)
                link_positions.append([mount_x, side_y, mount_z])
                link_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_inertial_positions.append([0.0, 0.0, 0.0])
                link_inertial_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_parent_indices.append(0)
                link_joint_types.append(p.JOINT_REVOLUTE)
                link_joint_axes.append([0.0, 1.0, 0.0])
                lower_joint_index = len(link_masses)
                link_masses.append(0.04)
                link_collision_shapes.append(-1)
                link_visual_shapes.append(-1)
                link_positions.append([0.0, 0.0, -max(0.04, float(getattr(entity, 'rear_climb_assist_upper_length_m', 0.09)))])
                link_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_inertial_positions.append([0.0, 0.0, 0.0])
                link_inertial_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_parent_indices.append(upper_joint_index)
                link_joint_types.append(p.JOINT_REVOLUTE)
                link_joint_axes.append([0.0, 1.0, 0.0])
                joint_pairs.append((upper_joint_index, lower_joint_index, 'rear'))

        if getattr(entity, 'wheel_style', 'standard') == 'legged':
            mount_x = float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.42))) * 0.22
            mount_z = -float(getattr(entity, 'body_height_m', 0.18)) * 0.12
            for side_index, side_sign in enumerate(side_offsets):
                side_y = float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.42))) * 0.27 * side_sign
                upper_joint_index = len(link_masses)
                link_masses.append(0.05)
                link_collision_shapes.append(-1)
                link_visual_shapes.append(-1)
                link_positions.append([mount_x, side_y, mount_z])
                link_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_inertial_positions.append([0.0, 0.0, 0.0])
                link_inertial_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_parent_indices.append(0)
                link_joint_types.append(p.JOINT_REVOLUTE)
                link_joint_axes.append([0.0, 1.0, 0.0])
                lower_joint_index = len(link_masses)
                link_masses.append(0.04)
                link_collision_shapes.append(-1)
                link_visual_shapes.append(-1)
                link_positions.append([0.0, 0.0, -max(0.06, float(getattr(entity, 'body_clearance_m', 0.20)) * 0.65)])
                link_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_inertial_positions.append([0.0, 0.0, 0.0])
                link_inertial_orientations.append([0.0, 0.0, 0.0, 1.0])
                link_parent_indices.append(upper_joint_index)
                link_joint_types.append(p.JOINT_REVOLUTE)
                link_joint_axes.append([0.0, 1.0, 0.0])
                joint_pairs.append((upper_joint_index, lower_joint_index, 'leg'))

        if not joint_pairs:
            return None, None
        return {
            'linkMasses': link_masses,
            'linkCollisionShapeIndices': link_collision_shapes,
            'linkVisualShapeIndices': link_visual_shapes,
            'linkPositions': link_positions,
            'linkOrientations': link_orientations,
            'linkInertialFramePositions': link_inertial_positions,
            'linkInertialFrameOrientations': link_inertial_orientations,
            'linkParentIndices': link_parent_indices,
            'linkJointTypes': link_joint_types,
            'linkJointAxis': link_joint_axes,
        }, joint_pairs

    def _sync_joint_targets(self, entity):
        body_id = self._entity_body_ids.get(entity.id)
        joint_pairs = self._entity_joint_pairs.get(entity.id, ())
        if body_id is None or not joint_pairs:
            return
        stance_ratio = 1.0 if (getattr(entity, 'step_climb_state', None) or self._current_jump_pose_height_m(entity) > 1e-3) else 0.0
        for upper_joint, lower_joint, joint_kind in joint_pairs:
            if joint_kind == 'rear':
                upper_target = 1.10 - 0.40 * stance_ratio
                lower_target = -1.72 + 0.85 * stance_ratio
            else:
                upper_target = 0.95 - 0.28 * stance_ratio
                lower_target = -1.45 + 0.50 * stance_ratio
            p.setJointMotorControl2(body_id, upper_joint, p.POSITION_CONTROL, targetPosition=upper_target, force=12.0, physicsClientId=self.client)
            p.setJointMotorControl2(body_id, lower_joint, p.POSITION_CONTROL, targetPosition=lower_target, force=12.0, physicsClientId=self.client)

    def _ensure_terrain_body(self):
        asset_path = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'robot_venue_map_asset', 'venue_map_pybullet.obj'))
        terrain_key = None
        if os.path.exists(asset_path):
            terrain_key = (asset_path, os.path.getmtime(asset_path))
        if terrain_key == self._terrain_key:
            return
        if self._terrain_body is not None:
            p.removeBody(self._terrain_body, physicsClientId=self.client)
            self._terrain_body = None
        self._terrain_key = terrain_key
        if terrain_key is None:
            return
        try:
            terrain_shape = p.createCollisionShape(
                p.GEOM_MESH,
                fileName=asset_path,
                flags=p.GEOM_FORCE_CONCAVE_TRIMESH,
                physicsClientId=self.client,
            )
            self._terrain_body = p.createMultiBody(
                baseMass=0.0,
                baseCollisionShapeIndex=terrain_shape,
                basePosition=[0.0, 0.0, 0.0],
                physicsClientId=self.client,
            )
        except Exception:
            self._terrain_body = None

    def _create_entity_body(self, entity, map_manager):
        half_x, half_y, half_z = self._body_half_extents_m(entity)
        collision_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=[half_x, half_y, half_z],
            physicsClientId=self.client,
        )
        spawn_ground = 0.0 if map_manager is None else float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))
        spawn_position = [
            self._world_units_to_meters(float(entity.position['x'])),
            self._world_units_to_meters(float(entity.position['y'])),
            self._entity_center_z_m(entity, spawn_ground),
        ]
        yaw_quat = p.getQuaternionFromEuler([0.0, 0.0, math.radians(float(getattr(entity, 'angle', 0.0)))])
        link_arrays, joint_pairs = self._build_joint_arrays(entity)
        body_id = p.createMultiBody(
            baseMass=self._entity_mass_kg(entity),
            baseCollisionShapeIndex=collision_shape,
            basePosition=spawn_position,
            baseOrientation=yaw_quat,
            physicsClientId=self.client,
            **(link_arrays or {}),
        )
        p.changeDynamics(
            body_id,
            -1,
            lateralFriction=self.lateral_friction,
            restitution=self.restitution,
            linearDamping=self.linear_drag,
            angularDamping=self.angular_drag,
            physicsClientId=self.client,
        )
        for joint_index in range(p.getNumJoints(body_id, physicsClientId=self.client)):
            p.setCollisionFilterGroupMask(body_id, joint_index, 0, 0, physicsClientId=self.client)
            p.changeDynamics(body_id, joint_index, mass=0.02, physicsClientId=self.client)
        self._entity_body_ids[entity.id] = body_id
        self._body_entity_ids[body_id] = entity.id
        self._entity_joint_pairs[entity.id] = tuple(joint_pairs or ())
        self._sync_joint_targets(entity)

    def _remove_stale_bodies(self, entities):
        active_ids = {entity.id for entity in entities}
        stale_ids = [entity_id for entity_id in self._entity_body_ids.keys() if entity_id not in active_ids]
        for entity_id in stale_ids:
            body_id = self._entity_body_ids.pop(entity_id, None)
            self._entity_joint_pairs.pop(entity_id, None)
            self._entity_commanded_planar_velocity_mps.pop(entity_id, None)
            if body_id is not None:
                self._body_entity_ids.pop(body_id, None)
                p.removeBody(body_id, physicsClientId=self.client)

    def _ensure_entity_body(self, entity, map_manager):
        body_id = self._entity_body_ids.get(entity.id)
        if body_id is None:
            self._create_entity_body(entity, map_manager)
            body_id = self._entity_body_ids.get(entity.id)
        return body_id

    def _can_entity_jump(self, entity, body_position_z_m, map_manager):
        if getattr(entity, 'type', None) != 'robot' or getattr(entity, 'robot_type', '') != '步兵':
            return False
        if map_manager is None:
            return False
        terrain_height = float(map_manager.get_terrain_height_m(entity.position['x'], entity.position['y']))
        grounded_center = self._entity_center_z_m(entity, terrain_height)
        return abs(float(body_position_z_m) - grounded_center) <= self.airborne_ground_tolerance_m

    def _apply_jump_request(self, entity, body_id, map_manager):
        if not bool(getattr(entity, 'jump_requested', False)):
            return
        entity.jump_requested = False
        body_position, _ = p.getBasePositionAndOrientation(body_id, physicsClientId=self.client)
        if not self._can_entity_jump(entity, body_position[2], map_manager):
            return
        linear_velocity, _ = p.getBaseVelocity(body_id, physicsClientId=self.client)
        planar_speed = math.hypot(linear_velocity[0], linear_velocity[1])
        minimum_planar_speed = max(self.infantry_jump_forward_speed_mps, planar_speed)
        yaw_rad = math.radians(float(getattr(entity, 'angle', 0.0)))
        jump_velocity = (
            math.cos(yaw_rad) * minimum_planar_speed,
            math.sin(yaw_rad) * minimum_planar_speed,
            self.infantry_jump_launch_velocity_mps,
        )
        p.resetBaseVelocity(body_id, linearVelocity=jump_velocity, physicsClientId=self.client)

    def _evaluate_target_motion(self, entity, body_id, map_manager, dt):
        body_position, _ = p.getBasePositionAndOrientation(body_id, physicsClientId=self.client)
        current_world_x = self._meters_to_world_units(body_position[0])
        current_world_y = self._meters_to_world_units(body_position[1])
        commanded_world_x = current_world_x + float(entity.velocity.get('vx', 0.0)) * float(dt)
        commanded_world_y = current_world_y + float(entity.velocity.get('vy', 0.0)) * float(dt)
        authored_world_x = float(entity.position['x'])
        authored_world_y = float(entity.position['y'])
        teleport_threshold_world = max(
            self._meters_to_world_units(0.35),
            self._max_speed_world_units() * max(float(dt), 1e-6) * 2.5,
        )
        authored_offset_world = math.hypot(authored_world_x - current_world_x, authored_world_y - current_world_y)
        force_xy_sync = authored_offset_world > teleport_threshold_world
        desired_world_x = authored_world_x if force_xy_sync else commanded_world_x
        desired_world_y = authored_world_y if force_xy_sync else commanded_world_y
        current_ground = float(map_manager.get_terrain_height_m(current_world_x, current_world_y)) if map_manager is not None else 0.0
        direct_step_limit = self._resolved_direct_step_height(entity)
        climb_step_limit = self._resolved_step_climb_height(entity)
        jump_pose_height = self._current_jump_pose_height_m(entity)
        jump_traversal_clearance = self._current_jump_clearance_m(entity)
        effective_step_limit = direct_step_limit + jump_traversal_clearance
        use_level_pose = self._entity_uses_level_body_pose(entity)

        if map_manager is None:
            return desired_world_x, desired_world_y, current_ground, False, force_xy_sync

        path_result = map_manager.evaluate_movement_path(
            current_world_x,
            current_world_y,
            desired_world_x,
            desired_world_y,
            max_height_delta_m=effective_step_limit,
            collision_radius=self._entity_collision_radius_world(entity),
            angle_deg=float(getattr(entity, 'angle', 0.0)),
            body_length_m=None if use_level_pose else float(getattr(entity, 'body_length_m', getattr(entity, 'body_size_m', 0.0))),
            body_width_m=None if use_level_pose else float(getattr(entity, 'body_width_m', getattr(entity, 'body_size_m', 0.0))),
            body_clearance_m=0.0 if use_level_pose else float(getattr(entity, 'body_clearance_m', 0.0)) + jump_pose_height,
        )
        if path_result.get('ok'):
            return desired_world_x, desired_world_y, float(path_result.get('end_height_m', current_ground)), bool(path_result.get('requires_step_alignment', False)), force_xy_sync

        desired_ground = float(map_manager.get_terrain_height_m(desired_world_x, desired_world_y))
        if desired_ground <= current_ground + 1e-6 and self._is_entity_pose_valid(map_manager, entity, desired_world_x, desired_world_y, angle_deg=float(getattr(entity, 'angle', 0.0))):
            return desired_world_x, desired_world_y, desired_ground, False, force_xy_sync

        if bool(getattr(entity, 'can_climb_steps', False)):
            transition = map_manager.get_step_transition(
                current_world_x,
                current_world_y,
                desired_world_x,
                desired_world_y,
                max_height_delta_m=climb_step_limit,
            )
            if transition is not None:
                top_point = transition.get('top_point') or (desired_world_x, desired_world_y)
                top_ground = float(map_manager.get_terrain_height_m(top_point[0], top_point[1]))
                entity.step_climb_state = {
                    'phase': 'pybullet_step',
                    'top_point': top_point,
                    'progress': 1.0,
                }
                return float(top_point[0]), float(top_point[1]), top_ground, True, True

        entity.step_climb_state = None
        return current_world_x, current_world_y, current_ground, False, False

    def _apply_entity_drive(self, entity, body_id, map_manager, dt):
        body_position, _ = p.getBasePositionAndOrientation(body_id, physicsClientId=self.client)
        linear_velocity, _ = p.getBaseVelocity(body_id, physicsClientId=self.client)
        target_world_x, target_world_y, target_ground, stepped, force_xy_sync = self._evaluate_target_motion(entity, body_id, map_manager, dt)
        target_x_m = self._world_units_to_meters(target_world_x)
        target_y_m = self._world_units_to_meters(target_world_y)
        planar_vx = (target_x_m - body_position[0]) / max(float(dt), 1e-6)
        planar_vy = (target_y_m - body_position[1]) / max(float(dt), 1e-6)
        planar_speed = math.hypot(planar_vx, planar_vy)
        max_speed_mps = self.max_speed
        if planar_speed > max_speed_mps:
            planar_vx *= max_speed_mps / planar_speed
            planar_vy *= max_speed_mps / planar_speed
        vertical_velocity = float(linear_velocity[2]) * max(0.0, 1.0 - self.linear_drag * float(dt))
        target_center_z = self._entity_center_z_m(entity, target_ground)
        reset_z = max(body_position[2], target_center_z)
        if stepped:
            reset_z = target_center_z
        yaw_quat = p.getQuaternionFromEuler([0.0, 0.0, math.radians(float(getattr(entity, 'angle', 0.0)))])
        reset_x = target_x_m
        reset_y = target_y_m
        self._entity_commanded_planar_velocity_mps[entity.id] = (planar_vx, planar_vy)
        p.resetBasePositionAndOrientation(body_id, [reset_x, reset_y, reset_z], yaw_quat, physicsClientId=self.client)
        p.resetBaseVelocity(body_id, linearVelocity=[0.0, 0.0, vertical_velocity], angularVelocity=[0.0, 0.0, math.radians(float(getattr(entity, 'angular_velocity', 0.0)))], physicsClientId=self.client)
        self._apply_jump_request(entity, body_id, map_manager)
        self._sync_joint_targets(entity)

    def _sync_entity_from_body(self, entity, body_id, map_manager):
        body_position, body_orientation = p.getBasePositionAndOrientation(body_id, physicsClientId=self.client)
        linear_velocity, angular_velocity = p.getBaseVelocity(body_id, physicsClientId=self.client)
        world_x = self._meters_to_world_units(body_position[0])
        world_y = self._meters_to_world_units(body_position[1])
        ground_height = 0.0 if map_manager is None else float(map_manager.get_terrain_height_m(world_x, world_y))
        base_center_height = self._entity_center_z_m(entity, ground_height) - self._current_jump_pose_height_m(entity)
        corrected_center_z = max(float(body_position[2]), base_center_height)
        if corrected_center_z != float(body_position[2]):
            p.resetBasePositionAndOrientation(body_id, [body_position[0], body_position[1], corrected_center_z], body_orientation, physicsClientId=self.client)
            body_position = (body_position[0], body_position[1], corrected_center_z)
        airborne_height = max(0.0, corrected_center_z - base_center_height)
        _, _, yaw_deg = [math.degrees(value) for value in p.getEulerFromQuaternion(body_orientation)]
        entity.position['x'] = world_x
        entity.position['y'] = world_y
        entity.position['z'] = ground_height + airborne_height
        entity.angle = yaw_deg % 360.0
        commanded_planar_velocity = self._entity_commanded_planar_velocity_mps.get(entity.id)
        if commanded_planar_velocity is None:
            entity.velocity['vx'] = self._meters_to_world_units(float(linear_velocity[0]))
            entity.velocity['vy'] = self._meters_to_world_units(float(linear_velocity[1]))
        else:
            entity.velocity['vx'] = self._meters_to_world_units(float(commanded_planar_velocity[0]))
            entity.velocity['vy'] = self._meters_to_world_units(float(commanded_planar_velocity[1]))
        entity.velocity['vz'] = float(linear_velocity[2])
        entity.angular_velocity = math.degrees(float(angular_velocity[2]))
        entity.jump_airborne_height_m = airborne_height if getattr(entity, 'robot_type', '') == '步兵' else 0.0
        if airborne_height <= 1e-4:
            entity.jump_clearance_target_m = 0.0
            entity.step_climb_state = None if getattr(entity, 'step_climb_state', None) and getattr(entity, 'step_climb_state', {}).get('phase') == 'pybullet_step' else entity.step_climb_state
        entity.last_valid_position = dict(entity.position)
        entity.toppled = False
        entity.topple_pitch_deg = 0.0
        entity.topple_roll_deg = 0.0

    def _emit_collision_damage(self, entities, rules_engine):
        if rules_engine is None:
            return
        entity_lookup = {entity.id: entity for entity in entities}
        processed_pairs = set()
        for contact in p.getContactPoints(physicsClientId=self.client):
            body_a = int(contact[1])
            body_b = int(contact[2])
            entity_id_a = self._body_entity_ids.get(body_a)
            entity_id_b = self._body_entity_ids.get(body_b)
            if entity_id_a is None or entity_id_b is None or entity_id_a == entity_id_b:
                continue
            pair_key = tuple(sorted((entity_id_a, entity_id_b)))
            if pair_key in processed_pairs:
                continue
            processed_pairs.add(pair_key)
            entity_a = entity_lookup.get(entity_id_a)
            entity_b = entity_lookup.get(entity_id_b)
            if entity_a is None or entity_b is None or not entity_a.is_alive() or not entity_b.is_alive():
                continue
            velocity_a, _ = p.getBaseVelocity(body_a, physicsClientId=self.client)
            velocity_b, _ = p.getBaseVelocity(body_b, physicsClientId=self.client)
            commanded_a = self._entity_commanded_planar_velocity_mps.get(entity_id_a, (float(velocity_a[0]), float(velocity_a[1])))
            commanded_b = self._entity_commanded_planar_velocity_mps.get(entity_id_b, (float(velocity_b[0]), float(velocity_b[1])))
            relative_speed_mps = math.sqrt(
                (commanded_a[0] - commanded_b[0]) ** 2
                + (commanded_a[1] - commanded_b[1]) ** 2
                + (velocity_a[2] - velocity_b[2]) ** 2
            )
            if relative_speed_mps < self.contact_damage_speed_threshold_mps:
                continue
            rules_engine.handle_collision_damage(entity_a, entity_b, self._meters_to_world_units(relative_speed_mps))

    def simulate_ballistic_projectile(self, shooter, entities, rules_engine, target=None, aim_point=None, allow_ricochet=False):
        if shooter is None or rules_engine is None:
            return {'trace': None, 'hit_target': None, 'hit_point': None}
        map_manager = getattr(rules_engine, '_map_manager', lambda: None)()
        if aim_point is not None:
            preferred_pitch_deg = float(getattr(shooter, 'gimbal_pitch_deg', 0.0))
            start_point = rules_engine._shooter_muzzle_point(shooter, pitch_deg=preferred_pitch_deg)
            target_point = (
                float(aim_point.get('x', shooter.position['x'])),
                float(aim_point.get('y', shooter.position['y'])),
                float(aim_point.get('z', start_point[2])),
            )
            yaw_deg = math.degrees(math.atan2(target_point[1] - start_point[1], target_point[0] - start_point[0]))
            pitch_deg = preferred_pitch_deg
            for _ in range(2):
                pitch_deg = rules_engine._solve_ballistic_pitch_deg(
                    shooter,
                    start_point,
                    target_point,
                    preferred_pitch_deg=preferred_pitch_deg,
                )
                start_point = rules_engine._shooter_muzzle_point(shooter, pitch_deg=pitch_deg)
                yaw_deg = math.degrees(math.atan2(target_point[1] - start_point[1], target_point[0] - start_point[0]))
        else:
            yaw_deg = float(getattr(shooter, 'turret_angle', shooter.angle))
            pitch_deg = float(getattr(shooter, 'gimbal_pitch_deg', 0.0))
            start_point = rules_engine._shooter_muzzle_point(shooter, pitch_deg=pitch_deg)
        yaw_rad = math.radians(yaw_deg)
        pitch_rad = math.radians(pitch_deg)
        speed_mps = max(1e-6, rules_engine._projectile_speed_mps(getattr(shooter, 'ammo_type', '17mm')))
        velocity_m = [
            math.cos(pitch_rad) * math.cos(yaw_rad) * speed_mps,
            math.cos(pitch_rad) * math.sin(yaw_rad) * speed_mps,
            math.sin(pitch_rad) * speed_mps,
        ]
        current_point_m = list(rules_engine._metric_point_from_world(start_point))
        path_points = [start_point]
        max_range_m = self._world_units_to_meters(float(rules_engine.get_range(getattr(shooter, 'type', 'robot'))))
        simulation_dt = max(0.002, min(0.02, float(rules_engine.rules.get('shooting', {}).get('projectile_simulation_dt_sec', 0.01))))
        gravity = rules_engine._projectile_gravity_mps2()
        drag = max(0.0, rules_engine._projectile_drag_coefficient(getattr(shooter, 'ammo_type', '17mm')))
        hit_target = None
        hit_point = None
        traveled_m = 0.0
        bounce_count = 0
        speed_scale = 1.0
        while traveled_m < max_range_m:
            speed = math.sqrt(velocity_m[0] ** 2 + velocity_m[1] ** 2 + velocity_m[2] ** 2)
            if speed <= 1e-6:
                break
            dt = min(simulation_dt, max(0.002, 0.08 / max(speed, 1e-6)))
            accel_x = -drag * speed * velocity_m[0]
            accel_y = -drag * speed * velocity_m[1]
            accel_z = -gravity - drag * speed * velocity_m[2]
            next_point_m = (
                current_point_m[0] + velocity_m[0] * dt + 0.5 * accel_x * dt * dt,
                current_point_m[1] + velocity_m[1] * dt + 0.5 * accel_y * dt * dt,
                current_point_m[2] + velocity_m[2] * dt + 0.5 * accel_z * dt * dt,
            )
            next_velocity = (
                velocity_m[0] + accel_x * dt,
                velocity_m[1] + accel_y * dt,
                velocity_m[2] + accel_z * dt,
            )
            next_point_world = rules_engine._world_point_from_metric(next_point_m)
            candidate_target, candidate_hit_point = rules_engine._find_projectile_hit_target_metric_segment(
                shooter,
                tuple(current_point_m),
                next_point_m,
                entities,
                preferred_target=target,
            )
            if candidate_target is not None and candidate_hit_point is not None:
                hit_target = candidate_target
                hit_point = candidate_hit_point
                path_points.append(hit_point)
                break
            if map_manager is not None and rules_engine._projectile_hits_obstacle(next_point_world):
                path_points.append(next_point_world)
                if allow_ricochet and bounce_count == 0:
                    segment_distance_m = math.sqrt(
                        (next_point_m[0] - current_point_m[0]) ** 2
                        + (next_point_m[1] - current_point_m[1]) ** 2
                        + (next_point_m[2] - current_point_m[2]) ** 2
                    )
                    reflected = rules_engine._reflect_projectile_direction(path_points[-2], (velocity_m[0], velocity_m[1], velocity_m[2]), self._meters_to_world_units(speed * dt))
                    reflected_speed = max(0.1, math.sqrt(reflected[0] ** 2 + reflected[1] ** 2 + reflected[2] ** 2))
                    velocity_m = [
                        reflected[0] / reflected_speed * speed * 0.62,
                        reflected[1] / reflected_speed * speed * 0.62,
                        reflected[2] / reflected_speed * speed * 0.52,
                    ]
                    current_point_m = list(rules_engine._metric_point_from_world(next_point_world))
                    traveled_m += segment_distance_m
                    speed_scale *= 0.62
                    bounce_count += 1
                    continue
                break
            path_points.append(next_point_world)
            traveled_m += math.sqrt(
                (next_point_m[0] - current_point_m[0]) ** 2
                + (next_point_m[1] - current_point_m[1]) ** 2
                + (next_point_m[2] - current_point_m[2]) ** 2
            )
            current_point_m = [float(next_point_m[0]), float(next_point_m[1]), float(next_point_m[2])]
            velocity_m = [float(next_velocity[0]), float(next_velocity[1]), float(next_velocity[2])]
        trace_payload = rules_engine._build_projectile_trace_payload(shooter, path_points, speed_scale=speed_scale)
        return {'trace': trace_payload, 'hit_target': hit_target, 'hit_point': hit_point}

    def update(self, entities, map_manager, rules_engine=None, dt=None):
        if self.client is None:
            return
        sim_dt = float(dt if dt is not None else 1.0 / max(float(self.config.get('simulator', {}).get('fps', 50)), 1.0))
        self._ensure_terrain_body()
        self._remove_stale_bodies(entities)
        tracked = []
        for entity in entities:
            if not getattr(entity, 'collidable', True):
                continue
            body_id = self._ensure_entity_body(entity, map_manager)
            if body_id is None:
                continue
            tracked.append((entity, body_id))
            if not entity.is_alive() or not getattr(entity, 'movable', True):
                p.resetBaseVelocity(body_id, linearVelocity=[0.0, 0.0, 0.0], angularVelocity=[0.0, 0.0, 0.0], physicsClientId=self.client)
                continue
            self._apply_entity_drive(entity, body_id, map_manager, sim_dt)

        substep_count = max(1, int(math.ceil(sim_dt / max(self.fixed_time_step, 1e-6))))
        for _ in range(substep_count):
            p.stepSimulation(physicsClientId=self.client)

        for entity, body_id in tracked:
            self._sync_entity_from_body(entity, body_id, map_manager)

        self._emit_collision_damage(entities, rules_engine)