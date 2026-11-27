"""Authenticated employee and project administration workspace pages.

Only the control API supplies resource data. This module never enumerates the
inventory or uses navigation visibility as an object authorization decision.
"""

import html
import json

from isolate_permissions import has_permission, is_platform_admin, role_names


WORDS = {
    "en": {
        "workspace": "My workspace", "administration": "Administration", "eyebrow": "YOUR ACCESS, IN ONE PLACE",
        "heading": "Find your next connection", "lead": "Servers, databases and internal tools. Current access is checked every time you connect.",
        "all": "All resources", "favorites": "Favorites", "recent": "Recent", "search": "Search resources",
        "placeholder": "Name, project, owner or tag…", "project": "Project", "any_project": "Any project",
        "protocol": "Protocol", "any_protocol": "All protocols", "search_hint": "Search with / or Ctrl K. Use arrow keys to navigate, then Enter to open.",
        "loading": "Loading resources…", "more": "Load more resources", "empty": "No matching resources",
        "empty_help": "Try another search or ask a project owner about access.", "empty_favorites": "Your shortcuts belong here",
        "favorites_help": "Star a resource to keep it within reach. Favorites follow your account across devices.",
        "empty_recent": "Your next connection starts here", "recent_help": "Resources appear here after an authorized connection is started.",
        "reset": "Browse all resources", "retry": "Try again", "owner": "Owner", "environment": "Environment",
        "available": "Available", "approval_required": "Approval required", "step_up_required": "Verify identity",
        "maintenance": "Maintenance", "denied": "Access required", "unavailable": "Unavailable", "unknown": "Check access",
        "reason_available": "Access is available.", "reason_approval": "An administrator must approve this session.",
        "reason_step_up": "Fresh authentication is required.", "reason_maintenance": "This resource is in maintenance.",
        "reason_denied": "A separate connection grant is required.", "reason_unavailable": "The connection service is not enabled for this resource.",
        "connect": "Connect", "details": "Details", "request_access": "Request access", "request_approval": "Request approval",
        "explain_access": "Why this access?",
        "step_up": "Verify identity", "view": "View resource", "add_favorite": "Add to favorites", "remove_favorite": "Remove from favorites",
        "error": "Resources could not be loaded. Your previous results have been cleared.",
        "preferences_error": "Your favorites could not be saved. Try again.", "preferences_load_error": "Favorites could not be loaded. Refresh before making changes.",
        "session_expired": "Your session has expired. Sign in to continue.", "sign_in": "Sign in",
        "forbidden": "You no longer have permission to open this workspace.", "loaded": "resources loaded",
        "no_api": "The connection API is not enabled for this installation. Ask an administrator to configure the gateway.",
        "admin_heading": "Your administration workspace", "admin_lead": "Open the tools available to your current role. Every action is checked against its project.",
        "scope": "Current role", "platform_admin": "Platform administrator", "inventory": "Resource inventory",
        "inventory_help": "Manage the resources in your projects.", "access": "Access requests", "access_help": "Review requests and follow decisions.",
        "sessions": "Active sessions", "sessions_help": "Inspect current connections in permitted projects.",
        "approvals": "Session approvals", "approvals_help": "Review approval gates for individual sessions.",
        "audit": "Session history", "audit_help": "Review permitted session evidence and activity.",
        "grants": "Access policies", "grants_help": "Manage grants and their scope.", "packages": "Access packages",
        "packages_help": "Maintain reusable access assignments.", "matrix": "Access matrix", "matrix_help": "Inspect who can reach each resource.",
        "gitops": "Policy changes", "gitops_help": "Inspect policy sync and revisions.", "users": "People and activity",
        "users_help": "Review users and recent activity.", "jobs": "Jobs and runbooks", "jobs_help": "Follow execution and recovery outcomes.",
        "alerts": "Operational alerts", "alerts_help": "Review operational signals.", "docs": "Setup and documentation", "docs_help": "Find deployment and configuration guidance.",
        "open": "Open", "admin_notice": "Management roles do not grant permission to connect. Connection policies apply separately.",
    },
    "ru": {
        "workspace": "Мои ресурсы", "administration": "Управление", "eyebrow": "ПОДКЛЮЧЕНИЯ",
        "heading": "Каталог ресурсов", "lead": "Серверы, базы данных и внутренние приложения. Isolate проверяет права перед каждым подключением.",
        "all": "Все ресурсы", "favorites": "Избранное", "recent": "Недавние подключения", "search": "Поиск ресурсов",
        "placeholder": "Имя ресурса, проект, владелец или тег…", "project": "Проект", "any_project": "Все проекты",
        "protocol": "Протокол", "any_protocol": "Все протоколы", "search_hint": "Нажмите / или Ctrl + K для поиска. Выберите ресурс стрелками и откройте клавишей Enter.",
        "loading": "Загружаем ресурсы…", "more": "Загрузить ещё", "empty": "Ресурсы не найдены",
        "empty_help": "Измените запрос или сбросьте фильтры. Если нужного ресурса в каталоге нет, уточните доступ у владельца проекта.", "empty_favorites": "Избранных ресурсов пока нет",
        "favorites_help": "Нажмите на звезду рядом с ресурсом. Избранное привязано к вашей учётной записи и доступно на других устройствах.",
        "empty_recent": "Недавних подключений пока нет", "recent_help": "Подключитесь к ресурсу из каталога, чтобы он появился в этом списке.",
        "reset": "Показать все ресурсы", "retry": "Повторить", "owner": "Владелец", "environment": "Окружение",
        "available": "Подключение разрешено", "approval_required": "Нужно согласование", "step_up_required": "Нужен повторный вход",
        "maintenance": "Технические работы", "denied": "Нужно запросить доступ", "unavailable": "Подключение недоступно", "unknown": "Доступ ещё не проверен",
        "reason_available": "Действующее правило разрешает подключение.", "reason_approval": "Отправьте заявку на согласование этого подключения.",
        "reason_step_up": "Войдите повторно, чтобы подтвердить личность.", "reason_maintenance": "Попробуйте подключиться после окончания технических работ.",
        "reason_denied": "Запросите право на подключение к этому ресурсу.", "reason_unavailable": "Подключение к этому ресурсу через Isolate пока не настроено.",
        "connect": "Подключиться", "details": "Подробнее", "request_access": "Запросить доступ", "request_approval": "Запросить согласование",
        "explain_access": "Условия доступа",
        "step_up": "Подтвердить личность", "view": "Открыть ресурс", "add_favorite": "Добавить в избранное", "remove_favorite": "Убрать из избранного",
        "error": "Не удалось загрузить каталог. Нажмите «Повторить».",
        "preferences_error": "Не удалось сохранить избранное. Повторите попытку.", "preferences_load_error": "Не удалось загрузить избранное. Обновите страницу, чтобы снова его редактировать.",
        "session_expired": "Сеанс в Isolate завершился. Войдите снова.", "sign_in": "Войти",
        "forbidden": "Для просмотра каталога нужна соответствующая роль. Обратитесь к администратору.", "loaded": "Загружено ресурсов: {count}",
        "no_api": "Подключения через каталог пока не настроены. Обратитесь к администратору бастиона.",
        "admin_heading": "Управление бастионом", "admin_lead": "Здесь собраны инструменты, доступные вашей роли в Isolate.",
        "scope": "Роль в Isolate", "platform_admin": "Администратор платформы", "inventory": "Учёт ресурсов",
        "inventory_help": "Добавляйте и редактируйте ресурсы своих проектов.", "access": "Заявки на доступ", "access_help": "Рассматривайте заявки и проверяйте принятые решения.",
        "sessions": "Активные сессии", "sessions_help": "Проверяйте открытые подключения в доступных проектах.",
        "approvals": "Согласование подключений", "approvals_help": "Рассматривайте заявки на конкретные подключения.",
        "audit": "Журнал сессий", "audit_help": "Найдите завершённые подключения и их записи.",
        "grants": "Правила доступа", "grants_help": "Настройте, кому и к каким ресурсам разрешено подключаться.", "packages": "Пакеты доступа",
        "packages_help": "Объединяйте разрешения и назначайте их одним пакетом.", "matrix": "Матрица доступа", "matrix_help": "Проверьте, кому и какие ресурсы доступны.",
        "gitops": "GitOps", "gitops_help": "Сравните правила в Git с действующими и проверьте синхронизацию.", "users": "Пользователи",
        "users_help": "Просматривайте учётные записи и недавние действия.", "jobs": "Задания и регламенты", "jobs_help": "Запускайте регламенты, следите за заданиями и просматривайте вывод команд.",
        "alerts": "События и предупреждения", "alerts_help": "Проверьте события, требующие внимания.", "docs": "Документация", "docs_help": "Руководства по работе с Isolate, настройке и эксплуатации.",
        "open": "Открыть", "admin_notice": "Для подключения к ресурсам требуются отдельные правила доступа.",
    },
}


def _e(value):
    return html.escape(str(value), quote=True)


def _json_script(value):
    return (json.dumps(value, ensure_ascii=False).replace("&", "\\u0026")
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def administration_links(identity, config, labels):
    """Page-entry permissions determine navigation; destination routes recheck."""
    links = []
    for permission, path, key in (
        ("inventory.read", "/inventory", "inventory"), ("access.read", "/access", "access"),
        ("sessions.read", "/sessions/active", "sessions"),
        ("sessions.approve", "/session-approvals", "approvals"), ("audit.read", "/history", "audit"),
    ):
        if has_permission(identity, config, permission):
            links.append({"url": path, "label": labels[key], "description": labels[key + "_help"]})
    if is_platform_admin(identity, config):
        for path, key in (("/grants", "grants"), ("/packages", "packages"), ("/policy/matrix", "matrix"),
                          ("/policy/gitops", "gitops"), ("/users", "users"), ("/jobs", "jobs"),
                          ("/alerts", "alerts"), ("/docs", "docs")):
            links.append({"url": path, "label": labels[key], "description": labels[key + "_help"]})
    if config.get('api', {}).get('enabled'):
        russian = labels.get('administration') == 'Управление'
        if has_permission(identity, config, 'access.read'):
            links.append({'url': '/workspace/governance', 'label': 'Проверка выданных прав' if russian else 'Access lifecycle',
                'description': 'Проверяйте выданные права, сроки доступа подрядчиков и отзыв разрешений.' if russian else 'Owner reviews, contractors, expiry and offboarding.'})
        if is_platform_admin(identity, config):
            links.append({'url': '/policy/impact', 'label': 'Оценка изменений доступа' if russian else 'Policy impact preview',
                'description': 'Посмотрите, кто получит или потеряет доступ после изменения правила.' if russian else 'Review the effect of a policy change before applying it.'})
        if config.get('audit_index', {}).get('enabled') and has_permission(identity, config, 'audit.read'):
            links.append({'url': '/investigations', 'label': 'Расследования' if russian else 'Investigation',
                'description': 'Найдите связанные события: вход, проверку доступа и действия в сессии.' if russian else 'Related evidence from sign-in to result.'})
        if campaign_navigation_allowed(identity, config):
            links.append({'url': '/operations/campaigns', 'label': 'Поэтапные запуски' if russian else 'Staged operations',
                'description': 'Запустите регламент на пробной группе серверов, затем на остальных. Задайте условия остановки.' if russian else 'Canary, bounded batches and automatic stop conditions.'})
    return links


def campaign_navigation_allowed(identity, config):
    if not (config.get('api', {}).get('enabled') and config.get('campaigns', {}).get('enabled')):
        return False
    from isolate_mcp import IsolateMCPService, token_scopes
    service = IsolateMCPService(config, None)
    scopes = token_scopes(identity.get('raw_claims') or {})
    return any(service._runbook_access_error(identity, scopes, kind) is None for kind in ('read_only', 'operational'))


def _switcher(labels, can_manage, administration=False):
    result = '<nav class="workspace-switcher" aria-label="{}">'.format(_e(labels["workspace"]))
    for url, label, selected in (("/workspace", labels["workspace"], not administration),
                                 ("/workspace/admin", labels["administration"], administration)):
        if url.endswith("/admin") and not can_manage:
            continue
        result += '<a href="{}" {}>{}</a>'.format(url, 'aria-current="page"' if selected else "", _e(label))
    return result + "</nav>"


def register_workspace_routes(app, config, current_identity, csrf_token):
    from flask import abort, redirect, request
    import isolate_web as web

    def identity():
        current = current_identity()
        if current is None:
            return redirect("/login")
        if not isinstance(current, dict) or not current.get("keycloak_sub") or not current.get("username"):
            abort(403)
        if not (web.is_self_service_user(current, config) or is_platform_admin(current, config)
                or has_permission(current, config, "inventory.read")):
            abort(403)
        return current

    def render(title, body):
        page_config = dict(config, dashboard=dict(config.get("dashboard", {}), refresh_seconds=0))
        return web._html(title, body, config=page_config)

    @app.get("/workspace")
    def workspace_catalog():
        current = identity()
        if not isinstance(current, dict):
            return current
        locale = web._dashboard_locale(config)
        labels = WORDS.get(locale, WORDS["en"])
        managed = bool(administration_links(current, config, labels))
        bootstrap = {"labels": labels, "locale": locale, "csrf": csrf_token(),
            "resources_url": "/api/v1/workspace/resources", "preferences_url": "/api/v1/workspace/preferences",
            "enabled": config.get("api", {}).get("enabled", False),
            "initial": {key: str(request.args.get(key) or "")[:512] for key in ("q", "project", "protocol", "view")}}
        body = '<link rel="stylesheet" href="/static/workspace-catalog.css">'
        body += '<section class="workspace-page" aria-labelledby="workspace-title">'
        body += _switcher(labels, managed)
        body += '<header class="workspace-hero"><div><span class="workspace-eyebrow">{}</span><h1 id="workspace-title">{}</h1><p>{}</p></div><span class="workspace-identity">{}</span></header>'.format(
            _e(labels["eyebrow"]), _e(labels["heading"]), _e(labels["lead"]), _e(current["username"]))
        body += '<form id="workspace-filters" class="workspace-search" role="search"><label class="workspace-search-main"><span class="workspace-search-icon" aria-hidden="true">⌕</span><span class="sr-only">{}</span><input id="workspace-query" name="q" type="search" autocomplete="off" placeholder="{}" aria-describedby="workspace-search-hint"><kbd aria-hidden="true">Ctrl K</kbd></label>'.format(_e(labels["search"]), _e(labels["placeholder"]))
        body += '<label class="workspace-filter"><span>{}</span><input id="workspace-project" name="project" placeholder="{}" maxlength="128"></label>'.format(_e(labels["project"]), _e(labels["any_project"]))
        body += '<label class="workspace-filter"><span>{}</span><select id="workspace-protocol" name="protocol">'.format(_e(labels["protocol"]))
        for value, label in (("", labels["any_protocol"]), ("ssh", "SSH"), ("http", "HTTP"), ("kubernetes", "Kubernetes"), ("postgresql", "PostgreSQL"), ("mysql", "MySQL")):
            body += '<option value="{}">{}</option>'.format(_e(value), _e(label))
        body += '</select></label><button class="sr-only" type="submit">{}</button></form>'.format(_e(labels["search"]))
        body += '<div class="workspace-toolbar"><div class="workspace-views" role="group" aria-label="{}">'.format(_e(labels["workspace"]))
        for value, key in (("all", "all"), ("favorites", "favorites"), ("recent", "recent")):
            body += '<button type="button" data-workspace-view="{}" aria-pressed="{}">{}</button>'.format(value, "true" if value == "all" else "false", _e(labels[key]))
        body += '</div><span id="workspace-count" class="workspace-count"></span></div>'
        body += '<p id="workspace-search-hint" class="workspace-keyboard-hint">{}</p>'.format(_e(labels["search_hint"]))
        body += '<div id="workspace-feedback" class="workspace-feedback" role="alert" hidden></div><div id="workspace-status" class="workspace-status" role="status" aria-live="polite">{}</div>'.format(_e(labels["loading"]))
        body += '<div id="workspace-grid" class="workspace-resource-grid" role="list" aria-label="{}" aria-busy="true"></div><div id="workspace-empty" class="workspace-empty" hidden></div>'.format(_e(labels["all"]))
        body += '<div class="workspace-pagination"><button id="workspace-more" class="button secondary" type="button" hidden>{}</button></div>'.format(_e(labels["more"]))
        body += ('<noscript><p class="notice">Для поиска ресурсов нужен JavaScript. <a href="/me">Открыть список серверов</a>.</p></noscript></section>'
                 if locale == "ru" else
                 '<noscript><p class="notice">JavaScript is required for resource search. <a href="/me">Open the server catalogue</a>.</p></noscript></section>')
        body += '<script type="application/json" id="workspace-config">{}</script><script src="/static/workspace-catalog.js" defer></script>'.format(_json_script(bootstrap))
        return render(labels["workspace"], body)

    @app.get("/workspace/admin")
    def workspace_administration():
        current = identity()
        if not isinstance(current, dict):
            return current
        locale = web._dashboard_locale(config)
        labels = WORDS.get(locale, WORDS["en"])
        links = administration_links(current, config, labels)
        if not links:
            abort(403)
        body = '<link rel="stylesheet" href="/static/workspace-catalog.css"><section class="workspace-page" aria-labelledby="workspace-title">'
        body += _switcher(labels, True, administration=True)
        body += '<header class="workspace-hero"><div><span class="workspace-eyebrow">ISOLATE CONTROL</span><h1 id="workspace-title">{}</h1><p>{}</p></div></header>'.format(_e(labels["admin_heading"]), _e(labels["admin_lead"]))
        if is_platform_admin(current, config):
            roles = labels["platform_admin"]
        else:
            from isolate_profile_ui import portal_role_label
            roles = ", ".join(portal_role_label(role, locale) if locale == "ru" else role for role in role_names(current, config))
        body += '<p class="workspace-role"><span>{}</span><strong>{}</strong></p>'.format(_e(labels["scope"]), _e(roles))
        body += '<div class="workspace-admin-grid">'
        for item in links:
            body += '<a class="workspace-admin-card" href="{}"><span class="workspace-admin-card-label">{}</span><span class="workspace-admin-card-description">{}</span><span class="workspace-admin-open">{} <span aria-hidden="true">↗</span></span></a>'.format(_e(item["url"]), _e(item["label"]), _e(item["description"]), _e(labels["open"]))
        body += '</div><p class="workspace-policy-note">{}</p></section>'.format(_e(labels["admin_notice"]))
        return render(labels["administration"], body)
