import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_encryption_key: bytes | None = None


def _get_encryption_key() -> bytes:
    global _encryption_key
    if _encryption_key is None:
        _encryption_key = base64.b64decode(settings.field_encryption_key)
    return _encryption_key


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({**data, "exp": expire, "type": "access"}, settings.secret_key, algorithm="HS256")


def create_refresh_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    jti = secrets.token_hex(16)
    return jwt.encode({**data, "exp": expire, "type": "refresh", "jti": jti}, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError:
        return {}


def encrypt_field(plaintext: str) -> str:
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_field(encrypted: str) -> str:
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()


_IP_SALT = os.getenv("IP_HASH_SALT", "backbone-statement-recon-salt")


def hash_ip(ip: str) -> str:
    return hashlib.sha256(f"{_IP_SALT}:{ip}".encode()).hexdigest()[:16]
