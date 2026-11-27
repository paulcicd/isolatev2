"""Permission-scoped sections of the dashboard navigation."""

from html import escape

from isolate_permissions import has_permission
from isolate_ui_icons import icon


def render_navigation(config, identity, locale, words, *, admin, roles, path):
    russian = locale == "ru"
    api = config.get("api", {}).get("enabled")
    groups = []
    operations, access = [], []

    if admin:
        operations.extend((
            ("/jobs", words["jobs"], "workflow"),
            ("/alerts", words["alerts"], "shield-alert"),
            ("/sessions/active", words["active_sessions"], "activity"),
            ("/inventory", words["inventory"], "database"),
            ("/announcements", words["announcements"], "file-text"),
        ))
        access.extend((
            ("/access", words["requests"], "key-round"),
            ("/packages", words["packages"], "key-round"),
            ("/policy/matrix", words["matrix"], "network"),
            ("/policy/simulate", words["simulator"], "list-filter"),
        ))
        groups.extend((
            ("overview", words["summary"] if russian else "Overview", "layout-dashboard", [
                ("/", words["summary"] if russian else "Dashboard", "layout-dashboard"),
                ("/grants", "Правила доступа" if russian else "Access rules", "shield-check"),
                ("/history", "Журнал сессий" if russian else "Session logs", "file-clock"),
                ("/settings", "Настройки" if russian else "Settings", "settings-2"),
            ]),
            ("operations", words["operations"], "workflow", operations),
            ("access", words["access_control"], "shield-check", access),
            ("platform", words["platform"], "settings-2", [
                ("/policy/gitops", words["gitops"], "workflow"),
                ("/users", words["users"], "users"),
                ("/notifications", words["notifications"], "activity"),
            ]),
        ))
    else:
        delegated = (
            ("/inventory", "inventory", "database", "inventory.read"),
            ("/access", "requests", "key-round", "access.read"),
            ("/history", "history", "file-clock", "audit.read"),
            ("/sessions/active", "active_sessions", "activity", "sessions.read"),
        )
        access.extend((route, words[label], symbol) for route, label, symbol, permission in delegated
                      if has_permission(identity, config, permission))
        groups.append(("projects", "Мои проекты" if russian else "My projects", "network", access))

    if has_permission(identity, config, "sessions.approve") or has_permission(identity, config, "sessions.read"):
        access.append(("/session-approvals", "Согласование подключений" if russian else "Session approvals", "shield-check"))

    workspace = []
    if api:
        workspace.append(("/workspace", "Каталог ресурсов" if russian else "Resources", "server"))
        if config.get("gateway", {}).get("enabled"):
            workspace.append(("/me/terminal", "Терминал" if russian else "Terminal", "terminal"))
        if admin or roles:
            workspace.append(("/workspace/admin", "Управление" if russian else "Administration", "sliders-horizontal"))
        if has_permission(identity, config, "access.read"):
            access.append(("/workspace/governance", "Проверка выданных прав" if russian else "Access lifecycle", "users"))
        if admin:
            access.append(("/policy/impact", "Оценка изменений доступа" if russian else "Policy impact", "network"))
        from isolate_workspace_ui import campaign_navigation_allowed
        if campaign_navigation_allowed(identity, config):
            (operations if admin else workspace).append(
                ("/operations/campaigns", "Поэтапные запуски" if russian else "Staged operations", "workflow"))
    groups.append(("workspace", "Рабочее пространство" if russian else "Workspace", "server", workspace))

    if api and config.get("audit_index", {}).get("enabled"):
        groups.append(("audit", "Аудит" if russian else "Audit", "file-clock", [
            ("/audit/search", "Журнал аудита" if russian else "Audit search", "search"),
            ("/investigations", "Расследования" if russian else "Investigation", "file-clock"),
        ]))
    groups.append(("personal", "Личный кабинет" if russian else "My workspace", "users", [
        ("/me", "Мои серверы" if russian else "My servers", "server"),
        ("/me/profile", "Личный кабинет" if russian else "My profile", "settings-2"),
        ("/me/access", "Мои заявки" if russian else "My requests", "key-round"),
        ("/me/sessions", "Мои сессии" if russian else "My sessions", "activity"),
        ("/me/history", "История подключений" if russian else "My history", "file-clock"),
        ("/me/session-approvals", "Согласование моих подключений" if russian else "My approvals", "shield-check"),
    ]))
    groups = [group for group in groups if group[3]]
    available = {route for _, _, _, links in groups for route, _, _ in links}
    current = max((route for route in available if
                   path == route or (route not in ("/", "/me") and path.startswith(route + "/"))),
                  key=len, default="")
    if not current:
        for prefix, parents in (
            ("/job/", ("/jobs", "/operations/campaigns")),
            ("/session/", ("/history", "/me/history")),
            ("/replay/", ("/history", "/me/history")),
            ("/user/", ("/users",)),
            ("/me/resources/", ("/workspace", "/me")),
        ):
            if path.startswith(prefix):
                current = next((route for route in parents if route in available), "")
                break

    buttons, sections = [], []
    for key, title, symbol, links in groups:
        selected = any(route == current for route, _, _ in links)
        group_id = "nav-group-" + key
        title = escape(title)
        buttons.append(
            f'<button type="button" data-nav-trigger="{key}" aria-controls="{group_id}" '
            f'aria-pressed="{str(selected).lower()}">{icon(symbol)}<span class="sr-only">{title}</span></button>'
        )
        items = []
        for route, label, link_icon in links:
            active = ' active' if route == current else ''
            aria = ' aria-current="page"' if active else ''
            items.append(f'<a class="nav-link{active}" href="{route}"{aria}>'
                         f'{icon(link_icon)}<span>{escape(label)}</span></a>')
        sections.append(f'<section class="nav-section" data-nav-group="{key}" id="{group_id}" aria-labelledby="{group_id}-title">'
                        f'<h2 class="nav-label" id="{group_id}-title">{title}</h2>{"".join(items)}</section>')
    return "".join(buttons), "".join(sections)
