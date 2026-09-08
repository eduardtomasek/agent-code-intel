# test/lib/fixtures.sh — shared test fixtures for the migration harness and the
# existing black-box suite.
#
# The legacy refresh-intel.sh stamp format (`# code-intel-init: version=… body=…`
# with a sha256 of the body) is checked by the tool in three places and must be
# reproduced byte-for-byte. Keeping the generator here means one definition, not
# one per caller.

# aci_write_pristine_refresh_script <dir> <workspace> — a refresh-intel.sh whose
# stamp hash matches its body, exactly as the old tool generated it. The tool's
# script_state() only parses this file, it never runs it.
aci_write_pristine_refresh_script() {
  local d="$1" ws="$2"
  python3 - "$d/refresh-intel.sh" "$ws" <<'PY'
import hashlib, sys
path, ws = sys.argv[1], sys.argv[2]
lines = [
    "#!/usr/bin/env bash",
    "__STAMP__",
    "#",
    "# refresh-intel.sh -- test fixture",
    "",
    'WORKSPACE="%s"' % ws,
    'PROJECT="whatever"',
    "",
    "echo hi",
]
i = lines.index("__STAMP__")
body = "\n".join(lines[:i] + lines[i + 1:])
h = hashlib.sha256(body.encode()).hexdigest()
lines[i] = "# code-intel-init: version=9.9.9 body=%s" % h
open(path, "w").write("\n".join(lines))
PY
}

# aci_write_modified_refresh_script <dir> <workspace> — same shape, then a
# hand-edit so the stamp hash no longer matches (script_state() == modified).
aci_write_modified_refresh_script() {
  aci_write_pristine_refresh_script "$1" "$2"
  printf '\n# a hand-edited line\n' >> "$1/refresh-intel.sh"
}
