from __future__ import annotations
from typing import Any, Dict, Optional, List
import logging
from supabase import create_client, Client

log = logging.getLogger("db")

DEFAULT_MUSCLES = {"legs": 0, "back": 0, "chest": 0, "shoulders": 0, "arms": 0, "core": 0}
DEFAULT_STATS = {"strength": 0, "stamina": 0, "athletics": 0}

BASE_EXERCISES = [
    {"name": "Присед", "category": "strength", "primary_muscle": "legs",
     "muscle_map": {"legs": 0.7, "core": 0.2, "back": 0.1}},
    {"name": "Жим лёжа", "category": "strength", "primary_muscle": "chest",
     "muscle_map": {"chest": 0.6, "shoulders": 0.2, "arms": 0.2}},
    {"name": "Становая тяга", "category": "strength", "primary_muscle": "back",
     "muscle_map": {"back": 0.5, "legs": 0.3, "core": 0.2}},
    {"name": "Подтягивания", "category": "strength", "primary_muscle": "back",
     "muscle_map": {"back": 0.7, "arms": 0.3}},
    {"name": "Жим стоя", "category": "strength", "primary_muscle": "shoulders",
     "muscle_map": {"shoulders": 0.6, "arms": 0.2, "core": 0.2}},
    {"name": "Планка", "category": "core", "primary_muscle": "core",
     "muscle_map": {"core": 1.0}},
]

class Db:
    def __init__(self, url: str, service_key: str) -> None:
        self.client: Client = create_client(url, service_key)

    def seed_exercises_if_empty(self) -> None:
        """Idempotent seed: если упражнений нет — добавим базовые."""
        try:
            res = self.client.table("exercises").select("id").limit(1).execute()
            if res.data:
                return
            self.client.table("exercises").insert(BASE_EXERCISES).execute()
            log.info("Seeded base exercises: %s", len(BASE_EXERCISES))
        except Exception:
            log.exception("Failed to seed exercises")

    def get_or_create_user(self, telegram_id: int, username: Optional[str]) -> Dict[str, Any]:
        """Создаём/обновляем пользователя по telegram_id и возвращаем строку users."""
        # Upsert безопаснее вставки: уникальность telegram_id защищает от дублей
        payload = {"telegram_id": telegram_id, "username": username}
        self.client.table("users").upsert(payload, on_conflict="telegram_id").execute()

        # Берём реальную запись с внутренним id
        res = (
            self.client.table("users")
            .select("id,telegram_id,username,units,timezone")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError("User upsert/select failed")
        return res.data[0]

    def ensure_progress(self, user_id: int) -> None:
        """Если progress нет — создаём."""
        res = (
            self.client.table("progress")
            .select("user_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return
        self.client.table("progress").insert(
            {
                "user_id": user_id,
                "level": 1,
                "xp": 0,
                "stats": DEFAULT_STATS,
                "muscles": DEFAULT_MUSCLES,
            }
        ).execute()

    def get_progress(self, user_id: int) -> Dict[str, Any]:
        res = (
            self.client.table("progress")
            .select("user_id,level,xp,stats,muscles,updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError("Progress not found")
        return res.data[0]