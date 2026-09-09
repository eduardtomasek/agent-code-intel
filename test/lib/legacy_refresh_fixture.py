#!/usr/bin/env python3
"""Create fixtures for the supported legacy ``refresh-intel.sh`` migration."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def write_pristine(directory: Path, workspace: str) -> Path:
    """Write the exact stamped legacy file that production still recognises."""
    path = directory / "refresh-intel.sh"
    lines = [
        "#!/usr/bin/env bash",
        "__STAMP__",
        "#",
        "# refresh-intel.sh -- test fixture",
        "",
        f'WORKSPACE="{workspace}"',
        'PROJECT="whatever"',
        "",
        "echo hi",
    ]
    index = lines.index("__STAMP__")
    body = "\n".join(lines[:index] + lines[index + 1 :])
    lines[index] = "# code-intel-init: version=9.9.9 body=" + hashlib.sha256(
        body.encode()
    ).hexdigest()
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", choices=("pristine", "modified"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("workspace")
    args = parser.parse_args()

    path = write_pristine(args.directory, args.workspace)
    if args.state == "modified":
        with path.open("a") as handle:
            handle.write("\n# a hand-edited line\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
