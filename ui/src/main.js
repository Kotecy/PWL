/**
 * Точка входа: загрузка состояния, тема, оконные кнопки, настройки, горячие клавиши.
 */
import { data, init, apply, on } from './store.js';
import { invoke, isNative, errorText } from './bridge.js';
import { $, toast, openModal, anyModalOpen, wireModalDismiss, closeMenu } from './ui.js';
import { initServers } from './servers.js';
import { initAccounts, currentServerId } from './accounts.js';
import {
  initScreens, showWelcome, showServers, showServerForm, showAccountForm, currentScreen,
} from './screens.js';
import { serverById } from './store.js';

/* ── тема ────────────────────────────────────────────────── */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $('btn-theme');
  btn.querySelector('use').setAttribute('href', theme === 'dark' ? '#i-sun' : '#i-moon');
  btn.title = theme === 'dark' ? 'Светлая тема (Ctrl+T)' : 'Тёмная тема (Ctrl+T)';
}

const prefersReducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/**
 * Смена темы с волной: новая тема раскрывается кругом из центра кнопки до самого дальнего угла окна.
 * Без поддержки View Transitions (или при reduce-motion) тема просто переключается.
 */
async function swapTheme(theme, origin) {
  if (!document.startViewTransition || prefersReducedMotion()) { applyTheme(theme); return; }
  const { x, y } = origin;
  const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const transition = document.startViewTransition(() => applyTheme(theme));
  try {
    await transition.ready;
    document.documentElement.animate(
      { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
      { duration: 620, easing: 'cubic-bezier(.4, 0, .2, 1)', pseudoElement: '::view-transition-new(root)' },
    );
    $('btn-theme').firstElementChild.animate(
      [{ transform: 'rotate(-90deg) scale(.6)' }, { transform: 'none' }],
      { duration: 420, easing: 'cubic-bezier(.2, .8, .2, 1)' },
    );
    await transition.finished;
  } catch { /* переход прерван повторным нажатием — тема уже применена */ }
}

function buttonCenter() {
  const r = $('btn-theme').getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

/** Тема, к которой идёт текущая смена. Пока она задана, событие 'settings' тему не трогает, иначе оно сорвало бы анимацию. */
let pendingTheme = null;

async function toggleTheme() {
  const prev = pendingTheme ?? document.documentElement.dataset.theme;
  const next = prev === 'dark' ? 'light' : 'dark';
  pendingTheme = next;
  const swap = swapTheme(next, buttonCenter()); // не ждём IPC
  try {
    await apply({ op: 'setSettings', patch: { theme: next } });
  } catch (e) {
    pendingTheme = null;
    applyTheme(prev);
    toast(errorText(e), 'err');
    return;
  }
  await swap;
  if (pendingTheme === next) pendingTheme = null;
}

/* ── настройки ───────────────────────────────────────────── */

function syncSettings() {
  $('opt-tray').checked = data.settings.minimizeToTray;
  $('opt-confirm').checked = data.settings.confirmDelete;
  $('opt-secrets').textContent = data.secretsSecure
    ? 'Пароли зашифрованы средствами Windows (DPAPI)'
    : 'Пароли хранятся локально; шифрование доступно на Windows';
  $('status-secure').hidden = !data.secretsSecure;
}

async function openSettings() {
  syncSettings();
  openModal('modal-settings');
  try {
    $('opt-datadir').textContent = await invoke('data_dir');
  } catch {
    $('opt-datadir').textContent = 'недоступно';
  }
}

async function patchSettings(patch) {
  try {
    await apply({ op: 'setSettings', patch });
  } catch (e) {
    toast(errorText(e), 'err');
    syncSettings();
  }
}

/* ── оконные кнопки ──────────────────────────────────────── */

function windowButton(id, command) {
  $(id).addEventListener('click', async () => {
    if (!isNative) { toast('Оконные кнопки работают в приложении, не в браузере'); return; }
    try {
      await invoke(command);
    } catch (e) {
      toast(errorText(e), 'err');
    }
  });
}

/* ── горячие клавиши ─────────────────────────────────────── */

function hotkeys(e) {
  // Браузерные сочетания в приложении не нужны: перезагрузка сбросила бы экран, печать и сохранение страницы бессмысленны.
  if (e.key === 'F5' || e.key === 'F12' || ((e.ctrlKey || e.metaKey) && ['r', 'p', 's', 'u'].includes(e.key.toLowerCase()))) {
    e.preventDefault();
    return;
  }
  const ctrl = e.ctrlKey || e.metaKey;
  const typing = !!e.target?.matches?.('input, select, textarea');

  if (ctrl && e.key.toLowerCase() === 't') { e.preventDefault(); toggleTheme(); return; }
  if (ctrl && e.key.toLowerCase() === 'f') {
    const screen = currentScreen();
    if (screen === 'servers' || screen === 'accounts') {
      e.preventDefault();
      $(screen === 'servers' ? 'server-search' : 'account-search').focus();
    }
    return;
  }
  if (ctrl && e.key.toLowerCase() === 'n') {
    const screen = currentScreen();
    if (screen === 'servers') { e.preventDefault(); showServerForm(null); }
    else if (screen === 'accounts') { e.preventDefault(); showAccountForm(serverById(currentServerId()), null); }
    return;
  }
  if (e.key === 'Escape') {
    closeMenu();
    if (anyModalOpen()) {
      const open = [...document.querySelectorAll('.overlay')].find((o) => !o.hidden);
      open?.querySelector('[data-close]')?.click();
      return;
    }
    if (typing) { e.target.blur(); return; }
    const screen = currentScreen();
    if (screen === 'accounts') showServers();
    else if (screen === 'server-form') $('btn-server-cancel').click();
    else if (screen === 'account-form') $('btn-account-cancel').click();
  }
}

/* ── старт ───────────────────────────────────────────────── */

async function boot() {
  wireModalDismiss();
  initScreens();
  initServers();
  initAccounts();

  $('btn-theme').addEventListener('click', toggleTheme);
  $('btn-settings').addEventListener('click', openSettings);
  windowButton('btn-min', 'win_minimize');
  windowButton('btn-max', 'win_toggle_maximize');
  windowButton('btn-close', 'win_close');
  $('btn-open-datadir').addEventListener('click', async () => {
    if (!isNative) { toast('Папка открывается в приложении, не в браузере'); return; }
    try {
      await invoke('open_data_dir');
    } catch (e) {
      toast(errorText(e), 'err');
    }
  });
  $('opt-tray').addEventListener('change', (e) => patchSettings({ minimizeToTray: e.target.checked }));
  $('opt-confirm').addEventListener('change', (e) => patchSettings({ confirmDelete: e.target.checked }));
  window.addEventListener('keydown', hotkeys);
  // Стандартное меню браузера (назад, обновить, печать) в приложении не нужно; в полях ввода оставляем — там полезны вставка и копирование.
  window.addEventListener('contextmenu', (e) => {
    if (!e.target?.closest?.('input, textarea')) e.preventDefault();
  });

  on('settings', (settings) => {
    if (pendingTheme === null) applyTheme(settings.theme);
    syncSettings();
  });

  await init();

  applyTheme(data.settings.theme);
  syncSettings();
  $('status-version').textContent = isNative ? `v${data.version}` : `v${data.version} · превью в браузере`;

  const m = data.migration;
  if (m) {
    toast(`Данные перенесены: серверов ${m.servers}, аккаунтов ${m.accounts}`, 'ok', 7000);
    for (const w of m.warnings || []) toast(w, 'info', 7000);
  }

  if (!data.settings.accepted) showWelcome();
  else showServers();
}

boot().catch((e) => {
  toast(`Не удалось запустить: ${errorText(e)}`, 'err', 10000);
  const node = $('status-save');
  node.dataset.state = 'error';
  node.textContent = 'Ошибка запуска';
});
