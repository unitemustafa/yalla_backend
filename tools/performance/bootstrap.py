"""Create ignored local-only secrets without reading production configuration."""

import secrets
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    target = root / ".env.local"
    if target.exists():
        if "PERF_RATE_LIMIT_SECRET=" not in target.read_text(encoding="utf-8"):
            with target.open("a", encoding="utf-8") as stream:
                stream.write(
                    "PERF_RATE_LIMIT_SECRET=" + secrets.token_urlsafe(64) + "\n"
                )
        print("Existing local configuration preserved")
        return
    target.write_text(
        "PERF_SECRET_KEY=" + secrets.token_urlsafe(64) + "\n"
        "PERF_DATABASE_PASSWORD=" + secrets.token_urlsafe(32) + "\n",
        encoding="utf-8",
    )
    with target.open("a", encoding="utf-8") as stream:
        stream.write("PERF_RATE_LIMIT_SECRET=" + secrets.token_urlsafe(64) + "\n")
    (root / "artifacts").mkdir(exist_ok=True)
    print("Created ignored local performance configuration")


if __name__ == "__main__":
    main()
