"""Personal settings rendered from an authenticated portal identity."""

from html import escape

from isolate_oidc import identity_provider_config
from isolate_permissions import role_names
from isolate_ui_icons import icon


_WORDS = {
    "en": {
        "title": "My profile",
        "intro": "Manage the way Isolate looks and find your own activity.",
        "account": "Account",
        "provider": "Sign-in provider",
        "roles": "Portal roles",
        "groups": "Identity provider groups",
        "member": "User",
        "managed": "Change account details, password and MFA in your identity provider.",
        "appearance": "Appearance",
        "theme": "Theme",
        "system": "System",
        "light": "Light",
        "dark": "Dark",
        "language": "Interface language",
        "appearance_note": "Theme is saved in this browser. Language is kept when you sign in again.",
        "activity": "My activity",
        "resources": "Accessible resources",
        "favorites": "Favorites",
        "recent": "Recent connections",
        "requests": "Access requests",
        "approvals": "Session approvals",
        "sessions": "Active sessions",
        "history": "Connection history",
        "terminal": "Terminal preferences",
        "terminal_hint": "In the terminal toolbar, choose Settings to adjust the font, palette and history buffer.",
        "terminal_open": "Open Web SSH",
    },
    "ru": {
        "title": "Личный кабинет",
        "intro": "Настройки интерфейса, данные учётной записи, подключения и заявки.",
        "account": "Учётная запись",
        "provider": "Служба входа",
        "roles": "Роли в Isolate",
        "groups": "Группы учётной записи",
        "member": "Пользователь",
        "managed": "Пароль, данные учётной записи и второй фактор (MFA) меняются в настройках службы входа.",
        "appearance": "Оформление",
        "theme": "Тема",
        "system": "Как в системе",
        "light": "Светлая",
        "dark": "Тёмная",
        "language": "Язык интерфейса",
        "appearance_note": "Тема сохраняется в этом браузере, а язык — при повторном входе в Isolate.",
        "activity": "Мои ресурсы и подключения",
        "resources": "Доступные ресурсы",
        "favorites": "Избранное",
        "recent": "Недавние подключения",
        "requests": "Заявки на доступ",
        "approvals": "Согласование подключений",
        "sessions": "Активные сессии",
        "history": "История подключений",
        "terminal": "Настройки терминала",
        "terminal_hint": "В настройках Web SSH можно выбрать шрифт, тему и число строк в буфере прокрутки.",
        "terminal_open": "Открыть Web SSH",
    },
}

_ROLES_RU = {
    "admin": "Администратор",
    "project-owner": "Владелец проекта",
    "approver": "Согласующий",
    "auditor": "Аудитор",
    "inventory-operator": "Оператор учёта ресурсов",
}


def portal_role_label(role, locale):
    """Render a role name for display while keeping the canonical role ID unchanged."""
    return _ROLES_RU.get(role, role) if locale == "ru" else role.replace("-", " ").capitalize()


def _link(href, label, symbol):
    return '<a href="{}">{}<span>{}</span>{}</a>'.format(
        escape(href, quote=True), icon(symbol), escape(label), icon("chevron-right", "profile-chevron")
    )


def render_profile(config, identity, locale, *, can_browse, can_terminal, catalog_url="/workspace"):
    """Build a settings view using existing account and workspace preferences."""
    w = _WORDS.get(locale, _WORDS["en"])
    provider = identity_provider_config(config)
    provider_name = str(provider.get("display_name") or "OpenID Connect")
    roles = role_names(identity, config)
    role_labels = [portal_role_label(role, locale) for role in roles]
    groups = identity.get("groups") or ()
    if not isinstance(groups, (list, tuple)):
        groups = ()

    account_rows = (
        (w["provider"], provider_name),
        (w["roles"], ", ".join(role_labels) or w["member"]),
        (w["groups"], ", ".join(group for group in groups if isinstance(group, str)) or "—"),
    )
    details = "".join('<div><dt>{}</dt><dd>{}</dd></div>'.format(escape(label), escape(value))
                      for label, value in account_rows)
    language_links = "".join(
        '<a href="/me/profile?lang={}" lang="{}"{}>{}</a>'.format(
            language, language, ' aria-current="true"' if language == locale else "", name
        ) for language, name in (("ru", "Русский"), ("en", "English"))
    )
    theme_options = "".join('<option value="{}">{}</option>'.format(value, escape(w[value]))
                            for value in ("system", "light", "dark"))

    activity = []
    if can_browse:
        activity.append((catalog_url, w["resources"], "server"))
        if catalog_url == "/workspace":
            activity += [
                ("/workspace?view=favorites", w["favorites"], "file-text"),
                ("/workspace?view=recent", w["recent"], "clock"),
            ]
        activity += [
            ("/me/access", w["requests"], "key-round"),
            ("/me/session-approvals", w["approvals"], "shield-check"),
            ("/me/sessions", w["sessions"], "activity"),
            ("/me/history", w["history"], "file-clock"),
        ]
    activity_panel = ""
    if activity:
        links = "".join("<li>{}</li>".format(_link(href, label, symbol)) for href, label, symbol in activity)
        activity_panel = '<section class="panel"><h2>{}</h2><ul class="profile-links">{}</ul></section>'.format(
            escape(w["activity"]), links
        )
    terminal_panel = ""
    if can_terminal:
        terminal_panel = ('<section class="panel"><h2>{}</h2><p>{}</p><ul class="profile-links"><li>{}</li></ul>'
                          '</section>').format(escape(w["terminal"]), escape(w["terminal_hint"]),
                                              _link("/me/terminal", w["terminal_open"], "terminal"))

    return """<link rel="stylesheet" href="/static/isolate-profile.css">
<header class="profile-heading"><h1>{title}</h1><p class="page-lead">{intro}</p></header>
<div class="profile-grid">
  <section class="panel" aria-labelledby="profile-appearance">
    <h2 id="profile-appearance">{appearance}</h2>
    <div class="profile-preferences">
      <label for="profile-theme">{theme}</label>
      <select id="profile-theme" data-theme-select>{theme_options}</select>
      <span id="profile-language">{language}</span>
      <nav class="profile-languages" aria-labelledby="profile-language">{language_links}</nav>
    </div>
    <p class="profile-note">{appearance_note}</p>
  </section>
  <section class="panel" aria-labelledby="profile-account">
    <h2 id="profile-account">{account}</h2>
    <p class="profile-account-name">{username}</p>
    <dl class="profile-identity">{details}</dl>
    <p class="profile-note">{managed}</p>
  </section>
  {activity_panel}{terminal_panel}
</div>""".format(**{key: escape(value) for key, value in w.items()},
                 username=escape(str(identity.get("username") or "—")), details=details,
                 language_links=language_links, theme_options=theme_options,
                 activity_panel=activity_panel, terminal_panel=terminal_panel)
