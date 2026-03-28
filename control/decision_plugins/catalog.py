#!/usr/bin/env python3
# -*- coding: utf-8 -*-

PLUGINS = {
    'return_to_supply_unlock': {
        'id': 'return_to_supply_unlock',
        'description': '哨兵前管锁定后返回补给区解锁。',
        'roles': {
            'sentry': {'order': 10, 'label': '回补解锁', 'condition_ref': 'front_gun_locked', 'action_ref': 'return_to_supply_unlock', 'default_destination_types': ('supply',)},
        },
    },
    'recover_after_respawn': {
        'id': 'recover_after_respawn',
        'description': '复活后先回补并恢复状态。',
        'roles': {
            'sentry': {'order': 20, 'label': '复活回补', 'condition_ref': 'recover_after_respawn', 'action_ref': 'recover_after_respawn', 'default_destination_types': ('supply',)},
            'infantry': {'order': 10, 'label': '复活回补', 'condition_ref': 'recover_after_respawn', 'action_ref': 'recover_after_respawn', 'default_destination_types': ('supply',)},
            'hero': {'order': 10, 'label': '复活回补', 'condition_ref': 'recover_after_respawn', 'action_ref': 'recover_after_respawn', 'default_destination_types': ('supply',)},
            'engineer': {'order': 10, 'label': '复活回补', 'condition_ref': 'recover_after_respawn', 'action_ref': 'recover_after_respawn', 'default_destination_types': ('supply',)},
        },
    },
    'emergency_retreat': {
        'id': 'emergency_retreat',
        'description': '在血量、热量或弹药不利时执行规避撤退。',
        'roles': {
            'sentry': {'order': 30, 'label': '紧急撤退', 'condition_ref': 'critical_state', 'action_ref': 'emergency_retreat', 'default_destination_types': ('supply', 'fort', 'base')},
            'infantry': {'order': 40, 'label': '紧急撤退', 'condition_ref': 'critical_state', 'action_ref': 'emergency_retreat', 'default_destination_types': ('supply', 'fort', 'base')},
            'engineer': {'order': 20, 'label': '紧急撤退', 'condition_ref': 'critical_state', 'action_ref': 'emergency_retreat', 'default_destination_types': ('supply', 'fort', 'base')},
        },
    },
    'sentry_opening_highground': {
        'id': 'sentry_opening_highground',
        'description': '哨兵开局先上一级台阶后转飞坡。',
        'roles': {
            'sentry': {'order': 40, 'label': '开局一级台阶飞坡', 'condition_ref': 'sentry_opening_highground', 'action_ref': 'sentry_opening_highground', 'default_destination_types': ('first_step',)},
        },
    },
    'sentry_fly_slope': {
        'id': 'sentry_fly_slope',
        'description': '哨兵对正飞坡并执行冲坡。',
        'roles': {
            'sentry': {'order': 50, 'label': '飞坡突入', 'condition_ref': 'sentry_fly_slope', 'action_ref': 'sentry_fly_slope', 'default_destination_types': ('fly_slope',)},
        },
    },
    'force_push_base': {
        'id': 'force_push_base',
        'description': '基地护盾解锁后优先推进基地。',
        'roles': {
            'sentry': {'order': 60, 'label': '推进基地', 'condition_ref': 'force_push_base', 'action_ref': 'push_base', 'default_destination_types': ('base',)},
            'infantry': {'order': 30, 'label': '推进基地', 'condition_ref': 'force_push_base', 'action_ref': 'push_base', 'default_destination_types': ('base',)},
            'hero': {'order': 30, 'label': '推进基地', 'condition_ref': 'force_push_base', 'action_ref': 'push_base', 'default_destination_types': ('base',)},
        },
    },
    'swarm_attack': {
        'id': 'swarm_attack',
        'description': '发现目标即转入战斗追击。',
        'roles': {
            'sentry': {'order': 70, 'label': '发现即集火', 'condition_ref': 'has_target', 'action_ref': 'swarm_attack'},
            'infantry': {'order': 70, 'label': '发现即集火', 'condition_ref': 'has_target', 'action_ref': 'swarm_attack'},
            'hero': {'order': 80, 'label': '发现即集火', 'condition_ref': 'has_target', 'action_ref': 'swarm_attack'},
        },
    },
    'protect_hero': {
        'id': 'protect_hero',
        'description': '哨兵为英雄提供贴身保护。',
        'roles': {
            'sentry': {'order': 80, 'label': '保护英雄', 'condition_ref': 'protect_hero', 'action_ref': 'protect_hero'},
        },
    },
    'highground_assault': {
        'id': 'highground_assault',
        'description': '围绕高地与前哨区域执行压制。',
        'roles': {
            'sentry': {'order': 90, 'label': '高地压制', 'condition_ref': 'take_enemy_highground', 'action_ref': 'highground_assault'},
            'infantry': {'order': 100, 'label': '高地压制前哨', 'condition_ref': 'take_enemy_highground', 'action_ref': 'highground_assault'},
            'hero': {'order': 70, 'label': '近战高地压制', 'condition_ref': 'hero_melee_highground_assault', 'action_ref': 'highground_assault'},
        },
    },
    'support_infantry_push': {
        'id': 'support_infantry_push',
        'description': '哨兵协同步兵推进。',
        'roles': {
            'sentry': {'order': 100, 'label': '配合步兵推进', 'condition_ref': 'support_infantry_push', 'action_ref': 'support_infantry_push'},
        },
    },
    'support_engineer': {
        'id': 'support_engineer',
        'description': '哨兵护送工程位。',
        'roles': {
            'sentry': {'order': 110, 'label': '护送工程', 'condition_ref': 'support_engineer', 'action_ref': 'support_engineer'},
        },
    },
    'intercept_enemy_engineer': {
        'id': 'intercept_enemy_engineer',
        'description': '优先拦截敌方工程。',
        'roles': {
            'sentry': {'order': 120, 'label': '拦截敌工', 'condition_ref': 'intercept_enemy_engineer', 'action_ref': 'intercept_enemy_engineer'},
            'infantry': {'order': 90, 'label': '拦截敌工', 'condition_ref': 'intercept_enemy_engineer', 'action_ref': 'intercept_enemy_engineer'},
        },
    },
    'push_outpost': {
        'id': 'push_outpost',
        'description': '推进敌方前哨站。',
        'roles': {
            'sentry': {'order': 130, 'label': '推进前哨站', 'condition_ref': 'push_outpost', 'action_ref': 'push_outpost', 'default_destination_types': ('outpost',)},
            'infantry': {'order': 110, 'label': '推进前哨站', 'condition_ref': 'push_outpost', 'action_ref': 'push_outpost', 'default_destination_types': ('outpost',)},
        },
    },
    'teamfight_cover': {
        'id': 'teamfight_cover',
        'description': '哨兵在团战窗口提供掩护。',
        'roles': {
            'sentry': {'order': 140, 'label': '团战掩护', 'condition_ref': 'teamfight_window', 'action_ref': 'teamfight_cover'},
        },
    },
    'push_base': {
        'id': 'push_base',
        'description': '常规推进基地。',
        'roles': {
            'sentry': {'order': 150, 'label': '推进基地', 'condition_ref': 'push_base', 'action_ref': 'push_base', 'default_destination_types': ('base',)},
            'infantry': {'order': 130, 'label': '推进基地', 'condition_ref': 'push_base', 'action_ref': 'push_base', 'default_destination_types': ('base',)},
            'hero': {'order': 150, 'label': '推进基地', 'condition_ref': 'push_base', 'action_ref': 'push_base', 'default_destination_types': ('base',)},
        },
    },
    'terrain_fly_slope': {
        'id': 'terrain_fly_slope',
        'description': '主动利用飞坡建立地形侧翼。',
        'roles': {
            'sentry': {'order': 160, 'label': '飞坡', 'condition_ref': 'terrain_fly_slope', 'action_ref': 'terrain_fly_slope', 'default_destination_types': ('fly_slope',), 'terrain_mode': 'fly_slope'},
            'infantry': {'order': 140, 'label': '飞坡', 'condition_ref': 'terrain_fly_slope', 'action_ref': 'terrain_fly_slope', 'default_destination_types': ('fly_slope',), 'terrain_mode': 'fly_slope'},
            'hero': {'order': 120, 'label': '飞坡', 'condition_ref': 'terrain_fly_slope', 'action_ref': 'terrain_fly_slope', 'default_destination_types': ('fly_slope',), 'terrain_mode': 'fly_slope'},
            'engineer': {'order': 50, 'label': '飞坡', 'condition_ref': 'terrain_fly_slope', 'action_ref': 'terrain_fly_slope', 'default_destination_types': ('fly_slope',), 'terrain_mode': 'fly_slope'},
        },
    },
    'terrain_first_step': {
        'id': 'terrain_first_step',
        'description': '主动翻越一级台阶切入。',
        'roles': {
            'sentry': {'order': 170, 'label': '翻越一级台阶', 'condition_ref': 'terrain_first_step', 'action_ref': 'terrain_first_step', 'default_destination_types': ('first_step',), 'terrain_mode': 'first_step'},
            'infantry': {'order': 150, 'label': '翻越一级台阶', 'condition_ref': 'terrain_first_step', 'action_ref': 'terrain_first_step', 'default_destination_types': ('first_step',), 'terrain_mode': 'first_step'},
            'hero': {'order': 130, 'label': '翻越一级台阶', 'condition_ref': 'terrain_first_step', 'action_ref': 'terrain_first_step', 'default_destination_types': ('first_step',), 'terrain_mode': 'first_step'},
            'engineer': {'order': 60, 'label': '翻越一级台阶', 'condition_ref': 'terrain_first_step', 'action_ref': 'terrain_first_step', 'default_destination_types': ('first_step',), 'terrain_mode': 'first_step'},
        },
    },
    'terrain_second_step': {
        'id': 'terrain_second_step',
        'description': '主动翻越二级台阶切入。',
        'roles': {
            'sentry': {'order': 180, 'label': '翻越二级台阶', 'condition_ref': 'terrain_second_step', 'action_ref': 'terrain_second_step', 'default_destination_types': ('second_step',), 'terrain_mode': 'second_step'},
            'infantry': {'order': 160, 'label': '翻越二级台阶', 'condition_ref': 'terrain_second_step', 'action_ref': 'terrain_second_step', 'default_destination_types': ('second_step',), 'terrain_mode': 'second_step'},
            'hero': {'order': 140, 'label': '翻越二级台阶', 'condition_ref': 'terrain_second_step', 'action_ref': 'terrain_second_step', 'default_destination_types': ('second_step',), 'terrain_mode': 'second_step'},
            'engineer': {'order': 70, 'label': '翻越二级台阶', 'condition_ref': 'terrain_second_step', 'action_ref': 'terrain_second_step', 'default_destination_types': ('second_step',), 'terrain_mode': 'second_step'},
        },
    },
    'patrol_key_facilities': {
        'id': 'patrol_key_facilities',
        'description': '当无高优先级行为时巡逻关键设施。',
        'roles': {
            'sentry': {'order': 190, 'label': '巡关键设施', 'condition_ref': '', 'action_ref': 'patrol_key_facilities', 'fallback': True},
            'infantry': {'order': 170, 'label': '巡关键设施', 'condition_ref': '', 'action_ref': 'patrol_key_facilities', 'fallback': True},
            'hero': {'order': 160, 'label': '巡关键设施', 'condition_ref': '', 'action_ref': 'patrol_key_facilities', 'fallback': True},
        },
    },
    'must_restock': {
        'id': 'must_restock',
        'description': '弹药耗尽时强制补给。',
        'roles': {
            'infantry': {'order': 20, 'label': '强制补给', 'condition_ref': 'must_restock', 'action_ref': 'opening_supply', 'default_destination_types': ('supply',)},
            'hero': {'order': 20, 'label': '强制补给', 'condition_ref': 'must_restock', 'action_ref': 'opening_supply', 'default_destination_types': ('supply',)},
        },
    },
    'opening_supply': {
        'id': 'opening_supply',
        'description': '常规进入补给区建立弹药储备。',
        'roles': {
            'infantry': {'order': 50, 'label': '常规补给', 'condition_ref': 'needs_supply', 'action_ref': 'opening_supply', 'default_destination_types': ('supply',)},
            'hero': {'order': 40, 'label': '常规补给', 'condition_ref': 'needs_supply', 'action_ref': 'opening_supply', 'default_destination_types': ('supply',)},
        },
    },
    'infantry_opening_highground': {
        'id': 'infantry_opening_highground',
        'description': '步兵开局抢高地增益。',
        'roles': {
            'infantry': {'order': 60, 'label': '开局抢高地增益', 'condition_ref': 'infantry_opening_highground', 'action_ref': 'infantry_opening_highground'},
        },
    },
    'activate_energy': {
        'id': 'activate_energy',
        'description': '前往中央能量机关激活位。',
        'roles': {
            'infantry': {'order': 80, 'label': '激活能量机关', 'condition_ref': 'activate_energy', 'action_ref': 'activate_energy', 'default_destination_types': ('energy_mechanism',)},
            'hero': {'order': 90, 'label': '激活能量机关', 'condition_ref': 'activate_energy', 'action_ref': 'activate_energy', 'default_destination_types': ('energy_mechanism',)},
        },
    },
    'teamfight_push': {
        'id': 'teamfight_push',
        'description': '步兵在团战窗口执行推进。',
        'roles': {
            'infantry': {'order': 120, 'label': '团战推进', 'condition_ref': 'teamfight_window', 'action_ref': 'teamfight_push'},
        },
    },
    'hero_seek_cover': {
        'id': 'hero_seek_cover',
        'description': '远程英雄寻找掩护位。',
        'roles': {
            'hero': {'order': 50, 'label': '英雄找掩护', 'condition_ref': 'hero_seek_cover', 'action_ref': 'hero_seek_cover'},
        },
    },
    'hero_opening_highground': {
        'id': 'hero_opening_highground',
        'description': '英雄开局进入高地部署/近战高地位。',
        'roles': {
            'hero': {'order': 60, 'label': '开局高地部署', 'condition_ref': 'hero_opening_highground', 'action_ref': 'hero_opening_highground'},
        },
    },
    'hero_lob_outpost': {
        'id': 'hero_lob_outpost',
        'description': '远程英雄吊射前哨站。',
        'roles': {
            'hero': {'order': 100, 'label': '吊射前哨站', 'condition_ref': 'hero_lob_outpost', 'action_ref': 'hero_lob_outpost', 'default_destination_types': ('second_step', 'fly_slope')},
        },
    },
    'hero_lob_base': {
        'id': 'hero_lob_base',
        'description': '远程英雄吊射基地。',
        'roles': {
            'hero': {'order': 110, 'label': '吊射基地', 'condition_ref': 'hero_lob_base', 'action_ref': 'hero_lob_base', 'default_destination_types': ('second_step', 'fly_slope')},
        },
    },
    'engineer_exchange': {
        'id': 'engineer_exchange',
        'description': '工程位回家兑矿。',
        'roles': {
            'engineer': {'order': 30, 'label': '回家兑矿', 'condition_ref': 'engineer_exchange', 'action_ref': 'engineer_exchange', 'default_destination_types': ('mineral_exchange',)},
        },
    },
    'engineer_mine': {
        'id': 'engineer_mine',
        'description': '工程位前往采矿。',
        'roles': {
            'engineer': {'order': 40, 'label': '前往采矿', 'condition_ref': 'engineer_mine', 'action_ref': 'engineer_mine', 'default_destination_types': ('mining_area',)},
        },
    },
    'engineer_cycle': {
        'id': 'engineer_cycle',
        'description': '工程位执行取矿兑矿循环。',
        'roles': {
            'engineer': {'order': 80, 'label': '取矿兑矿循环', 'condition_ref': '', 'action_ref': 'engineer_cycle', 'fallback': True},
        },
    },
}
