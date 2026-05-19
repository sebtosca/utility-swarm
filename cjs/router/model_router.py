import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cjs.config import Settings
from cjs.observability.audit import AuditLogger
from cjs.observability.logging import get_logger

logger = get_logger(__name__)

FALLBACK_MODEL = "claude-haiku-4-5-20251001"
CIRCUIT_THRESHOLD = 3


@dataclass
class RouterResult:
    content: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    model: str
    thinking: str | None = None


class ModelRouter:
    def __init__(
        self,
        run_id: str,
        run_folder: Path,
        config: Settings,
        audit: AuditLogger | None = None,
    ) -> None:
        self.run_id = run_id
        self._run_folder = run_folder
        self._config = config
        self._audit = audit or AuditLogger(run_folder, run_id)
        self._client = anthropic.Anthropic(
            api_key=os.environ.get(config.auth.api_key_env, ""),
        )
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()

    # --- public call surface ---

    def call_text(
        self, system: str, user: str, node: str, agent: str | None = None
    ) -> RouterResult:
        return self._dispatch(
            system=system,
            user=user,
            node=node,
            agent=agent,
            preferred=self._config.models.text,
        )

    def call_vision(
        self,
        system: str,
        user: str,
        images: list[Path],
        node: str,
        agent: str | None = None,
    ) -> RouterResult:
        image_blocks = [self._encode_image(p) for p in images]
        return self._dispatch(
            system=system,
            user=user,
            node=node,
            agent=agent,
            preferred=self._config.models.vision,
            extra_content=image_blocks,
        )

    def call_extended_thinking(
        self, system: str, user: str, node: str, agent: str | None = None
    ) -> RouterResult:
        return self._dispatch(
            system=system,
            user=user,
            node=node,
            agent=agent,
            preferred=self._config.models.extended_thinking,
            thinking=True,
        )

    def call_structured(
        self,
        system: str,
        user: str,
        node: str,
        schema: dict,
        schema_name: str,
        agent: str | None = None,
        images: list[Path] | None = None,
    ) -> RouterResult:
        tool_def = {
            "name": schema_name,
            "description": f"Submit the structured {schema_name} output.",
            "input_schema": schema,
        }
        image_blocks = [self._encode_image(p) for p in images] if images else None
        preferred = self._config.models.vision if images else self._config.models.text
        return self._dispatch(
            system=system,
            user=user,
            node=node,
            agent=agent,
            preferred=preferred,
            extra_content=image_blocks,
            tools=[tool_def],
            tool_choice={"type": "tool", "name": schema_name},
        )

    # --- circuit breaker ---

    def _active_model(self, preferred: str) -> str:
        with self._lock:
            if self._failures.get(preferred, 0) >= CIRCUIT_THRESHOLD:
                return FALLBACK_MODEL
        return preferred

    def _record_success(self, model: str) -> None:
        with self._lock:
            self._failures[model] = 0

    def _record_failure(self, model: str) -> None:
        with self._lock:
            self._failures[model] = self._failures.get(model, 0) + 1

    # --- call orchestration ---

    def _dispatch(
        self,
        *,
        system: str,
        user: str,
        node: str,
        agent: str | None,
        preferred: str,
        extra_content: list | None = None,
        thinking: bool = False,
        tools: list | None = None,
        tool_choice: dict | None = None,
    ) -> RouterResult:
        model = self._active_model(preferred)
        prompt = f"{system}\n\n{user}"
        t0 = time.perf_counter()

        try:
            result = self._call_with_retry(
                system=system,
                user=user,
                model=model,
                extra_content=extra_content or [],
                thinking=thinking,
                tools=tools or [],
                tool_choice=tool_choice,
            )
            self._record_success(preferred)
        except Exception as exc:
            self._record_failure(preferred)
            latency_ms = (time.perf_counter() - t0) * 1000
            self._audit.log(
                node=node,
                agent=agent,
                model=model,
                prompt=prompt,
                tokens_in=0,
                tokens_out=0,
                latency_ms=latency_ms,
                error=str(exc),
            )
            logger.error("llm_call_failed", node=node, model=model, error=str(exc))
            raise

        latency_ms = (time.perf_counter() - t0) * 1000
        result.latency_ms = latency_ms

        self._audit.log(
            node=node,
            agent=agent,
            model=result.model,
            prompt=prompt,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=latency_ms,
        )
        logger.info(
            "llm_call_ok",
            node=node,
            model=result.model,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=round(latency_ms, 1),
        )

        if model != preferred:
            self._write_escalation(node=node, from_model=preferred, to_model=model)

        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type(anthropic.APIError),
        reraise=True,
    )
    def _call_with_retry(
        self,
        *,
        system: str,
        user: str,
        model: str,
        extra_content: list,
        thinking: bool,
        tools: list | None = None,
        tool_choice: dict | None = None,
    ) -> RouterResult:
        user_content: list = extra_content + [{"type": "text", "text": user}]
        kwargs: dict = {
            "model": model,
            "max_tokens": 8192,
            "system": system,
            "messages": [{"role": "user", "content": user_content}],
            "extra_headers": {"X-Run-ID": self.run_id},
        }
        if thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 5000}
            kwargs["max_tokens"] = 16000
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        response = self._client.messages.create(**kwargs)

        text_content = ""
        thinking_content: str | None = None
        for block in response.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "thinking":
                thinking_content = block.thinking
            elif block.type == "tool_use":
                text_content = json.dumps(block.input)

        return RouterResult(
            content=text_content,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            latency_ms=0.0,
            model=response.model,
            thinking=thinking_content,
        )

    # --- helpers ---

    @staticmethod
    def _encode_image(path: Path) -> dict:
        suffix = path.suffix.lower().lstrip(".")
        media_map = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        media_type = media_map.get(suffix, "image/jpeg")
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }

    def _write_escalation(self, *, node: str, from_model: str, to_model: str) -> None:
        from cjs.escalation.events import write_escalation_event
        write_escalation_event(
            self._run_folder / "escalations.jsonl",
            type="model_fallback",
            run_id=self.run_id,
            node=node,
            from_model=from_model,
            to_model=to_model,
            reason="circuit_open",
        )
        logger.warning("model_fallback", from_model=from_model, to_model=to_model, node=node)
        logger.warning("model_fallback", from_model=from_model, to_model=to_model, node=node)
