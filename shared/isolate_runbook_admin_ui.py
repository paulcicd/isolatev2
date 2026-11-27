"""Draft, preview, and publish custom runbooks from the admin dashboard."""

from datetime import datetime, timezone
import html
import json
import re
from urllib.parse import urlencode

from flask import abort, make_response, redirect, request

from isolate_admin_ui import admin_empty, admin_heading


_MANAGE = "/jobs/runbooks/manage"
_CATALOG = "/jobs?view=runbooks"
_ERROR_RU = {
    "invalid or reserved runbook ID": "Укажите допустимый ID, свободный от встроенных регламентов.",
    "title must be text of 1 to 120 characters": "Укажите название длиной от 1 до 120 символов.",
    "description must be text of 0 to 1000 characters": "Сократите описание до 1000 символов.",
    "parameters must be an object with at most 24 entries": "Укажите в схеме JSON-объект с количеством параметров до 24.",
    "invalid parameter definition": "Проверьте имя и настройки каждого параметра в схеме.",
    "provide between 1 and 16 commands": "Укажите от 1 до 16 команд.",
    "each command must be an array of 1 to 32 strings": "Запишите каждую команду массивом из 1–32 строк.",
    "command arguments must be text of at most 4096 characters": "Ограничьте каждый аргумент команды 4096 символами.",
    "command must use a fixed absolute executable path": "Укажите абсолютный путь к исполняемому файлу первым элементом команды.",
    "a command parameter must occupy a whole argument": "Запишите параметр отдельным аргументом, например \"{service}\".",
    "command parameters must be arguments to a fixed script or executable": "Передавайте параметры как аргументы заранее указанного скрипта или программы.",
    "parameters must be an object": "Укажите пример значений как JSON-объект.",
    "runbook definition exceeds 16 KiB": "Сократите определение регламента до 16 КиБ.",
    "save a draft before publishing": "Сохраните черновик перед публикацией.",
    "runbook has reached its limit of 32 published versions": "У регламента уже 32 опубликованные версии. Создайте регламент с новым ID.",
    "published runbook version is not active": "Эта версия уже недоступна. Обновите список версий.",
    "custom runbook was not found": "Регламент не найден.",
}
_PARAMETER_ERRORS_RU = {
    "is required": "Заполните параметр «{}».",
    "must have type string or integer": "Выберите тип string или integer для параметра «{}».",
    "must be an integer": "Укажите целое число для параметра «{}».",
    "must be a 32-bit integer": "Укажите 32-битное целое число для параметра «{}».",
    "is below the minimum": "Значение параметра «{}» меньше заданного минимума.",
    "exceeds the maximum": "Значение параметра «{}» больше заданного максимума.",
    "minimum exceeds maximum": "Минимум превышает максимум в схеме параметра «{}».",
    "has an invalid value": "Значение параметра «{}» не соответствует его схеме.",
    "has an invalid pattern": "Исправьте шаблон для параметра «{}».",
    "pattern must be a single character class with an optional quantifier": "В шаблоне параметра «{}» укажите один класс символов. Можно задать допустимую длину.",
    "must be a safe string of 1 to 128 characters": "Укажите значение параметра «{}» длиной до 128 символов. Начните с латинской буквы или цифры и используйте буквы, цифры или символы _.:@/-.",
}


def _escape(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _url(identifier=None, *, create=False):
    if create:
        return _MANAGE + "?new=1"
    return _MANAGE + "?" + urlencode({"runbook": identifier}) if identifier else _MANAGE


def _link(href, label, *, primary=False):
    return '<a class="admin-button{}" href="{}">{}</a>'.format(
        " admin-primary" if primary else "", _escape(href), _escape(label),
    )


def _hidden(name, value):
    return '<input type="hidden" name="{}" value="{}">'.format(name, _escape(value))


def _field(name, title, value, hint, *, rows=None, code=False, required=False, kind="text", attrs=""):
    help_id = "runbook-editor-" + name + "-hint"
    common = 'name="{}" aria-describedby="{}"{}{}'.format(name, help_id, " required" if required else "", attrs)
    if rows:
        field = '<textarea {} rows="{}"{}>{}</textarea>'.format(
            common, rows, ' class="font-mono" spellcheck="false" autocapitalize="off"' if code else "", _escape(value),
        )
    else:
        field = '<input {} type="{}" value="{}">'.format(common, kind, _escape(value))
    return '<label class="admin-field"><span>{}</span>{}<span class="field-hint" id="{}">{}</span></label>'.format(
        _escape(title), field, help_id, _escape(hint),
    )


def _status(label, tone):
    return '<span class="admin-chip" data-tone="{}">{}</span>'.format(tone, _escape(label))


def _error(message):
    return '<p class="notice error" role="alert">{}</p>'.format(_escape(message)) if message else ""


def _domain_error(error, language):
    message = str(error)
    if language != "ru":
        return message
    if message in _ERROR_RU:
        return _ERROR_RU[message]
    parameter = re.fullmatch(r"parameter (\S+) (.+)", message)
    if parameter and parameter[2] in _PARAMETER_ERRORS_RU:
        return _PARAMETER_ERRORS_RU[parameter[2]].format(parameter[1])
    for prefix in ("unknown command parameter ", "unknown runbook parameter: "):
        if message.startswith(prefix):
            return 'Параметр «{}» отсутствует в схеме.'.format(message.removeprefix(prefix))
    if message.startswith(("invalid fields for parameter ", "minimum for ", "maximum for ")):
        return "Проверьте поля и числовые границы в схеме параметров."
    return "Проверьте данные регламента и повторите действие."


def _latest(record):
    versions = record["versions"]
    return record["draft"] or (versions[-1]["definition"] if versions else {})


def _defaults(record):
    source = _latest(record) if record else {}
    return {
        "runbook_id": record["id"] if record else "",
        "revision": record["revision"] if record else 0,
        "runbook_title": source.get("title", ""),
        "runbook_description": source.get("description", ""),
        "runbook_timeout": source.get("default_timeout", 60),
        "runbook_commands": json.dumps(source["commands"], indent=2, ensure_ascii=False) if source else "",
        "runbook_parameters": json.dumps(source.get("parameters", {}), indent=2, ensure_ascii=False),
        "sample_parameters": "{}",
    }


def _confirm_action(t, token, record, *, version=None):
    if version is None:
        action = "publish"
        caption = t("Publish draft", "Опубликовать черновик")
        prompt = t("Publish the saved draft as a new version for future runs.",
                   "Опубликуйте сохранённый черновик как новую версию для следующих запусков.")
    else:
        action = "retire"
        caption = t("Retire v{}", "Отозвать v{}").format(version)
        prompt = t("Version {} will be unavailable for future execution.",
                   "Версия {} станет недоступна для последующих запусков.").format(version)
    return ('<details class="admin-disclosure" data-admin-dialog data-dialog-size="compact" data-title="{}">'
            '<summary class="admin-button{}">{}</summary><form class="admin-panel" method="post" action="{}">'
            '{}{}{}{}<p>{}</p><div class="admin-toolbar"><label><input type="checkbox" name="confirm" '
            'value="true" required> {}</label><button class="admin-button{}" type="submit">{}</button>'
            '</div></form></details>').format(
        _escape(caption), " admin-primary" if version is None else "", _escape(caption), _escape(_url(record["id"])),
        _hidden("csrf_token", token), _hidden("revision", record["revision"]), _hidden("action", action),
        _hidden("version", version) if version is not None else "", _escape(prompt),
        t("Confirm change", "Подтверждаю изменение"), " admin-primary" if version is None else " button-danger",
        _escape(caption),
    )


def _history(t, record, token):
    rows = []
    for version in reversed(record["versions"]):
        number = version["version"]
        if version.get("retired_at") is not None:
            status = _status(t("Retired", "Отозвана"), "danger")
            action = "—"
        else:
            status = (_status(t("Current", "Текущая"), "positive") if number == record["active_version"]
                      else _status(t("Previous version", "Предыдущая"), "info"))
            action = _confirm_action(t, token, record, version=number)
        published = datetime.fromtimestamp(version["published_at"], timezone.utc)
        date = '<time datetime="{}">{}</time>'.format(published.isoformat(), published.strftime("%Y-%m-%d %H:%M UTC"))
        rows.append('<tr><th scope="row"><code>v{}</code></th><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            number, status, date, _escape(version["published_by"]), action,
        ))
    if not rows:
        return ""
    headings = (t("Version", "Версия"), t("Status", "Состояние"), t("Published", "Опубликована"),
                t("Published by", "Кто опубликовал"), t("Actions", "Действия"))
    return ('<section class="admin-panel"><h2>{}</h2><p class="admin-muted">{}</p><div class="table-wrap">'
            '<table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div></section>').format(
        t("Version history", "История версий"),
        t("New runs use the current version. Queued work keeps its version until that version is retired.",
          "Новые запуски используют текущую версию. Задания в очереди сохраняют свою версию. Отзыв блокирует её дальнейшее выполнение."),
        "".join('<th scope="col">{}</th>'.format(title) for title in headings), "".join(rows),
    )


def _directory(t, records):
    if not records:
        return admin_empty(t("No custom runbooks yet.", "Пользовательских регламентов пока нет."))
    rows = []
    for record in records:
        identifier = record["id"]
        active = record["active_version"]
        version = ('<code>v{}</code>'.format(active) if active is not None
                   else t("No active version", "Без активной версии"))
        draft = _status(t("Draft saved", "Есть черновик"), "info") if record["draft"] else "—"
        rows.append('<tr><th scope="row"><a href="{}" data-i18n="off">{}</a><small class="admin-meta"><code>{}</code></small>'
                    '</th><td>{}</td><td>{}</td></tr>'.format(
                        _escape(_url(identifier)), _escape(_latest(record).get("title") or identifier),
                        _escape(identifier), version, draft,
                    ))
    return ('<div class="table-wrap"><table><thead><tr><th scope="col">{}</th><th scope="col">{}</th>'
            '<th scope="col">{}</th></tr></thead><tbody>{}</tbody></table></div>').format(
        t("Runbook", "Регламент"), t("Active version", "Активная версия"), t("Draft", "Черновик"), "".join(rows),
    )


def _editor(t, config, record, values, token, preview, preview_open):
    fields = ""
    if record is None:
        fields += _field("runbook_id", t("Runbook ID", "ID регламента"), values["runbook_id"],
                         t("Start with a lowercase letter. You can also use digits and hyphens, as in rotate-api-logs.",
                           "Начните со строчной латинской буквы. Можно добавлять цифры и дефисы, как в rotate-api-logs."),
                         required=True, attrs=' maxlength="64" pattern="[a-z][a-z0-9\\-]*" autocapitalize="off" spellcheck="false"')
    fields += _field("runbook_title", t("Name", "Название"), values["runbook_title"],
                     t("This name appears in the runbook catalog.", "Название видно в каталоге регламентов."),
                     required=True, attrs=' maxlength="120"')
    fields += _field("runbook_timeout", t("Timeout, seconds", "Таймаут, с"), values["runbook_timeout"],
                     t("Default time limit for execution on one server.", "Ограничение времени на одном сервере по умолчанию."),
                     kind="number", required=True, attrs=' min="1" max="{}"'.format(
                         int(config.get("command_execution", {}).get("max_timeout", 900)),
                     ))
    summary = _field("runbook_description", t("Description", "Описание"), values["runbook_description"],
                     t("Explain when to use the runbook and what it changes.", "Опишите, когда запускать регламент и что он меняет."),
                     rows=3, attrs=' maxlength="1000"')
    command = _field("runbook_commands", t("Commands (JSON)", "Команды (JSON)"), values["runbook_commands"],
                     t('Enter a list of argument arrays. Use an absolute executable path, for example [["/usr/bin/id", "-u"]].',
                       'Укажите список массивов аргументов. Используйте абсолютный путь к программе, например [["/usr/bin/id", "-u"]].'),
                     required=True, rows=6, code=True)
    parameters = _field("runbook_parameters", t("Parameter schema (JSON)", "Схема параметров (JSON)"),
                        values["runbook_parameters"],
                        t('For an argument such as {service}, define {"service":{"type":"string","required":true}}. Use {} for no parameters.',
                          'Для аргумента вида {service} задайте {"service":{"type":"string","required":true}}. Если параметров нет, укажите {}.'),
                        rows=6, code=True)
    sample = _field("sample_parameters", t("Sample values (JSON)", "Пример значений (JSON)"), values["sample_parameters"],
                    t('For example {"service":"nginx.service"}. Preview displays the command without running it.',
                      'Например, {"service":"nginx.service"}. Предпросмотр покажет команду без запуска.'), rows=3, code=True)
    rendered = ('<pre><code>{}</code></pre>'.format(_escape(preview["command"])) if preview else "")
    publication = ""
    if record and record["draft"]:
        publication = '<div class="admin-actions">{}{}</div>'.format(
            _status(t("Draft saved", "Черновик сохранён"), "info"), _confirm_action(t, token, record),
        )
    return ('<section class="admin-panel"><header class="admin-heading"><div><h2>{}</h2>{}</div>{}</header>'
            '<form method="post" action="{}">{}{}<fieldset><legend>{}</legend><div class="admin-fields">{}</div>'
            '<div class="admin-fields">{}</div></fieldset>'
            '<fieldset><legend>{}</legend><div class="admin-fields">{}{}</div></fieldset>'
            '<div class="admin-toolbar"><button class="admin-button admin-primary" type="submit" name="action" value="save_draft">{}</button>{}</div>'
            '<details class="admin-disclosure"{}><summary>{}</summary><div class="admin-fields">{}</div><button class="admin-button" type="submit" '
            'name="action" value="preview">{}</button>{}</details>'
            '</form></section>').format(
        t("Edit draft", "Редактирование черновика") if record else t("New runbook", "Новый регламент"),
        '<code>{}</code>'.format(_escape(record["id"])) if record else "", publication,
        _escape(_url(record["id"]) if record else _url(create=True)), _hidden("csrf_token", token),
        _hidden("revision", values["revision"]), t("Details", "Сведения"), fields, summary,
        t("Commands and parameters", "Команды и параметры"), command, parameters,
        t("Save draft", "Сохранить черновик"), _link(_MANAGE, t("Back to list", "К списку")),
        " open" if preview_open else "",
        t("Preview command", "Предпросмотр команды"), sample,
        t("Show command", "Показать команду"), rendered,
    )


def _render(t, config, records, record, values, token, error, preview, preview_open):
    actions = _link(_CATALOG, t("Runbook catalog", "Каталог регламентов"))
    if values is None:
        actions += _link(_url(create=True), t("New runbook", "Новый регламент"), primary=True)
    heading = admin_heading(t("Manage runbooks", "Управление регламентами"),
                            t("Create drafts and publish versions of custom runbooks.",
                              "Создавайте черновики и публикуйте версии пользовательских регламентов."), actions)
    runbooks = config.get("runbooks") or {}
    if not runbooks.get("enabled"):
        operational = t("Runbook execution is disabled. You can still prepare and publish versions.",
                        "Запуск регламентов отключён. Черновики и публикация доступны.")
    elif not (runbooks.get("operational") or {}).get("enabled"):
        operational = t("Operational execution is disabled. You can prepare and publish versions. Running them requires enabling the operational class.",
                        "Запуск операционных регламентов отключён. Черновики и публикация доступны. Для запуска нужно включить операционный класс.")
    else:
        operational = t("Custom runbooks are operational. Execution requires an allowed group and the operate permission on the target.",
                        "Пользовательские регламенты относятся к операционным. Для запуска нужны разрешённая группа и право operate на целевом сервере.")
    if values is None:
        content = _directory(t, records)
    else:
        content = _editor(t, config, record, values, token, preview, preview_open)
        if record:
            content += _history(t, record, token)
    return '<div class="admin-page">{}<p class="notice">{}</p>{}{}</div>'.format(
        heading, _escape(operational), _error(error), content,
    )


def _json_field(value, label, t):
    try:
        return json.loads(value)
    except (ValueError, RecursionError) as exc:
        raise ValueError(t("{} must contain valid JSON.", "Проверьте синтаксис JSON в поле «{}».").format(label)) from exc


def _definition(config, values, t):
    try:
        timeout = int(values["runbook_timeout"])
    except ValueError:
        timeout = 0
    maximum = int(config.get("command_execution", {}).get("max_timeout", 900))
    if not 1 <= timeout <= maximum:
        raise ValueError(t("Enter a timeout between 1 and {} seconds.", "Укажите таймаут от 1 до {} с.").format(maximum))
    return {
        "title": values["runbook_title"], "description": values["runbook_description"], "default_timeout": timeout,
        "commands": _json_field(values["runbook_commands"], t("Commands", "Команды"), t),
        "parameters": _json_field(values["runbook_parameters"] or "{}", t("Parameter schema", "Схема параметров"), t),
    }


def register_runbook_admin(app, config, *, require_admin, store_factory, csrf_token, validate_csrf,
                           require_confirmation, audit_admin, render_page, locale):
    from isolate_runbook_catalog import (
        RunbookConflict, get_custom_runbook, list_custom_runbooks, preview_runbook_draft,
        publish_runbook, retire_runbook, save_runbook_draft,
    )
    from isolate_runbooks import RunbookError

    @app.route(_MANAGE, methods=["GET", "POST"])
    def manage_runbooks():
        admin = require_admin()
        if not isinstance(admin, dict):
            return admin
        if request.method == "POST":
            validate_csrf()
        language = locale()
        t = lambda en, ru: ru if language == "ru" else en
        store = store_factory()
        identifier = request.args.get("runbook")
        try:
            record = get_custom_runbook(store, identifier) if identifier else None
        except RunbookError:
            abort(404)
        if identifier and record is None:
            abort(404)
        creating = not identifier and request.args.get("new") == "1"
        values = _defaults(record) if identifier or creating else None
        message = ""
        preview = None
        preview_open = False
        status = 200
        if request.method == "POST":
            action = request.form.get("action")
            if values is None or action not in ("save_draft", "preview", "publish", "retire"):
                abort(400)
            revision = request.form.get("revision", "")
            actor = admin.get("username") or admin.get("keycloak_sub")
            target = identifier or request.form.get("runbook_id", "").strip()
            preview_open = action == "preview"
            try:
                if action in ("save_draft", "preview"):
                    values = {name: request.form.get(name, value) for name, value in values.items()}
                    values["revision"] = revision
                    definition = _definition(config, values, t)
                    if action == "preview":
                        sample = _json_field(values["sample_parameters"] or "{}", t("Sample values", "Пример значений"), t)
                        preview = preview_runbook_draft(definition, sample)
                    else:
                        result = save_runbook_draft(store, target, definition, actor=actor, expected_revision=revision)
                else:
                    if record is None:
                        abort(404)
                    if request.form.get("confirm") != "true":
                        raise ValueError(t("Confirm the change before continuing.", "Подтвердите изменение перед продолжением."))
                    require_confirmation()
                    if action == "publish":
                        result = publish_runbook(store, target, actor=actor, expected_revision=revision)
                    else:
                        version = request.form.get("version", "")
                        if not re.fullmatch(r"[1-9][0-9]?", version):
                            raise ValueError(t("Select a published version.", "Выберите опубликованную версию."))
                        result = retire_runbook(store, target, actor=actor, expected_revision=revision,
                                                version=version)
            except RunbookConflict:
                message = t("This runbook changed. Reopen it from the list before saving your changes.",
                            "Этот регламент уже изменился. Откройте его из списка и перенесите изменения в актуальную версию.")
                status = 409
            except RunbookError as exc:
                message = _domain_error(exc, language)
                status = 400
            except ValueError as exc:
                message = str(exc)
                status = 400
            if action != "preview":
                details = {"runbook_id": target[:128]}
                if status == 200:
                    details["revision"] = result["revision"]
                    if action == "publish":
                        details["version"] = result["active_version"]
                    elif action == "retire":
                        details["version"] = int(version)
                audit_admin("runbook_" + action, admin, "applied" if status == 200 else "denied", details)
                if status == 200:
                    return redirect(_url(target), code=303)
        records = list_custom_runbooks(store) if values is None else ()
        body = _render(t, config, records, record, values, csrf_token(), message, preview, preview_open)
        response = make_response(render_page(t("Manage runbooks", "Управление регламентами"), body), status)
        response.headers["Cache-Control"] = "no-store"
        return response
