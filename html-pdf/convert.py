#!/usr/bin/env python3
"""
html-pdf converter
Converts an HTML file to a pixel-perfect A4 PDF with:
  - No rasterization (targeted panel rgba backgrounds flattened, SVG blur disabled)
  - Exact A4 size (no margins, no white borders)
  - No page overflow or clipping

IMPORTANT: Only replace high-alpha white-ish PANEL backgrounds — never replace
decorative rgba values in gradients, borders, shadows, or text colors.
Replacing ALL rgba() destroys gradients and breaks the visual design.
"""

import asyncio
import re
import sys
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Step 1: Pre-process HTML to eliminate rasterization triggers
# ---------------------------------------------------------------------------

# Whitelist: only these specific semi-transparent white/cool-white panel backgrounds
# cause compositing-layer rasterization. Everything else (decorative gradients,
# borders, shadows, text colors) must be left untouched.
PANEL_REPLACEMENTS = [
    # Pure white panels
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.98\s*\)', '#ffffff'),
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.97\s*\)', '#ffffff'),
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.96\s*\)', '#f5f5f5'),
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.95\s*\)', '#fafafa'),
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.92\s*\)', '#f5f5f5'),
    # arch-layer / arch-container backgrounds (causes ::before z-index bleed in PDF)
    (r'rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*0\.9\s*\)',  '#f5f5f5'),
    (r'rgba\(\s*240\s*,\s*244\s*,\s*248\s*,\s*0\.8\s*\)',  '#e8edf2'),
    (r'rgba\(\s*224\s*,\s*238\s*,\s*244\s*,\s*0\.8\s*\)',  '#dce8ed'),
    # Cool-white panels
    (r'rgba\(\s*248\s*,\s*250\s*,\s*252\s*,\s*0\.95\s*\)', '#f8fafc'),
    (r'rgba\(\s*248\s*,\s*250\s*,\s*252\s*,\s*0\.92\s*\)', '#f8fafc'),
    (r'rgba\(\s*248\s*,\s*250\s*,\s*252\s*,\s*0\.9\s*\)',  '#f8fafc'),
    (r'rgba\(\s*242\s*,\s*247\s*,\s*249\s*,\s*0\.88\s*\)', '#f2f7f9'),
    (r'rgba\(\s*240\s*,\s*244\s*,\s*248\s*,\s*0\.95\s*\)', '#f0f4f8'),
    (r'rgba\(\s*240\s*,\s*244\s*,\s*248\s*,\s*0\.9\s*\)',  '#f0f4f8'),
    (r'rgba\(\s*240\s*,\s*244\s*,\s*248\s*,\s*0\.72\s*\)', '#f0f4f8'),
]

# CSS injected before </head> — removes compositing-layer triggers
PDF_OVERRIDE_CSS = """
  <style id="__html_pdf_override__">
    @page { size: A4; margin: 0; }
    .page {
      margin: 0 !important;
      border-radius: 0 !important;
      box-shadow: none !important;
    }
    *, *::before, *::after {
      filter: none !important;
      backdrop-filter: none !important;
      -webkit-backdrop-filter: none !important;
      will-change: auto !important;
      mask-image: none !important;
      -webkit-mask-image: none !important;
    }
  </style>
</head>"""


def preprocess_html(html: str) -> str:
    """
    Targeted fixes that prevent Chrome from creating compositing layers
    which it then rasterizes into bitmaps instead of keeping as crisp vectors:

    1. Specific high-alpha white-ish panel rgba() → opaque equivalents
       ONLY the whitelist above. Never replace all rgba() — that destroys
       decorative gradients and completely breaks the visual design.

    2. SVG feGaussianBlur stdDeviation → 0
       Blur filters force rasterization of the filtered element and its children.

    3. Inject CSS override: remove filter/backdrop-filter/will-change,
       strip .page margin/border-radius/box-shadow, set @page margin 0.
    """
    # Fix 1: targeted panel background replacements only
    for pattern, replacement in PANEL_REPLACEMENTS:
        html = re.sub(pattern, replacement, html)

    # Fix 2: zero out SVG blur stdDeviation
    html = re.sub(r'stdDeviation="[^"]*"', 'stdDeviation="0"', html)

    # Fix 3: inject override style
    if "</head>" in html:
        html = html.replace("</head>", PDF_OVERRIDE_CSS, 1)

    return html


# ---------------------------------------------------------------------------
# Step 2: Render with Playwright for vector-quality PDF output
# ---------------------------------------------------------------------------

async def render_pdf(input_path: Path, output_path: Path) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Installing now...")
        os.system(f"{sys.executable} -m pip install playwright -q")
        os.system(f"{sys.executable} -m playwright install chromium")
        from playwright.async_api import async_playwright

    html = input_path.read_text(encoding="utf-8")
    html = preprocess_html(html)

    tmp_path = input_path.with_suffix(".tmp_pdf.html")
    tmp_path.write_text(html, encoding="utf-8")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 794, "height": 1123},
                device_scale_factor=3,
            )
            page = await context.new_page()
            await page.goto(tmp_path.as_uri(), wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(2000)
            await page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            await browser.close()
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: python convert.py <input.html> [output.pdf]")
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    if not input_path.exists():
        print(f"Error: file not found: {input_path}")
        sys.exit(1)

    output_path = Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else input_path.with_name(input_path.stem + "_高清版.pdf")

    print(f"Converting: {input_path}")
    print(f"Output:     {output_path}")

    asyncio.run(render_pdf(input_path, output_path))

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"Done — {size_mb:.2f} MB → {output_path}")


if __name__ == "__main__":
    main()
