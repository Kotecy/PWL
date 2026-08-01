const sunIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.1" fill="currentColor" stroke="none"/><path d="M12 1.6v2.4M12 20v2.4M1.6 12H4M20 12h2.4M4.4 4.4l1.7 1.7M17.9 17.9l1.7 1.7M19.6 4.4l-1.7 1.7M6.1 17.9l-1.7 1.7" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/></svg>`;
const moonIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.1A8.3 8.3 0 0 1 8.9 3.8 8.4 8.4 0 1 0 20.2 15.1Z"/></svg>`;

const RACES = {
  'Люди': ['Воин', 'Маг', 'Стрелок'],
  'Зооморфы': ['Оборотень', 'Странник', 'Друид'],
  'Сиды': ['Паладин', 'Жрец', 'Лучник'],
  'Амфибии': ['Шаман', 'Убийца', 'Бард'],
  'Древние': ['Страж', 'Мистик', 'Дух крови'],
  'Тени': ['Призрак', 'Жнец', 'Лазурный дракон'],
};

const root = document.documentElement;
const themeButton = document.getElementById('themeButton');
let currentTheme = 'dark';

const screens = {
  welcome: document.getElementById('welcomeScreen'),
  workspace: document.getElementById('workspaceScreen'),
  server: document.getElementById('serverScreen'),
  account: document.getElementById('accountScreen'),
};

const servers = [];
let clientPath = '';
let currentServer = null;
let selectedAccount = null;
let editingAccountIndex = null;
let wizardMode = false;
let accountFromServer = false;
let serverMenuServer = null;

function setWizardMode(enabled) {
  wizardMode = enabled;
  document.getElementById('serverKicker').hidden = !enabled;
  document.getElementById('accountKicker').hidden = !enabled;
}

function setTheme(theme) {
  currentTheme = theme === 'light' ? 'light' : 'dark';
  root.dataset.theme = currentTheme;
  themeButton.innerHTML = currentTheme === 'dark' ? sunIcon : moonIcon;
  themeButton.setAttribute('aria-label', currentTheme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
}

function showScreen(name) {
  for (const key of Object.keys(screens)) {
    screens[key].hidden = key !== name;
  }
}

function fillRaces() {
  const raceSelect = document.getElementById('raceSelect');
  raceSelect.innerHTML = '';
  for (const race of Object.keys(RACES)) {
    const option = document.createElement('option');
    option.value = race;
    option.textContent = race;
    raceSelect.appendChild(option);
  }
}

function fillClasses() {
  const race = document.getElementById('raceSelect').value;
  const classSelect = document.getElementById('classSelect');
  classSelect.innerHTML = '';
  for (const cls of RACES[race]) {
    const option = document.createElement('option');
    option.value = cls;
    option.textContent = cls;
    classSelect.appendChild(option);
  }
}

const CLASS_ICONS = {
  'Воин': 'var', 'Маг': 'mag', 'Стрелок': 'gan', 'Оборотень': 'tank', 'Странник': 'mk', 'Друид': 'dru',
  'Паладин': 'pal', 'Жрец': 'prist', 'Лучник': 'luk', 'Шаман': 'sham', 'Убийца': 'sin', 'Бард': 'bard',
  'Страж': 'sik', 'Мистик': 'mist', 'Дух крови': 'dk', 'Призрак': 'gost', 'Лазурный дракон': 'lazur',
  'Жнец': 'kosa',
};

const SERVER_ART = ['art-gold', 'art-azure', 'art-violet', 'art-emerald', 'art-crimson'];

const SERVER_GLYPHS = [
  `<svg viewBox="0 0 24 24"><path d="M12 3.5 13.6 10.4 20.5 12 13.6 13.6 12 20.5 10.4 13.6 3.5 12 10.4 10.4Z"/></svg>`,
  `<svg viewBox="0 0 24 24"><circle cx="8.5" cy="15.5" r="4.5"/><path d="M11.8 12.2 20 4"/><path d="m16.5 7.5 3 3"/></svg>`,
  `<svg viewBox="0 0 24 24"><path d="M4.5 8.5 8.5 12 12 6l3.5 6 4-3.5V17h-15Z"/></svg>`,
  `<svg viewBox="0 0 24 24"><path d="M19 14.5A7.5 7.5 0 0 1 9.5 5 7.5 7.5 0 1 0 19 14.5Z"/></svg>`,
  `<svg viewBox="0 0 24 24"><path d="M12 3c1.4 2.6 4.1 4 4.1 7a4.1 4.1 0 0 1-8.2 0c0-3 2.7-4.4 4.1-7Z"/><path d="M12 21a4.5 4.5 0 0 0 4.5-4.5c0-2.1-1.5-3.5-3-4.8"/></svg>`,
  `<svg viewBox="0 0 24 24"><path d="M7.5 5h9l4 5.5L12 20 3.5 10.5Z"/><path d="M3.5 10.5h17M12 20l-3.2-9.5M12 20l3.2-9.5"/></svg>`,
  `<svg viewBox="0 0 24 24"><path d="M12 21v-4M12 4v3M4 12h3M17 12h3"/><circle cx="12" cy="12" r="5.5"/><circle cx="12" cy="12" r="1.6"/></svg>`,
];

function shuffleGlyphs() {
  const copy = [...SERVER_GLYPHS];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

const SERVERS_PER_PAGE = 4;
let serverPage = 0;
let pendingClientPath = '';
let pathModalServer = null;

function renderWorkspace() {
  const emptyCard = document.getElementById('emptyCard');
  const serverList = document.getElementById('serverList');
  if (servers.length === 0) {
    emptyCard.hidden = false;
    serverList.hidden = true;
    renderPagination();
    return;
  }
  emptyCard.hidden = true;
  serverList.hidden = false;
  const pageCount = Math.ceil(servers.length / SERVERS_PER_PAGE);
  if (serverPage >= pageCount) serverPage = pageCount - 1;
  const start = serverPage * SERVERS_PER_PAGE;
  const pageServers = servers.slice(start, start + SERVERS_PER_PAGE);
  const cards = document.getElementById('serverCards');
  cards.innerHTML = '';
  const glyphs = shuffleGlyphs();
  pageServers.forEach((server, i) => {
    const index = start + i;
    const card = document.createElement('section');
    card.className = `server-card ${SERVER_ART[index % SERVER_ART.length]}`;
    const noPath = !server.path;
    card.innerHTML = `
      <span class="server-card-art" aria-hidden="true">
        ${glyphs[i % glyphs.length]}
        <span class="server-card-status"></span>
      </span>
      <div class="server-card-body">
        <div class="server-card-name-row">
          <div class="server-card-name">${server.name}</div>
          ${noPath ? '<button class="server-card-alert" type="button" aria-label="Нет пути к Elementclient" title="Путь к Elementclient не задан"><svg viewBox="0 0 16 16"><path d="M3 3l10 10M13 3L3 13"/></svg></button>' : ''}
        </div>
        <div class="server-card-meta">${server.accounts ? server.accounts.length : 0} аккаунтов</div>
      </div>
      <span class="server-card-chevron" aria-hidden="true"><svg viewBox="0 0 16 16"><path d="M6 3.5 10.5 8 6 12.5"/></svg></span>`;
    card.addEventListener('click', () => openServerAccounts(server));
    card.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      if (noPath) {
        serverMenuServer = server;
        openServerContextMenu(event.clientX, event.clientY);
      }
    });
    card.querySelector('.server-card-alert')?.addEventListener('click', (event) => {
      event.stopPropagation();
      pathModalServer = server;
      openPathModal();
    });
    cards.appendChild(card);
  });
  renderPagination();
}

function renderPagination() {
  const nav = document.getElementById('serverPagination');
  const pageCount = Math.ceil(servers.length / SERVERS_PER_PAGE);
  nav.hidden = pageCount <= 1;
  nav.innerHTML = '';
  for (let p = 0; p < pageCount; p++) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'page-btn' + (p === serverPage ? ' active' : '');
    btn.textContent = String(p + 1);
    btn.addEventListener('click', () => {
      serverPage = p;
      renderWorkspace();
    });
    nav.appendChild(btn);
  }
}

function openServerAccounts(server) {
  currentServer = server;
  selectedAccount = null;
  showScreen('workspace');
  document.getElementById('serverList').hidden = true;
  document.getElementById('accountsView').hidden = false;
  document.getElementById('accountsServerName').textContent = server.name;
  renderAccounts();
}

function classIcon(className) {
  const file = CLASS_ICONS[className];
  if (!file) return '';
  return `<img class="class-icon-img" src="class/${file}.webp" alt="" width="26" height="26" loading="lazy">`;
}

function renderAccounts() {
  const tbody = document.getElementById('accountsBody');
  const accounts = currentServer ? currentServer.accounts : [];
  tbody.innerHTML = '';
  for (const [index, account] of accounts.entries()) {
    const tr = document.createElement('tr');
    tr.dataset.index = index;
    if (selectedAccount === index) tr.classList.add('selected');
    tr.innerHTML = `
      <td class="acc-grip"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 4.5h6M5 8h6M5 11.5h6"/></svg></td>
      <td class="acc-class"><span class="class-icon" aria-hidden="true">${classIcon(account.class)}</span></td>
      <td>${account.nick}</td>
      <td>${account.login}</td>
      <td>${currentServer ? currentServer.name : ''}</td>
      <td>${account.comment || ''}</td>`;
    tr.addEventListener('click', () => {
      selectedAccount = currentRowIndex(tr);
      renderAccounts();
    });
    tr.addEventListener('dblclick', () => enterAccount());
    tr.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      selectedAccount = currentRowIndex(tr);
      renderAccounts();
      openContextMenu(event.clientX, event.clientY);
    });
    tr.addEventListener('pointerdown', (event) => startRowDrag(event, tr, currentRowIndex(tr)));
    tbody.appendChild(tr);
  }
  document.getElementById('enterButton').disabled = selectedAccount === null;
}

function currentRowIndex(row) {
  return Array.prototype.indexOf.call(row.parentElement.children, row);
}

let dragState = null;

function startRowDrag(event, row, index) {
  if (event.button !== 0) return;
  event.preventDefault();
  const tbody = row.parentElement;
  const rows = Array.from(tbody.children);
  dragState = {
    row,
    index,
    startY: event.clientY,
    lastIndex: index,
    tbody,
    rows,
    pointerId: event.pointerId,
    grabOffsetY: event.clientY - row.getBoundingClientRect().top,
    transformY: 0,
  };
  row.classList.add('dragging');
  row.style.transition = 'none';
  row.style.zIndex = 10;
  document.addEventListener('pointermove', onRowDragMove);
  document.addEventListener('pointerup', endRowDrag);
  document.addEventListener('pointercancel', endRowDrag);
}

function onRowDragMove(event) {
  if (!dragState) return;
  const { row } = dragState;
  const rectTop = row.getBoundingClientRect().top;
  const naturalTop = rectTop - dragState.transformY;
  const targetTransformY = (event.clientY - dragState.grabOffsetY) - naturalTop;
  dragState.transformY = targetTransformY;
  row.style.transform = `translateY(${targetTransformY}px)`;
  autoScrollAccounts(event);

  const rows = Array.from(dragState.tbody.children);
  const rowHeight = rows[0] ? rows[0].offsetHeight : 40;
  const targetIndex = dragState.lastIndex + Math.round(targetTransformY / rowHeight);
  const clamped = Math.max(0, Math.min(rows.length - 1, targetIndex));
  if (clamped !== dragState.lastIndex) {
    reorderRows(clamped);
  }
}

function reorderRows(targetIndex) {
  const { row, tbody, rows } = dragState;
  const fromIndex = dragState.lastIndex;
  const accounts = currentServer ? currentServer.accounts : [];

  const before = new Map();
  for (const r of rows) before.set(r, r.getBoundingClientRect().top);

  const [moved] = accounts.splice(fromIndex, 1);
  accounts.splice(targetIndex, 0, moved);
  selectedAccount = targetIndex;
  document.getElementById('enterButton').disabled = false;

  const ref = rows[targetIndex > fromIndex ? targetIndex + 1 : targetIndex];
  tbody.insertBefore(row, ref || null);

  const newRows = Array.from(tbody.children);
  void tbody.offsetHeight;
  for (const r of newRows) {
    if (r === row) continue;
    const delta = (before.get(r) ?? 0) - r.getBoundingClientRect().top;
    if (Math.abs(delta) > 0.5) {
      r.style.transition = 'none';
      r.style.transform = `translateY(${delta}px)`;
    }
  }
  void tbody.offsetHeight;
  for (const r of newRows) {
    if (r === row) continue;
    r.style.transition = 'transform .25s cubic-bezier(.2,.8,.3,1)';
    r.style.transform = '';
  }

  dragState.lastIndex = targetIndex;
  dragState.rows = newRows;
}

function autoScrollAccounts(event) {
  const wrap = document.getElementById('accountsTableWrap');
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect();
  const edge = 40;
  if (event.clientY < rect.top + edge) wrap.scrollTop -= 10;
  else if (event.clientY > rect.bottom - edge) wrap.scrollTop += 10;
}

function endRowDrag() {
  if (!dragState) return;
  const { row, tbody } = dragState;
  row.classList.remove('dragging');
  row.style.transition = 'transform .2s ease';
  row.style.transform = '';
  row.style.zIndex = '';
  document.removeEventListener('pointermove', onRowDragMove);
  document.removeEventListener('pointerup', endRowDrag);
  document.removeEventListener('pointercancel', endRowDrag);
  dragState = null;
  void tbody.offsetHeight;
}

function openContextMenu(x, y) {
  const menu = document.getElementById('contextMenu');
  menu.hidden = false;
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
}

function hideContextMenu() {
  document.getElementById('contextMenu').hidden = true;
}

function openServerContextMenu(x, y) {
  const menu = document.getElementById('serverContextMenu');
  menu.hidden = false;
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
}

function hideServerContextMenu() {
  document.getElementById('serverContextMenu').hidden = true;
  serverMenuServer = null;
}

function openPathModal() {
  if (!pathModalServer) return;
  pendingClientPath = '';
  document.getElementById('pathStatus').hidden = true;
  document.getElementById('pathError').hidden = true;
  document.getElementById('pathSaveButton').disabled = true;
  document.getElementById('pathModalTitle').textContent = `«${pathModalServer.name}» — нужен Elementclient`;
  document.getElementById('pathModal').hidden = false;
}

function closePathModal() {
  document.getElementById('pathModal').hidden = true;
  pathModalServer = null;
  pendingClientPath = '';
}

function resetPathStatus() {
  pendingClientPath = '';
  document.getElementById('pathStatus').hidden = true;
  document.getElementById('pathSaveButton').disabled = true;
}

async function enterAccount() {
  if (currentServer && !currentServer.path) {
    pathModalServer = currentServer;
    openPathModal();
    return;
  }
  if (currentServer && selectedAccount !== null) {
    const res = await window.pywebview.api.launch(currentServer.name, selectedAccount);
    if (!res.ok) {
      pathModalServer = currentServer;
      openPathModal();
    }
  }
}

document.getElementById('accountsBackButton').addEventListener('click', () => {
  document.getElementById('accountsView').hidden = true;
  document.getElementById('serverList').hidden = false;
});

document.getElementById('enterButton').addEventListener('click', () => {
  if (selectedAccount !== null) {
    enterAccount();
  }
});

function openAccountForm(editIndex) {
  resetAccountForm();
  setWizardMode(false);
  accountFromServer = true;
  editingAccountIndex = editIndex;
  if (editIndex !== null && currentServer) {
    const acc = currentServer.accounts[editIndex];
    document.getElementById('accountLogin').value = acc.login || '';
    document.getElementById('accountPassword').value = acc.password || '';
    document.getElementById('characterNick').value = acc.nick || '';
    document.getElementById('autoRole').checked = !!acc.auto;
    document.getElementById('raceSelect').value = raceOf(acc.class);
    fillClasses();
    document.getElementById('classSelect').value = acc.class;
    document.getElementById('accountComment').value = acc.comment || '';
    document.getElementById('commentField').hidden = false;
    document.getElementById('accountBackButton').textContent = 'Отмена';
  }
  showScreen('account');
}

function raceOf(cls) {
  for (const race of Object.keys(RACES)) {
    if (RACES[race].includes(cls)) return race;
  }
  return Object.keys(RACES)[0];
}

document.getElementById('addAccountButton').addEventListener('click', () => {
  openAccountForm(null);
});

document.getElementById('contextEditButton').addEventListener('click', () => {
  hideContextMenu();
  openAccountForm(selectedAccount);
});

document.getElementById('contextDeleteButton').addEventListener('click', async () => {
  hideContextMenu();
  if (currentServer && selectedAccount !== null) {
    await window.pywebview.api.delete_account(currentServer.name, selectedAccount);
    currentServer.accounts.splice(selectedAccount, 1);
    selectedAccount = null;
    renderAccounts();
    renderWorkspace();
  }
});

document.getElementById('serverAddPathButton').addEventListener('click', () => {
  const server = serverMenuServer;
  hideServerContextMenu();
  if (server) {
    pathModalServer = server;
    openPathModal();
  }
});

document.getElementById('pathBrowseButton').addEventListener('click', async () => {
  const errorEl = document.getElementById('pathError');
  errorEl.hidden = true;
  const res = await window.pywebview.api.pick_elementclient();
  if (res && res.ok) {
    pendingClientPath = res.path;
    document.getElementById('pathStatus').hidden = false;
    document.getElementById('pathSaveButton').disabled = false;
  } else if (res && res.error) {
    errorEl.textContent = res.error;
    errorEl.hidden = false;
  }
});

document.getElementById('pathSaveButton').addEventListener('click', async () => {
  if (pathModalServer && pendingClientPath) {
    pathModalServer.path = pendingClientPath;
    await window.pywebview.api.set_server_path(pathModalServer.name, pendingClientPath);
    const accountsVisible = currentServer && !document.getElementById('accountsView').hidden;
    renderWorkspace();
    if (accountsVisible) {
      document.getElementById('serverList').hidden = true;
      document.getElementById('accountsView').hidden = false;
      renderAccounts();
    }
  }
  closePathModal();
});

document.getElementById('pathCancelButton').addEventListener('click', closePathModal);
document.getElementById('pathModal').addEventListener('click', (event) => {
  if (event.target === event.currentTarget) closePathModal();
});

window.addEventListener('click', () => {
  hideContextMenu();
  hideServerContextMenu();
});
window.addEventListener('contextmenu', (event) => {
  if (event.defaultPrevented) return;
  if (event.target.closest('.accounts-table') || event.target.closest('.server-card')) return;
  hideContextMenu();
  hideServerContextMenu();
});

window.addEventListener('pywebviewready', async () => {
  const state = await window.pywebview.api.get_state();
  setTheme(state.theme);
  document.getElementById('trayToggle').checked = state.minimize_to_tray;
  const launchMode = document.querySelector(`input[name="launchMode"][value="${state.launch_mode}"]`);
  if (launchMode) launchMode.checked = true;
  document.getElementById('welcomeVersion').textContent = `v${state.version}`;
  document.getElementById('workspaceVersion').textContent = `v${state.version}`;
  const data = await window.pywebview.api.get_data();
  servers.length = 0;
  servers.push(...data.servers);
  fillRaces();
  fillClasses();
  renderWorkspace();
  showScreen(state.accepted ? 'workspace' : 'welcome');
});

themeButton.addEventListener('click', async () => {
  const next = currentTheme === 'dark' ? 'light' : 'dark';
  setTheme(next);
  await window.pywebview.api.set_theme(next);
});

document.getElementById('minimizeButton').addEventListener('click', () => window.pywebview.api.minimize());
document.getElementById('closeButton').addEventListener('click', () => window.pywebview.api.close());

const settingsModal = document.getElementById('settingsModal');
document.getElementById('settingsButton').addEventListener('click', () => {
  settingsModal.hidden = false;
});
document.getElementById('settingsCloseButton').addEventListener('click', () => {
  settingsModal.hidden = true;
});
settingsModal.addEventListener('click', (event) => {
  if (event.target === settingsModal) settingsModal.hidden = true;
});
window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') settingsModal.hidden = true;
});
document.getElementById('trayToggle').addEventListener('change', async (event) => {
  await window.pywebview.api.set_minimize_to_tray(event.target.checked);
});
document.querySelectorAll('input[name="launchMode"]').forEach((radio) => {
  radio.addEventListener('change', async (event) => {
    if (event.target.checked) {
      await window.pywebview.api.set_launch_mode(event.target.value);
    }
  });
});

function resetServerForm() {
  document.getElementById('serverName').value = '';
  clientPath = '';
  document.getElementById('clientStatus').hidden = true;
  document.getElementById('clientError').hidden = true;
}

function openServerForm() {
  resetServerForm();
  showScreen('server');
}

function openServerFormWizard() {
  resetServerForm();
  setWizardMode(true);
  showScreen('server');
}

document.getElementById('acceptButton').addEventListener('click', async () => {
  await window.pywebview.api.accept_welcome();
  openServerFormWizard();
});

document.getElementById('addServerButton').addEventListener('click', () => {
  setWizardMode(false);
  openServerForm();
});
document.getElementById('addServerToolbarButton').addEventListener('click', () => {
  setWizardMode(false);
  openServerForm();
});

document.getElementById('browseButton').addEventListener('click', async () => {
  const errorEl = document.getElementById('clientError');
  errorEl.hidden = true;
  const res = await window.pywebview.api.pick_elementclient();
  if (res && res.ok) {
    clientPath = res.path;
    document.getElementById('clientStatus').hidden = false;
  } else if (res && res.error) {
    errorEl.textContent = res.error;
    errorEl.hidden = false;
  }
});

document.getElementById('serverForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const name = document.getElementById('serverName').value.trim();
  const server = { name, path: clientPath, accounts: [] };
  const res = await window.pywebview.api.add_server(name, clientPath);
  if (res.ok) {
    servers.push(server);
    if (wizardMode) currentServer = server;
  }
  serverPage = Math.floor((servers.length - 1) / SERVERS_PER_PAGE);
  renderWorkspace();
  if (wizardMode) {
    resetAccountForm();
    accountFromServer = false;
    editingAccountIndex = null;
    showScreen('account');
  } else {
    showScreen('workspace');
  }
});

document.getElementById('serverLaterButton').addEventListener('click', () => {
  setWizardMode(false);
  showScreen('workspace');
});

document.getElementById('accountBackButton').addEventListener('click', () => {
  if (accountFromServer) {
    if (currentServer) openServerAccounts(currentServer);
    else showScreen('workspace');
  } else if (wizardMode) {
    showScreen('server');
  } else {
    document.getElementById('accountsView').hidden = true;
    document.getElementById('serverList').hidden = false;
    showScreen('workspace');
  }
});

function resetAccountForm() {
  document.getElementById('commentField').hidden = true;
  document.getElementById('accountBackButton').textContent = 'Назад';
  document.getElementById('accountForm').reset();
  fillClasses();
}

document.getElementById('accountForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const account = {
    login: document.getElementById('accountLogin').value.trim(),
    password: document.getElementById('accountPassword').value,
    nick: document.getElementById('characterNick').value.trim(),
    auto: document.getElementById('autoRole').checked,
    class: document.getElementById('classSelect').value,
    comment: document.getElementById('accountComment').value.trim(),
  };
  if (currentServer) {
    if (editingAccountIndex !== null) {
      await window.pywebview.api.update_account(currentServer.name, editingAccountIndex, account);
      currentServer.accounts[editingAccountIndex] = account;
    } else {
      await window.pywebview.api.add_account(currentServer.name, account);
      currentServer.accounts.push(account);
    }
  }
  resetAccountForm();
  editingAccountIndex = null;
  setWizardMode(false);
  renderWorkspace();
  if (accountFromServer) {
    if (currentServer) openServerAccounts(currentServer);
    else showScreen('workspace');
  } else {
    document.getElementById('accountsView').hidden = true;
    document.getElementById('serverList').hidden = false;
    showScreen('workspace');
  }
  accountFromServer = false;
});

document.getElementById('raceSelect').addEventListener('change', fillClasses);