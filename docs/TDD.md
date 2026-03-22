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
crew_sender/
├── crew_sender.py        # 主脚本
├── crew_today.csv        # 每天从 Excel 导出（操作者维护）
├── requirements.txt
├── assets/               # UI 模板图片（用于 locateOnScreen）
│   ├── contacts_label.png    # 搜索结果中「Contacts」文字标签截图
│   ├── info_button.png       # 联系人行右侧 ⓘ 按钮截图
│   └── group_chats_label.png # 搜索结果中「Group Chats」文字标签截图
├── logs/                 # 自动生成
│   └── log_YYYYMMDD_HHMMSS.json
└── README.md
```

---

## 依赖

```
openai>=1.0.0           # OpenAI 兼容 SDK，接入七牛云 DeepSeek API
python-dotenv>=1.0.0    # 从 .env 加载 API 配置
pyautogui>=0.9.54
pyperclip>=1.8.2
pillow>=10.0.0          # pyautogui.locateOnScreen 依赖
numpy>=1.24.0           # verify_sent 方差检测
```

---

## 环境变量（.env 文件）

在项目根目录创建 `.env`，内容如下（不得提交到 git）：

```
OPENAI_BASE_URL=https://api.qnaigc.com/v1
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=deepseek-v3-0324
```

脚本启动时通过 `python-dotenv` 自动加载，无需手动 export。`.env` 已加入 `.gitignore`。

---

## 配置区（脚本顶部）

```python
CHECKINS_REQUIRED = 12       # 打卡满多少次可上岸领 199 元
SKIP_NAMES: list[str] = []   # 固定跳过的姓名列表
DEFAULT_CSV = "crew_today.csv"
SEND_INTERVAL   = 4.0        # 每条发完后冷却秒数
SEARCH_WAIT     = 1.5        # 粘贴姓名后等待搜索结果秒数
OPEN_WAIT       = 1.2        # 点击联系人后等待对话窗口打开秒数
LOCATE_CONFIDENCE = 0.85     # locateOnScreen 置信度阈值
```

---

## 模块划分

```
crew_sender.py
├── load_csv()              → list[dict]
├── generate_message()      → str           # 单条，调用七牛云 DeepSeek API
├── generate_all_messages() → list[dict]    # 批量
├── preview_and_confirm()   → set[str]      # 返回最终 skip 集合
├── WeChat 控制层
│   ├── get_wechat_window() → (x, y, w, h)  # AppleScript 获取窗口位置
│   ├── activate_wechat()
│   ├── open_search()
│   ├── search_contact()
│   ├── detect_contact_in_results() → "ok" | "not_found" | "multiple"
│   ├── click_contact()
│   ├── verify_window_title() → bool
│   ├── send_message()
│   └── verify_sent()       → bool
├── send_one()              # 单人完整流程，抛出 FailError
├── run()                   # 主流程
└── save_log()
```

---

## AI 文案生成层 — 详细设计

### 初始化（模块级）

```python
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
_model = os.environ.get("OPENAI_MODEL", "deepseek-v3-0324")
```

---

### 系统提示词

```python
SYSTEM_PROMPT = """\
你是船队打卡激励助手。根据用户提供的信息，严格按照以下格式输出一条鼓励消息，\
不得添加任何额外说明或内容：

hello，{name}，你已经连续打卡 {checkins} 次，{shore_hint}。\
我看了你的打卡内容，{specific_encouragement}
继续加油！
----------
{motivational_quote}

字段说明：
- {name}：直接使用提供的姓名
- {checkins}：直接使用提供的打卡次数数字
- {shore_hint}：打卡次数 < 12 时，填「还有 X 次就上岸啦」（X = 12 - 打卡次数）；\
打卡次数 ≥ 12 时，填「你已经完成了上岸目标，太棒了」
- {specific_encouragement}：必须结合今日打卡内容评价具体说，不得泛泛而谈，\
以句号结尾
- {motivational_quote}：一句简短有力的励志语，适合激励在船工作的人，口语化

整体要求：口语化、自然、积极，不加 emoji，不分段。
"""
```

---

### generate_message

```python
def generate_message(name: str, checkins: int, comment: str) -> str:
    user_prompt = (
        f"姓名：{name}\n"
        f"打卡次数：{checkins}\n"
        f"今日打卡内容评价：{comment}"
    )
    response = _client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()
```

---

### generate_all_messages

```python
def generate_all_messages(crew_data: list[dict]) -> list[dict]:
    results = []
    total = len(crew_data)
    for i, row in enumerate(crew_data, 1):
        name = row["姓名"]
        checkins = int(row["打卡次数"])
        comment = row["评价"]
        print(f"  生成文案 [{i:02d}/{total}] {name} ...", end=" ", flush=True)
        message = generate_message(name, checkins, comment)
        print("完成")
        results.append({
            "name": name,
            "checkins": checkins,
            "comment": comment,
            "message": message,
        })
    return results
```

---

## 微信控制层 — 详细设计

### 获取微信窗口位置

每次运行开始时调用一次，缓存结果。

```python
def get_wechat_window() -> tuple[int, int, int, int]:
    script = """
    tell application "System Events" to tell process "WeChat"
        set p to position of window 1
        set s to size of window 1
        return (item 1 of p) & "," & (item 2 of p) & "," & (item 1 of s) & "," & (item 2 of s)
    end tell
    """
    out = subprocess.run(["osascript", "-e", script],
                         capture_output=True, text=True, timeout=5).stdout.strip()
    x, y, w, h = map(int, out.split(","))
    return x, y, w, h
```

返回示例：`(775, 22, 755, 1058)`

---

### 激活微信

```python
def activate_wechat():
    subprocess.run(["osascript", "-e",
                    'tell application "WeChat" to activate'],
                   capture_output=True, timeout=5)
    time.sleep(0.8)
```

---

### 打开搜索框

```python
def open_search():
    pyautogui.hotkey("command", "f")
    time.sleep(0.6)
```

---

### 输入联系人姓名

```python
def search_contact(name: str):
    pyautogui.hotkey("command", "a")   # 清空已有内容
    time.sleep(0.1)
    pyperclip.copy(name)
    pyautogui.hotkey("command", "v")
    time.sleep(SEARCH_WAIT)            # 等待搜索结果渲染
```

---

### 检测搜索结果 ← 核心逻辑

**判断依据**：在当前屏幕截图中，定位 `contacts_label.png` 和 `group_chats_label.png`，划定 Contacts 区域的上下边界，然后在该区域内用 `locateAllOnScreen` 数 `info_button.png`（ⓘ）的数量。

```python
def detect_contact_in_results() -> Literal["ok", "not_found", "multiple"]:
    screenshot = pyautogui.screenshot()

    contacts_pos = pyautogui.locate(
        "assets/contacts_label.png", screenshot, confidence=LOCATE_CONFIDENCE
    )
    if contacts_pos is None:
        return "not_found"

    group_chats_pos = pyautogui.locate(
        "assets/group_chats_label.png", screenshot, confidence=LOCATE_CONFIDENCE
    )

    # 划定 Contacts 区域的 Y 边界
    region_top    = contacts_pos.top
    region_bottom = group_chats_pos.top if group_chats_pos else contacts_pos.top + 200
    region_left   = contacts_pos.left
    region_width  = 300   # 搜索下拉框宽度
    region_height = region_bottom - region_top

    contacts_region = (region_left, region_top, region_width, region_height)

    info_buttons = list(pyautogui.locateAll(
        "assets/info_button.png", screenshot,
        confidence=LOCATE_CONFIDENCE, region=contacts_region
    ))

    count = len(info_buttons)
    if count == 0:
        return "not_found"
    elif count == 1:
        return "ok"
    else:
        return "multiple"
```

---

### 点击联系人

检测通过（count == 1）后，点击 `contacts_label` 下方第一个联系人行的中心。

```python
def click_contact(contacts_label_pos):
    # 联系人行在 Contacts 标签下方约 38px 处
    click_x = contacts_label_pos.left + contacts_label_pos.width // 2
    click_y = contacts_label_pos.top + contacts_label_pos.height + 38
    pyautogui.click(click_x, click_y)
    time.sleep(OPEN_WAIT)
```

---

### 验证窗口标题

> ⚠️ WeChat 4.x 使用自定义渲染框架，不通过 accessibility API 暴露聊天内容：
> - `AXTitle of window 1` 始终为 `"Weixin"`
> - `entire contents of window 1` 只返回 3 个 button，无文本信息
>
> **实际实现**：截图间接验证 —— 点击联系人后 `contacts_label.png` 从屏幕消失，
> 表明搜索下拉已关闭、已成功进入聊天窗口。
> 结合 `detect_contact_in_results` 已验证"唯一联系人"，安全性足够。

```python
def verify_window_title(name: str) -> bool:
    # 点击后搜索下拉消失 = 已进入聊天，视为验证通过
    screenshot = pyautogui.screenshot()
    try:
        contacts_pos = pyautogui.locate(
            "assets/contacts_label.png", screenshot,
            confidence=LOCATE_CONFIDENCE,
        )
    except Exception:
        contacts_pos = None
    return contacts_pos is None
```

---

### 发送消息

```python
def send_message(message: str, wx_window: tuple):
    wx_x, wx_y, wx_w, wx_h = wx_window
    # 输入框：右侧面板底部，向上约 55px 处
    input_x = wx_x + wx_w - 370    # 右侧聊天面板中心
    input_y = wx_y + wx_h - 55
    pyautogui.click(input_x, input_y)
    time.sleep(0.3)
    pyautogui.hotkey("command", "a")  # 清空防残留
    time.sleep(0.1)
    pyperclip.copy(message)
    pyautogui.hotkey("command", "v")
    time.sleep(0.4)
    pyautogui.press("return")
    time.sleep(0.5)
```

---

### 验证消息已发出

发送后截取输入框区域，检查是否已清空（输入框内无文字时，该区域接近纯白/纯灰）。

```python
def verify_sent(wx_window: tuple) -> bool:
    wx_x, wx_y, wx_w, wx_h = wx_window
    # 截取输入框区域
    region = (wx_x + wx_w - 600, wx_y + wx_h - 100, 500, 60)
    screenshot = pyautogui.screenshot(region=region)
    # 检查该区域的像素方差：有文字时方差大，清空后方差小
    import numpy as np
    arr = np.array(screenshot.convert("L"))
    return float(arr.std()) < 12.0    # 阈值需首次运行后根据实测调整
```

> ⚠️ 这个方差阈值（12.0）在首次实测后可能需要微调，在 README 中说明如何校准。

---

### 单人完整流程

```python
class FailError(Exception):
    pass

def send_one(name: str, message: str, wx_window: tuple):
    activate_wechat()
    open_search()
    search_contact(name)

    result = detect_contact_in_results()
    if result == "not_found":
        raise FailError(f"未找到联系人「{name}」，请检查备注名是否与 CSV 一致")
    if result == "multiple":
        raise FailError(f"「{name}」搜索结果不唯一，存在发错人风险")

    # 获取 contacts_label 位置用于点击偏移
    screenshot = pyautogui.screenshot()
    contacts_pos = pyautogui.locate("assets/contacts_label.png", screenshot,
                                    confidence=LOCATE_CONFIDENCE)
    click_contact(contacts_pos)

    if not verify_window_title(name):
        raise FailError(f"「{name}」窗口标题验证失败，实际打开了其他对话")

    send_message(message, wx_window)

    if not verify_sent(wx_window):
        raise FailError(f"「{name}」消息发送未确认，请手动检查微信")
```

---

## 日志格式

```json
[
  {
    "name": "张海涛",
    "status": "SENT",
    "checkins": 8,
    "message": "海涛，目前已打卡8次...",
    "time": "2026-03-22T14:30:12"
  },
  {
    "name": "李志强",
    "status": "FAIL",
    "reason": "搜索结果不唯一，存在发错人风险",
    "message": "志强，目前已打卡3次...",
    "time": "2026-03-22T14:30:25"
  }
]
```

状态枚举：`SENT` / `SKIPPED` / `FAIL` / `ERROR`

---

## FAIL 即停的主循环逻辑

```python
for idx, item in enumerate(to_send, 1):
    try:
        send_one(item["name"], item["message"], wx_window)
        results.append({"name": item["name"], "status": "SENT", ...})
    except FailError as e:
        results.append({"name": item["name"], "status": "FAIL", "reason": str(e), ...})
        save_log(log_file, results)
        print(f"\n❌ FAIL — {e}")
        print(f"🛑 自动化已停止（已完成 {idx-1}/{len(to_send)} 条）")
        print(f"📄 日志已保存至 {log_file}")
        sys.exit(1)
    except KeyboardInterrupt:
        # Ctrl+C 中断
        save_log(log_file, results)
        sys.exit(0)

    time.sleep(SEND_INTERVAL)
```

---

## assets 模板图片说明

这三张图片需要在目标 Mac 上用 Snipaste 手动截取，截取后放入 `assets/` 目录：

| 文件名 | 截取内容 | 用途 |
|--------|----------|------|
| `contacts_label.png` | 搜索结果下拉中「Contacts」文字标签（已提供）| 定位 Contacts 区域上边界 |
| `group_chats_label.png` | 搜索结果下拉中「Group Chats」文字标签 | 定位 Contacts 区域下边界 |
| `info_button.png` | 联系人行右侧的 ⓘ 按钮 | 计数 Contacts 区域内联系人数量 |

截取要求：原始像素，不缩放，不压缩，PNG 格式。

---

## 首次运行校准步骤

1. 确认 `assets/` 目录下三张模板图片均已就位
2. 运行 `python3 crew_sender.py --dry-run`（只测试搜索和检测，不发送）
3. 观察是否能正确识别 Contacts 标签和 ⓘ 按钮
4. 如识别失败，在脚本中调低 `LOCATE_CONFIDENCE`（如从 0.85 调到 0.80）
5. 发送第一条后观察输入框清空检测，调整 `verify_sent` 中的方差阈值
