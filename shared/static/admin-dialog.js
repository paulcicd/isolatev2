(() => {
  if (typeof HTMLDialogElement === 'undefined' || !HTMLDialogElement.prototype.showModal) return;

  const links = new Map(Array.from(document.querySelectorAll('[data-open-dialog]'),
    link => [link.dataset.openDialog, link]));
  const closeLabel = document.documentElement.lang === 'ru' ? 'Закрыть' : 'Close';

  document.querySelectorAll('details[data-admin-dialog]').forEach((disclosure, index) => {
    const page = disclosure.closest('.admin-page');
    const summary = disclosure.querySelector(':scope > summary');
    const initiallyOpen = disclosure.open;
    const link = links.get(disclosure.id);
    const trigger = link || document.createElement('button');
    if (!link) {
      trigger.type = 'button';
      trigger.className = summary.className || 'admin-button';
      trigger.append(...summary.childNodes);
    }

    const dialog = document.createElement('dialog');
    dialog.className = 'admin-dialog';
    dialog.id = disclosure.id || `admin-dialog-${index}`;
    if (disclosure.dataset.dialogSize) dialog.dataset.dialogSize = disclosure.dataset.dialogSize;
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-controls', dialog.id);

    const heading = document.createElement('header');
    heading.className = 'admin-dialog-heading';
    const title = document.createElement('h2');
    title.id = `${dialog.id}-title`;
    title.textContent = disclosure.dataset.title || trigger.textContent.trim();
    dialog.setAttribute('aria-labelledby', title.id);
    const close = document.createElement('button');
    close.className = 'admin-button';
    close.type = 'button';
    close.setAttribute('aria-label', page.dataset.closeLabel || closeLabel);
    close.textContent = '×';
    close.addEventListener('click', () => dialog.close());

    const body = document.createElement('div');
    body.className = 'admin-dialog-body';
    body.append(...Array.from(disclosure.children).slice(1));
    heading.append(title, close);
    dialog.append(heading, body);
    if (link) disclosure.remove();
    else disclosure.replaceWith(trigger);
    page.append(dialog);

    trigger.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      dialog.showModal();
    });
    dialog.addEventListener('close', () => trigger.focus({ preventScroll: true }));

    if (initiallyOpen) {
      const notice = page.closest('.content')?.querySelector(':scope > .notice.error');
      if (notice) {
        notice.setAttribute('role', 'alert');
        body.prepend(notice);
      }
      dialog.showModal();
    }
  });
})();
