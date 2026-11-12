/**
 * Экран аккаунтов. Виртуальный список: в DOM живут только видимые строки
 * (~20 узлов) независимо от того, 5 аккаунтов на сервере или 5000.
 *
 * Строки переиспользуются из пула, скролл обрабатывается один раз за кадр,
 * порядок меняется перетаскиванием с указателем (работает и мышью, и тачем).
 */
import { data, apply, on, serverById } from './store.js';
import { invoke, errorText } from './bridge.js';
import { $, el, icon, openMenu, confirmDialog, toast, plural } from './ui.js';
import { showAccountForm, ensureClient, showServers } from './screens.js';

const ROW = 44; // синхронно с --row-h в base.css
const OVERSCAN = 4;

let serverId = null;
let rows = [];
let sel = -1;
let query = '';
let pool = [];
let frame = 0;
let drag = null;

const server = () => serverById(serverId);
const account = (i) => rows[i] || null;

/* ── строки ──────────────────────────────────────────────── */

function makeRow() {
  const node = el('div', 'vrow');
  const grip = el('span', 'c-grip');
  grip.append(icon('i-grip'));
  const cls = el('span', 'c-class');
  const ic = el('i', 'class-ic');
  cls.append(ic);
  const nick = el('span', 'c-nick');
  const login = el('span', 'c-login');
  const note = el('span', 'c-note');
  const act = el('span', 'c-act');
  const more = el('button', 'row-btn');
  more.type = 'button';
  more.title = 'Действия';
  more.append(icon('i-edit'));
  act.append(more);
  node.append(grip, cls, nick, login, note, act);
  node._parts = { ic, nick, login, note };
  return node;
}

function fillRow(node, index) {
  const a = rows[index];
  const p = node._parts;
  node.dataset.index = String(index);
  node.style.setProperty('--y', `${index * ROW}px`);
  node.classList.toggle('sel', index === sel);
  node.hidden = false;

  p.ic.style.setProperty('--i', String(a.spriteIndex));
  p.ic.title = data.classBySlug.get(a.class)?.name || a.class; // имя класса — только подсказкой, иконки достаточно
  p.nick.textContent = a.nick || a.login;
  if (a.autoRole) {
    const badge = el('span', 'auto-badge', 'АВТО');
    p.nick.append(badge);
  }
  p.login.textContent = a.login;
  p.note.textContent = a.comment || '';
  node.title = a.comment ? `${a.nick} — ${a.comment}` : a.nick || a.login;
}

function paint() {
  frame = 0;
  const list = $('vlist');
  const host = $('vlist-rows');
  const top = list.scrollTop;
  const first = Math.max(0, Math.floor(top / ROW) - OVERSCAN);
  const last = Math.min(rows.length, Math.ceil((top + list.clientHeight) / ROW) + OVERSCAN);
  const need = Math.max(0, last - first);

  while (pool.length < need) {
    const node = makeRow();
    pool.push(node);
    host.append(node);
  }
  for (let i = 0; i < pool.length; i += 1) {
    const node = pool[i];
    if (i < need) fillRow(node, first + i);
    else node.hidden = true;
  }
}

function schedule() {
  if (!frame) frame = requestAnimationFrame(paint);
}

/* ── выбор и запуск ──────────────────────────────────────── */

function select(index, scroll = false) {
  sel = index;
  $('btn-enter').disabled = index < 0;
  if (scroll && index >= 0) {
    const list = $('vlist');
    const y = index * ROW;
    if (y < list.scrollTop) list.scrollTop = y;
    else if (y + ROW > list.scrollTop + list.clientHeight) list.scrollTop = y + ROW - list.clientHeight;
  }
  schedule();
}

async function enter(index) {
  const a = account(index);
  const s = server();
  if (!a || !s) return;
  if (!(await ensureClient(s))) return;
  try {
    const info = await invoke('launch', { serverId: s.id, accountId: a.id });
    toast(`Запуск: ${a.nick || a.login} · pid ${info.pid}`, 'ok');
  } catch (e) {
    toast(errorText(e), 'err', 5000);
  }
}

async function remove(index) {
  const a = account(index);
  const s = server();
  if (!a || !s) return;
  if (data.settings.confirmDelete) {
    const ok = await confirmDialog({
      title: 'Удалить аккаунт?',
      text: `${a.nick || a.login} (${a.login}) будет удалён с сервера «${s.name}».`,
      actions: [
        { label: 'Отмена', cls: 'btn quiet', value: null },
        { label: 'Удалить', cls: 'btn danger', value: true },
      ],
    });
    if (!ok) return;
  }
  try {
    await apply({ op: 'deleteAccount', serverId: s.id, id: a.id });
    toast('Аккаунт удалён', 'ok');
  } catch (e) {
    toast(errorText(e), 'err');
  }
}

function rowMenu(index, x, y) {
  const a = account(index);
  if (!a) return;
  select(index);
  openMenu(x, y, [
    { label: 'Войти в игру', icon: 'i-play', onClick: () => enter(index) },
    { label: 'Редактировать', icon: 'i-edit', onClick: () => showAccountForm(server(), a) },
    'sep',
    { label: 'Удалить', icon: 'i-trash', danger: true, onClick: () => remove(index) },
  ]);
}

/* ── перетаскивание ──────────────────────────────────────── */

function dragStart(e, index) {
  if (e.button !== 0 || query) return; // при поиске порядок не меняем
  const list = $('vlist');
  drag = { index, from: index, to: index, y0: e.clientY, active: false, id: rows[index].id };
  list.setPointerCapture(e.pointerId);
}

function dragMove(e) {
  if (!drag) return;
  if (!drag.active) {
    if (Math.abs(e.clientY - drag.y0) < 5) return;
    drag.active = true;
    const line = el('div', 'drop-line');
    line.id = 'drop-line';
    $('vlist-rows').append(line);
    document.body.style.cursor = 'grabbing';
  }
  const list = $('vlist');
  const rect = list.getBoundingClientRect();
  const y = e.clientY - rect.top + list.scrollTop;
  drag.to = Math.max(0, Math.min(rows.length, Math.round(y / ROW)));
  $('drop-line').style.setProperty('--y', `${drag.to * ROW}px`);

  const edge = 28;
  if (e.clientY - rect.top < edge) list.scrollTop -= 8;
  else if (rect.bottom - e.clientY < edge) list.scrollTop += 8;
}

async function dragEnd() {
  if (!drag) return;
  const { active, from, to, id } = drag;
  drag = null;
  document.body.style.cursor = '';
  $('drop-line')?.remove();
  if (!active) return;

  const target = to > from ? to - 1 : to;
  if (target === from) return;
  try {
    await apply({ op: 'moveAccount', serverId, id, to: target });
    select(rows.findIndex((a) => a.id === id));
  } catch (e) {
    toast(errorText(e), 'err');
  }
}

/* ── перерисовка ─────────────────────────────────────────── */

function refilter(keepId) {
  const s = server();
  const all = s ? s.accounts : [];
  const q = query.trim().toLowerCase();
  rows = q
    ? all.filter((a) => `${a.nick} ${a.login} ${a.comment}`.toLowerCase().includes(q))
    : all.slice();

  const wanted = keepId ?? (sel >= 0 ? rows[sel]?.id : null);
  sel = wanted ? rows.findIndex((a) => a.id === wanted) : -1;
  if (sel < 0 && rows.length) sel = 0;
}

export function renderAccounts(keepId) {
  const s = server();
  if (!s) { showServers(); return; }

  $('accounts-title').textContent = s.name;
  const n = s.accounts.length;
  $('accounts-count').textContent = `${n} ${plural(n, 'аккаунт', 'аккаунта', 'аккаунтов')}`;

  refilter(keepId);
  $('vlist-sizer').style.height = `${rows.length * ROW}px`;
  $('accounts-empty').hidden = rows.length > 0;
  $('accounts-empty').querySelector('p').textContent = query ? 'Ничего не найдено' : 'Аккаунтов пока нет';
  $('btn-add-account-empty').hidden = !!query;
  $('btn-enter').disabled = sel < 0;
  schedule();
}

export function openServer(id) {
  serverId = id;
  query = '';
  $('account-search').value = '';
  $('vlist').scrollTop = 0;
  sel = 0;
  renderAccounts();
}

export function currentServerId() {
  return serverId;
}

export function initAccounts() {
  const list = $('vlist');
  const host = $('vlist-rows');

  list.addEventListener('scroll', schedule, { passive: true });
  new ResizeObserver(schedule).observe(list);

  host.addEventListener('pointerdown', (e) => {
    const row = e.target.closest('.vrow');
    if (!row || e.target.closest('.row-btn')) return;
    const index = Number(row.dataset.index);
    select(index);
    dragStart(e, index);
  });
  // Захват указателя на скролл-контейнере: события приходят ему, не строке.
  list.addEventListener('pointermove', dragMove);
  list.addEventListener('pointerup', dragEnd);
  list.addEventListener('pointercancel', dragEnd);

  host.addEventListener('dblclick', (e) => {
    const row = e.target.closest('.vrow');
    if (row) enter(Number(row.dataset.index));
  });
  host.addEventListener('contextmenu', (e) => {
    const row = e.target.closest('.vrow');
    if (!row) return;
    e.preventDefault();
    rowMenu(Number(row.dataset.index), e.clientX, e.clientY);
  });
  host.addEventListener('click', (e) => {
    const btn = e.target.closest('.row-btn');
    if (!btn) return;
    const index = Number(btn.closest('.vrow').dataset.index);
    showAccountForm(server(), account(index));
  });

  list.addEventListener('keydown', (e) => {
    if (!rows.length) return;
    const page = Math.max(1, Math.floor(list.clientHeight / ROW) - 1);
    const map = {
      ArrowDown: () => select(Math.min(rows.length - 1, sel + 1), true),
      ArrowUp: () => select(Math.max(0, sel - 1), true),
      PageDown: () => select(Math.min(rows.length - 1, sel + page), true),
      PageUp: () => select(Math.max(0, sel - page), true),
      Home: () => select(0, true),
      End: () => select(rows.length - 1, true),
      Enter: () => enter(sel),
      Delete: () => remove(sel),
    };
    const fn = map[e.key];
    if (fn) { e.preventDefault(); fn(); }
  });

  $('account-search').addEventListener('input', (e) => {
    query = e.target.value;
    renderAccounts();
  });
  $('btn-enter').addEventListener('click', () => enter(sel));
  $('btn-add-account').addEventListener('click', () => showAccountForm(server(), null));
  $('btn-add-account-empty').addEventListener('click', () => showAccountForm(server(), null));

  on('accounts', (evt) => {
    if (evt.serverId === serverId) renderAccounts(evt.id);
  });
}
