# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""块级解析器：移植自 JS 版 lex / lexList，单遍行扫描 + 有界递归。"""

from __future__ import annotations

import re

from md_core.inline import (
    MAX_COMMENT_LINES,
    MAX_DEPTH,
    InlineCtx,
    indent_of,
    parse_inline,
)
from md_core.nodes import CodeBlock, Heading, Hr, ListBlock, ListItem, Paragraph, Quote, Table

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*(.*?)[ \t]*$")
HR_RE = re.compile(r"^ {0,3}(?:[-*_][ \t]*){3,}$")
LIST_RE = re.compile(r"^ {0,3}([-+*]|\d{1,9}[.)])([ \t]+)(.*)$")
REFDEF_RE = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(\S+)(?:\s+[\"'(](.*?)[\"')])?\s*$")
ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*#*[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
TABLE_SEP_RE = re.compile(r"^[ \t]*\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
HTML_COMMENT_ONE_LINE_RE = re.compile(r"^\s*<!--.*?-->\s*$", re.DOTALL)
HTML_COMMENT_START_RE = re.compile(r"^\s*<!--")
HTML_COMMENT_END_RE = re.compile(r"-->\s*$")


def match_fence(line: str):
    m = FENCE_RE.match(line)
    if not m:
        return None
    marks, info = m.group(1), m.group(2)
    if marks[0] == "`" and "`" in info:
        return None  # 信息串不能含反引号
    return {"ch": marks[0], "len": len(marks), "lang": info.strip().split(" ")[0] if info.strip() else ""}


def is_hr(line: str) -> bool:
    return bool(HR_RE.match(line))


def match_list(line: str):
    m = LIST_RE.match(line)
    if not m:
        return None
    bullet, spaces, content = m.group(1), m.group(2), m.group(3)
    ordered = any(ch.isdigit() for ch in bullet)
    indent = len(line) - len(line.lstrip(" "))
    extra = len(spaces) - 1
    return {
        "indent": indent,
        "bullet": bullet,
        "ordered": ordered,
        "start": int(bullet[:-1]) if ordered else 1,
        "delim": bullet[-1],
        "content_indent": indent + len(bullet) + 1 + extra,
        "content": content,
    }


def match_refdef(line: str):
    m = REFDEF_RE.match(line)
    if not m:
        return None
    url = m.group(2)
    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1]
    return {"id": m.group(1).lower(), "url": url, "title": m.group(3) or ""}


def is_table_sep(line: str) -> bool:
    if "|" not in line:
        return False
    return bool(TABLE_SEP_RE.match(line))


def split_row(line: str) -> list[str]:
    """拆分表格行：尊重 \\| 转义（奇数反斜杠前缀的管道是字面量）。"""
    s = line.strip()
    s = s.removeprefix("|")
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells: list[str] = []
    cur: list[str] = []
    for k, c in enumerate(s):
        if c == "|":
            bs = 0
            p = k - 1
            while p >= 0 and s[p] == "\\":
                bs += 1
                p -= 1
            if bs % 2 == 1:
                cur.append("|")
                continue
            cells.append("".join(cur).strip())
            cur = []
            continue
        cur.append(c)
    cells.append("".join(cur).strip())
    return [c.replace("\\|", "|") for c in cells]


def strip_html_comment(line: str) -> str:
    return "" if HTML_COMMENT_ONE_LINE_RE.match(line) else line


def setext_level(line: str) -> int:
    m = SETEXT_RE.match(line)
    if not m:
        return 0
    return 1 if m.group(1)[0] == "=" else 2


def is_block_start(line: str) -> bool:
    return bool(
        match_fence(line)
        or re.match(r"^ {0,3}#{1,6}(?:[ \t]|$)", line)
        or re.match(r"^>", line)
        or is_hr(line)
        or match_list(line)
        or indent_of(line) >= 4
    )


def lex(src: str, ctx: InlineCtx, depth: int = 0) -> list:
    """块级解析：单遍行扫描；列表/引用内容递归调用（refs 全局共享）。"""
    lines = src.replace("\t", "    ").split("\n")
    blocks: list = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        # 多行 HTML 注释块（有上限，未闭合时不吞掉后续文档）
        if HTML_COMMENT_START_RE.match(line) and not HTML_COMMENT_END_RE.search(line):
            start = i
            while i < n and not HTML_COMMENT_END_RE.search(lines[i]) and i - start < MAX_COMMENT_LINES:
                i += 1
            if i < n and HTML_COMMENT_END_RE.search(lines[i]):
                i += 1
            else:
                i = start + 1
            continue
        if strip_html_comment(line) == "":
            i += 1
            continue

        # 链接引用定义
        refdef = match_refdef(line)
        if refdef:
            ctx.refs[refdef["id"]] = refdef
            i += 1
            continue

        # 围栏代码
        fence = match_fence(line)
        if fence:
            i += 1
            code: list[str] = []
            closed = False
            while i < n:
                f2 = match_fence(lines[i])
                if f2 and f2["ch"] == fence["ch"] and f2["len"] >= fence["len"]:
                    closed = True
                    break
                code.append(lines[i])
                i += 1
            if closed:
                i += 1
            blocks.append(CodeBlock(fence["lang"], "\n".join(code)))
            continue

        # 引用块
        if re.match(r"^>", line):
            quote_lines: list[str] = []
            while i < n and re.match(r"^>", lines[i]):
                quote_lines.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            if depth >= MAX_DEPTH:
                blocks.append(Paragraph(parse_inline("\n".join(quote_lines), ctx)))
            else:
                blocks.append(Quote(lex("\n".join(quote_lines), ctx, depth + 1)))
            continue

        # ATX 标题
        atx = ATX_RE.match(line)
        if atx:
            blocks.append(Heading(len(atx.group(1)), parse_inline(atx.group(2) or "", ctx)))
            i += 1
            continue

        # 分隔线
        if is_hr(line):
            blocks.append(Hr())
            i += 1
            continue

        # 列表
        lm = match_list(line)
        if lm:
            block, i = _lex_list(lines, i, lm, ctx, depth)
            blocks.append(block)
            continue

        # GFM 表格（表头 + 分隔行；不能打断段落）
        if "|" in line and i + 1 < n and is_table_sep(lines[i + 1]):
            head = split_row(line)
            align = []
            for cell in split_row(lines[i + 1]):
                t = cell.strip()
                if t.startswith(":") and t.endswith(":"):
                    align.append("center")
                elif t.endswith(":"):
                    align.append("right")
                elif t.startswith(":"):
                    align.append("left")
                else:
                    align.append("")
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1
            normalized = [[row[k] if k < len(row) else "" for k in range(len(head))] for row in rows]
            blocks.append(Table(head, normalized, align))
            continue

        # 缩进代码（4 空格）
        if indent_of(line) >= 4:
            code: list[str] = []
            while i < n:
                ln = lines[i]
                if not ln.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and indent_of(lines[j]) >= 4:
                        code.append("")
                        i += 1
                        continue
                    break
                if indent_of(ln) < 4:
                    break
                code.append(ln[4:])
                i += 1
            blocks.append(CodeBlock("", "\n".join(code)))
            continue

        # 段落（含 setext 标题转换）
        para: list[str] = []
        first_line = strip_html_comment(line)
        if first_line:
            para.append(first_line)
        i += 1
        heading = 0
        while i < n and lines[i].strip():
            level = setext_level(lines[i])
            if level:
                heading = level
                i += 1
                break
            if is_block_start(lines[i]):
                break
            stripped = strip_html_comment(lines[i])
            if stripped:
                para.append(stripped)
            i += 1
        inline = parse_inline("\n".join(para), ctx)
        if heading:
            blocks.append(Heading(heading, inline))
        elif para:
            blocks.append(Paragraph(inline))
    return blocks


def _lex_list(lines: list[str], i: int, marker: dict, ctx: InlineCtx, depth: int) -> tuple[ListBlock, int]:
    """列表解析：收集同标记类型的连续项，内容按内容缩进去缩进后递归。"""
    items: list[ListItem] = []
    tight = True
    n = len(lines)
    while i < n:
        m = match_list(lines[i])
        same_list = (
            m
            and m["indent"] == marker["indent"]
            and m["ordered"] == marker["ordered"]
            and (m["delim"] == marker["delim"] if m["ordered"] else m["bullet"] == marker["bullet"])
        )
        if not same_list:
            break
        i += 1
        content: list[str] = [m["content"]]
        pending_blank = False
        while i < n:
            ln = lines[i]
            if not ln.strip():
                pending_blank = True
                i += 1
                continue
            m2 = match_list(ln)
            if m2 and m2["indent"] == marker["indent"]:
                break  # 同级下一项 / 新列表
            if indent_of(ln) >= marker["content_indent"]:
                if pending_blank:
                    content.append("")
                    tight = False
                pending_blank = False
                content.append(ln[marker["content_indent"]:])
                i += 1
                continue
            if pending_blank:
                break
            content.append(ln)  # 惰性延续行
            i += 1
        if pending_blank:
            tight = False
        if depth >= MAX_DEPTH:
            items.append(ListItem([Paragraph(parse_inline("\n".join(content), ctx))]))
        else:
            items.append(ListItem(lex("\n".join(content), ctx, depth + 1)))
    return ListBlock(marker["ordered"], marker["start"], tight, items), i
