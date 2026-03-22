# Feature Development List

## 开发状态说明

| 状态 | 含义 |
|------|------|
| 🟡 规划中 | 需求已确认，尚未开始实现 |
| 🔵 开发中 | 正在实现 |
| ✅ 已完成 | 功能已实现并验证 |
| ⏸ 暂停 | 暂时搁置 |
| ❌ 取消 | 已决定不做 |

---

## F-003 本地 Web 控制台（航海控制台风格）

**状态**：🟡 规划中
**优先级**：高
**关联 PRD**：F3（预览确认）、F8（消息持久化）、F9（Web 控制台）、F10（服务生命周期）

### 需求描述

将现有 CLI 工具封装为本地 Web 应用，提供可视化的消息预览、编辑、执行界面。

### 新增文件

- `app.py` — Flask Web 后端，提供 REST API + SSE
- `templates/index.html` — 单页前端，航海控制台视觉风格
- `static/style.css` — 深海蓝黑配色，玻璃态卡片，雷达背景动效
- `static/app.js` — 原生 ES2022，无框架
- `start.command` — macOS 双击启动脚本

### 实现步骤

1. [ ] 更新 `requirements.txt`，添加 `flask>=3.0.0`
2. [ ] 实现 `app.py`：
   - Flask 应用初始化与路由
   - 心跳 Watchdog（20 秒无心跳自动退出）
   - `/api/load-csv`：CSV 上传与解析
   - `/api/generate`：单条 AI 生成
   - `/api/generate-all`：SSE 批量生成
   - `/api/save-csv`：写回 CSV message 列
   - `/api/execute`：SSE 流转 crew_sender.py 进度
   - `/api/stop`：终止子进程
3. [ ] 实现前端（`templates/index.html` + `static/`）：
   - 航海控制台视觉系统（色彩、字体、背景动效）
   - 控制面板（CSV 导入、模式选择、操作按钮）
   - 任务表格（展开编辑、状态徽章动画）
   - Console 日志区（SSE 实时输出，JSON 格式化）
   - 心跳机制（5s，隐藏时 15s）
4. [ ] 创建 `start.command` 并设置执行权限
5. [ ] 端到端验证（导入 CSV → 生成 → 编辑 → 保存 → 执行）

### 关键设计决策

- 服务仅监听 `127.0.0.1:5001`，不对外暴露
- 双击 `start.command` → 后台启动 Flask → 浏览器自动打开
- 关闭浏览器 → 心跳停止 → 20 秒内服务自动退出
- 执行过程中不退出（等待当前发送完成）

---

## F-002 消息持久化到 CSV

**状态**：🟡 规划中
**优先级**：高
**关联 PRD**：F8

### 需求描述

CSV 增加 `message` 列，存储 AI 生成或人工编辑后的最终文案，实现双重可追溯。

### 实现步骤

1. [ ] 修改 `crew_sender.py` 的 `load_csv`：支持读取可选的 `message` 列
2. [ ] 修改 `generate_all_messages`：`message` 非空时跳过 AI 调用
3. [ ] 新增 `save_messages_to_csv(path, crew_messages)`：写回 CSV message 列
4. [ ] 更新 `crew_today.csv` 示例数据，展示 message 列格式

---

## F-001 初始版本 CLI 自动化发送

**状态**：✅ 已完成
**完成日期**：2026-03-22

### 功能描述

- 读取 CSV，调用七牛云 DeepSeek API 生成消息
- 终端预览确认后，通过 pyautogui + AppleScript 自动操作微信发送
- 支持 `--dry-run`（仅检测不发送）和 `--safe`（粘贴不按 Enter）模式
- FAIL 即停机制，发送日志保存到 logs/
- 三张 PNG 模板用于 locateOnScreen 定位微信搜索结果

### 已解决的关键技术问题

- macOS IME 拦截 pyautogui.hotkey → 改用 AppleScript keystroke 绕过
- pyscreeze.ImageNotFoundException ≠ pyautogui.ImageNotFoundException → 用 type(e).__name__ 判断
- contacts_region 宽度 300px 不够 → 改为 500px
- AppleScript 整数拼接返回 list → 加 `as text` 强制转换
- WeChat 4.x AXTitle 始终为 "Weixin" → 改为截图检测 contacts_label 消失
