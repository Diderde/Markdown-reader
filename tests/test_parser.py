# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""md_core 解析核心的单元测试（不依赖 Flet，不访问网络）。"""

from __future__ import annotations

import time

from md_core.blocks import lex, match_list, match_refdef, split_row
from md_core.extensions import REGISTRY
from md_core.highlight import resolve_lang, tokenize_code
from md_core.inline import InlineCtx, parse_inline
from md_core.nodes import (
    CodeBlock,
    CodeNode,
    Emphasis,
    Heading,
    Image,
    Link,
    ListBlock,
    Quote,
    Table,
    TextNode,
)
from md_core.pipeline import clean_source, decode_text, run_pipeline


def make_ctx() -> InlineCtx:
    return InlineCtx(refs={}, exts=list(REGISTRY))


def texts(nodes) -> list[str]:
    return [n.value for n in nodes if isinstance(n, TextNode)]


class TestInline:
    def test_emphasis_nested(self):
        nodes = parse_inline("*斜体中包含 **加粗** 的嵌套写法。*", make_ctx())
        assert len(nodes) == 1 and isinstance(nodes[0], Emphasis) and nodes[0].kind == "em"
        children = nodes[0].children
        assert texts(children) == ["斜体中包含 ", " 的嵌套写法。"]
        inner = [c for c in children if isinstance(c, Emphasis)]
        assert len(inner) == 1 and inner[0].kind == "strong"
        assert texts(inner[0].children) == ["加粗"]

    def test_strike_and_highlight(self):
        nodes = parse_inline("~~删除~~ ==高亮==", make_ctx())
        assert [type(n).__name__ for n in nodes] == ["Emphasis", "TextNode", "Emphasis"]
        assert nodes[0].kind == "del" and nodes[2].kind == "highlight"

    def test_code_span_strips_spaces(self):
        nodes = parse_inline("` x `", make_ctx())
        assert isinstance(nodes[0], CodeNode) and nodes[0].value == "x"

    def test_unclosed_code_is_literal(self):
        nodes = parse_inline("`abc", make_ctx())
        assert texts(nodes) == ["`abc"]

    def test_autolink_and_mail(self):
        nodes = parse_inline("<https://example.com> <a@b.com>", make_ctx())
        assert [type(n).__name__ for n in nodes] == ["Link", "TextNode", "Link"]
        assert nodes[0].href == "https://example.com"
        assert nodes[2].href == "mailto:a@b.com"

    def test_inline_link_with_title(self):
        nodes = parse_inline('[官网](https://x.com "标题")', make_ctx())
        assert isinstance(nodes[0], Link)
        assert nodes[0].href == "https://x.com" and nodes[0].title == "标题"

    def test_reference_link_after_use(self):
        ctx = make_ctx()
        nodes = parse_inline("[ref][id]", ctx)
        assert texts(nodes) == ["[ref][id]"]  # 定义未出现前是字面量
        ctx.refs["id"] = {"url": "https://r.com", "title": ""}
        nodes = parse_inline("[ref][id]", ctx)
        assert isinstance(nodes[0], Link) and nodes[0].href == "https://r.com"

    def test_escape_asterisk(self):
        nodes = parse_inline("\\*不是斜体\\*", make_ctx())
        assert texts(nodes) == ["*不是斜体*"]

    def test_hard_break(self):
        nodes = parse_inline("a  \nb", make_ctx())
        assert [type(n).__name__ for n in nodes] == ["TextNode", "Br", "TextNode"]

    def test_softbreak(self):
        nodes = parse_inline("a\nb", make_ctx())
        assert [type(n).__name__ for n in nodes] == ["TextNode", "Softbreak", "TextNode"]

    def test_lone_bang_literal(self):
        nodes = parse_inline("哇!真棒", make_ctx())
        assert texts(nodes) == ["哇!真棒"]

    def test_cjk_intraword_underscore_is_literal(self):
        """修复验证：原 JS 版用 ASCII \\w，中文语境 _ 会误判为可开强调。"""
        nodes = parse_inline("中文_下划线_中文", make_ctx())
        assert texts(nodes) == ["中文_下划线_中文"]

    def test_emphasis_budget_no_hang(self):
        src = "*" * 5000
        parse_inline(src, make_ctx())  # 正常返回即通过


class TestBlocks:
    def test_atx_heading(self):
        b = block_of("### 标题")
        assert isinstance(b, Heading) and b.level == 3

    def test_setext_heading(self):
        b = block_of("次级\n---")
        assert isinstance(b, Heading) and b.level == 2

    def test_fence_code_with_lang(self):
        b = block_of("```python\nprint(1)\n```")
        assert isinstance(b, CodeBlock) and b.lang == "python" and b.code == "print(1)"

    def test_tilde_fence(self):
        b = block_of("~~~\ncode\n~~~")
        assert isinstance(b, CodeBlock) and b.code == "code"

    def test_unclosed_fence_consumes_to_end(self):
        blocks = lex("```js\nlet a = 1;\n后面也算代码", make_ctx())
        assert len(blocks) == 1 and isinstance(blocks[0], CodeBlock)

    def test_quote(self):
        b = block_of("> 引用\n> 多行")
        assert isinstance(b, Quote)

    def test_task_list(self):
        blocks = lex("- [x] 完成\n- [ ] 未完成", make_ctx())
        assert isinstance(blocks[0], ListBlock) and len(blocks[0].items) == 2

    def test_nested_list(self):
        blocks = lex("- 外层\n  - 内层", make_ctx())
        outer = blocks[0]
        assert isinstance(outer, ListBlock)
        inner = [b for b in outer.items[0].blocks if isinstance(b, ListBlock)]
        assert len(inner) == 1

    def test_table_alignment_and_escape(self):
        b = block_of("| 左 | 中 | 右 |\n| :--- | :---: | ---: |\n| a \\| b | c | d |")
        assert isinstance(b, Table)
        assert b.align == ["left", "center", "right"]
        assert b.rows[0] == ["a | b", "c", "d"]

    def test_table_row_padding(self):
        b = block_of("| a | b |\n| --- | --- |\n| 1 |")
        assert b.rows[0] == ["1", ""]

    def test_split_row_escaped_pipe(self):
        assert split_row("| a \\| b | c |") == ["a | b", "c"]

    def test_link_refdef(self):
        assert match_refdef('[id]: https://x.com "标题"') == {
            "id": "id",
            "url": "https://x.com",
            "title": "标题",
        }

    def test_list_match(self):
        m = match_list("- 项目")
        assert m["ordered"] is False and m["content"] == "项目"
        m2 = match_list("2. 第二")
        assert m2["ordered"] is True and m2["start"] == 2

    def test_deep_quotes_flatten_not_crash(self):
        src = "\n".join(["> " * k + "深" for k in range(1, 200)])
        blocks = lex(src, make_ctx())  # MAX_DEPTH 之上展平为段落，不爆栈
        assert blocks


def block_of(src: str):
    blocks = lex(src, make_ctx())
    assert len(blocks) == 1
    return blocks[0]


class TestHighlight:
    def test_alias(self):
        assert resolve_lang("py") == "python"
        assert resolve_lang("md") == ""

    def test_python_tokens(self):
        tokens = tokenize_code("def f():  # 注释\n    return 42", "python")
        classes = [c for c, _ in tokens]
        assert "kw" in classes and "com" in classes and "num" in classes

    def test_unknown_lang_returns_plain(self):
        assert tokenize_code("abc", "") == [("", "abc")]


class TestPipeline:
    def test_clean_source(self):
        assert clean_source("﻿a\r\nb\rc") == "a\nb\nc"  # BOM 仅在开头移除

    def test_run_pipeline_stats(self):
        result = run_pipeline("# 标题\n\n段落 **加粗**。")
        assert result.stats.blocks >= 2
        assert result.stats.nodes >= 2
        assert result.stats.chars == len("# 标题\n\n段落 **加粗**。")

    def test_decode_utf8_and_gbk(self):
        assert decode_text("中文".encode()) == "中文"
        assert decode_text("中文".encode("gb18030")) == "中文"  # GBK 超集回退

    def test_image_data_uri_preserved(self):
        result = run_pipeline("![占位](data:image/png;base64,iVBORw0KGgo=)")
        img = result.blocks[0].inline[0]
        assert isinstance(img, Image) and img.href.startswith("data:image/png")


class TestBoundedness:
    def test_highlight_ext_bounded_close(self):
        """修复验证：== 无闭合时旧实现会全串 indexOf，长输入不再退化为 O(n)。"""
        src = "==a" + "b" * 100000
        nodes = parse_inline(src, make_ctx())  # 应快速返回且 == 为字面量
        assert "".join(texts(nodes)).startswith("==a")

    def test_emphasis_window_bounded(self):
        src = "*" + "a" * 200000
        parse_inline(src, make_ctx())  # 有界窗口，正常返回

    def test_long_tilde_run_bounded(self):
        """修复验证：长 `~` 串下旧实现每消费 4 字符就重扫剩余整段（20k 字符约 10s）。"""
        src = "a" + "~" * 20000
        start = time.perf_counter()
        nodes = parse_inline(src, make_ctx())
        assert time.perf_counter() - start < 2.0   # 修复后约 25ms，留足 CI 容差
        assert len(nodes) == 5001                  # 语义不变：每 4 个 ~ 生成一个删除线节点

    def test_unclosed_brackets_bounded(self):
        """修复验证：`[` 风暴下旧实现逐字符扫描 2048 窗口（100k 字符约 6s）。"""
        src = "[" * 100000
        start = time.perf_counter()
        nodes = parse_inline(src, make_ctx())
        assert time.perf_counter() - start < 2.0   # 修复后约 60ms
        assert "".join(texts(nodes)) == src        # 未闭合方括号保持字面量

    def test_scan_budget_degrades_marker_storm(self):
        """修复验证：标记密集输入由文档级扫描预算兜底（旧实现 9.9 万字符超 60s）。"""
        ctx = make_ctx()
        start = time.perf_counter()
        parse_inline("*a " * 20000, ctx)
        assert time.perf_counter() - start < 3.0
        assert ctx.scan_left <= 0                  # 预算耗尽 → 剩余内容按纯文本降级

    def test_scan_budget_untouched_for_normal_text(self):
        """反向守护：正常文档不得触发降级（否则等于静默丢失格式）。"""
        ctx = make_ctx()
        parse_inline("正常段落 **加粗** 与 `代码`、[链接](https://e.example)。\n\n第二段。", ctx)
        assert ctx.scan_left > 0
