"""Password hashing, session tokens and role-checking dependencies.

Passwords: PBKDF2-HMAC-SHA256 with a random 16-byte salt and 310,000 iterations
(Python's standard-library hashlib; no plaintext is ever stored).
Sessions: a random bearer token is given to the client; only its SHA-256 hash is
stored in the database, so a leaked database does not leak live tokens.
"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AuthSession, User, utcnow

ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, role: str, user: Optional[User] = None, worker_name: Optional[str] = None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=_hash_token(token), role=role, user_id=user.id if user else None,
                       worker_name=worker_name, expires_at=utcnow() + timedelta(hours=settings.session_hours)))
    db.commit()
    return token


def end_session(db: Session, token: str) -> None:
    db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).delete()
    db.commit()


def check_admin_code(code: str) -> bool:
    """Constant-time comparison with ADMIN_ACCESS_CODE. An unset code never matches."""
    if not settings.admin_access_code:
        return False
    return hmac.compare_digest(code.encode(), settings.admin_access_code.encode())


class LoginThrottle:
    """In-memory limit on failed admin-code attempts per client address (demo-level)."""

    def __init__(self):
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        window = settings.admin_login_lockout_s
        self._fails[key] = [t for t in self._fails.get(key, []) if now - t < window]
        return self._fails[key]

    def locked_for(self, key: str, now: float) -> float:
        recent = self._recent(key, now)
        if len(recent) >= settings.admin_login_max_failures:
            return max(0.0, settings.admin_login_lockout_s - (now - recent[0]))
        return 0.0

    def fail(self, key: str, now: float):
        self._recent(key, now).append(now)

    def clear(self, key: str):
        self._fails.pop(key, None)


admin_throttle = LoginThrottle()


def check_worker_code(code: str) -> bool:
    if not settings.worker_code:
        return False
    return hmac.compare_digest(code.encode(), settings.worker_code.encode())


@dataclass
class Principal:
    role: str
    user: Optional[User]
    worker_name: Optional[str]
    token: str

    @property
    def actor(self) -> str:
        if self.role == "worker":
            return f"worker:{self.worker_name}"
        if self.role == "admin" and not self.user:
            return "admin:console"
        return f"{self.role}:{self.user.email}" if self.user else self.role


bearer = HTTPBearer(auto_error=False, description="Token from /api/auth/login or /api/auth/worker")


def optional_principal(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                       db: Session = Depends(get_db)) -> Optional[Principal]:
    token = creds.credentials if creds else None
    if not token:
        return None
    sess = db.query(AuthSession).filter(AuthSession.token_hash == _hash_token(token)).first()
    if not sess or sess.expires_at < utcnow():
        return None
    return Principal(role=sess.role, user=sess.user, worker_name=sess.worker_name, token=token)


def require_principal(p: Optional[Principal] = Depends(optional_principal)) -> Principal:
    if p is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in to continue.")
    return p


def require_customer(p: Principal = Depends(require_principal)) -> Principal:
    if p.role not in ("customer", "admin") or p.user is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A customer account is required.")
    return p


def require_staff(p: Principal = Depends(require_principal)) -> Principal:
    """Warehouse workers and admins."""
    if p.role not in ("worker", "admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Warehouse access is required.")
    return p


def require_admin(p: Principal = Depends(require_principal)) -> Principal:
    if p.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access is required.")
    return p
