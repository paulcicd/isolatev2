(() => {
  'use strict';
  const selectors = ['project', 'project_set', 'project_glob'];
  const fieldNames = ['id', 'scope_type', 'scope_value', 'host', 'remote_user', 'sudo_mode', 'allowed_actions'];
  let ruleSequence = 0;
  for (const form of document.querySelectorAll('[data-package-form]')) {
    const raw = form.querySelector('[name="access_json"]');
    const jsonField = raw.closest('label');
    const builder = form.querySelector('[data-package-builder]');
    const controls = form.querySelector('[data-package-builder-controls]');
    const template = form.querySelector('[data-package-rule-template]');
    builder.append(controls.content.cloneNode(true));
    const add = builder.querySelector('[data-package-add]');
    const toggle = builder.querySelector('[data-package-toggle]');
    const list = builder.querySelector('[data-package-rule-list]');
    let visual = false;

    function fields(row) {
      return Object.fromEntries(fieldNames.map(name => [name, row.querySelector('[data-package-field="' + name + '"]')]));
    }

    function appendRule(rule = {}) {
      const row = template.content.firstElementChild.cloneNode(true);
      const sequence = ++ruleSequence;
      const hintIds = new Map();
      for (const hint of row.querySelectorAll('.field-hint[id], .workflow-field-hint[id]')) {
        const id = hint.id + '-rule-' + sequence;
        hintIds.set(hint.id, id);
        hint.id = id;
      }
      for (const input of row.querySelectorAll('[name]')) {
        input.dataset.packageField = input.name;
        input.removeAttribute('name');
        const describedBy = input.getAttribute('aria-describedby');
        if (describedBy) {
          input.setAttribute('aria-describedby', describedBy.split(/\s+/).map(id => hintIds.get(id) || id).join(' '));
        }
      }
      const controls = fields(row);
      const selector = selectors.find(key => rule[key]) || 'project';
      controls.id.value = rule.id || '';
      controls.scope_type.value = selector;
      controls.scope_value.value = rule[selector] || '';
      controls.host.value = rule.host || '';
      controls.remote_user.value = rule.remote_user || '';
      controls.sudo_mode.value = rule.sudo_mode || 'none';
      controls.allowed_actions.value = (rule.allowed_actions || ['ssh']).join(', ');
      row.querySelector('[data-package-remove]').addEventListener('click', () => {
        row.remove();
        add.focus();
      });
      list.append(row);
      row.dispatchEvent(new CustomEvent('isolate:fields-added', { bubbles: true }));
      return controls.scope_value;
    }

    function encodedRules() {
      return Array.from(list.children, row => {
        const controls = fields(row);
        const rule = {
          [controls.scope_type.value]: controls.scope_value.value.trim(),
          remote_user: controls.remote_user.value.trim(),
          sudo_mode: controls.sudo_mode.value,
          allowed_actions: controls.allowed_actions.value.split(',').map(action => action.trim()).filter(Boolean),
        };
        if (controls.id.value.trim()) rule.id = controls.id.value.trim();
        if (controls.host.value.trim()) rule.host = controls.host.value.trim();
        return rule;
      });
    }

    function chooseMode(next) {
      if (next) {
        let rules;
        try {
          rules = JSON.parse(raw.value);
          if (!Array.isArray(rules) || rules.some(rule => !rule || typeof rule !== 'object' || Array.isArray(rule) || (
            rule.allowed_actions && !Array.isArray(rule.allowed_actions)
          ) || (rule.sudo_mode && !['none', 'sudo-i'].includes(rule.sudo_mode)) ||
            selectors.filter(key => rule[key]).length !== 1)) return false;
        } catch {
          return false;
        }
        list.replaceChildren();
        for (const rule of rules) appendRule(rule);
        if (!rules.length) appendRule();
      } else if (visual) {
        raw.value = JSON.stringify(encodedRules(), null, 2);
      }
      visual = next;
      jsonField.hidden = visual;
      raw.required = !visual;
      add.hidden = !visual;
      list.hidden = !visual;
      for (const input of list.querySelectorAll('input, select')) input.disabled = !visual;
      toggle.textContent = visual ? form.dataset.jsonLabel : form.dataset.visualLabel;
      return true;
    }

    add.addEventListener('click', () => appendRule().focus());
    toggle.addEventListener('click', () => {
      if (chooseMode(!visual)) {
        if (visual) list.querySelector('input').focus();
        else raw.focus();
      } else raw.focus();
    });
    form.addEventListener('submit', () => {
      if (visual) raw.value = JSON.stringify(encodedRules(), null, 2);
    });
    builder.hidden = false;
    if (!chooseMode(true)) chooseMode(false);
  }
})();
