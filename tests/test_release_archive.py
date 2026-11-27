import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("isolate_build_release", ROOT / "scripts/isolate-build-release.py")
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)
from isolate_install import plan_release


@unittest.skipUnless(shutil.which("git"), "Git is required for release package tests")
class ReleaseArchiveTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.repository = self.directory / "repository"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")

    def git(self, *arguments):
        result = subprocess.run(["git", "-c", "user.name=Release Fixture", "-c", "user.email=release@example.test",
                                  "-C", str(self.repository), *arguments], check=True, capture_output=True)
        return result.stdout.decode().strip()

    def commit_fixture(self, lock=True):
        files = {"requirements.txt": "# runtime requirements\n", "shared/application.py": "original = True\n",
                 "scripts/isolate-service.py": "# launcher\n", "scripts/isolate-install.py": "# installer\n",
                 "wrappers/client.py": "# client\n", "README.md": "Release guide\n",
                 "deploy/RELEASES.md": "Deployment guide\n", "configs/neutral.example.yml": "{}\n",
                 "ansible/enroll-hosts.example.yml": "{}\n", "ansible/hosts.ini": "old inventory\n",
                 "img1.png": "outdated screenshot\n", "shared/logs/audit.log": "private log fixture\n",
                 "shared/secret.pfx": "private certificate fixture\n", "configs/isolate.yml": "instance config\n"}
        if lock:
            files[PACKAGER.RUNTIME_LOCK] = "# exact runtime lock fixture\n"
        for name, body in files.items():
            path = self.repository / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body.encode())
        self.git("add", "--all")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "test fixture")
        return self.git("rev-parse", "HEAD")

    def test_committed_release_is_reproducible_and_matches_installer(self):
        revision = self.commit_fixture()
        (self.repository / "shared/application.py").write_bytes(b"original = False\n")
        (self.repository / "shared/local_override.py").write_bytes(b"ignored = True\n")
        sbom = self.directory / "bom.json"
        sbom.write_text('{"bomFormat":"CycloneDX"}', encoding="utf-8")
        version = "2.1.0-rc.1"
        first, second = self.directory / "first", self.directory / "second"
        metadata = PACKAGER.build_release(self.repository, "HEAD", version, first, sbom)
        PACKAGER.build_release(self.repository, revision, version, second, sbom)
        self.assertEqual(metadata["revision"], revision)
        self.assertEqual(json.loads((first / "release.json").read_bytes()), metadata)
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
        for row in (first / "SHA256SUMS").read_text(encoding="ascii").splitlines():
            digest, file = row.split("  ")
            self.assertEqual(digest, hashlib.sha256((first / file).read_bytes()).hexdigest())
        with tarfile.open(first / metadata["archive"]) as archive:
            prefix = "isolate-" + version + "/"
            names = {name.removeprefix(prefix) for name in archive.getnames()}
            self.assertEqual(names, {"requirements.txt", PACKAGER.RUNTIME_LOCK, "shared/application.py",
                                     "scripts/isolate-service.py", "scripts/isolate-install.py", "wrappers/client.py",
                                     "README.md", "deploy/RELEASES.md", "configs/neutral.example.yml",
                                     "ansible/enroll-hosts.example.yml"})
            self.assertEqual(archive.extractfile(prefix + "shared/application.py").read(), b"original = True\n")
            extracted = self.directory / "extracted"
            archive.extractall(extracted, filter="data")
        config = self.directory / "site.yml"
        config.write_text("{}\n", encoding="utf-8")
        config.chmod(0o600)
        plan = plan_release(self.directory / "runtime", extracted / ("isolate-" + version), version, config, service_user="")
        self.assertEqual(metadata["source_sha256"], plan["source_sha256"])
        self.assertEqual(metadata["source_file_count"], plan["file_count"])

    def test_missing_runtime_lock_fails_before_writing_release(self):
        self.commit_fixture(lock=False)
        output = self.directory / "out"
        with self.assertRaisesRegex(ValueError, "dependencies"):
            PACKAGER.build_release(self.repository, "HEAD", "2.1.0-rc.1", output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
