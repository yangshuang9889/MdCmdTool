# -*- coding: utf-8 -*-
"""开发手册行号批量重算 v2（从 v1.6.0 备份重建，避免二次改写误差）。

三路对齐：
1. 符号引用（`symbol` L123 / | symbol | L123 |）→ 直接取源码中该符号的定义行；
   区间引用重写为「定义起始-定义结束」。
2. 其余裸行号（如表格第一列的「常量区 | L48 - L70」）→ 用源码新旧版本 diff 的行映射平移。
3. 都匹配不上的保持原样。
"""
import difflib
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")
SRC_BAK = SRC + ".v160.bak"
MAN = os.path.join(BASE, "开发手册.md")
MAN_BAK = MAN + ".v160.bak"

PAT_INLINE = re.compile(r"(`([A-Za-z_][A-Za-z0-9_.]*)`\s*[（(]?\s*)L(\d+)")
PAT_TABLE = re.compile(r"(\|\s*`?([A-Za-z_][A-Za-z0-9_.]*)`?\s*\|\s*)L(\d+)"
                       r"(\s*[–-]\s*L(\d+))?(\s*\|)")
NUM = re.compile(r"L(\d+)")


def read_text(path):
    with io.open(path, encoding="utf-8-sig") as fp:
        return fp.read().replace("\r\n", "\n")


def parse_source(lines):
    defs = {}
    for i, line in enumerate(lines, 1):
        m = re.match(r"^(\s*)(?:class|def)\s+([A-Za-z_]\w*)", line)
        if m:
            defs.setdefault(m.group(2), []).append([i, i, len(m.group(1))])
        m2 = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", line)
        if m2:
            defs.setdefault(m2.group(1), []).append([i, i, 0])
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
    return {name: (items[0][0], items[0][1]) for name, items in defs.items()}


def build_line_map(old_lines, new_lines):
    """旧行号 -> 新行号（1-based），仅覆盖能确定的 equal 块。"""
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    mapping = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                mapping[i1 + 1 + k] = j1 + 1 + k
    return mapping


def main():
    new_src = read_text(SRC).split("\n")
    old_src = read_text(SRC_BAK).split("\n")
    defs = parse_source(new_src)
    mapping = build_line_map(old_src, new_src)
    man_lines = read_text(MAN_BAK).split("\n")
    stats = {"symbol": 0, "diff": 0, "keep": 0}

    def look(name):
        for key in (name, name.split(".")[-1]):
            if key in defs:
                return defs[key]
        return None

    out = []
    for line in man_lines:
        handled = []          # 已被符号规则处理掉的数字 span

        def sub_inline(match):
            span = look(match.group(2))
            handled.append((match.start(3), match.end(3)))
            if not span:
                stats["keep"] += 1
                return match.group(0)
            stats["symbol"] += 1
            return "%sL%d" % (match.group(1), span[0])

        def sub_table(match):
            span = look(match.group(2))
            for group in (3, 5):
                if match.group(group) is not None:
                    handled.append((match.start(group), match.end(group)))
            if not span:
                stats["keep"] += 1
                return match.group(0)
            stats["symbol"] += 1
            if match.group(5) is not None:
                return "%sL%d-L%d%s" % (match.group(1), span[0], span[1], match.group(6))
            return "%sL%d%s" % (match.group(1), span[0], match.group(6))

        line = PAT_TABLE.sub(sub_table, line)
        line = PAT_INLINE.sub(sub_inline, line)

        # 剩余裸行号：走 diff 映射（从右往左替换，避免位移）
        pieces = []
        for match in NUM.finditer(line):
            start, end = match.span(1)
            if any(s <= start < e for s, e in handled):
                continue
            pieces.append((start, end, int(match.group(1))))
        for start, end, value in reversed(pieces):
            if value in mapping:
                line = line[:start] + str(mapping[value]) + line[end:]
                stats["diff"] += 1
            else:
                stats["keep"] += 1
        out.append(line)

    with io.open(MAN, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("\n".join(out))
    print("符号重算 %d 处 / diff 平移 %d 处 / 原样保留 %d 处"
          % (stats["symbol"], stats["diff"], stats["keep"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
