#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
if [[ ! -f "$ROOT/scripts/setup.sh" ]]; then
 echo 'Run setup from the source checkout: see docs/setup/README.md.' >&2; exit 2
fi
exec bash "$ROOT/scripts/setup.sh" --system-only "$@"
