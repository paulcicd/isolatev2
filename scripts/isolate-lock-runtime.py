#!/usr/bin/env python3
"""Refresh the CPython 3.12 Linux x86_64 release lock from PyPI wheels."""

import argparse
from email.parser import BytesParser
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent.parent
PYPI = "https://pypi.org/simple"
HEADER = (
    "# CPython 3.12, Linux x86_64, glibc 2.34 or newer.\n"
    "# One published wheel per package, including transitive dependencies.\n"
    "# Refresh with python scripts/isolate-lock-runtime.py (uv 0.13.10).\n\n"
)


def _name(value):
    return re.sub(r"[-_.]+", "-", value).lower()


def _wheel_requirement(wheel):
    with zipfile.ZipFile(wheel) as archive:
        [metadata] = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        package = BytesParser().parsebytes(archive.read(metadata))
    with wheel.open("rb") as stream:
        wheel_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return _name(package["Name"]), package["Version"], wheel_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default="uv", help="path to the uv executable")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="isolate-runtime-lock-") as temporary:
        scratch = Path(temporary)
        resolved = scratch / "resolved.txt"
        wheels = scratch / "wheels"
        subprocess.run([
            args.uv, "--no-config", "--no-cache", "pip", "compile", "requirements.txt",
            "--python-version", "3.12", "--python-platform", "x86_64-manylinux_2_34",
            "--default-index", PYPI, "--only-binary=:all:", "--generate-hashes",
            "--no-header", "--no-annotate", "--output-file", str(resolved),
        ], cwd=ROOT, check=True)

        platforms = [f"manylinux_2_{minor}_x86_64" for minor in range(34, 4, -1)]
        platforms += ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
        platform_args = [argument for platform in platforms for argument in ("--platform", platform)]
        # The target lock is already resolved. Downloading dependencies again
        # would let pip evaluate markers against the build machine's OS.
        subprocess.run([
            sys.executable, "-m", "pip", "--isolated", "download", "--disable-pip-version-check",
            "--no-cache-dir", "--no-deps", "--index-url", PYPI, "--dest", str(wheels), "--only-binary=:all:",
            "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312",
            *platform_args, "--require-hashes", "-r", str(resolved),
        ], check=True)

        requirements = sorted(_wheel_requirement(wheel) for wheel in wheels.glob("*.whl"))
        expected = {_name(name): version for name, version in re.findall(
            r"^([a-zA-Z0-9_.-]+)==([^\s;\\]+)", resolved.read_text(encoding="utf-8"), re.MULTILINE,
        )}
        downloaded = {name: version for name, version, _ in requirements}
        if not expected or expected != downloaded or len(requirements) != len(downloaded):
            raise RuntimeError("Lock resolution and verified wheel downloads differ")
        output = HEADER + "".join(
            f"{name}=={version} --hash=sha256:{wheel_hash}\n" for name, version, wheel_hash in requirements
        )
        (ROOT / "requirements-linux-py312.lock").write_text(output, encoding="utf-8", newline="\n")
        print(f"Locked {len(requirements)} wheel artifacts")


if __name__ == "__main__":
    main()
