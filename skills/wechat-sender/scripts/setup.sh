#!/bin/bash
# setup.sh — 首次安装检查与依赖安装
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=== 船员发送系统 — 环境检查 ==="
echo "项目路径：$PROJECT_DIR"

# 检查 Python3
if ! command -v python3 &>/dev/null; then
  echo "❌ 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi
echo "✅ Python: $(python3 --version)"

# 检查并安装依赖
cd "$PROJECT_DIR"
if python3 -c "import flask, openai, pyautogui, pyperclip, dotenv" 2>/dev/null; then
  echo "✅ 依赖已安装"
else
  echo "📦 安装依赖..."
  pip3 install -r requirements.txt
  echo "✅ 依赖安装完成"
fi

# 检查 .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo ""
  echo "⚠️  未找到 .env 文件，正在从 .env.example 创建..."
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  echo "请编辑 $PROJECT_DIR/.env，填入真实的 OPENAI_API_KEY"
  open "$PROJECT_DIR/.env" 2>/dev/null || echo "文件路径：$PROJECT_DIR/.env"
  exit 1
else
  echo "✅ .env 存在"
fi

# 检查辅助功能权限（仅检测，不能自动授权）
echo ""
echo "⚠️  请确认已授权辅助功能权限："
echo "   系统设置 → 隐私与安全性 → 辅助功能 → Terminal.app ✓"

echo ""
echo "=== 环境检查完成，可以运行了 ==="
