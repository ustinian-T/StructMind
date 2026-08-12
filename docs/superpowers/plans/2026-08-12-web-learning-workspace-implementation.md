# StructMind Web Learning Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `static/` 浏览器 Web 端升级为任务驱动、题目优先、AI 连续对话的核心学习工作台，同时保持现有 API、题库判定和全部功能入口可用。

**Architecture:** 保留现有 Vanilla JavaScript 单页应用和事件委托架构，在 `static/app.js` 内重组语义化渲染结构，在 `static/styles.css` 内建立统一设计令牌和响应式产品组件。新增静态回归测试锁定核心信息架构、来源标识、可访问性入口和移动端结构，再通过 Playwright 真实浏览器验证功能及视觉结果。

**Tech Stack:** Vanilla JavaScript ES2020+、原生 CSS、FastAPI 静态服务、Node `node:test`、Python `pytest`、Playwright CLI。

## Global Constraints

- 本阶段仅修改浏览器 Web 端，不修改 uni-app 页面。
- 保留现有 `/api/*` 接口、状态模型、题库答案判定、权限规则和 AI 流式回退逻辑。
- 不新增前端框架、网络字体、图标库或构建依赖。
- 正式题库答案、Word 作业答案和 AI 参考内容必须显示不同来源。
- 主视觉使用暖灰白、深墨色和单一氧化青绿，不使用大面积渐变、装饰 emoji 或默认玻璃卡片。
- 支持 1440×900 桌面、390×844 手机、键盘焦点、WCAG AA 和 `prefers-reduced-motion`。
- 保留并兼容工作区中现有的远程 `API_BASE` 与 AI SSE/WebSocket 流式改动。

---

### Task 1: Web 信息架构和可访问性回归契约

**Files:**
- Create: `tests/test_web_workspace.cjs`
- Modify: `static/index.html`

**Interfaces:**
- Consumes: 现有静态入口 `/styles.css` 与 `/app.js`。
- Produces: 对学习台导航、主内容跳转、正式题库来源、导师意图和移动底栏结构的静态契约。

- [ ] **Step 1: 添加会失败的静态回归测试**

测试读取 `static/index.html`、`static/app.js`、`static/styles.css`，断言存在 `skip-link`、`main-content`、学习台文案、`source-official`、`tutor-intent`、`bottom-nav`、`100dvh`、`:focus-visible` 和 `prefers-reduced-motion`。

- [ ] **Step 2: 运行测试并确认旧界面未满足契约**

Run: `node --test tests/test_web_workspace.cjs`

Expected: 至少因缺少 `skip-link` 或 `source-official` 失败。

- [ ] **Step 3: 更新 HTML 入口元信息和无障碍加载状态**

在 `static/index.html` 添加产品描述、主题色、跳到主要内容链接，并将加载文案改为“正在整理学习台”。

- [ ] **Step 4: 保留失败测试进入下一任务**

Run: `node --test tests/test_web_workspace.cjs`

Expected: HTML 相关断言通过，应用结构和样式断言继续失败。

### Task 2: 全局应用框架与设计令牌

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_web_workspace.cjs`

**Interfaces:**
- Consumes: `S.tab`、`S.user`、`S.config`、`navItems()` 和现有事件委托。
- Produces: `renderShell()` 输出的 `.app-shell`、`.sidebar`、`#main-content`、`.system-status`、`.bottom-nav` 和语义化导航。

- [ ] **Step 1: 重构应用框架标记**

将导航文案调整为学习台、题库、作业、AI 导师、复习和更多功能；合并系统状态；添加桌面账户区、移动底部导航、主内容 id 和无障碍状态文本。

- [ ] **Step 2: 重建 CSS 令牌与通用组件**

使用 OKLCH 定义背景、表面、文字、边框、强调色及语义色；统一按钮、输入、表格、焦点、加载、空状态、模态层和语义 z-index；默认取消渐变和普遍阴影。

- [ ] **Step 3: 建立桌面和移动结构**

桌面为 232px 左侧轨道与最大 1440px 主画布；手机为单列主内容、固定四项底部导航和安全区适配。

- [ ] **Step 4: 运行静态契约**

Run: `node --test tests/test_web_workspace.cjs`

Expected: 全局框架、焦点、移动端和减少动态效果断言通过。

### Task 3: 任务驱动学习台与学习画像

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_web_workspace.cjs`

**Interfaces:**
- Consumes: `S.stats`、`S.profile`、`isLoggedIn()`、`profileAccuracy()`。
- Produces: `renderDashboard()` 的 `.learning-home`、`.next-session`、`.study-agenda`、`.trust-strip` 和可执行学习建议。

- [ ] **Step 1: 替换欢迎卡与统计卡片墙**

未登录状态展示清晰产品说明、登录操作和题库可信度；已登录状态展示继续练习或薄弱项推荐主任务。

- [ ] **Step 2: 将画像改为行动信息**

展示今日计划、待复习、最近进步和最多四个章节掌握信息，不重复堆叠相同统计数字。

- [ ] **Step 3: 增加真实空状态**

无画像数据时解释如何通过第一次练习生成画像，并提供“开始练习”。

- [ ] **Step 4: 运行结构测试**

Run: `node --test tests/test_web_workspace.cjs`

Expected: 学习台任务和可信度结构断言通过。

### Task 4: 题库创建与题目中心工作区

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_web_workspace.cjs`

**Interfaces:**
- Consumes: `S.session`、`S.idx`、`S.results`、`startSession()`、`submitBankAnswer()` 和题库对象。
- Produces: `.practice-builder`、`.question-workspace`、`.question-stage`、`.question-context`、`.source-official` 和移动固定答题操作。

- [ ] **Step 1: 重构创建练习界面**

将题型、章节和题量配置合并为一条可理解工作流，实时显示正式题库可用题数，并建立清晰主次操作。

- [ ] **Step 2: 重构题目主栏**

题干宽度限制在 72 字符附近，选项提供默认、悬停、焦点、选中和禁用状态，来源标记明确写为“正式题库”。

- [ ] **Step 3: 重构进度上下文栏与结果**

右栏只显示模式、进度、题量与导航；答题结果原位展开标准答案、解析与下一题操作。

- [ ] **Step 4: 保持事件契约**

保留 `data-submit-bank`、`data-prev-question`、`data-next-question`、`data-reset-session` 和选项输入命名，避免破坏委托逻辑。

- [ ] **Step 5: 运行结构测试**

Run: `node --test tests/test_web_workspace.cjs`

Expected: 正式题库来源、题目工作区和移动答题结构断言通过。

### Task 5: 连续阅读式 AI 导师

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_web_workspace.cjs`

**Interfaces:**
- Consumes: `S.tutorMessages`、`S.tutorLoading`、`S.tutorStreamContent`、`sendTutorMsg()`、WebSocket 和 SSE 回退。
- Produces: `.tutor-workspace`、`.tutor-thread`、`.tutor-message`、`.tutor-intent`、`.tutor-composer` 和 `.tutor-context`。

- [ ] **Step 1: 将聊天卡片改为连续对话画布**

助手消息使用无气泡正文，用户消息使用轻量底色；每条助手回复显示“AI 导师”来源。

- [ ] **Step 2: 重构空状态与学习意图**

提供解释概念、检查思路、逐步提示和生成变式题四种学习意图，以及四个真实数据结构问题。

- [ ] **Step 3: 重构复合输入框**

使用多行 textarea、明确发送按钮、回车发送与 Shift+Enter 换行；流式状态使用文本光标，失败消息提供直接配置入口。

- [ ] **Step 4: 保留流式功能**

兼容现有 WebSocket、SSE 与 REST 回退，不改变 `S.tutorConvId` 的更新方式。

- [ ] **Step 5: 运行结构测试**

Run: `node --test tests/test_web_workspace.cjs`

Expected: 导师连续阅读、学习意图和 AI 来源断言通过。

### Task 6: 统一作业、讨论、复习、设置、审计与管理页面

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`

**Interfaces:**
- Consumes: 现有作业、讨论、错题、配置、审计和管理员渲染及事件属性。
- Produces: 统一 `.page-section`、`.data-list`、`.source-word`、`.source-ai`、`.settings-layout`、`.audit-table` 和紧凑管理列表。

- [ ] **Step 1: 统一来源标签**

作业答案显示“Word 作业答案”，AI 评分和解释显示“AI 参考”，正式题库维持“正式题库”。

- [ ] **Step 2: 统一辅助页面结构**

错题默认强调知识点与重做动作；配置表单分组并保留内联状态；审计表增加粘性表头；管理与讨论使用紧凑布局。

- [ ] **Step 3: 检查所有原事件属性仍存在**

使用源代码搜索确认 `data-start-assignment`、`data-grade-assignment`、`data-grade-discussion`、`data-redo-question`、`data-save-config` 和 `data-approve-user` 未丢失。

### Task 7: 自动化回归和真实浏览器验收

**Files:**
- Modify when needed: `static/app.js`
- Modify when needed: `static/styles.css`
- Test: `tests/test_web_workspace.cjs`
- Artifacts: `output/playwright/web-*.png`

**Interfaces:**
- Consumes: 本地 `python server.py` 服务和 Playwright CLI。
- Produces: 桌面与手机截图、控制台检查、功能回归结果和最终修整。

- [ ] **Step 1: 运行全部相关自动化测试**

Run: `node --test tests/test_web_workspace.cjs tests/test_unicloud_frontend.cjs tests/test_unicloud_regressions.cjs`

Run: `python -m pytest tests/test_core.py tests/test_parser.py -q`

Expected: 全部通过。

- [ ] **Step 2: 启动本地服务并打开真实浏览器**

Run: `python server.py`

Open: `http://127.0.0.1:8765`

- [ ] **Step 3: 验收桌面端**

在 1440×900 验收学习台、练习创建、题目、AI 导师和导入审计；记录控制台错误并输出截图到 `output/playwright/`。

- [ ] **Step 4: 验收手机端**

在 390×844 验收学习台、答题和 AI 导师；检查水平溢出、底部导航、固定操作与软键盘输入布局。

- [ ] **Step 5: 修整并重跑验证**

根据截图修复视觉层级、间距、溢出、焦点或控制台问题，再重复相关测试与截图。

- [ ] **Step 6: 最终目标审计**

逐项对照设计规格的功能、视觉、响应式、来源边界、可访问性和质量标准，只有证据覆盖全部项目后才完成目标。
