#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC Locker - 电脑屏幕锁定器
使用 tkinter + ctypes 实现，PyInstaller 打包为独立 exe
"""

import os
import sys
import json
import time
import hashlib
import threading
import base64
import dataclasses
import copy
import shutil
from datetime import datetime
from pathlib import Path

# ============== GUI ==============
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, colorchooser, filedialog

# ============== Windows API ==============
import ctypes
from ctypes import wintypes

# ==================== 常量 ====================

CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "PC-Locker"
CONFIG_FILE = CONFIG_DIR / "config.json"
THEME_DIR = CONFIG_DIR / "themes"
APP_NAME = "PC Locker"
VERSION = "1.1.0"

# 默认配置
DEFAULT_CONFIG = {
    "password_hash": "",
    "password_salt": "",
    "is_password_set": False,
    "auto_lock_timeout": 5,        # 分钟，0=永不
    "show_datetime": True,
    "max_failed_attempts": 5,
    "lockout_delay_seconds": 10,
    "theme_name": "极简浅色",
}

# 内置主题字典
BUILTIN_THEMES = {
    "深空墨色": {
        "bg_main": "#0a0e27",
        "bg_card": "#111830",
        "bg_input": "#0d1225",
        "text_primary": "#e0e6f0",
        "text_secondary": "#99a3b4",
        "text_hint": "#808c9e",
        "accent": "#00d4ff",
        "accent_hover": "#00b8d9",
        "separator": "#1a2a4a",
        "error": "#ff4757",
        "warning": "#ff9500",
        "success": "#00ff88",
        "bottom_text": "#334050",
        "font_size_time": 72,
        "clock_position": "center",
        "settings_bg": "#0f1525",
        "settings_title_bg": "#151d35",
        "settings_input_bg": "#151d35",
        "settings_border": "#1a2540",
        "background_image": "",
    },
    "极简浅色": {
        "bg_main": "#f5f7fa",
        "bg_card": "#ffffff",
        "bg_input": "#f0f2f5",
        "text_primary": "#1a1a2e",
        "text_secondary": "#555c68",
        "text_hint": "#8892a0",
        "accent": "#007aff",
        "accent_hover": "#005ecb",
        "separator": "#dde0e6",
        "error": "#ff3b30",
        "warning": "#ff9500",
        "success": "#34c759",
        "bottom_text": "#b0b8c4",
        "font_size_time": 72,
        "clock_position": "center",
        "settings_bg": "#f0f2f5",
        "settings_title_bg": "#ffffff",
        "settings_input_bg": "#f5f7fa",
        "settings_border": "#dde0e6",
        "background_image": "",
    },
    "冰岛蓝调": {
        "bg_main": "#0d1b2a",
        "bg_card": "#1b2838",
        "bg_input": "#141f2d",
        "text_primary": "#e0e8f0",
        "text_secondary": "#8fa4bc",
        "text_hint": "#6b8599",
        "accent": "#48cae4",
        "accent_hover": "#38afd4",
        "separator": "#243b54",
        "error": "#e63946",
        "warning": "#f4a261",
        "success": "#2a9d8f",
        "bottom_text": "#2c4a63",
        "font_size_time": 72,
        "clock_position": "center",
        "settings_bg": "#111d2e",
        "settings_title_bg": "#162538",
        "settings_input_bg": "#1a2939",
        "settings_border": "#203550",
        "background_image": "",
    },
    "森林绿意": {
        "bg_main": "#0a1612",
        "bg_card": "#132620",
        "bg_input": "#0e1a16",
        "text_primary": "#d8e8df",
        "text_secondary": "#7da892",
        "text_hint": "#5a826e",
        "accent": "#52b788",
        "accent_hover": "#40916c",
        "separator": "#1e3d30",
        "error": "#e07a5f",
        "warning": "#f2cc8f",
        "success": "#81b29a",
        "bottom_text": "#1e4030",
        "font_size_time": 72,
        "clock_position": "center",
        "settings_bg": "#0d1914",
        "settings_title_bg": "#152822",
        "settings_input_bg": "#11201b",
        "settings_border": "#1d362c",
        "background_image": "",
    },
}

DEFAULT_THEME_NAME = "深空墨色"

# ==================== Windows API 定义 ====================

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# 窗口样式常量
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_MAXIMIZE = 0x01000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1

# 显示器相关
SM_CXSCREEN = 0
SM_CYSCREEN = 1
MONITOR_DEFAULTTOPRIMARY = 0x00000001

# 键盘状态
VK_CAPITAL = 0x14

# 电源状态
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x000000002

# 输入钩子相关
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
HC_ACTION = 0
LLKHF_ALTDOWN = 0x00000020
LLKHF_INJECTED = 0x00000010

# 需要拦截的逃逸键（虚拟键码）
BLOCKED_KEYS = {
    0x09: "Tab",       # Tab
    0x1B: "Escape",    # Escape
    0x12: "Alt",       # Alt (单独)
}

# 需要拦截的逃逸组合键（通过 Alt 检测）
BLOCKED_ALT_COMBOS = {
    0x09: "Alt+Tab",
    0xF4: "Alt+F4",
    0x73: "Alt+F3",
    0x74: "Alt+F4(2)",
    0xBB: "Alt+=",
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


LowLevelKeyboardProc = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(KBDLLHOOKSTRUCT),
)

LowLevelMouseProc = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.POINTER(MSLLHOOKSTRUCT),
)


# ==================== 密码加密服务 ====================

class PasswordService:
    """密码加密与验证服务（PBKDF2-HMAC-SHA256）"""

    ITERATIONS = 100000
    SALT_LENGTH = 16

    @staticmethod
    def generate_salt() -> str:
        """生成随机盐值"""
        return os.urandom(PasswordService.SALT_LENGTH).hex()

    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """对密码进行 PBKDF2 哈希"""
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            PasswordService.ITERATIONS,
        )
        return dk.hex()

    @staticmethod
    def verify_password(password: str, stored_hash: str, salt: str) -> bool:
        """验证密码是否正确（常量时间比较）"""
        new_hash = PasswordService.hash_password(password, salt)
        return hmac_compare(new_hash, stored_hash)


def hmac_compare(a: str, b: str) -> bool:
    """常量时间字符串比较，防止时序攻击"""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# ==================== 配置管理 ====================

class ConfigManager:
    """配置文件读写管理"""

    def __init__(self):
        self.config = dict(DEFAULT_CONFIG)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        THEME_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self):
        """加载配置文件"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # 合并默认值（防止字段缺失）
                for k, v in DEFAULT_CONFIG.items():
                    if k not in saved:
                        saved[k] = v
                self.config = saved
            except Exception:
                pass

    def save(self):
        """保存配置到文件"""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[错误] 保存配置失败: {e}")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value):
        self.config[key] = value
        self.save()

    def get_theme_name(self) -> str:
        """获取当前主题名称"""
        name = self.config.get("theme_name", DEFAULT_THEME_NAME)
        if name not in BUILTIN_THEMES:
            name = DEFAULT_THEME_NAME
        return name

    def get_theme(self) -> dict:
        """获取当前主题配置（返回副本）"""
        name = self.get_theme_name()
        base = copy.deepcopy(BUILTIN_THEMES.get(name, BUILTIN_THEMES[DEFAULT_THEME_NAME]))

        # 加载用户自定义覆盖（如果存在）
        custom_file = THEME_DIR / f"{name}.json"
        if custom_file.exists():
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    custom = json.load(f)
                base.update(custom)
            except Exception:
                pass
        return base

    def set_theme_name(self, name: str):
        """设置当前主题名称"""
        self.set("theme_name", name)

    def save_custom_theme(self, name: str, overrides: dict):
        """保存用户对某个主题的自定义修改"""
        THEME_DIR.mkdir(parents=True, exist_ok=True)
        custom_file = THEME_DIR / f"{name}.json"
        try:
            with open(custom_file, "w", encoding="utf-8") as f:
                json.dump(overrides, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[错误] 保存主题失败: {e}")


# ==================== 主题管理器 ====================

class ThemeManager:
    """主题应用管理 — 将主题配置应用到锁屏界面"""

    @staticmethod
    def apply_to_lock(lock_window: "LockWindow"):
        """将当前主题应用到 LockWindow 的各个组件"""
        theme = lock_window.app.config.get_theme()
        root = lock_window.root
        if not root:
            return

        bg = theme["bg_main"]
        root.configure(bg=bg)

        if hasattr(lock_window, 'main_frame') and lock_window.main_frame:
            lock_window.main_frame.configure(bg=bg)

        if hasattr(lock_window, 'time_frame') and lock_window.time_frame:
            lock_window.time_frame.configure(bg=bg)

        if hasattr(lock_window, 'time_label') and lock_window.time_label:
            font_size = theme.get("font_size_time", 72)
            lock_window.time_label.configure(
                fg=theme["accent"],
                bg=bg,
                font=("Consolas", font_size, "bold"),
            )

        if hasattr(lock_window, 'date_label') and lock_window.date_label:
            lock_window.date_label.configure(
                fg=theme["text_secondary"],
                bg=bg,
            )

        if hasattr(lock_window, 'separator') and lock_window.separator:
            lock_window.separator.configure(bg=theme["separator"])

        card_bg = theme["bg_card"]
        if hasattr(lock_window, 'card_frame') and lock_window.card_frame:
            lock_window.card_frame.configure(bg=card_bg)

        if hasattr(lock_window, 'hint_label') and lock_window.hint_label:
            lock_window.hint_label.configure(
                fg=theme["text_hint"],
                bg=card_bg,
            )

        if hasattr(lock_window, 'caps_label') and lock_window.caps_label:
            lock_window.caps_label.configure(
                fg=theme["warning"],
                bg=card_bg,
            )

        input_bg = theme["bg_input"]
        if hasattr(lock_window, 'pwd_frame') and lock_window.pwd_frame:
            lock_window.pwd_frame.configure(bg=input_bg)

        if hasattr(lock_window, 'pwd_entry') and lock_window.pwd_entry:
            lock_window.pwd_entry.configure(
                bg=input_bg,
                fg=theme["text_primary"],
                insertbackground=theme["accent"],
            )

        if hasattr(lock_window, 'submit_btn') and lock_window.submit_btn:
            lock_window.submit_btn.configure(
                bg=theme["accent"],
                fg=theme["bg_main"],
                activebackground=theme["accent_hover"],
                activeforeground=theme["bg_main"],
            )

        if hasattr(lock_window, 'status_label') and lock_window.status_label:
            lock_window.status_label.configure(bg=card_bg)

        if hasattr(lock_window, 'bottom_label') and lock_window.bottom_label:
            lock_window.bottom_label.configure(
                fg=theme["bottom_text"],
                bg=bg,
            )

        # 设置背景图片（如果有）
        ThemeManager._set_background_image(root, theme.get("background_image", ""))

    @staticmethod
    def _set_background_image(root: tk.Widget, image_path: str):
        """设置窗口背景图片"""
        if not image_path or not Path(image_path).exists():
            return
        try:
            from PIL import Image, ImageTk
            img = Image.open(image_path)
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            img = img.resize((sw, sh), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(root, image=photo)
            label.image = photo  # 保持引用防止被回收
            label.place(relx=0, rely=0, relwidth=1, relheight=1)
            label.lower()  # 放到最底层
        except Exception:
            pass  # PIL 未安装或图片加载失败时静默忽略


# ==================== 主题编辑器 ====================

class ThemeEditor:
    """iOS 风格主题编辑器"""

    def __init__(self, parent, app: "PCLockerApp"):
        self.parent = parent
        self.app = app
        self.root: tk.Toplevel = None
        self._preview_job = None
        self._current_overrides = {}

    def show(self):
        """显示主题编辑器窗口"""
        if self.root:
            self.root.lift()
            self.root.focus_force()
            return

        self.root = tk.Toplevel(self.parent)
        self.root.title("主题编辑")
        self.root.geometry("520x700")
        self.root.resizable(False, False)
        self.root.configure(bg="#1c1c1e")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.transient(self.parent)

        # 居中显示
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 520) // 2
        y = (sh - 700) // 2
        self.root.geometry(f"520x700+{x}+{y}")

        # 加载当前覆盖
        theme_name = self.app.config.get_theme_name()
        custom_file = THEME_DIR / f"{theme_name}.json"
        if custom_file.exists():
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    self._current_overrides = json.load(f)
            except Exception:
                self._current_overrides = {}
        else:
            self._current_overrides = {}

        self._build_ui()

    def _build_ui(self):
        root = self.root

        # 标题栏
        title_bar = tk.Frame(root, bg="#2c2c2e", height=48)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        title_lbl = tk.Label(
            title_bar,
            text="  \u2764\ufe0f  主题编辑",
            font=("Microsoft YaHei UI", 14, "bold"),
            fg="#ffffff",
            bg="#2c2c2e",
            anchor="w",
        )
        title_lbl.pack(side="left", fill="both", expand=True, padx=15)

        close_btn = tk.Button(
            title_bar,
            text="\u2715",
            font=("Consolas", 11),
            fg="#8e8e93",
            bg="#2c2c2e",
            activebackground="#ff3b30",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_close,
        )
        close_btn.pack(side="right", padx=12)

        # 可滚动内容区
        canvas = tk.Canvas(root, bg="#1c1c1e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1c1c1e")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=500)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0))
        scrollbar.pack(side="right", fill="y")

        content = scrollable_frame

        # ---- 预设主题选择 ----
        self._build_preset_section(content)

        # ---- 分隔线 ----
        tk.Frame(content, bg="#38383a", height=1).pack(fill="x", pady=18)

        # ---- 背景设置 ----
        self._build_background_section(content)

        # ---- 分隔线 ----
        tk.Frame(content, bg="#38383a", height=1).pack(fill="x", pady=18)

        # ---- 锁屏颜色设置 ----
        self._build_color_section(content)

        # ---- 分隔线 ----
        tk.Frame(content, bg="#38383a", height=1).pack(fill="x", pady=18)

        # ---- 字体大小设置 ----
        self._build_font_section(content)

        # ---- 分隔线 ----
        tk.Frame(content, bg="#38383a", height=1).pack(fill="x", pady=18)

        # ---- 时钟位置设置 ----
        self._build_clock_pos_section(content)

        # ---- 分隔线 ----
        tk.Frame(content, bg="#38383a", height=1).pack(fill="x", pady=18)

        # ---- 设置界面颜色设置 ----
        self._build_settings_color_section(content)

        # 底部按钮区
        btn_area = tk.Frame(root, bg="#1c1c1e")
        btn_area.pack(fill="x", padx=15, pady=(10, 15))
        reset_btn = tk.Button(
            btn_area,
            text="\ud83d\udd04 重置为默认",
            font=("Microsoft YaHei UI", 11),
            fg="#ff9500",
            bg="#2c2c2e",
            activebackground="#3a3a3c",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=16, pady=8,
            command=self._reset_to_default,
        )
        reset_btn.pack(side="left")
        save_btn = tk.Button(
            btn_area,
            text="\u2705 应用并保存",
            font=("Microsoft YaHei UI", 11, "bold"),
            fg="#ffffff",
            bg="#007aff",
            activebackground="#005ecb",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=20, pady=8,
            command=self._apply_and_save,
        )
        save_btn.pack(side="right")

    def _section_header(self, parent, title: str):
        """创建 iOS 风格分组标题"""
        lbl = tk.Label(
            parent,
            text=title.upper(),
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#8e8e93",
            bg="#1c1c1e",
            anchor="w",
        )
        lbl.pack(fill="x", pady=(0, 8))
        return lbl

    def _build_preset_section(self, content):
        """构建预设主题选择区域"""
        self._section_header(content, "预设主题")

        card = tk.Frame(content, bg="#2c2c2e", padx=14, pady=12)
        card.pack(fill="x", ipady=4)

        current_name = self.app.config.get_theme_name()
        for i, (theme_name, theme_data) in enumerate(BUILTIN_THEMES.items()):
            row = tk.Frame(card, bg="#2c2c2e")
            row.pack(fill="x", pady=4 if i > 0 else 0)

            # 颜色预览圆点
            preview = tk.Frame(row, width=28, height=28, bg=theme_data["accent"], cursor="hand2")
            preview.pack(side="left", padx=(0, 12))
            preview.bind("<Button-1>", lambda e, n=theme_name: self._select_preset(n))

            name_lbl = tk.Label(
                row,
                text=theme_name,
                font=("Microsoft YaHei UI", 13),
                fg="#ffffff",
                bg="#2c2c2e",
                anchor="w",
                cursor="hand2",
            )
            name_lbl.pack(side="left", fill="x", expand=True)
            name_lbl.bind("<Button-1>", lambda e, n=theme_name: self._select_preset(n))

            if theme_name == current_name:
                check = tk.Label(row, text="\u2713", font=("Consolas", 14, "bold"), fg="#34c759", bg="#2c2c2e")
                check.pack(side="right")

    def _select_preset(self, name: str):
        """选择预设主题"""
        self.app.config.set_theme_name(name)
        # 重新加载覆盖
        custom_file = THEME_DIR / f"{name}.json"
        if custom_file.exists():
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    self._current_overrides = json.load(f)
            except Exception:
                self._current_overrides = {}
        else:
            self._current_overrides = {}
        # 刷新编辑器界面
        if self.root:
            for child in self.root.winfo_children():
                if isinstance(child, tk.Canvas):
                    break
            else:
                return
            # 简单做法：关闭重新打开
            self._on_close()
            self.show()

    def _build_background_section(self, content):
        """构建背景图片设置区域"""
        self._section_header(content, "背景图片")

        card = tk.Frame(content, bg="#2c2c2e", padx=14, pady=12)
        card.pack(fill="x", ipady=4)

        row = tk.Frame(card, bg="#2c2c2e")
        row.pack(fill="x")
        tk.Label(
            row, text="背景图片路径", font=("Microsoft YaHei UI", 13),
            fg="#ffffff", bg="#2c2c2e", anchor="w"
        ).pack(side="left", fill="x", expand=True)

        theme = self.app.config.get_theme()
        current_img = self._current_overrides.get("background_image", theme.get("background_image", ""))

        browse_btn = tk.Button(
            row, text="选择...", font=("Microsoft YaHei UI", 10),
            fg="#007aff", bg="#3a3a3c", activebackground="#4a4a4c",
            relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
            command=self._browse_background,
        )
        browse_btn.pack(side="right")

        path_row = tk.Frame(card, bg="#2c2c2e")
        path_row.pack(fill="x", pady=(8, 0))
        self.bg_path_var = tk.StringVar(value=current_img[:50] + "..." if len(current_img) > 50 else current_img)
        tk.Label(
            path_row, textvariable=self.bg_path_var, font=("Consolas", 10),
            fg="#8e8e93", bg="#2c2c2e", anchor="w"
        ).pack(fill="x")

        clear_btn = tk.Button(
            card, text="清除背景图片", font=("Microsoft YaHei UI", 10),
            fg="#ff3b30", bg="#2c2c2e", activebackground="#3a3a3c",
            relief="flat", bd=0, cursor="hand2", padx=0, pady=4,
            command=self._clear_background,
        )
        clear_btn.pack(anchor="w", pady=(6, 0))

    def _browse_background(self):
        """浏览选择背景图片"""
        paths = filedialog.askopenfilenames(
            title="选择背景图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                ("所有文件", "*.*"),
            ],
        )
        if paths:
            self._current_overrides["background_image"] = paths[0]
            display = paths[0]
            if len(display) > 50:
                display = display[:47] + "..."
            self.bg_path_var.set(display)

    def _clear_background(self):
        """清除背景图片"""
        self._current_overrides["background_image"] = ""
        self.bg_path_var.set("(无)")

    def _build_color_section(self, content):
        """构建锁屏颜色设置区域"""
        self._section_header(content, "锁屏颜色")

        card = tk.Frame(content, bg="#2c2c2e", padx=14, pady=12)
        card.pack(fill="x", ipady=4)

        theme = self.app.config.get_theme()
        color_keys = [
            ("bg_main", "主背景色"),
            ("bg_card", "卡片背景色"),
            ("bg_input", "输入框背景色"),
            ("accent", "强调色"),
            ("text_primary", "主文字色"),
            ("text_secondary", "次要文字色"),
        ]

        self.color_vars = {}
        self.color_buttons = {}

        for key, label_text in color_keys:
            row = tk.Frame(card, bg="#2c2c2e")
            row.pack(fill="x", pady=5)

            tk.Label(
                row, text=label_text, font=("Microsoft YaHei UI", 12),
                fg="#ffffff", bg="#2c2c2e", anchor="w"
            ).pack(side="left")

            current_val = self._current_overrides.get(key, theme.get(key, "#ffffff"))
            color_btn = tk.Button(
                row, width=4, height=1, bg=current_val,
                activebackground=current_val, relief="flat", bd=1,
                cursor="hand2", command=lambda k=key: self._pick_color(k),
            )
            color_btn.pack(side="right", padx=(8, 0))
            self.color_buttons[key] = color_btn

            hex_lbl = tk.Label(
                row, text=current_val.upper(), font=("Consolas", 10),
                fg="#8e8e93", bg="#2c2c2e"
            )
            hex_lbl.pack(side="right")
            self.color_vars[key] = hex_lbl

    def _pick_color(self, key: str):
        """打开颜色选择器"""
        theme = self.app.config.get_theme()
        initial = self._current_overrides.get(key, theme.get(key, "#ffffff"))
        result = colorchooser.askcolor(initialcolor=initial, title=f"选择 {key} 颜色")
        if result[1]:
            color_hex = result[1].lower()
            self._current_overrides[key] = color_hex
            if key in self.color_buttons:
                self.color_buttons[key].configure(bg=color_hex, activebackground=color_hex)
            if key in self.color_vars:
                self.color_vars[key].configure(text=color_hex.upper())

    def _build_font_section(self, content):
        """构建字体大小设置区域"""
        self._section_header(content, "字体大小")

        card = tk.Frame(content, bg="#2c2c2e", padx=14, pady=12)
        card.pack(fill="x", ipady=4)

        row = tk.Frame(card, bg="#2c2c2e")
        row.pack(fill="x")
        tk.Label(
            row, text="时钟字体大小", font=("Microsoft YaHei UI", 13),
            fg="#ffffff", bg="#2c2c2e", anchor="w"
        ).pack(side="left", fill="x", expand=True)

        theme = self.app.config.get_theme()
        current_size = self._current_overrides.get("font_size_time", theme.get("font_size_time", 72))
        self.font_size_var = tk.IntVar(value=int(current_size))
        size_spin = tk.Spinbox(
            row, from_=36, to=120, increment=6,
            textvariable=self.font_size_var, width=6,
            font=("Consolas", 12), bg="#3a3a3c", fg="#ffffff",
            buttonbackground="#48484a", insertbackground="#007aff",
        )
        size_spin.pack(side="right")

    def _build_clock_pos_section(self, content):
        """构建时钟位置设置区域"""
        self._section_header(content, "时钟位置")

        card = tk.Frame(content, bg="#2c2c2e", padx=14, pady=12)
        card.pack(fill="x", ipady=4)

        theme = self.app.config.get_theme()
        current_pos = self._current_overrides.get("clock_position", theme.get("clock_position", "center"))
        self.clock_pos_var = tk.StringVar(value=current_pos)

        positions = [("居中", "center"), ("顶部", "top"), ("底部", "bottom")]
        for i, (label_text, val) in enumerate(positions):
            rb = tk.Radiobutton(
                card, text=label_text, variable=self.clock_pos_var, value=val,
                font=("Microsoft YaHei UI", 12), fg="#ffffff", bg="#2c2c2e",
                selectcolor="#007aff", activebackground="#2c2c2e",
                activeforeground="#ffffff",
            )
            rb.pack(anchor="w", pady=2)

    def _build_settings_color_section(self, content):
        """构建设置界面颜色设置区域"""
        self._section_header(content, "设置界面颜色")

        card = tk.Frame(content, bg="#2c2c2e", padx=14, pady=12)
        card.pack(fill="x", ipady=4)

        theme = self.app.config.get_theme()
        settings_keys = [
            ("settings_bg", "设置面板背景"),
            ("settings_title_bg", "标题栏背景"),
            ("settings_input_bg", "输入框背景"),
            ("settings_border", "边框/分隔线"),
        ]

        for key, label_text in settings_keys:
            row = tk.Frame(card, bg="#2c2c2e")
            row.pack(fill="x", pady=5)

            tk.Label(
                row, text=label_text, font=("Microsoft YaHei UI", 12),
                fg="#ffffff", bg="#2c2c2e", anchor="w"
            ).pack(side="left")

            current_val = self._current_overrides.get(key, theme.get(key, "#ffffff"))
            color_btn = tk.Button(
                row, width=4, height=1, bg=current_val,
                activebackground=current_val, relief="flat", bd=1,
                cursor="hand2", command=lambda k=key: self._pick_color(k),
            )
            color_btn.pack(side="right", padx=(8, 0))
            if key not in self.color_buttons:
                self.color_buttons[key] = color_btn

            hex_lbl = tk.Label(
                row, text=current_val.upper(), font=("Consolas", 10),
                fg="#8e8e93", bg="#2c2c2e"
            )
            hex_lbl.pack(side="right")
            if key not in self.color_vars:
                self.color_vars[key] = hex_lbl

    def _reset_to_default(self):
        """重置为默认主题"""
        theme_name = self.app.config.get_theme_name()
        custom_file = THEME_DIR / f"{theme_name}.json"
        if custom_file.exists():
            try:
                custom_file.unlink()
            except Exception:
                pass
        self._current_overrides = {}
        # 刷新界面
        self._on_close()
        self.show()

    def _apply_and_save(self):
        """应用更改并保存"""
        theme_name = self.app.config.get_theme_name()

        # 收集所有修改
        overrides = dict(self._current_overrides)

        # 字体大小
        if hasattr(self, 'font_size_var'):
            overrides["font_size_time"] = int(self.font_size_var.get())

        # 时钟位置
        if hasattr(self, 'clock_pos_var'):
            overrides["clock_position"] = self.clock_pos_var.get()

        # 保存自定义覆盖
        if overrides:
            self.app.config.save_custom_theme(theme_name, overrides)
        else:
            # 清除自定义文件以恢复纯内置主题
            custom_file = THEME_DIR / f"{theme_name}.json"
            if custom_file.exists():
                try:
                    custom_file.unlink()
                except Exception:
                    pass

        messagebox.showinfo("成功", "主题已保存！下次进入锁屏时生效。", parent=self.root)
        self._on_close()

    def _on_close(self):
        """关闭主题编辑器"""
        if self.root:
            self.root.destroy()
            self.root = None


# ==================== 全局键盘/鼠标钩子 ====================

class InputHookManager:
    """全局输入钩子管理器 — 在锁定状态下拦截所有按键和鼠标事件"""

    def __init__(self):
        self._keyboard_hook = None
        self._mouse_hook = None
        self._keyboard_proc = None
        self._mouse_proc = None
        self._active = False

    def install(self):
        """安装低级键盘和鼠标钩子"""
        if self._active:
            return

        # 键盘钩子回调
        def keyboard_handler(nCode, wParam, lParam):
            if nCode >= 0 and self._active:
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    kb = lParam.contents
                    flags = kb.flags
                    # 允许正常按键通过（用于密码输入）
                    # 但拦截 Alt+Tab、Alt+F4、Escape 等
                    is_alt_down = bool(flags & LLKHF_ALTDOWN)
                    vk = kb.vkCode
                    if is_alt_down and vk in BLOCKED_ALT_COMBOS:
                        return 1  # 吞掉这个按键
                    if not is_alt_down and vk in BLOCKED_KEYS:
                        return 1
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        # 鼠标钩子回调（仅记录，不拦截——全屏置顶窗口已阻止与其他应用交互）
        def mouse_handler(nCode, wParam, lParam):
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._keyboard_proc = LowLevelKeyboardProc(keyboard_handler)
        self._mouse_proc = LowLevelMouseProc(mouse_handler)

        self._keyboard_hook = user32.SetWindowsHookExA(
            WH_KEYBOARD_LL, self._keyboard_proc, kernel32.GetModuleHandleW(None), 0
        )
        self._mouse_hook = user32.SetWindowsHookExA(
            WH_MOUSE_LL, self._mouse_proc, kernel32.GetModuleHandleW(None), 0
        )
        self._active = True

        # 启动消息循环线程来处理钩子消息
        threading.Thread(target=self._message_loop, daemon=True).start()

    def _message_loop(self):
        """运行消息循环以保持钩子活跃"""
        msg = wintypes.MSG()
        while self._active:
            try:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            except Exception:
                break

    def uninstall(self):
        """卸载钩子"""
        self._active = False
        if self._keyboard_hook:
            user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None


# 全局钩子实例
input_hook = InputHookManager()


# ==================== 锁定窗口 ====================

class LockWindow:
    """全屏锁定窗口"""

    def __init__(self, app: "PCLockerApp"):
        self.app = app
        self.root: tk.Tk = None
        self.failed_attempts = 0
        self.is_locked_out = False
        self.lockout_end_time = 0
        self._clock_job = None
        self._visible = False

        # 主题化组件引用
        self.main_frame = None
        self.time_frame = None
        self.separator = None
        self.card_frame = None
        self.hint_label = None
        self.pwd_frame = None
        self.bottom_label = None

    def show(self):
        """显示锁定窗口"""
        if self._visible:
            return

        self.root = tk.Tk()
        self.root.title(APP_NAME)

        theme = self.app.config.get_theme()
        bg = theme["bg_main"]
        self.root.configure(bg=bg)

        # ====== 全屏无边框窗口设置 ======
        self.root.overrideredirect(True)           # 无标题栏
        self.root.attributes("-topmost", True)      # 置顶
        # 注意：overrideredirect 与 fullscreen 属性互斥，手动设置全屏尺寸
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")       # 手动铺满屏幕

        # 使用 Windows API 进一步强化窗口属性
        hwnd = self.root.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE | WS_MAXIMIZE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, exstyle | WS_EX_TOPMOST)
        user32.SetWindowPos(
            HWND_TOPMOST, hwnd, 0, 0, sw, sh,
            SWP_SHOWWINDOW
        )

        # 禁止窗口关闭
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        # 绑定 Escape（防止关闭）和其他快捷键
        self.root.bind("<Escape>", lambda e: "break")
        self.root.bind("<Alt-F4>", lambda e: "break")
        self.root.bind("<Alt-Tab>", lambda e: "break")

        # ====== 构建 UI ======
        self._build_ui()

        # ====== 安装输入钩子 ======
        input_hook.install()

        self._visible = True
        self.failed_attempts = 0
        self.is_locked_out = False

        # 启动时钟更新
        self._update_clock()

        # 聚焦密码框
        self._focus_password()
        self.root.mainloop()

    def hide(self):
        """隐藏锁定窗口"""
        if not self._visible:
            return

        # 卸载输入钩子
        input_hook.uninstall()

        self._visible = False
        if self._clock_job:
            self.root.after_cancel(self._clock_job)
        try:
            self.root.destroy()
        except Exception:
            pass
        self.root = None

    def _build_ui(self):
        """构建锁定界面 UI"""
        root = self.root
        theme = self.app.config.get_theme()
        bg = theme["bg_main"]

        # 主容器 — 居中布局
        self.main_frame = tk.Frame(root, bg=bg)
        clock_pos = theme.get("clock_position", "center")
        if clock_pos == "top":
            self.main_frame.place(relx=0.5, rely=0.15, anchor="center")
        elif clock_pos == "bottom":
            self.main_frame.place(relx=0.5, rely=0.85, anchor="center")
        else:
            self.main_frame.place(relx=0.5, rely=0.5, anchor="center")

        # ----- 时间显示 -----
        self.time_frame = tk.Frame(self.main_frame, bg=bg)
        self.time_frame.pack(pady=(0, 40))

        font_size = theme.get("font_size_time", 72)
        self.time_label = tk.Label(
            self.time_frame,
            text="",
            font=("Consolas", font_size, "bold"),
            fg=theme["accent"],
            bg=bg,
        )
        self.time_label.pack()

        self.date_label = tk.Label(
            self.time_frame,
            text="",
            font=("Microsoft YaHei UI", 14),
            fg=theme["text_secondary"],
            bg=bg,
        )
        self.date_label.pack(pady=(8, 0))

        # ----- 分隔线 -----
        self.separator = tk.Frame(self.main_frame, bg=theme["separator"], height=1, width=300)
        self.separator.pack(pady=(10, 30))

        # ----- 密码输入区域（毛玻璃卡片效果）-----
        card_bg = theme["bg_card"]
        self.card_frame = tk.Frame(self.main_frame, bg=card_bg, padx=40, pady=30)
        self.card_frame.pack()

        # 提示文字
        self.hint_label = tk.Label(
            self.card_frame,
            text="\u94fe \u63a5 \u5df2 \u9501 \u5b9a",
            font=("Microsoft YaHei UI", 13),
            fg=theme["text_hint"],
            bg=card_bg,
        )
        self.hint_label.pack(pady=(0, 15))

        # Caps Lock 警告提示
        self.caps_label = tk.Label(
            self.card_frame,
            text="\u5927\u5199\u9501\u5b9a\u5df2\u5f00\u542f",
            font=("Microsoft YaHei UI", 11),
            fg=theme["warning"],
            bg=card_bg,
        )

        # 密码输入框
        input_bg = theme["bg_input"]
        self.pwd_frame = tk.Frame(self.card_frame, bg=input_bg)
        self.pwd_frame.pack(fill="x")

        self.pwd_entry = tk.Entry(
            self.pwd_frame,
            font=("Consolas", 18),
            width=22,
            bg=input_bg,
            fg=theme["text_primary"],
            insertbackground=theme["accent"],
            relief="flat",
            show="\u25cf",
        )
        self.pwd_entry.pack(side="left", padx=(10, 0), pady=(10, 10), ipady=6)
        self.pwd_entry.bind("<Return>", self._on_submit)
        self.pwd_entry.bind("<KeyPress>", self._on_key_press)

        # 确认按钮
        self.submit_btn = tk.Button(
            self.pwd_frame,
            text="\u2192",
            font=("Consolas", 16, "bold"),
            bg=theme["accent"],
            fg=bg,
            activebackground=theme["accent_hover"],
            activeforeground=bg,
            relief="flat",
            bd=0,
            cursor="hand2",
            width=3,
            command=self._on_submit,
        )
        self.submit_btn.pack(side="right", padx=(0, 10), pady=(10, 10), ipady=6, ipadx=4)

        # 状态消息
        self.status_label = tk.Label(
            self.card_frame,
            text="",
            font=("Microsoft YaHei UI", 11),
            bg=card_bg,
        )
        self.status_label.pack(pady=(12, 0))

        # ----- 底部信息 -----
        self.bottom_label = tk.Label(
            self.main_frame,
            text=f"{APP_NAME} v{VERSION}",
            font=("Microsoft YaHei UI", 9),
            fg=theme["bottom_text"],
            bg=bg,
        )
        self.bottom_label.pack(pady=(40, 0))

        # ----- 设置按钮 -----
        self.settings_btn = tk.Button(
            self.main_frame,
            text="设置",
            font=("Microsoft YaHei UI", 9),
            fg=theme["bottom_text"],
            bg=bg,
            activebackground=theme["bg_card"],
            activeforeground=theme["text_primary"],
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_open_settings,
        )
        self.settings_btn.pack(pady=(4, 0))

    def _update_clock(self):
        """每秒更新时间显示"""
        if not self._visible or not self.root:
            return
        now = datetime.now()
        self.time_label.config(text=now.strftime("%H:%M:%S"))
        weekdays = ["\u661f\u671f\u4e00", "\u661f\u671f\u4e8c", "\u661f\u671f\u4e09",
                     "\u661f\u671f\u56db", "\u661f\u671f\u4e94", "\u661f\u671f\u516d", "\u661f\u671e\u65e5"]
        date_str = now.strftime(f"%Y\u5e74%m\u6708%d\u65e5  {weekdays[now.weekday()]}")
        self.date_label.config(text=date_str)

        # 更新 Caps Lock 状态
        caps_on = user32.GetKeyState(VK_CAPITAL) & 0x0001 != 0
        if caps_on:
            self.caps_label.pack(pady=(0, 8), before=self.pwd_entry.master)
        else:
            self.caps_label.pack_forget()

        # 更新锁定冷却倒计时
        if self.is_locked_out:
            remaining = max(0, self.lockout_end_time - time.time())
            if remaining > 0:
                theme = self.app.config.get_theme()
                self.status_label.config(
                    text=f"\u8f93\u9519\u6b21\u6570\u8fc7\u591a\uff0c\u8bf7\u7b49\u5f85 {int(remaining)} \u79d2\u540e\u91cd\u8bd5",
                    fg=theme["error"],
                )
            else:
                self.is_locked_out = False
                self.failed_attempts = 0
                theme = self.app.config.get_theme()
                self.status_label.config(text="", fg=theme["text_hint"])

        self._clock_job = self.root.after(1000, self._update_clock)

    def _on_key_press(self, event):
        """按键时检测 Caps Lock"""
        caps_on = user32.GetKeyState(VK_CAPITAL) & 0x0001 != 0
        if caps_on:
            self.caps_label.pack(pady=(0, 8), before=self.pwd_entry.master)
        else:
            self.caps_label.pack_forget()

    def _focus_password(self):
        """聚焦密码输入框"""
        if self.root and self._visible:
            self.pwd_entry.focus_force()
            self.pwd_entry.icursor("end")
            # 定期重新聚焦（防失焦）
            self.root.after(500, self._focus_password)

    def _on_submit(self, event=None):
        """提交密码验证"""
        if self.is_locked_out:
            remaining = max(0, self.lockout_end_time - time.time())
            if remaining > 0:
                return

        password = self.pwd_entry.get().strip()
        if not password:
            self._shake_input()
            theme = self.app.config.get_theme()
            self._set_status("\u8bf7\u8f93\u5165\u5bc6\u7801", theme["warning"])
            return

        # 调用后端验证
        valid = self.app.verify_password(password)

        if valid:
            # 解锁成功
            theme = self.app.config.get_theme()
            self._set_status("\u89e3\u9501\u6210\u529f", theme["success"])
            self.root.after(300, self._on_unlock_success)
        else:
            self.failed_attempts += 1
            self._shake_input()
            max_attempts = self.app.config.get("max_failed_attempts", 5)
            delay = self.app.config.get("lockout_delay_seconds", 10)
            theme = self.app.config.get_theme()

            if self.failed_attempts >= max_attempts:
                self.is_locked_out = True
                self.lockout_end_time = time.time() + delay
                self._set_status(
                    f"\u5bc6\u7801\u9519\u8bef {self.failed_attempts} \u6b21\uff0c\u8bf7\u7b49\u5f85 {delay} \u79d2",
                    theme["error"],
                )
                self.pwd_entry.delete(0, "end")
            else:
                remaining = max_attempts - self.failed_attempts
                self._set_status(
                    f"\u5bc6\u7801\u9519\u8bef\uff0c\u8fd8\u5269 {remaining} \u6b21\u673a\u4f1a",
                    theme["error"],
                )
                self.pwd_entry.delete(0, "end")

    def _shake_input(self):
        """输入框抖动动画（模拟左右晃动）"""
        if not self._visible or not self.root:
            return
        card = self.pwd_entry.master.master
        x = 0
        original_bg = card.cget("bg")
        card.config(bg="#1a1020")
        for offset in [8, -8, 6, -6, 4, -4, 2, -2, 0]:
            self.root.after(abs(offset) * 15 + x, lambda o=offset: card.place(relx=0.5 + o / 400, rely=0.5, anchor="center"))
            x += abs(offset) * 15 + 20
        self.root.after(x, lambda: (
            card.config(bg=original_bg) if hasattr(card, 'config') else None,
            card.place(relx=0.5, rely=0.5, anchor="center") if hasattr(card, 'place') else None
        ))

    def _set_status(self, text: str, color: str):
        """设置状态文字"""
        if self._visible and self.status_label:
            self.status_label.config(text=text, fg=color)

    def _on_unlock_success(self):
        """解锁成功回调"""
        self.hide()
        self.app.on_unlocked()

    def _on_open_settings(self):
        """从锁屏界面打开设置（需先在密码框输入解锁密码）"""
        theme = self.app.config.get_theme()
        password = self.pwd_entry.get().strip()

        if not password:
            self._set_status("请先在上方输入框输入密码", theme["warning"])
            return

        # 验证密码
        if not self.app.verify_password(password):
            self._shake_input()
            self._set_status("密码错误，无法打开设置", theme["error"])
            return

        # 验证通过，关闭锁屏 → 打开设置
        self._set_status("验证成功，正在打开设置...", theme["success"])
        self._do_open_settings()

    def _do_open_settings(self):
        """执行打开设置"""
        try:
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] 进入 _do_open_settings, 准备 hide\n")
            self.hide()
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] hide 完成, 准备调用 on_open_settings_from_lock\n")
            self.app.on_open_settings_from_lock()
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] on_open_settings_from_lock 返回\n")
        except Exception as e:
            import traceback
            traceback.print_exc()
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[ERROR] {traceback.format_exc()}\n")
            self.app._show_lock()


class PasswordDialog:
    """独立密码修改对话框"""

    def __init__(self, parent, app):
        self.app = app
        self.parent = parent
        self.root = None
        self.theme = app.config.get_theme()

    def show(self):
        self.root = tk.Toplevel(self.parent)
        self.root.title("修改密码")
        self.root.geometry("380x420")
        self.root.resizable(False, False)
        self.root.configure(bg=self.theme["settings_bg"])
        self.root.attributes("-topmost", True)
        self.root.grab_set()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 居中
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - 380) // 2
        y = (sh - 420) // 2
        self.root.geometry(f"380x420+{x}+{y}")

        t = self.theme
        # 标题栏
        title_bar = tk.Frame(self.root, bg=t["settings_title_bg"], height=40)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="  修改密码", font=("Microsoft YaHei UI", 12, "bold"),
                 fg=t["text_primary"], bg=t["settings_title_bg"], anchor="w").pack(side="left", fill="both", expand=True, padx=12)
        tk.Button(title_bar, text="\u2715", font=("Consolas", 10),
                  fg=t["text_secondary"], bg=t["settings_title_bg"],
                  activebackground="#ff4757", activeforeground="white",
                  relief="flat", bd=0, cursor="hand2", command=self._on_close).pack(side="right", padx=10)

        # 内容区
        body = tk.Frame(self.root, bg=t["settings_bg"], padx=24, pady=20)
        body.pack(fill="both", expand=True)

        is_set = self.app.config.get("is_password_set", False)

        if is_set:
            tk.Label(body, text="当前密码:", font=("Microsoft YaHei UI", 10),
                     fg=t["text_secondary"], bg=t["settings_bg"]).pack(anchor="w")
            self.old_pwd = tk.Entry(body, font=("Consolas", 13), width=34,
                                    bg=t["settings_input_bg"], fg=t["text_primary"],
                                    insertbackground=t["accent"], relief="flat", show="\u25cf")
            self.old_pwd.pack(fill="x", ipady=5, pady=(4, 14))

        tk.Label(body, text="新密码:", font=("Microsoft YaHei UI", 10),
                 fg=t["text_secondary"], bg=t["settings_bg"]).pack(anchor="w")
        self.new_pwd = tk.Entry(body, font=("Consolas", 13), width=34,
                                bg=t["settings_input_bg"], fg=t["text_primary"],
                                insertbackground=t["accent"], relief="flat", show="\u25cf")
        self.new_pwd.pack(fill="x", ipady=5, pady=(4, 10))

        tk.Label(body, text="确认新密码:", font=("Microsoft YaHei UI", 10),
                 fg=t["text_secondary"], bg=t["settings_bg"]).pack(anchor="w")
        self.confirm_pwd = tk.Entry(body, font=("Consolas", 13), width=34,
                                    bg=t["settings_input_bg"], fg=t["text_primary"],
                                    insertbackground=t["accent"], relief="flat", show="\u25cf")
        self.confirm_pwd.pack(fill="x", ipady=5, pady=(4, 10))

        # 强度条
        self.strength_frame = tk.Frame(body, bg=t["settings_bg"])
        self.strength_frame.pack(fill="x", pady=(0, 6))
        self.str_bars = []
        for i in range(4):
            bar = tk.Frame(self.strength_frame, bg=t["settings_border"], height=3)
            bar.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 2, 0))
            self.str_bars.append(bar)
        self.str_label = tk.Label(self.strength_frame, text="", font=("Microsoft YaHei UI", 9),
                                   fg=t["text_secondary"], bg=t["settings_bg"])
        self.str_label.pack(side="left", padx=(8, 0))
        self.new_pwd.bind("<KeyRelease>", self._update_strength)

        # 结果提示
        self.result_lbl = tk.Label(body, text="", font=("Microsoft YaHei UI", 10), bg=t["settings_bg"])
        self.result_lbl.pack(pady=(8, 10))

        # 确认按钮
        tk.Button(body, text="确认修改", font=("Microsoft YaHei UI", 11, "bold"),
                  bg=t["accent"], fg="#ffffff", activebackground=t["accent_hover"],
                  relief="flat", bd=0, cursor="hand2", padx=28, pady=7,
                  command=self._on_submit).pack(anchor="e")

        self.new_pwd.bind("<Return>", lambda e: self.confirm_pwd.focus_force())
        self.confirm_pwd.bind("<Return>", lambda e: self._on_submit())
        if is_set:
            self.old_pwd.focus_force()
        else:
            self.new_pwd.focus_force()
        self.root.wait_window()

    def _update_strength(self, event=None):
        pwd = self.new_pwd.get()
        s = 0
        if len(pwd) >= 6: s += 1
        if len(pwd) >= 10: s += 1
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd): s += 1
        if any(c.isdigit() for c in pwd): s += 1
        if any(not c.isalnum() for c in pwd): s += 1
        s = min(s, 4)
        colors = ["#ff4757", "#ff9500", "#ffd000", "#34c759"]
        labels = ["弱", "一般", "中等", "强"]
        t = self.theme
        for i, bar in enumerate(self.str_bars):
            bar.config(bg=colors[s - 1] if i < s else t["settings_border"])
        if pwd:
            self.str_label.config(text=labels[s - 1] if s > 0 else "", fg=colors[s - 1] if s > 0 else t["text_secondary"])
        else:
            self.str_label.config(text="", fg=t["text_secondary"])

    def _on_submit(self):
        new = self.new_pwd.get().strip()
        confirm = self.confirm_pwd.get().strip()
        if not new or len(new) < 4:
            self.result_lbl.config(text="密码至少 4 位", fg="#ff9500")
            return
        if new != confirm:
            self.result_lbl.config(text="两次输入不一致", fg="#ff4757")
            return
        is_set = self.app.config.get("is_password_set", False)
        if is_set:
            old = getattr(self, 'old_pwd', None)
            if old:
                old_val = old.get().strip()
                if not old_val:
                    self.result_lbl.config(text="请输入当前密码", fg="#ff9500"); return
                if not self.app.verify_password(old_val):
                    self.result_lbl.config(text="当前密码错误", fg="#ff4757"); return
        if self.app.set_new_password(new):
            self.result_lbl.config(text="密码修改成功", fg="#34c759")
            self.root.after(800, self._on_close)
        else:
            self.result_lbl.config(text="修改失败", fg="#ff4757")

    def _on_close(self):
        if self.root:
            self.root.destroy()
            self.root = None


# ==================== 设置窗口 ====================

class SettingsWindow:
    """设置面板窗口"""

    def __init__(self, app: "PCLockerApp"):
        self.app = app
        self.root: tk.Toplevel = None
        self._hidden_root = None
        # 必须初始化 self.theme，后续所有颜色引用都通过它
        self.theme = app.config.get_theme()

    def show(self):
        """显示设置窗口（阻塞等待关闭）"""
        try:
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] SettingsWindow.show() 开始\n")
        except Exception:
            pass
        if self.root:
            self.root.lift()
            self.root.focus_force()
            return

        # 创建一个隐藏的 Tk 根窗口作为 Toplevel 的父级
        self._hidden_root = tk.Tk()
        self._hidden_root.withdraw()  # 隐藏不显示

        self.root = tk.Toplevel(self._hidden_root)
        self.root.title(f"{APP_NAME} - 设置")
        self.root.geometry("480x600")
        self.root.resizable(False, False)
        self.root.configure(bg=self.theme["settings_bg"])
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 居中显示
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 480, 600
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()

        try:
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] SettingsWindow _build_ui 完成, 准备 mainloop\n")
        except Exception:
            pass

        # 用隐藏根窗口的 mainloop 阻塞等待关闭（不能用 Toplevel 的 mainloop）
        self._hidden_root.mainloop()

        try:
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] SettingsWindow mainloop 退出, show() 返回\n")
        except Exception:
            pass

    def _build_ui(self):
        root = self.root
        t = self.theme  # 使用 self.theme 的别名，确保全部走实例属性

        # 标题栏
        title_bar = tk.Frame(root, bg=t["settings_title_bg"], height=45)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        title_lbl = tk.Label(
            title_bar,
            text=f"  {APP_NAME} \u8bbe\u7f6e",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg=t["accent"],
            bg=t["settings_title_bg"],
            anchor="w",
        )
        title_lbl.pack(side="left", fill="both", expand=True, padx=10)

        close_btn = tk.Button(
            title_bar,
            text="\u2715",
            font=("Consolas", 10),
            fg=t["text_secondary"],
            bg=t["settings_title_bg"],
            activebackground=t["error"],
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_close,
        )
        close_btn.pack(side="right", padx=10)

        # 内容区
        content = tk.Frame(root, bg=t["settings_bg"])
        content.pack(fill="both", expand=True, padx=25, pady=20)

        # ---- 密码修改区域 ----
        section_pwd = tk.Frame(content, bg=t["settings_bg"])
        section_pwd.pack(fill="x", pady=(0, 20))

        sec_title = tk.Label(
            section_pwd,
            text="修改密码",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg=t["text_primary"],
            bg=t["settings_bg"],
            anchor="w",
        )
        sec_title.pack(fill="x", pady=(0, 10))

        change_btn = tk.Button(section_pwd, text="修改密码",
                               font=("Microsoft YaHei UI", 11), bg=t["accent"], fg="#ffffff",
                               activebackground=t["accent_hover"], activeforeground="#ffffff",
                               relief="flat", bd=0, cursor="hand2", padx=24, pady=8,
                               command=self._open_password_dialog)
        change_btn.pack(anchor="w")
        change_btn.pack(side="right")

        # ---- 分隔线 ----
        sep = tk.Frame(content, bg=t["settings_border"], height=1)
        sep.pack(fill="x", pady=15)

        # ---- 行为配置区域 ----
        section_cfg = tk.Frame(content, bg=t["settings_bg"])
        section_cfg.pack(fill="x")

        cfg_title = tk.Label(section_cfg, text="行为配置",
                             font=("Microsoft YaHei UI", 12, "bold"), fg=t["text_primary"], bg=t["settings_bg"], anchor="w")
        cfg_title.pack(fill="x", pady=(0, 12))

        # 自动锁定超时
        timeout_row = tk.Frame(section_cfg, bg=t["settings_bg"])
        timeout_row.pack(fill="x", pady=6)
        tk.Label(timeout_row, text="\u81ea\u52a8\u9501\u5b9a\u8d85\u65f6:",
                 font=("Microsoft YaHei UI", 10), fg="#b3bac8", bg=t["settings_bg"]).pack(side="left")
        self.timeout_var = tk.StringVar(value=str(self.app.config.get("auto_lock_timeout", 5)))
        timeout_options = ["\u4ece\u4e0d", "1 \u5206\u949f", "5 \u5206\u949f", "10 \u5206\u949f",
                          "15 \u5206\u949f", "30 \u5206\u949f", "60 \u5206\u949f"]
        timeout_values = ["0", "1", "5", "10", "15", "30", "60"]
        self.timeout_combo = ttk_combobox(timeout_row, textvariable=self.timeout_var,
                                          values=timeout_options, state="readonly", width=12)
        self.timeout_combo.pack(side="right")
        self.timeout_combo.bind("<<ComboboxSelected>>", self._on_timeout_change)

        # 安全选项
        security_row = tk.Frame(section_cfg, bg=t["settings_bg"])
        security_row.pack(fill="x", pady=6)
        tk.Label(security_row, text="\u6700\u5927\u5141\u8bb8\u9519\u8bef\u6b21\u6570:",
                 font=("Microsoft YaHei UI", 10), fg="#b3bac8", bg=t["settings_bg"]).pack(side="left")
        self.attempts_var = tk.StringVar(value=str(self.app.config.get("max_failed_attempts", 5)))
        attempts_combo = ttk_combobox(security_row, textvariable=self.attempts_var,
                                      values=["3", "5", "8", "10"], state="readonly", width=8)
        attempts_combo.pack(side="right")
        attempts_combo.bind("<<ComboboxSelected>>", self._on_attempts_change)

        # ---- 分隔线 ----
        sep2 = tk.Frame(content, bg=t["settings_border"], height=1)
        sep2.pack(fill="x", pady=15)

        # ---- 主题配置区域 ----
        section_theme = tk.Frame(content, bg=t["settings_bg"])
        section_theme.pack(fill="x")

        theme_title = tk.Label(section_theme, text="主题自定义",
                               font=("Microsoft YaHei UI", 12, "bold"), fg=t["text_primary"], bg=t["settings_bg"], anchor="w")
        theme_title.pack(fill="x", pady=(0, 12))

        # 当前主题显示
        theme_info_row = tk.Frame(section_theme, bg=t["settings_bg"])
        theme_info_row.pack(fill="x", pady=4)
        current_name = self.app.config.get_theme_name()
        tk.Label(theme_info_row, text="\u5f53\u524d\u4e3b\u9898:",
                 font=("Microsoft YaHei UI", 10), fg="#b3bac8", bg=t["settings_bg"]).pack(side="left")
        tk.Label(theme_info_row, text=current_name,
                 font=("Microsoft YaHei UI", 10, "bold"), fg=t["accent"], bg=t["settings_bg"]).pack(side="left", padx=(6, 0))

        # 编辑主题按钮
        edit_btn = tk.Button(section_theme, text="\u270f \u6253\u5f00\u4e3b\u9898\u7f16\u8f91\u5668",
                             font=("Microsoft YaHei UI", 11), fg=t["accent"], bg=t["settings_input_bg"],
                             activebackground=t["settings_border"], activeforeground=t["accent"],
                             relief="flat", bd=0, cursor="hand2", padx=16, pady=7,
                             command=self._open_theme_editor)
        edit_btn.pack(fill="x", pady=(10, 0))


    def _on_timeout_change(self, event=None):
        val = int(self.timeout_var.get().split()[0]) if self.timeout_var.get() != "\u4ece\u4e0d" else 0
        self.app.config.set("auto_lock_timeout", val)
        self.app._restart_idle_timer()

    def _on_attempts_change(self, event=None):
        val = int(self.attempts_var.get())
        self.app.config.set("max_failed_attempts", val)

    def _open_password_dialog(self):
        """打开密码修改对话框"""
        dlg = PasswordDialog(self.root, self.app)
        dlg.show()

    def _open_theme_editor(self):
        """打开主题编辑器"""
        editor = ThemeEditor(self.root, self.app)
        editor.show()

    def _on_close(self):
        """关闭设置窗口（同时销毁隐藏根窗口）"""
        if self.root:
            self.root.destroy()
            self.root = None
        if self._hidden_root:
            try:
                self._hidden_root.destroy()
            except Exception:
                pass
            self._hidden_root = None


def ttk_combobox(parent, **kwargs):
    """创建一个带样式的下拉选择框"""
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Custom.TCombobox",
                     fieldbackground="#151d35",
                     background="#1a2540",
                     foreground="#e0e6f0",
                     arrowcolor="#00d4ff",
                     borderwidth=0)
    combo = ttk.Combobox(parent, style="Custom.TCombobox", **kwargs)
    return combo


# ==================== 初始设置向导 ====================

class SetupWizard:
    """首次启动时的初始密码设置向导"""

    def __init__(self, app: "PCLockerApp"):
        self.app = app
        self.root: tk.Tk = None

    def run(self) -> bool:
        """运行设置向导，返回是否成功设置密码"""
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - \u521d\u59cb\u8bbe\u7f6e")
        self.root.geometry("420x480")
        self.root.resizable(False, False)
        self.theme = self.app.config.get_theme()
        self.root.configure(bg=self.theme["bg_main"])
        self.root.attributes("-topmost", True)

        # 居中
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - 420)//2}+{(sh - 480)//2}")

        self.result = False
        self._build_ui()
        self.root.mainloop()
        return self.result

    def _build_ui(self):
        root = self.root

        # 标题
        tk.Label(root, text=APP_NAME, font=("Microsoft YaHei UI", 24, "bold"), fg=self.theme["accent"], bg=self.theme["bg_main"]).pack()
        tk.Label(root, text="\u9996\u6b21\u4f7f\u7528\uff0c\u8bf7\u8bbe\u7f6e\u60a8\u7684\u89e3\u9501\u5bc6\u7801",
                 font=("Microsoft YaHei UI", 11), fg=self.theme["text_secondary"], bg=self.theme["bg_main"]).pack(pady=(8, 30))

        form = tk.Frame(root, bg=self.theme["bg_card"], padx=35, pady=25)
        form.pack()

        # 新密码
        tk.Label(form, text="\u8bbe\u7f6e\u89e3\u9501\u5bc6\u7801", font=("Microsoft YaHei UI", 11),
                 fg=self.theme["text_secondary"], bg=self.theme["bg_card"]).pack(anchor="w", pady=(0, 4))
        self.new_pwd = tk.Entry(form, font=("Consolas", 16), width=28,
                                bg=self.theme["bg_input"], fg=self.theme["text_primary"], insertbackground=self.theme["accent"],
                                relief="flat", show="\u25cf")
        self.new_pwd.pack(fill="x", ipady=8, pady=(0, 12))
        self.new_pwd.bind("<Return>", lambda e: self.confirm_pwd.focus_force())

        # 确认密码
        tk.Label(form, text="\u786e\u8ba4\u5bc6\u7801", font=("Microsoft YaHei UI", 11),
                 fg=self.theme["text_secondary"], bg=self.theme["bg_card"]).pack(anchor="w", pady=(0, 4))
        self.confirm_pwd = tk.Entry(form, font=("Consolas", 16), width=28,
                                    bg=self.theme["bg_input"], fg=self.theme["text_primary"], insertbackground=self.theme["accent"],
                                    relief="flat", show="\u25cf")
        self.confirm_pwd.pack(fill="x", ipady=8, pady=(0, 8))
        self.confirm_pwd.bind("<Return>", lambda e: self._submit())

        # 强度指示
        self.strength_frame = tk.Frame(form, bg=self.theme["bg_card"])
        self.strength_frame.pack(fill="x", pady=(0, 4))
        self.str_bars = []
        for i in range(4):
            bar = tk.Frame(self.strength_frame, bg=self.theme["settings_border"], height=3)
            bar.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 2, 0))
            self.str_bars.append(bar)
        self.str_label = tk.Label(self.strength_frame, text="", font=("Microsoft YaHei UI", 9),
                                  fg=self.theme["text_secondary"], bg=self.theme["bg_card"])
        self.str_label.pack(side="left", padx=(8, 0))
        self.new_pwd.bind("<KeyRelease>", self._update_strength)

        # 状态提示
        self.msg_label = tk.Label(form, text="", font=("Microsoft YaHei UI", 10), bg=self.theme["bg_card"])
        self.msg_label.pack(pady=(10, 0))

        # 按钮
        btn = tk.Button(form, text="完成设置",
                        font=("Microsoft YaHei UI", 12, "bold"), bg=self.theme["accent"], fg=self.theme["bg_main"],
                        activebackground=self.theme["accent_hover"], activeforeground=self.theme["bg_main"],
                        relief="flat", bd=0, cursor="hand2", padx=30, pady=8,
                        command=self._submit)
        btn.pack(pady=(15, 0))

        self.new_pwd.focus_force()

    def _update_strength(self, event=None):
        pwd = self.new_pwd.get()
        s = 0
        if len(pwd) >= 6: s += 1
        if len(pwd) >= 10: s += 1
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd): s += 1
        if any(c.isdigit() for c in pwd): s += 1
        if any(not c.isalnum() for c in pwd): s += 1
        s = min(s, 4)
        colors = ["#ff4757", "#ff9500", "#ffd000", "#34c759"]
        labels = ["弱", "一般", "中等", "强"]
        for i, bar in enumerate(self.str_bars):
            bar.config(bg=colors[s - 1] if i < s else self.theme["settings_border"])
        self.str_label.config(text=labels[s - 1] if s > 0 and pwd else "", fg=colors[s - 1] if s > 0 and pwd else self.theme["text_secondary"])

    def _submit(self):
        new = self.new_pwd.get().strip()
        confirm = self.confirm_pwd.get().strip()
        if not new or len(new) < 4:
            self.msg_label.config(text="\u5bc6\u7801\u81f3\u5c11 4 \u4f4d", fg="#ff9500")
            return
        if new != confirm:
            self.msg_label.config(text="\u4e24\u6b21\u8f93\u5165\u4e0d\u4e00\u81f4", fg="#ff4757")
            return
        if self.app.set_new_password(new):
            self.result = True
            self.root.destroy()
        else:
            self.msg_label.config(text="\u8bbe\u7f6e\u5931\u8d25", fg="#ff4757")


# ==================== 主应用 ====================

class PCLockerApp:
    """PC Locker 主应用程序"""

    def __init__(self):
        self.config = ConfigManager()
        self.lock_window: LockWindow = None
        self.settings_window: SettingsWindow = None
        self._idle_timer_thread = None
        self._idle_running = False

    def verify_password(self, password: str) -> bool:
        """验证密码"""
        if not self.config.get("is_password_set", False):
            return False
        stored_hash = self.config.get("password_hash", "")
        salt = self.config.get("password_salt", "")
        if not stored_hash or not salt:
            return False
        return PasswordService.verify_password(password, stored_hash, salt)

    def set_new_password(self, password: str) -> bool:
        """设置新密码"""
        try:
            salt = PasswordService.generate_salt()
            hash_val = PasswordService.hash_password(password, salt)
            self.config.set("password_hash", hash_val)
            self.config.set("password_salt", salt)
            self.config.set("is_password_set", True)
            return True
        except Exception as e:
            print(f"[错误] 设置密码失败: {e}")
            return False

    def start(self):
        """启动应用"""
        # 检查是否首次运行（未设置密码）
        if not self.config.get("is_password_set", False):
            wizard = SetupWizard(self)
            if not wizard.run():
                print("[信息] 未完成初始设置，退出")
                sys.exit(0)

        # 启动空闲检测计时器
        self._start_idle_timer()

        # 直接进入锁定界面
        self._show_lock()

    def _show_lock(self):
        """显示锁定界面"""
        self.lock_window = LockWindow(self)
        self.lock_window.show()

    def on_unlocked(self):
        """密码解锁成功后的回调：直接解锁，不弹设置"""
        self.lock_window = None

    def _show_settings(self):
        """显示设置窗口（阻塞等待）"""
        self.settings_window = SettingsWindow(self)
        self.settings_window.show()
        self.settings_window = None

    def on_open_settings_from_lock(self):
        """从锁屏界面打开设置：显示设置窗口，关闭后保持解锁状态（启动空闲检测）"""
        try:
            with open(os.path.join(CONFIG_DIR, "debug.log"), "a", encoding="utf-8") as f:
                f.write(f"[DEBUG] on_open_settings_from_lock 被调用\n")
        except Exception:
            pass
        self._show_settings()
        # 设置窗口关闭后，启动空闲检测，超时自动重新锁屏
        self._start_idle_timer()
        # 用隐藏 Tk 窗口保持进程存活，等待空闲计时器触发自动锁屏
        self._idle_wait_root = tk.Tk()
        self._idle_wait_root.withdraw()
        self._idle_wait_root.mainloop()

    def _start_idle_timer(self):
        """启动空闲检测计时器"""
        self._stop_idle_timer()
        self._idle_running = True
        self._idle_timer_thread = threading.Thread(target=self._idle_monitor_loop, daemon=True)
        self._idle_timer_thread.start()

    def _stop_idle_timer(self):
        """停止空闲检测计时器"""
        self._idle_running = False
        self._idle_timer_thread = None

    def _restart_idle_timer(self):
        """重启空闲检测计时器（配置变更后调用）"""
        self._start_idle_timer()

    def _idle_monitor_loop(self):
        """空闲检测监控循环"""
        while self._idle_running:
            try:
                timeout_minutes = self.config.get("auto_lock_timeout", 5)
                if timeout_minutes <= 0:
                    time.sleep(30)
                    continue

                # 获取系统空闲时间（毫秒）
                last_info = LASTINPUTINFO()
                last_info.cbSize = ctypes.sizeof(LASTINPUTINFO)
                if user32.GetLastInputInfo(ctypes.byref(last_info)):
                    idle_ms = kernel32.GetTickCount() - last_info.dwTime
                    idle_sec = idle_ms // 1000
                    timeout_sec = timeout_minutes * 60

                    if idle_sec >= timeout_sec and self._idle_running:
                        # 触发自动锁定
                        self._idle_running = False
                        self._trigger_auto_lock()
                        break
            except Exception:
                pass
            time.sleep(5)  # 每5秒检测一次

    def _trigger_auto_lock(self):
        """从空闲检测触发自动锁定（在守护线程中调用）"""
        # 先销毁空闲等待窗口（如果存在），避免两个 Tk 实例冲突
        if hasattr(self, '_idle_wait_root') and self._idle_wait_root:
            try:
                self._idle_wait_root.destroy()
                self._idle_wait_root = None
            except Exception:
                pass
        if self.lock_window is None or not getattr(self.lock_window, "_visible", False):
            self._show_lock()


# ==================== 入口 ====================

if __name__ == "__main__":
    app = PCLockerApp()
    app.start()
