from __future__ import annotations

from io import BytesIO

from PIL import Image

from camoufox_playwright_mcp.backend.response import scale_image_to_fit_message


def test_scale_image_to_fit_message_keeps_small_png() -> None:
    data = _png(100, 80)

    assert scale_image_to_fit_message(data, "png") == data


def test_scale_image_to_fit_message_scales_large_png_to_claude_limits() -> None:
    data = _png(2200, 1200)

    scaled = scale_image_to_fit_message(data, "png")

    with Image.open(BytesIO(scaled)) as image:
        width, height = image.size
    assert width <= 1568
    assert height <= 1568
    assert width * height <= int(1.15 * 1024 * 1024)


def _png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()
