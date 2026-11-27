"""Read-only enterprise overview built from current session and audit evidence."""

import datetime
import hashlib
import html
import math
import time
from urllib.parse import quote

from isolate_permissions import PermissionDenied, is_platform_admin
from isolate_sessions import list_active_sessions


WORDS = {
    'en': {
        'eyebrow': 'BASTION CONTROL PLANE', 'heading': 'Operations overview',
        'lead': 'Current connections, access activity and the evidence behind every session.',
        'live': 'Live overview', 'refresh': 'Refresh overview', 'refreshing': 'Refreshing…',
        'updated': 'Updated', 'refresh_error': 'Refresh unavailable. Showing the last successful snapshot.',
        'stats': 'Quick stats', 'active': 'Active sessions', 'active_help': 'Connections currently marked active in the session registry.',
        'blocked': 'Blocked IPs', 'blocked_help': 'An IP blocklist is not configured. Access denials remain available in the audit log.',
        'average': 'Average session duration', 'average_help': 'Measured from the start of each active connection.',
        'average_scope': 'Active connections', 'average_pending': 'The average is shown when sessions are active.',
        'sessions': 'Active sessions', 'sessions_help': 'Authorized connections across your infrastructure.',
        'view_all': 'View all sessions', 'user': 'User / session', 'resource': 'Resource / address',
        'protocol': 'Protocol', 'duration': 'Duration', 'actions': 'Actions', 'logs': 'View logs',
        'terminate': 'Terminate', 'terminating': 'Termination requested', 'empty': 'No active sessions',
        'empty_help': 'Authorized connections will appear here when a session starts.',
        'audit': 'Live audit stream', 'audit_help': 'Recent access and connection events.',
        'history_help': 'Recent connections recorded by the bastion.',
        'audit_empty': 'No audit events recorded yet.', 'audit_unavailable': 'Audit source temporarily unavailable.',
        'audit_link': 'All audit events', 'history_link': 'Explore session logs', 'utc': 'All times UTC', 'unknown': 'Not recorded',
        'online': 'Control store reachable', 'offline': 'Control store unavailable', 'start_unavailable': 'Start time unavailable',
        'unavailable': 'Unavailable', 'not_configured': 'Not configured', 'no_sessions': 'No active sessions',
        'partial': 'Showing the newest {count} sessions. Open all sessions for the full registry.',
        'termination_title': 'Terminate this session?',
        'termination_help': 'Requests immediate disconnection. This action is recorded in the audit log.',
        'reason': 'Reason', 'reason_hint': 'Describe why this connection must end. Avoid secrets and credentials.',
        'reason_placeholder': 'For example, the incident response requires disconnection',
        'cancel': 'Keep session', 'confirm': 'Confirm termination',
        'identity_login': 'Identity signed in', 'identity_logout': 'Identity signed out',
        'ssh_start': 'SSH session started', 'ssh_end': 'SSH session ended',
        'protocol_start': 'Protocol session started', 'protocol_end': 'Protocol session ended',
        'policy_selected': 'Access policy evaluated', 'session_terminate': 'Session termination requested',
        'connection_ticket_created': 'Connection ticket issued', 'generic_event': 'Audit event',
    },
    'ru': {
        'eyebrow': 'УПРАВЛЕНИЕ БАСТИОНОМ', 'heading': 'Обзор операций',
        'lead': 'Активные подключения, события входа и проверки доступа.',
        'live': 'Обновляется автоматически', 'refresh': 'Обновить обзор', 'refreshing': 'Обновление…',
        'updated': 'Обновлено', 'refresh_error': 'Не удалось обновить обзор. Показаны данные последнего обновления.',
        'stats': 'Основные показатели', 'active': 'Активные сессии', 'active_help': 'Подключения, которые бастион сейчас считает активными.',
        'blocked': 'Заблокированные IP', 'blocked_help': 'Список блокировки IP-адресов не настроен. Отказы в доступе можно посмотреть в журнале аудита.',
        'average': 'Средняя длительность сессии', 'average_help': 'Считается с момента открытия каждого активного подключения.',
        'average_scope': 'По активным подключениям', 'average_pending': 'Среднее появится, когда откроется сессия.',
        'sessions': 'Активные сессии', 'sessions_help': 'Текущие подключения через этот бастион.',
        'view_all': 'Все сессии', 'user': 'Пользователь / сессия', 'resource': 'Ресурс / адрес',
        'protocol': 'Протокол', 'duration': 'Длительность', 'actions': 'Действия', 'logs': 'Журнал',
        'terminate': 'Завершить', 'terminating': 'Запрос на отключение отправлен', 'empty': 'Нет активных сессий',
        'empty_help': 'Новые сессии появятся здесь после подключения.',
        'audit': 'Журнал аудита', 'audit_help': 'Последние подключения и проверки доступа.',
        'history_help': 'Последние подключения, зарегистрированные бастионом.',
        'audit_empty': 'Событий аудита пока нет.', 'audit_unavailable': 'Не удалось загрузить события аудита. Обновите обзор.',
        'audit_link': 'Все события', 'history_link': 'История подключений', 'utc': 'Время в UTC', 'unknown': 'Нет данных',
        'online': 'Хранилище состояния доступно', 'offline': 'Хранилище состояния недоступно', 'start_unavailable': 'Время открытия неизвестно',
        'unavailable': 'Недоступно', 'not_configured': 'Не настроено', 'no_sessions': 'Нет активных сессий',
        'partial': 'Показаны последние {count} подключений. Полный список — в разделе «Активные сессии».',
        'termination_title': 'Завершить эту сессию?',
        'termination_help': 'Бастион отправит запрос на отключение и запишет действие в журнал аудита.',
        'reason': 'Причина', 'reason_hint': 'Укажите причину отключения. Не вводите секреты и учётные данные.',
        'reason_placeholder': 'Например, расследование инцидента INC-1042',
        'cancel': 'Продолжить сессию', 'confirm': 'Подтвердить завершение',
        'identity_login': 'Вход в Isolate', 'identity_logout': 'Выход из Isolate',
        'ssh_start': 'Открыта SSH-сессия', 'ssh_end': 'Закрыта SSH-сессия',
        'protocol_start': 'Открыто подключение', 'protocol_end': 'Подключение закрыто',
        'policy_selected': 'Проверено правило доступа', 'session_terminate': 'Запрошено отключение',
        'connection_ticket_created': 'Выдан токен подключения', 'generic_event': 'Событие аудита',
    },
}


def _text(value, maximum=160):
    """Project metadata to printable bounded strings before HTML rendering."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ''
    return ''.join(char for char in str(value) if ord(char) >= 32 and ord(char) != 127)[:maximum]


def _escape(value):
    return html.escape(str(value), quote=True)


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _duration(seconds):
    if seconds is None:
        return '—'
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return '{:02d}:{:02d}:{:02d}'.format(hours, minutes, seconds)


def _timestamp(value):
    number = _number(value)
    if number is None:
        return '—'
    try:
        return datetime.datetime.fromtimestamp(number, datetime.timezone.utc).strftime('%H:%M:%S')
    except (ValueError, OSError, OverflowError):
        return '—'


def _locale(config):
    from isolate_web import _dashboard_locale
    return _dashboard_locale(config)


def _require_admin(identity, config):
    if not is_platform_admin(identity, config):
        raise PermissionDenied('platform administration is required for the overview')


def overview_snapshot(config, redis, identity, now=None):
    """Return a bounded safe projection. Never return audit payloads or tokens."""
    _require_admin(identity, config)
    now = time.time() if now is None else now
    sessions = []
    durations = []
    available = True
    try:
        redis.ping()
        records = list_active_sessions(redis)
    except Exception:
        records = []
        available = False
    for row in records:
        start = _number(row.get('started_at'))
        age = max(0, now - start) if start is not None else None
        if age is not None:
            durations.append(age)
        if len(sessions) < 100:
            sessions.append({
                'id': _text(row.get('connection_id'), 128), 'username': _text(row.get('username'), 80),
                'host': _text(row.get('server_name') or row.get('host_name') or row.get('host_id'), 100),
                'address': _text(row.get('target_host') or row.get('server_ip'), 64),
                'protocol': _text(row.get('protocol') or 'ssh', 24), 'duration': _duration(age),
                'terminating': bool(row.get('terminate_requested')),
            })
    indexed = bool(config.get('audit_index', {}).get('enabled'))
    audit_available = True
    events = []
    try:
        if indexed:
            from isolate_audit_index import AuditIndex
            source = AuditIndex(config['audit_index']).search(limit=30, include_index_time=True)['events']
        else:
            from isolate_history import read_history
            source = read_history(config.get('logging', {}).get('base_path', ''), identity,
                limit=30, admin_groups=config.get('dashboard', {}).get('admin_groups') or [],
                permission_config=config, archive_config=config, state_client=redis)
        for row in reversed(source[:30]):
            name = _text(row.get('event') or ('ssh_end' if str(row.get('result', '')).startswith('exit=') else 'ssh_start'), 80)
            outcome = _text(row.get('outcome') or row.get('status') or row.get('result'), 40)
            level = 'WARN' if any(word in (name + ' ' + outcome).lower() for word in ('denied','fail','error','revok','reject')) else (
                'AUTH' if any(word in name.lower() for word in ('auth','login','logout','policy','ticket','approval')) else 'INFO')
            timestamp = row.get('ts') or row.get('_index_timestamp')
            actor = _text(row.get('username') or row.get('actor'), 64)
            project = _text(row.get('project'), 64)
            host = _text(row.get('host_id'), 32)
            source_id = _text(row.get('event_id') or row.get('connection_id'), 128)
            # Use a stable opaque key to keep the visible row anchored during refresh.
            anchor = repr((source_id, _number(timestamp), name, actor, project, host)).encode('utf-8')
            events.append({'time': _timestamp(timestamp), 'level': level, 'event': name, 'actor': actor,
                'project': project, 'host': host, 'anchor': hashlib.sha256(anchor).hexdigest()[:24]})
    except Exception:
        audit_available = False
    return {'available': available, 'active_count': len(records) if available else None,
        'average_duration': _duration(sum(durations) / len(durations) if durations else None),
        'sessions': sessions, 'events': events, 'audit_available': audit_available,
        'indexed': indexed, 'updated': _timestamp(now), 'partial': len(records) > len(sessions)}


def _icon(name):
    from isolate_ui_icons import icon
    return icon(name)


def _stat(label, value, hint, symbol, note, state='neutral'):
    return ('<section class="overview-stat" data-stat="{symbol}" data-stat-state="{state}">'
            '<div class="overview-stat-top"><span class="overview-stat-icon">{icon}</span><h3>{label}</h3></div>'
            '<strong class="overview-stat-value font-mono">{value}</strong>'
            '<p class="overview-stat-note">{note}</p><p class="overview-stat-hint">{hint}</p></section>').format(
        icon=_icon(symbol), label=_escape(label), value=_escape(value), note=_escape(note),
        hint=_escape(hint), symbol=_escape(symbol), state=_escape(state))


def render_overview_fragment(config, redis, csrf_token, identity):
    """Refreshable columns; the root route must authenticate each request."""
    labels = WORDS[_locale(config)]
    data = overview_snapshot(config, redis, identity)
    stats = _stat(labels['active'], data['active_count'] if data['available'] else '—',
        labels['active_help'], 'activity', labels['online'] if data['available'] else labels['offline'],
        'healthy' if data['available'] else 'unavailable')
    stats += _stat(labels['blocked'], '—', labels['blocked_help'], 'shield-check', labels['not_configured'])
    average_note = 'average_scope'
    average_hint = 'average_help'
    if not data['available']:
        average_note = 'unavailable'
    elif not data['active_count']:
        average_note, average_hint = 'no_sessions', 'average_pending'
    elif data['average_duration'] == '—':
        average_note = 'start_unavailable'
    stats += _stat(labels['average'], data['average_duration'], labels[average_hint], 'clock',
        labels[average_note], 'neutral' if data['available'] else 'unavailable')
    rows = []
    termination_enabled = config.get('session_control', {}).get('terminate_enabled', False)
    for row in data['sessions']:
        session_url = '/session/' + quote(row['id'], safe='')
        actions = '<a class="overview-log-action" href="{}">{}{}</a>'.format(
            session_url, _icon('arrow-up-right'), _escape(labels['logs'])) if row['id'] else ''
        if row['terminating']:
            actions += '<span class="overview-pending">{}</span>'.format(_escape(labels['terminating']))
        elif termination_enabled and row['id']:
            actions += '<button type="button" class="overview-terminate" data-overview-terminate="{}" aria-label="{}">{}</button>'.format(
                _escape(row['id']), _escape(labels['terminate'] + ' · ' + row['username']), _escape(labels['terminate']))
        rows.append('<tr><td><span class="overview-person">{user}</span><span class="overview-secondary font-mono text-xs">{id}</span></td>'
            '<td><span class="overview-resource">{host}</span><span class="overview-secondary font-mono text-xs">{address}</span></td>'
            '<td><span class="overview-protocol font-mono text-xs">{protocol}</span></td>'
            '<td class="font-mono text-xs overview-duration">{duration}</td><td><div class="overview-actions">{actions}</div></td></tr>'.format(
                user=_escape(row['username'] or labels['unknown']), id=_escape(row['id'][:12]),
                host=_escape(row['host'] or labels['unknown']), address=_escape(row['address'] or '—'),
                protocol=_escape(row['protocol'].upper()), duration=row['duration'], actions=actions))
    if rows:
        table = '<div class="overview-table-scroll" tabindex="0" role="region" aria-labelledby="overview-sessions-title"><table class="overview-table"><thead><tr>' + ''.join(
            '<th scope="col">{}</th>'.format(_escape(labels[key])) for key in ('user','resource','protocol','duration','actions'))
        table += '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
    else:
        key = 'empty' if data['available'] else 'unavailable'
        table = '<div class="overview-empty">{}<h3>{}</h3><p>{}</p></div>'.format(
            _icon('terminal'), _escape(labels[key]), _escape(labels['empty_help']) if data['available'] else '')
    if data['partial']:
        table += '<p class="overview-footnote">{}</p>'.format(_escape(labels['partial'].format(count=len(rows))))
    audit_rows = []
    for event in reversed(data['events']):
        # Producer event identifiers remain visible separately from translated UI.
        context = ' · '.join(value for value in (event['actor'], event['project'], event['host']) if value)
        subject = '<span class="overview-audit-subject">{}</span>'.format(_escape(context)) if context else ''
        audit_rows.append('<li class="overview-audit-row overview-level-{level}" data-audit-event="{anchor}"><div class="overview-audit-meta">'
            '<span class="overview-audit-prefix">{prefix}</span><span class="overview-audit-title">{title}</span><time>{time}</time></div>'
            '<div class="overview-audit-detail"><code class="overview-audit-code">{code}</code>'
            '{subject}</div></li>'.format(
                level=event['level'].lower(), time=event['time'], prefix=event['level'], anchor=_escape(event['anchor']),
                title=_escape(labels.get(event['event'], labels['generic_event'])), code=_escape(event['event']),
                subject=subject))
    if not audit_rows:
        key = 'audit_empty' if data['audit_available'] else 'audit_unavailable'
        symbol = 'file-clock' if data['audit_available'] else 'shield-alert'
        state = 'empty' if data['audit_available'] else 'unavailable'
        audit_rows.append('<li class="overview-audit-empty" data-feed-state="{}">{}{}</li>'.format(
            state, _icon(symbol), _escape(labels[key])))
    result = '<div class="overview-stats" aria-label="{}">{}</div>'.format(_escape(labels['stats']), stats)
    result += '<section class="overview-sessions"><div class="overview-panel-heading">'
    result += '<div class="overview-panel-label">{}<div><h2 id="overview-sessions-title">{}</h2><p>{}</p></div></div><span class="overview-count font-mono text-xs">{}</span></div>'.format(
        _icon('activity'), _escape(labels['sessions']), _escape(labels['sessions_help']), _escape(data['active_count'] if data['available'] else '—'))
    result += '<div class="overview-sessions-body">' + table + '</div>'
    result += '<a class="overview-panel-footer" href="/sessions/active">{}{}</a></section>'.format(_escape(labels['view_all']), _icon('arrow-up-right'))
    result += '<section class="overview-audit"><div class="overview-panel-heading">'
    result += '<div class="overview-panel-label">{}<div><h2 id="overview-audit-title">{}</h2><p>{}</p></div></div><span class="overview-count font-mono text-xs" title="{}">UTC</span></div>'.format(
        _icon('file-clock'), _escape(labels['audit']), _escape(labels['audit_help'] if data['indexed'] else labels['history_help']), _escape(labels['utc']))
    result += '<ol class="overview-audit-stream" tabindex="0" aria-labelledby="overview-audit-title">{}</ol>'.format(''.join(audit_rows))
    result += '<a class="overview-panel-footer" href="{}">{}{}</a></section>'.format(
        '/audit/search' if data['indexed'] else '/history',
        _escape(labels['audit_link'] if data['indexed'] else labels['history_link']), _icon('arrow-up-right'))
    result += '<p class="overview-snapshot-time font-mono text-xs">{} {} · {}</p>'.format(_escape(labels['updated']),data['updated'],_escape(labels['utc']))
    return result


def render_overview(config, redis, csrf_token, identity):
    labels = WORDS[_locale(config)]
    _require_admin(identity, config)
    body = '<section class="enterprise-overview" data-overview-url="/dashboard/overview-fragment" data-overview-error="{}" data-overview-refreshing="{}">'.format(
        _escape(labels['refresh_error']), _escape(labels['refreshing']))
    body += '<div class="overview-heading"><div><p class="overview-eyebrow">{}</p><h1>{}</h1><p class="page-lead">{}</p></div>'.format(
        _escape(labels['eyebrow']), _escape(labels['heading']), _escape(labels['lead']))
    body += '<div class="overview-heading-actions"><span class="overview-live-label"><span class="overview-live-dot" aria-hidden="true"></span>{}</span><button type="button" class="overview-refresh" data-overview-refresh aria-label="{}">{}</button></div></div>'.format(
        _escape(labels['live']), _escape(labels['refresh']), _icon('refresh-cw'))
    body += '<p class="overview-refresh-status" role="status" aria-live="polite"></p>'
    body += '<div id="overview-live-region" class="overview-grid">' + render_overview_fragment(config, redis, csrf_token, identity) + '</div>'
    body += '<dialog id="overview-terminate-dialog" class="overview-dialog" aria-labelledby="overview-terminate-title"><form method="post">'
    body += '<h2 id="overview-terminate-title">{}</h2><p>{}</p>'.format(_escape(labels['termination_title']),_escape(labels['termination_help']))
    body += '<input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="confirm" value="true">'.format(_escape(csrf_token))
    body += '<label for="overview-terminate-reason">{}</label><input id="overview-terminate-reason" name="reason" maxlength="1024" placeholder="{}" aria-describedby="overview-reason-help"><p id="overview-reason-help" class="field-hint">{}</p>'.format(
        _escape(labels['reason']),_escape(labels['reason_placeholder']),_escape(labels['reason_hint']))
    body += '<div class="overview-dialog-actions"><button type="button" data-overview-dialog-close>{}</button><button type="submit" class="button-danger">{}</button></div></form></dialog></section>'.format(
        _escape(labels['cancel']),_escape(labels['confirm']))
    body += '<script src="/static/dashboard-overview.js" defer></script>'
    return body


def render_settings(config):
    """Read-only deployment overview with an explicit safe field projection."""
    russian = _locale(config) == 'ru'
    from isolate_oidc import identity_provider_config
    provider = identity_provider_config(config)
    title = 'Настройки платформы' if russian else 'Platform settings'
    lead = ('Действующие параметры входа и состояние компонентов. Для изменения настроек обратитесь к администратору бастиона.'
            if russian else 'Component state and sign-in configuration. Configuration changes are applied by your deployment administrator.')
    enabled = 'Включено' if russian else 'Enabled'
    disabled = 'Выключено' if russian else 'Disabled'
    groups = [
        ('Вход в Isolate' if russian else 'Identity', [
            ('Служба входа' if russian else 'Provider', provider.get('display_name') or provider.get('provider') or 'OIDC'),
            ('Вход' if russian else 'Sign-in', 'OpenID Connect · PKCE S256'),
            ('Адрес портала' if russian else 'Portal URL', config.get('dashboard', {}).get('public_url') or '—'),
        ]),
        ('Сервисы' if russian else 'Services', [
            (label, enabled if config.get(section, {}).get('enabled') else disabled)
            for section, label in [('api','API'), ('gateway','SSH / Web SSH'), ('audit_index','Индекс аудита' if russian else 'Audit index'),
                ('campaigns','Поэтапные запуски' if russian else 'Staged operations'),
                ('recordings','Архив записей' if russian else 'Recording archive')]
        ]),
    ]
    body = '<h1>{}</h1><p class="page-lead">{}</p><div class="settings-grid">'.format(_escape(title), _escape(lead))
    for heading, rows in groups:
        body += '<section class="panel"><h2>{}</h2><dl>'.format(_escape(heading))
        body += ''.join('<dt>{}</dt><dd>{}</dd>'.format(_escape(label), _escape(value)) for label, value in rows)
        body += '</dl></section>'
    return body + '</div>'
