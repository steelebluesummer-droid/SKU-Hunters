# 03 · 视觉基础（Visual Foundations）v1.1

> 门禁文档 · 定义三层设计 token 与可访问性红线。
> v1.1 变更：①token 从「一层半」补全为 raw/semantic/component 三层；②颜色值标记为 provisional；③补对比度计算表、字重/行高/触控目标；④明确「锁定 vs 暂定」边界。

---

## 1. 设计原则

1. **不用纯红白**：MINISO 红只做品牌点缀，不铺大面积红白。
2. **品牌红 ≠ 错误红**：品牌红 `#E60012` 与错误语义 `#FF4D4F` 严格分离，不得混用。
3. **卡片白底 + 轻阴影**，内容区暖灰底，密度克制（避免卡片套卡片）。
4. **状态不只用颜色表达**：进度/状态/选中态必须有文字或图标等第二编码（色盲友好）。
5. **数据可视化优先**：洞察类信息能用图表就不用长文字。
6. **克制动效**：尊重 `prefers-reduced-motion`，只做淡入/位移，不自动播放。

---

## 2. 三层 Token 结构

```
Raw tokens（原始色板，无语义）
   ↓
Semantic tokens（语义：action/danger/surface/text，跨组件复用）
   ↓
Component tokens（组件：button/card/nav 的具体取值）
```

### 2.1 Raw tokens（原始色板 · provisional）

| Token | 值 | 备注 |
|-------|-----|------|
| `--purple-50` | `#F6F3FF` | 淡紫底 |
| `--purple-400` | `#B7A8F5` | 浅紫（仅装饰/色带/图标，不可作正文） |
| `--purple-600` | `#7A5FD0` | 主色粉紫 |
| `--purple-700` | `#6A4FC0` | 主色 hover |
| `--red-600` | `#E60012` | 品牌红（仅点缀） |
| `--gray-50` | `#F7F7F8` | 暖灰背景 |
| `--gray-200` | `#F0F0F0` | 边框/分割线 |
| `--gray-500` | `#8C8C8C` | 仅大字/装饰（**不作普通小字**） |
| `--gray-600` | `#6B6B6B` | 辅助文本（≥4.5:1） |
| `--gray-700` | `#595959` | 次级文本 |
| `--gray-900` | `#262626` | 主文本 |
| `--white` | `#FFFFFF` | 表面 |
| `--green-500` | `#52C41A` | 成功 |
| `--gold-500` | `#FAAD14` | 警告 |
| `--red-500` | `#FF4D4F` | 错误语义（**非品牌红**） |
| `--blue-500` | `#1677FF` | 信息 |

### 2.2 Semantic tokens（语义）

| Token | 值 |
|-------|-----|
| `--color-action-primary` | `var(--purple-600)` |
| `--color-action-primary-hover` | `var(--purple-700)` |
| `--color-action-primary-fg` | `var(--white)` |
| `--color-brand-accent` | `var(--red-600)` |
| `--color-danger` | `var(--red-500)` |
| `--color-success` | `var(--green-500)` |
| `--color-warning` | `var(--gold-500)` |
| `--color-info` | `var(--blue-500)` |
| `--color-surface` | `var(--white)` |
| `--color-surface-alt` | `var(--purple-50)` |
| `--color-bg` | `var(--gray-50)` |
| `--color-text` | `var(--gray-900)` |
| `--color-text-secondary` | `var(--gray-700)` |
| `--color-text-muted` | `var(--gray-600)` |
| `--color-border` | `var(--gray-200)` |

### 2.3 Component tokens（组件）

| Token | 值 |
|-------|-----|
| `--button-primary-bg` | `var(--color-action-primary)` |
| `--button-primary-fg` | `var(--color-action-primary-fg)` |
| `--card-selected-border` | `var(--color-action-primary)` |
| `--card-selected-bg` | `var(--color-surface-alt)` |
| `--nav-active-bg` | `var(--color-surface-alt)` |
| `--task-card-strip-active` | `var(--purple-400)` |
| `--task-card-strip-archived` | `#BBB` |

---

## 3. 颜色对比度表（实测 · AA 判定）

> 判定标准：普通小字（<18px 或 <14px 粗体）需 ≥4.5:1；大字（≥18px 或 ≥14px 粗体）需 ≥3:1。

| 前景 | 背景 | 对比度 | 普通小字 AA | 结论 |
|------|------|--------|------------|------|
| `#262626`（主文本） | `#FFFFFF` | 16.6:1 | ✓ | 通过 |
| `#595959`（次文本） | `#FFFFFF` | 7.0:1 | ✓ | 通过 |
| `#6B6B6B`（辅助） | `#FFFFFF` | 5.3:1 | ✓ | 通过 |
| `#8C8C8C` | `#FFFFFF` | 3.36:1 | ✗ | **禁作普通小字**，仅 ≥18px 大字或装饰 |
| `#7A5FD0`（主色） | `#FFFFFF` | 4.80:1 | ✓ | 通过（按钮白字可用） |
| `#E60012`（品牌红） | `#FFFFFF` | 4.80:1 | ✓ | 通过 |
| `#FF4D4F`（错误） | `#FFFFFF` | 3.9:1 | ✗ | 错误文字需加深或加粗/放大 |
| `#7A5FD0`（主色） | `#F6F3FF`（淡紫底） | 4.38:1 | ✗ | 主色字在淡紫底不足 4.5，需加深或加粗 |
| `#B7A8F5`（浅紫） | `#FFFFFF` | 1.9:1 | ✗ | 仅装饰，禁作文字 |

**落地约束**：
- 普通小字正文/辅助一律用 `--color-text` / `--color-text-secondary` / `--color-text-muted`（≥4.5:1）。
- `#8C8C8C` 只出现在「大字标签、时间戳装饰、图标描边」，不作为 12–13px 正文。
- 主色文字落在淡紫底时，改用 `--purple-700` 或加粗至 14px 以上，保证 ≥4.5:1。

---

## 4. 字体层级（补行高/字重）

| 层级 | 字号 | 字重 | 行高 | 用途 |
|------|------|------|------|------|
| Page Title | 20px | 600 | 28px | 页面标题 |
| Card Title | 15px | 600 | 22px | 卡片/模块标题 |
| Body | 13px | 400 | 20px | 正文 |
| Caption | 12px | 400 | 18px | 辅助说明、时间戳、来源 |

字体族：`-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif`。

---

## 5. 间距 / 圆角 / 阴影 / 触控

**间距 scale**（8px 基准）：`4 / 8 / 12 / 16 / 24 / 32`（对应 `--space-xs/sm/md/lg/xl/2xl`）。

**圆角**：`--radius-sm:4`（输入框/小标签）· `--radius-md:8`（按钮/卡片默认）· `--radius-lg:12`（主卡片/色板）· `--radius-xl:16`（概念图）。

**阴影**（轻）：
```
--shadow-card:  0 1px 2px rgba(0,0,0,0.03), 0 2px 8px rgba(0,0,0,0.06)
--shadow-hover: 0 6px 20px rgba(122,95,208,0.15)
```

**触控目标**：所有可点击控件（按钮、卡片、角标）最小触控区域 **44×44px**（移动端），桌面端至少 32×32px。

---

## 6. 关键视觉规范

| 元素 | 规范 |
|------|------|
| App 背景 | `--color-bg`（暖灰），内容面板 `--color-surface`（白） |
| 任务卡状态色带 | 左侧 3px 竖条，进行中 `--purple-400`，归档 `#BBB`（配文字/图标第二编码） |
| 机会卡选中态 | 2px `--color-action-primary` 边框 + 淡紫底 + 勾选图标（非仅颜色） |
| 概念图 | 圆角 16、高 340px，占位态渐变底 + 图标（即梦接入后换真图） |
| 色板（TrendGallery） | WGSN 式大色块：高 ≥120px，色名叙事（非 #hex） |
| 证据角标 | 灰色圆形上标 `[1]`，hover 弹出来源 Popover |
| 过程日志 | 折叠式顶部条 |

---

## 7. 可访问性红线

1. **颜色对比度**：正文/辅助 ≥4.5:1（见第 3 节表），`#8C8C8C` 不作普通小字。
2. **状态不用颜色表达**：进行中/归档/选中等必须有文字或图标辅助。
3. **键盘可达**：所有可点击卡片支持 `tabIndex` + `Enter/Space`。
4. **动效尊重 `prefers-reduced-motion`**：reduce 下禁用 transform/opacity 动画与自动播放。
5. **图表可访问性**：每个图表必须有**文本摘要**（`aria-label` + 可见 caption）或**可访问数据表**（`<table>`）替代，不能只有图形。
6. **焦点可见**：`focus-visible` 清晰 outline。
7. **触控目标**：≥44×44px（移动端）。

---

## 8. 锁定 vs 暂定（决策边界）

**本轮锁定（Stage 5 不得改）**：
- 粉紫主色方向 + MINISO 红仅点缀 + 暖灰 App 背景 / 白内容面板。
- 品牌红与错误红语义分离（`#E60012` ≠ `#FF4D4F`）。
- 三层 token 结构（raw/semantic/component）。
- 可访问性红线（对比度、键盘、`prefers-reduced-motion`、状态不只用颜色、图表文本替代）。

**暂定（provisional，留 Stage 6 定稿）**：
- 具体色值（`#7A5FD0` 等）为「功能阶段暂定值」，最终色调在真实页面出来后微调。
- 阴影强度、圆角数值、间距 scale 的最终取值。
- 字体具体字重（600 是否统一、是否引入更细字重）。

---

## 9. 不做的事

- 不引入 CSS-in-JS / Tailwind / 新 UI 框架（保持 antd 5 + 原生 CSS variables）。
- 不引入玻璃拟态、深色主题、3D 装饰。
- 不改品牌 Logo 与 MINISO 红的核心语义。
