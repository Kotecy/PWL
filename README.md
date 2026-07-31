# PWL by Kotecy

Десктопное приложение для автоматического входа в аккаунты Perfect World.

## Интерфейс

С версии **0.3.0** интерфейс работает на HTML/CSS внутри нативного окна pywebview:

- без браузерных вкладок, адресной строки и меню;
- только собственный компактный бар PWL;
- нативное перетаскивание frameless-окна;
- чёткие SVG-иконки и плавные CSS-состояния;
- светлая и тёмная темы;
- Python остаётся backend приложения.

На Windows используется системный WebView2 Runtime. В актуальных Windows 10/11 он обычно уже установлен вместе с Microsoft Edge.

## Запуск из исходников

```bash
pip install -r requirements.txt
python main.py
```

## Сборка

```powershell
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name PWL --add-data "web;web" main.py
```

GitHub Actions автоматически публикует `PWL.exe` в артефакте `PWL-windows` и rolling-релизе `latest`.
