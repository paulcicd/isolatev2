"""Locally served Lucide symbols for the shared dashboard shell."""

import html
import re


def icon(name, css_class=""):
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError("invalid icon name")
    return ('<svg class="ui-icon {}" width="18" height="18" fill="none" stroke="currentColor" '
            'stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" '
            'aria-hidden="true" focusable="false"><use href="/static/vendor/lucide/sprite.svg#{}">'
            '</use></svg>').format(html.escape(css_class, quote=True), name)
