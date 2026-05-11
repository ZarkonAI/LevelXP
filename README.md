# LevelXP bot

Telegram-бот на **aiogram v3** + **Supabase** для ведения тренировок, истории, повторов и прогресса персонажа.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\Activate.ps1  # Windows PowerShell
pip install -r requirements.txt
```

## Настройка `.env`

```env
BOT_TOKEN=your_telegram_bot_token
SUPABASE_URL=https://your-project.supabase.co
# Предпочтительно:
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
# Совместимость (если SERVICE_KEY не задан):
# SUPABASE_KEY=your_supabase_service_role_key

ENV=dev
LOG_LEVEL=INFO
```

## Запуск

```bash
python -m app.main
```

## Health-check команды

- `/ping` → `ok`
- `/version` → `FitXP v1.0`