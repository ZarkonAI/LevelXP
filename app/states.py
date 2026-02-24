from aiogram.fsm.state import State, StatesGroup


class QuickLogStates(StatesGroup):
    choose_mode = State()
    choose_exercise = State()
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
