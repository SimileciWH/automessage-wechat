# TDD — 船员打卡消息自动发送系统

## 运行环境

| 项目 | 值 |
|------|----|
| OS | macOS |
| 屏幕分辨率 | 1920 × 1080（非 Retina，像素与逻辑坐标 1:1） |
| 微信版本 | 4.1.5.240（桌面版） |
| Python | 3.10+ |

---

## 项目结构

```
automessage-wechat/
├── crew_sender.py            # 微信自动化引擎（纯自动化，不含AI生成）
├── app.py                    # Flask Web 后端
├── start.command             # macOS 双击启动脚本
├── templates/
│   └── index.html            # 单页前端（航海控制台风格）
├── static/
│   ├── style.css             # 航海控制台样式
│   └── app.js                # 前端逻辑
├── crew_today.csv            # 每天从 Excel 导出（含 message 列）
├── requirements.txt
├── assets/
│   ├── contacts_label.png
│   ├── info_button.png
│   └── group_chats_label.png
├── logs/
│   └── log_YYYYMMDD_HHMMSS.json
├── docs/
│   ├── PRD.md
│   ├── TDD.md
│   └── feature_dev_list.md
├── .env                      # 不提交 git
├── .env.example
├── .gitignore
├── CLAUDE.md
└── README.md
```

---

## 依赖

```
openai>=1.0.0           # OpenAI 兼容 SDK，接入七牛云 DeepSeek API
python-dotenv>=1.0.0    # 从 .env 加载 API 配置
pyautogui>=0.9.54
pyperclip>=1.8.2
pillow>=10.0.0
numpy>=1.24.0           # verify_sent 方差检测
opencv-python>=4.8.0    # locateOnScreen confidence 参数依赖
flask>=3.0.0            # Web 后端
```

---

## 环境变量（.env 文件）

```
OPENAI_BASE_URL=https://api.qnaigc.com/v1
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=deepseek-v3-0324
```

---

## CSV 数据格式

### 输入格式（Excel 导出）

| 微信名称 | 姓名 | 打卡次数 | 评价 |
|---------|------|---------|------|
| [老][2026Q1][AI 编程] 好运-明烨 | 明烨 | 8 | 今天记录了航行数据，整理了报表 |

- `微信名称`：用于微信搜索框输入，与微信通讯录备注名完全一致
- `姓名`：消息称谓，用于 `hello，明烨` 和日志记录
- Excel 导出时末尾多余空列（`,,,,,,`）自动过滤

### 扩展格式（含生成消息）

| 微信名称 | 姓名 | 打卡次数 | 评价 | message |
|---------|------|---------|------|---------|
| [老][2026Q1][AI 编程] 好运-明烨 | 明烨 | 8 | 今天记录了... | hello，明烨，你已经... |

**规则**：`message` 列存在且非空时，crew_sender.py 直接使用，跳过 AI 生成。

---

## crew_sender.py — 自动化引擎

### 职责边界

- **负责**：微信 UI 自动化、发送验证、日志保存
- **不负责**：AI 消息生成（移至 app.py Web 后端处理）
- AI 生成逻辑保留在 crew_sender.py 中作为 CLI 模式的 fallback（CSV 无 message 列时使用）

### 配置区

```python
CHECKINS_REQUIRED    = 12      # 打卡满多少次可上岸
SKIP_NAMES: list[str] = []     # CLI 模式固定跳过名单
DEFAULT_CSV          = "crew_today.csv"
SEND_INTERVAL        = 4.0     # 每条发完后冷却秒数
SEARCH_WAIT          = 1.5     # 粘贴姓名后等待搜索结果秒数
OPEN_WAIT            = 1.2     # 点击联系人后等待对话窗口打开秒数
LOCATE_CONFIDENCE    = 0.85    # locateOnScreen 置信度阈值
SENT_VARIANCE_THRESHOLD = 12.0 # 输入框清空检测方差阈值
```

### CLI 参数

```
python crew_sender.py [csv_path] [--dry-run] [--safe] [--no-confirm]
                      [--skip "name1,name2"] [--json-progress]
```

| 参数 | 说明 |
|------|------|
| `--dry-run` | 仅执行搜索检测，不粘贴不发送 |
| `--safe` | 粘贴消息但不按 Enter，由人工手动发送 |
| `--no-confirm` | 跳过终端预览确认（Web 后端调用时使用） |
| `--skip` | 临时跳过名单，逗号分隔 |
| `--json-progress` | 以 JSON Lines 格式输出进度（供 Web 后端 SSE 解析） |

### 函数列表

```python
def load_csv(path: str) -> list[dict]
def generate_message(name: str, checkins: int, comment: str) -> str
def generate_all_messages(crew_data: list[dict]) -> list[dict]
def preview_and_confirm(crew_messages: list[dict], initial_skip: set) -> set
def get_wechat_window() -> tuple[int, int, int, int]
def activate_wechat() -> None
def open_search() -> None
def search_contact(wechat_name: str) -> None   # 参数改为 wechat_name
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

### --json-progress 输出格式

当传入 `--json-progress` 时，进度通过 stdout 输出 JSON Lines（每行一个 JSON 对象）：

```json
{"type": "start", "total": 30}
{"type": "progress", "index": 1, "total": 30, "name": "张海涛", "status": "sending"}
{"type": "progress", "index": 1, "total": 30, "name": "张海涛", "status": "sent"}
{"type": "progress", "index": 2, "total": 30, "name": "李志强", "status": "fail", "reason": "搜索结果不唯一"}
{"type": "done", "sent": 1, "skipped": 0, "failed": 1}
```

---

## app.py — Flask Web 后端

### 架构

```python
app = Flask(__name__)

# 全局状态
last_heartbeat: float       # 最近一次心跳时间
_send_process: subprocess.Popen | None  # 当前执行的子进程
```

### 心跳 Watchdog

```python
def _watchdog():
    while True:
        time.sleep(5)
        if _send_process is None:          # 无发送任务时才检测
            if time.time() - last_heartbeat > 20:
                os.kill(os.getpid(), signal.SIGTERM)

threading.Thread(target=_watchdog, daemon=True).start()
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 返回 index.html |
| POST | `/api/heartbeat` | 前端心跳，刷新 last_heartbeat |
| POST | `/api/load-csv` | 上传 CSV 文件，返回解析结果 JSON |
| POST | `/api/generate` | 单条 AI 生成，返回 `{message}` |
| GET | `/api/generate-all` | SSE：逐条 AI 生成，推送进度 |
| POST | `/api/save-csv` | 接收完整数据，写回 CSV 文件 |
| GET | `/api/execute` | SSE：启动 crew_sender.py，推送进度 |
| POST | `/api/stop` | 终止当前执行中的子进程 |

### load-csv 响应格式

```json
{
  "filename": "crew_today.csv",
  "filepath": "/abs/path/crew_today.csv",
  "crew": [
    {
      "name": "张海涛",
      "checkins": 8,
      "comment": "今天记录了航行数据",
      "message": "hello，张海涛..."
    }
  ]
}
```

### generate-all SSE 格式

```
data: {"index": 0, "total": 5, "name": "张海涛", "message": "hello..."}

data: {"index": 1, "total": 5, "name": "李志强", "message": "hello..."}

data: DONE
```

### execute SSE 格式

Flask 以 `subprocess.Popen` 启动 `crew_sender.py --json-progress --no-confirm`，
逐行读取 stdout，原样转发为 SSE 事件：

```
data: {"type": "start", "total": 30}

data: {"type": "progress", "index": 1, "name": "张海涛", "status": "sent"}

data: {"type": "done", "sent": 28, "skipped": 2, "failed": 0}
```

### save-csv 请求格式

```json
{
  "filepath": "/abs/path/crew_today.csv",
  "crew": [
    {"name": "张海涛", "checkins": 8, "comment": "...", "message": "hello...", "skip": false}
  ]
}
```

---

## 前端设计系统 — 航海控制台

### 色彩系统

```css
--bg-primary:    #040d1a;              /* 深海黑 */
--bg-secondary:  #071428;              /* 深海蓝 */
--bg-card:       rgba(7, 20, 45, 0.85);/* 玻璃态卡片 */
--accent-teal:   #00d4aa;              /* 声纳青绿 */
--accent-blue:   #1d6fa4;              /* 海洋蓝 */
--accent-amber:  #f59e0b;              /* 警戒琥珀 */
--accent-red:    #ef4444;              /* 危险红 */
--border-glow:   rgba(0, 212, 170, 0.25); /* 边框发光 */
--text-primary:  #cbd5e1;
--text-secondary:#64748b;
--text-bright:   #e2e8f0;
--font-mono:     'JetBrains Mono', 'Fira Code', monospace;
```

### 背景效果

- 深色线性渐变底色（`#040d1a` → `#071428`）
- 极细网格线（nautical chart 风格，`rgba(0,212,170,0.05)`）
- 右下角小型旋转雷达动画（纯 CSS，低透明度装饰）

### 状态徽章

| 状态 | 样式 |
|------|------|
| PENDING | 灰色实心圆 + 文字 |
| GENERATING | 青绿脉冲动画 |
| READY | 青绿实心 ✓ |
| SENDING | 蓝色脉冲动画 |
| SENT | 绿色实心 ✓ |
| SKIPPED | 琥珀色 ⊘ |
| FAIL | 红色 ✗ + 原因 tooltip |

### 页面布局

```
┌──────────────────────────────────────────────────┐
│  HEADER: 系统名 + 服务状态 + CSV 文件名           │
├───────────┬──────────────────────────────────────┤
│  CONTROL  │  MISSION TABLE                       │
│  PANEL    │  ┌──────────────────────────────┐   │
│           │  │ # │ 姓名 │ 打卡 │ 消息预览  │ ⚙ │   │
│ 导入 CSV  │  ├──────────────────────────────┤   │
│           │  │ 展开行：消息编辑器 + 操作按钮 │   │
│ 模式选择  │  └──────────────────────────────┘   │
│           │                                      │
│ 全部生成  │                                      │
│ 保存 CSV  │                                      │
│ 执行      │                                      │
├───────────┴──────────────────────────────────────┤
│  CONSOLE LOG（终端风格，SSE 实时输出）             │
└──────────────────────────────────────────────────┘
```

### 关键交互细节

- 表格行点击展开，显示可编辑的消息文本域
- 「全部生成」触发 SSE，消息逐条填入，有打字机效果
- 「执行」按钮发送中禁用，完成/失败后恢复
- 底部 Console 区域高度固定，内容超出自动滚动到底部
- 前端每 5 秒向 `/api/heartbeat` 发一次 POST（页面可见时）
- `visibilitychange` 事件处理：页面隐藏时降低心跳频率到 15 秒

---

## start.command

```bash
#!/bin/bash
cd "$(dirname "$0")"
nohup python app.py > logs/app.log 2>&1 &
sleep 1
open http://localhost:5001
```

- chmod +x start.command（写入时需设置权限）
- 终端窗口在 sleep 1 后自动关闭（Terminal.app 行为）

---

## 微信控制层（保持不变）

### 获取微信窗口位置

```python
def get_wechat_window() -> tuple[int, int, int, int]:
    script = """
    tell application "System Events" to tell process "WeChat"
        set p to position of window 1
        set s to size of window 1
        return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ¬
               ((item 1 of s) as text) & "," & ((item 2 of s) as text)
    end tell
    """
    out = subprocess.run(["osascript", "-e", script],
                         capture_output=True, text=True, timeout=5).stdout.strip()
    x, y, w, h = map(int, out.split(","))
    return x, y, w, h
```

### AppleScript 键盘辅助（绕过 macOS IME 干扰）

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

> ⚠️ **重要**：所有键盘快捷键（Cmd+F、Cmd+A、Cmd+V、Return）必须通过 AppleScript 发送，
> 不得使用 `pyautogui.hotkey()`，否则被 macOS 输入法拦截。

### detect_contact_in_results

```python
def detect_contact_in_results() -> Literal["ok", "not_found", "multiple"]:
    screenshot = pyautogui.screenshot()
    try:
        contacts_pos = pyautogui.locate(
            "assets/contacts_label.png", screenshot, confidence=LOCATE_CONFIDENCE)
    except Exception as e:
        if type(e).__name__ != "ImageNotFoundException":
            raise
        contacts_pos = None

    if contacts_pos is None:
        return "not_found"

    try:
        group_chats_pos = pyautogui.locate(
            "assets/group_chats_label.png", screenshot, confidence=LOCATE_CONFIDENCE)
    except Exception:
        group_chats_pos = None

    region_top    = contacts_pos.top
    region_bottom = group_chats_pos.top if group_chats_pos else contacts_pos.top + 200
    contacts_region = (contacts_pos.left, region_top, 500, region_bottom - region_top)

    try:
        info_buttons = list(pyautogui.locateAll(
            "assets/info_button.png", screenshot,
            confidence=LOCATE_CONFIDENCE, region=contacts_region
        ))
    except Exception as e:
        if type(e).__name__ != "ImageNotFoundException":
            raise
        info_buttons = []

    count = len(info_buttons)
    if count == 0:
        return "not_found"
    elif count == 1:
        return "ok"
    else:
        return "multiple"
```

> ⚠️ `pyscreeze.ImageNotFoundException` 与 `pyautogui.ImageNotFoundException` 是不同的类，
> 必须用 `type(e).__name__` 字符串比对，不得用 `isinstance`。

### verify_window_title

> ⚠️ WeChat 4.x AXTitle 始终为 "Weixin"，无法通过 Accessibility API 获取聊天窗口标题。
> 实现为：点击联系人后，contacts_label.png 从屏幕消失 = 搜索下拉已关闭 = 已进入聊天。

```python
def verify_window_title(name: str) -> bool:
    screenshot = pyautogui.screenshot()
    try:
        contacts_pos = pyautogui.locate(
            "assets/contacts_label.png", screenshot, confidence=LOCATE_CONFIDENCE)
    except Exception:
        contacts_pos = None
    return contacts_pos is None
```

### verify_sent

```python
SENT_VARIANCE_THRESHOLD = 12.0

def verify_sent(wx_window: tuple) -> bool:
    wx_x, wx_y, wx_w, wx_h = wx_window
    region = (wx_x + wx_w - 600, wx_y + wx_h - 100, 500, 60)
    screenshot = pyautogui.screenshot(region=region)
    arr = np.array(screenshot.convert("L"))
    return float(arr.std()) < SENT_VARIANCE_THRESHOLD
```

---

## 日志格式

```json
[
  {
    "wechat_name": "[老][2026Q1][AI 编程] 好运-明烨",
    "name": "明烨",
    "status": "SENT",
    "checkins": 8,
    "message": "hello，明烨...",
    "time": "2026-03-22T14:30:12"
  },
  {
    "wechat_name": "[老][2026Q1][AI 编程] 九七",
    "name": "九七",
    "status": "FAIL",
    "reason": "搜索结果不唯一，存在发错人风险",
    "message": "hello，九七...",
    "time": "2026-03-22T14:30:25"
  }
]
```

状态枚举：`SENT` / `SKIPPED` / `FAIL` / `DRY_RUN`

---

## assets 模板图片说明

| 文件名 | 截取内容 | 用途 |
|--------|----------|------|
| `contacts_label.png` | 搜索结果下拉中「Contacts」文字标签 | 定位 Contacts 区域上边界 |
| `group_chats_label.png` | 搜索结果下拉中「Group Chats」文字标签 | 定位 Contacts 区域下边界（有群聊时） |
| `internet_search_label.png` | 搜索结果下拉中「Internet search results」标签 | 定位 Contacts 区域下边界（无群聊时） |
| `info_button.png` | 联系人行右侧的 ⓘ 按钮 | 计数 Contacts 区域内联系人数量 |

> 两种下边界标签可共存，`detect_contact_in_results` 取 top 最小值（最靠近 Contacts）作为边界。

截取要求：原始像素，不缩放，不压缩，PNG 格式。

---

## 首次运行校准步骤

1. 确认 `assets/` 目录下三张模板图片均已就位
2. 运行 `python crew_sender.py --dry-run`（只测试搜索和检测，不发送）
3. 观察是否能正确识别 Contacts 标签和 ⓘ 按钮
4. 如识别失败，在脚本中调低 `LOCATE_CONFIDENCE`（如从 0.85 调到 0.80）
5. 发送第一条后观察输入框清空检测，调整 `SENT_VARIANCE_THRESHOLD`
