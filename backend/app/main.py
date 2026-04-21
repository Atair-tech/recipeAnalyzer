from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.ai import router as ai_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.database import router as database_router
from app.api.routes.imports import router as imports_router
from app.api.routes.pairing import router as pairing_router
from app.api.routes.recipes import router as recipes_router
from app.api.routes.system import router as system_router
from app.api.routes.tagging import router as tagging_router
from app.core.config import ALLOWED_ORIGINS
from app.db.database import initialize_database
from app.services.search_service import rebuild_recipe_search_index


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    rebuild_recipe_search_index()
    yield


app = FastAPI(
    title="Recipe Analyzer API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router, prefix="/api", tags=["system"])
app.include_router(analytics_router, prefix="/api", tags=["analytics"])
app.include_router(ai_router, prefix="/api", tags=["ai"])
app.include_router(imports_router, prefix="/api", tags=["imports"])
app.include_router(database_router, prefix="/api", tags=["database"])
app.include_router(pairing_router, prefix="/api", tags=["pairing"])
app.include_router(recipes_router, prefix="/api", tags=["recipes"])
app.include_router(tagging_router, prefix="/api", tags=["tagging"])


@app.get("/")
def root():
    return {"message": "Recipe Analyzer backend is running"}
