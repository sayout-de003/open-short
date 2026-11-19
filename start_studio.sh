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
      -e OLLAMA_KEEP_ALIVE=-1 \
      ollama/ollama:latest
fi

# 2. Start services via systemd
echo "Starting OpenShorts services via systemd..."
systemctl start openshort-backend openshort-frontend
sleep 2

echo "=================================================="
echo " Studio is LIVE and Operational!"
echo " Web Dashboard: http://localhost:5175"
echo " Backend API:   http://localhost:8000"
echo " Ollama Models: http://localhost:11434"
echo "=================================================="
