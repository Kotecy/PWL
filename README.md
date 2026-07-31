<div align="center">

# PWL by Kotecy

**Менеджер аккаунтов Perfect World** — десктопное приложение с нативным
frameless-окном и современным интерфейсом на HTML/CSS/JS.

[![Version](https://img.shields.io/badge/version-0.5.2-blue)](#)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](#)
[![Platform](https://img.shields.io/badge/Windows-10/11-0078D6?logo=windows&logoColor=white)](#)

</div>

---

## Возможности

- **Онбординг-мастер** — добавление сервера и первого аккаунта в два шага прямо из приветственного экрана
- **Список серверов** — карточки с уникальными эмблемами и пагинацией (4 сервера на страницу)
- **Подключение Elementclient** — у сервера без пути к клиенту отображается предупреждение; путь можно указать через контекстное меню или при попытке входа
- **Список аккаунтов** — перетаскивание строк для смены порядка, контекстное меню, редактирование, автовход на персонажа (макет)
- **Светлая и тёмная темы** — переключаются одной кнопкой и сохраняются между запусками
- **Нативное окно** — frameless с собственной шапкой, скруглёнными углами и плавным перетаскиванием
- **Без браузера** — интерфейс рендерится через WebView2, Python остаётся backend'ом

## Технологии

| Слой | Стек |
| --- | --- |
| Backend | Python 3.12+, pywebview, Edge Chromium (WebView2) |
| UI | HTML5, CSS3 (переменные, градиенты, анимации), ванильный JavaScript |
| Нативное окно | Win32 API: регион окна, `WS_MINIMIZEBOX`, перетаскивание |
| Сборка | PyInstaller, GitHub Actions |

## Быстрый старт

### Требования

- Windows 10/11 с WebView2 Runtime (обычно предустановлен вместе с Microsoft Edge)
- Python 3.12+

### Запуск из исходников

```bash
pip install -r requirements.txt
python main.py
```

### Сборка в .exe

```powershell
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name PWL --add-data "web;web" main.py
```

GitHub Actions автоматически собирает `PWL.exe` при каждом пуше в `main` и публикует его в артефакт `PWL-windows` и rolling-релиз `latest`.

## Использование

1. При первом запуске — **Принять**, мастер предложит добавить первый сервер и аккаунт
2. Название сервера + путь до `Elementclient` (опционально, можно добавить позже)
3. Из списка серверов можно перейти к аккаунтам, добавить ещё или указать путь к клиенту
4. Аккаунты можно перетаскивать мышью, менять им порядок и редактировать по правому клику

## Структура проекта

```
PWL/
├── main.py              # Backend, нативное окно, JS-мост (Api)
├── requirements.txt
├── web/
│   ├── index.html       # Все экраны интерфейса
│   ├── styles.css       # Тёмная/светлая темы, карточки, таблицы
│   └── app.js           # Логика экранов, мастера, drag-and-drop
├── .github/workflows/   # Сборка Windows .exe
└── CHANGELOG.md
```

## Хранение данных

Настройки (флаг онбординга, тема) сохраняются в JSON:

```
%APPDATA%\PWL\config.json
```

## Лицензия

Проект распространяется под лицензией [MIT](LICENSE).
