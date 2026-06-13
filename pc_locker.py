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
from datetime import datetime
from pathlib import Path

# ============== GUI ==============
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox, simpledialog

# ============== Windows API ==============
import ctypes
from ctypes import wintypes

# ==================== 常量 ====================

CONFIG_DIR = Path(os.environ.get("APPDATA", ".")) / "PC-Locker"
CONFIG_FILE = CONFIG_DIR / "config.json"
APP_NAME = "PC Locker"
VERSION = "1.0.0"

# 默认配置
DEFAULT_CONFIG = {
    "password_hash": "",
    "password_salt": "",
    "is_password_set": False,
    "auto_lock_timeout": 5,        # 分钟，0=永不
    "show_datetime": True,
    "max_failed_attempts": 5,
    "lockout_delay_seconds": 10,
}

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

# 空闲检测结构体（模块级定义）
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

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

        # 鼠标钩子回调
        def mouse_handler(nCode, wParam, lParam):
            if nCode >= 0 and self._active:
                # 锁定时禁用鼠标点击（但允许移动以显示光标）
                if wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                    return 1
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

    def show(self):
        """显示锁定窗口"""
        if self._visible:
            return

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg="#0a0e27")

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

        # 主容器 — 居中布局
        main_frame = tk.Frame(root, bg="#0a0e27")
        main_frame.place(relx=0.5, rely=0.5, anchor="center")

        # ----- 时间显示 -----
        time_frame = tk.Frame(main_frame, bg="#0a0e27")
        time_frame.pack(pady=(0, 40))

        self.time_label = tk.Label(
            time_frame,
            text="",
            font=("Consolas", 72, "bold"),
            fg="#00d4ff",
            bg="#0a0e27",
        )
        self.time_label.pack()

        self.date_label = tk.Label(
            time_frame,
            text="",
            font=("Microsoft YaHei UI", 14),
            fg="#99a3b4",
            bg="#0a0e27",
        )
        self.date_label.pack(pady=(8, 0))

        # ----- 分隔线 -----
        separator = tk.Frame(main_frame, bg="#1a2a4a", height=1, width=300)
        separator.pack(pady=(10, 30))

        # ----- 密码输入区域（毛玻璃卡片效果）-----
        card_frame = tk.Frame(main_frame, bg="#111830", padx=40, pady=30)
        card_frame.pack()

        # 提示文字
        hint_label = tk.Label(
            card_frame,
            text="\u94fe \u63a5 \u5df2 \u9501 \u5b9a",
            font=("Microsoft YaHei UI", 13),
            fg="#808c9e",
            bg="#111830",
        )
        hint_label.pack(pady=(0, 15))

        # Caps Lock 警告提示
        self.caps_label = tk.Label(
            card_frame,
            text="\u5927\u5199\u9501\u5b9a\u5df2\u5f00\u542f",
            font=("Microsoft YaHei UI", 11),
            fg="#ff9500",
            bg="#111830",
        )

        # 密码输入框
        pwd_frame = tk.Frame(card_frame, bg="#0d1225")
        pwd_frame.pack(fill="x")

        self.pwd_entry = tk.Entry(
            pwd_frame,
            font=("Consolas", 18),
            width=22,
            bg="#0d1225",
            fg="#ffffff",
            insertbackground="#00d4ff",
            relief="flat",
            show="\u25cf",
        )
        self.pwd_entry.pack(side="left", padx=(10, 0), pady=(10, 10), ipady=6)
        self.pwd_entry.bind("<Return>", self._on_submit)
        self.pwd_entry.bind("<KeyPress>", self._on_key_press)

        # 确认按钮
        self.submit_btn = tk.Button(
            pwd_frame,
            text="\u2192",
            font=("Consolas", 16, "bold"),
            bg="#00d4ff",
            fg="#0a0e27",
            activebackground="#00b8d9",
            activeforeground="#0a0e27",
            relief="flat",
            bd=0,
            cursor="hand2",
            width=3,
            command=self._on_submit,
        )
        self.submit_btn.pack(side="right", padx=(0, 10), pady=(10, 10), ipady=6, ipadx=4)

        # 状态消息
        self.status_label = tk.Label(
            card_frame,
            text="",
            font=("Microsoft YaHei UI", 11),
            bg="#111830",
        )
        self.status_label.pack(pady=(12, 0))

        # ----- 底部信息 -----
        bottom_label = tk.Label(
            main_frame,
            text=f"{APP_NAME} v{VERSION}",
            font=("Microsoft YaHei UI", 9),
            fg="#334050",
            bg="#0a0e27",
        )
        bottom_label.pack(pady=(40, 0))

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
                self.status_label.config(
                    text=f"\u8f93\u9519\u6b21\u6570\u8fc7\u591a\uff0c\u8bf7\u7b49\u5f85 {int(remaining)} \u79d2\u540e\u91cd\u8bd5",
                    fg="#ff4757",
                )
            else:
                self.is_locked_out = False
                self.status_label.config(text="", fg="#808c9e")

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
            self._set_status("\u8bf7\u8f93\u5165\u5bc6\u7801", "#ff9500")
            return

        # 调用后端验证
        valid = self.app.verify_password(password)

        if valid:
            # 解锁成功
            self._set_status("\u89e3\u9501\u6210\u529f", "#00ff88")
            self.root.after(300, self._on_unlock_success)
        else:
            self.failed_attempts += 1
            self._shake_input()
            max_attempts = self.app.config.get("max_failed_attempts", 5)
            delay = self.app.config.get("lockout_delay_seconds", 10)

            if self.failed_attempts >= max_attempts:
                self.is_locked_out = True
                self.lockout_end_time = time.time() + delay
                self._set_status(
                    f"\u5bc6\u7801\u9519\u8bef {self.failed_attempts} \u6b21\uff0c\u8bf7\u7b49\u5f85 {delay} \u79d2",
                    "#ff4757",
                )
                self.pwd_entry.delete(0, "end")
            else:
                remaining = max_attempts - self.failed_attempts
                self._set_status(
                    f"\u5bc6\u7801\u9519\u8bef\uff0c\u8fd8\u5269 {remaining} \u6b21\u673a\u4f1a",
                    "#ff4757",
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


# ==================== 设置窗口 ====================

class SettingsWindow:
    """设置面板窗口"""

    def __init__(self, app: "PCLockerApp"):
        self.app = app
        self.root: tk.Toplevel = None

    def show(self):
        """显示设置窗口"""
        if self.root:
            self.root.lift()
            self.root.focus_force()
            return

        self.root = tk.Toplevel()
        self.root.title(f"{APP_NAME} - \u8bbe\u7f6e")
        self.root.geometry("480x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f1525")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 居中显示
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 480, 520
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        root = self.root

        # 标题栏
        title_bar = tk.Frame(root, bg="#151d35", height=45)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        title_lbl = tk.Label(
            title_bar,
            text=f"  \u2699  {APP_NAME} \u8bbe\u7f6e",
            font=("Microsoft YaHei UI", 13, "bold"),
            fg="#00d4ff",
            bg="#151d35",
            anchor="w",
        )
        title_lbl.pack(side="left", fill="both", expand=True, padx=10)

        close_btn = tk.Button(
            title_bar,
            text="\u2715",
            font=("Consolas", 10),
            fg="#808c9e",
            bg="#151d35",
            activebackground="#ff4757",
            activeforeground="white",
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_close,
        )
        close_btn.pack(side="right", padx=10)

        # 内容区
        content = tk.Frame(root, bg="#0f1525")
        content.pack(fill="both", expand=True, padx=25, pady=20)

        # ---- 密码修改区域 ----
        section_pwd = tk.Frame(content, bg="#0f1525")
        section_pwd.pack(fill="x", pady=(0, 20))

        sec_title = tk.Label(
            section_pwd,
            text="\ud83d\udd11 \u4fee\u6539\u5bc6\u7801",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#e0e6f0",
            bg="#0f1525",
            anchor="w",
        )
        sec_title.pack(fill="x", pady=(0, 10))

        # 当前密码
        tk.Label(section_pwd, text="\u5f53\u524d\u5bc6\u7801\uff08\u9996\u6b21\u8bbe\u7f6e\u53ef\u7559\u7a7a\uff09:",
                  font=("Microsoft YaHei UI", 10), fg="#99a3b4", bg="#0f1525").pack(anchor="w")
        self.old_pwd = tk.Entry(section_pwd, font=("Consolas", 12), width=38,
                                 bg="#151d35", fg="#fff", insertbackground="#00d4ff",
                                 relief="flat", show="\u25cf")
        self.old_pwd.pack(fill="x", ipady=6, pady=(4, 10))

        # 新密码
        tk.Label(section_pwd, text="\u65b0\u5bc6\u7801:", font=("Microsoft YaHei UI", 10),
                 fg="#99a3b4", bg="#0f1525").pack(anchor="w")
        self.new_pwd = tk.Entry(section_pwd, font=("Consolas", 12), width=38,
                                bg="#151d35", fg="#fff", insertbackground="#00d4ff",
                                relief="flat", show="\u25cf")
        self.new_pwd.pack(fill="x", ipady=6, pady=(4, 8))

        # 确认新密码
        tk.Label(section_pwd, text="\u786e\u8ba4\u65b0\u5bc6\u7801:", font=("Microsoft YaHei UI", 10),
                 fg="#99a3b4", bg="#0f1525").pack(anchor="w")
        self.confirm_pwd = tk.Entry(section_pwd, font=("Consolas", 12), width=38,
                                    bg="#151d35", fg="#fff", insertbackground="#00d4ff",
                                    relief="flat", show="\u25cf")
        self.confirm_pwd.pack(fill="x", ipady=6, pady=(4, 8))

        # 密码强度指示
        self.strength_bar_frame = tk.Frame(section_pwd, bg="#0f1525")
        self.strength_bar_frame.pack(fill="x", pady=(0, 4))
        self.strength_bars = []
        bar_colors = ["#2d1b1b", "#2d1b1b", "#2d1b1b", "#2d1b1b"]
        for i, color in enumerate(bar_colors):
            bar = tk.Frame(self.strength_bar_frame, bg=color, height=3)
            bar.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 2, 0))
            self.strength_bars.append(bar)
        self.strength_label = tk.Label(self.strength_bar_frame, text="", font=("Microsoft YaHei UI", 9),
                                       fg="#606878", bg="#0f1525")
        self.strength_label.pack(side="left", padx=(8, 0))
        self.new_pwd.bind("<KeyRelease>", self._check_strength)

        # 修改按钮
        btn_frame = tk.Frame(section_pwd, bg="#0f1525")
        btn_frame.pack(fill="x", pady=(12, 0))
        self.change_result = tk.Label(btn_frame, text="", font=("Microsoft YaHei UI", 10), bg="#0f1525")
        self.change_result.pack(side="left")
        change_btn = tk.Button(btn_frame, text="\uD83D\uDD11 \u4fee\u6539\u5bc6\u7801",
                               font=("Microsoft YaHei UI", 11, "bold"), bg="#00d4ff", fg="#0a0e27",
                               activebackground="#00b8d9", activeforeground="#0a0e27",
                               relief="flat", bd=0, cursor="hand2", padx=20, pady=6,
                               command=self._change_password)
        change_btn.pack(side="right")

        # ---- 分隔线 ----
        sep = tk.Frame(content, bg="#1a2540", height=1)
        sep.pack(fill="x", pady=15)

        # ---- 行为配置区域 ----
        section_cfg = tk.Frame(content, bg="#0f1525")
        section_cfg.pack(fill="x")

        cfg_title = tk.Label(section_cfg, text="\u2699 \u884c\u4e3a\u914d\u7f6e",
                             font=("Microsoft YaHei UI", 12, "bold"), fg="#e0e6f0", bg="#0f1525", anchor="w")
        cfg_title.pack(fill="x", pady=(0, 12))

        # 自动锁定超时
        timeout_row = tk.Frame(section_cfg, bg="#0f1525")
        timeout_row.pack(fill="x", pady=6)
        tk.Label(timeout_row, text="\u81ea\u52a8\u9501\u5b9a\u8d85\u65f6:",
                 font=("Microsoft YaHei UI", 10), fg="#b3bac8", bg="#0f1525").pack(side="left")
        self.timeout_var = tk.StringVar(value=str(self.app.config.get("auto_lock_timeout", 5)))
        timeout_options = ["\u4ece\u4e0d", "1 \u5206\u949f", "5 \u5206\u949f", "10 \u5206\u949f",
                          "15 \u5206\u949f", "30 \u5206\u949f", "60 \u5206\u949f"]
        timeout_values = ["0", "1", "5", "10", "15", "30", "60"]
        self.timeout_combo = ttk_combobox(timeout_row, textvariable=self.timeout_var,
                                          values=timeout_options, state="readonly", width=12)
        self.timeout_combo.pack(side="right")
        self.timeout_combo.bind("<<ComboboxSelected>>", self._on_timeout_change)

        # 安全选项
        security_row = tk.Frame(section_cfg, bg="#0f1525")
        security_row.pack(fill="x", pady=6)
        tk.Label(security_row, text="\u6700\u5927\u5141\u8bb8\u9519\u8bef\u6b21\u6570:",
                 font=("Microsoft YaHei UI", 10), fg="#b3bac8", bg="#0f1525").pack(side="left")
        self.attempts_var = tk.StringVar(value=str(self.app.config.get("max_failed_attempts", 5)))
        attempts_combo = ttk_combobox(security_row, textvariable=self.attempts_var,
                                      values=["3", "5", "8", "10"], state="readonly", width=8)
        attempts_combo.pack(side="right")
        attempts_combo.bind("<<ComboboxSelected>>", self._on_attempts_change)

    def _check_strength(self, event=None):
        """检查密码强度并更新指示条"""
        pwd = self.new_pwd.get()
        strength = 0
        if len(pwd) >= 6:
            strength += 1
        if len(pwd) >= 10:
            strength += 1
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd):
            strength += 1
        if any(c.isdigit() for c in pwd):
            strength += 1
        if any(not c.isalnum() for c in pwd):
            strength += 1
        strength = min(strength, 4)

        colors = ["#ff4757", "#ff9500", "#ffd000", "#00ff88"]
        labels = ["\u5f31", "\u4e00\u822c", "\u4e2d\u7b49", "\u5f3a"]
        for i, bar in enumerate(self.strength_bars):
            if i < strength:
                bar.config(bg=colors[strength - 1])
            else:
                bar.config(bg="#1a1520")
        if pwd:
            self.strength_label.config(text=labels[strength - 1] if strength > 0 else "", fg=colors[strength - 1])
        else:
            self.strength_label.config(text="", fg="#606878")

    def _change_password(self):
        """修改密码"""
        old = self.old_pwd.get().strip()
        new = self.new_pwd.get().strip()
        confirm = self.confirm_pwd.get().strip()

        if not new:
            self.change_result.config(text="\u8bf7\u8f93\u5165\u65b0\u5bc6\u7801", fg="#ff9500")
            return
        if len(new) < 4:
            self.change_result.config(text="\u5bc6\u7801\u957f\u5ea6\u81f3\u5c11 4 \u4f4d", fg="#ff9500")
            return
        if new != confirm:
            self.change_result.config(text="\u4e24\u6b21\u8f93\u5165\u4e0d\u4e00\u81f4", fg="#ff4757")
            return

        # 如果已设置过密码，验证旧密码
        if self.app.config.get("is_password_set", False):
            if old:
                if not self.app.verify_password(old):
                    self.change_result.config(text="\u5f53\u524d\u5bc6\u7801\u9519\u8bef", fg="#ff4757")
                    return
            else:
                self.change_result.config(text="\u8bf7\u8f93\u5165\u5f53\u524d\u5bc6\u7801", fg="#ff9500")
                return

        # 设置新密码
        success = self.app.set_new_password(new)
        if success:
            self.change_result.config(text="\u2705 \u5bc6\u7801\u4fee\u6539\u6210\u529f", fg="#00ff88")
            self.old_pwd.delete(0, "end")
            self.new_pwd.delete(0, "end")
            self.confirm_pwd.delete(0, "end")
        else:
            self.change_result.config(text="\u4fee\u6539\u5931\u8d25", fg="#ff4757")

    def _on_timeout_change(self, event=None):
        val = int(self.timeout_var.get().split()[0]) if self.timeout_var.get() != "\u4ece\u4e0d" else 0
        self.app.config.set("auto_lock_timeout", val)
        self.app._restart_idle_timer()

    def _on_attempts_change(self, event=None):
        val = int(self.attempts_var.get())
        self.app.config.set("max_failed_attempts", val)

    def _on_close(self):
        """关闭设置窗口"""
        if self.root:
            self.root.destroy()
            self.root = None


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
        self.root.configure(bg="#0a0e27")
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
        tk.Label(root, text="\uD83D\uDD10", font=("Segoe UI Emoji", 48), bg="#0a0e27").pack(pady=(30, 10))
        tk.Label(root, text=APP_NAME, font=("Microsoft YaHei UI", 24, "bold"), fg="#00d4ff", bg="#0a0e27").pack()
        tk.Label(root, text="\u9996\u6b21\u4f7f\u7528\uff0c\u8bf7\u8bbe\u7f6e\u60a8\u7684\u89e3\u9501\u5bc6\u7801",
                 font=("Microsoft YaHei UI", 11), fg="#808c9e", bg="#0a0e27").pack(pady=(8, 30))

        form = tk.Frame(root, bg="#111830", padx=35, pady=25)
        form.pack()

        # 新密码
        tk.Label(form, text="\u8bbe\u7f6e\u89e3\u9501\u5bc6\u7801", font=("Microsoft YaHei UI", 11),
                 fg="#b3bac8", bg="#111830").pack(anchor="w", pady=(0, 4))
        self.new_pwd = tk.Entry(form, font=("Consolas", 16), width=28,
                                bg="#0d1225", fg="#fff", insertbackground="#00d4ff",
                                relief="flat", show="\u25cf")
        self.new_pwd.pack(fill="x", ipady=8, pady=(0, 12))
        self.new_pwd.bind("<Return>", lambda e: self.confirm_pwd.focus_force())

        # 确认密码
        tk.Label(form, text="\u786e\u8ba4\u5bc6\u7801", font=("Microsoft YaHei UI", 11),
                 fg="#b3bac8", bg="#111830").pack(anchor="w", pady=(0, 4))
        self.confirm_pwd = tk.Entry(form, font=("Consolas", 16), width=28,
                                    bg="#0d1225", fg="#fff", insertbackground="#00d4ff",
                                    relief="flat", show="\u25cf")
        self.confirm_pwd.pack(fill="x", ipady=8, pady=(0, 8))
        self.confirm_pwd.bind("<Return>", lambda e: self._submit())

        # 强度指示
        self.strength_frame = tk.Frame(form, bg="#111830")
        self.strength_frame.pack(fill="x", pady=(0, 4))
        self.str_bars = []
        for i in range(4):
            bar = tk.Frame(self.strength_frame, bg="#1a1520", height=3)
            bar.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 2, 0))
            self.str_bars.append(bar)
        self.str_label = tk.Label(self.strength_frame, text="", font=("Microsoft YaHei UI", 9),
                                  fg="#606878", bg="#111830")
        self.str_label.pack(side="left", padx=(8, 0))
        self.new_pwd.bind("<KeyRelease>", self._update_strength)

        # 状态提示
        self.msg_label = tk.Label(form, text="", font=("Microsoft YaHei UI", 10), bg="#111830")
        self.msg_label.pack(pady=(10, 0))

        # 按钮
        btn = tk.Button(form, text="\u2705 \u5b8c\u6210\u8bbe\u7f6e",
                        font=("Microsoft YaHei UI", 12, "bold"), bg="#00d4ff", fg="#0a0e27",
                        activebackground="#00b8d9", activeforeground="#0a0e27",
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
        colors = ["#ff4757", "#ff9500", "#ffd000", "#00ff88"]
        labels = ["\u5f31", "\u4e00\u822c", "\u4e2d\u7b49", "\u5f3a"]
        for i, bar in enumerate(self.str_bars):
            bar.config(bg=colors[s - 1] if i < s else "#1a1520")
        self.str_label.config(text=labels[s - 1] if s > 0 and pwd else "", fg=colors[s - 1] if s > 0 and pwd else "#606878")

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
        """解锁成功后的回调"""
        self.lock_window = None
        # 解锁后重新开始空闲检测
        self._start_idle_timer()

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
        if self.lock_window is None or not getattr(self.lock_window, "_visible", False):
            self._show_lock()


# ==================== 入口 ====================

if __name__ == "__main__":
    app = PCLockerApp()
    app.start()
