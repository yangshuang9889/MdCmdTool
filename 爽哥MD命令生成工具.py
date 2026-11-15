# -*- coding: utf-8 -*-
"""
爽哥MD编辑工具 (ShuaiGe Markdown Editor)
--------------------------------------------------
一款单文件 Windows 桌面工具，用于：
  1. 成批录入「命令 + 说明」，一键生成 Markdown 表格 / 代码清单 / 列表；
  2. 提供常用 Markdown 语法快捷插入按钮；
  3. 编辑区与实时预览区联动；
  4. 一键导出 .md 文件、一键复制到剪贴板；
  5. 设置窗口：黑白主题切换（整窗实时生效并持久化）、.md 文件关联。

制作人：杨爽
AI 工具：Marvis
反馈邮箱：675680672@qq.com

运行环境：Windows + Python 3.8+（仅依赖标准库 tkinter）
"""

import os
import re
import sys
import time
import ctypes
import json
import logging
import queue
import socket
import tempfile
import threading
import traceback
import unicodedata
import urllib.error
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox

try:  # 仅 Windows 提供 winreg；缺失时文件关联功能降级为不可用
    import winreg
except Exception:  # pragma: no cover
    winreg = None

# ---------------------------------------------------------------------------
# 常量信息
# ---------------------------------------------------------------------------
APP_NAME = "爽哥MD编辑工具"
APP_VERSION = "1.6.0"
AUTHOR = "杨爽"
AI_TOOL = "Marvis"
EMAIL = "675680672@qq.com"

FONT_CN = "Microsoft YaHei UI"
FONT_MONO = "Consolas"

# 随包资源名（与 exe 同级分发，同时打进 PyInstaller 包内）
ICON_MAIN_NAME = "app.ico"          # 主图标：exe / 主窗口 / 关于弹窗
ICON_MD_NAME = "md_file.ico"        # .md 文件关联图标
IMAGE_MAIN_NAME = "app_icon.png"    # 关于弹窗内展示用位图
DIRTY_TITLE_MARK = " *"             # 窗口标题未保存标记（v1.5.0）

# 在线检查更新（v1.6.0）：直接复用本项目的 GitHub 开源仓库 Releases 做版本比对，
# 不依赖任何第三方更新服务器，也不上传任何本机信息。
UPDATE_REPO = "yangshuang9889/MdCmdTool"
UPDATE_API_LATEST = "https://api.github.com/repos/%s/releases/latest" % UPDATE_REPO
UPDATE_PAGE = "https://github.com/%s/releases" % UPDATE_REPO
UPDATE_REPO_PAGE = "https://github.com/%s" % UPDATE_REPO
UPDATE_TIMEOUT = 8.0                # 单次请求超时（秒）
UPDATE_UA = "SgMdEditor/%s (+%s)" % (APP_VERSION, UPDATE_REPO_PAGE)

# ---------------------------------------------------------------------------
# 主题（黑 / 白）：所有界面配色集中在此表，切换时统一刷新，避免颜色散落硬编码
# ---------------------------------------------------------------------------
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_KEYS = (THEME_LIGHT, THEME_DARK)
THEME_LABELS = {THEME_LIGHT: "白色主题（默认）", THEME_DARK: "黑色主题"}

THEMES = {
    THEME_LIGHT: {
        "window_bg": "#f3f4f6",
        "panel_bg": "#ffffff",
        "text_bg": "#ffffff",
        "text_fg": "#1f2328",
        "insert_bg": "#1f2328",
        "select_bg": "#cfe4ff",
        "select_fg": "#1f2328",
        "toolbar_bg": "#f6f8fa",
        "statusbar_bg": "#eef1f4",
        "status_fg": "#424a53",
        "muted_fg": "#6e7781",
        "hint_fg": "#57606a",
        "border": "#d0d7de",
        "menu_bg": "#ffffff",
        "menu_fg": "#1f2328",
        "menu_active_bg": "#1f6feb",
        "menu_active_fg": "#ffffff",
        "header_bg": "#1f6feb",
        "header_fg": "#ffffff",
        "button_bg": "#f6f8fa",
        "button_fg": "#1f2328",
        "button_active_bg": "#e6ebf1",
        "field_bg": "#ffffff",
        "field_fg": "#1f2328",
        "sash_bg": "#d8dee4",
        "h1_fg": "#12263f",
        "h2_fg": "#1b3a57",
        "h3_fg": "#24506f",
        "h4_fg": "#2e5f77",
        "h5_fg": "#3a5568",
        "h6_fg": "#6b7c8c",
        "link_fg": "#1668dc",
        "code_inline_bg": "#eef1f4",
        "code_inline_fg": "#c7254e",
        "code_block_bg": "#f6f8fa",
        "code_block_fg": "#1f2328",
        "quote_bg": "#f5f9fc",
        "quote_fg": "#55677a",
        "table_bg": "#fbfcfe",
        "hr_fg": "#c9d1d9",
        "hint_tag_fg": "#9aa5b1",
    },
    THEME_DARK: {
        "window_bg": "#1b1f24",
        "panel_bg": "#22272e",
        "text_bg": "#22272e",
        "text_fg": "#d7dde3",
        "insert_bg": "#e6edf3",
        "select_bg": "#2f4a67",
        "select_fg": "#f0f6fc",
        "toolbar_bg": "#1f242b",
        "statusbar_bg": "#1b1f24",
        "status_fg": "#c3ccd6",
        "muted_fg": "#8b949e",
        "hint_fg": "#9aa7b4",
        "border": "#3a424c",
        "menu_bg": "#22272e",
        "menu_fg": "#d7dde3",
        "menu_active_bg": "#316dca",
        "menu_active_fg": "#ffffff",
        "header_bg": "#316dca",
        "header_fg": "#ffffff",
        "button_bg": "#2d333b",
        "button_fg": "#d7dde3",
        "button_active_bg": "#3a424c",
        "field_bg": "#22272e",
        "field_fg": "#d7dde3",
        "sash_bg": "#3a424c",
        "h1_fg": "#9ecbff",
        "h2_fg": "#8cc4f8",
        "h3_fg": "#7bb7f0",
        "h4_fg": "#9db8d2",
        "h5_fg": "#a8b9c9",
        "h6_fg": "#94a3b1",
        "link_fg": "#58a6ff",
        "code_inline_bg": "#2d333b",
        "code_inline_fg": "#ff9d8a",
        "code_block_bg": "#2b3138",
        "code_block_fg": "#d7dde3",
        "quote_bg": "#262c34",
        "quote_fg": "#a9b6c2",
        "table_bg": "#262c34",
        "hr_fg": "#4a545f",
        "hint_tag_fg": "#7d8590",
    },
}


def palette_of(name):
    """按名取调色板副本；未知主题一律回退白色主题。"""
    return dict(THEMES.get(name, THEMES[THEME_LIGHT]))


def _init_ttk_style(root, palette):
    """把 ttk 主题切到 clam（唯一能自由改背景色的内置主题）并按调色板重设样式。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=palette["panel_bg"])
    style.configure("Card.TFrame", background=palette["panel_bg"])
    style.configure("TLabel", background=palette["panel_bg"],
                    foreground=palette["text_fg"])
    style.configure("Card.TLabel", background=palette["panel_bg"],
                    foreground=palette["text_fg"])
    style.configure("TLabelframe", background=palette["panel_bg"],
                    bordercolor=palette["border"], relief="solid",
                    borderwidth=1)
    style.configure("TLabelframe.Label", background=palette["panel_bg"],
                    foreground=palette["text_fg"])
    style.configure("TButton", background=palette["button_bg"],
                    foreground=palette["button_fg"],
                    bordercolor=palette["border"], relief="raised",
                    focuscolor=palette["button_bg"])
    style.map("TButton",
              background=[("active", palette["button_active_bg"]),
                          ("pressed", palette["button_active_bg"]),
                          ("disabled", palette["window_bg"])],
              foreground=[("disabled", palette["muted_fg"])])
    style.configure("TCheckbutton", background=palette["window_bg"],
                    foreground=palette["text_fg"],
                    indicatorcolor=palette["field_bg"],
                    focuscolor=palette["window_bg"])
    style.map("TCheckbutton",
              background=[("active", palette["window_bg"])],
              foreground=[("disabled", palette["muted_fg"])])
    style.configure("Status.TCheckbutton", background=palette["statusbar_bg"],
                    foreground=palette["status_fg"],
                    indicatorcolor=palette["field_bg"],
                    focuscolor=palette["statusbar_bg"])
    style.map("Status.TCheckbutton",
              background=[("active", palette["statusbar_bg"])])
    style.configure("TRadiobutton", background=palette["panel_bg"],
                    foreground=palette["text_fg"],
                    indicatorcolor=palette["field_bg"],
                    focuscolor=palette["panel_bg"])
    style.map("TRadiobutton",
              background=[("active", palette["panel_bg"])])
    style.configure("TScrollbar", background=palette["button_bg"],
                    troughcolor=palette["window_bg"],
                    bordercolor=palette["border"],
                    arrowcolor=palette["muted_fg"],
                    relief="flat")
    style.map("TScrollbar",
              background=[("active", palette["button_active_bg"])])
    style.configure("TPanedwindow", background=palette["sash_bg"])
    style.configure("Sash", background=palette["sash_bg"], gripcount=0)
    style.configure("TSeparator", background=palette["border"])
    return style


def bind_colors(widget, palette, bg_key=None, fg_key=None):
    """给控件打上「调色板键」标记并立即上色；主题切换时由 apply_palette 统一刷新。"""
    if bg_key:
        widget._theme_bg = bg_key
    if fg_key:
        widget._theme_fg = fg_key
    try:
        if bg_key:
            widget.configure(background=palette[bg_key])
    except Exception:
        pass
    try:
        if fg_key:
            widget.configure(foreground=palette[fg_key])
    except Exception:
        pass
    return widget


def style_menu(menu, palette):
    """菜单（含级联子菜单）配色；Windows 下菜单栏着色需同时设 active* 项。"""
    try:
        menu.configure(background=palette["menu_bg"],
                       foreground=palette["menu_fg"],
                       activebackground=palette["menu_active_bg"],
                       activeforeground=palette["menu_active_fg"],
                       selectcolor=palette["menu_fg"],
                       borderwidth=0,
                       activeborderwidth=0)
    except Exception:
        pass
    return menu


def apply_palette(tree, palette):
    """递归刷新控件树内所有带主题标记的控件与菜单（主窗口 / 弹窗通用）。"""
    try:
        children = tree.winfo_children()
    except Exception:
        return
    for child in children:
        if isinstance(child, tk.Menu):
            style_menu(child, palette)
        else:
            bg = getattr(child, "_theme_bg", None)
            fg = getattr(child, "_theme_fg", None)
            if bg or fg:
                try:
                    if bg:
                        child.configure(background=palette[bg])
                    if fg:
                        child.configure(foreground=palette[fg])
                except Exception:
                    pass
        apply_palette(child, palette)


def _asset_path(name):
    """在 exe 同级目录与 PyInstaller 解包目录中查找随包资源，找不到返回空串。"""
    candidates = [os.path.join(_app_base_dir(), name)]
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        candidates.append(os.path.join(mei, name))
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _load_about_logo(max_size=44):
    """加载关于弹窗展示用的小图标（纯 tk 实现，不依赖 Pillow）。"""
    path = _asset_path(IMAGE_MAIN_NAME)
    if not path:
        return None
    try:
        img = tk.PhotoImage(file=path)
        factor = max(1, int(round(max(img.width(), img.height()) / float(max_size))))
        return img.subsample(factor, factor) if factor > 1 else img
    except Exception:
        return None




# ---------------------------------------------------------------------------
# 日志：优先写在程序所在目录的 logs/，不可写时回退到 %LOCALAPPDATA%
# ---------------------------------------------------------------------------
def _app_base_dir():
    """返回程序所在目录（兼容 PyInstaller 单文件 exe）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# 配置持久化：exe 同级目录 settings.json（面板显隐 / 窗口尺寸位置 / 分隔条位置）
# ---------------------------------------------------------------------------
SETTINGS_FILE = os.path.join(_app_base_dir(), "settings.json")

PANEL_KEYS = ("left", "middle", "right")
PANEL_TITLES = {
    "left": "① 命令速查录入",
    "middle": "② Markdown 编辑器",
    "right": "③ 实时预览",
}
PANEL_SHORT_TITLES = {"left": "①命令", "middle": "②编辑", "right": "③预览"}
PANEL_WEIGHTS = {"left": 1, "middle": 2, "right": 2}
PANEL_DEFAULT_VISIBLE = {"left": True, "middle": True, "right": True}
# 各面板可用的最小宽度：低于该值时面板内文字会被挤压，
# 恢复历史分隔条位置时用它校验，不达标则放弃恢复、改走比例分配。
PANEL_MIN_WIDTH = {"left": 150, "middle": 280, "right": 220}


def default_settings():
    """默认配置：白色主题、三栏全显示、不指定尺寸与分隔条。"""
    return {"version": APP_VERSION,
            "theme": THEME_LIGHT,
            "panels": dict(PANEL_DEFAULT_VISIBLE),
            "geometry": "",
            "sash": [],
            "sash_width": 0,
            "auto_check_update": False}


def _sanitize_settings(raw):
    """把任意来源（含被手改坏的）配置清洗成安全结构，非法项逐项回退默认值。

    兼容 v1.2.0 及更早版本不含 theme 字段的旧配置：缺失即回退白色主题。
    """
    data = default_settings()
    if not isinstance(raw, dict):
        return data
    theme = raw.get("theme")
    if isinstance(theme, str) and theme.strip().lower() in THEMES:
        data["theme"] = theme.strip().lower()
    panels = raw.get("panels")
    if isinstance(panels, dict):
        for key in PANEL_KEYS:
            val = panels.get(key)
            if isinstance(val, bool):
                data["panels"][key] = val
    if not any(data["panels"].values()):
        # 全隐藏无意义，回退为全显示
        data["panels"] = dict(PANEL_DEFAULT_VISIBLE)
    geom = raw.get("geometry")
    if isinstance(geom, str):
        geom = geom.strip()
        if re.match(r"^\d{3,5}x\d{3,5}([+-]-?\d{1,5}[+-]-?\d{1,5})?$", geom):
            data["geometry"] = geom
    sash = raw.get("sash")
    if isinstance(sash, list):
        clean = []
        for item in sash[:2]:
            if isinstance(item, int) and not isinstance(item, bool) and 40 <= item <= 8000:
                clean.append(item)
        data["sash"] = clean
    sash_width = raw.get("sash_width")
    if isinstance(sash_width, int) and not isinstance(sash_width, bool) \
            and 160 <= sash_width <= 8000:
        data["sash_width"] = sash_width
    auto_check = raw.get("auto_check_update")
    if isinstance(auto_check, bool):
        data["auto_check_update"] = auto_check
    return data


def load_settings():
    """读取 settings.json；文件缺失 / JSON 损坏 / 类型异常一律安全回退默认值。"""
    try:
        if not os.path.exists(SETTINGS_FILE):
            return default_settings()
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return _sanitize_settings(raw)
    except Exception as exc:
        log_action("配置读取失败", "%s | %r" % (SETTINGS_FILE, exc))
        return default_settings()


def save_settings(data):
    """原子写入 settings.json；失败只记日志，绝不影响主流程。"""
    try:
        payload = _sanitize_settings(data)
        payload["version"] = APP_VERSION
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
        return True
    except Exception as exc:
        log_action("配置写入失败", "%s | %r" % (SETTINGS_FILE, exc))
        return False


# ---------------------------------------------------------------------------
# 文件关联（仅写 HKEY_CURRENT_USER\Software\Classes，绝不在启动时自动写）
# ---------------------------------------------------------------------------
ASSOC_PROGID = "SgMdEditor.md"                     # 本工具独占的 ProgID
ASSOC_EXT = ".md"                                  # 关联的扩展名
ASSOC_DESC = "Markdown 文档（爽哥MD编辑工具）"
ASSOC_ROOT = r"Software\Classes"
ASSOC_PREV_VALUE = "_prev_ext_default"             # 备份原 .md 关联，供取消关联时还原
SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000


def _assoc_target_path():
    """关联指向的目标：打包后为 exe，源码运行时为脚本文件。"""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return os.path.abspath(__file__)


def _assoc_command():
    """构造 shell\\open\\command 的命令行：打包后直接调 exe，源码运行时用 pythonw 调脚本。"""
    if getattr(sys, "frozen", False):
        exe = os.path.abspath(sys.executable)
        return '"%s" "%%1"' % exe
    exe = os.path.abspath(sys.executable)
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    script = os.path.abspath(__file__)
    return '"%s" "%s" "%%1"' % (exe, script)


def _assoc_icon_value():
    """DefaultIcon：优先用 .md 专用 ico，其次主 ico，最后退回 exe 内嵌图标。"""
    for name in (ICON_MD_NAME, ICON_MAIN_NAME):
        path = _persist_asset(name)
        if path:
            return '"%s",0' % path
    return '"%s",0' % _assoc_target_path()


def _reg_get(path, name):
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, name)
            return value
    except OSError:
        return None


def _reg_set(path, name, value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_WRITE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    return True


def _reg_delete_value(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except OSError:
        return False


def _reg_delete_tree(path):
    """递归删除 HKCU 下自建的键（只用于本工具自己的 ProgID 键）。"""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ) as key:
            subs = []
            index = 0
            while True:
                try:
                    subs.append(winreg.EnumKey(key, index))
                except OSError:
                    break
                index += 1
        for sub in subs:
            _reg_delete_tree(path + "\\" + sub)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        return True
    except OSError:
        return False


def _notify_assoc_changed():
    """通知 Shell 刷新文件关联与图标缓存。"""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST,
                                             None, None)
    except Exception:
        pass


def assoc_status(progid=ASSOC_PROGID, ext=ASSOC_EXT):
    """读取当前关联状态；只读，不会写任何注册表项。"""
    info = {"progid": progid, "ext": ext, "current": "", "mine": False,
            "icon": "", "command": "", "target": _assoc_target_path(),
            "error": ""}
    if winreg is None:
        info["error"] = "当前环境不支持注册表操作"
        return info
    try:
        info["current"] = _reg_get("%s\\%s" % (ASSOC_ROOT, ext), "") or ""
        info["mine"] = info["current"].strip().lower() == progid.strip().lower()
        info["icon"] = _reg_get("%s\\%s\\DefaultIcon" % (ASSOC_ROOT, progid), "") or ""
        info["command"] = _reg_get(
            "%s\\%s\\shell\\open\\command" % (ASSOC_ROOT, progid), "") or ""
    except Exception as exc:
        info["error"] = str(exc)
    return info


def enable_association(progid=ASSOC_PROGID, ext=ASSOC_EXT):
    """把扩展名关联到本工具（仅在用户点击「关联」按钮时调用）。"""
    if winreg is None:
        return False, "当前环境不支持注册表操作"
    base = "%s\\%s" % (ASSOC_ROOT, progid)
    ext_key = "%s\\%s" % (ASSOC_ROOT, ext)
    try:
        previous = _reg_get(ext_key, "") or ""
        if previous and previous.strip().lower() != progid.strip().lower():
            _reg_set(base, ASSOC_PREV_VALUE, previous)
        _reg_set(base, "", ASSOC_DESC)
        _reg_set(base + "\\DefaultIcon", "", _assoc_icon_value())
        _reg_set(base + "\\shell\\open\\command", "", _assoc_command())
        _reg_set(ext_key, "", progid)
        _reg_set(ext_key + "\\OpenWithProgids", progid, "")
        _notify_assoc_changed()
        log_action("文件关联", "已关联 %s -> %s" % (ext, progid))
        return True, "已把 %s 关联到本工具。\n双击 .md 文件将用「%s」打开。" % (ext, APP_NAME)
    except Exception as exc:
        log_action("文件关联失败", "%r" % exc)
        return False, "写入注册表失败：%s" % exc


def disable_association(progid=ASSOC_PROGID, ext=ASSOC_EXT):
    """取消关联并清理本工具自建的注册表键（仅在用户点击「取消关联」时调用）。"""
    if winreg is None:
        return False, "当前环境不支持注册表操作"
    base = "%s\\%s" % (ASSOC_ROOT, progid)
    ext_key = "%s\\%s" % (ASSOC_ROOT, ext)
    try:
        previous = _reg_get(base, ASSOC_PREV_VALUE) or ""
        current = _reg_get(ext_key, "") or ""
        if current.strip().lower() == progid.strip().lower():
            if previous:
                _reg_set(ext_key, "", previous)
            else:
                _reg_delete_value(ext_key, "")
        _reg_delete_value(ext_key + "\\OpenWithProgids", progid)
        _reg_delete_tree(base)
        _notify_assoc_changed()
        log_action("文件关联", "已取消 %s 关联" % ext)
        if previous:
            return True, "已取消关联，并还原为原有打开方式：%s" % previous
        return True, "已取消关联，.md 文件恢复为系统默认打开方式。"
    except Exception as exc:
        log_action("取消文件关联失败", "%r" % exc)
        return False, "清理注册表失败：%s" % exc


def _pick_log_dir():
    candidates = [
        os.path.join(_app_base_dir(), "logs"),
        os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                     APP_NAME, "logs"),
    ]
    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".write_test")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
            return path
        except Exception:
            continue
    return tempfile.gettempdir()


LOG_DIR = _pick_log_dir()
LOG_FILE = os.path.join(LOG_DIR, "sg-md-editor-%s.log" % time.strftime("%Y%m%d"))

logger = logging.getLogger("shuage.md.editor")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    _handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(_handler)


def log_action(action, detail=""):
    """记录用户操作日志，便于反馈问题时定位。"""
    try:
        logger.info("%s | %s", action, detail)
    except Exception:
        pass


def _install_excepthook():
    def _hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            logger.error("未捕获异常:\n%s", text)
        except Exception:
            pass
        try:
            messagebox.showerror(
                "程序异常",
                "程序发生异常，详细信息已写入日志：\n%s\n\n请把该日志通过邮件发送至 %s"
                % (LOG_FILE, EMAIL),
            )
        except Exception:
            pass

    sys.excepthook = _hook


# ---------------------------------------------------------------------------
# Markdown 渲染（轻量级，输出到 tkinter Text 控件，无第三方依赖）
# ---------------------------------------------------------------------------
_INLINE_RE = re.compile(
    r"(`[^`\n]+`"                      # 行内代码
    r"|\*\*[^*\n]+\*\*"                 # 加粗 **
    r"|__[^_\n]+__"                     # 加粗 __
    r"|~~[^~\n]+~~"                     # 删除线
    r"|\*[^*\n]+\*"                     # 斜体 *
    r"|_[^_\n]+_"                       # 斜体 _
    r"|\[[^\]\n]*\]\([^)\n]*\)"         # 链接 / 图片
    r")"
)

_FENCE_RE = re.compile(r"^\s*```(.*)$")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

PREVIEW_TAG_ORDER = [
    ("normal", {"font": (FONT_CN, 10), "spacing3": 6}),
    ("h1", {"font": (FONT_CN, 18, "bold"), "spacing1": 14, "spacing3": 8,
            "foreground": "#12263f"}),
    ("h2", {"font": (FONT_CN, 15, "bold"), "spacing1": 12, "spacing3": 6,
            "foreground": "#1b3a57"}),
    ("h3", {"font": (FONT_CN, 12, "bold"), "spacing1": 10, "spacing3": 4,
            "foreground": "#24506f"}),
    ("h4", {"font": (FONT_CN, 11, "bold"), "spacing1": 8, "spacing3": 3, "foreground": "#2e5f77"}),
    ("h5", {"font": (FONT_CN, 10, "bold"), "spacing1": 6, "spacing3": 2, "foreground": "#3a5568"}),
    ("h6", {"font": (FONT_CN, 9, "bold"), "spacing1": 6, "spacing3": 2, "foreground": "#6b7c8c"}),
    ("bold", {"font": (FONT_CN, 10, "bold")}),
    ("italic", {"font": (FONT_CN, 10, "italic")}),
    ("strike", {"overstrike": 1}),
    ("link", {"foreground": "#1668dc", "underline": 1}),
    ("code_inline", {"font": (FONT_MONO, 9), "background": "#eef1f4",
                     "foreground": "#c7254e"}),
    ("code_block", {"font": (FONT_MONO, 9), "background": "#f6f8fa",
                    "lmargin1": 16, "lmargin2": 16, "spacing1": 6,
                    "spacing3": 6}),
    ("quote", {"lmargin1": 18, "lmargin2": 18, "foreground": "#55677a",
               "background": "#f5f9fc"}),
    ("list", {"lmargin1": 14, "lmargin2": 32}),
    ("list2", {"lmargin1": 34, "lmargin2": 52}),
    ("table", {"font": (FONT_CN, 10), "background": "#fbfcfe",
               "lmargin1": 12, "spacing1": 1}),
    ("hr", {"foreground": "#c9d1d9", "spacing1": 8, "spacing3": 8}),
    ("hint", {"font": (FONT_CN, 10, "italic"), "foreground": "#9aa5b1"}),
]

# 预览标签里需要随主题变化的键：标签名 -> 调色板中对应字段
_TAG_COLOR_MAP = {
    "h1": "h1_fg", "h2": "h2_fg", "h3": "h3_fg",
    "h4": "h4_fg", "h5": "h5_fg", "h6": "h6_fg",
    "link": "link_fg", "hr": "hr_fg", "hint": "hint_tag_fg",
}


def preview_tag_options(palette):
    """按当前主题生成预览区全部标签样式（黑色主题下语法高亮仍可读）。"""
    specs = []
    for name, options in PREVIEW_TAG_ORDER:
        opts = dict(options)
        key = _TAG_COLOR_MAP.get(name)
        if key:
            opts["foreground"] = palette[key]
        if name == "code_inline":
            opts["background"] = palette["code_inline_bg"]
            opts["foreground"] = palette["code_inline_fg"]
        elif name == "code_block":
            opts["background"] = palette["code_block_bg"]
            opts["foreground"] = palette["code_block_fg"]
        elif name == "quote":
            opts["background"] = palette["quote_bg"]
            opts["foreground"] = palette["quote_fg"]
        elif name == "table":
            opts["background"] = palette["table_bg"]
            opts["foreground"] = palette["text_fg"]
        specs.append((name, opts))
    return specs


def _disp_width(text):
    """计算字符串在等宽环境下的显示宽度（CJK 记 2）。"""
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text, width):
    gap = width - _disp_width(text)
    return text + (" " * gap if gap > 0 else "")


def _truncate(text, limit=26):
    if _disp_width(text) <= limit:
        return text
    out = ""
    for ch in text:
        if _disp_width(out) + _disp_width(ch) > limit - 1:
            break
        out += ch
    return out + "…"


def plain_inline(text):
    """去掉行内标记，取纯文本（用于标题等场景）。"""
    def _repl(match):
        token = match.group(0)
        if token.startswith("`"):
            return token[1:-1]
        if token.startswith("**") or token.startswith("__"):
            return token[2:-2]
        if token.startswith("~~"):
            return token[2:-2]
        if token.startswith("*") or token.startswith("_"):
            return token[1:-1]
        link = re.match(r"\[([^\]]*)\]\(([^)]*)\)", token)
        if link:
            return link.group(1) or link.group(2)
        return token

    return _INLINE_RE.sub(_repl, text)


def render_inline(widget, text, extra_tags=()):
    """把带行内标记的文本写入 Text 控件，并附加样式标签。"""
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            widget.insert("end", text[pos:match.start()], tuple(extra_tags) or ("normal",))
        token = match.group(0)
        if token.startswith("`"):
            widget.insert("end", token[1:-1], tuple(extra_tags) + ("code_inline",))
        elif token.startswith("**") or token.startswith("__"):
            widget.insert("end", token[2:-2], tuple(extra_tags) + ("bold",))
        elif token.startswith("~~"):
            widget.insert("end", token[2:-2], tuple(extra_tags) + ("strike",))
        elif token.startswith("*") or token.startswith("_"):
            widget.insert("end", token[1:-1], tuple(extra_tags) + ("italic",))
        else:
            link = re.match(r"\[([^\]]*)\]\(([^)]*)\)", token)
            if link:
                label = link.group(1) or link.group(2)
                widget.insert("end", label, tuple(extra_tags) + ("link",))
                url = link.group(2)
                if url and url != label:
                    widget.insert("end", " (%s)" % url,
                                  tuple(extra_tags) + ("hint",))
            else:
                widget.insert("end", token, tuple(extra_tags) or ("normal",))
        pos = match.end()
    if pos < len(text):
        widget.insert("end", text[pos:], tuple(extra_tags) or ("normal",))


def _split_table_row(raw):
    """按未转义的竖线拆分表格行，并还原 \\| 转义与行内标记。"""
    body = raw.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    cleaned = []
    for cell in cells:
        text = cell.replace("\\|", "|").strip()
        cleaned.append(_truncate(plain_inline(text), 24))
    while cleaned and not cleaned[-1]:
        cleaned.pop()
    return cleaned


def render_table_block(widget, lines):
    """把 Markdown 表格渲染成对齐的字符网格（预览用）。"""
    rows = []
    for idx, raw in enumerate(lines):
        if idx == 1 and _TABLE_SEP_RE.match(raw):
            continue
        cells = _split_table_row(raw)
        if cells and all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return
    col_count = max(len(row) for row in rows)
    for row in rows:
        row.extend([""] * (col_count - len(row)))
    widths = []
    for col in range(col_count):
        widths.append(max(4, max(_disp_width(row[col]) for row in rows)))

    head, sep, foot = [], [], []
    for width in widths:
        head.append("─" * (width + 2))
        sep.append("─" * (width + 2))
        foot.append("─" * (width + 2))
    widget.insert("end", "┌" + "┬".join(head) + "┐\n", ("table",))
    for row_idx, row in enumerate(rows):
        line = "│ " + " │ ".join(_pad(cell, widths[i]) for i, cell in enumerate(row)) + " │"
        widget.insert("end", line + "\n", ("table",))
        if row_idx == 0 and len(rows) > 1:
            widget.insert("end", "├" + "┼".join(sep) + "┤\n", ("table",))
    widget.insert("end", "└" + "┴".join(foot) + "┘\n", ("table",))


def render_markdown(widget, md_text):
    """Markdown -> Text 控件渲染。"""
    widget.configure(state="normal")
    widget.delete("1.0", "end")

    if not md_text.strip():
        widget.insert("end", "预览区：在「Markdown 编辑器」中输入内容，这里会实时渲染。\n",
                      ("hint",))
        widget.configure(state="disabled")
        return

    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    total = len(lines)
    index = 0
    while index < total:
        line = lines[index]

        # 1. 代码块
        fence = _FENCE_RE.match(line)
        if fence:
            lang = fence.group(1).strip()
            index += 1
            buffer_lines = []
            while index < total and not re.match(r"^\s*```\s*$", lines[index]):
                buffer_lines.append(lines[index])
                index += 1
            index += 1  # 跳过结束围栏
            if lang:
                widget.insert("end", "  %s\n" % lang, ("hint",))
            for buf in buffer_lines:
                widget.insert("end", buf + "\n", ("code_block",))
            if not buffer_lines:
                widget.insert("end", "\n", ("code_block",))
            widget.insert("end", "\n", ("normal",))
            continue

        # 2. 空行
        if not line.strip():
            widget.insert("end", "\n", ("normal",))
            index += 1
            continue

        # 3. 水平分割线
        if _HR_RE.match(line):
            widget.insert("end", "─" * 46 + "\n", ("hr",))
            index += 1
            continue

        # 4. 标题
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            text = plain_inline(heading.group(2).strip())
            text = re.sub(r"\s*#+\s*$", "", text)
            widget.insert("end", text + "\n", ("normal", "h%d" % level))
            index += 1
            continue

        # 5. 引用
        quote = _QUOTE_RE.match(line)
        if quote:
            widget.insert("end", "▎ ", ("quote",))
            render_inline(widget, quote.group(1), ("quote",))
            widget.insert("end", "\n", ("quote",))
            index += 1
            continue

        # 6. 表格
        if line.strip().startswith("|"):
            table_lines = []
            while index < total and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            render_table_block(widget, table_lines)
            widget.insert("end", "\n", ("normal",))
            continue

        # 7. 列表 / 任务列表
        listed = _LIST_RE.match(line)
        if listed:
            indent = len(listed.group(1).replace("\t", "  "))
            marker = listed.group(2)
            body = listed.group(3)
            base_tags = ("normal", "list" if indent < 2 else "list2")
            task = _TASK_RE.match(body)
            if task:
                box = "☑ " if task.group(1).lower() == "x" else "☐ "
                widget.insert("end", box, base_tags)
                render_inline(widget, task.group(2), base_tags)
            elif marker in ("-", "*", "+"):
                widget.insert("end", "• ", base_tags)
                render_inline(widget, body, base_tags)
            else:
                widget.insert("end", "%s " % marker, base_tags)
                render_inline(widget, body, base_tags)
            widget.insert("end", "\n", base_tags)
            index += 1
            continue

        # 8. 普通段落
        render_inline(widget, line.strip(), ("normal",))
        widget.insert("end", "\n", ("normal",))
        index += 1

    widget.configure(state="disabled")


# ---------------------------------------------------------------------------
# 命令速查解析
# ---------------------------------------------------------------------------
def parse_command_lines(raw_text):
    """把「命令 + 说明」文本解析成 (命令, 说明) 列表。

    支持分隔符：Tab、竖线 |、箭头 →、全角冒号：、两个及以上空格、单个空格。
    """
    items = []
    for raw in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cmd, desc = "", ""
        if "\t" in line:
            parts = line.split("\t")
            cmd = parts[0].strip()
            desc = " ".join(p.strip() for p in parts[1:] if p.strip())
        elif "|" in line:
            cmd, desc = [p.strip() for p in line.split("|", 1)]
        elif "→" in line:
            cmd, desc = [p.strip() for p in line.split("→", 1)]
        elif "：" in line:
            cmd, desc = [p.strip() for p in line.split("：", 1)]
        elif re.search(r"\s{2,}", line):
            cmd, desc = [p.strip() for p in re.split(r"\s{2,}", line, 1)]
        else:
            parts = line.split(" ", 1)
            cmd = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
        if cmd:
            items.append((cmd, desc))
    return items


def build_markdown_table(items, title="常用命令速查"):
    if not items:
        return ""
    rows = ["## %s" % title, "", "| 命令 | 说明 |", "| --- | --- |"]
    for cmd, desc in items:
        rows.append("| `%s` | %s |" % (cmd.replace("|", "\\|"),
                                       (desc or "—").replace("|", "\\|")))
    return "\n".join(rows) + "\n"


def build_code_list(items, lang="bash", title="常用命令清单"):
    if not items:
        return ""
    rows = ["### %s" % title, "", "```%s" % lang]
    for cmd, desc in items:
        rows.append("# %s" % (desc or "说明"))
        rows.append(cmd)
    rows.append("```")
    return "\n".join(rows) + "\n"


def build_bullet_list(items, title="常用命令列表"):
    if not items:
        return ""
    rows = ["### %s" % title, ""]
    for cmd, desc in items:
        rows.append("- `%s` — %s" % (cmd, desc or "—"))
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# 关于窗口
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 在线检查更新（v1.6.0）
# 版本源 = 本项目 GitHub 仓库的 Releases（https://github.com/yangshuang9889/MdCmdTool）
# 流程：GET /repos/{owner}/{repo}/releases/latest -> 取 tag_name 与 body -> 与 APP_VERSION 比对
# 仅发起一次匿名只读 HTTPS 请求，不携带任何本机标识，不做后台常驻轮询。
# ---------------------------------------------------------------------------
def parse_version(text):
    """把 "v1.6.0" / "1.6" / "1.6.0.0" 解析成可比较的整数元组；无法解析返回 None。"""
    if text is None:
        return None
    match = re.match(r"^[vV]?(\d+(?:\.\d+)*)", str(text).strip())
    if not match:
        return None
    parts = [int(item) for item in match.group(1).split(".") if item != ""]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def compare_version(current, remote):
    """比较版本：远端更新返回 1，相同返回 0，远端更旧返回 -1，无法解析返回 None。"""
    left, right = parse_version(current), parse_version(remote)
    if left is None or right is None:
        return None
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    if right > left:
        return 1
    if right == left:
        return 0
    return -1


def parse_release_payload(payload):
    """从 GitHub Releases API 返回体里提取检查更新需要的字段。"""
    if not isinstance(payload, dict):
        raise ValueError("接口返回格式异常")
    tag = payload.get("tag_name") or payload.get("name") or ""
    version = parse_version(tag)
    if version is None:
        raise ValueError("发布版本号无法解析：%r" % tag)
    assets = []
    for item in (payload.get("assets") or []):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or ""
        url = item.get("browser_download_url") or ""
        if name and url:
            assets.append((name, url))
    return {"version": ".".join(str(part) for part in version[:3]),
            "tag": str(tag),
            "name": payload.get("name") or str(tag),
            "notes": (payload.get("body") or "").strip(),
            "url": payload.get("html_url") or UPDATE_PAGE,
            "published": (payload.get("published_at") or "")[:10],
            "prerelease": bool(payload.get("prerelease")),
            "assets": assets}


def fetch_latest_release(timeout=UPDATE_TIMEOUT):
    """请求最新 Release。仓库没有任何发布时抛 LookupError，其余失败统一抛 RuntimeError。"""
    request = urllib.request.Request(UPDATE_API_LATEST, headers={
        "User-Agent": UPDATE_UA,
        "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise LookupError("仓库暂无已发布的版本")
        if exc.code in (403, 429):
            raise RuntimeError("GitHub 接口访问受限（HTTP %d），请稍后再试" % exc.code)
        raise RuntimeError("接口返回 HTTP %d" % exc.code)
    except urllib.error.URLError as exc:
        raise RuntimeError("网络不可用：%s" % (exc.reason,))
    except socket.timeout:
        raise RuntimeError("请求超时（%d 秒）" % int(timeout))
    except ValueError:
        raise RuntimeError("返回内容不是合法 JSON")
    return parse_release_payload(payload)


class UpdateDialog(tk.Toplevel):
    """检查更新结果窗口：当前版本 / 最新版本 / 发布时间 / 更新说明 / 下载入口。"""

    def __init__(self, master, palette, current_version, info=None, error=None):
        tk.Toplevel.__init__(self, master)
        palette = palette or THEMES[THEME_LIGHT]
        info = info or {}
        self._url = info.get("url") or UPDATE_PAGE
        self.title("检查更新 · %s" % APP_NAME)
        self.configure(bg=palette["window_bg"])
        self.transient(master)
        self.minsize(600, 440)
        try:
            icon = _asset_path(ICON_MAIN_NAME)
            if icon:
                self.iconbitmap(icon)
        except Exception:
            pass

        header = tk.Frame(self, bg=palette["header_bg"], height=50)
        header.pack(fill="x")
        tk.Label(header, text="在线检查更新 · %s" % APP_NAME, bg=palette["header_bg"],
                 fg=palette["header_fg"], font=(FONT_CN, 12, "bold")).pack(
            side="left", padx=16, pady=14)

        body = tk.Frame(self, bg=palette["panel_bg"])
        body.pack(fill="both", expand=True, padx=18, pady=14)

        if error:
            relation = None
            rows = [("当前版本", "v%s" % current_version),
                    ("检查结果", "检查失败"),
                    ("失败原因", error)]
        else:
            relation = compare_version(current_version, info.get("version"))
            if relation == 1:
                state = "发现新版本，建议更新"
            elif relation == 0:
                state = "已是最新版本"
            else:
                state = "当前版本比线上更高（开发版）"
            rows = [("当前版本", "v%s" % current_version),
                    ("最新版本", "v%s" % info.get("version", "未知")),
                    ("发布时间", info.get("published") or "（未知）"),
                    ("版本状态", state)]

        for row, (key, value) in enumerate(rows):
            tk.Label(body, text=key + "：", bg=palette["panel_bg"],
                     fg=palette["hint_fg"], font=(FONT_CN, 10), anchor="e",
                     width=9).grid(row=row, column=0, sticky="e", pady=3)
            tk.Label(body, text=value, bg=palette["panel_bg"],
                     fg=palette["text_fg"], font=(FONT_CN, 10, "bold"),
                     anchor="w", justify="left", wraplength=430).grid(
                row=row, column=1, sticky="w", pady=3)

        notes_box = tk.Frame(body, bg=palette["toolbar_bg"], highlightthickness=1,
                             highlightbackground=palette["border"])
        notes_box.grid(row=len(rows), column=0, columnspan=2, sticky="nsew",
                       pady=(12, 6))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(len(rows), weight=1)
        tk.Label(notes_box, text="更新说明", bg=palette["toolbar_bg"],
                 fg=palette["status_fg"], font=(FONT_CN, 9, "bold"),
                 anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        notes_text = tk.Text(notes_box, height=9, wrap="word", relief="flat",
                             bg=palette["text_bg"], fg=palette["text_fg"],
                             insertbackground=palette["insert_bg"],
                             font=(FONT_MONO, 9), padx=6, pady=6)
        notes_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        scroll = ttk.Scrollbar(notes_box, orient="vertical",
                               command=notes_text.yview)
        scroll.pack(side="right", fill="y", pady=6, padx=(0, 8))
        notes_text.configure(yscrollcommand=scroll.set)
        content = (info.get("notes") or "").strip()
        if not content:
            if relation == 1:
                content = "该版本未填写更新说明，可点击下方按钮查看发布页。"
            elif error:
                content = "未能获取更新说明。"
            else:
                content = "当前已是最新版本，无需更新。"
        notes_text.insert("1.0", content)
        notes_text.configure(state="disabled")

        buttons = tk.Frame(self, bg=palette["panel_bg"])
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        if relation == 1:
            ttk.Button(buttons, text="打开发布页 / 下载最新版", width=24,
                       command=self.open_page).pack(side="left")
        else:
            ttk.Button(buttons, text="打开项目主页", width=18,
                       command=self.open_page).pack(side="left")
        ttk.Button(buttons, text="关闭", width=9,
                   command=self.destroy).pack(side="right")

        self.update_idletasks()
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + 80
            self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        except Exception:
            pass

    def open_page(self):
        try:
            webbrowser.open(self._url, new=2)
            log_action("检查更新", "打开发布页 %s" % self._url)
        except Exception as exc:
            messagebox.showerror("提示", "无法打开浏览器：%s" % exc, parent=self)


class AboutDialog(tk.Toplevel):
    """关于窗口：作者信息 + 日志反馈说明。"""

    def __init__(self, master, palette=None, app=None):
        super().__init__(master)
        self._app = app
        palette = palette or THEMES[THEME_LIGHT]
        self._palette = palette
        self.title("关于 %s" % APP_NAME)
        self.configure(bg=palette["window_bg"])
        self.resizable(False, False)
        self.transient(master)
        try:
            icon = _asset_path(ICON_MAIN_NAME)
            if icon:
                self.iconbitmap(icon)
        except Exception:
            pass

        header = tk.Frame(self, bg=palette["header_bg"], height=64)
        header.pack(fill="x")
        tk.Label(header, text="关于 · %s" % APP_NAME, bg=palette["header_bg"],
                 fg=palette["header_fg"], font=(FONT_CN, 12, "bold")).pack(
            side="left", padx=16, pady=18)
        logo = _load_about_logo()
        if logo is not None:
            label = tk.Label(header, image=logo, bg=palette["header_bg"])
            label.image = logo
            label.pack(side="right", padx=12, pady=8)

        body = tk.Frame(self, bg=palette["panel_bg"])
        body.pack(fill="both", expand=True, padx=18, pady=14)

        info = [
            ("软件名称", APP_NAME),
            ("版本号", APP_VERSION),
            ("制作人", AUTHOR),
            ("AI 工具", AI_TOOL),
            ("反馈邮箱", EMAIL),
        ]
        for row, (key, value) in enumerate(info):
            tk.Label(body, text=key + "：", bg=palette["panel_bg"],
                     fg=palette["hint_fg"], font=(FONT_CN, 10), anchor="e",
                     width=9).grid(row=row, column=0, sticky="e", pady=3)
            tk.Label(body, text=value, bg=palette["panel_bg"],
                     fg=palette["text_fg"], font=(FONT_CN, 10, "bold"),
                     anchor="w").grid(row=row, column=1, sticky="w", pady=3)

        tip_box = tk.Frame(body, bg=palette["toolbar_bg"], highlightthickness=1,
                           highlightbackground=palette["border"])
        tip_box.grid(row=len(info), column=0, columnspan=2, sticky="we",
                     pady=(14, 6), ipadx=8, ipady=8)
        tip_text = (
            "【日志与问题反馈】\n"
            "运行日志目录：\n%s\n\n"
            "遇到报错、界面异常或有功能建议，请将日志目录下最新的\n"
            "%s 文件作为附件，通过邮件发送至 %s，\n"
            "邮件标题建议写「%s 问题反馈」，正文简述操作步骤。"
            % (LOG_DIR, os.path.basename(LOG_FILE), EMAIL, APP_NAME)
        )
        tk.Label(tip_box, text=tip_text, bg=palette["toolbar_bg"],
                 fg=palette["status_fg"], font=(FONT_CN, 9), justify="left",
                 anchor="w").pack(fill="x", padx=6, pady=2)

        buttons = tk.Frame(self, bg=palette["panel_bg"])
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(buttons, text="打开日志目录", width=13,
                   command=self.open_log_dir).pack(side="left")
        ttk.Button(buttons, text="复制反馈信息", width=13,
                   command=self.copy_feedback).pack(side="left", padx=8)
        if self._app is not None:
            ttk.Button(buttons, text="检查更新", width=10,
                       command=self.check_update).pack(side="left", padx=8)
        ttk.Button(buttons, text="关闭", width=9,
                   command=self.destroy).pack(side="right")

        self.update_idletasks()
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + 120
            self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        except Exception:
            pass

        log_action("关于窗口", "已打开")

    def check_update(self):
        """从关于窗口直接触发在线检查更新（先关掉本窗口，避免弹窗叠层）。"""
        app = self._app
        try:
            self.destroy()
        except Exception:
            pass
        if app is not None:
            app.check_update(True)

    def open_log_dir(self):
        try:
            os.startfile(LOG_DIR)  # noqa: S606
            log_action("打开日志目录", LOG_DIR)
        except Exception as exc:
            messagebox.showerror("提示", "无法打开日志目录：%s" % exc, parent=self)

    def copy_feedback(self):
        info = ("%s v%s\n制作人：%s\nAI 工具：%s\n反馈邮箱：%s\n日志目录：%s\n日志文件：%s\n"
                % (APP_NAME, APP_VERSION, AUTHOR, AI_TOOL, EMAIL, LOG_DIR, LOG_FILE))
        self.clipboard_clear()
        self.clipboard_append(info)
        self.update()
        log_action("复制反馈信息", LOG_FILE)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class FlowFrame(tk.Frame):
    """流式布局容器：子控件按可用宽度自动换行，
    每个控件始终以自身最佳尺寸显示，不压缩、不裁切。"""

    def __init__(self, master=None, spacing=4, **kwargs):
        tk.Frame.__init__(self, master, **kwargs)
        self._spacing = spacing
        self._items = []
        self._last_width = -1
        self._placed_ok = False
        self.bind("<Configure>", self._on_configure)

    def add_widget(self, widget):
        self._items.append(widget)
        self.after_idle(self.relayout)

    def _on_configure(self, event=None):
        width = self.winfo_width()
        if width != self._last_width:
            self.after_idle(self.relayout)

    def relayout(self):
        width = self.winfo_width()
        if width <= 1 or not self._items:
            return
        if width == self._last_width and self._placed_ok:
            return
        rows = []
        cur = []
        cur_w = 0
        for widget in self._items:
            w = max(widget.winfo_reqwidth(), 1)
            h = max(widget.winfo_reqheight(), 1)
            extra = self._spacing if cur else 0
            if cur and cur_w + extra + w > width:
                rows.append(cur)
                cur = []
                cur_w = 0
                extra = 0
            cur.append((widget, w, h))
            cur_w += extra + w
        if cur:
            rows.append(cur)
        y = 0
        for row in rows:
            row_h = max(h for _, _, h in row)
            x = 0
            for widget, w, h in row:
                widget.place(x=x, y=y + (row_h - h) // 2, width=w, height=h)
                x += w + self._spacing
            y += row_h + self._spacing
        total = max(y - self._spacing, 0)
        self._placed_ok = True
        self._last_width = width
        if total > 0 and self.winfo_reqheight() != total:
            self.configure(height=total)


class SettingsWindow(tk.Toplevel):
    """设置窗口：外观主题（黑/白，实时生效）+ .md 文件关联（手动触发）。"""

    def __init__(self, app):
        tk.Toplevel.__init__(self, app.root)
        self.app = app
        self.alive = True
        self.title("设置 · %s" % APP_NAME)
        self.transient(app.root)
        self.minsize(560, 560)
        self.resizable(True, False)
        try:
            icon = _asset_path(ICON_MAIN_NAME)
            if icon:
                self.iconbitmap(icon)
        except Exception:
            pass

        self._theme_var = tk.StringVar(value=app.theme)
        self._assoc_text = tk.StringVar(value="正在读取当前关联状态…")
        self._tip_text = tk.StringVar(value="")
        self._assoc_buttons = []

        self._build()
        self.apply_theme()
        self.refresh_assoc_status()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Escape>", lambda e: self.on_close())
        self.update_idletasks()
        self._center_on_parent()

    # ---------------- 界面 ----------------
    def _build(self):
        palette = self.app.palette
        outer = bind_colors(tk.Frame(self), palette, "window_bg")
        outer.pack(fill="both", expand=True, padx=14, pady=12)

        # ① 外观主题
        theme_box = ttk.LabelFrame(outer, text=" 外观主题 ")
        theme_box.pack(fill="x")
        inner = ttk.Frame(theme_box)
        inner.pack(fill="x", padx=14, pady=(8, 4))
        self._theme_radios = []
        for key in THEME_KEYS:
            rb = ttk.Radiobutton(inner, text=THEME_LABELS[key], value=key,
                                 variable=self._theme_var,
                                 command=self._on_theme_change)
            rb.pack(side="left", padx=(0, 22))
            self._theme_radios.append(rb)
        bind_colors(ttk.Label(theme_box, justify="left", wraplength=520,
                              text="切换后立即对主窗口、三栏面板、编辑器与预览区、"
                                   "工具栏、状态栏、菜单与对话框整体生效，并写入 "
                                   "settings.json，下次启动自动恢复。"),
                    palette, "panel_bg", "hint_fg").pack(fill="x", padx=14, pady=(0, 10))

        # ② 文件关联
        assoc_box = ttk.LabelFrame(outer, text=" 文件关联（.md） ")
        assoc_box.pack(fill="both", expand=True, pady=(12, 0))
        bind_colors(ttk.Label(assoc_box, textvariable=self._assoc_text,
                             justify="left", wraplength=520),
                    palette, "panel_bg", "text_fg").pack(fill="x", padx=14, pady=(10, 6))
        btn_row = ttk.Frame(assoc_box)
        btn_row.pack(fill="x", padx=14)
        for text, command in (("关联 .md 文件到本工具", self._on_enable),
                              ("取消关联", self._on_disable),
                              ("刷新状态", self.refresh_assoc_status)):
            btn = ttk.Button(btn_row, text=text, command=command, padding=(12, 4))
            btn.pack(side="left", padx=(0, 8))
            self._assoc_buttons.append(btn)
            if text == "取消关联":
                self._disable_btn = btn
        bind_colors(ttk.Label(assoc_box, justify="left", wraplength=520,
                              text="说明：本功能只写 HKEY_CURRENT_USER\\Software\\Classes "
                                   "下本工具专属的 ProgID（%s），不改动系统级关联；"
                                   "程序启动时不会自动写注册表，必须由你点击上面的按钮才生效。"
                                   "取消关联会清理本工具自建的注册表键，并尽量还原原来的打开方式。"
                                   % ASSOC_PROGID),
                    palette, "panel_bg", "hint_fg").pack(fill="x", padx=14, pady=(8, 10))
        bind_colors(ttk.Label(assoc_box, textvariable=self._tip_text, justify="left",
                             wraplength=520),
                    palette, "panel_bg", "muted_fg").pack(fill="x", padx=14, pady=(0, 10))

        # ③ 在线更新
        upd_box = ttk.LabelFrame(outer, text=" 在线更新 ")
        upd_box.pack(fill="x", pady=(12, 0))
        self._auto_update_var = tk.BooleanVar(
            value=bool(self.app.settings.get("auto_check_update")))
        ttk.Checkbutton(upd_box, text="启动时自动检查更新（发现新版本只在状态栏提示，不弹窗）",
                        variable=self._auto_update_var,
                        command=self._on_auto_update_toggle).pack(
            anchor="w", padx=14, pady=(8, 2))
        upd_row = ttk.Frame(upd_box)
        upd_row.pack(fill="x", padx=14, pady=(2, 4))
        ttk.Button(upd_row, text="立即检查更新", padding=(12, 4),
                   command=self._on_check_update).pack(side="left")
        ttk.Button(upd_row, text="打开发布页", padding=(12, 4),
                   command=self.open_release_page).pack(side="left", padx=8)
        bind_colors(ttk.Label(upd_box, justify="left", wraplength=520,
                              text="更新源是本项目 GitHub 开源仓库（%s）的 Releases：检查时只发起"
                                   "一次匿名只读 HTTPS 请求，读取最新版本号与更新说明，"
                                   "不上传任何本机信息，也不安装任何东西——发现新版本后由你自己"
                                   "决定是否到发布页下载。" % UPDATE_REPO),
                    palette, "panel_bg", "hint_fg").pack(fill="x", padx=14, pady=(0, 10))

        # 底部
        bottom = bind_colors(ttk.Frame(outer), palette, "window_bg")
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Button(bottom, text="关闭", command=self.on_close,
                   padding=(16, 4)).pack(side="right")

    def _center_on_parent(self):
        try:
            root = self.app.root
            w = self.winfo_width()
            h = self.winfo_height()
            x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
            y = root.winfo_rooty() + max(0, (root.winfo_height() - h) // 3)
            self.geometry("+%d+%d" % (x, y))
        except Exception:
            pass

    # ---------------- 主题 ----------------
    def _on_theme_change(self):
        name = self._theme_var.get()
        try:
            self.app.apply_theme(name)
            self._tip_text.set("已切换到%s，主窗口配色已同步并保存。" % THEME_LABELS[name])
        except Exception as exc:
            log_action("主题切换失败", repr(exc))
            self._tip_text.set("主题切换失败：%s" % exc)

    def apply_theme(self):
        """跟随主窗口调色板刷新本窗口。"""
        palette = self.app.palette
        try:
            self.configure(bg=palette["window_bg"])
        except Exception:
            pass
        apply_palette(self, palette)
        self._theme_var.set(self.app.theme)

    # ---------------- 文件关联 ----------------
    def refresh_assoc_status(self):
        info = assoc_status()
        if info.get("error"):
            self._assoc_text.set("当前状态：无法读取注册表（%s）" % info["error"])
        elif info["mine"]:
            self._assoc_text.set(
                "当前状态：已关联到本工具（%s）\n打开命令：%s\n文件图标：%s"
                % (info["progid"], info["command"] or "（未写入）",
                   info["icon"] or "（未写入）"))
        else:
            shown = info["current"] or "（系统默认 / 无）"
            self._assoc_text.set(
                "当前状态：未关联到本工具\n当前 .md 打开方式：%s" % shown)
        try:
            self._disable_btn.configure(state=("normal" if info["mine"] else "disabled"))
        except Exception:
            pass
        return info

    def _on_enable(self):
        ok, msg = enable_association()
        self._tip_text.set(msg.replace("\n", " "))
        self.refresh_assoc_status()
        log_action("设置窗口", "关联 .md 结果 %s" % ("成功" if ok else "失败"))

    def _on_disable(self):
        ok, msg = disable_association()
        self._tip_text.set(msg.replace("\n", " "))
        self.refresh_assoc_status()
        log_action("设置窗口", "取消 .md 关联结果 %s" % ("成功" if ok else "失败"))

    # ---------------- 在线更新 ----------------
    def _on_auto_update_toggle(self):
        enabled = bool(self._auto_update_var.get())
        self.app.settings["auto_check_update"] = enabled
        try:
            self.app.save_layout()
        except Exception as exc:
            log_action("设置窗口", "保存自动检查配置失败 %r" % exc)
        try:
            self.app._update_auto_check()
        except Exception:
            pass
        self._tip_text.set("已%s启动时自动检查更新。" % ("开启" if enabled else "关闭"))
        log_action("设置窗口", "自动检查更新=%s" % enabled)

    def _on_check_update(self):
        self.app.check_update(True)

    def open_release_page(self):
        try:
            webbrowser.open(UPDATE_PAGE, new=2)
            self._tip_text.set("已在浏览器中打开发布页：%s" % UPDATE_PAGE)
        except Exception as exc:
            self._tip_text.set("无法打开浏览器：%s" % exc)

    def on_close(self):
        self.alive = False
        try:
            self.app.settings_window = None
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


class MdToolApp:
    def __init__(self, root):
        self.root = root
        self.status_var = tk.StringVar(value="就绪")
        self.stat_var = tk.StringVar(value="字符 0 · 行 1")
        self.current_file = None
        self._dirty = False
        self._base_content = ""
        self.preview_job = None
        self.buttons = {}
        # 最近一次有效选区（起点, 终点, 文本）：按钮点击抢走焦点后选区高亮会消失，
        # 用它兜底，保证"选中文本 + 点按钮"仍能套用模板。
        self._last_selection = None

        # 配置持久化：面板显隐 / 窗口尺寸位置 / 分隔条位置 / 主题
        self.settings = load_settings()
        self.theme = self.settings.get("theme") or THEME_LIGHT
        if self.theme not in THEMES:
            self.theme = THEME_LIGHT
        self.palette = palette_of(self.theme)
        self._panel_visible = dict(self.settings["panels"])
        self._panel_vars = {}
        self._panel_widgets = {}
        self._panel_buttons = {}
        self._panel_checks = {}
        self._save_job = None
        self.settings_window = None

        self._setup_window()
        self._apply_theme_style()
        self._build_menu()
        self._build_toolbar()
        # 状态栏必须先于三栏 body 打包：tkinter 的 pack 按打包先后分配空间，
        # 若 body（expand=True）先打包会把高度吃满，导致底部状态栏被压到十几像素、
        # 面板显隐复选项无法显示（v1.2.0 踩坑）。
        self._build_statusbar()
        self._build_body()
        self._bind_shortcuts()
        self.load_welcome()
        self.schedule_preview()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self._restore_layout)
        # 启动时静默检查更新（默认关闭，设置窗口可开）：只写日志与状态栏，不打断操作
        self._auto_update_job = None
        self._update_auto_check(delay=2600)
        log_action("启动", "%s v%s | 日志 %s" % (APP_NAME, APP_VERSION, LOG_FILE))

    # ---------------- 界面构建 ----------------
    def _setup_window(self):
        self.root.title("%s v%s" % (APP_NAME, APP_VERSION))
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        init_w = max(1024, min(1440, int(screen_w * 0.88)))
        init_h = max(680, min(920, int(screen_h * 0.84)))
        saved_geom = self.settings.get("geometry") or ""
        if saved_geom and self._geometry_ok(saved_geom):
            self.root.geometry(saved_geom)
        else:
            self.root.geometry("%dx%d" % (init_w, init_h))
        # 允许缩到 940x620，流式工具栏仍保证按钮完整可见
        self.root.minsize(940, 620)
        self.root.configure(bg=self.palette["window_bg"])
        try:
            icon_path = _asset_path(ICON_MAIN_NAME)
            if icon_path:
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

    def _build_menu(self):
        palette = self.palette
        menubar = tk.Menu(self.root)
        self.menubar = menubar

        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="新建", accelerator="Ctrl+N", command=self.new_document)
        m_file.add_command(label="打开 Markdown...", accelerator="Ctrl+O",
                           command=self.open_document)
        m_file.add_separator()
        m_file.add_command(label="保存", accelerator="Ctrl+S",
                           command=self.save_current)
        m_file.add_command(label="另存为...", accelerator="Ctrl+Shift+S",
                           command=self.export_document)
        m_file.add_separator()
        m_file.add_command(label="设置...", accelerator="Ctrl+,",
                           command=self.open_settings)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.on_close)
        menubar.add_cascade(label="文件", menu=m_file)

        m_edit = tk.Menu(menubar, tearoff=0)
        m_edit.add_command(label="撤销", accelerator="Ctrl+Z",
                           command=lambda: self.editor.event_generate("<<Undo>>"))
        m_edit.add_command(label="重做", accelerator="Ctrl+Y",
                           command=lambda: self.editor.event_generate("<<Redo>>"))
        m_edit.add_separator()
        m_edit.add_command(label="全选", accelerator="Ctrl+A",
                           command=self.select_all)
        m_edit.add_command(label="复制全部内容到剪贴板", accelerator="Ctrl+Shift+C",
                           command=self.copy_all)
        menubar.add_cascade(label="编辑", menu=m_edit)

        m_view = tk.Menu(menubar, tearoff=0)
        for idx, key in enumerate(PANEL_KEYS):
            var = tk.BooleanVar(value=bool(self._panel_visible.get(key, True)))
            self._panel_vars[key] = var
            m_view.add_checkbutton(label="显示%s" % PANEL_TITLES[key],
                                   accelerator="Ctrl+%d" % (idx + 1),
                                   variable=var,
                                   command=lambda k=key: self.toggle_panel(k))
        m_view.add_separator()
        m_view.add_command(label="显示全部面板", command=self.show_all_panels)
        menubar.add_cascade(label="视图", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="检查更新...", command=lambda: self.check_update(True))
        m_help.add_separator()
        m_help.add_command(label="使用说明", command=self.show_help)
        m_help.add_command(label="日志与问题反馈", command=self.show_feedback_help)
        m_help.add_separator()
        m_help.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=m_help)

        self._menus = [menubar, m_file, m_edit, m_view, m_help]
        for menu in self._menus:
            style_menu(menu, palette)
        self.root.configure(menu=menubar)

    def _add_tool_button(self, parent, text, command, width=None):
        # 按文字自然宽度 + padding 自适应，不再用字符数估算宽度
        # width=0 取消 ttk 默认的 11 字符最小宽，让按钮按文字自适应
        btn = ttk.Button(parent, text=text, command=command, padding=(8, 2), width=0)
        if hasattr(parent, "add_widget"):
            parent.add_widget(btn)
        else:
            btn.pack(side="left", padx=2, pady=4)
        self.buttons[text] = btn
        return btn

    def _build_toolbar(self):
        palette = self.palette
        bar = bind_colors(tk.Frame(self.root, bg=palette["toolbar_bg"]),
                          palette, "toolbar_bg")
        bar.pack(side="top", fill="x")
        self.toolbar_frame = bar

        # 右侧动作按钮固定靠右，永远可见，不参与换行
        right = bind_colors(tk.Frame(bar, bg=palette["toolbar_bg"]),
                            palette, "toolbar_bg")
        right.pack(side="right", padx=(4, 10), pady=6)
        export_btn = ttk.Button(right, text="导出 .md 文件",
                                command=self.export_document, padding=(10, 3), width=0)
        export_btn.pack(side="right", padx=4)
        self.buttons["导出 .md 文件"] = export_btn
        copy_btn = ttk.Button(right, text="一键复制",
                              command=self.copy_all, padding=(10, 3), width=0)
        copy_btn.pack(side="right", padx=4)
        self.buttons["一键复制"] = copy_btn

        # 左侧语法按钮容器：流式自动换行
        flow = bind_colors(FlowFrame(bar, bg=palette["toolbar_bg"], spacing=3),
                           palette, "toolbar_bg")
        flow.pack(side="left", fill="x", expand=True, padx=(10, 0), pady=6)
        self.tool_flow = flow

        flow.add_widget(bind_colors(ttk.Label(flow, text="语法：",
                                              font=(FONT_CN, 10, "bold")),
                                    palette, "toolbar_bg", "text_fg"))

        specs = [
            ("H1", lambda: self.apply_line_prefix("# ")),
            ("H2", lambda: self.apply_line_prefix("## ")),
            ("H3", lambda: self.apply_line_prefix("### ")),
            ("H4", lambda: self.apply_line_prefix("#### ")),
            ("H5", lambda: self.apply_line_prefix("##### ")),
            ("H6", lambda: self.apply_line_prefix("###### ")),
            ("加粗", lambda: self.wrap_selection("**", "**", "加粗文字")),
            ("斜体", lambda: self.wrap_selection("*", "*", "斜体文字")),
            ("删除线", lambda: self.wrap_selection("~~", "~~", "删除线")),
            ("行内代码", lambda: self.wrap_selection("`", "`", "code")),
            ("脚注", self.insert_footnote),
            ("代码块", self.insert_code_block),
            ("无序列表", lambda: self.apply_line_prefix("- ")),
            ("有序列表", lambda: self.apply_line_prefix("1. ", numbered=True)),
            ("任务列表", lambda: self.apply_line_prefix("- [ ] ")),
            ("引用", lambda: self.apply_line_prefix("> ")),
            ("链接", self.insert_link),
            ("图片链接", self.insert_image),
            ("表格", self.insert_table_template),
            ("分割线", self.insert_hr),
        ]
        for text, command in specs:
            btn = ttk.Button(flow, text=text, command=command, padding=(7, 2), width=0)
            flow.add_widget(btn)
            self.buttons[text] = btn

    def _build_body(self):
        palette = self.palette
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(side="top", fill="both", expand=True, padx=8, pady=6)
        self._sash_manual = False
        self._sash_job = None
        self._sash_last_width = -1
        paned.bind("<ButtonRelease-1>", self._on_sash_drag, add="+")
        paned.bind("<Configure>", self._on_paned_configure, add="+")
        self.paned = paned

        # 左：命令速查录入
        left = ttk.LabelFrame(paned, text=" ① 命令速查录入（每行：命令 + 说明） ")
        paned.add(left, weight=1)

        hint = ("每行一条命令，命令与说明之间可用 Tab、| 、→ 或两个空格分隔。\n"
                "示例：git status | 查看工作区状态")
        left_head = ttk.Frame(left)
        left_head.pack(fill="x", padx=8, pady=(6, 4))
        self._make_hide_button(left_head, "left").pack(side="right", padx=(6, 0))
        bind_colors(ttk.Label(left_head, text=hint, justify="left",
                              font=(FONT_CN, 9)),
                    palette, None, "hint_fg").pack(side="left", fill="x", expand=True)

        # 先为底部按钮行保留空间，避免窗口变矮时按钮被挤掉
        btn_row = bind_colors(
            FlowFrame(left, spacing=3, bg=palette["panel_bg"]),
            palette, "panel_bg")
        btn_row.pack(side="bottom", fill="x", padx=8, pady=(4, 8))

        wrap = ttk.Frame(left)
        wrap.pack(fill="both", expand=True, padx=8)
        self.cmd_text = bind_colors(
            tk.Text(wrap, height=12, width=24, wrap="none", undo=True,
                    font=(FONT_MONO, 10), relief="solid",
                    borderwidth=1, bg=palette["text_bg"],
                    fg=palette["text_fg"],
                    insertbackground=palette["insert_bg"],
                    selectbackground=palette["select_bg"],
                    selectforeground=palette["select_fg"]),
            palette, "text_bg", "text_fg")
        cmd_scroll = ttk.Scrollbar(wrap, orient="vertical",
                                   command=self.cmd_text.yview)
        self.cmd_text.configure(yscrollcommand=cmd_scroll.set)
        self.cmd_text.pack(side="left", fill="both", expand=True)
        cmd_scroll.pack(side="right", fill="y")

        for text, command in [
            ("生成表格", lambda: self.generate_from_commands("table")),
            ("生成代码清单", lambda: self.generate_from_commands("code")),
            ("生成列表", lambda: self.generate_from_commands("list")),
        ]:
            self._add_tool_button(btn_row, text, command)
        for text, command in [
            ("载入示例", self.load_sample_commands),
            ("清空", self.clear_commands),
        ]:
            btn = ttk.Button(btn_row, text=text, command=command, padding=(8, 2), width=0)
            btn_row.add_widget(btn)
            self.buttons[text] = btn

        # 中：Markdown 编辑器
        middle = ttk.LabelFrame(paned, text=" ② Markdown 编辑器 ")
        paned.add(middle, weight=2)
        mid_head = ttk.Frame(middle)
        mid_head.pack(fill="x", padx=6, pady=(4, 0))
        self._make_hide_button(mid_head, "middle").pack(side="right")
        bind_colors(ttk.Label(mid_head, text="Markdown 源码（选中文字后点顶部语法按钮自动套用）",
                              font=(FONT_CN, 9)),
                    palette, None, "hint_fg").pack(side="left")
        mid_wrap = ttk.Frame(middle)
        mid_wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self.editor = bind_colors(
            tk.Text(mid_wrap, wrap="word", undo=True, maxundo=300,
                    width=34,
                    font=(FONT_CN, 10), relief="solid", borderwidth=1,
                    bg=palette["text_bg"], fg=palette["text_fg"],
                    insertbackground=palette["insert_bg"],
                    selectbackground=palette["select_bg"],
                    selectforeground=palette["select_fg"],
                    padx=10, pady=8, spacing1=2, spacing3=2),
            palette, "text_bg", "text_fg")
        ed_scroll = ttk.Scrollbar(mid_wrap, orient="vertical",
                                  command=self.editor.yview)
        self.editor.configure(yscrollcommand=ed_scroll.set)
        self.editor.pack(side="left", fill="both", expand=True)
        ed_scroll.pack(side="right", fill="y")
        self.editor.tag_configure("sel", background=palette["select_bg"],
                                  foreground=palette["select_fg"])
        # exportselection=False：点工具栏按钮时焦点转移，选区不被系统清空
        self.editor.configure(exportselection=False)
        self.editor.bind("<Button-1>", self._on_editor_click, add="+")
        self.editor.bind("<ButtonRelease-1>", self._remember_selection, add="+")
        self.editor.bind("<<Selection>>", self._remember_selection, add="+")

        # 右：实时预览
        right = ttk.LabelFrame(paned, text=" ③ 实时预览 ")
        paned.add(right, weight=2)
        right_head = ttk.Frame(right)
        right_head.pack(fill="x", padx=6, pady=(4, 0))
        self._make_hide_button(right_head, "right").pack(side="right")
        bind_colors(ttk.Label(right_head, text="所见即所得（编辑区改动后自动刷新）",
                              font=(FONT_CN, 9)),
                    palette, None, "hint_fg").pack(side="left")
        r_wrap = ttk.Frame(right)
        r_wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self.preview = bind_colors(
            tk.Text(r_wrap, wrap="word", relief="solid", borderwidth=1,
                    width=26,
                    bg=palette["text_bg"], fg=palette["text_fg"],
                    selectbackground=palette["select_bg"],
                    selectforeground=palette["select_fg"],
                    state="disabled", padx=12, pady=8,
                    cursor="arrow"),
            palette, "text_bg", "text_fg")
        pv_scroll = ttk.Scrollbar(r_wrap, orient="vertical",
                                  command=self.preview.yview)
        self.preview.configure(yscrollcommand=pv_scroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        pv_scroll.pack(side="right", fill="y")
        for name, options in preview_tag_options(palette):
            self.preview.tag_configure(name, **options)

        self._panel_widgets = {"left": left, "middle": middle, "right": right}
        self._apply_panel_state(initial=True)

    # ---------------- 主题（黑 / 白） ----------------
    def _apply_theme_style(self):
        """把 ttk 样式按当前调色板重设（clam 主题才能自由着色）。"""
        _init_ttk_style(self.root, self.palette)

    def apply_theme(self, name, persist=True):
        """切换主题并立即对整窗生效；persist=True 时写入 settings.json。"""
        if name not in THEMES:
            name = THEME_LIGHT
        self.theme = name
        self.palette = palette_of(name)
        self._apply_theme_style()
        try:
            self.root.configure(bg=self.palette["window_bg"])
        except Exception:
            pass
        apply_palette(self.root, self.palette)
        for menu in getattr(self, "_menus", []) or []:
            style_menu(menu, self.palette)
        self._restyle_texts()
        self._restyle_windows()
        self.refresh_preview()
        if persist:
            self.settings["theme"] = name
            self.save_layout()
        log_action("主题切换", name)
        return self.theme

    def _restyle_texts(self):
        """三个 Text 控件与编辑器选区、预览标签全部按新调色板重设。"""
        palette = self.palette
        for widget in (getattr(self, "cmd_text", None),
                       getattr(self, "editor", None),
                       getattr(self, "preview", None)):
            if widget is None:
                continue
            try:
                widget.configure(background=palette["text_bg"],
                                 foreground=palette["text_fg"],
                                 selectbackground=palette["select_bg"],
                                 selectforeground=palette["select_fg"])
            except Exception:
                pass
        for widget in (getattr(self, "cmd_text", None),
                       getattr(self, "editor", None)):
            if widget is None:
                continue
            try:
                widget.configure(insertbackground=palette["insert_bg"])
            except Exception:
                pass
        editor = getattr(self, "editor", None)
        if editor is not None:
            try:
                editor.tag_configure("sel", background=palette["select_bg"],
                                     foreground=palette["select_fg"])
            except Exception:
                pass
        preview = getattr(self, "preview", None)
        if preview is not None:
            for tag, options in preview_tag_options(palette):
                try:
                    preview.tag_configure(tag, **options)
                except Exception:
                    pass

    def _restyle_windows(self):
        """设置窗口等次级窗口同步换肤。"""
        win = getattr(self, "settings_window", None)
        if win is not None and getattr(win, "alive", False):
            win.apply_theme()

    def open_settings(self):
        """打开「设置」窗口（单例，重复打开只置顶）。"""
        if self.settings_window is not None and getattr(self.settings_window, "alive", False):
            try:
                self.settings_window.lift()
                self.settings_window.focus_force()
                return
            except Exception:
                self.settings_window = None
        self.settings_window = SettingsWindow(self)
        log_action("打开设置", "设置窗口")

    # ---------------- 面板显隐与配置持久化 ----------------
    def _make_hide_button(self, parent, key):
        """每个面板头部右上角的「隐藏」按钮。"""
        btn = ttk.Button(parent, text="隐藏", padding=(6, 1), width=0,
                         command=lambda: self.toggle_panel(key, False))
        self._panel_buttons[key] = btn
        return btn

    def visible_panels(self):
        return [k for k in PANEL_KEYS if self._panel_visible.get(k, True)]

    def _apply_panel_state(self, initial=False):
        """按 _panel_visible 把面板实际 add/forget 到 PanedWindow，保持原有顺序。"""
        paned = self.paned
        for key in PANEL_KEYS:
            widget = self._panel_widgets.get(key)
            if widget is None:
                continue
            shown = bool(self._panel_visible.get(key, True))
            try:
                managed = str(widget) in paned.panes()
            except Exception:
                managed = False
            if shown and not managed:
                index = 0
                for prev in PANEL_KEYS:
                    if prev == key:
                        break
                    if self._panel_visible.get(prev, True):
                        index += 1
                try:
                    count = len(paned.panes())
                except Exception:
                    count = 0
                if index >= count:
                    # ttk.Panedwindow.insert 的 index 必须落在现有从属窗口范围内，
                    # 追加到末尾须用 add，否则抛 "Slave index N out of bounds"
                    paned.add(widget, weight=PANEL_WEIGHTS[key])
                else:
                    paned.insert(index, widget, weight=PANEL_WEIGHTS[key])
            elif not shown and managed:
                paned.forget(widget)
        for key in PANEL_KEYS:
            var = self._panel_vars.get(key)
            if var is not None:
                try:
                    var.set(bool(self._panel_visible.get(key, True)))
                except Exception:
                    pass
        if not initial:
            # 面板数量变化 → 重新按可见面板分配比例
            self._sash_manual = False
            self._sash_last_width = -1
        self._schedule_ratio(60 if initial else 30)

    def _schedule_ratio(self, delay=60):
        if self._sash_job is not None:
            try:
                self.root.after_cancel(self._sash_job)
            except Exception:
                pass
        self._sash_job = self.root.after(delay, self._apply_sash_ratio)

    def toggle_panel(self, key, visible=None):
        """切换面板显隐：至少保留一个面板，隐藏最后一个会被阻止并提示。"""
        if key not in PANEL_KEYS:
            return
        current = bool(self._panel_visible.get(key, True))
        target = (not current) if visible is None else bool(visible)
        if target == current:
            return
        if not target and len(self.visible_panels()) <= 1:
            var = self._panel_vars.get(key)
            if var is not None:
                try:
                    var.set(True)
                except Exception:
                    pass
            self.status_var.set("至少保留一个面板，已阻止隐藏最后一个面板")
            log_action("面板显隐", "阻止隐藏最后一个面板：%s" % key)
            messagebox.showinfo(
                "无法隐藏",
                "三栏至少需要保留一个面板可见。\n"
                "如需腾出空间，请先显示另一个面板（Ctrl+1/2/3 或「视图」菜单）再隐藏当前面板。",
                parent=self.root)
            return
        self._panel_visible[key] = target
        self._apply_panel_state()
        name = PANEL_TITLES.get(key, key)
        self.status_var.set("%s已%s（Ctrl+%d 可再次切换）"
                            % (name, "显示" if target else "隐藏",
                               PANEL_KEYS.index(key) + 1))
        log_action("面板显隐", "%s -> %s" % (name, "显示" if target else "隐藏"))
        self.save_layout()

    def show_all_panels(self):
        for key in PANEL_KEYS:
            self._panel_visible[key] = True
        self._apply_panel_state()
        self.status_var.set("三个面板已全部显示")
        log_action("面板显隐", "全部显示")
        self.save_layout()

    # ---------------- 配置持久化 ----------------
    def _geometry_ok(self, geom):
        """判断保存的窗口几何是否可用（尺寸不小于最小窗口、位置仍落在屏幕附近）。"""
        try:
            geom = geom.strip()
            m = re.match(r"^(\d{3,5})x(\d{3,5})([+-]-?\d{1,5})([+-]-?\d{1,5})$", geom)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                x, y = int(m.group(3)), int(m.group(4))
            else:
                m2 = re.match(r"^(\d{3,5})x(\d{3,5})$", geom)
                if not m2:
                    return False
                w, h = int(m2.group(1)), int(m2.group(2))
                x = y = None
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            if w < 940 or h < 620:
                return False
            if x is not None:
                if x + 120 < 0 or y + 60 < 0 or x > sw - 120 or y > sh - 60:
                    return False
                if w > sw + 200 or h > sh + 200:
                    return False
            return True
        except Exception:
            return False

    def _current_geometry(self):
        try:
            geo = self.root.geometry()
            m = re.match(r"^(\d{3,5})x(\d{3,5})([+-]-?\d{1,5})([+-]-?\d{1,5})$", geo)
            if m:
                return geo
            m2 = re.match(r"^(\d{3,5})x(\d{3,5})$", geo)
            if m2:
                return "%sx%s+%d+%d" % (m2.group(1), m2.group(2),
                                        self.root.winfo_x(), self.root.winfo_y())
        except Exception:
            pass
        return ""

    def current_sash(self):
        """当前分隔条位置（只取可见面板之间的分隔条）。"""
        values = []
        try:
            visible = self.visible_panels()
            for idx in range(max(0, len(visible) - 1)):
                values.append(int(self.paned.sashpos(idx)))
        except Exception:
            return []
        return values

    def save_layout(self):
        """把当前面板显隐 / 窗口几何 / 分隔条 / 主题写入 settings.json。"""
        self.settings["panels"] = dict(self._panel_visible)
        self.settings["theme"] = self.theme
        geo = self._current_geometry()
        if geo:
            self.settings["geometry"] = geo
        sash = self.current_sash()
        if len(sash) == len(self.visible_panels()) - 1:
            self.settings["sash"] = sash
            try:
                self.settings["sash_width"] = int(self.paned.winfo_width())
            except Exception:
                pass
        return save_settings(self.settings)

    def on_close(self):
        """关闭窗口：先确认未保存修改，再落盘布局、取消延迟任务并销毁窗口。"""
        if not self.confirm_unsaved("退出"):
            return
        try:
            self.save_layout()
        except Exception:
            pass
        for attr in ("_sash_job", "_save_job"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        log_action("退出", "面板 %s | 尺寸 %s" % (
            ",".join(self.visible_panels()), self.settings.get("geometry", "")))
        try:
            self.root.destroy()
        except Exception:
            pass

    def _restore_layout(self):
        """首次布局完成后恢复上次的分隔条位置；无有效记录则按比例自动分配。"""
        try:
            saved = list(self.settings.get("sash") or [])
            visible = self.visible_panels()
            if saved and len(saved) == len(visible) - 1 and self._apply_saved_sash(saved, visible):
                self._sash_manual = True
                self._sash_last_width = -1
            else:
                self._sash_manual = False
                self._apply_sash_ratio()
        except Exception as exc:
            log_action("布局恢复失败", repr(exc))

    def _apply_saved_sash(self, saved, visible):
        """把历史分隔条位置按当前面板总宽等比换算后落位。

        历史记录是绝对像素坐标，若本次窗口尺寸与上次不同（如用户改了分辨率、
        或换了 DPI 缩放），直接套用会把某个面板挤成负数/超宽。
        因此先按 sash_width→当前宽度等比缩放，再逐段校验最小宽度，
        任一不达标即返回 False，由调用方回退到比例分配。
        """
        total = self.paned.winfo_width()
        if total <= 160:
            return False
        saved_total = int(self.settings.get("sash_width") or 0)
        if saved_total <= 160:
            # 旧版配置没有记录宽度：按当前宽度等值处理，仅做最小宽度校验
            saved_total = total
        scale = float(total) / float(saved_total) if saved_total > 0 else 1.0
        positions = [int(round(v * scale)) for v in saved]
        prev = 0
        for idx, key in enumerate(visible[:-1]):
            if positions[idx] - prev < PANEL_MIN_WIDTH.get(key, 120):
                return False
            if positions[idx] >= total:
                return False
            prev = positions[idx]
        if total - prev < PANEL_MIN_WIDTH.get(visible[-1], 160):
            return False
        for idx, pos in enumerate(positions):
            try:
                self.paned.sashpos(idx, pos)
            except Exception:
                return False
        return True

    def _on_sash_drag(self, event=None):
        # 用户手动拖过分隔条后，不再自动按比例重置，并延迟落盘
        self._sash_manual = True
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(400, self.save_layout)

    def _on_paned_configure(self, event=None):
        if getattr(self, "_sash_manual", False):
            return
        try:
            width = self.paned.winfo_width()
        except Exception:
            return
        if width == self._sash_last_width:
            return
        self._sash_last_width = width
        if self._sash_job is not None:
            try:
                self.root.after_cancel(self._sash_job)
            except Exception:
                pass
        self._sash_job = self.root.after(60, self._apply_sash_ratio)

    def _apply_sash_ratio(self):
        """按「当前可见面板」分配分隔条位置：3 栏 18%/30%/26%，2 栏按缺省主次分配。"""
        self._sash_job = None
        try:
            paned = self.paned
            visible = self.visible_panels()
            total = paned.winfo_width()
            if total <= 160 or not visible:
                return
            if len(visible) == 1:
                return  # 单面板自动占满，无需设置分隔条
            if len(visible) == 2:
                first, second = visible
                if first == "left" and second == "middle":
                    s1 = max(170, int(total * 0.24))
                    s1 = min(s1, total - 200)
                elif first == "left" and second == "right":
                    s1 = max(170, int(total * 0.30))
                    s1 = min(s1, total - 220)
                else:  # middle + right
                    s1 = total - max(int(total * 0.34), 280)
                    s1 = max(s1, 200)
                paned.sashpos(0, max(120, s1))
                return
            s1 = max(170, int(total * 0.18))
            right_need = max(int(total * 0.26), 260)
            mid_need = max(int(total * 0.30), 320)
            s2 = total - right_need
            if s2 < s1 + mid_need:
                s2 = s1 + mid_need
            if s2 > total - 120:
                s2 = total - 120
            paned.sashpos(0, s1)
            paned.sashpos(1, s2)
        except Exception:
            pass

    def _build_statusbar(self):
        palette = self.palette
        bar = bind_colors(tk.Frame(self.root, bg=palette["statusbar_bg"], height=26),
                          palette, "statusbar_bg")
        bar.pack(side="bottom", fill="x")
        self.statusbar_frame = bar
        bind_colors(tk.Label(bar, textvariable=self.status_var,
                             bg=palette["statusbar_bg"], fg=palette["status_fg"],
                             font=(FONT_CN, 9), anchor="w"),
                    palette, "statusbar_bg", "status_fg").pack(side="left", padx=10)
        bind_colors(tk.Label(bar, textvariable=self.stat_var,
                             bg=palette["statusbar_bg"], fg=palette["muted_fg"],
                             font=(FONT_CN, 9), anchor="e"),
                    palette, "statusbar_bg", "muted_fg").pack(side="right", padx=10)
        # 面板显隐复选：与「视图」菜单、Ctrl+1/2/3 等价的便捷入口
        toggles = bind_colors(tk.Frame(bar, bg=palette["statusbar_bg"]),
                              palette, "statusbar_bg")
        toggles.pack(side="right", padx=(0, 14))
        bind_colors(tk.Label(toggles, text="面板：", bg=palette["statusbar_bg"],
                             fg=palette["muted_fg"], font=(FONT_CN, 9)),
                    palette, "statusbar_bg", "muted_fg").pack(side="left")
        for key in PANEL_KEYS:
            cb = ttk.Checkbutton(toggles, text=PANEL_SHORT_TITLES[key],
                                 variable=self._panel_vars[key],
                                 command=lambda k=key: self.toggle_panel(k),
                                 takefocus=False, style="Status.TCheckbutton")
            cb.pack(side="left", padx=(3, 0))
            self._panel_checks[key] = cb

    def _bind_shortcuts(self):
        self.root.bind("<Control-n>", lambda e: self.new_document())
        self.root.bind("<Control-o>", lambda e: self.open_document())
        self.root.bind("<Control-s>", lambda e: self.save_current())
        self.root.bind("<Control-Shift-S>", lambda e: self.export_document())
        self.root.bind("<Control-Shift-s>", lambda e: self.export_document())
        self.root.bind("<Control-Shift-C>", lambda e: self.copy_all())
        self.root.bind("<Control-Shift-c>", lambda e: self.copy_all())
        self.root.bind("<F1>", lambda e: self.show_help())
        self.root.bind("<Control-comma>", lambda e: self.open_settings())
        self.root.bind("<Control-,>", lambda e: self.open_settings())
        for idx, key in enumerate(PANEL_KEYS):
            self.root.bind("<Control-Key-%d>" % (idx + 1),
                           lambda e, k=key: self.toggle_panel(k))
        self.editor.bind("<<Modified>>", self._on_editor_modified)
        self.editor.bind("<KeyRelease>", lambda e: self.update_stats())

    def _on_editor_modified(self, _event=None):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self._sync_dirty_state()
            self.schedule_preview()
            self.update_stats()

    # ---------------- 预览与统计 ----------------
    def schedule_preview(self, delay=220):
        if self.preview_job is not None:
            try:
                self.root.after_cancel(self.preview_job)
            except Exception:
                pass
        self.preview_job = self.root.after(delay, self.refresh_preview)

    def refresh_preview(self):
        self.preview_job = None
        try:
            content = self.editor.get("1.0", "end-1c")
            render_markdown(self.preview, content)
            self.update_stats()
        except Exception as exc:  # 预览出错不影响编辑
            log_action("预览异常", repr(exc))
            self.status_var.set("预览渲染失败：%s" % exc)

    def update_stats(self):
        try:
            content = self.editor.get("1.0", "end-1c")
            lines = content.count("\n") + 1
            self.stat_var.set("字符 %d · 行 %d" % (len(content), lines))
        except Exception:
            pass

    # ---------------- 编辑器操作 ----------------
    def _editor_insert(self, text, replace_selection=False):
        """在光标处插入文本；replace_selection=True 时用 text 替换选区。返回插入起点。"""
        self.editor.focus_set()
        target = self.editor.index("insert")
        if replace_selection:
            sel = self._editor_selection()
            if sel:
                target = sel[0]
                self._drop_selection_tag()
                self.editor.delete(sel[0], sel[1])
                self.editor.mark_set("insert", target)
        self.editor.insert(target, text)
        self._last_selection = None
        self.schedule_preview()
        self.update_stats()
        return target

    # ---- 选区获取（兼容"点按钮抢焦点导致选区高亮消失"） ----
    def _drop_selection_tag(self):
        try:
            self.editor.tag_remove("sel", "1.0", "end")
        except tk.TclError:
            pass

    def _on_editor_click(self, _event=None):
        # 鼠标按下先作废记忆选区；拖动产生的新选区由 ButtonRelease / Selection 事件重新记录
        self._last_selection = None

    def _span_from(self, start, end):
        """规范化选区区间：末尾落在行首时回退一个字符（避免把换行带进模板），
        空白选区视为无效。返回 (start, end, text) 或 None。"""
        try:
            if start != end and int(str(end).split(".")[1]) == 0:
                end = self.editor.index("%s-1c" % end)
            if self.editor.compare(start, ">=", end):
                return None
            text = self.editor.get(start, end)
        except (tk.TclError, ValueError, IndexError):
            return None
        if not text or not text.strip():
            return None
        return start, end, text

    def _remember_selection(self, _event=None):
        try:
            ranges = self.editor.tag_ranges("sel")
        except tk.TclError:
            ranges = ()
        if ranges:
            self._last_selection = self._span_from(self.editor.index(ranges[0]),
                                                   self.editor.index(ranges[1]))
        else:
            self._last_selection = None

    def _editor_selection(self):
        """返回 (start, end, text)；无有效选区（含纯空白选区）返回 None。"""
        try:
            ranges = self.editor.tag_ranges("sel")
        except tk.TclError:
            ranges = ()
        if ranges:
            span = self._span_from(self.editor.index(ranges[0]),
                                   self.editor.index(ranges[1]))
            if span:
                self._last_selection = span
                return span
        remembered = self._last_selection
        if remembered:
            start, end, text = remembered
            try:
                if text and self.editor.get(start, end) == text:
                    return start, end, text
            except tk.TclError:
                pass
            self._last_selection = None
        return None

    def _replace_range(self, start, end, new_text, caret_offset=None,
                       select=None):
        """用 new_text 替换 [start, end)，可选设置光标 / 选区（均为相对 start 的字符偏移）。"""
        self._drop_selection_tag()
        self.editor.delete(start, end)
        self.editor.insert(start, new_text)
        if select:
            s_off, e_off = select
            s_idx = "%s+%dc" % (start, s_off)
            self.editor.tag_add("sel", s_idx, "%s+%dc" % (start, e_off))
            self.editor.mark_set("insert", s_idx)
        else:
            off = len(new_text) if caret_offset is None else caret_offset
            self.editor.mark_set("insert", "%s+%dc" % (start, off))
        self._last_selection = None
        self.editor.focus_set()
        self.editor.see("insert")
        self.schedule_preview()
        self.update_stats()

    def wrap_selection(self, prefix, suffix, placeholder=""):
        self.editor.focus_set()
        sel = self._editor_selection()
        if sel:
            start, end, selected = sel
            # 包裹后仍选中原文内部，便于继续叠加其它语法
            self._replace_range(start, end, prefix + selected + suffix,
                                select=(len(prefix),
                                        len(prefix) + len(selected)))
            log_action("语法插入", "包裹选中文本 %s（%d 字符）" % (prefix, len(selected)))
            return
        start = self.editor.index("insert")
        self.editor.insert("insert", prefix + placeholder + suffix)
        self.editor.tag_add("sel", "%s+%dc" % (start, len(prefix)),
                            "%s+%dc" % (start, len(prefix) + len(placeholder)))
        self.editor.mark_set("insert", "%s+%dc" % (start, len(prefix)))
        self._last_selection = None
        log_action("语法插入", prefix)
        self.schedule_preview()
        self.update_stats()

    def apply_line_prefix(self, prefix, numbered=False):
        self.editor.focus_set()
        sel = self._editor_selection()
        if sel:
            start = self.editor.index("%s linestart" % sel[0])
            end = self.editor.index("%s lineend" % sel[1])
        else:
            start = self.editor.index("insert linestart")
            end = self.editor.index("insert lineend")
        block = self.editor.get(start, end)
        new_lines = []
        for idx, line in enumerate(block.split("\n")):
            mark = ("%d. " % (idx + 1)) if numbered else prefix
            if line.startswith(mark):
                new_lines.append(line[len(mark):])
            else:
                stripped = re.sub(r"^(#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)",
                                  "", line)
                new_lines.append(mark + stripped)
        new_block = "\n".join(new_lines)
        if sel:
            # 处理后保持选中，便于连续套用其它语法
            self._drop_selection_tag()
            self.editor.delete(start, end)
            self.editor.insert(start, new_block)
            self.editor.tag_add("sel", start, "%s+%dc" % (start, len(new_block)))
            self.editor.mark_set("insert", start)
            self._last_selection = None
        else:
            self.editor.delete(start, end)
            self.editor.insert(start, new_block)
            self.editor.mark_set("insert", start)
        log_action("语法插入", "行首前缀 %r%s" % (prefix, "（含选中文本）" if sel else ""))
        self.schedule_preview()
        self.update_stats()

    def insert_code_block(self):
        sel = self._editor_selection()
        if sel:
            start, end, selected = sel
            self._replace_range(start, end, "```\n" + selected + "\n```",
                                caret_offset=4 + len(selected))
            log_action("语法插入", "代码块（选中 %d 字符作内容）" % len(selected))
            return
        start = self._editor_insert("```\n\n```")
        self.editor.mark_set("insert", "%s+4c" % start)
        log_action("语法插入", "代码块")

    def insert_link(self):
        sel = self._editor_selection()
        url = "https://example.com"
        if sel:
            start, end, selected = sel
            text = "[%s](%s)" % (selected, url)
            self._replace_range(start, end, text,
                                select=(len(selected) + 3,
                                        len(selected) + 3 + len(url)))
            log_action("语法插入", "链接（选中文本作标题，地址待填）")
            return
        start = self._editor_insert("[链接文字](%s)" % url)
        begin = "%s+1c" % start
        self.editor.tag_add("sel", begin, "%s+4c" % begin)
        self.editor.mark_set("insert", begin)
        self._last_selection = None
        log_action("语法插入", "链接")

    def insert_image(self):
        sel = self._editor_selection()
        if sel:
            start, end, selected = sel
            # 选中文本作为图片地址；光标停在 alt 说明文字处（"![" 之后）
            self._replace_range(start, end, "![](%s)" % selected, caret_offset=2)
            log_action("语法插入", "图片链接（选中文本作地址）")
            return
        self._editor_insert("![图片说明](https://example.com/image.png)")
        log_action("语法插入", "图片链接")

    def insert_table_template(self):
        sel = self._editor_selection()
        if sel:
            self._build_table_from_selection(sel)
            return
        tpl = ("| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n| 内容 | 内容 | 内容 |\n")
        self._editor_insert(tpl)
        log_action("语法插入", "表格模板")

    def _build_table_from_selection(self, sel):
        """把选中文本解析成表格：按行拆行、按 Tab/竖线/多空格拆列。"""
        start, end, selected = sel
        rows = [ln for ln in selected.split("\n") if ln.strip()]
        if not rows:
            return
        parsed = []
        for line in rows:
            if "\t" in line:
                cells = line.split("\t")
            elif "|" in line:
                cells = line.split("|")
            elif re.search(r"\s{2,}", line):
                cells = re.split(r"\s{2,}", line)
            else:
                cells = [line]
            cells = [c.strip() for c in cells]
            while cells and cells[0] == "":
                cells.pop(0)
            while cells and cells[-1] == "":
                cells.pop()
            parsed.append(cells or [line.strip()])
        cols = max(2, max(len(r) for r in parsed))
        header = ["列%d" % (i + 1) for i in range(cols)]
        lines = ["| " + " | ".join(header) + " |",
                 "| " + " | ".join(["---"] * cols) + " |"]
        for r in parsed:
            filled = r + ["内容"] * (cols - len(r))
            lines.append("| " + " | ".join(c.replace("|", "\\|")
                                           for c in filled) + " |")
        table = "\n".join(lines) + "\n"
        self._replace_range(start, end, table)
        log_action("语法插入",
                   "表格（选中 %d 行 → %d 列）" % (len(parsed), cols))

    def insert_hr(self):
        sel = self._editor_selection()
        if sel:
            # 选中文本时：用分割线代码替换选中内容
            start, end, selected = sel
            self._replace_range(start, end, "---")
            log_action("语法插入", "分割线（替换选中 %d 字符）" % len(selected))
            return
        self._editor_insert("\n---\n\n")
        log_action("语法插入", "分割线")

    def _next_footnote_index(self):
        """扫描全文已有的 [^N] 脚注标记，返回下一个可用编号。"""
        try:
            content = self.editor.get("1.0", "end-1c")
        except tk.TclError:
            return 1
        used = [int(n) for n in re.findall(r"\[\^(\d+)\]", content)]
        return (max(used) + 1) if used else 1

    def insert_footnote(self):
        index = self._next_footnote_index()
        marker = "[^%d]: " % index
        sel = self._editor_selection()
        if sel:
            start, end, selected = sel
            # 选中文本作为脚注说明，整体替换为脚注定义行
            self._replace_range(start, end, marker + selected)
            log_action("语法插入", "脚注（选中文本作脚注内容，编号 %d）" % index)
            return
        placeholder = "脚注内容"
        start = self._editor_insert(marker + placeholder)
        offset = len(marker)
        self.editor.tag_add("sel", "%s+%dc" % (start, offset),
                            "%s+%dc" % (start, offset + len(placeholder)))
        self.editor.mark_set("insert", "%s+%dc" % (start, offset))
        self._last_selection = None
        log_action("语法插入", "脚注（编号 %d）" % index)
        self.schedule_preview()
        self.update_stats()

    def select_all(self):
        self.editor.tag_add("sel", "1.0", "end-1c")
        self.editor.mark_set("insert", "1.0")
        log_action("全选", "")

    # ---------------- 命令速查 -> Markdown ----------------
    def _command_items(self):
        return parse_command_lines(self.cmd_text.get("1.0", "end-1c"))

    def generate_from_commands(self, mode):
        items = self._command_items()
        if not items:
            self.status_var.set("请先在左侧录入命令（每行：命令 + 说明）")
            messagebox.showinfo(
                "提示",
                "左侧「命令速查录入」还没有有效内容。\n\n"
                "每行录一条命令，命令与说明之间用 Tab、| 、→ 或两个空格分隔，例如：\n"
                "git status | 查看工作区状态",
                parent=self.root)
            return
        if mode == "table":
            block = build_markdown_table(items)
            action = "生成 Markdown 表格"
        elif mode == "code":
            block = build_code_list(items)
            action = "生成代码清单"
        else:
            block = build_bullet_list(items)
            action = "生成 Markdown 列表"

        current = self.editor.get("1.0", "end-1c")
        prefix = "\n\n" if current.strip() and not current.endswith("\n\n") else ""
        self.editor.insert("end", prefix + block)
        self.editor.see("end")
        self.schedule_preview()
        self.update_stats()
        self.status_var.set("已生成「%s」，共 %d 条命令，可在右侧实时预览"
                            % (action, len(items)))
        log_action(action, "%d 条" % len(items))

    def load_sample_commands(self):
        sample = (
            "git status\t查看工作区状态\n"
            "git log --oneline -10\t单行查看最近 10 条提交\n"
            "git checkout -b feature/login\t创建并切换到新分支\n"
            "npm run build\t构建前端生产包\n"
            "docker compose up -d\t后台启动容器编排\n"
            "pip install -r requirements.txt\t安装 Python 依赖\n"
            "Get-Process | Sort-Object CPU -Descending\t按 CPU 排序查看进程\n"
        )
        self.cmd_text.delete("1.0", "end")
        self.cmd_text.insert("1.0", sample)
        self.status_var.set("已载入 7 条示例命令")
        log_action("载入示例命令", "7 条")

    def clear_commands(self):
        self.cmd_text.delete("1.0", "end")
        self.status_var.set("已清空命令录入区")
        log_action("清空命令录入区", "")

    # ---------------- 文件与剪贴板 ----------------
    # ---------------- 未保存修改与标题 ----------------
    def _title_text(self):
        """窗口标题：应用名 + 版本 + 文件名 + 未保存标记。"""
        text = "%s v%s" % (APP_NAME, APP_VERSION)
        if self.current_file:
            text += " - %s" % os.path.basename(self.current_file)
        if self._dirty:
            text += DIRTY_TITLE_MARK
        return text

    def _refresh_title(self):
        try:
            self.root.title(self._title_text())
        except Exception:
            pass

    def _activate_front(self):
        """把主窗口还原并提到最前（双击转交时用）。"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _sync_dirty_state(self):
        """按「当前内容 vs 上次保存快照」判定是否有未保存修改。"""
        try:
            current = self.editor.get("1.0", "end-1c")
        except Exception:
            return
        dirty = current != self._base_content
        if dirty != self._dirty:
            self._dirty = dirty
            self._refresh_title()

    def _mark_saved(self):
        """内容已落盘或已重新载入：刷新快照并清掉未保存标记。"""
        try:
            self._base_content = self.editor.get("1.0", "end-1c")
        except Exception:
            self._base_content = ""
        self._dirty = False
        self._refresh_title()

    def _doc_display_name(self):
        if self.current_file:
            return os.path.basename(self.current_file)
        return "未命名文档"

    def confirm_unsaved(self, action="继续"):
        """有未保存修改时弹确认框；返回 True 表示可以继续。

        · 是：先保存（已打开的文件直接覆盖，未命名文档弹另存为）
        · 否：不保存，直接放弃
        · 取消：中止本次操作，留在当前文档
        """
        self._sync_dirty_state()
        if not self._dirty:
            return True
        ans = messagebox.askyesnocancel(
            "有未保存的修改",
            "「%s」还有未保存的修改。\n\n"
            "· 是：保存后%s\n"
            "· 否：不保存，直接%s\n"
            "· 取消：留在当前文档" % (self._doc_display_name(), action, action),
            parent=self.root)
        if ans is None:
            log_action("取消操作", "%s | 用户选择留在当前文档" % action)
            self.status_var.set("已取消：%s" % action)
            return False
        if ans:
            ok = self.save_current()
            if not ok:
                log_action("保存未完成", "%s | 已中止" % action)
            return ok
        log_action("放弃未保存修改", action)
        return True

    def save_current(self):
        """保存当前文档：已有路径直接覆盖写回，未命名文档走另存为。返回是否成功。"""
        self._sync_dirty_state()
        if not self.current_file:
            return self.export_document()
        if not self._dirty:
            self.status_var.set("内容无变化，无需保存：%s" % self.current_file)
            return True
        content = self.editor.get("1.0", "end-1c")
        ok, err = self.save_to(self.current_file, content)
        if not ok:
            self.status_var.set("保存失败：%s" % err)
            messagebox.showerror("保存失败", "无法写入文件：\n%s" % err,
                                 parent=self.root)
            log_action("保存失败", "%s | %r" % (self.current_file, err))
            return False
        self._mark_saved()
        self.status_var.set("已保存：%s（%d 字符）" % (self.current_file, len(content)))
        log_action("保存文件", "%s | %d 字符" % (self.current_file, len(content)))
        return True

    def new_document(self):
        if not self.confirm_unsaved("新建空白文档"):
            return
        self.editor.delete("1.0", "end")
        self.editor.edit_reset()
        self._last_selection = None
        self.current_file = None
        self._mark_saved()
        self.schedule_preview()
        self.update_stats()
        self.status_var.set("已新建空白文档")
        log_action("新建文档", "")

    def load_path(self, path):
        """把指定 .md 文件读入编辑器。

        菜单「打开」、双击 .md 关联打开、单实例转发三条入口共用此方法，
        保证读取编码回退、标题刷新、预览调度的行为完全一致。
        若当前文档有未保存修改，先弹框确认；同一文件重复打开直接激活窗口。
        """
        if not path:
            return False
        path = os.path.abspath(path)
        if self.current_file and os.path.abspath(self.current_file) == path:
            self._activate_front()
            self.status_var.set("该文件已在当前窗口中打开：%s" % path)
            log_action("重复打开", path)
            return True
        if not self.confirm_unsaved("打开「%s」" % os.path.basename(path)):
            return False
        try:
            raw = None
            for enc in ("utf-8-sig", "utf-8", "gbk"):
                try:
                    with open(path, "r", encoding=enc) as fh:
                        raw = fh.read()
                    break
                except UnicodeDecodeError:
                    continue
            if raw is None:
                raise RuntimeError("无法识别文件编码")
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", raw)
            self._last_selection = None
            self.current_file = path
            self._mark_saved()
            self.schedule_preview()
            self.update_stats()
            self.status_var.set("已打开（%d 字符）：%s" % (len(raw), path))
            log_action("打开文件", path)
            return True
        except Exception as exc:
            log_action("打开文件失败", "%s | %r" % (path, exc))
            messagebox.showerror("打开失败", "无法打开文件：\n%s" % exc,
                                 parent=self.root)
            return False

    def open_document(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="打开 Markdown 文件",
            filetypes=[("Markdown 文件", "*.md *.markdown"), ("所有文件", "*.*")])
        if not path:
            return
        self.load_path(path)

    def export_document(self):
        content = self.editor.get("1.0", "end-1c")
        if not content.strip():
            self.status_var.set("编辑器为空，无法导出")
            messagebox.showinfo("提示", "编辑器内容为空，请先输入或生成 Markdown 内容。",
                                parent=self.root)
            return False
        default_name = self.current_file or os.path.join(
            os.path.dirname(self.current_file) if self.current_file else
            os.path.expanduser("~"),
            "爽哥命令速查_%s.md" % time.strftime("%Y%m%d_%H%M"))
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出 Markdown 文件",
            defaultextension=".md", initialfile=os.path.basename(default_name),
            filetypes=[("Markdown 文件", "*.md"), ("所有文件", "*.*")])
        if not path:
            return False
        ok, err = self.save_to(path, content)
        if ok:
            self.current_file = path
            self._mark_saved()
            self.status_var.set("已导出：%s（%d 字符）" % (path, len(content)))
            messagebox.showinfo("导出成功",
                                "Markdown 文件已保存到：\n%s" % path,
                                parent=self.root)
            log_action("导出成功", "%s | %d 字符" % (path, len(content)))
            return True
        else:
            self.status_var.set("导出失败：%s" % err)
            messagebox.showerror("导出失败", "无法写入文件：\n%s" % err,
                                 parent=self.root)
            log_action("导出失败", "%s | %r" % (path, err))
            return False

    @staticmethod
    def save_to(path, content):
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content if content.endswith("\n") else content + "\n")
            return True, ""
        except Exception as exc:
            return False, exc

    def copy_all(self):
        content = self.editor.get("1.0", "end-1c")
        if not content.strip():
            self.status_var.set("编辑器为空，无可复制内容")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()
        self.status_var.set("已复制到剪贴板（%d 字符）" % len(content))
        log_action("复制到剪贴板", "%d 字符" % len(content))

    # ---------------- 在线检查更新（v1.6.0） ----------------
    def _update_auto_check(self, delay=1500):
        """按配置开关安排 / 取消启动时的静默检查；设置窗口切换开关后立即生效。"""
        job = getattr(self, "_auto_update_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
            self._auto_update_job = None
        if self.settings.get("auto_check_update"):
            self._auto_update_job = self.root.after(
                delay, lambda: self.check_update(manual=False))

    def check_update(self, manual=True):
        """检查更新：manual=False 为启动时静默检查（仅在状态栏提示，绝不弹窗）。"""
        if getattr(self, "_update_busy", False):
            if manual:
                messagebox.showinfo("检查更新", "正在检查中，请稍候…", parent=self.root)
            return
        self._update_busy = True
        if manual:
            self.status_var.set("正在向 GitHub 检查最新版本…")
            log_action("检查更新", "手动触发")
        result = {}

        def worker():
            try:
                result["info"] = fetch_latest_release()
            except LookupError as exc:
                result["error"] = str(exc)
                result["no_release"] = True
            except Exception as exc:
                result["error"] = str(exc) or exc.__class__.__name__
            try:
                self.root.after(0, lambda: self._on_update_result(result, manual))
            except Exception:
                pass

        threading.Thread(target=worker, name="UpdateCheck", daemon=True).start()

    def _on_update_result(self, result, manual):
        """网络线程回到主线程后处理结果：弹窗（手动）或只更状态栏（静默）。"""
        self._update_busy = False
        info = result.get("info")
        error = result.get("error")
        if error:
            log_action("检查更新", "失败：%s" % error)
            if manual:
                self.status_var.set("检查更新失败")
                if result.get("no_release"):
                    messagebox.showinfo(
                        "检查更新",
                        "仓库暂未发布任何版本。\n\n源码与发布页：%s" % UPDATE_REPO_PAGE,
                        parent=self.root)
                else:
                    messagebox.showwarning(
                        "检查更新",
                        "检查失败：%s\n\n可直接访问发布页手动查看：\n%s"
                        % (error, UPDATE_PAGE),
                        parent=self.root)
            return
        latest = info.get("version") or "未知"
        relation = compare_version(APP_VERSION, latest)
        if relation == 1:
            log_action("检查更新", "发现新版本 v%s（当前 v%s）" % (latest, APP_VERSION))
            self.status_var.set("发现新版本 v%s，可在「帮助 → 检查更新」查看" % latest)
            if manual:
                UpdateDialog(self.root, self.palette, APP_VERSION, info=info)
        elif relation == 0:
            log_action("检查更新", "已是最新版本 v%s" % APP_VERSION)
            if manual:
                self.status_var.set("当前已是最新版本 v%s" % APP_VERSION)
                UpdateDialog(self.root, self.palette, APP_VERSION, info=info)
        else:
            log_action("检查更新", "线上版本 %s 低于当前 %s" % (latest, APP_VERSION))
            if manual:
                self.status_var.set("当前版本 v%s 高于线上 %s" % (APP_VERSION, latest))
                UpdateDialog(self.root, self.palette, APP_VERSION, info=info)

    # ---------------- 帮助 ----------------
    def show_about(self):
        dialog = AboutDialog(self.root, self.palette, self)
        self._about_dialog = dialog
        return dialog

    def show_help(self):
        readme = os.path.join(_app_base_dir(), "使用说明.md")
        if os.path.exists(readme):
            try:
                os.startfile(readme)  # noqa: S606
                log_action("打开使用说明", readme)
                return
            except Exception:
                pass
        messagebox.showinfo(
            "使用说明",
            "① 左侧录入命令（命令 + 说明，每行一条）\n"
            "② 点击「生成表格 / 生成代码清单 / 生成列表」写入编辑器\n"
            "③ 用顶部语法按钮快速插入 Markdown 语法\n"
            "④ 右侧实时预览，顶部「导出 .md 文件」保存，「一键复制」粘贴到任意位置\n"
            "⑤ 面板太挤：点各栏「隐藏」折叠，Ctrl+1/2/3 或「视图」菜单恢复（布局自动记忆）\n"
            "⑥ 「文件 → 设置…」(Ctrl+,) 可切换黑白主题、关联 .md 文件\n\n"
            "日志目录：%s\n反馈邮箱：%s" % (LOG_DIR, EMAIL),
            parent=self.root)

    def show_feedback_help(self):
        messagebox.showinfo(
            "日志与问题反馈",
            "程序会自动记录运行日志：\n%s\n\n"
            "遇到问题请把该日志作为附件发送至 %s。\n"
            "邮件标题建议：%s 问题反馈" % (LOG_FILE, EMAIL, APP_NAME),
            parent=self.root)
        log_action("查看反馈说明", LOG_FILE)

    # ---------------- 初始内容 ----------------
    def load_welcome(self):
        welcome = (
            "# 爽哥MD编辑工具\n"
            "\n"
            "> 左侧录入命令 → 点「生成表格」→ 右侧实时预览 → 顶部一键导出 .md\n"
            "\n"
            "> 小技巧：面板太挤时，点各栏右上角「隐藏」可折叠，Ctrl+1/2/3 或「视图」菜单随时恢复，"
            "下次启动自动沿用上次布局。\n"
            "\n"
            "> 小技巧：「文件 → 设置…」(Ctrl+,) 可切换黑白主题、把 .md 文件关联到本工具。\n"
            "\n"
            "> 小技巧：先在编辑区选中文字，再点顶部「图片链接 / 链接 / 加粗 / 代码块」等按钮，"
            "选中内容会自动套进模板；未选中时插入空模板。\n"
            "\n"
            "## 常用命令速查\n"
            "\n"
            "| 命令 | 说明 |\n"
            "| --- | --- |\n"
            "| `git status` | 查看工作区状态 |\n"
            "| `git log --oneline -10` | 单行查看最近 10 条提交 |\n"
            "| `npm run build` | 构建前端生产包 |\n"
            "\n"
            "## 语法速记\n"
            "\n"
            "- **加粗**：`**文字**`\n"
            "- *斜体*：`*文字*`\n"
            "- 行内代码：`` `code` ``\n"
            "- 任务列表：`- [ ] 待办`\n"
            "- 链接：[Marvis 官网](https://marvis.qq.com)\n"
            "\n"
            "### 代码块示例\n"
            "\n"
            "```bash\n"
            "npm install\n"
            "npm run build\n"
            "```\n"
            "\n"
            "---\n"
            "\n"
            "制作人：杨爽　|　AI 工具：Marvis　|　反馈邮箱：675680672@qq.com\n"
        )
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", welcome)
        self.editor.edit_reset()
        self._last_selection = None
        self._mark_saved()
        self.update_stats()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _enable_dpi_awareness():
    """声明 DPI 感知，避免 125%/150% 缩放下系统位图放大导致
    字体模糊与按钮文字裁断。"""
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _enable_dpi_awareness()
    _install_excepthook()
    root = tk.Tk()
    app = MdToolApp(root)
    root.mainloop()
    return app


def _persist_asset(name):
    """把随包图标落盘到持久目录，避免把 onefile 的临时解包路径写进注册表。"""
    import shutil
    direct = os.path.join(_app_base_dir(), name)
    if os.path.exists(direct):
        return direct
    mei = getattr(sys, "_MEIPASS", None)
    src = os.path.join(mei, name) if mei else ""
    if not src or not os.path.exists(src):
        return ""
    base = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                        APP_NAME, "icons")
    dst = os.path.join(base, name)
    try:
        if (not os.path.exists(dst)) or os.path.getsize(dst) != os.path.getsize(src):
            os.makedirs(base, exist_ok=True)
            shutil.copy2(src, dst)
        return dst
    except Exception as exc:
        log_action("图标持久化失败", "%s -> %s（%r）" % (src, dst, exc))
        return ""


# ---------------------------------------------------------------------------
# 单实例守卫与文件转交（v1.4.0 新增）
#   目的：主程序已在运行时，双击关联的 .md 文件不再另起一个进程，
#         而是把文件路径转交给已运行的窗口，由它加载到当前编辑器。
#   机制：命名互斥体判断是否为首个实例 → 首实例监听本机回环端口并把端口
#         写进 instance.json → 后续实例读该文件、连上去发送文件路径后退出。
# ---------------------------------------------------------------------------
SINGLE_INSTANCE_MUTEX = "Local\\SgMdEditor_SingleInstance_v1"
INSTANCE_FILE_NAME = "instance.json"
IPC_HOST = "127.0.0.1"
IPC_TIMEOUT = 1.5
IPC_MAX_BYTES = 8192
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

_MUTEX_HANDLE = None
_IPC_QUEUE = queue.Queue()


def _instance_file_path():
    """记录运行中实例 pid / 端口的文件，放在本地应用数据目录，不污染 exe 目录。"""
    base = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                        APP_NAME)
    return os.path.join(base, INSTANCE_FILE_NAME)


def _cli_file_path():
    """从命令行取第一个真实存在的文件路径（.md 关联会把路径作为 %1 传入）。"""
    for arg in sys.argv[1:]:
        if not arg or arg.startswith("-"):
            continue
        candidate = os.path.abspath(arg.strip('"').strip("'"))
        if os.path.isfile(candidate):
            return candidate
    return ""


def _acquire_single_instance():
    """创建命名互斥体，返回 (是否首个实例, 互斥体句柄)。

    句柄保存在模块级变量里常驻，进程退出时由系统自动释放；
    创建失败等异常情况一律按“首个实例”处理，避免程序打不开。
    """
    global _MUTEX_HANDLE
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, 0, SINGLE_INSTANCE_MUTEX)
        err = ctypes.get_last_error()
        if not handle:
            log_action("单实例互斥体创建失败", "err=%d" % err)
            return True, None
        _MUTEX_HANDLE = handle
        return (err != ERROR_ALREADY_EXISTS), handle
    except Exception as exc:
        log_action("单实例检测异常", repr(exc))
        return True, None


def _start_ipc_server(app, root):
    """首实例启动监听线程，并把端口写进 instance.json 供后续实例发现。"""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((IPC_HOST, 0))
        srv.listen(5)
        port = int(srv.getsockname()[1])
        info = {"pid": os.getpid(), "port": port,
                "version": APP_VERSION, "ts": int(time.time())}
        path = _instance_file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False)
        threading.Thread(target=_ipc_accept_loop, args=(srv,),
                         daemon=True, name="SgMdIpcAccept").start()
        _drain_ipc_queue(app, root)
        log_action("单实例监听已启动", "pid=%d port=%d" % (os.getpid(), port))
        return srv
    except Exception as exc:
        log_action("单实例监听启动失败", repr(exc))
        return None


def _ipc_accept_loop(srv):
    """监听线程：只接收“请打开这个文件”的一行 JSON，解析后丢进队列。"""
    while True:
        try:
            conn, _addr = srv.accept()
        except Exception:
            return
        try:
            conn.settimeout(IPC_TIMEOUT)
            buf = b""
            while len(buf) < IPC_MAX_BYTES:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                buf += chunk
                if buf.endswith(b"\n"):
                    break
            text = buf.decode("utf-8", "replace").strip()
            if text:
                payload = json.loads(text)
                target = (payload.get("path") or "").strip()
                if target:
                    _IPC_QUEUE.put(target)
        except Exception as exc:
            log_action("单实例消息解析失败", repr(exc))
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _drain_ipc_queue(app, root):
    """在 Tk 主线程里消费队列，确保界面操作不跨线程执行。"""
    try:
        while True:
            target = _IPC_QUEUE.get_nowait()
            try:
                app._activate_front()
                _activate_window_by_pid(os.getpid())
                app.load_path(target)
            except Exception as exc:
                log_action("单实例加载失败", "%s | %r" % (target, exc))
    except queue.Empty:
        pass
    except Exception as exc:
        log_action("单实例队列异常", repr(exc))
    try:
        root.after(200, lambda: _drain_ipc_queue(app, root))
    except Exception:
        pass


def _forward_to_running(path):
    """把文件路径交给已在运行的实例；成功返回 True。"""
    try:
        info_path = _instance_file_path()
        if not os.path.exists(info_path):
            return False
        with open(info_path, "r", encoding="utf-8") as fh:
            info = json.load(fh)
        port = int(info.get("port") or 0)
        pid = int(info.get("pid") or 0)
        if port <= 0:
            return False
        msg = json.dumps({"path": path, "from": os.getpid()},
                         ensure_ascii=False) + "\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(IPC_TIMEOUT)
            sock.connect((IPC_HOST, port))
            sock.sendall(msg.encode("utf-8"))
        log_action("文件已转交运行中实例", "%s -> pid=%d" % (path, pid))
        _activate_window_by_pid(pid)
        return True
    except Exception as exc:
        log_action("文件转交失败", "%s | %r" % (path, exc))
        return False


def _activate_window_by_pid(pid):
    """把指定进程的可见顶层窗口还原并提到前台；失败静默（不影响加载）。"""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p,
                                                    ctypes.POINTER(ctypes.c_ulong)]
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
        user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        found = []
        wndproc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)

        def _collect(hwnd, _lparam):
            owned = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owned))
            if owned.value == pid and user32.IsWindowVisible(hwnd):
                if user32.GetWindowTextLengthW(hwnd) > 0:
                    found.append(hwnd)
            return True

        user32.EnumWindows(wndproc(_collect), 0)
        for hwnd in found:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        return bool(found)
    except Exception as exc:
        log_action("窗口激活失败", repr(exc))
        return False


def _run_application():
    """启动入口：先判断是否已有实例在跑，再决定“转交文件”还是“开新窗口”。"""
    target = _cli_file_path()
    is_first, _handle = _acquire_single_instance()
    if not is_first:
        if target and _forward_to_running(target):
            return None
        log_action("转交未成功", "按新实例继续启动 | %s" % (target or "无文件参数"))
    _enable_dpi_awareness()
    _install_excepthook()
    root = tk.Tk()
    app = MdToolApp(root)
    _start_ipc_server(app, root)
    if target:
        root.after(120, lambda: app.load_path(target))
    root.mainloop()
    return app


if __name__ == "__main__":
    _run_application()
