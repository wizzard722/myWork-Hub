"""Wachtwoorden, toegangstokens (JWT, EdDSA) en refresh-tokens.

- Wachtwoorden: Argon2id.
- Toegangstokens: kortlevend JWT, ondertekend met een Ed25519-sleutel van de core.
  Apps controleren ze met de publieke sleutel via ``/.well-known/jwks.json``.
- Refresh-tokens: willekeurig, alleen de SHA-256-hash staat in de database.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.config import Settings

log = logging.getLogger(__name__)

AUDIENCE = "mywork-hub"
ROLES = ("owner", "admin", "member")
MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()
# Gebruikt om ook bij een onbekend e-mailadres even lang te rekenen (geen timing-lek).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_refresh_token() -> tuple[str, str]:
    """Geeft (token, hash). Alleen de hash wordt opgeslagen."""
    token = secrets.token_urlsafe(32)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    """De ingelogde gebruiker, zoals vastgelegd in het toegangstoken."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_slug: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


class InvalidToken(Exception):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class TokenSigner:
    def __init__(self, private_key: Ed25519PrivateKey, issuer: str, ttl: timedelta) -> None:
        self._key = private_key
        self.issuer = issuer
        self.ttl = ttl
        raw = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self._public_raw = raw
        self.kid = hashlib.sha256(raw).hexdigest()[:16]
        self._public_key = private_key.public_key()

    @classmethod
    def from_settings(cls, settings: Settings) -> TokenSigner:
        pem = settings.jwt_private_key
        if not pem and settings.jwt_private_key_file:
            pem = Path(settings.jwt_private_key_file).read_text()
        if pem:
            key = serialization.load_pem_private_key(pem.encode(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("HUB_JWT_PRIVATE_KEY moet een Ed25519-sleutel zijn")
        elif settings.is_production:
            raise ValueError("HUB_JWT_PRIVATE_KEY of HUB_JWT_PRIVATE_KEY_FILE is verplicht")
        else:
            log.warning("Geen JWT-sleutel ingesteld: tijdelijke sleutel (alleen ontwikkeling)")
            key = Ed25519PrivateKey.generate()
        return cls(key, settings.public_url, timedelta(minutes=settings.access_token_minutes))

    def issue(self, principal: Principal) -> str:
        now = datetime.now(UTC)
        claims = {
            "iss": self.issuer,
            "aud": AUDIENCE,
            "sub": str(principal.user_id),
            "tid": str(principal.tenant_id),
            "tslug": principal.tenant_slug,
            "role": principal.role,
            "iat": now,
            "exp": now + self.ttl,
            "jti": secrets.token_hex(8),
        }
        return jwt.encode(claims, self._key, algorithm="EdDSA", headers={"kid": self.kid})

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=["EdDSA"],
                audience=AUDIENCE,
                issuer=self.issuer,
                options={"require": ["exp", "sub", "tid", "role"]},
            )
            role = claims["role"]
            if role not in ROLES:
                raise InvalidToken("onbekende rol")
            return Principal(
                user_id=uuid.UUID(claims["sub"]),
                tenant_id=uuid.UUID(claims["tid"]),
                tenant_slug=claims.get("tslug", ""),
                role=role,
            )
        except (jwt.PyJWTError, ValueError, KeyError) as exc:
            raise InvalidToken(str(exc)) from exc

    def jwks(self) -> dict:
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": _b64url(self._public_raw),
                    "kid": self.kid,
                    "alg": "EdDSA",
                    "use": "sig",
                }
            ]
        }


def generate_private_key_pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
