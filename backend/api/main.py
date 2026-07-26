import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.squad import router as squad_router

# Database and Redis URL environment variables with local defaults
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/fergie_time"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = FastAPI(
    title="FergieTime API",
    description="Backend API for FergieTime FPL AI Agent",
    version="0.1.0",
)

# Set up CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(squad_router)


@app.get("/health")
def health_check():
    """Health check endpoint to verify system status and configuration."""
    return {
        "status": "ok",
        "database_configured": bool(DATABASE_URL),
        "redis_configured": bool(REDIS_URL),
    }
