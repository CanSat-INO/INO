#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source scripts/environment.sh
exec /usr/bin/python3 tools/settings_gui.py
