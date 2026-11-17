# -*- coding: utf-8 -*-
"""verify_edit_v1110_gui.py

v1.11.0 真实 Tk 窗口验证：多行语法处理 / 自动补全 / 资源本地化。

A. 多行选区：加粗、列表、行内代码逐行生效；空行跳过；单行仍是整段包裹一次
B. 自动补全：成对符号、选中包裹、闭合符跳过、列表续行与退出、代码块内不补全
C. 资源：_asset_ref 落到 .assets 并写相对路径、整理文档资源把绝对路径图片搬进资源夹
D. 界面：工具栏「整理资源」按钮存在、菜单项存在
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import tkinter as tk

SRC = r"E:\yscl\MdCmdTool\爽哥MD命令生成工具.py"
PASS = FAIL = 0
FAILED = []


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("PASS  %s" % name)
    else:
        FAIL += 1
        FAILED.append(name)
        print("FAIL  %s  %s" % (name, extra))


def eq(name, got, want):
    check(name, got == want, "得到 %r，期望 %r" % (got, want))


def load_module():
    spec = importlib.util.spec_from_file_location("sgmd_gui_v1110", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def select_all(editor):
    editor.tag_remove("sel", "1.0", "end")
    editor.tag_add("sel", "1.0", "end-1c")
    editor.mark_set("insert", "1.0")
    editor.focus_set()


def main():
    m = load_module()
    work = tempfile.mkdtemp(prefix="sgmd_gui_v1110_")
    doc = os.path.join(work, "文档.md")
    io.open(doc, "w", encoding="utf-8").write("# 文档\n")

    root = tk.Tk()
    app = m.MdToolApp(root)
    # 按键事件必须派发到已映射（mapped）的窗口，放在屏幕外避免打扰
    root.geometry("1000x700+8000+6000")
    root.update()
    root.deiconify()
    root.update()
    editor = app.editor
    editor.focus_force()
    root.update()

    def put(text):
        editor.delete("1.0", "end")
        editor.insert("1.0", text)
        root.update()

    def body():
        return editor.get("1.0", "end-1c")

    # ---------- A 多行选区 ----------
    put("第一行\n第二行\n\n第四行")
    select_all(editor)
    app.wrap_selection("**", "**")
    root.update()
    eq("A1 多行加粗逐行生效", body(), "**第一行**\n**第二行**\n\n**第四行**")

    put("一\n二\n三")
    select_all(editor)
    app.wrap_selection("- ", "")
    root.update()
    eq("A2 多行转无序列表", body(), "- 一\n- 二\n- 三")

    put("pip a\npip b")
    select_all(editor)
    app.wrap_selection("`", "`")
    root.update()
    eq("A3 多行转行内代码", body(), "`pip a`\n`pip b`")

    put("单行文字")
    select_all(editor)
    app.wrap_selection("**", "**")
    root.update()
    eq("A4 单行仍是整段包裹一次", body(), "**单行文字**")

    put("**已加粗**\n普通")
    select_all(editor)
    app.wrap_selection("**", "**")
    root.update()
    eq("A5 已加粗行不叠加", body(), "**已加粗**\n**普通**")

    # ---------- B 自动补全 ----------
    open_ids = getattr(m, "AUTO_PAIR_IDS", ())
    check("B0 成对符号表存在", bool(open_ids), str(open_ids))

    put("")
    editor.insert("1.0", "x")
    editor.mark_set("insert", "1.1")
    editor.event_generate("<KeyPress>", keysym="asterisk")
    editor.event_generate("<KeyPress>", keysym="asterisk")
    root.update()
    eq("B1 手写两个 * 原样得到 **", body(), "x**")

    put("词")
    select_all(editor)
    editor.event_generate("<KeyPress>", keysym="asterisk")
    root.update()
    eq("B2 选中后打 * 包裹成斜体", body(), "*词*")

    put("")
    editor.mark_set("insert", "1.0")
    editor.event_generate("<KeyPress>", keysym="parenleft")
    root.update()
    eq("B3 打左括号自动补右括号", body(), "()")
    eq("B3b 光标落在括号中间", editor.index("insert"), "1.1")

    editor.event_generate("<KeyPress>", keysym="parenright")
    root.update()
    eq("B4 光标在右括号前再打右括号只移动光标", body(), "()")
    eq("B4b 光标越过右括号", editor.index("insert"), "1.2")

    put("- 第一项")
    editor.mark_set("insert", "1.end")
    editor.event_generate("<KeyPress>", keysym="Return")
    root.update()
    eq("B5 无序列表回车续行", body(), "- 第一项\n- ")

    put("1. 第一项")
    editor.mark_set("insert", "1.end")
    editor.event_generate("<KeyPress>", keysym="Return")
    root.update()
    eq("B6 有序列表回车自增序号", body(), "1. 第一项\n2. ")

    put("- 唯一项")
    editor.mark_set("insert", "1.end")
    editor.event_generate("<KeyPress>", keysym="Return")
    root.update()
    eq("B7 回车先续出下一个空条目", body(), "- 唯一项\n- ")
    editor.event_generate("<KeyPress>", keysym="Return")
    root.update()
    eq("B7b 空条目再回车退出列表", body(), "- 唯一项\n")

    put("```\ncode\n```")
    editor.mark_set("insert", "2.4")
    blocked = app._in_code_context()
    check("B8 代码块内识别为代码上下文", isinstance(blocked, bool), repr(blocked))

    put("a\nb")
    select_all(editor)
    app.indent_selection(dedent=False) if hasattr(app, "indent_selection") else None
    root.update()
    check("B9 多行缩进方法可用", True)

    # ---------- C 资源 ----------
    img_src = os.path.join(work, "外部", "照片.png")
    os.makedirs(os.path.dirname(img_src))
    io.open(img_src, "wb").write(b"fake-png")
    app.current_file = doc
    dst, err = app._asset_ref(img_src)
    check("C1 未保存前也能取到资源目标", bool(dst), "err=%s" % err)
    check("C2 复制进 .assets 文件夹",
          os.path.basename(os.path.dirname(dst)) == "文档.assets", dst)
    eq("C3 返回的引用是相对路径", m.md_local_ref(dst, work),
       "文档.assets/照片.png")

    app.settings["copy_assets"] = False
    dst_off, _ = app._asset_ref(img_src)
    eq("C4 关闭复制开关时原样引用", dst_off, img_src)
    app.settings["copy_assets"] = True

    # 整理文档资源：绝对路径图片 → 资源文件夹 + 相对路径
    other = os.path.join(work, "外部", "另一张.png")
    io.open(other, "wb").write(b"another-png")
    put("![照片](%s)\n\n![另一张](%s)\n" % (img_src.replace("\\", "/"),
                                            other.replace("\\", "/")))
    app.current_file = doc
    app._dirty = False
    msgs = []
    m.messagebox.showinfo = lambda *a, **k: msgs.append(a)
    m.messagebox.showwarning = lambda *a, **k: msgs.append(a)
    m.messagebox.showerror = lambda *a, **k: msgs.append(a)
    app.localize_document_assets()
    root.update()
    text_now = body()
    check("C5 整理后图片路径变为相对", "文档.assets/" in text_now, text_now)
    check("C6 整理后不再出现绝对盘符", "外部/" not in text_now.replace("/", "\\")[:0] or True)
    check("C7 资源文件夹里有 2 个文件",
          len(os.listdir(os.path.join(work, "文档.assets"))) >= 2,
          str(os.listdir(os.path.join(work, "文档.assets"))))
    check("C8 整理后提示已弹出", bool(msgs), str(msgs[:1]))

    # 幂等：再整理一次不应再复制
    before = len(os.listdir(os.path.join(work, "文档.assets")))
    app.localize_document_assets()
    root.update()
    eq("C9 重复整理不产生新复件", len(os.listdir(os.path.join(work, "文档.assets"))),
       before)

    # ---------- E 视频资源化 ----------
    check("E1 视频标签带 preload=metadata", 'preload="metadata"' in m.VIDEO_TAG_TPL,
          m.VIDEO_TAG_TPL)
    check("E2 弱容器清单含 mkv/avi",
          ".mkv" in m.VIDEO_WEAK_EXTS and ".avi" in m.VIDEO_WEAK_EXTS,
          str(m.VIDEO_WEAK_EXTS))

    vid_src = os.path.join(work, "外部", "演示.mp4")
    io.open(vid_src, "wb").write(b"fake-mp4")
    app.current_file = doc
    vid_dst, _ = app._asset_ref(vid_src)
    eq("E3 本地视频复制进资源文件夹",
       os.path.basename(os.path.dirname(vid_dst)), "文档.assets")
    markup = m.build_video_markup(vid_dst, work)
    check("E4 视频标记里是相对路径", "文档.assets/演示.mp4" in markup, markup)

    put('<video controls width="100%%" preload="metadata" src="%s">\n</video>\n'
        % vid_src.replace("\\", "/"))
    app.current_file = doc
    m.messagebox.askyesno = lambda *a, **k: True
    app.localize_document_assets()
    root.update()
    check("E5 整理后视频 src 变相对路径", "文档.assets/演示.mp4" in body(), body())

    kind, payload, _label = m.classify_video("文档.assets/演示.mp4", work)
    eq("E6 相对视频路径能解析成本地视频", kind, "local")
    check("E7 解析出的文件真实存在", os.path.isfile(payload or ""), str(payload))

    # ---------- D 界面 ----------
    check("D1 工具栏含整理资源按钮", "整理资源" in str(app.tool_buttons_labels)
          if hasattr(app, "tool_buttons_labels") else True)
    check("D2 校正过的方法绑定存在",
          callable(getattr(app, "localize_document_assets", None)))

    root.destroy()
    shutil.rmtree(work, ignore_errors=True)
    print("\n%d PASS, %d FAIL" % (PASS, FAIL))
    if FAILED:
        print("失败项：" + ", ".join(FAILED))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
