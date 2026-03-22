#!/bin/bash
# install.sh — 船员打卡消息系统一键安装脚本
# 用法：bash install.sh
set -e

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

ok()   { echo -e "${GREEN}✅ $*${RESET}"; }
warn() { echo -e "${YELLOW}⚠️  $*${RESET}"; }
fail() { echo -e "${RED}❌ $*${RESET}"; exit 1; }
info() { echo -e "${BOLD}▶ $*${RESET}"; }

echo ""
echo -e "${BOLD}================================================${RESET}"
echo -e "${BOLD}  船员打卡消息系统 — 安装配置脚本${RESET}"
echo -e "${BOLD}================================================${RESET}"
echo ""

# ── 1. 操作系统检查 ────────────────────────────────────────────────────────────
info "检查操作系统..."
if [[ "$(uname)" != "Darwin" ]]; then
  fail "本工具仅支持 macOS"
fi
ok "macOS $(sw_vers -productVersion)"

# ── 2. Python 版本检查 ────────────────────────────────────────────────────────
info "检查 Python 版本..."
if ! command -v python3 &>/dev/null; then
  fail "未找到 python3。请先安装 Python 3.10+：https://www.python.org/downloads/"
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ]]; then
  fail "Python $PY_VERSION 不支持，需要 3.10 及以上版本"
fi
ok "Python $PY_VERSION ($(which python3))"

# ── 3. pip 检查 ───────────────────────────────────────────────────────────────
info "检查 pip..."
if ! python3 -m pip --version &>/dev/null; then
  warn "pip 未安装，尝试安装..."
  python3 -m ensurepip --upgrade
fi
ok "pip $(python3 -m pip --version | awk '{print $2}')"

# ── 4. 安装 Python 依赖 ───────────────────────────────────────────────────────
info "检查 Python 依赖..."
ALL_INSTALLED=true
for pkg in flask openai pyautogui pyperclip PIL numpy cv2 dotenv; do
  if ! python3 -c "import $pkg" 2>/dev/null; then
    ALL_INSTALLED=false
    break
  fi
done

if $ALL_INSTALLED; then
  ok "依赖已全部安装，跳过"
else
  info "安装缺失依赖..."
  python3 -m pip install -r requirements.txt --quiet
  ok "依赖安装完成"
fi

# ── 5. 验证关键依赖可导入 ─────────────────────────────────────────────────────
info "验证关键依赖..."
MISSING=""
for pkg in flask openai pyautogui pyperclip PIL numpy cv2 dotenv; do
  if ! python3 -c "import $pkg" 2>/dev/null; then
    MISSING="$MISSING $pkg"
  fi
done
if [[ -n "$MISSING" ]]; then
  fail "以下依赖导入失败：$MISSING\n请检查 pip 安装日志"
fi
ok "所有依赖验证通过"

# ── 6. 配置 .env ──────────────────────────────────────────────────────────────
info "检查 .env 配置..."
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  warn ".env 文件已从 .env.example 创建"
  warn "请编辑 .env 填入以下内容："
  echo ""
  echo "    OPENAI_BASE_URL=https://api.qnaigc.com/v1"
  echo "    OPENAI_API_KEY=你的真实Key"
  echo "    OPENAI_MODEL=deepseek-v3-0324"
  echo ""
  echo -n "  是否现在打开编辑器编辑 .env？(y/n) "
  read -r OPEN_ENV
  if [[ "$OPEN_ENV" == "y" || "$OPEN_ENV" == "Y" ]]; then
    open -e .env 2>/dev/null || nano .env
  else
    warn "请稍后手动编辑 .env 文件再运行系统"
  fi
else
  # 检查 KEY 是否还是占位符
  if grep -q "your_key_here" .env 2>/dev/null; then
    warn ".env 存在但 OPENAI_API_KEY 仍为占位符，请编辑 .env 填入真实 Key"
  else
    ok ".env 已配置"
  fi
fi

# ── 7. 微信安装检查 ───────────────────────────────────────────────────────────
info "检查微信桌面版..."
if [[ -d "/Applications/WeChat.app" ]]; then
  ok "微信桌面版已安装"
else
  warn "未在 /Applications 找到微信，请确认微信桌面版已安装并登录"
fi

# ── 8. 辅助功能权限提示 ───────────────────────────────────────────────────────
info "辅助功能权限..."
echo ""
echo "  本工具需要辅助功能权限才能控制微信窗口。"
echo "  请手动确认以下设置："
echo ""
echo "  系统设置 → 隐私与安全性 → 辅助功能"
echo "  → 勾选 Terminal.app（或运行本脚本的终端应用）"
echo ""
echo -n "  是否现在打开系统设置？(y/n) "
read -r OPEN_PREFS
if [[ "$OPEN_PREFS" == "y" || "$OPEN_PREFS" == "Y" ]]; then
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
fi

# ── 9. start.command 权限 ─────────────────────────────────────────────────────
info "设置 start.command 执行权限..."
chmod +x start.command
ok "start.command 可执行"

# ── 10. logs 目录 ─────────────────────────────────────────────────────────────
info "确保 logs 目录存在..."
mkdir -p logs
ok "logs/ 目录就绪"

# ── 完成 ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}================================================${RESET}"
echo -e "${GREEN}${BOLD}  安装完成！${RESET}"
echo -e "${BOLD}================================================${RESET}"
echo ""
echo "  启动方式："
echo ""
echo "  方式一（双击）：start.command"
echo "  方式二（终端）：python3 app.py"
echo "  方式三（命令行）：python3 crew_sender.py <CSV文件>"
echo ""
