"""渲染器：把块级/行内节点树转换为 Flet 控件（深色主题，配色对齐 HTML 版）。"""

from __future__ import annotations

import base64
import re

import flet as ft

from md_core.highlight import resolve_lang, tokenize_code
from md_core.nodes import (
    Br,
    CodeBlock,
    CodeNode,
    Emphasis,
    Heading,
    Hr,
    Image,
    Link,
    ListBlock,
    Paragraph,
    Quote,
    Softbreak,
    Table,
    TextNode,
)

# 配色（对齐 HTML 版 :root 变量与 .md 规则）
FG = "#d5d9e0"
MUTED = "#8b93a3"
ACCENT = "#4f8cff"
BORDER = "#262b36"
CODE_BG = "#10131a"
CODE_FG = "#c8d0dd"
INLINE_CODE_BG = "#232c3d"
QUOTE_BG = "#16203a"
QUOTE_FG = "#b9c0cd"
MARK_BG = "#6b5b00"
MARK_FG = "#ffe08a"
TOKEN_COLORS = {
    "kw": "#c792ea",
    "str": "#c3e88d",
    "num": "#f78c6c",
    "com": "#63727e",
    "tag": "#82aaff",
    "prop": "#89ddff",
}
MONO = "Consolas"
HEADING_SIZES = {1: 26, 2: 21, 3: 18, 4: 16, 5: 14.5, 6: 13.5}
MAX_IMAGE_WIDTH = 560


def safe_url(u: str, kind: str) -> str:
    """URL 协议白名单：链接仅 http/https/mailto 与相对地址；图片另允许 data:image。"""
    if not u:
        return ""
    m = _SCHEME_RE.match(u)
    if not m:
        return u
    scheme = m.group(1).lower()
    if scheme in ("http", "https", "mailto"):
        return u
    if kind == "img" and scheme == "data" and u.startswith("data:image/"):
        return u
    return ""


_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


def render_inline_spans(nodes: list) -> list[ft.TextSpan]:
    """行内节点 → TextSpan 列表（链接用 url 参数，点击由 Flet 原生打开）。

    注意 Flet 1.0 的 TextSpan 字段序为 (text, style, spans, url, ...)：
    子级列表必须用 spans= 关键字传递，位置传参会落入 text 字段渲染成 repr。
    """
    spans: list[ft.TextSpan] = []
    for nd in nodes:
        if isinstance(nd, TextNode):
            spans.append(ft.TextSpan(text=nd.value))
        elif isinstance(nd, Softbreak):
            spans.append(ft.TextSpan(text=" "))
        elif isinstance(nd, Br):
            spans.append(ft.TextSpan(text="\n"))
        elif isinstance(nd, CodeNode):
            spans.append(
                ft.TextSpan(
                    text=nd.value,
                    style=ft.TextStyle(font_family=MONO, bgcolor=INLINE_CODE_BG, color=FG),
                )
            )
        elif isinstance(nd, Emphasis):
            spans.append(
                ft.TextSpan(
                    spans=render_inline_spans(nd.children),
                    style=_emphasis_style(nd.kind),
                )
            )
        elif isinstance(nd, Link):
            url = safe_url(nd.href, "link")
            if not url:
                spans.extend(render_inline_spans(nd.children))
                continue
            spans.append(
                ft.TextSpan(
                    spans=render_inline_spans(nd.children),
                    style=ft.TextStyle(color=ACCENT, decoration=ft.TextDecoration.NONE),
                    url=url,
                    tooltip=nd.title or None,
                )
            )
        elif isinstance(nd, Image):
            # 图片在行内流中由 render_flow 处理；此处不应到达
            spans.append(ft.TextSpan(text=f"[{nd.alt}]"))
    return spans


def _emphasis_style(kind: str) -> ft.TextStyle:
    if kind == "strong":
        return ft.TextStyle(weight=ft.FontWeight.BOLD)
    if kind == "em":
        return ft.TextStyle(italic=True)
    if kind == "del":
        return ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH, color=MUTED)
    return ft.TextStyle(bgcolor=MARK_BG, color=MARK_FG)  # highlight


def render_flow(nodes: list, stats: dict, max_image_width: int = MAX_IMAGE_WIDTH) -> list[ft.Control]:
    """行内流渲染：文本段聚合成 RichText，图片独立为 Image 控件。"""
    controls: list[ft.Control] = []
    pending: list[ft.TextSpan] = []

    def flush():
        if pending:
            stats["nodes"] += len(pending)
            controls.append(ft.Text(spans=list(pending), size=15, color=FG))
            pending.clear()

    for nd in nodes:
        if isinstance(nd, Image):
            flush()
            controls.append(_image_control(nd, max_image_width))
            continue
        pending.extend(render_inline_spans([nd]))
    flush()
    return controls


def _image_control(nd: Image, max_image_width: int = MAX_IMAGE_WIDTH) -> ft.Control:
    url = safe_url(nd.href, "img")
    fallback = ft.Text(f"[{nd.alt or '图片'}]", color=MUTED, size=13)
    if not url:
        return fallback
    kwargs: dict = {
        "fit": ft.BoxFit.CONTAIN,
        "border_radius": 6,
        "error_content": fallback,
        "tooltip": nd.title or None,
    }
    if url.startswith("data:image/"):
        header, _, payload = url.partition(",")
        if "base64" in header:
            try:
                base64.b64decode(payload, validate=True)
            except ValueError:  # base64 损坏 → 回退 alt 文本
                return fallback
            return ft.Image(src=payload, width=max_image_width, **kwargs)
        return fallback  # svg+xml 等 Flet 不支持的 data URI
    return ft.Image(src=url, width=max_image_width, **kwargs)


def render_blocks(
    blocks: list, stats: dict | None = None, max_image_width: int = MAX_IMAGE_WIDTH
) -> list[ft.Control]:
    stats = stats if stats is not None else {"nodes": 0}
    controls: list[ft.Control] = []
    for b in blocks:
        stats["nodes"] += 1
        if isinstance(b, Heading):
            controls.append(_heading(b, stats))
        elif isinstance(b, Paragraph):
            controls.extend(_paragraph(b, stats, max_image_width))
        elif isinstance(b, CodeBlock):
            controls.append(_code_block(b))
        elif isinstance(b, Quote):
            controls.append(
                ft.Container(
                    content=ft.Column(render_blocks(b.blocks, stats, max_image_width), spacing=6, tight=True),
                    border=ft.Border(left=ft.BorderSide(3, ACCENT)),
                    bgcolor=QUOTE_BG,
                    padding=ft.Padding(14, 8, 14, 8),
                    margin=ft.Margin(0, 4, 0, 4),
                )
            )
        elif isinstance(b, ListBlock):
            controls.append(_list(b, stats, max_image_width))
        elif isinstance(b, Table):
            controls.append(_table(b, stats))
        elif isinstance(b, Hr):
            controls.append(ft.Divider(height=32, color=BORDER))
    return controls


def _heading(b: Heading, stats: dict) -> ft.Control:
    level = min(6, max(1, b.level))
    text = ft.Text(
        spans=render_inline_spans(b.inline),
        size=HEADING_SIZES[level],
        weight=ft.FontWeight.BOLD,
        color=FG if level < 5 else MUTED,
    )
    if level <= 2:
        return ft.Column(
            [
                ft.Container(text, padding=ft.Padding(0, 6, 0, 2)),
                ft.Divider(height=1, color=BORDER),
            ],
            spacing=2,
            tight=True,
        )
    return ft.Container(text, padding=ft.Padding(0, 4, 0, 2))


def _paragraph(b: Paragraph, stats: dict, max_image_width: int = MAX_IMAGE_WIDTH) -> list[ft.Control]:
    flow = render_flow(b.inline, stats, max_image_width)
    if not flow:
        return [ft.Text("", size=4)]
    return [ft.Container(ctrl, padding=ft.Padding(0, 3, 0, 3)) for ctrl in flow]


def _code_block(b: CodeBlock) -> ft.Control:
    lang = resolve_lang(b.lang)
    if lang:
        spans = [
            ft.TextSpan(
                text=text,
                style=ft.TextStyle(color=TOKEN_COLORS.get(cls, CODE_FG), font_family=MONO),
            )
            for cls, text in tokenize_code(b.code, lang)
        ]
    else:
        spans = [ft.TextSpan(text=b.code, style=ft.TextStyle(color=CODE_FG, font_family=MONO))]
    text = ft.Text(spans=spans, size=13, no_wrap=True)
    return ft.Container(
        content=ft.Row([text], scroll=ft.ScrollMode.AUTO, spacing=0),
        bgcolor=CODE_BG,
        border=ft.Border.all(1, BORDER),
        border_radius=8,
        padding=ft.Padding(16, 14, 16, 14),
        margin=ft.Margin(0, 6, 0, 6),
    )


def _list(b: ListBlock, stats: dict, max_image_width: int = MAX_IMAGE_WIDTH) -> ft.Control:
    rows: list[ft.Control] = []
    for index, item in enumerate(b.items):
        marker = f"{b.start + index}." if b.ordered else "•"
        task = _peel_task(item.blocks)
        if task is not None:
            rows.append(
                ft.Row(
                    [
                        ft.Checkbox(value=task["checked"], disabled=True, scale=0.85),
                        ft.Text(
                            spans=render_inline_spans(task["rest"]),
                            size=15,
                            color=MUTED if task["checked"] else FG,
                        ),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                )
            )
            continue
        content_controls = render_blocks(item.blocks, stats, max_image_width)
        if b.tight:
            # 紧凑列表：把段落容器转为裸控件，保持单行观感
            flattened: list[ft.Control] = []
            for ctrl in content_controls:
                inner = getattr(ctrl, "content", None)
                flattened.append(inner if inner is not None else ctrl)
            content_controls = flattened
        rows.append(
            ft.Row(
                [
                    ft.Container(
                        ft.Text(marker, size=15, color=ACCENT, weight=ft.FontWeight.BOLD),
                        width=24,
                    ),
                    ft.Column(content_controls, spacing=3, tight=True, expand=True),
                ],
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
    return ft.Container(
        ft.Column(rows, spacing=4, tight=True),
        margin=ft.Margin(0, 4, 0, 4),
    )


def _peel_task(blocks: list):
    """任务列表探测：首段落首文本节点以 [ ]/[x] 开头。"""
    if not blocks:
        return None
    first = blocks[0]
    if not isinstance(first, Paragraph) or not first.inline:
        return None
    n0 = first.inline[0]
    if not isinstance(n0, TextNode):
        return None
    import re

    m = re.match(r"^\[([ xX])\]\s+", n0.value)
    if not m:
        return None
    rest_text = n0.value[m.end():]
    rest = list(first.inline)
    if rest_text:
        rest[0] = TextNode(rest_text)
    else:
        rest = rest[1:]
    return {"checked": m.group(1).lower() == "x", "rest": rest}


def _table(b: Table, stats: dict) -> ft.Control:
    def cell_text(raw: str, align: str, bold: bool = False):
        spans = render_inline_spans(_inline_of(raw))
        text_align = {
            "left": ft.TextAlign.LEFT,
            "center": ft.TextAlign.CENTER,
            "right": ft.TextAlign.RIGHT,
        }.get(align, ft.TextAlign.LEFT)
        return ft.Text(spans=spans, size=14, weight=ft.FontWeight.BOLD if bold else None,
                       text_align=text_align, color=FG)

    def _inline_of(raw: str):
        from md_core.extensions import REGISTRY
        from md_core.inline import InlineCtx, parse_inline

        return parse_inline(raw, InlineCtx(refs={}, exts=list(REGISTRY)))

    columns = [
        ft.DataColumn(cell_text(head, b.align[k] if k < len(b.align) else "", bold=True))
        for k, head in enumerate(b.head)
    ]
    rows = []
    for idx, row in enumerate(b.rows):
        cells = []
        for k in range(len(b.head)):
            raw = row[k] if k < len(row) else ""
            align = b.align[k] if k < len(b.align) else ""
            cells.append(ft.DataCell(cell_text(raw, align)))
        row_color = ft.Colors.with_opacity(0.05, "#7f8ca0") if idx % 2 else None
        rows.append(ft.DataRow(cells=cells, color=row_color))
    table = ft.DataTable(
        columns=columns,
        rows=rows,
        border=ft.Border.all(1, BORDER),
    )
    return ft.Container(
        ft.Row([table], scroll=ft.ScrollMode.AUTO, spacing=0),
        margin=ft.Margin(0, 6, 0, 6),
    )
