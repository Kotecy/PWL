/**
 * Мок ядра для превью в браузере. Повторяет контракт pwl-core
 * (Bootstrap / Op / Change) и хранит данные в localStorage.
 *
 * Только для разработки: в приложении Tauri-мост есть, и этот файл не грузится.
 */

const KEY = 'pwl.mock.v1';

const CLASSES = [
  ['var', 'Воин', 'Люди'], ['mag', 'Маг', 'Люди'], ['gan', 'Стрелок', 'Люди'],
  ['tank', 'Оборотень', 'Зооморфы'], ['mk', 'Странник', 'Зооморфы'], ['dru', 'Друид', 'Зооморфы'],
  ['pal', 'Паладин', 'Сиды'], ['prist', 'Жрец', 'Сиды'], ['luk', 'Лучник', 'Сиды'],
  ['sham', 'Шаман', 'Амфибии'], ['sin', 'Убийца', 'Амфибии'], ['bard', 'Бард', 'Амфибии'],
  ['sik', 'Страж', 'Древние'], ['mist', 'Мистик', 'Древние'], ['dk', 'Дух крови', 'Древние'],
  ['gost', 'Призрак', 'Тени'], ['kosa', 'Жнец', 'Тени'], ['lazur', 'Лазурный дракон', 'Тени'],
].map(([slug, name, race], i) => ({ slug, name, race, spriteIndex: i }));

const RACES = [...new Set(CLASSES.map((c) => c.race))]
  .map((name) => ({ name, classes: CLASSES.filter((c) => c.race === name).map((c) => c.slug) }));

const uid = () => Math.random().toString(16).slice(2, 14);
const hash = (s) => { let h = 2166136261; for (const ch of s) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
const clone = (v) => JSON.parse(JSON.stringify(v));
const fail = (code, message) => { throw { code, message }; };

function account(draft) {
  const info = CLASSES.find((c) => c.slug === draft.class) || CLASSES[0];
  return {
    id: uid(), login: draft.login, nick: draft.nick || draft.login,
    autoRole: !!draft.autoRole, class: info.slug, comment: draft.comment || '',
    hasPassword: !!draft.password, spriteIndex: info.spriteIndex,
  };
}

const view = (s) => ({ id: s.id, name: s.name, clientPath: s.clientPath, art: hash(s.id) % 8, glyph: hash(s.id) % 20, accounts: s.accounts.map((a) => ({ ...a })) });
const meta = (s) => ({ id: s.id, name: s.name, clientPath: s.clientPath, art: hash(s.id) % 8, glyph: hash(s.id) % 20, accountCount: s.accounts.length });

function seed() {
  const nicks = ['Shadowblade', 'Астрель', 'NightFury', 'Вельмира', 'Ironheart', 'Луноликий', 'Stormrage', 'Элианор', 'Frostwind', 'Дракоша', 'Silentkill', 'Мираэль', 'Bloodmoon', 'Светонос', 'Windwalker', 'Тенька', 'Hellfire', 'Аврора', 'Stonefist', 'Нимфа', 'Dawnbreaker', 'Вестник', 'Soulreaper', 'Заряна'];
  const mk = (name, count, clientPath) => ({
    id: uid(), name, clientPath,
    accounts: Array.from({ length: count }, (_, i) => account({
      login: `player${i + 1}`, password: 'demo', nick: nicks[i % nicks.length] + (i >= nicks.length ? ` ${Math.floor(i / nicks.length) + 1}` : ''),
      autoRole: i % 5 === 0, class: CLASSES[(i * 5) % CLASSES.length].slug,
      comment: i % 4 === 0 ? 'основа' : i % 7 === 0 ? 'твин для БСО' : '',
    })),
  });
  return {
    schema: 1,
    settings: { theme: 'dark', minimizeToTray: false, accepted: true, confirmDelete: true },
    servers: [
      mk('Sirius', 42, 'C:\\Perfect World\\element\\elementclient.exe'),
      mk('Vega', 7, 'C:\\PW Vega\\element\\elementclient.exe'),
      mk('Atlant', 0, null),
    ],
  };
}

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* повреждённый мок — начинаем заново */ }
  const fresh = seed();
  save(fresh);
  return fresh;
}

function save(s) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* приватный режим */ }
}

let db = load();
const server = (id) => db.servers.find((s) => s.id === id) || fail('not_found', 'Сервер не найден');

function run(op) {
  switch (op.op) {
    case 'addServer': {
      const name = (op.name || '').trim() || fail('validation', 'Введите название сервера');
      const s = { id: uid(), name, clientPath: op.clientPath || null, accounts: [] };
      db.servers.push(s);
      return { kind: 'serverAdded', server: view(s) };
    }
    case 'renameServer': {
      const s = server(op.id);
      s.name = (op.name || '').trim() || fail('validation', 'Введите название сервера');
      return { kind: 'serverUpdated', meta: meta(s) };
    }
    case 'setClientPath': {
      const s = server(op.id);
      s.clientPath = op.path || null;
      return { kind: 'serverUpdated', meta: meta(s) };
    }
    case 'deleteServer': {
      db.servers = db.servers.filter((s) => s.id !== op.id);
      return { kind: 'serverRemoved', id: op.id };
    }
    case 'addAccount': {
      const s = server(op.serverId);
      if (!op.draft?.login?.trim()) fail('validation', 'Введите логин');
      const a = account(op.draft);
      s.accounts.push(a);
      return { kind: 'accountAdded', serverId: s.id, account: a };
    }
    case 'updateAccount': {
      const s = server(op.serverId);
      const i = s.accounts.findIndex((a) => a.id === op.id);
      if (i < 0) fail('not_found', 'Аккаунт не найден');
      const next = account(op.draft);
      next.id = op.id;
      next.hasPassword = op.draft.password ? true : s.accounts[i].hasPassword;
      s.accounts[i] = next;
      return { kind: 'accountUpdated', serverId: s.id, account: next };
    }
    case 'deleteAccount': {
      const s = server(op.serverId);
      s.accounts = s.accounts.filter((a) => a.id !== op.id);
      return { kind: 'accountRemoved', serverId: s.id, id: op.id };
    }
    case 'moveAccount': {
      const s = server(op.serverId);
      const from = s.accounts.findIndex((a) => a.id === op.id);
      if (from < 0) fail('not_found', 'Аккаунт не найден');
      const [a] = s.accounts.splice(from, 1);
      const to = Math.max(0, Math.min(op.to, s.accounts.length));
      s.accounts.splice(to, 0, a);
      return { kind: 'accountMoved', serverId: s.id, id: op.id, to };
    }
    case 'setSettings': {
      db.settings = { ...db.settings, ...Object.fromEntries(Object.entries(op.patch || {}).filter(([, v]) => v !== null && v !== undefined)) };
      return { kind: 'settings', settings: clone(db.settings) };
    }
    default:
      fail('unknown_op', `Неизвестная операция: ${op.op}`);
  }
}

export async function mockInvoke(cmd, args = {}) {
  // Как и настоящий IPC: через границу уходят копии, а не ссылки на базу мока.
  return clone(await handle(cmd, args));
}

async function handle(cmd, args) {
  switch (cmd) {
    case 'bootstrap':
      return {
        version: '1.0.0-preview', schema: db.schema, settings: clone(db.settings),
        servers: db.servers.map(view), races: RACES, classes: CLASSES,
        secretsSecure: false, migration: null,
      };
    case 'apply': {
      const change = run(args.op);
      save(db);
      return change;
    }
    case 'apply_batch': {
      const changes = args.ops.map(run);
      save(db);
      return changes;
    }
    case 'launch': {
      const s = server(args.serverId);
      if (!s.clientPath) fail('no_client', 'Не указан путь к elementclient.exe');
      if (!s.accounts.some((a) => a.id === args.accountId)) fail('not_found', 'Аккаунт не найден');
      return { pid: 4000 + Math.floor(Math.random() * 1000), exe: s.clientPath };
    }
    case 'pick_client':
      return 'C:\\Perfect World\\element\\elementclient.exe';
    case 'data_dir':
      return '%APPDATA%\\PWL  (демо в браузере)';
    case 'open_data_dir':
      return null;
    case 'flush':
      save(db);
      return null;
    case 'win_minimize':
    case 'win_toggle_maximize':
    case 'win_close':
    case 'quit':
      return null;
    default:
      fail('unknown_command', `Нет такой команды: ${cmd}`);
  }
}
