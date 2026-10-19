"""Push generated test credentials into the isolated app's external sandbox."""

import argparse
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = "com.yallamarket.app.performance"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--device", required=True)
    args = parser.parse_args()
    manifest = json.loads(
        (ROOT / "artifacts/accounts.private.json").read_text(encoding="utf-8")
    )
    if manifest.get("environment") != "isolated-local-performance":
        raise ValueError("Wrong fixture environment")
    account = manifest["accounts"][-1]
    content = {
        "environment": manifest["environment"],
        "email": account["email"],
        "password": account["password"],
        "address_id": account["address_id"],
        **manifest["catalogs"][-1],
    }
    target = ROOT / "artifacts/mobile.private.json"
    target.write_text(json.dumps(content), encoding="utf-8")
    target.chmod(0o600)
    adb = [args.adb, "-s", args.device]
    directory = f"/sdcard/Android/data/{PACKAGE}/files"
    for _ in range(120):
        packages = subprocess.run(
            adb + ["shell", "pm", "list", "packages", PACKAGE],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        if PACKAGE in packages:
            subprocess.run(
                adb + ["shell", "mkdir", "-p", directory],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                adb + ["push", str(target), directory + "/performance.private.json"],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                adb + ["reverse", "tcp:18081", "tcp:18081"],
                capture_output=True,
                check=True,
            )
            print(
                "Generated test credentials pushed to isolated package; no values printed"
            )
            return
        time.sleep(1)
    raise RuntimeError("Isolated application was not installed within 120 seconds")


if __name__ == "__main__":
    main()
