"""Hook storage locks serialize processes on both supported OS families."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from straw_boss.file_lock import lock_exclusive


class FileLockTest(unittest.TestCase):
    def test_contender_waits_until_descriptor_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'shared.lock'
            code = (
                'import sys\nfrom straw_boss.file_lock import lock_exclusive\n'
                'with open(sys.argv[1], "a") as file:\n'
                ' print("ready", flush=True)\n'
                ' lock_exclusive(file)\n'
                ' print("acquired", flush=True)\n'
            )
            with path.open('a') as owner:
                lock_exclusive(owner)
                child = subprocess.Popen(
                    [sys.executable, '-c', code, str(path)], stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                    env={**os.environ, 'PYTHONPATH': str(SCRIPTS)})
                try:
                    self.assertEqual(child.stdout.readline().strip(), 'ready')
                    with self.assertRaises(subprocess.TimeoutExpired):
                        child.wait(timeout=0.2)
                except BaseException:
                    child.kill()
                    child.communicate()
                    raise
            try:
                stdout, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, 0, stderr)
                self.assertEqual(stdout.strip(), 'acquired')
            finally:
                if child.poll() is None:
                    child.kill()
                    child.communicate()
