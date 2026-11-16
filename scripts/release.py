#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""爽哥发版助手 —— 用 GitHub API 一条命令发版，不用打开浏览器。

为什么有它
----------
网页上传 30MB 的 exe 经常卡半天、还容易传到一半失败。本脚本直连 GitHub
REST API：建 tag → 建/更 Release → 上传资产 → 改资产显示名，全程命令行完成。

凭据来源
--------
不需要新建 PAT，直接复用本机 Git Credential Manager 里已登录的 token
（git credential fill 现取现用，不写盘、不回显）。若 GCM 里的凭据失效，
把 GITHUB_TOKEN 环境变量设上即可，脚本会优先用它。

常用命令
--------
    # 看一眼线上现有发行版（只读，安全）
    python scripts/release.py info

    # 演练：只打印将要做什么，不真的改动
    python scripts/release.py publish --dry-run

    # 正式发版：版本号默认取主程序里的 APP_VERSION
    python scripts/release.py publish

    # 指定版本 / 资产文件 / 自定义说明
    python scripts/release.py publish -v 1.9.0 --asset dist/SgMdEditor-v1.9.0.exe \\
        --notes-file notes.md

    # 只补传资产，不动说明和标题
    python scripts/release.py publish --skip-meta

发版前会做的检查
----------------
1. 资产文件必须存在，且体积与 dist/ 里的一致；
2. 版本号必须能在 CHANGELOG.md 里找到对应小节（自动抽成发行说明）；
3. version_info.txt 的 filevers 必须与版本号一致，防止打歪包；
4. 同名资产已存在时默认拒绝覆盖，需加 --force 才删旧传新。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:  # Windows 控制台默认 GBK，避免打印中文说明时崩掉
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API = "https://api.github.com"
UPLOAD_API = "https://uploads.github.com"
UA = "shuage-release-helper/1.1"
CONFIG_NAME = "release.json"


def _default_root() -> str:
    """脚本放在 <项目>/scripts/ 下时自动上溯一级，否则认为脚本就在项目根。"""
    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(here).lower() == "scripts":
        return os.path.dirname(here)
    return here


ROOT = _default_root()  # 项目根目录，main() 里可被 -C/--project 覆盖


# ---------------------------------------------------------------- 基础工具


class ReleaseError(RuntimeError):
    pass


def run(cmd: list[str], cwd: str | None = None, stdin: str | None = None,
        env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, cwd=cwd, input=stdin, capture_output=True,
                          text=True, timeout=180, env=env)


def die(msg: str, code: int = 1):
    print(f"\n[失败] {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- 凭据与仓库


def get_token() -> str:
    """优先 GITHUB_TOKEN 环境变量，其次从 Git Credential Manager 现取。"""
    for key in ("GITHUB_TOKEN", "GH_TOKEN"):
        tok = os.environ.get(key, "").strip()
        if tok:
            return tok

    git = shutil_which("git")
    if not git:
        die("找不到 git，无法读取本机凭据；请设置 GITHUB_TOKEN 环境变量。")

    proc = run([git, "credential", "fill"],
               stdin="protocol=https\nhost=github.com\n\n")
    if proc.returncode != 0:
        die("Git Credential Manager 未返回凭据。\n"
            f"{proc.stderr.strip()}\n"
            "请先 git push 一次完成登录，或设置 GITHUB_TOKEN 环境变量。")

    fields = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k] = v
    tok = fields.get("password", "").strip()
    if not tok:
        die("GCM 里没有 github.com 的 token，可用 git push 触发登录后再试。")
    return tok


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def detect_repo() -> str:
    """从 git remote origin 解析 owner/repo，解析不到就报错。"""
    git = shutil_which("git")
    if git:
        proc = run([git, "-C", ROOT, "remote", "get-url", "origin"])
        if proc.returncode == 0 and proc.stdout.strip():
            url = proc.stdout.strip()
            m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", url)
            if m:
                return f"{m.group(1)}/{m.group(2)}"
    die("无法从 git remote origin 解析仓库，请用 --repo owner/name 指定。")


class GitHub:
    def __init__(self, repo: str, token: str, dry_run: bool = False):
        self.repo = repo
        self.token = token
        self.dry_run = dry_run

    def _request(self, url: str, method: str = "GET", data: bytes | None = None,
                 headers: dict | None = None, timeout: int = 120):
        hdrs = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": UA,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, method=method, data=data, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return resp.status, None
                try:
                    return resp.status, json.loads(raw.decode("utf-8"))
                except Exception:
                    return resp.status, raw[:200].decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            return e.code, body
        except urllib.error.URLError as e:
            return 0, f"网络错误: {e}"

    def api(self, path: str, method: str = "GET", data=None):
        body = json.dumps(data).encode("utf-8") if data is not None else None
        hdrs = {"Content-Type": "application/json"} if body else {}
        return self._request(API + path, method, body, hdrs)

    # -------------------------------------------------------- 具体操作

    def whoami(self):
        status, data = self.api("/user")
        if status != 200:
            die(f"鉴权失败（HTTP {status}）：{str(data)[:300]}")
        return data

    def check_permission(self) -> dict:
        status, data = self.api(f"/repos/{self.repo}")
        if status != 200:
            die(f"读不到仓库 {self.repo}（HTTP {status}）：{str(data)[:300]}")
        return data

    def get_release_by_tag(self, tag: str):
        status, data = self.api(f"/repos/{self.repo}/releases/tags/{tag}")
        if status == 200:
            return data
        if status == 404:
            return None
        die(f"查询 release 失败（HTTP {status}）：{str(data)[:300]}")

    def list_releases(self, limit: int = 10):
        status, data = self.api(f"/repos/{self.repo}/releases?per_page={limit}")
        if status != 200:
            die(f"查询 release 列表失败（HTTP {status}）：{str(data)[:300]}")
        return data

    def create_release(self, tag: str, title: str, body: str,
                       prerelease: bool, draft: bool, target: str):
        payload = {
            "tag_name": tag,
            "target_commitish": target,
            "name": title,
            "body": body,
            "draft": draft,
            "prerelease": prerelease,
        }
        status, data = self.api(f"/repos/{self.repo}/releases", "POST", payload)
        if status not in (200, 201):
            die(f"创建 release 失败（HTTP {status}）：{str(data)[:500]}")
        return data

    def update_release(self, release_id: int, payload: dict):
        status, data = self.api(f"/repos/{self.repo}/releases/{release_id}",
                                "PATCH", payload)
        if status != 200:
            die(f"更新 release 失败（HTTP {status}）：{str(data)[:500]}")
        return data

    def delete_asset(self, asset_id: int):
        status, data = self.api(f"/repos/{self.repo}/releases/assets/{asset_id}",
                                "DELETE")
        if status not in (204, 200):
            die(f"删除旧资产失败（HTTP {status}）：{str(data)[:300]}")

    def rename_asset(self, asset_id: int, new_name: str):
        status, data = self.api(f"/repos/{self.repo}/releases/assets/{asset_id}",
                                "PATCH", {"name": new_name})
        if status != 200:
            die(f"重命名资产失败（HTTP {status}）：{str(data)[:300]}")
        return data

    def upload_asset(self, upload_url: str, file_path: str, asset_name: str):
        """upload_url 形如 https://uploads.github.com/repos/o/r/releases/1/assets{?name,label}"""
        base = upload_url.split("{", 1)[0]
        url = f"{base}?name={urllib.parse.quote(asset_name)}"
        size = os.path.getsize(file_path)
        print(f"  上传 {os.path.basename(file_path)} → {asset_name} "
              f"（{size / 1048576:.1f} MB）...")
        started = time.time()

        # 30MB 级别用一次性 POST 即可；用 with 保证句柄及时释放
        with open(file_path, "rb") as f:
            blob = f.read()
        status, data = self._request(
            url, "POST", blob,
            {"Content-Type": "application/octet-stream"}, timeout=900)

        if status not in (200, 201):
            die(f"上传失败（HTTP {status}）：{str(data)[:500]}")
        cost = time.time() - started
        print(f"  上传完成，用时 {cost:.1f}s（{size / 1048576 / max(cost, 0.01):.1f} MB/s）")
        return data


# ---------------------------------------------------------------- 本地信息
#
# 不同项目的约定千差万别，这里全部靠「探测 + 可覆盖」：
#   版本号   ← 根目录任意 .py 里的 APP_VERSION / __version__ / VERSION
#   发行说明 ← CHANGELOG*.md / 更新日志*.md 里对应版本的小节
#   资产     ← dist/ 下带版本号的 exe，或唯一的那个 exe
#   显示名   ← release.json > APP_NAME > 根目录 exe 名
# 探测不准时用命令行参数（-v / --asset / --asset-name / --notes-file）兜底。


def load_project_config() -> dict:
    """项目根可放 release.json 做长期配置，避免每次敲一长串参数。

    {
      "repo": "owner/name",
      "asset": "dist/xxx.exe",
      "asset_name": "中文显示名.exe",
      "target": "main"
    }
    """
    path = os.path.join(ROOT, CONFIG_NAME)
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path, encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[警告] {CONFIG_NAME} 解析失败，已忽略：{e}")
        return {}


SKIP_DIRS = {".git", ".github", ".venv", "venv", "env", "build", "dist", "__pycache__",
             "node_modules", "tests", "test", "docs", "archives", "temp", "analysis",
             ".idea", ".vscode", "site-packages"}


def iter_py_files(max_depth: int = 2) -> list[str]:
    """列出项目里的 .py（含最多两层子目录），跳过构建/测试/分析等噪音目录。"""
    out = []
    base = ROOT.rstrip("\\/").count(os.sep)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        depth = dirpath.rstrip("\\/").count(os.sep) - base
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames
                       if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for n in filenames:
            if n.endswith(".py"):
                out.append(os.path.join(dirpath, n))
    # 主程序通常体积最大，优先扫它
    out.sort(key=lambda p: os.path.getsize(p), reverse=True)
    return out


def read_app_meta() -> dict:
    """从项目里的 .py 找版本号与应用名，找不到返回 None。"""
    meta = {"name": None, "version": None, "source": None}
    ver_pat = re.compile(
        r'^(?:APP_VERSION|__version__|VERSION)\s*=\s*["\']([^"\']{1,24})["\']', re.M)
    name_pat = re.compile(r'^(?:APP_NAME|APP_TITLE)\s*=\s*["\']([^"\']+)["\']', re.M)
    for fp in iter_py_files():
        try:
            txt = open(fp, encoding="utf-8", errors="ignore").read(400000)
        except OSError:
            continue
        if meta["version"] is None:
            m = ver_pat.search(txt)
            if m:
                meta["version"] = m.group(1).strip().lstrip("vV")
                meta["source"] = os.path.basename(fp)
        if meta["name"] is None:
            m = name_pat.search(txt)
            if m:
                meta["name"] = m.group(1).strip()
        if meta["version"] and meta["name"]:
            break
    if meta["name"]:
        # 去掉名字尾巴上的版本号，如「爽哥雷池告警助手  V1.4」
        meta["name"] = re.sub(r"\s*[vV]?\d+(?:\.\d+)+\s*$", "", meta["name"]).strip() or None
    if meta["name"] is None:
        # 退一步：用项目根目录的 exe 名或目录名当应用名
        exes = [n[:-4] for n in os.listdir(ROOT) if n.lower().endswith(".exe")] \
            if os.path.isdir(ROOT) else []
        meta["name"] = exes[0] if len(exes) == 1 else os.path.basename(ROOT.rstrip("\\/"))
    return meta


def read_version_info() -> tuple | None:
    """读 version_info*.txt 里的 filevers，用于核对打包是否同步。"""
    try:
        names = [n for n in os.listdir(ROOT) if n.lower().startswith("version_info")
                 and n.lower().endswith(".txt")]
    except OSError:
        return None
    for n in sorted(names):
        try:
            txt = open(os.path.join(ROOT, n), encoding="utf-8-sig", errors="ignore").read()
        except OSError:
            continue
        m = re.search(r"filevers\s*=\s*\(([^)]+)\)", txt)
        if m:
            try:
                return tuple(int(x.strip()) for x in m.group(1).split(","))
            except ValueError:
                continue
    return None


def changelog_path() -> str | None:
    try:
        names = os.listdir(ROOT)
    except OSError:
        return None
    for n in names:
        low = n.lower()
        if (("changelog" in low or "更新日志" in n) and low.endswith((".md", ".txt", ".markdown"))
                and os.path.isfile(os.path.join(ROOT, n))):
            return os.path.join(ROOT, n)
    return None


def extract_changelog(version: str) -> str | None:
    """抽出版本小节正文。

    兼容几种常见写法：
        ## v1.9.0（2026-11-16）      口语版
        ## [1.9.12] - 2026-11-10     Keep a Changelog
        ### 1.9.12
    """
    path = changelog_path()
    if not path:
        return None
    txt = open(path, encoding="utf-8-sig", errors="ignore").read()
    pattern = re.compile(
        r"^#{1,4}[ \t]+\[?[ \t]*v?" + re.escape(version) + r"(?![0-9.])\]?[^\n]*\n"
        r"(.*?)(?=^#{1,2}[ \t]|\Z)",
        re.M | re.S)
    m = pattern.search(txt)
    if not m:
        return None
    body = re.sub(r"\n{3,}", "\n\n", m.group(1).strip("\n"))
    return body.strip() or None


def list_dist_exes() -> list[str]:
    dist = os.path.join(ROOT, "dist")
    if not os.path.isdir(dist):
        return []
    return [os.path.join(dist, n) for n in sorted(os.listdir(dist))
            if n.lower().endswith(".exe") and os.path.isfile(os.path.join(dist, n))]


def default_asset_path(version: str) -> str | None:
    """优先级：dist 下带版本号的 exe > 按应用名命名的 exe > 唯一 exe > 根目录 exe。"""
    exes = list_dist_exes()
    hit = [p for p in exes if version in os.path.basename(p)]
    if len(hit) == 1:
        return hit[0]
    name = read_app_meta().get("name") or ""
    named = [p for p in exes if name and os.path.basename(p) == f"{name}.exe"]
    if len(named) == 1:
        return named[0]
    if len(exes) == 1:
        return exes[0]
    root_exe = [os.path.join(ROOT, n) for n in os.listdir(ROOT)
                if n.lower().endswith(".exe") and name and n == f"{name}.exe"] \
        if os.path.isdir(ROOT) else []
    if len(root_exe) == 1:
        return root_exe[0]
    return None


def default_asset_name() -> str:
    """资产在 GitHub 上的显示名：release.json > 实际要传的文件名 > APP_NAME.exe。"""
    cfg = load_project_config()
    if cfg.get("asset_name"):
        return str(cfg["asset_name"])
    meta = read_app_meta()
    ver = meta.get("version")
    path = default_asset_path(ver) if ver else None
    if path:
        return os.path.basename(path)
    name = meta.get("name")
    return f"{name}.exe" if name else "release.exe"


# ---------------------------------------------------------------- 子命令


def cmd_info(gh: GitHub, args):
    me = gh.whoami()
    repo = gh.check_permission()
    print(f"账号      : {me.get('login')}")
    print(f"仓库      : {repo.get('full_name')}  默认分支 {repo.get('default_branch')}")
    print(f"本地版本  : APP_VERSION={read_app_meta().get('version')}  "
          f"version_info={read_version_info()}")
    print("\n线上发行版：")
    for rel in gh.list_releases(args.limit):
        flag = []
        if rel.get("draft"):
            flag.append("草稿")
        if rel.get("prerelease"):
            flag.append("预发行")
        tag = rel.get("tag_name")
        print(f"\n  {tag}  |  {rel.get('name')}  |  {''.join(flag) or '正式'}")
        print(f"    发布: {rel.get('published_at')}   id={rel.get('id')}  "
              f"说明 {len(rel.get('body') or '')} 字符")
        for a in rel.get("assets", []):
            print(f"    资产: {a.get('name')}  {a.get('size')} 字节  id={a.get('id')}")
            print(f"          {a.get('browser_download_url')}")


def cmd_publish(gh: GitHub, args):
    meta = read_app_meta()
    version = (args.version or meta.get("version") or "").lstrip("vV")
    if not version:
        die("没拿到版本号：主程序里找不到 APP_VERSION，请用 -v 指定。")

    tag = f"v{version}"
    title = args.title or f"{tag} {first_line_of_notes(version) or ''}".strip()

    # --- 说明正文
    if args.notes_file:
        body = open(args.notes_file, encoding="utf-8-sig").read().strip()
    elif args.notes:
        body = args.notes
    else:
        body = extract_changelog(version)
        cl = changelog_path()
        if not body:
            die(f"{os.path.basename(cl) if cl else 'CHANGELOG'} 里没找到 v{version} 的小节，"
                "请先补上或用 --notes / --notes-file 指定说明。")
    if not body:
        die("发行说明为空，已中止（GitHub 上会显示成空说明）。")

    # --- 资产文件
    asset_path = args.asset or default_asset_path(version)
    if not args.skip_upload and not asset_path:
        die(f"找不到 v{version} 的 exe，请用 --asset 指定路径。")
    if asset_path and not os.path.exists(asset_path):
        die(f"资产文件不存在：{asset_path}")
    asset_name = args.asset_name or default_asset_name()

    # --- 一致性检查
    warns = []
    fatal = []
    vi = read_version_info()
    if vi:
        expect = tuple(int(x) for x in (version.split(".") + ["0", "0", "0"])[:4])
        if tuple(vi) != expect:
            warns.append(f"version_info 是 {vi}，与版本号 {version} 不一致（{expect}）")
    if asset_path and asset_path.lower().endswith(".exe"):
        size_mb = os.path.getsize(asset_path) / 1048576
        if size_mb < 1:
            warns.append(f"资产只有 {size_mb:.2f} MB，像是不完整的包")
        hint = exe_version_hint(asset_path, version)
        if hint is False:
            fatal.append(
                f"资产 {os.path.basename(asset_path)} 内嵌版本不是 {version}，"
                "八成是上一个版本的旧包，请先重新打包（build.bat）")
        elif hint is None:
            warns.append("读不到资产内嵌版本，无法确认包是否为本次构建")

    print(f"仓库      : {gh.repo}")
    print(f"版本      : {version}  →  tag {tag}")
    print(f"标题      : {title}")
    print(f"说明      : {len(body)} 字符（来自 "
          f"{'文件' if args.notes_file else '参数' if args.notes else os.path.basename(changelog_path() or 'CHANGELOG')}）")
    print(f"资产      : {asset_path or '(跳过)'}"
          + (f"  {os.path.getsize(asset_path)} 字节" if asset_path else ""))
    print(f"显示名    : {asset_name}")
    print(f"草稿/预发行: {args.draft} / {args.prerelease}")
    for w in warns:
        print(f"[警告] {w}")
    for f in fatal:
        print(f"[中止原因] {f}")
    if fatal and not args.allow_version_mismatch:
        if args.dry_run:
            print("\n[dry-run] 正式执行时会在这里中止；确实要用旧包请加 --allow-version-mismatch")
        else:
            die("包内容与版本号对不上，已中止，未改动线上任何内容。\n"
                "  · 正确做法：先 build.bat 重新打包，再发版\n"
                "  · 若坚持用现有文件：加 --allow-version-mismatch")

    if args.dry_run:
        print("\n[dry-run] 以上为预演，未做任何改动。")
        existing = gh.get_release_by_tag(tag)
        print(f"[dry-run] 线上是否已存在 {tag}: {'是' if existing else '否'}")
        return

    # --- 1) 本地打 annotated tag 并推送（与项目习惯一致）
    existing = gh.get_release_by_tag(tag)
    if not args.no_git_tag:
        ensure_git_tag(tag, dry_run=args.dry_run)

    # --- 2) 创建或更新 release
    if existing:
        if not args.skip_meta:
            print(f"\n[1/2] 更新已有 Release（id={existing['id']}）")
            rel = gh.update_release(existing["id"], {
                "name": title,
                "body": body,
                "prerelease": bool(args.prerelease),
                "draft": bool(args.draft),
            })
            print("      已更新标题与说明")
        else:
            rel = existing
            print(f"\n[1/2] 跳过元信息（--skip-meta），沿用已有 Release id={rel['id']}")
    else:
        print(f"\n[1/2] 新建 Release {tag}")
        rel = gh.create_release(tag, title, body, bool(args.prerelease),
                               bool(args.draft), args.target)

    # --- 3) 上传资产
    if args.skip_upload or not asset_path:
        print("[2/2] 跳过资产上传")
    else:
        print("[2/2] 处理资产")
        rel = refresh_release(gh, tag)
        same = [a for a in rel.get("assets", []) if a.get("name") == asset_name]
        same_size = [a for a in same if a.get("size") == os.path.getsize(asset_path)]
        if same_size and not args.force:
            print(f"      已存在同名同体积资产 {asset_name}，跳过（要重传加 --force）")
        else:
            for a in same:
                if not args.force:
                    die(f"已存在同名资产 {asset_name} 但体积不同，为防覆盖已中止；"
                        "确认要替换请加 --force")
                print(f"      删除旧资产 {a.get('name')} (id={a.get('id')})")
                gh.delete_asset(a["id"])
            gh.upload_asset(rel["upload_url"], asset_path, asset_name)
            rel = refresh_release(gh, tag)

    # --- 4) 结果核对
    rel = refresh_release(gh, tag)
    print(f"\n完成：{rel.get('html_url')}")
    for a in rel.get("assets", []):
        print(f"  资产 {a.get('name')}  {a.get('size')} 字节")
        print(f"  下载 {a.get('browser_download_url')}")
    if not rel.get("assets"):
        print("  [注意] 该 Release 目前没有任何资产")
    print(f"\n程序内「检查更新」读到的版本：{rel.get('tag_name')}（"
          f"{'预发行' if rel.get('prerelease') else '正式'}）")


def first_line_of_notes(version: str) -> str:
    """取小节里第一句正文当标题摘要，兼容「首行摘要」和「### 分类 + 列表」两种排版。"""
    body = extract_changelog(version) or ""
    for line in body.splitlines():
        s = line.strip().lstrip("*").strip()
        if not s or s.startswith("#"):
            continue
        s = s.lstrip("-").strip()
        if s:
            return s.replace("**", "")[:100]
    return ""


def exe_version_hint(path: str, version: str) -> bool | None:
    """判断 exe 内嵌版本是否与目标版本一致。

    PyInstaller 把 VS_VERSION_INFO 以 UTF-16LE 存进资源段，直接搜
    「1.9.0.0」这样的四段版本串即可，不用装 pywin32。返回 None 表示判断不了。
    """
    if not os.path.exists(path):
        return None
    full = version if version.count(".") == 3 else f"{version}.0"
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return None
    for enc in ("utf-16-le", "ascii"):
        try:
            if full.encode(enc) in blob:
                return True
        except Exception:
            continue
    return False


def ensure_git_tag(tag: str, dry_run: bool = False):
    git = shutil_which("git")
    if not git:
        print("  [跳过] 没找到 git，交给 GitHub 按 target_commitish 自动建 tag")
        return
    local = run([git, "-C", ROOT, "rev-parse", "-q", "--verify", f"refs/tags/{tag}"])
    if local.returncode == 0:
        remote = run([git, "-C", ROOT, "ls-remote", "--tags", "origin", tag])
        if remote.returncode == 0 and remote.stdout.strip():
            print(f"  tag {tag} 本地与远端都已存在，跳过")
            return
        push = run([git, "-C", ROOT, "push", "origin", f"refs/tags/{tag}"])
        print("  tag 已存在本地，推送：" + ("成功" if push.returncode == 0
                                          else f"失败 {push.stderr.strip()[:200]}"))
        return
    msg = f"release: {tag}"
    created = run([git, "-C", ROOT, "tag", "-a", tag, "-m", msg])
    if created.returncode != 0:
        print(f"  [警告] 本地打 tag 失败：{created.stderr.strip()[:200]}")
        return
    push = run([git, "-C", ROOT, "push", "origin", f"refs/tags/{tag}"])
    if push.returncode == 0:
        print(f"  tag {tag} 已创建并推送")
    else:
        print(f"  [警告] tag 推送失败：{push.stderr.strip()[:300]}")


def refresh_release(gh: GitHub, tag: str) -> dict:
    rel = gh.get_release_by_tag(tag)
    if not rel:
        die(f"刚提交的操作在 {tag} 上读不回来，请到网页确认")
    return rel


# ---------------------------------------------------------------- 入口


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="爽哥发版助手：用 GitHub API 一条命令发版，不用浏览器。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  python scripts/release.py info\n"
               "  python scripts/release.py publish --dry-run\n"
               "  python scripts/release.py publish\n")
    p.add_argument("-C", "--project", default=None,
                   help="项目根目录，默认用脚本所在项目的根（一个脚本给所有项目发版）")
    p.add_argument("--repo", default=None,
                   help="owner/name，默认从 release.json 或 git remote 解析")
    # 注意：子解析器的同名参数会覆盖父级取值，所以父级单独用 dry_run_global
    p.add_argument("--dry-run", action="store_true", dest="dry_run_global",
                   help="只演练，不改动线上")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("info", help="查看线上发行版（只读）")
    sp.add_argument("--limit", type=int, default=10)

    sq = sub.add_parser("publish", help="创建或更新发行版并上传资产")
    sq.add_argument("--dry-run", action="store_true",
                    help="只演练，不改动线上（写在这里或子命令前都可以）")
    sq.add_argument("-v", "--version", default=None, help="版本号，默认取 APP_VERSION")
    sq.add_argument("--title", default=None, help="Release 标题")
    sq.add_argument("--notes", default=None, help="直接用这段文字作发行说明")
    sq.add_argument("--notes-file", default=None, help="从文件读发行说明")
    sq.add_argument("--asset", default=None, help="要上传的 exe 路径")
    sq.add_argument("--asset-name", default=None,
                    help="资产在 GitHub 上的显示名，默认取 release.json / APP_NAME")
    sq.add_argument("--target", default=None,
                    help="不建 tag 时的目标分支，默认 release.json 里的 target 或 main")
    sq.add_argument("--draft", action="store_true", help="存为草稿")
    sq.add_argument("--prerelease", action="store_true", help="标记为预发行")
    sq.add_argument("--force", action="store_true", help="同名资产已存在时删旧传新")
    sq.add_argument("--allow-version-mismatch", action="store_true",
                    help="即使 exe 内嵌版本与版本号不一致也照发（有风险，慎用）")
    sq.add_argument("--skip-upload", action="store_true", help="只改说明与标题")
    sq.add_argument("--skip-meta", action="store_true", help="只传资产，不动标题与说明")
    sq.add_argument("--no-git-tag", action="store_true",
                    help="不在本地打 tag，交给 API 自动建")

    # 子命令后面也允许写 -C，用 SUPPRESS 避免把父级已填的值冲掉
    for sub_p in (sp, sq):
        sub_p.add_argument("-C", "--project", default=argparse.SUPPRESS,
                           help="项目根目录（写在子命令后面也可以）")
    return p


def main(argv=None) -> int:
    global ROOT
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(raw)

    project = getattr(args, "project", None)
    if not project:
        # 允许把 -C 写在子命令后面，如 publish -C E:\other
        for i, a in enumerate(raw):
            if a in ("-C", "--project") and i + 1 < len(raw):
                project = raw[i + 1]
                break
            if a.startswith("--project="):
                project = a.split("=", 1)[1]
                break
    if project:
        ROOT = os.path.abspath(os.path.expanduser(project))
    if not os.path.isdir(ROOT):
        die(f"项目目录不存在：{ROOT}")

    cfg = load_project_config()
    args.dry_run = bool(getattr(args, "dry_run", False)
                        or getattr(args, "dry_run_global", False))
    repo = args.repo or cfg.get("repo") or detect_repo()
    token = get_token()
    gh = GitHub(repo, token, dry_run=args.dry_run)

    if args.cmd == "info":
        print(f"项目目录  : {ROOT}")
        cmd_info(gh, args)
    elif args.cmd == "publish":
        # release.json 兜底，命令行显式参数优先
        if cfg.get("asset") and not args.asset:
            a = str(cfg["asset"])
            args.asset = a if os.path.isabs(a) else os.path.join(ROOT, a)
        args.target = args.target or cfg.get("target") or "main"
        cmd_publish(gh, args)
    else:
        die(f"未知子命令 {args.cmd}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
