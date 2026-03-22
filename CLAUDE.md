# CLAUDE.md — 给 Claude Code 的实现指令

## 你的任务

根据 PRD.md 和 TDD.md，实现完整项目，包括：
1. `crew_sender.py` — 微信自动化引擎
2. `app.py` — Flask Web 后端
3. `templates/index.html` — 航海控制台前端
4. `static/style.css` + `static/app.js` — 前端样式与逻辑
5. `start.command` — macOS 双击启动脚本

---

## 实现前必须做的事

1. 先完整阅读 `PRD.md` 和 `TDD.md`，不得跳过
2. 严格按照 TDD.md 的模块划分和函数签名实现，不得自行重构结构
3. 不得在没有讨论的情况下引入 TDD.md 未提到的第三方库

---

## 文件结构

```
automessage-wechat/
├── crew_sender.py
├── app.py
├── start.command             # chmod +x，macOS 双击可用
├── templates/
│   └── index.html
├── static/
│   ├── style.css
│   └── app.js
├── crew_today.csv
├── requirements.txt          # 含 flask>=3.0.0
├── assets/
│   └── README_assets.md
├── logs/
│   └── .gitkeep
├── docs/
│   ├── PRD.md
│   ├── TDD.md
│   └── feature_dev_list.md
├── .env.example
├── .gitignore
└── README.md
```

---

## crew_sender.py 实现规范

### 配置区

脚本顶部必须有独立的配置区，每个变量附一行中文注释：

```python
CHECKINS_REQUIRED       = 12      # 打卡满多少次可上岸
SKIP_NAMES: list[str]   = []      # CLI 模式固定跳过名单
DEFAULT_CSV             = "crew_today.csv"
SEND_INTERVAL           = 4.0     # 每条发完后冷却秒数
SEARCH_WAIT             = 1.5     # 粘贴姓名后等待搜索结果秒数
OPEN_WAIT               = 1.2     # 点击联系人后等待对话窗口秒数
LOCATE_CONFIDENCE       = 0.85    # locateOnScreen 置信度阈值
SENT_VARIANCE_THRESHOLD = 12.0    # 输入框清空检测方差阈值
```

### 必须实现的函数（签名不得改变）

```python
def load_csv(path: str) -> list[dict]
def generate_message(name: str, checkins: int, comment: str) -> str
def generate_all_messages(crew_data: list[dict]) -> list[dict]
def preview_and_confirm(crew_messages: list[dict], initial_skip: set) -> set
def get_wechat_window() -> tuple[int, int, int, int]
def activate_wechat() -> None
def open_search() -> None
def search_contact(wechat_name: str) -> None   # 用微信名称搜索
def detect_contact_in_results() -> Literal["ok", "not_found", "multiple"]
def click_contact(contacts_label_pos) -> None
def verify_window_title(name: str) -> bool
def send_message(message: str, wx_window: tuple, paste_only: bool = False) -> None
def verify_sent(wx_window: tuple) -> bool
def send_one(wechat_name: str, name: str, message: str, wx_window: tuple,
             safe_mode: bool = False) -> None  # 增加 wechat_name 参数
def save_log(path: Path, results: list[dict]) -> None
def save_messages_to_csv(path: str, crew_messages: list[dict]) -> None
def run(csv_path: str, dry_run: bool = False, safe: bool = False) -> None
```

### CSV 列说明

| 列名 | 用途 |
|------|------|
| `微信名称` | 微信搜索框输入（与通讯录备注名完全一致） |
| `姓名` | 消息称谓：`hello，明烨` 及日志记录 |
| `打卡次数` | AI 生成消息的参数 |
| `评价` | AI 生成消息的参数 |
| `message`（可选） | 已生成的消息，存在且非空则跳过 AI |

Excel 导出末尾的多余空列（`,,,,,`）在 `load_csv` 中过滤：
```python
rows = [{k: v for k, v in row.items() if k.strip()} for row in rows]
```

### CSV 消息列处理

`load_csv` 读取 CSV 时，若存在 `message` 列且值非空，则 `generate_all_messages` 跳过该行的 AI 调用：

```python
def generate_all_messages(crew_data: list[dict]) -> list[dict]:
    for row in crew_data:
        if row.get("message", "").strip():  # 已有消息，直接复用
            message = row["message"].strip()
        else:                               # 无消息，调用 AI
            message = generate_message(row["姓名"], ...)
        results.append({
            "wechat_name": row["微信名称"].strip(),
            "name": row["姓名"].strip(),
            ...
        })
```

### CLI 参数（完整列表）

```python
parser.add_argument("csv", nargs="?", default=DEFAULT_CSV)
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--safe", action="store_true")
parser.add_argument("--no-confirm", action="store_true")   # 跳过终端确认
parser.add_argument("--skip", default="")                   # 逗号分隔跳过名单
parser.add_argument("--json-progress", action="store_true") # JSON Lines 输出模式
```

### --json-progress 模式

开启时，进度输出替换为 JSON Lines，供 Flask SSE 解析。不得在此模式下输出任何非 JSON 文本：

```python
def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)

# 用法示例
_emit({"type": "start", "total": 30})
_emit({"type": "progress", "index": 1, "total": 30, "name": "张海涛", "status": "sent"})
_emit({"type": "done", "sent": 28, "skipped": 2, "failed": 0})
```

### FailError

```python
class FailError(Exception):
    pass
```

### 键盘操作必须通过 AppleScript

所有快捷键必须通过 AppleScript 发送，不得使用 `pyautogui.hotkey()`、`pyautogui.press()`：

```python
def _wechat_hotkey(key: str, modifier: str = "command") -> None:
    script = (
        f'tell application "System Events" to tell process "WeChat" '
        f'to keystroke "{key}" using {modifier} down'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)

def _wechat_keycode(code: int) -> None:
    script = (
        f'tell application "System Events" to tell process "WeChat" '
        f'to key code {code}'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
```

Key code 对照：Return=36，Escape=53，F=3，A=0，V=9

### detect_contact_in_results 关键细节

- 截一次全屏截图，复用同一张图完成所有 locate 调用
- `group_chats_label.png` 不存在时：`region_bottom = contacts_pos.top + 200`
- contacts_region 宽度使用 500px（不得用 300px，否则 ⓘ 按钮被截断）
- ImageNotFoundException 用 `type(e).__name__` 判断，不得用 `isinstance`

### verify_sent

- 使用 numpy 灰度方差，阈值 `SENT_VARIANCE_THRESHOLD = 12.0`
- 函数内附注释说明校准方法

### save_log 调用时机

以下三种情况必须调用：
1. 所有发送正常完成后
2. 遇到 FailError 停机前
3. 捕获到 KeyboardInterrupt 后

---

## app.py 实现规范

### 基本结构

```python
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import os, csv, json, subprocess, threading, time, signal
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
app = Flask(__name__)

last_heartbeat = time.time()
_send_process: subprocess.Popen | None = None
```

### 心跳 Watchdog（必须实现）

```python
def _watchdog():
    while True:
        time.sleep(5)
        if _send_process is None:
            if time.time() - last_heartbeat > 20:
                os.kill(os.getpid(), signal.SIGTERM)

threading.Thread(target=_watchdog, daemon=True).start()
```

### AI 客户端（模块级）

```python
_ai_client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
_ai_model = os.environ.get("OPENAI_MODEL", "deepseek-v3-0324")
```

使用与 crew_sender.py 完全相同的 SYSTEM_PROMPT（提取为共用常量或直接复制）。

### API 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 返回 index.html |
| POST | `/api/heartbeat` | 前端心跳 |
| POST | `/api/load-csv` | multipart 文件上传，返回解析结果 |
| POST | `/api/generate` | 单条 AI 生成 `{name,checkins,comment}` → `{message}` |
| GET | `/api/generate-all` | SSE：逐条生成，query param `crew`（JSON 字符串） |
| POST | `/api/save-csv` | 写回 CSV |
| GET | `/api/execute` | SSE：运行 crew_sender.py |
| POST | `/api/stop` | 终止子进程 |

### /api/execute SSE 实现

```python
@app.route('/api/execute')
def execute():
    csv_path = request.args.get('filepath')
    mode     = request.args.get('mode', 'normal')
    skip     = request.args.get('skip', '')

    cmd = ['python', 'crew_sender.py', csv_path,
           '--no-confirm', '--json-progress']
    if mode == 'safe':
        cmd.append('--safe')
    elif mode == 'dry-run':
        cmd.append('--dry-run')
    if skip:
        cmd += ['--skip', skip]

    def stream():
        global _send_process
        _send_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=Path(__file__).parent
        )
        for line in _send_process.stdout:
            line = line.strip()
            if line:
                yield f"data: {line}\n\n"
        _send_process.wait()
        _send_process = None
        yield "data: STREAM_END\n\n"

    return Response(stream_with_context(stream()), mimetype='text/event-stream')
```

### 启动配置

```python
if __name__ == "__main__":
    app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)
```

---

## 前端实现规范（航海控制台风格）

### style.css 色彩变量（必须使用）

```css
:root {
    --bg-primary:    #040d1a;
    --bg-secondary:  #071428;
    --bg-card:       rgba(7, 20, 45, 0.85);
    --accent-teal:   #00d4aa;
    --accent-blue:   #1d6fa4;
    --accent-amber:  #f59e0b;
    --accent-red:    #ef4444;
    --border-glow:   rgba(0, 212, 170, 0.25);
    --text-primary:  #cbd5e1;
    --text-secondary:#64748b;
    --text-bright:   #e2e8f0;
    --font-mono:     'JetBrains Mono', 'Fira Code', monospace;
}
```

### 背景效果

- 渐变底色：`linear-gradient(135deg, #040d1a 0%, #071428 100%)`
- 极细网格线：用 CSS background-image repeating-linear-gradient，颜色 `rgba(0,212,170,0.04)`，间距 40px
- 右下角雷达：纯 CSS `@keyframes` 旋转扫描线，透明度 0.12，不影响交互

### 页面布局

```html
<body>
  <header class="app-header">...</header>
  <main class="app-main">
    <aside class="control-panel">...</aside>
    <section class="mission-table">...</section>
  </main>
  <footer class="console-footer">...</footer>
</body>
```

### 控制面板内容

1. CSV 文件选择区（支持 `<input type="file">` + 拖拽）
2. 模式选择（三个 radio button 卡片：正式发送 / 安全模式 / Dry-Run）
3. 操作按钮组：「全部生成」「保存 CSV」「执行」「停止」

### 任务表格列

| # | 状态 | 姓名 | 打卡次数 | 消息预览（50字截断） | 操作 |
|---|------|------|---------|---------------------|------|
| checkbox 跳过 | 状态徽章 | 文本 | 数字 | 截断文本 | 生成 / 编辑 |

- 点击行展开：内联 `<textarea>` 显示完整消息，可直接编辑
- 展开状态下显示「重新生成」「收起」按钮

### 状态徽章样式

```css
.badge-generating { animation: pulse-teal 1.5s infinite; }
.badge-sending    { animation: pulse-blue 1.5s infinite; }
.badge-sent       { color: #22c55e; }
.badge-fail       { color: var(--accent-red); }
.badge-skipped    { color: var(--accent-amber); }
```

### Console 日志区

- 高度 200px，`overflow-y: auto`，自动滚动到底部
- 背景 `#000a14`，文字颜色 `#00d4aa`，字体 monospace 14px
- 解析 JSON Lines 并格式化：
  - `sending` → `⏳ [01/30] 张海涛 发送中...`
  - `sent`    → `✅ [01/30] 张海涛 已发送`
  - `fail`    → `❌ [01/30] 张海涛 失败: 原因`
  - `done`    → `━━━ 完成 已发 N / 跳过 N / 失败 N ━━━`

### 心跳实现

```javascript
let heartbeatInterval = setInterval(() => {
    fetch('/api/heartbeat', { method: 'POST' });
}, 5000);

document.addEventListener('visibilitychange', () => {
    clearInterval(heartbeatInterval);
    const interval = document.hidden ? 15000 : 5000;
    heartbeatInterval = setInterval(() => {
        fetch('/api/heartbeat', { method: 'POST' });
    }, interval);
});
```

---

## start.command 实现

```bash
#!/bin/bash
cd "$(dirname "$0")"
nohup python app.py > logs/app.log 2>&1 &
sleep 1
open http://localhost:5001
```

创建后立即执行 `chmod +x start.command`。

---

## 不允许的实现方式

- ❌ 不得使用 `pyautogui.hotkey()`、`pyautogui.press()` 操作微信键盘
- ❌ 不得使用 `pyautogui.typewrite()` 输入中文
- ❌ 不得使用固定屏幕坐标（必须基于 `get_wechat_window()` 计算偏移）
- ❌ FAIL 后不得继续发送剩余联系人
- ❌ 不得在 --json-progress 模式下输出非 JSON 文本
- ❌ Flask 服务不得监听 0.0.0.0（仅 127.0.0.1）
- ❌ app.js 不得引入任何第三方 JS 框架（Vue/React/jQuery）

---

## 完成自检清单

### crew_sender.py
- [ ] CSV 有 message 列时跳过 AI 生成
- [ ] --json-progress 输出纯 JSON Lines，无其他文本
- [ ] --no-confirm 跳过终端确认
- [ ] --skip 参数正确合并到跳过集合
- [ ] FAIL 即停，不跳过继续
- [ ] detect_contact_in_results region 宽度 500px
- [ ] 所有键盘操作通过 AppleScript 发送
- [ ] Ctrl+C 必定保存日志

### app.py
- [ ] 心跳 Watchdog：无任务时 20 秒无心跳自动退出
- [ ] /api/execute 正确流转 JSON Lines 到 SSE
- [ ] /api/save-csv 正确写入 message 列
- [ ] /api/generate-all SSE 逐条推送
- [ ] 仅监听 127.0.0.1:5001

### 前端
- [ ] SSE 进度实时显示在 Console 区，自动滚底
- [ ] 心跳每 5 秒发送，页面隐藏时 15 秒
- [ ] 「执行」发送中禁用，完成后恢复
- [ ] 表格行展开显示可编辑 textarea
- [ ] 状态徽章动画正常

### 其他
- [ ] start.command 有执行权限
- [ ] requirements.txt 含 flask>=3.0.0
