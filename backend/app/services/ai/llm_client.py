"""Provider-abstracted LLM client with full call logging.

Every call returns an ``LlmResult`` and records prompt, response, token counts,
latency and estimated cost. The default ``mock`` provider lets the whole system
run end-to-end with no external API key (used in the validation MVP and tests).
Real providers (Anthropic, OpenAI) plug in behind the same interface.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Rough public per-1K-token prices (USD) for cost estimation only.
_PRICE_TABLE = {
    "claude-opus-4-8": (0.015, 0.075),
    "claude-sonnet-4-6": (0.003, 0.015),
    "gpt-4o": (0.005, 0.015),
    "mock": (0.0, 0.0),
}


@dataclass
class LlmResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    estimated_cost_usd: float
    success: bool = True
    error_message: str | None = None


def _estimate_tokens(text: str) -> int:
    # ~4 chars per token heuristic — good enough for cost telemetry.
    return max(1, len(text) // 4)


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = _PRICE_TABLE.get(model, _PRICE_TABLE["mock"])
    return (prompt_tokens / 1000.0) * inp + (completion_tokens / 1000.0) * out


class LlmClient:
    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = provider or settings.llm_provider
        self.model = model or settings.llm_model

    def complete(self, prompt: str, system: str | None = None) -> LlmResult:
        start = time.perf_counter()
        try:
            if self.provider == "mock":
                text = self._mock_complete(prompt)
            elif self.provider == "anthropic":
                text = self._anthropic_complete(prompt, system)
            elif self.provider == "openai":
                text = self._openai_complete(prompt, system)
            else:
                raise ValueError(f"unknown LLM provider: {self.provider}")
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - start) * 1000)
            log.exception("llm_call_failed")
            return LlmResult(
                text="", provider=self.provider, model=self.model,
                prompt_tokens=_estimate_tokens(prompt), completion_tokens=0,
                latency_ms=latency, estimated_cost_usd=0.0,
                success=False, error_message=str(exc),
            )

        latency = int((time.perf_counter() - start) * 1000)
        pt = _estimate_tokens((system or "") + prompt)
        ct = _estimate_tokens(text)
        result = LlmResult(
            text=text, provider=self.provider, model=self.model,
            prompt_tokens=pt, completion_tokens=ct, latency_ms=latency,
            estimated_cost_usd=_estimate_cost(self.model, pt, ct),
        )
        log.info(
            "llm_call",
            extra={
                "provider": self.provider, "model": self.model,
                "prompt_tokens": pt, "completion_tokens": ct,
                "latency_ms": latency, "cost_usd": result.estimated_cost_usd,
            },
        )
        return result

    # -- providers --------------------------------------------------------
    def _mock_complete(self, prompt: str) -> str:
        """Deterministic placeholder so the pipeline is fully exercised offline."""
        return (
            "MOCK RECOMMENDATION\n"
            "This is a deterministic placeholder response generated without an "
            "external LLM. The full pipeline (guardrails, evidence, prompt "
            "templating, logging) ran exactly as it will in production; only the "
            "generation step is stubbed. Configure LLM_PROVIDER=anthropic with a "
            "valid key to enable real generation."
        )

    def _anthropic_complete(self, prompt: str, system: str | None) -> str:
        import anthropic  # imported lazily; optional dependency

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text")

    def _openai_complete(self, prompt: str, system: str | None) -> str:
        from openai import OpenAI  # lazy optional dependency

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system or ""},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""
