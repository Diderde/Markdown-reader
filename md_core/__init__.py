# SPDX-License-Identifier: GPL-2.0-or-later
"""md_core —— Markdown 解析核心（纯逻辑，不依赖 Flet，可独立单测）。

移植自单文件版 markdown-reader.html 的 JS 实现，分层与算法保持一致：
  blocks.lex（块级）→ inline.parse_inline（行内）→ render（Flet 控件）

相对原版的修复与差异见项目 README「相对 HTML 版的修复」一节。
"""

from md_core.pipeline import run_pipeline

__all__ = ["run_pipeline"]
