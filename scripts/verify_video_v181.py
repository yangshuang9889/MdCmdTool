# -*- coding: utf-8 -*-
"""v1.8.1「插入视频」回归校验。

背景：v1.8.0 的 build_video_markup 只要文本里沾到 "<iframe"/"http" 就整段原样返回，
用户剪贴板里若是聊天/文档文字（含手册里的 iframe 示例）会被当成视频插进文档，
表现为"插入视频功能不好使"。v1.8.1 改为只接受"整段就是一个视频标记/地址"。

运行：python scripts\verify_video_v181.py
"""
import io
import os
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "爽哥MD命令生成工具.py")

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append("%s %s" % (name, extra))
        print("FAIL %s %s" % (name, extra))


def load():
    spec = importlib.util.spec_from_file_location("mdtool_v181", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CLEAN = (
    '<iframe\n'
    '  src="https://player.bilibili.com/player.html?bvid=BV18asF6mEfy&cid=42947642163&page=1&autoplay=0&isOutside=true"\n'
    '  title="bilibili"\n'
    '  allowfullscreen>\n'
    '</iframe>'
)

POLLUTED = (
    "按流程先读手册，查清 H 按钮现在是怎么实现的。\n"
    "手册里的示例：\n"
    + CLEAN +
    "\n上面这段就是要插的视频，记得改 src。"
)

VIDEO_TAG = '<video src="demo.mp4" controls></video>'


def main():
    m = load()
    base = os.path.join(ROOT, "video_cache")

    # --- 1. 纯净度判定 ---
    check("纯净iframe", m.video_markup_pure(CLEAN) is True)
    check("纯净video", m.video_markup_pure(VIDEO_TAG) is True)
    check("污染文本不纯", m.video_markup_pure(POLLUTED) is False)
    check("裸地址不纯", m.video_markup_pure("https://x.com/a.mp4") is False)
    check("未闭合不纯", m.video_markup_pure('<iframe src="a">') is False)
    check("超长不纯", m.video_markup_pure("<iframe src='a'></iframe>" + "x" * 5000) is False)

    # --- 2. 网址判定 ---
    check("url_like 正常", m.url_like("https://www.bilibili.com/video/BV18asF6mEfy?p=1") is True)
    check("url_like 带空格", m.url_like("https://a.com/b.mp4 这是我的视频") is False)
    check("url_like 非网址", m.url_like("随便一句话") is False)

    # --- 3. 核心修复：污染输入必须拒绝 ---
    check("污染文本被拒", m.build_video_markup(POLLUTED, base) == "")
    check("污染文本被拒(无目录)", m.build_video_markup(POLLUTED) == "")
    check("缺 src 的 iframe 被拒",
          m.build_video_markup('<iframe allowfullscreen></iframe>', base) == "")
    check("夹带文字的 video 被拒",
          m.build_video_markup('看这个<video src="a.mp4"></video>', base) == "")

    # --- 4. 正常输入仍然可用 ---
    out = m.build_video_markup(CLEAN, base)
    # v1.10.0：B站地址会被补上 autoplay=1（否则播放页要手动点才播），其余属性原样保留
    check("纯净iframe保留(结构)", out.strip().startswith("<iframe") and
          out.strip().endswith("</iframe>"))
    check("纯净iframe补autoplay", "autoplay=1" in out)
    check("纯净iframe保留属性", 'title="bilibili"' in out and "allowfullscreen" in out)
    check("纯净iframe带cid", "cid=42947642163" in out)
    check("video标记保留", m.build_video_markup(VIDEO_TAG, base).strip() == VIDEO_TAG)
    check("BV号可插", "player.bilibili.com" in m.build_video_markup("BV18asF6mEfy", base))
    check("播放页可插", "player.bilibili.com" in
          m.build_video_markup("https://www.bilibili.com/video/BV18asF6mEfy?p=1", base))
    check("普通网页可插", "example.com/v.mp4" in
          m.build_video_markup("https://example.com/v.mp4", base))
    check("不存在的本地文件被拒", m.build_video_markup(r"E:\nope.mp4", base) == "")

    # --- 5. 播放链路回归（不真的起 Edge，只验证解析） ---
    kind, payload, label = m.classify_video(m.video_source_of(out), base)
    check("解析为bili", kind == "bili", kind)
    check("payload 带 cid", "cid=" in payload)
    check("播放页可生成", bool(m.build_player_html((kind, payload, label))))

    print("-" * 52)
    print("PASS %d / %d，FAIL %d" % (PASS, PASS + FAIL, FAIL))
    if FAILED:
        print("失败项：")
        for f in FAILED:
            print("  -", f)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
