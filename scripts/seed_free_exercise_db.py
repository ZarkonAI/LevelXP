from __future__ import annotations

import argparse
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

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


class TranslationService:
    def __init__(self) -> None:
        from argostranslate import package, translate

        self._package = package
        self._translate = translate
        self._cache: Dict[str, str] = {}
        self.translated_strings = 0
        self.cache_hits = 0

    def ensure_en_ru_package(self) -> None:
        from_code = "en"
        to_code = "ru"

        ap = self._package  # <-- ВОТ ЭТОГО не хватало

        # 1) обновить индекс пакетов
        ap.update_package_index()

        # 2) если пакет уже установлен — выходим
        installed = ap.get_installed_packages()
        if any(p.from_code == from_code and p.to_code == to_code for p in installed):
            return

        # 3) найти доступный пакет en->ru, скачать и установить
        available = ap.get_available_packages()
        pkg = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)
        if not pkg:
            raise RuntimeError("Не найден пакет перевода en->ru в индексе Argos Translate")

        ap.install_from_path(pkg.download())

    def translate_text(self, text: str) -> str:
        clean_text = text.strip()
        if not clean_text:
            return clean_text
        if clean_text in self._cache:
            self.cache_hits += 1
            return self._cache[clean_text]

        translated = self._translate.translate(clean_text, "en", "ru")
        self._cache[clean_text] = translated
        self.translated_strings += 1
        return translated

    def translate_lines(self, lines: List[Any]) -> List[str]:
        translated_lines: List[str] = []
        for line in lines:
            translated_lines.append(self.translate_text(str(line)))
        return translated_lines


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


def build_row(
    exercise: Dict[str, Any],
    translator: TranslationService,
    translate_instructions: bool,
) -> Dict[str, Any]:
    source_ref = str(exercise.get("id") or "").strip()
    if not source_ref:
        raise ValueError("exercise id is missing")

    primary_muscles_raw = exercise.get("primaryMuscles") if isinstance(exercise.get("primaryMuscles"), list) else []
    secondary_muscles = exercise.get("secondaryMuscles") if isinstance(exercise.get("secondaryMuscles"), list) else []
    instructions_en = exercise.get("instructions") if isinstance(exercise.get("instructions"), list) else []
    images = exercise.get("images") if isinstance(exercise.get("images"), list) else []
    name_en = str(exercise.get("name") or "").strip() or f"Exercise {source_ref}"
    name_ru = translator.translate_text(name_en)

    if translate_instructions:
        instructions = translator.translate_lines(instructions_en)
    else:
        instructions = instructions_en

    primary_muscle, muscle_map = build_muscle_fields(exercise)

    return {
        "source": SOURCE,
        "source_ref": source_ref,
        "owner_user_id": None,
        "name": name_ru,
        "name_en": name_en,
        "level": exercise.get("level"),
        "mechanic": exercise.get("mechanic"),
        "force": exercise.get("force"),
        "equipment": exercise.get("equipment"),
        "category": exercise.get("category"),
        "primary_muscles_raw": primary_muscles_raw,
        "secondary_muscles": secondary_muscles,
        "instructions": instructions,
        "instructions_en": instructions_en,
        "images": images,
        "image_url": get_image_url(images),
        "primary_muscle": primary_muscle,
        "muscle_map": muscle_map,
    }


def upsert_batch(client: Client, batch: List[Dict[str, Any]]) -> None:
    client.table("exercises").upsert(batch, on_conflict="source,source_ref").execute()


def get_existing_refs(client: Client, source_refs: List[str]) -> Set[str]:
    existing: Set[str] = set()
    for start in range(0, len(source_refs), BATCH_SIZE):
        chunk = source_refs[start : start + BATCH_SIZE]
        response = (
            client.table("exercises")
            .select("source_ref")
            .eq("source", SOURCE)
            .in_("source_ref", chunk)
            .execute()
        )
        existing.update(str(item["source_ref"]) for item in response.data or [] if item.get("source_ref"))
    return existing


def run(limit: Optional[int], dry_run: bool, translate_instructions: bool) -> None:
    exercises = load_exercises()
    if limit is not None:
        exercises = exercises[:limit]

    translator = TranslationService()
    translator.ensure_en_ru_package()

    rows: List[Dict[str, Any]] = []
    failed = 0
    for idx, exercise in enumerate(exercises, start=1):
        try:
            rows.append(build_row(exercise, translator=translator, translate_instructions=translate_instructions))
        except Exception as exc:
            failed += 1
            ex_id = exercise.get("id") if isinstance(exercise, dict) else "unknown"
            print(f"[ERROR] exercise #{idx} id={ex_id}: {exc}")

    print(f"Prepared rows: {len(rows)} | failed={failed}")

    muscle_stats = Counter(row.get("primary_muscle") for row in rows)
    print(f"Primary muscle stats: {dict(muscle_stats)}")

    if dry_run:
        print("Dry-run enabled: no DB changes were made.")
        print(
            "Translation stats: "
            f"translated={translator.translated_strings}, cache_hits={translator.cache_hits}"
        )
        return

    client = get_supabase_client()
    existing_refs = get_existing_refs(client, [row["source_ref"] for row in rows])
    inserted = 0
    updated = 0
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        try:
            was_existing = row["source_ref"] in existing_refs
            upsert_batch(client, [row])
            if was_existing:
                updated += 1
            else:
                inserted += 1
                existing_refs.add(row["source_ref"])
        except Exception as exc:
            failed += 1
            print(f"[ERROR] upsert failed for source_ref={row.get('source_ref')}: {exc}")
        if idx % BATCH_SIZE == 0 or idx == total:
            print(f"Processed upserts: {idx}/{total}")

    print(
        "Done. "
        f"inserted={inserted}, updated={updated}, failed={failed}, "
        f"translated={translator.translated_strings}, cache_hits={translator.cache_hits}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed global exercises from yuhonas/free-exercise-db")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of imported exercises")
    parser.add_argument("--dry-run", action="store_true", help="Build and print stats without DB writes")
    parser.add_argument(
        "--translate-instructions",
        action="store_true",
        help="Translate instruction lines from EN to RU (slower)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(
        limit=args.limit,
        dry_run=args.dry_run,
        translate_instructions=args.translate_instructions,
    )
