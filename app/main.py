import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.api.v1 import api_router
from app.services.scheduler import start_scheduler, shutdown_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("smart_todo")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)

    logger.info("Starting background scheduler...")
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Shutting down background scheduler...")
    shutdown_scheduler()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Set CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/db-status")
async def db_status():
    try:
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal
        
        # Ensure tables are created
        await init_db()
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"))
            tables = [row[0] for row in result.fetchall()]
            
            # Mask password in URL
            url_str = str(settings.DATABASE_URL)
            if "@" in url_str:
                parts = url_str.split("@")
                proto_user = parts[0].rsplit(":", 1)[0]
                masked_url = f"{proto_user}:****@{parts[1]}"
            else:
                masked_url = url_str

            return {
                "status": "connected",
                "database_url": masked_url,
                "tables_count": len(tables),
                "tables": tables
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "database_url": str(settings.DATABASE_URL)
        }

