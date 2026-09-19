"""文档节点定义：行内节点与块级节点（与 JS 版 typedef 一一对应）。"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------- 行内节点 ----------------

@dataclass
class TextNode:
    value: str


@dataclass
class Softbreak:
    pass


@dataclass
class Br:
    pass


@dataclass
class CodeNode:
    value: str


@dataclass
class Emphasis:
    """strong / em / del / highlight 四合一：kind 区分渲染样式。"""

    kind: str  # 'strong' | 'em' | 'del' | 'highlight'
    children: list


@dataclass
class Link:
    href: str
    children: list
    title: str = ""


@dataclass
class Image:
    href: str
    alt: str = ""
    title: str = ""


# ---------------- 块级节点 ----------------

@dataclass
class Heading:
    level: int
    inline: list


@dataclass
class Paragraph:
    inline: list


@dataclass
class CodeBlock:
    lang: str
    code: str


@dataclass
class Quote:
    blocks: list


@dataclass
class ListItem:
    blocks: list


@dataclass
class ListBlock:
    ordered: bool
    start: int
    tight: bool
    items: list = field(default_factory=list)


@dataclass
class Table:
    head: list
    rows: list
    align: list


@dataclass
class Hr:
    pass
