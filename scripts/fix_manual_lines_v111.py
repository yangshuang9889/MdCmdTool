# -*- coding: utf-8 -*-
"""fix_manual_lines_v111.py

按源码实际定义行重算「开发手册」里的 `符号` Lnnn 行号引用。

v1.10.1 改动给源码增加了行数（BILI_PLAYER_URL 注释 + bili_clean_url 函数），
手册里的行号引用随之整体漂移。本脚本把每条引用改写到对应符号的定义起始行，
区间引用（L104 – L105）保持原有跨度，改完后 check_manual_lines.py 应零失败。

用法：python scripts\\fix_manual_lines_v111.py
"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")
MAN = os.path.join(BASE, "开发手册.md")

REF_RE = re.compile(
    r"`(?P<name>[A-Za-z_][A-Za-z0-9_.]*)`[\s（(|]*"
    r"L(?P<n1>\d+)(?:\s*[–-]\s*L(?P<n2>\d+))?")


def read_lines(path):
    with io.open(path, encoding="utf-8-sig") as fp:
        return fp.read().replace("\r\n", "\n").split("\n")


def parse_defs(lines):
    """符号 -> 首个定义行（def / class / 模块级大写常量）。"""
    defs = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r"^\s*(?:class|def)\s+([A-Za-z_]\w*)", line)
        if m:
            defs.setdefault(m.group(1), i)
            continue
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", line)
        if m:
            defs.setdefault(m.group(1), i)
    return defs


def main():
    src = read_lines(SRC)
    man = read_lines(MAN)
    defs = parse_defs(src)

    table_re = re.compile(
        r"^\|\s*`(?P<name>[A-Za-z_][A-Za-z0-9_.]*)`\s*\|"
        r"[^|\n]*\|\s*L(?P<n1>\d+)(?:\s*[–-]\s*L(?P<n2>\d+))?\s*\|")

    changed = skipped = 0
    out = []
    for line in man:
        def repl(m):
            nonlocal changed, skipped
            name = m.group("name")
            start = defs.get(name)
            if start is None:
                skipped += 1
                return m.group(0)
            old1 = int(m.group("n1"))
            new1 = start
            text = m.group(0).replace("L%d" % old1, "L%d" % new1, 1)
            if m.group("n2"):
                old2 = int(m.group("n2"))
                new2 = new1 + (old2 - old1)
                text = text.replace("L%d" % old2, "L%d" % new2, 1)
            if text != m.group(0):
                changed += 1
            return text

        line = REF_RE.sub(repl, line)
        line = table_re.sub(repl, line)
        out.append(line)

    with io.open(MAN, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(out))

    print("手册引用重算完成：改动 %d 条，符号未找到 %d 条" % (changed, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
