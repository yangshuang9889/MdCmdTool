# -*- coding: utf-8 -*-
"""v1.8.0 视频嵌入功能验证脚本（30+ 用例，逐条 PASS/FAIL）。

运行：python scripts\\verify_video_v180.py
覆盖：常量契约、视频地址识别、标记生成、播放页 HTML、预览渲染、
      类方法与工具栏/快捷键挂点、进程清理钩子。
"""
import importlib.util
import io
import os
import re
import sys
import tempfile
import tkinter as tk

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "爽哥MD命令生成工具.py")
SAMPLE_IFRAME = """<iframe
  src="https://player.bilibili.com/player.html?bvid=BV18asF6mEfy&cid=42947642163&page=1&autoplay=0&isOutside=true"
  title="哔哩哔哩视频播放器"
  allow="fullscreen; autoplay; encrypted-media; picture-in-picture"
  allowfullscreen
  loading="lazy"
  style="width:100%; aspect-ratio:16/9; border:0;">
</iframe>"""

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))


def eq(name, got, want):
    check(name, got == want, "got=%r want=%r" % (got, want))


def load_module():
    sys.path.insert(0, os.path.dirname(SRC))
    spec = importlib.util.spec_from_file_location("sgmd_video", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    src_text = io.open(SRC, encoding="utf-8-sig").read()
    m = load_module()
    tmpdir = tempfile.mkdtemp(prefix="sgmd_video_")
    local_mp4 = os.path.join(tmpdir, "demo.mp4")
    with open(local_mp4, "wb") as fp:
        fp.write(b"\x00" * 64)

    # ---------- A. 常量契约 ----------
    # v1.9.0 起版本号随迭代前移，此处只校验「不低于 1.8.0」，避免版本推进后误报
    check("A1 APP_VERSION 不低于 1.8.0",
          tuple(int(x) for x in m.APP_VERSION.split(".")[:3]) >= (1, 8, 0),
          m.APP_VERSION)
    check("A2 VIDEO_EXTENSIONS 覆盖 mp4/webm/mkv",
          {".mp4", ".webm", ".mkv"} <= set(m.VIDEO_EXTENSIONS), m.VIDEO_EXTENSIONS)
    check("A3 VIDEO_PANEL_H 为合理正整数",
          isinstance(m.VIDEO_PANEL_H, int) and 120 <= m.VIDEO_PANEL_H <= 600,
          m.VIDEO_PANEL_H)
    check("A4 BILI_PLAYER_URL 含 bvid 占位",
          "%s" in m.BILI_PLAYER_URL and "player.bilibili.com" in m.BILI_PLAYER_URL,
          m.BILI_PLAYER_URL)
    tag_names = [name for name, _opts in m.PREVIEW_TAG_ORDER]
    check("A5 预览标签含 video", "video" in tag_names)
    check("A6 预览标签含 imgfail（坏视频复用提示样式）", "imgfail" in tag_names)
    eq("A7 video 标签颜色随主题映射", m._TAG_COLOR_MAP.get("video"), "link_fg")

    # ---------- B. 视频地址识别 ----------
    eq("B1 样板 iframe 识别为 B 站",
       m.classify_video(m.video_source_of(SAMPLE_IFRAME))[0], "bili")
    check("B2 样板 iframe 保留 cid 参数",
          "cid=42947642163" in m.classify_video(m.video_source_of(SAMPLE_IFRAME))[1])
    check("B3 样板 iframe 标签含 BV 号",
          "BV18asF6mEfy" in m.classify_video(m.video_source_of(SAMPLE_IFRAME))[2])
    p2 = m.classify_video("https://www.bilibili.com/video/BV18asF6mEfy?p=2")
    eq("B4 B 站播放页识别为 bili", p2[0], "bili")
    check("B5 播放页分P 转成 player.html?page=2", "page=2" in p2[1], p2[1])
    bv = m.classify_video("BV18asF6mEfy")
    eq("B6 裸 BV 号识别为 bili", bv[0], "bili")
    check("B7 裸 BV 号补齐 bvid 参数", "bvid=BV18asF6mEfy" in bv[1], bv[1])
    eq("B8 普通网页地址识别为 web",
       m.classify_video("https://example.com/player?x=1")[0], "web")
    eq("B9 存在的本地视频识别为 local",
       m.classify_video(local_mp4, tmpdir)[0], "local")
    eq("B10 不存在的本地视频识别为 bad",
       m.classify_video(os.path.join(tmpdir, "nope.mp4"), tmpdir)[0], "bad")
    eq("B11 空字符串识别为 bad", m.classify_video("")[0], "bad")
    eq("B12 无 BV 号的 bilibili 首页识别为 web",
       m.classify_video("https://www.bilibili.com/")[0], "web")

    # ---------- C. 标记生成 ----------
    keep = m.build_video_markup(SAMPLE_IFRAME)
    # v1.10.0：B站 iframe 的 src 会被补 autoplay=1（历史 bug：autoplay=0 时播放页灰屏），
    # 因此只校验结构与其余属性原样保留，不再要求整段逐字相同。
    check("C1 完整 iframe 原样保留", keep.strip().startswith("<iframe") and
          keep.strip().endswith("</iframe>"), keep[:60])
    check("C2 原样保留时未丢 loading=lazy", 'loading="lazy"' in keep)
    check("C3 原样保留时未丢 allowfullscreen", "allowfullscreen" in keep)
    gen = m.build_video_markup("BV18asF6mEfy")
    check("C4 BV 号生成 iframe 标记", gen.startswith("<iframe") and gen.endswith("</iframe>"),
          gen[:40])
    check("C5 生成的 iframe 带 16:9 样式", "aspect-ratio:16/9" in gen, gen)
    local_tag = m.build_video_markup(local_mp4, tmpdir)
    check("C6 本地视频生成 video 标签（写相对路径）",
          local_tag.startswith("<video") and "demo.mp4" in local_tag
          and local_mp4 not in local_tag, local_tag[:80])
    eq("C7 无效输入不生成标记", m.build_video_markup("hello world"), "")

    # ---------- D. 片段解析 ----------
    eq("D1 video_source_of 提取属性式 src",
       m.video_source_of(SAMPLE_IFRAME),
       "https://player.bilibili.com/player.html?bvid=BV18asF6mEfy&cid=42947642163"
       "&page=1&autoplay=0&isOutside=true")
    eq("D2 video_source_of 直接返回裸地址",
       m.video_source_of("https://player.bilibili.com/player.html?bvid=BV1xx"),
       "https://player.bilibili.com/player.html?bvid=BV1xx")
    check("D3 html_block_complete 认出闭合 iframe",
          m.html_block_complete(SAMPLE_IFRAME))
    check("D4 html_block_complete 认出未闭合 iframe",
          not m.html_block_complete(SAMPLE_IFRAME.rsplit("</iframe>", 1)[0]))
    check("D5 looks_like_video_line 认出视频网址",
          m.looks_like_video_line("https://www.bilibili.com/video/BV18asF6mEfy"))
    check("D6 looks_like_video_line 不误判普通文字",
          not m.looks_like_video_line("这是一段普通说明文字"))
    check("D7 looks_like_video_line 认出本地视频路径",
          m.looks_like_video_line(local_mp4, tmpdir))
    check("D8 looks_like_video_line 不误判普通图片链接",
          not m.looks_like_video_line("https://example.com/a.png"))

    # ---------- E. 播放页 HTML ----------
    html = m.build_player_html(m.classify_video(m.video_source_of(SAMPLE_IFRAME)))
    check("E1 播放页含 iframe", "<iframe" in html)
    check("E2 播放页含 bvid", "bvid=BV18asF6mEfy" in html)
    check("E3 播放页去掉滚动条", "overflow:hidden" in html)
    check("E4 播放页 iframe 铺满 100%", "height:100%" in html)
    check("E5 播放页转义 & 为 &amp;", "&amp;cid=" in html)

    # ---------- F. 预览渲染 ----------
    root = tk.Tk()
    root.withdraw()
    widget = tk.Text(root)
    for name, opts in m.preview_tag_options(m.THEMES[m.THEME_LIGHT]):
        widget.tag_configure(name, **opts)
    ctx = {"base_dir": tmpdir, "paths": {}}
    md = ("# 标题\n\n<iframe\n  src=\"https://player.bilibili.com/player.html?"
          "bvid=BV18asF6mEfy&cid=42947642163&page=1\"\n  title=\"哔哩哔哩视频播放器\"\n"
          "  allowfullscreen\n  loading=\"lazy\">\n</iframe>\n\n"
          "https://www.bilibili.com/video/BV18asF6mEfy\n\n"
          "BV18asF6mEfy\n\n")
    m.render_markdown(widget, md, None, ctx)
    text = widget.get("1.0", "end-1c")
    rngs = widget.tag_ranges("video")
    eq("F1 iframe + 裸链接 + BV 号渲染出 3 个视频条目", len(rngs) // 2, 3)
    check("F2 预览出现 ▶ 标记", text.count("▶") >= 3, text.count("▶"))
    check("F3 预览显示标题行「B站视频」", "B站视频" in text)
    eq("F4 视频位置映射数量与 tag 数一致", len(ctx["paths"]), 3)
    cid_hit = [v for v in ctx["paths"].values() if "cid=42947642163" in v[1]]
    check("F5 映射保留完整播放地址（含 cid）", len(cid_hit) == 1, cid_hit)
    widget2 = tk.Text(root)
    for name, opts in m.preview_tag_options(m.THEMES[m.THEME_LIGHT]):
        widget2.tag_configure(name, **opts)
    ctx2 = {"base_dir": tmpdir, "paths": {}}
    m.render_markdown(widget2, "本地视频一行：\n\n" + local_mp4 + "\n\n"
                      + os.path.join(tmpdir, "gone.mp4") + "\n", None, ctx2)
    text2 = widget2.get("1.0", "end-1c")
    check("F6 本地视频渲染出播放条目", "本地视频" in text2, text2[:120])
    check("F7 缺失视频给出红棕提示而不是中断渲染",
          "文件不存在" in text2 and widget2.tag_ranges("imgfail"))
    root.destroy()

    # ---------- G. Edge 与类方法 ----------
    edge = m.find_edge_exe()
    check("G1 find_edge_exe 返回可用路径或 None",
          edge is None or os.path.exists(edge), edge)
    for attr in ("insert_video", "_play_video", "_stop_video",
                 "_embed_video_window", "_watch_video_window",
                 "_activate_video_panel", "_preview_video_ctx",
                 "_open_video_in_browser", "_resize_video_host"):
        check("G2 类方法存在 %s" % attr, hasattr(m.MdToolApp, attr))
    check("G3 工具栏含「插入视频」按钮", '("插入视频", self.insert_video)' in src_text)
    check("G4 快捷键 Ctrl+Shift+V 已绑定",
          "<Control-Shift-V>" in src_text and "self.insert_video()" in src_text)
    check("G5 on_close 里会结束播放进程", "self._stop_video(silent=True)" in src_text)
    check("G6 预览刷新传入视频上下文", "self._preview_video_ctx()" in src_text)
    check("G7 render_markdown 支持 video_ctx 形参",
          re.search(r"def render_markdown\([^)]*video_ctx", src_text) is not None)
    check("G8 单实例/配置未因视频功能被动过",
          "SgMdEditor_SingleInstance_v1" in src_text and '"auto_check_update"' in src_text)

    passed = sum(1 for ok, _n, _d in results if ok)
    total = len(results)
    for ok, name, detail in results:
        if not ok:
            print("FAIL %-46s %s" % (name, detail))
    print("%d/%d PASS" % (passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
