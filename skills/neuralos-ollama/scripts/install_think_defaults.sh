#!/bin/bash
# Install neuralOS-ollama defaults: models, env, verification.
set -e
MODEL="${NEURALOS_OLLAMA_MODEL:-qwen3.5:9b}"

echo "== pulling $MODEL (thinking-capable; callers send think:false) =="
ollama pull "$MODEL"

echo "== writing env defaults to ~/.zshrc (idempotent) =="
grep -q NEURALOS_OLLAMA_MODEL ~/.zshrc 2>/dev/null || \
  echo "export NEURALOS_OLLAMA_MODEL=\"$MODEL\"" >> ~/.zshrc
grep -q NEURALOSD_REASON_MODEL ~/.zshrc 2>/dev/null || \
  echo "export NEURALOSD_REASON_MODEL=\"$MODEL\"" >> ~/.zshrc
# think is disabled per-request by the client; NEURALOSD_THINK=1 re-enables
grep -q NEURALOSD_THINK ~/.zshrc 2>/dev/null || \
  echo "export NEURALOSD_THINK=0" >> ~/.zshrc

echo "== done. verify with: python3 scripts/verify_setup.py =="
