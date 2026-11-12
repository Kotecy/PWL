/**
 * Мост к Rust. Один модуль — одна точка входа, чтобы UI не знал,
 * где он живёт: в Tauri (window.__TAURI__) или в браузере (мок).
 *
 * Мок подключается ТОЛЬКО если нативного моста нет, поэтому в собранном
 * приложении этот код не исполняется.
 */

const tauri = window.__TAURI__;
export const isNative = typeof tauri?.core?.invoke === 'function';

let impl;
if (isNative) {
  impl = tauri.core.invoke;
} else {
  const { mockInvoke } = await import('./mock.js');
  impl = mockInvoke;
}

/** Вызов команды ядра. Ошибка приходит как {code, message}. */
export function invoke(cmd, args) {
  return impl(cmd, args);
}

/** Подписка на событие оболочки. Возвращает функцию отписки. */
export async function listen(event, handler) {
  if (!isNative) return () => {};
  return tauri.event.listen(event, (e) => handler(e.payload));
}

/** Сообщение об ошибке, пригодное для человека. */
export function errorText(e) {
  if (!e) return 'Неизвестная ошибка';
  if (typeof e === 'string') return e;
  return e.message || e.code || 'Неизвестная ошибка';
}
