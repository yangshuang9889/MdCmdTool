# -*- coding: utf-8 -*-
"""v1.5.0 未保存提示与保存链路验证（源码级，Tk 真实窗口）。"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import tkinter as tk

SRC = r"E:\yscl\MdCmdTool\爽哥MD命令生成工具.py"
PASS = []
FAIL = []


def ok(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, extra))


def load_module():
    spec = importlib.util.spec_from_file_location("sgmd_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    work = tempfile.mkdtemp(prefix="sgmd_v150_")
    p1 = os.path.join(work, "a.md")
    p2 = os.path.join(work, "b.md")
    io.open(p1, "w", encoding="utf-8").write("# A\n\n原始内容\n")
    io.open(p2, "w", encoding="utf-8").write("# B\n\n第二个文件\n")

    m = load_module()
    root = tk.Tk()
    root.withdraw()
    app = m.MdToolApp(root)
    root.update()

    title0 = root.title()
    ok("启动标题无未保存标记", "*" not in title0, title0)

    ok("打开干净文件返回 True", app.load_path(p1) is True)
    root.update()
    ok("打开后标题为文件名", "a.md" in root.title() and "*" not in root.title(), root.title())
    ok("current_file 指向 a.md", app.current_file and app.current_file.endswith("a.md"))

    # 模拟编辑
    app.editor.insert("end", "追加一行\n")
    root.update()
    ok("编辑后进入未保存状态", app._dirty is True)
    ok("标题追加未保存标记", root.title().endswith("*"), root.title())

    # 三态确认：取消
    asked = {}
    m.messagebox.askyesnocancel = lambda *a, **k: asked.setdefault("res", None)
    app.load_path(p2)
    root.update()
    ok("取消时仍停留在 a.md", app.current_file and app.current_file.endswith("a.md"))
    ok("取消时标题仍带 * 标记", root.title().endswith("*"))

    # 否：放弃修改并切换
    m.messagebox.askyesnocancel = lambda *a, **k: False
    app.load_path(p2)
    root.update()
    ok("选否后切换到 b.md", app.current_file and app.current_file.endswith("b.md"))
    ok("选否后未保存标记消失", "*" not in root.title(), root.title())
    ok("选否后 a.md 未被写入", "追加一行" not in io.open(p1, encoding="utf-8").read())

    # 是：保存后切换
    app.editor.insert("end", "B 修改\n")
    root.update()
    m.messagebox.askyesnocancel = lambda *a, **k: True
    app.load_path(p1)
    root.update()
    ok("选是后 b.md 已写盘", "B 修改" in io.open(p2, encoding="utf-8").read())
    ok("选是后切换到 a.md", app.current_file.endswith("a.md"))
    ok("选是后标记清除", "*" not in root.title())

    # 同一文件重复打开：不弹框、不重载
    app.editor.delete("1.0", "end")
    app.editor.insert("1.0", "内存里的内容")
    root.update()
    called = []
    m.messagebox.askyesnocancel = lambda *a, **k: called.append(1)
    app.load_path(p1)
    root.update()
    ok("同文件重复打开不弹框", not called)
    ok("同文件重复打开保留内存内容", "内存里的内容" in app.editor.get("1.0", "end-1c"))

    # 新建：取消保留
    m.messagebox.askyesnocancel = lambda *a, **k: None
    app.new_document()
    root.update()
    ok("新建-取消保留原内容", "内存里的内容" in app.editor.get("1.0", "end-1c"))

    # 新建：放弃
    m.messagebox.askyesnocancel = lambda *a, **k: False
    app.new_document()
    root.update()
    ok("新建-放弃清空编辑器", app.editor.get("1.0", "end-1c") == "")
    ok("新建后标题无文件名与标记", "a.md" not in root.title() and "*" not in root.title(), root.title())

    # 菜单与快捷键
    labels = {}
    for menu in app._menus:
        end = menu.index("end")
        if end is None:
            continue
        for i in range(end + 1):
            try:
                labels[menu.entrycget(i, "label")] = i
            except Exception:
                pass
    ok("文件菜单含保存项", "保存" in labels, str(list(labels)[:12]))
    ok("文件菜单含另存为项", "另存为..." in labels)
    ok("Ctrl+S 绑定保存", app.root.bind("<Control-s>") != "")
    ok("退出菜单绑定 on_close", "退出" in labels)

    # 退出取消 / 放弃
    app.editor.insert("1.0", "改一下")
    root.update()
    m.messagebox.askyesnocancel = lambda *a, **k: None
    app.on_close()
    root.update()
    ok("退出-取消时窗口仍在", bool(root.winfo_exists()))
    m.messagebox.askyesnocancel = lambda *a, **k: False
    app.on_close()
    try:
        root.update()
        alive = bool(root.winfo_exists()) and root.state() != "withdrawn"
    except Exception:
        alive = False
    ok("退出-放弃后窗口关闭", not alive)

    print("测试文件目录（保留）:", work)
    print("\n通过 %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        print("失败项:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
