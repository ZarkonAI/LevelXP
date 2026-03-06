from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

SOURCE = "free-exercise-db"
EXERCISES_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMAGE_PREFIX = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"

CANONICAL_MUSCLES = ("legs", "back", "chest", "shoulders", "arms", "core")
MUSCLE_ALIASES = {
    "quadriceps": "legs",
    "hamstrings": "legs",
    "calves": "legs",
    "glutes": "legs",
    "lats": "back",
    "lower back": "back",
    "middle back": "back",
    "traps": "back",
    "chest": "chest",
    "pectorals": "chest",
    "shoulders": "shoulders",
    "deltoids": "shoulders",
    "biceps": "arms",
    "triceps": "arms",
    "forearms": "arms",
    "abdominals": "core",
    "abs": "core",
    "obliques": "core",
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
    response = requests.get(EXERCISES_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected payload type: expected list")
    return payload


def normalize_muscle(muscle_name: Any) -> Optional[str]:
    if not muscle_name:
        return None
    normalized = str(muscle_name).strip().lower()
    return MUSCLE_ALIASES.get(normalized)


def build_muscle_fields(exercise: Dict[str, Any]) -> Tuple[str, Dict[str, float]]:
    primary_source = exercise.get("primaryMuscles")
    secondary_source = exercise.get("secondaryMuscles")

    primary_candidates = primary_source if isinstance(primary_source, list) else []
    secondary_candidates = secondary_source if isinstance(secondary_source, list) else []

    primary_group: Optional[str] = None
    for muscle in primary_candidates:
        mapped = normalize_muscle(muscle)
        if mapped:
            primary_group = mapped
            break

    if not primary_group:
        return "core", {"core": 1.0}

    muscle_map: Dict[str, float] = {primary_group: 1.0}

    added_secondary = 0
    for muscle in secondary_candidates:
        if added_secondary >= 3:
            break
        mapped = normalize_muscle(muscle)
        if not mapped or mapped == primary_group:
            continue
        if mapped in muscle_map:
            continue
        muscle_map[mapped] = 0.3
        added_secondary += 1

    return primary_group, muscle_map


def get_image_url(exercise: Dict[str, Any]) -> Optional[str]:
    images = exercise.get("images")
    if not isinstance(images, list) or not images:
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

    primary_muscle, muscle_map = build_muscle_fields(exercise)

    category = exercise.get("category")
    if not category:
        category = "strength"

    secondary_muscles = exercise.get("secondaryMuscles")
    instructions = exercise.get("instructions")

    return {
        "owner_user_id": None,
        "source": SOURCE,
        "source_ref": source_ref,
        "name": str(exercise.get("name") or "").strip() or f"Exercise {source_ref}",
        "equipment": exercise.get("equipment"),
        "category": str(category),
        "secondary_muscles": secondary_muscles if isinstance(secondary_muscles, list) else [],
        "instructions": instructions if isinstance(instructions, list) else [],
        "image_url": get_image_url(exercise),
        "primary_muscle": primary_muscle if primary_muscle in CANONICAL_MUSCLES else "core",
        "muscle_map": muscle_map,
    }


def upsert_exercise(client: Client, row: Dict[str, Any]) -> str:
    source_ref = row["source_ref"]

    existing = (
        client.table("exercises")
        .select("id")
        .eq("source", SOURCE)
        .eq("source_ref", source_ref)
        .limit(1)
        .execute()
    )

    if existing.data:
        exercise_id = existing.data[0]["id"]
        client.table("exercises").update(row).eq("id", exercise_id).execute()
        return "updated"

    client.table("exercises").insert(row).execute()
    return "inserted"


def run(limit: Optional[int]) -> None:
    client = get_supabase_client()
    exercises = load_exercises()

    if limit is not None:
        exercises = exercises[:limit]

    inserted = 0
    updated = 0
    failed = 0

    for idx, exercise in enumerate(exercises, start=1):
        try:
            row = build_row(exercise)
            result = upsert_exercise(client, row)
            if result == "inserted":
                inserted += 1
            else:
                updated += 1
        except Exception as exc:
            failed += 1
            ex_id = exercise.get("id") if isinstance(exercise, dict) else "unknown"
            print(f"[ERROR] exercise #{idx} id={ex_id}: {exc}")

        if idx % 50 == 0:
            print(f"Progress: {idx}/{len(exercises)} | inserted={inserted} updated={updated} failed={failed}")

    print("Done.")
    print(f"Total: {len(exercises)} | inserted={inserted} updated={updated} failed={failed}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed global exercises from yuhonas/free-exercise-db")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of imported exercises")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.limit)
