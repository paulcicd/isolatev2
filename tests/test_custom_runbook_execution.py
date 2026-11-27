"""Custom definitions retain their authorization and identity through queueing."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import fakeredis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from isolate_jobs import JobError, create_runbook_fleet, execute_job, verify_job_signature
from isolate_runbook_catalog import publish_runbook, retire_runbook, save_runbook_draft


class CustomRunbookExecutionTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        signing_key = root / "job.key"
        signing_key.write_bytes(b"t" * 64)
        self.store = fakeredis.FakeRedis()
        self.identity = {"username": "publisher", "keycloak_sub": "publisher-sub", "groups": ["Operators"]}
        self.config = {
            "command_execution": {"jobs_path": str(root / "jobs"), "signing_key_file": str(signing_key)},
            "runbooks": {
                "enabled": True,
                "read_only": {"allowed_groups": ["Operators"]},
                "operational": {"enabled": True, "allowed_groups": ["Operators"]},
            },
            "ssh": {"default_sudo_mode": "none"},
            "logging": {"base_path": str(root / "logs")},
        }
        self.store.set("server_1", json.dumps({
            "server_id": "1", "project_name": "staging", "server_name": "sample", "server_ip": "192.0.2.10",
            "server_port": 22, "server_user": "operator",
        }))
        self.set_actions(["operate"])

    def set_actions(self, actions):
        self.store.set("grant_1", json.dumps({
            "id": "1", "subject": "group", "name": "Operators", "project": "staging",
            "remote_user": "operator", "sudo_mode": "none", "allowed_actions": actions,
        }))

    def publish(self, executable, revision=0):
        draft = save_runbook_draft(self.store, "custom-example", {
            "title": "Sample runbook", "description": "Fixture",
            "commands": [[executable]], "parameters": {}, "default_timeout": 30,
        }, actor="publisher-sub", expected_revision=revision)
        return publish_runbook(self.store, "custom-example", actor="publisher-sub", expected_revision=draft["revision"])

    def queue(self, **kwargs):
        return create_runbook_fleet(self.store, self.config, self.identity, "custom-example", ["1"],
                                    confirmed=True, **kwargs)["jobs"][0]

    def test_review_and_worker_use_the_published_revision(self):
        first = self.publish("/usr/bin/uptime")
        digest = first["versions"][0]["definition_sha256"]
        self.publish("/usr/bin/true", first["revision"])
        reviewed = self.queue(definition_sha256=digest)
        self.assertEqual(reviewed["runbook_definition_sha256"], digest)
        self.assertEqual(reviewed["command"], "/usr/bin/uptime")
        self.assertTrue(verify_job_signature(reviewed, self.config))
        self.assertEqual(self.queue()["command"], "/usr/bin/true")
        with mock.patch("isolate_jobs.subprocess.Popen", side_effect=OSError("fixture stops before SSH")) as ssh:
            result = execute_job(self.store, self.config, reviewed)
        ssh.assert_called_once()
        self.assertIn("/usr/bin/uptime", ssh.call_args.args[0][-1])
        self.assertEqual(result["status"], "failed")

    def test_worker_reads_output_when_ssh_exits_during_an_empty_read(self):
        self.publish("/usr/bin/uptime")
        queued = self.queue()
        output = b"final runbook output\n"
        pending_output = iter((output, b""))
        process = mock.Mock(returncode=None)
        process.stdout.fileno.return_value = 42
        process.poll.side_effect = lambda: process.returncode

        def read_ssh_output(fd, size):
            if process.returncode is None:
                # SSH writes and exits after the nonblocking read finds no data.
                process.returncode = 0
                raise BlockingIOError
            return next(pending_output)

        with (
            mock.patch("isolate_jobs.subprocess.Popen", return_value=process),
            mock.patch("isolate_jobs.os.set_blocking"),
            mock.patch("isolate_jobs.os.read", side_effect=read_ssh_output),
        ):
            result = execute_job(self.store, self.config, queued)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["output_bytes"], len(output))
        self.assertEqual(Path(result["output_path"]).read_bytes(), output)

    def test_retired_version_cannot_start_a_queued_job(self):
        first = self.publish("/usr/bin/uptime")
        queued = self.queue()
        retire_runbook(self.store, "custom-example", actor="publisher-sub", expected_revision=first["revision"])
        with mock.patch("isolate_jobs.subprocess.Popen") as ssh:
            self.assertEqual(execute_job(self.store, self.config, queued)["status"], "failed")
        ssh.assert_not_called()
        with self.assertRaises(JobError):
            self.queue()

    def test_operational_gate_and_host_permission_are_required(self):
        self.publish("/usr/bin/uptime")
        self.config["runbooks"]["operational"]["enabled"] = False
        with self.assertRaisesRegex(JobError, "operational runbooks are disabled"):
            self.queue()
        self.config["runbooks"]["operational"]["enabled"] = True
        self.set_actions(["runbook"])
        with self.assertRaisesRegex(JobError, "host 1 is not allowed"):
            self.queue()


if __name__ == "__main__":
    unittest.main()
