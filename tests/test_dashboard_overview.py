"""Overview projections respect authorization and never expose audit payloads."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import fakeredis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))

from isolate_audit_index import AuditIndex
from isolate_config import DEFAULT_CONFIG
from isolate_dashboard_ui import overview_snapshot, render_overview
from isolate_permissions import PermissionDenied


class OverviewTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = copy.deepcopy(DEFAULT_CONFIG)
        self.config['dashboard'].update(admin_groups=['Platform'], default_locale='en')
        self.config['audit_index'].update(enabled=True, driver='sqlite', path=str(Path(self.directory.name) / 'audit.db'))
        self.redis = fakeredis.FakeRedis()
        self.identity = {'username':'operator', 'keycloak_sub':'stable-operator', 'groups':['Platform']}
        self.index = AuditIndex(self.config['audit_index'])
        self.index.initialize()

    def session(self, identifier, **values):
        data = {'connection_id':identifier,'status':'active','username':'alice','host_id':'10001',
                'started_at':100,'protocol':'webssh','target_host':'10.20.1.5'}
        data.update(values)
        self.redis.set('active_session_'+identifier, json.dumps(data))

    def test_non_admin_is_denied_before_reading_any_source(self):
        self.config['dashboard']['role_bindings'] = [{'group':'Owners','role':'project-owner','projects':['prod']}]
        with mock.patch('isolate_dashboard_ui.list_active_sessions', side_effect=AssertionError('must not read')):
            with self.assertRaises(PermissionDenied):
                overview_snapshot(self.config, self.redis, {'groups':['Owners']})

    def test_live_statistics_are_derived_only_from_active_sessions_with_known_starts(self):
        self.session('a', started_at=100)
        self.session('b', started_at=200)
        self.session('missing', started_at=None)
        self.session('complete', status='completed', started_at=0)
        snapshot = overview_snapshot(self.config, self.redis, self.identity, now=400)
        self.assertEqual(snapshot['active_count'], 3)
        self.assertEqual(snapshot['average_duration'], '00:04:10')
        self.assertTrue(snapshot['available'])
        self.assertEqual({s['id'] for s in snapshot['sessions']}, {'a','b','missing'})
        self.assertNotIn('blocked_count', snapshot)

    def test_snapshot_projects_safe_fields_and_html_escapes_user_data(self):
        self.session('conn', username='<img src=x onerror=alert(1)>', command='TOP-SECRET-COMMAND',
                     token='TOP-SECRET-TOKEN', server_name='db<script>alert(1)</script>')
        self.index.ingest({'event_id':'event-a','ts':200,'event':'identity_login','username':'<svg/onload=x>',
                           'project':'prod','command':'TOP-SECRET-COMMAND','scope':'TOP-SECRET-SCOPE',
                           'parameters':{'secret':'TOP-SECRET-PARAMETER'},'password':'TOP-SECRET-PASSWORD'})
        snapshot = overview_snapshot(self.config, self.redis, self.identity, now=300)
        self.assertEqual(snapshot['events'][0]['level'], 'AUTH')
        projected = json.dumps(snapshot)
        for value in ('TOP-SECRET-COMMAND','TOP-SECRET-TOKEN','TOP-SECRET-SCOPE','TOP-SECRET-PARAMETER','TOP-SECRET-PASSWORD'):
            self.assertNotIn(value, projected)
        # Icons belong to the shared shell and have no effect on data escaping.
        with mock.patch('isolate_dashboard_ui._icon', return_value=''):
            page = render_overview(self.config, self.redis, '<csrf>', self.identity)
        self.assertNotIn('<img src=x', page)
        self.assertIn('&lt;img src=x', page)
        self.assertNotIn('<svg/onload=x>', page)
        self.assertIn('&lt;csrf&gt;', page)

    def test_source_outages_are_explicit_and_do_not_show_zero_as_healthy(self):
        with mock.patch.object(self.redis, 'ping', side_effect=ConnectionError('private endpoint details')), \
                mock.patch.object(AuditIndex, 'search', side_effect=RuntimeError('private DSN')):
            snapshot = overview_snapshot(self.config, self.redis, self.identity)
        self.assertFalse(snapshot['available'])
        self.assertIsNone(snapshot['active_count'])
        self.assertFalse(snapshot['audit_available'])
        self.assertNotIn('private', json.dumps(snapshot))

    def test_russian_form_help_and_termination_are_explicitly_localized(self):
        self.config['dashboard']['default_locale'] = 'ru'
        self.config['session_control']['terminate_enabled'] = True
        self.session('active-connection')
        with mock.patch('isolate_dashboard_ui._icon', return_value=''):
            page = render_overview(self.config, self.redis, 'csrf', self.identity)
        for text in ('Обзор операций','Активные сессии','Журнал аудита','Подтвердить завершение',
                     'Укажите причину отключения.', 'Не настроено'):
            self.assertIn(text, page)
        self.assertIn('aria-describedby="overview-reason-help"', page)
        self.assertIn('data-overview-terminate="active-connection"', page)
        self.assertIn('name="confirm" value="true"', page)
        self.assertNotIn('Terminate', page)
        self.config['session_control']['terminate_enabled'] = False
        with mock.patch('isolate_dashboard_ui._icon', return_value=''):
            page = render_overview(self.config, self.redis, 'csrf', self.identity)
        self.assertNotIn('data-overview-terminate=', page)

    def test_audit_polling_is_bounded_and_sessions_declare_truncation(self):
        for number in range(105):
            self.session(str(number), started_at=number)
        with mock.patch.object(AuditIndex, 'search', return_value={'events':[]}) as search:
            snapshot = overview_snapshot(self.config, self.redis, self.identity, now=200)
        self.assertEqual(snapshot['active_count'], 105)
        self.assertEqual(len(snapshot['sessions']), 100)
        self.assertTrue(snapshot['partial'])
        search.assert_called_once_with(limit=30, include_index_time=True)


if __name__ == '__main__':
    unittest.main()
