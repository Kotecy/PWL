/**
 * Генератор спрайтов классов.
 *
 * Было: 36 отдельных файлов (18 webp + 18 jpg), по одному запросу на строку
 * таблицы, и полная перерисовка таблицы при смене темы.
 * Стало: 2 спрайта, один запрос на тему, смена темы = смена CSS-переменной.
 *
 * Запуск: node tools/build-sprites.mjs   (нужен sharp: npm i в tools/)
 * Результат коммитится в ui/assets — сборка приложения node не требует.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import sharp from 'sharp';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const src = path.join(here, 'sprite-src', 'class');
const out = path.join(root, 'ui', 'assets');

// Порядок обязан совпадать с catalog::CLASSES (sprite_index) в pwl-core.
export const ORDER = [
  'var', 'mag', 'gan', 'tank', 'mk', 'dru', 'pal', 'prist', 'luk',
  'sham', 'sin', 'bard', 'sik', 'mist', 'dk', 'gost', 'kosa', 'lazur',
];

const CELL = 52; // 26 CSS-px @2x

async function sheet(theme) {
  const cells = await Promise.all(
    ORDER.map(async (slug) => {
      const file = theme === 'dark' ? path.join(src, `${slug}.webp`) : path.join(src, 'dark', `${slug}.jpg`);
      return sharp(file).resize(CELL, CELL, { fit: 'cover' }).toBuffer();
    }),
  );
  return sharp({
    create: { width: CELL * ORDER.length, height: CELL, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } },
  })
    .composite(cells.map((input, i) => ({ input, left: i * CELL, top: 0 })))
    .webp({ quality: 88, effort: 6 })
    .toBuffer();
}

await mkdir(out, { recursive: true });
for (const theme of ['dark', 'light']) {
  const buf = await sheet(theme);
  const file = path.join(out, `classes-${theme}.webp`);
  await writeFile(file, buf);
  console.log(`classes-${theme}.webp  ${(buf.length / 1024).toFixed(1)} KB  (${ORDER.length} иконок ${CELL}px)`);
}

// Иконки бандла: 128x128 из исходного 32x32 (для NSIS/меню).
const icon128 = await sharp(path.join(root, 'src-tauri', 'icons', '32x32.png'))
  .resize(128, 128, { kernel: 'lanczos3' })
  .png()
  .toBuffer();
await writeFile(path.join(root, 'src-tauri', 'icons', '128x128.png'), icon128);
console.log(`icons/128x128.png  ${(icon128.length / 1024).toFixed(1)} KB`);

const manifest = `/* Сгенерировано tools/build-sprites.mjs — не править руками */\nexport const CLASS_ORDER = ${JSON.stringify(ORDER)};\nexport const SPRITE_CELL = 26;\n`;
await writeFile(path.join(out, 'sprite-manifest.js'), manifest);
console.log('sprite-manifest.js');