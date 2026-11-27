"""Presentation translation preserves identity, evidence and submitted values."""

from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from isolate_ui_locale import localize_html, localize_template


class Controls(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.controls = []
        self.ids = set()
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        value = dict(attrs)
        if tag in ("input", "select", "textarea"):
            self.controls.append(value)
        if value.get("id"):
            self.ids.add(value["id"])


class UILocaleTest(unittest.TestCase):
    def test_presentation_and_encoded_titles_translate(self):
        body = '<h1>Jobs &amp; Runbooks</h1><p class="page-lead">Execution details and captured output.</p><table><th>Status</th><td>Status</td></table>'
        result = localize_html(body, "ru")
        self.assertIn("Задания и регламенты", result)
        self.assertIn("Результат выполнения и сохранённый вывод команды.", result)
        self.assertIn("<th>Статус</th><td>Status</td>", result)

    def test_evidence_user_values_scripts_and_code_are_verbatim(self):
        protected = '<pre>Save &lt;script&gt;</pre><code>Filter</code><script type="application/json">{"title":"Status","text":"<h1>Save</h1>"}</script><dd>User</dd><td><a href="/user/Save">Save</a></td><section data-i18n="off"><h2>Save</h2></section>'
        self.assertEqual(localize_html(protected, "ru"), protected)

    def test_fields_keep_values_urls_and_textarea_contents(self):
        body = '<form action="/jobs?q=Save" method="post"><input type="hidden" name="csrf_token" value="Save"><input name="project" value="Save" placeholder="project"><textarea name="parameters">{"x":"Save","escaped":"&lt;/textarea&gt;"}</textarea><button>Save</button></form>'
        result = localize_html(body, "ru")
        self.assertIn('action="/jobs?q=Save"', result)
        self.assertIn('name="csrf_token" value="Save">', result)
        self.assertIn('name="project" value="Save" placeholder="проект"', result)
        self.assertIn('{"x":"Save","escaped":"&lt;/textarea&gt;"}', result)
        self.assertIn('<button>Сохранить</button>', result)

    def test_both_languages_get_accessible_field_specific_hints(self):
        body = '<form><input name="host_ids"><select name="runbook_id"><option value="uptime">System uptime and load</option></select><textarea name="parameters">{}</textarea><input name="confirm" type="checkbox"><input name="csrf_token" type="hidden"></form>'
        for locale in ("en", "ru"):
            with self.subTest(locale=locale):
                result = localize_html(body, locale)
                parsed = Controls(result)
                self.assertEqual(len(parsed.controls), 5)
                for control in parsed.controls[:-1]:
                    hint = control["aria-describedby"].split()[-1]
                    self.assertIn(hint, parsed.ids)
                self.assertNotIn("aria-describedby", parsed.controls[-1])
                self.assertEqual(len(parsed.ids), 4)
                self.assertIn("field-hint", result)
                self.assertIn("проверьте весь список" if locale == "ru" else "Review the full target list", result)

    def test_controls_inside_labels_keep_the_existing_accessible_name(self):
        result = localize_html('<form><label>Timeout <input name="timeout" type="number" min="1"></label></form>', "ru")
        self.assertIn("Тайм-аут", result)
        self.assertNotIn("aria-label", result)
        self.assertIn('min="1"', result)

    def test_safe_hint_escaping_and_opt_out(self):
        body = '<form><input name="project" data-hint="off"><div data-i18n="off"><label>Save<input name="user"></label></div></form>'
        self.assertEqual(localize_html(body, "ru"), body)

    def test_english_copy_and_unknown_labels_are_unchanged(self):
        body = '<h1>Inventory</h1><button>Save</button><h2>Unregistered application heading</h2>'
        self.assertEqual(localize_html(body, "en"), body)
        self.assertIn("Unregistered application heading", localize_html(body, "ru"))

    def test_preinterpolation_templates_translate_ui_without_touching_values(self):
        template = '<h1>Job {job_id}</h1><p>The hypothetical grant does not change effective access.</p><select name="mode"><option value="disabled">disabled</option></select><pre>{output}</pre>'
        localized = localize_template(template, "ru")
        rendered = localized.format(job_id="Save", output="Filter &lt;script&gt;")
        self.assertIn('<h1>Задание Save</h1>', rendered)
        self.assertIn('value="disabled">отключено', rendered)
        self.assertIn('<pre>Filter &lt;script&gt;</pre>', rendered)

    def test_existing_help_is_not_duplicated(self):
        body = '<form><input name="project" aria-describedby="specific-help"><small id="specific-help">Project-specific guidance</small></form>'
        self.assertEqual(localize_html(body, "en"), body)

    def test_implicit_option_values_preserve_mutation_semantics(self):
        template = '<select name="sudo_mode"><option>none</option><option>sudo-i</option></select>'
        result = localize_template(template, "ru")
        self.assertIn('<option value="none">нет</option>', result)
        self.assertIn('<option>sudo-i</option>', result)
        self.assertEqual(localize_template(template, "en"), template)


if __name__ == "__main__":
    unittest.main()
