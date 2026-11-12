/**
 * Зеркало состояния ядра в памяти UI.
 *
 * Ни один клик не читает диск: bootstrap один раз, дальше точечные патчи
 * (Change) применяются к зеркалу. Именно этого не было в v0.9, где каждый
 * вызов моста перечитывал config.json и файл аккаунтов.
 */
import { invoke, listen, isNative, errorText } from './bridge.js';
import { $, toast, debounce } from './ui.js';

export const data = {
  version: '',
  schema: 0,
  settings: { theme: 'dark', minimizeToTray: false, accepted: false, confirmDelete: true },
  servers: [],
  races: [],
  classes: [],
  classBySlug: new Map(),
  secretsSecure: false,
  migration: null,
};

const subs = new Map();

/** Подписка на тему: 'bootstrap', 'servers', 'accounts', 'settings' или '*'. */
export function on(topic, fn) {
  if (!subs.has(topic)) subs.set(topic, new Set());
  subs.get(topic).add(fn);
  return () => subs.get(topic).delete(fn);
}

function emit(topic, payload) {
  for (const fn of subs.get(topic) || []) fn(payload);
  for (const fn of subs.get('*') || []) fn(topic, payload);
}

/* ── индикатор сохранения ────────────────────────────────── */

const SAVE_TEXT = {
  idle: 'Данные загружены',
  saving: 'Сохранение…',
  saved: 'Все изменения сохранены',
  error: 'Не удалось сохранить',
};

export function setSaveState(state) {
  const node = $('status-save');
  node.dataset.state = state;
  node.textContent = SAVE_TEXT[state] || '';
}

const requestFlush = debounce(async () => {
  try {
    await invoke('flush');
    // В браузере мок пишет синхронно, события оболочки там нет.
    if (!isNative) setSaveState('saved');
  } catch (e) {
    setSaveState('error');
    toast(errorText(e), 'err');
  }
}, 400);

function touched() {
  setSaveState('saving');
  requestFlush();
}

/* ── загрузка ────────────────────────────────────────────── */

export async function init() {
  const b = await invoke('bootstrap');
  data.version = b.version;
  data.schema = b.schema;
  data.settings = b.settings;
  data.servers = b.servers;
  data.races = b.races;
  data.classes = b.classes;
  data.classBySlug = new Map(b.classes.map((c) => [c.slug, c]));
  data.secretsSecure = b.secretsSecure;
  data.migration = b.migration;

  await listen('pwl://saved', () => setSaveState('saved'));
  await listen('pwl://save-error', (msg) => {
    setSaveState('error');
    toast(`Ошибка сохранения: ${msg}`, 'err', 6000);
  });
  await listen('pwl://warning', (msg) => toast(msg, 'info', 6000));

  setSaveState('idle');
  emit('bootstrap');
}

/* ── мутации ─────────────────────────────────────────────── */

export async function apply(op) {
  const change = await invoke('apply', { op });
  absorb(change);
  touched();
  return change;
}

export async function applyBatch(ops) {
  const changes = await invoke('apply_batch', { ops });
  for (const c of changes) absorb(c);
  touched();
  return changes;
}

export function serverById(id) {
  return data.servers.find((s) => s.id === id) || null;
}

function absorb(c) {
  switch (c.kind) {
    case 'settings':
      data.settings = c.settings;
      emit('settings', c.settings);
      break;
    case 'serverAdded':
      data.servers.push(c.server);
      emit('servers');
      break;
    case 'serverUpdated': {
      const s = serverById(c.meta.id);
      if (s) Object.assign(s, { name: c.meta.name, clientPath: c.meta.clientPath, art: c.meta.art, glyph: c.meta.glyph });
      emit('servers');
      emit('accounts', { serverId: c.meta.id, reason: 'meta' });
      break;
    }
    case 'serverRemoved':
      data.servers = data.servers.filter((s) => s.id !== c.id);
      emit('servers');
      break;
    case 'accountAdded': {
      const s = serverById(c.serverId);
      if (s) s.accounts.push(c.account);
      emit('servers');
      emit('accounts', { serverId: c.serverId, reason: 'add', id: c.account.id });
      break;
    }
    case 'accountUpdated': {
      const s = serverById(c.serverId);
      if (s) {
        const i = s.accounts.findIndex((a) => a.id === c.account.id);
        if (i >= 0) s.accounts[i] = c.account;
      }
      emit('accounts', { serverId: c.serverId, reason: 'update', id: c.account.id });
      break;
    }
    case 'accountRemoved': {
      const s = serverById(c.serverId);
      if (s) s.accounts = s.accounts.filter((a) => a.id !== c.id);
      emit('servers');
      emit('accounts', { serverId: c.serverId, reason: 'remove', id: c.id });
      break;
    }
    case 'accountMoved': {
      const s = serverById(c.serverId);
      if (s) {
        const from = s.accounts.findIndex((a) => a.id === c.id);
        if (from >= 0) {
          const [a] = s.accounts.splice(from, 1);
          s.accounts.splice(Math.min(c.to, s.accounts.length), 0, a);
        }
      }
      emit('accounts', { serverId: c.serverId, reason: 'move', id: c.id });
      break;
    }
    default:
      break;
  }
}
