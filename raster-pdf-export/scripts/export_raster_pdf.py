#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from PIL import Image


FREEZE_MOTION_CSS = """
*,
*::before,
*::after {
  transition: none !important;
  animation: none !important;
  caret-color: transparent !important;
}
html {
  scroll-behavior: auto !important;
}
body {
  margin: 0 !important;
}
"""


def build_output_path(input_path: Path, output_dir: Path) -> Path:
    stem = input_path.stem
    stem = stem.removesuffix("20260526")
    return output_dir / f"{stem}_图片版_超清.pdf"


async def render_html_to_raster_pdf(
    input_path: Path,
    output_path: Path,
    scale: int,
    jpeg_quality: int,
    wait_ms: int,
    selector: str,
    keep_pngs: bool,
) -> None:
    from playwright.async_api import async_playwright

    png_dir = output_path.with_suffix("")
    if png_dir.exists():
        shutil.rmtree(png_dir)
    png_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 794, "height": 1123},
            device_scale_factor=scale,
            screen={"width": 794, "height": 1123},
        )
        page = await context.new_page()
        await page.emulate_media(media="screen")
        await page.goto(input_path.as_uri(), wait_until="networkidle", timeout=120000)
        await page.add_style_tag(content=FREEZE_MOTION_CSS)
        await page.evaluate(
            """
            async () => {
              if (document.fonts && document.fonts.ready) {
                try {
                  await document.fonts.ready;
                } catch (error) {
                  console.warn(error);
                }
              }
            }
            """
        )
        await page.wait_for_timeout(wait_ms)

        pages = page.locator(selector)
        page_count = await pages.count()
        if page_count == 0:
            raise RuntimeError(f"{input_path} 中没有找到页面选择器: {selector}")

        png_paths: list[Path] = []
        for index in range(page_count):
            current = pages.nth(index)
            png_path = png_dir / f"page-{index + 1:02d}.png"
            await current.screenshot(path=str(png_path))
            png_paths.append(png_path)
            print(f"[{input_path.name}] captured {index + 1}/{page_count}: {png_path.name}")

        await browser.close()

    images: list[Image.Image] = []
    try:
        for png_path in png_paths:
            images.append(Image.open(png_path).convert("RGB"))

        first, rest = images[0], images[1:]
        first.save(
            output_path,
            "PDF",
            resolution=72 * scale,
            save_all=True,
            append_images=rest,
            quality=jpeg_quality,
        )
    finally:
        for image in images:
            image.close()
        if not keep_pngs:
            shutil.rmtree(png_dir, ignore_errors=True)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export HTML files to raster PDFs via page screenshots.")
    parser.add_argument("inputs", nargs="+", type=Path, help="HTML files to export")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd(), help="Directory for exported PDFs")
    parser.add_argument("--scale", type=int, default=4, help="Chromium device scale factor")
    parser.add_argument("--jpeg-quality", type=int, default=95, help="Embedded image quality for PDF")
    parser.add_argument("--wait-ms", type=int, default=1200, help="Extra wait after load before capture")
    parser.add_argument("--selector", default=".page", help="Per-page element selector")
    parser.add_argument("--keep-pngs", action="store_true", help="Keep intermediate PNG pages")
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    for input_path in args.inputs:
        input_path = input_path.resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"未找到输入文件: {input_path}")
        output_path = build_output_path(input_path, output_dir)
        print(f"Exporting {input_path.name} -> {output_path.name}")
        await render_html_to_raster_pdf(
            input_path=input_path,
            output_path=output_path,
            scale=args.scale,
            jpeg_quality=args.jpeg_quality,
            wait_ms=args.wait_ms,
            selector=args.selector,
            keep_pngs=args.keep_pngs,
        )
        print(f"Done: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
