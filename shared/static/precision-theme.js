/* Resolve the saved preference before paint; storage may be disabled by policy. */
(function () {
  'use strict';
  var root = document.documentElement;
  var media = window.matchMedia('(prefers-color-scheme: dark)');
  function valid(value) { return ['light', 'dark', 'system'].indexOf(value) !== -1; }
  function read() {
    try { var value = localStorage.getItem('isolate-theme'); return valid(value) ? value : 'system'; }
    catch (_) { return 'system'; }
  }
  function apply(value) {
    root.dataset.themePreference = value;
    root.dataset.theme = value === 'system' ? (media.matches ? 'dark' : 'light') : value;
    document.querySelectorAll('[data-theme-select]').forEach(function (select) { select.value = value; });
    document.querySelectorAll('[data-theme-choice]').forEach(function (button) {
      var selected = button.dataset.themeChoice === value;
      button.setAttribute('aria-pressed', String(selected));
      if (selected) {
        var label = button.closest('details')?.querySelector('[data-theme-label]');
        if (label) label.textContent = button.querySelector('[data-theme-name]').textContent;
      }
    });
  }
  function choose(value) {
    if (!valid(value)) return;
    try { localStorage.setItem('isolate-theme', value); } catch (_) {}
    apply(value);
  }
  apply(read());
  document.addEventListener('DOMContentLoaded', function () {
    apply(root.dataset.themePreference);
    document.querySelectorAll('[data-theme-select]').forEach(function (select) {
      select.addEventListener('change', function () { choose(select.value); });
    });
    document.querySelectorAll('[data-theme-choice]').forEach(function (button) {
      button.addEventListener('click', function () {
        choose(button.dataset.themeChoice);
        var popup = button.closest('details');
        if (popup) {
          popup.open = false;
          popup.querySelector('summary').focus();
        }
      });
    });
  });
  function systemChanged() { if (root.dataset.themePreference === 'system') apply('system'); }
  if (media.addEventListener) media.addEventListener('change', systemChanged);
  else if (media.addListener) media.addListener(systemChanged);
  window.addEventListener('storage', function (event) {
    if (event.key === 'isolate-theme' || event.key === null) apply(read());
  });
})();
