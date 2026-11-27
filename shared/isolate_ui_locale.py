"""Translate presentation labels without touching stored values or evidence.

Legacy pages build HTML on the server. This pass deliberately limits translation
to UI elements and known copy, and leaves table data, code, JSON and user inputs
verbatim. New pages can call ``message`` directly when assembling their labels.
"""

import html
from html.parser import HTMLParser
import re


TRANSLATIONS = {
    "search": "поиск", "host ids": "ID серверов", "runbook id": "Регламент", "parameters": "Параметры",
    "recovery_required": "нужно проверить результат", "Open": "Открыто",
    "single": "отдельное задание", "reachable": "доступен",
    "Queued fleet {} with {} job(s).": "Группа заданий {} поставлена в очередь. Заданий — {}.",
    "Retried {} failed host(s) in fleet {}.": "Повторно запущено заданий — {}. Группа — {}.",
    "Alert state updated.": "Статус события обновлён.",
    "Access request approved": "Заявка на доступ одобрена.",
    "Access request denied": "Заявка на доступ отклонена.",
    "Access request repeated": "Отправлена новая заявка на доступ.",
    "Access revoked": "Доступ отозван.",
    "Host {} added": "Сервер {} добавлен.",
    "Updated hosts: {}": "Обновлены серверы {}.",
    "Host updated": "Настройки сервера сохранены.",
    "Announcement published": "Объявление опубликовано.",
    "Announcement removed": "Объявление снято с публикации.",
    "Approved Git policy synchronized": "Согласованные правила из Git применены.",
    "Policy rolled back; pause the sync timer if Git still contains the newer revision": "Предыдущая версия правил восстановлена. Приостановите автосинхронизацию, если в Git пока осталась более новая версия.",
    "Access package created: {}": "Создан пакет доступа «{}».",
    "Package assigned to {} subject(s)": "Пакет назначен. Получателей — {}.",
    "Assignment {} revoked; {} managed grant(s) removed": "Назначение {} отозвано. Удалено правил из пакета — {}.",
    "Preview completed; no changes were applied": "Проверка завершена. Действующие правила остались прежними.",
    "Package updated and assignments synchronized": "Изменения пакета сохранены и применены к его назначениям.",
    "Package rollback created revision {}": "Предыдущие настройки пакета восстановлены и сохранены как версия {}.",
    "Policy updated": "Правила доступа сохранены.",

    "Isolate Dashboard": "Обзор бастиона",
    "Settings": "Настройки",
    "Operations Overview": "Обзор операций",
    "Current bastion activity, access requests, and recent SSH connections.": "Сессии бастиона, заявки на доступ и последние подключения по SSH.",
    "Recent Activity": "Последние события", "Recent activity": "Последние события",
    "Review sessions": "Просмотреть сессии", "Review requests": "Рассмотреть заявки",
    "Open history": "Открыть историю", "Review notices": "Просмотреть объявления",
    "View all history": "Вся история", "active sessions": "активные сессии",
    "pending access requests": "заявки на рассмотрении", "recent connections": "последние подключения",
    "active announcements": "активные объявления", "No SSH connections have been recorded yet.": "В журнале пока нет подключений по SSH.",
    "Jobs & Runbooks": "Задания и регламенты", "Queue runbook": "Запустить регламент",
    "Queue policy-authorized diagnostics, monitor execution, inspect output, and retry failed hosts.": "Запускайте регламенты для доступных серверов, следите за выполнением и открывайте вывод команд. Задания с ошибкой можно запустить повторно.",
    "No runbook class is enabled for your verified Keycloak groups.": "Для ваших групп Keycloak не разрешён запуск ни одной категории регламентов.",
    "No jobs match the selected filters.": "По выбранным фильтрам заданий нет.",
    "Execution details and captured output.": "Результат выполнения и сохранённый вывод команды.",
    "The remote outcome is unknown. Inspect the target before submitting a new job. Automatic retry is disabled.": "Неизвестно, выполнилась ли команда на сервере. Проверьте сервер, прежде чем запускать её заново.",
    "No output was captured.": "Нет сохранённого вывода команды.",
    "Fleet rollouts": "Запуски на нескольких серверах", "Job history": "История заданий",
    "Authorization snapshot": "Права на момент запуска", "Follow related evidence": "Открыть связанные события",
    "Cancel job": "Отменить задание", "Retry job": "Повторить задание", "Retry failed": "Повторить задания с ошибкой",
    "Runbook": "Регламент", "Host IDs": "ID серверов", "Or project": "Или проект",
    "Parameters JSON": "Параметры (JSON)", "Timeout": "Тайм-аут", "Tags": "Теги",
    "confirm execution on all selected hosts": "подтверждаю выполнение на всех выбранных серверах",
    "confirm": "подтверждаю", "queued": "в очереди", "running": "выполняется", "claimed": "задание принято",
    "recovery required": "проверьте результат", "completed": "завершено", "failed": "ошибка",
    "Access Matrix": "Матрица доступа", "Access Packages": "Пакеты доступа",
    "Access Requests": "Заявки на доступ", "Active Sessions": "Активные сессии",
    "Alert Center": "События и предупреждения", "Announcements": "Объявления",
    "Grants": "Правила доступа", "History": "Журнал сессий", "Inventory": "Инвентарь",
    "Live Session": "Наблюдение за сессией", "Notification Delivery": "Журнал доставки уведомлений",
    "Policy GitOps": "Политики GitOps", "Policy Simulator": "Проверка доступа",
    "Project Sets": "Наборы проектов", "Session Control": "Управление сессией",
    "Session Details": "Сведения о сессии", "Session Replay": "Запись сессии", "Users": "Пользователи",
    "Recording temporarily unavailable": "Запись временно недоступна",
    "Internal Server Error": "Внутренняя ошибка сервера", "Sign-in temporarily unavailable": "Вход временно недоступен",
    "Access request delivery status": "Доставка уведомлений о заявках", "Active sessions": "Активные сессии",
    "Add host": "Добавить ресурс", "Add or replace grant": "Добавить или заменить правило",
    "Add or replace project set": "Добавить или заменить набор проектов", "Assign package": "Назначить пакет",
    "Assignments": "Назначения", "Blast radius preview": "Что затронет изменение",
    "Bulk grant action": "Массовое изменение правил", "Bulk project-set members": "Изменить состав набора",
    "Bulk update": "Массовое изменение", "Commands": "Команды", "Configured sinks": "Каналы доставки",
    "Create package": "Создать пакет", "Decision": "Решение", "Edit and preview": "Изменить и проверить",
    "Effective grant candidates": "Правила, подходящие под запрос", "Identity observed in audit": "Учётная запись в журнале аудита",
    "Output": "Вывод", "Policy findings": "Замечания к политике", "Preview": "Проверка изменений",
    "Preview grant blast radius": "Проверить, кого затронет правило", "Recent access requests": "Последние заявки на доступ",
    "Recent sessions": "Последние сессии", "Remove grant": "Удалить правило",
    "Remove project set": "Удалить набор проектов", "Result": "Результат", "Revision history": "История версий",
    "Revoke assignment": "Отозвать назначение", "Rollback": "Откат", "Rollback revisions": "Версии для отката",
    "Session alert delivery status": "Доставка уведомлений о сессиях", "Summary": "Сводка", "Timeline": "Лента событий",
    "Top projects": "Самые активные проекты", "Access rules": "Правила доступа", "Admin groups": "Группы администраторов",
    "Default TTL": "Срок доступа по умолчанию", "Description": "Описание", "Max TTL": "Максимальный срок доступа",
    "Minimum approvals": "Сколько согласований требуется", "Name": "Название", "Status": "Статус",
    "Add": "Добавить", "Apply": "Применить", "Approve": "Согласовать", "Deny": "Отклонить",
    "Check": "Проверить", "Filter": "Применить фильтр", "Publish": "Опубликовать", "Remove": "Удалить",
    "Request again": "Запросить повторно", "Save": "Сохранить", "Search": "Найти", "Simulate": "Проверить",
    "Terminate": "Завершить", "Assign": "Назначить", "Revoke access": "Отозвать доступ",
    "Sync approved revision": "Применить согласованную версию", "Create rollback revision": "Создать версию отката",
    "Unassign": "Отменить назначение", "Acknowledge": "Принять к сведению", "Comment": "Добавить комментарий",
    "Reopen": "Открыть повторно", "Resolve": "Закрыть", "Apply revision": "Применить версию",
    "Pause": "Пауза", "Play": "Воспроизвести", "Reset": "Сбросить", "all statuses": "все статусы",
    "all types": "все типы", "runbook": "регламент", "remote command": "удалённая команда",
    "Created": "Создано", "Error": "Ошибка", "Exit code": "Код завершения", "Finished": "Завершено",
    "Fleet / attempt": "Групповой запуск / попытка", "Project / host": "Проект / сервер", "Remote identity": "Учётная запись на сервере",
    "Revision": "Версия", "Started": "Начало", "Type": "Тип", "Updated": "Изменено", "Updated by": "Кто изменил",
    "User": "Пользователь", "ID": "ID", "time": "время", "user": "пользователь", "project": "проект",
    "host": "сервер", "remote user": "учётная запись на сервере", "result": "результат", "details": "подробнее",
    "status": "статус", "type": "тип", "operation": "операция", "exit": "код завершения", "actions": "действия",
    "progress": "ход выполнения", "results": "результаты", "fleet": "группа", "created": "создано", "id": "ID",
    "name": "название", "subject": "кому выдан доступ", "groups": "группы", "roles": "роли", "owner": "владелец",
    "environment": "окружение", "services": "сервисы", "note": "примечание", "port": "порт",
    "open": "открыть", "edit": "изменить", "replay": "запись", "live": "наблюдать", "control": "управление",
    "duration": "длительность", "started": "начало", "finished": "завершено", "reason": "причина",
    "scope": "область действия", "severity": "важность", "delivery": "доставка", "revision": "версия",
    "IP": "IP", "assignment id": "ID назначения", "comment": "комментарий", "default": "по умолчанию",
    "grant id": "ID правила", "group or user": "группа или пользователь", "host id": "ID сервера",
    "id for update": "ID для изменения", "new project": "новый проект", "new remote user": "новая учётная запись на сервере",
    "new services": "новые сервисы", "one or comma-separated subjects": "имена пользователей, групп или ролей через запятую",
    "Operational notice": "Объявление для инженеров", "optional comment": "комментарий, необязательно",
    "optional grant id to replace": "ID заменяемого правила, необязательно", "optional host": "сервер, необязательно",
    "package id or name": "ID или название пакета", "Read-only production access for support teams": "Доступ команды поддержки к продакшену только для чтения",
    "remote_user": "учётная запись на сервере", "replace tags: env=prod": "заменить теги: env=prod",
    "resource owner": "владелец ресурса", "revision id": "ID версии", "revocation reason": "причина отзыва",
    "selector": "условие отбора", "start: ISO time +timezone": "начало: время ISO с часовым поясом",
    "subject name": "имя пользователя, группы или роли", "sudo_mode": "режим sudo", "Support Read-Only": "Доступ для поддержки (только чтение)",
    "ticket": "номер заявки", "username": "имя пользователя",
    "Job {job_id}": "Задание {job_id}", "User {username}": "Пользователь {username}",
    "Edit Host {server_id}": "Изменение ресурса {server_id}", "Service changes: {}": "Изменения сервисов: {}",
    "Job {}": "Задание {}", "job {}": "задание {}", "request {}": "заявка {}",
    "Edit Host": "Изменение ресурса", "User Details": "Сведения о пользователе",
    "Job Details": "Сведения о задании", "Jobs": "Задания", "Notifications": "Уведомления",
    "Documentation": "Документация",
    "Service changes": "Изменения сервисов",
    "Active only": "Только активные", "All": "Все", "Back to packages": "К пакетам доступа",
    "Download CSV": "Скачать CSV", "Download JSON": "Скачать JSON", "Download {}": "Скачать {}",
    "Fetch status, drift and blast radius": "Проверить статус, расхождения и затронутые правила",
    "Full evaluation": "Полная проверка", "Maintenance": "Обслуживание", "No sudo": "Без sudo",
    "Note": "Примечание", "Owner": "Владелец", "Project": "Проект", "Privileged hint": "Порядок привилегированного доступа",
    "Provider": "Провайдер", "Services": "Сервисы", "Until": "До", "Workspace": "Рабочее пространство",
    "access requests": "заявки на доступ", "acknowledged": "принято в работу", "affected subjects,": "затронутых пользователей, групп и ролей,",
    "and before": "и до", "comments": "комментарии", "connections": "подключения", "decision": "решение",
    "expires (UTC)": "действует до (UTC)", "grant": "правило", "grant candidates": "подходящие правила",
    "grant changes; revision {} to {}.": "изменений правил при переходе с версии {} на {}.", "history": "история",
    "loading": "загрузка", "managed package": "управляемый пакет", "notify": "уведомления",
    "policy is read-only here.": "здесь политика доступна только для чтения.", "raw": "исходная запись",
    "raw transcript": "исходная запись терминала", "recent failures": "последние ошибки",
    "Recording": "Запись", "Session text": "Текст сессии", "Download TXT": "Скачать TXT",
    "Host metadata": "Сведения о сервере", "Privileged access and proxy": "Привилегии и прокси",
    "Showing the beginning of the recording due to the size limit.": "Показано начало записи. Остальной вывод превышает лимит размера.",
    "requested end (UTC)": "запрошено до (UTC)", "resolved": "закрыто", "service changes": "изменения сервисов",
    "session": "сессия", "start (UTC)": "начало (UTC)", "sudo": "sudo", "total": "всего", "view": "просмотреть",
    "{finished}/{total} finished": "завершено {finished} из {total}",
    "Last 50 changes to running systemd units. Baseline establishes the initial state; failed scans do not create changes.": "Последние 50 изменений в списке запущенных служб systemd. Isolate сравнивает результаты успешных проверок. Первая проверка сохраняет исходный список.",
    "Effective group, role, and user access across projects, calculated with the production policy resolver.": "Доступ групп, ролей и пользователей к проектам по действующим правилам.",
    "Session risk, failed jobs, and notification delivery failures in one operational queue.": "Подозрительные или долгие сессии, ошибки заданий и сбои при отправке уведомлений.",
    "This form never applies policy. It compares the current resolver result with a hypothetical additional grant.": "Добавьте пробное правило, чтобы увидеть, кому откроется или закроется доступ. Действующие правила останутся прежними.",
    "Preview reports affected subjects and grant create/update/delete operations. Revisions are immutable, making rollback reproducible.": "Проверьте, какие пользователи, группы и роли получат другие права и какие правила будут добавлены, изменены или удалены. При откате Isolate восстанавливает сохранённую версию правил.",
    "Please retry sign-in shortly.": "Попробуйте войти позже.", "Request ID: {}": "ID запроса: {}",
    "Evidence could not be verified. Request ID: {}": "Не удалось проверить запись. ID запроса: {}",
    "pending": "на рассмотрении", "approved": "согласовано", "denied": "отклонено", "revoked": "отозвано",
    "active": "активно", "cancelled": "отменено", "timed_out": "истекло время ожидания",
    "expired": "срок истёк", "success": "успех", "allowed": "разрешено",
    "requested": "запрошено", "unavailable": "недоступно", "unknown": "неизвестно",
    "Approval required": "Требуется согласование", "Changed:": "Изменено:", "Confirm": "Подтвердить",
    "Confirm apply": "Подтвердить применение", "Enforced GitOps:": "Управление правилами через GitOps:", "Environment": "Окружение",
    "Gained:": "Добавлено:", "Lost:": "Отозвано:", "Permanent": "Постоянно", "Permanent allowed": "Постоянный доступ разрешён",
    "Port": "Порт", "Proxy ID": "ID промежуточного сервера", "Readable text": "Текстовая запись", "Reason": "Причина",
    "Ticket required": "Требуется номер заявки", "URL": "URL", "VIP": "VIP",
    "No alerts match the selected filters.": "По выбранным фильтрам событий нет.",
    "No conflicting, redundant, or shadowed grants were found for current inventory.": "Для ресурсов каталога не найдено правил, которые конфликтуют, дублируют друг друга или не срабатывают из-за правил с большим приоритетом.",
    "The hypothetical grant does not change effective access.": "Пробное правило не изменит действующий доступ.",
    "add": "добавить", "all findings": "все замечания", "all kinds": "все типы", "all projects": "все проекты",
    "available": "доступно", "clear tags": "удалить теги", "command": "команда", "confirm update": "подтверждаю изменение",
    "conflict": "конфликт", "critical": "критично", "disabled": "отключено", "enabled": "включено",
    "failed job": "ошибка задания", "false": "нет", "group": "группа", "info": "информация",
    "keep VIP": "сохранить отметку VIP", "keep maintenance": "сохранить режим обслуживания",
    "long session": "длительная сессия", "maintenance": "обслуживание", "none": "нет",
    "not VIP": "убрать отметку VIP", "notification failure": "ошибка уведомления", "operate": "операционная задача",
    "privileged": "привилегированный", "project_glob": "шаблон проекта", "project_globs": "шаблоны проектов",
    "project_set": "набор проектов", "projects": "проекты", "redundant": "избыточное",
    "remove": "удалить", "role": "роль", "shadowed": "не действует из-за приоритета", "standard": "обычный",
    "true": "да", "unusual source": "необычный источник", "warning": "предупреждение",
}


FIELD_HINTS = {
    "runbook_id": ("Choose an operation permitted by your current groups and resource grants.", "Выберите регламент, который разрешён для вашей группы и выбранных ресурсов."),
    "host_ids": ("Enter resource IDs separated by commas. Review the full target list before execution.", "Укажите ID ресурсов через запятую. Перед запуском проверьте весь список."),
    "host_id": ("Use the numeric resource ID from the inventory.", "Укажите числовой ID ресурса из каталога."),
    "host": ("Use the resource ID. Leave empty only when the action applies to the whole selected project.", "Укажите ID ресурса. Пустое поле применяет действие ко всему выбранному проекту."),
    "project": ("Use the exact project name from the inventory.", "Укажите точное название проекта из каталога."),
    "projects": ("Enter exact project names separated by commas.", "Введите точные названия проектов через запятую."),
    "project_globs": ("Project patterns support *. Check the matching resources before saving.", "В шаблоне названия проекта можно использовать *. Перед сохранением проверьте, какие ресурсы попали в выборку."),
    "project_glob": ("Use * to match several project names. Review the resulting scope.", "Используйте *, чтобы выбрать проекты по части названия. Проверьте, какие проекты совпали с шаблоном."),
    "tags": ("Use key=value pairs separated by commas, for example env=stage,owner=platform.", "Укажите пары ключ=значение через запятую, например env=stage,owner=platform."),
    "parameters": ("Enter a JSON object with only the parameters supported by the selected runbook.", "Введите параметры, которые принимает регламент, в виде JSON-объекта."),
    "timeout": ("Maximum wait in seconds. The configured limit still applies.", "Сколько секунд ждать завершения. Верхний предел задан в настройках."),
    "confirm": ("Confirm only after reviewing the target, scope and effect of this action.", "Перед подтверждением проверьте, на какие ресурсы повлияет действие."),
    "reason": ("Explain the business purpose. Avoid passwords, tokens and other secrets.", "Опишите рабочую цель. Не указывайте пароли, токены и другие секреты."),
    "comment": ("Add context for reviewers. Comments can be visible to other authorized users.", "Поясните своё решение или запрос. Комментарий увидят другие пользователи с доступом к этой записи."),
    "text": ("Use clear text for the intended audience and exclude credentials.", "Напишите понятный текст для получателей. Не добавляйте учётные данные."),
    "description": ("Describe the purpose and intended users of this assignment.", "Укажите, кому и для какой задачи нужен этот доступ."),
    "name": ("Use a unique descriptive name. Follow the format required by this resource.", "Укажите уникальное понятное название в формате, допустимом для ресурса."),
    "names": ("Enter names separated by commas. Every value is checked independently.", "Укажите названия через запятую."),
    "ip": ("Enter the resource's IPv4 or IPv6 address. DNS names belong in the name field.", "Укажите IPv4 или IPv6 ресурса. DNS-имя можно указать в поле «Название»."),
    "port": ("TCP port between 1 and 65535. Use the endpoint's actual listening port.", "Укажите TCP-порт, на котором ресурс принимает подключения (от 1 до 65535)."),
    "remote_user": ("The account on the target resource, not the person signing in to Isolate.", "Укажите учётную запись, под которой Isolate подключится к ресурсу."),
    "user": ("Use the verified username. Access remains bound to the current policy.", "Укажите подтверждённое имя пользователя. Доступ определяется действующей политикой."),
    "groups": ("Enter exact group names from your identity provider, separated by commas.", "Перечислите точные названия групп из IdP через запятую."),
    "roles": ("Enter exact role names separated by commas.", "Введите точные названия ролей через запятую."),
    "admin_groups": ("Only members of these verified identity-provider groups can administer this package.", "Управлять пакетом смогут только пользователи из указанных групп IdP."),
    "sudo_mode": ("Choose none for ordinary access or sudo-i only when explicitly approved.", "Для обычного доступа выберите none. Выбирайте sudo-i, только если повышение прав согласовано."),
    "nosudo": ("Keep enabled for an ordinary shell without automatic sudo elevation.", "Включите для обычной оболочки без автоматического повышения прав через sudo."),
    "allowed_actions": ("List only required actions, separated by commas, for example ssh,runbook.", "Перечислите только нужные действия через запятую, например ssh,runbook."),
    "allowed_action": ("Select the action this rule allows. Other actions remain governed by their own checks.", "Выберите действие, разрешённое этим правилом. Для остальных действий действуют собственные проверки."),
    "subject": ("Select whether this rule matches a user, group, role or registered service identity.", "Выберите, кому назначить правило доступа — пользователю, группе, роли или зарегистрированной сервисной учётной записи."),
    "subject_name": ("Use the exact verified subject name for the selected type.", "Введите точное имя пользователя, группы, роли или сервисной учётной записи, на которую распространяется правило."),
    "owner": ("Resource owner or team responsible for access and maintenance.", "Владелец ресурса или команда, отвечающая за доступ и обслуживание."),
    "environment": ("Use your team's environment label, for example production or staging.", "Укажите принятое в команде окружение, например production или staging."),
    "services": ("Describe the services hosted by this resource. This does not grant connection permissions.", "Перечислите сервисы на ресурсе. Права на подключение задаются отдельно в правилах доступа."),
    "note": ("Operational context for other authorized users. Exclude credentials.", "Опишите особенности ресурса для тех, у кого есть доступ к записи. Учётные данные храните отдельно."),
    "q": ("Search within resources and evidence you are currently permitted to view.", "Поиск показывает только доступные вам ресурсы и события."),
    "status": ("Limit results to the selected lifecycle status.", "Оставить в результатах записи с выбранным статусом."),
    "type": ("Limit results to the selected operation or resource type.", "Оставить в результатах выбранный тип операций или ресурсов."),
    "kind": ("Select the type of object or event you want to inspect.", "Выберите тип объекта или события для просмотра."),
    "ttl": ("Requested lifetime, for example 30m or 2h. The configured maximum applies.", "Укажите, на сколько нужен доступ, например 30m или 2h. Максимальный срок задан в настройках."),
    "default_ttl": ("Lifetime used by default for new assignments, within the maximum lifetime.", "На сколько выдавать доступ, если срок не указан."),
    "max_ttl": ("Upper bound on temporary access. Choose the shortest practical lifetime.", "Самый долгий срок, на который можно выдать временный доступ."),
    "starts_at": ("Use an ISO 8601 date and time with timezone, for example 2026-11-10T09:00:00+07:00.", "Укажите дату и время ISO 8601 с часовым поясом, например 2026-11-10T09:00:00+07:00."),
    "maintenance": ("Mark the resource as under maintenance. Connection policy checks this state.", "Режим обслуживания учитывается при проверке новых подключений к ресурсу."),
    "maintenance_until": ("Maintenance end time. Check the form's date format and timezone.", "Укажите, когда закончится обслуживание. Проверьте формат даты и часовой пояс."),
    "maintenance_reason": ("Explain the maintenance window to people who need this resource.", "Опишите причину обслуживания для пользователей ресурса."),
    "minimum_approvals": ("Number of distinct eligible reviewers required before access can start.", "Сколько разных согласующих должны одобрить заявку, чтобы доступ стал доступен."),
    "approval_required": ("Require the configured session approval before a connection starts.", "Разрешать подключение после согласования каждой новой сессии."),
    "ticket": ("Enter the relevant incident or change request identifier.", "Укажите номер связанного инцидента или заявки на изменение."),
    "ticket_required": ("Require an incident or change request reference in the access request.", "Требовать ссылку на инцидент или заявку на изменение при запросе доступа."),
    "permanent": ("Permanent access has no automatic expiry. Review the business need first.", "У постоянного доступа нет срока действия. Его отзывают вручную."),
    "permanent_allowed": ("Allow permanent assignments only when your access policy permits them.", "Разрешите выдавать доступ без срока действия, если это допускает политика вашей организации."),
    "access_json": ("Provide the access rules as JSON. Review every project, target identity and action.", "Укажите правила доступа в JSON. Проверьте проекты, целевые учётные записи и действия."),
    "expected_revision": ("The revision you reviewed. A concurrent change requires reviewing the newer revision.", "Укажите версию, которую вы проверили. Если кто-то сохранил изменения раньше вас, проверьте новую версию."),
    "revision": ("Choose the exact policy revision to inspect or apply.", "Укажите точную версию политики для просмотра или применения."),
    "replace_grant_id": ("ID of the existing rule to replace. Review its current scope before continuing.", "Укажите ID правила, которое хотите заменить. Проверьте, кому оно выдаёт доступ."),
    "package": ("Choose the access package to assign or inspect.", "Выберите пакет доступа для назначения или просмотра."),
    "proxy_id": ("Inventory ID of an explicitly authorized jump host. Leave empty for a direct connection.", "Укажите ID разрешённого промежуточного хоста из каталога. Для прямого подключения оставьте поле пустым."),
    "vip": ("Highlight the resource as important; this marker does not grant access.", "Выделить важный ресурс. Права по-прежнему определяются правилами доступа."),
    "clear_tags": ("Remove the existing tags from all selected resources.", "Удалить существующие теги у всех выбранных ресурсов."),
    "ids": ("Numeric identifiers separated by commas. Review every selected item before applying.", "Числовые ID через запятую. Перед применением проверьте каждый выбранный объект."),
    "id": ("Use the identifier of the object this form manages.", "Введите ID записи, которую хотите просмотреть или изменить."),
    "severity": ("Filter or classify events by operational severity.", "Укажите уровень важности события."),
    "mode": ("Choose the operation mode. Review its effect before applying changes.", "Выберите режим операции. Перед применением проверьте его последствия."),
    "member_type": ("Choose whether members are exact projects, project patterns or another supported selector.", "Выберите, какие проекты входят в набор — по точным названиям, шаблонам или другому условию."),
    "values": ("Enter values for the selected member type, separated by commas.", "Укажите значения для выбранного условия через запятую."),
    "selector_type": ("Choose the kind of resource selector this operation uses.", "Выберите способ отбора ресурсов для этой операции."),
    "selector_value": ("Enter the exact value or permitted pattern for the selected selector type.", "Укажите точное значение или шаблон для выбранного условия."),
    "policy_action": ("Evaluate the exact action you intend to perform on the resource.", "Проверьте именно то действие, которое планируете выполнить на ресурсе."),
    "privileged_provider": ("Name of your configured privileged-access provider.", "Название провайдера, через которого инженеры получают привилегированный доступ."),
    "privileged_url": ("Trusted HTTPS address of the external privileged-access workflow.", "HTTPS-адрес доверенного сервиса, через который запрашивают привилегированный доступ."),
    "privileged_hint": ("Explain the required privileged-access procedure without including secrets.", "Опишите порядок получения привилегированного доступа без указания секретов."),
    "canary_count": ("Targets in the first stage. All must succeed before later batches start.", "Число серверов для пробного запуска. Следующий этап начнётся, если команда успешно отработает на всех этих серверах."),
    "batch_size": ("Maximum targets in each later batch, within the configured limit.", "Сколько серверов обрабатывать на каждом этапе после пробного запуска."),
    "failure_budget": ("Allowed known command failures after the canary. Uncertain outcomes always stop expansion.", "Сколько подтверждённых ошибок допустимо после пробного запуска. При неизвестном результате Isolate остановит запуск следующих групп."),
    "max_failure_percent": ("Maximum cumulative percentage of known failures after the canary.", "Допустимая доля подтверждённых ошибок после пробного запуска в процентах."),
    "subject_id": ("Use the verified provider-bound subject identifier, not an editable display name.", "Скопируйте постоянный ID учётной записи из IdP."),
    "project_name": ("Use the exact project name from the inventory.", "Укажите точное название проекта из каталога."),
    "due_at": ("Review deadline. Check the required date format and timezone.", "Дата, к которой нужно завершить проверку доступа. Проверьте часовой пояс."),
    "expires_at": ("Access expiry time. Choose a bounded duration appropriate to the task.", "Укажите, до какого времени нужен доступ для этой задачи."),
    "decision": ("Choose the access decision after reviewing the current rule and its revision.", "Выберите решение после проверки действующего правила и его версии."),
    "ends_at": ("Use an ISO 8601 expiry time with timezone, or the Unix timestamp accepted by this form.", "Введите время окончания в ISO 8601 с часовым поясом или в формате Unix time."),
    "since": ("Include events on or after this UTC date or ISO 8601 timestamp with timezone.", "Укажите дату в UTC или дату и время в ISO 8601 с часовым поясом, с которых нужно показать события."),
    "until": ("Include events up to this UTC date or ISO 8601 timestamp with timezone.", "Укажите дату в UTC или дату и время в ISO 8601 с часовым поясом, до которых нужно показать события."),
    "finding": ("Filter by the policy issue you want to review.", "Выберите замечание к политике, которое нужно проверить."),
    "limit": ("Maximum records on this page, within the configured limit.", "Сколько записей показать на странице. Верхний предел задан в настройках."),
    "protocol": ("Choose the connection protocol. Permissions are checked for each protocol separately.", "Выберите протокол подключения. Разрешения для каждого протокола проверяются отдельно."),
    "result": ("Filter the recorded outcome without changing the underlying evidence.", "Выберите результат, по которому нужно отобрать записи."),
}


def message(text, locale="en"):
    """Return a UI label in the selected language, keeping unknown copy intact."""
    return TRANSLATIONS.get(text, text) if locale == "ru" else text


translate = message


_PROTECTED = frozenset({"script", "style", "pre", "code", "textarea", "td", "dd", "option"})
_UI_TEXT = frozenset({"h1", "h2", "h3", "h4", "label", "button", "th", "dt", "legend", "summary", "a"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
_ATTRIBUTES = frozenset({"placeholder", "aria-label", "title"})


class _Presentation(HTMLParser):
    def __init__(self, locale, hints, template=False, fallback_hints=None):
        super().__init__(convert_charrefs=False)
        self.locale = locale
        self.hints = hints
        self.template = template
        self.output = []
        self.stack = []
        self.pending = {}
        self.counter = 0
        self.text = []
        self.fallback_hints = fallback_hints or {}

    def _protected(self):
        protected = _PROTECTED - {"td", "dd", "option"} if self.template else _PROTECTED
        return any(tag in protected or attrs.get("data-i18n") == "off" for tag, attrs in self.stack)

    def _translate(self, text):
        return html.escape(message(html.unescape(text), self.locale), quote=False)

    def _flush(self):
        if not self.text:
            return
        data = "".join(self.text)
        self.text.clear()
        translate = not self._protected() and self.stack and (self.template or
            self.stack[-1][0] in _UI_TEXT or self.stack[-1][1].get("data-i18n") == "ui"
            or "page-lead" in self.stack[-1][1].get("class", "").split())
        stripped = data.strip()
        if translate and html.unescape(stripped) in TRANSLATIONS:
            if self.template and self.stack[-1][0] == "option" and "value" not in self.stack[-1][1]:
                # HTML options without value submit their display text. Preserve
                # that original value before translating a developer-owned label.
                label = html.unescape(stripped)
                if message(label, self.locale) != label:
                    if not self.output[-1].lower().startswith("<option"):
                        self.output.append(data)
                        return
                    self.output[-1] = self.output[-1][:-1] + ' value="' + html.escape(label, quote=True) + '">'
            position = data.find(stripped)
            self.output.append(data[:position] + self._translate(stripped) + data[position + len(stripped):])
        else:
            self.output.append(data)

    def _tag(self, tag, attrs, closed=False):
        self._flush()
        source = self.get_starttag_text()
        values = dict(attrs)
        if not self._protected():
            for attr, value in attrs:
                if attr in _ATTRIBUTES and value:
                    translated = message(value, self.locale)
                    if translated != value:
                        pattern = r'(?<![\w-])' + re.escape(attr) + r'\s*=\s*(?:"[^"]*"|\'[^\']*\')'
                        source = re.sub(pattern, lambda _: attr + '="' + html.escape(translated, quote=True) + '"', source, count=1, flags=re.I)
        hint = ""
        if (self.hints and not self._protected() and any(item[0] == "form" for item in self.stack)
                and tag in ("input", "select", "textarea") and values.get("name")
                and values.get("type", "").lower() not in ("hidden", "submit", "reset", "button", "image")
                and not values.get("aria-describedby")
                and values.get("data-hint") != "off"):
            name = values["name"]
            copy = FIELD_HINTS.get(name)
            description = copy[1 if self.locale == "ru" else 0] if copy else self.fallback_hints.get(name)
            if description:
                self.counter += 1
                identifier = "form-hint-{}".format(self.counter)
                described = " ".join(filter(None, (values.get("aria-describedby"), identifier)))
                source = re.sub(r'\saria-describedby\s*=\s*(?:"[^"]*"|\'[^\']*\')', "", source, flags=re.I)
                additions = ' aria-describedby="{}"'.format(html.escape(described, quote=True))
                # Bare filter controls need an accessible name too. A visible
                # surrounding label remains the source of the name elsewhere.
                if not values.get("aria-label") and not any(item[0] == "label" for item in self.stack):
                    label = values.get("placeholder") or name.replace("_", " ")
                    additions += ' aria-label="{}"'.format(html.escape(message(label, self.locale), quote=True))
                end = "/>" if source.rstrip().endswith("/>") else ">"
                source = source.rstrip()[:-len(end)] + additions + end
                hint = '<small class="field-hint" id="{}">{}</small>'.format(identifier, html.escape(description))
        self.output.append(source)
        if closed or tag in _VOID:
            self.output.append(hint)
        else:
            self.stack.append((tag, values))
            if hint:
                self.pending[len(self.stack)] = hint

    def handle_starttag(self, tag, attrs):
        self._tag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._tag(tag, attrs, True)

    def handle_endtag(self, tag):
        self._flush()
        self.output.append("</{}>".format(tag))
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                hint = self.pending.pop(index + 1, "")
                del self.stack[index:]
                self.output.append(hint)
                break

    def handle_data(self, data):
        self.text.append(data)

    def handle_entityref(self, name):
        self.text.append("&{};".format(name))

    def handle_charref(self, name):
        self.text.append("&#{};".format(name))

    def handle_comment(self, data):
        self._flush()
        self.output.append("<!--{}-->".format(data))

    def handle_decl(self, decl):
        self._flush()
        self.output.append("<!{}>".format(decl))


def localize_html(body, locale="en", hints=True, fallback_hints=None):
    """Translate known presentation labels and attach field-specific form help.

    This function never changes field values, action URLs or evidence payloads.
    ``data-i18n="off"`` protects an entire subtree of user-generated content.
    """
    parser = _Presentation("ru" if locale == "ru" else "en", hints, fallback_hints=fallback_hints)
    parser.feed(body)
    parser.close()
    parser._flush()
    return "".join(parser.output)


def localize_template(template, locale="en"):
    """Translate a developer-owned HTML literal before values are interpolated.

    Unlike the final-body pass this can translate static paragraph, status and
    option text, because no inventory records, identities or outputs are present.
    Keep the interpolation placeholders unchanged in every translation.
    """
    parser = _Presentation("ru" if locale == "ru" else "en", hints=False, template=True)
    parser.feed(template)
    parser.close()
    parser._flush()
    return "".join(parser.output)
