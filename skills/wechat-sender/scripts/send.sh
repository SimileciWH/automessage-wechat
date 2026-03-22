#!/bin/bash
# send.sh — 船员打卡消息发送入口
#
# 用法：
#   send.sh                          # 启动 Web 控制台
#   send.sh <csv文件>                 # 命令行发送（正式模式）
#   send.sh <csv文件> --safe          # 命令行安全模式
#   send.sh <csv文件> --dry-run       # 只验证备注名
#   send.sh <csv文件> --skip 张三,李四 # 跳过指定人
#   send.sh --web                     # 强制启动 Web 控制台

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_DIR"

# 检查 .env
if [ ! -f ".env" ]; then
  echo "❌ 未找到 .env，请先运行 setup.sh"
  exit 1
fi

# 无参数或 --web：启动 Web 控制台
if [ $# -eq 0 ] || [ "$1" = "--web" ]; then
  echo "🌐 启动 Web 控制台..."
  echo "   浏览器打开 http://localhost:5001"
  python3 app.py
  exit 0
fi

# 有 CSV 参数：命令行模式
CSV_FILE="$1"
shift

if [ ! -f "$CSV_FILE" ]; then
  echo "❌ CSV 文件不存在：$CSV_FILE"
  echo "请检查文件路径"
  exit 1
fi

echo "📋 CSV：$CSV_FILE"
echo "⚙️  参数：$*"
echo ""

python3 crew_sender.py "$CSV_FILE" "$@"
