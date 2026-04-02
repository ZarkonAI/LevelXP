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

Создайте `.env` в корне проекта (не коммитьте его):

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

## Частые ошибки

- **Invalid API key**
  - Проверьте `SUPABASE_SERVICE_KEY` / `SUPABASE_KEY` и `SUPABASE_URL`.
  - Убедитесь, что ключ относится к тому же проекту Supabase.
- **Проблемы с `parse_mode` / default props в aiogram v3**
  - Используйте `DefaultBotProperties(parse_mode=ParseMode.HTML)` при создании `Bot`.
- **PowerShell execution policy**
  - Если не активируется venv: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Мини-чеклист ручного теста v1

1. Запустить бота и выполнить `/start`.
2. Выполнить `/ping` и `/version`.
3. Добавить 10 тренировок через «⚡ Быстрая запись».
4. Открыть историю и проверить последние записи.
5. Открыть карточку тренировки из истории.
6. Нажать «🔁 Повторить сегодня» и проверить новую запись.
7. Нажать «✏️ Исправить запись» и сохранить правки.
8. Проверить раздел «🧬 Персонаж» после тренировок (XP/уровень).
9. Сохранить тренировку как шаблон и повторить шаблон.
10. Проверить, что повторный клик «✅ Сохранить» не дублирует запись.

## Безопасность

1. Никогда не коммитьте `.env` и любые ключи.
2. Supabase service role key хранится только в переменных окружения (или `.env` локально).
3. Если ключ случайно утёк:
   - немедленно сгенерируйте новый в Supabase;
   - обновите переменные окружения на сервере;
   - перезапустите бота.

## SQL миграции

Для истории/повтора/статусов тренировок примените:

- `sql/20260224_workouts_status_source_idx.sql`

