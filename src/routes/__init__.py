"""FastAPI 路由聚合。"""

from fastapi import APIRouter

api_router = APIRouter(prefix="/api")

from .auth import router as auth_router
from .admin import router as admin_router
from .practice import router as practice_router
from .ai import router as ai_router
from .assignment import router as assignment_router
from .community import router as community_router
from .learning import router as learning_router
from .config import router as config_router

api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(practice_router)
api_router.include_router(ai_router)
api_router.include_router(assignment_router)
api_router.include_router(community_router)
api_router.include_router(learning_router)
api_router.include_router(config_router)
