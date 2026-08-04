#!/bin/bash
set -e

echo "=== Transversal2 Imagen Container ==="
echo "Starting Ollama..."

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "Waiting for Ollama..."
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama ready."
        break
    fi
    sleep 2
done

# Pull vision model if not present
echo "Checking vision model..."
if ! ollama list 2>/dev/null | grep -q "gemma3:12b"; then
    echo "Pulling gemma3:12b (this may take a while)..."
    ollama pull gemma3:12b
fi

echo "=== Starting ComfyUI ==="
# Start ComfyUI (blocking)
exec python3 /app/ComfyUI/main.py --listen --port 8188
