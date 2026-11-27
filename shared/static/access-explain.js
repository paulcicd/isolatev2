/* Lazy, text-only access diagnostics. A snapshot never replaces authorization. */
(() => {
  if (window.isolateAccessExplanationInstalled) return;
  window.isolateAccessExplanationInstalled = true;
  document.addEventListener('toggle', async event => {
    const panel = event.target;
    if (!(panel instanceof HTMLDetailsElement) || !panel.matches('[data-access-explanation]') || !panel.open || panel.dataset.loading === 'true') return;
    const target = panel.querySelector('[data-explanation-result]');
    if (!target) return;
    const russian = panel.dataset.language === 'ru';
    const labels = {
      "A separate approval is required for each new session.": "Каждое новое подключение нужно согласовать отдельно.",
      "Access for this identity has been ended by a lifecycle decision.": "Доступ для этой учётной записи отозван.",
      "Access is available.": "Доступ разрешён.",
      "Access is rechecked when an operation starts and while it runs. This explanation does not grant access.": "При запуске операции и во время её выполнения Isolate проверяет доступ заново.",
      "Connect": "Подключиться",
      "Contact an administrator": "Обратиться к администратору",
      "Contact the resource owner": "Обратиться к владельцу ресурса",
      "Current access lifecycle evidence could not be verified.": "Не удалось проверить, действуют ли ограничения доступа.",
      "Current identity and route preflight passed.": "Учётная запись и настройки подключения прошли предварительную проверку.",
      "Current identity, lifecycle or route requirements prevent access. Ask an administrator to review the resource.": "Проверка учётной записи, ограничений доступа или подключения завершилась ошибкой. Попросите администратора проверить настройки ресурса.",
      "Fresh authentication at the required assurance level is needed.": "Войдите ещё раз и пройдите дополнительную проверку при входе.",
      "Fresh authentication is required.": "Войдите в Isolate ещё раз.",
      "Group/role rows model policy principals, not a complete list of people. Combined memberships and current IdP membership must be reviewed separately.": "Прогноз показывает права по отдельным группам и ролям. Проверьте в IdP состав групп и сочетание прав у конкретных пользователей.",
      "Identity assurance configuration needs administrator attention.": "Попросите администратора проверить требования к повторной аутентификации.",
      "New connections are administratively disabled.": "Новые подключения отключены администратором.",
      "New connections are enabled.": "Новые подключения разрешены.",
      "No access lifecycle restriction blocks this identity for the resource project.": "Для этой учётной записи доступ к проекту не отозван.",
      "No active assignment matches this resource.": "Действующие правила не дают вашей учётной записи доступ к этому ресурсу.",
      "No separate session approval is required.": "Подключение можно начать без отдельного согласования.",
      "Policy permits this action; operation-specific submission and channel checks still apply.": "Правило разрешает действие. При запуске Isolate ещё проверит параметры операции и соединения.",
      "Request access": "Запросить доступ",
      "Request session": "Запросить согласование подключения",
      "The Kubernetes operation is enabled.": "Ресурс поддерживает эту операцию Kubernetes.",
      "The SSH target port is not permitted.": "Подключение к этому порту SSH запрещено.",
      "The SSH target port is permitted.": "Подключение к этому порту SSH разрешено.",
      "The connection services are enabled.": "На бастионе включены службы, необходимые для подключения.",
      "The connection services are not enabled.": "На бастионе отключены службы, необходимые для подключения.",
      "The current authentication meets the configured assurance requirement.": "Вы вошли с требуемым способом аутентификации.",
      "The principal type permits this action.": "Действие разрешено для этого типа учётной записи.",
      "The resource is in maintenance.": "Ресурс на техническом обслуживании.",
      "The resource is not blocked by maintenance.": "Ресурс доступен для новых подключений.",
      "The resource protocol configuration needs administrator attention.": "Попросите администратора проверить настройки протокола для этого ресурса.",
      "The resource protocol has a valid inventory-bound configuration.": "Протокол настроен для этого ресурса в каталоге.",
      "The selected active rule is checked first. Actions from other rules are not combined.": "Isolate проверяет действие по одному выбранному правилу доступа.",
      "The selected active rule permits this action.": "Выбранное правило разрешает это действие.",
      "The selected policy does not resolve a remote account.": "Для подключения по этому правилу не задана учётная запись на ресурсе.",
      "The selected rule does not allow the requested action.": "Это действие запрещено выбранным правилом.",
      "This Kubernetes operation is not enabled for the resource.": "Эта операция Kubernetes отключена в настройках ресурса.",
      "This SSH channel is enabled.": "Канал SSH разрешён в настройках ресурса.",
      "This channel requires an enabled compatible SSH profile.": "Включите в настройках ресурса профиль SSH, который разрешает этот канал.",
      "This workload identity is not enabled for the requested action.": "Действие запрещено для этой сервисной учётной записи.",
      "Verify identity": "Войти повторно",
      "View resource": "Открыть ресурс",
      "passed": "Пройдено",
      "failed": "Не пройдено",
      "required": "Требуется"
    };
    const label = value => russian && Object.hasOwn(labels, value) ? labels[value] : value;
    const endpoint = panel.dataset.accessExplanation;
    if (!endpoint || !endpoint.startsWith('/api/v1/access/explain/')) return;
    panel.dataset.loading = 'true';
    target.textContent = russian ? 'Проверка доступа…' : 'Checking current access…';
    try {
      const response = await fetch(endpoint, {credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'}});
      if (!response.ok) throw new Error('explanation unavailable');
      const value = await response.json();
      target.replaceChildren();
      const summary = document.createElement('p'); summary.textContent = label(value.summary); target.append(summary);
      const selected = value.policy && value.policy.selected_grant;
      if (selected) {
        const rule = document.createElement('p');
        rule.textContent = (russian ? 'Правило: ' : 'Selected rule: ') + (selected.id || (russian ? 'из политики доступа' : 'policy'));
        target.append(rule);
      }
      const list = document.createElement('ul');
      for (const check of value.checks || []) {
        const item = document.createElement('li'); item.textContent = label(check.status) + ': ' + label(check.message); list.append(item);
      }
      target.append(list);
      const precedence = document.createElement('p'); precedence.textContent = label(value.policy.precedence_note); target.append(precedence);
      if (value.next_action && typeof value.next_action.url === 'string' && value.next_action.url.startsWith('/') && !value.next_action.url.startsWith('//')) {
        const link = document.createElement('a'); link.href = value.next_action.url; link.textContent = label(value.next_action.label); target.append(link);
      }
      const notice = document.createElement('p'); notice.textContent = label(value.notice); target.append(notice);
    } catch (_) {
      target.textContent = russian ? 'Не удалось проверить доступ. Войдите в Isolate снова. Если это не поможет, обратитесь к администратору.' : 'Explanation unavailable. Sign in again or ask an administrator.';
    } finally { panel.dataset.loading = 'false'; }
  }, true);
})();
