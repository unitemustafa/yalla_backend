"""Record source revisions and opt-in APK hashes without local secrets."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, action="append", required=True)
    parser.add_argument("--apk-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repositories = []
    for repo in args.repository:
        files = git(
            repo, "ls-files", "--modified", "--others", "--exclude-standard"
        ).splitlines()
        sources = {
            name: digest(repo / name)
            for name in files
            if (repo / name).is_file()
            and (repo / name).suffix
            in {".py", ".dart", ".kts", ".yaml", ".xml", ".md", ".txt", ".lock"}
            and "private" not in name.lower()
            and ".env" not in name.lower()
            and not name.startswith("docs/performance-results-")
        }
        repositories.append(
            {
                "repository": repo.resolve().name,
                "head": git(repo, "rev-parse", "HEAD"),
                "branch": git(repo, "branch", "--show-current"),
                "dirty_sources_sha256": sources,
            }
        )
    apks = [
        {"file": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
        for path in sorted(args.apk_directory.glob("*.apk"))
    ]
    toolchain_file = args.apk_directory / "flutter-version.json"
    toolchain = (
        json.loads(toolchain_file.read_text(encoding="utf-8-sig"))
        if toolchain_file.exists()
        else None
    )
    args.output.write_text(
        json.dumps(
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "repositories": repositories,
                "apks": apks,
                "flutter_toolchain": toolchain,
                "limitations": "End-of-session source hashes; historical APKs retain their own hashes and run metadata, not a claim all binaries match final sources. Local performance APKs are not production builds.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Manifest: {len(repositories)} repositories, {len(apks)} APKs")


if __name__ == "__main__":
    main()
