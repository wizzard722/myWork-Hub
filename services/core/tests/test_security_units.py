"""Unit-tests zonder database: subdomeinen, wachtwoorden en tokens."""

import uuid
from datetime import timedelta

import pytest

from core.config import Settings
from core.security import (
    InvalidToken,
    Principal,
    TokenSigner,
    generate_private_key_pem,
    hash_password,
    verify_password,
)
from core.tenancy import slug_from_host, valid_slug


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("acme.myworkhub.nl", "acme"),
        ("ACME.myworkhub.nl:443", "acme"),
        ("acme.myworkhub.nl.", "acme"),
        ("myworkhub.nl", None),
        ("www.myworkhub.nl", None),
        ("a.b.myworkhub.nl", None),
        ("acme.anders.nl", None),
        ("evilmyworkhub.nl", None),
        ("127.0.0.1:8080", None),
        ("[::1]:8080", None),
        (None, None),
    ],
)
def test_slug_from_host(host, expected):
    assert slug_from_host(host, "myworkhub.nl") == expected


def test_slug_from_localhost_subdomain():
    assert slug_from_host("acme.localhost:8080", "localhost") == "acme"
    assert slug_from_host("localhost:8080", "localhost") is None


@pytest.mark.parametrize("slug", ["ab", "1acme", "acme-", "a--b", "admin", "Acme"])
def test_invalid_slugs(slug):
    assert not valid_slug(slug)


def test_password_hashing():
    hashed = hash_password("een-lang-wachtwoord")
    assert verify_password(hashed, "een-lang-wachtwoord")
    assert not verify_password(hashed, "verkeerd")
    assert not verify_password(None, "een-lang-wachtwoord")
    assert not verify_password("geen-hash", "x")


def principal():
    return Principal(uuid.uuid4(), uuid.uuid4(), "acme", "admin")


def test_token_roundtrip():
    signer = TokenSigner.from_settings(Settings(jwt_private_key=generate_private_key_pem()))
    p = principal()
    assert signer.verify(signer.issue(p)) == p


def test_token_from_other_key_rejected():
    a = TokenSigner.from_settings(Settings())
    b = TokenSigner.from_settings(Settings())
    with pytest.raises(InvalidToken):
        b.verify(a.issue(principal()))


def test_expired_token_rejected():
    signer = TokenSigner.from_settings(Settings())
    signer.ttl = timedelta(seconds=-1)
    with pytest.raises(InvalidToken):
        signer.verify(signer.issue(principal()))


def test_production_requires_key():
    with pytest.raises(ValueError):
        TokenSigner.from_settings(Settings(environment="production"))


def test_key_must_be_ed25519():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )
    with pytest.raises(ValueError):
        TokenSigner.from_settings(Settings(jwt_private_key=pem))
