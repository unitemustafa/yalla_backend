"""Remove unrelated Android log streams and sensitive diagnostic identifiers.

Only supplied text logs are rewritten; measurement JSON/CSV/traces are untouched.
"""

import argparse
import re
from pathlib import Path


def sanitize(content):
    # Normalize NUL-padded diagnostic text from older PowerShell redirects.
    content = content.replace("\x00", "").lstrip("\ufeff\ufffd")
    # flutter drive also forwards logs from unrelated installed Flutter apps.
    own_pids = set(re.findall(r"I/flutter\s*\(\s*(\d+)\):\s*\d\d:\d\d\s+\+0:", content))
    lines = []
    removed = 0
    for line in content.splitlines():
        android = re.search(r"[VDIWEF]/[\w.]+\s*\(\s*(\d+)\):", line)
        if android and android.group(1) not in own_pids:
            removed += 1
            continue
        line = re.sub(
            r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "[redacted-device-id]", line
        )
        line = re.sub(
            r"https?://127\.0\.0\.1:\d+/[^\s'\"<>]+", "[redacted-vm-service-url]", line
        )
        line = re.sub(r"(?i)Bearer\s+[A-Za-z0-9_.-]+", "Bearer [redacted]", line)
        lines.append(line)
    return "\n".join(lines) + "\n", removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args()
    for path in args.logs:
        if path.suffix != ".log":
            raise ValueError("Only explicit .log diagnostics may be sanitized")
        raw = path.read_bytes()
        encoding = (
            "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        )
        content = raw.decode(encoding, errors="replace")
        cleaned, removed = sanitize(content)
        path.write_text(cleaned, encoding="utf-8")
        print(f"Sanitized {path.name}: removed {removed} unrelated Android lines")


if __name__ == "__main__":
    main()
