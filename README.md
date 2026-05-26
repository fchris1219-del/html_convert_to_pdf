# HTML → PDF 转换工具集

本仓库提供两个独立的 HTML 转 PDF Claude Skill，分别针对**印刷输出**和**线上传阅**两种场景深度优化，彻底解决 Chromium PDF 渲染中的栅格化问题，保证文字和线条的矢量清晰度。

---

## 两个 Skill 对比

| 维度 | `html-pdf`（印刷版） | `html-pdf-web`（线上传阅版） |
|------|---------------------|----------------------------|
| **适用场景** | 打印、印刷、导出存档 | 在线分享、屏幕阅读、数字传阅 |
| **rgba 处理** | 白名单替换已知面板背景色 | **保留原值**（rgba 不触发栅格化） |
| **box-shadow** | 仅删除 `.page` 级别 | **全部删除**（任何层级） |
| **mix-blend-mode** | 保留 | **删除**（强制 normal） |
| **isolation** | 保留 | **删除**（强制 auto） |
| **3D transform** | 保留 | **压扁为 2D**（消除 GPU 合成层） |
| **media 类型** | print（默认） | **screen**（`emulate_media='screen'`） |
| **device_scale_factor** | 3（印刷精度，文件较大） | **2**（屏幕清晰度，文件更小） |
| **输出文件名** | `文件名_高清版.pdf` | `文件名_数字版.pdf` |

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
.page {
  box-shadow: none !important;
  border-radius: 0 !important;
}
@page { size: A4; margin: 0; }
```

`filter`、`backdrop-filter`、`will-change` 会创建独立 GPU 合成层，在 PDF 输出时被栅格化。注意：**不覆盖 `transform`**，避免破坏依赖 `translateX(-50%)` 居中的布局。

#### 4. Playwright 渲染（而非 Chrome CLI）

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

将 HTML 文件转换为**线上传阅专用 PDF**：100% 矢量输出，无任何栅格化，颜色针对屏幕阅读适配。适合数字分享、在线阅读、网络传阅。

### 触发词

`线上传阅` · `屏幕版PDF` · `传阅版` · `web pdf` · `数字版` · `在线分享` · `网络版PDF` · 明确要求无栅格化的 PDF

> **与印刷版的区别：** 如果用户只是普通 html 转 pdf（印刷/打印），请使用 `html-pdf` skill。

### 用法

```bash
python3 html-pdf-web/convert.py "/path/to/file.html"
# 输出：/path/to/file_数字版.pdf

python3 html-pdf-web/convert.py "/path/to/file.html" "/path/to/output.pdf"
# 指定输出路径
```

### 核心技术

#### 1. 保留所有 rgba 颜色值（关键设计决策）

**印刷版**对白色面板的 rgba 做白名单替换，但**线上版选择完全保留** rgba，原因：

- rgba 本身不是合成触发器，真正的触发器是 CSS 属性（filter/box-shadow 等）
- 深色背景设计若把 rgba 合成到白色，视觉会完全失真（半透明发光层变实心白块）
- 线上 PDF 阅读器（Acrobat、浏览器内嵌）对半透明层的渲染一致性差

#### 2. 更全面的 CSS 栅格化触发器清除

相比印刷版，线上版额外清除：

```css
*, *::before, *::after {
  box-shadow:     none !important;   /* 新增 */
  text-shadow:    none !important;   /* 新增 */
  mix-blend-mode: normal !important; /* 新增 */
  isolation:      auto !important;   /* 新增 */
  filter:         none !important;
  backdrop-filter: none !important;
  will-change:    auto !important;
  mask-image:     none !important;
}
```

这些属性任意一个激活，Chrome 就会为该元素创建独立 GPU 合成层，PDF 输出时位图化。

#### 3. 3D transform → 2D 压扁

`translate3d`、`translateZ`、`rotateX/Y/Z` 等会激活 3D 渲染上下文，强制创建 GPU 合成层。

处理策略：
- `translate3d(x, y, z)` → `translate(x, y)`（保留 x/y，丢弃 z）
- `translateZ(...)` → 删除（无视觉效果）
- `perspective(...)` → 删除（3D 渲染上下文）
- `rotateX/Y/Z(...)` → 删除（3D 旋转）
- `scaleZ / scale3d` → 删除

#### 4. Screen media 渲染

使用 `emulate_media='screen'` 让 `@media screen {}` 规则生效，避免 print-only 样式带来不必要的颜色/布局变化，让 HTML 原本针对屏幕设计的 CSS 规则完整生效。

#### 5. JS 运行时修复 rgba color / border-color

**根因：** Chromium PDF 渲染器对含 rgba() 的 `color` 或 `border-color` 会把该元素包进独立的 PDF 透明组。透明组内 `<br>` 换行处两段文字是独立 paint record，交接边界暴露透明组白色底色 → 白条；两组边界浮点误差 → 1px 缝线。

**修复：** 在 Playwright 渲染后、PDF 导出前，通过 `page.evaluate()` 注入 JS，遍历所有元素，将 `color` 和 `border-color` 中的 rgba 值与实际背景色（`effectiveBg`）预合成为纯色。

`effectiveBg` 策略（从元素自身向上，停在 body 前）：
1. solid backgroundColor（alpha > 0.3，直接用）
2. backgroundImage gradient → 提取第一个 alpha > 0.5 的颜色
3. gradient 所有颜色都很透明 → 视为装饰性渐变，fallback 白色
4. 找不到 → fallback 白色（不穿透 body，避免深色 navy 污染）

#### 6. SVG blur 关闭

与印刷版相同，`feGaussianBlur` 是最强力的栅格化触发器，必须关闭。

### 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 深色卡片内出现白条 | rgba() 边框触发 PDF 透明组，换行处暴露白色底色 | JS 已自动修复 color + border-color |
| 某些按钮/胶囊出现白边 | 元素有 `rgba(255,255,255,0.06)` 等近透明背景，effectiveBg 误判为白色 | 已设阈值 alpha>0.3，低于此的背景跳过向上找 |
| 元素内出现 1px 横缝 | rgba() 文字颜色建立多个透明组，边界浮点误差 | JS 已自动修复 |
| 字体显示方块 | 网络字体加载超时 | 将 `wait_for_timeout` 从 1500 改为 4000ms |
| 某些阴影效果消失 | box-shadow 被删除（栅格化触发器） | 正常，线上传阅版不保留阴影 |

---

## 依赖安装

两个 Skill 均依赖 Playwright + Chromium，脚本会**自动安装**，也可手动安装：

```bash
pip3 install playwright
python3 -m playwright install chromium
```

---

## 目录结构

```
html_convert_to_pdf/
├── README.md
├── html-pdf/              # 印刷版 Skill
│   ├── SKILL.md           # Skill 元数据与文档
│   └── convert.py         # 转换脚本
└── html-pdf-web/          # 线上传阅版 Skill
    ├── SKILL.md           # Skill 元数据与文档
    └── convert.py         # 转换脚本
```

---

## 如何选择

```
用户需要 HTML 转 PDF
        │
        ▼
   用途是什么？
   ┌────────────────────────────────────┐
   │  打印 / 印刷 / 存档                 │──▶ html-pdf（印刷版）
   │  线上分享 / 屏幕阅读 / 数字传阅     │──▶ html-pdf-web（线上传阅版）
   └────────────────────────────────────┘
```
