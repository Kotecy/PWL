/**
 * Прогон интерфейса без браузера: реальный index.html + реальные модули ui/src
 * в DOM (linkedom), мост — мок на localStorage. Ловит опечатки в id, ошибки
 * рендера и логики, которые иначе видны только в собранном приложении.
 *
 *   npm i            # в папке tools
 *   node tools/smoke-ui.mjs
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import { parseHTML } from 'linkedom';

const here = path.dirname(fileURLToPath(import.meta.url));
const ui = path.resolve(here, '..', 'ui');
const html = readFileSync(path.join(ui, 'index.html'), 'utf8');
const { window, document } = parseHTML(html);

/* ── минимальные браузерные API, которых нет в linkedom ──── */

const store = new Map();
window.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const proto = window.Element.prototype;
if (!('hidden' in proto)) {
  Object.defineProperty(proto, 'hidden', {
    get() { return this.hasAttribute('hidden'); },
    set(v) { if (v) this.setAttribute('hidden', ''); else this.removeAttribute('hidden'); },
  });
}
proto.getBoundingClientRect = () => ({ top: 0, left: 0, right: 900, bottom: 600, width: 900, height: 600, x: 0, y: 0 });
proto.setPointerCapture = () => {};
proto.releasePointerCapture = () => {};
proto.focus = function focus() { document._active = this; };
proto.blur = function blur() { document._active = null; };
if (!proto.style.setProperty) proto.style.setProperty = () => {};

// linkedom отдаёт value у select/option только на чтение — дописываем сеттеры.
Object.defineProperty(window.HTMLOptionElement.prototype, 'value', {
  get() { return this.getAttribute('value') ?? this.textContent; },
  set(v) { this.setAttribute('value', String(v)); },
  configurable: true,
});
Object.defineProperty(window.HTMLOptionElement.prototype, 'selected', {
  get() { return this.hasAttribute('selected'); },
  set(v) { if (v) this.setAttribute('selected', ''); else this.removeAttribute('selected'); },
  configurable: true,
});
Object.defineProperty(window.HTMLSelectElement.prototype, 'value', {
  get() { const opts = [...this.options]; return (opts.find((o) => o.selected) || opts[0])?.value || ''; },
  set(v) { for (const o of this.options) o.selected = o.value === String(v); },
  configurable: true,
});

Object.defineProperty(window.HTMLElement.prototype, 'clientHeight', { get() { return this.id === 'vlist' ? 440 : 600; }, configurable: true });
Object.defineProperty(window.HTMLElement.prototype, 'scrollTop', { get() { return this._top || 0; }, set(v) { this._top = v; }, configurable: true });

window.innerWidth = 900;
window.innerHeight = 600;
window.requestAnimationFrame = (fn) => setTimeout(() => fn(Date.now()), 0);
window.cancelAnimationFrame = (id) => clearTimeout(id);
window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };

for (const key of ['window', 'document', 'localStorage', 'requestAnimationFrame', 'cancelAnimationFrame',
  'ResizeObserver', 'HTMLElement', 'Element', 'Node', 'Event', 'CustomEvent', 'getComputedStyle']) {
  globalThis[key] = window[key] ?? window;
}
globalThis.window = window;
globalThis.document = document;

/* ── помощники ───────────────────────────────────────────── */

const $ = (id) => document.getElementById(id);
const tick = (ms = 30) => new Promise((r) => setTimeout(r, ms));
let passed = 0;
const fails = [];

function check(name, cond, extra = '') {
  if (cond) { passed += 1; console.log(`  ok   ${name}`); }
  else { fails.push(name); console.log(`  FAIL ${name} ${extra}`); }
}

function fire(node, type, props = {}) {
  const e = new window.Event(type, { bubbles: true, cancelable: true });
  Object.assign(e, props);
  node.dispatchEvent(e);
  return e;
}

const visibleRows = () => [...$('vlist-rows').children].filter((n) => !n.hidden && n.classList.contains('vrow'));
const screen = () => ['welcome', 'servers', 'accounts', 'server-form', 'account-form'].find((s) => !$(`screen-${s}`).hidden);

/* ── прогон ──────────────────────────────────────────────── */

console.log('PWL ui smoke\n');
await import(pathToFileURL(path.join(ui, 'src', 'main.js')).href);
await tick(60);

check('старт: экран серверов', screen() === 'servers', `получен ${screen()}`);
check('карточки серверов отрисованы', $('server-grid').children.length === 3, `${$('server-grid').children.length}`);
check('версия в статусбаре', $('status-version').textContent.includes('превью'));
check('пагинация скрыта при 3 серверах', $('server-pager').hidden);

// вход на сервер
fire($('server-grid').children[0], 'click');
await tick();
check('переход к аккаунтам', screen() === 'accounts');
check('заголовок = имя сервера', $('accounts-title').textContent === 'Sirius', $('accounts-title').textContent);
check('счётчик аккаунтов', $('accounts-count').textContent.startsWith('42'), $('accounts-count').textContent);
check('виртуальный список: высота по всем строкам', $('vlist-sizer').style.height === '1848px', $('vlist-sizer').style.height);
check('в DOM только видимые строки', visibleRows().length > 0 && visibleRows().length < 20, `${visibleRows().length}`);
check('иконка класса из спрайта', visibleRows()[0].querySelector('.class-ic').style.getPropertyValue?.('--i') !== undefined);

// поиск
$('account-search').value = 'основа';
fire($('account-search'), 'input');
await tick();
const found = visibleRows().length;
check('поиск фильтрует', found > 0 && found < 14, `${found}`);
$('account-search').value = '';
fire($('account-search'), 'input');
await tick();

// выбор с клавиатуры
fire($('vlist'), 'keydown', { key: 'ArrowDown' });
await tick();
check('стрелка выделяет строку', visibleRows().some((r) => r.classList.contains('sel')));
check('кнопка «Войти» активна', !$('btn-enter').disabled);

// добавление аккаунта через форму
fire($('btn-add-account'), 'click');
await tick();
check('форма аккаунта открыта', screen() === 'account-form');
check('расы заполнены', $('f-race').options.length === 6, `${$('f-race').options.length}`);
check('классы по расе', $('f-class').options.length === 3, `${$('f-class').options.length}`);
$('f-login').value = 'smoketest';
$('f-password').value = 'secret';
$('f-nick').value = 'Дымовой';
fire($('form-account'), 'submit');
await tick(60);
check('после сохранения — список аккаунтов', screen() === 'accounts');
check('аккаунт добавлен', $('accounts-count').textContent.startsWith('43'), $('accounts-count').textContent);
check('статус сохранения обновлён', ['saving', 'saved'].includes($('status-save').dataset.state), $('status-save').dataset.state);

// пустой логин не проходит
fire($('btn-add-account'), 'click');
await tick();
$('f-login').value = '';
fire($('form-account'), 'submit');
await tick();
check('валидация логина', !$('account-form-error').hidden && screen() === 'account-form');
fire($('btn-account-cancel'), 'click');
await tick();

// удаление с подтверждением
fire($('vlist'), 'keydown', { key: 'End' });
await tick();
fire($('vlist'), 'keydown', { key: 'Delete' });
await tick();
check('диалог подтверждения открыт', !$('modal-confirm').hidden);
const del = [...$('confirm-actions').children].find((b) => b.textContent === 'Удалить');
fire(del, 'click');
await tick(60);
check('аккаунт удалён', $('accounts-count').textContent.startsWith('42'), $('accounts-count').textContent);

// перетаскивание
const before = visibleRows()[0].querySelector('.c-login').textContent;
const row = visibleRows()[0];
fire(row, 'pointerdown', { button: 0, pointerId: 1, clientY: 10 });
fire($('vlist'), 'pointermove', { pointerId: 1, clientY: 120 });
check('линия вставки появилась', !!$('drop-line'));
fire($('vlist'), 'pointerup', { pointerId: 1, clientY: 120 });
await tick(60);
check('порядок изменился', visibleRows()[0].querySelector('.c-login').textContent !== before,
  `${before} → ${visibleRows()[0].querySelector('.c-login').textContent}`);

// тема
fire($('btn-theme'), 'click');
await tick(60);
check('тема переключилась', document.documentElement.dataset.theme === 'light', document.documentElement.dataset.theme);
check('тема сохранена в моке', JSON.parse(store.get('pwl.mock.v1')).settings.theme === 'light');

// настройки
fire($('btn-settings'), 'click');
await tick(40);
check('настройки открыты', !$('modal-settings').hidden);
check('папка данных показана', $('opt-datadir').textContent.includes('PWL'));
fire($('modal-settings').querySelector('[data-close]'), 'click');
await tick();

// сервер без клиента → диалог пути
fire($('btn-back'), 'click');
await tick();
const atlant = [...$('server-grid').children].find((c) => c.querySelector('.s-name').textContent === 'Atlant');
check('предупреждение об отсутствии клиента', !!atlant.querySelector('.s-warn'));
fire(atlant, 'click');
await tick();
fire($('btn-add-account'), 'click');
await tick();
$('f-login').value = 'pathcheck';
$('f-password').value = 'x';
fire($('form-account'), 'submit');
await tick(60);
fire($('btn-enter'), 'click');
await tick(40);
check('без клиента требуется путь', !$('modal-path').hidden);
fire($('btn-pick-modal'), 'click');
await tick(40);
check('путь выбран', !$('btn-path-save').disabled);
fire($('btn-path-save'), 'click');
await tick(80);
check('клиент сохранён, запуск прошёл', $('modal-path').hidden);

// новый сервер
fire($('btn-back'), 'click');
await tick();
fire($('btn-add-server'), 'click');
await tick();
$('f-server-name').value = 'Phoenix';
fire($('form-server'), 'submit');
await tick(60);
check('сервер добавлен', $('server-grid').children.length === 4, `${$('server-grid').children.length}`);

// горячие клавиши
fire(window, 'keydown', { key: 'n', ctrlKey: true, target: document.body });
await tick();
check('Ctrl+N открывает форму сервера', screen() === 'server-form');
fire(window, 'keydown', { key: 'Escape', target: document.body });
await tick();
check('Escape возвращает к списку', screen() === 'servers');

console.log(`\n${passed} проверок пройдено, ${fails.length} провалено`);
if (fails.length) { console.log('Провалы:\n  ' + fails.join('\n  ')); process.exit(1); }
