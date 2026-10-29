"""
Problem2Project AI — Application Configuration
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Problem2Project AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = "CHANGE_ME_GENERATE_A_RANDOM_SECRET_KEY"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str = ""

    # AI Provider
    AI_PROVIDER: str = "openrouter"  # openrouter | google | anthropic
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "meta-llama/llama-3.3-70b-instruct"
    GOOGLE_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Web Search
    SEARCH_PROVIDER: str = "google_custom"  # google_custom | serper | brave
    SEARCH_API_KEY: Optional[str] = None
    SEARCH_ENGINE_ID: Optional[str] = None

    # GitHub
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/integrations/github/callback"

    # Execution
    EXECUTION_TIMEOUT_SECONDS: int = 30
    EXECUTION_MAX_RETRIES: int = 3

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
    SANDBOX_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "sandboxes"

    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{(Path(__file__).resolve().parent.parent / 'data' / 'problem2project.db').as_posix()}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def setup_directories(self):
        """Create necessary directories on startup."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def ai_configured(self) -> bool:
        if self.OPENROUTER_API_KEY and self.OPENROUTER_API_KEY != "your-openrouter-api-key-here":
            return True
        if self.AI_PROVIDER == "google":
            return bool(self.GOOGLE_API_KEY and self.GOOGLE_API_KEY != "your-google-api-key-here")
        elif self.AI_PROVIDER == "anthropic":
            return bool(self.ANTHROPIC_API_KEY and self.ANTHROPIC_API_KEY != "your-anthropic-api-key-here")
        return bool(self.OPENROUTER_API_KEY)

    @property
    def search_configured(self) -> bool:
        return bool(
            self.SEARCH_API_KEY
            and self.SEARCH_API_KEY != "your-search-api-key-here"
        )

    @property
    def github_configured(self) -> bool:
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET)


settings = Settings()
