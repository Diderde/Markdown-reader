# SPDX-License-Identifier: GPL-2.0-or-later
"""行内解析器：移植自 JS 版 parseInline，含 flanking 判定与“三的倍数”规则。

相对原版的修复：
- `_` 的 intra-word 判定使用 Unicode 字母数字（原 JS 用 ASCII ``\\w``），
  修正了中文语境下 ``中文_斜体_中文`` 被误判为斜体的问题（CommonMark 语义）；
- 扩展语法（==高亮==）的闭合扫描改为有界窗口，原版是未 bounded 的 indexOf。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from md_core.nodes import Br, CodeNode, Emphasis, Image, Link, Softbreak, TextNode

# ---------------- 防御性上限（防病态输入的二次方爆炸 / 递归爆栈） ----------------

MAX_SCAN = 2048         # 链接 / 代码 span / 链接目标的前向扫描窗口
MAX_EM_SCAN = 1024      # 强调 / 删除线的闭合扫描窗口
MAX_AUTOLINK = 512      # 自动链接最大长度
MAX_DEPTH = 64          # 引用 / 列表递归深度上限
MAX_COMMENT_LINES = 50  # 未闭合 HTML 注释最多吞掉的行数

# ---------------- 字符工具 ----------------

# ASCII 标点（与原版保持一致的轻量近似；CJK 标点视为普通字符）
PUNCT_RE = re.compile(r"[\u0021-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E]")
# 修复点：原 JS 用 ASCII \w，这里用 Unicode 字母数字（更符合 CommonMark 语义）
WORD_RE = re.compile(r"[^\W_]", re.UNICODE)  # 字母或数字（不含下划线）


def is_whitespace(c: str) -> bool:
    return bool(c) and c.isspace()


def is_word_char(c: str) -> bool:
    return bool(c) and bool(WORD_RE.match(c))


def is_punct(c: str) -> bool:
    return bool(c) and bool(PUNCT_RE.match(c))


def is_left_flanking(before: str, after: str) -> bool:
    if not after or is_whitespace(after):
        return False
    if is_punct(after):
        return not before or is_whitespace(before)
    return True


def is_right_flanking(before: str, after: str) -> bool:
    if not before:
        return True
    if is_whitespace(before):
        return False
    if is_punct(before):
        return bool(after) and is_whitespace(after)
    return True


def count_run(s: str, i: int, ch: str) -> int:
    n = 0
    while i + n < len(s) and s[i + n] == ch:
        n += 1
    return n


def indent_of(line: str) -> int:
    n = 0
    while n < len(line) and line[n] == " ":
        n += 1
    return n


# ---------------- 有界扫描 ----------------

SPECIALS = set("`\\*_[!<~\n")
ESCAPABLES = set('\\`!"#$%&\'()*+,-./:;<=>?@[\\]^_{|}~')


def next_special(src: str, from_: int, limit: int) -> int:
    """在 [from_, limit) 内找下一个特殊字符位置；找不到返回 -1。"""
    for k in range(from_, min(len(src), limit)):
        if src[k] in SPECIALS:
            return k
    return -1


def index_of_capped(src: str, ch: str, from_: int, cap: int) -> int:
    """在 [from_, from_+cap) 内查找字符 ch；有界，避免全串 O(n) 扫描。"""
    end = min(len(src), from_ + cap)
    for k in range(from_, end):
        if src[k] == ch:
            return k
    return -1


def find_closing_run(src: str, from_: int, run: int, limit: int) -> int:
    """从 from_ 起查找恰好 run 个反引号的闭合 run；找不到返回 -1。"""
    end = min(len(src), limit)
    j = from_
    while j < end:
        if src[j] != "`":
            j += 1
            continue
        r = count_run(src, j, "`")
        if r == run:
            return j
        j += r
    return -1


# ---------------- 行内语法 ----------------

@dataclass
class Hit:
    """一次成功消费：node 为生成的节点，next 为继续扫描的位置。"""

    node: object
    next: int


@dataclass
class InlineCtx:
    refs: dict            # 链接引用定义 id -> {url, title}
    exts: list            # 自定义行内扩展（见 extensions 注册）


def try_emphasis(src: str, i: int, ctx: InlineCtx) -> Hit | None:
    ch = src[i]
    run = count_run(src, i, ch)
    if run >= 2:
        r2 = _try_emphasis_len(src, i, ch, run, 2, ctx)
        if r2:
            return r2
    return _try_emphasis_len(src, i, ch, 1, 1, ctx)


def _try_emphasis_len(src: str, i: int, ch: str, run: int, length: int, ctx: InlineCtx) -> Hit | None:
    before = src[i - 1] if i > 0 else ""
    after = src[i + run] if i + run < len(src) else ""
    if not after or is_whitespace(after):
        return None                       # opener 后不能是空白
    if ch == "_" and before and is_word_char(before):
        return None                       # 修复点：Unicode intra-word 判定
    if not is_left_flanking(before, after):
        return None
    opener_can_close = is_right_flanking(before, after)
    limit = min(len(src), i + MAX_EM_SCAN)

    j = i + run
    while j < limit:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":                      # 跳过代码 span
            r0 = count_run(src, j, "`")
            close = find_closing_run(src, j + r0, r0, limit)
            if close == -1:
                return None
            j = close + r0
            continue
        if c == ch:
            r = count_run(src, j, ch)
            c_before = src[j - 1]
            c_after = src[j + r] if j + r < len(src) else ""
            closer_ok = (
                j > i + run               # 修复点：以完整 run 为界拒绝空内容（原版用消费长度）
                and not is_whitespace(c_before)
                and not (ch == "_" and c_after and is_word_char(c_after))
                and is_right_flanking(c_before, c_after)
            )
            if closer_ok:
                closer_can_open = is_left_flanking(c_before, c_after)
                one_flex = opener_can_close or closer_can_open
                total = run + r
                three_blocked = one_flex and total % 3 == 0 and not (run % 3 == 0 and r % 3 == 0)
                if not three_blocked:
                    inner = src[i + length:j]
                    kind = "strong" if length == 2 else "em"
                    return Hit(Emphasis(kind, parse_inline(inner, ctx)), j + min(r, length))
            j += r
            continue
        j += 1
    return None


def try_code_span(src: str, i: int) -> Hit | None:
    run = count_run(src, i, "`")
    close = find_closing_run(src, i + run, run, i + run + MAX_SCAN)
    if close == -1:
        return None
    content = src[i + run:close]
    if len(content) >= 2 and content[0] == " " and content[-1] == " " and content.strip():
        content = content[1:-1]
    return Hit(CodeNode(content), close + run)


def try_strike(src: str, i: int, ctx: InlineCtx) -> Hit | None:
    run = count_run(src, i, "~")
    if run < 2:
        return None
    after = src[i + 2] if i + 2 < len(src) else ""
    if not after or is_whitespace(after):
        return None
    limit = min(len(src), i + MAX_EM_SCAN)
    j = i + 2
    while j < limit:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            r0 = count_run(src, j, "`")
            close = find_closing_run(src, j + r0, r0, limit)
            if close == -1:
                return None
            j = close + r0
            continue
        if c == "~":
            r = count_run(src, j, "~")
            if r >= 2 and not is_whitespace(src[j - 1]):
                return Hit(Emphasis("del", parse_inline(src[i + 2:j], ctx)), j + 2)
            j += r
            continue
        j += 1
    return None


AUTOLINK_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9+.\-]{1,31}:[^<>\s]*)>")
AUTOMAIL_RE = re.compile(r"<([^<>\s@]+@[^<>\s@]+)>")


def try_autolink(src: str, i: int) -> Hit | None:
    if src[i] != "<":
        return None
    if index_of_capped(src, ">", i + 1, MAX_AUTOLINK) == -1:
        return None
    m = AUTOLINK_RE.match(src, i)
    if m:
        return Hit(Link(m.group(1), [TextNode(m.group(1))]), m.end())
    e = AUTOMAIL_RE.match(src, i)
    if e:
        return Hit(Link("mailto:" + e.group(1), [TextNode(e.group(1))]), e.end())
    return None


def parse_link_dest(src: str, open_: int) -> tuple[str, str, int] | None:
    """解析 (url "title") 形式的链接目标；返回 (url, title, next)。"""
    depth = 1
    i = open_ + 1
    in_quotes = False
    quote_ch = ""
    limit = min(len(src), open_ + 1 + MAX_SCAN)
    while i < limit:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if in_quotes:
            if c == quote_ch:
                in_quotes = False
            i += 1
            continue
        if c in "\"'":
            in_quotes = True
            quote_ch = c
            i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0 or i >= len(src):
        return None
    inner = src[open_ + 1:i]
    trimmed = inner.strip()
    if not trimmed:
        return "", "", i + 1
    m = re.match(r"^(\S+?)(?:\s+[\"'](.*?)[\"'])?\s*$", inner, re.DOTALL)
    if not m:
        return None
    url = m.group(1)
    if url.startswith("<") and url.endswith(">"):
        url = url[1:-1]
    return url, m.group(2) or "", i + 1


def try_link(src: str, i: int, ctx: InlineCtx, image: bool) -> Hit | None:
    open_ = i + 1 if image else i
    if open_ >= len(src) or src[open_] != "[":
        return None
    j = index_of_capped(src, "]", open_ + 1, MAX_SCAN)
    if j == -1:
        return None
    label = src[open_ + 1:j]
    k = j + 1
    node = None
    nxt = -1

    def make(href: str, title: str):
        if image:
            return Image(href, alt=label, title=title)
        return Link(href, parse_inline(label, ctx), title=title)

    nxt_after_bracket = k
    if k < len(src) and src[k] == "(":
        r = parse_link_dest(src, k)
        if r is not None:
            node = make(r[0], r[1])
            nxt = r[2]
    elif k < len(src) and src[k] == "[":
        end = index_of_capped(src, "]", k + 1, MAX_SCAN)
        if end != -1:
            ref_id = (src[k + 1:end] or label).lower()
            ref = ctx.refs.get(ref_id)
            if ref:
                node = make(ref["url"], ref["title"])
                nxt = end + 1
    if node is None:
        ref = ctx.refs.get(label.lower())  # 快捷引用 [text]
        if ref:
            node = make(ref["url"], ref["title"])
            nxt = nxt_after_bracket
    return Hit(node, nxt) if node is not None else None


def parse_inline(src: str, ctx: InlineCtx) -> list:
    """行内解析主循环：单遍扫描 + 文本段跳跃 + 迭代预算防死循环。"""
    parts: list = []
    text: list[str] = []

    def flush():
        if text:
            parts.append(TextNode("".join(text)))
            text.clear()

    # 预计算各扩展标记的全部出现位置（一次 O(n)），游标跳跃避免 O(n²)
    ext_hits = [[p for p in _find_all(src, ext.marker)] for ext in ctx.exts]
    ext_cursor = [0] * len(ctx.exts)

    budget = len(src) * 2 + 64
    iterations = 0
    i = 0
    n = len(src)
    while i < n:
        iterations += 1
        if iterations > budget:
            raise RuntimeError("行内解析超出迭代预算（疑似未消费字符路径）")
        c = src[i]

        # 1) 扩展语法（先于内建规则）
        hit = None
        for ext in ctx.exts:
            if src.startswith(ext.marker, i):
                r = ext.parse(src, i, ctx)
                if r is not None and r.next > i:
                    hit = r
                    break
        if hit is not None:
            flush()
            parts.append(hit.node)
            i = hit.next
            continue

        # 2) 反斜杠转义（含硬换行）
        if c == "\\":
            nxt = src[i + 1] if i + 1 < n else None
            if nxt is None:
                text.append("\\")
                i += 1
            elif nxt == "\n":
                flush()
                parts.append(Br())
                i += 2
            elif nxt in ESCAPABLES:
                text.append(nxt)
                i += 2
            else:
                text.append("\\")
                i += 1
            continue

        # 3) 换行：行尾两空格 → 硬换行（消费换行符）；否则软换行
        if c == "\n":
            if text and text[-1].endswith("  "):
                text[-1] = text[-1].rstrip(" ")
                flush()
                parts.append(Br())
                i += 1
                continue
            # 软换行：丢弃行尾空白
            while text and not text[-1]:
                text.pop()
            if text:
                text[-1] = text[-1].rstrip(" ")
            flush()
            parts.append(Softbreak())
            i += 1
            continue

        # 4) 内建行内语法
        if c == "`":
            r = try_code_span(src, i)
            if r:
                flush()
                parts.append(r.node)
                i = r.next
                continue
            run = count_run(src, i, "`")
            text.append(src[i:i + run])
            i += run
            continue
        if c in "*_":
            r = try_emphasis(src, i, ctx)
            if r:
                flush()
                parts.append(r.node)
                i = r.next
                continue
            run = count_run(src, i, c)
            text.append(src[i:i + run])
            i += run
            continue
        if c == "~":
            r = try_strike(src, i, ctx)
            if r:
                flush()
                parts.append(r.node)
                i = r.next
                continue
            run = count_run(src, i, "~")
            text.append(src[i:i + run])
            i += run
            continue
        if c == "<":
            r = try_autolink(src, i)
            if r:
                flush()
                parts.append(r.node)
                i = r.next
                continue
            text.append(c)
            i += 1
            continue
        if c == "!":
            if i + 1 < n and src[i + 1] == "[":
                r = try_link(src, i, ctx, image=True)
                if r:
                    flush()
                    parts.append(r.node)
                    i = r.next
                    continue
            text.append(c)
            i += 1
            continue
        if c == "[":
            r = try_link(src, i, ctx, image=False)
            if r:
                flush()
                parts.append(r.node)
                i = r.next
                continue
            text.append(c)
            i += 1
            continue

        # 5) 普通文本段：跳到下一个特殊字符 / 扩展标记
        end = n
        for k in range(len(ctx.exts)):
            hits = ext_hits[k]
            while ext_cursor[k] < len(hits) and hits[ext_cursor[k]] < i:
                ext_cursor[k] += 1
            if ext_cursor[k] < len(hits) and hits[ext_cursor[k]] < end:
                end = hits[ext_cursor[k]]
        ns = next_special(src, i, end)
        if ns != -1 and ns < end:
            end = ns
        if end == i:
            text.append(c)
            i += 1
            continue
        text.append(src[i:end])
        i = end

    flush()
    return parts


def _find_all(src: str, marker: str):
    if not marker:
        return
    p = src.find(marker)
    while p != -1:
        yield p
        p = src.find(marker, p + 1)
