const sunIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.6"/><path d="M12 2.5v2M12 19.5v2M4.2 4.2l1.45 1.45M18.35 18.35l1.45 1.45M2.5 12h2M19.5 12h2M4.2 19.8l1.45-1.45M18.35 5.65l1.45-1.45"/></svg>`;
const moonIcon = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.2 15.1A8.3 8.3 0 0 1 8.9 3.8 8.4 8.4 0 1 0 20.2 15.1Z"/></svg>`;

const welcome = document.getElementById('welcomeScreen');
const workspace = document.getElementById('workspaceScreen');
const themeButton = document.getElementById('themeButton');
let currentTheme = 'dark';

function setTheme(theme) {
  currentTheme = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = currentTheme;
  themeButton.innerHTML = currentTheme === 'dark' ? sunIcon : moonIcon;
  themeButton.setAttribute('aria-label', currentTheme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
}

function showScreen(accepted) {
  welcome.hidden = accepted;
  workspace.hidden = !accepted;
}

window.addEventListener('pywebviewready', async () => {
  const state = await window.pywebview.api.get_state();
  setTheme(state.theme);
  document.getElementById('welcomeVersion').textContent = `v${state.version}`;
  document.getElementById('workspaceVersion').textContent = `v${state.version}`;
  showScreen(state.accepted);
});

themeButton.addEventListener('click', async () => {
  const next = currentTheme === 'dark' ? 'light' : 'dark';
  setTheme(next);
  await window.pywebview.api.set_theme(next);
});

document.getElementById('minimizeButton').addEventListener('click', () => window.pywebview.api.minimize());
document.getElementById('closeButton').addEventListener('click', () => window.pywebview.api.close());
document.getElementById('acceptButton').addEventListener('click', async () => {
  await window.pywebview.api.accept_welcome();
  showScreen(true);
});
