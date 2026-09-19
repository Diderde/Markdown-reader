# SPDX-License-Identifier: GPL-2.0-or-later
"""渲染流水线：清洗 → 引用预扫描 → 块级 lex → 统计与计时。"""

from __future__ import annotations

from dataclasses import dataclass, field

from md_core.blocks import lex, match_refdef
from md_core.extensions import REGISTRY
from md_core.inline import InlineCtx


@dataclass
class RenderStats:
    chars: int = 0
    blocks: int = 0
    nodes: int = 0
    lex_ms: float = 0.0
    render_ms: float = 0.0


@dataclass
class PipelineResult:
    blocks: list
    stats: RenderStats = field(default_factory=RenderStats)


def clean_source(src: str) -> str:
    """去 BOM、统一换行（与 JS 版一致）。"""
    return str(src).replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")


def run_pipeline(src: str) -> PipelineResult:
    """完整解析：返回块级树 + 统计。渲染（Flet 控件构建）由 UI 层负责。"""
    import time

    clean = clean_source(src)
    stats = RenderStats(chars=len(clean))
    ctx = InlineCtx(refs={}, exts=list(REGISTRY))

    # 预扫描：引用定义全局生效（定义可出现在使用之后）
    for line in clean.replace("\t", "    ").split("\n"):
        refdef = match_refdef(line)
        if refdef:
            ctx.refs[refdef["id"]] = refdef

    t0 = time.perf_counter()
    blocks = lex(clean, ctx)
    t1 = time.perf_counter()
    stats.lex_ms = (t1 - t0) * 1000
    stats.blocks = _count_blocks(blocks)
    stats.nodes = _count_nodes(blocks)
    stats.render_ms = 0.0  # 由 UI 层渲染计时后回填
    return PipelineResult(blocks=blocks, stats=stats)


def _count_blocks(blocks: list) -> int:
    total = 0
    stack = list(blocks)
    while stack:
        b = stack.pop()
        total += 1
        if hasattr(b, "blocks") and getattr(b, "blocks", None):
            stack.extend(b.blocks)
        if hasattr(b, "items"):
            for item in b.items:
                stack.extend(item.blocks)
    return total


def _count_nodes(blocks: list) -> int:
    """统计行内节点数（含嵌套 children）。"""
    total = 0

    def walk_inlines(nodes: list) -> None:
        nonlocal total
        for nd in nodes:
            total += 1
            children = getattr(nd, "children", None)
            if children:
                walk_inlines(children)

    def walk_blocks(bs: list) -> None:
        nonlocal total
        for b in bs:
            if getattr(b, "inline", None):
                walk_inlines(b.inline)
            if getattr(b, "blocks", None):
                walk_blocks(b.blocks)
            if hasattr(b, "items"):
                for item in b.items:
                    walk_blocks(item.blocks)

    walk_blocks(blocks)
    return total


def decode_text(data: bytes) -> str:
    """解码文本：优先 UTF-8；出现无法解码字节时回退 GB18030（GBK 超集，修复点）。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gb18030")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")
