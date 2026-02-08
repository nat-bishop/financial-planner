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

    # Gemini
    gemini_api_key: str = ""
    gemini_categorize_model: str = "gemini-2.0-flash"
    gemini_temperature: float = 0.1
    gemini_max_tokens: int = 4096

    # Categorization
    categorize_batch_size: int = 30
    categorize_limit: int = 100
    categorize_confidence_threshold: float = 0.7


settings = Settings()
