import logging
import re
from typing import List, Optional
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from app import db as db_module
from app import texts
from app.keyboards import back_cancel_kb, confirm_kb, exercise_card_kb, exercise_category_kb, exercises_kb, main_menu_kb, mode_kb, muscle_choice_kb, translate_exercise_actions_kb
from app.keyboards_inline import actions_inline_kb, category_inline_kb, custom_primary_muscle_inline_kb, exercises_inline_kb, mode_inline_kb, search_prompt_inline_kb, search_results_inline_kb, training_start_inline_kb
from app.states import QuickLogStates, TranslateStates
log = logging.getLogger("handlers.training")
router = Router()
MUSCLE_MAP = {
    "🦵 Ноги": "legs",
    "🧱 Спина": "back",
    "🫀 Грудь": "chest",
    "🧍 Плечи": "shoulders",
    "💪 Руки": "arms",
    "🎯 Кор": "core",
}
MODE_STRENGTH = "🏋️ Силовая (одинаковый отдых)"
MODE_PATTERN = "🔁 Отдых по подходам"
MUSCLE_LABELS = {"legs": "🦵 Ноги", "core": "🎯 Кор", "back": "🧱 Спина", "chest": "🫀 Грудь", "shoulders": "🧍 Плечи", "arms": "💪 Руки"}

async def _send_exercise_media(message: Message, display_name: str, image_url: str, *, required: bool = False):
    if image_url:
        try:
            await message.answer_photo(photo=image_url, caption=texts.TECHNIQUE_CAPTION.format(display_name=display_name))
            return
        except Exception:
            await message.answer(f"{display_name}\n{texts.TECHNIQUE_LINK_PREFIX} {image_url}")
            return
    if required:
        await message.answer(texts.TRANSLATE_IMAGE_MISSING)


async def _show_selected_exercise_card(message: Message, state: FSMContext, db, *, show_status: bool = False, status_text: str | None = None):
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        await _show_choose_exercise(message, state)
        return

    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    is_admin = db.is_admin(user)
    is_favorite = db.is_favorite(user_id=int(user["id"]), exercise_id=int(exercise_id))
    is_featured = bool(data.get("exercise_is_featured"))
    if show_status:
        info_text = status_text or (texts.FAVORITE_REMOVED if not is_favorite else texts.FAVORITE_ADDED)
        await message.answer(info_text)

    updated = False
    wizard_message_id = data.get("wizard_message_id")
    wizard_chat_id = data.get("wizard_chat_id")
    if wizard_message_id and wizard_chat_id:
        try:
            await message.bot.edit_message_text(
                chat_id=int(wizard_chat_id),
                message_id=int(wizard_message_id),
                text=texts.EXERCISE_CARD_HINT,
                reply_markup=actions_inline_kb(is_favorite=is_favorite, is_admin=is_admin, is_featured=is_featured),
            )
            updated = True
        except Exception:
            updated = False
    if not updated:
        msg_actions = await message.answer(
            texts.EXERCISE_CARD_HINT,
            reply_markup=actions_inline_kb(is_favorite=is_favorite, is_admin=is_admin, is_featured=is_featured),
        )
        await state.update_data(wizard_message_id=msg_actions.message_id, wizard_chat_id=msg_actions.chat.id)

    await state.set_state(QuickLogStates.choose_exercise_inline)
    await state.update_data(wizard_step="exercise_card")

async def _render_last_category_exercises(message: Message, state: FSMContext):
    data = await state.get_data()
    ex_map = data.get("last_ex_map") or data.get("ex_map") or {}
    exercises = []
    for key in sorted(ex_map.keys(), key=lambda value: int(value) if str(value).isdigit() else 9999):
        row = ex_map.get(key) or {}
        exercises.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "name_ru": row.get("name_ru"),
                "image_url": row.get("image_url"),
                "display_name": row.get("display_name"),
                "primary_muscle": row.get("primary_muscle"),
                "muscle_map": row.get("muscle_map"),
                "equipment": row.get("equipment"),
                "weight_mode": row.get("weight_mode"),
                "xp_mult": row.get("xp_mult"),
                "is_featured": bool(row.get("is_featured")),
            }
        )
    await state.update_data(exercises=exercises, ex_map=ex_map, selected_category=data.get("last_category") or data.get("selected_category"))
    await state.set_state(QuickLogStates.choose_exercise)
    await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises, translate_mode=data.get("translate_mode") is True))


def _format_equipment(equipment: object) -> str:
    if isinstance(equipment, list):
        values = [str(item).strip() for item in equipment if str(item).strip()]
        return ", ".join(values) if values else "-"
    text = str(equipment or "").strip()
    return text or "-"


def _format_muscles(primary_muscle: str | None, muscle_map: object) -> str:
    primary = str(primary_muscle or "").strip().lower()
    labels = []
    if primary:
        labels.append(MUSCLE_LABELS.get(primary, primary))
    if isinstance(muscle_map, dict):
        secondary = sorted(
            [
                (str(m).strip().lower(), float(coeff or 0))
                for m, coeff in muscle_map.items()
                if str(m).strip().lower() != primary
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        for muscle, _ in secondary[:2]:
            labels.append(MUSCLE_LABELS.get(muscle, muscle))
    return ", ".join(labels) if labels else "—"


def _extract_points(raw_instructions: object) -> list[str]:
    points: list[str] = []
    if isinstance(raw_instructions, list):
        points = [str(item).strip(" -•\n\t") for item in raw_instructions if str(item).strip()]
    elif isinstance(raw_instructions, str):
        parts = re.split(r"[\n\r]+|\s*\d+[\)\.]\s*|\s*[•\-]\s*", raw_instructions)
        points = [part.strip() for part in parts if part and part.strip()]
    return [point for point in points if point]


def _format_technique_points(exercise: dict, exercise_lang: str) -> str:
    preferred = _extract_points(exercise.get("instructions_ru")) if exercise_lang == "ru" else []
    fallback = _extract_points(exercise.get("instructions"))
    points = preferred or fallback
    if not points:
        return "—"
    shown = points[:4]
    if len(shown) < 2:
        shown = points[:2]
    return "\n".join(f"• {point}" for point in shown)


async def _send_exercise_preview(message: Message, exercise: dict, exercise_lang: str) -> Message:
    display_name = str(exercise.get("display_name") or exercise.get("name") or "Упражнение")
    caption = texts.EXERCISE_PREVIEW_TEMPLATE.format(
        display_name=display_name,
        muscles=_format_muscles(exercise.get("primary_muscle"), exercise.get("muscle_map")),
        equipment=_format_equipment(exercise.get("equipment")),
        technique=_format_technique_points(exercise, exercise_lang),
    )
    image_url = str(exercise.get("image_url") or "").strip()
    if image_url:
        try:
            return await message.answer_photo(photo=image_url, caption=caption)
        except Exception:
            return await message.answer(f"{caption}\n{texts.TECHNIQUE_LINK_PREFIX} {image_url}")
    return await message.answer(caption)


def _normalize_for_trigrams(value: str) -> str:
    clean = re.sub(r"[^\w\s\-]", " ", (value or "").lower().replace("ё", "е"), flags=re.UNICODE)
    clean = re.sub(r"_", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def trigrams(value: str) -> set[str]:
    normalized = _normalize_for_trigrams(value)
    if not normalized:
        return set()
    if len(normalized) < 3:
        return {normalized}
    return {normalized[idx : idx + 3] for idx in range(len(normalized) - 2)}


def dice(a: str, b: str) -> float:
    a_tri = trigrams(a)
    b_tri = trigrams(b)
    if not a_tri or not b_tri:
        return 0.0
    return (2 * len(a_tri.intersection(b_tri))) / (len(a_tri) + len(b_tri))


async def _load_exercises_page(state: FSMContext, db, user_id: int, *, page: int):
    data = await state.get_data()
    category = data.get("selected_category")
    all_items = db.list_exercises_active_all(user_id=user_id, primary_muscle=category)
    items, has_next, safe_page = db.list_exercises_page(all_items, page=page, page_size=12)
    await state.update_data(exercises=items, exercises_page=safe_page)
    return items, has_next, safe_page


async def _show_exercise_list_wizard(state: FSMContext, bot, db, user_id: int, *, page: int = 0):
    exercises, has_next, safe_page = await _load_exercises_page(state, db, user_id, page=page)
    if not exercises:
        await _edit_wizard_text(state, bot, texts.SEARCH_EMPTY, category_inline_kb())
        await state.set_state(QuickLogStates.choose_category)
        await state.update_data(wizard_step="choose_category")
        return
    await state.set_state(QuickLogStates.choose_exercise_inline)
    await state.update_data(wizard_step="exercise_list")
    await _edit_wizard_text(state, bot, _exercise_page_title(page=safe_page, has_next=has_next), exercises_inline_kb(exercises, page=safe_page, has_next=has_next))


def _search_exercises(exercises: list[dict], query: str) -> list[dict]:
    normalized_query = db_module.Db.normalize_search_text(query)
    if not normalized_query:
        return []
    query_tokens = db_module.Db.search_tokens(normalized_query)
    query_len = len(normalized_query)

    token_hits: list[dict] = []
    seen_ids: set[int] = set()
    for exercise in exercises:
        if db_module.Db.token_match(
            query_tokens=query_tokens,
            name=str(exercise.get("name") or ""),
            name_ru=str(exercise.get("name_ru") or ""),
        ):
            enriched = dict(exercise)
            exercise_id = int(enriched.get("id") or 0)
            if exercise_id > 0 and exercise_id not in seen_ids:
                seen_ids.add(exercise_id)
                enriched["_token_hit"] = True
                token_hits.append(enriched)

    token_hits.sort(key=lambda row: (-int(bool(row.get("is_featured"))), str(row.get("display_name") or row.get("name") or "").lower()))
    if token_hits:
        return token_hits

    fuzzy_hits: list[dict] = []
    threshold = 0.7 if query_len <= 3 else 0.62 if query_len <= 5 else 0.55
    for exercise in exercises:
        score = max(
            dice(normalized_query, str(exercise.get("name_ru") or "")),
            dice(normalized_query, str(exercise.get("name") or "")),
        )
        if score >= threshold:
            enriched = dict(exercise)
            enriched["_score"] = score
            exercise_id = int(enriched.get("id") or 0)
            if exercise_id > 0 and exercise_id not in seen_ids:
                seen_ids.add(exercise_id)
                fuzzy_hits.append(enriched)

    fuzzy_hits.sort(key=lambda row: (-float(row.get("_score") or 0), -int(bool(row.get("is_featured"))), str(row.get("display_name") or row.get("name") or "").lower()))
    return fuzzy_hits


async def _show_search_results_wizard(state: FSMContext, bot, *, page: int = 0):
    data = await state.get_data()
    all_results = data.get("search_results_all") or []
    page_items, has_next, safe_page = db_module.Db.list_exercises_page(all_results, page=page, page_size=12)
    total_pages = max((len(all_results) + 11) // 12, 1)
    await state.update_data(exercises=page_items, search_page=safe_page)
    await state.set_state(QuickLogStates.search_results)
    await state.update_data(wizard_step="search_results")
    title = texts.SEARCH_RESULTS_TITLE.format(page=safe_page + 1, total=total_pages)
    await _edit_wizard_text(state, bot, title, search_results_inline_kb(page_items, page=safe_page, has_next=has_next))


async def _send_translate_card(message: Message, exercise: dict):
    name_en = str(exercise.get("name") or exercise.get("display_name") or "Упражнение")
    image_url = str(exercise.get("image_url") or "").strip()
    text = texts.TRANSLATE_CARD_TEMPLATE.format(
        name_en=name_en,
        muscles=_format_muscles(exercise.get("primary_muscle"), exercise.get("muscle_map")),
        equipment=_format_equipment(exercise.get("equipment")),
    )
    if image_url:
        try:
            await message.answer_photo(photo=image_url, caption=text)
            return
        except Exception:
            await message.answer(f"{text}\n{texts.TECHNIQUE_LINK_PREFIX} {image_url}")
            return
    await message.answer(text)
    await message.answer(texts.TRANSLATE_IMAGE_MISSING)


async def _start_translate_for_exercise(message: Message, state: FSMContext, exercise: dict, *, waiting_input: bool = False):
    await state.update_data(
        selected_exercise_id=exercise.get("id"),
        selected_exercise_name_en=exercise.get("name") or exercise.get("display_name"),
        selected_exercise=exercise,
    )
    await _send_translate_card(message, exercise)
    if waiting_input:
        await state.set_state(TranslateStates.waiting_name_ru)
        await message.answer(texts.RU_NAME_PROMPT, reply_markup=back_cancel_kb())
        return
    await state.set_state(QuickLogStates.choose_exercise)
    await message.answer(texts.TRANSLATE_CHOOSE_ACTION, reply_markup=translate_exercise_actions_kb())


async def _show_next_untranslated(message: Message, state: FSMContext, db):
    data = await state.get_data()
    category = data.get("last_category") or data.get("selected_category")
    if not category:
        await message.answer(texts.CHOOSE_CATEGORY)
        return
    exercise = db.get_next_untranslated_exercise(category)
    if not exercise:
        await message.answer(texts.TRANSLATE_ALL_DONE, reply_markup=exercise_category_kb(translate_mode=True))
        await state.set_state(QuickLogStates.choose_category)
        return
    await _start_translate_for_exercise(message, state, exercise, waiting_input=False)


EXERCISE_PICK_RE = re.compile(r"^(\d+)\)")
def _trim_title(title: str, max_len: int = 80) -> str:
    value = (title or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"
def _build_workout_title(data: dict) -> str:
    exercise_name = str(data.get("exercise_name") or "Тренировка")
    weight = float(data.get("weight") or 0)
    reps = int(data.get("reps") or 0)
    sets_count = int(data.get("sets_count") or 0)
    if weight == 0:
        title = f"{exercise_name} · {reps}×{sets_count}"
    else:
        title = f"{exercise_name} · {weight:g}кг×{reps}×{sets_count}"
    if data.get("mode") == "pattern":
        title += " · rest pattern"
    else:
        rest_minutes = data.get("rest_minutes")
        if rest_minutes is not None:
            title += f" · rest {float(rest_minutes):g}м"
    return _trim_title(title)
def _parse_float(raw: str) -> float:
    return float(raw.strip().replace(",", "."))
def _extract_pattern_values(raw: str) -> Optional[List[float]]:
    raw = (raw or "").strip()
    if not raw:
        return []
    tokens = re.findall(r"\d+(?:[\.,]\d+)?", raw)
    if not tokens:
        return None
    return [float(token.replace(",", ".")) for token in tokens]
def _prefill_hint(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return ""
    formatted = f"{float(value):g}" if isinstance(value, float) else str(value)
    return f"\nТекущее: {formatted}{suffix}. Введи новое или отправь '.' чтобы оставить как есть"


def _weight_prompt_text(data: dict) -> str:
    weight_mode = str(data.get("weight_mode") or "external").strip().lower()
    if weight_mode == "bodyweight_plus":
        text = texts.ENTER_WEIGHT_BODYWEIGHT_PLUS
    elif weight_mode == "assist":
        text = texts.ENTER_WEIGHT_ASSIST
    else:
        text = texts.ENTER_WEIGHT_EXTERNAL
    if bool(data.get("body_weight_missing")):
        text = f"{text}\n{texts.WEIGHT_MODE_BODY_WEIGHT_WARNING}"
    return text
def _validate_name(name: str) -> bool:
    clean = (name or "").strip()
    if len(clean) < 2 or len(clean) > 60:
        return False
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9\- ]+", clean):
        return False
    low = clean.lower()
    blocked = ("http", "https", "t.me", ".com", ".ru", ".net", ".org")
    return not any(token in low for token in blocked)


async def _remember_wizard_message(state: FSMContext, message: Message):
    await state.update_data(wizard_message_id=message.message_id, wizard_chat_id=message.chat.id)


async def _edit_wizard_text(state: FSMContext, bot, text: str, reply_markup):
    data = await state.get_data()
    message_id = data.get("wizard_message_id")
    chat_id = data.get("wizard_chat_id")
    if not message_id or not chat_id:
        return
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=int(message_id), text=text, reply_markup=reply_markup)
    except Exception:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id), reply_markup=reply_markup)


async def _cleanup_wizard_messages(state: FSMContext, bot):
    data = await state.get_data()
    chat_id = data.get("wizard_chat_id")
    wizard_message_id = data.get("wizard_message_id")
    last_photo_message_id = data.get("last_photo_message_id")
    for message_id in [wizard_message_id, last_photo_message_id]:
        if not chat_id or not message_id:
            continue
        try:
            await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
        except Exception:
            pass


def _exercise_page_title(page: int, has_next: bool) -> str:
    total_label = "?" if has_next else str(page + 1)
    return f"Выбери упражнение (стр. {page + 1}/{total_label})"

async def _to_menu(message: Message, state: FSMContext):
    await _cleanup_wizard_messages(state, message.bot)
    await state.clear()
    await message.answer(texts.MENU, reply_markup=main_menu_kb())
async def _show_choose_exercise(message: Message, state: FSMContext):
    data = await state.get_data()
    exercises = data.get("exercises") or []
    ex_map = {
        str(idx): {
            "id": exercise.get("id"),
            "name": exercise.get("name"),
            "name_ru": exercise.get("name_ru"),
            "image_url": exercise.get("image_url"),
            "display_name": exercise.get("display_name"),
            "primary_muscle": exercise.get("primary_muscle"),
            "muscle_map": exercise.get("muscle_map"),
            "equipment": exercise.get("equipment"),
            "weight_mode": exercise.get("weight_mode"),
            "xp_mult": exercise.get("xp_mult"),
            "is_featured": bool(exercise.get("is_featured")),
        }
        for idx, exercise in enumerate(exercises, start=1)
    }
    await state.update_data(ex_map=ex_map, last_ex_map=ex_map, last_category=data.get("selected_category"))
    await state.set_state(QuickLogStates.choose_exercise)
    await message.answer(texts.CHOOSE_EXERCISE, reply_markup=exercises_kb(exercises, translate_mode=data.get("translate_mode") is True))


async def _goto_enter_weight(message: Message, state: FSMContext, data: dict):
    await state.set_state(QuickLogStates.enter_weight)
    await message.answer(f"{_weight_prompt_text(data)}{_prefill_hint(data.get('prefill_weight'), ' кг')}", reply_markup=back_cancel_kb())
@router.message(F.text == "🏋️ Тренировка")
async def training_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        wizard = await message.answer(texts.TRAINING_CHOOSE, reply_markup=training_start_inline_kb())
        await _remember_wizard_message(state, wizard)
        await state.update_data(wizard_step="choose_mode", category=None, page=0, search_query=None)
    except Exception:
        log.exception("training_menu failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.callback_query(F.data == "quick:start")
async def quick_log_start(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(QuickLogStates.choose_mode)
        await state.update_data(wizard_step="choose_mode")
        await _edit_wizard_text(state, callback.bot, texts.CHOOSE_MODE, mode_inline_kb())
        await callback.answer()
    except Exception:
        log.exception("quick_log_start failed")
        await callback.answer(texts.TECH_ERROR, show_alert=True)




@router.callback_query(F.data == "menu:back")
async def wizard_back_to_menu(callback: CallbackQuery, state: FSMContext):
    await _cleanup_wizard_messages(state, callback.bot)
    await state.clear()
    if callback.message:
        await callback.message.answer(texts.MENU, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_mode, F.data == "back:start")
async def mode_back_to_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if data.get("wizard_message_id"):
        await state.update_data(wizard_message_id=data.get("wizard_message_id"), wizard_chat_id=data.get("wizard_chat_id"))
    await state.update_data(wizard_step="choose_mode", category=None, page=0, search_query=None)
    await _edit_wizard_text(state, callback.bot, texts.TRAINING_CHOOSE, training_start_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_mode, F.data.startswith("mode:"))
async def choose_mode_inline(callback: CallbackQuery, state: FSMContext, db):
    value = str(callback.data or "").split(":", 1)[1]
    if value not in {"strength", "pattern"}:
        await callback.answer()
        return
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    await state.update_data(
        mode=value,
        exercises=[],
        selected_category=None,
        search_query=None,
        exercises_page=0,
        exercise_lang=db.get_exercise_lang(user_id=int(user["id"])),
    )
    await state.set_state(QuickLogStates.choose_category)
    await state.update_data(wizard_step="choose_category")
    await _edit_wizard_text(state, callback.bot, texts.CHOOSE_CATEGORY, category_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_category, F.data == "back:mode")
async def back_to_mode_inline(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuickLogStates.choose_mode)
    await state.update_data(wizard_step="choose_mode")
    await _edit_wizard_text(state, callback.bot, texts.CHOOSE_MODE, mode_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_category, F.data == "search:open")
async def open_search_inline(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_query=None, selected_category=None, search_origin="category", wizard_step="search_wait_query")
    await state.set_state(QuickLogStates.search_query)
    await _edit_wizard_text(state, callback.bot, texts.SEARCH_PROMPT, search_prompt_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_category, F.data == "custom:open")
@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "custom:open")
@router.callback_query(QuickLogStates.search_results, F.data == "custom:open")
async def open_custom_inline(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(search_origin=data.get("search_origin") or "category", wizard_step="custom_name")
    await state.set_state(QuickLogStates.custom_name)
    await _edit_wizard_text(state, callback.bot, texts.ENTER_CUSTOM_NAME, search_prompt_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "search:open")
async def open_search_from_exercises_inline(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_query=None, search_origin="exercise_inline", wizard_step="search_wait_query")
    await state.set_state(QuickLogStates.search_query)
    await _edit_wizard_text(state, callback.bot, texts.SEARCH_PROMPT, search_prompt_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_category, F.data.startswith("cat:"))
async def choose_category_inline(callback: CallbackQuery, state: FSMContext, db):
    category = str(callback.data or "").split(":", 1)[1]
    if category not in MUSCLE_LABELS:
        await callback.answer()
        return
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    await state.update_data(selected_category=category, search_query=None, exercise_lang=db.get_exercise_lang(user_id=int(user["id"])))
    await _show_exercise_list_wizard(state, callback.bot, db, int(user["id"]), page=0)
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "back:cat")
async def back_to_category_inline(callback: CallbackQuery, state: FSMContext):
    await state.set_state(QuickLogStates.choose_category)
    await state.update_data(wizard_step="choose_category")
    await _edit_wizard_text(state, callback.bot, texts.CHOOSE_CATEGORY, category_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data.startswith("page:"))
async def paginate_exercises_inline(callback: CallbackQuery, state: FSMContext, db):
    page = max(int(str(callback.data or "").split(":", 1)[1]), 0)
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    await _show_exercise_list_wizard(state, callback.bot, db, int(user["id"]), page=page)
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data.startswith("ex:"))
@router.callback_query(QuickLogStates.search_results, F.data.startswith("ex:"))
async def choose_exercise_inline(callback: CallbackQuery, state: FSMContext, db):
    exercise_id = int(str(callback.data or "").split(":", 1)[1])
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    exercise_lang = db.get_exercise_lang(user_id=int(user["id"]))
    exercise = db.get_exercise(exercise_id=exercise_id, user_id=int(user["id"]))
    display_name = str(exercise.get("display_name") or exercise.get("name") or "Упражнение")
    data = await state.get_data()

    wizard_message_id = data.get("wizard_message_id")
    wizard_chat_id = data.get("wizard_chat_id")
    if wizard_message_id and wizard_chat_id:
        try:
            await callback.bot.edit_message_reply_markup(chat_id=int(wizard_chat_id), message_id=int(wizard_message_id), reply_markup=None)
        except Exception:
            pass

    msg_photo = await _send_exercise_preview(callback.message, exercise, exercise_lang=exercise_lang)
    is_admin = db.is_admin(user)
    is_favorite = db.is_favorite(user_id=int(user["id"]), exercise_id=exercise_id)
    msg_actions = await callback.message.answer(
        texts.EXERCISE_CARD_HINT,
        reply_markup=actions_inline_kb(
            is_favorite=is_favorite,
            is_admin=is_admin,
            is_featured=bool(exercise.get("is_featured")),
        ),
    )

    await state.update_data(
        exercise_id=exercise_id,
        exercise_name=display_name,
        exercise_display_name=display_name,
        image_url=exercise.get("image_url"),
        selected_exercise_id=exercise_id,
        selected_exercise_name_en=exercise.get("name") or display_name,
        weight_mode=str(exercise.get("weight_mode") or "external"),
        xp_mult=float(exercise.get("xp_mult") or 1.0),
        body_weight_missing=user.get("body_weight_kg") is None,
        exercise_is_featured=bool(exercise.get("is_featured")),
        last_exercise_id=exercise_id,
        last_category=data.get("selected_category"),
        page=data.get("exercises_page") or 0,
        search_query=data.get("search_query"),
        wizard_message_id=msg_actions.message_id,
        last_photo_message_id=msg_photo.message_id,
        wizard_chat_id=msg_actions.chat.id,
        wizard_step="exercise_card",
    )
    await state.set_state(QuickLogStates.choose_exercise_inline)
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "card:back")
async def exercise_card_back_inline(callback: CallbackQuery, state: FSMContext, db):
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    data = await state.get_data()
    page = int(data.get("page") or data.get("exercises_page") or 0)
    photo_message_id = data.get("last_photo_message_id")
    wizard_chat_id = data.get("wizard_chat_id")
    if photo_message_id and wizard_chat_id:
        try:
            await callback.bot.delete_message(chat_id=int(wizard_chat_id), message_id=int(photo_message_id))
        except Exception:
            pass
    await _show_exercise_list_wizard(state, callback.bot, db, int(user["id"]), page=page)
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "card:continue")
async def continue_after_exercise_card_inline(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await _goto_enter_weight(callback.message, state, data)
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "card:fav")
async def toggle_favorite_inline(callback: CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        await callback.answer()
        return
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    is_favorite = db.is_favorite(user_id=int(user["id"]), exercise_id=int(exercise_id))
    if is_favorite:
        db.remove_favorite(user_id=int(user["id"]), exercise_id=int(exercise_id))
    else:
        db.add_favorite(user_id=int(user["id"]), exercise_id=int(exercise_id))
    await _show_selected_exercise_card(callback.message, state, db, show_status=True)
    await callback.answer()


@router.callback_query(QuickLogStates.choose_exercise_inline, F.data == "card:featured")
async def toggle_featured_inline(callback: CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        await callback.answer()
        return
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    if not db.is_admin(user):
        await callback.answer()
        return
    new_value = db.toggle_featured(exercise_id=int(exercise_id))
    await state.update_data(exercise_is_featured=bool(new_value))
    await _show_selected_exercise_card(
        callback.message,
        state,
        db,
        show_status=True,
        status_text=texts.FEATURED_ENABLED if new_value else texts.FEATURED_DISABLED,
    )
    await callback.answer()


@router.callback_query(F.data == "back:search")
async def back_from_search_inline(callback: CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    origin = data.get("search_origin")
    user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
    if origin == "exercise_inline":
        page = int(data.get("exercises_page") or 0)
        await _show_exercise_list_wizard(state, callback.bot, db, int(user["id"]), page=page)
    else:
        await state.set_state(QuickLogStates.choose_category)
        await state.update_data(wizard_step="choose_category")
        await _edit_wizard_text(state, callback.bot, texts.CHOOSE_CATEGORY, category_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.search_results, F.data.startswith("search_page:"))
async def paginate_search_results_inline(callback: CallbackQuery, state: FSMContext):
    page = max(int(str(callback.data or "").split(":", 1)[1]), 0)
    await _show_search_results_wizard(state, callback.bot, page=page)
    await callback.answer()


@router.callback_query(QuickLogStates.search_results, F.data == "search:reset")
async def search_reset_inline(callback: CallbackQuery, state: FSMContext):
    await state.update_data(search_query=None, search_results_all=[])
    await state.set_state(QuickLogStates.choose_category)
    await state.update_data(wizard_step="choose_category")
    await _edit_wizard_text(state, callback.bot, texts.CHOOSE_CATEGORY, category_inline_kb())
    await callback.answer()


@router.callback_query(QuickLogStates.custom_primary_muscle, F.data.startswith("custom:muscle:"))
async def custom_primary_muscle_inline(callback: CallbackQuery, state: FSMContext, db):
    try:
        choice = str(callback.data or "").split(":", 2)[2]
        data = await state.get_data()
        exercise_name = str(data.get("exercise_name") or "").strip()
        if not exercise_name:
            await state.set_state(QuickLogStates.custom_name)
            await _edit_wizard_text(state, callback.bot, texts.ENTER_CUSTOM_NAME, search_prompt_inline_kb())
            await callback.answer()
            return
        selected_category = str(data.get("selected_category") or "").strip().lower()
        if choice == "current":
            primary_muscle = selected_category if selected_category in MUSCLE_LABELS else None
        else:
            primary_muscle = choice if choice in MUSCLE_LABELS else None
        if not primary_muscle:
            await _edit_wizard_text(
                state,
                callback.bot,
                texts.CHOOSE_PRIMARY_MUSCLE,
                custom_primary_muscle_inline_kb(current_muscle=selected_category or None),
            )
            await callback.answer()
            return
        user = db.get_or_create_user(callback.from_user.id, callback.from_user.username)
        try:
            exercise = db.create_custom_exercise(int(user["id"]), exercise_name, primary_muscle)
        except ValueError:
            await state.set_state(QuickLogStates.custom_name)
            await _edit_wizard_text(state, callback.bot, texts.ERR_EXERCISE_NAME, search_prompt_inline_kb())
            await callback.answer()
            return
        await state.update_data(
            exercise_id=exercise["id"],
            exercise_name=exercise.get("display_name"),
            primary_muscle=primary_muscle,
            selected_category=primary_muscle,
            weight_mode="external",
            xp_mult=1.0,
            body_weight_missing=user.get("body_weight_kg") is None,
            wizard_step="enter_weight",
        )
        await state.set_state(QuickLogStates.enter_weight)
        await _edit_wizard_text(
            state,
            callback.bot,
            f"{_weight_prompt_text(await state.get_data())}{_prefill_hint(data.get('prefill_weight'), ' кг')}",
            search_prompt_inline_kb(),
        )
        await callback.answer()
    except Exception:
        log.exception("custom_primary_muscle_inline failed")
        await callback.answer(texts.TECH_ERROR, show_alert=True)
@router.message(F.text == "❌ Отмена")
async def cancel_anywhere(message: Message, state: FSMContext):
    try:
        current = await state.get_state()
        if current and current.startswith("QuickLogStates:"):
            await _to_menu(message, state)
    except Exception:
        log.exception("cancel_anywhere failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.choose_mode, F.text == "↩️ В меню")
async def back_from_choose_mode(message: Message, state: FSMContext):
    await _to_menu(message, state)
@router.message(QuickLogStates.choose_category, F.text == "↩️ Назад")
async def back_from_choose_category(message: Message, state: FSMContext):
    await message.answer(texts.USE_INLINE_BACK_HINT)

@router.message(QuickLogStates.choose_exercise, F.text == "↩️ Назад")
async def back_from_choose_exercise(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.search_query, F.text == "↩️ Назад")
async def back_from_search_query(message: Message, state: FSMContext, db):
    data = await state.get_data()
    origin = data.get("search_origin")
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if origin == "exercise_inline":
        page = int(data.get("exercises_page") or 0)
        await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
        return
    await state.set_state(QuickLogStates.choose_category)
    await state.update_data(wizard_step="choose_category")
    await _edit_wizard_text(state, message.bot, texts.CHOOSE_CATEGORY, category_inline_kb())


@router.message(QuickLogStates.choose_exercise_inline, F.text == "↩️ Назад")
@router.message(QuickLogStates.search_results, F.text == "↩️ Назад")
async def back_from_inline_wizard_text(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.custom_name, F.text == "↩️ Назад")
async def back_from_custom_name(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.choose_category)
    await state.update_data(wizard_step="choose_category")
    if data.get("wizard_message_id"):
        await _edit_wizard_text(state, message.bot, texts.CHOOSE_CATEGORY, category_inline_kb())
        return
    await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb(translate_mode=data.get("translate_mode") is True))
@router.message(QuickLogStates.custom_primary_muscle, F.text == "↩️ Назад")
async def back_from_custom_primary(message: Message, state: FSMContext):
    await state.set_state(QuickLogStates.custom_name)
    data = await state.get_data()
    if data.get("wizard_message_id"):
        await _edit_wizard_text(state, message.bot, texts.ENTER_CUSTOM_NAME, search_prompt_inline_kb())
        return
    await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
@router.message(QuickLogStates.enter_weight, F.text == "↩️ Назад")
async def back_from_weight(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.enter_reps, F.text == "↩️ Назад")
async def back_from_reps(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.enter_sets, F.text == "↩️ Назад")
async def back_from_sets(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.enter_rest_single, F.text == "↩️ Назад")
async def back_from_rest_single(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.enter_rest_pattern, F.text == "↩️ Назад")
async def back_from_rest_pattern(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.confirm, F.text == "↩️ Назад")
async def back_from_confirm(message: Message, state: FSMContext, db):
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    page = int((await state.get_data()).get("exercises_page") or 0)
    await _show_exercise_list_wizard(state, message.bot, db, int(user["id"]), page=page)
@router.message(QuickLogStates.choose_mode)
async def choose_mode(message: Message, state: FSMContext, db):
    try:
        if message.text == MODE_STRENGTH:
            mode = "strength"
        elif message.text == MODE_PATTERN:
            mode = "pattern"
        else:
            await message.answer(texts.CHOOSE_MODE, reply_markup=mode_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        translate_mode = db.is_admin(user) and db.get_translate_mode(user_id=int(user["id"]))
        await state.update_data(mode=mode, exercises=[], selected_category=None, translate_mode=translate_mode)
        await state.set_state(QuickLogStates.choose_category)
        await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb(translate_mode=translate_mode))
    except Exception:
        log.exception("choose_mode failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.choose_category)
async def choose_category(message: Message, state: FSMContext, db):
    try:
        if message.text == "🔎 Поиск":
            await state.set_state(QuickLogStates.search_query)
            await message.answer(texts.SEARCH_PROMPT, reply_markup=back_cancel_kb())
            return
        if message.text == "➕ Своё упражнение":
            await state.set_state(QuickLogStates.custom_name)
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return
        if message.text == "⏭ Следующее непереведённое":
            data = await state.get_data()
            if data.get("translate_mode"):
                await _show_next_untranslated(message, state, db)
            else:
                await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb(translate_mode=False))
            return

        selected_muscle = MUSCLE_MAP.get(message.text or "")
        if not selected_muscle:
            data = await state.get_data()
            await message.answer(texts.CHOOSE_CATEGORY, reply_markup=exercise_category_kb(translate_mode=data.get("translate_mode") is True))
            return

        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        exercises = db.list_exercises(user_id=int(user["id"]), limit=12, primary_muscle=selected_muscle)
        if not exercises:
            data = await state.get_data()
            await message.answer(texts.SEARCH_EMPTY, reply_markup=exercise_category_kb(translate_mode=data.get("translate_mode") is True))
            return

        await state.update_data(exercises=exercises, selected_category=selected_muscle)
        await _show_choose_exercise(message, state)
    except Exception:
        log.exception("choose_category failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())

@router.message(QuickLogStates.choose_exercise, F.text == "⏭ Следующее непереведённое")
async def next_untranslated(message: Message, state: FSMContext, db):
    data = await state.get_data()
    if not data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or []))
        return
    await _show_next_untranslated(message, state, db)


@router.message(QuickLogStates.choose_exercise, F.text == "✅ Ввести RU")
async def choose_enter_ru(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or []))
        return
    await state.set_state(TranslateStates.waiting_name_ru)
    await message.answer(texts.RU_NAME_PROMPT, reply_markup=back_cancel_kb())


@router.message(QuickLogStates.choose_exercise, F.text == "🆗 Оставить EN")
async def keep_en_name(message: Message, state: FSMContext, db):
    data = await state.get_data()
    if not data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or []))
        return
    exercise_id = data.get("selected_exercise_id")
    name_en = str(data.get("selected_exercise_name_en") or "")
    if exercise_id and name_en:
        db.update_exercise_name_ru(exercise_id=int(exercise_id), name_ru=name_en)
    await message.answer(texts.TRANSLATE_KEEP_EN.format(name_en=name_en or "-"))
    await _show_next_untranslated(message, state, db)




@router.message(QuickLogStates.choose_exercise, F.text == "⭐ В избранное")
async def add_to_favorite(message: Message, state: FSMContext, db):
    data = await state.get_data()
    if data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or [], translate_mode=True))
        return
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        await _show_choose_exercise(message, state)
        return
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    db.add_favorite(user_id=int(user["id"]), exercise_id=int(exercise_id))
    await _show_selected_exercise_card(message, state, db, show_status=True)


@router.message(QuickLogStates.choose_exercise, F.text == "⭐ Убрать из избранного")
async def remove_from_favorite(message: Message, state: FSMContext, db):
    data = await state.get_data()
    if data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or [], translate_mode=True))
        return
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        await _show_choose_exercise(message, state)
        return
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    db.remove_favorite(user_id=int(user["id"]), exercise_id=int(exercise_id))
    await _show_selected_exercise_card(message, state, db, show_status=True)


@router.message(QuickLogStates.choose_exercise, F.text.startswith("🔥 Рекомендуемое:"))
async def toggle_featured_flag(message: Message, state: FSMContext, db):
    data = await state.get_data()
    if data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or [], translate_mode=True))
        return
    exercise_id = data.get("exercise_id")
    if not exercise_id:
        await _show_choose_exercise(message, state)
        return
    user = db.get_or_create_user(message.from_user.id, message.from_user.username)
    if not db.is_admin(user):
        await _show_choose_exercise(message, state)
        return
    new_value = db.toggle_featured(exercise_id=int(exercise_id))
    await state.update_data(exercise_is_featured=bool(new_value))
    await _show_selected_exercise_card(
        message,
        state,
        db,
        show_status=True,
        status_text=texts.FEATURED_ENABLED if new_value else texts.FEATURED_DISABLED,
    )


@router.message(QuickLogStates.choose_exercise, F.text == "✅ Продолжить")
async def continue_after_exercise_card(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("translate_mode"):
        await message.answer(texts.CHOOSE_EXERCISE_FROM_LIST, reply_markup=exercises_kb(data.get("exercises") or [], translate_mode=True))
        return
    if not data.get("exercise_id"):
        await _show_choose_exercise(message, state)
        return
    await _goto_enter_weight(message, state, data)

@router.message(QuickLogStates.choose_exercise)
async def choose_exercise(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        ex_map = data.get("ex_map") or {}
        match = EXERCISE_PICK_RE.match((message.text or "").strip())
        selected = ex_map.get(match.group(1)) if match else None
        if not selected:
            await message.answer(
                texts.CHOOSE_EXERCISE_FROM_LIST,
                reply_markup=exercises_kb(data.get("exercises") or [], translate_mode=data.get("translate_mode") is True),
            )
            return
        display_name = str(selected.get("display_name") or selected.get("name") or "Упражнение")
        image_url = str(selected.get("image_url") or "").strip()
        await state.update_data(
            exercise_id=selected["id"],
            exercise_name=display_name,
            exercise_display_name=display_name,
            image_url=image_url or None,
            exercise_is_featured=bool(selected.get("is_featured")),
            selected_exercise_id=selected["id"],
            selected_exercise_name_en=selected.get("name") or display_name,
            weight_mode=str(selected.get("weight_mode") or "external"),
            xp_mult=float(selected.get("xp_mult") or 1.0),
            body_weight_missing=user.get("body_weight_kg") is None,
            last_category=data.get("selected_category"),
        )
        if data.get("translate_mode"):
            await _start_translate_for_exercise(message, state, selected, waiting_input=False)
            return

        await _show_selected_exercise_card(message, state, db)
    except Exception:
        log.exception("choose_exercise failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(TranslateStates.waiting_name_ru, F.text == "↩️ Назад")
async def back_from_translate_name(message: Message, state: FSMContext):
    data = await state.get_data()
    exercise = data.get("selected_exercise")
    if data.get("translate_mode") and isinstance(exercise, dict):
        await state.set_state(QuickLogStates.choose_exercise)
        await message.answer(texts.TRANSLATE_CHOOSE_ACTION, reply_markup=translate_exercise_actions_kb())
        return
    await _render_last_category_exercises(message, state)


@router.message(TranslateStates.waiting_name_ru)
async def set_ru_name(message: Message, state: FSMContext, db):
    try:
        value = (message.text or "").strip()
        data = await state.get_data()
        if not data.get("translate_mode"):
            await _render_last_category_exercises(message, state)
            return
        if value == "-":
            await message.answer(texts.TRANSLATE_SKIPPED)
            await state.set_state(QuickLogStates.choose_exercise)
            await message.answer(texts.TRANSLATE_CHOOSE_ACTION, reply_markup=translate_exercise_actions_kb())
            return
        if not _validate_name(value):
            await message.answer(texts.ERR_EXERCISE_NAME, reply_markup=back_cancel_kb())
            return
        exercise_id = data.get("selected_exercise_id")
        name_en = str(data.get("selected_exercise_name_en") or "")
        if exercise_id:
            db.update_exercise_name_ru(exercise_id=int(exercise_id), name_ru=value)
        await message.answer(texts.TRANSLATE_SAVED.format(name_en=name_en or "-", name_ru=value))
        await _show_next_untranslated(message, state, db)
    except Exception:
        log.exception("set_ru_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


@router.message(QuickLogStates.search_query)
async def search_query(message: Message, state: FSMContext, db):
    try:
        query = (message.text or "").strip()
        if not query:
            await _edit_wizard_text(state, message.bot, texts.SEARCH_PROMPT, search_prompt_inline_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        all_exercises = db.list_exercises_active_all(user_id=int(user["id"]), primary_muscle=None)
        results = _search_exercises(all_exercises, query)
        await state.update_data(search_query=query, selected_category=None, search_results_all=results)
        if not results:
            await _edit_wizard_text(state, message.bot, texts.SEARCH_EMPTY, search_prompt_inline_kb())
            return
        await _show_search_results_wizard(state, message.bot, page=0)
    except Exception:
        log.exception("search_query failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.custom_name)
async def custom_name(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        inline_wizard = bool(data.get("wizard_message_id"))
        exercise_name = (message.text or "").strip()
        if not exercise_name:
            if inline_wizard:
                await _edit_wizard_text(state, message.bot, texts.ENTER_CUSTOM_NAME, search_prompt_inline_kb())
            else:
                await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return
        if not _validate_name(exercise_name):
            await state.set_state(QuickLogStates.custom_name)
            if inline_wizard:
                await _edit_wizard_text(state, message.bot, texts.ERR_EXERCISE_NAME, search_prompt_inline_kb())
            else:
                await message.answer(texts.ERR_EXERCISE_NAME, reply_markup=back_cancel_kb())
            return
        await state.update_data(exercise_name=exercise_name)
        await state.set_state(QuickLogStates.custom_primary_muscle)
        data = await state.get_data()
        selected_category = str(data.get("selected_category") or "").strip().lower()
        if inline_wizard:
            await _edit_wizard_text(
                state,
                message.bot,
                texts.CHOOSE_PRIMARY_MUSCLE,
                custom_primary_muscle_inline_kb(current_muscle=selected_category or None),
            )
        else:
            await message.answer(texts.CHOOSE_PRIMARY_MUSCLE, reply_markup=muscle_choice_kb())
    except Exception:
        log.exception("custom_name failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.custom_primary_muscle)
async def custom_primary_muscle(message: Message, state: FSMContext, db):
    try:
        data = await state.get_data()
        if data.get("wizard_message_id"):
            selected_category = str(data.get("selected_category") or "").strip().lower()
            await _edit_wizard_text(
                state,
                message.bot,
                texts.CHOOSE_PRIMARY_MUSCLE,
                custom_primary_muscle_inline_kb(current_muscle=selected_category or None),
            )
            return
        primary_muscle = MUSCLE_MAP.get(message.text or "")
        if not primary_muscle:
            await message.answer(texts.CHOOSE_PRIMARY_MUSCLE, reply_markup=muscle_choice_kb())
            return
        exercise_name = data.get("exercise_name")
        if not exercise_name:
            await state.set_state(QuickLogStates.custom_name)
            await message.answer(texts.ENTER_CUSTOM_NAME, reply_markup=back_cancel_kb())
            return
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        try:
            exercise = db.create_custom_exercise(int(user["id"]), exercise_name, primary_muscle)
        except ValueError:
            await message.answer(texts.ERR_EXERCISE_NAME, reply_markup=back_cancel_kb())
            await state.set_state(QuickLogStates.custom_name)
            return
        await state.update_data(exercise_id=exercise["id"], exercise_name=exercise.get("display_name"), primary_muscle=primary_muscle)
        await state.update_data(weight_mode="external", xp_mult=1.0, body_weight_missing=user.get("body_weight_kg") is None)
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(
            f"{_weight_prompt_text(await state.get_data())}{_prefill_hint(data.get('prefill_weight'), ' кг')}",
            reply_markup=back_cancel_kb(),
        )
    except Exception:
        log.exception("custom_primary_muscle failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_weight)
async def enter_weight(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_weight") is not None:
            weight = float(data.get("prefill_weight") or 0)
        else:
            weight = _parse_float(raw)
        if weight < 0 or weight > 1000:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(weight=weight)
        await state.set_state(QuickLogStates.enter_reps)
        await message.answer(f"{texts.ENTER_REPS}{_prefill_hint(data.get('prefill_reps'))}", reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_weight failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_reps)
async def enter_reps(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_reps") is not None:
            reps = int(data.get("prefill_reps") or 0)
        else:
            reps = int(raw)
        if reps < 1 or reps > 200:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(reps=reps)
        await state.set_state(QuickLogStates.enter_sets)
        await message.answer(f"{texts.ENTER_SETS}{_prefill_hint(data.get('prefill_sets'))}", reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_reps failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_sets)
async def enter_sets(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_sets") is not None:
            sets_count = int(data.get("prefill_sets") or 0)
        else:
            sets_count = int(raw)
        if sets_count < 1 or sets_count > 50:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        await state.update_data(sets_count=sets_count)
        if data.get("mode") == "pattern":
            await state.set_state(QuickLogStates.enter_rest_pattern)
            hint = _prefill_hint(data.get("prefill_rest_pattern_text"), " мин") if data.get("prefill_rest_pattern_text") else ""
            await message.answer(f"{texts.ENTER_REST_PATTERN}{hint}", reply_markup=back_cancel_kb())
        else:
            await state.set_state(QuickLogStates.enter_rest_single)
            await message.answer(f"{texts.ENTER_REST_SINGLE}{_prefill_hint(data.get('prefill_rest_minutes'), ' мин')}", reply_markup=back_cancel_kb())
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_sets failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.enter_rest_single)
async def enter_rest_single(message: Message, state: FSMContext):
    try:
        raw = (message.text or "").strip()
        data = await state.get_data()
        if raw == "." and data.get("prefill_rest_minutes") is not None:
            minutes = float(data.get("prefill_rest_minutes") or 0)
        else:
            minutes = _parse_float(raw)
        if minutes < 0 or minutes > 30:
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        rest_seconds = int(round(minutes * 60))
        await state.update_data(rest_minutes=minutes, rest_seconds=rest_seconds, rest_pattern_seconds=None)
        await _show_confirm(message, state)
    except (TypeError, ValueError):
        await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
    except Exception:
        log.exception("enter_rest_single failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())

@router.message(QuickLogStates.enter_rest_pattern)
async def enter_rest_pattern(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        sets_count = int(data.get("sets_count", 1))
        expected_length = max(sets_count - 1, 0)
        raw = (message.text or "").strip()
        if raw == "." and isinstance(data.get("prefill_rest_pattern_minutes"), list):
            values = list(data.get("prefill_rest_pattern_minutes") or [])
        else:
            values = _extract_pattern_values(raw)
        if values is None:
            await message.answer(texts.ERR_NUMBER, reply_markup=back_cancel_kb())
            return
        if expected_length == 0:
            values = []
        if len(values) != expected_length or any(v < 0 or v > 30 for v in values):
            await message.answer(texts.ERR_RANGE, reply_markup=back_cancel_kb())
            return
        rest_pattern_seconds = [int(round(v * 60)) for v in values]
        rest_seconds = int(round(sum(rest_pattern_seconds) / len(rest_pattern_seconds))) if rest_pattern_seconds else 0
        await state.update_data(rest_pattern_minutes=values, rest_pattern_seconds=rest_pattern_seconds, rest_seconds=rest_seconds)
        await _show_confirm(message, state)
    except Exception:
        log.exception("enter_rest_pattern failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())


async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(QuickLogStates.confirm)
    lines = [
        f"{data.get('exercise_display_name') or data['exercise_name']}",
        f"Вес: {data['weight']} кг",
        f"Повторы: {data['reps']}",
        f"Подходы: {data['sets_count']}",
    ]
    if data.get("mode") == "pattern":
        minutes_values = data.get("rest_pattern_minutes") or []
        pattern_str = ", ".join(str(v).replace(".", ",") for v in minutes_values) if minutes_values else "—"
        lines.append(f"Отдых по подходам: {pattern_str}")
    else:
        lines.append(f"Отдых: {str(data.get('rest_minutes', 0)).replace('.', ',')} мин")
    if data.get("image_url"):
        lines.append(f"{texts.TECHNIQUE_LINK_PREFIX} {data['image_url']}")
    await message.answer(f"{texts.CONFIRM}\n\n" + "\n".join(lines), reply_markup=confirm_kb())
@router.message(QuickLogStates.confirm, F.text == "✏️ Изменить")
async def edit_quick_log(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        for key in ("weight", "reps", "sets_count", "rest_minutes", "rest_seconds", "rest_pattern_minutes", "rest_pattern_seconds"):
            data.pop(key, None)
        await state.set_data(data)
        await state.set_state(QuickLogStates.enter_weight)
        await message.answer(f"{_weight_prompt_text(data)}{_prefill_hint(data.get('prefill_weight'), ' кг')}", reply_markup=back_cancel_kb())
    except Exception:
        log.exception("edit_quick_log failed")
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.confirm, F.text == "✅ Сохранить")
async def save_quick_log(message: Message, state: FSMContext, db):
    current_state = await state.get_state()
    if not current_state:
        return
    data = await state.get_data()
    if data.get("saved"):
        return
    await state.update_data(saved=True)
    try:
        user = db.get_or_create_user(message.from_user.id, message.from_user.username)
        db.ensure_progress(user["id"])
        template_payload = data.get("template_edit_payload") if isinstance(data.get("template_edit_payload"), list) else None
        if template_payload is not None:
            payload = list(template_payload)
            first = payload[0] if payload else {}
            first["weight"] = float(data["weight"])
            first["reps"] = int(data["reps"])
            first["sets_count"] = int(data["sets_count"])
            first["rest_seconds"] = int(data["rest_seconds"])
            first["rest_pattern"] = data.get("rest_pattern_seconds")
            if payload:
                payload[0] = first
            workout_id = db.create_workout(user["id"], title=_build_workout_title(data), mode="template", status="planned")
            for idx, item in enumerate(payload, start=1):
                if item.get("exercise_id") is None:
                    continue
                item_id = db.create_workout_item(workout_id, int(item["exercise_id"]), order_index=idx)
                db.create_set(
                    workout_item_id=item_id,
                    weight=float(item.get("weight") or 0),
                    reps=int(item.get("reps") or 0),
                    sets_count=int(item.get("sets_count") or 0),
                    rest_seconds=int(item.get("rest_seconds") or 0),
                    rest_pattern_seconds=item.get("rest_pattern") if isinstance(item.get("rest_pattern"), list) else None,
                )
        else:
            workout_id = db.create_workout(
                user["id"],
                title=_build_workout_title(data),
                mode=data["mode"],
                status="planned" if data.get("repeat_source_workout_id") else "done",
                source_workout_id=int(data["repeat_source_workout_id"]) if data.get("repeat_source_workout_id") else None,
            )
            item_id = db.create_workout_item(workout_id, int(data["exercise_id"]), order_index=1)
            db.create_set(
                workout_item_id=item_id,
                weight=float(data["weight"]),
                reps=int(data["reps"]),
                sets_count=int(data["sets_count"]),
                rest_seconds=int(data["rest_seconds"]),
                rest_pattern_seconds=data.get("rest_pattern_seconds"),
            )
    except Exception:
        log.exception("save_quick_log failed")
        await state.clear()
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
        return
    try:
        if template_payload is not None:
            total_xp = 0
            total_sets = 0
            muscle_delta = {}
            top = []
            for idx, item in enumerate(template_payload):
                ex_id = item.get("exercise_id")
                if ex_id is None:
                    continue
                award_item = db.award_and_update_progress(
                    user_id=int(user["id"]),
                    exercise_id=int(ex_id),
                    weight=float(data["weight"]) if idx == 0 else float(item.get("weight") or 0),
                    reps=int(data["reps"]) if idx == 0 else int(item.get("reps") or 0),
                    sets_count=int(data["sets_count"]) if idx == 0 else int(item.get("sets_count") or 0),
                )
                total_xp += int(award_item.get("xp_gain") or 0)
                total_sets += int(award_item.get("total_sets_for_workout") or 0)
                for m, val in (award_item.get("muscle_delta") or {}).items():
                    muscle_delta[m] = int(muscle_delta.get(m, 0)) + int(val)
                top.extend(award_item.get("muscle_gains_sorted_top3") or [])
            db.update_workout_metrics(
                user_id=int(user["id"]),
                workout_id=int(workout_id),
                total_xp=total_xp,
                total_sets=total_sets,
                muscle_delta=muscle_delta,
                status="done",
            )
            progress = db.get_progress(int(user["id"]))
            reward_text = (
                "<b>FitXP · Награда</b>\n"
                f"+<b>{total_xp} XP</b> | Уровень: <b>{progress['level']}</b>\n"
                f"XP: <b>{progress['xp']}/{100 + int(progress['level']) * 25}</b>\n\n"
                "<b>Прокачка</b>\n"
                + ("\n".join([f"- {MUSCLE_LABELS.get(m, '🏋️ Нагрузка')}: +{g}" for m, g in top[:3]]) if top else "- 🏋️ Общая нагрузка учтена")
                + "\n\nПрогресс засчитан."
            )
        else:
            award = db.award_and_update_progress(
                user_id=int(user["id"]),
                exercise_id=int(data["exercise_id"]),
                weight=float(data["weight"]),
                reps=int(data["reps"]),
                sets_count=int(data["sets_count"]),
            )
            db.update_workout_metrics(
                user_id=int(user["id"]),
                workout_id=int(workout_id),
                total_xp=int(award.get("xp_gain") or 0),
                total_sets=int(award.get("total_sets_for_workout") or 0),
                muscle_delta=award.get("muscle_delta") if isinstance(award.get("muscle_delta"), dict) else {},
                status="done",
            )
            top = award.get("muscle_gains_sorted_top3") or []
            pump_text = "\n".join([f"- {MUSCLE_LABELS.get(m, '🏋️ Нагрузка')}: +{g}" for m, g in top]) if top else "- 🏋️ Общая нагрузка учтена"
            reward_text = (
                "<b>FitXP · Награда</b>\n"
                f"+<b>{award['xp_gain']} XP</b> | Уровень: <b>{award['level_new']}</b>\n"
                f"XP: <b>{award['xp_new']}/{award['xp_to_next']}</b>\n\n"
                "<b>Прокачка</b>\n"
                f"{pump_text}\n\n"
                "Прогресс засчитан."
            )
        await state.clear()
        await message.answer(reward_text, reply_markup=main_menu_kb())
        new_achievements = db.check_and_award_achievements(int(user["id"]))
        if new_achievements:
            lines = [texts.ACHIEVEMENT_UNLOCKED.format(name=db_module.ACHIEVEMENTS_META.get(aid, aid)) for aid in new_achievements]
            await message.answer("\n".join(lines), reply_markup=main_menu_kb())
    except Exception:
        log.exception("award_and_update_progress failed")
        await state.clear()
        await message.answer(texts.TECH_ERROR, reply_markup=main_menu_kb())
@router.message(QuickLogStates.confirm)
async def confirm_fallback(message: Message):
    await message.answer(texts.CONFIRM, reply_markup=confirm_kb())
