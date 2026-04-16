from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.v1.routes import router as v1_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine

settings = get_settings()
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
camera_videos_dir = Path(__file__).resolve().parent / "camera_videos"

app = FastAPI(title="Tunnel Accident Detection System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")
app.mount("/camera_videos", StaticFiles(directory=camera_videos_dir), name="camera_videos")

app.include_router(v1_router, prefix="/api/v1")


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API working"}
