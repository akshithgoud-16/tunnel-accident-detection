from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_name: str = "Tunnel Accident Detection API"
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./app/dev.db",
    )
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:5173",
    )
    uploads_dir: Path = Path(os.getenv("UPLOADS_DIR", "app/uploads"))


def get_settings() -> Settings:
    return Settings()
