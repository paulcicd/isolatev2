"""Bilingual static presentation copy for access and operations workflows.

Call ``workflow_copy`` on a source literal before interpolating resource or user
values. It deliberately does not process completed HTML, API data or evidence.
"""

import html
from html.parser import HTMLParser
import re

COPY_RU = {
    'System uptime and load': 'Время работы и средняя нагрузка',
    'Filesystem usage': 'Свободное место на файловых системах',
    'Filesystem inode usage': 'Свободные и занятые inode',
    'Memory usage': 'Использование памяти',
    'Top CPU processes': 'Процессы с наибольшей нагрузкой на CPU',
    'Top memory processes': 'Процессы с наибольшим потреблением памяти',
    'Top snapshot': 'Снимок top',
    'Atop snapshot': 'Снимок atop',
    'Service status': 'Состояние службы',
    'Service active state': 'Проверить, запущена ли служба',
    'Service journal tail': 'Последние записи журнала службы',
    'Failed services': 'Службы в состоянии failed',
    'Listening sockets': 'Сетевые сокеты в режиме LISTEN',
    'Network addresses': 'Сетевые адреса',
    'Network routes': 'Сетевые маршруты',
    'Restart service': 'Перезапуск службы',
    'Flush system DNS cache': 'Очистка системного кеша DNS',
    'Deployment diagnostics': 'Диагностика развёртывания',
    'Investigation': 'Расследование',
    'Request access': 'Запросить доступ',
    'Request session': 'Запросить согласование подключения',
    'Contact an administrator': 'Обратиться к администратору',
    'Contact the resource owner': 'Обратиться к владельцу ресурса',
    'Verify identity': 'Войти повторно',
    'Connect': 'Подключиться',
    'View resource': 'Открыть ресурс',
    'The selected active rule is checked first. Actions from other rules are not combined.': 'Isolate проверяет действие по одному выбранному правилу доступа.',
    'Access is rechecked when an operation starts and while it runs. This explanation does not grant access.': 'При запуске операции и во время её выполнения Isolate проверяет доступ заново.',
    'No active assignment matches this resource.': 'Действующие правила не дают вашей учётной записи доступ к этому ресурсу.',
    'The selected rule does not allow the requested action.': 'Это действие запрещено выбранным правилом.',
    'The selected policy does not resolve a remote account.': 'Для подключения по этому правилу не задана учётная запись на ресурсе.',
    'The selected active rule permits this action.': 'Выбранное правило разрешает это действие.',
    'Access for this identity has been ended by a lifecycle decision.': 'Доступ для этой учётной записи отозван.',
    'Current access lifecycle evidence could not be verified.': 'Не удалось проверить, действуют ли ограничения доступа.',
    'No access lifecycle restriction blocks this identity for the resource project.': 'Для этой учётной записи доступ к проекту не отозван.',
    'This workload identity is not enabled for the requested action.': 'Действие запрещено для этой сервисной учётной записи.',
    'The principal type permits this action.': 'Действие разрешено для этого типа учётной записи.',
    'The resource is in maintenance.': 'Ресурс на техническом обслуживании.',
    'The resource is not blocked by maintenance.': 'Ресурс доступен для новых подключений.',
    'New connections are enabled.': 'Новые подключения разрешены.',
    'New connections are administratively disabled.': 'Новые подключения отключены администратором.',
    'The connection services are enabled.': 'На бастионе включены службы, необходимые для подключения.',
    'The connection services are not enabled.': 'На бастионе отключены службы, необходимые для подключения.',
    'The resource protocol configuration needs administrator attention.': 'Попросите администратора проверить настройки протокола для этого ресурса.',
    'The resource protocol has a valid inventory-bound configuration.': 'Протокол настроен для этого ресурса в каталоге.',
    'The SSH target port is permitted.': 'Подключение к этому порту SSH разрешено.',
    'The SSH target port is not permitted.': 'Подключение к этому порту SSH запрещено.',
    'This SSH channel is enabled.': 'Канал SSH разрешён в настройках ресурса.',
    'This channel requires an enabled compatible SSH profile.': 'Включите в настройках ресурса профиль SSH, который разрешает этот канал.',
    'The Kubernetes operation is enabled.': 'Ресурс поддерживает эту операцию Kubernetes.',
    'This Kubernetes operation is not enabled for the resource.': 'Эта операция Kubernetes отключена в настройках ресурса.',
    'Fresh authentication at the required assurance level is needed.': 'Войдите ещё раз и пройдите дополнительную проверку при входе.',
    'Identity assurance configuration needs administrator attention.': 'Попросите администратора проверить требования к повторной аутентификации.',
    'The current authentication meets the configured assurance requirement.': 'Вы вошли с требуемым способом аутентификации.',
    'A separate approval is required for each new session.': 'Каждое новое подключение нужно согласовать отдельно.',
    'No separate session approval is required.': 'Подключение можно начать без отдельного согласования.',
    'Fresh authentication is required.': 'Войдите в Isolate ещё раз.',
    'Current identity, lifecycle or route requirements prevent access. Ask an administrator to review the resource.': 'Проверка учётной записи, ограничений доступа или подключения завершилась ошибкой. Попросите администратора проверить настройки ресурса.',
    'Current identity and route preflight passed.': 'Учётная запись и настройки подключения прошли предварительную проверку.',
    'Access is available.': 'Доступ разрешён.',
    'Policy permits this action; operation-specific submission and channel checks still apply.': 'Правило разрешает действие. При запуске Isolate ещё проверит параметры операции и соединения.',
    'Group/role rows model policy principals, not a complete list of people. Combined memberships and current IdP membership must be reviewed separately.': 'Прогноз показывает права по отдельным группам и ролям. Проверьте в IdP состав групп и сочетание прав у конкретных пользователей.',
    'Staged runbook operations': 'Поэтапные запуски',
    'Run a small canary first, then bounded batches. Unknown outcomes always stop expansion; jobs are never retried automatically.': 'Сначала запустите регламент на нескольких серверах. Если все команды отработают успешно, Isolate продолжит запуск группами. При неизвестном результате следующие группы не запускаются. Повторный запуск выполняют вручную.',
    'Target host IDs, separated by commas': 'ID серверов через запятую',
    'Parameters (JSON)': 'Параметры (JSON)',
    'Canary hosts': 'Число серверов для пробы',
    'Batch size': 'Серверов на каждом следующем этапе',
    'Allowed failures after canary': 'Допустимое число ошибок после пробы',
    'Maximum failure percentage': 'Допустимая доля ошибок, %',
    'Review plan': 'Проверить план',
    'No runbooks are currently available for your identity. Existing campaign history remains available below.': 'Вашей учётной записи пока недоступны регламенты. Прошлые запуски можно открыть в истории.',
    'Campaign history': 'История запусков',
    'Review campaign': 'Проверьте план запуска',
    'Canary: {} host(s). Later batches: {}. Failure budget: {}. Maximum failure rate: {}%.': 'Серверов для пробы — {}. Серверов на следующем этапе — {}. Допустимое число ошибок — {}. Допустимая доля ошибок — {}%.',
    'The canary must succeed completely. Expired or revoked authorization, uncertain outcomes and configured failure thresholds stop new work.': 'Для перехода к следующему этапу команды должны отработать на всех пробных серверах. Новые задания не запустятся, если закончится срок доступа, доступ отзовут, результат окажется неизвестен или число ошибок превысит заданный порог.',
    'I reviewed the targets and stop conditions': 'Я проверил список серверов и условия остановки',
    'Start canary': 'Начать пробный запуск',
    'Campaign status': 'Ход выполнения',
    'Investigate campaign': 'Открыть расследование',
    'All campaigns': 'Все запуски',
    'Stop future batches and request cancellation of active jobs': 'Не запускать следующие группы и запросить отмену текущих заданий',
    'Stop campaign': 'Остановить запуск',
    'Campaign {}': 'Запуск {}',
    'Host {}': 'Сервер {}',
    'stage {}': 'этап {}',
    'Job {}': 'Задание {}',
    'View output': 'Открыть вывод команды',
    'Runbook': 'Регламент (Runbook)',
    'Access lifecycle': 'Проверка выданных прав',
    'Review current access, track temporary assignments and end access with durable offboarding decisions.': 'Проверяйте действующие права, выдавайте временный доступ и отзывайте его, когда он больше не нужен.',
    'Administration': 'Управление',
    'Resources': 'Ресурсы',
    'Review schedule': 'График проверок доступа',
    'Last completed': 'Последняя проверка',
    'Next review due': 'Следующая проверка',
    'Due and expiring': 'Проверки и доступы с истекающим сроком',
    'No outstanding reminders.': 'Ближайших проверок и истекающих назначений нет.',
    'Start an owner review': 'Проверка прав владельцем',
    'A review freezes the visible grants. Keeping access records a decision without extending its expiry. Changed grants require a fresh review.': 'При начале проверки Isolate сохранит доступные вам правила. Если правило изменится, его нужно проверить заново. Решение сохранить доступ оставляет в силе прежний срок.',
    'Start review': 'Начать проверку',
    'Temporary or contractor assignment': 'Выдать временный доступ',
    'Assignments require an immutable provider-bound subject, expire within 90 days, and never grant sudo/root. Expiry does not remove any independent group access.': 'Укажите постоянный ID пользователя в IdP и срок до 90 дней. Временное назначение действует с обычными правами, без sudo и root. Права по отдельным групповым правилам сохранятся после окончания этого назначения.',
    'Stable subject': 'Постоянный ID пользователя',
    'Display username': 'Имя для отображения',
    'Target account': 'Учётная запись на ресурсе',
    'Expires in days': 'Срок действия в днях',
    'Actions (comma separated)': 'Действия через запятую',
    'Create assignment': 'Создать назначение',
    'End access': 'Отозвать доступ',
    'Offboarding blocks this subject even when group or externally managed grants still exist. It does not delete the IdP account or rewrite GitOps policy. Reboarding needs an independent reviewed procedure.': 'Отзыв блокирует подключение через Isolate, даже если доступ остаётся в групповых или внешних правилах. Учётная запись в IdP и политика GitOps сохраняются. Возврат доступа требует отдельного согласования.',
    'End project access': 'Отозвать доступ к проекту',
    'Global offboarding': 'Отзыв доступа ко всем проектам',
    'End all Isolate access': 'Отозвать весь доступ через Isolate',
    'Owner reviews': 'Проверки владельцами проектов',
    'Owner: {} · Due: {}': 'Ответственный: {} · Срок: {}',
    'Grant #{}': 'Правило №{}',
    'Awaiting review': 'Ждёт проверки',
    'Grant timeline': 'История правила',
    'Keep current access': 'Сохранить текущий доступ',
    'Revoke this rule': 'Отозвать правило',
    'Confirm externally removed': 'Подтвердить, что внешнее правило удалено',
    'Record decision': 'Записать решение',
    'Decision': 'Решение',
    'Assignments': 'Назначения',
    'User / project': 'Пользователь / проект',
    'Expiry': 'Действует до',
    'Status': 'Состояние',
    'Revoke assignment': 'Отозвать назначение',
    'Review candidates': 'Правила, которые стоит проверить',
    'These findings are prompts for an owner review, not proof that access is unused or unnecessary. No rights are removed automatically.': 'Эти признаки помогают найти правила для проверки. Решение о сохранении или отзыве каждого правила принимает владелец.',
    'Offboarding decisions': 'История отзыва доступа',
    'blocked': 'заблокирован',
    'Reason': 'Обоснование',
    'Confirm this access change': 'Я проверил, какие права изменятся',
    'Access explanation': 'Условия доступа',
    'Selected rule': 'Выбранное правило',
    'Back to resources': 'К ресурсам',
    'Policy impact preview': 'Что изменится в доступе',
    'Compare a proposed assignment change with current policy before saving it.': 'Проверьте, кому даст или закроет доступ предлагаемое изменение правила.',
    'This page only previews. Group and role rows are policy scenarios, not a complete IdP membership census. Current lifecycle restrictions, MFA, session approvals and target settings still apply.': 'Проверка не применяет изменения. Результаты по группам и ролям показывают права по отдельности, без учёта членства в IdP. Ограничения доступа, MFA, согласование подключений и настройки ресурсов действуют как обычно.',
    'Existing grant ID': 'ID правила доступа',
    'Required for replace/remove': 'Обязательно для замены или удаления',
    'Limit to project': 'Ограничить проектом',
    'Optional exact project': 'Точное название проекта (необязательно)',
    'Proposed grant JSON (a partial object is allowed for replacement)': 'Правило в JSON (при замене достаточно изменённых полей)',
    'Preview impact': 'Проверить изменения',
    'Back to grants': 'К правилам доступа',
    'Preview result': 'Какие права изменятся',
    'Gained: {} · Lost: {} · Changed: {}': 'Выдано: {} · Отозвано: {} · Изменено: {}',
    'Principal scenario': 'Пользователь, группа или роль',
    'Before': 'До изменения',
    'After': 'После изменения',
    'Denied: ': 'Отказ: ',
    'rule {}': 'правило {}',
    'No effective policy changes were found in this snapshot.': 'При текущих настройках это правило не изменит доступ.',
    'Result rows are truncated; use an exact project filter to review a smaller change.': 'Результатов больше, чем можно показать. Укажите точное название проекта, чтобы сузить проверку.',
    'Preview unavailable: ': 'Не удалось проверить изменения: ',
    'Enter a valid JSON grant object.': 'Введите корректный JSON-объект правила.',
    'Check investigation filters': 'Проверьте фильтры расследования',
    'Person / stable ID': 'Пользователь / постоянный ID',
    'Resource ID': 'ID ресурса',
    'From (UTC)': 'С (UTC)',
    'To (UTC)': 'По (UTC)',
    'Session approval': 'Согласование подключения',
    'Access request': 'Заявка на доступ',
    'Runbook campaign': 'Поэтапный запуск',
    'Sign-in session': 'Сеанс входа в Isolate',
    'Session': 'Сессия',
    'Job': 'Задание',
    'Grant': 'Правило',
    'Project': 'Проект',
    'Resource': 'Ресурс',
    'Action': 'Действие',
    'Change': 'Изменение',
    'Due': 'Срок',
    'Add': 'Добавить',
    'Replace': 'Заменить',
    'Remove': 'Удалить',
    'Start the local Isolate proxy. {}': 'Запустите локальный прокси Isolate. {}',
    'Isolate supplies the database credential. Use the private local capability file as your client password and verify the gateway database certificate with native TLS. Your database identity is selected by policy.': 'Isolate сам передаёт учётные данные серверу БД. Возьмите пароль для клиента из локального файла доступа и включите в клиенте проверку TLS-сертификата шлюза. Учётную запись БД определяет правило доступа.',
    'Connect your database client to 127.0.0.1:15432 with native TLS and your database identity.': 'Подключите клиент БД к 127.0.0.1:15432 с TLS под указанной учётной записью БД.',
    'Database identity: ': 'Учётная запись БД: ',
    'Open this internal application on its isolated application domain. Current access is checked throughout the session.': 'Откройте внутреннее приложение по адресу на выделенном домене. Isolate проверяет доступ, пока подключение активно.',
    'Use this authenticated API endpoint from your client. Sign in with ': 'Укажите этот адрес API в клиенте. Для входа выполните ',
    '; bearer credentials remain in your private client cache.': '; токены хранятся в защищённом кеше клиента.',
    'Configure kubectl with the Isolate ExecCredential helper and the trusted gateway CA. Your verified identity is impersonated upstream.': 'Настройте в kubectl плагин Isolate ExecCredential и укажите доверенный CA шлюза. Isolate передаст Kubernetes подтверждённое имя и группы пользователя.',
    'Configured operations: {}. Each operation also requires its own grant action. Use a kubectl client with WebSocket streaming enabled.': 'Операции, включённые на ресурсе: {}. Правило доступа должно отдельно разрешать каждую нужную операцию. Используйте kubectl с поддержкой потокового обмена по WebSocket.',
}


def workflow_copy(config, source):
    """Translate developer-owned literals, before any data interpolation."""
    from isolate_web import _dashboard_locale
    if _dashboard_locale(config) != 'ru':
        return source
    if source in COPY_RU:
        return COPY_RU[source]
    # HTML literals combine several pieces of copy. Longest-first replacement
    # keeps phrases intact and leaves structural attributes/field names alone.
    for english in sorted(COPY_RU, key=len, reverse=True):
        source = source.replace(english, COPY_RU[english])
    return source


def workflow_value(config, value):
    """Localize a known machine status or fixed diagnostic, never substrings."""
    from isolate_web import _dashboard_locale
    if _dashboard_locale(config) != 'ru':
        return value
    labels = {
        'active': 'Действует', 'completed': 'Завершено', 'failed': 'Ошибка',
        'cancelled': 'Отменено', 'timed_out': 'Истекло время ожидания', 'queued': 'В очереди',
        'held': 'Ожидает этапа', 'claimed': 'Задание принято', 'running': 'Выполняется',
        'pending': 'Ожидает решения', 'approved': 'Согласовано', 'denied': 'Отклонено', 'closed': 'Закрыто',
        'recovery_required': 'Требуется проверка результата', 'open': 'Открыто',
        'revoked': 'Отозвано', 'expired': 'Срок истёк', 'scheduled': 'Запланировано',
        'keep': 'Сохранить', 'revoke': 'Отозвать', 'removed': 'Удалено из внешней политики',
        'passed': 'Пройдено', 'required': 'Требуется',
        'review_due': 'Пора проверить', 'review_overdue': 'Срок проверки прошёл', 'periodic_review_due': 'Плановая проверка',
        'assignment_expiring': 'Срок доступа скоро истечёт', 'no_expiry': 'Без срока действия',
        'privileged_identity': 'Привилегированная учётная запись',
        'broad_project_scope': 'Доступ ко многим проектам', 'username_only_binding': 'Правило привязано только к имени пользователя',
        'gained': 'Добавлено', 'lost': 'Отозвано', 'changed': 'Изменено',
    }
    return labels.get(value, COPY_RU.get(value, value))


FIELD_HINTS = {
    'runbook_id': ('Choose a procedure allowed by your current role.', 'Выберите регламент, который разрешено запускать с вашими правами.'),
    'host_ids': ('Use inventory IDs separated by commas. Every selected target is checked again before execution.', 'Укажите ID серверов из каталога через запятую. При запуске Isolate проверит доступ к каждому из них.'),
    'parameters': ('Enter a JSON object using the procedure parameter names. Use {} when no parameters are needed.', 'Введите параметры регламента в виде JSON-объекта. Для запуска без параметров оставьте {}.'),
    'canary_count': ('All canary targets must succeed before later batches start.', 'Следующий этап начнётся, если команда успешно отработает на всех пробных серверах.'),
    'batch_size': ('Maximum number of targets released in each later stage.', 'Сколько серверов обрабатывать на каждом этапе после пробного запуска.'),
    'failure_budget': ('Known failed commands allowed after the canary. Zero stops on the first failure.', 'Сколько подтверждённых ошибок команда может вернуть после пробного запуска. При 0 первая ошибка остановит запуск следующих групп.'),
    'max_failure_percent': ('Cumulative failure limit from 0 to 100 percent. Unknown outcomes always stop expansion.', 'Допустимая доля ошибок за весь запуск от 0 до 100%. При неизвестном результате Isolate остановит запуск следующих групп независимо от этого порога.'),
    'confirm': ('Review the target scope and consequences before confirming.', 'Перед подтверждением проверьте список затронутых ресурсов и последствия действия.'),
    'project': ('Use the exact project name available to your role.', 'Введите точное название проекта из доступных вам ресурсов.'),
    'subject_id': ('Use the immutable provider-bound subject ID from trusted identity records.', 'Скопируйте постоянный ID учётной записи из IdP.'),
    'username': ('Display label only. The immutable subject determines the identity.', 'Это имя увидит инженер в интерфейсе. Isolate определяет учётную запись по постоянному ID.'),
    'remote_user': ('Select an existing target account with the minimum required privileges.', 'Укажите учётную запись, которая уже есть на ресурсе и имеет только необходимые права.'),
    'expires_days': ('Assignment duration from 1 to 90 days. Keeping access in a review does not extend it.', 'Укажите срок от 1 до 90 дней. Если при проверке оставить доступ, срок останется прежним.'),
    'allowed_actions': ('List protocol actions separated by commas, for example ssh,webssh.', 'Укажите разрешённые действия через запятую, например ssh,webssh.'),
    'reason': ('Explain the business need or reference the approved ticket. It is retained in the scoped access record.', 'Укажите, зачем нужен доступ, или добавьте номер согласованной заявки. Isolate сохранит обоснование вместе с назначением.'),
    'decision': ('Keep preserves expiry. Revoke changes this rule. External removal requires the rule to be absent.', 'При сохранении доступа срок останется прежним. Для правила из внешней политики сначала удалите его в источнике, затем подтвердите здесь.'),
    'mode': ('Preview adding, replacing or removing a rule. This form does not apply policy changes.', 'Выберите изменение для проверки. Действующие правила останутся без изменений.'),
    'grant_id': ('Existing numeric rule ID. Required when replacing or removing a rule.', 'При замене или удалении укажите числовой ID действующего правила.'),
    'grant': ('Use grant field names in a valid JSON object. For replacement, omitted fields retain their current values.', 'Укажите поля правила в JSON. При замене достаточно перечислить поля, которые хотите изменить.'),
    'kind': ('Choose which lifecycle object to follow. Visibility remains limited to your current permissions.', 'Выберите, за чем хотите проследить. Поиск покажет только доступные вам события.'),
    'id': ('Exact identifier of the selected object, such as a job or campaign ID.', 'Введите точный ID объекта, например задания или поэтапного запуска.'),
    'subject': ('Filter by immutable subject ID, including authorized decisions about that person.', 'Введите постоянный ID пользователя, чтобы найти его события и доступные вам решения по его правам.'),
    'host_id': ('Numeric inventory resource ID.', 'Числовой ID ресурса в каталоге.'),
    'from': ('Start of the time range in UTC.', 'Начало периода в UTC.'),
    'to': ('End of the time range in UTC.', 'Конец периода в UTC.'),
    'status': ('Choose a current status, or show all records.', 'Выберите статус или оставьте «Все».'),
}


def workflow_hints(config, body):
    """Add visible, associated help to known workflow controls without changing data."""
    from isolate_web import _dashboard_locale
    language = 1 if _dashboard_locale(config) == 'ru' else 0

    class FormHints(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.parts = []
            self.count = 0
            self.pending = []
            self.labels = []

        def handle_starttag(self, tag, attrs):
            source = self.get_starttag_text()
            values = dict(attrs)
            if tag == 'label':
                self.labels.append([])
            hint = FIELD_HINTS.get(values.get('name'))
            if tag in ('input', 'select', 'textarea') and hint and values.get('type') != 'hidden' and 'aria-describedby' not in values:
                self.count += 1
                identifier = 'workflow-help-' + str(self.count)
                source = re.sub(r'\s*/?>$', lambda match: ' aria-describedby="' + identifier + '"' + match[0], source)
                help_html = '<small class="field-hint" id="{}">{}</small>'.format(identifier, html.escape(hint[language]))
                if self.labels:
                    self.labels[-1].append(help_html)
                elif tag == 'input':
                    source += help_html
                else:
                    self.pending.append((tag, help_html))
            self.parts.append(source)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            self.parts.append('</' + tag + '>')
            if tag == 'label' and self.labels:
                self.parts.extend(self.labels.pop())
            if self.pending and self.pending[-1][0] == tag:
                self.parts.append(self.pending.pop()[1])

        def handle_data(self, data):
            self.parts.append(data)

        def handle_entityref(self, name):
            self.parts.append('&' + name + ';')

        def handle_charref(self, name):
            self.parts.append('&#' + name + ';')

        def handle_comment(self, data):
            self.parts.append('<!--' + data + '-->')

    parser = FormHints()
    parser.feed(body)
    parser.close()
    return ''.join(parser.parts)
