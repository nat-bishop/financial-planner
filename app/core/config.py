from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/finance.db"

    # Encryption key for credentials (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    encryption_key: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    # Browser provider
    browser_headless: bool = False

    # Gemini
    gemini_api_key: str = ""


settings = Settings()

# Application defaults — not env-overridable
GEMINI_CATEGORIZE_MODEL = "gemini-3-flash-preview"
GEMINI_TEMPERATURE = 0.1
GEMINI_MAX_TOKENS = 4096
CATEGORIZE_BATCH_SIZE = 30
CATEGORIZE_LIMIT = 100
CATEGORIZE_CONFIDENCE_THRESHOLD = 0.7
