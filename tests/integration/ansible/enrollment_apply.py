"""Run the enrollment role with two loopback OpenSSH servers and the scoped API."""

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import pwd
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

from flask import request
from werkzeug.serving import make_server

from enrollment_integration import PLAYBOOK

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_admin_api import AdminAPITest


SERVICE_ACCOUNT = "enroll-service"
TARGET_ACCOUNT = "enroll-target"


def make_key(path):
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(path)], check=True, timeout=20)
    return path.with_suffix(".pub")


@contextmanager
def ssh_server(scratch, name, controller_key):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    host_key = scratch / name
    public_key = make_key(host_key)
    configuration = scratch / (name + ".conf")
    configuration.write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {host_key}\nPidFile {scratch / (name + '.pid')}\n"
        "PasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\n"
        "PermitRootLogin prohibit-password\nAuthorizedKeysFile .ssh/authorized_keys\n"
        f"Match User root\n    AuthorizedKeysFile {controller_key}\n",
        encoding="utf-8",
    )
    # An undrained pipe can block sshd after repeated enrollment connections.
    log_path = scratch / (name + ".stderr.log")
    with log_path.open("wb") as log:
        process = subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(configuration)], stderr=log)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(log_path.read_text(errors="replace"))
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError(f"OpenSSH fixture did not start: {name}")
        yield port, public_key
    finally:
        process.terminate()
        process.wait(timeout=10)


@contextmanager
def inventory_api(fixture, scratch):
    certificate, key = scratch / "fixture.pem", scratch / "fixture.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
                    "-keyout", str(key), "-out", str(certificate)], check=True, capture_output=True, timeout=30)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certificate, key)
    server = make_server("127.0.0.1", 0, fixture.app, ssl_context=tls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}", certificate
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def run_playbook(inventory, scratch):
    inventory_file = scratch / "hosts.yml"
    inventory_file.write_text(json.dumps(inventory), encoding="utf-8")
    execution = subprocess.run(
        ["ansible-playbook", "-i", str(inventory_file), str(PLAYBOOK)], cwd=scratch,
        env=dict(os.environ, ISOLATE_TOKEN="machine-token", ANSIBLE_STDOUT_CALLBACK="default",
                 ANSIBLE_LOCAL_TEMP=str(scratch / "controller")), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120,
    )
    assert execution.returncode == 0, execution.stdout
    return execution.stdout


def public_key_bytes(public_key):
    return b" ".join(public_key.read_bytes().split()[:2])


def run_fixture(stack, scratch):
    fixture = AdminAPITest()
    stack.callback(fixture.doCleanups)
    fixture.setUp()
    writes = []

    @fixture.app.before_request
    def record_writes():
        if request.method in {"POST", "PUT"}:
            writes.append(request.method)

    # The enrollment service may write only 'stage'. This external project must
    # stay invisible to its real inventory API calls.
    outsider = fixture.create(values=dict(fixture.host, project_name="prod"))
    writes.clear()

    origin, certificate = stack.enter_context(inventory_api(fixture, scratch))
    controller_key = scratch / "controller-key"
    controller_public = make_key(controller_key)
    target_port, target_public = stack.enter_context(ssh_server(scratch, "target-key", controller_public))
    bastion_port, bastion_public = stack.enter_context(ssh_server(scratch, "bastion-key", controller_public))
    service_key = scratch / "service-key"
    service_public = make_key(service_key)
    service = pwd.getpwnam(SERVICE_ACCOUNT)
    os.chown(service_key, service.pw_uid, service.pw_gid)
    controller_trust = scratch / "controller-trust"
    controller_trust.write_bytes(b"".join(
        f"[127.0.0.1]:{port} ".encode() + public_key_bytes(key) + b"\n"
        for port, key in ((target_port, target_public), (bastion_port, bastion_public))
    ))
    common_ssh = {
        "ansible_user": "root", "ansible_host": "127.0.0.1", "ansible_python_interpreter": sys.executable,
        "ansible_private_key_file": str(controller_key),
        "ansible_ssh_common_args": f"-o UserKnownHostsFile={controller_trust} -o GlobalKnownHostsFile=/dev/null",
    }
    trust_files = [scratch / file for file in ("gateway-known-hosts", "worker-known-hosts")]
    target = dict(common_ssh, ansible_port=target_port)
    target.update({
        "isolate_enrollment_bastion": "fixture-bastion", "isolate_enrollment_project": "stage",
        "isolate_enrollment_external_id": "stage/fixture-enroll", "isolate_enrollment_ssh_user": TARGET_ACCOUNT,
        "isolate_enrollment_api_origin": origin, "isolate_enrollment_tls_ca_file": str(certificate),
        "isolate_enrollment_target_host_key_file": str(target_public),
        "isolate_enrollment_bastion_user": SERVICE_ACCOUNT, "isolate_enrollment_bastion_identity_file": str(service_key),
        "isolate_enrollment_known_hosts_files": [str(file) for file in trust_files],
    })
    inventory = {"all": {
        "hosts": {"fixture-bastion": dict(common_ssh, ansible_port=bastion_port),
                  "localhost": {"ansible_connection": "local", "ansible_remote_tmp": str(scratch / "modules")}},
        "children": {"isolate_enrollment_targets": {"hosts": {"fixture-target": target}}},
    }}

    def visible_hosts():
        response = fixture.client.get("/api/v1/admin/hosts", headers=fixture.headers("machine-token"))
        assert response.status_code == 200, response.data
        return response.get_json()["hosts"]

    run_playbook(inventory, scratch)
    [created] = visible_hosts()
    assert writes == ["POST"] and created["server_id"] != outsider["server_id"]
    assert created["server_port"] == target_port and created["server_user"] == TARGET_ACCOUNT
    assert created["tags"]["isolate_enrollment_id"] == "stage/fixture-enroll"
    expected_pin = f"[127.0.0.1]:{target_port} ".encode() + public_key_bytes(target_public)
    assert all(file.read_bytes().strip() == expected_pin for file in trust_files)
    authorized_keys = Path(pwd.getpwnam(TARGET_ACCOUNT).pw_dir) / ".ssh/authorized_keys"
    assert public_key_bytes(authorized_keys) == public_key_bytes(service_public)
    print("PASS: enrollment creates one scoped host and verifies real SSH with both trust stores")

    replay = run_playbook(inventory, scratch)
    assert "changed=0" in replay and writes == ["POST"] and visible_hosts() == [created], replay
    print("PASS: repeating the same enrollment makes no changes")

    target["isolate_enrollment_server_name"] = "fixture-target-renamed"
    run_playbook(inventory, scratch)
    [updated] = visible_hosts()
    assert writes == ["POST", "PUT"] and updated["server_id"] == created["server_id"]
    assert updated["server_name"] == "fixture-target-renamed" and updated["_revision"] != created["_revision"]
    print("PASS: changed metadata updates the existing host with its current revision")


if __name__ == "__main__":
    if not any(Path(marker).exists() for marker in ("/.dockerenv", "/run/.containerenv")):
        raise SystemExit("Run this fixture inside its disposable integration container")
    # StrictModes validates ancestors of the absolute AuthorizedKeysFile path.
    # Keep the fixture under /run, outside the world-writable /tmp directory.
    with (
        tempfile.TemporaryDirectory(prefix="isolate-enrollment-apply-", dir="/run") as directory,
        ExitStack() as resources,
    ):
        root = Path(directory)
        root.chmod(0o755)
        run_fixture(resources, root)
