from __future__ import annotations

import logging
import math
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
                "workouts_count": 0,
                "total_sets": 0,
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
        if res.data and res.data[0].get("id") is not None:
            return {"id": res.data[0]["id"], "name": res.data[0].get("name", name)}

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

    def create_workout(self, user_id: int, title: str = "Quick", mode: str = "strength") -> int:
        payload = {"user_id": user_id, "title": title, "mode": mode}
        res = self.client.table("workouts").insert(payload).execute()
        if res.data and res.data[0].get("id") is not None:
            return int(res.data[0]["id"])

        fallback = (
            self.client.table("workouts")
            .select("id")
            .eq("user_id", user_id)
            .eq("title", title)
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
        rest_pattern_seconds: Optional[List[int]] = None,
    ) -> int:
        payload = {
            "workout_item_id": workout_item_id,
            "weight": weight,
            "reps": reps,
            "sets_count": sets_count,
            "rest_seconds": rest_seconds,
            "rest_pattern": rest_pattern_seconds,
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

    def award_and_update_progress(
        self,
        user_id: int,
        exercise_id: int,
        weight: float,
        reps: int,
        sets_count: int,
    ) -> Dict[str, Any]:
        progress_res = (
            self.client.table("progress")
            .select("user_id,level,xp,muscles,workouts_count,total_sets")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not progress_res.data:
            raise RuntimeError("Progress not found for awarding")
        progress = progress_res.data[0]

        exercise = self.get_exercise(exercise_id)

        volume = float(weight) * int(reps) * int(sets_count)
        load_points = math.sqrt(max(0.0, volume))
        xp_gain = max(5, round(load_points * 0.8))

        muscle_map = exercise.get("muscle_map") or {}
        primary_muscle = exercise.get("primary_muscle")
        if not isinstance(muscle_map, dict) or not muscle_map:
            muscle_map = {primary_muscle: 1.0} if primary_muscle else {}

        muscles = progress.get("muscles") or {}
        if not isinstance(muscles, dict):
            muscles = {}

        muscle_gains: List[tuple[str, int]] = []
        for muscle, coeff in muscle_map.items():
            if muscle is None:
                continue
            gain = round(load_points * float(coeff))
            if gain <= 0:
                continue
            muscles[muscle] = int(muscles.get(muscle, 0)) + gain
            muscle_gains.append((str(muscle), gain))

        def xp_to_next(level: int) -> int:
            return 100 + level * 25

        xp_new = int(progress.get("xp", 0)) + int(xp_gain)
        level_new = int(progress.get("level", 1))
        while xp_new >= xp_to_next(level_new):
            xp_new -= xp_to_next(level_new)
            level_new += 1

        workouts_count = int(progress.get("workouts_count", 0)) + 1
        total_sets = int(progress.get("total_sets", 0)) + int(sets_count)

        self.client.table("progress").update(
            {
                "level": level_new,
                "xp": xp_new,
                "muscles": muscles,
                "workouts_count": workouts_count,
                "total_sets": total_sets,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", user_id).execute()

        muscle_gains_sorted_top3 = sorted(muscle_gains, key=lambda x: x[1], reverse=True)[:3]
        return {
            "xp_gain": int(xp_gain),
            "level_new": int(level_new),
            "xp_new": int(xp_new),
            "xp_to_next": int(xp_to_next(level_new)),
            "muscle_gains_sorted_top3": muscle_gains_sorted_top3,
        }
