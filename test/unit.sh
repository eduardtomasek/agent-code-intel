#!/usr/bin/env bash
# test/unit.sh — the `unittest` layer (issue #43 §2, layer 2): pure logic for
# the Python port, no external stack.
#
# Runs under Python 3.11.x by default. ACI_PYTHON selects a supplementary
# interpreter explicitly.
#
# Usage:
#   test/unit.sh                         # every test
#   test/unit.sh test_cli_parser         # one module
#   ACI_PYTHON=python3.14 test/unit.sh   # supplementary interpreter

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$HERE/.." && pwd)"
PY_NAME="${ACI_PYTHON:-python3.11}"
PY="$(command -v "$PY_NAME")" || {
  echo "[ERROR: no usable Python — set ACI_PYTHON, or install Python 3.11]" >&2
  exit 1
}

echo "python3: $("$PY" --version 2>&1)  ($PY)"
echo

# The test modules put $REPO on sys.path themselves; run them as top-level
# modules from test/unit (no __init__.py anywhere under test/).
cd "$HERE/unit"
if [[ $# -gt 0 ]]; then
  TARGETS=(); for t in "$@"; do TARGETS+=("${t%.py}"); done
  exec "$PY" -m unittest -v "${TARGETS[@]}"
fi
exec "$PY" -m unittest discover -s "$HERE/unit" -t "$HERE/unit" -v
