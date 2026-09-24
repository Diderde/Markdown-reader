# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""示例文档与占位图（纯 stdlib 生成 PNG，Flet 可直接渲染 base64 图片）。"""

from __future__ import annotations

import base64
import struct
import zlib


def _png_placeholder(width: int = 160, height: int = 64, rgb: tuple = (0x33, 0xAA, 0x55)) -> str:
    """生成纯色 PNG 的 base64（无第三方依赖）。"""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return base64.b64encode(png).decode("ascii")


SAMPLE_IMAGE_B64 = _png_placeholder()

SAMPLE = f"""# Markdown 阅读器

> 双栏编辑 · 实时渲染 · 桌面与移动端自适应。本示例文档覆盖主要语法。

## 强调与行内元素

**加粗**、*斜体*、~~删除线~~、==高亮（内置扩展示例）==、`行内代码`。

*斜体中包含 **加粗** 的嵌套写法。* 中文_下划线_不是斜体_（intra-word 修复示例）。

## 链接与图片

[Python 官网](https://www.python.org "官网")、[引用式链接][ref1]、
自动链接 <https://example.com>、邮箱 <hello@example.com>。

[ref1]: https://example.com "引用链接"

![纯色占位图](data:image/png;base64,{SAMPLE_IMAGE_B64} "PNG data URI，离线可用")

## 列表

- 无序列表项
- 嵌套列表：
  - 子项 A
  - 子项 B
    1. 有序子列表
    2. 第二项
- [x] 已完成任务
- [ ] 未完成任务

## 表格与对齐

| 左对齐 | 居中 | 右对齐 | 说明 |
| :--- | :---: | ---: | --- |
| 苹果 | 香蕉 | 3 | 水果 |
| 转义 \\| 管道 | 正常 | 12 | 表格 |

## 代码块

```python
# 语法高亮（内置 Python / JS / JSON / HTML / CSS / Bash）
def greet(name):
    return f"Hello, {{name}}!"
```

## 引用与分隔线

> 引用内同样支持 **Markdown** 语法。
>
> 多行引用。

---

## 转义示例

\\*不是斜体\\*，\\_也不是强调\\_，`**代码内不做强调**`。

## Setext 标题（次级）
由下一行 `---` 生成
"""
