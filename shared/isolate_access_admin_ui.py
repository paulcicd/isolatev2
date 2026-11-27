"""Server-rendered access administration views."""

import html
import json
from urllib.parse import quote, urlencode

from isolate_admin_ui import admin_heading as _heading
from isolate_ui_icons import icon


def _copy(locale):
    return lambda en, ru: ru if locale == "ru" else en


def _escape(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _url(path, **values):
    query = urlencode({key: value for key, value in values.items() if value not in (None, "")})
    return _escape(path + ("?" + query if query else ""))


def _button(label, href=None, *, primary=False, glyph=None, dialog_id=None):
    content = (icon(glyph) if glyph else "") + _escape(label)
    classes = "admin-button" + (" admin-primary" if primary else "")
    if href:
        dialog = ' data-open-dialog="{}"'.format(_escape(dialog_id)) if dialog_id else ""
        return '<a class="{}" href="{}"{}>{}</a>'.format(classes, href, dialog, content)
    return '<button class="{}">{}</button>'.format(classes, content)


def _tabs(label, current, entries):
    links = "".join('<a href="{}"{}>{}</a>'.format(url, ' aria-current="page"' if key == current else "", _escape(title))
                    for key, title, url in entries)
    return '<nav class="admin-tabs" aria-label="{}">{}</nav>'.format(_escape(label), links)


def _chip(content, tone="info"):
    return '<span class="admin-chip" data-tone="{}">{}</span>'.format(tone, _escape(content))


def _opening(title, shortcode, *, opened=False):
    return '<details class="admin-disclosure"{}><summary>{}</summary>{}</details>'.format(
        " open" if opened else "", _escape(title), shortcode
    )


def _rule_dialog(title, body, *, editor_id=None, opened=False, summary=None):
    attrs = (' id="{}"{}'.format(_escape(editor_id), " open" if opened else " hidden") if editor_id
             else ' data-dialog-size="compact"')
    return ('<details class="admin-disclosure access-rule-editor" data-admin-dialog data-title="{}"{}>'
            '<summary class="admin-button">{}</summary>{}</details>').format(
        _escape(title), attrs, _escape(summary or title), body,
    )


def _export(t, kind):
    return '<details class="admin-disclosure access-export"><summary class="admin-button">{}</summary><div class="admin-panel">{}</div></details>'.format(
        _escape(t("Export", "Выгрузить")),
        "".join(_button(fmt, _url("/export/" + kind, format=fmt.lower())) for fmt in ("CSV", "JSON")),
    )


def _table(t, headers, rows, *, selected=None):
    if not rows:
        return '<div class="admin-panel admin-empty">{}</div>'.format(_escape(t("No results", "Нет результатов")))
    body = "".join('<tr{}>{}</tr>'.format(' class="admin-selected"' if index == selected else "",
                                          "".join("<td>{}</td>".format(cell) for cell in row))
                   for index, row in enumerate(rows))
    columns = "".join('<th scope="col">{}</th>'.format(_escape(title)) for title in headers)
    return '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(columns, body)


def _terms(pairs):
    return '<dl class="key-value">{}</dl>'.format("".join(
        "<dt>{}</dt><dd>{}</dd>".format(_escape(label), _escape(value if value not in (None, "") else "—"))
        for label, value in pairs))


def _list(values):
    return ", ".join(str(value) for value in (values or []))


def _field(label, widget):
    return '<label><span>{}</span>{}</label>'.format(_escape(label), widget)


def _hidden(name, value):
    return '<input type="hidden" name="{}" value="{}">'.format(name, _escape(value))


def _input(name, value="", *, kind="text", attrs=""):
    return '<input type="{}" name="{}" value="{}"{}>'.format(kind, name, _escape(value), attrs)


def _select(name, selected, choices):
    return '<select name="{}">{}</select>'.format(name, "".join(
        '<option value="{}"{}>{}</option>'.format(_escape(value), " selected" if value == selected else "", _escape(label))
        for value, label in choices))


def _check(name, label, checked=False, required=False):
    return '<label class="access-check"><input type="checkbox" name="{}" value="true"{}{}><span>{}</span></label>'.format(
        name, " checked" if checked else "", " required" if required else "", _escape(label)
    )


def _search(t, name, query, label):
    return _field(label, _input(name, query, kind="search"))


def _post(token, action="", fields="", footer="", attrs=""):
    return '<form method="post" class="access-form"{}>{}{}<div class="admin-fields">{}</div><div class="admin-toolbar access-submit">{}</div></form>'.format(
        attrs, _hidden("csrf_token", token), _hidden("action", action) if action else "", fields, footer
    )


def _submit(t, button, *, confirm=True, danger=False):
    return (_check("confirm", t("Confirm change", "Подтверждаю изменение"), required=True) if confirm else "") + (
        '<button class="{}">{}</button>'.format("button-danger" if danger else "admin-button admin-primary", _escape(button)))


def _subjects(t):
    return (("group", t("Group", "Группа")), ("user", t("User", "Пользователь")), ("role", t("Role", "Роль")))


def _selectors(t):
    return (("project", t("Project", "Проект")), ("project_set", t("Project set", "Набор проектов")),
            ("project_glob", t("Project pattern", "Шаблон проекта")))


def _sudo(t):
    return (("none", t("No sudo", "Без sudo")), ("sudo-i", "sudo -i"))


def _selector(rule):
    return next((key for key in ("project", "project_set", "project_glob") if rule.get(key)), "project")


def _matches(query, *values):
    return not query or any(query in str(item or "").casefold() for item in values)


def _role(t, grant):
    return dict(_subjects(t)).get(grant.get("subject"), grant.get("subject"))


def _grant_source(grant):
    if grant.get("managed_by") == "access_package":
        return "package"
    return "temporary" if grant.get("temporary") else "direct"


def _grant_editor(t, csrf, grant, attrs):
    selector = _selector(grant)
    fields = "".join((
        _field(t("Subject type", "Тип субъекта"), _select("subject", grant.get("subject", "group"), _subjects(t))),
        _field(t("Subject name", "Имя субъекта"), _input("name", grant.get("name"), attrs=" required")),
        _field(t("Scope type", "Тип области"), _select("selector_type", selector, _selectors(t))),
        _field(t("Scope", "Область доступа"), _input("selector_value", grant.get(selector), attrs=" required")),
        _field(t("Host ID (optional)", "ID сервера (необязательно)"), _input("host", grant.get("host"))),
        _field(t("SSH account", "Учётная запись SSH"), _input("remote_user", grant.get("remote_user"), attrs=" required")),
        _field(t("Privilege elevation", "Повышение привилегий"), _select("sudo_mode", grant.get("sudo_mode"), _sudo(t))),
        _field(t("Allowed actions", "Разрешённые действия"), _input("allowed_actions", _list(grant.get("allowed_actions") or ["ssh"]))),
    ))
    return _post(csrf, "grant_save", _hidden("id", grant.get("id")) + fields,
                 _submit(t, t("Save rule", "Сохранить правило")), attrs)


def _project_set_editor(t, csrf, record, attrs, *, editing):
    fields = "".join((
        _field(t("Project set name", "Название набора"), _input("name", record.get("name"), attrs=" required")),
        _field(t("Projects", "Проекты"), _input("projects", _list(record.get("projects")))),
        _field(t("Project patterns", "Шаблоны проектов"), _input("project_globs", _list(record.get("project_globs")))),
    ))
    return _post(csrf, "project_set_save", _hidden("editor", "edit" if editing else "new") + fields,
                 _submit(t, t("Save set", "Сохранить набор")), attrs)


def _bulk(t, csrf, *, project_sets=False):
    mode = _field(t("Change", "Действие"), _select("mode", "", (("add", t("Add", "Добавить")), ("remove", t("Remove", "Удалить")))))
    if project_sets:
        fields = (
            _field(t("Set names, separated by commas", "Названия наборов через запятую"), _input("names", attrs=" required"))
            + _field(t("Member type", "Тип записи"), _select("member_type", "", (("projects", t("Projects", "Проекты")), ("project_globs", t("Project patterns", "Шаблоны проектов")))))
            + mode + _field(t("Projects or patterns, separated by commas", "Проекты или шаблоны через запятую"), _input("values", attrs=" required"))
        )
        action = "project_set_bulk_members"
    else:
        fields = (
            _field(t("Rule IDs, separated by commas", "ID правил через запятую"), _input("ids", attrs=" required"))
            + mode + _field(t("Capability", "Разрешение"), _input("allowed_action", attrs=' required placeholder="runbook"'))
        )
        action = "grant_bulk_action"
    return _opening(t("Bulk changes", "Массовые изменения"), _post(csrf, action, fields, _submit(t, t("Apply", "Применить"))))


def render_grants(grants, project_sets, params, csrf, locale, *, read_only=False, submitted=None):
    t = _copy(locale)
    sets_mode = params.get("view") == "sets" or bool(params.get("edit_set"))
    base = {"view": "sets"} if sets_mode else {}
    query = params.get("q", "")
    if query:
        base["q"] = query
    search = query.strip().casefold()
    source = params.get("source", "") if not sets_mode else ""
    sources = {"direct": t("Direct rule", "Отдельное правило"), "package": t("Access package", "Из пакета"),
               "temporary": t("Temporary", "Временное")}
    if source in sources:
        base["source"] = source
    active = "sets" if sets_mode else "rules"
    tabs = _tabs(t("Access rules views", "Разделы правил доступа"), active, (
        ("rules", t("Rules", "Правила") + " · " + str(len(grants)), "/grants"),
        ("sets", t("Project sets", "Наборы проектов") + " · " + str(len(project_sets)), _url("/grants", view="sets")),
    ))
    add_title = t("Add project set", "Создать набор") if sets_mode else t("Add rule", "Добавить правило")
    add_link = _url("/grants", **base, editor="new") + "#access-rule-add"
    create = "" if read_only else _button(add_title, add_link, primary=True, dialog_id="access-rule-add")
    heading = _heading(t("Access Rules", "Правила доступа"),
                       t("Manage who can connect to resources and what they can do.", "Управляйте доступом к ресурсам и разрешёнными действиями."),
                       _export(t, "grants") + create)
    filters = _hidden("view", "sets") if sets_mode else ""
    filters += _search(t, "q", query, t("Search project sets", "Поиск по наборам проектов") if sets_mode else t("Subject, project, host or rule ID", "Субъект, проект, сервер или ID правила"))
    if not sets_mode:
        filters += _field(t("Source", "Источник"), _select("source", source, [("", t("All sources", "Все источники")), *sources.items()]))
    filter_bar = '<form class="inline admin-toolbar" action="/grants">{}</form>'.format(filters + _button(t("Filter", "Найти")))
    selected_id = str(params.get("edit_set" if sets_mode else "edit_grant") or params.get("selected") or "")
    records = project_sets if sets_mode else grants
    key = "name" if sets_mode else "id"
    if sets_mode:
        visible = [item for item in records if _matches(search, item.get("name"), _list(item.get("projects")), _list(item.get("project_globs")))]
    else:
        visible = [item for item in records if (source not in sources or _grant_source(item) == source)
                   and _matches(search, item.get("name"), item.get("id"), item.get(_selector(item)), item.get("host"), item.get("remote_user"))]
    selected = next((item for item in records if str(item.get(key, "")) == selected_id), None)
    if not selected and visible:
        selected = visible[0]
    rows = []
    for record in visible:
        label = _escape(record.get("name"))
        link = '<a href="{}">{}</a>'.format(_url("/grants", **base, selected=record[key]), label)
        if sets_mode:
            rows.append((link, _escape(len(record.get("projects") or [])), _escape(len(record.get("project_globs") or []))))
        else:
            subject = link + '<small class="admin-meta">{}</small>'.format(_escape(_role(t, record)))
            scope = _escape(record.get(_selector(record))) + '<small class="admin-meta">{}</small>'.format(
                _escape(dict(_selectors(t))[_selector(record)]))
            actions = " ".join(_chip(item) for item in (record.get("allowed_actions") or ["ssh"]))
            rows.append((subject, scope, actions, _escape(sources[_grant_source(record)])))
    headers = ((t("Project set", "Набор проектов"), t("Projects", "Проекты"), t("Patterns", "Шаблоны")) if sets_mode else
               (t("Subject", "Субъект"), t("Scope", "Область доступа"), t("Actions", "Действия"), t("Source", "Источник")))
    table = _table(t, headers, rows, selected=visible.index(selected) if selected in visible else None)
    edit_key = "edit_set" if sets_mode else "edit_grant"
    expected_action = "project_set_save" if sets_mode else "grant_save"
    draft = submitted if submitted and submitted.get("action") == expected_action else None
    can_edit = not read_only and bool(selected) and (sets_mode or _grant_source(selected) != "package")
    draft_values = None
    if draft:
        if sets_mode:
            draft_values = {"name": draft.get("name"), "projects": [draft.get("projects")], "project_globs": [draft.get("project_globs")]}
        else:
            field_names = ("id", "subject", "name", "host", "remote_user", "sudo_mode")
            draft_values = {name: draft.get(name) for name in field_names}
            selector = draft.get("selector_type")
            if selector in dict(_selectors(t)):
                draft_values[selector] = draft.get("selector_value")
            draft_values["allowed_actions"] = [draft.get("allowed_actions") or "ssh"]
    editing = bool(params.get(edit_key))
    if draft:
        editing = (draft.get("editor") == "edit" or (not draft.get("editor") and editing)) if sets_mode else bool(draft.get("id"))
    creating = not editing and (params.get("editor") == "new" or draft is not None)
    editors = ""
    if not read_only:
        add_values = draft_values if creating and draft_values is not None else {}
        form_target = ' action="{}"'.format(_url("/grants", **base, selected=selected[key] if selected else None))
        add_form = (_project_set_editor(t, csrf, add_values, form_target, editing=False) if sets_mode
                    else _grant_editor(t, csrf, add_values, form_target))
        editors = _rule_dialog(add_title, add_form, editor_id="access-rule-add", opened=creating)
    if selected:
        subject_type = _escape(_role(t, selected)) if not sets_mode else ""
        inspector = '<small class="admin-meta">{}</small><h2>{}</h2>'.format(subject_type, _escape(selected["name"]))
        if sets_mode:
            inspector += _terms(((t("Projects", "Проекты"), _list(selected.get("projects"))),
                                 (t("Project patterns", "Шаблоны проектов"), _list(selected.get("project_globs")))))
        else:
            selector = _selector(selected)
            inspector += _terms(((t("Rule ID", "ID правила"), selected["id"]),
                                 (dict(_selectors(t))[selector], selected.get(selector)),
                                 (t("Host restriction", "Ограничение по серверу"), selected.get("host") or t("All in scope", "Все в области доступа")),
                                 (t("SSH account", "Учётная запись SSH"), selected.get("remote_user")),
                                 (t("Privilege elevation", "Повышение привилегий"), dict(_sudo(t)).get(selected.get("sudo_mode") or "none", selected.get("sudo_mode"))),
                                 (t("Allowed actions", "Разрешённые действия"), _list(selected.get("allowed_actions") or ["ssh"])),
                                 (t("Source", "Источник"), sources[_grant_source(selected)])))
        if can_edit:
            identifier = selected[key]
            edit_title = t("Edit project set", "Редактировать набор") if sets_mode else t("Edit rule", "Редактировать правило")
            edit_values = draft_values if editing and draft_values is not None else selected
            edit_form = (_project_set_editor(t, csrf, edit_values, form_target, editing=True) if sets_mode
                         else _grant_editor(t, csrf, edit_values, form_target))
            editors += _rule_dialog(edit_title, edit_form, editor_id="access-rule-edit", opened=editing)
            edit_link = _url("/grants", **base, **{edit_key: identifier}) + "#access-rule-edit"
            remove_action = "project_set_remove" if sets_mode else "grant_remove"
            remove_title = t("Remove project set", "Удалить набор") if sets_mode else t("Remove rule", "Удалить правило")
            confirm = '<p>{}</p>'.format(_escape(t('Remove “{}”?', 'Удалить «{}»?').format(selected["name"])))
            remove = _post(csrf, remove_action, _hidden(key, identifier), _submit(t, t("Remove", "Удалить"), danger=True), form_target)
            inspector += '<div class="admin-actions access-rule-actions">{}{}</div>'.format(
                _button(t("Edit", "Редактировать"), edit_link, dialog_id="access-rule-edit"),
                _rule_dialog(remove_title, confirm + remove, summary=t("Remove", "Удалить")),
            )
        elif not sets_mode and _grant_source(selected) == "package" and selected.get("package_id"):
            inspector += _button(t("Open access package", "Открыть пакет доступа"),
                                 _url("/packages/" + quote(str(selected["package_id"]), safe="")))
    else:
        inspector = '<p class="admin-empty">{}</p>'.format(_escape(t("Select a row to see its details.", "Выберите строку, чтобы открыть подробности.")))
    notice = ('<p class="notice warning">{}</p>'.format(_escape(t("GitOps manages this policy. View only.", "Политикой управляет GitOps. Здесь она доступна для просмотра."))) if read_only else "")
    bulk = "" if read_only else _bulk(t, csrf, project_sets=sets_mode)
    return '<section class="admin-page access-admin">{}{}{}{}<div class="admin-split"><div>{}{}</div><aside class="admin-panel">{}</aside></div>{}</section>'.format(
        heading, notice, tabs, filter_bar, table, bulk, inspector, editors,
    )


def _package_path(identifier):
    return "/packages/" + quote(str(identifier), safe="")


def _package_state(t, package):
    if package.get("status") == "enabled":
        return _chip(t("Enabled", "Действует"), "positive")
    return _chip(t("Disabled", "Отключён"), "warning")


def _package_form(t, csrf, package=None, submitted=None):
    package = package or {}
    lifecycle = package.get("lifecycle") or {}
    approval = package.get("approval") or {}
    current = {
        "name": package.get("name"), "status": package.get("status") or "enabled",
        "description": package.get("description"),
        "access_json": json.dumps(package.get("access") or [], indent=2, sort_keys=True),
        "default_ttl": lifecycle.get("default_ttl"), "max_ttl": lifecycle.get("max_ttl"),
        "permanent_allowed": "true" if lifecycle.get("permanent_allowed") else "",
        "approval_required": "true" if approval.get("required") else "",
        "ticket_required": "true" if approval.get("ticket_required") else "",
        "admin_groups": _list(approval.get("admin_groups")),
        "minimum_approvals": approval.get("minimum_approvals", 1),
    }
    if submitted:
        for key in current:
            current[key] = submitted.get(key)
    heading = t("Edit package", "Редактировать пакет") if package else t("Create package", "Создать пакет")
    fields = "".join((
        _field(t("Package name", "Название пакета"), _input("name", current["name"], attrs=" required")),
        _field(t("Status", "Состояние"), _select("status", current["status"], (
            ("enabled", t("Enabled", "Действует")), ("disabled", t("Disabled", "Отключён"))))),
        _field(t("Description", "Описание"), _input("description", current["description"])),
    ))
    lifetime = "".join((
        _field(t("Default lifetime", "Срок по умолчанию"), _input("default_ttl", current["default_ttl"], attrs=' placeholder="7d"')),
        _field(t("Maximum lifetime", "Максимальный срок"), _input("max_ttl", current["max_ttl"], attrs=' placeholder="30d"')),
        _check("permanent_allowed", t("Allow permanent assignments", "Разрешать бессрочные назначения"), current["permanent_allowed"] == "true"),
        _field(t("Approver groups", "Группы согласующих"), _input("admin_groups", current["admin_groups"])),
        _field(t("Minimum approvals", "Минимум согласований"), _input("minimum_approvals", current["minimum_approvals"], kind="number", attrs=' min="1"')),
        _check("approval_required", t("Require approval", "Требовать согласование"), current["approval_required"] == "true"),
        _check("ticket_required", t("Require a ticket", "Требовать номер заявки"), current["ticket_required"] == "true"),
    ))
    rules = ('<div class="access-package-rules admin-fields" data-package-rules>'
             '<div data-package-builder hidden></div><label class="access-package-json"><span>{}</span>'
             '<textarea name="access_json" rows="9" required>{}</textarea></label>{}</div>').format(
        _escape(t("Access rules (JSON)", "Правила доступа (JSON)")),
        _escape(current["access_json"]),
        '<template data-package-rule-template><fieldset class="admin-panel"><legend>{}</legend><div class="admin-fields">{}</div>'
        '<button type="button" class="admin-button" data-package-remove>{}</button></fieldset></template>'.format(
            _escape(t("Access rule", "Правило доступа")),
            _field(t("Rule ID (optional)", "ID правила (необязательно)"), _input("id"))
            + _field(t("Scope type", "Тип области"), _select("scope_type", "project", _selectors(t)))
            + _field(t("Scope", "Область доступа"), _input("scope_value", attrs=" required"))
            + _field(t("Host ID (optional)", "ID сервера (необязательно)"), _input("host"))
            + _field(t("SSH account", "Учётная запись SSH"), _input("remote_user", attrs=" required"))
            + _field(t("Privilege elevation", "Повышение привилегий"), _select("sudo_mode", "none", _sudo(t)))
            + _field(t("Actions, separated by commas", "Действия через запятую"), _input("allowed_actions", "ssh")),
            _escape(t("Remove rule", "Удалить правило")),
        ) + '<template data-package-builder-controls><div class="admin-toolbar">'
            '<button type="button" class="admin-button" data-package-add>{}</button>'
            '<button type="button" class="admin-button" data-package-toggle>{}</button></div><div data-package-rule-list></div>'
            '</template>'.format(_escape(t("Add access rule", "Добавить правило доступа")),
                                 _escape(t("Edit JSON", "Редактировать JSON")))
    )
    if package:
        confirmation = _check("confirm", t("Confirm revision", "Подтверждаю применение"))
        preview = '<button class="admin-button" name="action" value="preview">{}</button>'.format(_escape(t("Preview changes", "Проверить изменения")))
        save = '<button class="admin-button admin-primary" name="action" value="update">{}</button>'.format(_escape(t("Apply revision", "Применить ревизию")))
        footer = preview + confirmation + save
        action = ""
    else:
        footer = _submit(t, heading)
        action = "create"
    return ('<section class="admin-panel access-package-editor"><h2>{}</h2><form method="post" data-package-form '
            'data-json-label="{}" data-visual-label="{}">{}{}{}<div class="admin-fields">{}</div><h3>{}</h3>{}'
            '{}<div class="admin-toolbar access-submit">{}</div></form><script src="/static/access-package-editor.js" defer></script></section>').format(
        _escape(heading), _escape(t("Edit JSON", "Редактировать JSON")), _escape(t("Back to rule editor", "Открыть редактор правил")),
        _hidden("csrf_token", csrf), _hidden("expected_revision", submitted.get("expected_revision") or package["revision"] if submitted else package["revision"]) if package else "",
        _hidden("action", action) if action else "", fields, _escape(t("Access rules", "Правила доступа")),
        rules, _opening(t("Lifetime and approval", "Срок действия и согласование"), '<div class="admin-fields">{}</div>'.format(lifetime), opened=bool(submitted)), footer,
    )


def _assignment_form(t, csrf, packages, selected, submitted):
    assignment = submitted if submitted and submitted.get("action") == "assign" else {}
    approval = (selected or {}).get("approval") or {}
    package_field = _select("package", str(assignment.get("package") or (selected or {}).get("id") or ""), (
        ("", t("Choose a package", "Выберите пакет")), *((str(package["id"]), package["name"]) for package in packages),
    ))
    fields = "".join((
        _field(t("Package", "Пакет"), package_field.replace("<select ", "<select required ", 1)),
        _field(t("Subject type", "Тип субъекта"), _select("subject", assignment.get("subject"), _subjects(t))),
        _field(t("Subject names, separated by commas", "Имена субъектов через запятую"), _input("name", assignment.get("name"), attrs=" required")),
        _field(t("Assignment lifetime", "Срок назначения"), _input("ttl", assignment.get("ttl"), attrs=' placeholder="7d"')),
        _field(t("Ticket", "Номер заявки"), _input("ticket", assignment.get("ticket"), attrs=" required" if approval.get("ticket_required") else "")),
        _check("permanent", t("Permanent", "Бессрочно"), assignment.get("permanent") == "true"),
    ))
    if selected and (int(approval.get("minimum_approvals") or 1) > 1 or selected.get("status") != "enabled"):
        return '<section class="admin-panel"><h2>{}</h2><p>{}</p></section>'.format(
            _escape(t("Assign package", "Назначить пакет")),
            _escape(t("Direct assignment is unavailable for this package. Check its status and approval requirements.",
                      "Для этого пакета прямое назначение недоступно. Проверьте состояние и требования к согласованию.")),
        )
    return '<section class="admin-panel"><h2>{}</h2>{}</section>'.format(
        _escape(t("Assign package", "Назначить пакет")),
        _post(csrf, "assign", fields, _submit(t, t("Assign access", "Назначить доступ"))),
    )


def render_packages(packages, assignments, params, csrf, locale, stamp, *, read_only=False, submitted=None):
    t = _copy(locale)
    by_id = {str(package["id"]): package for package in packages}
    action = submitted.get("action") if submitted else ""
    view = params.get("view")
    if view not in ("catalog", "assignments"):
        view = "assignments" if action in ("assign", "unassign") else "catalog"
    selected_id = str(params.get("package") or "")
    query = params.get("q", "")
    search = query.strip().casefold()
    heading = _heading(t("Access Packages", "Пакеты доступа"),
                       t("Group access rules and manage who has them.", "Объединяйте правила доступа и управляйте их назначениями."),
                       "" if read_only else _button(t("Create package", "Создать пакет"), _url("/packages", view="catalog", editor="new"), primary=True)
                       + _button(t("Assign package", "Назначить пакет"), _url("/packages", view="assignments", editor="assign")))
    tabs = _tabs(t("Package views", "Разделы пакетов доступа"), view, (
        ("catalog", t("Catalogue", "Каталог"), "/packages"),
        ("assignments", t("Assignments", "Назначения"), _url("/packages", view="assignments")),
    ))
    fields = _hidden("view", view) + _search(t, "q", query, t("Search packages or subjects", "Поиск по пакетам и субъектам"))
    if view == "assignments":
        choices = [("", t("All packages", "Все пакеты")), *((str(item["id"]), item["name"]) for item in packages)]
        fields += _field(t("Package", "Пакет"), _select("package", selected_id, choices))
    toolbar = '<form class="inline admin-toolbar" action="/packages">{}{}</form>'.format(fields, _button(t("Filter", "Найти")))
    editor = ""
    if view == "assignments":
        if not read_only and (params.get("editor") == "assign" or action == "assign"):
            editor = _assignment_form(t, csrf, packages, by_id.get(selected_id), submitted)
        headers = (t("Subject", "Субъект"), t("Package", "Пакет"), t("State", "Состояние"), t("Expires", "Действует до"), t("Ticket", "Заявка"), t("Actions", "Действия"))
        rows = []
        for record in assignments:
            if selected_id and str(record["package_id"]) != selected_id:
                continue
            if not _matches(search, record.get("name"), record.get("package_name"), record.get("id"), record.get("ticket")):
                continue
            revoke = "" if read_only else _opening(t("Revoke", "Отозвать"),
                _post(csrf, "unassign", _hidden("id", record["id"]), _submit(t, t("Revoke access", "Отозвать доступ"), danger=True)))
            active = record.get("status") == "active" and not record.get("expired")
            state = (t("Active", "Действует") if active else
                     t("Expired", "Истекло") if record.get("expired") else t("Revoked", "Отозвано"))
            subject = "<strong>{}</strong><small class=\"admin-meta\">{} · #{}</small>".format(
                _escape(record["name"]), _escape(_role(t, record)), _escape(record["id"]))
            rows.append((subject,
                         '<a href="{}">{}</a>'.format(_url(_package_path(record["package_id"])), _escape(record.get("package_name"))),
                         _chip(state, "positive" if active else "warning"),
                         _escape(stamp(record.get("expires_at")) or t("Permanent", "Бессрочно")),
                         _escape(record.get("ticket") or "—"), revoke if active else "—"))
    else:
        if not read_only and (params.get("editor") == "new" or action == "create"):
            editor = _package_form(t, csrf, submitted=submitted)
        headers = (t("Package", "Пакет"), t("Status", "Состояние"), t("Rules", "Правила"), t("Assignments", "Назначения"), t("Revision", "Ревизия"))
        live_counts = {}
        for record in assignments:
            if record.get("status") == "active" and not record.get("expired"):
                package_key = str(record.get("package_id"))
                live_counts[package_key] = live_counts.get(package_key, 0) + 1
        rows = []
        for package in packages:
            if not _matches(search, package.get("name"), package.get("description"), package.get("id")):
                continue
            package_link = '<a href="{}">{}</a><small class="admin-meta">{}</small>'.format(
                _url(_package_path(package["id"])), _escape(package["name"]), _escape(package.get("description") or ""))
            count = live_counts.get(str(package["id"]), 0)
            assignments_link = '<a href="{}">{}</a>'.format(
                _url("/packages", view="assignments", package=package["id"]), count)
            rows.append((package_link, _package_state(t, package), str(len(package.get("access") or [])),
                         assignments_link, _escape(package.get("revision"))))
    return '<section class="admin-page access-admin">{}{}{}{}{}</section>'.format(
        heading, tabs, toolbar, _table(t, headers, rows), editor
    )


def render_package_details(package, revisions, params, csrf, locale, stamp, *, preview=None, read_only=False, submitted=None):
    t = _copy(locale)
    path = _package_path(package["id"])
    views = (
        ("rules", t("Rules", "Правила")), ("conditions", t("Conditions", "Условия")),
        ("revisions", t("Revisions", "Ревизии")),
    )
    view = params.get("tab") or "rules"
    if view not in dict(views):
        view = "rules"
    editor = params.get("editor") == "true" or bool(submitted and submitted.get("action") in ("preview", "update"))
    tabs = _tabs(t("Package details", "Разделы пакета доступа"), view, [(key, title, _url(path, tab=key)) for key, title in views])
    lifecycle = package.get("lifecycle") or {}
    approval = package.get("approval") or {}
    policy_meta = _terms((
        (t("Revision", "Ревизия"), package["revision"]), (t("Updated by", "Кто изменил"), package.get("updated_by")),
        (t("Last updated", "Последнее изменение"), stamp(package.get("updated_at"))),
    ))
    actions = _button(t("Assignments", "Назначения"), _url("/packages", view="assignments", package=package["id"]))
    if not read_only:
        actions += _button(t("Edit", "Редактировать"), _url(path, tab=view, editor="true"), primary=True)
    body = ('<section class="admin-page access-admin"><p><a href="/packages">{}</a></p>{}{}'
            '<div class="admin-toolbar access-summary">{}</div>').format(
        _escape(t("Back to packages", "К пакетам доступа")),
        _heading(package["name"], package.get("description") or t("Access package", "Пакет доступа"), actions),
        tabs, _package_state(t, package) + '<span class="admin-meta">#{} · {} {}</span>'.format(_escape(package["id"]),
                _escape(t("Revision", "Ревизия")), _escape(package["revision"])),
    )
    if view == "rules":
        headers = (t("Rule", "Правило"), t("Scope", "Область доступа"), t("SSH account", "Учётная запись SSH"), t("Actions", "Действия"))
        rows = []
        for rule in package.get("access") or []:
            selector = _selector(rule)
            account = '<code>{}</code><small class="admin-meta">{}</small>'.format(_escape(rule.get("remote_user")),
                _escape(dict(_sudo(t)).get(rule.get("sudo_mode"), rule.get("sudo_mode"))))
            scope = "{}<small class=\"admin-meta\">{}</small>".format(_escape(rule.get(selector)),
                _escape(dict(_selectors(t))[selector] + ((" · " + t("Host", "Сервер") + " #" + str(rule["host"])) if rule.get("host") else "")))
            rows.append((_escape(rule.get("id")), scope, account, " ".join(_chip(item) for item in (rule.get("allowed_actions") or []))))
        body += _table(t, headers, rows)
    elif view == "conditions":
        yes, no = t("Yes", "Да"), t("No", "Нет")
        details = _terms((
            (t("Default lifetime", "Срок по умолчанию"), lifecycle.get("default_ttl")),
            (t("Maximum lifetime", "Максимальный срок"), lifecycle.get("max_ttl")),
            (t("Permanent access allowed", "Бессрочный доступ разрешён"), yes if lifecycle.get("permanent_allowed") else no),
            (t("Approval required", "Требуется согласование"), yes if approval.get("required") else no),
            (t("Approver groups", "Группы согласующих"), _list(approval.get("admin_groups"))),
            (t("Minimum approvals", "Минимум согласований"), approval.get("minimum_approvals")),
            (t("Ticket required", "Требуется номер заявки"), yes if approval.get("ticket_required") else no),
        ))
        body += '<div class="admin-split"><section class="admin-panel">{}</section><aside class="admin-panel">{}</aside></div>'.format(details, policy_meta)
    else:
        headers = (t("Revision", "Ревизия"), t("Status", "Состояние"), t("Author", "Автор"), t("Updated", "Дата изменения"),
                   t("Rollback source", "Исходная ревизия"), t("Action", "Действие"))
        rows = []
        for revision in revisions:
            action = ""
            if not read_only and revision["revision"] != package["revision"]:
                rollback = _post(csrf, "rollback", _hidden("revision", revision["revision"]) + _hidden("expected_revision", package["revision"]),
                                 _submit(t, t("Create rollback revision", "Создать ревизию отката"), danger=True))
                action = _opening(t("Roll back", "Откатить"), rollback)
            rows.append((_escape(revision["revision"]), _package_state(t, revision), _escape(revision.get("updated_by")), _escape(stamp(revision.get("updated_at"))),
                         _escape(revision.get("rolled_back_from") or "—"), action or "—"))
        body += _table(t, headers, rows)
    if preview is not None:
        counters = t("{} affected subjects · {} grant changes · revision {} → {}",
                     "Затронуто субъектов: {} · Изменений правил: {} · Ревизия {} → {}").format(
                    preview["affected_subjects"], preview["grant_change_count"], preview["from_revision"], preview["to_revision"])
        impacted = []
        for assignment in preview["assignments"]:
            impacted.append((
                _escape(assignment.get("assignment_id")), _escape(assignment.get("name")),
                _opening(t("Grant changes", "Изменения правил"), '<pre>{}</pre>'.format(_escape(json.dumps(assignment["grant_changes"], indent=2, sort_keys=True)))),
            ))
        body += '<section class="admin-panel"><h2>{}</h2><p>{}</p>{}</section>'.format(
            _escape(t("Preview changes", "Предварительный просмотр изменений")), _escape(counters),
            _table(t, (t("Assignment", "Назначение"), t("Subject", "Субъект"), t("Details", "Сведения")), impacted),
        )
    if editor and (not read_only or preview is not None):
        if read_only:
            return body + "</section>"
        body += _package_form(t, csrf, package, submitted=submitted)
    return body + "</section>"


def _matrix_access(t, cell):
    states = {
        "allowed": (t("Allowed", "Разрешено"), "positive"),
        "partial": (t("Partial access", "Частичный доступ"), "warning"),
        "mixed": (t("Different privileges", "Разные права"), "info"),
        "denied": (t("Denied", "Нет доступа"), "danger"),
    }
    label, tone = states[cell["state"]]
    return _chip(label, tone)


def _decision_summary(t, outcome):
    if not outcome.get("allowed"):
        return _chip(t("Denied", "Нет доступа"), "danger") + '<small class="admin-meta">{}</small>'.format(
            _escape(outcome.get("reason")))
    return _chip(t("Allowed", "Разрешено"), "positive") + _terms((
        (t("SSH account", "Учётная запись SSH"), outcome.get("remote_user")),
        (t("Privilege elevation", "Повышение привилегий"), dict(_sudo(t)).get(outcome.get("sudo_mode"), outcome.get("sudo_mode"))),
        (t("Actions", "Действия"), _list(outcome.get("allowed_actions"))),
        (t("Rule ID", "ID правила"), outcome.get("grant_id")),
    ))


def _matrix_preview(t, csrf, preview, draft):
    draft = draft or {}
    fields = "".join((
        _field(t("Subject type", "Тип субъекта"), _select("subject", draft.get("subject"), _subjects(t))),
        _field(t("Subject name", "Имя субъекта"), _input("name", draft.get("name"), attrs=" required")),
        _field(t("Scope type", "Тип области"), _select("selector_type", draft.get("selector_type"), _selectors(t))),
        _field(t("Scope", "Область доступа"), _input("selector_value", draft.get("selector_value"), attrs=" required")),
        _field(t("Host ID (optional)", "ID сервера (необязательно)"), _input("host", draft.get("host"))),
        _field(t("Replace rule ID (optional)", "ID заменяемого правила (необязательно)"), _input("replace_grant_id", draft.get("replace_grant_id"))),
        _field(t("SSH account", "Учётная запись SSH"), _input("remote_user", draft.get("remote_user"), attrs=" required")),
        _field(t("Privilege elevation", "Повышение привилегий"), _select("sudo_mode", draft.get("sudo_mode"), _sudo(t))),
        _field(t("Allowed actions", "Разрешённые действия"), _input("allowed_actions", draft.get("allowed_actions") or "ssh")),
    ))
    copy = t("See how a proposed rule affects SSH access. The policy stays unchanged.",
             "Сравните текущий доступ по SSH с доступом после пробного изменения. Политика при этом не меняется.")
    result = ""
    if preview is not None:
        totals = " ".join(_chip(label + " " + str(preview["counts"][key]), tone) for key, label, tone in (
            ("gained", t("Gained", "Появился доступ"), "positive"), ("lost", t("Lost", "Доступ потерян"), "danger"), ("changed", t("Changed", "Права изменились"), "warning")))
        rows = [(
            "<strong>{}</strong><small class=\"admin-meta\">{} · #{}</small>".format(
                _escape(item.get("server_name")), _escape(item.get("project")), _escape(item.get("host_id"))),
            _decision_summary(t, item["before"]), _decision_summary(t, item["after"]),
        ) for item in preview["impacts"]]
        result = ('<section class="admin-panel"><h2>{}</h2><div class="admin-toolbar">{}</div>{}</section>').format(
            _escape(t("Blast radius preview", "Результат оценки изменения")), totals,
            _table(t, (t("Server", "Сервер"), t("Before", "До"), t("After", "После")), rows),
        )
    return (result + '<section class="admin-panel"><h2>{}</h2><p>{}</p>{}</section>').format(
        _escape(t("Assess a change", "Оценить изменение")), _escape(copy),
        _post(csrf, fields=fields, footer=_submit(t, t("Preview", "Рассчитать"), confirm=False)),
    )


def _matrix_filters(t, fields, *, findings=False):
    return ('<form class="inline admin-toolbar matrix-filters{}" method="get" action="/policy/matrix">{}'
            '<button class="admin-button admin-primary" type="submit">{} {}</button></form>').format(
        " matrix-filters-findings" if findings else "", fields, icon("search"), _escape(t("Filter", "Найти")),
    )


def render_access_matrix(matrix, params, csrf, locale, *, preview=None, submitted=None):
    t = _copy(locale)
    path = "/policy/matrix"
    sort = params.get("view")
    view = "preview" if submitted is not None else (sort if sort in ("project", "subject", "findings", "preview") else "project")
    if params.get("finding") and sort is None and submitted is None:
        view = "findings"
    modes = (
        ("project", t("By project", "По проектам")), ("subject", t("By subject", "По субъектам")),
        ("findings", t("Findings", "Замечания")), ("preview", t("Assess a change", "Оценить изменение")),
    )
    heading = _heading(t("Access Matrix", "Матрица доступа"),
                       t("Inspect effective SSH access for groups, users, and roles.",
                         "Проверьте, к каким серверам через SSH могут подключаться группы, пользователи и роли."),
                       _export(t, "access-matrix"))
    tabs = _tabs(t("Access matrix views", "Разделы матрицы доступа"), view, [(key, title, _url(path, view=key)) for key, title in modes])
    if view == "preview":
        content = _matrix_preview(t, csrf, preview, submitted)
    elif view == "findings":
        selected = params.get("finding", "")
        labels = {
            "conflict": t("Conflicting rules", "Конфликтующие правила"),
            "redundant": t("Duplicate rules", "Дублирующие правила"),
            "shadowed": t("Overridden rules", "Перекрытые правила"),
        }
        details = {
            "conflict": t("Equal precedence, different outcomes.", "У правил одинаковый приоритет, но разные права."),
            "redundant": t("Equal precedence, identical outcomes.", "У правил одинаковый приоритет и одинаковые права."),
            "shadowed": t("Matches inventory but never takes precedence.", "Правило подходит к серверам, но другие правила всегда имеют больший приоритет."),
        }
        fields = _hidden("view", "findings") + _field(t("Finding type", "Тип замечания"), _select(
            "finding", selected, [("", t("All findings", "Все замечания")), *labels.items()]))
        toolbar = _matrix_filters(t, fields, findings=True)
        rows = []
        for finding in matrix["findings"]:
            kind = finding.get("type")
            if selected and selected != kind:
                continue
            grant_ids = str(finding.get("grant_ids") or "").split(",")
            links = " ".join('<a href="{}">#{}</a>'.format(_url("/grants", selected=identifier), _escape(identifier))
                             for identifier in grant_ids if identifier)
            rows.append((_chip(labels.get(kind) or kind, "danger" if kind == "conflict" else "warning"),
                         _escape(finding.get("subject") or "—"), _escape(finding.get("project") or "—"),
                         _escape(finding.get("host_id") or "—"), links, _escape(details.get(kind) or finding.get("details"))))
        content = toolbar + _table(t, (t("Finding", "Замечание"), t("Subject", "Субъект"), t("Project", "Проект"),
                                      t("Host", "Сервер"), t("Rules", "Правила"), t("Details", "Сведения")), rows)
    else:
        content = _matrix_entries(t, matrix, params, view)
    return '<section class="admin-page access-admin">{}{}{}</section>'.format(heading, tabs, content)


def _matrix_entries(t, matrix, params, view):
    path = "/policy/matrix"
    query = params.get("subject", "")
    projects = matrix["projects"]
    records = [record for record in matrix["rows"]
               if _matches(query.strip().casefold(), "{}:{}".format(record["subject"], record["name"]))]
    by_subject = {"{}:{}".format(record["subject"], record["name"]): record for record in records}
    fields = _hidden("view", view) + _search(t, "subject", query, t("Search subjects", "Поиск по субъектам"))
    if view == "project":
        project = params.get("project") or next(iter(projects), "")
        fields += _field(t("Project", "Проект"), _select("project", project, [(item, item) for item in projects]))
        entries = [("{}:{}".format(item["subject"], item["name"]), _role(t, item), item["cells"][project]) for item in records if project in item["cells"]]
        headings = (t("Subject", "Субъект"), t("SSH access", "Доступ по SSH"), t("Hosts", "Серверы"))
        current = {"view": view, "subject": query, "project": project}
    else:
        subject = params.get("principal") or next(iter(by_subject), "")
        fields += _field(t("Subject", "Субъект"), _select("principal", subject, [(key, key) for key in by_subject]))
        entry = by_subject.get(subject)
        entries = [(item, "", entry["cells"][item]) for item in projects] if entry else []
        headings = (t("Project", "Проект"), t("SSH access", "Доступ по SSH"), t("Hosts", "Серверы"))
        current = {"view": view, "subject": query, "principal": subject}
    filters = _matrix_filters(t, fields)
    selected_name = params.get("selected") or next((name for name, _, _ in entries), "")
    selected_cell = None
    selected_index = None
    rows = []
    for index, (name, subtitle, cell) in enumerate(entries):
        if name == selected_name:
            selected_cell = cell
            selected_index = index
        link = '<a href="{}">{}</a>'.format(_url(path, **current, selected=name), _escape(name))
        if subtitle:
            link += '<small class="admin-meta">{}</small>'.format(_escape(subtitle))
        rows.append((link, _matrix_access(t, cell), '<code>{}/{}</code>'.format(cell["allowed_hosts"], cell["total_hosts"])))
    inspector = '<p class="admin-empty">{}</p>'.format(_escape(t("Choose a row to inspect its access.", "Выберите строку, чтобы проверить права.")))
    if selected_cell is not None:
        privileges = _list([dict(_sudo(t)).get(mode, mode) for mode in selected_cell["sudo_modes"]])
        inspector = '<h2>{}</h2>{}{}'.format(_escape(selected_name), _matrix_access(t, selected_cell), _terms((
            (t("Hosts with access", "Серверы с доступом"), "{}/{}".format(selected_cell["allowed_hosts"], selected_cell["total_hosts"])),
            (t("SSH accounts", "Учётные записи SSH"), _list(selected_cell["remote_users"])),
            (t("Privilege elevation", "Повышение привилегий"), privileges),
            (t("Allowed actions", "Разрешённые действия"), _list(selected_cell["actions"])),
        )))
    return '{}<div class="admin-split matrix-results">{}<aside class="admin-panel">{}</aside></div>'.format(
        filters, _table(t, headings, rows, selected=selected_index), inspector,
    )
