# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""行内扩展注册表：与 JS 版 MdReader.use({ marker, parse }) 等价。

内置演示扩展：==高亮==。
修复点：原 JS 版闭合扫描用未 bounded 的 indexOf；这里限定 MAX_EM_SCAN 窗口，
超长未闭合输入退化为有界线性，不再可能出现极端扫描。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from md_core.inline import MAX_EM_SCAN, InlineCtx
from md_core.nodes import Emphasis


@dataclass
class InlineExtension:
    marker: str
    parse: Callable


@dataclass
class _Hit:
    node: object
    next: int


def _highlight_parse(src: str, i: int, ctx: InlineCtx):
    close = src.find("==", i + 2, i + 2 + MAX_EM_SCAN)  # 修复点：有界闭合扫描
    if close == -1:
        return None
    inner = src[i + 2:close]
    if not inner.strip():
        return None
    return _Hit(Emphasis("highlight", parse_inline_safe(inner, ctx)), close + 2)


def parse_inline_safe(src: str, ctx: InlineCtx) -> list:
    from md_core.inline import parse_inline

    return parse_inline(src, ctx)


# 注册表：与 JS 版一致，模块级单例
REGISTRY: list[InlineExtension] = [InlineExtension("==", _highlight_parse)]


def use(ext: InlineExtension) -> None:
    """注册自定义行内扩展（marker 必须非空、parse 必须可调用）。"""
    if ext and isinstance(ext.marker, str) and ext.marker and callable(ext.parse):
        REGISTRY.append(ext)
