"""Regression checks for the directory package's release requirements."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class DirectoryPackageTests(unittest.TestCase):
    def test_rejects_broken_release_packages(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(source, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            manifest = root / "plugins/qurl/plugin.json"
            original = manifest.read_text()
            for field, value, expected in (
                ("requires_local_executor", False, "requires_local_executor"),
                ("shortDescription", "x" * 31, "shortDescription"),
                ("logo", "./../README.md", "inside the plugin"),
            ):
                with self.subTest(field=field):
                    data = json.loads(original)
                    openai = data["extensions"]["com.openai"]
                    target = openai if field == "requires_local_executor" else openai["interface"]
                    target[field] = value
                    manifest.write_text(json.dumps(data))
                    result = subprocess.run(
                        [sys.executable, "-I", str(root / "scripts/check_manifests.py"), str(root)],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected, result.stdout)
            manifest.write_text(original)
            (root / "plugins/qurl/skills/qurl/references/access-policies.md").unlink()
            result = subprocess.run(
                [sys.executable, "-I", str(root / "scripts/check_manifests.py"), str(root)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing or unsafe bundled reference", result.stdout)


if __name__ == "__main__":
    unittest.main()
