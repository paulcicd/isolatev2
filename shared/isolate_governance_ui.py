"""Server-rendered, project-scoped access review and assignment workspace."""

import datetime
import html
import secrets
from urllib.parse import urlencode

import isolate_governance as governance
from isolate_ui_icons import icon
from isolate_workflow_ui import workflow_copy, workflow_hints, workflow_value


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _url(view="attention", project="", **query):
    values = dict(view=view if view != "attention" else "", project=project, **query)
    params = urlencode({key: value for key, value in values.items() if value})
    return "/workspace/governance" + ("?" + params if params else "")


def _timestamp(value):
    if not value:
        return "—"
    return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _table(labels, rows, empty):
    if not rows:
        return '<p class="admin-empty" role="status">{}</p>'.format(_e(empty))
    header = "".join('<th scope="col">{}</th>'.format(_e(label)) for label in labels)
    return '<div class="table-wrap"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(
        header, "".join(rows))


def _row(*cells):
    return "<tr>{}</tr>".format("".join("<td>{}</td>".format(cell) for cell in cells))


def _link(label, url, *, button=False, primary=False):
    style = "admin-button" + (" admin-primary" if primary else "") if button else ""
    return '<a class="{}" href="{}">{}</a>'.format(style, _e(url), _e(label))


def _panel(title, body):
    return '<section class="admin-panel governance-panel"><h2>{}</h2>{}</section>'.format(_e(title), body)


def _field(name, label, value="", kind="text", attributes=""):
    return '<label>{}<input name="{}" type="{}" value="{}" required{}></label>'.format(
        _e(label), name, kind, _e(value), attributes)


def _decision_progress(review):
    total = len(review["items"])
    decided = sum(bool(item.get("decision")) for item in review["items"])
    return '<span class="admin-meta governance-progress">{} / {}</span>'.format(decided, total)


def render_governance(config, identity, data, visible_projects, args, csrf_token):
    from isolate_web import _dashboard_locale, _html

    russian = _dashboard_locale(config) == "ru"

    def tr(en, ru):
        return ru if russian else en

    def ui(source):
        return workflow_copy(config, source)

    def localized(value):
        _STATES = {
            "open": "Open", "completed": "Completed", "active": "Active", "expired": "Expired",
            "scheduled": "Scheduled", "revoked": "Revoked", "keep": "Kept", "revoke": "Revoked",
            "removed": "Removed externally", "blocked": "Blocked", "assignment_expiring": "Access expiring soon",
            "review_overdue": "Overdue review", "periodic_review_due": "Scheduled review",
            "no_expiry": "No expiry", "privileged_identity": "Privileged account",
            "broad_project_scope": "Multiple projects", "username_only_binding": "Username-only binding",
        }
        return workflow_value(config, value) if russian else _STATES.get(value, value)

    def chip(value):
        tones = {"open": "info", "completed": "positive", "active": "positive", "expired": "warning",
                 "scheduled": "info", "revoked": "danger", "keep": "positive", "revoke": "danger", "blocked": "danger"}
        return '<span class="admin-chip" data-tone="{}">{}</span>'.format(tones.get(value, ""), _e(localized(value)))

    def form(operation, contents, label, **hidden):
        hidden.update(operation=operation, csrf_token=csrf_token())
        inputs = "".join('<input type="hidden" name="{}" value="{}">'.format(key, _e(value)) for key, value in hidden.items())
        return ('<form class="governance-form" method="post" action="/workspace/governance/actions">{}'
                '<div class="admin-fields">{}{}</div><label class="governance-confirm">'
                '<input type="checkbox" name="confirm" value="true" required> {}</label>'
                '<button class="admin-primary" type="submit">{}</button></form>').format(
            inputs, contents, _field("reason", ui("Reason"), attributes=' maxlength="2048"'),
            _e(ui("Confirm this access change")), _e(label))

    project = args.get("project", "")
    view_labels = {
        "attention": tr("Attention", "Требует внимания"), "reviews": tr("Reviews", "Проверки"),
        "assignments": tr("Temporary access", "Временный доступ"), "offboarding": tr("Offboarding", "Прекращение доступа"),
    }
    view = args.get("view") if args.get("view") in view_labels else "attention"
    action = args.get("action")
    owner_projects = [scope for scope in visible_projects if governance.has_permission(identity, config, "access.approve", scope)
                      and governance.has_permission(identity, config, "inventory.write", scope)]
    is_admin = governance.is_platform_admin(identity, config)
    what_project = ui("Project")
    due_label = tr("Due", "Срок")
    status_label = ui("Status")
    no_matches = tr("No records match these filters.", "По этим условиям записей нет.")
    review_count = sum(item["kind"] == "review_overdue" for item in data["reminders"])
    expiry_count = sum(item["kind"] == "assignment_expiring" for item in data["reminders"])
    periodic_count = sum(item["kind"] == "periodic_review_due" for item in data["reminders"])

    def project_options(projects):
        return "".join('<option value="{}"{}>{}</option>'.format(_e(scope), " selected" if scope == project else "", _e(scope))
                       for scope in projects)

    title = tr("Access lifecycle", "Проверка выданных прав")
    lead = tr("Owner reviews, temporary access, and offboarding.", "Проверки владельцами, временный доступ и прекращение доступа.")
    body = '<section class="admin-page governance-workspace"><header class="admin-heading"><div><h1>{}</h1><p>{}</p></div>'.format(title, lead)
    if owner_projects:
        body += '<div class="admin-actions">{}{}</div>'.format(
            _link(tr("Grant temporary access", "Выдать на срок"), _url("assignments", project, action="new-assignment"), button=True),
            _link(ui("Start review"), _url("reviews", project, action="new-review"), button=True, primary=True))
    body += '</header><div class="admin-toolbar governance-navigation"><nav class="admin-tabs" aria-label="{}">'.format(title)
    body += "".join('<a href="{}"{}>{}</a>'.format(_e(_url(key, project)),
        ' aria-current="page"' if key == view else "", _e(label)) for key, label in view_labels.items())
    body += ('</nav><form class="inline" method="get" action="/workspace/governance">'
             '<input type="hidden" name="view" value="{}"><label>{}<select name="project">'
             '<option value="">{}</option>{}</select></label><button type="submit">{}</button></form></div>').format(
        view, _e(what_project), tr("All projects", "Все проекты"), project_options(visible_projects), tr("Apply", "Применить"))

    owner_select = '<label>{}<select name="project">{}</select></label>'.format(_e(what_project), project_options(owner_projects))
    actions = {
        "new-review": ("reviews", "create_review", "Start an owner review", "Start review"),
        "new-assignment": ("assignments", "assignment", "Temporary or contractor assignment", "Create assignment"),
        "end-project": ("offboarding", "offboard", "End access", "End project access"),
        "end-all": ("offboarding", "offboard", "Global offboarding", "End all Isolate access"),
    }
    if action in actions and (is_admin if action == "end-all" else bool(owner_projects)):
        tab, operation, heading, label = actions[action]
        if view == tab:
            contents = owner_select
            hidden = {}
            if operation in ("create_review", "assignment"):
                hidden["intent"] = secrets.token_hex(16)
            if operation == "assignment":
                contents += (_field("subject_id", ui("Stable subject"), attributes=' maxlength="1024"')
                    + _field("username", ui("Display username")) + _field("remote_user", ui("Target account"), "support")
                    + _field("expires_days", ui("Expires in days"), "7", "number", ' min="1" max="90"')
                    + _field("allowed_actions", ui("Actions (comma separated)"), "ssh,webssh"))
                help_text = ui("Assignments require an immutable provider-bound subject, expire within 90 days, and never grant sudo/root. Expiry does not remove any independent group access.")
            elif operation == "offboard":
                if action == "end-all":
                    contents = ""
                    hidden["project"] = "*"
                contents += _field("subject_id", ui("Stable subject"), attributes=' maxlength="1024"')
                help_text = ui("Offboarding blocks this subject even when group or externally managed grants still exist. It does not delete the IdP account or rewrite GitOps policy. Reboarding needs an independent reviewed procedure.")
            else:
                help_text = ui("A review freezes the visible grants. Keeping access records a decision without extending its expiry. Changed grants require a fresh review.")
            body += _panel(ui(heading), '<p class="admin-muted">{}</p>{}<p>{}</p>'.format(_e(help_text),
                form(operation, contents, ui(label), **hidden), _link(tr("Cancel", "Отмена"), _url(view, project), button=True)))

    if view == "attention":
        body += '<div class="governance-counts">'
        for label, target, count, glyph, tone in (
            (tr("Overdue reviews", "Просроченные проверки"), _url("reviews", project, status="overdue"), review_count, "info", "danger"),
            (tr("Access expiring soon", "Скоро истекает доступ"), _url("assignments", project, status="expiring"), expiry_count, "clock", "warning"),
            (tr("Scheduled reviews due", "Пора проверить"), _url("reviews", project), periodic_count, "file-clock", "info"),
        ):
            body += '<a class="admin-panel governance-count" data-tone="{}" href="{}"><span>{} {}</span><strong>{}</strong></a>'.format(
                tone, _e(target), icon(glyph), label, count)
        body += '</div>'
        reminder_rows = []
        for item in sorted(data["reminders"], key=lambda record: record["due_at"]):
            scope = item["project"]
            if item["kind"] == "review_overdue":
                link = _url("reviews", scope, review=item["review_id"])
            elif item["kind"] == "assignment_expiring":
                link = _url("assignments", scope, assignment=item["assignment_id"])
            else:
                link = _url("reviews", scope, action="new-review" if scope in owner_projects else "")
            reminder_rows.append(_row(_link(localized(item["kind"]), link), _e(scope), _timestamp(item["due_at"])))
        body += _panel(tr("Action queue", "Очередь действий"), _table((tr("Event", "Событие"), what_project, due_label), reminder_rows,
            ui("No outstanding reminders.")))
        if data["findings"]:
            body += '<details class="admin-panel admin-disclosure"><summary>{} <span class="admin-meta">{}</span></summary>'.format(
                ui("Review candidates"), len(data["findings"]))
            body += '<p class="admin-muted">{}</p>'.format(ui("These findings are prompts for an owner review, not proof that access is unused or unnecessary. No rights are removed automatically."))
            findings = [_row(_link(ui("Grant #{}").format(item["grant_id"]), "/investigations?" + urlencode({"kind": "grant", "id": item["grant_id"]})),
                _e(item["project"]), _e(", ".join(localized(reason) for reason in item["reasons"]))) for item in data["findings"]]
            body += _table((tr("Grant", "Правило"), what_project, ui("Reason")), findings, no_matches) + "</details>"

    elif view == "reviews":
        reviews = sorted(data["reviews"], key=lambda item: item["created_at"], reverse=True)
        selected = next((row for row in reviews if row["id"] == args.get("review")), None)
        if selected:
            body += _link(tr("Back to reviews", "К списку проверок"), _url("reviews", project), button=True)
            details = '<div class="admin-toolbar"><strong>{}</strong>{}{}</div><p class="admin-meta">{}</p>'.format(
                _e(selected["project"]), chip(selected["status"]), _decision_progress(selected),
                _e(ui("Owner: {} · Due: {}").format(selected["owner_subject"], _timestamp(selected["due_at"]))))
            body += _panel(tr("Review details", "Проверка доступа"), details)
            rows = []
            for item in selected["items"]:
                grant_id = item["grant_id"]
                history = _link(ui("Grant timeline"), "/investigations?" + urlencode({"kind": "grant", "id": grant_id}))
                subject = '<strong>{}</strong><span class="admin-meta">{}</span>'.format(
                    _e(item.get("name") or item.get("subject") or "—"), _e(ui("Grant #{}").format(grant_id)))
                decision = (chip(item["decision"]) if item.get("decision") else
                            '<span class="admin-meta">{}</span>'.format(ui("Awaiting review")))
                if item.get("reason"):
                    decision += '<span class="admin-meta">{}</span>'.format(_e(item["reason"]))
                buttons = history
                if selected["status"] == "open" and not item.get("decision") and selected["project"] in owner_projects:
                    choices = ui('<label>Decision<select name="decision"><option value="keep">Keep current access</option>'
                                 '<option value="revoke">Revoke this rule</option><option value="removed">Confirm externally removed</option></select></label>')
                    buttons += '<details class="admin-disclosure governance-decision"><summary>{}</summary>{}</details>'.format(
                        tr("Review grant", "Рассмотреть правило"), form("review", choices, ui("Record decision"),
                        review_id=selected["id"], grant_id=grant_id))
                rows.append(_row(subject, '<code>{}</code>'.format(_e(item.get("remote_user") or "—")), decision, buttons))
            body += _panel(ui("Owner reviews"), _table((tr("Grant", "Правило"), ui("Target account"), ui("Decision"), tr("Action", "Действие")), rows, no_matches))
        else:
            overdue = {item["review_id"] for item in data["reminders"] if item["kind"] == "review_overdue"}
            rows = [_row(_link(row["project"], _url("reviews", project, review=row["id"])), _e(row["owner_subject"]),
                _timestamp(row["due_at"]), _decision_progress(row), chip(row["status"])) for row in reviews
                if args.get("status") != "overdue" or row["id"] in overdue]
            body += _panel(ui("Owner reviews"), _table((what_project, tr("Owner", "Ответственный"), due_label,
                tr("Decisions", "Решения"), status_label), rows, no_matches))
            schedules = [_row(_e(row["project"]), _timestamp(row["last_completed_at"]), _timestamp(row["next_due_at"])) for row in data["review_schedule"]]
            body += _panel(ui("Review schedule"), _table((what_project, ui("Last completed"), ui("Next review due")), schedules, no_matches))

    elif view == "assignments":
        expiring = {item["assignment_id"] for item in data["reminders"] if item["kind"] == "assignment_expiring"}
        selected = next((row for row in data["assignments"] if row["id"] == args.get("assignment")), None)
        if selected:
            body += _link(tr("Back to assignments", "К списку назначений"), _url("assignments", project), button=True)
            details = '<dl class="governance-meta"><div><dt>{}</dt><dd>{}</dd></div><div><dt>{}</dt><dd>{}</dd></div><div><dt>{}</dt><dd>{}</dd></div><div><dt>{}</dt><dd>{}</dd></div></dl>'.format(
                _e(ui("Stable subject")), _e(selected["subject_id"]), _e(ui("Target account")), _e(selected["remote_user"]),
                tr("Actions", "Действия"), _e(", ".join(selected["allowed_actions"])), _e(ui("Reason")), _e(selected["reason"]))
            if selected["status"] == "active" and selected["project"] in owner_projects:
                details += '<details class="admin-disclosure"><summary>{}</summary>{}</details>'.format(
                    ui("Revoke assignment"), form("revoke_assignment", "", ui("Revoke assignment"), assignment_id=selected["id"]))
            body += _panel(selected["username"], details)
        rows = []
        for row in sorted(data["assignments"], key=lambda item: item["expires_at"]):
            state = row.get("effective_status", row["status"])
            if args.get("status") == "expiring" and row["id"] not in expiring:
                continue
            rows.append(_row(_link(row["username"], _url("assignments", project, assignment=row["id"])),
                _e(row["project"]), _timestamp(row["expires_at"]), chip(state)))
        body += _panel(tr("Temporary assignments", "Временные назначения"), _table(
            (tr("User", "Пользователь"), what_project, ui("Expiry"), status_label), rows, no_matches))

    elif view == "offboarding":
        actions = ""
        if owner_projects:
            actions += _link(ui("End project access"), _url("offboarding", project, action="end-project"), button=True)
        if is_admin:
            actions += _link(ui("End all Isolate access"), _url("offboarding", project, action="end-all"), button=True)
        rows = [_row('<code>{}</code>'.format(_e(row["subject_id"])), _e(row["project"]) if row["project"] != "*" else tr("All projects", "Все проекты"),
            _timestamp(row["created_at"]), chip(row["status"]), _e(row.get("reason"))) for row in
            sorted(data["offboardings"], key=lambda item: item["created_at"], reverse=True)]
        body += _panel(ui("Offboarding decisions"), '<div class="admin-toolbar">{}</div>{}'.format(actions,
            _table((ui("Stable subject"), what_project, tr("Date", "Дата"), status_label, ui("Reason")), rows, no_matches)))
    return _html(title, workflow_hints(config, body + "</section>"), config=config)


def render_governance_error(config, status):
    from isolate_web import _dashboard_locale, _html

    russian = _dashboard_locale(config) == "ru"
    if status == 503:
        title = "Проверка прав временно недоступна" if russian else "Access lifecycle is temporarily unavailable"
        detail = "Повторите попытку позже." if russian else "Try again shortly."
    elif status == 403:
        title = "Действие недоступно" if russian else "Action unavailable"
        detail = "Проверьте полномочия для этого проекта и выбранного действия." if russian else "Check your permissions for this project and action."
    elif status == 409:
        title = "Запись уже изменилась" if russian else "The record has changed"
        detail = "Откройте актуальную запись и проверьте, нужно ли повторять действие." if russian else "Open the current record and check whether the action is still needed."
    else:
        title = "Не удалось обработать запрос" if russian else "Could not process the request"
        detail = "Проверьте выбранную запись и данные формы." if russian else "Check the selected record and form values."
    body = '<section class="admin-page"><h1>{}</h1><p role="alert">{}</p>{}</section>'.format(
        title, detail, _link("К проверке прав" if russian else "Back to access lifecycle", _url(), button=True))
    return _html(title, body, config=config)
