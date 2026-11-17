# -*- coding: utf-8 -*-
"""v1.5.0 exe 端到端验证：单实例转交 + 标题切换 + 无残留进程。"""
import ctypes
import ctypes.wintypes as wt
import io
import os
import subprocess
import sys
import tempfile
import time

EXE = r"E:\yscl\MdCmdTool\爽哥MD编辑工具.exe"
NAME = "爽哥MD编辑工具.exe"
PASS, FAIL = [], []
# v1.11.0：版本号从主源码 dynamic 读取，避免每次发版都要改校验脚本
def _read_app_ver():
    import os
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(root, "爽哥MD命令生成工具.py"),
                  encoding="utf-8-sig").read()
    hit = re.search(r'APP_VERSION\s*=\s*"([\d.]+)"', src)
    return hit.group(1) if hit else "0.0.0"


APP_VER = _read_app_ver()


def ok(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, extra))


def pids_of(name):
    TH32CS_SNAPPROCESS = 0x2

    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32()
    pe.dwSize = ctypes.sizeof(PE32)
    out = []
    got = k32.Process32FirstW(snap, ctypes.byref(pe))
    while got:
        if pe.szExeFile.lower() == name.lower():
            out.append(pe.th32ProcessID)
        got = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return out


def app_titles(pids):
    """枚举所有同名进程的可见窗口标题（--onefile 有父/子两进程，窗口在子进程上）。"""
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    res = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, lparam):
        p = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value in pids and u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u32.GetWindowTextW(hwnd, buf, n + 1)
                if "爽哥MD编辑工具" in buf.value:
                    res.append(buf.value)
        return True

    u32.EnumWindows(cb, 0)
    return res


def main():
    work = tempfile.mkdtemp(prefix="sgmd_exe150_")
    p1 = os.path.join(work, "t1.md")
    p2 = os.path.join(work, "t2.md")
    io.open(p1, "w", encoding="utf-8").write("# T1\n")
    io.open(p2, "w", encoding="utf-8").write("# T2\n")

    before = pids_of(NAME)
    ok("启动前无同类进程", before == [], str(before))

    subprocess.Popen([EXE, p1], cwd=os.path.dirname(EXE))
    time.sleep(9)
    pids = pids_of(NAME)
    ok("首个实例已启动", len(pids) >= 1, str(pids))
    t = app_titles(set(pids)) if pids else []
    ok("窗口标题含版本号", any(("v%s" % APP_VER) in x for x in t), str(t))
    ok("窗口标题含 t1.md", any("t1.md" in x for x in t), str(t))
    ok("标题无未保存标记", all(not x.endswith("*") for x in t), str(t))

    base = len(pids)
    subprocess.Popen([EXE, p2], cwd=os.path.dirname(EXE))
    time.sleep(7)
    pids2 = pids_of(NAME)
    ok("第二个实例未常驻（进程数未增加）", len(pids2) <= base, "%s -> %s" % (base, len(pids2)))
    t2 = app_titles(set(pids2)) if pids2 else []
    ok("标题切换为 t2.md", any("t2.md" in x for x in t2), str(t2))

    for pid in pids2:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    time.sleep(3)
    ok("退出后无残留进程", pids_of(NAME) == [], str(pids_of(NAME)))
    print("测试目录（保留）:", work)
    print("\n通过 %d / %d" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        print("失败项:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
