import { Terminal } from '/static/vendor/xterm/xterm.mjs';
import { timeLabel, chunkIndexAt, findTerminalMatches } from './terminal-workspace-utils.mjs';

const root = document.getElementById('terminal-replay');
const configuration = document.getElementById('terminal-replay-config');
if (root && configuration) {
  const config = JSON.parse(configuration.textContent), ru = config.language === 'ru';
  const words = ru ? { loading: 'Загружаем запись и проверяем её целостность…',
    failed: 'Не удалось открыть запись. Обновите страницу. Если ошибка повторится, сообщите администратору ID сессии.',
    loaded: 'Запись готова к просмотру', empty: 'В записи нет вывода команд.', bookmarkFailed: 'Не удалось сохранить изменения в закладках. Повторите попытку.',
    bookmarksFailed: 'Не удалось загрузить закладки. Обновите страницу.', none: 'Закладок пока нет.', delete: 'Удалить закладку',
    saved: 'Закладка сохранена.', noMatches: 'Нет совпадений', play: 'Воспроизведение', paused: 'Пауза' }
    : { loading: 'Loading verified recording…', failed: 'Recording unavailable or integrity verification failed.', loaded: 'Recording ready',
      empty: 'No terminal output in this recording.', bookmarkFailed: 'Could not save bookmark. Check your access and try again.',
      bookmarksFailed: 'Bookmarks are temporarily unavailable.', none: 'No bookmarks yet. Save an important moment.', delete: 'Delete bookmark',
      saved: 'Bookmark saved.', noMatches: 'No matches', play: 'Playing', paused: 'Paused' };
  const terminalElement = document.getElementById('tr-terminal'), readable = document.getElementById('tr-readable');
  const readableToggle = document.getElementById('tr-readable-toggle'), textView = document.getElementById('tr-text-view');
  const readableEmpty = document.getElementById('tr-readable-empty'), playback = document.getElementById('tr-playback-actions');
  const state = document.getElementById('tr-state'), clock = document.getElementById('tr-clock'), scrubber = document.getElementById('tr-scrubber');
  const speed = document.getElementById('tr-speed'), bookmarkState = document.getElementById('tr-bookmark-state');
  const terminal = new Terminal({ rows: 40, cols: 140, scrollback: 20000, disableStdin: true, convertEol: false,
    fontSize: 14, fontFamily: 'ui-monospace, monospace', theme: { background: '#090a0c', foreground: '#e7e8ea', cursor: '#7aa7ff', selectionBackground: '#1a2436' } });
  terminal.open(terminalElement); speed.value = String(config.defaultSpeed);
  let chunks = [], duration = 0, position = 0, cursor = 0, playing = false, disposed = false, frame = null, lastFrame = null, searchIndex = -1;
  let ready = false, renderVersion = 0, renderQueue = Promise.resolve();
  const controller = new AbortController();
  const bookmarksEndpoint = `/api/v1/recordings/${encodeURIComponent(config.connectionId)}/bookmarks`;
  const headers = () => ({ 'Content-Type': 'application/json', 'X-CSRF-Token': config.csrf });
  function updateClock() { clock.textContent = `${timeLabel(position)} / ${timeLabel(duration)}`; scrubber.value = String(position); }
  function pause() {
    playing = false; lastFrame = null; if (frame !== null) cancelAnimationFrame(frame); frame = null;
    document.getElementById('tr-play').disabled = !ready;
  }
  function renderAt(value) {
    pause(); const target = Math.max(0, Math.min(duration, Number(value) || 0)), version = ++renderVersion;
    // Serialize resets with pending xterm writes so fast scrubbing cannot mix
    // output from an old seek into a newer one.
    const task = renderQueue.then(async () => {
      if (version !== renderVersion || disposed) return;
      position = target; cursor = chunkIndexAt(chunks, position); terminal.reset();
      for (let start = 0; start < cursor && !disposed && version === renderVersion; start += 200) {
        const output = chunks.slice(start, Math.min(cursor, start + 200)).map(chunk => chunk.data).join('');
        await new Promise(resolve => terminal.write(output, resolve));
      }
      if (version === renderVersion) updateClock();
    });
    renderQueue = task.catch(() => {}); return task;
  }
  function tick(timestamp) {
    if (!playing || disposed) return;
    if (lastFrame === null) lastFrame = timestamp;
    position = Math.min(duration, position + Math.max(0, timestamp - lastFrame) / 1000 * Number(speed.value)); lastFrame = timestamp;
    const next = chunkIndexAt(chunks, position);
    if (next > cursor) {
      terminal.write(chunks.slice(cursor, next).map(chunk => chunk.data).join(''));
      cursor = next;
    }
    updateClock();
    if (position >= duration) { pause(); state.textContent = words.loaded; } else frame = requestAnimationFrame(tick);
  }
  async function play() {
    if (!ready || disposed || playing || readableToggle.checked) return;
    const version = renderVersion; await renderQueue;
    if (version !== renderVersion || disposed || readableToggle.checked) return;
    if (position >= duration) {
      const next = renderVersion + 1;
      await renderAt(0);
      if (next !== renderVersion || disposed || readableToggle.checked) return;
    }
    playing = true; lastFrame = null; state.textContent = words.play;
    document.getElementById('tr-play').disabled = true; frame = requestAnimationFrame(tick);
  }
  document.getElementById('tr-play').addEventListener('click', play);
  document.getElementById('tr-pause').addEventListener('click', () => { pause(); state.textContent = words.paused; });
  document.getElementById('tr-reset').addEventListener('click', () => renderAt(0));
  scrubber.addEventListener('input', () => renderAt(scrubber.value));
  function resize() {
    if (disposed || terminalElement.hidden || !terminalElement.clientWidth) return;
    terminal.resize(Math.max(20, Math.min(500, Math.floor((terminalElement.clientWidth - 16) / 8.45))),
      Math.max(5, Math.min(200, Math.floor((terminalElement.clientHeight - 8) / 17))));
  }
  const observer = new ResizeObserver(resize); observer.observe(terminalElement); resize();
  const findPanel = document.getElementById('tr-find'), findInput = document.getElementById('tr-find-input');
  const findLabel = document.getElementById('tr-find-label'), findCount = document.getElementById('tr-find-count');
  document.getElementById('tr-find-toggle').addEventListener('click', () => { findPanel.hidden = !findPanel.hidden; if (!findPanel.hidden) findInput.focus(); });
  let findQuery = '', findMatches = [];
  function resetSearch() {
    findQuery = '';
    searchIndex = -1;
    findCount.textContent = '';
    const selection = window.getSelection();
    if (selection?.anchorNode && readable.contains(selection.anchorNode)) selection.removeAllRanges();
  }
  function updateView() {
    const textMode = readableToggle.checked;
    pause();
    resetSearch();
    root.dataset.view = textMode ? 'text' : 'playback';
    terminalElement.hidden = textMode;
    textView.hidden = !textMode;
    playback.hidden = textMode;
    findLabel.textContent = textMode ? findLabel.dataset.text : findLabel.dataset.terminal;
    if (ready) state.textContent = chunks.length ? words.loaded : words.empty;
    resize();
  }
  const url = new URL(window.location.href);
  readableToggle.checked = url.searchParams.get('view') === 'text';
  readableToggle.addEventListener('change', () => {
    if (readableToggle.checked) url.searchParams.set('view', 'text');
    else url.searchParams.delete('view');
    window.history.replaceState(window.history.state, '', url);
    updateView();
  });
  updateView();

  function findTranscriptMatches(query) {
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const matches = [];
    for (const match of readable.textContent.matchAll(new RegExp(escaped, 'giu'))) {
      matches.push({ offset: match.index, length: match[0].length });
      if (matches.length === 1000) break;
    }
    return matches;
  }
  function selectTranscriptMatch(match) {
    const range = document.createRange();
    range.setStart(readable.firstChild, match.offset);
    range.setEnd(readable.firstChild, match.offset + match.length);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    const output = readable.getBoundingClientRect();
    const selected = range.getBoundingClientRect();
    if (selected.top < output.top || selected.bottom > output.bottom) {
      readable.scrollTop += selected.top - output.top - readable.clientHeight / 3;
    }
  }
  async function find(direction) {
    if (!ready || !findInput.value) return;
    const query = findInput.value;
    const textMode = readableToggle.checked;
    if (query !== findQuery || (!textMode && position < duration)) {
      if (textMode) {
        findMatches = findTranscriptMatches(query);
      } else {
        // Search all recorded output, including portions ahead of the playhead.
        const next = renderVersion + 1;
        await renderAt(duration);
        if (next !== renderVersion || readableToggle.checked || query !== findInput.value) return;
        findMatches = findTerminalMatches(terminal.buffer.active, query);
      }
      findQuery = query;
      searchIndex = -1;
    }
    if (!findMatches.length) { findCount.textContent = words.noMatches; return; }
    const count = findMatches.length;
    searchIndex = searchIndex < 0 && direction < 0 ? count - 1 : (searchIndex + direction + count) % count;
    const match = findMatches[searchIndex];
    if (textMode) {
      selectTranscriptMatch(match);
    } else {
      terminal.select(match.column, match.row, match.length);
      terminal.scrollToLine(match.row);
    }
    findCount.textContent = `${searchIndex + 1}/${count}`;
  }
  findInput.addEventListener('input', resetSearch);
  findInput.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); find(event.shiftKey ? -1 : 1); } });
  document.getElementById('tr-find-previous').addEventListener('click', () => find(-1));
  document.getElementById('tr-find-next').addEventListener('click', () => find(1));
  async function loadBookmarks() {
    try {
      const response = await fetch(bookmarksEndpoint, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error();
      const data = await response.json(), list = document.getElementById('tr-bookmark-list'); list.replaceChildren();
      const bookmarks = (data.bookmarks || []).slice(0, 200).filter(item => Number.isFinite(item.seconds) && item.seconds >= 0);
      bookmarks.sort((a, b) => a.seconds - b.seconds).forEach(item => {
        const row = document.createElement('li'), jump = document.createElement('button'), remove = document.createElement('button');
        jump.type = remove.type = 'button'; jump.className = 'tr-bookmark-jump';
        const timestamp = document.createElement('time'), label = document.createElement('span'); timestamp.textContent = timeLabel(item.seconds); label.textContent = String(item.label || '');
        jump.append(timestamp, label); jump.addEventListener('click', () => renderAt(item.seconds));
        remove.textContent = '×'; remove.className = 'tr-bookmark-delete'; remove.setAttribute('aria-label', `${words.delete}: ${String(item.label || '')}`);
        remove.addEventListener('click', async () => {
          remove.disabled = true;
          try {
            const response = await fetch(`${bookmarksEndpoint}/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'same-origin', headers: headers(), signal: controller.signal });
            if (!response.ok) throw new Error(); await loadBookmarks();
          } catch { bookmarkState.textContent = words.bookmarkFailed; remove.disabled = false; }
        });
        row.append(jump, remove); list.append(row);
      });
      bookmarkState.textContent = bookmarks.length ? '' : words.none;
    } catch (error) { if (error.name !== 'AbortError') bookmarkState.textContent = words.bookmarksFailed; }
  }
  document.getElementById('tr-bookmark-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!ready) return;
    const input = document.getElementById('tr-bookmark-label'), label = input.value.trim(); if (!label) return;
    const submit = event.target.querySelector('button[type="submit"]'); submit.disabled = true;
    try {
      const response = await fetch(bookmarksEndpoint, { method: 'POST', credentials: 'same-origin', headers: headers(),
        body: JSON.stringify({ seconds: Math.round(position * 1000) / 1000, label: label.slice(0, 160) }), signal: controller.signal });
      if (!response.ok) throw new Error(); input.value = ''; await loadBookmarks(); bookmarkState.textContent = words.saved;
    } catch (error) { if (error.name !== 'AbortError') bookmarkState.textContent = words.bookmarkFailed; }
    finally { submit.disabled = false; }
  });
  root.addEventListener('keydown', event => {
    const editing = ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(event.target.tagName);
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'f') {
      event.preventDefault(); findPanel.hidden = false; findInput.focus();
    } else if (event.code === 'Space' && !editing && !readableToggle.checked) { event.preventDefault(); if (playing) pause(); else play(); }
  });
  window.addEventListener('pagehide', () => { disposed = true; controller.abort(); pause(); renderVersion++; observer.disconnect(); terminal.dispose(); });
  async function initialize() {
    state.textContent = words.loading; document.getElementById('tr-play').disabled = true;
    try {
      const response = await fetch(`/replay/${encodeURIComponent(config.connectionId)}.json`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(); const data = await response.json();
      if (disposed) return;
      if (data.error && !(data.chunks || []).length && !data.plain) throw new Error();
      chunks = (data.chunks || []).filter(chunk => Number.isFinite(chunk.t) && chunk.t >= 0 && typeof chunk.data === 'string');
      chunks.sort((a, b) => a.t - b.t); duration = chunks.length ? chunks[chunks.length - 1].t : 0;
      readable.textContent = typeof data.readable === 'string' ? data.readable : '';
      readable.hidden = !readable.textContent;
      readableEmpty.hidden = !readable.hidden;
      document.getElementById('tr-truncated').hidden = data.truncated !== true;
      if (!chunks.length && data.plain) chunks = [{ t: 0, data: data.plain }];
      scrubber.max = String(duration); ready = true; updateClock();
      state.textContent = chunks.length ? words.loaded : words.empty;
      document.getElementById('tr-play').disabled = false;
      if (chunks.length && duration === 0) await renderAt(0);
      loadBookmarks();
    } catch (error) { if (error.name !== 'AbortError') state.textContent = words.failed; }
  }
  initialize();
}
