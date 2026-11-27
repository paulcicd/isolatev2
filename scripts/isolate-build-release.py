#!/usr/bin/env python3
"""Build a deterministic Linux/systemd distribution from a Git commit."""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "shared"))
from isolate_install import CODE_DIRECTORIES, CODE_FILES, InstallError, _canonical, _version


RUNTIME_LOCK = "requirements-linux-py312.lock"
DIST_FILES = frozenset(("README.md", "CHANGELOG.md", "Dockerfile.prod", ".dockerignore", "package.json",
                        "package-lock.json", "ansible/enroll-isolate-hosts.yml", "ansible/enroll-hosts.example.yml"))
DIST_DIRECTORIES = frozenset(("deploy", "ui", "terraform-provider-isolate"))
UNSHIPPED_DIRECTORIES = frozenset((".git", ".runtime", ".venv", "__pycache__", "keys", "logs", "node_modules", "secrets"))
SECRET_NAMES = frozenset((".env", "authorized_keys", "known_hosts", "id_rsa", "id_ed25519", "id_ecdsa"))
UNSHIPPED_SUFFIXES = frozenset((".db", ".env", ".key", ".log", ".p12", ".pem", ".pfx", ".pyc", ".pyo", ".sqlite", ".sqlite3"))


def _git(repository, *arguments):
    result = subprocess.run(["git", "-C", str(repository), *arguments], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Git command failed: " + arguments[0])
    return result.stdout


def _installer_source(path):
    return len(path.parts) == 1 and path.name in {*CODE_FILES, RUNTIME_LOCK} or (
        path.parts[0] in CODE_DIRECTORIES and len(path.parts) > 1 and path.suffix not in (".pyc", ".pyo")
    )


def _included(path):
    if any(part.casefold() in UNSHIPPED_DIRECTORIES or part.startswith(".tmp-") for part in path.parts):
        return False
    if path.name.casefold() in SECRET_NAMES or path.suffix.casefold() in UNSHIPPED_SUFFIXES:
        return False
    return (
        _installer_source(path)
        or path.as_posix() in DIST_FILES
        or path.parts[0] in DIST_DIRECTORIES
        or path.parts[:3] == ("ansible", "roles", "isolate_host_enrollment")
        or (len(path.parts) == 2 and path.parts[0] == "configs"
            and (path.name == "defaults.conf" or path.name.endswith(".example.yml")))
    )


def _archive_files(repository, revision):
    """Read approved paths directly from the committed tree without extracting it."""
    selected = {}
    portable_names = set()
    with tarfile.open(fileobj=io.BytesIO(_git(repository, "archive", "--format=tar", revision)), mode="r:") as tree:
        for item in tree:
            if item.isdir():
                continue
            path = PurePosixPath(item.name)
            if not item.name or path.is_absolute() or ".." in path.parts or "\\" in item.name or path.as_posix() != item.name:
                raise ValueError("Git tree contains an unsafe distribution path")
            if not _included(path):
                continue
            if not item.isfile() or item.name.casefold() in portable_names:
                raise ValueError("Unsafe or colliding distribution entry: " + item.name)
            portable_names.add(item.name.casefold())
            selected[path] = (tree.extractfile(item).read(), 0o755 if item.mode & 0o111 else 0o644)
    required = ("requirements.txt", RUNTIME_LOCK, "scripts/isolate-service.py", "scripts/isolate-install.py")
    if any(PurePosixPath(name) not in selected for name in required) or any(
        not any(path.parts[0] == directory for path in selected) for directory in CODE_DIRECTORIES
    ):
        raise ValueError("Committed tree is missing launcher, dependencies or application source")
    return selected


def _write_archive(destination, name, selected, timestamp):
    with destination.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w:", format=tarfile.PAX_FORMAT) as archive:
                for path, (content, mode) in sorted(selected.items()):
                    item = tarfile.TarInfo(name + "/" + path.as_posix())
                    item.mode, item.size, item.mtime = mode, len(content), timestamp
                    archive.addfile(item, io.BytesIO(content))


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def build_release(repository, ref, version, output, sbom=None):
    version = _version(version)
    revision = _git(repository, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    timestamp = int(_git(repository, "show", "-s", "--format=%ct", revision))
    selected = _archive_files(repository, revision)
    inventory = {path.as_posix(): sha256(content) for path, (content, _) in selected.items() if _installer_source(path)}
    if sbom is not None:
        sbom_data = Path(sbom).read_bytes()
        document = json.loads(sbom_data)
        if not isinstance(document, dict) or document.get("bomFormat") != "CycloneDX":
            raise ValueError("SBOM must be CycloneDX JSON")
    name = "isolate-" + version
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("Release output directory must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    artifact_names = [name + ".tar.gz", "release.json", "SHA256SUMS"]
    if sbom is not None:
        artifact_names.append("dependency-sbom.json")
    with tempfile.TemporaryDirectory(prefix="release-", dir=output.parent) as temporary:
        stage = Path(temporary) / "dist"
        stage.mkdir()
        archive_name = artifact_names[0]
        _write_archive(stage / archive_name, name, selected, timestamp)
        release = {"version": version, "revision": revision, "archive": archive_name,
                   "archive_sha256": sha256((stage / archive_name).read_bytes()),
                   "source_sha256": sha256(_canonical(inventory)), "source_file_count": len(inventory),
                   "dependency_lock_sha256": inventory[RUNTIME_LOCK]}
        (stage / "release.json").write_bytes(_canonical(release) + b"\n")
        if sbom is not None:
            (stage / "dependency-sbom.json").write_bytes(sbom_data)
        checksums = "".join(f"{sha256((stage / artifact).read_bytes())}  {artifact}\n"
                            for artifact in sorted(artifact_names) if artifact != "SHA256SUMS")
        (stage / "SHA256SUMS").write_bytes(checksums.encode("ascii"))
        stage.rename(output)
    return release


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Git ref to resolve to a committed source tree")
    parser.add_argument("--version", required=True, help="release version without tag prefix v")
    parser.add_argument("--output", type=Path, required=True, help="destination for package and metadata")
    parser.add_argument("--sbom", type=Path, help="CycloneDX JSON SBOM for the runtime lock")
    args = parser.parse_args(argv)
    try:
        result = build_release(REPOSITORY, args.ref, args.version, args.output, args.sbom)
    except (InstallError, OSError, ValueError, tarfile.TarError) as exc:
        parser.exit(2, "release packaging failed: {}\n".format(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
