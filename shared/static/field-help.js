/* Keep form descriptions associated with their controls and reveal them on demand. */
(function () {
  'use strict';
  const describedControls = 'input[aria-describedby], select[aria-describedby], textarea[aria-describedby]';
  const enhanced = new WeakSet();
  const russian = document.documentElement.lang === 'ru';
  let active = null;
  let pinned = false;
  let dismissTimer;

  function close() {
    clearTimeout(dismissTimer);
    if (!active) return;
    active.button.setAttribute('aria-expanded', 'false');
    active.button.removeAttribute('aria-controls');
    active.popup.hidden = true;
    active.popup.remove();
    active = null;
    pinned = false;
  }

  function position() {
    if (!active) return;
    const {button, popup} = active;
    const anchor = button.getBoundingClientRect();
    if (!anchor.width || anchor.bottom < 0 || anchor.top > window.innerHeight) {
      close();
      return;
    }
    const width = popup.offsetWidth;
    const height = popup.offsetHeight;
    const nearDialog = button.closest('dialog');
    const alignEnd = nearDialog || anchor.left + width + 8 > window.innerWidth;
    const left = alignEnd ? anchor.right - width : anchor.left;
    const above = (nearDialog || anchor.bottom + height + 6 > window.innerHeight) && anchor.top > height + 14;
    popup.style.left = `${Math.max(8, Math.min(left, window.innerWidth - width - 8))}px`;
    const top = above ? anchor.top - height - 6 : anchor.bottom + 6;
    popup.style.top = `${Math.max(8, Math.min(top, window.innerHeight - height - 8))}px`;
  }

  function open(item, keep = false) {
    clearTimeout(dismissTimer);
    if (active !== item) close();
    active = item;
    pinned = pinned || keep;
    if (!item.popup.isConnected) (item.button.closest('dialog') || document.body).append(item.popup);
    item.popup.hidden = false;
    item.button.setAttribute('aria-expanded', 'true');
    item.button.setAttribute('aria-controls', item.popup.id);
    position();
  }

  function scheduleClose(item) {
    clearTimeout(dismissTimer);
    dismissTimer = setTimeout(() => {
      if (active === item && !pinned && document.activeElement !== item.button) close();
    }, 150);
  }

  function enhance(control) {
    if (enhanced.has(control) || control.type === 'hidden') return;
    const ids = control.getAttribute('aria-describedby').trim().split(/\s+/);
    const hints = ids.map(id => document.getElementById(id)).filter(element =>
      element && element.matches('.field-hint, .workflow-field-hint') && element.textContent.trim());
    if (!hints.length) return;
    enhanced.add(control);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'field-help-trigger';
    button.setAttribute('aria-label', russian ? 'Подсказка к полю' : 'Field help');
    button.setAttribute('aria-describedby', hints.map(hint => hint.id).join(' '));
    button.setAttribute('aria-expanded', 'false');
    const icon = document.createElement('span');
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '?';
    button.append(icon);

    const popup = document.createElement('div');
    popup.className = 'field-help-popup';
    popup.id = `field-help-${hints[0].id}`;
    popup.setAttribute('aria-hidden', 'true');
    popup.hidden = true;
    popup.textContent = hints.map(hint => hint.textContent.trim()).join(' ');

    const label = control.labels && control.labels[0];
    const wrappingLabel = label?.contains(control);
    const adminField = wrappingLabel && label.parentElement.matches('.admin-fields, .admin-toolbar');
    // An interactive button inside a label would interfere with its control.
    if (adminField || (wrappingLabel && label.matches('.content > form:not(.inline) > label, .content > form:not(.inline) > p > label'))) {
      const field = document.createElement('span');
      field.className = adminField ? 'field-help-admin-slot' : 'field-help-slot';
      label.before(field);
      field.append(label, button);
    } else if (!wrappingLabel && control.matches('input:not([type="checkbox"], [type="radio"]), select, textarea')) {
      const field = document.createElement('span');
      field.className = 'field-help-input';
      control.before(field);
      field.append(control, button);
    } else {
      (wrappingLabel ? label : control).after(button);
    }
    for (const hint of hints) hint.classList.add('field-help-description');

    const item = {button, popup};
    button.addEventListener('focus', () => open(item));
    button.addEventListener('blur', () => { if (active === item && !pinned) close(); });
    button.addEventListener('pointerenter', event => { if (event.pointerType !== 'touch') open(item); });
    button.addEventListener('pointerleave', () => scheduleClose(item));
    button.addEventListener('click', () => { if (active === item && pinned) close(); else open(item, true); });
    popup.addEventListener('pointerenter', () => clearTimeout(dismissTimer));
    popup.addEventListener('pointerleave', () => scheduleClose(item));
    const dialog = control.closest('dialog');
    if (dialog) dialog.addEventListener('close', () => { if (active === item) close(); });
  }

  document.querySelectorAll(describedControls).forEach(enhance);
  document.addEventListener('isolate:fields-added', event => {
    event.target.querySelectorAll(describedControls).forEach(enhance);
  });

  document.addEventListener('pointerdown', event => {
    if (active && !active.button.contains(event.target) && !active.popup.contains(event.target)) close();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && active) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }, true);
  window.addEventListener('resize', position);
  document.addEventListener('scroll', position, true);
})();
