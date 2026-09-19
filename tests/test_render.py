"""渲染器测试：仅构造控件（不创建窗口），验证结构与参数传递。"""

from __future__ import annotations

from md_core import render
from md_core.nodes import Image, Paragraph


def _find_images(controls):
    found = []

    def walk(c):
        if type(c).__name__ == "Image":
            found.append(c)
            return
        for attr in ("controls", "content"):
            v = getattr(c, attr, None)
            if isinstance(v, list):
                for x in v:
                    walk(x)
            elif v is not None and hasattr(v, "__dataclass_fields__"):
                walk(v)

    for c in controls:
        walk(c)
    return found


class TestImageWidth:
    def test_image_respects_max_width(self):
        ctrl = render._image_control(Image(href="https://example.com/a.png"), max_image_width=200)
        assert ctrl.width == 200

    def test_render_blocks_threads_width(self):
        blocks = [Paragraph([Image(href="https://example.com/a.png")])]
        controls = render.render_blocks(blocks, max_image_width=240)
        images = _find_images(controls)
        assert images and all(i.width == 240 for i in images)

    def test_default_width_is_desktop(self):
        controls = render.render_blocks([Paragraph([Image(href="https://example.com/a.png")])])
        assert _find_images(controls)[0].width == render.MAX_IMAGE_WIDTH
