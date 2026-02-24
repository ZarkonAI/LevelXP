from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

log = logging.getLogger("db")

DEFAULT_MUSCLES = {"legs": 0, "back": 0, "chest": 0, "shoulders": 0, "arms": 0, "core": 0}
DEFAULT_STATS = {"strength": 0, "stamina": 0, "athletics": 0}

BASE_EXERCISES = [
    {
        "name": "Присед",
        "category": "strength",
        "primary_muscle": "legs",
        "muscle_map": {"legs": 0.7, "core": 0.2, "back": 0.1},
    },
    {
        "name": "Жим лёжа",
        "category": "strength",
        "primary_muscle": "chest",
        "muscle_map": {"chest": 0.6, "shoulders": 0.2, "arms": 0.2},
    },
    {
        "name": "Становая тяга",
        "category": "strength",
        "primary_muscle": "back",
        "muscle_map": {"back": 0.5, "legs": 0.3, "core": 0.2},
    },
    {
        "name": "Подтягивания",
        "category": "strength",
        "primary_muscle": "back",
        "muscle_map": {"back": 0.7, "arms": 0.3},
    },
    {
        "name": "Жим стоя",
        "category": "strength",
        "primary_muscle": "shoulders",
        "muscle_map": {"shoulders": 0.6, "arms": 0.2, "core": 0.2},
    },
    {"name": "Планка", "category": "core", "primary_muscle": "core", "muscle_map": {"core": 1.0}},
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
        payload = {"telegram_id": telegram_id, "username": username}
        self.client.table("users").upsert(payload, on_conflict="telegram_id").execute()

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
        res = self.client.table("progress").select("user_id").eq("user_id", user_id).limit(1).execute()
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
            .select("user_id,level,xp,stats,muscles,workouts_count,total_sets,updated_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError("Progress not found")
        return res.data[0]

    def get_exercise(self, exercise_id: int) -> Dict[str, Any]:
        res = (
            self.client.table("exercises")
            .select("id,name,primary_muscle,muscle_map")
            .eq("id", exercise_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError("Exercise not found")
        return res.data[0]

    def update_progress(
        self,
        user_id: int,
        level: int,
        xp: int,
        muscles: Dict[str, int],
        workouts_count: Optional[int] = None,
        total_sets: Optional[int] = None,
    ) -> Dict[str, Any]:
        base_payload: Dict[str, Any] = {
            "level": level,
            "xp": xp,
            "muscles": muscles,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        payload = dict(base_payload)
        if workouts_count is not None:
            payload["workouts_count"] = workouts_count
        if total_sets is not None:
            payload["total_sets"] = total_sets

        res = self.client.table("progress").update(payload).eq("user_id", user_id).execute()
        if not res.data:
            raise RuntimeError("update_progress failed")
        return res.data[0]

    def list_exercises(self, limit: int = 12) -> List[Dict[str, Any]]:
        res = (
            self.client.table("exercises")
            .select("id,name,primary_muscle,muscle_map")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def create_custom_exercise(self, name: str, primary_muscle: str) -> Dict[str, Any]:
        payload = {
            "name": name,
            "category": "custom",
            "primary_muscle": primary_muscle,
            "muscle_map": {primary_muscle: 1.0},
        }
        res = self.client.table("exercises").insert(payload).execute()
        if res.data:
            row = res.data[0]
            if "id" in row and "name" in row:
                return {"id": row["id"], "name": row["name"]}

        fallback = (
            self.client.table("exercises")
            .select("id,name")
            .eq("name", name)
            .eq("primary_muscle", primary_muscle)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not fallback.data:
            raise RuntimeError("create_custom_exercise failed")
        return fallback.data[0]

    def create_workout(self, user_id: int, title: str = "Quick") -> int:
        res = self.client.table("workouts").insert({"user_id": user_id, "title": title}).execute()
        if res.data and res.data[0].get("id") is not None:
            return int(res.data[0]["id"])

        fallback = (
            self.client.table("workouts")
            .select("id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not fallback.data:
            raise RuntimeError("create_workout failed")
        return int(fallback.data[0]["id"])

    def create_workout_item(self, workout_id: int, exercise_id: int, order_index: int = 1) -> int:
        payload = {"workout_id": workout_id, "exercise_id": exercise_id, "order_index": order_index}
        res = self.client.table("workout_items").insert(payload).execute()
        if res.data and res.data[0].get("id") is not None:
            return int(res.data[0]["id"])

        fallback = (
            self.client.table("workout_items")
            .select("id")
            .eq("workout_id", workout_id)
            .eq("exercise_id", exercise_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not fallback.data:
            raise RuntimeError("create_workout_item failed")
        return int(fallback.data[0]["id"])

    def create_set(
        self,
        workout_item_id: int,
        weight: float,
        reps: int,
        sets_count: int,
        rest_seconds: int,
    ) -> int:
        payload = {
            "workout_item_id": workout_item_id,
            "weight": weight,
            "reps": reps,
            "sets_count": sets_count,
            "rest_seconds": rest_seconds,
        }
        res = self.client.table("sets").insert(payload).execute()
        if res.data and res.data[0].get("id") is not None:
            return int(res.data[0]["id"])

        fallback = (
            self.client.table("sets")
            .select("id")
            .eq("workout_item_id", workout_item_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not fallback.data:
            raise RuntimeError("create_set failed")
        return int(fallback.data[0]["id"])
