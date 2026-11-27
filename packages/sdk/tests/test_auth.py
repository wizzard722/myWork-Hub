import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from mywork_sdk import HubAuth, HubUser, current_user, require_role
from mywork_sdk.auth import InvalidToken, get_auth
from mywork_sdk.testing import fake_user, login_as

KEY = Ed25519PrivateKey.generate()
JWK = {**jwt.algorithms.OKPAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1"}


def token(role="member", key=KEY, kid="k1", minutes=5, aud="mywork-hub"):
    now = datetime.now(UTC)
    claims = {
        "sub": str(uuid.uuid4()),
        "tid": str(uuid.uuid4()),
        "tslug": "acme",
        "role": role,
        "aud": aud,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"kid": kid})


def make_auth(calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request.url.path)
        return httpx.Response(200, json={"keys": [JWK]})

    return HubAuth("http://core", http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_verify_valid_token():
    user = make_auth().verify(token("admin"))
    assert user.role == "admin" and user.tenant_slug == "acme"


@pytest.mark.parametrize(
    "bad",
    [
        lambda: token(key=Ed25519PrivateKey.generate()),
        lambda: token(minutes=-1),
        lambda: token(aud="iets-anders"),
        lambda: token(kid="onbekend"),
        lambda: token(role="superheld"),
        lambda: "geen-token",
    ],
)
def test_invalid_tokens(bad):
    with pytest.raises(InvalidToken):
        make_auth().verify(bad())


def test_jwks_is_cached():
    calls = []
    auth = make_auth(calls)
    auth.verify(token())
    auth.verify(token())
    assert calls == ["/.well-known/jwks.json"]


def app_with_routes(auth):
    app = FastAPI()
    app.dependency_overrides[get_auth] = lambda: auth

    @app.get("/me")
    def me(user: HubUser = Depends(current_user)):
        return {"role": user.role}

    @app.get("/admin")
    def admin(user: HubUser = Depends(require_role("admin"))):
        return {"ok": True}

    return app


def test_dependencies():
    client = TestClient(app_with_routes(make_auth()))
    assert client.get("/me").status_code == 401
    member = {"Authorization": f"Bearer {token('member')}"}
    assert client.get("/me", headers=member).json() == {"role": "member"}
    assert client.get("/admin", headers=member).status_code == 403
    admin = {"Authorization": f"Bearer {token('admin')}"}
    assert client.get("/admin", headers=admin).status_code == 200


def test_testing_helpers():
    app = app_with_routes(make_auth())
    login_as(app, fake_user("owner"))
    assert TestClient(app).get("/admin").status_code == 200
