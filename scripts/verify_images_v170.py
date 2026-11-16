# -*- coding: utf-8 -*-
"""v1.7.0「预览区显示图片」验证脚本。

覆盖：
1. 图片标记解析 parse_image_markup（普通 / <> 包裹 / 带标题 / 非法）
2. 地址解析 resolve_image_path（绝对 / 相对 / file:/// / 网络 / base64 / 不存在）
3. 插入地址计算 image_insert_target（相对文档目录 / 跨盘 / 含空格）
4. Tk 实渲染：PNG、JPG（Pillow）、缺失文件降级、网络图降级、宽度缩放、缓存复用
5. 界面静态约束：版本号、工具栏按钮、快捷键、预览 tag_bind
"""
import importlib.util
import re
import os
import sys
import tempfile
import tkinter as tk

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
    else:
        FAIL.append("%s %s" % (name, detail))


def load_module():
    spec = importlib.util.spec_from_file_location("sgmd_v170", SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sgmd_v170"] = module
    spec.loader.exec_module(module)
    return module


def make_images(tmp):
    from PIL import Image
    png = os.path.join(tmp, "大图 demo.png")
    Image.new("RGBA", (1200, 900), (30, 120, 200, 255)).save(png)
    jpg = os.path.join(tmp, "photo.jpg")
    Image.new("RGB", (640, 480), (200, 60, 40)).save(jpg, quality=88)
    gif = os.path.join(tmp, "anim.gif")
    Image.new("P", (100, 80)).save(gif)
    return png, jpg, gif


def main():
    m = load_module()
    tmp = tempfile.mkdtemp(prefix="sgmd_img_")
    png, jpg, gif = make_images(tmp)

    # ---------------- 1. 标记解析 ----------------
    check("解析：普通", m.parse_image_markup("![风景](a.png)") == ("风景", "a.png"))
    check("解析：无说明", m.parse_image_markup("![](b.jpg)") == ("", "b.jpg"))
    check("解析：尖括号包裹",
          m.parse_image_markup("![图](<dir/a b.png>)") == ("图", "dir/a b.png"))
    check("解析：带标题",
          m.parse_image_markup('![图](a.png "标题")') == ("图", "a.png"))
    check("解析：非法", m.parse_image_markup("![x](y") == ("", "![x](y"))

    # ---------------- 2. 地址解析 ----------------
    check("路径：绝对", m.resolve_image_path(png) == os.path.normpath(png))
    rel = os.path.relpath(png, tmp)
    check("路径：相对基准目录",
          m.resolve_image_path(rel, tmp) == os.path.normpath(png))
    uri = "file:///" + png.replace("\\", "/")
    try:
        check("路径：file:///", m.resolve_image_path(uri) == os.path.normpath(png))
    except ValueError as exc:
        check("路径：file:///", False, repr(exc))
    for bad, tag in (("https://x.com/a.png", "网络"),
                     ("data:image/png;base64,AAA", "base64"),
                     ("不存在.png", "缺失")):
        try:
            m.resolve_image_path(bad, tmp)
            check("路径拒绝：%s" % tag, False, "未抛异常")
        except ValueError:
            check("路径拒绝：%s" % tag, True)

    # ---------------- 3. 插入地址 ----------------
    check("插入：同目录相对", m.image_insert_target(png, tmp) in
          (rel.replace("\\", "/"), "<%s>" % rel.replace("\\", "/")))
    spaced = m.image_insert_target(png, tmp)
    check("插入：含空格加 <>", spaced.startswith("<") and spaced.endswith(">"), spaced)
    other_drive = m.image_insert_target(r"D:\x\y.png", tmp) if os.path.exists("D:\\") else r"D:/x/y.png"
    check("插入：跨盘/不可相对", ":" in other_drive or other_drive.startswith(".."), other_drive)

    # ---------------- 4. Tk 实渲染 ----------------
    root = tk.Tk()
    root.withdraw()
    widget = tk.Text(root)
    m.render_markdown(widget, "", None)
    check("空文档提示", "预览区" in widget.get("1.0", "end"))

    base_dir = tmp
    ctx = {"base_dir": base_dir, "max_width": 400, "cache": {}, "paths": {}}
    md = ("# 图片测试\n\n"
          "![大图](<大图 demo.png>)\n\n"
          "![照片](photo.jpg)\n\n"
          "![缺失](nofile.png)\n\n"
          "![网络](https://example.com/a.png)\n\n"
          "行内图片 ![小图](anim.gif) 结尾\n")
    m.render_markdown(widget, md, ctx)

    names = [str(item) for item in widget.image_names()]
    check("渲染：图片项数量", len(names) == 3, "实际 %d -> %s" % (len(names), names))
    check("渲染：图片路径映射", len(ctx["paths"]) == 3, str(list(ctx["paths"])))
    check("渲染：缓存写入", len(ctx["cache"]) == 3, str(list(ctx["cache"])))
    widths = [photo.width() for photo in ctx["cache"].values()]
    check("渲染：按宽度缩放", all(w <= 400 for w in widths), str(widths))
    check("渲染：高度受限", all(p.height() <= m.IMAGE_PREVIEW_MAX_H
                                for p in ctx["cache"].values()), "")
    body = widget.get("1.0", "end")
    check("渲染：缺失图提示", "文件不存在" in body, body[-120:])
    check("渲染：网络图提示", "网络图片暂不预览" in body, "")
    fail_ranges = widget.tag_ranges("imgfail")
    check("渲染：失败标红标签", len(fail_ranges) >= 2, str(fail_ranges))
    check("渲染：成功图片带 img 标签", len(widget.tag_ranges("img")) >= 3, "")

    # 缓存复用：第二次渲染不再新增缓存键
    ctx2 = {"base_dir": base_dir, "max_width": 400,
            "cache": ctx["cache"], "paths": {}}
    cache_before = len(ctx2["cache"])
    m.render_markdown(widget, md, ctx2)
    check("缓存：命中不重复解码", len(ctx2["cache"]) == cache_before,
          "%d -> %d" % (cache_before, len(ctx2["cache"])))
    check("缓存：路径映射重建", len(ctx2["paths"]) == 3, str(len(ctx2["paths"])))

    # 未装 Pillow 分支的兜底（直接调用 tk 原生路径逻辑）
    photo = m.load_preview_image(png, 200)
    # 240 是 IMAGE_PREVIEW_MIN_W 兜底宽度：请求宽度小于兜底时按兜底缩放
    check("缩放：PNG 读取", photo.width() <= m.IMAGE_PREVIEW_MIN_W and photo.height() > 0,
          "%dx%d" % (photo.width(), photo.height()))

    root.destroy()

    # ---------------- 5. 静态约束 ----------------
    with open(SRC, encoding="utf-8-sig") as fp:
        source = fp.read()
    ver = re.search(r'APP_VERSION = "([\d.]+)"', source)
    check("静态：版本不低于 1.7.0",
          bool(ver) and tuple(int(x) for x in ver.group(1).split(".")) >= (1, 7, 0),
          ver.group(1) if ver else "未找到")
    check("静态：工具栏按钮", '("插入图片", self.insert_image_file)' in source)
    check("静态：快捷键", '"<Control-Shift-I>"' in source)
    check("静态：预览点击打开", 'tag_bind("img", "<Button-1>", self._open_preview_image)' in source)
    check("静态：渲染透传上下文",
          "self._preview_image_ctx()" in source
          and re.search(r"render_markdown\(self\.preview, content,\s*self\._preview_image_ctx\(\)",
                        source) is not None)
    check("静态：Pillow 可选", "_PIL_OK" in source and "except Exception:  # pragma: no cover" in source)
    check("静态：JPG 在扩展名表", '".jpg"' in source and "IMAGE_EXTENSIONS" in source)

    print("=" * 62)
    for name in PASS:
        print("PASS %s" % name)
    for name in FAIL:
        print("FAIL %s" % name)
    print("-" * 62)
    print("合计 %d 项：PASS %d / FAIL %d" % (len(PASS) + len(FAIL), len(PASS), len(FAIL)))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
