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

    def list_workouts(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        res = (
            self.client.table("workouts")
            .select("id,workout_date,title,created_at")
            .eq("user_id", user_id)
            .order("workout_date", desc=True)
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def get_workout_details(self, workout_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        workout_res = (
            self.client.table("workouts")
            .select("id,workout_date,title")
            .eq("id", workout_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not workout_res.data:
            return None
        workout = workout_res.data[0]

        items_res = (
            self.client.table("workout_items")
            .select("id,exercise_id,order_index")
            .eq("workout_id", workout_id)
            .order("order_index", desc=False)
            .execute()
        )
        items = items_res.data or []
        if not items:
            return {"workout": workout, "items": []}

        exercise_ids = [int(item["exercise_id"]) for item in items if item.get("exercise_id") is not None]
        exercise_names: Dict[int, str] = {}
        if exercise_ids:
            ex_res = (
                self.client.table("exercises")
                .select("id,name")
                .in_("id", exercise_ids)
                .execute()
            )
            exercise_names = {int(row["id"]): str(row.get("name") or "Упражнение") for row in (ex_res.data or [])}

        result_items: List[Dict[str, Any]] = []
        for item in items:
            sets_res = (
                self.client.table("sets")
                .select("weight,reps,sets_count,rest_seconds,rest_pattern")
                .eq("workout_item_id", item["id"])
                .order("id", desc=False)
                .execute()
            )
            sets_rows = sets_res.data or []
            if not sets_rows:
                result_items.append(
                    {
                        "exercise_id": item.get("exercise_id"),
                        "exercise_name": exercise_names.get(int(item.get("exercise_id") or 0), "Упражнение"),
                        "weight": 0,
                        "reps": 0,
                        "sets_count": 0,
                        "rest_seconds": 0,
                        "rest_pattern": None,
                    }
                )
                continue

            for set_row in sets_rows:
                result_items.append(
                    {
                        "exercise_id": item.get("exercise_id"),
                        "exercise_name": exercise_names.get(int(item.get("exercise_id") or 0), "Упражнение"),
                        "weight": set_row.get("weight") or 0,
                        "reps": set_row.get("reps") or 0,
                        "sets_count": set_row.get("sets_count") or 0,
                        "rest_seconds": set_row.get("rest_seconds") or 0,
                        "rest_pattern": set_row.get("rest_pattern"),
                    }
                )

        return {"workout": workout, "items": result_items}

    def create_template_from_workout(self, user_id: int, workout_id: int, name: str) -> int:
        details = self.get_workout_details(workout_id=workout_id, user_id=user_id)
        if not details:
            raise RuntimeError("Workout not found or forbidden")

        payload = [
            {
                "exercise_id": item.get("exercise_id"),
                "weight": item.get("weight") or 0,
                "reps": item.get("reps") or 0,
                "sets_count": item.get("sets_count") or 0,
                "rest_seconds": item.get("rest_seconds") or 0,
                "rest_pattern": item.get("rest_pattern"),
            }
            for item in details.get("items", [])
            if item.get("exercise_id") is not None
        ]

        res = self.client.table("templates").insert({"user_id": user_id, "name": name, "payload": payload}).execute()
        if res.data and res.data[0].get("id") is not None:
            return int(res.data[0]["id"])

        fallback = (
            self.client.table("templates")
            .select("id")
            .eq("user_id", user_id)
            .eq("name", name)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not fallback.data:
            raise RuntimeError("create_template_from_workout failed")
        return int(fallback.data[0]["id"])

    def list_templates(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        res = (
            self.client.table("templates")
            .select("id,name,created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def get_template(self, user_id: int, template_id: int) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table("templates")
            .select("id,name,payload")
            .eq("user_id", user_id)
            .eq("id", template_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        return res.data[0]

    def create_workout_from_template(self, user_id: int, template_row: Dict[str, Any], title: Optional[str] = None) -> int:
        workout_title = title or str(template_row.get("name") or "Template")
        workout_id = self.create_workout(user_id=user_id, title=workout_title, mode="template")

        payload = template_row.get("payload") or []
        if not isinstance(payload, list):
            payload = []

        for idx, item in enumerate(payload, start=1):
            exercise_id = item.get("exercise_id")
            if exercise_id is None:
                continue

            workout_item_id = self.create_workout_item(workout_id=workout_id, exercise_id=int(exercise_id), order_index=idx)
            rest_pattern = item.get("rest_pattern")
            self.create_set(
                workout_item_id=workout_item_id,
                weight=float(item.get("weight") or 0),
                reps=int(item.get("reps") or 0),
                sets_count=int(item.get("sets_count") or 0),
                rest_seconds=int(item.get("rest_seconds") or 0),
                rest_pattern_seconds=rest_pattern if isinstance(rest_pattern, list) else None,
            )

        return workout_id

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
