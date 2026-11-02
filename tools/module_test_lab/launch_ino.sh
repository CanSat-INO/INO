#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CANSAT_GUI_PYTHON=${CANSAT_GUI_PYTHON:-$HERE/../../.venv/bin/python}
exec bash "$HERE/launch_v13_4.sh" "$@"
