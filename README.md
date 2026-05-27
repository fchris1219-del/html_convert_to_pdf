# HTML → PDF 转换工具集

本仓库提供三个独立的 HTML 转 PDF Claude Skill，覆盖**印刷输出**、**线上传阅**、**超清图片版**三种场景，彻底解决 Chromium PDF 渲染中的栅格化、字体、渐变等兼容性问题。

---

## 三个 Skill 对比总览

| 维度 | `html-pdf`<br>印刷版 | `html-pdf-web`<br>线上传阅版 | `raster-pdf-export`<br>超清图片版 |
|------|---------------------|------------------------------|----------------------------------|
| **输出类型** | 矢量 PDF | 矢量 PDF | 图片嵌入 PDF（光栅） |
| **适用场景** | 打印、印刷、存档 | 在线分享、屏幕阅读、移动端 | 视觉效果优先、发光/模糊/渐变特效 |
| **文字可选中** | ✅ 是 | ✅ 是 | ❌ 否（图片） |
| **渐变文字** | 保留（印刷可渲染） | **降级为纯色**（移动端兼容） | **100% 还原**（截图保留所有效果） |
| **rgba 处理** | 白名单替换面板背景 | 保留原值 + JS 运行时合成 | 不处理（截图完整呈现） |
| **box-shadow** | 仅 .page 级别删除 | 全部删除（任何层级） | 完整保留 |
| **glow / blur 特效** | 删除 | 删除 | **完整保留** |
| **device_scale_factor** | 3（印刷精度） | 2（屏幕清晰度） | 4（超清截图，默认） |
| **文件大小** | 小 | 较小 | 大（每页为高分辨率图片） |
| **输出文件名** | `_高清版.pdf` | `_数字版.pdf` | `_图片版_超清.pdf` |

---

## Skill 一：`html-pdf`（印刷版）

**路径：** `html-pdf/`

### 用途

将 HTML 文件转换为**精确 A4、完全矢量、无留白**的高清 PDF，适合打印和印刷。

- 文字和线条保持矢量清晰度，不出现位图栅格化
- 页面尺寸恰好是 210mm × 297mm，四边无空白
- 每个 HTML `.page` 对应 PDF 的一页，不溢出也不截断

### 触发词

`html转pdf` · `转成pdf` · `导出pdf` · `html to pdf` · `把这个html转换` · 用户传入 `.html` 文件并要求 PDF 输出

### 用法

```bash
python3 html-pdf/convert.py "/path/to/file.html"
# 输出：/path/to/file_高清版.pdf

python3 html-pdf/convert.py "/path/to/file.html" "/path/to/output.pdf"
# 指定输出路径
```

### 核心技术

#### 1. 定向 rgba → 纯色（白名单替换）

**根因：** HTML 中背景色为半透明 `rgba(R,G,B,alpha)`，叠在渐变装饰层上时，Chrome 做多层合成产生位图栅格。

**修复：** 仅替换已知会触发栅格化的面板背景色（白名单约 15 条），将高 alpha 值的白色/冷白色半透明背景合成为等效纯色（公式：`R_out = A·R + (1-A)·255`）。

> **为什么用白名单而非全量替换？** 全量替换会破坏渐变装饰效果，完全改变视觉设计。

#### 2. SVG blur 关闭（stdDeviation → 0）

`<feGaussianBlur>` 是最强力的栅格化触发器，会强制将滤镜覆盖的整个子树位图化。将 `stdDeviation` 设为 0 相当于关闭模糊，视觉变化极小。

#### 3. CSS 覆盖层注入

```css
*, *::before, *::after {
  filter: none !important;
  backdrop-filter: none !important;
  will-change: auto !important;
  mask-image: none !important;
}
.page { box-shadow: none !important; border-radius: 0 !important; }
@page { size: A4; margin: 0; }
```

注意：**不覆盖 `transform`**，避免破坏依赖 `translateX(-50%)` 居中的布局。

#### 4. Playwright 渲染

- `wait_until="networkidle"` + 额外等待 2s，确保字体/懒加载完成
- `device_scale_factor=3` 提升位图回退质量
- 精确传递 `format="A4"`、`print_background=True`、零边距

### 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 某行/区域文字模糊 | rgba 半透明 + 底层渐变合成 | 脚本 Fix 1（白名单替换） |
| 全页模糊 | feGaussianBlur 未清除 | 脚本 Fix 2（stdDeviation=0） |
| PDF 四边有白边 | @page margin 未清零 | 脚本 Fix 3 CSS |
| 某些元素位置偏移 | 不要覆盖 transform！ | 脚本已确保不覆盖 |
| 字体未加载/方块字 | 网络字体加载超时 | 将 `wait_for_timeout` 改为 4000ms |
| 内容被截断 | .page max-height 太小 | 检查 HTML 是否正确设置 297mm |

---

## Skill 二：`html-pdf-web`（线上传阅版）

**路径：** `html-pdf-web/`

### 用途

将 HTML 文件转换为**线上传阅专用 PDF**：100% 矢量输出，无任何栅格化，颜色针对屏幕阅读适配，兼容移动端 PDF 阅读器。

### 触发词

`线上传阅` · `屏幕版PDF` · `传阅版` · `web pdf` · `数字版` · `在线分享` · `网络版PDF` · 明确要求无栅格化的 PDF

> 如果用户只是普通 html 转 pdf（印刷/打印），请使用 `html-pdf` skill。

### 用法

```bash
python3 html-pdf-web/convert.py "/path/to/file.html"
# 输出：/path/to/file_数字版.pdf

python3 html-pdf-web/convert.py "/path/to/file.html" "/path/to/output.pdf"
# 指定输出路径
```

### 核心技术

#### Fix A：渐变文字 → 纯色（移动端兼容）

**根因：** CSS 渐变文字通过 `background-clip:text` + `-webkit-text-fill-color:transparent` 实现。PDF 渲染器和移动端阅读器（iOS Books、Android 内置 PDF）无法解析这种渐变剪切路径，表现为文字完全不可见（透明）或显示为黑色方块。

**修复：** 在 Playwright 渲染后通过 JS 遍历所有元素，检测渐变文字并从 `backgroundImage` 渐变中提取第一个非透明颜色，设为纯色文字，同时清除 `background-clip` 和渐变背景。

```
检测条件：webkitTextFillColor === transparent AND backgroundClip === text
颜色提取：渐变中第一个 alpha > 0.3 的颜色 → 或 hex 颜色 → 或 fallback 白色
```

#### Fix B：rgba color / border-color → 纯色

**根因：** Chromium PDF 渲染器对含 rgba() 的 `color` 或 `border-color` 会把该元素包进独立的 PDF 透明组。透明组内 `<br>` 换行处交接边界暴露白色底色 → 白条；两组边界浮点误差 → 1px 缝线。

**修复：** JS 遍历所有元素，将 `color` 和 `border-color` 中的 rgba 值与实际背景色（`effectiveBg`）预合成为纯色。

#### 更全面的 CSS 栅格化触发器清除

相比印刷版，线上版额外清除：

```css
*, *::before, *::after {
  box-shadow:      none !important;   /* 新增 */
  text-shadow:     none !important;   /* 新增 */
  mix-blend-mode:  normal !important; /* 新增 */
  isolation:       auto !important;   /* 新增 */
  filter:          none !important;
  backdrop-filter: none !important;
  will-change:     auto !important;
  mask-image:      none !important;
}
```

#### 3D transform → 2D 压扁

`translate3d`、`translateZ`、`rotateX/Y/Z` 等会激活 3D 渲染上下文，强制创建 GPU 合成层。处理策略：
- `translate3d(x, y, z)` → `translate(x, y)`
- `translateZ / rotateX/Y/Z / perspective / scaleZ / scale3d` → 删除

#### Screen media 渲染

`emulate_media='screen'` 让 `@media screen {}` 规则完整生效，避免 print-only 样式带来不必要的颜色/布局变化。

### 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 移动端渐变文字不可见 | PDF 阅读器不支持 background-clip:text | Fix A 已自动降级为纯色 |
| 深色卡片内出现白条 | rgba() 边框触发 PDF 透明组，换行处暴露白色底色 | Fix B 已自动修复 |
| 某些按钮/胶囊出现白边 | 元素有极低 alpha 的半透明背景，effectiveBg 误判 | 已设阈值 alpha>0.3，低于此跳过向上找 |
| 元素内出现 1px 横缝 | rgba() 文字颜色建立多个透明组，边界浮点误差 | Fix B 已自动修复 |
| 字体显示方块 | 网络字体加载超时 | 将 `wait_for_timeout` 从 1500 改为 4000ms |
| 某些阴影效果消失 | box-shadow 被删除（栅格化触发器） | 正常，线上传阅版不保留阴影 |

---

## Skill 三：`raster-pdf-export`（超清图片版）

**路径：** `raster-pdf-export/`

### 用途

将 HTML 页面**逐页截图**后封装为 PDF：每一页都是高分辨率位图，完整保留浏览器渲染效果，包括发光、渐变、模糊、光效等复杂视觉特效。

适合：白皮书、单页海报、演示文稿、设计感强的视觉稿，任何"视觉效果优先于文字可选中"的场景。

### 触发词

`图片版PDF` · `扫描件效果` · `逐页截图再封PDF` · `视觉效果完整保留` · 矢量版丢失发光/渐变/模糊时

### 用法

```bash
# 默认超清（scale=4）
python3 raster-pdf-export/scripts/export_raster_pdf.py --scale 4 /path/to/file.html

# 多文件批量
python3 raster-pdf-export/scripts/export_raster_pdf.py --scale 4 /path/to/a.html /path/to/b.html

# 指定输出目录
python3 raster-pdf-export/scripts/export_raster_pdf.py --scale 4 --output-dir /path/to/out/ /path/to/file.html

# 保留中间截图文件
python3 raster-pdf-export/scripts/export_raster_pdf.py --scale 4 --keep-pngs /path/to/file.html
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--scale` | 4 | Chromium device_scale_factor，决定截图分辨率（4 = 超清） |
| `--jpeg-quality` | 95 | 嵌入 PDF 的图片质量（1-100） |
| `--wait-ms` | 1200 | 加载完成后额外等待时间（ms），字体/动画稳定用 |
| `--selector` | `.page` | 每页元素的 CSS 选择器 |
| `--keep-pngs` | 否 | 保留中间 PNG 截图文件 |
| `--output-dir` | 当前目录 | 输出 PDF 的目录 |

### 核心技术

#### 截图流程

1. Playwright + Chromium 打开本地 HTML 文件
2. `emulate_media('screen')` 确保 screen CSS 规则生效
3. `wait_until="networkidle"` + `document.fonts.ready` 等待字体和网络资源加载完成
4. 注入 CSS 冻结动画/过渡效果（`transition: none`、`animation: none`），保证截图稳定
5. 逐个对 `.page` 元素调用 `screenshot()`，生成 PNG
6. 用 Pillow 将所有 PNG 合并为单个 PDF

#### 与矢量版的核心差异

矢量版（html-pdf / html-pdf-web）必须**删除** filter、box-shadow、blend-mode 等属性才能避免栅格化；而图片版**保留所有这些效果**，因为最终输出本身就是截图，不存在 PDF 矢量渲染的问题。

### 依赖

```bash
pip3 install playwright pillow
python3 -m playwright install chromium
```

### 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 找不到页面（RuntimeError） | HTML 中没有 `.page` 元素 | 用 `--selector` 指定实际的页面容器选择器 |
| 字体未加载/方块字 | 字体加载超时 | 增大 `--wait-ms`（如 3000） |
| 文件过大 | scale=4 每页图片很大 | 降低 `--scale 3` 或 `--jpeg-quality 85` |
| 截图有动画帧残影 | CSS 动画未完全冻结 | 增大 `--wait-ms` 让动画先跑完再截图 |

---

## 如何选择

```
用户需要 HTML 转 PDF
        │
        ├── 需要打印 / 印刷 / 存档？
        │       └──▶ html-pdf（印刷版）
        │
        ├── 线上分享 / 移动端阅读 / 渐变文字多？
        │       └──▶ html-pdf-web（线上传阅版）
        │
        └── 有发光/模糊/复杂特效，视觉效果最重要？
                └──▶ raster-pdf-export（超清图片版）
```

---

## 依赖安装

所有 Skill 均依赖 Playwright + Chromium，`raster-pdf-export` 额外需要 Pillow：

```bash
pip3 install playwright pillow
python3 -m playwright install chromium
```

脚本在检测到 Playwright 未安装时会**自动执行安装**。

---

## 目录结构

```
html_convert_to_pdf/
├── README.md
├── html-pdf/                          # 印刷版 Skill
│   ├── SKILL.md
│   └── convert.py
├── html-pdf-web/                      # 线上传阅版 Skill
│   ├── SKILL.md
│   └── convert.py
└── raster-pdf-export/                 # 超清图片版 Skill
    ├── SKILL.md
    └── scripts/
        └── export_raster_pdf.py
```
