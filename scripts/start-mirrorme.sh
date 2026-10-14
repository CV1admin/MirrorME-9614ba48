#!/usr/bin/env sh
set -eu

MODEL="${MIRRORME_MODEL:-mirrorme:latest}"
BRIDGE_PORT="${MIRRORME_BRIDGE_PORT:-8765}"

command -v ollama >/dev/null 2>&1 || { echo "Ollama is not installed."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Python 3 is not installed."; exit 1; }

if ! ollama list | grep -q "^${MODEL}"; then
  # mirrorme:latest is built locally from ollama/Modelfile; other names are pulled.
  if [ "${MODEL}" = "mirrorme:latest" ] && [ -f ollama/Modelfile ]; then
    ollama create "${MODEL}" -f ollama/Modelfile
  else
    ollama pull "${MODEL}"
  fi
fi
python3 local_bridge/mirrorme_bridge.py --model "${MODEL}" --port "${BRIDGE_PORT}"
