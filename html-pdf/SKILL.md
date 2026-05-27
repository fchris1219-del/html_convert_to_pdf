---
name: html-pdf
description: >
  Converts an HTML file to a high-fidelity A4 PDF — no rasterization, no
  margins, no overflow. Use this skill whenever the user wants to export,
  convert, or save an HTML file as a PDF. Trigger on phrases like "html转pdf",
  "转成pdf", "导出pdf", "html to pdf", "把这个html转换", or whenever the user
  hands you a .html file path and asks for a PDF output.
---

# HTML → PDF 转换

## 目标

生成一个**完全矢量化、精确 A4、无留白**的 PDF：
- 文字和线条保持矢量清晰度，不出现位图栅格化
- 页面尺寸恰好是 210mm × 297mm，四边无空白
- 每个 HTML `.page` 对应 PDF 的一页，不溢出也不截断

---

## 快速上手

直接调用 `scripts/convert.py`，传入 HTML 路径即可：

```bash
python3 "<skill_dir>/scripts/convert.py" "/path/to/file.html"
# 输出到同目录的同名 .pdf 文件

python3 "<skill_dir>/scripts/convert.py" "/path/to/file.html" "/path/to/output.pdf"
# 指定输出路径
```

脚本会自动处理依赖（若未安装 Playwright 则自动 pip install）。

---

## 脚本做了什么（以及为什么这样做）

### 1. 消除栅格化：rgba → 纯色

**现象**：页面底部的某些元素出现模糊/像素化，而同样 CSS 的上方元素却正常。  
**根因**：HTML 中背景色为半透明 `rgba(R, G, B, alpha)`，当它叠在页面的渐变装饰层上时，Chrome 必须做多层合成，产生位图栅格。上方元素碰巧处于渐变衰减区（接近透明），Chrome 优化掉合成；下方元素处于渐变中心，必须合成，因此栅格化。  
**修复**：把所有 `rgba(R, G, B, A)` 用白色背景做 alpha 预合成，变成等效纯色 `#RRGGBB`（公式：`R_out = A·R + (1−A)·255`）。

### 2. 消除 SVG 模糊：stdDeviation → 0

**根因**：`<feGaussianBlur stdDeviation="N">` 强制将被滤镜覆盖的整个子树栅格化。  
**修复**：将所有 `stdDeviation` 设为 0（相当于关闭模糊，视觉效果微小）。

### 3. 注入 CSS 覆盖层

```css
*, *::before, *::after {
  filter: none !important;
  backdrop-filter: none !important;
  will-change: auto !important;
}
```

`filter`、`backdrop-filter`、`will-change` 都会创建独立的 GPU 合成层，Chrome 在 PDF 输出时会将其栅格化。覆盖为 `none` 可消除这些层。  
注意：**不覆盖 `transform`**，因为很多布局依赖 `transform: translateX(-50%)` 做居中，覆盖会破坏版式。

### 4. 强制 A4 页面尺寸

注入：
```css
@page { size: A4; margin: 0; }
.page { width: 210mm !important; max-height: 297mm !important; overflow: hidden !important; }
```

### 5. 用 Playwright 渲染，而非 Chrome 无头命令行

`chrome --print-to-pdf` 不触发 `@media print`，也不允许细粒度控制。  
Playwright 允许：
- 加载后等待字体/网络请求完成（`wait_until="networkidle"`）
- 额外等 2 秒让 JS 动画、懒加载完成
- 设置 `device_scale_factor=3` 提升位图回退质量
- 精确传递 `format="A4"`、`print_background=True`、零边距

---

## 手动调用（不用脚本时）

如果需要在对话中直接操作，可按以下顺序：

```python
import asyncio, re
from pathlib import Path
from playwright.async_api import async_playwright

# 1. 读取 HTML
html = Path("input.html").read_text(encoding="utf-8")

# 2. rgba → opaque
def rgba_to_hex(m):
    r,g,b,a = float(m[1]),float(m[2]),float(m[3]),float(m[4])
    if a >= 1.0: return f"rgb({int(r)},{int(g)},{int(b)})"
    return f"#{round(a*r+(1-a)*255):02x}{round(a*g+(1-a)*255):02x}{round(a*b+(1-a)*255):02x}"
html = re.sub(r'rgba\(\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*,\s*(\d+\.?\d*)\s*\)', rgba_to_hex, html)

# 3. SVG blur off
html = re.sub(r'stdDeviation="[^"]*"', 'stdDeviation="0"', html)

# 4. Override style
html = html.replace("</head>", """
  <style>
    *,*::before,*::after{filter:none!important;backdrop-filter:none!important;will-change:auto!important;}
    @page{size:A4;margin:0}
    .page{width:210mm!important;max-height:297mm!important;overflow:hidden!important}
  </style>
</head>""", 1)

# 5. Write temp file + render
tmp = Path("__tmp__.html"); tmp.write_text(html, "utf-8")

async def run():
    async with async_playwright() as p:
        br = await p.chromium.launch(headless=True)
        ctx = await br.new_context(viewport={"width":794,"height":1123}, device_scale_factor=3)
        pg = await ctx.new_page()
        await pg.goto(tmp.as_uri(), wait_until="networkidle")
        await pg.wait_for_timeout(2000)
        await pg.pdf(path="output.pdf", format="A4", print_background=True,
                     margin={"top":"0","right":"0","bottom":"0","left":"0"})
        await br.close()

asyncio.run(run())
tmp.unlink()
```

---

## 依赖检查

```bash
# 检查是否已安装
python3 -c "import playwright; print('OK')"

# 若未安装
pip3 install playwright
python3 -m playwright install chromium
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 某行/区域文字模糊 | rgba 半透明 + 底层渐变合成 | 脚本 Fix 1 |
| 全页模糊 | feGaussianBlur 未清除 | 脚本 Fix 2 |
| PDF 四边有白边 | @page margin 未清零 | 脚本 Fix 4 |
| 某些元素位置偏移 | 不要覆盖 transform！ | 脚本已确保不覆盖 |
| 字体未加载/方块字 | 网络字体加载超时 | 增大 `wait_for_timeout` 到 4000ms |
| 内容被截断 | .page max-height 太小 | 检查 HTML 是否正确设置 297mm |
