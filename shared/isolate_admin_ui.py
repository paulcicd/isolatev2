"""Presentation helpers for the administrative workspaces."""

import html
from urllib.parse import urlencode

from isolate_ui_icons import icon


def admin_heading(title, description, actions=""):
    return '<header class="admin-heading"><div><h1>{}</h1><p>{}</p></div>{}</header>'.format(
        html.escape(title), html.escape(description),
        '<div class="admin-actions">{}</div>'.format(actions) if actions else "",
    )


def export_menu(path, args, locale):
    name = "Экспорт" if locale == "ru" else "Export"
    links = []
    for output_format in ("csv", "json"):
        href = path + "?" + urlencode(dict(args, format=output_format))
        links.append('<a class="admin-button" href="{}">{}</a>'.format(html.escape(href), output_format.upper()))
    return ('<details class="admin-disclosure admin-export"><summary class="admin-button">{} {} {}</summary>'
            '<div class="admin-popover">{}</div></details>').format(
        icon("arrow-up-right"), name, icon("chevron-down"), "".join(links),
    )


def admin_empty(copy):
    return '<p class="admin-empty" role="status">{}</p>'.format(html.escape(copy))
