# -*- coding: utf-8 -*-
"""v1.6.0 在线检查更新功能验证脚本（源码级，不启动界面）。

覆盖点：
  1. 版本号常量与更新源地址是否正确指向开源仓库；
  2. parse_version / compare_version 的边界用例；
  3. parse_release_payload 对 GitHub 返回体的解析（含缺失字段、非法 tag）;
  4. 连接真实 GitHub API：有 Release 时应返回可解析版本，仓库暂无发布版本时应抛 LookupError，网络异常应抛 RuntimeError；
  5. 设置项 auto_check_update 默认关闭且能被清洗函数正确吸收。

用法：python verify_update_v160.py
"""
import importlib.util
import os
import sys
import traceback

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print("[%s] %s%s" % ("PASS" if cond else "FAIL", name,
                         (" | " + detail) if detail else ""))


def load_module():
    spec = importlib.util.spec_from_file_location("sg_md_editor", SRC)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sg_md_editor"] = module
    spec.loader.exec_module(module)
    return module


def main():
    mod = load_module()

    # 1. 常量
    _ver = tuple(int(x) for x in mod.APP_VERSION.split("."))
    check("APP_VERSION >= 1.6.0", _ver >= (1, 6, 0), mod.APP_VERSION)
    check("UPDATE_REPO 指向开源仓库", mod.UPDATE_REPO == "yangshuang9889/MdCmdTool",
          mod.UPDATE_REPO)
    check("latest 接口地址正确",
          mod.UPDATE_API_LATEST ==
          "https://api.github.com/repos/yangshuang9889/MdCmdTool/releases/latest",
          mod.UPDATE_API_LATEST)
    check("发布页地址正确",
          mod.UPDATE_PAGE == "https://github.com/yangshuang9889/MdCmdTool/releases",
          mod.UPDATE_PAGE)
    check("超时为 8 秒", abs(mod.UPDATE_TIMEOUT - 8.0) < 1e-6, str(mod.UPDATE_TIMEOUT))

    # 2. 版本解析
    cases = [("v1.6.0", (1, 6, 0)), ("1.6", (1, 6, 0)), ("1.6.0.0", (1, 6, 0, 0)),
             ("V2.0", (2, 0, 0)), ("1.10.3", (1, 10, 3))]
    ok = all(mod.parse_version(src) == want for src, want in cases)
    check("parse_version 常规用例", ok)
    check("parse_version 非法输入返回 None",
          mod.parse_version("") is None and mod.parse_version(None) is None
          and mod.parse_version("release") is None)

    # 3. 版本比较
    cmp_cases = [("1.5.0", "1.6.0", 1), ("1.6.0", "1.6.0", 0), ("1.6.1", "1.6.0", -1),
                 ("1.5.0", "v1.5.0", 0), ("1.9.0", "1.10.0", 1),
                 ("1.5.0", "2.0", 1), ("1.5.0", "abc", None)]
    bad = [(a, b, want, mod.compare_version(a, b))
           for a, b, want in cmp_cases if mod.compare_version(a, b) != want]
    check("compare_version 全部用例", not bad, str(bad))

    # 4. 返回体解析
    payload = {"tag_name": "v1.6.0", "name": "v1.6.0 新增在线检查更新",
               "body": "## 新增\n- 通过 GitHub Releases 检查更新",
               "html_url": "https://github.com/yangshuang9889/MdCmdTool/releases/tag/v1.6.0",
               "published_at": "2026-11-15T10:00:00Z", "prerelease": False,
               "assets": [{"name": "爽哥MD编辑工具.exe",
                           "browser_download_url": "https://example.com/a.exe"}]}
    info = mod.parse_release_payload(payload)
    check("解析版本号", info["version"] == "1.6.0", info["version"])
    check("解析发布时间", info["published"] == "2026-11-15", info["published"])
    check("解析更新说明", "GitHub Releases" in info["notes"])
    check("解析下载资源", len(info["assets"]) == 1, str(info["assets"]))
    check("解析发布页链接", info["url"].endswith("/v1.6.0"))
    for bad_payload in (None, {}, {"tag_name": "nightly"}):
        try:
            mod.parse_release_payload(bad_payload)
            check("非法返回体应抛错 %r" % (bad_payload,), False)
        except (ValueError, TypeError):
            check("非法返回体应抛错 %r" % (bad_payload,), True)

    # 5. 真实网络请求（当前仓库可能还没有 Release）
    try:
        real = mod.fetch_latest_release()
        check("真实 API 请求", True, "最新版本 %s" % real["version"])
        parsed = mod.parse_version(real["version"])
        check("远端版本可解析", parsed is not None, str(real["version"]))
        cmp_result = mod.compare_version(mod.APP_VERSION, real["version"])
        check("远端版本可比较（1/0/-1）", cmp_result in (1, 0, -1), "本机 %s vs 远端 %s -> %r"
              % (mod.APP_VERSION, real["version"], cmp_result))
    except LookupError as exc:
        check("真实 API 请求（仓库暂无 Release 属正常）", True, str(exc))
    except RuntimeError as exc:
        check("真实 API 请求", False, "网络失败：%s" % exc)

    # 6. 设置项
    defaults = mod.default_settings()
    check("auto_check_update 默认关闭", defaults.get("auto_check_update") is False,
          str(defaults.get("auto_check_update")))
    check("清洗函数接受 True",
          mod._sanitize_settings({"auto_check_update": True})["auto_check_update"] is True)
    check("清洗函数忽略非布尔值",
          mod._sanitize_settings({"auto_check_update": "yes"})["auto_check_update"] is False)

    # 7. 源码静态检查：入口与防御
    text = open(SRC, encoding="utf-8-sig").read()
    check("帮助菜单含检查更新入口", 'label="检查更新..."' in text)
    check("关于窗口含检查更新按钮", 'text="检查更新"' in text)
    check("设置窗口含自动检查开关", '启动时自动检查更新' in text)
    check("网络请求在子线程执行", 'name="UpdateCheck"' in text)
    check("结果回到主线程 via root.after", 'self.root.after(0, lambda: self._on_update_result' in text)
    # 视频功能（v1.8.0）会拉起 Edge 播放器，因此不再禁止全局 subprocess，
    # 改为限定「更新链路内不出现任何下载 / 安装 / 自替换动作」
    _lines = text.splitlines()
    _start = next(k for k, ln in enumerate(_lines)
                  if ln.startswith("def fetch_latest_release"))
    _end = len(_lines)
    for _k in range(_start + 1, len(_lines)):
        if _lines[_k].startswith("def ") or _lines[_k].startswith("class "):
            _end = _k
            break
    _update_block = "\n".join(_lines[_start:_end])
    check("更新链路不自动下载安装",
          "urlretrieve" not in text
          and "subprocess" not in _update_block
          and "os.system" not in _update_block
          and "Popen" not in _update_block)

    passed = sum(1 for _, ok, _ in results if ok)
    print("\n合计 %d/%d PASS" % (passed, len(results)))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
