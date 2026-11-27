import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../shared/static/precision-theme.js', import.meta.url), 'utf8');
function fixture({ saved = null, dark = false, blocked = false } = {}) {
  const documentEvents = {}, windowEvents = {}, mediaEvents = {};
  const root = { dataset: {} };
  const select = { value: '', addEventListener(name, handler) { this[name] = handler; } };
  const storage = {
    value: saved,
    getItem() { if (blocked) throw Error('blocked'); return this.value; },
    setItem(_key, value) { if (blocked) throw Error('blocked'); this.value = value; },
  };
  const media = { matches: dark, addEventListener: (name, handler) => { mediaEvents[name] = handler; } };
  vm.runInNewContext(source, {
    localStorage: storage,
    document: {
      documentElement: root,
      querySelectorAll: selector => selector === '[data-theme-select]' ? [select] : [],
      addEventListener: (name, handler) => { documentEvents[name] = handler; },
    },
    window: {
      matchMedia: () => media,
      addEventListener: (name, handler) => { windowEvents[name] = handler; },
    },
  });
  documentEvents.DOMContentLoaded();
  return { root, select, storage, media, mediaEvents, windowEvents };
}
{
  const f = fixture();
  assert.equal(f.root.dataset.themePreference, 'system');
  assert.equal(f.root.dataset.theme, 'light');
  f.media.matches = true;
  f.mediaEvents.change();
  assert.equal(f.root.dataset.theme, 'dark');
  f.select.value = 'light';
  f.select.change();
  assert.equal(f.storage.value, 'light');
  f.mediaEvents.change();
  assert.equal(f.root.dataset.theme, 'light', 'explicit choice wins over system changes');
  f.storage.value = 'dark';
  f.windowEvents.storage({ key: 'isolate-theme' });
  assert.equal(f.select.value, 'dark', 'other tabs update both preference and control');
  f.storage.value = null;
  f.windowEvents.storage({ key: null });
  assert.equal(f.select.value, 'system', 'clearing storage restores system preference');
}
assert.equal(fixture({ saved: 'dark' }).root.dataset.theme, 'dark', 'existing saved preference survives startup');
assert.equal(fixture({ saved: 'invalid', dark: true }).root.dataset.themePreference, 'system');
{
  const f = fixture({ blocked: true });
  f.select.value = 'dark';
  assert.doesNotThrow(() => f.select.change());
  assert.equal(f.root.dataset.theme, 'dark', 'storage restrictions do not break the UI');
}
console.log('Precision themes: system changes, persistence, cross-tab updates and blocked storage passed.');
