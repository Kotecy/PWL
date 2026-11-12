/**
 * Экран серверов: сетка карточек, поиск, пагинация по 4, контекстное меню.
 * Перерисовка только по событию 'servers' — не на каждый клик.
 */
import { data, apply, on } from './store.js';
import { $, el, icon, clear, openMenu, confirmDialog, toast, plural } from './ui.js';
import { errorText } from './bridge.js';
import { showAccounts, showServerForm } from './screens.js';

const PER_PAGE = 4;
/** Число эмблем в SVG-спрайте (g0…g19). Обязано совпадать с GLYPH_VARIANTS в pwl-core/domain.rs — это проверяет build-assets.mjs. */
const GLYPHS = 20;
let page = 0;
let query = '';

function filtered() {
  const q = query.trim().toLowerCase();
  return q ? data.servers.filter((s) => s.name.toLowerCase().includes(q)) : data.servers;
}

function card(server) {
  const node = el('button', 'server-card');
  node.type = 'button';
  node.dataset.id = server.id;

  const emblem = el('span', 'emblem');
  emblem.append(icon(`g${server.glyph % GLYPHS}`));
  node.append(emblem);

  const body = el('span', 's-body');
  body.append(el('span', 's-name', server.name));

  const metaRow = el('span', 's-meta');
  const n = server.accounts.length;
  metaRow.append(el('span', 's-count', `${n} ${plural(n, 'аккаунт', 'аккаунта', 'аккаунтов')}`));
  if (!server.clientPath) {
    const warn = el('span', 's-warn');
    warn.append(icon('i-warn'), el('span', null, 'нет клиента'));
    metaRow.append(warn);
  }
  body.append(metaRow);
  node.append(body);
  node.append(icon('i-right', 'ic s-go'));

  node.addEventListener('click', () => showAccounts(server.id));
  node.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    menuFor(server, e.clientX, e.clientY);
  });
  return node;
}

function menuFor(server, x, y) {
  openMenu(x, y, [
    { label: 'Открыть аккаунты', icon: 'i-right', onClick: () => showAccounts(server.id) },
    { label: 'Переименовать', icon: 'i-edit', onClick: () => showServerForm(server) },
    { label: 'Путь к клиенту', icon: 'i-folder', onClick: () => showServerForm(server, { focusPath: true }) },
    'sep',
    { label: 'Удалить сервер', icon: 'i-trash', danger: true, onClick: () => removeServer(server) },
  ]);
}

async function removeServer(server) {
  const n = server.accounts.length;
  let keepAccounts = true;
  if (n > 0) {
    const choice = await confirmDialog({
      title: `Удалить «${server.name}»?`,
      text: `На сервере ${n} ${plural(n, 'аккаунт', 'аккаунта', 'аккаунтов')}. Их можно оставить в библиотеке или удалить вместе с сервером.`,
      actions: [
        { label: 'Отмена', cls: 'btn quiet', value: null },
        { label: 'Удалить всё', cls: 'btn danger', value: 'all' },
        { label: 'Оставить аккаунты', cls: 'btn primary', value: 'keep' },
      ],
    });
    if (!choice) return;
    keepAccounts = choice === 'keep';
  } else {
    const ok = await confirmDialog({
      title: `Удалить «${server.name}»?`,
      text: 'Сервер исчезнет из списка. Действие нельзя отменить.',
      actions: [
        { label: 'Отмена', cls: 'btn quiet', value: null },
        { label: 'Удалить', cls: 'btn danger', value: 'all' },
      ],
    });
    if (!ok) return;
  }

  try {
    await apply({ op: 'deleteServer', id: server.id, keepAccounts });
    toast(`Сервер «${server.name}» удалён`, 'ok');
  } catch (e) {
    toast(errorText(e), 'err');
  }
}

function pager(total) {
  const host = $('server-pager');
  clear(host);
  const pages = Math.ceil(total / PER_PAGE);
  if (pages <= 1) { host.hidden = true; return; }
  host.hidden = false;

  const mk = (label, target, disabled, current, iconName) => {
    const b = el('button', 'page-btn');
    b.type = 'button';
    if (iconName) b.append(icon(iconName)); else b.textContent = String(label);
    b.disabled = disabled;
    if (current) b.setAttribute('aria-current', 'true');
    b.addEventListener('click', () => { page = target; render(); });
    return b;
  };

  host.append(mk(null, page - 1, page === 0, false, 'i-left'));
  for (let i = 0; i < pages; i += 1) host.append(mk(i + 1, i, false, i === page));
  host.append(mk(null, page + 1, page >= pages - 1, false, 'i-right'));
}

export function render() {
  const list = filtered();
  const pages = Math.max(1, Math.ceil(list.length / PER_PAGE));
  if (page >= pages) page = pages - 1;

  const grid = $('server-grid');
  clear(grid);
  for (const s of list.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE)) grid.append(card(s));

  const empty = $('server-empty');
  empty.hidden = list.length > 0;
  if (!list.length) {
    empty.querySelector('h3').textContent = query ? 'Ничего не найдено' : 'Здесь пока пусто';
    empty.querySelector('p').textContent = query ? `По запросу «${query}» серверов нет` : 'Добавьте первый сервер, чтобы начать';
    $('btn-add-server-empty').hidden = !!query;
  }
  pager(list.length);
}

export function initServers() {
  $('server-search').addEventListener('input', (e) => {
    query = e.target.value;
    page = 0;
    render();
  });
  on('servers', render);
  render();
}
