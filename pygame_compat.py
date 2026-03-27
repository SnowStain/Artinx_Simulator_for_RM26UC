#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pygame兼容性模块
兼容pygame-ce和标准pygame
"""

try:
    import pygame_ce as _pygame
except ImportError:
    try:
        import pygame as _pygame
    except ImportError:
        raise ImportError("请安装pygame或pygame-ce")

# 重新导出所有pygame模块
pygame = _pygame

# 确保所有常用的pygame常量和函数都可用
QUIT = pygame.QUIT
KEYDOWN = pygame.KEYDOWN
K_ESCAPE = pygame.K_ESCAPE
K_w = pygame.K_w
K_s = pygame.K_s
K_a = pygame.K_a
K_d = pygame.K_d
K_q = pygame.K_q
K_e = pygame.K_e
K_SPACE = pygame.K_SPACE
K_LSHIFT = pygame.K_LSHIFT
K_RSHIFT = pygame.K_RSHIFT
MOUSEBUTTONDOWN = pygame.MOUSEBUTTONDOWN
MOUSEBUTTONUP = pygame.MOUSEBUTTONUP

# 重新导出常用函数
init = pygame.init
quit = pygame.quit
display = pygame.display
draw = pygame.draw
font = pygame.font
event = pygame.event
key = pygame.key
mouse = pygame.mouse
image = pygame.image
transform = pygame.transform
Surface = pygame.Surface
Color = pygame.Color
Rect = pygame.Rect
