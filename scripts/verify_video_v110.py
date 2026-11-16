# -*- coding: utf-8 -*-
"""verify_video_v110.py

v1.10.0 视频播放链路回归：
1. 静态：面板挂主窗口底部（before=self.paned，修复被压成 61px 的历史 bug）
2. 静态：Edge 启动参数（独立 profile、反后台节流、autoplay 策略、窗口尺寸）
3. 静态：嵌入/定位/关闭全链路日志加固锚点（style 前后、GetParent、MoveWindow、
   PostMessageW WM_CLOSE、轮询次数、profile 清理）
4. 动态：真实拉起窗口后播放面板高度应 > 200（复现并守护「预览区视频不能播放」根因）
5. 播放页四类产出：bili -> iframe(无 lazy, autoplay=1)；web 直链 -> <video>；
   web 页面 -> iframe；local -> <video>(file:///)
6. 版本号基线：APP_VERSION 元组 >= (1,10,0)
"""
import importlib.util
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "爽哥MD命令生成工具.py")

results = []


def check(name, ok, detail=""):
    results.append((bool(ok), name, detail))


def load_module():
    spec = importlib.util.spec_from_file_location("sgmd_v110", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load_module()
    src = open(SRC, encoding="utf-8-sig").read()

    # ---------- 1. 面板挂载与尺寸（根因修复） ----------
    check("面板挂主窗口底部",
          "self.video_panel=ttk.LabelFrame(self.root" in
          src.replace(" ", "").replace("\n", ""))
    check("pack 顺序 before=self.paned",
          "before=self.paned" in src)
    check("pack 顺序根因注释",
          "61 像素" in src and "expand=True" in src)
    check("播放区高度常量",
          m.VIDEO_PANEL_MIN_W >= 400 and 380 <= m.VIDEO_PANEL_MAX_H <= 460)

    # ---------- 2. Edge 启动参数 ----------
    spawn = src[src.index("def _spawn_video_window"):src.index("def _watch_video_window")]
    for flag in ("--app=%s", "--user-data-dir=%s",
                 "--autoplay-policy=no-user-gesture-required",
                 "--disable-background-timer-throttling",
                 "--disable-renderer-backgrounding",
                 "--disable-backgrounding-occluded-windows",
                 "--no-first-run", "--no-default-browser-check"):
        check("启动参数含 %s" % flag, flag in spawn)
    check("独立 profile", "profile" in spawn and "edgeprofile" not in spawn)
    check("启动参数入日志", 'log_detail("启动视频播放器"' in spawn)
    check("PID 入日志", "proc.pid" in spawn)

    # ---------- 3. 嵌入/定位/关闭/超时日志 ----------
    watch = src[src.index("def _watch_video_window"):src.index("def _embed_video_window")]
    check("轮询次数计数", "self._video_polls" in watch)
    check("轮询日志", 'log_detail("等待播放窗口"' in watch)
    check("超时日志", 'log_warn("视频窗口等待超时"' in watch)
    check("进程退出日志", 'log_warn("播放器进程已退出"' in watch)

    embed = src[src.index("def _embed_video_window"):src.index("def _place_video_window")]
    check("样式位读取", "GetWindowLongW" in embed and "GWL_STYLE" in embed)
    check("样式结果回读", "new_style" in embed)
    check("父窗口回读", "GetParent" in embed)
    check("嵌入结果日志", 'log_action("视频窗口已嵌入"' in embed and "轮询" in embed)

    place = src[src.index("def _place_video_window"):src.index("def _stop_video")]
    check("MoveWindow 铺满", "MoveWindow" in place)
    check("定位失败日志", "定位失败" in place and "log_detail" in place)

    stop = src[src.index("def _stop_video"):src.index("def _open_video_in_browser")]
    check("关闭先发 WM_CLOSE", "PostMessageW" in stop and "WM_CLOSE" in stop)
    check("关闭日志含 hwnd/pid", 'log_action("视频播放已关闭"' in stop)

    # ---------- 4. profile 生命周期 ----------
    for fn in ("_new_video_profile", "_drop_video_profile", "_cleanup_video_profiles"):
        check("profile 方法 %s 存在" % fn, "def %s" % fn in src)
    check("保留策略常量", m.VIDEO_PROFILE_KEEP >= 1)
    check("启动时清理历史 profile",
          "_cleanup_video_profiles()" in src)
    check("关闭时清理本次 profile",
          "_drop_video_profile()" in stop)

    # ---------- 5. 日志轮转 ----------
    logseg = src[src.index("LOG_MAX_BYTES"):src.index("def log_error")]
    check("RotatingFileHandler", "RotatingFileHandler" in logseg)
    check("maxBytes 2MB", "LOG_MAX_BYTES = 2 * 1024 * 1024" in logseg)
    check("backupCount 3", "LOG_BACKUP_COUNT = 3" in logseg)
    check("DEBUG 级别", "setLevel(logging.DEBUG)" in logseg)
    check("不向 root 传播", "propagate = False" in logseg)
    for fn in ("log_action", "log_detail", "log_warn", "log_error"):
        check("日志函数 %s 存在" % fn, "def %s" % fn in src)

    # ---------- 6. 播放页四类产出 ----------
    def has(src_text, needle):
        return needle in src_text

    bili_html = m.build_player_html(("bili", "https://player.bilibili.com/player.html?bvid=BV1GJ411x7h7&page=1", "B站"))
    check("bili 页用 iframe", has(bili_html, "<iframe") or has(bili_html, "iframe"))
    check("bili 页无 lazy", "loading=\"lazy\"" not in bili_html)
    check("bili 页 autoplay=1", "autoplay=1" in bili_html)

    web_mp4 = m.build_player_html(("web", "https://example.com/a.mp4", "example.com"))
    check("web 直链用 <video>", "<video" in web_mp4)
    check("web 直链 autoplay", "autoplay" in web_mp4)
    web_page = m.build_player_html(("web", "https://example.com/page.html", "example.com"))
    check("web 页面用 iframe", "iframe" in web_page)
    local_html = m.build_player_html(("local", r"E:\yscl\MdCmdTool\temp\x.mp4", "x.mp4"))
    check("local 用 <video>", "<video" in local_html)
    check("local 用 file:///", "file:///" in local_html)
    check("local 静音起播", "muted" in local_html)
    check("local 起播脚本", "v.play()" in local_html and "loadedmetadata" in local_html)
    check("起播失败提示", "视频加载失败" in local_html)
    check("bili 页无起播脚本", "v.play()" not in bili_html)

    # ---------- 7. 版本 ----------
    ver = tuple(int(x) for x in str(m.APP_VERSION).split("."))
    check("版本号 >= 1.10.0", ver >= (1, 10, 0), str(ver))

    # ---------- 8. 动态：真实拉起窗口，播放面板高度应 > 200 ----------
    try:
        import tkinter as tk
        m.MdToolApp._update_auto_check = lambda self, delay=0: None
        root = tk.Tk()
        root.geometry("1200x820")
        app = m.MdToolApp(root)
        root.update()
        app._activate_video_panel()
        app._resize_video_host()
        root.update()
        root.update_idletasks()
        h = app.video_host.winfo_height()
        w = app.video_host.winfo_width()
        check("动态：播放面板高度 > 200", h > 200, "host=%dx%d" % (w, h))
        check("动态：面板挂在 root 下",
              app.video_panel.master is root, str(app.video_panel.master))
        try:
            app._stop_video(silent=True)
        except Exception:
            pass
        root.destroy()
    except Exception as exc:
        check("动态窗口构造", False, repr(exc))

    # ---------- 汇总 ----------
    passed = sum(1 for ok, _n, _d in results if ok)
    failed = len(results) - passed
    print("合计 %d 项：PASS %d / FAIL %d" % (len(results), passed, failed))
    for ok, name, detail in results:
        if not ok:
            print("FAIL %s | %s" % (name, detail))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
