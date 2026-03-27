#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import tkinter as tk
from tkinter import ttk


class DeveloperWindow:
    def __init__(self, game_engine, renderer):
        self.game_engine = game_engine
        self.renderer = renderer
        self.thread = None
        self.root = None
        self.status_var = None
        self.coord_var = None
        self.mode_var = None
        self.facility_var = None
        self.entity_var = None
        self.facility_listbox = None
        self.entity_listbox = None
        self._visible = True
        self._shutdown = False

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self._shutdown = True
        if self.root is not None:
            try:
                self.root.after(0, self.root.destroy)
            except RuntimeError:
                pass

    def toggle_visibility(self):
        self._visible = not self._visible
        if self.root is None:
            return

        def _apply():
            if self._visible:
                self.root.deiconify()
                self.root.lift()
            else:
                self.root.withdraw()

        self.root.after(0, _apply)

    def _run(self):
        self.root = tk.Tk()
        self.root.title('开发者工具')
        self.root.geometry('380x620')
        self.root.protocol('WM_DELETE_WINDOW', self.toggle_visibility)

        self.status_var = tk.StringVar(value='开发者工具已启动')
        self.coord_var = tk.StringVar(value='坐标: (-, -)')
        self.mode_var = tk.StringVar(value=self.renderer.editor_mode)
        self.facility_var = tk.StringVar(value=self.renderer.facility_types[self.renderer.selected_facility_type])
        self.entity_var = tk.StringVar(value=self._entity_label(self.renderer.selected_entity_index))

        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text='开发者工具', font=('Microsoft YaHei UI', 14, 'bold')).pack(anchor=tk.W)
        ttk.Label(container, textvariable=self.status_var, wraplength=340).pack(anchor=tk.W, pady=(6, 12))

        mode_frame = ttk.LabelFrame(container, text='编辑模式', padding=8)
        mode_frame.pack(fill=tk.X)
        ttk.Radiobutton(mode_frame, text='设施框选', value='facility', variable=self.mode_var, command=self._set_mode).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text='初始站位', value='entity', variable=self.mode_var, command=self._set_mode).pack(anchor=tk.W)

        facility_frame = ttk.LabelFrame(container, text='设施类型', padding=8)
        facility_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        self.facility_listbox = tk.Listbox(facility_frame, height=8, exportselection=False)
        for item in self.renderer.facility_types:
            self.facility_listbox.insert(tk.END, item)
        self.facility_listbox.selection_set(self.renderer.selected_facility_type)
        self.facility_listbox.bind('<<ListboxSelect>>', self._on_facility_select)
        self.facility_listbox.pack(fill=tk.X)

        entity_frame = ttk.LabelFrame(container, text='初始站位实体', padding=8)
        entity_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.entity_listbox = tk.Listbox(entity_frame, height=14, exportselection=False)
        for index in range(len(self.renderer.entity_keys)):
            self.entity_listbox.insert(tk.END, self._entity_label(index))
        if self.renderer.entity_keys:
            self.entity_listbox.selection_set(self.renderer.selected_entity_index)
        self.entity_listbox.bind('<<ListboxSelect>>', self._on_entity_select)
        self.entity_listbox.pack(fill=tk.BOTH, expand=True)

        action_frame = ttk.LabelFrame(container, text='动作', padding=8)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(action_frame, text='保存设施与站位', command=self._save_config).pack(fill=tk.X)
        ttk.Button(action_frame, text='保存当前对局', command=self._save_match).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(action_frame, text='载入当前对局', command=self._load_match).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(action_frame, text='暂停/继续', command=self.game_engine.toggle_pause).pack(fill=tk.X, pady=(6, 0))

        hint_frame = ttk.LabelFrame(container, text='主窗口操作', padding=8)
        hint_frame.pack(fill=tk.X, pady=(10, 0))
        hints = [
            '设施框选: 主窗口左键拖拽',
            '删除设施: 主窗口右键',
            '摆放站位: 主窗口左键点击',
            '旋转实体: 主窗口按 R',
            '显示/隐藏开发者窗: 主窗口按 F1',
        ]
        for hint in hints:
            ttk.Label(hint_frame, text=hint).pack(anchor=tk.W)

        ttk.Label(container, textvariable=self.coord_var).pack(anchor=tk.W, pady=(10, 0))

        self._poll_state()
        self.root.mainloop()

    def _entity_label(self, index):
        if not self.renderer.entity_keys:
            return '无实体'
        team, key = self.renderer.entity_keys[index]
        return f'{team}.{key}'

    def _set_mode(self):
        self.renderer.editor_mode = self.mode_var.get()
        self.status_var.set(f'已切换模式: {"设施框选" if self.renderer.editor_mode == "facility" else "初始站位"}')

    def _on_facility_select(self, _event):
        selection = self.facility_listbox.curselection()
        if not selection:
            return
        self.renderer.selected_facility_type = selection[0]
        self.facility_var.set(self.renderer.facility_types[selection[0]])
        self.status_var.set(f'当前设施类型: {self.facility_var.get()}')

    def _on_entity_select(self, _event):
        selection = self.entity_listbox.curselection()
        if not selection:
            return
        self.renderer.selected_entity_index = selection[0]
        self.entity_var.set(self._entity_label(selection[0]))
        self.status_var.set(f'当前实体: {self.entity_var.get()}')

    def _save_config(self):
        self.game_engine.save_editor_config()
        self.status_var.set('已保存设施与初始站位到 config.json')

    def _save_match(self):
        self.game_engine.save_match()
        self.status_var.set('已保存当前对局到 saves/latest_match.json')

    def _load_match(self):
        ok = self.game_engine.load_match()
        self.status_var.set('已载入当前对局' if ok else '载入失败，请检查存档文件')

    def _poll_state(self):
        if self._shutdown or self.root is None:
            return

        self.mode_var.set(self.renderer.editor_mode)
        if self.renderer.mouse_world is not None:
            self.coord_var.set(f'坐标: ({self.renderer.mouse_world[0]}, {self.renderer.mouse_world[1]})')
        else:
            self.coord_var.set('坐标: (-, -)')

        try:
            self.facility_listbox.selection_clear(0, tk.END)
            self.facility_listbox.selection_set(self.renderer.selected_facility_type)
            self.entity_listbox.selection_clear(0, tk.END)
            if self.renderer.entity_keys:
                self.entity_listbox.selection_set(self.renderer.selected_entity_index)
        except tk.TclError:
            return

        self.root.after(150, self._poll_state)