import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Base Directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = BASE_DIR / "config"
    BUFFER_DIR: Path = BASE_DIR / "buffer"
    CLIPS_DIR: Path = BASE_DIR / "clips"
    LOGS_DIR: Path = BASE_DIR / "logs"

    # API Keys
    GEMINI_API_KEY: str = ""
    AI_MAX_CALLS_PER_MINUTE: int = 10
    AI_MAX_CALLS_PER_DAY: int = 30
    AI_FALLBACK_ON_LIMIT: bool = True

    # YouTube OAuth
    YOUTUBE_CLIENT_SECRETS_PATH: str = "config/client_secrets.json"
    YOUTUBE_TOKEN_PATH: str = "config/token.json"
    YOUTUBE_SCHEDULE_SLOTS: str = "12:00"
    YOUTUBE_TIMEZONE: str = "America/New_York"
    YOUTUBE_DEFAULT_PRIVACY: str = "scheduled"
    REQUIRE_MANUAL_APPROVAL: bool = True
    AUTO_UPLOAD_ENABLED: bool = False
    REVIEW_COUNTDOWN_MINUTES: int = 10

    # Twitch Ingestion
    TWITCH_CHANNEL: str = "jynxzi"
    STREAM_QUALITY: str = "720p60"
    BUFFER_MINUTES: int = 8

    # Peak Detection & Quality Filtering
    MAX_CLIP_DURATION: int = 45
    PEAK_COOLDOWN_SECONDS: int = 60
    PEAK_Z_SCORE_THRESHOLD: float = 3.0 # Increased to 3.0 per requirement
    PEAK_MIN_VELOCITY: float = 10.0     # 10 msg/s required
    AUTO_PROCESS_PEAKS: bool = False    # Hold in queue for manual selection

    # 40/60 Layout
    OUTPUT_WIDTH: int = 1080
    OUTPUT_HEIGHT: int = 1920
    LAYOUT_FACECAM_RATIO: float = 0.40
    LAYOUT_GAMEPLAY_RATIO: float = 0.60
    FACECAM_TARGET_FACE_HEIGHT_RATIO: float = 0.55 # Streamer face occupies 50% - 60% of facecam window height
    FACECAM_MIN_CROP_HEIGHT: int = 280            # Quality limit: prevents over-zooming that tanks resolution

    # Subtitles
    SUBTITLE_MAX_WORDS: int = 4
    SUBTITLE_MAX_CHARS: int = 30        # Extended to 30 chars per requirement
    SUBTITLE_VERTICAL_POS_PCT: float = 0.20 # 20% vertical height
    SUBTITLE_ACTIVE_COLOR: str = "#FF1E1E"
    SUBTITLE_CENSOR_TEXT: bool = True

    # Server
    BACKEND_HOST: str = "localhost"
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 3000

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
for directory in [settings.CONFIG_DIR, settings.BUFFER_DIR, settings.CLIPS_DIR, settings.LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
