/**
 * Навигация между экранами и формы сервера/аккаунта.
 * Экраны переключаются атрибутом hidden — без пересоздания разметки.
 */
import { data, apply, applyBatch, serverById } from './store.js';
import { invoke, errorText } from './bridge.js';
import { $, el, clear, openModal, closeModal, toast } from './ui.js';
import { render as renderServers } from './servers.js';
import { openServer, renderAccounts, currentServerId } from './accounts.js';

const SCREENS = ['welcome', 'servers', 'accounts', 'server-form', 'account-form'];
let current = 'welcome';
let serverCtx = null;   // редактируемый сервер или null
let serverReturn = null; // куда вернуться после формы сервера
let accountCtx = null;  // {server, account}
let onboarding = false;
let pickedPath = null;
let pathResolve = null;

export function show(name) {
  for (const s of SCREENS) $(`screen-${s}`).hidden = s !== name;
  current = name;
}

export function currentScreen() {
  return current;
}

export function showWelcome() {
  show('welcome');
}

export function showServers() {
  show('servers');
  renderServers();
}

export function showAccounts(id) {
  openServer(id);
  show('accounts');
  $('vlist').focus({ preventScroll: true });
}

/* ── форма сервера ───────────────────────────────────────── */

export function showServerForm(server = null, opts = {}) {
  serverCtx = server;
  serverReturn = current === 'accounts' ? currentServerId() : null;
  if (opts.onboarding) onboarding = true;
  pickedPath = server?.clientPath || null;

  $('server-form-kicker').hidden = !onboarding;
  $('server-form-title').textContent = server ? 'Настройки сервера' : 'Добавление сервера';
  $('f-server-name').value = server?.name || '';
  $('server-form-error').hidden = true;
  paintPath();
  show('server-form');
  (opts.focusPath ? $('btn-pick-server') : $('f-server-name')).focus();
}

function paintPath() {
  const node = $('server-path');
  node.hidden = !pickedPath;
  node.textContent = pickedPath || '';
  node.title = pickedPath || '';
}

async function pickInto(kind) {
  try {
    const path = await invoke('pick_client');
    if (!path) return null;
    if (kind === 'server') { pickedPath = path; paintPath(); }
    return path;
  } catch (e) {
    toast(errorText(e), 'err');
    return null;
  }
}

async function saveServer(e) {
  e.preventDefault();
  const name = $('f-server-name').value.trim();
  const err = $('server-form-error');
  if (!name) {
    err.textContent = 'Введите название сервера';
    err.hidden = false;
    $('f-server-name').focus();
    return;
  }
  try {
    if (serverCtx) {
      const ops = [];
      if (name !== serverCtx.name) ops.push({ op: 'renameServer', id: serverCtx.id, name });
      if (pickedPath !== serverCtx.clientPath) ops.push({ op: 'setClientPath', id: serverCtx.id, path: pickedPath });
      if (ops.length) await applyBatch(ops);
      if (serverReturn) showAccounts(serverReturn); else showServers();
    } else {
      const change = await apply({ op: 'addServer', name, clientPath: pickedPath });
      toast(`Сервер «${name}» добавлен`, 'ok');
      if (onboarding) {
        showAccountForm(serverById(change.server.id), null);
      } else {
        showServers();
      }
    }
  } catch (ex) {
    err.textContent = errorText(ex);
    err.hidden = false;
  }
}

/* ── форма аккаунта ──────────────────────────────────────── */

function fillRaces(selected) {
  const raceSel = $('f-race');
  clear(raceSel);
  for (const r of data.races) {
    const opt = el('option', null, r.name);
    opt.value = r.name;
    raceSel.append(opt);
  }
  raceSel.value = selected || data.races[0]?.name;
  fillClasses(null);
}

function fillClasses(selected) {
  const race = data.races.find((r) => r.name === $('f-race').value);
  const sel = $('f-class');
  clear(sel);
  for (const slug of race?.classes || []) {
    const info = data.classBySlug.get(slug);
    const opt = el('option', null, info?.name || slug);
    opt.value = slug;
    sel.append(opt);
  }
  if (selected && [...sel.options].some((o) => o.value === selected)) sel.value = selected;
}

export function showAccountForm(server, account = null) {
  if (!server) return;
  accountCtx = { server, account };
  $('account-form-kicker').hidden = !onboarding;
  $('account-form-title').textContent = account ? 'Редактирование аккаунта' : 'Добавление аккаунта';
  $('account-form-error').hidden = true;

  $('f-login').value = account?.login || '';
  $('f-password').value = '';
  $('f-password').placeholder = account?.hasPassword ? 'Без изменений' : '';
  $('f-nick').value = account?.nick || '';
  $('f-auto').checked = !!account?.autoRole;
  $('f-comment').value = account?.comment || '';

  const info = account ? data.classBySlug.get(account.class) : null;
  fillRaces(info?.race);
  if (account) fillClasses(account.class);

  show('account-form');
  $('f-login').focus();
}

async function saveAccount(e) {
  e.preventDefault();
  const err = $('account-form-error');
  const login = $('f-login').value.trim();
  const password = $('f-password').value;
  const { server, account } = accountCtx;

  if (!login) {
    err.textContent = 'Введите логин';
    err.hidden = false;
    $('f-login').focus();
    return;
  }
  if (!account && !password) {
    err.textContent = 'Введите пароль';
    err.hidden = false;
    $('f-password').focus();
    return;
  }

  const draft = {
    login,
    password: password ? password : null,
    nick: $('f-nick').value.trim(),
    autoRole: $('f-auto').checked,
    class: $('f-class').value,
    comment: $('f-comment').value.trim(),
  };

  try {
    if (account) {
      await apply({ op: 'updateAccount', serverId: server.id, id: account.id, draft });
      toast('Аккаунт обновлён', 'ok');
    } else {
      await apply({ op: 'addAccount', serverId: server.id, draft });
      toast('Аккаунт добавлен', 'ok');
    }
    const wasOnboarding = onboarding;
    onboarding = false;
    accountCtx = null;
    if (wasOnboarding || current === 'account-form') showAccounts(server.id);
    else renderAccounts();
  } catch (ex) {
    err.textContent = errorText(ex);
    err.hidden = false;
  }
}

/* ── путь к клиенту по требованию ────────────────────────── */

export function ensureClient(server) {
  if (server.clientPath) return Promise.resolve(true);

  $('path-title').textContent = `Нужен Elementclient для «${server.name}»`;
  $('path-error').hidden = true;
  $('modal-path-value').hidden = true;
  $('btn-path-save').disabled = true;
  let chosen = null;

  const modal = openModal('modal-path');
  modal._serverId = server.id;
  return new Promise((resolve) => {
    pathResolve = (value) => {
      pathResolve = null;
      closeModal(modal);
      resolve(value);
    };
    modal._chosen = () => chosen;
    modal._setChosen = (p) => {
      chosen = p;
      const node = $('modal-path-value');
      node.hidden = !p;
      node.textContent = p || '';
      node.title = p || '';
      $('btn-path-save').disabled = !p;
    };
  });
}

export function initScreens() {
  $('btn-accept').addEventListener('click', async () => {
    try {
      await apply({ op: 'setSettings', patch: { accepted: true } });
    } catch (e) {
      toast(errorText(e), 'err');
    }
    onboarding = true;
    showServerForm(null, { onboarding: true });
  });

  $('btn-add-server').addEventListener('click', () => showServerForm(null));
  $('btn-add-server-empty').addEventListener('click', () => showServerForm(null));
  $('btn-back').addEventListener('click', showServers);
  $('btn-pick-server').addEventListener('click', () => pickInto('server'));
  $('form-server').addEventListener('submit', saveServer);
  $('btn-server-cancel').addEventListener('click', () => {
    onboarding = false;
    if (serverReturn) showAccounts(serverReturn); else showServers();
  });

  $('f-race').addEventListener('change', () => fillClasses(null));
  $('form-account').addEventListener('submit', saveAccount);
  $('btn-account-cancel').addEventListener('click', () => {
    const s = accountCtx?.server;
    onboarding = false;
    accountCtx = null;
    if (s) showAccounts(s.id); else showServers();
  });

  $('btn-pick-modal').addEventListener('click', async () => {
    const modal = $('modal-path');
    const p = await pickInto('modal');
    if (p && modal._setChosen) modal._setChosen(p);
  });
  $('btn-path-save').addEventListener('click', async () => {
    const modal = $('modal-path');
    const chosen = modal._chosen?.();
    const id = modal._serverId;
    if (!chosen || !id) return;
    try {
      await apply({ op: 'setClientPath', id, path: chosen });
      pathResolve?.(true);
    } catch (e) {
      const err = $('path-error');
      err.textContent = errorText(e);
      err.hidden = false;
    }
  });
  $('modal-path').addEventListener('pointerdown', (e) => {
    if (e.target === $('modal-path')) pathResolve?.(false);
  });
  for (const btn of $('modal-path').querySelectorAll('[data-close]')) {
    btn.addEventListener('click', () => pathResolve?.(false));
  }
}
