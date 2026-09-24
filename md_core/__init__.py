# SPDX-License-Identifier: GPL-2.0-or-later
"""md_core —— Markdown 解析核心（解析层纯逻辑、不依赖 Flet，可独立单测）。

移植自单文件版 markdown-reader.html 的 JS 实现，分层与算法保持一致：
  blocks.lex（块级）→ inline.parse_inline（行内）→ render（Flet 控件）

注：`render` 子模块负责把节点树转成 Flet 控件，是本包唯一依赖 Flet 的部分。
"""

from md_core.pipeline import run_pipeline

__all__ = ["run_pipeline"]
