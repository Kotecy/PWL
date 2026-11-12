/**
 * DOM-хелперы, тосты, контекстное меню, модальные окна.
 * Разметка создаётся через createElement — никакого innerHTML с данными
 * пользователя (CSP + защита от подстановки разметки в ник/комментарий).
 */

export const $ = (id) => document.getElementById(id);

export function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

/** Иконка из SVG-спрайта в index.html. */
export function icon(name, cls = 'ic') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', cls);
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#${name}`);
  svg.append(use);
  return svg;
}

export function button(cls, label, iconName, onClick) {
  const b = el('button', cls);
  b.type = 'button';
  if (iconName) b.append(icon(iconName));
  if (label) b.append(el('span', null, label));
  if (onClick) b.addEventListener('click', onClick);
  return b;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

/* ── тосты ───────────────────────────────────────────────── */

export function toast(text, kind = 'info', ms = 3200) {
  const host = $('toasts');
  const node = el('div', `toast ${kind === 'info' ? '' : kind}`);
  node.append(icon(kind === 'err' ? 'i-warn' : kind === 'ok' ? 'i-check' : 'i-shield'));
  node.append(el('span', null, text));
  host.append(node);
  const drop = () => {
    node.classList.add('out');
    setTimeout(() => node.remove(), 160);
  };
  setTimeout(drop, ms);
  node.addEventListener('click', drop);
  while (host.children.length > 4) host.firstChild.remove();
}

/* ── контекстное меню ────────────────────────────────────── */

let menuCleanup = null;

export function closeMenu() {
  if (menuCleanup) { menuCleanup(); menuCleanup = null; }
}

/** items: [{label, icon, danger, onClick} | 'sep'] */
export function openMenu(x, y, items) {
  closeMenu();
  const menu = $('menu');
  clear(menu);
  for (const item of items) {
    if (item === 'sep') { menu.append(el('div', 'menu-sep')); continue; }
    const b = el('button', `menu-item${item.danger ? ' danger' : ''}`);
    b.type = 'button';
    b.append(icon(item.icon || 'i-right'));
    b.append(el('span', null, item.label));
    b.addEventListener('click', () => { closeMenu(); item.onClick(); });
    menu.append(b);
  }
  menu.hidden = false;

  const r = menu.getBoundingClientRect();
  const left = Math.min(x, window.innerWidth - r.width - 8);
  const top = Math.min(y, window.innerHeight - r.height - 8);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;

  const onDown = (e) => { if (!menu.contains(e.target)) closeMenu(); };
  const onKey = (e) => { if (e.key === 'Escape') closeMenu(); };
  window.addEventListener('pointerdown', onDown, true);
  window.addEventListener('keydown', onKey, true);
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
  menuCleanup = () => {
    menu.hidden = true;
    window.removeEventListener('pointerdown', onDown, true);
    window.removeEventListener('keydown', onKey, true);
    window.removeEventListener('blur', closeMenu);
    window.removeEventListener('resize', closeMenu);
  };
}

/* ── модальные окна ──────────────────────────────────────── */

const openModals = [];

export function openModal(id) {
  const node = $(id);
  node.hidden = false;
  openModals.push(node);
  // Фокус — в поле ввода, а при его отсутствии на саму карточку: кнопка «×» с кольцом фокуса при открытии выглядит как случайное выделение.
  const target = node.querySelector('input:not([type="checkbox"]), select') || node.querySelector('.modal');
  if (target) {
    if (!target.matches('input, select')) target.tabIndex = -1;
    target.focus({ preventScroll: true });
  }
  return node;
}

export function closeModal(node) {
  const target = typeof node === 'string' ? $(node) : node || openModals[openModals.length - 1];
  if (!target) return;
  target.hidden = true;
  const i = openModals.indexOf(target);
  if (i >= 0) openModals.splice(i, 1);
}

export function anyModalOpen() {
  return openModals.length > 0;
}

/** Кнопки «закрыть» внутри модалок. */
export function wireModalDismiss() {
  for (const overlay of document.querySelectorAll('.overlay')) {
    overlay.addEventListener('pointerdown', (e) => {
      if (e.target === overlay) closeModal(overlay);
    });
    for (const btn of overlay.querySelectorAll('[data-close]')) {
      btn.addEventListener('click', () => closeModal(overlay));
    }
  }
}

/**
 * Диалог подтверждения. actions: [{label, cls, value}]
 * Возвращает Promise с value выбранной кнопки или null при отмене.
 */
export function confirmDialog({ title, text, actions }) {
  $('confirm-title').textContent = title;
  $('confirm-text').textContent = text;
  const host = $('confirm-actions');
  clear(host);
  return new Promise((resolve) => {
    const node = openModal('modal-confirm');
    const done = (value) => { closeModal(node); resolve(value); };
    for (const a of actions) {
      host.append(button(a.cls || 'btn quiet', a.label, null, () => done(a.value)));
    }
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); done(null); }
    };
    node.addEventListener('keydown', onKey, { once: true });
  });
}

/* ── прочее ──────────────────────────────────────────────── */

export function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

export function debounce(fn, ms) {
  let timer = 0;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
