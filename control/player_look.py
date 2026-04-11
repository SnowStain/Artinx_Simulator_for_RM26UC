#!/usr/bin/env python3
# -*- coding: utf-8 -*-

DEFAULT_PLAYER_MOUSE_INPUT = {
    'yaw_sensitivity_deg': 0.21,
    'pitch_sensitivity_deg': 0.005,
    'yaw_sign': 1.0,
    'pitch_sign': -1.0,
    'max_pitch_up_deg': 30.0,
    'max_pitch_down_deg': 30.0,
}


def _simulator_config(config):
    if not isinstance(config, dict):
        return {}
    simulator_config = config.get('simulator', {})
    return simulator_config if isinstance(simulator_config, dict) else {}


def _coerce_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_min(value, default, minimum=0.0):
    return max(float(minimum), _coerce_float(value, default))


def _coerce_sign(value, default):
    numeric = _coerce_float(value, default)
    return 1.0 if numeric >= 0.0 else -1.0


def get_player_mouse_input_settings(config):
    simulator_config = _simulator_config(config)
    unified = simulator_config.get('player_mouse_input', {})
    if not isinstance(unified, dict):
        unified = {}
    return {
        'yaw_sensitivity_deg': _coerce_min(
            unified.get('yaw_sensitivity_deg', simulator_config.get('player_look_sensitivity_deg', DEFAULT_PLAYER_MOUSE_INPUT['yaw_sensitivity_deg'])),
            DEFAULT_PLAYER_MOUSE_INPUT['yaw_sensitivity_deg'],
            minimum=0.01,
        ),
        'pitch_sensitivity_deg': _coerce_min(
            unified.get('pitch_sensitivity_deg', simulator_config.get('player_pitch_sensitivity_deg', DEFAULT_PLAYER_MOUSE_INPUT['pitch_sensitivity_deg'])),
            DEFAULT_PLAYER_MOUSE_INPUT['pitch_sensitivity_deg'],
            minimum=0.0001,
        ),
        'yaw_sign': _coerce_sign(unified.get('yaw_sign', DEFAULT_PLAYER_MOUSE_INPUT['yaw_sign']), DEFAULT_PLAYER_MOUSE_INPUT['yaw_sign']),
        'pitch_sign': _coerce_sign(unified.get('pitch_sign', DEFAULT_PLAYER_MOUSE_INPUT['pitch_sign']), DEFAULT_PLAYER_MOUSE_INPUT['pitch_sign']),
        'max_pitch_up_deg': _coerce_min(
            unified.get('max_pitch_up_deg', DEFAULT_PLAYER_MOUSE_INPUT['max_pitch_up_deg']),
            DEFAULT_PLAYER_MOUSE_INPUT['max_pitch_up_deg'],
        ),
        'max_pitch_down_deg': _coerce_min(
            unified.get('max_pitch_down_deg', DEFAULT_PLAYER_MOUSE_INPUT['max_pitch_down_deg']),
            DEFAULT_PLAYER_MOUSE_INPUT['max_pitch_down_deg'],
        ),
    }


def set_player_mouse_input_settings(
    config,
    yaw_sensitivity_deg=None,
    pitch_sensitivity_deg=None,
    yaw_sign=None,
    pitch_sign=None,
    max_pitch_up_deg=None,
    max_pitch_down_deg=None,
):
    if not isinstance(config, dict):
        return dict(DEFAULT_PLAYER_MOUSE_INPUT)
    simulator_config = config.setdefault('simulator', {})
    current = get_player_mouse_input_settings(config)
    updated = {
        'yaw_sensitivity_deg': current['yaw_sensitivity_deg'] if yaw_sensitivity_deg is None else _coerce_min(yaw_sensitivity_deg, current['yaw_sensitivity_deg'], minimum=0.01),
        'pitch_sensitivity_deg': current['pitch_sensitivity_deg'] if pitch_sensitivity_deg is None else _coerce_min(pitch_sensitivity_deg, current['pitch_sensitivity_deg'], minimum=0.0001),
        'yaw_sign': current['yaw_sign'] if yaw_sign is None else _coerce_sign(yaw_sign, current['yaw_sign']),
        'pitch_sign': current['pitch_sign'] if pitch_sign is None else _coerce_sign(pitch_sign, current['pitch_sign']),
        'max_pitch_up_deg': current['max_pitch_up_deg'] if max_pitch_up_deg is None else _coerce_min(max_pitch_up_deg, current['max_pitch_up_deg']),
        'max_pitch_down_deg': current['max_pitch_down_deg'] if max_pitch_down_deg is None else _coerce_min(max_pitch_down_deg, current['max_pitch_down_deg']),
    }
    simulator_config['player_mouse_input'] = dict(updated)
    simulator_config['player_look_sensitivity_deg'] = updated['yaw_sensitivity_deg']
    simulator_config['player_pitch_sensitivity_deg'] = updated['pitch_sensitivity_deg']
    return dict(updated)


def scale_player_mouse_motion(config, delta_x, delta_y):
    settings = get_player_mouse_input_settings(config)
    yaw_delta_deg = _coerce_float(delta_x, 0.0) * settings['yaw_sign'] * settings['yaw_sensitivity_deg']
    pitch_delta_deg = _coerce_float(delta_y, 0.0) * settings['pitch_sign'] * settings['pitch_sensitivity_deg']
    return yaw_delta_deg, pitch_delta_deg


def get_entity_pitch_limits(entity, config=None):
    settings = get_player_mouse_input_settings(config)
    configured_up = settings['max_pitch_up_deg']
    configured_down = settings['max_pitch_down_deg']
    entity_up = _coerce_min(getattr(entity, 'max_pitch_up_deg', configured_up), configured_up)
    entity_down = _coerce_min(getattr(entity, 'max_pitch_down_deg', configured_down), configured_down)
    return min(entity_up, configured_up), min(entity_down, configured_down)


def clamp_entity_pitch(entity, pitch_deg, config=None):
    max_up, max_down = get_entity_pitch_limits(entity, config=config)
    return max(-max_down, min(max_up, _coerce_float(pitch_deg, 0.0)))