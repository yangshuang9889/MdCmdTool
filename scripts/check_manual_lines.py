# -*- coding: utf-8 -*-
"""开发手册行号引用校验：符号 -> 源码定义行 / 方法体区间比对。"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")
MAN = os.path.join(BASE, "开发手册.md")


def read_lines(path):
    with io.open(path, encoding="utf-8-sig") as f:
        return f.read().replace("\r\n", "\n").split("\n")


def parse_source(lines):
    """返回 {符号: [(起始行, 结束行, 所属类)]}，覆盖 def / class。"""
    defs = {}
    stack = []          # [(indent, name)]
    cur = None
    for i, line in enumerate(lines, 1):
        if not line.strip():
            # 空行不打断代码块（Python 允许方法内空行）
            continue
        indent = len(line) - len(line.lstrip(" "))
        if cur and indent <= stack[-1][0] and line.strip():
            # 收束上一批定义：把结束行记到最近定义
            pass
        m = re.match(r"^(\s*)(?:class|def)\s+([A-Za-z_]\w*)", line)
        if m:
            name = m.group(2)
            stack.append((indent, name, i))
            defs.setdefault(name, []).append([i, i, indent])
    # 计算每个定义的方法体结束行：下一个缩进 <= 自身缩进 的代码行 - 1
    ent = [(name, item) for name, items in defs.items() for item in items]
    ent.sort(key=lambda x: x[1][0])
    for k, (name, item) in enumerate(ent):
        start, _, indent0 = item
        end = len(lines)
        for name2, item2 in ent[k + 1:]:
            if item2[0] <= start:
                continue
            if item2[2] <= indent0:
                end = item2[0] - 1
                break
        item[1] = end
    # 模块级常量
    for i, line in enumerate(lines, 1):
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", line)
        if m:
            defs.setdefault(m.group(1), []).append([i, i, 0])
    return defs


REF_PATTERNS = [
    re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`\s*[（(]?\s*L(\d+)"),
    re.compile(r"\|\s*`?([A-Za-z_][A-Za-z0-9_.]*)`?\s*\|\s*L(\d+)\s*(?:[–-]\s*L(\d+))?\s*\|"),
]


def main():
    src = read_lines(SRC)
    man = read_lines(MAN)
    defs = parse_source(src)
    total = len(src)

    pairs = []
    for no, line in enumerate(man, 1):
        for pat in REF_PATTERNS:
            for m in pat.finditer(line):
                pairs.append((no, m.group(1), int(m.group(2))))
    seen = set()
    uniq = []
    for p in pairs:
        key = (p[1], p[2])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)

    ok = fail = unknown = 0
    fails = []
    for no, name, ln in uniq:
        items = defs.get(name)
        if not items:
            unknown += 1
            continue
        hit = any(s <= ln <= e for s, e, _ in items)
        if hit:
            ok += 1
        else:
            fail += 1
            fails.append((no, name, ln, items[0][0], items[0][1]))

    nums = [int(x) for x in re.findall(r"L(\d+)", "\n".join(man))]
    over = [n for n in nums if n < 1 or n > total]

    print("源码行数: %d" % total)
    print("引用对(去重): %d  通过: %d  失败: %d  非符号: %d" % (len(uniq), ok, fail, unknown))
    print("L 数字总数: %d  越界: %d" % (len(nums), len(over)))
    if over:
        print("越界示例:", sorted(set(over))[:20])
    if fails:
        print("--- 失败明细（手册行号 / 符号 / 引用行 / 源码定义区间）---")
        for f in fails:
            print("  手册L%-5d `%s` L%-5d  应在 %d-%d" % f)
    return 0 if fail == 0 and not over else 1


if __name__ == "__main__":
    sys.exit(main())
