from __future__ import annotations

import argparse
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

SOURCE = "free-exercise-db"
EXERCISES_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMAGE_PREFIX = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
BATCH_SIZE = 50

CANONICAL_MUSCLES = ("legs", "back", "chest", "shoulders", "arms", "core")
MUSCLE_ALIASES = {
    "quadriceps": "legs",
    "hamstrings": "legs",
    "calves": "legs",
    "glutes": "legs",
    "abductors": "legs",
    "adductors": "legs",
    "lats": "back",
    "lower back": "back",
    "middle back": "back",
    "traps": "back",
    "neck": "back",
    "chest": "chest",
    "shoulders": "shoulders",
    "biceps": "arms",
    "triceps": "arms",
    "forearms": "arms",
    "abdominals": "core",
}


def get_supabase_client() -> Client:
    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

    if not supabase_url:
        raise RuntimeError("Missing required env var: SUPABASE_URL")
    if not supabase_key:
        raise RuntimeError("Missing required env var: SUPABASE_SERVICE_KEY or SUPABASE_KEY")

    return create_client(supabase_url, supabase_key)


def load_exercises() -> List[Dict[str, Any]]:
    response = requests.get(EXERCISES_URL, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected payload type: expected list")
    return payload


def normalize_muscle(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return MUSCLE_ALIASES.get(normalized)


def build_muscle_fields(exercise: Dict[str, Any]) -> Tuple[str, Dict[str, float]]:
    primary_source = exercise.get("primaryMuscles") if isinstance(exercise.get("primaryMuscles"), list) else []
    secondary_source = exercise.get("secondaryMuscles") if isinstance(exercise.get("secondaryMuscles"), list) else []

    primary_groups = [normalize_muscle(item) for item in primary_source]
    primary_groups = [group for group in primary_groups if group]

    if primary_groups:
        primary_group = Counter(primary_groups).most_common(1)[0][0]
    else:
        primary_group = "core"

    muscle_map: Dict[str, float] = {primary_group: 1.0}

    secondary_groups = [normalize_muscle(item) for item in secondary_source]
    secondary_groups = [group for group in secondary_groups if group and group != primary_group]
    for group in secondary_groups:
        if len([k for k, v in muscle_map.items() if v == 0.3]) >= 3:
            break
        if group in muscle_map:
            continue
        muscle_map[group] = 0.3

    if not muscle_map:
        return "core", {"core": 1.0}

    return primary_group if primary_group in CANONICAL_MUSCLES else "core", muscle_map


def get_image_url(images: List[Any]) -> Optional[str]:
    if not images:
        return None
    first = images[0]
    if not first:
        return None
    first_path = str(first).lstrip("/")
    return f"{IMAGE_PREFIX}{first_path}"


def build_row(exercise: Dict[str, Any]) -> Dict[str, Any]:
    source_ref = str(exercise.get("id") or "").strip()
    if not source_ref:
        raise ValueError("exercise id is missing")

    primary_muscles_raw = exercise.get("primaryMuscles") if isinstance(exercise.get("primaryMuscles"), list) else []
    secondary_muscles = exercise.get("secondaryMuscles") if isinstance(exercise.get("secondaryMuscles"), list) else []
    instructions = exercise.get("instructions") if isinstance(exercise.get("instructions"), list) else []
    images = exercise.get("images") if isinstance(exercise.get("images"), list) else []

    primary_muscle, muscle_map = build_muscle_fields(exercise)

    return {
        "source": SOURCE,
        "source_ref": source_ref,
        "owner_user_id": None,
        "name": str(exercise.get("name") or "").strip() or f"Exercise {source_ref}",
        "level": exercise.get("level"),
        "mechanic": exercise.get("mechanic"),
        "force": exercise.get("force"),
        "equipment": exercise.get("equipment"),
        "category": exercise.get("category"),
        "primary_muscles_raw": primary_muscles_raw,
        "secondary_muscles": secondary_muscles,
        "instructions": instructions,
        "images": images,
        "image_url": get_image_url(images),
        "primary_muscle": primary_muscle,
        "muscle_map": muscle_map,
    }


def upsert_batch(client: Client, batch: List[Dict[str, Any]]) -> None:
    client.table("exercises").upsert(batch, on_conflict="source,source_ref").execute()


def run(limit: Optional[int], dry_run: bool) -> None:
    exercises = load_exercises()
    if limit is not None:
        exercises = exercises[:limit]

    rows: List[Dict[str, Any]] = []
    failed = 0
    for idx, exercise in enumerate(exercises, start=1):
        try:
            rows.append(build_row(exercise))
        except Exception as exc:
            failed += 1
            ex_id = exercise.get("id") if isinstance(exercise, dict) else "unknown"
            print(f"[ERROR] exercise #{idx} id={ex_id}: {exc}")

    print(f"Prepared rows: {len(rows)} | failed={failed}")

    muscle_stats = Counter(row.get("primary_muscle") for row in rows)
    print(f"Primary muscle stats: {dict(muscle_stats)}")

    if dry_run:
        print("Dry-run enabled: no DB changes were made.")
        return

    client = get_supabase_client()
    total = len(rows)
    for start in range(0, total, BATCH_SIZE):
        batch = rows[start : start + BATCH_SIZE]
        upsert_batch(client, batch)
        end = min(start + BATCH_SIZE, total)
        print(f"Upserted: {end}/{total}")

    print("Done.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed global exercises from yuhonas/free-exercise-db")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of imported exercises")
    parser.add_argument("--dry-run", action="store_true", help="Build and print stats without DB writes")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
