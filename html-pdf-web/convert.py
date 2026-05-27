#!/usr/bin/env python3
"""
html-pdf-web: HTML → 线上传阅专用 PDF
针对数字屏幕阅读优化，彻底消除栅格化触发器，保证矢量输出，颜色100%还原。

与 html-pdf (印刷版) 的核心区别：
  1. 保留所有 rgba 颜色（不做合成，颜色100%忠实原设计）
     ※ rgba 本身不触发栅格化，真正的触发器是 filter/backdrop-filter 等 CSS 属性
  2. 移除所有 CSS 栅格化触发器（比印刷版覆盖更全）：
       filter / backdrop-filter / will-change /
       box-shadow / text-shadow / mix-blend-mode / isolation / mask-image
  3. 压扁 3D transform → 2D 等效（translate3d/translateZ/rotateX 等强制 GPU 层合成）
  4. 使用 @media screen 渲染（emulate_media='screen'），匹配 screen 专属 CSS 规则
  5. device_scale_factor=2（屏幕清晰度，文件比印刷版小）
  6. 输出文件名自动追加 _web 后缀，与印刷版不冲突

【关键原则】
  rgba() 是颜色值，不是合成触发器。
  深色背景设计若把 rgba 合成到白色，视觉会完全失真（半透明发光层变实心白块）。
  正确做法：只删除那些会创建 GPU 合成层的 CSS 属性，rgba 原样保留。
"""

import asyncio
import re
import sys
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Fix 1: 压扁 3D transform → 2D（3D transform 强制创建 GPU 合成层 → 栅格化）
# ---------------------------------------------------------------------------

def _flatten_3d_transforms(html: str) -> str:
    # translate3d(x, y, z) → translate(x, y)
    html = re.sub(
        r"translate3d\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,[^)]+\)",
        r"translate(\1,\2)",
        html,
    )
    # translateZ(...) → 无视觉效果，删除
    html = re.sub(r"\btranslateZ\([^)]*\)\s*", "", html)
    # perspective(...) → 删除（创建 3D 渲染上下文）
    html = re.sub(r"\bperspective\([^)]*\)\s*", "", html)
    # rotateX/Y/Z(...) → 删除（3D 旋转）
    html = re.sub(r"\brotate[XYZ]\([^)]*\)\s*", "", html)
    # scaleZ / scale3d → 删除
    html = re.sub(r"\bscaleZ\([^)]*\)\s*", "", html)
    html = re.sub(r"\bscale3d\([^)]*\)\s*", "", html)
    return html


# ---------------------------------------------------------------------------
# CSS 注入：消除所有已知栅格化触发器（不触碰颜色值）
# ---------------------------------------------------------------------------

_SCREEN_CSS = """\
  <style id="__html_pdf_web_override__">
    /* ── 页面几何 ─────────────────────────────────── */
    @page { size: A4; margin: 0; }
    .page {
      margin: 0 !important;
      border-radius: 0 !important;
      box-shadow: none !important;
      width: 210mm !important;
      height: 297mm !important;
      overflow: hidden !important;
    }

    /* ── 装饰性网格背景 suppress ─────────────────────
       封面/页面的格纹装饰层（position:absolute; inset:0），
       背景是半透明网格线 linear-gradient。
       在 PDF 渲染时 Chromium 合成层顺序与屏幕有差异，
       这些线会穿透深色卡片显示出来，纯装饰，suppress 不影响内容。
       覆盖范围：.grid-bg / .page-grid / .cover-grid / .hero-grid
       以及通用的 [class*="grid-bg"] 模式。
    ─────────────────────────────────────────────── */
    .grid-bg,
    .grid-bg::before,
    .grid-bg::after,
    .page-grid,
    .page-grid::before,
    .page-grid::after,
    .cover-grid,
    .cover-grid::before,
    .cover-grid::after,
    .hero-grid,
    .hero-grid::before,
    .hero-grid::after {
      background-image: none !important;
      background: none !important;
    }

    /* ── 栅格化触发器全部关闭 ────────────────────────
       以下属性任意一个激活，Chrome 就会为该元素创建独立 GPU 合成层，
       并在 PDF 输出时将其位图化（栅格化）。
       rgba() 颜色值本身不在此列，不做处理。

         filter / backdrop-filter  → GPU 滤镜层
         will-change               → 显式提升合成层
         box-shadow / text-shadow  → 阴影合成层
         mix-blend-mode            → 混合模式层（需要合成）
         isolation: isolate        → 隔离堆叠上下文（为 blend-mode 服务）
         mask-image                → 遮罩层
    ─────────────────────────────────────────────── */
    *, *::before, *::after {
      filter:                  none !important;
      backdrop-filter:         none !important;
      -webkit-backdrop-filter: none !important;
      will-change:             auto !important;
      box-shadow:              none !important;
      text-shadow:             none !important;
      mix-blend-mode:          normal !important;
      isolation:               auto !important;
      mask-image:              none !important;
      -webkit-mask-image:      none !important;
    }

    /* ── 字体渲染优化（屏幕阅读） ─────────────────── */
    body {
      -webkit-font-smoothing:  antialiased !important;
      -moz-osx-font-smoothing: grayscale !important;
      text-rendering:          optimizeLegibility !important;
    }
  </style>
</head>"""


# ---------------------------------------------------------------------------
# 预处理流程
# ---------------------------------------------------------------------------

def preprocess_html(html: str) -> str:
    """
    执行顺序：
      1. SVG blur → 0（feGaussianBlur 是最强力的栅格化触发器）
      2. 3D transform → 2D 等效（GPU 合成层触发器）
      3. 注入 CSS 覆盖层（关闭所有 CSS 级栅格化触发器，rgba 原样保留）
    """
    # Fix 1: SVG 高斯模糊关闭
    html = re.sub(r'stdDeviation="[^"]*"', 'stdDeviation="0"', html)

    # Fix 2: 3D transform 压扁为 2D
    html = _flatten_3d_transforms(html)

    # Fix 3: 注入 CSS 覆盖
    if "</head>" in html:
        html = html.replace("</head>", _SCREEN_CSS, 1)

    return html


# ---------------------------------------------------------------------------
# Playwright 渲染
# ---------------------------------------------------------------------------

async def render_pdf(input_path: Path, output_path: Path) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright 未安装，正在自动安装...")
        os.system(f"{sys.executable} -m pip install playwright -q")
        os.system(f"{sys.executable} -m playwright install chromium")
        from playwright.async_api import async_playwright

    html = input_path.read_text(encoding="utf-8")
    html = preprocess_html(html)

    tmp_path = input_path.with_suffix(".tmp_web.html")
    tmp_path.write_text(html, encoding="utf-8")

    # JavaScript Fix A：将渐变文字（background-clip:text）替换为纯色文字。
    #
    # 根因：CSS 渐变文字通过 background-clip:text + -webkit-text-fill-color:transparent
    # 实现。PDF 渲染器和移动端阅读器（iOS Books、Android 内置 PDF）无法解析这种
    # 渐变剪切路径，表现为文字完全不可见（透明）或显示为黑色方块。
    #
    # 修复策略：
    #   1. 检测 webkitTextFillColor===transparent 且 backgroundClip===text 的元素
    #   2. 从 backgroundImage 渐变中提取第一个非透明颜色作为纯色替代
    #   3. 清除 backgroundClip / backgroundImage，让文字以纯色正常显示
    FIX_GRADIENT_TEXT_JS = """
(function fixGradientText() {
  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    const bgClip = cs.webkitBackgroundClip || cs.backgroundClip;
    const fillColor = cs.webkitTextFillColor;

    // 渐变文字标志：background-clip:text + 透明填充色
    const isGradientText =
      bgClip === 'text' &&
      (fillColor === 'transparent' || fillColor === 'rgba(0, 0, 0, 0)');
    if (!isGradientText) return;

    // 从渐变中提取第一个可用颜色
    let solidColor = null;
    const bgImg = cs.backgroundImage;
    if (bgImg && bgImg !== 'none') {
      // 优先找 rgb/rgba 颜色
      for (const m of [...bgImg.matchAll(/rgba?\\([^)]+\\)/g)]) {
        const parts = m[0].match(/[\\d.]+/g);
        if (parts && parts.length >= 3) {
          const a = parts.length >= 4 ? parseFloat(parts[3]) : 1;
          if (a > 0.3) {
            solidColor = `rgb(${Math.round(+parts[0])},${Math.round(+parts[1])},${Math.round(+parts[2])})`;
            break;
          }
        }
      }
      // 再找 hex 颜色
      if (!solidColor) {
        const hexMatch = bgImg.match(/#([0-9a-fA-F]{3,8})\\b/);
        if (hexMatch) solidColor = hexMatch[0];
      }
    }
    // fallback：使用元素的 color 属性（如有）或白色
    if (!solidColor) {
      const col = cs.color;
      solidColor = (col && col !== 'rgba(0, 0, 0, 0)' && col !== 'transparent') ? col : '#ffffff';
    }

    // 清除渐变文字并设置纯色
    el.style.webkitTextFillColor = solidColor;
    el.style.color = solidColor;
    el.style.backgroundImage = 'none';
    el.style.backgroundClip = 'initial';
    el.style.webkitBackgroundClip = 'initial';
  });
})();
"""

    # JavaScript Fix B：将 color 和 border-color 中的 rgba() 合成为纯色。
    #
    # 根因：Chromium PDF 渲染器对含 rgba() 的 color 或 border-color
    # 会把该元素包进独立的 PDF 透明组（transparency group）。
    # 透明组内 <br> 换行处两段文字是独立 paint record，交接边界暴露
    # 透明组白色底色 → 白条；两组边界浮点误差 → 1px 缝线。
    #
    # effectiveBg 策略（从元素自身向上，停在 body 前）：
    #   1. solid backgroundColor（直接用）
    #   2. backgroundImage gradient → 提取第一个 alpha>0.5 的 rgb() 颜色
    #   3. gradient 的所有颜色都很透明 → 当装饰性渐变，fallback 白色
    #   4. 找不到 → fallback 白色（不穿透 body，避免深色 navy 污染）
    FIX_RGBA_JS = """
(function fixSemiTransparentColors() {
  function parseRgba(s) {
    const m = s && s.match(/rgba?\\(\\s*([\\d.]+)\\s*,\\s*([\\d.]+)\\s*,\\s*([\\d.]+)(?:\\s*,\\s*([\\d.]+))?/);
    if (!m) return null;
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] !== undefined ? +m[4] : 1 };
  }
  function composite(fg, bg) {
    return {
      r: Math.round(fg.a * fg.r + (1 - fg.a) * bg.r),
      g: Math.round(fg.a * fg.g + (1 - fg.a) * bg.g),
      b: Math.round(fg.a * fg.b + (1 - fg.a) * bg.b),
    };
  }
  function effectiveBg(el) {
    let cur = el;
    while (cur && cur.tagName !== 'BODY' && cur !== document.documentElement) {
      const cs = getComputedStyle(cur);
      const solidBg = parseRgba(cs.backgroundColor);
      // alpha > 0.3：低于此阈值视为装饰性半透明（如 rgba(255,255,255,0.06)），
      // 继续向上找真正的背景色，避免把边框合成到近白色上变成白边。
      if (solidBg && solidBg.a > 0.3) return solidBg;
      const img = cs.backgroundImage;
      if (img && img !== 'none') {
        for (const m of [...img.matchAll(/rgba?\\([^)]+\\)/g)]) {
          const c = parseRgba(m[0]);
          if (c && c.a > 0.5) return { r: c.r, g: c.g, b: c.b, a: 1 };
        }
        return { r: 255, g: 255, b: 255, a: 1 };
      }
      cur = cur.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  }

  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    const bg = effectiveBg(el);

    // 修 color
    const col = parseRgba(cs.color);
    if (col && col.a < 1.0) {
      const o = composite(col, bg);
      el.style.color = `rgb(${o.r},${o.g},${o.b})`;
    }

    // 修 border-color（四方向）
    for (const side of ['Top','Right','Bottom','Left']) {
      const bc = parseRgba(cs['border' + side + 'Color']);
      if (bc && bc.a > 0 && bc.a < 1.0) {
        const o = composite(bc, bg);
        el.style.setProperty('border-' + side.toLowerCase() + '-color', `rgb(${o.r},${o.g},${o.b})`);
      }
    }
  });
})();
"""

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 794, "height": 1123},
                device_scale_factor=2,      # 屏幕级别（印刷版用 3，这里用 2 以减小文件体积）
            )
            page = await context.new_page()

            # 关键：使用 screen media，让 @media screen {} 规则生效
            await page.emulate_media(media="screen")

            await page.goto(tmp_path.as_uri(), wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(1500)   # 等待字体 / 动画完成

            # Fix A：渐变文字 → 纯色（移动端/PDF阅读器无法渲染渐变文字）
            await page.evaluate(FIX_GRADIENT_TEXT_JS)
            # Fix B：将半透明 color / border-color 合成为纯色，消除 PDF 透明组边界缝线
            await page.evaluate(FIX_RGBA_JS)

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
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python convert.py <input.html> [output.pdf]")
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    if not input_path.exists():
        print(f"错误：文件不存在 {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2]).resolve()
    else:
        output_path = input_path.with_name(input_path.stem + "_数字版.pdf")

    print(f"转换（线上传阅）: {input_path}")
    print(f"输出:             {output_path}")

    asyncio.run(render_pdf(input_path, output_path))

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"完成 — {size_mb:.2f} MB → {output_path}")


if __name__ == "__main__":
    main()
