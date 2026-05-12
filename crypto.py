import hashlib
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet


def derive_key(master_password: str, user_id: int) -> bytes:
    """Персональный ключ на основе мастер-пароля + user_id."""
    salt = f"vault_salt_{user_id}_2025".encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200_000,
        backend=default_backend(),
    )
    raw = kdf.derive(master_password.encode())
    return base64.urlsafe_b64encode(raw)


def encrypt(text: str, key: bytes) -> str:
    """Шифрует строку ключом Fernet."""
    return Fernet(key).encrypt(text.encode()).decode()


def decrypt(token: str, key: bytes) -> str:
    """Расшифровывает строку ключом Fernet."""
    return Fernet(key).decrypt(token.encode()).decode()


def hash_password(password: str, user_id: int) -> str:
    """SHA-256 хэш для хранения мастер-пароля (zero-knowledge)."""
    return hashlib.sha256(f"{password}:{user_id}:vault2025".encode()).hexdigest()


def hash_pin(pin: str, user_id: int) -> str:
    """SHA-256 хэш пин-кода."""
    return hashlib.sha256(f"{pin}:{user_id}:pin".encode()).hexdigest()
