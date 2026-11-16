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
import hashlib
import json
import logging
import logging.handlers
import queue
import shutil
import socket
import subprocess
import tempfile
import uuid
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
from tkinter import simpledialog

try:  # 仅 Windows 提供 winreg；缺失时文件关联功能降级为不可用
    import winreg
except Exception:  # pragma: no cover
    winreg = None

from urllib.parse import quote
from urllib.parse import unquote

try:  # 可选依赖：装了 Pillow 才能预览 JPG/BMP/WEBP 并做平滑缩放，缺失时退化为 Tk 原生格式
    from PIL import Image as _PILImage
    from PIL import ImageTk as _PILImageTk
    _PIL_OK = True
except Exception:  # pragma: no cover
    _PILImage = None
    _PILImageTk = None
    _PIL_OK = False

# ---------------------------------------------------------------------------
# 常量信息
# ---------------------------------------------------------------------------
APP_NAME = "爽哥MD编辑工具"
APP_VERSION = "1.10.1"
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

# 预览图片（v1.7.0）：预览区把 ![说明](路径) 渲染成真实图片
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
                    ".tif", ".tiff", ".ico", ".ppm", ".pgm")
IMAGE_PREVIEW_MAX_H = 480       # 单张图片在预览区的最大高度（像素）
IMAGE_PREVIEW_MARGIN = 56       # 预览区左右留白（内边距 + 滚动条）
IMAGE_PREVIEW_MIN_W = 240       # 预览区过窄时的兜底宽度
IMAGE_CACHE_LIMIT = 32          # 解码缓存条数上限，超出整体清空

# 预览视频（v1.8.0）：识别 <iframe> / <video> / B 站链接 / 本地视频路径，
# 单击预览里的「▶ 视频」条目，在预览区下方的内嵌面板里用系统 Edge（Chromium 内核）真播放。
# 说明：tkinter Text 无法承载 HTML，因此播放器是嵌入在预览栏底部的子窗口，不是文本流内元素。
VIDEO_EXTENSIONS = (".mp4", ".webm", ".ogg", ".ogv", ".mov", ".m4v", ".mkv")
VIDEO_PANEL_H = 250             # 内嵌播放面板默认高度（像素）
VIDEO_PANEL_MIN_W = 400         # 内嵌播放面板最小宽度（像素，v1.10.0 起横跨主窗口底部）
VIDEO_PANEL_MAX_H = 420         # 内嵌播放面板最大高度（像素）
VIDEO_EDGE_WAIT_MS = 12000      # 等待 Edge 播放窗口出现的最长时间（毫秒）
VIDEO_WINDOW_POLL_MS = 250      # 轮询 Edge 播放窗口的间隔（毫秒）
VIDEO_CACHE_DIR = "video_cache"  # 播放页与 Edge 独立配置目录（exe 同级）
VIDEO_PROFILE_DIR = "profiles"   # 每次播放独立的 Edge 配置目录（v1.10.0：防进程复用）
VIDEO_PROFILE_KEEP = 3           # 启动时保留最近几个 Edge 配置目录
# v1.10.0：B 站播放器只有 autoplay=1 才会自动起播；旧版写死 autoplay=0，预览区只显示静止黑屏
# v1.10.1：去掉 isOutside=true —— 带该参数时 B 站把播放器当站外引用，只回一帧静止画面
# （实测画面几乎全黑、帧不变化），去掉后同一 BV 号立即正常播放。
BILI_PLAYER_URL = ("https://player.bilibili.com/player.html?bvid=%s"
                   "&page=1&autoplay=1&high_quality=1&danmaku=1")
BILI_IFRAME_TPL = (
    '<iframe\n'
    '  src="%s"\n'
    '  title="哔哩哔哩视频播放器"\n'
    '  allow="fullscreen; autoplay; encrypted-media; picture-in-picture"\n'
    '  allowfullscreen\n'
    '  loading="lazy"\n'
    '  style="width:100%%; aspect-ratio:16/9; border:0;">\n'
    '</iframe>'
)
VIDEO_TAG_TPL = '<video controls width="100%%" src="%s">\n</video>'
# v1.10.0：本地/直链视频起播加固。Chromium 的自动播放策略在部分 Edge 版本上会无视
# --autoplay-policy 参数，导致播放页停在首帧（用户看到"能出画面但不动"）。这里用
# 「先静音起播 -> 起播成功后取消静音」的标准做法兜住，并主动重试、给出失败提示。
PLAYER_AUTOPLAY_JS = (
    '<script>\n'
    '(function () {\n'
    '  var v = document.querySelector("video");\n'
    '  if (!v) { return; }\n'
    '  var tries = 0;\n'
    '  var unlock = function () { v.muted = false; };\n'
    '  var attempt = function () {\n'
    '    tries++;\n'
    '    if (tries > 30) { return; }\n'
    '    var p = v.play();\n'
    '    if (!p || !p.then) { return; }\n'
    '    p.then(unlock, function () {\n'
    '      v.muted = true;\n'
    '      var q = v.play();\n'
    '      if (q && q.then) { q.then(unlock, function () { setTimeout(attempt, 300); }); }\n'
    '      else { setTimeout(attempt, 300); }\n'
    '    });\n'
    '  };\n'
    '  ["loadedmetadata", "canplay", "canplaythrough"].forEach(function (n) {\n'
    '    v.addEventListener(n, attempt);\n'
    '  });\n'
    '  document.addEventListener("click", attempt);\n'
    '  v.addEventListener("error", function () {\n'
    '    document.title = "视频加载失败";\n'
    '    document.body.insertAdjacentHTML("beforeend",\n'
    '      "<p style=\\"color:#f88;font:14px/1.6 sans-serif;padding:12px\\">"\n'
    '      + "视频加载失败，可点「浏览器打开」直接观看</p>");\n'
    '  });\n'
    '  attempt();\n'
    '})();\n'
    '</script>\n'
)
PLAYER_PAGE_TPL = (
    '<!doctype html>\n'
    '<html><head><meta charset="utf-8"><title>视频播放</title>\n'
    '<style>html,body{margin:0;height:100%%;background:#000;overflow:hidden}\n'
    'iframe,video{width:100%%;height:100%%;border:0;display:block;'
    'object-fit:contain;background:#000}</style></head>\n'
    '<body>%s%s</body></html>'
)
# 嵌入外部窗口用到的 Win32 常量：去掉弹出式标题栏，改成子窗口样式
GWL_STYLE = -16
WIN_DROP_STYLE = 0x80000000 | 0x00C00000 | 0x00040000 | 0x00080000   # POPUP|CAPTION|THICKFRAME|SYSMENU
WIN_CHILD_STYLE = 0x40000000 | 0x10000000                           # CHILD|VISIBLE
WM_CLOSE = 0x0010                                                   # 停止播放时先礼后兵

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


# ---------------- 中文右键菜单（v1.9.0） ----------------
# tkinter 的 Text / Entry 在 Windows 上不提供可用的中文右键菜单，用户只能靠快捷键。
# 这里给每个输入控件挂一套统一的中文右键菜单：
#   撤销 / 重做 / 剪切 / 复制 / 粘贴 / 删除 / 全选，按场景置灰；
#   只读控件（实时预览、更新说明）只保留「复制 / 全选」，避免点了没反应。

CTX_EDIT_ITEMS = ("undo", "redo", "sep", "cut", "copy", "paste", "delete",
                  "sep", "select")
CTX_READONLY_ITEMS = ("copy", "sep", "select")

CTX_ITEM_LABELS = {
    "undo": ("撤销", "Ctrl+Z"),
    "redo": ("重做", "Ctrl+Y"),
    "cut": ("剪切", "Ctrl+X"),
    "copy": ("复制", "Ctrl+C"),
    "paste": ("粘贴", "Ctrl+V"),
    "delete": ("删除", "Del"),
    "select": ("全选", "Ctrl+A"),
}


def _widget_is_entry(widget):
    """Entry / ttk.Entry 的选区索引（sel.first）与 Text 不同，需分开处理。"""
    try:
        return widget.winfo_class() in ("Entry", "TEntry")
    except Exception:
        return False


def _edit_flag(widget, name):
    """读 Text/Entry 的 edit canundo / canredo 标志，控件不支持时返回 False。"""
    try:
        return bool(int(widget.tk.call(widget._w, "edit", name)))
    except Exception:
        return False


class TextContextMenu:
    """给单个文本类控件挂中文右键菜单（Text / Entry 通用）。

    editable=False 表示只读控件：只保留「复制 / 全选」。
    on_changed 在每次菜单动作后回调，主编辑区用它刷新预览与统计。
    """

    def __init__(self, widget, palette_getter=None, editable=True,
                 on_changed=None):
        self.widget = widget
        self._palette_getter = palette_getter
        self.editable = bool(editable)
        self.on_changed = on_changed
        self.menu = tk.Menu(widget, tearoff=0)
        self._index = {}
        self._build()
        self.restyle()
        widget.bind("<Button-3>", self.popup, add="+")
        widget.bind("<Shift-F10>", self.popup, add="+")

    # ---------------- 构建与配色 ----------------
    def _build(self):
        menu = self.menu
        menu.delete(0, "end")
        self._index = {}
        items = CTX_EDIT_ITEMS if self.editable else CTX_READONLY_ITEMS
        for key in items:
            if key == "sep":
                menu.add_separator()
                continue
            label, accel = CTX_ITEM_LABELS[key]
            menu.add_command(label=label, accelerator=accel,
                             command=lambda k=key: self.fire(k))
            self._index[key] = menu.index("end")

    def restyle(self, palette=None):
        """主题切换后重新上色（与菜单栏同一套配色）。"""
        if palette is None and self._palette_getter is not None:
            try:
                palette = self._palette_getter()
            except Exception:
                palette = None
        if palette:
            style_menu(self.menu, palette)
        return self.menu

    def labels(self):
        """当前菜单可见项（测试用）：返回 label 列表，分隔线记为 None。"""
        out = []
        try:
            last = self.menu.index("end")
        except Exception:
            return out
        if last is None:
            return out
        for i in range(last + 1):
            try:
                if self.menu.type(i) == "separator":
                    out.append(None)
                else:
                    out.append(self.menu.entrycget(i, "label"))
            except Exception:
                out.append(None)
        return out

    # ---------------- 状态探测 ----------------
    def has_selection(self):
        widget = self.widget
        try:
            if _widget_is_entry(widget):
                return bool(widget.selection_present())
            return bool(widget.tag_ranges("sel"))
        except Exception:
            return False

    def selection_text(self):
        widget = self.widget
        try:
            if _widget_is_entry(widget):
                return widget.selection_get() if widget.selection_present() else None
            return widget.get("sel.first", "sel.last")
        except Exception:
            return None

    def has_content(self):
        widget = self.widget
        try:
            if _widget_is_entry(widget):
                return bool(widget.get())
            return bool(widget.get("1.0", "end-1c"))
        except Exception:
            return False

    def _clipboard_has_text(self):
        try:
            return bool(self.widget.clipboard_get())
        except Exception:
            return False

    def refresh_state(self):
        """按选区 / 剪贴板 / 撤销栈决定各项可点性，返回 {item: bool}。"""
        if not self._index:
            self._build()
        states = {
            "undo": _edit_flag(self.widget, "canundo"),
            "redo": _edit_flag(self.widget, "canredo"),
            "cut": self.has_selection(),
            "copy": self.has_selection(),
            "paste": self._clipboard_has_text(),
            "delete": self.has_selection(),
            "select": self.has_content(),
        }
        for key, idx in self._index.items():
            enabled = bool(states.get(key))
            try:
                self.menu.entryconfigure(
                    idx, state="normal" if enabled else "disabled")
            except Exception:
                pass
        return states

    # ---------------- 动作 ----------------
    def fire(self, key):
        handler = {
            "undo": self._undo,
            "redo": self._redo,
            "cut": self._cut,
            "copy": self._copy,
            "paste": self._paste,
            "delete": self._delete,
            "select": self._select_all,
        }.get(key)
        done = False
        if handler is not None:
            try:
                done = bool(handler())
            except Exception:
                done = False
        self._notify()
        return done

    def _notify(self):
        if self.on_changed is not None:
            try:
                self.on_changed()
            except Exception:
                pass

    def _undo(self):
        if _edit_flag(self.widget, "canundo"):
            self.widget.event_generate("<<Undo>>")
            return True
        return False

    def _redo(self):
        if _edit_flag(self.widget, "canredo"):
            self.widget.event_generate("<<Redo>>")
            return True
        return False

    def _write_clipboard(self, text):
        if not text:
            return False
        try:
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
            return True
        except Exception:
            return False

    def _copy(self):
        data = self.selection_text()
        if not data:
            return False
        return self._write_clipboard(data)

    def _cut(self):
        if not self.editable:
            return False
        data = self.selection_text()
        if not data:
            return False
        self._write_clipboard(data)
        try:
            self.widget.delete("sel.first", "sel.last")
        except Exception:
            return False
        return True

    def _delete(self):
        if not self.editable or not self.has_selection():
            return False
        try:
            self.widget.delete("sel.first", "sel.last")
        except Exception:
            return False
        return True

    def _paste(self):
        if not self.editable:
            return False
        try:
            data = self.widget.clipboard_get()
        except Exception:
            return False
        if not data:
            return False
        try:
            if self.has_selection():
                self.widget.delete("sel.first", "sel.last")
            self.widget.insert("insert", data)
        except Exception:
            return False
        return True

    def _select_all(self):
        widget = self.widget
        try:
            if _widget_is_entry(widget):
                widget.selection_range(0, "end")
                widget.icursor("end")
                return True
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
            widget.see("insert")
        except Exception:
            return False
        return True

    # ---------------- 弹出 ----------------
    def popup(self, event=None):
        try:
            self.widget.focus_set()
        except Exception:
            pass
        self.refresh_state()
        try:
            x = event.x_root if event is not None else self.widget.winfo_rootx()
            y = event.y_root if event is not None else self.widget.winfo_rooty()
            self.menu.tk_popup(x, y)
        except Exception:
            pass
        finally:
            try:
                self.menu.grab_release()
            except Exception:
                pass
        return "break"


def install_text_context_menu(widget, palette_getter=None, editable=True,
                              on_changed=None):
    """给任意文本类控件（Text / Entry）挂中文右键菜单，返回控制器。"""
    return TextContextMenu(widget, palette_getter=palette_getter,
                           editable=editable, on_changed=on_changed)


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
LOG_MAX_BYTES = 2 * 1024 * 1024     # 单个日志文件上限 2 MB（v1.10.0）
LOG_BACKUP_COUNT = 3                # 轮转后保留 3 个历史文件（v1.10.0）

logger = logging.getLogger("shuage.md.editor")
logger.setLevel(logging.DEBUG)
logger.propagate = False
if not logger.handlers:
    _handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8")
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(_handler)


def log_action(action, detail=""):
    """记录用户操作日志（INFO），便于反馈问题时定位。"""
    try:
        logger.info("%s | %s", action, detail)
    except Exception:
        pass


def log_detail(action, detail=""):
    """记录链路细节（DEBUG）：启动参数、进程 PID、hwnd、样式位等排障信息。"""
    try:
        logger.debug("%s | %s", action, detail)
    except Exception:
        pass


def log_warn(action, detail=""):
    """记录非致命异常（WARNING）：启动超时、进程提前退出、清理失败等。"""
    try:
        logger.warning("%s | %s", action, detail)
    except Exception:
        pass


def log_error(action, detail=""):
    """记录失败（ERROR）：进程启动失败、窗口嵌入失败、回调异常等。"""
    try:
        logger.error("%s | %s", action, detail)
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
    r"(!\[[^\]\n]*\]\([^)\n]*\)"      # 图片（v1.7.0，必须先于链接匹配）
    r"|`[^`\n]+`"                      # 行内代码
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

# 视频识别（v1.8.0）
_VIDEO_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')
_VIDEO_SRC_RE = re.compile(r'<source\b[^>]*\bsrc\s*=\s*"([^"]+)"', re.I)
_BILI_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_BILI_PAGE_RE = re.compile(r"^https?://(?:[\w.-]+\.)?bilibili\.com/\S+$", re.I)
_LOCAL_VIDEO_RE = re.compile(r"^(?:file:///)?[^\s]+\.(?:%s)$"
                             % "|".join(ext.lstrip(".") for ext in VIDEO_EXTENSIONS), re.I)

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
    ("img", {"spacing1": 6, "spacing3": 6}),
    ("imgfail", {"font": (FONT_CN, 9, "italic"), "foreground": "#b04a3a"}),
    ("video", {"font": (FONT_CN, 10), "underline": 1, "lmargin1": 8,
               "spacing1": 8, "spacing3": 8}),
]

# 预览标签里需要随主题变化的键：标签名 -> 调色板中对应字段
_TAG_COLOR_MAP = {
    "h1": "h1_fg", "h2": "h2_fg", "h3": "h3_fg",
    "h4": "h4_fg", "h5": "h5_fg", "h6": "h6_fg",
    "link": "link_fg", "hr": "hr_fg", "hint": "hint_tag_fg",
    "video": "link_fg",
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


# ---------------------------------------------------------------------------
# 预览图片（v1.7.0）：把 ![说明](路径) 还原成真实图片显示
# ---------------------------------------------------------------------------
_IMAGE_TOKEN_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]*)\)")


def parse_image_markup(token):
    """拆解 ![说明](目标) → (说明, 目标)；目标去掉 <> 包裹与 "标题"。"""
    match = _IMAGE_TOKEN_RE.match((token or "").strip())
    if not match:
        return "", (token or "").strip()
    alt = match.group(1).strip()
    raw = match.group(2).strip()
    if raw.startswith("<") and raw.endswith(">"):
        return alt, raw[1:-1].strip()
    titled = re.match(r"^(\S+)\s+(\"[^\"]*\"|'[^']*')$", raw)
    if titled:
        raw = titled.group(1)
    return alt, raw


def resolve_image_path(src, base_dir=None):
    """图片地址 → 本地绝对路径；网络图 / Base64 / 不存在的文件抛 ValueError。"""
    text = (src or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("图片地址为空")
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")):
        raise ValueError("网络图片暂不预览，请下载到本地再引用")
    if lowered.startswith("data:"):
        raise ValueError("内嵌 Base64 图片暂不预览")
    if lowered.startswith("file://"):
        text = unquote(text[len("file://"):])
        if re.match(r"^/[A-Za-z]:", text):
            text = text[1:]
    text = os.path.expanduser(text)
    if not os.path.isabs(text):
        text = os.path.join(base_dir or os.getcwd(), text)
    text = os.path.normpath(text)
    if not os.path.isfile(text):
        raise ValueError("文件不存在：%s" % text)
    return text


def load_preview_image(path, max_width, max_height=IMAGE_PREVIEW_MAX_H, master=None):
    """按预览区可用宽度等比缩放读取图片，返回 Tk PhotoImage。"""
    limit_w = max(IMAGE_PREVIEW_MIN_W, int(max_width or IMAGE_PREVIEW_MIN_W))
    limit_h = max(120, int(max_height or IMAGE_PREVIEW_MAX_H))
    if _PIL_OK:
        with _PILImage.open(path) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)          # 动图只渲染第一帧，避免预览抖动
            img.load()
            width, height = img.size
            if width <= 0 or height <= 0:
                raise ValueError("图片尺寸无效")
            scale = min(limit_w / float(width), limit_h / float(height), 1.0)
            if scale < 1.0:
                size = (max(1, int(width * scale)), max(1, int(height * scale)))
                img = img.resize(size, _PILImage.LANCZOS)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            return _PILImageTk.PhotoImage(img, master=master)
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".png", ".gif", ".ppm", ".pgm"):
        raise ValueError("未安装 Pillow，仅能预览 PNG/GIF/PPM")
    photo = tk.PhotoImage(file=path, master=master)
    factor = 1
    while factor < 16 and (photo.width() // factor > limit_w
                           or photo.height() // factor > limit_h):
        factor += 1
    if factor > 1:
        photo = photo.subsample(factor, factor)
    return photo


def render_image(widget, alt, src, extra_tags, image_ctx=None):
    """把一张图片写进预览 Text；无法显示时退化为一行提示文字（不吞异常信息）。"""
    tags = tuple(extra_tags) + ("img",)
    label = alt or os.path.basename((src or "").strip()) or "图片"
    if image_ctx is None:
        widget.insert("end", "[图片] %s（%s）" % (label, src), tags)
        return
    try:
        path = resolve_image_path(src, image_ctx.get("base_dir"))
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            mtime = 0
        max_width = int(image_ctx.get("max_width") or IMAGE_PREVIEW_MIN_W)
        cache = image_ctx.setdefault("cache", {})
        key = (path, mtime, max_width)
        photo = cache.get(key)
        if photo is None:
            photo = load_preview_image(path, max_width, master=widget)
            if len(cache) >= IMAGE_CACHE_LIMIT:
                cache.clear()
            cache[key] = photo
        index = widget.index("end-1c")
        widget.image_create("end-1c", image=photo, padx=0, pady=2)
        widget.tag_add("img", index)
        image_ctx.setdefault("paths", {})[index] = path
    except Exception as exc:
        widget.insert("end", "[图片] %s（%s）" % (label, exc), tags + ("imgfail",))


def image_insert_target(path, base_dir=None):
    """算出写进 Markdown 的图片地址：优先相对文档目录，跨盘用绝对路径，含空格用 <> 包裹。"""
    target = os.path.abspath(path)
    base = base_dir or os.getcwd()
    try:
        rel = os.path.relpath(target, base)
    except ValueError:            # 跨盘符无法计算相对路径
        rel = ""
    if rel and rel != os.pardir and not rel.startswith(".." + os.sep):
        target = rel
    text = str(target).replace("\\", "/")
    if " " in text:
        text = "<%s>" % text
    return text


def html_escape(text):
    """把文本转义成可安全塞进 HTML 属性的字符串。"""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def file_url(path):
    """本地绝对路径 → Edge 可直接打开的 file:/// URL（含空格/中文做百分号编码）。"""
    text = os.path.abspath(path).replace("\\", "/")
    return "file:///" + quote(text, safe="/:")


def video_attrs(block):
    """解析 <iframe>/<video> 标签属性 → dict（属性名统一小写）。"""
    attrs = {}
    head = re.match(r"<\s*(?:iframe|video)\b([^>]*)>", block or "", re.S | re.I)
    if not head:
        return attrs
    for match in _VIDEO_ATTR_RE.finditer(head.group(1)):
        attrs[match.group(1).lower()] = match.group(2) or ""
    return attrs


def video_source_of(block):
    """从视频标记里取播放地址：iframe 取 src，video 取自身 src 或首个 <source src>。"""
    src = (video_attrs(block).get("src") or "").strip()
    if src:
        return src
    source = _VIDEO_SRC_RE.search(block or "")
    if source:
        return source.group(1).strip()
    text = (block or "").strip()
    # 不是标签片段就直接当地址（裸 B 站链接 / 本地路径都走这里）
    return "" if "<" in text else text


def classify_video(src, base_dir=None):
    """视频地址归一化为 (kind, payload, label)。

    kind 取值：bili（B 站视频，payload=bvid）/ web（网页播放器，payload=URL）
    / local（本地视频，payload=绝对路径）/ bad（无法播放，label=原因）。
    """
    text = (src or "").strip()
    if not text:
        return ("bad", "", "没有视频地址")
    bili_match = _BILI_BV_RE.search(text)
    if bili_match and ("bilibili" in text.lower() or _BILI_BV_RE.fullmatch(text)):
        bvid = bili_match.group(0)
        # payload 保留完整播放地址（带 cid / page），才能精确定位分P
        payload = bili_embed_src(text) or (BILI_PLAYER_URL % bvid)
        return ("bili", payload, "B站 %s" % bvid)
    if text.lower().startswith(("http://", "https://")):
        host = text.split("//", 1)[-1].split("/")[0]
        return ("web", text, host or "网页")
    path = text
    if path.lower().startswith("file:///"):
        path = unquote(path[8:])
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
    if not os.path.isabs(path):
        path = os.path.join(base_dir or os.getcwd(), unquote(path))
    path = os.path.normpath(path)
    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS:
            return ("local", path, os.path.basename(path))
        return ("bad", "", "不是支持的视频格式：%s" % os.path.basename(path))
    return ("bad", "", "文件不存在：%s" % os.path.basename(path))


def html_block_complete(text):
    """判断一段 HTML 片段是否已闭合（用于跨行收集 iframe / video 块）。"""
    lowered = (text or "").lower()
    if "<iframe" in lowered:
        return "</iframe>" in lowered or re.search(r"<iframe\b[^>]*/>", text, re.I) is not None
    if "<video" in lowered:
        if "</video>" in lowered:
            return True
        return re.search(r"<video\b[^>]*/>", text, re.I) is not None
    return True


def looks_like_video_line(text, base_dir=None):
    """整行是否就是一个视频地址（B 站链接 / BV 号 / 本地视频路径）——避免误伤普通段落。"""
    value = (text or "").strip()
    if not value or len(value) > 400:
        return False
    if _BILI_BV_RE.fullmatch(value) or _BILI_PAGE_RE.match(value):
        return True
    token = value.strip("<>")
    if _BILI_PAGE_RE.match(token):
        return True
    if " " in value:
        # 路径里带空格的本地视频：只认确实存在的文件，避免把普通句子当视频
        return classify_video(value, base_dir)[0] == "local"
    return _LOCAL_VIDEO_RE.match(token) is not None


def bili_embed_src(text):
    """从 B 站链接 / BV 号还原 player.html 地址（保留 cid 与 p 参数）；非 B 站返回空串。"""
    value = (text or "").strip().strip("<>\"'")
    bv = _BILI_BV_RE.search(value)
    if not bv:
        return ""
    bvid = bv.group(0)
    if "player.bilibili.com" in value and "cid=" in value:
        # 已经是播放器地址：仍强制打开自动播放，否则内嵌窗口停在封面不播
        return ensure_autoplay(value)
    page_m = re.search(r"[?&]p=(\d+)", value)
    page = page_m.group(1) if page_m else "1"
    cid_m = re.search(r"[?&]cid=(\d+)", value)
    url = "https://player.bilibili.com/player.html?bvid=%s" % bvid
    if cid_m:
        url += "&cid=%s" % cid_m.group(1)
    return ensure_autoplay(url + "&page=%s" % page)


def video_insert_target(path, base_dir=None):
    """写进 Markdown 的本地视频地址：优先相对文档目录，反斜杠转 /，空格百分号编码。"""
    target = os.path.abspath(path)
    base = base_dir or os.getcwd()
    try:
        rel = os.path.relpath(target, base)
    except ValueError:
        rel = ""
    if rel and rel != os.pardir and not rel.startswith(".." + os.sep):
        target = rel
    return quote(str(target).replace("\\", "/"), safe="/:")


_TAG_HEAD_RE = re.compile(r"^<\s*(?:iframe|video)\b", re.I)


def video_markup_pure(value):
    """整段输入是否只由一段 iframe / video 标记构成（前后不夹带其它正文）。"""
    text = (value or "").strip()
    if not text or len(text) > 4000:
        return False
    if not _TAG_HEAD_RE.match(text):
        return False
    if not html_block_complete(text):
        return False
    if re.search(r"</\s*(?:iframe|video)\s*>\s*$", text, re.I):
        return True
    return re.search(r"/\s*>\s*$", text) is not None


def url_like(value):
    """整段输入是否只是一个网址（无空白、无多余文字）。"""
    text = (value or "").strip()
    if not text or len(text) > 2048:
        return False
    if any(ch.isspace() for ch in text):
        return False
    return re.match(r"^https?://[^\s/]+\.[^\s/?]+", text, re.I) is not None


def build_video_markup(text, base_dir=None):
    """把用户给的视频输入（iframe / B 站链接 / BV 号 / 网页 / 本地文件）变成可插入的 HTML。

    v1.8.1 修复：只接受"整段就是一个视频标记 / 地址"的输入。夹带正文的（剪贴板里
    常常是聊天记录或文档文字）一律判为识别失败返回空串，交给调用方提示用户，
    避免把一大段无关文字当成 iframe 插进文档。
    """
    value = (text or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if "<iframe" in lowered:
        if not video_markup_pure(value):
            return ""
        src = video_source_of(value)
        if not src:
            return ""
        fixed = bili_embed_src(src)
        if fixed and fixed != src:
            value = value.replace(src, fixed)
        return value.strip()
    if "<video" in lowered:
        if not video_markup_pure(value) or not video_source_of(value):
            return ""
        return value.strip()
    if _BILI_BV_RE.fullmatch(value):
        return BILI_IFRAME_TPL % bili_embed_src(value)
    if url_like(value):
        return BILI_IFRAME_TPL % (bili_embed_src(value) or value)
    kind, payload, _label = classify_video(value, base_dir)
    if kind == "local":
        return VIDEO_TAG_TPL % video_insert_target(payload, base_dir)
    return ""


def video_cache_dir():
    """播放页与 Edge 独立配置目录（exe 同级 video_cache/，不可写时回退 %LOCALAPPDATA%）。"""
    base = os.path.join(_app_base_dir(), VIDEO_CACHE_DIR)
    try:
        os.makedirs(base, exist_ok=True)
        probe = os.path.join(base, ".probe")
        with open(probe, "w", encoding="utf-8") as fp:
            fp.write("ok")
        os.remove(probe)
        return base
    except Exception:
        fallback = os.path.join(
            os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
            APP_NAME, VIDEO_CACHE_DIR)
        os.makedirs(fallback, exist_ok=True)
        return fallback


def render_video(widget, block, extra_tags=(), video_ctx=None):
    """把视频引用渲染成一行可点击条目；无法播放时退化为一行提示文字。

    条目字符位置 → 播放目标 的映射记在 video_ctx["paths"]，每次预览刷新重建（同图片）。
    """
    tags = tuple(extra_tags) + ("video",)
    src = video_source_of(block) or (block or "").strip()
    kind, payload, label = classify_video(src, (video_ctx or {}).get("base_dir"))
    if kind == "bad":
        widget.insert("end", "[视频] %s\n" % label,
                      tuple(extra_tags) + ("imgfail",))
        return
    head = {"bili": "▶ B站视频", "web": "▶ 网页播放器", "local": "▶ 本地视频"}[kind]
    index = widget.index("end-1c")
    widget.insert("end-1c", "%s · %s\n" % (head, label), tags)
    if video_ctx is not None:
        video_ctx.setdefault("paths", {})[index] = (kind, payload, label)


_MEDIA_URL_RE = re.compile(
    r"\.(?:%s)(?:$|[?#])" % "|".join(ext.lstrip(".") for ext in VIDEO_EXTENSIONS), re.I)


def bili_clean_url(url):
    """去掉 B 站播放地址里的 isOutside 参数（v1.10.1 修复预览区黑屏）。

    用户从网上抄来的 iframe 常常自带 isOutside=true；B 站收到该参数会把播放器按
    「站外引用」降级处理，回到预览窗口里的效果就是一帧静止画面（实测整块区域几乎
    全黑、连续截图帧差≈0.0004）。这里直接把它摘掉，其余参数原样保留。
    """
    value = (url or "").strip()
    if not re.search(r"[?&]isoutside=", value, re.I):
        return value
    head, _, query = value.partition("?")
    frag = ""
    if "#" in query:
        query, _, frag = query.partition("#")
    kept = [item for item in query.split("&")
            if item and not item.lower().startswith("isoutside=")]
    rebuilt = head + (("?" + "&".join(kept)) if kept else "")
    if frag:
        rebuilt += "#" + frag
    log_action("B站播放地址已移除 isOutside 参数", rebuilt)
    return rebuilt


def ensure_autoplay(url):
    """把 B 站播放地址的 autoplay 参数强制改成 1（内嵌预览必须自动起播）。"""
    value = bili_clean_url(url)
    if not value:
        return value
    if re.search(r"[?&]autoplay=", value):
        return re.sub(r"([?&])autoplay=[^&#]*",
                      lambda m: m.group(1) + "autoplay=1", value)
    return value + ("&" if "?" in value else "?") + "autoplay=1"


def media_url(url):
    """网页地址本身是否就是媒体直链（.mp4/.webm/... 结尾）——这类地址必须用 <video> 播。"""
    value = (url or "").strip()
    if not value.lower().startswith(("http://", "https://")):
        return False
    return _MEDIA_URL_RE.search(value.split("#", 1)[0]) is not None


class VideoHttpServer(object):
    """本机回环 HTTP 服务：给内嵌播放器提供 http:// 播放页与本地视频流。

    v1.10.0 修复：播放页原先用 file:// 打开，实测（temp/probe32~probe35）Chromium 在
    file:// 页面里给子框架的 Referer 为空、跨源媒体请求也会被卡住，表现为 B 站播放器
    整块黑屏（屏幕亮度掉到 0.2）、网页 mp4 永远停在 readyState=0 / currentTime=0；
    同一批页面改由 http://127.0.0.1:<port>/ 提供后四类输入都能正常出画面。
    因此播放页与本地视频统一走本机回环 HTTP，本地视频额外支持 Range 以便拖动进度。
    """

    MAX_CHUNK = 256 * 1024

    def __init__(self):
        self._pages = {}
        self._media = {}
        self._lock = threading.Lock()
        self._httpd = None
        self.port = 0
        self.base_url = ""

    # ---- 对外接口 -------------------------------------------------------
    def start(self):
        """启动服务；已在运行则直接复用。失败抛异常，由调用方兜底。"""
        if self._httpd is not None:
            return self
        import http.server
        import socketserver

        owner = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "SgMdVideo/1.0"

            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                owner._serve(self, True)

            def do_HEAD(self):
                owner._serve(self, False)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self._httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self.base_url = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self._httpd.serve_forever,
                         name="sg-md-video-http", daemon=True).start()
        return self

    def page_url(self, html):
        """注册播放页 HTML 并返回可访问 URL（同内容复用同一 URL）。"""
        if self._httpd is None:
            self.start()
        key = hashlib.md5(html.encode("utf-8")).hexdigest()[:12]
        with self._lock:
            self._pages[key] = html
        return "%s/player/%s.html" % (self.base_url, key)

    def media_url(self, path):
        """注册本地视频并返回可访问 URL（支持 Range），同一路径复用同一 token。"""
        if self._httpd is None:
            self.start()
        full = os.path.abspath(path)
        token = hashlib.md5(full.encode("utf-8")).hexdigest()[:12]
        with self._lock:
            self._media[token] = full
        return "%s/media/%s" % (self.base_url, token)

    def shutdown(self):
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception as exc:
                log_detail("本地视频服务关闭异常", repr(exc))

    # ---- 路由 -----------------------------------------------------------
    def _serve(self, h, with_body):
        import mimetypes
        import urllib.parse
        path = urllib.parse.urlsplit(h.path or "/").path
        parts = [p for p in path.split("/") if p]
        try:
            if len(parts) == 2 and parts[0] == "player":
                key = parts[1][:-5] if parts[1].endswith(".html") else parts[1]
                with self._lock:
                    html = self._pages.get(key)
                if html is None:
                    self._send_plain(h, 404, "page not found")
                    return
                body = html.encode("utf-8")
                h.send_response(200)
                h.send_header("Content-Type", "text/html; charset=utf-8")
                h.send_header("Content-Length", str(len(body)))
                h.send_header("Cache-Control", "no-store")
                h.end_headers()
                if with_body:
                    h.wfile.write(body)
                return
            if len(parts) == 2 and parts[0] == "media":
                with self._lock:
                    full = self._media.get(parts[1])
                if not full or not os.path.isfile(full):
                    log_warn("本地视频路由命中失败", "token=%s | 文件=%s" % (parts[1], full))
                    self._send_plain(h, 404, "media not found")
                    return
                self._send_file(h, full, mimetypes, with_body)
                return
            self._send_plain(h, 404, "not found")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            log_warn("本地视频服务处理请求失败", "%s | %r" % (h.path, exc))

    def _send_file(self, h, full, mimetypes, with_body):
        """带 Range 的文件流：Chromium 播放视频会先发 Range 请求，必须回 206 才能拖动。"""
        size = os.path.getsize(full)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        start, end, status = 0, size - 1, 200
        rng = h.headers.get("Range") if h.headers else None
        if rng and rng.startswith("bytes="):
            spec = rng[6:].split(",")[0].strip()
            head, _sep, tail = spec.partition("-")
            try:
                if head:
                    start = max(0, int(head))
                    end = int(tail) if tail else size - 1
                elif tail:
                    start = max(0, size - int(tail))
                if start > end or start >= size:
                    start, end, status = 0, size - 1, 200
                else:
                    end = min(end, size - 1)
                    status = 206
            except ValueError:
                start, end, status = 0, size - 1, 200
        length = (end - start + 1) if size else 0
        h.send_response(status)
        h.send_header("Content-Type", ctype)
        h.send_header("Accept-Ranges", "bytes")
        h.send_header("Content-Length", str(length))
        if status == 206:
            h.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        h.end_headers()
        if not with_body or length <= 0:
            return
        with open(full, "rb") as fp:
            fp.seek(start)
            remain = length
            while remain > 0:
                chunk = fp.read(min(self.MAX_CHUNK, remain))
                if not chunk:
                    break
                h.wfile.write(chunk)
                remain -= len(chunk)

    @staticmethod
    def _send_plain(h, code, msg):
        body = msg.encode("utf-8")
        h.send_response(code)
        h.send_header("Content-Type", "text/plain; charset=utf-8")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)


_VIDEO_HTTP = None
_VIDEO_HTTP_FAILED = False


def video_http_server():
    """取（必要时启动）全局播放页 http 服务；失败返回 None，调用方退回 file://。"""
    global _VIDEO_HTTP, _VIDEO_HTTP_FAILED
    if _VIDEO_HTTP is not None:
        return _VIDEO_HTTP
    if _VIDEO_HTTP_FAILED:
        return None
    try:
        srv = VideoHttpServer().start()
        _VIDEO_HTTP = srv
        log_action("本地视频服务已启动", "端口=%d | 地址=%s" % (srv.port, srv.base_url))
        return srv
    except Exception as exc:
        _VIDEO_HTTP_FAILED = True
        log_error("本地视频服务启动失败", repr(exc))
        return None


def _player_media_src(payload, server=None):
    """本地视频在播放页里的 src：优先本地 http 源（同源且支持 Range），否则退回 file://。"""
    if server is not None:
        try:
            return server.media_url(payload)
        except Exception as exc:
            log_warn("本地视频转 http 源失败", "%s | %r" % (payload, exc))
    return file_url(payload)


def build_player_html(target, server=None):
    """把播放目标包成一张本地播放页：B 站/普通网页用 <iframe>，媒体直链与本地视频用 <video>。

    server 传 VideoHttpServer 时，本地视频改由本地 http 源提供（file:// 下 Chromium 会
    卡住跨源媒体与 iframe Referer，见 VideoHttpServer 注释）。
    """
    kind, payload, _label = target
    script = ""
    if kind == "bili":
        src = ensure_autoplay(payload if str(payload).lower().startswith("http")
                              else BILI_PLAYER_URL % payload)
        inner = ('<iframe src="%s" title="哔哩哔哩视频播放器" '
                 'allow="fullscreen; autoplay; encrypted-media; picture-in-picture" '
                 'allowfullscreen></iframe>' % html_escape(src))
    elif kind == "web":
        # v1.10.0：Chromium 不允许在 iframe 内直接渲染媒体文件（会显示破损图标错误页），
        # 因此把 *.mp4 之类的直链改用 <video> 播放；普通网页仍交给 iframe。
        if media_url(payload):
            inner = ('<video controls autoplay playsinline muted preload="auto" '
                     'src="%s"></video>' % html_escape(payload))
            script = PLAYER_AUTOPLAY_JS
        else:
            inner = ('<iframe src="%s" title="网页播放器" '
                     'allow="fullscreen; autoplay; encrypted-media; picture-in-picture" '
                     'allowfullscreen></iframe>' % html_escape(payload))
    elif kind == "local":
        inner = ('<video controls autoplay playsinline muted preload="auto" '
                 'src="%s"></video>' % html_escape(_player_media_src(payload, server)))
        script = PLAYER_AUTOPLAY_JS
    else:
        return ""
    return PLAYER_PAGE_TPL % (inner, script)


def find_edge_exe():
    """定位系统 Microsoft Edge（Win10/11 自带，作为内嵌播放内核）。找不到返回空串。"""
    local = os.environ.get("LOCALAPPDATA") or ""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)",
                     "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles") or r"C:\Program Files",
                     "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe") if local else "",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def find_window_by_pid(pid):
    """按进程号找该进程最大的可见顶层窗口，用于把 Edge 播放窗嵌进本程序。"""
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    hits = []

    def _callback(hwnd, _lparam):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left > 200 and rect.bottom - rect.top > 120:
            hits.append(hwnd)
        return True

    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(_callback)
    user32.EnumWindows(callback, 0)
    return hits[0] if hits else 0


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
        if token.startswith("!["):
            alt, src = parse_image_markup(token)
            return alt or os.path.basename(src) or "图片"
        link = re.match(r"\[([^\]]*)\]\(([^)]*)\)", token)
        if link:
            return link.group(1) or link.group(2)
        return token

    return _INLINE_RE.sub(_repl, text)


def render_inline(widget, text, extra_tags=(), image_ctx=None):
    """把带行内标记的文本写入 Text 控件，并附加样式标签。

    image_ctx 非空时，![说明](路径) 会渲染为真实图片（v1.7.0）。
    """
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            widget.insert("end", text[pos:match.start()], tuple(extra_tags) or ("normal",))
        token = match.group(0)
        if token.startswith("!["):
            alt, src = parse_image_markup(token)
            render_image(widget, alt, src, extra_tags, image_ctx)
        elif token.startswith("`"):
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


def render_markdown(widget, md_text, image_ctx=None, video_ctx=None):
    """Markdown -> Text 控件渲染；image_ctx 渲染图片（v1.7.0），video_ctx 渲染视频（v1.8.0）。"""
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

        # 2. 视频块（v1.8.0）：以 <iframe / <video 开头的行，向下收集到标签闭合
        head_line = line.strip().lower()
        if head_line.startswith(("<iframe", "<video")):
            block_lines = [line]
            index += 1
            while (index < total and len(block_lines) < 60
                   and not html_block_complete("\n".join(block_lines))):
                block_lines.append(lines[index])
                index += 1
            render_video(widget, "\n".join(block_lines), ("normal",), video_ctx)
            continue

        # 3. 裸视频地址独立成行：B 站链接 / BV 号 / 本地视频路径
        if looks_like_video_line(line, (video_ctx or {}).get("base_dir")):
            render_video(widget, line.strip(), ("normal",), video_ctx)
            index += 1
            continue

        # 4. 空行
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
            render_inline(widget, quote.group(1), ("quote",), image_ctx)
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
                render_inline(widget, task.group(2), base_tags, image_ctx)
            elif marker in ("-", "*", "+"):
                widget.insert("end", "• ", base_tags)
                render_inline(widget, body, base_tags, image_ctx)
            else:
                widget.insert("end", "%s " % marker, base_tags)
                render_inline(widget, body, base_tags, image_ctx)
            widget.insert("end", "\n", base_tags)
            index += 1
            continue

        # 8. 普通段落
        render_inline(widget, line.strip(), ("normal",), image_ctx)
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
        # 只读说明文本：给「复制 / 全选」，方便用户拷走更新说明
        install_text_context_menu(notes_text, palette_getter=lambda p=palette: p,
                                  editable=False)

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
        # 中文右键菜单（v1.9.0）：三个输入区的 TextContextMenu 控制器，主题切换时统一重上色
        self._context_menus = []
        # 预览图片（v1.7.0）：解码缓存 / 「图片字符位置 -> 本地路径」映射 / 当前可用宽度
        self._image_cache = {}
        self._image_paths = {}
        self._image_max_width = IMAGE_PREVIEW_MIN_W
        # 预览视频（v1.8.0）：「视频条目字符位置 -> 播放目标」映射 / 内嵌播放进程与窗口句柄
        self._video_paths = {}
        self._video_proc = None
        self._video_hwnd = None
        self._video_current = None
        self._video_deadline = 0.0
        self._video_polls = 0          # 已轮询次数（v1.10.0，写入链路日志）
        self._video_profile = None     # 本次播放专用的 Edge 配置目录（v1.10.0）
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
        # v1.10.0：清掉历史播放遗留的 Edge 配置目录，避免 video_cache 无限膨胀
        try:
            self._cleanup_video_profiles()
        except Exception as exc:
            log_warn("清理历史 Edge 配置目录异常", repr(exc))
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

    def _attach_context_menu(self, widget, editable=True, on_changed=None):
        """给输入控件挂中文右键菜单（v1.9.0），并登记以便主题切换时重上色。"""
        menu = install_text_context_menu(
            widget, palette_getter=lambda: self.palette,
            editable=editable, on_changed=on_changed)
        self._context_menus.append(menu)
        return menu

    def _after_context_edit(self):
        """右键菜单改过编辑器内容后立即同步脏标记、预览与统计。"""
        try:
            self._sync_dirty_state()
        except Exception:
            pass
        self.schedule_preview()
        self.update_stats()

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
            ("插入图片", self.insert_image_file),
            ("插入视频", self.insert_video),
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
        self._attach_context_menu(self.cmd_text, editable=True)

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
        self._attach_context_menu(self.editor, editable=True,
                                  on_changed=self._after_context_edit)

        # 右：实时预览
        right = ttk.LabelFrame(paned, text=" ③ 实时预览 ")
        paned.add(right, weight=2)
        right_head = ttk.Frame(right)
        right_head.pack(fill="x", padx=6, pady=(4, 0))
        self._make_hide_button(right_head, "right").pack(side="right")
        bind_colors(ttk.Label(right_head, text="所见即所得（编辑区改动后自动刷新）",
                              font=(FONT_CN, 9)),
                    palette, None, "hint_fg").pack(side="left")
        # 内嵌视频播放面板（v1.8.0）：默认隐藏，点预览里的「▶ 视频」条目才出现。
        # tkinter 的 Text 放不了 HTML 播放器，所以播放器是 Edge 内核的独立子窗口。
        # v1.10.0：面板改为挂在主窗口底部并横跨整窗，画面比原先塞在预览栏里大得多。
        self.video_title_var = tk.StringVar(value="")
        self.video_panel = ttk.LabelFrame(self.root, text=" ▶ 视频播放器 ")
        video_head = ttk.Frame(self.video_panel)
        video_head.pack(fill="x", padx=6, pady=(2, 0))
        ttk.Button(video_head, text="关闭", padding=(6, 1),
                   command=self._stop_video).pack(side="right")
        ttk.Button(video_head, text="浏览器打开", padding=(6, 1),
                   command=self._open_video_in_browser).pack(side="right", padx=(0, 4))
        bind_colors(ttk.Label(video_head, textvariable=self.video_title_var,
                              font=(FONT_CN, 9)),
                    palette, None, "hint_fg").pack(side="left")
        self.video_host = tk.Frame(self.video_panel, bg="#000000",
                                   height=VIDEO_PANEL_H)
        self.video_host.pack(fill="x", padx=6, pady=6)
        self.video_host.pack_propagate(False)
        self._video_tip = tk.Label(self.video_host, bg="#000000", fg="#8b949e",
                                   font=(FONT_CN, 9),
                                   text="点上方预览里的「▶ 视频」条目开始播放"
                                        "（部分网站禁止被嵌入，可点「浏览器打开」）")
        self._video_tip.pack(expand=True)
        self.video_host.bind("<Configure>", self._place_video_window, add="+")

        r_wrap = ttk.Frame(right)
        r_wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self._right_wrap = r_wrap
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
        # 预览图片（v1.7.0）：悬停变手型，单击用系统看图程序打开原图
        self.preview.tag_bind("img", "<Button-1>", self._open_preview_image)
        self.preview.tag_bind("img", "<Enter>",
                              lambda _e: self.preview.configure(cursor="hand2"))
        self.preview.tag_bind("img", "<Leave>",
                              lambda _e: self.preview.configure(cursor="arrow"))
        # 预览视频（v1.8.0）：悬停变手型，单击在内嵌播放面板里真播放
        self.preview.tag_bind("video", "<Button-1>", self._open_preview_video)
        self.preview.tag_bind("video", "<Enter>",
                              lambda _e: self.preview.configure(cursor="hand2"))
        self.preview.tag_bind("video", "<Leave>",
                              lambda _e: self.preview.configure(cursor="arrow"))
        self.preview.bind("<Configure>", self._on_preview_configure, add="+")
        # 只读控件：只给「复制 / 全选」，其余动作置灰不出现
        self._attach_context_menu(self.preview, editable=False)

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
        for ctx in getattr(self, "_context_menus", []) or []:
            ctx.restyle(self.palette)
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
            self._stop_video(silent=True)      # 结束内嵌视频播放进程（v1.8.0）
        except Exception:
            pass
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
        self.root.bind("<Control-Shift-I>", lambda e: self.insert_image_file())
        self.root.bind("<Control-Shift-i>", lambda e: self.insert_image_file())
        self.root.bind("<Control-Shift-V>", lambda e: self.insert_video())
        self.root.bind("<Control-Shift-v>", lambda e: self.insert_video())
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
            render_markdown(self.preview, content, self._preview_image_ctx(),
                            self._preview_video_ctx())
            self.update_stats()
        except Exception as exc:  # 预览出错不影响编辑
            log_action("预览异常", repr(exc))
            self.status_var.set("预览渲染失败：%s" % exc)

    def _preview_image_ctx(self):
        """图片渲染上下文：基准目录（当前文档所在目录）、可用宽度、缓存与路径映射。"""
        base_dir = os.getcwd()
        if self.current_file:
            try:
                base_dir = os.path.dirname(os.path.abspath(self.current_file))
            except Exception:
                base_dir = os.getcwd()
        try:
            width = int(self.preview.winfo_width())
        except (tk.TclError, ValueError, AttributeError):
            width = 0
        if width <= 1:
            width = IMAGE_PREVIEW_MIN_W + IMAGE_PREVIEW_MARGIN
        max_width = max(IMAGE_PREVIEW_MIN_W, width - IMAGE_PREVIEW_MARGIN)
        self._image_max_width = max_width
        self._image_paths = {}
        return {"base_dir": base_dir, "max_width": max_width,
                "cache": self._image_cache, "paths": self._image_paths}

    def _open_preview_image(self, event=None):
        """单击预览图片：用系统默认看图程序打开原图。"""
        if event is None:
            return "break"
        try:
            index = self.preview.index("@%d,%d" % (event.x, event.y))
        except Exception:
            return "break"
        path = self._image_paths.get(index)
        if not path:
            return "break"
        try:
            os.startfile(path)
            log_action("预览图片", path)
            self.status_var.set("已打开图片：%s" % os.path.basename(path))
        except Exception as exc:
            log_action("预览图片失败", "%s | %r" % (path, exc))
            messagebox.showwarning(APP_NAME,
                                   "无法打开图片：\n%s\n\n%s" % (path, exc),
                                   parent=self.root)
        return "break"

    # ---------------- 预览视频（v1.8.0） ----------------
    def _preview_video_ctx(self):
        """视频渲染上下文：基准目录 + 「条目字符位置 → 播放目标」映射（每次刷新重建）。"""
        base_dir = os.getcwd()
        if self.current_file:
            try:
                base_dir = os.path.dirname(os.path.abspath(self.current_file))
            except Exception:
                base_dir = os.getcwd()
        self._video_paths = {}
        return {"base_dir": base_dir, "paths": self._video_paths}

    def _open_preview_video(self, event=None):
        """单击预览里的「▶ 视频」条目：在预览栏底部内嵌面板里真播放。"""
        if event is None:
            return "break"
        try:
            index = self.preview.index("@%d,%d" % (event.x, event.y))
        except Exception:
            return "break"
        target = self._video_paths.get(index)
        if not target:
            return "break"
        self._play_video(target)
        return "break"

    def _activate_video_panel(self):
        """把播放面板挂到主窗口底部（横跨整窗，画面更大）；已挂则不动。

        注意 packing 顺序：paned 是 fill="both", expand=True，若在它之后 pack 面板，
        剩余空间为 0，面板会被压成一条（历史 bug：播放区高仅 61 像素，视频几乎看不见）。
        因此这里用 before=self.paned 把它插到 paned 之前，先分到固定高度。
        """
        try:
            if not self.video_panel.winfo_manager():
                self.video_panel.pack(side="bottom", fill="x", padx=8, pady=(0, 6),
                                      before=self.paned)
                log_detail("视频面板展开", "挂载位置=主窗口底部（before=paned）")
        except Exception as exc:
            log_error("视频面板展开失败", repr(exc))

    def _resize_video_host(self):
        """按主窗口宽度算播放区高度（16:9，200~VIDEO_PANEL_MAX_H 像素）。"""
        try:
            width = max(VIDEO_PANEL_MIN_W, int(self.root.winfo_width()) - 48)
        except Exception:
            width = 720
        height = max(200, min(int(width * 9 / 16.0), VIDEO_PANEL_MAX_H))
        try:
            self.video_host.configure(width=width, height=height)
            self.video_panel.update_idletasks()
        except Exception as exc:
            log_detail("视频播放区尺寸设置失败", repr(exc))
        log_detail("视频播放区尺寸", "%dx%d" % (width, height))
        return width, height

    def _play_video(self, target):
        """按播放目标拉起内嵌播放器；同一目标重复点击不重开进程。"""
        kind, payload, label = target
        if self._video_current == target and self._video_proc is not None:
            self._activate_video_panel()
            self._place_video_window()
            return
        self._stop_video(silent=True)
        self._video_current = target
        html = build_player_html(target)
        if not html:
            log_warn("视频地址不可播放", "kind=%s | payload=%s" % (kind, payload))
            messagebox.showwarning(APP_NAME, "这个视频地址无法播放。", parent=self.root)
            return
        log_detail("播放目标", "kind=%s | 方式=%s | payload=%s | 页面字节=%d"
                   % (kind, "iframe" if kind == "bili" or not media_url(payload)
                      else "video", payload, len(html)))
        self._activate_video_panel()
        self._resize_video_host()
        self.root.update_idletasks()
        self.video_title_var.set("%s · %s" % (
            {"bili": "B站视频", "web": "网页播放器", "local": "本地视频"}.get(kind, "视频"),
            label))
        if self._spawn_video_window(html):
            self.status_var.set("正在加载视频：%s" % label)

    def _new_video_profile(self, cache_dir):
        """为本次播放新建独立 Edge 配置目录：避免复用已运行 Edge 进程导致窗口找不到。"""
        base = os.path.join(cache_dir, VIDEO_PROFILE_DIR)
        try:
            os.makedirs(base, exist_ok=True)
        except Exception as exc:
            log_warn("Edge 配置目录创建失败", repr(exc))
            return os.path.join(base, "edge_%d" % int(time.time()))
        profile = os.path.join(base, "edge_%s_%s" % (
            time.strftime("%Y%m%d%H%M%S"), uuid.uuid4().hex[:6]))
        log_detail("Edge 配置目录", profile)
        return profile

    def _drop_video_profile(self):
        """删除本次播放的临时 Edge 配置目录（Edge 刚退出时文件可能仍被占用，故重试）。"""
        profile = getattr(self, "_video_profile", None)
        self._video_profile = None
        if not profile:
            return
        last = None
        for attempt in range(3):
            if not os.path.isdir(profile):
                log_detail("Edge 配置目录已清理", profile)
                return
            try:
                shutil.rmtree(profile, ignore_errors=False)
                log_detail("Edge 配置目录已清理",
                           "%s（第 %d 次尝试）" % (profile, attempt + 1))
                return
            except Exception as exc:
                last = exc
                time.sleep(0.2)
        log_warn("Edge 配置目录清理失败（下次启动会再清理）", "%s | %r" % (profile, last))

    def _cleanup_video_profiles(self, keep=VIDEO_PROFILE_KEEP):
        """启动时清理历史 Edge 配置目录，只保留最近 keep 个（避免无限增长）。"""
        base = os.path.join(video_cache_dir(), VIDEO_PROFILE_DIR)
        if not os.path.isdir(base):
            return 0
        items = []
        try:
            for name in os.listdir(base):
                full = os.path.join(base, name)
                if os.path.isdir(full):
                    try:
                        items.append((os.path.getmtime(full), full))
                    except OSError:
                        pass
        except Exception as exc:
            log_warn("扫描历史 Edge 配置目录失败", repr(exc))
            return 0
        items.sort(reverse=True)
        removed = 0
        for _mtime, full in items[keep:]:
            try:
                shutil.rmtree(full, ignore_errors=True)
                removed += 1
            except Exception:
                pass
        log_detail("清理历史 Edge 配置目录", "保留 %d 个，移除 %d 个 | %s"
                   % (min(len(items), keep), removed, base))
        return removed

    def _spawn_video_window(self, html):
        """把播放页写成临时 HTML，用 Edge 应用窗口模式拉起，随后嵌进播放面板。"""
        edge = find_edge_exe()
        if not edge:
            log_warn("视频播放器不可用", "未找到 msedge.exe")
            messagebox.showwarning(
                APP_NAME,
                "没有找到 Microsoft Edge。\n\n"
                "内嵌视频播放依赖系统自带 Edge（Chromium 内核），"
                "也可以点「浏览器打开」用默认浏览器观看。",
                parent=self.root)
            return False
        try:
            cache_dir = video_cache_dir()
            page = os.path.join(cache_dir, "player_%s.html"
                                % hashlib.md5(html.encode("utf-8")).hexdigest()[:12])
            with open(page, "w", encoding="utf-8") as fp:
                fp.write(html)
        except Exception as exc:
            log_error("视频播放页写入失败", repr(exc))
            messagebox.showwarning(APP_NAME, "无法创建视频播放页：\n%r" % (exc,),
                                   parent=self.root)
            return False
        # v1.10.0：播放页改由本机回环 http 服务提供。file:// 页面下 Chromium 会给子框架
        # 传空 Referer 并卡住跨源媒体，实测导致 B 站整块黑屏、网页 mp4 readyState 恒为 0
        # （temp/probe32~probe35 证据）；改走 http://127.0.0.1:<port>/ 后四类输入均出画面。
        page_url = file_url(page)
        server = video_http_server()
        if server is not None:
            try:
                if self._video_current:
                    html = build_player_html(self._video_current, server=server)
                    with open(page, "w", encoding="utf-8") as fp:
                        fp.write(html)
                page_url = server.page_url(html)
                log_detail("视频播放页改走本地 http 源",
                           "端口=%d | 页面=%s" % (server.port, page_url))
            except Exception as exc:
                log_warn("本地 http 源不可用，退回 file://", repr(exc))
                page_url = file_url(page)
        else:
            log_warn("本地 http 源不可用，退回 file://", "video_http_server() 返回 None")
        try:
            width = max(VIDEO_PANEL_MIN_W, int(self.video_host.winfo_width()))
            height = max(240, int(self.video_host.winfo_height()) + 80)
        except Exception:
            width, height = 720, 480
        profile = self._new_video_profile(cache_dir)
        self._video_profile = profile
        args = [
            edge,
            "--app=%s" % page_url,
            "--user-data-dir=%s" % profile,
            "--window-size=%d,%d" % (width, height),
            "--autoplay-policy=no-user-gesture-required",
            "--no-first-run", "--no-default-browser-check",
            "--disable-features=Translate",
            # 内嵌窗口常被系统判成遮挡/后台窗口，这三项避免渲染与定时器被节流而不出画面
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
        ]
        log_detail("启动视频播放器", " | ".join(args))
        try:
            self._video_proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as exc:
            log_error("视频播放器启动失败", repr(exc))
            self._video_proc = None
            self._drop_video_profile()
            messagebox.showwarning(APP_NAME, "视频播放器启动失败：\n%r" % (exc,),
                                   parent=self.root)
            return False
        log_action("视频播放器已启动", "pid=%s | 尺寸=%dx%d | 配置目录=%s"
                   % (self._video_proc.pid, width, height, profile))
        self._video_hwnd = None
        self._video_polls = 0
        self._video_deadline = time.time() + VIDEO_EDGE_WAIT_MS / 1000.0
        self.root.after(VIDEO_WINDOW_POLL_MS, self._watch_video_window)
        log_action("视频播放", "%s | 页=%s | pid=%s | profile=%s"
                   % (self.video_title_var.get() or "-", page,
                      self._video_proc.pid, profile))
        return True

    def _watch_video_window(self):
        """轮询等待 Edge 播放窗口出现，出现后转成面板子窗口。"""
        if self._video_proc is None:
            return
        if self._video_hwnd:
            self._place_video_window()
            return
        self._video_polls = getattr(self, "_video_polls", 0) + 1
        try:
            hwnd = find_window_by_pid(self._video_proc.pid)
        except Exception as exc:
            hwnd = 0
            log_error("查找播放窗口异常", repr(exc))
        log_detail("等待播放窗口", "第 %d 次 | pid=%s | hwnd=%s | 剩余 %.1fs"
                   % (self._video_polls, self._video_proc.pid, hwnd,
                      max(0.0, self._video_deadline - time.time())))
        if hwnd and self._embed_video_window(hwnd):
            return
        exited = self._video_proc.poll() is not None
        if exited:
            log_warn("播放器进程已退出", "pid=%s 返回码=%s"
                     % (self._video_proc.pid, self._video_proc.returncode))
        if time.time() > self._video_deadline:
            log_warn("视频窗口等待超时", "已轮询 %d 次 | 进程已退出=%s"
                     % (self._video_polls, exited))
            self.status_var.set("视频加载较慢，可点「浏览器打开」直接观看")
            if exited:
                self.status_var.set("视频播放器已退出")
            self._stop_video(silent=True)
            return
        self.root.after(VIDEO_WINDOW_POLL_MS, self._watch_video_window)

    def _embed_video_window(self, hwnd):
        """把 Edge 顶层窗口改成 WS_CHILD 并挂到播放面板下，(0,0) 铺满。"""
        user32 = ctypes.windll.user32
        try:
            parent = self.video_host.winfo_id()
            old_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            style = (old_style & ~WIN_DROP_STYLE) | WIN_CHILD_STYLE
            user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            new_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            user32.SetParent(hwnd, parent)
            log_detail("视频窗口样式与挂载",
                       "hwnd=%s | host=%s | style %#x → %#x（读回 %#x）| SetParent 后父窗口=%s"
                       % (hwnd, parent, old_style & 0xFFFFFFFF,
                          style & 0xFFFFFFFF, new_style & 0xFFFFFFFF,
                          user32.GetParent(hwnd)))
            self._video_hwnd = hwnd
            try:
                self._video_tip.pack_forget()
            except Exception:
                pass
            self._place_video_window()
        except Exception as exc:
            log_error("视频窗口嵌入失败", "hwnd=%s | %r" % (hwnd, exc))
            self._video_hwnd = None
            return False
        log_action("视频窗口已嵌入", "hwnd=%s | 轮询 %d 次"
                   % (hwnd, getattr(self, "_video_polls", 0)))
        return True

    def _place_video_window(self, event=None):
        """播放面板尺寸变化时，让嵌入的播放窗口跟着铺满。"""
        if not self._video_hwnd:
            return
        try:
            width = max(1, int(self.video_host.winfo_width()))
            height = max(1, int(self.video_host.winfo_height()))
            if not ctypes.windll.user32.MoveWindow(self._video_hwnd, 0, 0,
                                                   width, height, True):
                log_detail("视频窗口定位失败", "hwnd=%s | %dx%d"
                           % (self._video_hwnd, width, height))
            elif not getattr(self, "_video_placed", False):
                self._video_placed = True
                log_detail("视频窗口已铺满播放区", "hwnd=%s | %dx%d"
                           % (self._video_hwnd, width, height))
        except Exception as exc:
            log_error("视频窗口定位异常", repr(exc))

    def _stop_video(self, silent=False):
        """停止播放：解除父子关系、结束 Edge 播放进程、清理临时配置目录、收起面板。"""
        hwnd, proc = self._video_hwnd, self._video_proc
        self._video_hwnd = None
        self._video_proc = None
        self._video_current = None
        if hwnd:
            try:
                ctypes.windll.user32.SetParent(hwnd, 0)
                # 先礼后兵：让窗口自己关闭，避免进程已 daemon 化时留下孤立窗口
                ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            except Exception as exc:
                log_detail("视频窗口解挂失败", repr(exc))
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
                log_detail("视频播放进程已结束", "pid=%s | 返回码=%s"
                           % (proc.pid, proc.returncode))
            except Exception:
                try:
                    proc.kill()
                    log_warn("视频播放进程强制结束", "pid=%s" % proc.pid)
                except Exception as exc:
                    log_warn("视频播放进程结束失败", repr(exc))
        self._video_placed = False
        self._drop_video_profile()
        try:
            self.video_panel.pack_forget()
        except Exception:
            pass
        try:
            self._video_tip.pack(expand=True)
        except Exception:
            pass
        if hwnd or proc is not None:
            log_action("视频播放已关闭", "hwnd=%s | pid=%s"
                       % (hwnd or "-", getattr(proc, "pid", "-")))
        if not silent:
            self.status_var.set("已关闭视频播放器")

    def _open_video_in_browser(self):
        """当前视频改用系统默认浏览器观看（内嵌播放的兜底出口）。"""
        target = self._video_current
        if not target:
            messagebox.showinfo(APP_NAME, "还没有在预览里选择视频。", parent=self.root)
            return
        kind, payload, label = target
        if kind == "bili":
            url = bili_clean_url(payload if payload.startswith("http")
                                 else BILI_PLAYER_URL % payload)
        elif kind == "web":
            url = payload
        else:
            url = file_url(payload)
        try:
            webbrowser.open(url)
            self.status_var.set("已在浏览器打开：%s" % label)
        except Exception as exc:
            log_action("浏览器打开视频失败", "%s | %r" % (url, exc))
            messagebox.showwarning(APP_NAME, "无法打开浏览器：\n%r" % (exc,),
                                   parent=self.root)

    def _on_preview_configure(self, event=None):
        """预览区宽度变化超过 60px 时重排图片（图片按当前宽度等比缩放）。"""
        if event is None or self.preview_job is not None:
            return
        try:
            width = int(event.width)
        except (AttributeError, ValueError):
            return
        if abs(width - (self._image_max_width + IMAGE_PREVIEW_MARGIN)) < 60:
            return
        self.schedule_preview(delay=420)

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

    def insert_image_file(self):
        """选择本地图片并插入 ![说明](路径)；路径优先相对当前文档目录（v1.7.0）。"""
        initial = os.getcwd()
        base_dir = ""
        if self.current_file:
            try:
                base_dir = os.path.dirname(os.path.abspath(self.current_file))
                initial = base_dir
            except Exception:
                base_dir = ""
        path = filedialog.askopenfilename(
            parent=self.root, title="选择要插入的图片", initialdir=initial,
            filetypes=[("图片文件", " ".join("*" + ext for ext in IMAGE_EXTENSIONS)),
                       ("所有文件", "*.*")])
        if not path:
            log_action("语法插入", "插入本地图片（已取消）")
            return
        target = image_insert_target(path, base_dir)
        alt = os.path.splitext(os.path.basename(path))[0]
        sel = self._editor_selection()
        if sel:
            start, end, selected = sel
            self._replace_range(start, end, "![%s](%s)" % (selected, target))
            log_action("语法插入", "插入本地图片（选中文本作说明）%s" % path)
            return
        self._editor_insert("![%s](%s)" % (alt, target))
        log_action("语法插入", "插入本地图片 %s" % path)
        self.status_var.set("已插入图片：%s" % os.path.basename(path))

    def insert_video(self):
        """插入视频（v1.8.1）：剪贴板里是干净的视频内容才直接采纳，否则弹多行输入框。

        修复要点：以前剪贴板里只要沾到 "<iframe" / "http" 就被整段原样插进文档，
        用户复制的聊天或文档文字会被当成视频插进来（表现为"插入视频不好使"）。
        """
        base_dir = ""
        if self.current_file:
            try:
                base_dir = os.path.dirname(os.path.abspath(self.current_file))
            except Exception:
                base_dir = ""
        clip = ""
        try:
            clip = (self.root.clipboard_get() or "").strip()
        except Exception:
            clip = ""
        markup = ""
        source = ""
        if clip:
            markup = build_video_markup(clip, base_dir)
            if markup:
                source = "剪贴板"
        if not markup:
            initial = ""
            low_clip = clip.lower()
            if clip and ("<iframe" in low_clip or "<video" in low_clip
                         or "http://" in low_clip or "https://" in low_clip):
                initial = clip[:2000]
            value = self._ask_video_text(initial=initial,
                                         clip_rejected=bool(clip))
            if value is None:
                log_action("语法插入", "插入视频（已取消）")
                return
            value = value.strip()
            if value:
                markup = build_video_markup(value, base_dir)
                if not markup:
                    messagebox.showwarning(
                        APP_NAME,
                        "没能识别这段视频地址。\n\n"
                        "只支持：完整 iframe / <video> 标记、B 站播放页或视频链接、"
                        "BV 号、网页播放器地址、本地视频文件。\n"
                        "如果粘贴的内容里夹带了别的话，请只保留视频标记或链接。",
                        parent=self.root)
                    return
                source = "手动输入"
            else:
                path = filedialog.askopenfilename(
                    parent=self.root, title="选择要插入的视频",
                    initialdir=base_dir or os.getcwd(),
                    filetypes=[("视频文件",
                                " ".join("*" + ext for ext in VIDEO_EXTENSIONS)),
                               ("所有文件", "*.*")])
                if not path:
                    log_action("语法插入", "插入本地视频（已取消）")
                    return
                markup = build_video_markup(path, base_dir)
                if not markup:
                    messagebox.showwarning(APP_NAME, "无法生成视频标记，请检查文件。",
                                           parent=self.root)
                    return
                source = "本地文件"
        ranges = self.editor.tag_ranges("sel")
        if ranges:
            self._replace_range(ranges[0], ranges[1], markup,
                                caret_offset=len(markup))
        else:
            self._editor_insert(markup)
            self.editor.see("insert")
        log_action("语法插入", "插入视频（%s）%.60s"
                   % (source, markup.replace("\n", " ")))
        self.status_var.set("已插入视频（来源：%s），点预览里的「▶」即可播放" % source)

    def _ask_video_text(self, initial="", clip_rejected=False):
        """多行"插入视频"输入框：粘贴多行 iframe 不会被单行框挤成一行。

        返回输入的文本；取消返回 None；点「选择本地视频」或留空确定返回空串。
        """
        result = {"value": None}
        win = tk.Toplevel(self.root)
        win.title("插入视频")
        win.transient(self.root)
        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=("粘贴 B 站视频链接 / BV 号 / iframe 代码 / 网页地址：\n"
                              "（留空则改为选择本地视频文件）"),
                  justify="left", font=(FONT_CN, 10)).pack(anchor="w")
        if clip_rejected:
            ttk.Label(body, text="剪贴板内容不是可识别的视频，已忽略。",
                      justify="left", font=(FONT_CN, 9),
                      foreground="#b26a00").pack(anchor="w", pady=(3, 0))
        box = tk.Text(body, width=76, height=8, wrap="char", undo=True,
                      font=(FONT_MONO, 10))
        box.pack(fill="both", expand=True, pady=(8, 6))
        self._attach_context_menu(box, editable=True)
        if initial:
            box.insert("1.0", initial)
        ttk.Label(body, text="Ctrl+Enter 确定 · Esc 取消",
                  font=(FONT_CN, 9), foreground="#777777").pack(anchor="w")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(8, 0))

        def _ok(event=None):
            result["value"] = box.get("1.0", "end-1c")
            win.destroy()
            return "break"

        def _cancel(event=None):
            result["value"] = None
            win.destroy()
            return "break"

        def _pick_file():
            result["value"] = ""
            win.destroy()

        ttk.Button(row, text="确定", command=_ok, padding=(14, 3)).pack(side="right")
        ttk.Button(row, text="取消", command=_cancel,
                   padding=(14, 3)).pack(side="right", padx=(0, 6))
        ttk.Button(row, text="选择本地视频…", command=_pick_file,
                   padding=(14, 3)).pack(side="left")
        box.bind("<Control-Return>", _ok)
        box.bind("<Escape>", _cancel)
        win.bind("<Escape>", _cancel)
        win.protocol("WM_DELETE_WINDOW", _cancel)
        win.update_idletasks()
        try:
            x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 3
            win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        except Exception:
            pass
        box.focus_set()
        box.mark_set("insert", "end-1c")
        win.grab_set()
        win.wait_window()
        return result["value"]

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
