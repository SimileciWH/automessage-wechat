# 船员打卡消息自动发送系统

每天只需更新 Excel 并导出 CSV，运行一条命令，自动为所有船员生成个性化鼓励消息并通过微信发送。

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS（支持 Screen Sharing 远程操控） |
| 微信版本 | 桌面版 4.1.5.240（已登录） |
| Python | 3.10 及以上 |
| 屏幕 | 1920×1080 或同等分辨率 |

---

## 首次安装

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入真实 Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```
OPENAI_BASE_URL=https://api.qnaigc.com/v1
OPENAI_API_KEY=你的真实Key
OPENAI_MODEL=deepseek-v3-0324
```

`.env` 已加入 `.gitignore`，不会被提交到 git。

### 3. 授权辅助功能

macOS 需要授权 Terminal（或运行 Python 的应用）控制桌面：

> 系统设置 → 隐私与安全性 → 辅助功能 → 添加 Terminal.app ✓

---

## assets 截图准备

`assets/` 目录下需要三张微信 UI 模板图片（已随项目提供）。
如果微信更新后识别失败，按以下步骤重新截取：

| 文件名 | 截取内容 |
|--------|----------|
| `contacts_label.png` | 搜索下拉中灰色「Contacts」文字标签 |
| `group_chats_label.png` | 搜索下拉中灰色「Group Chats」文字标签 |
| `info_button.png` | 联系人行右侧的 ⓘ 圆圈按钮 |

截取要求：用 Snipaste，原始像素，不缩放，不压缩，PNG 格式。
详见 [assets/README_assets.md](assets/README_assets.md)。

---

## 每天操作流程

**第一步：维护 Excel**

在 Excel 中更新当天的打卡数据，确保有三列：`姓名`、`打卡次数`、`评价`。

**第二步：导出 CSV**

Excel → 文件 → 导出 → CSV UTF-8（用逗号分隔）（.csv）

保存为 `crew_today.csv` 放到本目录，或任意文件名。

**第三步：运行**

```bash
# 使用默认 crew_today.csv
python3 crew_sender.py

# 指定文件
python3 crew_sender.py 2026-03-22.csv

# 只检测不发送（首次调试用）
python3 crew_sender.py --dry-run
```

**第四步：预览确认**

程序会打印所有生成文案，允许临时跳过某些人，输入 `yes` 开始自动发送。

---

## 配置项说明

脚本顶部配置区（`crew_sender.py` 第 20 行起）：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CHECKINS_REQUIRED` | `12` | 打卡满多少次可上岸领 199 元 |
| `SKIP_NAMES` | `[]` | 固定跳过的姓名列表，每次运行都跳过 |
| `DEFAULT_CSV` | `crew_today.csv` | 不指定文件时使用的默认 CSV |
| `SEND_INTERVAL` | `4.0` | 每条发完后冷却秒数 |
| `SEARCH_WAIT` | `1.5` | 粘贴姓名后等待搜索结果秒数 |
| `OPEN_WAIT` | `1.2` | 点击联系人后等待对话窗口秒数 |
| `LOCATE_CONFIDENCE` | `0.85` | 模板图片匹配置信度（0-1） |
| `SENT_VARIANCE_THRESHOLD` | `12.0` | 发送验证方差阈值（见常见问题） |

---

## 常见问题

### Q：提示「未找到联系人」

微信搜索是用 CSV 中的「姓名」列精确搜索的。请确认：
- CSV 中的姓名与微信联系人的**备注名或昵称**完全一致
- 没有多余空格或全角字符

### Q：提示「辅助功能权限」错误

前往：系统设置 → 隐私与安全性 → 辅助功能，勾选运行脚本的终端应用。

### Q：提示「搜索结果不唯一」

微信中存在两个包含该名字的联系人。临时解决：在 `SKIP_NAMES` 或预览环节跳过该人，手动发送后再处理。长期解决：修改微信备注名使其唯一。

### Q：提示「窗口标题验证失败」但确认打开了正确对话

WeChat 4.x UI 层级可能与预期不同。运行以下命令打印实际 UI 结构并联系开发者调整：

```bash
osascript -e 'tell application "System Events" to tell process "WeChat" to return entire contents of window 1'
```

### Q：提示「消息发送未确认」/ 阈值校准

`verify_sent` 通过检测输入框区域的像素方差判断发送是否成功。
运行时会打印实际方差值（如 `[verify_sent std=8.32 threshold=12.0]`）。
- 若输入框确实清空但方差 > 12.0：调高 `SENT_VARIANCE_THRESHOLD`（如改为 20.0）
- 若输入框未清空但方差 < 12.0：调低阈值

### Q：模板图片识别失败（`locateOnScreen` 报错）

微信更新后 UI 可能略有变化。调低 `LOCATE_CONFIDENCE`（如从 0.85 改为 0.80），或重新截取 assets 图片。

---

## 日志文件说明

每次运行在 `logs/` 目录生成 `log_YYYYMMDD_HHMMSS.json`，记录每位船员的发送状态：

```json
[
  {"name": "张海涛", "status": "SENT", "checkins": 8, "message": "...", "time": "2026-03-22T14:30:12"},
  {"name": "李志强", "status": "FAIL", "reason": "搜索结果不唯一", "message": "...", "time": "..."},
  {"name": "王小明", "status": "SKIPPED", "checkins": 3, "message": "...", "time": "..."}
]
```

状态枚举：`SENT` / `SKIPPED` / `FAIL` / `DRY_RUN`

程序异常退出前会自动保存当前日志，确保不丢失已完成记录。
