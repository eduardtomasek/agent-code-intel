#!/usr/bin/env bash
# test/reference-suite.sh — the existing black-box suite, unchanged, run against
# the frozen Bash reference (commit 9406cce) under an isolated PATH that carries
# Python >= 3.11.
#
# This is acceptance criteria 1 and 2 of issue #49:
#   - the reference comes from git history into a temp executable, no second
#     long-lived copy in the working tree;
#   - test/run.sh's assertions and expected outputs are untouched — only the
#     PATH it runs under (ACI_TEST_PATH) and the TOOL it points at change.
#
# Usage:
#   test/reference-suite.sh                 # all tests
#   test/reference-suite.sh workspace_derived_from_basename   # one test

set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib/reference.sh"
. "$HERE/lib/isolated_path.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

aci_acquire_reference "$WORK" || exit 1
ISOLATED_PATH="$(aci_isolated_path "$WORK")" || exit 1
PYBIN="${ISOLATED_PATH%%:*}/python3"

echo "reference:     $ACI_REFERENCE_COMMIT:agent-code-intel -> $ACI_REFERENCE"
echo "isolated PATH: $ISOLATED_PATH"
echo "python3:       $("$PYBIN" --version 2>&1)"
echo

TOOL="$ACI_REFERENCE" \
EXPECTED_NAME="agent-code-intel" \
ACI_TEST_PATH="$ISOLATED_PATH" \
  "$HERE/run.sh" "$@"
