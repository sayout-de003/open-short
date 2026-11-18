#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=================================================="
echo "   Starting Local AI Video Clipping Studio"
echo "=================================================="

# 1. Ensure Ollama container is running
if ! docker ps | grep -q "ollama"; then
    echo "Starting Ollama service..."
    docker start ollama || docker run -d --name ollama --restart unless-stopped \
      -v /root/.ollama:/root/.ollama \
      -p 11434:11434 \
      -e OLLAMA_NUM_PARALLEL=1 \
      -e OLLAMA_MAX_LOADED_MODELS=1 \
      -e OLLAMA_CONTEXT_LENGTH=8192 \
      ollama/ollama:latest
fi

# 2. Start Backend FastAPI if not running
if ! pgrep -f "uvicorn app:app" > /dev/null; then
    echo "Starting OpenShorts Backend (port 8000)..."
    nohup /root/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 > /root/openshort/output/backend.log 2>&1 &
    sleep 2
fi

# 3. Start Frontend Dashboard if not running
if ! pgrep -f "vite --host" > /dev/null; then
    echo "Starting OpenShorts Web Dashboard (port 5175)..."
    cd "$DIR/dashboard"
    nohup npx vite --host 0.0.0.0 --port 5175 > /root/openshort/output/frontend.log 2>&1 &
    cd "$DIR"
    sleep 2
fi

echo "=================================================="
echo " Studio is LIVE and Operational!"
echo " Web Dashboard: http://localhost:5175"
echo " Backend API:   http://localhost:8000"
echo " Ollama Models: http://localhost:11434"
echo "=================================================="
