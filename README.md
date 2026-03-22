# 船员打卡消息自动发送系统

每天只需更新 Excel 并导出 CSV，通过 **Web 控制台**、**命令行** 或 **OpenClaw Skill** 三种方式，自动为所有船员生成个性化鼓励消息并通过微信发送。

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS（需要辅助功能权限控制桌面） |
| 微信版本 | 桌面版 4.x（已登录，**深色模式**） |
| Python | 3.10 及以上 |
| 屏幕 | 支持 Retina（物理分辨率自动适配） |

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

# AI 限速配置（可选，默认值如下）
AI_INTERVAL=2.0       # 每次 AI 调用之间的间隔（秒）
AI_RETRY_WAIT=30.0    # 遇到 429 时等待重试的基础秒数
AI_MAX_RETRIES=3      # 429 最大重试次数
```

`.env` 已加入 `.gitignore`，不会被提交到 git。

### 3. 授权辅助功能

macOS 需要授权 Terminal（或运行 Python 的应用）控制桌面：

> 系统设置 → 隐私与安全性 → 辅助功能 → 添加 Terminal.app ✓

---

## 使用方式一：Web 控制台（推荐）

通过浏览器图形界面完成全部操作，无需命令行。

### 启动

双击 `start.command`，或在终端运行：

```bash
python3 app.py
```

浏览器自动打开 `http://localhost:5001`。

> Web 服务仅监听 `127.0.0.1`，不对外网暴露。

### 操作流程

**第一步：上传 CSV**

点击「选择文件」或将 CSV 拖入上传区，系统自动解析并展示所有船员列表。

CSV 必须包含以下列：

| 列名 | 说明 |
|------|------|
| `微信名称` | 微信搜索框输入的名称，需与通讯录备注名完全一致 |
| `姓名` | 消息称谓（`hello，明烨，...`）及日志记录 |
| `打卡次数` | 整数，用于生成消息内容 |
| `评价` | 当天打卡评价，AI 据此生成个性化鼓励语 |
| `message`（可选） | 已生成的消息，非空时跳过 AI，直接复用 |

**第二步：生成文案**

- 点击「全部生成」，系统逐条调用 AI 生成消息，实时流式展示
- 已有 `message` 内容的行自动跳过 AI，直接标记为「复用」
- 点击任意行可展开，内联编辑消息内容
- 点击行内「重新生成」可单独重生成某人的消息

**第三步：选择模式**

| 模式 | 说明 |
|------|------|
| 正式发送 | 全自动发送，每条发完自动验证并冷却 4 秒 |
| 安全模式 | 自动粘贴到微信输入框，**需人工按 Enter 确认**，适合首次测试 |
| Dry-Run | 只执行搜索，不粘贴不发送，用于验证备注名是否正确 |

**第四步：执行**

点击「执行」按钮，底部 Console 区实时显示发送进度：

```
⏳ [01/30] 张海涛 发送中...
✅ [01/30] 张海涛 已发送
❌ [02/30] 李志强 失败: 未找到联系人「李志强」，请检查微信备注名...
```

发送过程中可点击「停止」随时中断。

**注意事项**

- 执行前会自动保存当前 CSV（含已生成的 message 列），避免重复调用 AI
- 遇到 FAIL 即停止，不会跳过继续发送下一人
- 浏览器关闭或页面隐藏超过 20 秒，服务自动退出（心跳保活机制）

---

## 使用方式二：命令行

适合熟悉终端的用户，或需要脚本化调度的场景。

### 基本用法

```bash
# 使用默认 crew_today.csv
python3 crew_sender.py

# 指定文件
python3 crew_sender.py 20260322-大航海船员.csv

# 只搜索不发送（验证微信备注名）
python3 crew_sender.py --dry-run

# 安全模式：自动粘贴，手动按 Enter 确认
python3 crew_sender.py --safe
```

### 完整参数

| 参数 | 说明 |
|------|------|
| `csv`（位置参数） | CSV 文件路径，省略则用 `DEFAULT_CSV` |
| `--dry-run` | 只搜索不发送，打印搜索结果 |
| `--safe` | 安全模式，粘贴后等待人工 Enter |
| `--no-confirm` | 跳过预览确认，直接开始发送 |
| `--skip 姓名1,姓名2` | 本次运行额外跳过的人（逗号分隔） |
| `--json-progress` | 输出 JSON Lines 格式进度（供 Web SSE 解析） |

### 操作流程

**第一步：预览确认**

程序自动调用 AI 生成全部文案，逐条打印预览：

```
[01/30] 张海涛（8次）
-----
hello，张海涛，你已经连续打卡 8 次，还有 4 次就上岸啦...
-----

跳过某些人？输入姓名逗号分隔，回车跳过：
```

输入要跳过的姓名（如 `李志强,王小明`）或直接回车继续。

**第二步：输入 yes 开始**

```
以上 30 条消息即将发送，确认？(yes/no)：yes
```

**第三步：自动发送**

程序逐条搜索、点击、粘贴、验证：

```
[01/30] 张海涛 ✅ SENT
[02/30] 李志强 ✅ SENT
[03/30] 王小明 ❌ FAIL: 未找到联系人...
```

遇到 FAIL 立即停止，并保存当前日志。

---

## 使用方式三：OpenClaw Skill

将本项目封装为 [OpenClaw](https://github.com/openclaw/openclaw) Agent 的 skill，直接用自然语言驱动发送流程。

### 本地安装（项目级，推荐）

clone 本仓库后，在项目目录启动 OpenClaw 即自动加载 skill：

```bash
git clone https://github.com/SimileciWH/automessage-wechat.git
cd automessage-wechat
openclaw
```

> OpenClaw 启动时会自动扫描工作目录下的 `skills/` 文件夹。

### 本地安装（全局级）

安装一次后，所有工作目录都能使用：

```bash
ln -s /path/to/automessage-wechat/skills/wechat-sender ~/.openclaw/skills/wechat-sender
# 或直接复制
cp -r /path/to/automessage-wechat/skills/wechat-sender ~/.openclaw/skills/
```

### 使用示例

安装后在 OpenClaw 中直接用自然语言触发：

```
帮我发今天的打卡消息，CSV 文件是 20260322-大航海船员.csv
```

```
启动 Web 控制台
```

```
用安全模式发送，跳过张三
```

Skill 会自动选择合适的执行方式，检查前置条件，并引导你完成整个发送流程。

---

## assets 模板图片说明

`assets/` 目录存放微信 UI 截图，用于模板匹配定位搜索结果。**所有图片均需在深色模式下截取**（浅色模式颜色不同会导致匹配失败）。

| 文件名 | 用途 |
|--------|------|
| `recently_used_label.png` | 搜索下拉中的「Recently Used」分区标题 |
| `contacts_label.png` | 搜索下拉中的「Contacts」分区标题 |
| `group_chats_label.png` | 搜索下拉中的「Group Chats」分区标题（作为区域下边界） |
| `internet_search_label.png` | 搜索下拉中的「Internet search results」标题（作为区域下边界） |
| `info_button.png` | 联系人行右侧的 ⓘ 圆圈按钮，用于计数判断结果唯一性 |

如微信更新后识别失败，按以下步骤重新截取：

1. 打开微信，搜索任意联系人，使搜索结果面板可见
2. 用 Snipaste 截取对应 UI 元素，原始像素，不缩放，不压缩，PNG 格式
3. 替换 `assets/` 下对应文件

详见 [assets/README_assets.md](assets/README_assets.md)。

---

## 配置项说明

`crew_sender.py` 顶部配置区：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CHECKINS_REQUIRED` | `12` | 打卡满多少次可上岸 |
| `SKIP_NAMES` | `[]` | 每次运行都固定跳过的姓名列表 |
| `DEFAULT_CSV` | `crew_today.csv` | 不指定文件时的默认 CSV |
| `SEND_INTERVAL` | `4.0` | 每条发完后冷却秒数 |
| `SEARCH_WAIT` | `1.5` | 粘贴姓名后等待搜索结果秒数 |
| `OPEN_WAIT` | `1.2` | 点击联系人后等待对话窗口秒数 |
| `LOCATE_CONFIDENCE` | `0.85` | 模板图片通用匹配置信度 |
| `INFO_BTN_CONFIDENCE` | `0.75` | ⓘ 按钮专用置信度 |
| `SENT_VARIANCE_THRESHOLD` | `12.0` | 发送验证方差阈值 |

---

## 常见问题

### Q：提示「未找到联系人」

搜索使用 CSV 的「微信名称」列精确匹配。请确认：
- 「微信名称」与微信通讯录中的**备注名**完全一致（包括方括号、空格）
- 没有多余空格或全角字符

可先用 `--dry-run` 模式验证所有备注名。

### Q：提示「搜索结果不唯一」

微信中有多个名字相近的联系人被检测到。解决方法：
- 在微信中修改备注名使其更唯一
- 临时在预览环节跳过该人，手动发送

### Q：模板图片识别失败

通常由以下原因导致：
1. **深/浅色模式切换**：assets 图片必须与当前微信外观模式一致
2. **微信版本更新**：UI 样式变化需重新截取 assets
3. **屏幕分辨率变化**：重新截取后替换

### Q：提示「消息发送未确认」

`verify_sent` 通过输入框区域像素方差判断发送是否成功。
- 若输入框确实清空但仍报错：调高 `SENT_VARIANCE_THRESHOLD`（如改为 `20.0`）
- 若输入框未清空但不报错：调低阈值

### Q：提示「辅助功能权限」错误

> 系统设置 → 隐私与安全性 → 辅助功能 → 添加 Terminal.app ✓

---

## 日志文件说明

每次运行在 `logs/` 目录生成 `log_YYYYMMDD_HHMMSS.json`：

```json
[
  {"name": "张海涛", "status": "SENT", "checkins": 8, "message": "...", "time": "2026-03-22T14:30:12"},
  {"name": "李志强", "status": "FAIL", "reason": "搜索结果不唯一", "message": "...", "time": "..."},
  {"name": "王小明", "status": "SKIPPED", "checkins": 3, "message": "...", "time": "..."}
]
```

状态枚举：`SENT` / `SKIPPED` / `FAIL` / `DRY_RUN`

程序异常退出前自动保存当前日志，确保不丢失已完成记录。
