"""Inventory screens built on the dashboard's existing navigation and forms."""

import html
from urllib.parse import urlencode, quote

from isolate_admin_ui import admin_empty, admin_heading, export_menu
from isolate_ui_icons import icon


def _escape(value):
    return html.escape(str(value if value is not None else ""))


def inventory_page(rows, args, locale, csrf, *, is_admin, can_write, posted=None):
    def label(en, ru):
        return ru if locale == "ru" else en

    posted = posted or {}
    action = posted.get("action")

    def input_field(name, caption, *, values, default="", attrs="", hint=""):
        return ('<label class="admin-field">{}<input name="{}" value="{}"{}>{}</label>').format(
            _escape(caption), name, _escape(values.get(name, default)), attrs,
            '<small class="admin-muted">{}</small>'.format(_escape(hint)) if hint else "",
        )

    def select_field(name, caption, choices, values, disabled=False):
        options = "".join('<option value="{}"{}>{}</option>'.format(
            _escape(value), " selected" if values.get(name) == value else "", _escape(copy),
        ) for value, copy in choices)
        return '<label class="admin-field">{}<select name="{}"{}>{}</select></label>'.format(
            _escape(caption), name, " disabled" if disabled else "", options,
        )

    def check_field(name, caption, values, required=False):
        return '<label><input type="checkbox" name="{}" value="true"{}{}> {}</label>'.format(
            name, " checked" if values.get(name) == "true" and not required else "", " required" if required else "", _escape(caption),
        )

    def section(caption, fields):
        return '<fieldset><legend>{}</legend><div class="admin-fields">{}</div></fieldset>'.format(
            _escape(caption), "".join(fields),
        )

    def editor(mode, title, body, submit):
        return ('<details class="admin-disclosure inventory-editor" id="inventory-{}"{} data-admin-dialog>'
                '<summary class="admin-button{}">{} {}</summary>'
                '<form id="inventory-{}-form" class="admin-panel" method="post">'
                '<input type="hidden" name="csrf_token" value="{}"><input type="hidden" name="action" value="{}">'
                '{}<div class="admin-toolbar">{}<button class="admin-primary" type="submit">{}</button></div>'
                '</form></details>').format(
            mode, " open" if action == mode else "", " admin-primary" if mode == "add" else "",
            icon("server" if mode == "add" else "settings-2"), _escape(title), mode, _escape(csrf), mode,
            body, check_field("confirm", label("Confirm change", "Подтверждаю изменение"), {}, required=True), _escape(submit),
        )

    editors = []
    if is_admin:
        add = posted if action == "add" else {}
        editors.append(editor("add", label("Add host", "Добавить сервер"),
            section(label("Connection", "Подключение"), [
                input_field("project", label("Project", "Проект"), values=add, attrs=" required"),
                input_field("name", label("Host name", "Имя сервера"), values=add, attrs=" required"),
                input_field("ip", label("Address", "Адрес"), values=add, attrs=" required"),
                input_field("port", label("SSH port", "Порт SSH"), values=add, default="22", attrs=' type="number" min="1" max="65535" required'),
                input_field("user", label("SSH account", "Учётная запись SSH"), values=add, attrs=" required"),
            ]) + section(label("Metadata", "Сведения о сервере"), [
                input_field("services", label("Services", "Сервисы"), values=add),
                input_field("tags", label("Tags", "Теги"), values=add, hint="env=prod,owner=platform"),
                input_field("owner", label("Owner", "Владелец"), values=add),
                input_field("environment", label("Environment", "Окружение"), values=add),
                select_field("vip", "VIP", [("false", label("Standard", "Обычный сервер")), ("true", "VIP")], add),
            ]), label("Add host", "Добавить сервер")))

    if can_write:
        bulk = posted if action == "bulk_update" else {}
        ids = input_field("host_ids", label("Host IDs", "ID серверов"), values=bulk, hint=label(
            "Select rows or enter up to 200 IDs separated by commas.",
            "Отметьте строки или введите до 200 ID через запятую.",
        ))
        routing_lock = "" if is_admin else " disabled"
        keep = label("Keep current", "Оставить как есть")
        editors.append(editor("bulk_update", label("Bulk update", "Массовое обновление"),
            '<p class="admin-muted">{}</p>'.format(label(
                "Fill only the fields you want to change.", "Заполните только поля, которые хотите изменить.",
            )) + section(label("Targets", "Серверы"), [ids]) + section(label("Changes", "Что изменить"), [
                input_field("project", label("Project", "Проект"), values=bulk, attrs=routing_lock),
                input_field("user", label("SSH account", "Учётная запись SSH"), values=bulk, attrs=routing_lock),
                input_field("services", label("Services", "Сервисы"), values=bulk),
                input_field("tags", label("Replace tags", "Заменить теги"), values=bulk),
                check_field("clear_tags", label("Clear all tags", "Удалить все теги"), bulk),
                input_field("owner", label("Owner", "Владелец"), values=bulk),
                input_field("environment", label("Environment", "Окружение"), values=bulk),
                select_field("vip", "VIP", [("", keep), ("true", "VIP"), ("false", label("Standard", "Обычный сервер"))], bulk,
                             disabled=not is_admin),
                select_field("maintenance", label("Maintenance", "Техработы"), [
                    ("", keep), ("true", label("In maintenance", "Идут работы")), ("false", label("Available", "Доступен")),
                ], bulk),
            ]), label("Apply changes", "Применить изменения")))

    title = label("Inventory", "Инвентарь")
    filter_actions = ('<label class="admin-search">{}<input type="search" name="q" value="{}" aria-label="{}" '
                      'placeholder="{}"></label>').format(
        icon("search"), _escape(args.get("q") or ""), label("Search hosts", "Поиск серверов"),
        label("Name, address or host ID", "Имя, адрес или ID сервера"),
    )
    filter_actions += input_field("project", label("Project", "Проект"), values=args)
    filter_actions += input_field("tags", label("Tags", "Теги"), values=args)
    reset = '<a class="admin-button" href="/inventory">{}</a>'.format(label("Clear", "Сбросить"))
    filters = ('<div class="admin-panel"><form method="get" class="admin-toolbar inventory-filter">{}'
               '<button class="admin-primary" type="submit">{}</button>{}</form></div>').format(
        filter_actions, label("Search", "Найти"), reset if any(args.get(k) for k in ("q", "project", "tags")) else "",
    )
    if rows:
        headers = [
            label("Host", "Сервер"), label("Project", "Проект"), label("Address", "Адрес"),
            label("Status", "Состояние"), label("Tags", "Теги"), label("Owner", "Владелец"), label("Details", "Детали"),
        ]
        table = _inventory_table(rows, headers, locale, csrf, is_admin=is_admin, can_write=can_write,
                                 selected=set(posted.getlist("selected_host_id")) if hasattr(posted, "getlist") else set())
    else:
        table = admin_empty(label("No hosts match these filters.", "Серверов по этим фильтрам нет."))
    back = {key: args.get(key) for key in ("q", "project", "tags") if args.get(key)}
    heading = admin_heading(title, label("Hosts, connectivity and connection settings.", "Серверы, их доступность и параметры подключения."),
                            export_menu("/export/inventory", back, locale))
    count = '<p class="admin-muted">{}</p>'.format(label(f"Hosts shown: {len(rows)}", f"Показано серверов: {len(rows)}"))
    selected_label = label("Selected hosts", "Выбрано серверов")
    selection = '<p class="inventory-selection" hidden><output aria-live="polite">{}: <strong>0</strong></output></p>'.format(selected_label) if can_write else ""
    return ('<section class="admin-page admin-inventory" data-close-label="{}">{}{}{}{}{}{}</section>'
            '<script src="/static/inventory-ui.js" defer></script>').format(
        label("Close", "Закрыть"), heading, filters, '<div class="inventory-editors">{}</div>'.format("".join(editors)) if editors else "",
        selection, count, table,
    )


def _inventory_table(rows, headers, locale, csrf, *, is_admin, can_write, selected):
    ru = locale == "ru"

    def copy(en, russian):
        return russian if ru else en

    chooser_heading = '<th scope="col">{}</th>'.format(copy("Select", "Выбор")) if can_write else ""
    head = chooser_heading + "".join('<th scope="col">{}</th>'.format(_escape(title)) for title in headers)
    rendered_rows = []
    for row in rows:
        host_id = str(row["server_id"])
        segment = quote(host_id, safe="")
        project = row.get("project_name") or ""
        project_label = _escape(project or "—")
        if project and row["can_audit"]:
            project_label = '<a href="{}">{}</a>'.format(_escape("/history?" + urlencode({"project": project})), project_label)
        ip = str(row.get("server_ip") or "—")
        address = "{}:{}".format("[" + ip + "]" if ":" in ip else ip, row.get("server_port") or 22)
        chooser = ""
        if can_write:
            checkbox = ('<input type="checkbox" name="selected_host_id" value="{}" form="inventory-bulk_update-form"'
                        ' aria-label="{}"{}>').format(_escape(host_id), _escape(copy("Select host ", "Выбрать сервер ") + host_id),
                                                   " checked" if host_id in selected else "")
            chooser = "<td>{}</td>".format(checkbox if row["can_write"] else "—")
        vip = ' <span class="admin-chip" data-tone="warning">VIP</span>' if row.get("server_vip") else ""
        state, tone = copy("Not checked", "Не проверен"), ""
        if row["connectivity"] == "reachable":
            state, tone = copy("Reachable", "Отвечает"), "positive"
        elif row["connectivity"] == "failed":
            state, tone = copy("Unreachable", "Не отвечает"), "danger"
        if row.get("maintenance_active"):
            state, tone = copy("MAINT · Maintenance", "Техработы"), "warning"
        fields = [
            (copy("SSH account", "Учётная запись SSH"), row.get("server_user") or "—"),
            (copy("Services", "Сервисы"), row.get("server_services_display")),
            (copy("Environment", "Окружение"), row.get("environment")),
            (copy("Maintenance reason", "Причина техработ"), row.get("maintenance_reason")),
            (copy("Note", "Примечание"), row.get("server_note")),
            (copy("Privileged access", "Привилегированный доступ"), row.get("privileged_access_provider")),
            (copy("Privileged access notes", "Подсказка по привилегированному доступу"), row.get("privileged_access_hint")),
        ]
        facts = "".join("<div><dt>{}</dt><dd>{}</dd></div>".format(_escape(key), _escape(value)) for key, value in fields if value)
        edit_url = f"/inventory/{segment}/edit" if row["can_write"] else f"/me/resources/{segment}"
        links = [
            (edit_url, copy("Edit", "Редактировать") if row["can_write"] else copy("View host", "Открыть сервер")),
            (f"/inventory/{segment}/services", copy("Service changes", "Изменения сервисов")),
        ]
        if row["can_audit"]:
            links.append(("/history?" + urlencode({"host": host_id}), copy("Session logs", "Журнал сессий")))
        actions = "".join('<a href="{}">{}</a>'.format(_escape(url), _escape(label)) for url, label in links)
        if is_admin:
            actions += ('<form method="post" class="inline"><input type="hidden" name="csrf_token" value="{}">'
                        '<input type="hidden" name="action" value="connectivity_check"><input type="hidden" name="host_id" value="{}">'
                        '<input type="hidden" name="confirm" value="true"><button type="submit">{}</button></form>').format(
                _escape(csrf), _escape(host_id), copy("Check connectivity", "Проверить связь"),
            )
        rendered_rows.append("""<tr>{chooser}<td><strong>{name}</strong>{vip}<span class="admin-meta font-mono">#{host_id}</span></td>
          <td>{project}</td><td><code>{address}</code></td><td><span class="admin-chip" data-tone="{tone}">{state}</span></td>
          <td>{tags}</td><td>{owner}</td><td><details class="admin-disclosure inventory-host-details" data-admin-dialog data-dialog-size="compact" data-title="{name}">
          <summary>{details}</summary><dl class="admin-facts">{facts}</dl><div class="admin-toolbar">{actions}</div></details></td></tr>""".format(
            chooser=chooser, name=_escape(row.get("server_name") or host_id), vip=vip, host_id=_escape(host_id),
            project=project_label, address=_escape(address),
            tone=tone, state=state, tags=_escape(row.get("tags_display") or "—"), owner=_escape(row.get("resource_owner") or "—"),
            details=copy("Details", "Подробнее"), facts=facts, actions=actions,
        ))
    return '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(
        head, "".join(rendered_rows),
    )
