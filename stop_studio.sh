#!/usr/bin/env bash
echo "Stopping CREOVIS services..."
systemctl stop creovis-backend creovis-frontend 2>/dev/null || systemctl stop openshort-backend openshort-frontend
echo "CREOVIS stopped. (Ollama remains available in background)"
