"""
ProblemPilot AI — Application Configuration
Unified AI product combining Problem2Project AI and ProblemPilot AI.
"""
import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional, List


# Generate fallback secret key if none provided
_FALLBACK_SECRET = secrets.token_urlsafe(32)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "ProblemPilot AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = _FALLBACK_SECRET
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    ALGORITHM: str = "HS256"
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8501",
    ]

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

    # GitHub Integration
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/integrations/github/callback"
    GITHUB_OAUTH_STATE_SECRET: Optional[str] = None
    GITHUB_TOKEN_ENCRYPTION_KEY: Optional[str] = None
    GITHUB_PERSONAL_ACCESS_TOKEN: Optional[str] = None

    # Cloud Hosting Providers
    VERCEL_TOKEN: Optional[str] = None
    VERCEL_TEAM_ID: Optional[str] = None
    VERCEL_PROJECT_ID: Optional[str] = None
    RENDER_API_KEY: Optional[str] = None
    RENDER_SERVICE_ID: Optional[str] = None

    # Execution & Isolation
    EXECUTION_TIMEOUT_SECONDS: int = 30
    EXECUTION_MAX_RETRIES: int = 3
    MAX_MEMORY_MB: int = 512

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
        if self.OPENROUTER_API_KEY and self.OPENROUTER_API_KEY not in ("your-openrouter-api-key-here", ""):
            return True
        if self.AI_PROVIDER == "google":
            return bool(self.GOOGLE_API_KEY and self.GOOGLE_API_KEY not in ("your-google-api-key-here", ""))
        elif self.AI_PROVIDER == "anthropic":
            return bool(self.ANTHROPIC_API_KEY and self.ANTHROPIC_API_KEY not in ("your-anthropic-api-key-here", ""))
        return bool(self.OPENROUTER_API_KEY or self.GOOGLE_API_KEY or self.ANTHROPIC_API_KEY)

    @property
    def search_configured(self) -> bool:
        return bool(
            self.SEARCH_API_KEY
            and self.SEARCH_API_KEY not in ("your-search-api-key-here", "")
        )

    @property
    def github_configured(self) -> bool:
        return bool(
            (self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET)
            or self.GITHUB_PERSONAL_ACCESS_TOKEN
        )

    @property
    def vercel_configured(self) -> bool:
        return bool(self.VERCEL_TOKEN and self.VERCEL_TOKEN not in ("your-vercel-token-here", ""))

    @property
    def render_configured(self) -> bool:
        return bool(self.RENDER_API_KEY and self.RENDER_API_KEY not in ("your-render-api-key-here", ""))

    def get_missing_github_oauth_vars(self) -> List[str]:
        """Return list of missing required GitHub OAuth configuration variables."""
        missing = []
        if not self.GITHUB_CLIENT_ID:
            missing.append("GITHUB_CLIENT_ID")
        if not self.GITHUB_CLIENT_SECRET:
            missing.append("GITHUB_CLIENT_SECRET")
        if not self.GITHUB_REDIRECT_URI:
            missing.append("GITHUB_REDIRECT_URI")
        return missing

    def get_missing_vercel_vars(self) -> List[str]:
        """Return list of missing required Vercel configuration variables."""
        missing = []
        if not self.VERCEL_TOKEN or self.VERCEL_TOKEN in ("your-vercel-token-here", ""):
            missing.append("VERCEL_TOKEN")
        return missing


settings = Settings()
