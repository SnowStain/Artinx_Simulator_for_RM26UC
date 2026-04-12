#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import math

from state_machine.actor_state_machine import ActorStateMachine


class SentryStateMachine(ActorStateMachine):
    def __init__(self):
        super().__init__()
        self.register_state_group(
            'chassis',
            {
                'normal': self.chassis_normal,
                'step_climbing': self.chassis_step_climbing,
                'jumping': self.chassis_jumping,
                'spin': self.chassis_spin,
                'fast_spin': self.chassis_fast_spin,
                'follow_turret': self.chassis_follow_turret,
            },
            'normal',
        )
        self.register_state_group(
            'turret',
            {
                'aiming': self.turret_aiming,
                'searching': self.turret_searching,
            },
            'searching',
        )
        self.register_state_group(
            'leg',
            {
                'balancing': self.leg_balancing,
            },
            'balancing',
        )
        self.register_state_group(
            'fire_control',
            {
                'idle': self.fire_control_idle,
                'firing': self.fire_control_firing,
            },
            'idle',
        )

    def update(self, sentry):
        self.update_group(sentry, 'chassis')
        self.update_group(sentry, 'turret')
        self.update_group(sentry, 'leg')
        self.update_group(sentry, 'fire_control')

    def chassis_normal(self, sentry):
        if sentry.target:
            sentry.chassis_state = 'follow_turret'

    def chassis_step_climbing(self, sentry):
        return

    def chassis_jumping(self, sentry):
        return

    def chassis_spin(self, sentry):
        sentry.angular_velocity = 90
        sentry.spin_timer = float(getattr(sentry, 'spin_timer', 0.0)) + 0.02
        if sentry.spin_timer > 2.0:
            sentry.spin_timer = 0.0
            sentry.chassis_state = 'normal'
            sentry.angular_velocity = 0.0

    def chassis_fast_spin(self, sentry):
        sentry.angular_velocity = 180
        sentry.fast_spin_timer = float(getattr(sentry, 'fast_spin_timer', 0.0)) + 0.02
        if sentry.fast_spin_timer > 1.0:
            sentry.fast_spin_timer = 0.0
            sentry.chassis_state = 'normal'
            sentry.angular_velocity = 0.0

    def chassis_follow_turret(self, sentry):
        if not sentry.target:
            sentry.chassis_state = 'normal'
            return
        target_angle = float(getattr(sentry, 'turret_angle', sentry.angle))
        angle_diff = ((target_angle - float(sentry.angle) + 180.0) % 360.0) - 180.0
        sentry.angular_velocity = angle_diff * 0.1

    def turret_aiming(self, sentry):
        if not sentry.target:
            sentry.turret_state = 'searching'
            return
        dx = float(sentry.target['x']) - float(sentry.position['x'])
        dy = float(sentry.target['y']) - float(sentry.position['y'])
        target_angle = math.degrees(math.atan2(dy, dx))
        current_angle = float(getattr(sentry, 'turret_angle', sentry.angle))
        angle_diff = ((target_angle - current_angle + 180.0) % 360.0) - 180.0
        track_speed = float(getattr(sentry, 'auto_aim_track_speed_deg_per_sec', 180.0)) * 0.02
        if abs(angle_diff) <= track_speed:
            sentry.turret_angle = target_angle
        else:
            sentry.turret_angle = current_angle + track_speed * (1 if angle_diff > 0 else -1)

    def turret_searching(self, sentry):
        current_angle = float(getattr(sentry, 'turret_angle', sentry.angle))
        sentry.turret_angle = (current_angle + float(getattr(sentry, 'search_angular_speed', 36.0)) * 0.02) % 360.0

    def leg_balancing(self, sentry):
        return

    def fire_control_idle(self, sentry):
        if getattr(sentry, 'auto_aim_locked', False) and sentry.target and sentry.target.get('distance', float('inf')) < getattr(sentry, 'auto_aim_limit', 800):
            sentry.fire_control_state = 'firing'

    def fire_control_firing(self, sentry):
        if not getattr(sentry, 'auto_aim_locked', False) or not sentry.target or sentry.target.get('distance', float('inf')) >= getattr(sentry, 'auto_aim_limit', 800):
            sentry.fire_control_state = 'idle'