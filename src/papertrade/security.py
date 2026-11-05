"""Short-lived administrator sessions; credential values never enter audit records."""
import base64
import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from papertrade.config import Settings

password_hasher = PasswordHasher()


def issue_token(settings: Settings, lifetime=3600):
    key = settings.api_token.get_secret_value()
    if len(key) < 32:
        raise ValueError("Configure PT_API_TOKEN with at least 32 characters")
    payload = f"{int(time.time()) + lifetime}:{secrets.token_hex(16)}"
    sig = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()


def valid_token(token: str, settings: Settings) -> bool:
    key = settings.api_token.get_secret_value()
    if len(key) < 32:
        return False
    # The configured machine token is only sent by local CLI/API clients over the private interface.
    if secrets.compare_digest(token.encode(), key.encode()):
        return True
    try:
        expiry, nonce, signature = base64.urlsafe_b64decode(token).decode().split(":")
        expected = hmac.new(key.encode(), f"{expiry}:{nonce}".encode(), hashlib.sha256).hexdigest()
        return int(time.time()) < int(expiry) <= int(time.time()) + 3600 and secrets.compare_digest(signature, expected)
    except (ValueError, UnicodeError):
        return False


def valid_login(username, password, settings):
    encoded = settings.admin_password_hash.get_secret_value()
    try:
        verified = password_hasher.verify(encoded, password)
        return verified and secrets.compare_digest(username.encode(), settings.admin_username.encode())
    except (VerificationError, InvalidHashError):
        return False
