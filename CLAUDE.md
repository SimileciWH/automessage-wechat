# CLAUDE.md — 给 Claude Code 的实现指令

## 你的任务

根据 PRD.md 和 TDD.md，实现 `crew_sender.py` 主脚本和完整项目结构。

---

## 实现前必须做的事

1. 先完整阅读 `PRD.md` 和 `TDD.md`，不得跳过
2. 严格按照 TDD.md 的模块划分和函数签名实现，不得自行重构结构
3. 不得在没有讨论的情况下引入 TDD.md 未提到的第三方库

---

## 文件结构

按以下结构创建文件，不得增减：

```
crew_sender/
├── crew_sender.py
├── crew_today.csv        # 示例数据，5行
├── requirements.txt
├── assets/               # 空目录，附 README_assets.md 说明如何截图
│   └── README_assets.md
├── logs/                 # 空目录（运行时自动写入）
└── README.md
```

---

## crew_sender.py 实现规范

### 配置区

脚本顶部必须有独立的配置区，包含以下所有变量，每个变量附一行中文注释：

```python
CHECKINS_REQUIRED = 12
SKIP_NAMES: list[str] = []
DEFAULT_CSV = "crew_today.csv"
SEND_INTERVAL     = 4.0
SEARCH_WAIT       = 1.5
OPEN_WAIT         = 1.2
LOCATE_CONFIDENCE = 0.85
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
def search_contact(name: str) -> None
def detect_contact_in_results() -> Literal["ok", "not_found", "multiple"]
def click_contact(contacts_label_pos) -> None
def verify_window_title(name: str) -> bool
def send_message(message: str, wx_window: tuple) -> None
def verify_sent(wx_window: tuple) -> bool
def send_one(name: str, message: str, wx_window: tuple) -> None  # 抛出 FailError
def save_log(path: Path, results: list[dict]) -> None
def run(csv_path: str) -> None
```

### FailError

定义为自定义异常类：

```python
class FailError(Exception):
    pass
```

### --dry-run 参数支持

`run()` 函数支持 `dry_run: bool = False` 参数。dry-run 模式下：
- 正常读取 CSV 和生成文案
- 正常进行预览和确认
- 执行搜索和检测（`detect_contact_in_results`），打印检测结果
- **不执行点击、不发送消息**
- 日志中状态记录为 `DRY_RUN`

命令行入口：
```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=DEFAULT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.csv, dry_run=args.dry_run)
```

---

## 关键实现细节

### detect_contact_in_results

- 截一次全屏截图，复用同一张截图完成所有 locate 调用（避免多次截图出现时序差异）
- `group_chats_label.png` 可能不存在（搜索结果只有联系人没有群组时），此时 `region_bottom = contacts_pos.top + 200`
- 数 ⓘ 按钮时必须限定在 contacts_region 内，不得在全屏计数

### verify_sent

- 使用 numpy 计算截图灰度方差
- 阈值 `12.0` 在代码中定义为常量 `SENT_VARIANCE_THRESHOLD = 12.0`，方便后续调整
- 函数内附注释说明如何校准：首次运行后观察实际方差值，调整阈值

### 终端输出风格

- 启动横幅、每条发送状态、汇总信息使用中文
- 所有 FAIL 信息必须打印具体原因（从 FailError.args[0] 取）
- 进度格式：`[02/30]  张海涛 ... ✅` 或 `[02/30]  张海涛 ... ❌ FAIL`

### Ctrl+C 处理

在主发送循环中捕获 `KeyboardInterrupt`，捕获后：
1. 打印「用户中断」提示
2. 调用 `save_log()`
3. `sys.exit(0)`

### save_log 的调用时机

以下三种情况必须调用 `save_log`：
1. 所有发送正常完成后
2. 遇到 `FailError` 停机前
3. 捕获到 `KeyboardInterrupt` 后

---

## 不允许的实现方式

- ❌ 不得使用 `pyautogui.typewrite()` 输入中文（用 pyperclip + Cmd+V）
- ❌ 不得使用固定屏幕坐标（必须基于 `get_wechat_window()` 的返回值计算偏移）
- ❌ 不得在 FAIL 后继续发送剩余联系人（必须立即 `sys.exit(1)`）
- ❌ 不得省略 `verify_window_title` 和 `verify_sent` 两个验证步骤
- ❌ `detect_contact_in_results` 不得仅依赖 `contacts_label.png` 存在就判定 ok，必须数 ⓘ 按钮

---

## README.md 内容要求

必须包含以下章节，中文撰写：

1. 环境要求（macOS、微信版本、Python 版本）
2. 首次安装（pip install、API Key 配置、辅助功能授权）
3. assets 截图准备（说明需要截哪三张图，参考 `assets/README_assets.md`）
4. 每天操作流程（Excel 维护 → 导出 CSV → 运行命令）
5. 配置项说明（表格形式）
6. 常见问题（至少包含：联系人未找到、辅助功能权限、搜索结果不唯一、阈值校准）
7. 日志文件说明

---

## 完成标准

实现完成后，逐项自检：

- [ ] 所有函数签名与 TDD.md 一致
- [ ] FAIL 即停，不跳过继续
- [ ] `detect_contact_in_results` 正确处理 not_found / multiple / ok 三种情况
- [ ] `verify_window_title` 使用 AppleScript 而非截图
- [ ] `verify_sent` 使用方差检测而非固定等待
- [ ] `--dry-run` 模式可用
- [ ] Ctrl+C 必定保存日志
- [ ] 所有坐标基于窗口位置动态计算
- [ ] README.md 包含所有要求章节
- [ ] `assets/README_assets.md` 存在且说明三张图片的截取方法
