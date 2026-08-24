from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.todos import router as todos_router
from app.api.v1.notifications import router as notifications_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(todos_router)
api_router.include_router(notifications_router)
