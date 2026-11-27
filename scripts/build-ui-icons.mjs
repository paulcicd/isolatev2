import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const names = [
  'activity', 'arrow-up-right', 'arrow-right', 'book-open', 'chart-no-axes-combined',
  'check', 'chevron-down', 'chevron-right', 'circle-check', 'circle-pause', 'clock',
  'command', 'database', 'external-link', 'file-clock', 'file-text', 'globe', 'info', 'key-round',
  'layout-dashboard', 'list-filter', 'log-out', 'maximize', 'menu', 'minimize', 'network', 'refresh-cw',
  'search', 'server', 'settings-2', 'shield', 'shield-check', 'shield-alert',
  'sliders-horizontal', 'square-terminal', 'terminal', 'users', 'workflow', 'x',
];
const destination = path.join(root, 'shared/static/vendor/lucide');
await mkdir(destination, { recursive: true });
const symbols = [];
for (const name of names) {
  const source = await readFile(path.join(root, 'node_modules/lucide-static/icons', name + '.svg'), 'utf8');
  const content = source.slice(source.indexOf('>', source.indexOf('<svg')) + 1, source.lastIndexOf('</svg>'));
  symbols.push('<symbol id="' + name + '" viewBox="0 0 24 24">' + content.trim() + '</symbol>');
}
await writeFile(path.join(destination, 'sprite.svg'),
  '<!-- Lucide v1.71.0, ISC License. See LICENSE. -->\n<svg xmlns="http://www.w3.org/2000/svg">\n' +
  symbols.join('\n') + '\n</svg>\n');
await copyFile(path.join(root, 'node_modules/lucide-static/LICENSE'), path.join(destination, 'LICENSE'));
