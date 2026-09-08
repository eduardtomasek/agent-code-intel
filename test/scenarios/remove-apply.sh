# scenario: `--remove --apply` on a project carrying .code-intel and a pristine
# legacy refresh-intel.sh, with no stack running.
# Mutating: deletes .code-intel and refresh-intel.sh, leaves file.txt. Each
# implementation runs over its own fixture; the manifest diff is what proves
# both delete exactly the same set.

scenario_name()       { echo "remove-apply"; }
scenario_invariants() { echo "RM-2 RM-4 ID-2"; }
scenario_args()       { echo "--remove --apply"; }

scenario_setup() {
  local fixture="$1"
  ( cd "$fixture"
    git init -q .
    printf 'x\n' > file.txt
    printf 'SCHEMA=1\nWORKSPACE=diff-remove-ws\nPROJECT=%s\n' "$(basename "$fixture")" > .code-intel )

  # A pristine refresh-intel.sh: the code-intel-init stamp's sha256 matches the
  # body, exactly as the old tool generated it (same fixture shape as
  # write_pristine_refresh_script in test/run.sh).
  python3 - "$fixture/refresh-intel.sh" "diff-remove-ws" <<'PY'
import hashlib, sys
path, ws = sys.argv[1], sys.argv[2]
lines = ["#!/usr/bin/env bash", "__STAMP__", "#",
         "# refresh-intel.sh -- test fixture", "",
         'WORKSPACE="%s"' % ws, 'PROJECT="whatever"', "", "echo hi"]
i = lines.index("__STAMP__")
body = "\n".join(lines[:i] + lines[i + 1:])
lines[i] = "# code-intel-init: version=9.9.9 body=%s" % hashlib.sha256(body.encode()).hexdigest()
open(path, "w").write("\n".join(lines))
PY
}
