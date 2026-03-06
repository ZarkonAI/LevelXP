from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

log = logging.getLogger("db")

DEFAULT_MUSCLES = {"legs": 0, "back": 0, "chest": 0, "shoulders": 0, "arms": 0, "core": 0}
DEFAULT_STATS = {"strength": 0, "stamina": 0, "athletics": 0}


EXERCISE_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9\- ]+$")
EXERCISE_NAME_BLOCKLIST = ("http", "https", "t.me", ".com", ".ru", ".net", ".org")
EXERCISE_NAME_STOP_WORDS = ("бляд", "хуй", "пизд", "еба", "ебл", "сук")


ACHIEVEMENTS_META = {
    "first_workout": "Первая тренировка",
    "workouts_10": "10 тренировок",
    "workouts_30": "30 тренировок",
    "sets_100": "100 подходов суммарно",
    "legs_100": "Ноги 100+",
    "chest_100": "Грудь 100+",
    "back_100": "Спина 100+",
    "streak_3": "3 дня подряд",
}

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


def _trim_title(title: str, max_len: int = 80) -> str:
    value = (title or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


def _build_workout_title(
    exercise_name: str,
    weight: float,
    reps: int,
    sets_count: int,
    mode: str,
    rest_seconds: int,
    rest_pattern: Optional[List[int]] = None,
) -> str:
    if weight == 0:
        title = f"{exercise_name} · {reps}×{sets_count}"
    else:
        title = f"{exercise_name} · {weight:g}кг×{reps}×{sets_count}"

    if mode == "pattern":
        title += " · rest pattern"
    else:
        title += f" · rest {float(rest_seconds or 0) / 60:g}м"
    return _trim_title(title)


class Db:
    def __init__(self, url: str, service_key: str) -> None:
        self.client: Client = create_client(url, service_key)
        self._ex_cache: Dict[str, Any] = {"data": None, "expires_at": None}

    @staticmethod
    def _exercise_display_name(row: Dict[str, Any]) -> str:
        return str(row.get("name_ru") or row.get("name") or "Упражнение")

    def seed_exercises_if_empty(self) -> None:
        """Idempotent seed: если упражнений нет — добавим базовые."""
        try:
            res = self.client.table("exercises").select("id").limit(1).execute()
            if res.data:
                return
            self.client.table("exercises").insert(BASE_EXERCISES).execute()
            self._ex_cache = {"data": None, "expires_at": None}
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
                "achievements": [],
            }
        ).execute()

    @staticmethod
    def _is_missing_column_error(exc: Exception, column_name: str) -> bool:
        message = str(exc).lower()
        return "column" in message and column_name.lower() in message and "progress" in message

    def get_progress(self, user_id: int) -> Dict[str, Any]:
        field_sets = [
            "user_id,level,xp,stats,muscles,workouts_count,total_sets,achievements,updated_at",
            "user_id,level,xp,stats,muscles,workouts_count,total_sets,updated_at",
            "user_id,level,xp,stats,muscles,updated_at",
        ]

        last_exc: Optional[Exception] = None
        for fields in field_sets:
            try:
                res = self.client.table("progress").select(fields).eq("user_id", user_id).limit(1).execute()
                if not res.data:
                    raise RuntimeError("Progress not found")
                row = res.data[0] or {}
                if not isinstance(row.get("achievements"), list):
                    row["achievements"] = []
                row["workouts_count"] = self._to_int(row.get("workouts_count"), 0)
                row["total_sets"] = self._to_int(row.get("total_sets"), 0)
                row["stats"] = row.get("stats") if isinstance(row.get("stats"), dict) else DEFAULT_STATS.copy()
                row["muscles"] = row.get("muscles") if isinstance(row.get("muscles"), dict) else DEFAULT_MUSCLES.copy()
                return row
            except Exception as exc:
                last_exc = exc
                if "achievements" in fields and self._is_missing_column_error(exc, "achievements"):
                    continue
                if "workouts_count" in fields and (
                    self._is_missing_column_error(exc, "workouts_count") or self._is_missing_column_error(exc, "total_sets")
                ):
                    continue
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("Progress not found")

    def get_exercise(self, exercise_id: int) -> Dict[str, Any]:
        res = (
            self.client.table("exercises")
            .select("id,name,name_ru,image_url,primary_muscle,muscle_map")
            .eq("id", exercise_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise RuntimeError("Exercise not found")
        row = res.data[0]
        row["display_name"] = self._exercise_display_name(row)
        return row

    def _validate_exercise_name(self, name: str) -> Optional[str]:
        clean = (name or "").strip()
        if len(clean) < 2 or len(clean) > 60:
            return "length"

        low = clean.lower()
        if any(token in low for token in EXERCISE_NAME_BLOCKLIST):
            return "links"
        if any(token in low for token in EXERCISE_NAME_STOP_WORDS):
            return "stop_word"
        if not EXERCISE_NAME_RE.fullmatch(clean):
            return "symbols"
        return None

    def list_exercises(
        self,
        user_id: int,
        limit: int = 12,
        primary_muscle: Optional[str] = None,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query_builder = self.client.table("exercises").select(
            "id,name,name_ru,image_url,primary_muscle,muscle_map,is_featured,created_at"
        )
        query_builder = query_builder.or_(f"owner_user_id.is.null,owner_user_id.eq.{int(user_id)}")

        muscle_filter = (primary_muscle or "").strip().lower()
        if muscle_filter:
            query_builder = query_builder.eq("primary_muscle", muscle_filter)

        search_query = (query or "").strip()
        if search_query:
            query_builder = query_builder.or_(f"name.ilike.%{search_query}%,name_ru.ilike.%{search_query}%")

        res = query_builder.order("is_featured", desc=True).order("created_at", desc=True).limit(limit).execute()
        rows = res.data or []

        normalized = [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "name_ru": row.get("name_ru"),
                "image_url": row.get("image_url"),
                "primary_muscle": row.get("primary_muscle"),
                "muscle_map": row.get("muscle_map"),
                "display_name": self._exercise_display_name(row),
            }
            for row in rows
        ]
        return normalized[:limit]

    def create_custom_exercise(self, user_id: int, name: str, primary_muscle: str) -> Dict[str, Any]:
        reason = self._validate_exercise_name(name)
        if reason:
            raise ValueError("ERR_EXERCISE_NAME")

        clean_name = (name or "").strip()
        payload = {
            "name": clean_name,
            "category": "custom",
            "primary_muscle": primary_muscle,
            "muscle_map": {primary_muscle: 1.0},
            "owner_user_id": user_id,
        }
        res = self.client.table("exercises").insert(payload).execute()
        self._ex_cache = {"data": None, "expires_at": None}
        if res.data and res.data[0].get("id") is not None:
            row = res.data[0]
            return {"id": row["id"], "name": row.get("name", clean_name), "display_name": self._exercise_display_name(row)}

        fallback = (
            self.client.table("exercises")
            .select("id,name,name_ru")
            .eq("name", clean_name)
            .eq("primary_muscle", primary_muscle)
            .eq("owner_user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not fallback.data:
            raise RuntimeError("create_custom_exercise failed")
        row = fallback.data[0]
        row["display_name"] = self._exercise_display_name(row)
        return row

    def create_workout(
        self,
        user_id: int,
        title: str,
        mode: str = "strength",
        workout_date: Optional[str] = None,
        status: str = "done",
        source_workout_id: Optional[int] = None,
    ) -> int:
        payload: Dict[str, Any] = {"user_id": user_id, "title": title, "mode": mode, "status": status}
        if workout_date:
            payload["workout_date"] = workout_date
        if source_workout_id is not None:
            payload["source_workout_id"] = source_workout_id
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
            .select("id,workout_date,title,mode,status,total_xp,muscle_delta")
            .eq("user_id", user_id)
            .order("workout_date", desc=True)
            .order("id", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def get_workout_card(self, user_id: int, workout_id: int) -> Optional[Dict[str, Any]]:
        header_res = (
            self.client.table("workouts")
            .select("id,workout_date,title,mode,status")
            .eq("id", workout_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not header_res.data:
            return None

        header = header_res.data[0]
        items_res = (
            self.client.table("workout_items")
            .select("id,exercise_id,order_index")
            .eq("workout_id", workout_id)
            .order("order_index", desc=False)
            .limit(1)
            .execute()
        )
        item = (items_res.data or [{}])[0]

        exercise_id = int(item.get("exercise_id") or 0)
        exercise_name = "Упражнение"
        if exercise_id:
            ex_res = self.client.table("exercises").select("id,name,name_ru").eq("id", exercise_id).limit(1).execute()
            if ex_res.data:
                exercise_name = self._exercise_display_name(ex_res.data[0])

        set_row: Dict[str, Any] = {}
        if item.get("id"):
            sets_res = (
                self.client.table("sets")
                .select("id,weight,reps,sets_count,rest_seconds,rest_pattern")
                .eq("workout_item_id", item["id"])
                .order("id", desc=False)
                .limit(1)
                .execute()
            )
            set_row = (sets_res.data or [{}])[0]

        return {
            "id": int(header.get("id") or workout_id),
            "workout_date": header.get("workout_date"),
            "title": header.get("title"),
            "mode": header.get("mode"),
            "status": header.get("status"),
            "total_xp": int(header.get("total_xp") or 0),
            "muscle_delta": header.get("muscle_delta") if isinstance(header.get("muscle_delta"), dict) else {},
            "workout_item_id": int(item.get("id") or 0),
            "exercise_id": exercise_id,
            "exercise_name": exercise_name,
            "display_name": exercise_name,
            "weight": float(set_row.get("weight") or 0),
            "reps": int(set_row.get("reps") or 0),
            "sets_count": int(set_row.get("sets_count") or 0),
            "rest_seconds": int(set_row.get("rest_seconds") or 0),
            "rest_pattern": set_row.get("rest_pattern"),
        }

    def clone_workout_as_new(self, user_id: int, workout_id: int) -> int:
        card = self.get_workout_card(user_id=user_id, workout_id=workout_id)
        if not card:
            raise RuntimeError("Workout not found")

        workout_date = datetime.now(timezone.utc).date().isoformat()
        new_workout_id = self.create_workout(
            user_id=user_id,
            title=str(card.get("title") or "Тренировка"),
            mode=str(card.get("mode") or "strength"),
            workout_date=workout_date,
            status="planned",
            source_workout_id=workout_id,
        )
        workout_item_id = self.create_workout_item(
            workout_id=new_workout_id,
            exercise_id=int(card.get("exercise_id") or 0),
            order_index=1,
        )
        self.create_set(
            workout_item_id=workout_item_id,
            weight=float(card.get("weight") or 0),
            reps=int(card.get("reps") or 0),
            sets_count=int(card.get("sets_count") or 0),
            rest_seconds=int(card.get("rest_seconds") or 0),
            rest_pattern_seconds=card.get("rest_pattern") if isinstance(card.get("rest_pattern"), list) else None,
        )
        return int(new_workout_id)

    def update_workout_metrics(
        self,
        user_id: int,
        workout_id: int,
        total_xp: int,
        total_sets: int,
        muscle_delta: Dict[str, int],
        status: str = "done",
    ) -> None:
        payload = {
            "total_xp": int(max(0, total_xp)),
            "total_sets": int(max(0, total_sets)),
            "muscle_delta": muscle_delta if isinstance(muscle_delta, dict) else {},
            "status": status,
        }
        self.client.table("workouts").update(payload).eq("id", workout_id).eq("user_id", user_id).execute()

    def toggle_status(self, user_id: int, workout_id: int) -> str:
        card = self.get_workout_card(user_id=user_id, workout_id=workout_id)
        if not card:
            raise RuntimeError("Workout not found")
        new_status = "planned" if card.get("status") == "done" else "done"
        self.client.table("workouts").update({"status": new_status}).eq("id", workout_id).eq("user_id", user_id).execute()
        return new_status

    def toggle_workout_status_with_progress(self, user_id: int, workout_id: int) -> str:
        workout_res = (
            self.client.table("workouts")
            .select("id,status,total_xp,total_sets,muscle_delta")
            .eq("id", workout_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not workout_res.data:
            raise RuntimeError("Workout not found")

        workout = workout_res.data[0] or {}
        progress = self.get_progress(user_id)

        workout_xp = self._to_int(workout.get("total_xp"), 0)
        workout_sets = self._to_int(workout.get("total_sets"), 0)
        workout_muscles = workout.get("muscle_delta") if isinstance(workout.get("muscle_delta"), dict) else {}

        xp = self._to_int(progress.get("xp"), 0)
        total_sets = self._to_int(progress.get("total_sets"), 0)
        workouts_count = self._to_int(progress.get("workouts_count"), 0)
        muscles = progress.get("muscles") if isinstance(progress.get("muscles"), dict) else {}

        current_status = str(workout.get("status") or "planned")
        if current_status == "done":
            new_status = "planned"
            xp = max(0, xp - workout_xp)
            total_sets = max(0, total_sets - workout_sets)
            workouts_count = max(0, workouts_count - 1)
            for muscle, gain in workout_muscles.items():
                muscles[muscle] = max(0, self._to_int(muscles.get(muscle), 0) - self._to_int(gain, 0))
        else:
            new_status = "done"
            xp += workout_xp
            total_sets += workout_sets
            workouts_count += 1
            for muscle, gain in workout_muscles.items():
                muscles[muscle] = self._to_int(muscles.get(muscle), 0) + self._to_int(gain, 0)

        self.client.table("progress").update(
            {
                "xp": xp,
                "total_sets": total_sets,
                "workouts_count": workouts_count,
                "muscles": muscles,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", user_id).execute()

        self.client.table("workouts").update({"status": new_status}).eq("id", workout_id).eq("user_id", user_id).execute()
        return new_status

    def update_workout_entry(
        self,
        user_id: int,
        workout_id: int,
        weight: float,
        reps: int,
        sets_count: int,
        rest_seconds: int,
        rest_pattern: Optional[List[int]],
    ) -> bool:
        card = self.get_workout_card(user_id=user_id, workout_id=workout_id)
        if not card or not card.get("workout_item_id"):
            return False

        payload: Dict[str, Any] = {
            "weight": weight,
            "reps": reps,
            "sets_count": sets_count,
            "rest_seconds": rest_seconds,
            "rest_pattern": rest_pattern,
        }
        self.client.table("sets").update(payload).eq("workout_item_id", int(card["workout_item_id"])).execute()

        title = _build_workout_title(
            exercise_name=str(card.get("exercise_name") or "Тренировка"),
            weight=weight,
            reps=reps,
            sets_count=sets_count,
            mode=str(card.get("mode") or "strength"),
            rest_seconds=rest_seconds,
            rest_pattern=rest_pattern,
        )
        self.client.table("workouts").update({"title": title}).eq("id", workout_id).eq("user_id", user_id).execute()
        return True




    def update_workout_entry_with_recalc(
        self,
        user_id: int,
        workout_id: int,
        new_weight: float,
        new_reps: int,
        new_sets_count: int,
        new_rest_seconds: int,
        new_rest_pattern: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        workout_res = (
            self.client.table("workouts")
            .select("id,user_id,status,total_xp,total_sets,muscle_delta,mode")
            .eq("id", workout_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not workout_res.data:
            raise RuntimeError("Workout not found")
        workout = workout_res.data[0] or {}

        item_res = (
            self.client.table("workout_items")
            .select("id,exercise_id")
            .eq("workout_id", workout_id)
            .order("order_index", desc=False)
            .limit(1)
            .execute()
        )
        if not item_res.data:
            raise RuntimeError("Workout item not found")
        item = item_res.data[0] or {}

        set_res = (
            self.client.table("sets")
            .select("id")
            .eq("workout_item_id", int(item.get("id") or 0))
            .order("id", desc=False)
            .limit(1)
            .execute()
        )
        if not set_res.data:
            raise RuntimeError("Workout set not found")
        set_row = set_res.data[0] or {}

        exercise = self.get_exercise(int(item.get("exercise_id") or 0))
        exercise_name = str(exercise.get("display_name") or "Тренировка")

        status = str(workout.get("status") or "planned")
        old_total_xp = self._to_int(workout.get("total_xp"), 0)
        old_total_sets = self._to_int(workout.get("total_sets"), 0)
        old_muscle_delta = workout.get("muscle_delta") if isinstance(workout.get("muscle_delta"), dict) else {}

        progress = None
        xp = 0
        level = 1
        total_sets = 0
        muscles: Dict[str, int] = {}

        if status == "done":
            progress = self.get_progress(user_id)
            xp = self._to_int(progress.get("xp"), 0)
            level = max(1, self._to_int(progress.get("level"), 1))
            total_sets = self._to_int(progress.get("total_sets"), 0)
            muscles_raw = progress.get("muscles") if isinstance(progress.get("muscles"), dict) else {}
            muscles = {str(k): self._to_int(v, 0) for k, v in muscles_raw.items()}

            xp = max(0, xp - old_total_xp)
            total_sets = max(0, total_sets - old_total_sets)
            for muscle, gain in old_muscle_delta.items():
                muscles[str(muscle)] = max(0, self._to_int(muscles.get(str(muscle)), 0) - self._to_int(gain, 0))

        weight_val = self._to_float(new_weight, 0.0)
        reps_val = self._to_int(new_reps, 0)
        sets_val = self._to_int(new_sets_count, 0)
        new_total_xp, new_muscle_delta, new_total_sets = self.compute_delta(
            exercise_id=int(item.get("exercise_id") or 0),
            weight=weight_val,
            reps=reps_val,
            sets_count=sets_val,
        )

        self.client.table("sets").update(
            {
                "weight": weight_val,
                "reps": reps_val,
                "sets_count": sets_val,
                "rest_seconds": int(max(0, new_rest_seconds)),
                "rest_pattern": new_rest_pattern if isinstance(new_rest_pattern, list) else None,
            }
        ).eq("id", int(set_row.get("id") or 0)).execute()

        title = _build_workout_title(
            exercise_name=exercise_name,
            weight=weight_val,
            reps=reps_val,
            sets_count=sets_val,
            mode=str(workout.get("mode") or "strength"),
            rest_seconds=int(max(0, new_rest_seconds)),
            rest_pattern=new_rest_pattern if isinstance(new_rest_pattern, list) else None,
        )

        self.client.table("workouts").update(
            {
                "title": title,
                "total_xp": int(new_total_xp),
                "total_sets": int(new_total_sets),
                "muscle_delta": new_muscle_delta,
            }
        ).eq("id", workout_id).eq("user_id", user_id).execute()

        if status == "done" and progress is not None:
            xp += int(new_total_xp)
            total_sets += int(new_total_sets)
            for muscle, gain in new_muscle_delta.items():
                muscles[muscle] = self._to_int(muscles.get(muscle), 0) + self._to_int(gain, 0)

            def xp_to_next(level_value: int) -> int:
                return 100 + level_value * 25

            while xp >= xp_to_next(level):
                xp -= xp_to_next(level)
                level += 1

            self.client.table("progress").update(
                {
                    "xp": int(xp),
                    "level": int(level),
                    "total_sets": int(total_sets),
                    "muscles": muscles,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("user_id", user_id).execute()

        return {
            "status": status,
            "old_total_xp": int(old_total_xp),
            "new_total_xp": int(new_total_xp),
            "new_title": title,
            "new_muscle_delta": new_muscle_delta,
        }
    def get_workout_header(self, user_id: int, workout_id: int) -> Optional[Dict[str, Any]]:
        card = self.get_workout_card(user_id=user_id, workout_id=workout_id)
        if not card:
            return None
        return {
            "id": card.get("id"),
            "workout_date": card.get("workout_date"),
            "title": card.get("title"),
            "mode": card.get("mode"),
            "status": card.get("status"),
        }

    def get_workout_single_item(self, user_id: int, workout_id: int) -> Optional[Dict[str, Any]]:
        card = self.get_workout_card(user_id=user_id, workout_id=workout_id)
        if not card:
            return None
        return {
            "workout_item_id": card.get("workout_item_id"),
            "exercise_id": card.get("exercise_id"),
            "exercise_name": card.get("exercise_name"),
            "weight": card.get("weight"),
            "reps": card.get("reps"),
            "sets_count": card.get("sets_count"),
            "rest_seconds": card.get("rest_seconds"),
            "rest_pattern": card.get("rest_pattern"),
        }

    def update_workout_status(self, user_id: int, workout_id: int, status: str) -> bool:
        self.client.table("workouts").update({"status": status}).eq("id", workout_id).eq("user_id", user_id).execute()
        return True

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
                .select("id,name,name_ru")
                .in_("id", exercise_ids)
                .execute()
            )
            exercise_names = {int(row["id"]): self._exercise_display_name(row) for row in (ex_res.data or [])}

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
            exercise_id = int(item.get("exercise_id") or 0)
            exercise_name = exercise_names.get(exercise_id, "Упражнение")
            if not sets_rows:
                result_items.append(
                    {
                        "exercise_id": item.get("exercise_id"),
                        "exercise_name": exercise_name,
            "display_name": exercise_name,
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
                        "exercise_name": exercise_name,
            "display_name": exercise_name,
                        "weight": set_row.get("weight") or 0,
                        "reps": set_row.get("reps") or 0,
                        "sets_count": set_row.get("sets_count") or 0,
                        "rest_seconds": set_row.get("rest_seconds") or 0,
                        "rest_pattern": set_row.get("rest_pattern"),
                    }
                )

        first_item = result_items[0] if result_items else {
            "exercise_name": "Упражнение",
            "weight": 0,
            "reps": 0,
            "sets_count": 0,
            "rest_seconds": 0,
            "rest_pattern": None,
        }
        return {"workout": workout, "item": first_item, "items": result_items}

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

    def update_user_units(self, user_id: int, units: str) -> None:
        self.client.table("users").update({"units": units}).eq("id", user_id).execute()

    def update_user_timezone(self, user_id: int, timezone_value: str) -> None:
        self.client.table("users").update({"timezone": timezone_value}).eq("id", user_id).execute()

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

    @staticmethod
    def format_delta(total_xp: int, muscle_delta: Dict[str, int]) -> str:
        xp = int(total_xp or 0)
        lines = [f"XP: {xp:+d}"]
        if isinstance(muscle_delta, dict) and muscle_delta:
            top = sorted(
                ((str(m), int(v or 0)) for m, v in muscle_delta.items() if int(v or 0) != 0),
                key=lambda x: abs(x[1]),
                reverse=True,
            )[:3]
            if top:
                lines.append("Изменения по мышцам:")
                lines.extend([f"- {m}: {v:+d}" for m, v in top])
        return "\n".join(lines)

    def get_workout_payload_item(self, user_id: int, workout_id: int) -> Dict[str, Any]:
        card = self.get_workout_card(user_id=user_id, workout_id=workout_id)
        if not card:
            raise RuntimeError("Workout not found")
        return {
            "exercise_id": int(card.get("exercise_id") or 0),
            "weight": float(card.get("weight") or 0),
            "reps": int(card.get("reps") or 0),
            "sets_count": int(card.get("sets_count") or 0),
            "rest_seconds": int(card.get("rest_seconds") or 0),
            "rest_pattern": card.get("rest_pattern") if isinstance(card.get("rest_pattern"), list) else None,
        }

    def append_to_template(self, user_id: int, template_id: int, item: Dict[str, Any]) -> bool:
        template = self.get_template(user_id=user_id, template_id=template_id)
        if not template:
            return False
        payload = template.get("payload") if isinstance(template.get("payload"), list) else []
        payload.append(
            {
                "exercise_id": int(item.get("exercise_id") or 0),
                "weight": float(item.get("weight") or 0),
                "reps": int(item.get("reps") or 0),
                "sets_count": int(item.get("sets_count") or 0),
                "rest_seconds": int(item.get("rest_seconds") or 0),
                "rest_pattern": item.get("rest_pattern") if isinstance(item.get("rest_pattern"), list) else None,
            }
        )
        self.client.table("templates").update({"payload": payload}).eq("id", template_id).eq("user_id", user_id).execute()
        return True

    def compute_delta(self, exercise_id: int, weight: float, reps: int, sets_count: int) -> tuple[int, Dict[str, int], int]:
        exercise = self.get_exercise(exercise_id)
        weight_val = self._to_float(weight, 0.0)
        reps_val = self._to_int(reps, 0)
        sets_val = self._to_int(sets_count, 0)
        volume = weight_val * reps_val * sets_val
        load_points = math.sqrt(max(0.0, volume))
        total_xp = max(5, round(load_points * 0.8))

        muscle_map = exercise.get("muscle_map") or {}
        primary_muscle = exercise.get("primary_muscle")
        if not isinstance(muscle_map, dict) or not muscle_map:
            muscle_map = {primary_muscle: 1.0} if primary_muscle else {}

        muscle_delta: Dict[str, int] = {}
        for muscle, coeff in muscle_map.items():
            if muscle is None:
                continue
            gain = round(load_points * float(coeff))
            if gain <= 0:
                continue
            muscle_delta[str(muscle)] = int(muscle_delta.get(str(muscle), 0)) + int(gain)
        return int(total_xp), muscle_delta, int(sets_val)

    def compute_delta_from_payload(self, payload_items: List[Dict[str, Any]]) -> tuple[int, Dict[str, int], int]:
        total_xp = 0
        total_sets = 0
        muscle_delta: Dict[str, int] = {}
        for item in payload_items:
            ex_id = item.get("exercise_id")
            if ex_id is None:
                continue
            xp_item, muscle_item, sets_item = self.compute_delta(
                exercise_id=int(ex_id),
                weight=float(item.get("weight") or 0),
                reps=int(item.get("reps") or 0),
                sets_count=int(item.get("sets_count") or 0),
            )
            total_xp += int(xp_item)
            total_sets += int(sets_item)
            for muscle, gain in muscle_item.items():
                muscle_delta[muscle] = int(muscle_delta.get(muscle, 0)) + int(gain)
        return int(total_xp), muscle_delta, int(total_sets)

    def create_workout_from_template(self, user_id: int, template_row: Dict[str, Any], title: Optional[str] = None) -> int:
        workout_title = title or str(template_row.get("name") or "Template")
        workout_date = datetime.now(timezone.utc).date().isoformat()
        workout_id = self.create_workout(user_id=user_id, title=workout_title, mode="template", workout_date=workout_date, status="planned")

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

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            if value is None:
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def check_and_award_achievements(self, user_id: int) -> List[str]:
        progress_res = (
            self.client.table("progress")
            .select("user_id,workouts_count,total_sets,muscles,achievements")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not progress_res.data:
            return []

        progress = progress_res.data[0] or {}
        workouts_count = self._to_int(progress.get("workouts_count"), 0)
        total_sets = self._to_int(progress.get("total_sets"), 0)

        muscles_raw = progress.get("muscles")
        muscles = muscles_raw if isinstance(muscles_raw, dict) else {}
        legs = self._to_int(muscles.get("legs"), 0)
        chest = self._to_int(muscles.get("chest"), 0)
        back = self._to_int(muscles.get("back"), 0)

        achievements_raw = progress.get("achievements")
        current_ids = [str(a) for a in achievements_raw if isinstance(a, str)] if isinstance(achievements_raw, list) else []
        current_set = set(current_ids)

        unlocked: List[str] = []
        if workouts_count >= 1:
            unlocked.append("first_workout")
        if workouts_count >= 10:
            unlocked.append("workouts_10")
        if workouts_count >= 30:
            unlocked.append("workouts_30")
        if total_sets >= 100:
            unlocked.append("sets_100")
        if legs >= 100:
            unlocked.append("legs_100")
        if chest >= 100:
            unlocked.append("chest_100")
        if back >= 100:
            unlocked.append("back_100")

        streak_unlocked = False
        try:
            streak_rows = (
                self.client.table("workouts")
                .select("workout_date")
                .eq("user_id", user_id)
                .eq("status", "done")
                .order("workout_date", desc=True)
                .limit(30)
                .execute()
            ).data or []
            days = sorted({str(row.get("workout_date")) for row in streak_rows if row.get("workout_date")})
            run = 1
            for i in range(1, len(days)):
                prev = datetime.fromisoformat(days[i - 1]).date()
                cur = datetime.fromisoformat(days[i]).date()
                if (cur - prev).days == 1:
                    run += 1
                    if run >= 3:
                        streak_unlocked = True
                        break
                elif cur != prev:
                    run = 1
        except Exception:
            log.exception("check streak failed")

        if streak_unlocked:
            unlocked.append("streak_3")

        new_achievements = [aid for aid in unlocked if aid not in current_set]
        if not new_achievements:
            return []

        updated_ids = current_ids + new_achievements
        self.client.table("progress").update(
            {
                "achievements": updated_ids,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", user_id).execute()
        return new_achievements

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

        xp_gain, muscle_delta, sets_val = self.compute_delta(
            exercise_id=exercise_id,
            weight=weight,
            reps=reps,
            sets_count=sets_count,
        )

        muscles = progress.get("muscles") or {}
        if not isinstance(muscles, dict):
            muscles = {}

        for muscle, gain in muscle_delta.items():
            muscles[muscle] = int(muscles.get(muscle, 0)) + int(gain)

        def xp_to_next(level: int) -> int:
            return 100 + level * 25

        xp_new = self._to_int(progress.get("xp"), 0) + int(xp_gain)
        level_new = max(1, self._to_int(progress.get("level"), 1))
        while xp_new >= xp_to_next(level_new):
            xp_new -= xp_to_next(level_new)
            level_new += 1

        workouts_count = self._to_int(progress.get("workouts_count"), 0) + 1
        total_sets = self._to_int(progress.get("total_sets"), 0) + sets_val

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

        muscle_gains_sorted_top3 = sorted(muscle_delta.items(), key=lambda x: x[1], reverse=True)[:3]
        return {
            "xp_gain": int(xp_gain),
            "level_new": int(level_new),
            "xp_new": int(xp_new),
            "xp_to_next": int(xp_to_next(level_new)),
            "muscle_gains_sorted_top3": muscle_gains_sorted_top3,
            "muscle_delta": muscle_delta,
            "total_sets_for_workout": sets_val,
        }
