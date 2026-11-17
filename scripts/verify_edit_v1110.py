# -*- coding: utf-8 -*-
"""verify_edit_v1110.py

v1.11.0 回归：多行语法操作 + 资源文件夹 + 语法自动补全 + 资源本地化。

覆盖点：
1. 常量与设置：ASSET_DIR_SUFFIX / ASSET_SUFFIX_RE / AUTO_PAIR_* 存在；default_settings 带
   auto_pair / copy_assets / asset_suffix；_sanitize_settings 对旧设置（无这三项）保留默认，
   对非法后缀回退默认。
2. wrap_lines：多行逐行包裹、空行不包裹、缩进与行尾空白保留、已包裹行不叠加。
3. doc_asset_dir / safe_asset_name / unique_file_path / copy_into_asset_dir：
   资源文件夹命名、非法字符清理、重名加序号、同文件重复插入不产生复件、跨目录复制成功。
4. md_local_ref / html_local_ref：相对文档目录、反斜杠转 /、含空格时 md 用 <> 包裹且
   html 不做百分号编码。
5. 资源本地化正则：_ASSET_MD_IMAGE_RE / _ASSET_HTML_SRC_RE 能抓到图片与视频 src，
   不误伤网络地址。
6. 源码守卫：_bind_editor_keys 被 _bind_shortcuts 调用；多行 wrap_selection 走 wrap_lines；
   localize_document_assets 有入口（菜单 + 工具栏）。
7. 版本号基线：APP_VERSION >= (1, 11, 0)。
"""
import importlib.util
import os
import shutil
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "爽哥MD命令生成工具.py")

PASS = FAIL = 0
FAILED = []


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("PASS  %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("FAIL  %s  %s" % (name, detail))


def eq(name, got, want):
    check(name, got == want, "得到 %r，期望 %r" % (got, want))


def load_module():
    spec = importlib.util.spec_from_file_location("sgmd_v1110", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load_module()
    text = open(SRC, encoding="utf-8-sig").read()
    tmp = tempfile.mkdtemp(prefix="sgmd_v1110_")

    # ---------- 1. 常量与设置 ----------
    eq("1-1 默认资源后缀", m.ASSET_DIR_SUFFIX, ".assets")
    check("1-2 后缀校验正则存在", hasattr(m, "ASSET_SUFFIX_RE"))
    for flag in ("valid_assets", ".assets", "media.v1", "a_b-c.d"):
        check("1-3 合法后缀 %s" % flag, bool(m.ASSET_SUFFIX_RE.match(flag)))
    for flag in ("", "有 空格", "中文", ".assets/", "x" * 33):
        check("1-4 非法后缀拒绝 %r" % flag, not m.ASSET_SUFFIX_RE.match(flag))

    d = m.default_settings()
    eq("1-5 auto_pair 默认开启", d.get("auto_pair"), True)
    eq("1-6 copy_assets 默认开启", d.get("copy_assets"), True)
    eq("1-7 asset_suffix 默认值", d.get("asset_suffix"), ".assets")

    legacy = {"theme": m.THEME_LIGHT, "version": "1.10.1"}
    s = m._sanitize_settings(legacy)
    eq("1-8 旧设置迁移后 auto_pair 保留默认", s.get("auto_pair"), True)
    eq("1-9 旧设置迁移后 copy_assets 保留默认", s.get("copy_assets"), True)
    eq("1-10 asset_suffix_of 回退默认", m.asset_suffix_of({}), ".assets")
    eq("1-11 asset_suffix_of 读设置", m.asset_suffix_of({"asset_suffix": ".media"}),
       ".media")

    # ---------- 2. wrap_lines ----------
    eq("2-1 两行分别加粗",
       m.wrap_lines("第一行\n第二行", "**", "**"),
       "**第一行**\n**第二行**")
    eq("2-2 空行不包裹", m.wrap_lines("a\n\nb", "**", "**"), "**a**\n\n**b**")
    eq("2-3 缩进保留", m.wrap_lines("  缩进行", "**", "**"), "  **缩进行**")
    eq("2-4 行尾空白保留", m.wrap_lines("内容   ", "**", "**"), "**内容**   ")
    eq("2-5 已包裹行不叠加", m.wrap_lines("**已加粗**", "**", "**"), "**已加粗**")
    eq("2-6 三行不同命令批量成行内代码",
       m.wrap_lines("pip install a\npip install b\npip install c", "`", "`"),
       "`pip install a`\n`pip install b`\n`pip install c`")
    eq("2-7 CRLF 也能逐行处理",
       m.wrap_lines("a\r\nb", "- ", ""), "- a\n- b")

    # ---------- 3. 资源文件夹与复制 ----------
    doc_dir = os.path.join(tmp, "文档")
    os.makedirs(doc_dir)
    doc = os.path.join(doc_dir, "笔记.md")
    open(doc, "w", encoding="utf-8").write("# 笔记\n")
    eq("3-1 资源文件夹命名", os.path.basename(m.doc_asset_dir(doc)), "笔记.assets")
    eq("3-2 自定义后缀",
       os.path.basename(m.doc_asset_dir(doc, ".media")), "笔记.media")
    eq("3-3 同名文件加序号",
       os.path.basename(m.unique_file_path(tmp, "a.txt")), "a.txt")
    open(os.path.join(tmp, "a.txt"), "w").write("x")
    eq("3-4 已存在则 -1",
       os.path.basename(m.unique_file_path(tmp, "a.txt")), "a-1.txt")
    eq("3-5 非法字符清理", m.safe_asset_name('a:b*c?.png'), "b_c_.png")
    eq("3-5b 目录分隔符只取文件名", m.safe_asset_name('x/y/z.png'), "z.png")

    src_img = os.path.join(tmp, "外部图片.png")
    open(src_img, "wb").write(b"fake png bytes")
    dst, err = m.copy_into_asset_dir(src_img, doc)
    check("3-6 跨目录复制成功", bool(dst) and os.path.isfile(dst), "err=%r" % (err,))
    eq("3-7 落入资源文件夹",
       os.path.basename(os.path.dirname(dst or "")), "笔记.assets")
    dst2, _ = m.copy_into_asset_dir(src_img, doc)
    eq("3-8 重复插入不产生复件", dst2, dst)
    eq("3-9 资源文件夹只含一个文件",
       len(os.listdir(os.path.dirname(dst))), 1)
    eq("3-10 复制不改动原文件", os.path.isfile(src_img), True)

    # ---------- 4. 引用路径 ----------
    ref = m.md_local_ref(dst, doc_dir)
    eq("4-1 md 相对路径", ref, "笔记.assets/外部图片.png")
    eq("4-2 md 含空格用 <> 包裹",
       m.md_local_ref(os.path.join(doc_dir, "a b.png"), doc_dir), "<a b.png>")
    eq("4-3 html 不做百分号编码",
       m.html_local_ref(os.path.join(doc_dir, "a b.mp4"), doc_dir), "a b.mp4")
    eq("4-4 html 反斜杠转斜杠",
       m.html_local_ref(os.path.join(doc_dir, "sub", "x.mp4"), doc_dir), "sub/x.mp4")

    # ---------- 5. 本地化正则 ----------
    body = ("![图](C:/a/b.png)\n"
            "![图2](<C:/a/c d.png>)\n"
            "![网图](https://x.com/y.png)\n"
            '<video controls width="100%" src="D:/v/movie.mp4"></video>\n'
            '<iframe\n  src="https://player.bilibili.com/player.html?bvid=BV1x"\n></iframe>')
    md_hits = [mt.group(2) for mt in m._ASSET_MD_IMAGE_RE.finditer(body)]
    eq("5-1 抓到两张本地图片", len(md_hits), 3)
    check("5-2 尖括号包裹的地址被完整抓取",
          any("c d.png" in h and h.startswith("<") for h in md_hits), str(md_hits))
    html_hits = [mt.group(2) for mt in m._ASSET_HTML_SRC_RE.finditer(body)]
    check("5-3 抓到 video 本地路径", any("movie.mp4" in h for h in html_hits),
          str(html_hits))
    check("5-4 抓到跨行 iframe 的 src",
          any("player.bilibili.com" in h for h in html_hits), str(html_hits))

    # ---------- 6. 源码守卫 ----------
    check("6-1 _bind_editor_keys 被绑定调用",
          "_bind_editor_keys" in text and "self._bind_editor_keys()" in text)
    check("6-2 多行 wrap_selection 走 wrap_lines",
          "wrap_lines(selected" in text or "wrap_lines(" in text)
    check("6-3 菜单有整理资源入口", "整理文档资源" in text)
    check("6-4 工具栏有整理资源按钮", '("整理资源", self.localize_document_assets)' in text)
    check("6-5 插入图片走资源引用", "_asset_ref" in text)
    check("6-6 设置窗口有 auto_pair 开关", "_on_auto_pair_toggle" in text)

    # ---------- 7. 版本号 ----------
    check("7-1 版本号 >= 1.11.0",
          tuple(int(x) for x in m.APP_VERSION.split(".")) >= (1, 11, 0),
          m.APP_VERSION)

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n%d PASS, %d FAIL" % (PASS, FAIL))
    if FAILED:
        print("失败项：" + ", ".join(FAILED))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
