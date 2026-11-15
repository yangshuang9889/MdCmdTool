# -*- coding: utf-8 -*-
"""v1.7.0 补丁：预览区显示图片（![说明](路径) 渲染为真实图片）。

改动全部为「精确字符串替换」，每处替换都断言命中次数，避免错改。
执行前请确认已存在 爽哥MD命令生成工具.py.v160.bak 备份。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")

R = []          # (名称, 原文, 新文, 期望命中次数)


def add(name, old, new, count=1):
    R.append((name, old, new, count))


# ---------------------------------------------------------------- 1. 版本号
add("版本号",
    'APP_VERSION = "1.6.0"',
    'APP_VERSION = "1.7.0"')

# ---------------------------------------------------------------- 2. 导入 Pillow / unquote
add("导入 Pillow",
    '''try:  # 仅 Windows 提供 winreg；缺失时文件关联功能降级为不可用
    import winreg
except Exception:  # pragma: no cover
    winreg = None''',
    '''try:  # 仅 Windows 提供 winreg；缺失时文件关联功能降级为不可用
    import winreg
except Exception:  # pragma: no cover
    winreg = None

from urllib.parse import unquote

try:  # 可选依赖：装了 Pillow 才能预览 JPG/BMP/WEBP 并做平滑缩放，缺失时退化为 Tk 原生格式
    from PIL import Image as _PILImage
    from PIL import ImageTk as _PILImageTk
    _PIL_OK = True
except Exception:  # pragma: no cover
    _PILImage = None
    _PILImageTk = None
    _PIL_OK = False''')

# ---------------------------------------------------------------- 3. 图片常量
add("图片常量",
    'DIRTY_TITLE_MARK = " *"             # 窗口标题未保存标记（v1.5.0）',
    '''DIRTY_TITLE_MARK = " *"             # 窗口标题未保存标记（v1.5.0）

# 预览图片（v1.7.0）：预览区把 ![说明](路径) 渲染成真实图片
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
                    ".tif", ".tiff", ".ico", ".ppm", ".pgm")
IMAGE_PREVIEW_MAX_H = 480       # 单张图片在预览区的最大高度（像素）
IMAGE_PREVIEW_MARGIN = 56       # 预览区左右留白（内边距 + 滚动条）
IMAGE_PREVIEW_MIN_W = 240       # 预览区过窄时的兜底宽度
IMAGE_CACHE_LIMIT = 32          # 解码缓存条数上限，超出整体清空''')

# ---------------------------------------------------------------- 4. 行内正则加图片分支
add("行内正则",
    '''_INLINE_RE = re.compile(
    r"(`[^`\\n]+`"                      # 行内代码''',
    '''_INLINE_RE = re.compile(
    r"(!\\[[^\\]\\n]*\\]\\([^)\\n]*\\)"      # 图片（v1.7.0，必须先于链接匹配）
    r"|`[^`\\n]+`"                      # 行内代码''')

# ---------------------------------------------------------------- 5. 预览标签
add("预览标签",
    '''    ("hint", {"font": (FONT_CN, 10, "italic"), "foreground": "#9aa5b1"}),
]''',
    '''    ("hint", {"font": (FONT_CN, 10, "italic"), "foreground": "#9aa5b1"}),
    ("img", {"spacing1": 6, "spacing3": 6}),
    ("imgfail", {"font": (FONT_CN, 9, "italic"), "foreground": "#b04a3a"}),
]''')

# ---------------------------------------------------------------- 6. 新增图片渲染函数块
add("图片函数块",
    'def plain_inline(text):\n    """去掉行内标记，取纯文本（用于标题等场景）。"""',
    '''# ---------------------------------------------------------------------------
# 预览图片（v1.7.0）：把 ![说明](路径) 还原成真实图片显示
# ---------------------------------------------------------------------------
_IMAGE_TOKEN_RE = re.compile(r"!\\[([^\\]\\n]*)\\]\\(([^)\\n]*)\\)")


def parse_image_markup(token):
    """拆解 ![说明](目标) → (说明, 目标)；目标去掉 <> 包裹与 "标题"。"""
    match = _IMAGE_TOKEN_RE.match((token or "").strip())
    if not match:
        return "", (token or "").strip()
    alt = match.group(1).strip()
    raw = match.group(2).strip()
    if raw.startswith("<") and raw.endswith(">"):
        return alt, raw[1:-1].strip()
    titled = re.match(r"^(\\S+)\\s+(\\"[^\\"]*\\"|'[^']*')$", raw)
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
    text = str(target).replace("\\\\", "/")
    if " " in text:
        text = "<%s>" % text
    return text


def plain_inline(text):
    """去掉行内标记，取纯文本（用于标题等场景）。"""''')

# ---------------------------------------------------------------- 7. plain_inline 处理图片
add("纯文本取图",
    '''        link = re.match(r"\\[([^\\]]*)\\]\\(([^)]*)\\)", token)
        if link:
            return link.group(1) or link.group(2)
        return token''',
    '''        if token.startswith("!["):
            alt, src = parse_image_markup(token)
            return alt or os.path.basename(src) or "图片"
        link = re.match(r"\\[([^\\]]*)\\]\\(([^)]*)\\)", token)
        if link:
            return link.group(1) or link.group(2)
        return token''')

# ---------------------------------------------------------------- 8. render_inline 支持图片
add("行内渲染图片",
    '''def render_inline(widget, text, extra_tags=()):
    """把带行内标记的文本写入 Text 控件，并附加样式标签。"""
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            widget.insert("end", text[pos:match.start()], tuple(extra_tags) or ("normal",))
        token = match.group(0)
        if token.startswith("`"):''',
    '''def render_inline(widget, text, extra_tags=(), image_ctx=None):
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
        elif token.startswith("`"):''')

# ---------------------------------------------------------------- 9. render_markdown 透传上下文
add("渲染主入口签名",
    '''def render_markdown(widget, md_text):
    """Markdown -> Text 控件渲染。"""''',
    '''def render_markdown(widget, md_text, image_ctx=None):
    """Markdown -> Text 控件渲染；image_ctx 用于渲染图片（v1.7.0）。"""''')

add("引用行传上下文",
    '            render_inline(widget, quote.group(1), ("quote",))',
    '            render_inline(widget, quote.group(1), ("quote",), image_ctx)')

add("任务列表传上下文",
    '                render_inline(widget, task.group(2), base_tags)',
    '                render_inline(widget, task.group(2), base_tags, image_ctx)')

add("列表传上下文",
    '''            elif marker in ("-", "*", "+"):
                widget.insert("end", "• ", base_tags)
                render_inline(widget, body, base_tags)
            else:
                widget.insert("end", "%s " % marker, base_tags)
                render_inline(widget, body, base_tags)''',
    '''            elif marker in ("-", "*", "+"):
                widget.insert("end", "• ", base_tags)
                render_inline(widget, body, base_tags, image_ctx)
            else:
                widget.insert("end", "%s " % marker, base_tags)
                render_inline(widget, body, base_tags, image_ctx)''')

add("段落传上下文",
    '        render_inline(widget, line.strip(), ("normal",))',
    '        render_inline(widget, line.strip(), ("normal",), image_ctx)')

# ---------------------------------------------------------------- 10. 主窗口字段
add("图片状态字段",
    '''        self.preview_job = None
        self.buttons = {}''',
    '''        self.preview_job = None
        self.buttons = {}
        # 预览图片（v1.7.0）：解码缓存 / 「图片字符位置 -> 本地路径」映射 / 当前可用宽度
        self._image_cache = {}
        self._image_paths = {}
        self._image_max_width = IMAGE_PREVIEW_MIN_W''')

# ---------------------------------------------------------------- 11. 预览控件绑定图片事件
add("预览图片事件",
    '''        for name, options in preview_tag_options(palette):
            self.preview.tag_configure(name, **options)

        self._panel_widgets = {"left": left, "middle": middle, "right": right}''',
    '''        for name, options in preview_tag_options(palette):
            self.preview.tag_configure(name, **options)
        # 预览图片（v1.7.0）：悬停变手型，单击用系统看图程序打开原图
        self.preview.tag_bind("img", "<Button-1>", self._open_preview_image)
        self.preview.tag_bind("img", "<Enter>",
                              lambda _e: self.preview.configure(cursor="hand2"))
        self.preview.tag_bind("img", "<Leave>",
                              lambda _e: self.preview.configure(cursor="arrow"))
        self.preview.bind("<Configure>", self._on_preview_configure, add="+")

        self._panel_widgets = {"left": left, "middle": middle, "right": right}''')

# ---------------------------------------------------------------- 12. refresh_preview + 新方法
add("刷新预览传上下文",
    '''            content = self.editor.get("1.0", "end-1c")
            render_markdown(self.preview, content)
            self.update_stats()''',
    '''            content = self.editor.get("1.0", "end-1c")
            render_markdown(self.preview, content, self._preview_image_ctx())
            self.update_stats()''')

add("预览图片方法",
    '    def update_stats(self):',
    '''    def _preview_image_ctx(self):
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
                                   "无法打开图片：\\n%s\\n\\n%s" % (path, exc),
                                   parent=self.root)
        return "break"

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

    def update_stats(self):''')

# ---------------------------------------------------------------- 13. 插入本地图片按钮动作
add("插入本地图片",
    '    def insert_table_template(self):',
    '''    def insert_image_file(self):
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

    def insert_table_template(self):''')

# ---------------------------------------------------------------- 14. 工具栏按钮
add("工具栏按钮",
    '            ("图片链接", self.insert_image),',
    '''            ("图片链接", self.insert_image),
            ("插入图片", self.insert_image_file),''')

# ---------------------------------------------------------------- 15. 快捷键
add("快捷键",
    '        self.root.bind("<F1>", lambda e: self.show_help())',
    '''        self.root.bind("<Control-Shift-I>", lambda e: self.insert_image_file())
        self.root.bind("<Control-Shift-i>", lambda e: self.insert_image_file())
        self.root.bind("<F1>", lambda e: self.show_help())''')


def main():
    if not os.path.exists(SRC):
        print("源码不存在：%s" % SRC)
        return 2
    with io.open(SRC, encoding="utf-8-sig") as fp:
        text = fp.read()
    failed = []
    for name, old, new, count in R:
        hits = text.count(old)
        if hits != count:
            failed.append("%s：期望命中 %d 次，实际 %d 次" % (name, count, hits))
            continue
        text = text.replace(old, new, count)
        print("OK  %s（%d 处）" % (name, count))
    if failed:
        print("\n".join("FAIL " + item for item in failed))
        print("补丁未写入，源码保持不变。")
        return 1
    with io.open(SRC, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write(text)
    print("\n补丁写入完成：%s" % SRC)
    return 0


if __name__ == "__main__":
    sys.exit(main())
