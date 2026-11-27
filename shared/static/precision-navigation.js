(() => {
  'use strict';

  const sidebar = document.getElementById('sidebar-navigation');
  const rail = sidebar?.querySelector('.nav-rail');
  const navigation = sidebar?.querySelector('.primary-nav');
  const search = document.getElementById('navigation-search');
  const noResults = sidebar?.querySelector('[data-nav-no-results]');
  const flyout = document.querySelector('.nav-flyout');
  if (!rail || !navigation || !flyout) return;

  const flyoutTitle = flyout.querySelector('.nav-flyout-title');
  const flyoutLinks = flyout.querySelector('.nav-flyout-links');
  const groups = new Map();
  navigation.querySelectorAll('[data-nav-group]').forEach(section => {
    groups.set(section.dataset.navGroup, {
      section,
      title: section.querySelector('.nav-label').textContent.trim(),
      links: Array.from(section.querySelectorAll('.nav-link')),
    });
  });
  rail.querySelectorAll('[data-nav-trigger]').forEach(trigger => {
    const group = groups.get(trigger.dataset.navTrigger);
    if (group) group.trigger = trigger;
  });
  if (!groups.size) return;

  const storageKey = 'isolate.sidebar.navigation';
  const path = window.location.pathname;
  let saved;
  try {
    saved = JSON.parse(sessionStorage.getItem(storageKey));
  } catch {
    // A blocked storage API or invalid saved state should leave the menu usable.
  }
  const activeGroup = navigation.querySelector('.nav-link[aria-current="page"]')
    ?.closest('[data-nav-group]')?.dataset.navGroup;
  const savedGroup = groups.has(saved?.group) ? saved.group : null;
  let selected = (saved?.path === path && savedGroup) || activeGroup || savedGroup || groups.keys().next().value;
  const offsets = new Map();
  for (const id of groups.keys()) {
    const offset = saved?.offsets?.[id];
    if (Number.isFinite(offset) && offset > 0) offsets.set(id, offset);
  }
  let filtering = false;

  function rememberScroll() {
    if (!filtering && navigation.scrollHeight > navigation.clientHeight) {
      offsets.set(selected, navigation.scrollTop);
    }
  }

  function save() {
    rememberScroll();
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({ path, group: selected, offsets: Object.fromEntries(offsets) }));
    } catch {
      // Session storage is optional.
    }
  }

  function render() {
    const query = search?.value.trim().toLocaleLowerCase() || '';
    filtering = Boolean(query);
    let matched = false;
    groups.forEach(({ section, title, links, trigger }, id) => {
      const titleMatches = title.toLocaleLowerCase().includes(query);
      links.forEach(link => {
        link.hidden = filtering && !titleMatches && !link.textContent.toLocaleLowerCase().includes(query);
      });
      section.hidden = filtering ? links.every(link => link.hidden) : id !== selected;
      matched ||= !section.hidden;
      trigger?.setAttribute('aria-pressed', String(id === selected));
    });
    if (noResults) noResults.hidden = matched || !filtering;
    navigation.scrollTop = filtering ? 0 : offsets.get(selected) || 0;
  }

  let previewTrigger = null;
  let openTimer;
  let closeTimer;
  const hover = window.matchMedia('(any-hover: hover)');

  function closeFlyout(returnFocus = false) {
    clearTimeout(openTimer);
    clearTimeout(closeTimer);
    if (!previewTrigger) return;
    const trigger = previewTrigger;
    previewTrigger = null;
    delete trigger.dataset.preview;
    flyout.hidden = true;
    flyoutLinks.replaceChildren();
    if (returnFocus) trigger.focus({ preventScroll: true });
  }

  function positionFlyout() {
    if (!previewTrigger) return;
    const anchor = previewTrigger.getBoundingClientRect();
    const railBounds = rail.getBoundingClientRect();
    const width = document.documentElement.clientWidth;
    const height = window.innerHeight;
    const gap = 8;
    if (anchor.right <= 0 || anchor.left >= width || anchor.bottom <= Math.max(0, railBounds.top) ||
        anchor.top >= Math.min(height, railBounds.bottom)) {
      closeFlyout(flyout.contains(document.activeElement));
      return;
    }
    const right = anchor.right + gap;
    const left = anchor.left - flyout.offsetWidth - gap;
    const preferredLeft = right + flyout.offsetWidth + gap <= width || left < gap ? right : left;
    flyout.style.left = `${Math.max(gap, Math.min(preferredLeft, width - flyout.offsetWidth - gap))}px`;
    flyout.style.top = `${Math.max(gap, Math.min(anchor.top, height - flyout.offsetHeight - gap))}px`;
  }

  function showFlyout(trigger, focusLink = false) {
    closeFlyout();
    const id = trigger.dataset.navTrigger;
    const group = groups.get(id);
    if (!group?.links.length) return;
    previewTrigger = trigger;
    trigger.dataset.preview = 'true';
    flyout.dataset.navGroup = id;
    flyoutTitle.textContent = group.title;
    flyoutLinks.replaceChildren(...group.links.map(link => {
      const copy = link.cloneNode(true);
      copy.hidden = false;
      return copy;
    }));
    flyout.hidden = false;
    flyout.scrollTop = 0;
    positionFlyout();
    if (focusLink && previewTrigger) flyoutLinks.firstElementChild.focus({ preventScroll: true });
  }

  function scheduleClose() {
    clearTimeout(openTimer);
    clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
      if (!flyout.contains(document.activeElement)) closeFlyout();
    }, 180);
  }

  groups.forEach(({ trigger, links }, id) => {
    if (!trigger) return;
    trigger.addEventListener('click', event => {
      closeFlyout();
      rememberScroll();
      selected = id;
      if (search) search.value = '';
      render();
      save();
      if (event.detail === 0) links[0]?.focus();
    });
    trigger.addEventListener('pointerenter', event => {
      if (event.pointerType === 'touch' || !hover.matches || flyout.contains(document.activeElement)) return;
      clearTimeout(openTimer);
      clearTimeout(closeTimer);
      if (previewTrigger !== trigger) openTimer = setTimeout(() => showFlyout(trigger), 115);
    });
    trigger.addEventListener('pointerleave', event => {
      if (event.pointerType !== 'touch' && !flyout.contains(event.relatedTarget)) scheduleClose();
    });
    trigger.addEventListener('keydown', event => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
        event.preventDefault();
        showFlyout(trigger, true);
      }
    });
  });

  flyout.addEventListener('pointerenter', () => clearTimeout(closeTimer));
  flyout.addEventListener('pointerleave', event => {
    if (!previewTrigger?.contains(event.relatedTarget)) scheduleClose();
  });
  document.addEventListener('pointerdown', event => {
    if (!flyout.contains(event.target) && !previewTrigger?.contains(event.target)) closeFlyout();
  });
  document.addEventListener('focusin', event => {
    if (previewTrigger && !flyout.contains(event.target) && !previewTrigger.contains(event.target)) closeFlyout();
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !previewTrigger) return;
    event.stopPropagation();
    event.preventDefault();
    closeFlyout(flyout.contains(document.activeElement));
  }, { capture: true });
  window.addEventListener('resize', positionFlyout);
  rail.addEventListener('scroll', positionFlyout, { passive: true });

  search?.addEventListener('input', () => {
    rememberScroll();
    closeFlyout();
    render();
  });
  navigation.addEventListener('scroll', rememberScroll, { passive: true });
  for (const list of [navigation, flyoutLinks]) {
    list.addEventListener('click', event => {
      if (event.target.closest('.nav-link')) save();
    });
  }
  window.addEventListener('pagehide', save);

  rail.hidden = false;
  render();
})();
