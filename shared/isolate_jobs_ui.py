"""Server-rendered job console, runbook review and execution details."""

import html
import json
from urllib.parse import quote, urlencode

from isolate_admin_ui import admin_heading as _heading
from isolate_ui_icons import icon
from isolate_workflow_ui import COPY_RU


_STATUS = {
    "queued": ("Queued", "В очереди", "info"),
    "claimed": ("Claimed", "Задание принято", "info"),
    "running": ("Running", "Выполняется", "info"),
    "held": ("Waiting for stage", "Ожидает этапа", "info"),
    "recovery_required": ("Check outcome", "Требуется проверка", "warning"),
    "completed": ("Completed", "Завершено", "positive"),
    "failed": ("Failed", "Ошибка", "danger"),
    "cancelled": ("Cancelled", "Отменено", "info"),
    "timed_out": ("Timed out", "Время истекло", "danger"),
}

_RUNBOOK_DESCRIPTIONS_RU = {
    "uptime": "Показывает время работы системы и среднюю нагрузку.",
    "disk-usage": "Показывает типы файловых систем и занятое место.",
    "inode-usage": "Показывает использование inode на смонтированных файловых системах.",
    "memory": "Показывает объём и использование оперативной памяти и swap.",
    "cpu-processes": "Снимок процессов, отсортированных по нагрузке на CPU.",
    "memory-processes": "Снимок процессов, отсортированных по использованию памяти.",
    "top-snapshot": "Сохраняет один снимок вывода top.",
    "atop-snapshot": "Сохраняет один снимок метрик CPU, памяти, дисков и сети.",
    "service-status": "Показывает подробный статус юнита systemd.",
    "service-active": "Проверяет, активен ли юнит systemd.",
    "journal-tail": "Возвращает последние записи журнала юнита systemd.",
    "failed-services": "Перечисляет юниты systemd в состоянии failed.",
    "listening-sockets": "Показывает открытые сокеты TCP и UDP и связанные процессы.",
    "network-addresses": "Показывает сетевые интерфейсы и их адреса.",
    "network-routes": "Показывает текущую таблицу маршрутизации.",
    "service-restart": "Перезапускает указанный юнит systemd.",
    "dns-cache-flush": "Очищает кеш systemd-resolved.",
    "deploy-diagnostics": "Собирает состояние службы, её журнал, данные о дисках и памяти.",
}


def _escape(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _copy(locale):
    return lambda en, ru: ru if locale == "ru" else en


def _status(value, locale):
    en, ru, tone = _STATUS.get(value, ("Unknown", "Неизвестно", "warning"))
    return '<span class="admin-chip" data-tone="{}">{}</span>'.format(tone, _copy(locale)(en, ru))


def _job_type(value, locale):
    t = _copy(locale)
    if value == "runbook":
        return t("Runbook", "Регламент")
    if value == "remote-command":
        return t("Remote command", "Удалённая команда")
    return str(value or t("Unknown", "Неизвестно"))


def _runbook_title(record, locale):
    title = record.get("title") or record["id"]
    return COPY_RU.get(title, title) if locale == "ru" and record.get("source") != "custom" else title


def _runbook_kind(record, locale):
    t = _copy(locale)
    changing = record.get("class") == "operational"
    return '<span class="admin-chip" data-tone="{}">{}</span>'.format(
        "warning" if changing else "positive",
        t("Changes state", "Меняет состояние") if changing else t("Read-only", "Только чтение"),
    )


def _jobs_url(view="runs", **values):
    return "/jobs?" + urlencode({"view": view, **values})


def _hint(content):
    return '<small class="admin-muted">{}</small>'.format(_escape(content))


def _field(label, control, hint=""):
    return '<label>{} {}{}</label>'.format(_escape(label), control, _hint(hint) if hint else "")


def _input(name, value, *, kind="text", extra=""):
    return '<input type="{}" name="{}" value="{}" {}>'.format(_escape(kind), _escape(name), _escape(value), extra)


def _checkbox(label):
    return '<label><input type="checkbox" name="confirm" value="true" required> {}</label>'.format(_escape(label))


def _section(title, content, *, style="admin-panel"):
    return '<section class="{}"><h2>{}</h2>{}</section>'.format(style, _escape(title), content)


def _fields(content):
    return '<div class="admin-fields">{}</div>'.format(content)


def _link(url, label, *, primary=False, glyph=""):
    return '<a class="admin-button{}" href="{}">{}{}</a>'.format(
        " admin-primary" if primary else "", _escape(url), icon(glyph) if glyph else "", _escape(label),
    )


def _tab(url, label, current):
    return '<a href="{}"{}>{}</a>'.format(_escape(url), ' aria-current="page"' if current else "", _escape(label))


def _table(headings, rows):
    head = "".join('<th scope="col">{}</th>'.format(_escape(title)) for title in headings)
    body = "".join("<tr>" + "".join("<td>" + value + "</td>" for value in row) + "</tr>" for row in rows)
    return '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(head, body)


def _small(value):
    return '<div class="admin-meta font-mono">{}</div>'.format(_escape(value or "—"))


def _stat(icon_name, value, title):
    return ('<div class="summary-item">{}<strong>{}</strong><span class="admin-muted">{}</span></div>').format(
        icon(icon_name), value, _escape(title))


def _parameter_label(name, locale):
    t = _copy(locale)
    return {"service": t("Systemd unit", "Юнит systemd"), "lines": t("Number of lines", "Число строк")}.get(name, name)


def _parameter_fields(runbook, values, locale):
    t = _copy(locale)
    fields = []
    for name, definition in runbook["parameters"].items():
        value = values.get("parameter_" + name, definition.get("default", ""))
        attributes = ["required"] if definition.get("required") else []
        if definition["type"] == "integer":
            for key, attribute in (("minimum", "min"), ("maximum", "max")):
                if key in definition:
                    attributes.append('{}="{}"'.format(attribute, int(definition[key])))
            hint = t("Enter a whole number.", "Укажите целое число.")
            kind = "number"
        else:
            hint = ""
            kind = "text"
            if name == "service":
                attributes.append('maxlength="128" placeholder="nginx.service"')
                hint = t("Use the unit name, for example nginx.service.", "Например, nginx.service.")
        fields.append(_field(_parameter_label(name, locale),
                             _input("parameter_" + name, value, kind=kind, extra=" ".join(attributes)), hint))
    return "".join(fields)


def runbook_parameters(form, parse_json):
    """Accept the existing JSON field and the typed fields in the runbook form."""
    raw = form.get("parameters") or ""
    if raw.strip():
        return parse_json(raw, "runbook parameters")
    return {key.removeprefix("parameter_"): value for key, value in form.items()
            if key.startswith("parameter_") and value.strip()}


def _runbook_form(runbook, token, values, locale, max_timeout, json_mode):
    t = _copy(locale)
    runbook_id = runbook["id"]
    toggle = _link(_jobs_url("runbooks", runbook=runbook_id, parameters="guided" if json_mode else "json") + "#runbook-launch",
                   t("Use guided fields", "Заполнить поля") if json_mode else t("Use JSON", "Ввести JSON"))
    if json_mode:
        control = '<textarea name="parameters" rows="4">{}</textarea>'.format(_escape(values.get("parameters", "{}")))
        params = _field(t("Parameters JSON", "Параметры (JSON)"), control,
                        t("Use the parameter names defined by this runbook.", "Укажите параметры этого регламента в виде JSON-объекта."))
    else:
        params = _parameter_fields(runbook, values, locale)
    if not params:
        params = '<p class="admin-muted">{}</p>'.format(t("This runbook has no parameters.", "Для этого регламента параметры не нужны."))
    params += _field(t("Timeout, seconds", "Таймаут, с"),
                     _input("timeout", values.get("timeout", ""), kind="number", extra='min="1" max="{}" placeholder="{}"'.format(
                         max_timeout, int(runbook.get("default_timeout") or 60))),
                     t("Leave empty to use the runbook default.", "Оставьте пустым, чтобы использовать таймаут регламента."))
    targets = _field(t("Host IDs", "ID серверов"),
                     _input("host_ids", values.get("host_ids", ""), extra='placeholder="10001, 10002"'),
                     t("Separate inventory IDs with commas.", "Укажите ID серверов из каталога через запятую."))
    selectors = _field(t("Project", "Проект"), _input("project", values.get("project", "")))
    selectors += _field(t("Tags", "Теги"), _input("tags", values.get("tags", ""), extra='placeholder="env=stage"'))
    targets += ('<details class="admin-disclosure"{}><summary>{}</summary>{}</details>').format(
        " open" if values.get("project") or values.get("tags") else "",
        t("Select by project and tags", "Выбрать по проекту и тегам"), _fields(selectors),
    )
    return ('<section class="admin-panel" id="runbook-launch"><h2>{}</h2><p>{} {}</p>'
            '<form method="post" action="{}"><input type="hidden" name="csrf_token" value="{}">'
            '<input type="hidden" name="runbook_id" value="{}"><input type="hidden" name="runbook_parameter_mode" value="{}">'
            '<fieldset><legend>{}</legend><p class="admin-muted">{}</p>{}</fieldset>'
            '<fieldset><legend>{}</legend>{}<p>{}</p></fieldset>'
            '<button class="admin-button admin-primary" name="action" value="preview_runbook">{}</button></form></section>').format(
        t("Prepare a run", "Подготовить запуск"), _escape(_runbook_title(runbook, locale)), _runbook_kind(runbook, locale),
        _escape(_jobs_url("runbooks", runbook=runbook_id)), _escape(token), _escape(runbook_id), "json" if json_mode else "guided",
        t("1. Targets", "1. Серверы"),
        t("Enter host IDs or use project and tags. Choose one selection method.",
          "Укажите ID серверов или отберите цели по проекту и тегам."), targets,
        t("2. Parameters", "2. Параметры"), _fields(params), toggle,
        t("Review run", "Проверить перед запуском"))


def _runbook_review(review, token, locale):
    t = _copy(locale)
    runbook, parameters, timeout, planned, command = review
    targets = _table((t("Server", "Сервер"), t("Project", "Проект"), t("Remote account", "Учётная запись SSH")), [
        (_escape(host.get("server_name")) + _small(host["server_id"]), _escape(host.get("project_name")),
         _escape(decision.get("remote_user"))) for host, decision in planned
    ])
    body = '<p>{} {} · {} {}</p>'.format(_escape(_runbook_title(runbook, locale)), _runbook_kind(runbook, locale), timeout, t("sec", "с"))
    if runbook.get("source") == "custom":
        body += '<p>{}</p><pre><code>{}</code></pre>'.format(
            t("Command in version {}", "Команда в версии {}").format(runbook["version"]), _escape(command),
        )
    if parameters:
        body += '<dl class="key-value">{}</dl>'.format("".join(
            '<dt>{}</dt><dd><code>{}</code></dd>'.format(_escape(_parameter_label(name, locale)), _escape(value))
            for name, value in parameters.items()
        ))
    body += targets
    body += ('<form method="post" action="/jobs"><input type="hidden" name="csrf_token" value="{}">'
             '<input type="hidden" name="action" value="queue_runbook">'
             '<input type="hidden" name="definition_sha256" value="{}">'
             '<input type="hidden" name="runbook_id" value="{}"><input type="hidden" name="host_ids" value="{}">'
             '<input type="hidden" name="parameters" value="{}"><input type="hidden" name="timeout" value="{}">{}'
             '<div class="admin-actions"><button class="admin-button admin-primary">{}</button></div></form>').format(
        _escape(token), _escape(runbook["definition_sha256"]), _escape(runbook["id"]),
        _escape(",".join(str(host["server_id"]) for host, _ in planned)),
        _escape(json.dumps(parameters, ensure_ascii=False)), timeout,
        _checkbox(t("I have checked the targets and parameters.", "Я проверил серверы и параметры запуска.")),
        t("Queue execution", "Поставить в очередь"),
    )
    return _section(t("3. Confirm the run", "3. Подтверждение запуска"), body)


def _runbook_catalog(available, selected, token, values, locale, max_timeout, review, json_mode):
    t = _copy(locale)
    if review:
        return _runbook_review(review, token, locale) + (
            '<details class="admin-disclosure"><summary>{}</summary>{}</details>'
        ).format(t("Edit settings", "Изменить настройки"),
                 _runbook_form(review[0], token, values, locale, max_timeout, json_mode))
    body = _runbook_form(selected, token, values, locale, max_timeout, json_mode) if selected else ""
    cards = []
    for book in available:
        description = _RUNBOOK_DESCRIPTIONS_RU.get(book["id"], book["description"]) if locale == "ru" else book["description"]
        cards.append(_section(_runbook_title(book, locale), _small(book["id"]) + "<p>{}</p><p>{}</p>".format(
            _escape(description), _runbook_kind(book, locale)) + _link(
                _jobs_url("runbooks", runbook=book["id"]) + "#runbook-launch", t("Configure run", "Настроить запуск"))))
    if not cards:
        return '<div class="admin-empty">{}</div>'.format(
            t("No runbook class is enabled for your groups.", "Для ваших групп запуск регламентов не разрешён."))
    return body + _fields("".join(cards))


def _runs_panel(jobs, fleets, runbooks, args, token, locale, format_time):
    t = _copy(locale)
    options = "".join('<option value="{}"{}>{}</option>'.format(
        value, " selected" if args.get("status") == value else "", t(en, ru))
        for value, (en, ru, _) in _STATUS.items())
    exact = _fields("".join(_field(label, _input(name, args.get(name, ""))) for name, label in (
        ("user", t("Requested by", "Инициатор")), ("project", t("Exact project", "Точный проект")),
        ("host", t("Host ID", "ID сервера")))))
    types = "".join('<option value="{}"{}>{}</option>'.format(
        value, " selected" if args.get("type") == value else "", _job_type(value, locale))
        for value in ("runbook", "remote-command"))
    exact += _field(t("Type", "Тип задания"), '<select name="type"><option value="">{}</option>{}</select>'.format(
        t("All types", "Все типы"), types))
    form = ('<form method="get" action="/jobs"><input type="hidden" name="view" value="runs">'
            '<div class="admin-toolbar">{}{}</div><details class="admin-disclosure"{}><summary>{}</summary>{}</details>'
            '<div class="admin-actions"><button>{}</button>{}</div></form>').format(
        _field(t("Search by runbook, ID or project", "Поиск по регламенту, ID или проекту"),
               _input("q", args.get("q", ""), kind="search")),
        _field(t("Status", "Статус"), '<select name="status"><option value="">{}</option>{}</select>'.format(
            t("All statuses", "Все статусы"), options)),
        " open" if any(args.get(name) for name in ("user", "project", "host", "type")) else "",
        t("More filters", "Дополнительные фильтры"), exact,
        t("Apply filters", "Применить фильтры"), _link(_jobs_url(), t("Clear filters", "Сбросить")),
    )
    rows = []
    for job in jobs:
        identifier = str(job["id"])
        runbook = runbooks.get(job.get("runbook_id"))
        title = _runbook_title(runbook, locale) if runbook else job.get("runbook_id") or str(job.get("command") or "")[:80]
        label = title or _job_type(job.get("type"), locale)
        job_url = "/job/" + quote(identifier, safe="")
        rows.append((
            '<a href="{}">{}</a>{}'.format(job_url, _escape(label), _small("#" + identifier + " · " + _job_type(job.get("type"), locale))),
            _status(job.get("status"), locale), _escape(job.get("project")), _small(job.get("host_id")),
            _escape(job.get("username")), _small(format_time(job.get("created_at"))),
        ))
    results = _table(
        (t("Runbook / job", "Регламент / задание"), t("Status", "Статус"), t("Project", "Проект"),
         t("Server", "Сервер"), t("Requested by", "Инициатор"), t("Created", "Создано")), rows,
    ) if rows else '<div class="admin-empty">{}</div>'.format(t("No jobs match these filters.", "По выбранным фильтрам заданий нет."))
    body = _section(t("Job history", "История заданий"), form + results)
    if fleets:
        body += _fleet_panel(fleets, token, locale)
    return body


def _fleet_panel(fleets, token, locale):
    t = _copy(locale)
    rows = []
    for fleet in fleets:
        progress = '<progress value="{}" max="{}"></progress>{}'.format(
            fleet["finished"], fleet["total"], _small("{}/{}".format(fleet["finished"], fleet["total"])))
        counts = "{}: {} · {}: {} · {}: {} · {}: {} · {}: {} · {}: {}".format(
            t("Completed", "Успешно"), fleet["completed"], t("Failed", "Ошибки"), fleet["failed"] + fleet["timed_out"],
            t("Queued", "В очереди"), fleet["queued"], t("Running", "В процессе"), fleet["running"] + fleet["claimed"],
            t("Cancelled", "Отменено"), fleet["cancelled"], t("Check outcome", "Проверить"), fleet["recovery_required"],
        )
        action = ""
        if fleet["failed_job_ids"]:
            action = ('<details class="admin-disclosure"><summary>{}</summary><form method="post" action="/jobs">'
                      '<input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="action" value="retry_fleet">'
                      '<input type="hidden" name="fleet_id" value="{}">{}<button>{}</button></form></details>').format(
                t("Retry failed", "Повторить сбойные"), _escape(token), _escape(fleet["fleet_id"]),
                _checkbox(t("Confirm retry of failed jobs.", "Подтверждаю повтор заданий с ошибкой.")),
                t("Retry failed", "Повторить сбойные"))
        rows.append((_escape(fleet["runbook_id"]) + _small(fleet["fleet_id"]), _status(fleet["status"], locale),
                     _escape(fleet["username"]), progress, _escape(counts), action))
    return _section(t("Runs on multiple servers", "Запуски на нескольких серверах"), _table(
        (t("Fleet", "Группа заданий"), t("Status", "Статус"), t("Requested by", "Инициатор"),
         t("Progress", "Ход выполнения"), t("Results", "Результаты"), t("Actions", "Действия")), rows))


def render_jobs_page(*, locale, view, jobs, fleets, counts, runbooks, available, selected, review, args, values,
                     token, max_timeout, can_stage, format_time):
    t = _copy(locale)
    action = ""
    if available:
        action = _link(_jobs_url("runbooks", runbook=available[0]["id"]) + "#runbook-launch",
                       t("Run a runbook", "Запустить регламент"), primary=True, glyph="terminal")
    if view == "campaigns":
        action = _link("/operations/campaigns", t("Open staged operations", "Открыть поэтапные запуски"),
                       primary=True, glyph="workflow")
    title = t("Jobs & Runbooks", "Задания и регламенты")
    body = _heading(title, t("Run diagnostics and inspect outcomes for each server.",
                            "Запускайте диагностику и проверяйте результат по каждому серверу."), action)
    body += '<div class="summary-list">{}</div>'.format("".join(_stat(glyph, amount, label) for glyph, amount, label in (
        ("activity", sum(counts[status] for status in ("queued", "claimed", "running", "held")), t("Active jobs", "Активные задания")),
        ("circle-check", counts["completed"], t("Completed", "Завершено")),
        ("clock", counts["failed"] + counts["timed_out"] + counts["recovery_required"], t("Need attention", "Требуют внимания")),
    )))
    tabs = _tab(_jobs_url(), t("Runs", "Запуски"), view == "runs")
    tabs += _tab(_jobs_url("runbooks"), t("Runbooks", "Регламенты"), view == "runbooks")
    if can_stage:
        tabs += _tab(_jobs_url("campaigns"), t("Staged operations", "Поэтапные запуски"), view == "campaigns")
    tabs += _tab("/jobs/runbooks/manage", t("Manage runbooks", "Управление регламентами"), False)
    body += '<nav class="admin-tabs" aria-label="{}">{}</nav>'.format(t("Job views", "Разделы заданий"), tabs)
    if view == "runbooks":
        body += _runbook_catalog(available, selected, token, values, locale, max_timeout, review,
                                 args.get("parameters") == "json" or values.get("runbook_parameter_mode") == "json")
    elif view == "campaigns":
        body += _section(t("Run on a canary first", "Начните с пробных серверов"),
                         '<p>{}</p>'.format(t("Review target hosts, batch size and stop conditions before starting.",
                                             "Проверьте список серверов, размер групп и условия остановки перед запуском.")))
    else:
        body += _runs_panel(jobs, fleets, runbooks, args, token, locale, format_time)
    return '<div class="admin-page jobs-page">{}</div>'.format(body)


def _job_action(job, token, locale):
    t = _copy(locale)
    status = job.get("status")
    if status in ("queued", "claimed", "running"):
        action = "cancel"
        label = t("Cancel job", "Отменить задание")
    elif status in ("failed", "timed_out"):
        action = "retry"
        label = t("Retry job", "Повторить задание")
    else:
        return ""
    return ('<form method="post" action="/job/{}/{}"><input type="hidden" name="csrf_token" value="{}">{}'
            '<button class="admin-button{}">{}</button></form>').format(
        quote(str(job["id"]), safe=""), action, _escape(token),
        _checkbox(t("Confirm", "Подтверждаю")), " button-danger" if action == "cancel" else "", _escape(label))


def render_job_details(job, output, *, locale, token, format_time, explanation="", investigation=""):
    t = _copy(locale)
    job_id = str(job["id"])
    heading = _heading(t("Job", "Задание") + " " + job_id,
                       t("Execution result and captured command output.", "Результат выполнения и сохранённый вывод."),
                       _link(_jobs_url(), t("Back to runs", "К списку запусков")))
    head = '<div class="admin-toolbar">{} {} {}</div>'.format(_status(job.get("status"), locale),
        _small(job.get("runbook_id") or _job_type(job.get("type"), locale)),
        _small(t("Exit code", "Код завершения") + ": " + str(job["exit_code"]) if job.get("exit_code") is not None else ""))
    if job.get("status") == "recovery_required":
        head += '<div class="notice warning">{}</div>'.format(t(
            "The outcome is unknown. Check the server before starting another job.",
            "Результат неизвестен. Проверьте, что произошло на сервере, прежде чем запускать команду снова."))
    head += _job_action(job, token, locale)
    captured = _section(t("Command output", "Вывод команды"), '<pre tabindex="0">{}</pre>'.format(
        _escape(output or t("No output was captured.", "Нет сохранённого вывода команды."))))
    host = str(job.get("host_id") or "")
    attempt = str(job.get("attempt") or 1)
    fields = tuple((label, _escape(value)) for label, value in (
        (t("Type", "Тип задания"), _job_type(job.get("type"), locale)), (t("Requested by", "Инициатор"), job.get("username")),
        (t("Project", "Проект"), job.get("project")), (t("Remote account", "Учётная запись SSH"), job.get("remote_user")),
        ("sudo", job.get("sudo_mode")), (t("Created", "Создано"), format_time(job.get("created_at"))),
        (t("Started", "Начато"), format_time(job.get("started_at"))), (t("Finished", "Завершено"), format_time(job.get("finished_at"))),
        (t("Fleet / attempt", "Группа / попытка"), str(job.get("fleet_id") or "—") + " / " + attempt),
        (t("Error", "Ошибка"), job.get("error")),
    )) + ((t("Server", "Сервер"), '<a href="/history?{}">{}</a>'.format(urlencode({"host": host}), _escape(host))),)
    details = _section(t("Execution details", "Подробности запуска"),
                       '<dl class="key-value">{}</dl>{}'.format("".join("<dt>{}</dt><dd>{}</dd>".format(label, value or "—")
                                                                        for label, value in fields), investigation))
    snapshot = _escape(json.dumps({
        "groups": job.get("groups") or [], "roles": job.get("roles") or [], "grant_id": job.get("grant_id"),
        "policy_action": job.get("policy_action") or "command", "command_sha256": job.get("command_sha256"),
    }, indent=2, sort_keys=True))
    auth = '<details class="admin-disclosure"><summary>{}</summary><pre>{}</pre>{}</details>'.format(
        t("Authorization snapshot", "Права на момент запуска"), snapshot, explanation)
    return '<div class="admin-page jobs-page">{}{}<div class="admin-split">{}{}</div>{}</div>'.format(
        heading, head, captured, details, auth)
