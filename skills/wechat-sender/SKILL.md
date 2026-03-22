---
name: wechat_sender
description: 船员打卡消息自动发送——给定 CSV 文件，调用 AI 生成个性化鼓励消息并通过微信桌面客户端自动发送给每位船员。支持 Web 控制台和命令行两种模式。
metadata: {"openclaw": {"os": ["darwin"], "requires": {"bins": ["python3"], "env": ["OPENAI_API_KEY", "OPENAI_BASE_URL"]}, "primaryEnv": "OPENAI_API_KEY", "emoji": "⛵", "homepage": "https://github.com/SimileciWH/automessage-wechat"}}
---

# 船员打卡消息自动发送 Skill

## 概述

本 skill 封装了 `automessage-wechat` 项目的完整功能：
- 读取 CSV 打卡数据
- 调用 AI（DeepSeek/GPT）为每位船员生成个性化鼓励消息
- 通过 macOS 微信桌面客户端自动发送

**仅支持 macOS**，需要微信桌面版已登录，且启用辅助功能权限。

---

## 前置条件检查

用户触发本 skill 时，首先确认以下条件：

1. **环境变量**：`OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 已在 `.env` 文件或环境中配置
2. **依赖已安装**：运行 `pip3 install -r requirements.txt`（如未安装则提示用户执行）
3. **微信已登录**：macOS 微信桌面版处于登录状态
4. **辅助功能权限**：系统设置 → 隐私与安全性 → 辅助功能 → Terminal.app 已勾选
5. **CSV 文件**：用户需提供包含以下列的 CSV 文件：`微信名称`、`姓名`、`打卡次数`、`评价`

---

## 触发场景

以下情况自动触发本 skill：
- 用户说「帮我发打卡消息」「发微信给船员」「群发鼓励消息」
- 用户提供 `.csv` 文件并说「发给所有人」
- 用户说「启动发送控制台」「打开 Web 界面」

---

## 可用脚本

Skill 自带两个入口脚本，优先使用这些脚本而不是直接调用 Python：

| 脚本 | 用途 |
|------|------|
| `scripts/setup.sh` | 首次安装：检查依赖、创建 .env、提示权限配置 |
| `scripts/send.sh` | 发送入口：统一封装 Web 控制台和命令行两种模式 |

## 使用模式

### 首次安装

```bash
bash skills/wechat-sender/scripts/setup.sh
```

检查 Python 依赖、.env 文件、辅助功能权限，有问题自动提示修复。

### 模式一：Web 控制台（推荐新手）

```bash
# 无参数启动 Web 控制台
bash skills/wechat-sender/scripts/send.sh
# 或
bash skills/wechat-sender/scripts/send.sh --web
```

启动后引导用户：
1. 在浏览器 http://localhost:5001 上传 CSV
2. 点击「全部生成」生成文案（可逐条编辑）
3. 选择发送模式（正式 / 安全 / Dry-Run）
4. 点击「执行」开始自动发送

### 模式二：命令行（推荐熟练用户）

```bash
# 基本发送
bash skills/wechat-sender/scripts/send.sh 20260322-大航海船员.csv

# 安全模式（自动粘贴，手动按 Enter 确认）
bash skills/wechat-sender/scripts/send.sh crew.csv --safe

# 只验证备注名，不发送
bash skills/wechat-sender/scripts/send.sh crew.csv --dry-run

# 跳过某些人
bash skills/wechat-sender/scripts/send.sh crew.csv --skip 张三,李四
```

---

## 发送模式说明

| 模式 | 参数 | 说明 |
|------|------|------|
| 正式发送 | （默认） | 全自动发送，每条发送后验证并冷却 4 秒 |
| 安全模式 | `--safe` | 自动粘贴到输入框，需人工按 Enter 确认 |
| Dry-Run | `--dry-run` | 只搜索联系人，不粘贴不发送，用于验证备注名 |

**首次使用强烈建议先跑 `--dry-run`**，确认所有微信备注名正确后再正式发送。

---

## CSV 格式要求

| 列名 | 必须 | 说明 |
|------|------|------|
| `微信名称` | ✅ | 与微信通讯录备注名完全一致（含方括号、空格） |
| `姓名` | ✅ | 消息称谓，如「明烨」 |
| `打卡次数` | ✅ | 整数 |
| `评价` | ✅ | 当天评价，AI 据此生成个性化内容 |
| `message` | 可选 | 已生成的消息，非空则跳过 AI |

---

## 常见问题处理

### 「未找到联系人」

- `微信名称` 列必须与微信通讯录**备注名**完全一致
- 先用 `--dry-run` 逐一验证

### 「搜索结果不唯一」

- 修改微信备注名使其唯一
- 或用 `--skip 姓名` 本次跳过，手动发送

### 「辅助功能权限」错误

引导用户：系统设置 → 隐私与安全性 → 辅助功能 → 添加 Terminal.app

### 模板图片识别失败

assets 图片必须与当前微信**外观模式**（深色/浅色）一致。
重新截取方法：打开微信搜索任意联系人，用 Snipaste 截取对应 UI 元素替换 `assets/` 下的图片。

---

## 工作目录要求

所有命令必须在项目根目录执行（`crew_sender.py` 所在目录），因为：
- `assets/` 模板图片使用相对路径
- `.env` 文件读取使用相对路径
- `logs/` 目录在当前目录下创建

如用户从其他目录触发，先 `cd` 到项目目录：

```bash
cd /path/to/automessage-wechat
python3 crew_sender.py ...
```
