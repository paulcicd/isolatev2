"""Bilingual workflow rendering preserves submitted data and scoped access."""

import html
from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))

from isolate_workflow_ui import workflow_copy, workflow_hints, workflow_value


class WorkflowCopyTest(unittest.TestCase):
    def test_copy_is_localized_before_resource_interpolation(self):
        resource = '<img src=x onerror=alert(1)> Project completed'
        with mock.patch('isolate_web._dashboard_locale', return_value='ru'):
            output = workflow_copy({}, '<h1>Campaign {}</h1>').format(html.escape(resource))
            self.assertEqual(output, '<h1>Запуск &lt;img src=x onerror=alert(1)&gt; Project completed</h1>')
            self.assertEqual(workflow_value({}, 'completed'), 'Завершено')
            self.assertEqual(workflow_value({}, 'completed-host.example'), 'completed-host.example')
        with mock.patch('isolate_web._dashboard_locale', return_value='en'):
            self.assertEqual(workflow_copy({}, 'Review plan'), 'Review plan')

    def test_visible_control_hints_preserve_json_and_hidden_csrf(self):
        source = ('<form><input type="hidden" name="csrf_token" value="private&amp;csrf">'
                  '<label>Reason<input name="reason" value="Project completed"></label>'
                  '<label>Parameters<textarea name="parameters">{"name":"Project &amp; Review plan"}</textarea></label>'
                  '<label>Choice<select name="decision"><option value="keep">Keep current access</option></select></label></form>')
        with mock.patch('isolate_web._dashboard_locale', return_value='ru'):
            output = workflow_hints({}, source)
        self.assertIn('value="private&amp;csrf"', output)
        self.assertIn('value="Project completed"', output)
        self.assertIn('{"name":"Project &amp; Review plan"}', output)
        self.assertIn('<option value="keep">Keep current access</option>', output)
        self.assertIn('Укажите, зачем нужен доступ', output)
        references = re.findall(r'aria-describedby="([^"]+)"', output)
        self.assertEqual(len(references), 3)
        self.assertEqual(len(set(references)), 3)
        for identifier in references:
            self.assertIn('id="' + identifier + '"', output)
        self.assertNotIn('name="csrf_token" aria-describedby', output)


class WorkflowRouteLocaleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_campaigns
        test_campaigns.CampaignTest.setUpClass()

    def setUp(self):
        import test_campaigns
        from isolate_web import create_app
        self.fixture = test_campaigns.CampaignTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        patcher = mock.patch('isolate_web.redis_client', return_value=self.fixture.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = create_app(self.fixture.config)
        self.app.config.update(TESTING=True, SECRET_KEY='workflow-translation-test')
        self.client = self.app.test_client()
        self.headers = {'Authorization': 'Bearer ' + self.fixture.token}

    def test_russian_campaign_form_and_hints_keep_protocol_field_values(self):
        response = self.client.get('/operations/campaigns?lang=ru', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.data)
        text = response.get_data(as_text=True)
        self.assertIn('Проверить план', text)
        self.assertIn('Время работы и средняя нагрузка', text)
        self.assertIn('name="runbook_id"', text)
        self.assertIn('value="uptime"', text)
        self.assertIn('name="host_ids"', text)
        self.assertIn('aria-describedby=', text)
        self.assertIn('При неизвестном результате', text)
        self.assertNotIn(self.fixture.token, text)
        english = self.client.get('/operations/campaigns?lang=en', headers=self.headers).get_data(as_text=True)
        self.assertIn('Review plan', english)
        self.assertIn('All canary targets must succeed', english)

    def test_locale_changes_do_not_translate_api_contract_or_mutate_plan(self):
        english = self.client.post('/api/v1/runbook-campaigns/preview?lang=en',
                                   headers=self.headers, json=self.fixture.body)
        russian = self.client.post('/api/v1/runbook-campaigns/preview?lang=ru',
                                   headers=self.headers, json=self.fixture.body)
        self.assertEqual(english.status_code, 200, english.data)
        self.assertEqual(russian.status_code, 200, russian.data)
        self.assertEqual(russian.get_json(), english.get_json())


if __name__ == '__main__':
    unittest.main()
