/**
 * beforeBuildCommand: готовит ui/ к упаковке Tauri.
 *
 * Спрайты и иконки уже лежат в репозитории, поэтому сборка приложения
 * не требует node_modules и sharp — скрипт только проверяет комплект
 * и синхронизирует иконку тайтлбара. Пересобрать спрайты: build-sprites.mjs.
 */
import { copyFile, access, readdir, stat, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ui = path.join(root, 'ui');

const REQUIRED = [
  'index.html',
  'styles/base.css',
  'styles/components.css',
  'styles/screens.css',
  'src/main.js',
  'src/bridge.js',
  'src/store.js',
  'src/ui.js',
  'src/screens.js',
  'src/servers.js',
  'src/accounts.js',
  'assets/classes-dark.webp',
  'assets/classes-light.webp',
  'assets/sprite-manifest.js',
];

const missing = [];
for (const rel of REQUIRED) {
  await access(path.join(ui, rel)).catch(() => missing.push(rel));
}
if (missing.length) {
  console.error('Не хватает файлов интерфейса:\n  ' + missing.join('\n  '));
  process.exit(1);
}

// CSP без 'unsafe-inline': inline-стили в разметке и setAttribute('style') не сработают.
// Через CSSOM (el.style.x = ..., style.setProperty) можно — CSP это разрешает.
const conf = JSON.parse(await readFile(path.join(root, 'src-tauri', 'tauri.conf.json'), 'utf8'));
const csp = conf.app?.security?.csp ?? '';
const violations = [];
if (/unsafe-inline|unsafe-eval/.test(csp)) violations.push("CSP содержит 'unsafe-inline'/'unsafe-eval'");
const INLINE_STYLE = /\sstyle\s*=|setAttribute\(\s*['"]style['"]|<style[\s>]/;
async function scan(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await scan(full);
    else if (/\.(html|js)$/.test(entry.name) && INLINE_STYLE.test(await readFile(full, 'utf8'))) {
      violations.push(`inline-стиль в ${path.relative(root, full)}`);
    }
  }
}
await scan(ui);

// Эмблемы серверов: ядро выбирает номер 0..GLYPH_VARIANTS, UI обязан иметь такой символ.
const rust = await readFile(path.join(root, 'crates', 'pwl-core', 'src', 'domain.rs'), 'utf8');
const variants = Number(/GLYPH_VARIANTS:\s*u8\s*=\s*(\d+)/.exec(rust)?.[1]);
const indexHtml = await readFile(path.join(ui, 'index.html'), 'utf8');
const serversJs = await readFile(path.join(ui, 'src', 'servers.js'), 'utf8');
if (!variants) violations.push('не найден GLYPH_VARIANTS в domain.rs');
else {
  for (let i = 0; i < variants; i++) {
    if (!indexHtml.includes(`<symbol id="g${i}"`)) violations.push(`нет символа эмблемы g${i} в index.html`);
  }
  if (Number(/const GLYPHS\s*=\s*(\d+)/.exec(serversJs)?.[1]) !== variants) {
    violations.push(`GLYPHS в servers.js не равен GLYPH_VARIANTS (${variants})`);
  }
}

if (violations.length) {
  console.error('Нарушен контракт интерфейса:\n  ' + violations.join('\n  '));
  process.exit(1);
}

await copyFile(path.join(root, 'src-tauri', 'icons', '32x32.png'), path.join(ui, 'assets', 'app-32.png'));

let bytes = 0;
async function walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) await walk(full);
    else bytes += (await stat(full)).size;
  }
}
await walk(ui);

console.log(`ui готов: ${REQUIRED.length} обязательных файлов, ${(bytes / 1024).toFixed(0)} КБ всего`);
