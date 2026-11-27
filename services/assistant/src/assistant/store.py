"""Opslag van conversaties: Redis (productie) of geheugen (ontwikkeling/tests).

De sleutel bevat klant en gebruiker: een conversatie is alleen terug te vinden door de
gebruiker die hem begon.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Protocol

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    # Wachtend op bevestiging: automatisch uitgevoerde resultaten en te bevestigen acties.
    pending_results: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirm: list[dict[str, Any]] = Field(default_factory=list)


def _key(tenant_id: str, user_id: str, conversation_id: str) -> str:
    return f"assistant:conv:{tenant_id}:{user_id}:{conversation_id}"


class Store(Protocol):
    async def load(self, tenant_id: str, user_id: str, conv_id: str) -> Conversation | None: ...
    async def save(self, tenant_id: str, user_id: str, conv: Conversation) -> None: ...
    async def delete(self, tenant_id: str, user_id: str, conv_id: str) -> None: ...


class MemoryStore:
    def __init__(self, ttl: int) -> None:
        self.ttl = ttl
        self._data: dict[str, tuple[float, str]] = {}

    async def load(self, tenant_id, user_id, conv_id):
        item = self._data.get(_key(tenant_id, user_id, conv_id))
        if item is None or item[0] < time.monotonic():
            return None
        return Conversation.model_validate_json(item[1])

    async def save(self, tenant_id, user_id, conv):
        key = _key(tenant_id, user_id, conv.id)
        self._data[key] = (time.monotonic() + self.ttl, conv.model_dump_json())

    async def delete(self, tenant_id, user_id, conv_id):
        self._data.pop(_key(tenant_id, user_id, conv_id), None)


class RedisStore:
    def __init__(self, url: str, ttl: int) -> None:
        import redis.asyncio as redis

        self.redis = redis.from_url(url)
        self.ttl = ttl

    async def load(self, tenant_id, user_id, conv_id):
        raw = await self.redis.get(_key(tenant_id, user_id, conv_id))
        return Conversation.model_validate(json.loads(raw)) if raw else None

    async def save(self, tenant_id, user_id, conv):
        await self.redis.set(_key(tenant_id, user_id, conv.id), conv.model_dump_json(), ex=self.ttl)

    async def delete(self, tenant_id, user_id, conv_id):
        await self.redis.delete(_key(tenant_id, user_id, conv_id))
