from aiogram.fsm.state import State, StatesGroup


class QuickLogStates(StatesGroup):
    choose_mode = State()
    choose_category = State()
    choose_exercise = State()
    search_query = State()
    custom_name = State()
    custom_primary_muscle = State()
    enter_weight = State()
    enter_reps = State()
    enter_sets = State()
    enter_rest_single = State()
    enter_rest_pattern = State()
    confirm = State()


class TemplateStates(StatesGroup):
    waiting_name = State()
    choosing_save_mode = State()
    choosing_existing = State()


class HistoryStates(StatesGroup):
    browsing_list = State()
    viewing_card = State()
    choosing_repeat_mode = State()
    confirming_toggle = State()
    confirming_repeat = State()


class EditWorkoutStates(StatesGroup):
    waiting_weight = State()
    waiting_reps = State()
    waiting_sets = State()
    waiting_rest_single = State()
    waiting_rest_pattern = State()
    confirm = State()


class SettingsStates(StatesGroup):
    units_menu = State()
    waiting_timezone = State()
    exercise_lang_menu = State()
    translate_mode_menu = State()


class TemplateBrowseStates(StatesGroup):
    browsing = State()
    confirming = State()
    confirming_apply = State()


class TranslateStates(StatesGroup):
    waiting_name_ru = State()
