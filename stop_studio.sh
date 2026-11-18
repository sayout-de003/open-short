#!/usr/bin/env bash
echo "Stopping OpenShorts services..."
systemctl stop openshort-backend openshort-frontend
echo "OpenShorts stopped. (Ollama remains available in background)"
