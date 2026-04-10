#!/usr/bin/env python3
# -*- coding: utf-8 -*-

class SentryStateMachine:
    def __init__(self):
        # 底盘状态
        self.chassis_states = {
            'normal': self.chassis_normal,
            'step_climbing': self.chassis_step_climbing,
            'jumping': self.chassis_jumping,
            'spin': self.chassis_spin,
            'fast_spin': self.chassis_fast_spin,
            'follow_turret': self.chassis_follow_turret
        }
        
        # 云台状态
        self.turret_states = {
            'aiming': self.turret_aiming,
            'searching': self.turret_searching
        }
        
        # 狗腿状态
        self.leg_states = {
            'balancing': self.leg_balancing
        }
        
        # 火控状态
        self.fire_control_states = {
            'idle': self.fire_control_idle,
            'firing': self.fire_control_firing
        }
    
    def update(self, sentry):
        """更新哨兵状态"""
        # 更新底盘状态
        self.update_chassis(sentry)
        
        # 更新云台状态
        self.update_turret(sentry)
        
        # 更新狗腿状态
        self.update_leg(sentry)
        
        # 更新火控状态
        self.update_fire_control(sentry)
    
    def update_chassis(self, sentry):
        """更新底盘状态"""
        if hasattr(sentry, 'chassis_state'):
            if sentry.chassis_state in self.chassis_states:
                self.chassis_states[sentry.chassis_state](sentry)
        else:
            sentry.chassis_state = 'normal'
    
    def chassis_normal(self, sentry):
        """正常行驶状态"""
        # 检查是否需要切换状态
        if sentry.target:
            sentry.chassis_state = 'follow_turret'
    
    def chassis_step_climbing(self, sentry):
        """上台阶状态"""
        # 台阶攀爬逻辑
        pass
    
    def chassis_jumping(self, sentry):
        """飞坡状态"""
        # 飞坡逻辑
        pass
    
    def chassis_spin(self, sentry):
        """小陀螺状态"""
        # 小陀螺逻辑
        sentry.angular_velocity = 90  # 90度/秒
        # 持续一段时间后恢复正常
        if not hasattr(sentry, 'spin_timer'):
            sentry.spin_timer = 0
        sentry.spin_timer += 0.02  # 假设dt=0.02
        if sentry.spin_timer > 2:  # 旋转2秒
            sentry.spin_timer = 0
            sentry.chassis_state = 'normal'
            sentry.angular_velocity = 0
    
    def chassis_fast_spin(self, sentry):
        """快速小陀螺状态"""
        # 快速小陀螺逻辑
        sentry.angular_velocity = 180  # 180度/秒
        # 持续一段时间后恢复正常
        if not hasattr(sentry, 'fast_spin_timer'):
            sentry.fast_spin_timer = 0
        sentry.fast_spin_timer += 0.02
        if sentry.fast_spin_timer > 1:  # 旋转1秒
            sentry.fast_spin_timer = 0
            sentry.chassis_state = 'normal'
            sentry.angular_velocity = 0
    
    def chassis_follow_turret(self, sentry):
        """底盘跟随云台状态"""
        # 底盘跟随云台逻辑
        if sentry.target:
            # 计算目标方向
            import math
            target_angle = getattr(sentry, 'turret_angle', sentry.angle)
            
            # 调整角度
            angle_diff = target_angle - sentry.angle
            if angle_diff > 180:
                angle_diff -= 360
            elif angle_diff< -180:
                angle_diff += 360
            
            sentry.angular_velocity = angle_diff * 0.1  # 平滑旋转
        else:
            sentry.chassis_state = 'normal'
    
    def update_turret(self, sentry):
        """更新云台状态"""
        if hasattr(sentry, 'turret_state'):
            if sentry.turret_state in self.turret_states:
                self.turret_states[sentry.turret_state](sentry)
        else:
            sentry.turret_state = 'searching'
    
    def turret_aiming(self, sentry):
        """自瞄状态"""
        # 自瞄逻辑
        if sentry.target:
            # 计算瞄准角度
            import math
            dx = sentry.target['x'] - sentry.position['x']
            dy = sentry.target['y'] - sentry.position['y']
            target_angle = math.degrees(math.atan2(dy, dx))
            
            # 平滑瞄准
            current_angle = getattr(sentry, 'turret_angle', sentry.angle)
            angle_diff = target_angle - current_angle
            if angle_diff > 180:
                angle_diff -= 360
            elif angle_diff < -180:
                angle_diff += 360

            track_speed = getattr(sentry, 'auto_aim_track_speed_deg_per_sec', 180.0) * 0.02
            if abs(angle_diff) <= track_speed:
                sentry.turret_angle = target_angle
            else:
                sentry.turret_angle = current_angle + track_speed * (1 if angle_diff > 0 else -1)
        else:
            sentry.turret_state = 'searching'
    
    def turret_searching(self, sentry):
        """索敌状态"""
        # 索敌逻辑
        current_angle = getattr(sentry, 'turret_angle', sentry.angle)
        sentry.turret_angle = (current_angle + getattr(sentry, 'search_angular_speed', 36.0) * 0.02) % 360
        # 如果找到目标，切换到自瞄状态
    
    def update_leg(self, sentry):
        """更新狗腿状态"""
        if hasattr(sentry, 'leg_state'):
            if sentry.leg_state in self.leg_states:
                self.leg_states[sentry.leg_state](sentry)
        else:
            sentry.leg_state = 'balancing'
    
    def leg_balancing(self, sentry):
        """平衡状态"""
        # 平衡逻辑
        pass
    
    def update_fire_control(self, sentry):
        """更新火控状态"""
        if hasattr(sentry, 'fire_control_state'):
            if sentry.fire_control_state in self.fire_control_states:
                self.fire_control_states[sentry.fire_control_state](sentry)
        else:
            sentry.fire_control_state = 'idle'
    
    def fire_control_idle(self, sentry):
        """待机状态（仅摩擦轮）"""
        # 检查是否有目标
        if getattr(sentry, 'auto_aim_locked', False) and sentry.target and sentry.target.get('distance', float('inf')) < getattr(sentry, 'auto_aim_limit', 800):
            sentry.fire_control_state = 'firing'
    
    def fire_control_firing(self, sentry):
        """发射状态"""
        # 发射逻辑
        if not getattr(sentry, 'auto_aim_locked', False) or not sentry.target or sentry.target.get('distance', float('inf')) >= getattr(sentry, 'auto_aim_limit', 800):
            sentry.fire_control_state = 'idle'
    
    def set_chassis_state(self, sentry, state):
        """设置底盘状态"""
        if state in self.chassis_states:
            sentry.chassis_state = state
    
    def set_turret_state(self, sentry, state):
        """设置云台状态"""
        if state in self.turret_states:
            sentry.turret_state = state
    
    def set_fire_control_state(self, sentry, state):
        """设置火控状态"""
        if state in self.fire_control_states:
            sentry.fire_control_state = state
