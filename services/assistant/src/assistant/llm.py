"""Koppeling met het taalmodel (Claude via de Anthropic API).

De rest van de assistent praat alleen met ``LLM.create``; in tests wordt een nep-model
gebruikt. Antwoorden worden als gewone dicts teruggegeven (``content``,
``stop_reason``), zodat ze in Redis bewaard en ongewijzigd teruggestuurd kunnen worden.
"""

from __future__ import annotations

from typing import Any, Protocol

import anthropic


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLM(Protocol):
    async def create(
        self, *, system: str, tools: list[dict], messages: list[dict]
    ) -> dict[str, Any]: ...


class AnthropicLLM:
    def __init__(
        self,
        api_key: str,
        model: str,
        effort: str,
        max_tokens: int,
        http_client: anthropic.DefaultAsyncHttpxClient | None = None,
    ) -> None:
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key, max_retries=2, http_client=http_client
        )
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    async def create(self, *, system: str, tools: list[dict], messages: list[dict]) -> dict:
        try:
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                tools=tools,
                messages=messages,
                output_config={"effort": self.effort},
                # Automatische prompt-caching van het vaste deel (tools + systeemprompt).
                cache_control={"type": "ephemeral"},
                # Bij een weigering door de veiligheidsfilters automatisch een ander model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise LLMError("De assistent is even druk; probeer het zo opnieuw.", 429) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Fout van het taalmodel ({exc.status_code}).", 502) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Het taalmodel is niet bereikbaar.", 502) from exc
        return {
            # Ongewijzigd bewaren (ook thinking-blokken) om terug te sturen.
            "content": [
                block.model_dump(mode="json", exclude_none=True) for block in response.content
            ],
            "stop_reason": response.stop_reason,
        }
