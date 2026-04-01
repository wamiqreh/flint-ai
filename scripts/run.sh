#!/bin/bash
# Flint example runner — Unix shortcut
# Usage: scripts/run.sh examples/demo.py [--mode server]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python "$SCRIPT_DIR/run.py" "$@"
