/**
 * Статический сервер для превью интерфейса вне Windows.
 *
 * Tauri-GUI в песочнице не поднять (нет webkit2gtk и дисплея), но интерфейс
 * можно посмотреть в браузере: тот же ui/, тот же код, мост подменяется
 * мок-реализацией на localStorage (см. ui/src/bridge.js).
 *
 * Запуск: node tools/dev-server.mjs [порт]   (по умолчанию 5173)
 * В tauri.conf.json это beforeDevCommand.
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'ui');
const port = Number(process.argv[2] || process.env.PORT || 5173);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webp': 'image/webp',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml',
};

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    let rel = decodeURIComponent(url.pathname);
    if (rel.endsWith('/')) rel += 'index.html';

    const file = path.join(root, path.normalize(rel));
    if (!file.startsWith(root)) { res.writeHead(403).end('forbidden'); return; }

    const info = await stat(file).catch(() => null);
    if (!info?.isFile()) { res.writeHead(404).end('not found'); return; }

    const body = await readFile(file);
    res.writeHead(200, {
      'content-type': MIME[path.extname(file)] || 'application/octet-stream',
      'cache-control': 'no-cache',
      // Превью живёт в iframe на другом origin — разрешаем встраивание.
      'access-control-allow-origin': '*',
    });
    res.end(body);
  } catch (e) {
    res.writeHead(500).end(String(e));
  }
});

server.listen(port, '0.0.0.0', () => {
  console.log(`PWL ui → http://0.0.0.0:${port}  (корень: ${root})`);
});
