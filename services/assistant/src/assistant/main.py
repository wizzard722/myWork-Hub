"""Assistent-service: API voor de web-schil (achter de gateway op /api/assistant)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from assistant.agent import Agent, Turn
from assistant.config import Settings, load_settings
from assistant.llm import LLM, AnthropicLLM, LLMError
from assistant.store import Conversation, MemoryStore, RedisStore, Store
from assistant.tools import Registry
from mywork_sdk import HubUser, create_service, current_user
from mywork_sdk.auth import HubAuth, get_auth

VERSION = "0.1.0"


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


class DecisionsIn(BaseModel):
    # tool_use_id -> true (uitvoeren) / false (weigeren)
    decisions: dict[str, bool]


class StatusOut(BaseModel):
    enabled: bool
    model: str | None


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLM | None = None,
    http: httpx.AsyncClient | None = None,
    store: Store | None = None,
) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = http or httpx.AsyncClient(timeout=settings.tool_timeout_seconds)
        app.state.http = client
        app.state.store = store or (
            RedisStore(settings.redis_url, settings.conversation_ttl_seconds)
            if settings.redis_url
            else MemoryStore(settings.conversation_ttl_seconds)
        )
        model = llm
        if model is None and settings.enabled:
            model = AnthropicLLM(
                settings.anthropic_api_key,
                settings.llm_model,
                settings.llm_effort,
                settings.llm_max_tokens,
            )
        app.state.agent = (
            Agent(settings, model, client, Registry(client, settings.core_url)) if model else None
        )
        try:
            yield
        finally:
            if http is None:
                await client.aclose()

    app = create_service(name="assistant", version=VERSION, lifespan=lifespan)
    app.state.settings = settings
    # Tokens controleren met de publieke sleutel van de core.
    auth = HubAuth(settings.core_url)
    app.dependency_overrides.setdefault(get_auth, lambda: auth)

    @app.exception_handler(LLMError)
    async def llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)

    def agent_of(request: Request) -> Agent:
        agent = getattr(request.app.state, "agent", None)
        if agent is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "De assistent staat uit")
        return agent

    def turn_out(turn: Turn) -> dict[str, Any]:
        return asdict(turn)

    async def load(request: Request, user: HubUser, conv_id: str) -> Conversation:
        conv = await request.app.state.store.load(str(user.tenant_id), str(user.user_id), conv_id)
        if conv is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversatie niet gevonden of verlopen")
        return conv

    @app.get("/status", response_model=StatusOut, tags=["assistent"])
    def assistant_status(request: Request, user: HubUser = Depends(current_user)) -> StatusOut:
        enabled = getattr(request.app.state, "agent", None) is not None
        return StatusOut(enabled=enabled, model=settings.llm_model if enabled else None)

    @app.post("/chat", tags=["assistent"])
    async def chat(body: ChatIn, request: Request, user: HubUser = Depends(current_user)) -> dict:
        agent = agent_of(request)
        store: Store = request.app.state.store
        conv = (
            await load(request, user, body.conversation_id)
            if body.conversation_id
            else Conversation()
        )
        ctx = await agent.context(user, request.headers.get("x-request-id"))
        turn = await agent.chat(conv, ctx, body.message)
        await store.save(str(user.tenant_id), str(user.user_id), conv)
        return turn_out(turn)

    @app.post("/chat/{conversation_id}/decisions", tags=["assistent"])
    async def decisions(
        conversation_id: str,
        body: DecisionsIn,
        request: Request,
        user: HubUser = Depends(current_user),
    ) -> dict:
        agent = agent_of(request)
        conv = await load(request, user, conversation_id)
        ctx = await agent.context(user, request.headers.get("x-request-id"))
        turn = await agent.decide(conv, ctx, body.decisions)
        await request.app.state.store.save(str(user.tenant_id), str(user.user_id), conv)
        return turn_out(turn)

    @app.delete("/chat/{conversation_id}", status_code=204, tags=["assistent"])
    async def forget(
        conversation_id: str, request: Request, user: HubUser = Depends(current_user)
    ) -> None:
        await request.app.state.store.delete(
            str(user.tenant_id), str(user.user_id), conversation_id
        )

    return app


app = create_app()
