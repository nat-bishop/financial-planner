from cryptography.fernet import Fernet

from app.config import settings

_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.encryption_key:
            raise ValueError(
                "ENCRYPTION_KEY not set. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        _fernet = Fernet(settings.encryption_key.encode())
    return _fernet


def reset_fernet() -> None:
    """Reset cached Fernet instance. Used for testing with different keys."""
    global _fernet
    _fernet = None


def encrypt(data: str) -> str:
    """Encrypt a string using Fernet symmetric encryption."""
    return get_fernet().encrypt(data.encode()).decode()


def decrypt(data: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    return get_fernet().decrypt(data.encode()).decode()
