"""Exercise the Linux release installer and launcher with private loopback fixtures."""

import argparse
from contextlib import contextmanager
import http.server
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "shared"))

from joserfc.jwk import RSAKey
from redis import Redis
from redis.exceptions import RedisError
from isolate_install import CODE_DIRECTORIES, CODE_FILES


@contextmanager
def process(command, cwd):
    child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL)
    try:
        yield child
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_ready(child, probe):
    deadline = time.monotonic() + 15
    while child.poll() is None and time.monotonic() < deadline:
        try:
            if probe():
                return
        except (OSError, RuntimeError):
            pass
        time.sleep(0.1)
    raise RuntimeError("a release fixture failed to start")


@contextmanager
def oidc(root):
    cert, key = root / "oidc.crt", root / "oidc.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
                    "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True, timeout=30)
    jwks = {"keys": [RSAKey.generate_key(2048, parameters={"kid": "release-fixture"}).as_dict(private=False)]}

    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            document = documents.get(self.path)
            if document is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(document).encode())

        def log_message(self, *_):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider) as server:
        origin = f"https://127.0.0.1:{server.server_port}"
        issuer = origin + "/realms/fixture"
        protocol = issuer + "/protocol/openid-connect/"
        documents = {
            "/realms/fixture/.well-known/openid-configuration": {
                "issuer": issuer, "authorization_endpoint": protocol + "auth", "token_endpoint": protocol + "token",
                "jwks_uri": protocol + "certs", "code_challenge_methods_supported": ["S256"],
            },
            "/realms/fixture/protocol/openid-connect/certs": jwks,
        }
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield issuer, cert
        finally:
            server.shutdown()
            thread.join()


def check_dashboard(root, config, listen_port, version):
    launcher = root / "current/scripts/isolate-run.py"
    command = [sys.executable, "-I", "-B", str(launcher), "--root", str(root),
               "dashboard", "--config", str(config)]
    subprocess.run(command + ["--check"], check=True, capture_output=True, timeout=30)
    origin = f"http://127.0.0.1:{listen_port}"

    def health():
        with urllib.request.urlopen(origin + "/health", timeout=2) as response:
            return json.load(response).get("ok")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    with process(command, config.parent) as child:
        wait_ready(child, health)
        actual = (Path("/proc") / str(child.pid) / "cmdline").read_bytes()
        assert f"/releases/{version}/".encode() in actual, actual
        try:
            urllib.request.build_opener(NoRedirect).open(origin + "/login", timeout=5)
        except urllib.error.HTTPError as response:
            location = urllib.parse.urlsplit(response.headers["Location"])
            params = urllib.parse.parse_qs(location.query)
            assert response.code == 302 and location.path == "/realms/fixture/protocol/openid-connect/auth"
            assert params["code_challenge_method"] == ["S256"] and params.get("state") and params.get("nonce")
        else:
            raise AssertionError("dashboard login did not redirect")


def rehearse(source, temp, issuer, cert, redis_port):
    config, root = temp / "isolate.yml", temp / "installation"
    logs, secret = temp / "logs", temp / "dashboard-secret"
    logs.mkdir()
    secret.write_text("synthetic-release-test-session-key-0123456789\n", encoding="ascii")
    secret.chmod(0o600)
    listen_port = port()
    config.write_text(json.dumps({"data_root": str(temp), "redis": {"host": "127.0.0.1", "port": redis_port},
        "keycloak": {"issuer": issuer, "client_id": "fixture", "ca_file": str(cert),
                     "jwks_cache_path": str(temp / "oidc-jwks.json")},
        "dashboard": {"enabled": True, "secret_key_file": str(secret), "public_url": "https://access.example",
                      "listen_host": "127.0.0.1", "listen_port": listen_port, "workers": 1, "admin_groups": ["fixture"]},
        "gateway": {"host_key_file": str(temp / "gateway-host-key")},
        "recordings": {"signing_key_file": str(temp / "recording-signing-key")},
        "command_execution": {"signing_key_file": str(temp / "job-signing-key")},
        "policy_as_code": {"approval_key_file": str(temp / "policy-approval-key")},
        "logging": {"base_path": str(logs), "integrity": {"key_file": str(temp / "log-integrity-key")}},
    }), encoding="utf-8")
    config.chmod(0o600)
    saved_config = config.read_bytes()
    store = Redis(host="127.0.0.1", port=redis_port)
    store.set("release-fixture-marker", "preserved")
    installer = source / "scripts/isolate-install.py"

    def install(operation, *args):
        result = subprocess.run([sys.executable, "-I", "-B", str(installer), "--root", str(root), operation, *args],
                                capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or f"installer failed: {operation}")
        return json.loads(result.stdout)

    site = ["--config", str(config), "--service-user", pwd.getpwuid(os.geteuid()).pw_name]

    def stage(tree, version):
        args = ["--source", str(tree), "--version", version, *site]
        digest = install("plan", *args)["source_sha256"]
        staged = install("stage", *args, "--expected-source-sha256", digest)
        checksum = ["--version", version, "--expected-release-sha256", staged["release_sha256"]]
        assert install("verify", *checksum)["verified"]
        return checksum

    metadata = source / "release.json"
    first = json.loads(metadata.read_text(encoding="utf-8"))["version"] if metadata.is_file() else "2.1.0-rc.1"
    original = stage(source, first)
    assert install("activate", *original, *site, "--yes")["version"] == first
    check_dashboard(root, config, listen_port, first)
    next_source = temp / "upgrade-source"
    next_source.mkdir()
    for directory in CODE_DIRECTORIES:
        shutil.copytree(source / directory, next_source / directory)
    for name in CODE_FILES:
        if (source / name).is_file():
            shutil.copyfile(source / name, next_source / name)
    second = "9999.0.0" if first != "9999.0.0" else "9999.0.1"
    upgrade = stage(next_source, second)
    assert install("activate", *upgrade, *site, "--yes")["version"] == second
    check_dashboard(root, config, listen_port, second)
    assert install("rollback", *original, *site, "--yes")["operation"] == "rollback"
    check_dashboard(root, config, listen_port, first)
    assert config.read_bytes() == saved_config and store.get("release-fixture-marker") == b"preserved"
    print("PASS: staged installation, upgrade, rollback, Keycloak PKCE, preserved state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=REPO)
    source = parser.parse_args().source.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="isolate-release-") as directory:
        temp = Path(directory).resolve()
        redis_port = port()
        command = ["redis-server", "--bind", "127.0.0.1", "--port", str(redis_port), "--dir", str(temp),
                   "--save", "", "--appendonly", "no"]
        with process(command, temp) as redis_process, oidc(temp) as (issuer, cert):
            store = Redis(host="127.0.0.1", port=redis_port, socket_connect_timeout=1)
            def ping():
                try:
                    return store.ping()
                except RedisError:
                    return False

            wait_ready(redis_process, ping)
            rehearse(source, temp, issuer, cert, redis_port)


if __name__ == "__main__":
    main()
