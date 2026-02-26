#!/usr/bin/env bash
# Install Ollama with Podman, pull models, and verify.
# Run on the host where Ollama should run (e.g. remote server). Requires Podman.
#
# Usage:
#   ./install_ollama_podman.sh              # CPU, bind to 0.0.0.0:11434, default models
#   OLLAMA_GPU=1 ./install_ollama_podman.sh # Use NVIDIA GPU if available
#   OLLAMA_MODELS="llama3.2 mistral" ./install_ollama_podman.sh  # Custom model list
#
# Then set OLLAMA_HOST in LogToolAI/config.py to http://<this-host-ip>:11434

set -e

CONTAINER_NAME="${OLLAMA_CONTAINER_NAME:-ollama}"
VOLUME_NAME="${OLLAMA_VOLUME_NAME:-ollama-data}"
PORT="${OLLAMA_PORT:-11434}"
# Default: one small/fast model for LogToolAI (optional: add more)
DEFAULT_MODELS="llama3.2:1b"
MODELS="${OLLAMA_MODELS:-$DEFAULT_MODELS}"

echo "=== Ollama install (Podman) ==="
if ! command -v podman &>/dev/null; then
  echo "Error: podman not found. Install Podman first (e.g. dnf install podman)."
  exit 1
fi

# Remove existing container if it exists (optional: leave commented to preserve existing)
if podman ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Container '${CONTAINER_NAME}' already exists. Stopping and removing for reinstall..."
  podman stop "${CONTAINER_NAME}" 2>/dev/null || true
  podman rm "${CONTAINER_NAME}" 2>/dev/null || true
fi

echo "Creating volume ${VOLUME_NAME} (if needed)..."
podman volume create "${VOLUME_NAME}" 2>/dev/null || true

echo "Starting Ollama container (port ${PORT})..."
if [ "${OLLAMA_GPU}" = "1" ]; then
  echo "GPU mode: --gpus=all"
  podman run -d \
    --name "${CONTAINER_NAME}" \
    -v "${VOLUME_NAME}:/root/.ollama" \
    -p "0.0.0.0:${PORT}:11434" \
    --gpus=all \
    ollama/ollama
else
  podman run -d \
    --name "${CONTAINER_NAME}" \
    -v "${VOLUME_NAME}:/root/.ollama" \
    -p "0.0.0.0:${PORT}:11434" \
    ollama/ollama
fi

echo "Waiting for Ollama to be ready..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/api/version" 2>/dev/null | grep -q 200; then
    echo "Ollama is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Timeout waiting for Ollama. Check: podman logs ${CONTAINER_NAME}"
    exit 1
  fi
  sleep 2
done

echo "Pulling models: ${MODELS}"
for model in $MODELS; do
  echo "  - $model"
  podman exec "${CONTAINER_NAME}" ollama pull "$model" || true
done

echo ""
echo "=== Verification ==="
if curl -s "http://localhost:${PORT}/api/tags" | head -c 200; then
  echo ""
  echo "OK: Ollama is running and responding at http://localhost:${PORT}"
  echo "From another host use: http://<this-server-ip>:${PORT}"
  echo "Set OLLAMA_HOST in LogToolAI/config.py to that URL."
else
  echo "Warning: curl to /api/tags failed. Check: podman logs ${CONTAINER_NAME}"
  exit 1
fi
