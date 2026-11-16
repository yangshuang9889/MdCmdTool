# -*- coding: utf-8 -*-
"""v1.9.0「输入框中文右键菜单」回归校验。

覆盖点：
1. 可编辑控件（Text / Entry）菜单项为「撤销/重做/剪切/复制/粘贴/删除/全选」；
2. 只读控件（实时预览、更新说明）只保留「复制/全选」；
3. 置灰规则：无选区时剪切/复制/删除禁用；无可撤销时撤销禁用；剪贴板空时粘贴禁用；
4. 各动作真实生效：全选、复制、剪切、粘贴、删除、撤销、重做；
5. <Button-3> 已绑定，替换 tkinter 默认英文菜单；
6. 主题切换后菜单配色跟随调色板；
7. 源码集成：三个输入区 + 两个弹窗输入框均已挂载。

运行：python scripts\verify_context_v190.py
"""
import io
import os
import re
import sys
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "爽哥MD命令生成工具.py")

PASS = 0
FAIL = 0
FAILED = []

EDIT_LABELS = ["撤销", "重做", None, "剪切", "复制", "粘贴", "删除", None, "全选"]
READONLY_LABELS = ["复制", None, "全选"]


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILED.append("%s %s" % (name, extra))
        print("FAIL %s %s" % (name, extra))


def load():
    spec = importlib.util.spec_from_file_location("mdtool_v190", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def state_of(cm, label):
    """按 label 取菜单项 state（normal / disabled）。"""
    menu = cm.menu
    for i in range(menu.index("end") + 1):
        if menu.type(i) == "separator":
            continue
        if menu.entrycget(i, "label") == label:
            return str(menu.entrycget(i, "state"))
    return "missing"


def main():
    m = load()
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()

    # ---------------- 1. 可编辑 Text 菜单结构 ----------------
    txt = tk.Text(root, undo=True)
    cm = m.install_text_context_menu(txt, palette_getter=lambda: m.THEMES and
                                     m.palette_of(m.THEME_LIGHT))
    check("Text可编辑菜单项", cm.labels() == EDIT_LABELS, str(cm.labels()))
    check("Text右键已绑定Button-3", bool(txt.bind("<Button-3>")))

    # ---------------- 2. 空内容置灰规则 ----------------
    st = cm.refresh_state()
    check("空内容_撤销禁用", state_of(cm, "撤销") == "disabled")
    check("空内容_重做禁用", state_of(cm, "重做") == "disabled")
    check("空内容_剪切禁用", state_of(cm, "剪切") == "disabled")
    check("空内容_复制禁用", state_of(cm, "复制") == "disabled")
    check("空内容_删除禁用", state_of(cm, "删除") == "disabled")
    check("空内容_全选禁用", state_of(cm, "全选") == "disabled", str(st))

    # ---------------- 3. 有内容后全选 / 状态变化 ----------------
    txt.insert("1.0", "第一行\n第二行")
    st = cm.refresh_state()
    check("有内容_全选可用", state_of(cm, "全选") == "normal")
    check("有内容_撤销可用", state_of(cm, "撤销") == "normal")
    check("无选区_复制仍禁用", state_of(cm, "复制") == "disabled")

    check("全选动作成功", cm.fire("select") is True)
    check("全选后选区成立", cm.has_selection() is True)
    check("全选文本正确", cm.selection_text() == "第一行\n第二行",
          repr(cm.selection_text()))
    cm.refresh_state()
    check("有选区_剪切可用", state_of(cm, "剪切") == "normal")
    check("有选区_复制可用", state_of(cm, "复制") == "normal")
    check("有选区_删除可用", state_of(cm, "删除") == "normal")

    # ---------------- 4. 复制 / 剪切 / 粘贴 / 删除 ----------------
    check("复制动作成功", cm.fire("copy") is True)
    check("复制进剪贴板", txt.clipboard_get() == "第一行\n第二行")

    txt.tag_remove("sel", "1.0", "end")
    txt.tag_add("sel", "1.0", "1.4")
    cm.fire("cut")
    check("剪切移除原文", txt.get("1.0", "end-1c") == "\n第二行",
          repr(txt.get("1.0", "end-1c")))
    check("剪切写入剪贴板", txt.clipboard_get() == "第一行")

    txt.mark_set("insert", "1.0")
    check("粘贴动作成功", cm.fire("paste") is True)
    check("粘贴还原内容", txt.get("1.0", "end-1c") == "第一行\n第二行",
          repr(txt.get("1.0", "end-1c")))

    txt.tag_add("sel", "1.0", "1.4")
    check("删除动作成功", cm.fire("delete") is True)
    check("删除后内容", txt.get("1.0", "end-1c") == "\n第二行",
          repr(txt.get("1.0", "end-1c")))

    # ---------------- 5. 撤销 / 重做 ----------------
    txt.focus_force()
    before = txt.get("1.0", "end-1c")
    cm.fire("undo")
    root.update()
    after_undo = txt.get("1.0", "end-1c")
    check("撤销可用且有变化", m._edit_flag(txt, "canredo") and after_undo != before,
          "canredo=%s before=%r after=%r" % (m._edit_flag(txt, "canredo"),
                                             before, after_undo))
    check("撤销后_撤销项仍可用", state_of(cm, "撤销") == "normal")
    cm.refresh_state()
    check("撤销后重做置为可用", state_of(cm, "重做") == "normal")
    cm.fire("redo")
    root.update()
    check("重做回到撤销前", txt.get("1.0", "end-1c") == before,
          repr(txt.get("1.0", "end-1c")))

    # ---------------- 6. 只读 Text（预览区形态） ----------------
    ro = tk.Text(root, undo=False, state="disabled")
    cro = m.install_text_context_menu(ro, editable=False)
    check("只读菜单项", cro.labels() == READONLY_LABELS, str(cro.labels()))
    ro.configure(state="normal")
    ro.insert("1.0", "预览内容一\n预览内容二")
    ro.configure(state="disabled")
    cro.refresh_state()
    check("只读_全选可用", state_of(cro, "全选") == "normal")
    check("只读_复制禁用(无选区)", state_of(cro, "复制") == "disabled")
    check("只读_全选动作成功", cro.fire("select") is True)
    check("只读_全选选区成立", cro.has_selection() is True)
    check("只读_全选文本正确", cro.selection_text() == "预览内容一\n预览内容二",
          repr(cro.selection_text()))
    cro.refresh_state()
    check("只读_有选区复制可用", state_of(cro, "复制") == "normal")
    check("只读_复制动作成功", cro.fire("copy") is True)
    check("只读_复制进剪贴板", ro.clipboard_get() == "预览内容一\n预览内容二")
    check("只读_无剪切项", state_of(cro, "剪切") == "missing")
    check("只读_无撤销项", state_of(cro, "撤销") == "missing")
    check("只读_剪切动作无效", cro.fire("cut") is False)
    check("只读_粘贴动作无效", cro.fire("paste") is False)
    check("只读_删除动作无效", cro.fire("delete") is False)
    check("只读_原文未被改", ro.get("1.0", "end-1c") == "预览内容一\n预览内容二")

    # ---------------- 7. Entry 也能用 ----------------
    ent = tk.Entry(root)
    cen = m.install_text_context_menu(ent, editable=True)
    check("Entry菜单项", cen.labels() == EDIT_LABELS, str(cen.labels()))
    ent.insert(0, "abc")
    cen.fire("select")
    check("Entry全选", cen.has_selection() is True)
    check("Entry选区文本", cen.selection_text() == "abc", repr(cen.selection_text()))
    cen.fire("copy")
    check("Entry复制", ent.clipboard_get() == "abc")
    cen.fire("cut")
    check("Entry剪切", ent.get() == "", repr(ent.get()))

    # ---------------- 8. 主题配色跟随 ----------------
    dark = m.palette_of(m.THEME_DARK)
    cm.restyle(dark)
    check("主题_菜单背景跟随", str(cm.menu.cget("background")) == dark["menu_bg"],
          "%s vs %s" % (cm.menu.cget("background"), dark["menu_bg"]))
    check("主题_菜单前景跟随", str(cm.menu.cget("foreground")) == dark["menu_fg"])
    light = m.palette_of(m.THEME_LIGHT)
    cm.restyle(light)
    check("主题_切回浅色", str(cm.menu.cget("background")) == light["menu_bg"])

    # ---------------- 9. 源码集成点 ----------------
    with io.open(SRC, encoding="utf-8-sig") as f:
        src = f.read()
    check("集成_命令录入框", "self._attach_context_menu(self.cmd_text, editable=True)" in src)
    check("集成_源码编辑区", "self._attach_context_menu(self.editor, editable=True" in src)
    check("集成_实时预览", "self._attach_context_menu(self.preview, editable=False)" in src)
    check("集成_插入视频输入框", "self._attach_context_menu(box, editable=True)" in src)
    check("集成_更新说明文本",
          "install_text_context_menu(notes_text" in src)
    check("集成_主题重上色", "ctx.restyle(self.palette)" in src)
    check("集成_编辑器联动刷新", "on_changed=self._after_context_edit" in src)
    # 不再保留任何英文默认右键菜单痕迹（tkinter 默认菜单为英文 Copy/Paste）
    check("无英文菜单项", not re.search(r'add_command\(label="(Copy|Paste|Cut|Select All)"', src))

    try:
        root.destroy()
    except Exception:
        pass

    print("\n%d / %d PASS" % (PASS, PASS + FAIL))
    if FAIL:
        print("失败项：")
        for item in FAILED:
            print(" - %s" % item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
