#!/usr/bin/env bash
echo "Stopping OpenShorts services..."
pkill -f "uvicorn app:app" || true
pkill -f "vite --host" || true
echo "OpenShorts stopped. (Ollama remains available in background)"
