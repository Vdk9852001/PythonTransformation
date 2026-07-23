#!/bin/zsh

SCRIPT_DIR="${0:A:h}"
WORKSPACE_PYTHON="/Users/dheerajkashyapvaranasi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"

if [[ ! -x "$WORKSPACE_PYTHON" ]]; then
  osascript -e 'display alert "Python runtime not found" message "Run: python -m pip install -r requirements.txt, then start app.py with that Python environment." as critical'
  exit 1
fi

cd "$SCRIPT_DIR" || exit 1
exec "$WORKSPACE_PYTHON" app.py
