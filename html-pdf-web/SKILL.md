---
name: html-pdf-web
description: >
  把 HTML 文件转换为线上传阅专用 PDF：100% 矢量输出，无任何栅格化，
  颜色针对屏幕阅读适配。当用户提到"线上传阅""屏幕版 PDF""传阅版""web pdf"
  "数字版""在线分享""网络版 PDF"，或明确要求无栅格化的 PDF 时使用本 skill。
  如果用户只是普通 html 转 pdf（印刷/打印），请使用 html-pdf skill。
---

# HTML → 线上传阅 PDF

## 与印刷版（html-pdf）的区别

| 维度 | html-pdf（印刷） | html-pdf-web（线上传阅） |
|------|-----------------|------------------------|
| rgba 处理 | 白名单替换已知面板背景 | **保留原值**（rgba 不是栅格化触发器） |
| box-shadow | 保留（.page 级别删除） | **全部删除**（任何层级） |
| mix-blend-mode | 保留 | **删除**（normal） |
| isolation | 保留 | **删除**（auto） |
| 3D transform | 保留 | **压扁为 2D**（translateZ 等删除） |
| media 类型 | print（默认） | **screen**（`emulate_media='screen'`） |
| device_scale_factor | 3（印刷精度） | **2**（屏幕清晰度，文件更小） |
| 输出后缀 | 同名 .pdf | **_web.pdf** |

---

## 快速上手

```bash
python3 "<skill_dir>/convert.py" "/path/to/file.html"
# 输出 /path/to/file_web.pdf

python3 "<skill_dir>/convert.py" "/path/to/file.html" "/path/to/output.pdf"
# 指定输出路径
```

---

## 技术原理：为什么这样处理

### 1. 全量 rgba → 纯色（Fix 1）

**印刷版**用白名单是为了保留装饰性渐变的半透明效果（视觉差异大）。  
**线上版**选择全量替换，原因：
- 线上 PDF 阅读器（Acrobat、浏览器内嵌）对半透明层的渲染一致性差
- Chromium 在 PDF 输出时，任何半透明元素与底层非纯色叠加都会产生合成层 → 栅格化
- 全量替换后颜色外观不变（公式：`out = α·color + (1−α)·255`），只失去"透明感"，对传阅无影响

### 2. box-shadow / mix-blend-mode / isolation 全部删除（Fix 4 CSS）

这三个属性会创建独立的 GPU 合成层。在 Chromium 的 PDF 渲染路径中，合成层 = 位图栅格。
删除阴影对线上传阅视觉影响极小，但能确保所有文字和线条保持矢量清晰度。

### 3. 3D transform → 2D（Fix 3）

`translate3d(x,y,z)`、`translateZ()`、`rotateX/Y()` 等会激活 3D 渲染上下文，
强制 Chrome 为元素创建合成层。压扁为 `translate(x,y)` 后布局不变，合成层消失。

### 4. `emulate_media('screen')`（Playwright 参数）

默认情况下 Playwright 的 `page.pdf()` 使用 print media，会触发 `@media print {}` 规则。
线上版切换为 screen media，让 HTML 原本针对屏幕设计的 CSS 规则生效，
避免 print-only 样式带来不必要的颜色/布局变化。

### 5. SVG blur → 0（Fix 2）

与印刷版相同。`feGaussianBlur` 是最强力的栅格化触发器，必须关闭。

---

## 依赖

```bash
python3 -c "import playwright; print('OK')"
# 若未安装，脚本会自动 pip install playwright && playwright install chromium
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 深色卡片内出现白条 | `rgba()` 边框触发 PDF 透明组，换行处暴露白色底色 | JS 已自动修复 color + border-color |
| 某些按钮/胶囊出现白边 | 元素自身有 `rgba(255,255,255,0.06)` 等近透明背景，`effectiveBg` 误以为是白色 | 已设阈值 alpha>0.3，低于此的背景跳过向上找 |
| 元素内出现 1px 横缝 | `rgba()` 文字颜色建立多个透明组，边界浮点误差 | JS 已自动修复 |
| 字体显示方块 | 网络字体加载超时 | 将 `wait_for_timeout` 从 1500 改为 4000 |
| 某些阴影效果消失 | box-shadow 被删除（栅格化触发器） | 正常，线上传阅版不保留阴影 |
