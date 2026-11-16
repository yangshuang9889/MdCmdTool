# -*- coding: utf-8 -*-
"""开发手册行号批量重算 v4（v1.8.1 → v1.9.0，源自逆向还原的 v1.8.1 源码）。

三路对齐（沿用 v181 策略）：
1. 符号引用（`symbol` L123 / | symbol | L123 |）→ 取源码中该符号的定义行，
   区间引用重写为「定义起始-定义结束」；
2. 其余裸行号 → 用新旧源码 diff 的行映射平移；
3. 都匹配不上的保持原样。
"""
import difflib
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "爽哥MD命令生成工具.py")
TEMP = r"C:\Users\Administrator\AppData\Roaming\Tencent\Marvis\User\oAN1i2Siy4T87X5Sx6qEfhnB8hbI\workspace\conv_09820cbd9e7a4d079dc011089c84a476\temp"
SRC_BAK = os.path.join(TEMP, "src_v181_reconstructed.py")
MAN = os.path.join(BASE, "开发手册.md")
MAN_BAK = os.path.join(TEMP, "man_before_v190.md")

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

    MARK = "\u0001%d\u0001"

    out = []
    for line in man_lines:
        def sub_inline(match):
            span = look(match.group(2))
            if not span:
                stats["keep"] += 1
                return match.group(0)
            stats["symbol"] += 1
            # 用哨兵占位，避免符号结果被后续 diff 平移二次改写
            return "%sL%s" % (match.group(1), MARK % span[0])

        def sub_table(match):
            span = look(match.group(2))
            if not span:
                stats["keep"] += 1
                return match.group(0)
            stats["symbol"] += 1
            if match.group(5) is not None:
                return "%sL%s-L%s%s" % (match.group(1), MARK % span[0],
                                        MARK % span[1], match.group(6))
            return "%sL%s%s" % (match.group(1), MARK % span[0], match.group(6))

        line = PAT_TABLE.sub(sub_table, line)
        line = PAT_INLINE.sub(sub_inline, line)

        # 未被符号规则处理的裸行号：走 diff 映射（从右往左替换，避免位移）
        pieces = [(m.span(1), int(m.group(1))) for m in NUM.finditer(line)]
        for (start, end), value in reversed(pieces):
            if value in mapping:
                line = line[:start] + str(mapping[value]) + line[end:]
                stats["diff"] += 1
            else:
                stats["keep"] += 1
        # 还原符号行号
        line = re.sub("\u0001(\\d+)\u0001", r"\1", line)
        out.append(line)

    with io.open(MAN, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("\n".join(out))
    print("符号重算 %d 处 / diff 平移 %d 处 / 原样保留 %d 处"
          % (stats["symbol"], stats["diff"], stats["keep"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
