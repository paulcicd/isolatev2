"""Custom runbook authoring through the real Flask dashboard routes."""

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import fakeredis

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

import isolate_web
from isolate_runbook_catalog import get_custom_runbook


class RunbookAdminUITest(unittest.TestCase):
    manage = "/jobs/runbooks/manage"
    new = manage + "?new=1"
    edit = manage + "?runbook=sample-operation"

    def setUp(self):
        self.store = fakeredis.FakeRedis()
        self.app = isolate_web.create_app({
            "dashboard": {"admin_groups": ["Admins"], "role_bindings": [
                {"group": "Owners", "role": "project-owner", "projects": ["test"]},
            ]},
            "runbooks": {"enabled": True, "operational": {"enabled": False}},
            "keycloak": {}, "logging": {}, "access": {}, "policy": {}, "ssh": {},
        })
        self.app.config.update(TESTING=True, SECRET_KEY="custom-runbook-admin-test")
        self.client = self.app.test_client()
        redis = mock.patch.object(isolate_web, "redis_client", return_value=self.store)
        redis.start()
        self.addCleanup(redis.stop)
        audit = mock.patch.object(isolate_web, "prepare_and_dispatch")
        self.audit = audit.start()
        self.addCleanup(audit.stop)

    def login(self, group="Admins"):
        with self.client.session_transaction() as session:
            session["identity"] = {"username": "engineer", "keycloak_sub": "sub-engineer", "groups": [group]}
            session["csrf_token"] = "csrf"

    def draft(self, **updates):
        return dict({
            "action": "save_draft", "runbook_id": "sample-operation", "revision": "0", "csrf_token": "csrf",
            "runbook_title": "Sample operation", "runbook_timeout": "30", "runbook_description": "Fixture operation",
            "runbook_commands": json.dumps([["/usr/bin/printf", "<%s>", "{service}"]]),
            "runbook_parameters": json.dumps({"service": {"type": "string", "required": True}}),
        }, **updates)

    def record(self):
        return get_custom_runbook(self.store, "sample-operation")

    def test_authoring_requires_platform_admin_and_csrf(self):
        self.assertEqual(self.client.get(self.manage).status_code, 302)
        self.login("Owners")
        self.assertEqual(self.client.get(self.manage).status_code, 403)
        self.assertEqual(self.client.post(self.new, data=self.draft()).status_code, 403)
        self.login()
        self.assertEqual(self.client.post(self.new, data=self.draft(csrf_token="invalid")).status_code, 403)
        self.assertEqual(self.client.get(self.manage + "?runbook=uptime").status_code, 404)
        self.assertIsNone(self.record())

    def test_preview_escapes_output_and_keeps_localized_errors_without_saving(self):
        self.login()
        form = self.client.get(self.new + "&lang=ru")
        self.assertIn("Запуск операционных регламентов отключён", form.text)
        self.assertIn('aria-describedby="runbook-editor-runbook_commands-hint"', form.text)
        missing = self.client.post(self.new, data=self.draft(action="preview"))
        self.assertEqual(missing.status_code, 400)
        self.assertIn("Заполните параметр «service».", missing.text)
        self.assertIn('class="admin-disclosure" open', missing.text)
        sample = self.client.post(self.new + "&lang=en", data=self.draft(
            action="preview", sample_parameters='{"service":"nginx.service"}',
        ))
        self.assertEqual(sample.status_code, 200)
        self.assertIn("Manage runbooks", sample.text)
        self.assertIn('<pre><code>/usr/bin/printf &#x27;&lt;%s&gt;&#x27; nginx.service</code></pre>', sample.text)
        self.assertIsNone(self.record())

    def test_publication_and_retirement_require_confirmation_and_current_revision(self):
        self.login()
        saved = self.client.post(self.new, data=self.draft())
        self.assertEqual(saved.status_code, 303)
        self.assertEqual(saved.headers["Location"], self.edit)
        self.assertEqual(self.record()["revision"], 1)
        publication = {"action": "publish", "revision": "1", "csrf_token": "csrf"}
        self.assertEqual(self.client.post(self.edit, data=publication).status_code, 400)
        self.assertIsNone(self.record()["active_version"])
        publication["confirm"] = "true"
        self.assertEqual(self.client.post(self.edit, data=publication).status_code, 303)
        self.assertEqual(self.record()["active_version"], 1)
        conflict = self.client.post(self.edit, data=self.draft(revision="1", runbook_title="Stale title"))
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("Stale title", conflict.text)
        self.assertIsNone(self.record()["draft"])
        retirement = dict(publication, action="retire", revision="2")
        self.assertEqual(self.client.post(self.edit, data=retirement).status_code, 400)
        self.assertEqual(self.record()["active_version"], 1)
        retirement["version"] = "1"
        self.assertEqual(self.client.post(self.edit, data=retirement).status_code, 303)
        self.assertIsNone(self.record()["active_version"])
        self.assertIn("Retired", self.client.get(self.edit).text)
        applied = [call.args[0] for call in self.audit.call_args_list if call.args[0].get("outcome") == "applied"]
        self.assertEqual([entry["action"] for entry in applied], ["runbook_save_draft", "runbook_publish", "runbook_retire"])
        self.assertEqual([entry.get("version") for entry in applied], [None, 1, 1])
        self.assertNotIn("/usr/bin/printf", json.dumps(applied))
