"""Durable versions and typed argument handling for custom runbooks."""

import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

import fakeredis

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from isolate_runbook_catalog import (CUSTOM_RUNBOOK_PREFIX, RunbookConflict, get_custom_runbook,
                                     list_custom_runbooks, preview_runbook_draft, publish_runbook,
                                     retire_runbook, save_runbook_draft)
from isolate_runbooks import RunbookError, get_runbook, list_runbooks, render_runbook
from isolate_state import SQLState, StateClient


RUNBOOK_ID = "service-check"


def definition(title="Service diagnostics"):
    return {"title": title, "commands": [["/usr/bin/systemctl", "is-active", "--", "{service}"]],
            "parameters": {"service": {"type": "string", "required": True, "pattern": "[A-Za-z0-9_.-]{1,80}"}},
            "default_timeout": 30}


class CustomRunbookCatalogTest(unittest.TestCase):
    def setUp(self):
        self.store = fakeredis.FakeRedis()

    def save(self, draft=None, expected_revision=0):
        return save_runbook_draft(self.store, RUNBOOK_ID, definition() if draft is None else draft,
                                  actor="author", expected_revision=expected_revision)

    def publish(self, draft):
        return publish_runbook(self.store, RUNBOOK_ID, actor="publisher", expected_revision=draft["revision"])

    def test_draft_published_version_history_and_retirement(self):
        draft = self.save()
        self.assertIsNone(get_runbook({}, RUNBOOK_ID, store=self.store))
        self.assertNotIn(RUNBOOK_ID, {row["id"] for row in list_runbooks({}, store=self.store)})
        self.assertEqual(list_custom_runbooks(self.store)[0]["draft"]["title"], "Service diagnostics")
        first = self.publish(draft)
        self.assertIsNone(first["draft"])
        self.assertEqual(first["active_version"], 1)
        self.assertEqual(first["versions"][0]["published_by"], "publisher")
        digest = first["versions"][0]["definition_sha256"]
        self.assertEqual(get_runbook({}, RUNBOOK_ID, store=self.store)["class"], "operational")
        self.assertNotIn(RUNBOOK_ID, {row["id"] for row in list_runbooks({}, ["read_only"], store=self.store)})
        with self.assertRaises(RunbookConflict):
            self.save(definition("Stale draft"), expected_revision=draft["revision"])
        second_draft = self.save(definition("Revised check"), expected_revision=first["revision"])
        self.assertEqual(get_runbook({}, RUNBOOK_ID, store=self.store)["definition_sha256"], digest)
        second = self.publish(second_draft)
        self.assertEqual(second["active_version"], 2)
        self.assertEqual(get_runbook({}, RUNBOOK_ID, store=self.store)["title"], "Revised check")
        reviewed = render_runbook({}, RUNBOOK_ID, {"service": "nginx.service"},
                                  store=self.store, definition_sha256=digest)
        self.assertEqual(reviewed["runbook"]["title"], "Service diagnostics")
        self.assertEqual(reviewed["policy_action"], "operate")
        retired = retire_runbook(self.store, RUNBOOK_ID, actor="reviewer",
                                 expected_revision=second["revision"], version="1")
        self.assertEqual(retired["versions"][0]["retired_by"], "reviewer")
        self.assertIsNone(get_runbook({}, RUNBOOK_ID, store=self.store, definition_sha256=digest))
        self.assertEqual(get_runbook({}, RUNBOOK_ID, store=self.store)["version"], 2)
        retire_runbook(self.store, RUNBOOK_ID, actor="reviewer", expected_revision=retired["revision"])
        self.assertIsNone(get_runbook({}, RUNBOOK_ID, store=self.store))
        self.assertEqual(len(get_custom_runbook(self.store, RUNBOOK_ID)["versions"]), 2)

    def test_distinct_digests_for_republished_identical_draft(self):
        first = self.publish(self.save())
        second = self.publish(self.save(expected_revision=first["revision"]))
        versions = second["versions"]
        self.assertEqual(versions[0]["definition"], versions[1]["definition"])
        self.assertNotEqual(versions[0]["definition_sha256"], versions[1]["definition_sha256"])
        disabled = {"runbooks": {"disabled": [RUNBOOK_ID]}}
        self.assertIsNone(get_runbook(disabled, RUNBOOK_ID, store=self.store,
                                      definition_sha256=versions[0]["definition_sha256"]))
        self.assertNotIn(RUNBOOK_ID, {row["id"] for row in list_runbooks(disabled, store=self.store)})

    def test_builtin_hash_stays_compatible_and_id_is_reserved(self):
        builtin = get_runbook({}, "uptime")
        self.assertEqual(get_runbook({}, "uptime", store=self.store,
                                     definition_sha256=builtin["definition_sha256"]), builtin)
        self.assertIsNone(get_runbook({}, "uptime", store=self.store, definition_sha256="0" * 64))
        with self.assertRaisesRegex(RunbookError, "reserved"):
            save_runbook_draft(self.store, "uptime", definition(), actor="author")

    def test_integrity_check_rejects_changed_definition(self):
        self.publish(self.save())
        key = CUSTOM_RUNBOOK_PREFIX + RUNBOOK_ID
        stored = json.loads(self.store.get(key))
        stored["versions"][0]["definition"]["commands"] = [["/usr/bin/true"]]
        self.store.set(key, json.dumps(stored))
        with self.assertRaisesRegex(RunbookError, "integrity"):
            get_runbook({}, RUNBOOK_ID, store=self.store)

    def test_sql_backend_uses_same_catalogue_and_cas(self):
        ephemeral = self.store
        with tempfile.TemporaryDirectory() as directory:
            options = {"backend": "sqlite", "sqlite_path": str(Path(directory) / "catalog.db")}
            SQLState(options).initialize()
            self.store = StateClient(ephemeral, options)
            self.publish(self.save())
            self.assertIsNone(ephemeral.get(CUSTOM_RUNBOOK_PREFIX + RUNBOOK_ID))
            self.assertIn(RUNBOOK_ID, {row["id"] for row in list_runbooks({}, store=self.store)})
            with self.assertRaises(RunbookConflict):
                self.save()

    def test_rejects_invalid_definition_and_unsafe_parameters(self):
        with self.assertRaisesRegex(RunbookError, "operational"):
            self.save(dict(definition(), **{"class": "read_only"}))
        for command, error in ((["{service}"], "fixed absolute executable"),
                               (["/usr/bin/tool", "prefix{service}"], "whole argument"),
                               (["/usr/bin/tool", "{missing}"], "unknown command parameter"),
                               (["/bin/sh", "-c", "{service}", "fixed"], "fixed script or executable"),
                               (["/usr/bin/python3", "-c", "{service}"], "fixed script or executable"),
                               (["/usr/bin/env", "{service}"], "fixed script or executable")):
            with self.subTest(command=command), self.assertRaisesRegex(RunbookError, error):
                self.save(dict(definition(), commands=[command]))
        for value in ("", "-x", "double word", "foo;bar", "foo\nbar", "a" * 129, 10):
            with self.subTest(value=value), self.assertRaisesRegex(RunbookError, "safe string"):
                preview_runbook_draft(definition(), {"service": value})
        with self.assertRaisesRegex(RunbookError, "invalid value"):
            preview_runbook_draft(definition(), {"service": "app:worker"})

    def test_renders_fixed_script_and_positional_argument(self):
        runbook = dict(definition(), commands=[["/bin/sh", "-c", 'printf "%s\n" "$1"', "runbook", "{service}"]])
        rendered = preview_runbook_draft(runbook, {"service": "queue-worker.service"})
        self.assertEqual(shlex.split(rendered["command"]),
                         ["/bin/sh", "-c", 'printf "%s\n" "$1"', "runbook", "queue-worker.service"])

    def test_custom_commands_stop_at_first_failure(self):
        runbook = dict(definition(), commands=[["/usr/bin/false"], ["/usr/bin/true"]], parameters={})
        self.assertEqual(preview_runbook_draft(runbook)["command"], "/usr/bin/false && /usr/bin/true")
        built_in = render_runbook({}, "deploy-diagnostics", {"service": "nginx.service"})
        self.assertIn("; ", built_in["command"])

    def test_integer_defaults_and_validation(self):
        runbook = dict(definition(), commands=[["/usr/bin/tool", "{count}"]],
                       parameters={"count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5}})
        self.assertEqual(preview_runbook_draft(runbook)["command"], "/usr/bin/tool 5")
        self.assertEqual(preview_runbook_draft(runbook, {"count": "002"})["command"], "/usr/bin/tool 2")
        with self.assertRaisesRegex(RunbookError, "exceeds the maximum"):
            preview_runbook_draft(runbook, {"count": 11})
        for value in (True, 2.1, "1e1"):
            with self.subTest(value=value), self.assertRaisesRegex(RunbookError, "32-bit integer"):
                preview_runbook_draft(runbook, {"count": value})


if __name__ == "__main__":
    unittest.main()
