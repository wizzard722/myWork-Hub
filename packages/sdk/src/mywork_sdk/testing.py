"""Hulpmiddelen voor tests van apps: inloggen nabootsen zonder core."""

from __future__ import annotations

import uuid

from fastapi import FastAPI

from mywork_sdk.auth import HubUser, current_user

TEST_TENANT = uuid.UUID("00000000-0000-0000-0000-00000000a11a")


def fake_user(role: str = "member", tenant_slug: str = "test") -> HubUser:
    return HubUser(
        user_id=uuid.uuid4(),
        tenant_id=TEST_TENANT,
        tenant_slug=tenant_slug,
        role=role,
        token="test-token",
    )


def login_as(app: FastAPI, user: HubUser | None = None) -> HubUser:
    """Laat ``current_user`` in ``app`` deze gebruiker teruggeven (alleen in tests)."""
    user = user or fake_user()
    app.dependency_overrides[current_user] = lambda: user
    return user
