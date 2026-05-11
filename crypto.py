import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

SALT = b"vault_bot_personal_salt_2025_fixed"


def _get_fernet(master_password: str) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(master_password.encode()))
    return Fernet(key)


def encrypt(text: str, master_password: str) -> str:
    try:
        f = _get_fernet(master_password)
        encrypted = f.encrypt(text.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Ошибка шифрования: {e}")
        raise


def decrypt(encrypted_text: str, master_password: str) -> str:
    try:
        f = _get_fernet(master_password)
        decrypted = f.decrypt(encrypted_text.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Ошибка расшифровки: {e}")
        raise
