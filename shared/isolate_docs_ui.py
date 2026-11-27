"""Bilingual, searchable product guides rendered independently of the dashboard."""

from dataclasses import dataclass
from html import escape
import re
from urllib.parse import urlencode


Translation = tuple[str, str]
Section = tuple[Translation, tuple[tuple[Translation, Translation], ...]]


@dataclass(frozen=True)
class Guide:
    key: str
    title: Translation
    summary: Translation
    sections: tuple[Section, ...]
    related: tuple[str, ...] = ()
    links: tuple[tuple[str, Translation], ...] = ()
    example: str = ""


@dataclass(frozen=True)
class Workflow:
    title: Translation
    steps: tuple[tuple[str, Translation, Translation], ...]
    decision: Translation | None = None
    outcomes: tuple[tuple[str, Translation, Translation], ...] = ()


# English comes first in every pair. Keep these descriptions aligned with the
# actions exposed by the product and use the same labels as the interface.
GUIDE_GROUPS = (
    (("Use Isolate", "Работа в Isolate"), (
        Guide(
            "sign-in", ("Sign-in and profile", "Вход и профиль"),
            ("Sign in through your identity provider and find your personal settings.",
             "Как войти в Isolate и настроить портал для себя."),
            ((("Start a session", "Начало работы"), (
                (("Sign in", "Вход через OIDC"),
                 ("Open Isolate and complete sign-in with the configured OIDC provider, such as Keycloak. Complete MFA if prompted. The browser returns to Isolate after the provider verifies your identity.",
                  "Откройте Isolate. Он перенаправит вас на страницу входа провайдера OIDC, например Keycloak. Войдите в свою учётную запись и пройдите MFA, если этого требует провайдер. Затем браузер вернётся в портал.")),
                (("Profile", "Профиль"),
                 ("Use the avatar in the header to open your profile. You can return to your resources, requests, sessions and history from there. Your roles and groups come from the identity provider.",
                  "Нажмите на аватар в шапке. В профиле собраны ссылки на ваши ресурсы, заявки, сессии и историю. Роли и группы передаёт провайдер OIDC.")),
                (("Language and appearance", "Язык и тема"),
                 ("EN and RU change the language of the interface and guides. Light, Dark and System control the portal theme. System follows your device appearance, while an explicit choice is saved in this browser.",
                  "Переключатель «EN / RU» меняет язык портала и документации. Выберите светлую, тёмную или системную тему. Портал запомнит выбор в этом браузере. В режиме «Как в системе» тема меняется вместе с настройками устройства.")),
                (("Sign out", "Выход и повторный вход"),
                 ("Use Sign out to close your browser sign-in. If access expires or a connection requires fresh verification, complete sign-in again and retry the intended action.",
                  "Чтобы выйти из портала, нажмите «Выйти». Если сессия истекла или для подключения нужно ещё раз подтвердить личность, войдите повторно и вернитесь к своему действию.")),
            )),), ("resources", "troubleshooting"),
            (("/me/profile", ("Open my profile", "Открыть профиль")),),
        ),
        Guide(
            "resources", ("Find and connect to resources", "Каталог и подключение"),
            ("Search the catalogue, understand access and choose the right connection.",
             "Как найти хост или приложение, проверить свои права и подключиться."),
            ((("Catalogue", "Каталог"), (
                (("Search and filters", "Поиск и фильтры"),
                 ("Search by name, address, project, owner or tag where the catalogue supports that field. Use Project and Protocol to narrow the list. In the catalogue, / or Ctrl+K focuses search and the arrow keys select a result.",
                  "Введите имя, адрес, проект, владельца или тег. Доступные поля зависят от настроек каталога. Чтобы сузить выдачу, выберите проект и протокол. Нажмите / или Ctrl+K, чтобы перейти к поиску. По результатам можно перемещаться стрелками.")),
                (("Favorites and recent", "Избранное и недавние"),
                 ("Star a resource to save it to your account. Recent lists resources after an authorized connection starts. A saved resource still requires current access at connection time.",
                  "Отметьте ресурс звёздочкой, чтобы добавить его в избранное. В разделе «Недавние» появляются ресурсы, к которым вы начали разрешённое подключение. При следующем подключении Isolate снова проверит права.")),
                (("Details and Why this access?", "Карточка ресурса и проверка доступа"),
                 ("Details shows the resource and the relevant connection instructions. Why this access? explains the policy decision and any approval, fresh authentication or maintenance condition. Management visibility can coexist with restricted connection rights.",
                  "Откройте карточку, чтобы посмотреть параметры ресурса и инструкцию для его протокола. Раздел «Условия доступа» показывает, какое правило сработало и что мешает подключиться сейчас. Например, может потребоваться согласование или повторный вход, а хост может быть на обслуживании. Администратор проекта может видеть ресурс в каталоге без права подключения.")),
                (("Connect or request access", "Подключение и заявка"),
                 ("Connect opens the terminal or the protocol instructions. If the card asks for access, use the access request. If it asks to approve a session, use the connection-specific approval instead.",
                  "Нажмите «Подключиться». Для Web SSH откроется терминал, для клиентского подключения появится инструкция. Если прав пока нет, подайте заявку из карточки. Если правило требует согласования подключения, запросите его для выбранной сессии.")),
            )),), ("terminal", "protocols", "access-requests"), links=(("/workspace", ("Open catalogue", "Открыть каталог")),),
        ),
        Guide(
            "terminal", ("Web SSH, native SSH and shell", "Web SSH и SSH-клиент"),
            ("Work in parallel terminal panes, or use your own SSH client.", "Как работать в терминале браузера и подключаться своим SSH-клиентом."),
            ((("Web terminal", "Браузерный терминал"), (
                (("New tab and split", "Вкладки и панели"),
                 ("Choose a resource from the catalogue or open Terminal, then use New tab or one of the two split controls. Select a pane before typing. Each connection has its own authorization and state.",
                  "Откройте ресурс в каталоге или перейдите в терминал. Для второго подключения создайте вкладку или разделите текущую панель по горизонтали или вертикали. Перед вводом щёлкните по нужной панели. Isolate проверяет права отдельно для каждого подключения.")),
                (("Full screen and separate window", "Полноэкранный режим и отдельное окно"),
                 ("Full screen expands the current workspace and keeps its tabs and connections. Use the same button to return. Separate window opens a terminal with a new connection to the selected server. In that window, use Full screen to hide browser chrome when your browser supports it.",
                  "Кнопка «На весь экран» разворачивает текущее рабочее пространство и сохраняет вкладки и подключения. Повторное нажатие возвращает обычный вид. «В отдельном окне» открывает терминал и новое подключение к выбранному серверу. В самом окне можно нажать «На весь экран», чтобы скрыть элементы браузера, если он поддерживает этот режим.")),
                (("Find, paste and preferences", "Поиск, вставка и оформление"),
                 ("Search the terminal output with the search control. The multiline paste prompt lets you verify commands and the destination before inserting them. Open Terminal settings to adjust font, palette and scrollback.",
                  "Поиск находит текст в выводе терминала. Перед многострочной вставкой проверьте команды и выбранную панель. В настройках можно изменить шрифт, палитру и число строк, доступных при прокрутке.")),
                (("Reconnect and end", "Повторное подключение и выход"),
                 ("Use reconnect to start a new connection if a pane disconnects, or close the pane or tab when finished. Local output may still be visible in the workspace until the pane is removed. Recorded replay is separate from this local output.",
                  "Если соединение оборвалось, нажмите кнопку переподключения, чтобы начать новую сессию. По окончании работы закройте панель или вкладку. Пока панель открыта, в ней может оставаться предыдущий вывод. Запись сессии для воспроизведения хранится отдельно.")),
            )), (("SSH client and shell", "SSH-клиент и консоль бастиона"), (
                (("Native SSH", "Подключение из SSH-клиента"),
                 ("Follow the SSH instructions for the resource or use the bastion shell. If SSH asks for browser confirmation, open the provided link, verify the code and target, and confirm only the session you initiated. Return to the client to continue.",
                  "Возьмите команду в карточке ресурса или выберите хост в консоли бастиона. Если клиент предложит подтвердить вход в браузере, перейдите по ссылке и сверьте код и ресурс. Подтвердите сессию, которую начали сами, и вернитесь в клиент.")),
                (("Shell shortcuts", "Команды консоли"),
                 ("On an installation with shell integration, use isolate login and isolate whoami to verify your identity. Use s to search, p to list projects, g with the exact resource ID to connect and f to view your history.",
                  "Если CLI настроен, войдите командой isolate login и проверьте учётную запись командой isolate whoami. В консоли бастиона s ищет ресурсы, p показывает проекты, g с точным ID подключает к ресурсу, f открывает историю.")),
            ))), ("resources", "session-approvals", "monitoring"),
            links=(("/me/terminal", ("Open terminal workspace", "Открыть терминал")),),
        ),
        Guide(
            "protocols", ("Databases, Kubernetes and web apps", "Базы данных, Kubernetes и веб-приложения"),
            ("Use the client and trust settings shown for your resource.", "Как настроить клиент для базы данных или кластера и открыть внутреннее приложение."),
            ((("Choose a protocol", "Подключение по протоколу"), (
                (("PostgreSQL or MySQL", "PostgreSQL или MySQL"),
                 ("Open the resource for the correct protocol, sign in and start the local Isolate proxy using the command on that page. Point your database client at the displayed local address and port and verify the server certificate. In brokered mode use the private local capability file as directed. The policy selects your database identity.",
                  "Откройте карточку базы, войдите в Isolate и запустите локальный прокси командой из инструкции. В клиенте укажите выданный локальный адрес и порт, включите проверку сертификата сервера. Если шлюз выдаёт файл доступа, настройте клиент по инструкции к этому файлу. Учётную запись в базе определяет правило доступа.")),
                (("Kubernetes", "Kubernetes"),
                 ("Use the gateway endpoint, its trusted CA and the Isolate ExecCredential helper in kubeconfig. The gateway passes the verified identity upstream. Streaming operations such as exec, attach, logs, watch and port-forward depend on configuration and may require a separate grant action.",
                  "Укажите в kubeconfig адрес шлюза, доверенный CA и плагин Isolate ExecCredential. Шлюз проверит вашу учётную запись и передаст её кластеру. Доступность операций exec, attach, logs, watch и port-forward зависит от конфигурации. Для них могут требоваться отдельные права.")),
                (("Internal web application", "Внутреннее веб-приложение"),
                 ("For a resource configured as a web application, select Open application. The gateway opens its isolated application domain and checks current access during the session. For a resource configured as an HTTP API, follow the client instructions instead.",
                  "Для веб-приложения нажмите «Открыть приложение». Оно откроется на отдельном домене, а шлюз продолжит проверять права в ходе сессии. Для ресурса в режиме HTTP API настройте клиент по инструкции в карточке.")),
            )),), ("resources", "troubleshooting", "deployment"),
        ),
        Guide(
            "access-requests", ("Request temporary access", "Заявка на временный доступ"),
            ("Request the smallest useful time window and follow its decision.", "Как запросить доступ на нужный срок и узнать решение."),
            ((("Request and track", "Отправка и рассмотрение заявки"), (
                (("Project, host and identity", "Ресурс, учётная запись и sudo"),
                 ("In My requests, choose the project and target host, or a wider scope only when needed. Specify the remote account and sudo mode required by the task. Add a reason and a ticket when requested.",
                  "В разделе «Мои заявки» выберите проект и хост. Укажите удалённую учётную запись, нужный режим sudo и причину доступа. Если форма требует ссылку на задачу, приложите её. Выбирайте доступ ко всему проекту, только когда одного хоста недостаточно.")),
                (("Access window", "Срок доступа"),
                 ("Use the scheduling fields when access should start in the future. Check the interface time zone and the approved start and expiry. Approval can result in an access window narrower than the request.",
                  "Если доступ нужен позже, укажите дату и время начала и окончания. Проверьте часовой пояс интерфейса. Согласующий может сократить срок, поэтому перед работой сверьте даты в решении.")),
                (("Track, cancel or renew", "Статус, отмена и продление"),
                 ("Review status and comments in My requests. Cancel a pending request if no longer needed. Renewal creates another approval request. An expired or revoked grant cannot authorize a new connection.",
                  "Статус и комментарии видны в разделе «Мои заявки». Пока заявка на рассмотрении, её можно отменить. Для продления потребуется новая заявка. После истечения срока или отзыва права по этой заявке новое подключение запрещено.")),
                (("Review as an administrator", "Решение по заявке"),
                 ("Open Access requests, check the ticket, identity, target and window, then approve for a specific duration or deny with a comment. Review visibility and decision rights follow project scope.",
                  "В разделе «Заявки на доступ» проверьте, кто и к какому ресурсу запрашивает доступ, на какой срок и для какой задачи. Согласуйте срок или отклоните заявку с комментарием. Каждому согласующему доступны решения по назначенным проектам.")),
            )),), ("session-approvals", "identity-policy", "notifications"),
            (("/me/access", ("Open my requests", "Открыть мои заявки")),),
        ),
        Guide(
            "session-approvals", ("Approve a connection", "Согласование подключения"),
            ("Approve a specific SSH session when policy requires an additional check.", "Как получить разовое согласование на конкретное SSH-подключение."),
            ((("From request to connection", "Запрос и решение"), (
                (("Request approval", "Запрос на подключение"),
                 ("Open the resource and choose Request approval. Follow the status in My session approvals, then continue the intended connection once approved. The approval is tied to that connection and is consumed when used.",
                  "Откройте ресурс и запросите согласование. Статус виден в разделе «Согласование моих подключений». После одобрения продолжите выбранное подключение. Согласование расходуется при подключении и действует для одной сессии.")),
                (("Approve, deny or revoke", "Одобрение, отказ и отзыв"),
                 ("A permitted reviewer checks the purpose, identity, remote user and destination before deciding on the session. Privileged policies can require multiple different reviewers. Revocation ends authorization at the next applicable check.",
                  "Согласующий проверяет цель подключения, пользователя, удалённую учётную запись и ресурс. Для привилегированного подключения могут понадобиться решения нескольких согласующих. Отзыв учитывается при следующей проверке доступа.")),
            )),), ("access-requests", "terminal", "monitoring"),
            links=(("/me/session-approvals", ("Open my session approvals", "Посмотреть статус согласований")),),
        ),
        Guide(
            "monitoring", ("Sessions, history and replay", "Сессии, история и воспроизведение"),
            ("Inspect a connection and use recordings to understand what happened.", "Где посмотреть активные подключения, историю и запись сессии."),
            ((("Session views", "Поиск и разбор сессии"), (
                (("Active sessions and history", "Активные подключения и история"),
                 ("My sessions shows your connections in progress. My history shows previous connections with filters such as project, host and date. The administration views apply your management permissions and scope. CSV and JSON exports follow the selected filters where available.",
                  "В разделе «Мои сессии» видны ваши активные подключения. Чтобы найти завершённую сессию, отфильтруйте историю по проекту, хосту и дате. Администраторы и аудиторы видят сессии в пределах своих полномочий. Если доступна выгрузка в CSV или JSON, она учитывает выбранные фильтры.")),
                (("Details, live view and termination", "Карточка сессии, наблюдение и завершение"),
                 ("Session details explain the policy decision, identity, destination and audit events. Live view streams authorized output when enabled. Authorized operators can terminate a session where session control is enabled. Check the resource and session ID, enter a reason and confirm.",
                  "В карточке сессии можно проверить, кто и к чему подключился, какое правило сработало и какие события попали в журнал аудита. Если наблюдение включено, можно открыть вывод терминала в реальном времени. Чтобы завершить сессию, сверьте ресурс и ID, укажите причину и подтвердите действие. Для этого нужны соответствующие права.")),
                (("Replay and bookmarks", "Воспроизведение и закладки"),
                 ("Open Replay when a recording is available. Play or pause it, change speed, move the timeline and search the output. Save bookmarks at useful points to revisit them later. Availability and download permissions follow recording policy and retention.",
                  "Если есть запись, откройте её и найдите нужный момент по шкале времени или по тексту вывода. Можно менять скорость, ставить запись на паузу и добавлять закладки. Доступность просмотра и выгрузки зависит от прав и срока хранения.")),
                (("Text transcript", "Текстовая запись"),
                 ("Open the text transcript from the session history or details. Search, copy, or download it as TXT. The interactive SSH recording contains the terminal stream. A command appears if the shell echoes it, and output from multiple jobs can be interleaved. The JSON export encodes line endings and includes timestamps for playback.",
                  "Откройте текстовую запись в истории или в карточке сессии. В ней можно искать, копировать фрагменты и скачивать весь доступный текст в TXT. Запись интерактивной SSH-сессии содержит поток терминала. Команды видны, если их отобразила оболочка, а вывод нескольких задач может идти вперемешку. В JSON переводы строк закодированы, а метки времени нужны для воспроизведения.")),
            )),), ("audit", "terminal", "notifications"),
            links=(("/me/sessions", ("Open my sessions", "Открыть мои сессии")), ("/me/history", ("Open my history", "Открыть мою историю"))),
        ),
    )),
    (("Manage access and operations", "Доступ и операции"), (
        Guide(
            "identity-policy", ("Roles, grants and policy checks", "Роли и правила доступа"),
            ("Separate management scope from connection rights and preview policy changes.",
             "Как Isolate проверяет права и как оценить изменения правил перед применением."),
            ((("How authorization works", "Как Isolate принимает решение"), (
                (("Identity and project roles", "Учётная запись и роли в проектах"),
                 ("The platform administrator has global controls. Project roles, such as approver, inventory operator and auditor, apply only to their assigned projects and operations. Isolate checks the verified OIDC identity and permissions on each route and resource.",
                  "Администратор платформы управляет общими настройками. Согласующий, оператор инвентаря и аудитор выполняют свои операции в назначенных проектах. Isolate проверяет учётную запись через OIDC и отдельно проверяет права на действия и ресурсы.")),
                (("Grant fields and project sets", "Правила доступа и наборы проектов"),
                 ("In Access rules choose the subject type and subject name, then a host, project, project set or other supported selector. The selector limits the target. Set the remote account, sudo mode, allowed actions and any time bounds. An exact project set can be reused across grants and may also contain glob patterns.",
                  "В правилах доступа укажите, кому выдаёте право, например пользователю или группе. Задайте область: хост, проект, набор проектов или другой доступный критерий. Укажите удалённую учётную запись, режим sudo, действия и срок. Один набор проектов можно использовать в нескольких правилах. В наборе допустимы точные имена и шаблоны.")),
            )), (("Check before applying", "Проверка изменений"), (
                (("Access matrix", "Матрица доступа"),
                 ("Inspect effective access by subject and project, check policy findings and export results if needed. The matrix describes policy scenarios. Each live decision can also depend on identity, session conditions and timing.",
                  "В матрице видны права пользователей, групп и ролей по проектам. Здесь можно проверить замечания к правилам и выгрузить результат. При подключении Isolate также проверяет, кто вошёл, на какой срок выдано право и какие условия применяются к сессии.")),
                (("Simulator and impact preview", "Симулятор и оценка влияния"),
                 ("Use the simulator to see the selected rule for a proposed user, resource and action. In impact preview select add, replace or remove. Enter the current grant ID for replacement or removal and inspect what access is gained, lost or changed before saving the real edit.",
                  "В симуляторе укажите пользователя, ресурс и действие, чтобы увидеть сработавшее правило. Для оценки изменений выберите нужную операцию: добавление, замену или удаление. При замене или удалении укажите ID правила. Перед сохранением проверьте, где права появятся, исчезнут или изменятся.")),
            ))), ("packages", "governance", "gitops"),
            links=(("/grants", ("Open access rules", "Открыть правила доступа")), ("/policy/matrix", ("Open access matrix", "Открыть матрицу доступа"))),
        ),
        Guide(
            "inventory", ("Inventory and maintenance", "Инвентарь и обслуживание"),
            ("Maintain host records, metadata and planned service changes.", "Как вести карточки хостов, планировать обслуживание и отслеживать изменения сервисов."),
            ((("Host record", "Карточка хоста"), (
                (("Add or edit a host", "Добавление и настройка хоста"),
                 ("In Inventory select Add host or open a record to edit it. The project defines scope. Name identifies the host in search. Address and port define its connection route. The default remote user can be replaced by a matching grant. Set a proxy only when your deployment allows that route.",
                  "В инвентаре добавьте хост или откройте его карточку. Выберите проект, задайте имя для каталога, адрес и порт для подключения. Укажите удалённую учётную запись по умолчанию. Правило доступа может переопределить её. Задавайте прокси-хост, если этот маршрут разрешён в вашей установке.")),
                (("Enroll from Ansible", "Подключение из Ansible"),
                 ("The enrollment playbook installs the bastion public key for the remote account, configures trust for the server's host key, and checks SSH before registering the host through the inventory API. The automation account needs inventory write access for the target project.",
                  "Плейбук устанавливает публичный ключ бастиона для удалённой учётной записи, настраивает доверие к ключу сервера и проверяет SSH перед регистрацией через API инвентаря. Служебной учётной записи Ansible нужен доступ на запись в инвентарь этого проекта.")),
                (("Owner, environment and tags", "Владелец, окружение и теги"),
                 ("Record the accountable team, environment, service list and structured tags so operators can find and identify the right target. Review the selected hosts before a bulk update. Project operators can edit permitted metadata within their project, subject to server-side restrictions.",
                  "Укажите команду-владельца, окружение, сервисы и теги, по которым коллеги смогут найти хост. Перед массовым изменением сверьте список выбранных хостов. Оператор проекта может менять только разрешённые поля в своих проектах.")),
                (("Maintenance and service changes", "Окно обслуживания и список сервисов"),
                 ("Set a maintenance end time and reason from the supported administration controls. Maintenance stops new connections subject to policy. The Services view shows the discovery baseline and changes after successful discovery. Use approved runbooks for permitted remote work.",
                  "Укажите, до какого времени продлится обслуживание, и добавьте причину. Isolate учитывает это окно при проверке новых подключений. В разделе сервисов можно сравнить исходный список с результатами последней успешной проверки. Для удалённых работ используйте утверждённые регламенты.")),
            )),), ("resources", "automation", "notifications"),
            links=(("/inventory", ("Open inventory", "Открыть инвентарь")),),
        ),
        Guide(
            "packages", ("Access packages", "Пакеты доступа"),
            ("Bundle access rules, assign them and manage revisions.", "Как собрать набор правил, назначить его и обновить без потери истории."),
            ((("Create and assign", "Создание и назначение"), (
                (("Package rules", "Состав пакета"),
                 ("In Access packages define a name, status and the access rules it contains. Each rule describes a target scope, remote account, sudo mode and allowed actions. Default and maximum duration bound new timed assignments. Approval requirements determine who reviews assignments and whether a ticket is needed.",
                  "В разделе пакетов доступа задайте название, статус и состав правил. В каждом правиле укажите ресурсы, удалённую учётную запись, режим sudo и действия. Для временных назначений задайте срок по умолчанию и максимальный срок. В условиях согласования укажите, кто принимает решение и требуется ли ссылка на задачу.")),
                (("Assign", "Назначение пакета"),
                 ("Choose the intended user, group or role, duration and ticket. Confirm the assignment. The platform generates managed grants from the package. Update those grants through the package lifecycle.",
                  "Выберите пользователя, группу или роль. Укажите срок и приложите ссылку на задачу, если она нужна. После подтверждения Isolate создаст правила из пакета. Меняйте эти правила через пакет.")),
                (("Preview, apply and rollback", "Проверка, обновление и откат"),
                 ("Preview shows affected assignments and grant changes. Apply a reviewed revision after confirming. Select an older revision to roll back. Rollback creates a new revision and keeps the history. Review the current version again after a conflicting edit.",
                  "Перед обновлением проверьте, какие назначения и правила затронет новая версия. Для отката выберите прежнюю версию. Isolate создаст новую версию с её содержимым, а история сохранится. Если пакет успели обновить параллельно, перечитайте текущую версию и проверьте изменения заново.")),
            )),), ("identity-policy", "governance"),
            links=(("/packages", ("Open packages", "Открыть пакеты доступа")),),
        ),
        Guide(
            "governance", ("Access reviews and offboarding", "Пересмотр и отзыв доступа"),
            ("Review whether access is still needed and revoke assignments with an audit trail.",
             "Как проверить, кому ещё нужен доступ, и отозвать устаревшие назначения."),
            ((("Lifecycle actions", "Работа с назначениями"), (
                (("Assignments and expiry", "Список назначений и сроки"),
                 ("Open Access lifecycle. Review assignees, owners, project scope and expiration. Give contractors time-bounded access when policy requires it. A temporary grant stops authorizing once it expires.",
                  "Откройте раздел «Проверка выданных прав». Проверьте получателей, владельцев, проекты и даты окончания. Если правила вашей организации это предусматривают, выдавайте подрядчикам доступ на ограниченный срок. По его истечении назначение перестаёт давать право на подключение.")),
                (("Owner review", "Пересмотр доступа владельцем"),
                 ("Open the outstanding review and inspect each assignment in scope. Record the decision and its reason. Confirm the action in the workflow before moving to the next assignment.",
                  "Откройте пересмотр, по которому ещё нужно принять решение и проверьте каждое назначение в пределах своих прав. Для каждого запишите решение и причину. Подтвердите решение перед переходом к следующему назначению.")),
                (("Revoke access or offboard", "Отзыв назначения и отключение пользователя"),
                 ("Use revoke for an individual assignment or offboarding for the selected identity. Confirm the identity, project, reason and intended effect on active sessions where the workflow offers that option. Follow recorded outcomes in investigation and session views.",
                  "Отзовите отдельное назначение или отключите доступ пользователя. Перед подтверждением сверьте учётную запись, проект, причину и выбранное действие с активными сессиями, если этот параметр доступен. Результат можно проверить в расследовании и в списке сессий.")),
            )),), ("packages", "access-requests", "audit"),
            links=(("/workspace/governance", ("Open access lifecycle", "Проверить выданные права")),),
        ),
        Guide(
            "automation", ("Runbooks, campaigns and jobs", "Регламенты и поэтапные запуски"),
            ("Execute approved work and follow per-host results through staging and retries.",
             "Как запустить утверждённую операцию и найти результат по каждому хосту."),
            ((("One job or staged rollout", "Запуск операции"), (
                (("Runbook and parameters", "Выбор регламента и параметров"),
                 ("In Jobs & runbooks choose an approved task, target host or fleet and the required parameters. JSON parameters must match the runbook definition. Review the selected resource IDs and confirm before queueing. Arbitrary commands require a separately enabled mode and matching authorization.",
                  "В разделе «Задания и регламенты» выберите утверждённый регламент (runbook), укажите хост или группу и заполните обязательные параметры. Перед запуском сверьте ID ресурсов и проверьте, что поля JSON соответствуют регламенту. Произвольная команда доступна при включённом режиме и наличии отдельных прав.")),
                (("Create a custom runbook", "Создание своего регламента"),
                 ("Platform administrators can open Manage runbooks to save a draft, preview the command with sample parameters and publish a version. Custom runbooks use the operational class and require an operate grant on the target. Queued work keeps the reviewed version. Retiring a version blocks further starts with that version.",
                  "Администратор может открыть «Управление регламентами», сохранить черновик, проверить команду на примере параметров и опубликовать версию. Свои регламенты относятся к операционным. Для запуска нужно право operate на целевой сервер. В очереди сохраняется проверенная версия. После отзыва этой версии новые задания с ней не запустятся.")),
                (("Canary and batches", "Пробный запуск и следующие группы"),
                 ("For staged operations choose host IDs, canary size, later batch size and the allowed failure count and percentage. Review plan shows the exact target order and remote accounts. Review the stop conditions, then Start canary to submit the campaign.",
                  "Для поэтапного запуска (campaign в API) укажите ID хостов, размеры пробной и следующих групп, допустимое число и долю ошибок. В плане проверьте порядок хостов, удалённые учётные записи и условия остановки. Затем запустите операцию на пробных хостах.")),
                (("Stop conditions", "Условия остановки"),
                 ("Every canary job must succeed before the later batches can advance. Failures beyond the chosen threshold, expired or revoked access and uncertain results stop new work. Stop campaign prevents future batches and requests cancellation of active jobs.",
                  "Isolate запускает следующую группу, когда все пробные задания прошли успешно. Превышение порога ошибок, истечение или отзыв доступа либо неизвестный результат останавливают запуск новых заданий. При ручной остановке Isolate прекращает запуск следующих групп и запрашивает отмену активных заданий.")),
                (("Output, cancel and retry", "Вывод команды и повтор задания"),
                 ("Open the campaign and the job for the affected host. Review status, captured output and exit code when available. The job page shows its authorization and execution details. Cancel or retry only an eligible job. Investigate an uncertain remote outcome before starting another attempt.",
                  "В карточке запуска откройте задание нужного хоста. В нём видны статус, попытки, сохранённый вывод команды и код завершения, если он известен. Там же можно проверить параметры выполнения и сведения о доступе. Если результат неизвестен, сначала проверьте, что изменилось на хосте. Затем решите, можно ли повторить задание.")),
            )),), ("inventory", "audit", "notifications"),
            (("/jobs", ("Open jobs", "Открыть задания")), ("/operations/campaigns", ("Open campaigns", "Открыть поэтапные запуски"))),
        ),
        Guide(
            "audit", ("Audit and investigations", "Аудит и расследования"),
            ("Find evidence and follow related events across sessions, access and jobs.",
             "Как связать решение о доступе с подключением, записью сессии или результатом задания."),
            ((("Find and correlate evidence", "Поиск и разбор событий"), (
                (("Overview and audit search", "События журнала аудита"),
                 ("The overview summarizes active sessions, duration and recent audit activity where configured. Use audit search to filter indexed events by identity, project, time or identifiers. Missing or unavailable data should be checked at its source before drawing a conclusion.",
                  "На обзорной странице видны активные сессии, их длительность и последние события аудита, если настроен сбор данных. В журнале аудита выберите учётную запись, проект, время или идентификатор. Если записей нет, проверьте, поступают ли события в индекс.")),
                (("Investigation timeline", "Хронология расследования"),
                 ("Open an investigation from a related job, campaign or session where offered, or select the entity by type and ID. Read the events in order and compare the actor, decision, connection and job outcome. Follow links to the evidence available in your scope.",
                  "Откройте расследование по ссылке из карточки задания, поэтапного запуска или сессии. Если ссылки нет, укажите тип объекта и его ID. По хронологии проверьте, кто инициировал действие, какое решение принял Isolate и чем всё закончилось. Ссылки на связанные записи доступны в пределах ваших прав.")),
                (("Record sources and exports", "Запись сессии и выгрузка"),
                 ("Connection records and structured events have different sources. Captured terminal output can be replayed where retained. Structured command events require the associated instrumentation. Use page exports for authorized evidence and preserve its filters and time range in the case record.",
                  "История подключений и журнал аудита собираются из разных источников. Запись терминала можно воспроизвести, пока она хранится. Отдельные события о командах появляются в журнале, если настроен их сбор. При выгрузке укажите фильтры и период, по которым собрали материалы.")),
            )),), ("monitoring", "automation", "recovery"),
            links=(("/audit/search", ("Open audit search", "Открыть журнал аудита")), ("/investigations", ("Open investigations", "Открыть расследования"))),
        ),
        Guide(
            "notifications", ("Alerts, announcements and delivery", "Оповещения и объявления"),
            ("Follow security signals and communicate planned work to the right audience.",
             "Как разобраться в оповещении, предупредить коллег о работах и проверить доставку."),
            ((("Operational messages", "События и сообщения"), (
                (("Alert center", "Разбор оповещений"),
                 ("Use severity and source context to prioritize unusual, privileged or long-running sessions, failed jobs and delivery errors. Follow the source link before acknowledging an alert. Acknowledgement records review and leaves the underlying issue for investigation.",
                  "Учитывайте критичность и источник. Например, проверьте необычно долгую или привилегированную сессию либо ошибку задания. Перед отметкой о прочтении откройте связанное событие. Отметка показывает, кто взял оповещение в работу.")),
                (("Announcements", "Объявления о работах"),
                 ("Set the audience with the global, project or host scope, choose severity and give an expiry. Use a short message with the intended time and action. Announcements can be shown during search and before connection.",
                  "Выберите, кто увидит сообщение: все пользователи, участники проекта или пользователи конкретного хоста. Задайте важность и срок публикации. Напишите, когда пройдут работы и что нужно сделать. Объявление может появиться в каталоге и перед подключением.")),
                (("Notification delivery", "Доставка уведомлений"),
                 ("Open Notifications to inspect configured channel types and access-request or session-alert delivery results. On error, inspect the event and verify the destination through your deployment configuration. A delivery error does not change the original access decision.",
                  "В разделе уведомлений проверьте, по каким каналам отправили сообщения о заявках или сессиях. При ошибке откройте событие и проверьте настройки получателя. Решение по заявке действует независимо от доставки сообщения.")),
                (("People and activity", "Учётные записи и активность"),
                 ("Users lists observed identities. Open a user to inspect activity, groups, grants, requests and session history available to the operator. Manage the source account and membership in the identity provider.",
                  "В разделе «Пользователи» собраны учётные записи, с которыми уже работал Isolate. Откройте карточку, чтобы посмотреть группы, права, заявки и историю. Изменяйте учётную запись и группы у провайдера OIDC.")),
            )),), ("access-requests", "audit"),
            links=(("/alerts", ("Open alert center", "Открыть оповещения")), ("/announcements", ("Open announcements", "Открыть объявления")), ("/notifications", ("Open delivery status", "Проверить доставку"))),
        ),
        Guide(
            "gitops", ("Signed policy GitOps", "GitOps для подписанных правил доступа"),
            ("Review drift, sync approved policy and recover from a faulty revision.",
             "Как сравнить версии, применить согласованное изменение или откатить его."),
            ((("Revision lifecycle", "Проверка и применение версий"), (
                (("Review and compare", "Проверка расхождений"),
                 ("When GitOps is configured, inspect the approved revision, deployed revision and drift. Review the candidate and impact before applying. In enforced mode edit the source bundle and use the approved Git workflow for policy changes.",
                  "Если настроен GitOps, сравните согласованную версию с действующей и проверьте расхождения. Перед применением оцените влияние на доступ. Если правила можно менять только через Git, внесите исправление в исходный пакет и проведите его через ревью.")),
                (("Sync approved revision", "Синхронизация правил"),
                 ("Review the repository, branch, signature and approval status. Confirm synchronization of the approved revision. Recheck the deployed revision, audit record and expected policy outcomes after the change.",
                  "Сверьте репозиторий, ветку, подпись и статус согласования. Подтвердите применение версии. После обновления убедитесь, что Isolate использует нужную версию, проверьте запись в журнале аудита и контрольные сценарии доступа.")),
                (("Rollback revision", "Откат правил"),
                 ("Choose the reviewed snapshot and confirm rollback. Coordinate automatic sync first if it would reapply the newer revision. Recheck access and reconcile Git before resuming normal sync.",
                  "Выберите проверенный снимок и подтвердите откат. Если автосинхронизация может снова применить новую версию, сначала согласуйте паузу. Проверьте доступ и обновите версию в Git перед возобновлением синхронизации.")),
            )),), ("identity-policy", "recovery"),
            links=(("/policy/gitops", ("Open GitOps", "Открыть GitOps")),),
        ),
    )),
    (("Deploy and integrate", "Развёртывание и интеграции"), (
        Guide(
            "deployment", ("Installation and updates", "Установка и обновления"),
            ("Plan a host or Kubernetes deployment and validate the entire connection path.",
             "Как развернуть Isolate на сервере или в Kubernetes и проверить вход и подключение."),
            ((("Prepare and configure", "Подготовка и настройки"), (
                (("Installation options", "Варианты установки"),
                 ("Use Ansible for a managed host, the production image for containers or the Helm chart for Kubernetes. Use the Docker demo for a disposable trial. Choose a release and review its dependencies, runtime account and storage requirements before applying it.",
                  "Для управляемого сервера используйте Ansible, для контейнерной установки — образ релиза, для Kubernetes — Helm-чарт. Docker-демо подходит для отдельного тестового стенда. Выберите версию и проверьте зависимости, служебную учётную запись и хранилища.")),
                (("Private setup and identity", "Первоначальная настройка и вход"),
                 ("Use the setup tool to configure the portal origin, identity provider and state backend. Register the exact HTTPS /auth/callback address in the IdP. Browser login uses Authorization Code with PKCE S256. Native CLI login needs a provider that supports Device Authorization. Store credentials in protected files or workload secret storage.",
                  "Укажите адрес портала, провайдера OIDC и хранилище. У провайдера зарегистрируйте точный HTTPS-адрес с путём /auth/callback. Для портала используется Authorization Code с PKCE S256. Для входа в CLI провайдер должен поддерживать Device Authorization. Храните учётные данные в защищённом файле или хранилище секретов.")),
                (("State and gateway", "Хранилища, шлюз и TLS"),
                 ("Choose the supported authoritative store for inventory and policy. Redis handles leases and cache and can also serve as the legacy authority. Optional SQL authority must be initialized and migrated deliberately. Configure trusted TLS for the portal and gateway, and provision an isolated origin for each proxied web application.",
                  "Выберите основное хранилище инвентаря и правил. Redis хранит состояние краткосрочных сессий и кэш, а в режиме совместимости — основные данные. Для SQL-хранилища подготовьте схему и выполните миграцию. Настройте доверенный TLS для портала и шлюза. Для каждого проксируемого веб-приложения задайте отдельный адрес.")),
            )), (("Verify and roll out", "Проверка и обновление"), (
                (("Health, readiness and smoke checks", "Проверки готовности и подключения"),
                 ("Run configuration validation as the runtime account so file permissions are checked correctly. Check /health for the dashboard and the configured readiness endpoints for the ingress and worker. Complete a fresh OIDC sign-in and verify authorization, a test connection and recording on an approved resource.",
                  "Проверьте конфигурацию от имени служебной учётной записи, чтобы убедиться, что процесс читает нужные файлы. Откройте /health портала и проверьте готовность шлюза и воркера. Пройдите новый вход через OIDC, подключитесь к разрешённому тестовому ресурсу и убедитесь, что сессия записывается, если запись включена.")),
                (("Release flow", "Активация релиза"),
                 ("For versioned releases use plan, stage and verify before activation. Keep a verified backup and drain old ingress before restarting components that own active connections. Check health and critical workflows after switching. Code rollback and state recovery are distinct operations.",
                  "Перед активацией выполните plan, stage и verify. Подготовьте проверенную резервную копию. Перед перезапуском процессов, которые держат подключения, переведите старый шлюз в режим завершения активных сессий. После переключения проверьте состояние системы и основные сценарии. Откат приложения и восстановление данных выполняются отдельно.")),
            ))), ("recovery", "troubleshooting", "protocols"),
            (("/health", ("Check portal health", "Проверить /health портала")),),
            "isolate config validate --check-paths\nisolate health --json",
        ),
        Guide(
            "recovery", ("Backup, recovery and retention", "Резервные копии и восстановление"),
            ("Verify archives and rehearse recovery before it is needed.", "Как проверить архив, отработать восстановление и настроить хранение записей."),
            ((("Protect and verify state", "Резервные копии и журналы"), (
                (("Create and verify backups", "Создание и проверка копии"),
                 ("Use the service backup tool to archive configured paths and configured Redis key patterns. Verify the manifest and checksum. Include the authoritative SQL database, recording storage or audit index in their own backup plans where enabled. Keep verified archives in restricted off-host storage because they can contain credentials.",
                  "Сохраните настроенные пути и выбранные ключи Redis. Проверьте манифест и контрольную сумму копии. Для SQL, архива записей или индекса аудита подготовьте отдельные процедуры, если эти компоненты используются. Храните проверенные копии вне рабочего хоста и ограничьте к ним доступ. В архив могут попасть учётные данные.")),
                (("Restore in a test environment", "Пробное восстановление"),
                 ("Restore to a staging filesystem and disposable datastore first. Check inventory and grants, configuration and file ownership, IdP connectivity, access decisions and an authorized test connection. Plan conflict handling and session drainage before a live restore.",
                  "Распакуйте копию во временный каталог и загрузите данные в отдельное тестовое хранилище. Проверьте инвентарь, правила, настройки и владельцев файлов. Проверьте вход через OIDC, решение о доступе и разрешённое тестовое подключение. Перед восстановлением рабочей среды согласуйте, что делать с конфликтами данных и активными сессиями.")),
                (("Retention and audit pipeline", "Хранение записей и журнал аудита"),
                 ("Set session log retention and archive recordings separately if the service backup excludes them. Review a dry run before pruning. A central audit index helps search events, and configured sinks can forward them to your monitoring stack. Track index freshness and delivery errors.",
                  "Задайте срок хранения журналов сессий. Архивируйте записи отдельно, если они не входят в резервную копию. Перед очисткой запустите пробный прогон и проверьте список файлов. Если используется поисковый индекс или отправка событий в мониторинг, следите за актуальностью индекса и ошибками доставки.")),
            )),), ("deployment", "audit"), example="isolate backup list\nisolate backup verify --archive /path/to/backup.tar.gz",
        ),
        Guide(
            "integrations", ("CLI, API, Terraform and MCP", "CLI, API, Terraform и MCP"),
            ("Choose a supported integration and restrict its authorization to the job.",
             "Как подключить инструменты автоматизации и выдать им права на нужные действия."),
            ((("Choose an interface", "Инструменты и права"), (
                (("Command line", "Командная строка"),
                 ("The CLI supports OIDC sign-in and identity checks, inventory and grant administration, access packages and requests, history and exports, runbooks, diagnostics, policy management and service backups. Use isolate --help or the corresponding subcommand help for flags and confirm options.",
                  "Через CLI можно войти по OIDC, проверить учётную запись, управлять инвентарём, правилами, пакетами и заявками. Доступны также история и экспорт, регламенты, диагностика и резервные копии. Используйте isolate --help или справку подкоманды, чтобы проверить параметры и порядок подтверждения.")),
                (("OpenAPI", "OpenAPI"),
                 ("Use the versioned OpenAPI contract to discover operations and schemas. Connect over trusted HTTPS using a short-lived token with the required scopes and project rights. For administration writes follow the contract's confirmation, idempotency and revision requirements. Refresh state after a concurrent edit or uncertain outcome.",
                  "В OpenAPI описаны версии операций и форматы запросов. Подключайтесь по доверенному HTTPS с краткоживущим токеном и правами на нужный проект. Для изменений учитывайте требования к подтверждению, повторным запросам и версии объекта. После конфликта или неизвестного результата заново прочитайте текущее состояние.")),
                (("Terraform", "Terraform"),
                 ("The included provider manages host and grant resources through the admin API. Build or install your organization's approved binary, review the plan and import existing resources when appropriate. Use a private token file or configured workload identity. Keep token material out of Terraform state and plans.",
                  "Провайдер Terraform из репозитория Isolate управляет хостами и правилами через административный API. Установите или соберите утверждённую версию провайдера, проверьте план и при необходимости импортируйте существующие ресурсы. Передавайте токен через защищённый файл или используйте служебную учётную запись. Храните токены вне планов и файлов состояния Terraform.")),
                (("MCP and workloads", "MCP и служебные учётные записи"),
                 ("Enable MCP only for approved clients. Published tools still require matching scopes and policies. Select a reviewed runbook for approved command execution. Workload identities have separate bindings and project limits. Verify which actions are actually exposed before integrating a client.",
                  "Включайте MCP для согласованных клиентов. Доступ к каждому инструменту проверяется по областям токена и правилам доступа. Для штатной удалённой операции используйте утверждённый регламент. Выдавайте служебным учётным записям права отдельно и ограничивайте их нужными проектами. Перед подключением проверьте, какие действия доступны клиенту.")),
            )),), ("sign-in", "identity-policy", "automation"),
            links=(("/api/v1/openapi.json", ("Open API contract (JSON)", "Открыть OpenAPI (JSON)")),),
        ),
        Guide(
            "troubleshooting", ("Troubleshoot common problems", "Проблемы со входом, доступом и заданиями"),
            ("Find the right next check when sign-in, access or a connection fails.",
             "Что проверить, если портал вернул ошибку или операция остановилась."),
            ((("Check the failing step", "Диагностика по симптомам"), (
                (("Sign-in or 401", "Не удаётся войти или ошибка 401"),
                 ("Start a fresh sign-in from the portal. Operators should check the configured issuer, HTTPS callback, CA trust and IdP availability. Record the time and request ID when reporting an issue. Keep tokens and credentials out of the report.",
                  "Начните новый вход с портала. Администратору стоит проверить адрес issuer, HTTPS-адрес обратного вызова, доверие к CA и доступность провайдера OIDC. При обращении укажите время и ID запроса. Передавайте токены и учётные данные только через предназначенные для них защищённые каналы.")),
                (("403 or missing resource", "Ошибка 403 или ресурс не виден"),
                 ("Check the filters, your groups, project scope and protocol. Open Why this access? if the card is visible. Ask the project owner to verify the relevant grant, maintenance window, additional approval and other requirements.",
                  "Проверьте фильтры, группу, проект и протокол. Если ресурс виден, откройте «Условия доступа». Владелец ресурса может проверить правило, окно обслуживания и необходимость согласования.")),
                (("Connection or certificate error", "Не удаётся подключиться или проверить сертификат"),
                 ("Confirm that the resource and protocol match the client instructions. Verify the gateway certificate against the approved CA. If the resource was available before, ask an operator to check gateway readiness, target availability and credential configuration under its runtime account.",
                  "Сверьте ресурс и протокол с инструкцией в карточке. Проверьте сертификат шлюза и доверие к его CA. Если подключение раньше работало, попросите оператора проверить готовность шлюза, доступность цели и чтение учётных данных от имени служебной учётной записи.")),
                (("Job failed or result is unknown", "Ошибка задания или неизвестный результат"),
                 ("Open the job and inspect the target, last stage, attempt, output and exit code. Use the investigation timeline for related events. If the remote result is uncertain, confirm the target state before attempting the operation again.",
                  "Откройте задание. Проверьте ресурс, последний этап, попытку, вывод команды и код завершения. Связанные события можно найти через расследование. Если результат неизвестен, сначала выясните, успела ли операция изменить состояние хоста. После этого решите, нужен ли повтор.")),
            )),), ("sign-in", "resources", "automation", "deployment"),
        ),
    )),
)


GUIDES = {guide.key: guide for _, group in GUIDE_GROUPS for guide in group}


WORKFLOWS = {
    "sign-in": Workflow(
        ("From sign-in to the catalogue", "От входа до каталога"),
        (
            ("shield", ("Open Isolate", "Откройте портал"),
             ("Start sign-in in the browser.", "Начните вход в браузере.")),
            ("key-round", ("Sign in with your provider", "Войдите через OIDC"),
             ("Use your account and complete MFA if prompted.", "Используйте свою учётную запись. Пройдите MFA, если его запросит провайдер.")),
            ("layout-dashboard", ("Return to Isolate", "Вернитесь в Isolate"),
             ("Open the catalogue. Isolate checks access when you connect.", "Откройте каталог. При подключении Isolate проверит ваши права.")),
        ),
    ),
    "resources": Workflow(
        ("From the catalogue to a connection", "От каталога до подключения"),
        (
            ("search", ("Find the resource", "Найдите ресурс"),
             ("Search by name or narrow the list by project and protocol.", "Введите имя или отберите ресурсы по проекту и протоколу.")),
            ("file-text", ("Open its details", "Откройте карточку"),
             ("Confirm that the host, project and protocol match your task.", "Сверьте хост, проект и протокол.")),
            ("shield-check", ("Check access", "Проверьте доступ"),
             ("Read the rule and current conditions in “Why this access?”.", "В разделе «Условия доступа» проверьте правило и действующие условия.")),
        ),
        ("What can you do next?", "Что делать дальше?"),
        (
            ("pass", ("You can connect", "Доступ открыт"),
             ("Open Web SSH or follow the instructions for your client.", "Откройте Web SSH или настройте клиент по инструкции.")),
            ("wait", ("Access has a condition", "Доступ с условиями"),
             ("Request approval or sign in again as indicated.", "Запросите согласование или войдите повторно, как указано в карточке.")),
            ("stop", ("Access is missing", "Прав на подключение нет"),
             ("Submit an access request if the resource offers that option.", "Подайте заявку, если эта возможность есть в карточке.")),
        ),
    ),
    "terminal": Workflow(
        ("How an SSH connection starts", "Как открывается SSH-сессия"),
        (
            ("server", ("Choose the SSH resource", "Выберите SSH-ресурс"),
             ("Select Web SSH or copy the command for your client.", "Откройте Web SSH или скопируйте команду для своего клиента.")),
            ("shield-check", ("Isolate checks access", "Isolate проверяет права"),
             ("The gateway checks your account, access rules and session requirements.", "Шлюз проверяет учётную запись, правила доступа и условия подключения.")),
            ("terminal", ("Start the connection", "Начните подключение"),
             ("A successful connection opens a terminal on the target.", "После подключения терминал готов к работе на целевом хосте.")),
        ),
        ("If the terminal does not open", "Если терминал не открылся"),
        (
            ("wait", ("Verification or approval required", "Нужен повторный вход или согласование"),
             ("Complete the step shown in the resource or in your SSH client.", "Следуйте инструкции в карточке ресурса или в SSH-клиенте.")),
            ("stop", ("Access denied or target unavailable", "Доступ закрыт или хост недоступен"),
             ("Check the access explanation, then check reachability if the rule allows you in.", "Откройте условия доступа. Если права есть, проверьте доступность хоста.")),
        ),
    ),
    "access-requests": Workflow(
        ("Getting a right that expires", "Как получить доступ на время"),
        (
            ("file-text", ("Submit a request", "Подайте заявку"),
             ("Specify the resource, account, reason and access window.", "Укажите ресурс, учётную запись, причину и нужный срок.")),
            ("users", ("A reviewer checks the scope", "Согласующий проверяет заявку"),
             ("The project reviewer checks why access is needed and for how long.", "Ответственный за проект проверяет цель и срок доступа.")),
            ("clock", ("Check the decision", "Проверьте решение"),
             ("Open your request and confirm its status and approved dates.", "Откройте заявку и сверьте статус и согласованные даты.")),
        ),
        ("What does the decision allow?", "Что даёт решение по заявке?"),
        (
            ("pass", ("Approved", "Одобрено"),
             ("Connect within the approved window. Session approval can still be required.", "Подключитесь в согласованный срок. Для отдельной сессии может ещё требоваться согласование.")),
            ("wait", ("Pending", "На рассмотрении"),
             ("Wait for a decision and check the status in My requests.", "Дождитесь решения и проверьте статус в разделе «Мои заявки».")),
            ("stop", ("Denied, expired or revoked", "Отклонено, истекло или отозвано"),
             ("The request cannot authorize a new connection.", "По этой заявке новое подключение недоступно.")),
        ),
    ),
    "session-approvals": Workflow(
        ("Approving one SSH connection", "Как согласовать одно подключение"),
        (
            ("terminal", ("Start at the resource", "Откройте ресурс"),
             ("Request approval for the intended SSH connection.", "Запросите согласование нужного SSH-подключения.")),
            ("users", ("A reviewer checks the session", "Согласующий проверяет подключение"),
             ("The decision may need more than one reviewer.", "Для некоторых подключений решение принимают несколько согласующих.")),
            ("shield-check", ("Return to the connection", "Вернитесь к подключению"),
             ("Check the status before you continue.", "Перед подключением проверьте статус согласования.")),
        ),
        ("Can the connection continue?", "Можно ли подключиться?"),
        (
            ("pass", ("Approved and valid", "Одобрено и действует"),
             ("Continue the connection. It consumes the one-time approval.", "Продолжите подключение. Согласование действует однократно.")),
            ("wait", ("Pending", "Ждёт согласования"),
             ("Wait for all required reviewers to approve before connecting.", "Дождитесь решения от всех согласующих, которых требует правило.")),
            ("stop", ("Denied, revoked or expired", "Отклонено, отозвано или истекло"),
             ("The approval cannot authorize the connection.", "Это согласование больше не даёт права подключиться.")),
        ),
    ),
    "monitoring": Workflow(
        ("Finding the output of an SSH session", "Где найти вывод SSH-сессии"),
        (
            ("search", ("Find the connection", "Найдите подключение"),
             ("Use active sessions or filter history by project, host and date.", "Откройте активные сессии или отфильтруйте историю по проекту, хосту и дате.")),
            ("file-clock", ("Open the session details", "Откройте карточку сессии"),
             ("Compare the session ID, resource and time with the intended connection.", "Сверьте ID сессии, ресурс и время подключения.")),
        ),
        ("Is the session still running?", "Сессия ещё идёт?"),
        (
            ("detail", ("Active session", "Сессия активна"),
             ("Open the live view if enabled to follow new terminal output.", "Откройте просмотр в реальном времени, если он доступен. По мере работы в нём появляется новый вывод.")),
            ("detail", ("Completed session", "Сессия завершена"),
             ("Open the recording if retained and seek to the event of interest.", "Если запись сохранилась, откройте её и найдите нужный момент по шкале времени.")),
        ),
    ),
    "identity-policy": Workflow(
        ("How Isolate evaluates access", "Как Isolate проверяет доступ"),
        (
            ("key-round", ("Verify the account", "Проверка учётной записи"),
             ("Use the account and group claims verified through OIDC.", "Isolate использует учётную запись и группы из проверенных данных OIDC.")),
            ("list-filter", ("Match access rules", "Поиск подходящего правила"),
             ("Compare the subject, resource and action with the rule and its validity period.", "Isolate сверяет пользователя, ресурс, действие и срок правила.")),
            ("shield-check", ("Check current conditions", "Проверка условий подключения"),
             ("Check the maintenance window and any additional session requirements.", "Isolate учитывает обслуживание хоста и дополнительные требования к сессии.")),
        ),
        ("Access decision", "Решение о доступе"),
        (
            ("pass", ("Allowed", "Разрешено"),
             ("Connect with the remote account and sudo mode selected by the rule.", "Подключение открывается с учётной записью и режимом sudo из правила.")),
            ("wait", ("Extra verification", "Нужна дополнительная проверка"),
             ("Complete sign-in or obtain the required session approval.", "Войдите повторно или получите согласование подключения.")),
            ("stop", ("Denied", "Запрещено"),
             ("Check the access explanation or use the policy simulator before changing rules.", "Откройте условия доступа или проверьте правило в разделе «Проверка доступа».")),
        ),
    ),
    "automation": Workflow(
        ("From the runbook plan to a host's result", "От плана запуска до вывода команды"),
        (
            ("file-text", ("Review the plan", "Проверьте план"),
             ("Check the runbook, host order, remote accounts and stop conditions.", "Сверьте регламент, порядок хостов, учётные записи и условия остановки.")),
            ("workflow", ("Run on canary hosts", "Выполните пробный запуск"),
             ("Isolate starts the jobs on the first, smaller group of hosts.", "Isolate запускает задания на небольшой группе хостов.")),
            ("activity", ("Inspect host results", "Откройте вывод по хосту"),
             ("Open a host's job in the campaign to read its attempts, output and exit code.", "Найдите в списке заданий нужный хост. Откройте задание, чтобы увидеть попытки, вывод и код завершения.")),
        ),
        ("What happens after the canary?", "Что происходит после пробного запуска?"),
        (
            ("pass", ("All canary jobs succeed", "Пробный запуск успешен"),
             ("Isolate starts the next groups within the configured failure limits.", "Isolate запускает следующие группы с учётом заданных порогов ошибок.")),
            ("stop", ("A canary job fails", "Ошибка на пробном хосте"),
             ("The rollout stops. Inspect the failed host and its output.", "Следующая группа не запустится. Откройте задание проблемного хоста и проверьте вывод.")),
            ("wait", ("An outcome is unknown", "Результат неизвестен"),
             ("The rollout stops. Check the state of the host before any retry.", "Следующая группа не запустится. Проверьте состояние хоста перед повтором.")),
        ),
    ),
    "audit": Workflow(
        ("From an event to the evidence", "От события до деталей расследования"),
        (
            ("search", ("Find an event", "Найдите событие"),
             ("Filter the audit log by account, project, time or object ID.", "Отфильтруйте журнал аудита по учётной записи, проекту, времени или ID.")),
            ("file-clock", ("Open the investigation", "Откройте расследование"),
             ("Follow a linked object or enter the object type and ID.", "Перейдите по связанной записи или укажите тип объекта и ID.")),
            ("activity", ("Read the timeline", "Проверьте хронологию"),
             ("Match who acted, what was allowed and what happened next.", "Сопоставьте автора действия, решение о доступе и результат.")),
        ),
        ("Which record do you need?", "Какая запись нужна?"),
        (
            ("detail", ("An SSH session", "SSH-сессия"),
             ("Open the session details and replay the recording if it is available.", "Откройте карточку сессии и воспроизведите запись, если она доступна.")),
            ("detail", ("A job on a host", "Задание на хосте"),
             ("Open the job to inspect its status, attempts and captured output.", "Откройте задание и проверьте статус, попытки и сохранённый вывод.")),
        ),
    ),
    "deployment": Workflow(
        ("Updating a deployment", "Как обновить Isolate"),
        (
            ("file-text", ("Plan and stage", "Подготовьте релиз"),
             ("Review the target version and dependencies. Keep a verified backup.", "Сверьте версию и зависимости. Подготовьте проверенную резервную копию.")),
            ("check", ("Verify the candidate", "Проверьте новую версию"),
             ("Check the staged release and validate configuration as the runtime account.", "Проверьте подготовленный релиз и конфигурацию от служебной учётной записи.")),
            ("refresh-cw", ("Drain and activate", "Завершите сессии и переключите релиз"),
             ("Drain the old gateway first. After switching, check readiness, OIDC and a test connection.", "Переведите старый шлюз в режим завершения сессий. После переключения проверьте готовность, вход по OIDC и тестовое подключение.")),
        ),
        ("What did the checks reveal?", "Что показали проверки?"),
        (
            ("pass", ("Health and sign-in checks pass", "Готовность и вход подтверждены"),
             ("Verify that the authorized test connection and its recording work as configured.", "Проверьте разрешённое подключение и запись сессии, если она включена.")),
            ("wait", ("Release needs to be rolled back", "Нужно откатить релиз"),
             ("Roll back the application version and repeat the checks.", "Верните предыдущую версию приложения и повторите проверки.")),
            ("stop", ("State needs recovery", "Нужно восстановить данные"),
             ("Use the recovery procedure and a verified backup.", "Воспользуйтесь процедурой восстановления и проверенной резервной копией.")),
        ),
    ),
    "recovery": Workflow(
        ("From verified backup to recovery", "От резервной копии до восстановления"),
        (
            ("database", ("Verify the copy", "Проверьте копию"),
             ("Check the manifest and checksum. Identify any stores backed up separately.", "Проверьте манифест и контрольную сумму. Уточните, для каких хранилищ нужны отдельные копии.")),
            ("server", ("Restore in a test environment", "Отработайте восстановление на стенде"),
             ("Use a separate directory and store. Verify inventory, rules and file permissions.", "Возьмите отдельный каталог и хранилище. Сверьте инвентарь, правила доступа и права на файлы.")),
            ("shield-check", ("Verify access again", "Проверьте вход и доступ"),
             ("Test OIDC, the access decision and an authorized connection before using the backup in production.", "До восстановления рабочей среды проверьте вход по OIDC, решение о доступе и разрешённое подключение.")),
        ),
    ),
}


def _localized(value, locale):
    return value[locale == "ru"]


def _label(value, locale):
    return escape(_localized(value, locale))


def _url(locale, *, topic="", query=""):
    parameters = {"lang": locale}
    if topic:
        parameters["topic"] = topic
    if query:
        parameters["q"] = query
    return escape("/docs?" + urlencode(parameters), quote=True)


def _guide_link(guide, locale, *, active=False):
    current = ' aria-current="page"' if active else ""
    return '<a href="{}"{}>{}</a>'.format(_url(locale, topic=guide.key), current, _label(guide.title, locale))


def _card(guide, locale):
    return '<li><a class="docs-card" href="{}"><strong>{}</strong><span>{}</span></a></li>'.format(
        _url(locale, topic=guide.key), _label(guide.title, locale), _label(guide.summary, locale),
    )


def _search(query, locale):
    terms = re.findall(r"[\w-]+", query.casefold())
    if not terms:
        return []
    results = []
    for guide in GUIDES.values():
        title = _localized(guide.title, locale).casefold()
        summary = _localized(guide.summary, locale).casefold()
        details = " ".join(
            _localized(field, locale) for heading, entries in guide.sections
            for field in (heading, *(item for entry in entries for item in entry))
        ).casefold()
        evidence = " ".join((guide.key, title, summary, details))
        if all(term in evidence for term in terms):
            rank = sum(3 if term in title else 2 if term in summary else 1 for term in terms)
            results.append((rank, guide))
    return [guide for _, guide in sorted(results, key=lambda item: -item[0])]


def _navigation(locale, topic):
    label = _label(("Documentation sections", "Разделы документации"), locale)
    return '<nav class="docs-nav" aria-label="{}">{}</nav>'.format(label, "".join(
        '<section><h2>{}</h2><ul>{}</ul></section>'.format(_label(title, locale), "".join(
            "<li>{}</li>".format(_guide_link(guide, locale, active=guide.key == topic)) for guide in group
        )) for title, group in GUIDE_GROUPS
    ))


def _footer(locale, build):
    if not build:
        return ""
    items = (
        (("Version", "Версия"), build.get("version")),
        (("Revision", "Ревизия"), build.get("revision")),
        (("Built", "Собрано"), build.get("built_at")),
        (("Python", "Python"), build.get("python")),
        (("Schema", "Схема"), build.get("schema_version")),
        (("Uptime", "Время работы"), "{} s".format(build.get("uptime_seconds")) if build.get("uptime_seconds") is not None else None),
    )
    return '<footer class="docs-footer"><dl>{}</dl></footer>'.format("".join(
        "<div><dt>{}</dt><dd>{}</dd></div>".format(_label(item, locale), escape(str(value)))
        for item, value in items if value is not None
    ))


def _diagram(topic, locale):
    from isolate_ui_icons import icon

    workflow = WORKFLOWS.get(topic)
    if workflow is None:
        return ""
    steps = "".join(
        '<li><div class="docs-diagram-marker" aria-hidden="true">{}'
        '<span>{:02d}</span></div><strong>{}</strong><p>{}</p></li>'.format(
            icon(symbol), index, _label(title, locale), _label(detail, locale),
        ) for index, (symbol, title, detail) in enumerate(workflow.steps, start=1)
    )
    branches = ""
    if workflow.outcomes:
        symbols = {"pass": "circle-check", "wait": "circle-pause", "stop": "shield-alert", "detail": "file-text"}
        outcomes = "".join(
            '<li data-branch="{}"><strong>{}<span>{}</span></strong><p>{}</p></li>'.format(
                kind, icon(symbols[kind]), _label(title, locale), _label(detail, locale),
            ) for kind, title, detail in workflow.outcomes
        )
        branches = (
            '<div class="docs-diagram-decision"><h3 id="workflow-decision">{}</h3></div>'
            '<ul class="docs-diagram-branches" role="list" aria-labelledby="workflow-decision">{}</ul>'
        ).format(_label(workflow.decision, locale), outcomes)
    return (
        '<figure class="docs-diagram" data-workflow="{}" aria-labelledby="workflow-title">'
        '<figcaption class="docs-diagram-caption"><h2 id="workflow-title">{}</h2></figcaption>'
        '<div class="docs-diagram-body"><ol class="docs-diagram-steps" role="list">{}</ol>{}</div></figure>'
    ).format(topic, _label(workflow.title, locale), steps, branches)


def _guide(guide, locale):
    diagram = _diagram(guide.key, locale)
    sections = "".join(
        '<section id="section-{}"><h2>{}</h2><dl class="docs-terms">{}</dl></section>'.format(
            index, _label(title, locale), "".join(
                '<div><dt>{}</dt><dd>{}</dd></div>'.format(_label(term, locale), _label(description, locale))
                for term, description in entries
            ),
        ) for index, (title, entries) in enumerate(guide.sections, start=1)
    )
    outline = ""
    if len(guide.sections) > 1:
        outline = '<nav class="docs-outline" aria-label="{}">{}</nav>'.format(
            _label(("On this page", "На этой странице"), locale), "".join(
                '<a href="#section-{}">{}</a>'.format(index, _label(title, locale))
                for index, (title, _) in enumerate(guide.sections, start=1)
            ),
        )
    example = '<pre><code>{}</code></pre>'.format(escape(guide.example)) if guide.example else ""
    actions = ""
    if guide.links:
        actions = '<div class="docs-actions">{}</div>'.format("".join(
            '<a href="{}">{}</a>'.format(escape(href, quote=True), _label(title, locale))
            for href, title in guide.links
        ))
    related = ""
    if guide.related:
        related = '<section class="docs-related"><h2>{}</h2><ul class="docs-cards">{}</ul></section>'.format(
            _label(("Related guides", "Связанные разделы"), locale),
            "".join(_card(GUIDES[key], locale) for key in guide.related),
        )
    return ('<article><h1>{}</h1><p class="docs-lead">{}</p>{}{}{}{}{}</article>{}').format(
        _label(guide.title, locale), _label(guide.summary, locale), outline, diagram, sections, example, actions, related,
    )


def _home(locale):
    from isolate_ui_icons import icon

    title = _label(("Isolate Documentation", "Документация Isolate"), locale)
    lead = _label((
        "Find a resource, request access, investigate a session or operate your deployment.",
        "Как подключаться к ресурсам, управлять доступом и обслуживать бастион.",
    ), locale)
    cards = "".join(_card(GUIDES[key], locale) for key in ("resources", "access-requests", "troubleshooting"))
    groups = "".join(
        '<section><h2>{}</h2><ul class="docs-index-list">{}</ul></section>'.format(
            _label(title, locale), "".join("<li>{}</li>".format(_guide_link(guide, locale)) for guide in guides),
        ) for title, guides in GUIDE_GROUPS
    )
    return ('<div class="docs-intro">{}<h1>{}</h1><p class="docs-lead">{}</p></div>'
            '<ul class="docs-cards docs-featured">{}</ul><div class="docs-index">{}</div>').format(
        icon("book-open"), title, lead, cards, groups,
    )


def render_docs(locale, topic="", query="", *, build=None):
    """Render the isolated docs shell, or return None for an unknown article."""
    from isolate_ui_icons import icon

    locale = "ru" if locale == "ru" else "en"
    query = query.strip()[:120]
    guide = GUIDES.get(topic)
    if topic and guide is None:
        return None

    if query:
        title = ("Search documentation", "Поиск по документации")
        results = _search(query, locale)
        content = '<h1>{}</h1><p class="docs-lead">{}</p>'.format(_label(title, locale), escape(query))
        if results:
            content += '<ul class="docs-cards">{}</ul>'.format("".join(_card(result, locale) for result in results))
        else:
            content += '<p class="docs-empty">{}</p>'.format(_label((
                "No guides matched. Try a feature name, such as terminal or access.",
                "Подходящих статей нет. Попробуйте название функции, например «терминал» или «доступ».",
            ), locale))
    elif guide:
        title = guide.title
        content = _guide(guide, locale)
    else:
        title = ("Isolate Documentation", "Документация Isolate")
        content = _home(locale)

    home = _label(("Documentation", "Документация"), locale)
    back = _label(("Back to Isolate", "Вернуться в Isolate"), locale)
    search = _label(("Search guides", "Поиск по руководствам"), locale)
    browse = _label(("Browse topics", "Разделы справки"), locale)
    theme = _label(("Color theme", "Цветовая тема"), locale)
    lang = _label(("Language", "Язык"), locale)
    skip = _label(("Skip to content", "Перейти к содержимому"), locale)
    languages = "".join('<a href="{}" lang="{}" hreflang="{}"{}>{}</a>'.format(
        _url(language, topic=topic, query=query), language, language,
        ' aria-current="page"' if language == locale else "", language.upper(),
    ) for language in ("en", "ru"))
    themes = "".join('<option value="{}"{}>{}</option>'.format(
        value, " selected" if value == "system" else "", _label(label, locale),
    ) for value, label in (("light", ("Light", "Светлая")), ("dark", ("Dark", "Тёмная")),
                           ("system", ("System", "Как в системе"))))
    navigation = _navigation(locale, topic)
    return f'''<!doctype html>
<html lang="{locale}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_label(title, locale)}</title>
  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
  <script src="/static/precision-theme.js"></script>
  <link rel="stylesheet" href="/static/isolate-docs.css">
</head>
<body>
  <a class="docs-skip" href="#docs-main">{skip}</a>
  <header class="docs-header">
    <a class="docs-brand" href="{_url(locale)}">{icon("shield-check")}<span>Isolate <small>{home}</small></span></a>
    <form role="search" class="docs-search" method="get" action="/docs">
      <input type="hidden" name="lang" value="{locale}">
      <label class="docs-hidden" for="docs-search">{search}</label>
      {icon("search")}<input id="docs-search" name="q" type="search" value="{escape(query, quote=True)}" placeholder="{search}" maxlength="120">
      <button type="submit">{_label(("Search", "Найти"), locale)}</button>
    </form>
    <div class="docs-controls">
      <nav class="locale-switch" aria-label="{lang}">{languages}</nav>
      <label class="docs-hidden" for="docs-theme">{theme}</label>
      <select id="docs-theme" data-theme-select>{themes}</select>
      <a class="docs-back" href="/">{back}</a>
    </div>
  </header>
  <div class="docs-layout">
    <aside class="docs-sidebar">{navigation}</aside>
    <details class="docs-mobile-nav"><summary>{browse}</summary>{navigation}</details>
    <main class="docs-main" id="docs-main" tabindex="-1">{content}{_footer(locale, build)}</main>
  </div>
</body>
</html>'''
