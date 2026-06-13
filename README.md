# PC Locker

<div align="center">

**电脑屏幕锁定器** — 轻量级桌面锁屏工具

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-green.svg)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 功能特性

- **全屏锁定** — 无边框、置顶、覆盖任务栏，防止绕过
- **密码保护** — PBKDF2-HMAC-SHA256 加密存储（10万次迭代）
- **实时时钟** — 大号时间显示 + 日期/星期
- **快捷键拦截** — Alt+Tab / Alt+F4 / Escape 等全部拦截
- **鼠标禁用** — 锁定时禁止点击操作
- **Caps Lock 提示** — 自动检测大写锁定状态并警告
- **错误抖动动画** — 密码错误时输入框左右抖动反馈
- **失败锁定冷却** — 连续输错 N 次后延迟响应（防暴力破解）
- **自动锁定** — 超过设定时间无操作自动锁屏
- **密码强度指示** — 设置/修改时实时显示强度等级
- **轻量化** — 单文件 exe，约 11MB，内存占用极低

## 截图

> 首次启动设置向导 → 锁定界面

## 快速开始

### 方式一：直接运行源码

```bash
# 需要 Python 3.10+
python pc_locker.py
```

### 方式二：使用打包好的 exe

从 [Releases](../../releases) 下载 `PC-Locker.exe`，双击运行即可。

### 从源码打包 exe

```bash
# 安装依赖
pip install pyinstaller

# 打包为单文件 exe
pyinstaller --onefile --windowed --name PC-Locker pc_locker.py

# 生成的文件在 dist/ 目录下
```

## 使用方法

1. **首次运行** → 弹出初始设置向导，设置解锁密码（至少4位）
2. **进入锁定界面** → 全屏显示，输入密码按回车解锁
3. **配置文件** → 存储在 `%APPDATA%/PC-Locker/config.json`
   - 可修改密码、调整自动锁定超时、设置最大尝试次数等

## 技术实现

| 技术 | 用途 |
|------|------|
| `tkinter` | GUI 界面（Python 内置） |
| `ctypes` | Windows API 调用（窗口管理、全局钩子、空闲检测） |
| `hashlib.pbkdf2_hmac` | 密码哈希加密 |
| `PyInstaller` | 打包为独立 exe |

### 安全机制

- **全局低级钩子 (WH_KEYBOARD_LL / WH_MOUSE_LL)**：锁定状态下拦截所有键盘和鼠标事件
- **Windows API 强化窗口属性**：`WS_EX_TOPMOST` + `WS_POPUP` 确保窗口无法被遮挡或移走
- **PBKDF2 哈希 + 常量时间比较**：防止彩虹表攻击和时序攻击
- **失败次数限制 + 冷却延迟**：防止暴力枚举密码

## 项目结构

```
pc-locker/
├── pc_locker.py          # 主程序（单文件，约1100行）
├── .gitignore            # Git 忽略规则
├── README.md             # 项目说明文档
└── dist/                 # 打包产物（不提交到仓库）
    └── PC-Locker.exe     # 可执行文件
```

## 系统要求

- **操作系统**：Windows 10 / 11（64位）
- **Python 版本**：3.10+（仅源码运行需要）

## 开发计划

- [ ] 系统托盘图标与右键菜单
- [ ] 自定义快捷键绑定
- [ ] 开机自启动选项
- [ ] 多显示器支持
- [ ] 解锁成功/失败音效
- [ ] 背景自定义（图片/纯色）

## License

[MIT](LICENSE)

---

<div align="center">

Made with ❤️ by 乔一峰

</div>
