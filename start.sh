#!/bin/bash
# 一键启动 Research Collector（后端 + 前端）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查 .env
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，正在从 .env.example 复制..."
    cp .env.example .env
    echo "   请编辑 .env 填入 API Key 后重新运行。"
    exit 1
fi

echo "🚀 启动 Research Collector..."
echo ""

# 启动后端 API（后台运行）
echo "📡 启动后端 API (http://localhost:8000)..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

# 等待后端就绪
sleep 2

# 启动前端 UI
echo "🖥️  启动前端 UI (http://localhost:8501)..."
PYTHONPATH="$SCRIPT_DIR" streamlit run ui/streamlit_app.py --server.port 8501 &
UI_PID=$!

echo ""
echo "✅ 服务已启动："
echo "   后端 API: http://localhost:8000"
echo "   前端 UI:  http://localhost:8501"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，关闭子进程
cleanup() {
    echo ""
    echo "🛑 正在停止服务..."
    kill $API_PID 2>/dev/null
    kill $UI_PID 2>/dev/null
    wait $API_PID 2>/dev/null
    wait $UI_PID 2>/dev/null
    echo "👋 已停止。"
}

trap cleanup SIGINT SIGTERM

# 等待子进程
wait
