"""Standalone error pages that render without the dashboard or its services."""

import html

from isolate_ui_icons import icon


_MESSAGES = {
    "en": {
        400: ("We could not process the request", "Check the address or the form values, then try again."),
        500: ("Isolate hit an internal error", "If the error recurs, share the request ID with your administrator."),
        "catalogue": "Open resource catalogue", "home": "Return to Isolate", "request": "Request ID",
    },
    "ru": {
        400: ("Не удалось обработать запрос", "Проверьте адрес или данные в форме, затем повторите действие."),
        500: ("Внутренняя ошибка Isolate", "Если ошибка повторится, сообщите администратору ID запроса."),
        "catalogue": "Открыть каталог ресурсов", "home": "Вернуться в Isolate", "request": "ID запроса",
    },
}


def render_error_page(status, locale, request_id):
    language = locale if locale in _MESSAGES else "en"
    messages = _MESSAGES[language]
    title, detail = messages[status]
    action_url, action_label = ("/workspace", messages["catalogue"]) if status == 500 else ("/", messages["home"])
    return """<!doctype html>
<html lang="{language}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{title} · Isolate</title>
  <script src="/static/precision-theme.js"></script>
  <link rel="stylesheet" href="/static/isolate-error.css">
</head>
<body>
  <header class="error-brand">{brand_icon}<strong>isolate <span>/</span></strong></header>
  <main>
    <section data-status="{status}" aria-labelledby="error-title">
      <p class="error-status">{status_icon}<code>HTTP {status}</code></p>
      <h1 id="error-title">{title}</h1>
      <p class="error-detail">{detail}</p>
      <a class="error-action" href="{action_url}">{action_label}</a>
      {reference}
    </section>
  </main>
</body>
</html>""".format(
        language=language, status=status, title=html.escape(title), detail=html.escape(detail),
        brand_icon=icon("shield-check"), status_icon=icon("server" if status == 500 else "shield-alert"),
        action_url=action_url, action_label=html.escape(action_label),
        reference='<div class="error-reference"><span>{}</span><code>{}</code></div>'.format(
            html.escape(messages["request"]), html.escape(request_id),
        ) if request_id else "",
    )
