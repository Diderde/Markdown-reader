# SPDX-License-Identifier: GPL-2.0-or-later
"""Markdown Reader —— 桌面与移动端自适应。

- 宽屏（≥900px）：源码 | 预览 双栏；窄屏：编辑 / 预览 两个标签页
- 输入自适应防抖（120ms ~ 2s，随上次渲染耗时伸缩），解析在后台线程执行
- 打开 .md（UTF-8 / GB18030 自动识别）、示例、清空、源码区显隐
- 状态栏：文件名、字符数、解析耗时、块/节点数、错误计数
"""

from __future__ import annotations

import sys
import threading
import time
from urllib.parse import urlparse

import flet as ft

from md_core import render
from md_core.netinfo import get_lan_ips
from md_core.pipeline import decode_text, run_pipeline
from md_core.sample import SAMPLE

BG = "#0f1115"
PANEL = "#161a22"
EDITOR_BG = "#0b0d11"
EDITOR_FG = "#c8d0dd"
MUTED = "#8b93a3"
BORDER = "#262b36"
ACCENT = "#4f8cff"
ERROR_BG = "#5c1f1f"
ERROR_FG = "#ffb4b4"
NARROW_BREAKPOINT = 900
MAX_FILE_BYTES = 20 * 1024 * 1024

_MD_EXTS = (".md", ".markdown", ".txt")


class MarkdownReaderApp:
    """应用外壳：持有全部控件与状态，页面事件在其上接线。"""

    def __init__(self, page: ft.Page):
        self.page = page
        page.title = "Markdown Reader · 双端阅读器"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BG
        page.padding = 0
        page.fonts = {}

        self._debounce_timer: threading.Timer | None = None
        self._render_lock = threading.Lock()
        self._render_seq = 0
        self._last_render_ms = 0.0
        self._last_good_source: str = ""
        self._error_count = 0
        self._current_file = ""
        # --narrow：冒烟/演示开关，强制走移动端 Tabs 布局
        self._is_narrow = "--narrow" in sys.argv or (page.width or 0) < NARROW_BREAKPOINT

        # ---- 顶部栏 ----
        self.btn_open = ft.Button("导入 .md", on_click=self._pick_file, height=34)
        self.btn_sample = ft.Button("示例", on_click=self._load_sample, height=34)
        self.btn_clear = ft.Button("清空", on_click=self._clear, height=34)
        self.chk_source = ft.Switch(
            label="源码", value=True, scale=0.85, on_change=self._toggle_source
        )
        self.file_picker = ft.FilePicker()   # Flet 1.0：选文件走 async pick_files，没有 on_result 回调
        page.services.append(self.file_picker)  # Flet 1.0：服务型控件挂 services（overlay 会报 Unknown control）

        topbar = ft.Container(
            content=ft.Row(
                [
                    ft.Text("Markdown 阅读器", size=15, weight=ft.FontWeight.BOLD, color="#e7ebf2"),
                    ft.Row(
                        [self.btn_open, self.btn_sample, self.btn_clear, self.chk_source],
                        spacing=8,
                        wrap=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
            ),
            bgcolor=PANEL,
            padding=ft.Padding(16, 8, 16, 8),
            border=ft.Border(bottom=ft.BorderSide(1, BORDER)),
        )

        # ---- 局域网访问条（仅 Web 模式显示）----
        self.lan_strip = self._build_lan_strip(page)

        # ---- 编辑器与预览 ----
        self.editor = ft.TextField(
            multiline=True,
            min_lines=1,
            expand=True,
            border_color=ft.Colors.TRANSPARENT,
            focused_border_color=ft.Colors.TRANSPARENT,
            bgcolor=EDITOR_BG,
            color=EDITOR_FG,
            text_size=13,
            content_padding=ft.Padding(16, 16, 16, 16),
            on_change=self._schedule_refresh,
            hint_text="在此输入 Markdown……也支持从文件导入",
            cursor_color=ACCENT,
        )
        self.preview_column = ft.Column(spacing=2, expand=True)  # 滚动由外层预览容器统一处理
        self.preview_pane = ft.Container(
            content=self.preview_column,
            expand=True,
            padding=ft.Padding(18, 16, 18, 24),
        )
        self.error_banner = ft.Container(
            content=ft.Text("", size=13, color=ERROR_FG),
            bgcolor=ERROR_BG,
            border=ft.Border.all(1, "#8c3a3a"),
            border_radius=8,
            padding=ft.Padding(14, 8, 14, 8),
            visible=False,
        )
        self.empty_hint = ft.Text("输入 Markdown，右侧实时渲染", color=MUTED, size=14)

        # ---- 状态栏 ----
        self.stat_file = ft.Text("", size=12, color=MUTED)
        self.stat_doc = ft.Text("—", size=12, color=MUTED)
        self.stat_parse = ft.Text("—", size=12, color=MUTED)
        self.stat_render = ft.Text("—", size=12, color=MUTED)
        self.stat_errors = ft.Text("", size=12, color="#ff8a8a")
        self.status_var = ft.Text("", size=12, color=ACCENT)
        statusbar = ft.Container(
            content=ft.Row(
                [
                    self.stat_file,
                    self.stat_doc,
                    self.stat_parse,
                    self.stat_render,
                    self.stat_errors,
                    self.status_var,
                ],
                spacing=20,
                wrap=True,
            ),
            bgcolor=PANEL,
            padding=ft.Padding(16, 5, 16, 5),
            border=ft.Border(top=ft.BorderSide(1, BORDER)),
        )

        # ---- 自适应主体 ----
        self.body = ft.Column([], expand=True, spacing=0, tight=True)
        page.add(topbar, self.lan_strip, self.body, statusbar)
        self._apply_layout()
        page.on_resize = self._on_resize
        page.on_keyboard_event = self._on_key

        self._set_source(SAMPLE, status_file="")

    # ------------------------------------------------------------ 布局

    def _build_lan_strip(self, page: ft.Page) -> ft.Control:
        """Web 模式下显示局域网访问地址（手机同网段可开）；桌面模式隐藏。"""
        is_web = bool(page.url) and str(page.url).startswith("http")
        ips = get_lan_ips() if is_web else []
        if not ips:
            return ft.Container(visible=False)

        parsed = urlparse(str(page.url))
        port = parsed.port or 80
        urls = "\n".join(f"http://{ip}:{port}" for ip in ips)
        urls_row = ft.Row(
            [ft.Text(u, size=13, color=ACCENT, selectable=True) for u in urls.split("\n")],
            spacing=2,
            wrap=True,
        )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("手机访问（同一局域网）：", size=13, color=MUTED),
                    urls_row,
                    ft.TextButton(
                        "复制地址",
                        icon=ft.Icons.CONTENT_COPY,
                        # Flet 1.0：剪贴板写入交给客户端在用户手势内完成（Safari 等仅此时放行）
                        action=ft.CopyToClipboard(urls),
                        on_click=lambda _e: self._mark_copied(),
                    ),
                    ft.TextButton("隐藏", on_click=lambda _e: self._hide_lan_strip()),
                ],
                spacing=10,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor="#12203a",
            padding=ft.Padding(16, 6, 16, 6),
            border=ft.Border(bottom=ft.BorderSide(1, BORDER)),
        )

    def _mark_copied(self) -> None:
        """复制本身由 ft.CopyToClipboard 在客户端手势内完成，这里只更新状态提示。"""
        self.status_var.set("局域网地址已复制，手机浏览器打开即可（需同一局域网）。")

    def _hide_lan_strip(self) -> None:
        self.lan_strip.visible = False
        self.page.update()

    def _apply_layout(self) -> None:
        wide = not self._is_narrow
        if wide:
            self.body.controls = [
                ft.Row(
                    [
                        self._editor_pane(),
                        ft.VerticalDivider(width=1, color=BORDER),
                        self._preview_pane(),
                    ],
                    spacing=0,
                    expand=True,
                )
            ]
        else:
            # Flet 1.0：Tabs = TabBar（标签头）+ TabBarView（内容页）组合
            self.body.controls = [
                ft.Tabs(
                    selected_index=1 if not self.chk_source.value else 0,
                    length=2,
                    expand=True,
                    content=ft.Column(
                        [
                            ft.TabBar(tabs=[ft.Tab(label="源码"), ft.Tab(label="预览")]),
                            ft.TabBarView(
                                expand=True,
                                controls=[self._editor_pane(), self._preview_pane()],
                            ),
                        ],
                        expand=True,
                        spacing=0,
                        tight=True,
                    ),
                )
            ]
        self.body.update()

    def _editor_pane(self) -> ft.Container:
        return ft.Container(
            content=self.editor,
            expand=True,
            bgcolor=EDITOR_BG,
            visible=self.chk_source.value,
        )

    def _preview_pane(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [self.error_banner, self.preview_pane],
                spacing=4,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
            expand=True,
        )

    def _on_resize(self, _e) -> None:
        narrow = (self.page.width or 0) < NARROW_BREAKPOINT
        if narrow != self._is_narrow:
            self._is_narrow = narrow
            self._apply_layout()

    def _toggle_source(self, _e) -> None:
        self._apply_layout()

    def _on_key(self, e: ft.KeyboardEvent) -> None:
        if e.key == "Enter" and (e.ctrl or e.meta):
            self._refresh_now()

    # ------------------------------------------------------------ 渲染

    def _set_source(self, text: str, status_file: str | None = None) -> None:
        self.editor.value = text
        if status_file is not None:
            self.stat_file.value = status_file
        self._refresh_now()

    def _schedule_refresh(self, _e=None) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
        interval = min(2.0, max(0.12, self._last_render_ms * 2 / 1000))
        self._debounce_timer = threading.Timer(interval, self._refresh_now)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _refresh_now(self, _e=None) -> None:
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        self._render_seq += 1  # 主线程单调递增；旧线程序号过期即作废
        seq = self._render_seq
        threading.Thread(target=self._render_worker, args=(seq,), daemon=True, name="md-render").start()

    def _render_worker(self, seq: int) -> None:
        """解析+构建控件在后台线程执行；锁内串行，过期序号的渲染直接丢弃。"""
        with self._render_lock:
            if seq != self._render_seq:
                return  # 已有更新的渲染请求，本次结果作废（防旧覆盖新）
            src = self.editor.value or ""
        with self._render_lock:
            try:
                result = run_pipeline(src)
                stats = result.stats
                t0 = time.perf_counter()
                # 图片最大宽度随窗口收缩（手机上不横向溢出）
                image_width = max(240, min(560, int((self.page.width or 800) * 0.55)))
                controls = render.render_blocks(result.blocks, max_image_width=image_width)
                render_ms = (time.perf_counter() - t0) * 1000
                stats.render_ms = render_ms
            except Exception as exc:  # noqa: BLE001  # 渲染失败：保留上次成功结果 + 错误横幅
                self._error_count += 1
                self.error_banner.content.value = f"渲染失败：{exc}"
                self.error_banner.visible = True
                self.stat_errors.value = f"错误 {self._error_count}"
                self.page.update()
                return

            self.error_banner.visible = False
            is_empty = not src.strip()
            self.preview_column.controls = (
                [self.empty_hint] if is_empty else controls
            )
            self._last_render_ms = stats.lex_ms + stats.render_ms
            self._last_good_source = src
            self.stat_doc.value = f"{stats.chars:,} 字符"
            self.stat_parse.value = f"解析 {stats.lex_ms:.2f} ms"
            self.stat_render.value = (
                f"渲染 {stats.render_ms:.2f} ms · {stats.blocks} 块 · {stats.nodes:,} 节点"
            )
            self.page.update()

    # ------------------------------------------------------------ 文件导入

    def _pick_file(self, _e=None) -> None:
        """Flet 1.0：pick_files 是协程方法，须 await；选中文件由返回值给出（不再触发 on_result）。"""
        self.page.run_task(self._choose_md_file)

    async def _choose_md_file(self) -> None:
        files = await self.file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=list(_MD_EXTS),
            dialog_title="选择 Markdown 文件",
        )
        if files:
            self._load_picked(files[0])

    def _load_picked(self, f: ft.FilePickerFile) -> None:
        try:
            if f.size > MAX_FILE_BYTES:
                self._show_error("导入失败：文件超过 20 MB 上限，请精简后导入")
                return
            if not f.path:
                self._show_error("导入失败：无法获取文件路径")
                return
            with open(f.path, "rb") as fh:
                data = fh.read()
            if not data:
                self._show_error("导入失败：无法读取文件内容")
                return
            text = decode_text(data)
            kb = f.size / 1024
            self._set_source(text, status_file=f"{f.name}（{kb:.1f} KB）")
            self._current_file = f.name
        except OSError as exc:  # 文件读取失败不影响当前内容
            self._show_error(f"导入失败：{exc}")

    def _show_error(self, message: str) -> None:
        self.error_banner.content.value = message
        self.error_banner.visible = True
        self.page.update()

    def _load_sample(self, _e=None) -> None:
        self._current_file = ""
        self._set_source(SAMPLE, status_file="")

    def _clear(self, _e=None) -> None:
        self._current_file = ""
        self._set_source("", status_file="")


def main(page: ft.Page) -> None:
    MarkdownReaderApp(page)


if __name__ == "__main__":
    # --narrow 冒烟开关：强制走移动端 Tabs 布局
    ft.run(main)
