/* Refresh only the authorized overview projection; keep dialogs and focus stable. */
(() => {
  'use strict';
  const root = document.querySelector('.enterprise-overview');
  if (!root) return;
  const status = root.querySelector('.overview-refresh-status');
  const button = root.querySelector('[data-overview-refresh]');
  const dialog = root.querySelector('#overview-terminate-dialog');
  let pending = false;
  let timer;

  function replaceSnapshot(region, children) {
    const oldStream = region.querySelector('.overview-audit-stream');
    const previousScroll = oldStream?.scrollTop || 0;
    let firstVisible;
    let offset;
    if (previousScroll > 0) {
      const top = oldStream.getBoundingClientRect().top + oldStream.clientTop;
      firstVisible = Array.from(oldStream.querySelectorAll('[data-audit-event]')).find(row =>
        row.dataset.auditEvent && row.getBoundingClientRect().bottom > top);
      if (firstVisible) offset = firstVisible.getBoundingClientRect().top - top;
    }

    region.replaceChildren(...children);
    if (previousScroll <= 0) return;
    const stream = region.querySelector('.overview-audit-stream');
    if (!stream) return;
    const restoredRow = firstVisible && Array.from(stream.querySelectorAll('[data-audit-event]')).find(row =>
      row.dataset.auditEvent === firstVisible.dataset.auditEvent);
    // Prefer the same event and offset when newer or expired rows move the list.
    stream.scrollTop = restoredRow
      ? restoredRow.getBoundingClientRect().top - stream.getBoundingClientRect().top - stream.clientTop - offset
      : previousScroll;
  }

  async function refresh() {
    if (pending || document.hidden || dialog.open) return;
    pending = true;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(root.dataset.overviewUrl, {
        credentials: 'same-origin', headers: {Accept: 'text/html'}, redirect: 'error',
        signal: AbortSignal.timeout(8000),
      });
      if (!response.ok || !response.headers.get('Content-Type')?.includes('text/html')) throw new Error('Overview unavailable');
      const fragment = await response.text();
      const region = root.querySelector('#overview-live-region');
      if (!region.contains(document.activeElement) && !dialog.open) {
        const parsed = new DOMParser().parseFromString(fragment, 'text/html');
        if (parsed.querySelector('script')) throw new Error('Unexpected overview response');
        replaceSnapshot(region, parsed.body.childNodes);
      }
      status.textContent = '';
    } catch (_) {
      status.textContent = root.dataset.overviewError;
    } finally {
      pending = false;
      button.disabled = false;
      button.removeAttribute('aria-busy');
    }
  }

  root.addEventListener('click', event => {
    const terminate = event.target.closest('[data-overview-terminate]');
    if (terminate) {
      const form = dialog.querySelector('form');
      form.action = '/sessions/' + encodeURIComponent(terminate.dataset.overviewTerminate) + '/terminate';
      dialog.querySelector('[name="reason"]').value = '';
      dialog.showModal();
    }
    if (event.target.closest('[data-overview-dialog-close]')) dialog.close();
    if (event.target.closest('[data-overview-refresh]')) refresh();
  });
  timer = window.setInterval(refresh, 12000);
  window.addEventListener('pagehide', () => window.clearInterval(timer), {once: true});
})();
