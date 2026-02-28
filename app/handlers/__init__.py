from app.handlers.achievements import router as achievements_router
from app.handlers.history import router as history_router
from app.handlers.menu import router as menu_router
from app.handlers.settings import router as settings_router
from app.handlers.start import router as start_router
from app.handlers.templates import router as templates_router
from app.handlers.training import router as training_router

all_routers = [
    start_router,
    menu_router,
    training_router,
    history_router,
    templates_router,
    settings_router,
    achievements_router,
]
