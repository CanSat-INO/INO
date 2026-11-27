#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CANSAT_GUI_PYTHON=${CANSAT_GUI_PYTHON:-$HERE/../../.venv/bin/python}
if [[ ! -x "$CANSAT_GUI_PYTHON" ]]; then
 echo '[ERROR] GUI environment is missing. Run setup-simulation.bat or bash scripts/setup.sh.' >&2
 echo 'See docs/setup/README.md.' >&2; exit 2
fi
exec bash "$HERE/launch_v13_4.sh" "$@"
