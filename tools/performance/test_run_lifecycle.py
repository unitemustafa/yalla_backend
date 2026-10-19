"""The supervisor must not leave owned load processes running on interruption."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import psutil

from tools.performance.run import managed_generator


class GeneratorLifecycleTests(unittest.TestCase):
    def test_exception_stops_generator_and_its_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ready"
            code = (
                "import subprocess,sys,time;from pathlib import Path;"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
                "Path(sys.argv[1]).write_text('ready');time.sleep(60)"
            )
            owned = []
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                with managed_generator(
                    [sys.executable, "-c", code, str(marker)],
                    dict(os.environ),
                    subprocess.DEVNULL,
                ) as process:
                    deadline = time.monotonic() + 10
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(
                        marker.exists(), "Owned test generator did not start"
                    )
                    root = psutil.Process(process.pid)
                    owned = [root] + root.children(recursive=True)
                    self.assertGreater(len(owned), 1)
                    raise RuntimeError("simulated interruption")
            _, alive = psutil.wait_procs(owned, timeout=5)
            self.assertEqual(alive, [], "A load generator descendant survived cleanup")


if __name__ == "__main__":
    unittest.main()
