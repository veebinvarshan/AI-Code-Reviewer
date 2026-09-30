#!/bin/sh
# Starts the Ollama daemon, waits for it to be ready, then pulls the
# model named by $MODEL_NAME if it isn't already present locally.
# This lets `docker compose up` be a true one-command start with no
# manual `ollama pull` step.
set -e

ollama serve &
SERVE_PID=$!

echo "Waiting for Ollama daemon to become ready..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

MODEL_NAME="${MODEL_NAME:-qwen2.5-coder:7b-instruct-q4_K_M}"

if ollama list | grep -q "$MODEL_NAME"; then
  echo "Model $MODEL_NAME already present."
else
  echo "Pulling $MODEL_NAME (first run only, this can take a while)..."
  ollama pull "$MODEL_NAME"
fi

wait $SERVE_PID
