"""Browser filters and server-rendered views for the scoped audit index."""

import datetime
import html
import json
import math
import time
from urllib.parse import urlencode

from isolate_history import parse_history_time
from isolate_ui_icons import icon


_FILTERS = ("q", "period", "event", "host_id", "connection_id", "since", "until", "limit", "before")
_PERIODS = {
    "1h": (3600, "Last hour", "Последний час"),
    "24h": (86400, "Last 24 hours", "Последние 24 часа"),
    "7d": (604800, "Last 7 days", "Последние 7 дней"),
}
_EVENTS = {
    "identity_login": ("Signed in", "Вход в Isolate"),
    "identity_logout": ("Signed out", "Выход из Isolate"),
    "ssh_start": ("SSH session opened", "Открыта SSH-сессия"),
    "ssh_end": ("SSH session closed", "Закрыта SSH-сессия"),
    "ssh_denied": ("SSH connection denied", "SSH-подключение отклонено"),
    "command": ("Command recorded", "Записана команда"),
    "policy_selected": ("Access rule selected", "Выбрано правило доступа"),
    "campaign_created": ("Staged run created", "Создан поэтапный запуск"),
    "connection_ticket_created": ("Connection ticket issued", "Выдан билет подключения"),
    "session_terminate": ("Session termination requested", "Запрошено завершение сессии"),
}
_ERRORS = {
    "q": ("Enter at most 256 characters.", "Введите не больше 256 символов."),
    "period": ("Choose an available time range.", "Выберите период из списка."),
    "since": ("Enter a date, a timestamp with a time zone, or Unix time.",
              "Укажите дату, дату и время с часовым поясом или метку времени Unix."),
    "until": ("Enter a date, a timestamp with a time zone, or Unix time.",
              "Укажите дату, дату и время с часовым поясом или метку времени Unix."),
    "range": ("The end must be on or after the start.", "Конец периода должен быть не раньше начала."),
    "limit": ("Enter a whole number from 1 to 500.", "Введите целое число от 1 до 500."),
    "before": ("This page link is invalid. Open the latest results.",
               "Ссылка на страницу устарела или повреждена. Откройте последние события."),
    "exact": ("Enter an identifier of at most 256 characters.", "Укажите идентификатор длиной до 256 символов."),
}


class AuditFilterError(ValueError):
    def __init__(self, field, message_key=None):
        self.field = field
        self.message_key = message_key or field
        super().__init__(field)


def audit_browser_fields(args):
    return {key: value for key in _FILTERS if (value := args.get(key, "").strip())}


def audit_browser_query(fields):
    """Accept browser dates and time presets without changing the API contract."""
    filters = dict(fields)
    query = filters.get("q", "")
    if len(query) > 256:
        raise AuditFilterError("q")
    for name in ("event", "host_id", "connection_id"):
        if len(filters.get(name, "")) > 256:
            raise AuditFilterError(name, "exact")
    period = filters.pop("period", "")
    if period:
        if period not in _PERIODS:
            raise AuditFilterError("period")
        filters["since"] = time.time() - _PERIODS[period][0]
        filters.pop("until", None)
    else:
        for name in ("since", "until"):
            try:
                filters[name] = parse_history_time(filters.get(name), end_of_day=name == "until")
            except (ValueError, OverflowError, OSError):
                raise AuditFilterError(name) from None
        if all(filters[key] is not None for key in ("since", "until")) and filters["since"] > filters["until"]:
            raise AuditFilterError("until", "range")
    try:
        maximum = int(filters.get("limit", 25))
        if not 1 <= maximum <= 500:
            raise ValueError()
    except ValueError:
        raise AuditFilterError("limit") from None
    filters["limit"] = maximum
    if "before" in filters:
        try:
            cursor = json.loads(filters["before"])
            if (not isinstance(cursor, list) or len(cursor) != 2 or type(cursor[0]) not in (int, float)
                    or not math.isfinite(cursor[0]) or not isinstance(cursor[1], str) or not cursor[1]
                    or len(cursor[1]) > 256):
                raise ValueError()
        except (ValueError, RecursionError, OverflowError):
            raise AuditFilterError("before") from None
    return filters


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _url(fields, **updates):
    query = urlencode({key: value for key, value in dict(fields, **updates).items() if value is not None})
    return "/audit/search" + ("?" + query if query else "")


def _date(value):
    try:
        return datetime.datetime.fromtimestamp(float(value), datetime.timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _event_label(value, russian):
    return _EVENTS.get(value, (value, value))[russian]


def _status(record):
    value = str(record.get("result") or record.get("outcome") or record.get("status") or "")
    if not value and record.get("exit_code") is not None:
        value = "exit={}".format(record["exit_code"])
    tone = {
        "allowed": "positive", "ok": "positive", "success": "positive", "completed": "positive",
        "exit=0": "positive", "denied": "danger", "failed": "danger", "error": "danger",
        "blocked": "danger", "pending": "warning", "queued": "warning",
    }.get(value.lower(), "")
    if value.startswith("exit=") and value.removeprefix("exit=").lstrip("-").isdigit() and value != "exit=0":
        tone = "danger"
    return value, tone


def _status_chip(config, record):
    from isolate_workflow_ui import workflow_value

    value, tone = _status(record)
    if not value:
        return "—"
    text = workflow_value(config, value)
    return '<span class="admin-chip" data-tone="{}">{}</span>'.format(tone, _e(text))


def _inspector(config, record, fields, russian):
    def tr(en, ru):
        return ru if russian else en

    date = _date(record.get("ts"))
    values = (
        (tr("Event ID", "ID события"), record.get("event_id")),
        (tr("Time (UTC)", "Время (UTC)"), date.isoformat(timespec="seconds") if date else None),
        (tr("Actor", "Пользователь"), record.get("username")),
        (tr("Project", "Проект"), record.get("project")),
        (tr("Host ID", "ID сервера"), record.get("host_id")),
        (tr("Session ID", "ID сессии"), record.get("connection_id") or record.get("session_id")),
    )
    details = "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(label, _e(value)) for label, value in values if value)
    connections = record.get("connection_id") or record.get("session_id")
    related = (
        '<a class="admin-button" href="/investigations?{}">{}</a>'.format(
            _e(urlencode({"kind": "connection", "id": connections})), tr("Open investigation", "Открыть расследование"))
        if connections else ""
    )
    raw = _e(json.dumps(record, indent=2, ensure_ascii=False))
    return ('<aside id="audit-event" class="admin-panel audit-inspector" aria-labelledby="audit-detail-title" tabindex="-1">'
            '<header class="admin-toolbar"><h2 id="audit-detail-title">{title}</h2>'
            '<a class="admin-button" href="{close}">{close_label}</a></header>'
            '<code class="admin-meta">{code}</code>{status}<dl>{details}</dl>{related}'
            '<details class="admin-disclosure"><summary>{json_label}</summary><pre>{raw}</pre></details></aside>').format(
        title=_e(_event_label(str(record.get("event") or ""), russian)), close=_e(_url(fields)),
        close_label=tr("Close", "Закрыть"), code=_e(record.get("event")), status=_status_chip(config, record),
        details=details, related=related, json_label=tr("Event JSON", "JSON события"), raw=raw,
    )


def render_audit_page(config, fields, result=None, *, entry="", error=None, unavailable=False):
    from isolate_web import _dashboard_locale, _html
    from isolate_workflow_ui import workflow_hints

    russian = _dashboard_locale(config) == "ru"

    def tr(en, ru):
        return ru if russian else en

    def attributes(key):
        return ' aria-invalid="true" aria-describedby="audit-filter-error" autofocus' if error and key == error.field else ""

    def field(name, label, *, kind="text", placeholder="", extra=""):
        return ('<label>{}<input type="{}" name="{}" value="{}" maxlength="256" placeholder="{}"{}{}></label>').format(
            label, kind, name, _e(fields.get(name, "")), _e(placeholder), extra, attributes(name))

    title = tr("Audit search", "Журнал аудита")
    labels = {
        "q": tr("Search audit events", "Поиск по событиям"), "event": tr("Event type", "Тип события"),
        "period": tr("Time range", "Период"), "since": tr("From (UTC)", "Начало периода (UTC)"),
        "until": tr("To (UTC)", "Конец периода (UTC)"), "host_id": tr("Host ID", "ID сервера"),
        "connection_id": tr("Session ID", "ID сессии"), "limit": tr("Results per page", "Событий на странице"),
    }
    lead = tr("Find out who acted, when, and on which resource.", "Узнайте, кто, когда и на каком ресурсе выполнил действие.")
    body = '<section class="admin-page audit-search"><header class="admin-heading"><div><h1>{}</h1><p>{}</p></div></header>'.format(title, lead)
    if error:
        body += '<p class="notice error" id="audit-filter-error" role="alert">{}</p>'.format(_ERRORS[error.message_key][russian])
    if unavailable:
        body += '<p class="notice warning" role="alert">{}</p>'.format(
            tr("Audit events are temporarily unavailable. Try again shortly.", "Журнал аудита временно недоступен. Повторите попытку позже."))
    body += '<form method="get" action="/audit/search" class="admin-panel audit-filters"><div class="admin-toolbar">'
    body += field("q", labels["q"], kind="search", placeholder=tr("User, project, operation or ID", "Пользователь, проект, операция или ID"))
    period_labels = {"": tr("All time", "За всё время"), **{key: value[2 if russian else 1] for key, value in _PERIODS.items()}}
    if not fields.get("period") and (fields.get("since") or fields.get("until")):
        period_labels[""] = tr("Custom range", "Свой период")
    options = "".join('<option value="{}"{}>{}</option>'.format(
        key, " selected" if fields.get("period", "") == key else "", value) for key, value in period_labels.items())
    body += '<label>{}<select name="period"{}>{}</select></label>'.format(labels["period"], attributes("period"), options)
    body += field("event", labels["event"], placeholder=tr("All events", "Все события"), extra=' list="audit-types"')
    body += '<datalist id="audit-types">{}</datalist>'.format("".join(
        '<option value="{}">{}</option>'.format(key, value[russian]) for key, value in _EVENTS.items()))
    body += '<button class="admin-primary" type="submit">{} {}</button></div>'.format(icon("search"), tr("Search", "Найти"))
    advanced_keys = ("host_id", "connection_id", "since", "until", "limit")
    advanced_open = any(key in fields for key in advanced_keys) or bool(error and error.field in advanced_keys)
    body += '<details class="admin-disclosure"{}><summary>{} {}</summary><div class="admin-fields">'.format(
        " open" if advanced_open else "", icon("sliders-horizontal"), tr("Advanced filters", "Дополнительные фильтры"))
    body += "".join(field(key, labels[key], placeholder="2026-11-26" if key in ("since", "until") else "") for key in advanced_keys[:-1])
    body += field("limit", labels["limit"], placeholder="25", extra=' inputmode="numeric"')
    body += '</div><p class="admin-meta">{}</p></details></form>'.format(
        tr("Dates use UTC. To search for an exact time, include its time zone.", "Даты указаны в UTC. Для точного времени добавьте часовой пояс."))
    chips = []
    active_fields = dict(fields, before=None)
    for key in labels:
        if key in fields and not (key in ("since", "until") and fields.get("period")):
            label = period_labels.get(fields[key], fields[key]) if key == "period" else fields[key]
            chips.append('<a class="admin-chip" href="{}" aria-label="{}">{} · {} {}</a>'.format(
                _e(_url(active_fields, **{key: None})), _e(tr("Clear ", "Убрать фильтр ") + labels[key]),
                labels[key], _e(label), icon("x")))
    if chips or fields.get("before"):
        body += '<div class="admin-toolbar audit-chips">{}<a class="admin-button" href="/audit/search">{}</a></div>'.format(
            "".join(chips), tr("Clear filters", "Сбросить фильтры"))
    if result is None:
        return _html(title, workflow_hints(config, body + "</section>"), config=config)

    rows = result["events"]
    selected = next((record for record in rows if entry and record.get("event_id") == entry), None)
    body += '<div class="admin-split">' if selected else "<div>"
    body += '<section class="admin-panel audit-results"><header class="admin-toolbar"><h2>{}</h2><span class="admin-meta">{}</span></header>'.format(
        tr("Events", "События"), tr("UTC · Newest first", "UTC · Сначала новые"))
    if not rows:
        body += '<p class="admin-empty" role="status">{}</p>'.format(tr("No events match these filters.", "По этим фильтрам событий нет."))
    else:
        columns = (tr("Time", "Время"), tr("Event", "Событие"), tr("Actor", "Пользователь"),
                   tr("Project / host", "Проект / сервер"), tr("Result", "Результат"))
        body += '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>'.format("".join(
            '<th scope="col">{}</th>'.format(label) for label in columns))
        previous = None
        for record in rows:
            date = _date(record.get("ts"))
            day = date.date().isoformat() if date else tr("Time not recorded", "Время не записано")
            if day != previous:
                body += '<tr class="audit-day"><th scope="rowgroup" colspan="5">{}</th></tr>'.format(day)
                previous = day
            name = str(record.get("event") or "—")
            event_id = record.get("event_id")
            row_url = _url(fields, entry=event_id) + "#audit-event"
            glyph = "terminal" if name.startswith(("ssh_", "command")) else "shield-check"
            body += ('<tr{selected}><td><code>{time}</code></td><td><a class="audit-event-link" href="{url}">'
                     '{icon}<span><strong>{title}</strong><code class="admin-meta">{code}</code></span></a></td>'
                     '<td>{actor}</td><td>{project}<code class="admin-meta">{host}</code></td><td>{status}</td></tr>').format(
                selected=' class="audit-selected"' if selected is record else "", time=date.strftime("%H:%M:%S") if date else "—",
                url=_e(row_url), icon=icon(glyph), title=_e(_event_label(name, russian)), code=_e(name),
                actor=_e(record.get("username")) or "—", project=_e(record.get("project")) or "—",
                host=("#" + _e(record["host_id"])) if record.get("host_id") else "", status=_status_chip(config, record),
            )
        body += '</tbody></table></div>'
    body += '<footer class="admin-toolbar audit-pagination"><span class="admin-meta">{} · {}</span>'.format(
        tr("On this page", "На странице"), len(rows))
    if fields.get("before"):
        body += '<a class="admin-button" href="{}">{}</a>'.format(_e(_url(fields, before=None)), tr("Newest", "Последние"))
    if result["next"]:
        body += '<a class="admin-button" href="{}">{} {}</a>'.format(
            _e(_url(fields, before=json.dumps(result["next"]))), tr("Older", "Ранее"), icon("arrow-right"))
    body += '</footer></section>'
    if selected:
        body += _inspector(config, selected, fields, russian)
    elif entry:
        body += '<p class="notice warning" role="status">{}</p>'.format(
            tr("This event is outside the current page or access scope.", "Событие вне текущей страницы или недоступно с вашими правами."))
    return _html(title, workflow_hints(config, body + "</div></section>"), config=config)
