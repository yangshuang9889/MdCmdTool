# -*- coding: utf-8 -*-
"""verify_video_v111.py

v1.10.1 回归：预览区视频黑屏根因（B 站播放地址里的 isOutside=true）。

1. 常量：BILI_PLAYER_URL 不再带 isOutside，且带 autoplay=1 / high_quality / danmaku
2. bili_clean_url：单参数、区间中段、首位参数三种位置都能摘干净，其余参数不丢
3. ensure_autoplay：先清洗再补 autoplay=1
4. bili_embed_src：BV 号 / 站内页 / 播放器地址 / 带 p 分P 四类产出都不含 isOutside
5. build_video_markup：用户粘贴的旧 iframe（带 isOutside）插入后标记里已无该参数
6. classify_video → build_player_html：播放页 HTML 里不出现 isOutside
7. 源码守卫：代码里不得再出现 `&isOutside=true` 拼接
8. 版本号基线：APP_VERSION 元组 >= (1,10,1)
"""
import importlib.util
import os
import sys

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
    spec = importlib.util.spec_from_file_location("sgmd_v111", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD_IFRAME = (
    '<iframe\n'
    '  src="https://player.bilibili.com/player.html?bvid=BV18asF6mEfy&cid=42947642163'
    '&page=1&autoplay=0&isOutside=true"\n'
    '  title="bilibili"\n'
    '  allowfullscreen>\n'
    '</iframe>')


def main():
    m = load_module()
    src = open(SRC, encoding="utf-8-sig").read()

    # ---------- 1. 常量 ----------
    tpl = m.BILI_PLAYER_URL % "BV1Uesp6yEsM"
    check("1-1 播放地址模板不含 isOutside", "isoutside" not in tpl.lower(), tpl)
    check("1-2 模板带 autoplay=1", "autoplay=1" in tpl, tpl)
    check("1-3 模板带 high_quality / danmaku",
          "high_quality=1" in tpl and "danmaku=1" in tpl, tpl)

    # ---------- 2. bili_clean_url ----------
    cases = [
        ("2-1 尾参数", "https://player.bilibili.com/player.html?bvid=BV1xx&page=1&isOutside=true",
         "https://player.bilibili.com/player.html?bvid=BV1xx&page=1"),
        ("2-2 中段参数",
         "https://player.bilibili.com/player.html?bvid=BV1xx&isOutside=true&page=2",
         "https://player.bilibili.com/player.html?bvid=BV1xx&page=2"),
        ("2-3 首位参数",
         "https://player.bilibili.com/player.html?isOutside=true&bvid=BV1xx&page=1",
         "https://player.bilibili.com/player.html?bvid=BV1xx&page=1"),
        ("2-4 无该参数时原样返回",
         "https://player.bilibili.com/player.html?bvid=BV1xx&page=1",
         "https://player.bilibili.com/player.html?bvid=BV1xx&page=1"),
        ("2-5 只有该参数时不留残渣",
         "https://player.bilibili.com/player.html?isOutside=true",
         "https://player.bilibili.com/player.html"),
    ]
    for name, arg, want in cases:
        eq(name, m.bili_clean_url(arg), want)

    # ---------- 3. ensure_autoplay ----------
    out = m.ensure_autoplay(
        "https://player.bilibili.com/player.html?bvid=BV1xx&page=1&autoplay=0&isOutside=true")
    check("3-1 先清洗后补 autoplay", "isoutside" not in out.lower()
          and "autoplay=1" in out, out)
    out2 = m.ensure_autoplay("https://player.bilibili.com/player.html?bvid=BV1xx")
    check("3-2 缺 autoplay 时补上", out2.endswith("autoplay=1"), out2)

    # ---------- 4. bili_embed_src ----------
    srcs = {
        "4-1 BV 号": m.bili_embed_src("BV18asF6mEfy"),
        "4-2 站内页": m.bili_embed_src("https://www.bilibili.com/video/BV18asF6mEfy?p=2"),
        "4-3 播放器地址": m.bili_embed_src(
            "https://player.bilibili.com/player.html?bvid=BV18asF6mEfy&cid=42947642163"
            "&page=1&autoplay=0&isOutside=true"),
        "4-4 分P": m.bili_embed_src("https://www.bilibili.com/video/BV18asF6mEfy?p=3"),
    }
    for name, value in srcs.items():
        check(name + " 不含 isOutside", "isoutside" not in value.lower(), value)
        check(name + " 带 autoplay=1", "autoplay=1" in value, value)
    check("4-5 播放器地址保留 cid", "cid=42947642163" in srcs["4-3 播放器地址"], srcs["4-3 播放器地址"])
    check("4-6 分P 保留 p=3", "p=3" in srcs["4-4 分P"] or "page=3" in srcs["4-4 分P"],
          srcs["4-4 分P"])

    # ---------- 5. build_video_markup ----------
    markup = m.build_video_markup(OLD_IFRAME, os.path.dirname(SRC))
    check("5-1 旧 iframe 仍可插入", markup.startswith("<iframe") and "bilibili" in markup,
          markup[:80])
    check("5-2 插入后已无 isOutside", "isoutside" not in markup.lower(), markup)
    check("5-3 插入后仍保留 cid", "cid=42947642163" in markup)

    # ---------- 6. 播放页 ----------
    target = m.classify_video(m.video_source_of(markup), os.path.dirname(SRC))
    html = m.build_player_html(target)
    check("6-1 播放页生成成功", bool(html))
    check("6-2 播放页不含 isOutside", "isoutside" not in html.lower())
    check("6-3 播放页 iframe 带 autoplay=1", "autoplay=1" in html)

    # ---------- 7. 源码守卫 ----------
    check("7-1 代码里不再拼接 &isOutside=true", "&isOutside=true" not in src)

    # ---------- 8. 版本 ----------
    ver = tuple(int(x) for x in m.APP_VERSION.split("."))
    check("8-1 版本号 >= 1.10.1", ver >= (1, 10, 1), str(ver))

    print("-" * 52)
    print("PASS %d / %d，FAIL %d" % (PASS, PASS + FAIL, FAIL))
    if FAILED:
        print("失败项：")
        for name in FAILED:
            print("  -", name)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
