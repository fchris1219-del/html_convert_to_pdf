---
name: raster-pdf-export
description: Export HTML pages into image-based PDFs by capturing each .page element as a high-resolution browser screenshot and then packaging the screenshots back into a PDF. Use when the user wants a scan-like PDF that preserves browser-rendered effects such as glow, gradients, blur-like appearance, and lighting, especially for whitepapers, one-pagers, decks, or other fixed-layout HTML deliverables.
---

# Raster PDF Export

Use this skill when the target is an HTML artifact and the output should be a PDF where every page is a raster image.

## What This Skill Does

- Opens local HTML files in Chromium with Playwright.
- Waits for screen rendering and web fonts.
- Freezes animation and transition effects for stable capture.
- Captures each `.page` element as a PNG at high DPI.
- Repackages the PNGs into a single image-based PDF.

## When To Use It

- The user wants "图片版 PDF", "扫描件效果", or "逐页截图再封 PDF".
- Browser rendering fidelity matters more than vector text.
- Existing vector PDF output loses glow, gradients, or complex visual effects.

## Workflow

1. Confirm the source is local HTML and that each page is wrapped in a `.page` element.
2. Run `scripts/export_raster_pdf.py` against one or more HTML files.
3. Use `--scale 4` for the default ultra-HD output. Increase only if the user explicitly wants even larger files.
4. Keep `--keep-pngs` only when the user wants intermediate page images for inspection.

## Command Pattern

```bash
python3 scripts/export_raster_pdf.py --scale 4 /path/to/file.html
python3 scripts/export_raster_pdf.py --scale 4 /path/to/a.html /path/to/b.html
```

## Notes

- This workflow assumes fixed-layout HTML, not arbitrary long-scrolling web pages.
- If `.page` is missing, inspect the HTML and update the selector in the script before retrying.
- Output filenames end with `_图片版_超清.pdf`.
