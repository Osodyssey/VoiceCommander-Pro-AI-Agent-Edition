
# commands.py (unchanged default commands for AI edition)
import json, platform
from pathlib import Path
CONFIG_FILE = Path(__file__).parent / 'commands.json'
def make_open_command(target):
    system = platform.system()
    if system == 'Windows':
        return f'start "" "{target}"'
    elif system == 'Darwin':
        return f'open "{target}"'
    else:
        return f'xdg-open "{target}"'
def open_terminal_command():
    system = platform.system()
    if system == "Windows":
        return "start cmd"
    elif system == "Linux":
        return "gnome-terminal -- bash -lc \\'exec bash\\'"
    elif system == "Darwin":
        return "open -a Terminal"
_default_actions = {
    'باز کن کروم': make_open_command('https://www.google.com'),
    'باز کن یوتیوب': make_open_command('https://youtube.com'),
    'باز کن تلگرام': make_open_command('https://web.telegram.org'),
    'پوشه دانلودها': make_open_command(str(Path.home() / 'Downloads')),
    'باز کن فایل خانه': make_open_command(str(Path.home())),
    'باز کن ترمینال': open_terminal_command()
}
def load_commands():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                merged = {**_default_actions, **data}
                return merged
        except Exception:
            return _default_actions.copy()
    else:
        save_commands({})
        return _default_actions.copy()
def save_commands(custom_actions: dict):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(custom_actions, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print('خطا در ذخیرهٔ فرمان‌ها:', e)
        return False
