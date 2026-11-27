"""Exercise the real Ansible planner against a loopback HTTPS inventory API."""

import http.server
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading


PLAYBOOK = Path(__file__).resolve().parents[3] / "ansible/enroll-isolate-hosts.yml"
FIXTURE_TOKEN = "fixture-access-token"


class InventoryFixture(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/v1/admin/hosts" or self.headers.get("Authorization") != "Bearer " + FIXTURE_TOKEN:
            self.send_error(403)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"hosts": self.server.hosts}).encode("utf-8"))

    def log_message(self, *_):
        pass


def main():
    with tempfile.TemporaryDirectory(prefix="isolate-ansible-test-") as directory:
        scratch = Path(directory)
        env = dict(os.environ, ISOLATE_TOKEN=FIXTURE_TOKEN, ANSIBLE_STDOUT_CALLBACK="default",
                   ANSIBLE_LOCAL_TEMP=str(scratch / "controller"), ANSIBLE_REMOTE_TEMP=str(scratch / "modules"))
        cert, key = scratch / "fixture.pem", scratch / "fixture.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
                        "-keyout", str(key), "-out", str(cert)], cwd=scratch, check=True, capture_output=True, timeout=30)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), InventoryFixture) as server:
            server.hosts = []
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cert, key)
            server.socket = tls.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                check_playbook(server, scratch, cert, env)
            finally:
                server.shutdown()
                thread.join()


def check_playbook(server, scratch, cert, env):
    inventory = scratch / "fixture.yml"
    inventory.write_text(json.dumps({"all": {
        "hosts": {"test-bastion": {"ansible_host": "192.0.2.11"},
                  "localhost": {"ansible_connection": "local", "ansible_remote_tmp": str(scratch / "modules")}},
        "children": {"isolate_enrollment_targets": {"hosts": {"fixture-host": {
            "ansible_host": "192.0.2.10",
            "ansible_port": 2222,
            "isolate_enrollment_bastion": "test-bastion",
            "isolate_enrollment_api_origin": "https://127.0.0.1:" + str(server.server_port),
            "isolate_enrollment_tls_ca_file": str(cert),
            "isolate_enrollment_external_id": "stage/fixture-host",
            "isolate_enrollment_project": "stage",
            "isolate_enrollment_ssh_user": "operator",
        }}}},
    }}), encoding="utf-8")
    command = ["ansible-playbook", "-i", str(inventory), str(PLAYBOOK)]

    def run(option):
        return subprocess.run(command + [option], cwd=scratch, env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=40)

    syntax = run("--syntax-check")
    assert syntax.returncode == 0, syntax.stdout
    record = {"server_id": "13", "project_name": "stage", "server_name": "fixture-host", "server_ip": "192.0.2.10",
              "server_port": 2222, "server_user": "operator", "tags": {"isolate_enrollment_id": "stage/fixture-host"}}
    for rows, prompt in (
        ([], "Would add a host to Isolate"),
        ([record], "Inventory already current"),
        ([dict(record, server_port=22)], "Would update Isolate host 13"),
    ):
        server.hosts = rows
        check = run("--check")
        assert check.returncode == 0 and "changed=0" in check.stdout and prompt in check.stdout, check.stdout
        print("PASS: " + prompt)


if __name__ == "__main__":
    main()
