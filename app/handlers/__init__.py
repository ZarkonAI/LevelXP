from app.handlers.start import router as start_router
from app.handlers.training import router as training_router
from app.handlers.menu import router as menu_router

all_routers = [start_router, training_router, menu_router]
